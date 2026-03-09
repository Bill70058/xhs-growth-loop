#!/usr/bin/env python3
import json
import random


def ensure_policy_tables(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS policy_arm_stats (
          topic TEXT NOT NULL,
          arm_key TEXT NOT NULL,
          alpha REAL NOT NULL DEFAULT 1.0,
          beta REAL NOT NULL DEFAULT 1.0,
          pulls INTEGER NOT NULL DEFAULT 0,
          wins INTEGER NOT NULL DEFAULT 0,
          last_reward REAL,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (topic, arm_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS policy_reward_events (
          arm_id INTEGER PRIMARY KEY,
          topic TEXT NOT NULL,
          arm_key TEXT NOT NULL,
          reward REAL NOT NULL,
          label TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def arm_key_of(hook_type, structure_type, cta_type):
    return f"{hook_type}|{structure_type}|{cta_type}"


def load_arm_stats(cur, topic, arm_keys):
    out = {}
    for arm_key in arm_keys:
        cur.execute(
            """
            SELECT alpha, beta, pulls, wins, last_reward
            FROM policy_arm_stats
            WHERE topic = ? AND arm_key = ?
            """,
            (topic, arm_key),
        )
        row = cur.fetchone()
        if not row:
            out[arm_key] = {"alpha": 1.0, "beta": 1.0, "pulls": 0, "wins": 0, "last_reward": None}
            continue
        out[arm_key] = {
            "alpha": float(row[0] or 1.0),
            "beta": float(row[1] or 1.0),
            "pulls": int(row[2] or 0),
            "wins": int(row[3] or 0),
            "last_reward": None if row[4] is None else float(row[4]),
        }
    return out


def choose_arm_thompson(cur, topic, arm_keys, min_explore_pulls=2):
    stats = load_arm_stats(cur, topic, arm_keys)
    # Force exploration for unseen arms.
    low_pull_arms = [k for k in arm_keys if int(stats[k]["pulls"]) < int(min_explore_pulls)]
    if low_pull_arms:
        chosen = random.choice(low_pull_arms)
        for k in arm_keys:
            stats[k]["sample"] = random.betavariate(stats[k]["alpha"], stats[k]["beta"])
        return chosen, stats

    best_key = None
    best_sample = -1.0
    for k in arm_keys:
        a = stats[k]["alpha"]
        b = stats[k]["beta"]
        s = random.betavariate(a, b)
        stats[k]["sample"] = s
        if s > best_sample:
            best_sample = s
            best_key = k
    return best_key or arm_keys[0], stats


def apply_reward(cur, arm_id, topic, arm_key, reward, label):
    cur.execute("SELECT 1 FROM policy_reward_events WHERE arm_id = ?", (arm_id,))
    if cur.fetchone():
        return False

    reward = max(0.0, min(1.0, float(reward)))
    win = 1 if reward >= 0.5 else 0
    cur.execute(
        """
        INSERT INTO policy_reward_events (arm_id, topic, arm_key, reward, label)
        VALUES (?, ?, ?, ?, ?)
        """,
        (arm_id, topic, arm_key, reward, label),
    )
    cur.execute(
        """
        INSERT INTO policy_arm_stats (topic, arm_key, alpha, beta, pulls, wins, last_reward, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(topic, arm_key) DO UPDATE SET
          alpha = policy_arm_stats.alpha + excluded.alpha,
          beta = policy_arm_stats.beta + excluded.beta,
          pulls = policy_arm_stats.pulls + 1,
          wins = policy_arm_stats.wins + excluded.wins,
          last_reward = excluded.last_reward,
          updated_at = CURRENT_TIMESTAMP
        """,
        (topic, arm_key, reward, 1.0 - reward, win, reward),
    )
    return True


def summarize_topic_policy(cur, topic, limit=8):
    cur.execute(
        """
        SELECT arm_key, alpha, beta, pulls, wins, last_reward
        FROM policy_arm_stats
        WHERE topic = ?
        ORDER BY pulls DESC, wins DESC
        LIMIT ?
        """,
        (topic, int(limit)),
    )
    rows = cur.fetchall()
    arms = []
    for row in rows:
        arm_key, alpha, beta, pulls, wins, last_reward = row
        arms.append(
            {
                "arm_key": arm_key,
                "alpha": float(alpha or 1.0),
                "beta": float(beta or 1.0),
                "pulls": int(pulls or 0),
                "wins": int(wins or 0),
                "last_reward": None if last_reward is None else float(last_reward),
            }
        )
    return arms


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False)
