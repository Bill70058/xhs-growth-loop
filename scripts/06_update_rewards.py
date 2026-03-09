#!/usr/bin/env python3
import json
import os
import re
import sqlite3
from datetime import date
from urllib.parse import parse_qs, urlparse

from policy_bandit import apply_reward, arm_key_of, ensure_policy_tables

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
    for k, v in os.environ.items():
        if k in env:
            env[k] = v
    return env


def ensure_experiment_tables(cur):
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
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_publish_columns(cur):
    cur.execute("PRAGMA table_info(publish_records)")
    cols = {row[1] for row in cur.fetchall()}
    if "note_id" not in cols:
        cur.execute("ALTER TABLE publish_records ADD COLUMN note_id TEXT")


def median(values):
    vals = sorted([float(v) for v in values if v is not None])
    if not vals:
        return None
    n = len(vals)
    m = n // 2
    if n % 2 == 1:
        return vals[m]
    return (vals[m - 1] + vals[m]) / 2.0


def topic_baseline(cur, topic, today):
    topic = str(topic or "").strip()
    if topic:
        cur.execute(
            """
            SELECT CASE WHEN exposure > 0 THEN CAST(likes + comments + collects + shares AS REAL) / exposure ELSE 0 END
            FROM post_metrics_daily
            WHERE stat_date >= date(?, '-14 day') AND stat_date <= ? AND title LIKE ?
            """,
            (today, today, f"%{topic}%"),
        )
        m = median([r[0] for r in cur.fetchall()])
        if m is not None:
            return m
    cur.execute(
        """
        SELECT CASE WHEN exposure > 0 THEN CAST(likes + comments + collects + shares AS REAL) / exposure ELSE 0 END
        FROM post_metrics_daily
        WHERE stat_date >= date(?, '-14 day') AND stat_date <= ?
        """,
        (today, today),
    )
    m = median([r[0] for r in cur.fetchall()])
    return m if m is not None else 0.05


def pick_metric(cur, title, publish_date):
    title = str(title or "").strip()
    if not title:
        return None
    cur.execute(
        """
        SELECT exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE title = ? AND stat_date >= ? AND stat_date <= date(?, '+2 day')
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
        SELECT exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE title LIKE ? AND stat_date >= ? AND stat_date <= date(?, '+2 day')
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (f"%{title[:12]}%", publish_date, publish_date),
    )
    return cur.fetchone()


def pick_metric_by_note_id(cur, note_id, publish_date):
    nid = str(note_id or "").strip()
    if not nid:
        return None
    cur.execute(
        """
        SELECT exposure, likes, comments, collects, shares
        FROM post_metrics_daily
        WHERE post_id = ? AND stat_date >= ? AND stat_date <= date(?, '+2 day')
        ORDER BY stat_date DESC
        LIMIT 1
        """,
        (nid, publish_date, publish_date),
    )
    return cur.fetchone()


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


def main():
    env = load_env(ENV)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    today = str(date.today())
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_experiment_tables(cur)
    ensure_publish_columns(cur)
    ensure_policy_tables(cur)

    applied = 0
    pending = 0
    cur.execute(
        """
        SELECT
          ea.id, ea.publish_record_id, ea.topic, ea.arm_key, ea.hook_type, ea.structure_type, ea.cta_type,
          ea.title, ea.reward_source,
          pr.publish_date, pr.status, pr.note_id, pr.note_link, pr.raw_result
        FROM experiment_arms ea
        JOIN publish_records pr ON pr.id = ea.publish_record_id
        WHERE ea.publish_record_id IS NOT NULL
        ORDER BY ea.id ASC
        """
    )
    for row in cur.fetchall():
        arm_id, publish_record_id, topic, arm_key, hook_type, structure_type, cta_type, title, reward_source, publish_date, publish_status, note_id, note_link, raw_result = row
        if str(reward_source or "").startswith("bandit_v1"):
            continue
        resolved_note_id = str(note_id or "").strip() or extract_note_id(note_link, raw_result)
        if resolved_note_id and resolved_note_id != str(note_id or "").strip():
            cur.execute("UPDATE publish_records SET note_id = ? WHERE id = ?", (resolved_note_id, int(publish_record_id)))
        publish_status = str(publish_status or "").upper()
        if publish_status == "FAILED":
            er = 0.0
            label = "loss"
            source = "status_failed"
        elif publish_status == "READY_TO_PUBLISH":
            pending += 1
            continue
        else:
            metric = pick_metric_by_note_id(cur, resolved_note_id, publish_date)
            source = "note_id"
            if not metric:
                metric = pick_metric(cur, title, publish_date)
                source = "title_fallback"
            if not metric:
                pending += 1
                continue
            exposure, likes, comments, collects, shares = [int(x or 0) for x in metric]
            interaction = likes + comments + collects + shares
            er = (interaction / exposure) if exposure > 0 else 0.0
            base = topic_baseline(cur, topic, today)
            label = "win" if er >= base else "loss"
        reward = 1.0 if label == "win" else 0.0
        key = arm_key or arm_key_of(hook_type, structure_type, cta_type)
        if apply_reward(cur, arm_id, topic or "unknown", key, reward, label):
            cur.execute(
                """
                UPDATE experiment_arms
                SET arm_key = ?, engagement_rate = ?, result_label = ?, reward_source = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (key, float(er), label, f"bandit_v1:{source}", arm_id),
            )
            applied += 1

    conn.commit()
    conn.close()
    print(json.dumps({"applied": applied, "pending": pending}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
