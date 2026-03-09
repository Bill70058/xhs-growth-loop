#!/usr/bin/env python3
import json
import os
import subprocess
import time
from datetime import datetime
from urllib import error, request
from urllib.parse import urlparse

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
        if k in out or k.startswith("OPENCLAW_") or k.startswith("AUTOPILOT_"):
            out[k] = v
    return out


def default_runtime_next_url(env):
    if env.get("OPENCLAW_RUNTIME_NEXT_URL"):
        return env["OPENCLAW_RUNTIME_NEXT_URL"]
    runtime_url = env.get("OPENCLAW_RUNTIME_URL", "http://127.0.0.1:8787/runtime-help")
    if runtime_url.endswith("/runtime-help"):
        return runtime_url[: -len("/runtime-help")] + "/runtime-next"
    return runtime_url.rstrip("/") + "/runtime-next"


def safe_json(path, fallback):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return fallback


def call_runtime_next(url, timeout, payload):
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("runtime-next response is not object")
    decision = data.get("decision")
    if not isinstance(decision, dict):
        raise ValueError("runtime-next decision missing")
    return decision


def run_bridge_step(python_bin, step_id, cmd, soft_fail, max_retries):
    args = [
        python_bin,
        os.path.join(ROOT, "scripts", "openclaw_runtime_bridge.py"),
        "--step-id",
        step_id,
        "--max-retries",
        str(max_retries),
    ]
    if soft_fail:
        args.append("--soft-fail")
    args.extend(["--", "/bin/bash", "-lc", cmd])
    p = subprocess.run(args, cwd=ROOT)
    return int(p.returncode)


