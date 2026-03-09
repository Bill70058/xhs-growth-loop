#!/usr/bin/env python3
import json
import os
import random
import re
import sqlite3
import time
import uuid
from datetime import date
from urllib import error, request

from policy_bandit import arm_key_of, choose_arm_thompson, ensure_policy_tables

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV = os.path.join(ROOT, "config", ".env")


def load_env(path):
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    # Allow runtime overrides from process env (useful for CI/automation)
    for key, value in os.environ.items():
        if key in env or key.startswith("OPENCLAW_") or key in ("KEYWORD", "CANDIDATE_COUNT", "XHS_ACCOUNT"):
            env[key] = value
    return env


def extract_feed_title(feed):
    if not isinstance(feed, dict):
        return ""
    for key in ("title", "displayTitle"):
        value = feed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    note_card = feed.get("noteCard")
    if isinstance(note_card, dict):
        for key in ("displayTitle", "title"):
            value = note_card.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def load_market_seeds(summary, fallback_topic):
    seeds = []
    market = summary.get("market_learning", {})
    by_keyword = market.get("by_keyword", [])
    if not isinstance(by_keyword, list):
        return seeds

    for item in by_keyword:
        if not isinstance(item, dict):
            continue
        keyword = item.get("keyword") or fallback_topic
        path = item.get("file")
        if not path or not os.path.exists(path):
            continue
        try:
            payload = json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            continue
        feeds = payload.get("feeds", [])
        if not isinstance(feeds, list):
            continue
        for feed in feeds:
            title = extract_feed_title(feed)
            if title:
                seeds.append({"keyword": keyword, "title": title})
    return seeds


