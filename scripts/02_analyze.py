#!/usr/bin/env python3
import csv
import glob
import json
import os
import re
import sqlite3
from datetime import date
from urllib.parse import parse_qs, urlparse

from policy_bandit import apply_reward, arm_key_of, ensure_policy_tables, summarize_topic_policy

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
    return env


def pick_field(row, candidates):
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    for k, v in row.items():
        lk = k.lower()
        for c in candidates:
            if c.lower() in lk and v not in (None, ""):
                return v
    return ""


def to_int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except Exception:
        return 0


def get_last_valid_stats(cur, today):
    cur.execute(
        """
        SELECT
          stat_date,
          COUNT(*) AS rows_loaded,
          COALESCE(SUM(exposure), 0) AS total_exposure,
          COALESCE(SUM(likes + comments + collects + shares), 0) AS total_interaction
        FROM post_metrics_daily
        WHERE stat_date <> ?
        GROUP BY stat_date
        HAVING COUNT(*) > 0
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (today,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "stat_date": row[0],
        "rows_loaded": int(row[1] or 0),
        "total_exposure": int(row[2] or 0),
        "total_interaction": int(row[3] or 0),
    }


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


def ensure_publish_columns(cur):
    cur.execute("PRAGMA table_info(publish_records)")
    cols = {row[1] for row in cur.fetchall()}
    if "note_id" not in cols:
        cur.execute("ALTER TABLE publish_records ADD COLUMN note_id TEXT")


def map_publish_status(raw):
    s = str(raw or "").upper()
    if s == "PUBLISHED":
        return "published"
    if s == "READY_TO_PUBLISH":
        return "ready_to_publish"
    if s == "FAILED":
        return "failed"
    return "generated"


def extract_note_id(note_link, raw_result):
    link = str(note_link or "").strip()
    if link:
        try:
            u = urlparse(link)
            q = parse_qs(u.query or "")
            for key in ("note_id", "noteId", "id"):
                vals = q.get(key) or []
                if vals and str(vals[0]).strip():
                    return str(vals[0]).strip()
            m = re.search(r"/(?:explore|discovery/item|note)/([0-9A-Za-z_-]{8,64})", u.path or "")
            if m:
                return m.group(1)
        except Exception:
            pass

    raw = str(raw_result or "")
    patterns = [
        r'"note_id"\s*:\s*"([0-9A-Za-z_-]{8,64})"',
        r'"noteId"\s*:\s*"([0-9A-Za-z_-]{8,64})"',
        r'"post_id"\s*:\s*"([0-9A-Za-z_-]{8,64})"',
        r"note_id=([0-9A-Za-z_-]{8,64})",
    ]
    for p in patterns:
        m = re.search(p, raw)
        if m:
            return m.group(1)
    return ""


def sync_experiment_with_publish_records(cur):
    linked = 0
    legacy_pending = 0
    cur.execute(
        """
        SELECT
          p.id, p.candidate_id, p.status, p.note_link, p.raw_result, p.note_id,
          c.batch_date, c.candidate_no, c.experiment_run_id
        FROM publish_records p
        JOIN candidate_posts c ON c.id = p.candidate_id
        WHERE p.candidate_id IS NOT NULL
        ORDER BY p.id ASC
        """
    )
    rows = cur.fetchall()
    for publish_id, _candidate_id, publish_status, note_link, raw_result, note_id, batch_date, candidate_no, experiment_run_id in rows:
        extracted_note_id = str(note_id or "").strip() or extract_note_id(note_link, raw_result)
        if extracted_note_id:
            cur.execute("UPDATE publish_records SET note_id = ? WHERE id = ?", (extracted_note_id, publish_id))
        if not experiment_run_id:
            legacy_pending += 1
            continue
        cur.execute(
            """
            SELECT ea.id
            FROM experiment_arms ea
            WHERE ea.run_id = ? AND ea.candidate_no = ?
            ORDER BY ea.id DESC
            LIMIT 1
            """,
            (experiment_run_id, candidate_no),
        )
        arm = cur.fetchone()
        if not arm:
            continue
        arm_id = arm[0]
        cur.execute(
            """
            UPDATE experiment_arms
            SET publish_record_id = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (publish_id, map_publish_status(publish_status), arm_id),
        )
        linked += 1
    return {"linked": linked, "legacy_pending": legacy_pending}


