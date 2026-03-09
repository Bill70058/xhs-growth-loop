#!/usr/bin/env python3
import json
import os
import socket
import sqlite3
import sys
from urllib import error, request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(ROOT, "config", ".env")


def load_env(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():
        if k in out:
            out[k] = v
    return out


def tcp_check(host, port, timeout=1.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        s.close()


def openclaw_check(url, timeout=2):
    req = request.Request(
        url,
        data=b'{"topic":"\xe6\xb1\x82\xe8\x81\x8c","candidate_count":1}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 300
    except error.URLError:
        return False
    except Exception:
        return False


def main():
    env = load_env(ENV_PATH)
    db_path = env.get("DB_PATH", os.path.join(ROOT, "data", "growth.db"))
    cdp_port = int(env.get("XHS_CDP_PORT", "9333"))
    openclaw_url = env.get("OPENCLAW_CANDIDATE_URL", "http://127.0.0.1:8787/candidates")
    result = {
        "python_version": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 10),
        "env_file_exists": os.path.exists(ENV_PATH),
        "db_exists": os.path.exists(db_path),
        "cdp_port_open": tcp_check("127.0.0.1", cdp_port),
        "openclaw_candidate_reachable": openclaw_check(openclaw_url),
        "required_tables_ok": False,
    }
    if result["db_exists"]:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in cur.fetchall()}
            required = {
                "post_metrics_daily",
                "candidate_posts",
                "publish_records",
                "experiment_runs",
                "experiment_arms",
                "policy_arm_stats",
                "policy_reward_events",
            }
            result["required_tables_ok"] = required.issubset(tables)
            result["missing_tables"] = sorted(list(required - tables))
            conn.close()
        except Exception as e:
            result["db_error"] = str(e)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