def normalize_seed_title(text, limit=20):
    cleaned = (text or "").replace("\n", " ").strip()
    for ch in ("（", "）", "(", ")", "【", "】", "[", "]"):
        cleaned = cleaned.replace(ch, "")
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def env_truthy(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def call_openclaw_candidates(
    url,
    timeout_seconds,
    n,
    topic,
    summary,
    own_data_status,
    market_seeds,
    request_id,
    prompt_version,
):
    seed_titles = []
    for s in market_seeds[:20]:
        title = str(s.get("title", "")).strip()
        if title:
            seed_titles.append({"keyword": s.get("keyword", topic), "title": title})

    payload = {
        "request_id": request_id,
        "prompt_version": prompt_version,
        "topic": topic,
        "candidate_count": n,
        "own_data_status": own_data_status,
        "summary": summary,
        "market_seed_titles": seed_titles,
        "constraints": {
            "title_max_chars": 30,
            "tags_min": 3,
            "tags_max": 5,
        },
    }
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Idempotency-Key": request_id,
            "X-OpenClaw-Prompt-Version": prompt_version,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("openclaw response is not object")
    raw_candidates = parsed.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("openclaw response has empty candidates")
    return raw_candidates


def quality_check_candidates(candidates):
    issues = []
    ok = True
    for idx, c in enumerate(candidates, start=1):
        title = str(c.get("title", "")).strip()
        content = str(c.get("content", "")).strip()
        tags = str(c.get("tags", "")).strip()
        if len(title) < 8:
            ok = False
            issues.append(f"candidate_{idx}:title_too_short")
        if len(title) > 40:
            ok = False
            issues.append(f"candidate_{idx}:title_too_long")
        if "1)" not in content or "2)" not in content:
            issues.append(f"candidate_{idx}:content_not_structured")
        if "#" not in tags:
            issues.append(f"candidate_{idx}:missing_tags")
    return ok, issues


def normalize_openclaw_candidates(raw_candidates, fallback_topic, generation_mode):
    candidates = []
    for idx, item in enumerate(raw_candidates, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        if not title or not content:
            continue
        topic = str(item.get("topic", fallback_topic) or fallback_topic).strip() or fallback_topic
        tags = item.get("tags", "")
        if isinstance(tags, list):
            tags = " ".join([str(x).strip() for x in tags if str(x).strip()])
        tags = str(tags).strip()
        if not tags:
            tags = f"#{topic} #经验分享 #实用"
        candidates.append(
            {
                "candidate_no": idx,
                "topic": topic,
                "title": title,
                "content": content,
                "tags": tags,
                "generation_mode": generation_mode,
                "openclaw_source": True,
            }
        )
    return candidates


def build_local_template_candidates(n, topic, summary, own_data_status, market_seeds):
    use_market_mode = own_data_status.startswith("empty_today") and bool(market_seeds)
    generation_mode = "market_seeded" if use_market_mode else "template_baseline"
    hooks = [
        "我用这个方法把效率翻了 2 倍",
        "别再盲目做了，这 3 个步骤就够",
        "我复盘了 30 天，结果超预期",
        "这条是给想快速上手的人",
    ]
    angles = ["清单法", "复盘法", "模板法", "避坑法"]
    ctas = ["要我发模板就在评论区扣1", "收藏这条，明天直接照着做", "需要完整版本我再更新下一篇"]

    candidates = []
    for i in range(1, n + 1):
        angle = random.choice(angles)
        current_topic = topic
        if use_market_mode:
            seed = market_seeds[(i - 1) % len(market_seeds)]
            current_topic = seed.get("keyword") or topic
            seed_title = seed.get("title", "").replace("\n", " ").strip()
            short_seed_title = normalize_seed_title(seed_title, limit=20) or "热门选题"
            title = f"{current_topic}｜{short_seed_title}（{angle}拆解）"
            content = (
                f"先说结论：{current_topic}内容要从真实需求切入。\n"
                f"市场信号：最近高频话题是「{seed_title or '热门内容'}」。\n"
                f"1) 开头先给场景痛点\n"
                f"2) 用{angle}拆成可执行步骤\n"
                f"3) 结尾给可复用模板和行动指令\n"
                f"{random.choice(ctas)}\n"
                f"#{current_topic} #求职 #经验分享"
            )
        else:
            title = f"{current_topic}｜{random.choice(hooks)}（{angle}）"
            content = (
                f"先说结论：{current_topic}要先做结构再做细节。\n"
                f"1) 明确目标和边界\n"
                f"2) 用{angle}快速执行\n"
                f"3) 每天复盘一个关键指标\n"
                f"数据参考：当前互动率 {summary.get('interaction_rate', 0)}\n"
                f"{random.choice(ctas)}\n"
                f"#{current_topic} #经验分享 #实用"
            )

        candidates.append(
            {
                "candidate_no": i,
                "topic": current_topic,
                "title": title,
                "content": content,
                "tags": f"#{current_topic} #经验分享 #实用",
                "generation_mode": generation_mode,
                "openclaw_source": False,
            }
        )
    return candidates, generation_mode


def infer_hook_type(title):
    t = str(title or "")
    if "别再" in t or "避坑" in t:
        return "avoid_pitfall"
    if "复盘" in t:
        return "retrospective"
    if "步骤" in t or "清单" in t:
        return "step_list"
    return "direct_claim"


def infer_structure_type(content):
    c = str(content or "")
    step_count = len(re.findall(r"^\s*[0-9]+\)", c, flags=re.MULTILINE))
    if step_count >= 3:
        return "three_step"
    if "复盘" in c:
        return "retrospective"
    return "free_form"


def infer_cta_type(content):
    c = str(content or "")
    if "评论区扣1" in c or "评论区扣 1" in c:
        return "comment_keyword"
    if "收藏" in c:
        return "save_reuse"
    if "私信" in c:
        return "dm_keyword"
    return "generic"


def extract_features(candidate):
    title = str(candidate.get("title", ""))
    content = str(candidate.get("content", ""))
    tags = str(candidate.get("tags", ""))
    topic = str(candidate.get("topic", ""))
    tag_count = len([p for p in tags.split() if p.startswith("#")])
    step_count = len(re.findall(r"^\s*[0-9]+\)", content, flags=re.MULTILINE))

    return {
        "title_len": len(title),
        "has_digit_in_title": bool(re.search(r"[0-9]", title)),
        "has_question_in_title": ("?" in title) or ("？" in title),
        "topic_in_title": bool(topic) and topic in title,
        "step_count": step_count,
        "tag_count": tag_count,
        "mentions_template": "模板" in content,
        "market_signal_used": "市场信号" in content,
    }


def score_candidate(features, own_data_status):
    score = 0.0
    title_len = int(features.get("title_len", 0))
    step_count = int(features.get("step_count", 0))
    tag_count = int(features.get("tag_count", 0))

    if 12 <= title_len <= 20:
        score += 0.30
    elif 8 <= title_len <= 24:
        score += 0.20
    else:
        score += 0.08

    if step_count >= 3:
        score += 0.22
    elif step_count == 2:
        score += 0.12

    if features.get("has_digit_in_title"):
        score += 0.10
    if features.get("topic_in_title"):
        score += 0.12
    if features.get("mentions_template"):
        score += 0.08
    score += min(tag_count, 3) * 0.03

    if features.get("market_signal_used") and str(own_data_status).startswith("empty_today"):
        score += 0.12

    return round(score, 6)


def ensure_experiment_tables(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_date TEXT NOT NULL,
          topic TEXT,
          account TEXT,
          selection_policy TEXT NOT NULL,
          status TEXT DEFAULT 'generated',
          selected_candidate_no INTEGER,
          metadata_json TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_arms (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER NOT NULL,
          candidate_no INTEGER NOT NULL,
          arm_key TEXT,
          topic TEXT,
          title TEXT,
          content TEXT,
          tags TEXT,
          hook_type TEXT,
          structure_type TEXT,
          cta_type TEXT,
          features_json TEXT,
          score REAL,
          status TEXT DEFAULT 'generated',
          publish_record_id INTEGER,
          result_label TEXT,
          engagement_rate REAL,
          reward_source TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (run_id) REFERENCES experiment_runs(id)
        )
        """
    )


def ensure_arm_columns(cur):
    cur.execute("PRAGMA table_info(experiment_arms)")
    cols = {row[1] for row in cur.fetchall()}
    if "arm_key" not in cols:
        cur.execute("ALTER TABLE experiment_arms ADD COLUMN arm_key TEXT")
    if "reward_source" not in cols:
        cur.execute("ALTER TABLE experiment_arms ADD COLUMN reward_source TEXT")


def ensure_candidate_columns(cur):
    cur.execute("PRAGMA table_info(candidate_posts)")
    cols = {row[1] for row in cur.fetchall()}
    if "experiment_run_id" not in cols:
        cur.execute("ALTER TABLE candidate_posts ADD COLUMN experiment_run_id INTEGER")
    if "arm_key" not in cols:
        cur.execute("ALTER TABLE candidate_posts ADD COLUMN arm_key TEXT")
    if "generation_mode" not in cols:
        cur.execute("ALTER TABLE candidate_posts ADD COLUMN generation_mode TEXT")
    if "bandit_sample" not in cols:
        cur.execute("ALTER TABLE candidate_posts ADD COLUMN bandit_sample REAL")


def diversify_candidate_arms(candidates):
    hook_cycle = ["direct_claim", "step_list", "retrospective", "avoid_pitfall"]
    cta_cycle = ["comment_keyword", "save_reuse", "generic", "dm_keyword"]
    structure_cycle = ["three_step", "retrospective", "free_form"]
    diversified = []
    seen = set()
    for idx, c in enumerate(candidates):
        c = dict(c)
        hk = str(c.get("hook_type") or "")
        st = str(c.get("structure_type") or "")
        ct = str(c.get("cta_type") or "")
        key = arm_key_of(hk, st, ct)
        if not hk or not st or not ct or key in seen:
            hk = hook_cycle[idx % len(hook_cycle)]
            st = structure_cycle[idx % len(structure_cycle)]
            ct = cta_cycle[idx % len(cta_cycle)]
            c["hook_type"] = hk
            c["structure_type"] = st
            c["cta_type"] = ct
        seen.add(arm_key_of(hk, st, ct))
        diversified.append(c)
    return diversified


def main():
    env = load_env(ENV)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    n = max(int(env.get("CANDIDATE_COUNT", "3")), 1)
    topic = env.get("KEYWORD", "效率")
    account = env.get("XHS_ACCOUNT", "default")

    summary_file = os.path.join(data_dir, "analysis", "latest_summary.json")
    if not os.path.exists(summary_file):
        raise SystemExit("Missing latest_summary.json, run 02_analyze.py first")

    with open(summary_file, "r", encoding="utf-8") as f:
        summary = json.load(f)

    own_data_status = summary.get("own_data_status", "live_data")
    market_seeds = load_market_seeds(summary, topic)
    openclaw_enabled = env_truthy(env.get("OPENCLAW_CANDIDATE_ENABLED"), default=False)
    openclaw_url = env.get("OPENCLAW_CANDIDATE_URL", "http://127.0.0.1:8787/candidates")
    openclaw_timeout = int(env.get("OPENCLAW_CANDIDATE_TIMEOUT", "20"))
    openclaw_retry_max = max(int(env.get("OPENCLAW_CANDIDATE_RETRY_MAX", "2")), 0)
    openclaw_retry_backoff = float(env.get("OPENCLAW_CANDIDATE_RETRY_BACKOFF", "1.2"))
    openclaw_prompt_version = env.get("OPENCLAW_CANDIDATE_PROMPT_VERSION", "candidate_prompt_v1")
    openclaw_error = ""
    openclaw_retries_used = 0

    batch_date = str(date.today())
    openclaw_request_id = f"{batch_date}-{uuid.uuid4().hex[:10]}"
    if openclaw_enabled:
        last_err = None
        for attempt in range(0, openclaw_retry_max + 1):
            try:
                raw_candidates = call_openclaw_candidates(
                    url=openclaw_url,
                    timeout_seconds=openclaw_timeout,
                    n=n,
                    topic=topic,
                    summary=summary,
                    own_data_status=own_data_status,
                    market_seeds=market_seeds,
                    request_id=openclaw_request_id,
                    prompt_version=openclaw_prompt_version,
                )
                candidates = normalize_openclaw_candidates(
                    raw_candidates=raw_candidates,
                    fallback_topic=topic,
                    generation_mode="openclaw_generated",
                )
                if not candidates:
                    raise ValueError("openclaw normalized candidates empty")
                quality_ok, quality_issues = quality_check_candidates(candidates)
                if not quality_ok:
                    raise ValueError(f"openclaw quality_failed:{';'.join(quality_issues[:8])}")
                generation_mode = "openclaw_generated"
                openclaw_retries_used = attempt
                break
            except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
                last_err = e
                if attempt < openclaw_retry_max:
                    time.sleep(openclaw_retry_backoff * (attempt + 1))
        else:
            openclaw_error = str(last_err or "openclaw_unknown_error")
            candidates, generation_mode = build_local_template_candidates(
                n=n,
                topic=topic,
                summary=summary,
                own_data_status=own_data_status,
                market_seeds=market_seeds,
            )
            generation_mode = f"{generation_mode}_fallback_from_openclaw"
    else:
        candidates, generation_mode = build_local_template_candidates(
            n=n,
            topic=topic,
            summary=summary,
            own_data_status=own_data_status,
            market_seeds=market_seeds,
        )

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_experiment_tables(cur)
    ensure_arm_columns(cur)
    ensure_candidate_columns(cur)
    ensure_policy_tables(cur)

    candidates = candidates[:n]
    normalized = []
    for i, candidate in enumerate(candidates, start=1):
        candidate["candidate_no"] = i
        candidate["generation_mode"] = generation_mode
        title = candidate.get("title", "")
        content = candidate.get("content", "")
        features = extract_features(candidate)
        score = score_candidate(features, own_data_status)
        candidate["score"] = score
        candidate["hook_type"] = str(candidate.get("hook_type") or infer_hook_type(title))
        candidate["structure_type"] = str(candidate.get("structure_type") or infer_structure_type(content))
        candidate["cta_type"] = str(candidate.get("cta_type") or infer_cta_type(content))
        candidate["arm_key"] = arm_key_of(candidate["hook_type"], candidate["structure_type"], candidate["cta_type"])
        candidate["feature_snapshot"] = {
            "version": "rule_score_v1",
            "own_data_status": own_data_status,
            "openclaw_source": bool(candidate.get("openclaw_source")),
            **features,
        }
        normalized.append(candidate)
    candidates = diversify_candidate_arms(normalized)

    # Refresh derived fields in case diversification rewrote arm descriptors.
    for c in candidates:
        c["arm_key"] = arm_key_of(c["hook_type"], c["structure_type"], c["cta_type"])

    arm_keys = sorted({c["arm_key"] for c in candidates})
    chosen_arm_key, arm_stats = choose_arm_thompson(cur, topic, arm_keys, min_explore_pulls=2)
    for c in candidates:
        s = float(arm_stats.get(c["arm_key"], {}).get("sample", 0.5))
        c["bandit_sample"] = round(s, 6)
        c["final_score"] = round((0.75 * float(c["score"])) + (0.25 * s), 6)

    candidates = sorted(candidates, key=lambda x: x.get("final_score", 0), reverse=True)
    selected_idx = None
    for idx, c in enumerate(candidates, start=1):
        if selected_idx is None and c["arm_key"] == chosen_arm_key:
            selected_idx = idx
            break
    if selected_idx is None:
        selected_idx = 1

    for idx, c in enumerate(candidates, start=1):
        c["candidate_no"] = idx
        c["selected"] = idx == selected_idx

    selected_candidate_no = selected_idx

    run_metadata = {
        "generation_mode": generation_mode,
        "own_data_status": own_data_status,
        "source_summary_file": summary_file,
        "openclaw_enabled": openclaw_enabled,
        "openclaw_url": openclaw_url if openclaw_enabled else None,
        "openclaw_error": openclaw_error or None,
        "openclaw_request_id": openclaw_request_id if openclaw_enabled else None,
        "openclaw_prompt_version": openclaw_prompt_version if openclaw_enabled else None,
        "openclaw_retries_used": openclaw_retries_used,
        "selection_policy_detail": "thompson_v1+rule_score_v1",
        "chosen_arm_key": chosen_arm_key,
        "arm_samples": {k: round(float(v.get("sample", 0.0)), 6) for k, v in arm_stats.items()},
    }
    cur.execute(
        """
        INSERT INTO experiment_runs (batch_date, topic, account, selection_policy, status, selected_candidate_no, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_date,
            topic,
            account,
            "thompson_v1+rule_score_v1",
            "selected",
            selected_candidate_no,
            json.dumps(run_metadata, ensure_ascii=False),
        ),
    )
    run_id = cur.lastrowid

    for c in candidates:
        candidate_status = "selected" if c["selected"] else "generated"
        cur.execute(
            """
            INSERT INTO candidate_posts (
              batch_date, candidate_no, experiment_run_id, arm_key, generation_mode, bandit_sample,
              topic, title, content, tags, status, score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_date,
                c["candidate_no"],
                run_id,
                c["arm_key"],
                c["generation_mode"],
                c["bandit_sample"],
                c["topic"],
                c["title"],
                c["content"],
                c["tags"],
                candidate_status,
                c["final_score"],
            ),
        )
        cur.execute(
            """
            INSERT INTO experiment_arms (
              run_id, candidate_no, arm_key, topic, title, content, tags,
              hook_type, structure_type, cta_type, features_json, score, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                c["candidate_no"],
                c["arm_key"],
                c["topic"],
                c["title"],
                c["content"],
                c["tags"],
                c["hook_type"],
                c["structure_type"],
                c["cta_type"],
                json.dumps(c["feature_snapshot"], ensure_ascii=False),
                c["final_score"],
                candidate_status,
            ),
        )

    conn.commit()
    conn.close()

    out = os.path.join(data_dir, "candidates", f"candidates_{batch_date}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "batch_date": batch_date,
                "count": len(candidates),
                "file": out,
                "generation_mode": generation_mode,
                "own_data_status": own_data_status,
                "selection_policy": "thompson_v1+rule_score_v1",
                "selected_candidate_no": selected_candidate_no,
                "top_score": candidates[0]["score"] if candidates else None,
                "top_final_score": candidates[0]["final_score"] if candidates else None,
                "openclaw_enabled": openclaw_enabled,
                "openclaw_error": openclaw_error or None,
                "openclaw_request_id": openclaw_request_id if openclaw_enabled else None,
                "chosen_arm_key": chosen_arm_key,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
