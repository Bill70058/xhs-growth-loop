#!/usr/bin/env python3
import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer


HOST = os.environ.get("OPENCLAW_MOCK_HOST", "127.0.0.1")
PORT = int(os.environ.get("OPENCLAW_MOCK_PORT", "8787"))
ENABLE_PREVIEW = str(os.environ.get("AUTOPILOT_ENABLE_PREVIEW", "0")).strip().lower() in ("1", "true", "yes", "on")


def _build_candidates(topic, count, market_seed_titles):
    output = []
    seed_titles = [str(x.get("title", "")).strip() for x in (market_seed_titles or []) if isinstance(x, dict)]
    seed_titles = [x for x in seed_titles if x]
    for i in range(1, count + 1):
        seed = seed_titles[(i - 1) % len(seed_titles)] if seed_titles else "热门内容"
        title = f"{topic}｜{seed[:16]}（OpenClaw候选{i}）"
        content = (
            f"先说结论：{topic}可以通过结构化表达提升转化。\n"
            f"市场信号：最近高频样本是「{seed}」。\n"
            "1) 开头抛出真实场景痛点\n"
            "2) 给出可复制步骤\n"
            "3) 结尾给行动指令与模板领取方式\n"
            "评论区扣1获取完整模板"
        )
        output.append(
            {
                "topic": topic,
                "title": title,
                "content": content,
                "tags": [f"#{topic}", "#经验分享", "#实用"],
                "hook_type": "openclaw_default",
                "structure_type": "three_step",
                "cta_type": "comment_keyword",
            }
        )
    return output


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        if self.path == "/runtime-help":
            self._handle_runtime_help()
            return
        if self.path == "/runtime-next":
            self._handle_runtime_next()
            return
        if self.path != "/candidates":
            self._json(404, {"error": "not_found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size).decode("utf-8", errors="ignore")
            req = json.loads(body or "{}")
            topic = str(req.get("topic", "求职") or "求职").strip() or "求职"
            count = int(req.get("candidate_count", 3) or 3)
            count = max(1, min(count, 10))
            market_seed_titles = req.get("market_seed_titles", [])
            candidates = _build_candidates(topic, count, market_seed_titles)
            self._json(
                200,
                {
                    "provider": "openclaw-mock",
                    "count": len(candidates),
                    "candidates": candidates,
                },
            )
        except Exception as e:
            self._json(500, {"error": "internal_error", "detail": str(e)})

    def _handle_runtime_help(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size).decode("utf-8", errors="ignore")
            req = json.loads(body or "{}")
            attempt = int(req.get("attempt", 1) or 1)
            max_attempts = int(req.get("max_attempts", 1) or 1)
            returncode = int(req.get("returncode", 1) or 1)
            stderr_tail = str(req.get("stderr_tail", "") or "")
            action = "retry" if attempt < max_attempts else "fail"
            wait_seconds = 0
            env_overrides = {}
            reason = "default_retry"

            if returncode == 127 or "command not found" in stderr_tail:
                action = "retry" if attempt < max_attempts else "fail"
                reason = "missing_command_path"
                env_overrides["PATH"] = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
            elif "timed out" in stderr_tail.lower() or "timeout" in stderr_tail.lower():
                action = "retry" if attempt < max_attempts else "fail"
                wait_seconds = 1
                reason = "transient_timeout"

            self._json(
                200,
                {
                    "provider": "openclaw-mock",
                    "decision": {
                        "action": action,
                        "wait_seconds": wait_seconds,
                        "env_overrides": env_overrides,
                        "reason": reason,
                    },
                },
            )
        except Exception as e:
            self._json(500, {"error": "runtime_help_error", "detail": str(e)})

    def _handle_runtime_next(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size).decode("utf-8", errors="ignore")
            req = json.loads(body or "{}")
            cycle = int(req.get("cycle", 0) or 0)
            mvp = req.get("mvp", {}) if isinstance(req.get("mvp"), dict) else {}
            score = int(mvp.get("score", 0) or 0)
            note_cov = mvp.get("note_id_coverage", {}) if isinstance(mvp.get("note_id_coverage"), dict) else {}
            note_ratio = float(note_cov.get("ratio", 0.0) or 0.0)
            pending_reward = int(req.get("pending_reward", 0) or 0)
            plan = []
            # If maturity is low, add market collection to enrich samples.
            if score < 60 and cycle % 2 == 0:
                plan.append(
                    {
                        "step_id": "collect_market_refresh",
                        "cmd": "bash scripts/01_collect_market.sh",
                        "soft_fail": True,
                    },
                )
            # Backpressure: too many pending rewards -> reduce experiment generation frequency.
            if pending_reward >= 8:
                if cycle % 4 == 1:
                    plan.append(
                        {"step_id": "openclaw_generate", "cmd": "bash scripts/run_openclaw_generate.sh", "soft_fail": False}
                    )
                else:
                    plan.append(
                        {"step_id": "reward_backfill", "cmd": ".venv314/bin/python scripts/06_update_rewards.py", "soft_fail": True}
                    )
                    plan.append(
                        {"step_id": "analyze_followup", "cmd": ".venv314/bin/python scripts/02_analyze.py", "soft_fail": True}
                    )
            else:
                plan.append({"step_id": "openclaw_generate", "cmd": "bash scripts/run_openclaw_generate.sh", "soft_fail": False})

            plan.append({"step_id": "progress_report", "cmd": ".venv314/bin/python scripts/08_progress_report.py", "soft_fail": True})
            # If there are pending rewards, keep analysis pass after generate.
            if pending_reward > 0 and pending_reward < 8:
                plan.append(
                    {
                        "step_id": "analyze_followup",
                        "cmd": ".venv314/bin/python scripts/02_analyze.py",
                        "soft_fail": True,
                    }
                )
            # Optional preview to increase publish_records/note_id coverage.
            if ENABLE_PREVIEW and note_ratio < 0.8 and cycle % 3 == 0:
                plan.append(
                    {
                        "step_id": "preview_publish_probe",
                        "cmd": "bash scripts/04_publish_preview.sh",
                        "soft_fail": True,
                    }
                )
            self._json(
                200,
                {
                    "provider": "openclaw-mock",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "decision": {
                        "continue": True,
                        "sleep_seconds": 45,
                        "reason": "mock_autopilot_policy",
                        "plan": plan,
                    },
                },
            )
        except Exception as e:
            self._json(500, {"error": "runtime_next_error", "detail": str(e)})


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print(f"[openclaw-mock] listening on http://{HOST}:{PORT}/candidates")
    server.serve_forever()


if __name__ == "__main__":
    main()