def median(values):
    vals = sorted([float(v) for v in values if v is not None])
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def get_topic_baseline(cur, topic, today):
    topic = str(topic or "").strip()
    if topic:
        cur.execute(
            """
            SELECT
              CASE WHEN exposure > 0 THEN CAST(likes + comments + collects + shares AS REAL) / exposure ELSE 0 END AS er
            FROM post_metrics_daily
            WHERE stat_date >= date(?, '-14 day')
              AND stat_date <= ?
              AND title LIKE ?
            """,
            (today, today, f"%{topic}%"),
        )
        values = [row[0] for row in cur.fetchall()]
        base = median(values)
        if base is not None:
            return base

    cur.execute(
        """
        SELECT
          CASE WHEN exposure > 0 THEN CAST(likes + comments + collects + shares AS REAL) / exposure ELSE 0 END AS er
        FROM post_metrics_daily
        WHERE stat_date >= date(?, '-14 day')
          AND stat_date <= ?
        """,
        (today, today),
    )
    values = [row[0] for row in cur.fetchall()]
    base = median(values)
    return base if base is not None else 0.05


def find_candidate_metric(cur, title, publish_date):
    title = str(title or "").strip()
    if not title:
        return None
    cur.execute(
        """
        SELECT stat_date, exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE title = ?
          AND stat_date >= ?
          AND stat_date <= date(?, '+2 day')
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (title, publish_date, publish_date),
    )
    row = cur.fetchone()
    if row:
        return row
    cur.execute(
        """
        SELECT stat_date, exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE title LIKE ?
          AND stat_date >= ?
          AND stat_date <= date(?, '+2 day')
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (f"%{title[:12]}%", publish_date, publish_date),
    )
    return cur.fetchone()


def find_candidate_metric_by_note_id(cur, note_id, publish_date):
    nid = str(note_id or "").strip()
    if not nid:
        return None
    cur.execute(
        """
        SELECT stat_date, exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE post_id = ?
          AND stat_date >= ?
          AND stat_date <= date(?, '+2 day')
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (nid, publish_date, publish_date),
    )
    return cur.fetchone()


def apply_rewards_from_metrics(cur, today):
    applied = 0
    pending = 0
    cur.execute(
        """
        SELECT
          ea.id, ea.topic, ea.arm_key, ea.hook_type, ea.structure_type, ea.cta_type,
          ea.title, ea.result_label, ea.reward_source,
          pr.publish_date, pr.status, pr.note_id
        FROM experiment_arms ea
        JOIN publish_records pr ON pr.id = ea.publish_record_id
        WHERE ea.publish_record_id IS NOT NULL
        ORDER BY ea.id ASC
        """
    )
    rows = cur.fetchall()
    for row in rows:
        (
            arm_id,
            topic,
            arm_key,
            hook_type,
            structure_type,
            cta_type,
            title,
            result_label,
            reward_source,
            publish_date,
            publish_status,
            publish_note_id,
        ) = row
        if str(reward_source or "").startswith("bandit_v1"):
            continue

        publish_status = str(publish_status or "").upper()
        if publish_status == "FAILED":
            reward = 0.0
            label = "loss"
            engagement_rate = 0.0
        elif publish_status in ("READY_TO_PUBLISH",):
            pending += 1
            continue
        else:
            m = find_candidate_metric_by_note_id(cur, publish_note_id, publish_date)
            source = "note_id"
            if not m:
                m = find_candidate_metric(cur, title, publish_date)
                source = "title_fallback"
            if not m:
                pending += 1
                continue
            _stat_date, exposure, likes, comments, collects, shares = m
            exposure = int(exposure or 0)
            interaction = int(likes or 0) + int(comments or 0) + int(collects or 0) + int(shares or 0)
            engagement_rate = (interaction / exposure) if exposure > 0 else 0.0
            baseline = get_topic_baseline(cur, topic, today)
            label = "win" if engagement_rate >= baseline else "loss"
            reward = 1.0 if label == "win" else 0.0

        key = arm_key or arm_key_of(hook_type, structure_type, cta_type)
        updated = apply_reward(cur, arm_id=arm_id, topic=(topic or "unknown"), arm_key=key, reward=reward, label=label)
        if updated:
            cur.execute(
                """
                UPDATE experiment_arms
                SET arm_key = ?, engagement_rate = ?, result_label = ?, reward_source = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (key, float(engagement_rate), label, f"bandit_v1:{source}", arm_id),
            )
            applied += 1

    return {"applied": applied, "pending": pending}


