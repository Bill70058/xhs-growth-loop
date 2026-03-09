#!/usr/bin/env python3
import json
import os
import sqlite3
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_FILE = os.path.join(ROOT, "config", ".env")


def load_env(path):
    out = {}
    if os.path.exists(path):
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


def safe_json(path, fallback):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return fallback


def compute_note_id_coverage(cur):
    cur.execute("SELECT COUNT(*) FROM publish_records")
    total = int(cur.fetchone()[0] or 0)
    if total == 0:
        return {"total": 0, "with_note_id": 0, "ratio": 0.0}
    cur.execute("SELECT COUNT(*) FROM publish_records WHERE note_id IS NOT NULL AND TRIM(note_id) <> ''")
    with_id = int(cur.fetchone()[0] or 0)
    return {"total": total, "with_note_id": with_id, "ratio": round(with_id / total, 4)}


def mvp_score(summary, runtime, note_id_coverage):
    score = 0
    sl = summary.get("strategy_learning", {}) if isinstance(summary, dict) else {}
    if sl.get("has_run"):
        score += 20
    if sl.get("openclaw_enabled"):
        score += 20
    if str(sl.get("selection_policy") or "").startswith("thompson_v1"):
        score += 15
    rs = summary.get("experiment_sync", {}).get("reward_update", {}) if isinstance(summary, dict) else {}
    if int(rs.get("pending", 0) or 0) < 5:
        score += 10
    if int(rs.get("applied", 0) or 0) > 0:
        score += 10
    if runtime.get("ok"):
        score += 10
    ratio = float(note_id_coverage.get("ratio", 0.0))
    if ratio >= 0.8:
        score += 15
    elif ratio >= 0.5:
        score += 8
    return min(score, 100)


def main():
    env = load_env(ENV_FILE)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    summary_file = os.path.join(data_dir, "analysis", "latest_summary.json")
    runtime_latest_file = os.path.join(data_dir, "runtime", "bridge_latest.json")
    self_audit_file = os.path.join(ROOT, "docs", "SELF_AUDIT.md")

    summary = safe_json(summary_file, {})
    runtime_latest = safe_json(runtime_latest_file, {})
    note_cov = {"total": 0, "with_note_id": 0, "ratio": 0.0}
    pending = int(summary.get("experiment_sync", {}).get("reward_update", {}).get("pending", 0) or 0)

    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        note_cov = compute_note_id_coverage(cur)
        conn.close()

    score = mvp_score(summary, runtime_latest if isinstance(runtime_latest, dict) else {}, note_cov)
    gaps = []
    if note_cov["ratio"] < 0.8:
        gaps.append("note_id 覆盖率不足，仍存在标题回退归因")
    if pending > 0:
        gaps.append("待归因样本仍未清空，Bandit 学习信号偏弱")
    if not summary.get("strategy_learning", {}).get("openclaw_enabled"):
        gaps.append("OpenClaw 生成链路未稳定启用")
    if not runtime_latest:
        gaps.append("Runtime Bridge 轨迹缺失")

    report_md = os.path.join(ROOT, "docs", "LATEST_PROGRESS.md")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# LATEST PROGRESS",
        "",
        f"更新时间：{now}",
        "",
        "## MVP 评分",
        f"- score: {score}/100",
        "",
        "## 核心状态",
        f"- run_id: {summary.get('strategy_learning', {}).get('run_id')}",
        f"- selection_policy: {summary.get('strategy_learning', {}).get('selection_policy')}",
        f"- generation_mode: {summary.get('strategy_learning', {}).get('generation_mode')}",
        f"- pending_reward: {pending}",
        f"- note_id_coverage: {note_cov['with_note_id']}/{note_cov['total']} ({note_cov['ratio']*100:.2f}%)",
        f"- runtime_latest_step: {runtime_latest.get('step_id') if isinstance(runtime_latest, dict) else None}",
        f"- runtime_latest_ok: {runtime_latest.get('ok') if isinstance(runtime_latest, dict) else None}",
        "",
        "## 未完善项（自动生成）",
    ]
    if gaps:
        lines.extend([f"- {g}" for g in gaps])
    else:
        lines.append("- 当前自动检查未发现阻塞项")
    lines.extend(
        [
            "",
            "## 证据文件",
            f"- summary: {summary_file}",
            f"- self_audit: {self_audit_file}",
            f"- runtime_latest: {runtime_latest_file}",
            "",
        ]
    )
    with open(report_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    status_json = os.path.join(data_dir, "runtime", "mvp_status.json")
    os.makedirs(os.path.dirname(status_json), exist_ok=True)
    payload = {
        "updated_at": now,
        "score": score,
        "pending_reward": pending,
        "note_id_coverage": note_cov,
        "gaps": gaps,
    }
    with open(status_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(json.dumps({"report": report_md, "status": status_json, "score": score, "gaps": len(gaps)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
