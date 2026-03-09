#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
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
        if k in out or k.startswith("OPENCLAW_"):
            out[k] = v
    return out


def env_truthy(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def default_runtime_url(env):
    if env.get("OPENCLAW_RUNTIME_URL"):
        return env["OPENCLAW_RUNTIME_URL"]
    candidate_url = env.get("OPENCLAW_CANDIDATE_URL", "http://127.0.0.1:8787/candidates")
    if candidate_url.endswith("/candidates"):
        return candidate_url[: -len("/candidates")] + "/runtime-help"
    return candidate_url.rstrip("/") + "/runtime-help"


def run_cmd(cmd, extra_env):
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        env={**os.environ, **extra_env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return {
        "returncode": int(p.returncode),
        "stdout": str(p.stdout or ""),
        "stderr": str(p.stderr or ""),
    }


def call_runtime_help(url, timeout, payload):
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("runtime help response is not object")
    return parsed


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


def append_event(step_id, event):
    out_dir = os.path.join(ROOT, "data", "runtime")
    os.makedirs(out_dir, exist_ok=True)
    event_path = os.path.join(out_dir, f"bridge_{step_id}.jsonl")
    with open(event_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    latest_path = os.path.join(out_dir, "bridge_latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(event, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--soft-fail", action="store_true")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise SystemExit("missing command after --")

    env = load_env(ENV_FILE)
    runtime_enabled = env_truthy(env.get("OPENCLAW_RUNTIME_ENABLED"), default=True)
    runtime_url = default_runtime_url(env)
    runtime_timeout = int(env.get("OPENCLAW_RUNTIME_TIMEOUT", str(args.timeout)))
    runtime_auto_start_mock = env_truthy(env.get("OPENCLAW_RUNTIME_AUTO_START_MOCK"), default=True)
    run_request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    extra_env = {}
    attempts = max(args.max_retries, 0) + 1
    for attempt in range(1, attempts + 1):
        started = time.time()
        result = run_cmd(cmd, extra_env=extra_env)
        elapsed = round(time.time() - started, 3)
        ok = result["returncode"] == 0
        event = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "request_id": run_request_id,
            "step_id": args.step_id,
            "attempt": attempt,
            "max_attempts": attempts,
            "cmd": cmd,
            "elapsed_seconds": elapsed,
            "ok": ok,
            "returncode": result["returncode"],
            "stdout_tail": result["stdout"][-1200:],
            "stderr_tail": result["stderr"][-1200:],
            "runtime_enabled": runtime_enabled,
            "runtime_url": runtime_url if runtime_enabled else None,
        }

        if ok:
            append_event(args.step_id, event)
            print(json.dumps(event, ensure_ascii=False))
            return 0

        decision = {
            "action": "retry" if attempt < attempts else "fail",
            "wait_seconds": 0,
            "env_overrides": {},
            "reason": "local_default",
        }
        runtime_error = None
        if runtime_enabled and attempt < attempts:
            payload = {
                "request_id": run_request_id,
                "step_id": args.step_id,
                "attempt": attempt,
                "max_attempts": attempts,
                "cmd": cmd,
                "returncode": result["returncode"],
                "stdout_tail": result["stdout"][-1000:],
                "stderr_tail": result["stderr"][-1000:],
            }
            try:
                reply = call_runtime_help(runtime_url, runtime_timeout, payload)
                if isinstance(reply.get("decision"), dict):
                    d = reply["decision"]
                    decision = {
                        "action": str(d.get("action", "retry")),
                        "wait_seconds": int(d.get("wait_seconds", 0) or 0),
                        "env_overrides": d.get("env_overrides", {}) if isinstance(d.get("env_overrides"), dict) else {},
                        "reason": str(d.get("reason", "openclaw_runtime")),
                    }
                else:
                    decision["reason"] = "openclaw_missing_decision"
            except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
                runtime_error = str(e)
                decision["reason"] = "openclaw_runtime_unavailable"
                parsed = urlparse(runtime_url)
                local_runtime = parsed.hostname in ("127.0.0.1", "localhost")
                if runtime_auto_start_mock and local_runtime:
                    if try_start_local_openclaw_mock():
                        time.sleep(1)
                        try:
                            reply2 = call_runtime_help(runtime_url, runtime_timeout, payload)
                            if isinstance(reply2.get("decision"), dict):
                                d = reply2["decision"]
                                decision = {
                                    "action": str(d.get("action", "retry")),
                                    "wait_seconds": int(d.get("wait_seconds", 0) or 0),
                                    "env_overrides": d.get("env_overrides", {}) if isinstance(d.get("env_overrides"), dict) else {},
                                    "reason": str(d.get("reason", "openclaw_runtime_restart_ok")),
                                }
                                runtime_error = None
                        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e2:
                            runtime_error = str(e2)

        event["decision"] = decision
        if runtime_error:
            event["runtime_error"] = runtime_error
        append_event(args.step_id, event)
        print(json.dumps(event, ensure_ascii=False))

        if decision["action"] == "retry" and attempt < attempts:
            extra_env.update({str(k): str(v) for k, v in decision.get("env_overrides", {}).items()})
            wait_seconds = max(int(decision.get("wait_seconds", 0)), 0)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            continue

        if decision["action"] == "skip" and args.soft_fail:
            return 0

        if attempt >= attempts and args.soft_fail:
            return 0

        return int(result["returncode"] or 1)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