def try_start_local_openclaw_mock():
    script = os.path.join(ROOT, "scripts", "start_openclaw_mock.sh")
    if not os.path.exists(script):
        return False
    p = subprocess.run(
        ["/bin/bash", script, "--daemon"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return int(p.returncode) == 0


def main():
    env = load_env(ENV_FILE)
    python_bin = env.get("PYTHON_BIN", os.path.join(ROOT, ".venv314", "bin", "python"))
    if not os.path.exists(python_bin):
        python_bin = "/usr/bin/python3"

    max_cycles = int(env.get("AUTOPILOT_MAX_CYCLES", "100000"))
    sleep_seconds_default = int(env.get("AUTOPILOT_SLEEP_SECONDS", "45"))
    runtime_next_url = default_runtime_next_url(env)
    runtime_timeout = int(env.get("OPENCLAW_RUNTIME_TIMEOUT", "20"))
    max_retries = int(env.get("OPENCLAW_RUNTIME_MAX_RETRIES", "2"))
    runtime_auto_start_mock = str(env.get("OPENCLAW_RUNTIME_AUTO_START_MOCK", "1")).strip().lower() in ("1", "true", "yes", "on")
    log_file = os.path.join(ROOT, "logs", "autopilot.log")
    heartbeat_file = os.path.join(ROOT, "data", "runtime", "autopilot_heartbeat.json")
    milestones_file = os.path.join(ROOT, "data", "runtime", "autopilot_milestones.jsonl")
    milestones_latest_file = os.path.join(ROOT, "data", "runtime", "autopilot_milestones_latest.json")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    os.makedirs(os.path.dirname(heartbeat_file), exist_ok=True)

    cycle = 0
    while cycle < max_cycles:
        cycle += 1
        summary = safe_json(os.path.join(ROOT, "data", "analysis", "latest_summary.json"), {})
        mvp = safe_json(os.path.join(ROOT, "data", "runtime", "mvp_status.json"), {"score": 0})
        base_run_id = int(summary.get("strategy_learning", {}).get("run_id", 0) or 0)
        base_pending = int(summary.get("experiment_sync", {}).get("reward_update", {}).get("pending", 0) or 0)
        base_score = int(mvp.get("score", 0) or 0)
        base_note_ratio = float(mvp.get("note_id_coverage", {}).get("ratio", 0.0) or 0.0)
        payload = {
            "cycle": cycle,
            "time": datetime.now().isoformat(timespec="seconds"),
            "pending_reward": int(summary.get("experiment_sync", {}).get("reward_update", {}).get("pending", 0) or 0),
            "mvp": mvp,
            "summary_hint": {
                "run_id": summary.get("strategy_learning", {}).get("run_id"),
                "selection_policy": summary.get("strategy_learning", {}).get("selection_policy"),
            },
        }
        with open(heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "cycle": cycle,
                    "state": "planning",
                    "runtime_next_url": runtime_next_url,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        try:
            decision = call_runtime_next(runtime_next_url, runtime_timeout, payload)
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            parsed = urlparse(runtime_next_url)
            local_runtime = parsed.hostname in ("127.0.0.1", "localhost")
            recovered = False
            if runtime_auto_start_mock and local_runtime:
                if try_start_local_openclaw_mock():
                    time.sleep(1)
                    try:
                        decision = call_runtime_next(runtime_next_url, runtime_timeout, payload)
                        recovered = True
                    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
                        recovered = False
            if not recovered:
                decision = {
                    "continue": True,
                    "sleep_seconds": sleep_seconds_default,
                    "reason": "runtime_next_unavailable",
                    "plan": [
                        {"step_id": "openclaw_generate", "cmd": "bash scripts/run_openclaw_generate.sh", "soft_fail": False},
                        {"step_id": "progress_report", "cmd": ".venv314/bin/python scripts/08_progress_report.py", "soft_fail": True},
                    ],
                }

        plan = decision.get("plan", [])
        if not isinstance(plan, list) or not plan:
            plan = [{"step_id": "openclaw_generate", "cmd": "bash scripts/run_openclaw_generate.sh", "soft_fail": False}]

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"cycle": cycle, "decision": decision}, ensure_ascii=False) + "\n")
        with open(heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "cycle": cycle,
                    "state": "executing",
                    "decision_reason": decision.get("reason"),
                    "sleep_seconds": int(decision.get("sleep_seconds", sleep_seconds_default) or sleep_seconds_default),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        step_results = []
        for idx, item in enumerate(plan, start=1):
            step_id = str(item.get("step_id") or f"cycle{cycle}_step{idx}")
            cmd = str(item.get("cmd") or "").strip()
            if not cmd:
                continue
            soft_fail = bool(item.get("soft_fail", False))
            rc = run_bridge_step(python_bin, step_id, cmd, soft_fail, max_retries)
            step_results.append({"step_id": step_id, "rc": rc, "soft_fail": soft_fail})
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"cycle": cycle, "step_id": step_id, "cmd": cmd, "rc": rc}, ensure_ascii=False) + "\n")
            if rc != 0 and not soft_fail:
                break

        summary2 = safe_json(os.path.join(ROOT, "data", "analysis", "latest_summary.json"), {})
        mvp2 = safe_json(os.path.join(ROOT, "data", "runtime", "mvp_status.json"), {"score": 0})
        after_run_id = int(summary2.get("strategy_learning", {}).get("run_id", 0) or 0)
        after_pending = int(summary2.get("experiment_sync", {}).get("reward_update", {}).get("pending", 0) or 0)
        after_score = int(mvp2.get("score", 0) or 0)
        after_note_ratio = float(mvp2.get("note_id_coverage", {}).get("ratio", 0.0) or 0.0)

        milestones = []
        if after_run_id > base_run_id:
            milestones.append(f"新增实验 run_id {after_run_id}（+{after_run_id - base_run_id}）")
        if after_score > base_score:
            milestones.append(f"MVP score 提升 {base_score}->{after_score}")
        if after_pending < base_pending:
            milestones.append(f"待归因下降 {base_pending}->{after_pending}")
        if after_note_ratio > base_note_ratio:
            milestones.append(f"note_id 覆盖率提升 {base_note_ratio:.2%}->{after_note_ratio:.2%}")
        if not milestones:
            milestones.append("无显著提升，维持闭环执行")

        if after_pending > 0:
            conclusion = f"继续执行：当前待归因 {after_pending}，学习信号仍偏弱"
        elif after_score >= 80:
            conclusion = "进入较成熟 MVP 阶段，可考虑降频和稳定化"
        else:
            conclusion = "闭环稳定，继续累积奖励样本以推动策略学习"

        cycle_summary = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "cycle": cycle,
            "decision_reason": decision.get("reason"),
            "milestones": milestones,
            "conclusion": conclusion,
            "base": {
                "run_id": base_run_id,
                "score": base_score,
                "pending_reward": base_pending,
                "note_id_ratio": base_note_ratio,
            },
            "after": {
                "run_id": after_run_id,
                "score": after_score,
                "pending_reward": after_pending,
                "note_id_ratio": after_note_ratio,
            },
            "steps": step_results,
        }
        with open(milestones_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(cycle_summary, ensure_ascii=False) + "\n")
        with open(milestones_latest_file, "w", encoding="utf-8") as f:
            json.dump(cycle_summary, f, ensure_ascii=False, indent=2)

        if not bool(decision.get("continue", True)):
            with open(heartbeat_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "cycle": cycle,
                        "state": "stopped",
                        "reason": "decision_continue_false",
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            break
        if cycle >= max_cycles:
            with open(heartbeat_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "cycle": cycle,
                        "state": "stopped",
                        "reason": "reach_max_cycles",
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            break
        sleep_seconds = int(decision.get("sleep_seconds", sleep_seconds_default) or sleep_seconds_default)
        with open(heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "cycle": cycle,
                    "state": "sleeping",
                    "sleep_seconds": max(sleep_seconds, 5),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        time.sleep(max(sleep_seconds, 5))


if __name__ == "__main__":
    main()
