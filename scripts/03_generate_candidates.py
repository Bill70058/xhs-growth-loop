#!/usr/bin/env python3
import json
import os
import random
import sqlite3
from datetime import date

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
            if not title:
                continue
            seeds.append({"keyword": keyword, "title": title})

    return seeds


def normalize_seed_title(text, limit=20):
    cleaned = (text or "").replace("\n", " ").strip()
    for ch in ("（", "）", "(", ")", "【", "】", "[", "]"):
        cleaned = cleaned.replace(ch, "")
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def main():
    env = load_env(ENV)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    n = int(env.get("CANDIDATE_COUNT", "3"))
    topic = env.get("KEYWORD", "效率")

    summary_file = os.path.join(data_dir, "analysis", "latest_summary.json")
    if not os.path.exists(summary_file):
        raise SystemExit("Missing latest_summary.json, run 02_analyze.py first")

    with open(summary_file, "r", encoding="utf-8") as f:
        summary = json.load(f)
    own_data_status = summary.get("own_data_status", "live_data")
    market_seeds = load_market_seeds(summary, topic)
    use_market_mode = own_data_status.startswith("empty_today") and bool(market_seeds)

    hooks = [
        "我用这个方法把效率翻了 2 倍",
        "别再盲目做了，这 3 个步骤就够",
        "我复盘了 30 天，结果超预期",
        "这条是给想快速上手的人",
    ]
    angles = ["清单法", "复盘法", "模板法", "避坑法"]
    ctas = ["要我发模板就在评论区扣1", "收藏这条，明天直接照着做", "需要完整版本我再更新下一篇"]

    batch_date = str(date.today())
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
            }
        )

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    for c in candidates:
        cur.execute(
            """
            INSERT INTO candidate_posts (batch_date, candidate_no, topic, title, content, tags, status)
            VALUES (?, ?, ?, ?, ?, ?, 'generated')
            """,
            (batch_date, c["candidate_no"], c["topic"], c["title"], c["content"], c["tags"]),
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
                "generation_mode": "market_seeded" if use_market_mode else "template_baseline",
                "own_data_status": own_data_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