def summarize_reward_sources(cur):
    cur.execute(
        """
        SELECT reward_source, COUNT(*)
        FROM experiment_arms
        WHERE reward_source IS NOT NULL AND reward_source <> ''
        GROUP BY reward_source
        ORDER BY COUNT(*) DESC
        """
    )
    out = {}
    for source, cnt in cur.fetchall():
        out[str(source)] = int(cnt or 0)
    return out


def build_strategy_learning_summary(cur, batch_date):
    cur.execute(
        """
        SELECT id, topic, selection_policy, status, selected_candidate_no, metadata_json
        FROM experiment_runs
        WHERE batch_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (batch_date,),
    )
    run = cur.fetchone()
    if not run:
        return {
            "has_run": False,
            "run_id": None,
            "selection_policy": None,
            "selected_candidate_no": None,
            "arms": [],
            "status_breakdown": {},
        }

    run_id, run_topic, selection_policy, run_status, selected_candidate_no, metadata_json = run
    metadata = {}
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
        except Exception:
            metadata = {"raw_metadata_json": metadata_json}
    cur.execute(
        """
        SELECT
          candidate_no, arm_key, topic, hook_type, structure_type, cta_type, score, status, result_label, engagement_rate
        FROM experiment_arms
        WHERE run_id = ?
        ORDER BY candidate_no ASC
        """,
        (run_id,),
    )
    arm_rows = cur.fetchall()
    arms = []
    status_breakdown = {}
    for row in arm_rows:
        candidate_no, arm_key, topic, hook_type, structure_type, cta_type, score, status, result_label, engagement_rate = row
        status_breakdown[status] = status_breakdown.get(status, 0) + 1
        arms.append(
            {
                "candidate_no": candidate_no,
                "arm_key": arm_key,
                "topic": topic,
                "hook_type": hook_type,
                "structure_type": structure_type,
                "cta_type": cta_type,
                "score": float(score or 0),
                "status": status,
                "result_label": result_label,
                "engagement_rate": None if engagement_rate is None else float(engagement_rate),
            }
        )

    policy_summary = summarize_topic_policy(cur, run_topic or "")

    return {
        "has_run": True,
        "run_id": run_id,
        "selection_policy": selection_policy,
        "run_status": run_status,
        "selected_candidate_no": selected_candidate_no,
        "generation_mode": metadata.get("generation_mode"),
        "openclaw_enabled": metadata.get("openclaw_enabled"),
        "openclaw_error": metadata.get("openclaw_error"),
        "openclaw_prompt_version": metadata.get("openclaw_prompt_version"),
        "arms": arms,
        "status_breakdown": status_breakdown,
        "policy_summary": policy_summary,
    }


def main():
    env = load_env(ENV)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    today = str(date.today())

    files = sorted(glob.glob(os.path.join(data_dir, "raw", "content_data_*.csv")))
    if not files:
        raise SystemExit("No content_data csv found, run 01_collect.sh first")

    csv_file = files[-1]
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_experiment_tables(cur)
    ensure_arm_columns(cur)
    ensure_candidate_columns(cur)
    ensure_publish_columns(cur)
    ensure_policy_tables(cur)

    # Keep daily analyze idempotent for reruns on the same date.
    cur.execute("DELETE FROM post_metrics_daily WHERE stat_date = ?", (today,))

    total_exposure = 0
    total_interaction = 0
    rows_loaded = 0

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            post_id = pick_field(row, ["post_id", "note_id", "笔记ID", "笔记id", "id"]) or f"unknown_{rows_loaded}"
            title = pick_field(row, ["标题", "title"])
            exposure = to_int(pick_field(row, ["曝光", "exposure", "展示"]))
            views = to_int(pick_field(row, ["阅读", "播放", "views", "观看"]))
            likes = to_int(pick_field(row, ["点赞", "likes"]))
            comments = to_int(pick_field(row, ["评论", "comments"]))
            collects = to_int(pick_field(row, ["收藏", "collects"]))
            shares = to_int(pick_field(row, ["分享", "shares"]))
            profile_visits = to_int(pick_field(row, ["主页访问", "profile_visits"]))

            cur.execute(
                """
                INSERT INTO post_metrics_daily
                (stat_date, post_id, title, exposure, views, likes, comments, collects, shares, profile_visits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (today, post_id, title, exposure, views, likes, comments, collects, shares, profile_visits),
            )
            total_exposure += exposure
            total_interaction += likes + comments + collects + shares
            rows_loaded += 1

    conn.commit()

    own_data_status = "live_data"
    own_data_reference_date = today
    if rows_loaded == 0:
        fallback = get_last_valid_stats(cur, today)
        if fallback:
            total_exposure = fallback["total_exposure"]
            total_interaction = fallback["total_interaction"]
            own_data_status = "empty_today_fallback_last_valid"
            own_data_reference_date = fallback["stat_date"]
        else:
            own_data_status = "empty_today_no_fallback"

    interaction_rate = (total_interaction / total_exposure) if total_exposure else 0.0
    # Market-learning stream (keyword-based high performing feeds)
    market_dir = os.path.join(data_dir, "raw", "market", today)
    market_files = sorted(glob.glob(os.path.join(market_dir, "*.json")))
    market_keyword_count = 0
    market_total_feeds = 0
    market_by_keyword = []
    for mf in market_files:
        try:
            payload = json.load(open(mf, "r", encoding="utf-8"))
        except Exception:
            continue
        keyword = payload.get("keyword") or os.path.splitext(os.path.basename(mf))[0]
        feeds = payload.get("feeds", [])
        if not isinstance(feeds, list):
            feeds = []
        c = len(feeds)
        market_keyword_count += 1
        market_total_feeds += c
        market_by_keyword.append({"keyword": keyword, "count": c, "file": mf})

    sync_result = sync_experiment_with_publish_records(cur)
    reward_update = apply_rewards_from_metrics(cur, today)
    reward_sources = summarize_reward_sources(cur)
    strategy_learning = build_strategy_learning_summary(cur, today)
    conn.commit()

    summary = {
        "date": today,
        "source_csv": csv_file,
        "rows_loaded": rows_loaded,
        "own_data_status": own_data_status,
        "own_data_reference_date": own_data_reference_date,
        "total_exposure": total_exposure,
        "total_interaction": total_interaction,
        "interaction_rate": round(interaction_rate, 6),
        "market_learning": {
            "keyword_count": market_keyword_count,
            "total_feeds": market_total_feeds,
            "by_keyword": market_by_keyword,
        },
        "strategy_learning": strategy_learning,
        "experiment_sync": {
            "linked_publish_records": sync_result["linked"],
            "legacy_pending_publish_records": sync_result["legacy_pending"],
            "reward_update": reward_update,
            "reward_sources": reward_sources,
        },
        "insight": "优先放大高互动主题；低曝光但高互动的内容可二次分发。",
    }

    out = os.path.join(data_dir, "analysis", "latest_summary.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
