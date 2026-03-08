#!/usr/bin/env python3
import csv
import glob
import json
import os
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
