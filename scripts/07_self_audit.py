#!/usr/bin/env python3
import json
import os
import sqlite3
from datetime import datetime

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


def read_summary(data_dir):
    p = os.path.join(data_dir, "analysis", "latest_summary.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, "r", encoding="utf-8"))
    except Exception:
        return {}


def build_findings(db_path, summary):
    findings = []
    risk = []
    if not os.path.exists(db_path):
        risk.append("数据库不存在，无法执行策略学习与回流更新。")
        return findings, risk

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # A/B diversity: check recent run arm diversity
    cur.execute(
        """
        SELECT id FROM experiment_runs ORDER BY id DESC LIMIT 1
        """
    )
    row = cur.fetchone()
    if row:
        run_id = row[0]
        cur.execute("SELECT COUNT(DISTINCT arm_key), COUNT(*) FROM experiment_arms WHERE run_id = ?", (run_id,))
        distinct_arms, total_arms = cur.fetchone()
        findings.append(f"最近一次实验 run_id={run_id}，arm 多样性 {distinct_arms}/{total_arms}。")
        if int(distinct_arms or 0) < 2 and int(total_arms or 0) >= 2:
            risk.append("A/B 臂多样性不足，探索能力受限。")

    # Reward effectiveness
    cur.execute("SELECT COUNT(*) FROM policy_reward_events")
    reward_events = int(cur.fetchone()[0] or 0)
    findings.append(f"累计奖励事件数：{reward_events}")
    if reward_events < 5:
        risk.append("有效奖励样本偏少，Bandit 参数尚未进入稳定学习期。")

    # Pending rewards
    exp_sync = summary.get("experiment_sync", {})
    pending = (((exp_sync or {}).get("reward_update") or {}).get("pending")) or 0
    findings.append(f"待归因样本数（pending）：{pending}")
    if int(pending) > 0:
        risk.append("存在待归因样本，需等待 T+1/T+2 指标或发布完成。")

    # OpenClaw quality status
    st = summary.get("strategy_learning", {})
    if st:
        findings.append(
            f"当前策略: {st.get('selection_policy')} | mode: {st.get('generation_mode')} | openclaw_error: {st.get('openclaw_error')}"
        )
        if st.get("openclaw_error"):
            risk.append("OpenClaw 当前有错误回退，需检查服务可用性或输出质量。")

    conn.close()
    return findings, risk


def write_report(path, findings, risk):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# SELF AUDIT",
        "",
        f"更新时间：{now}",
        "",
        "## 检测结果",
    ]
    if findings:
        for i, item in enumerate(findings, start=1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("1. 暂无可用检测结果。")

    lines.append("")
    lines.append("## 当前不足（自动识别）")
    if risk:
        for i, item in enumerate(risk, start=1):
            lines.append(f"{i}. {item}")
    else:
        lines.append("1. 未发现明显阻塞项。")

    lines.append("")
    lines.append("## 建议下一步")
    if risk:
        for i, item in enumerate(risk, start=1):
            lines.append(f"{i}. 针对：{item}")
    else:
        lines.append("1. 继续扩大样本并观察 Bandit 收敛趋势。")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    env = load_env(ENV)
    data_dir = env.get("DATA_DIR", os.path.join(ROOT, "data"))
    db_path = env.get("DB_PATH", os.path.join(data_dir, "growth.db"))
    summary = read_summary(data_dir)
    findings, risk = build_findings(db_path, summary)
    out = os.path.join(ROOT, "docs", "SELF_AUDIT.md")
    write_report(out, findings, risk)
    print(json.dumps({"report": out, "findings": len(findings), "risks": len(risk)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
