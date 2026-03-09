# AUTOPILOT

更新时间：2026-03-09

## 目标
通过 OpenClaw runtime 决策实现不停机推进：
1. 持续执行采集/分析/生成/复盘；
2. 遇到异常自动请求决策并重试；
3. 每轮自动记录最新进度与未完善项。

## 入口
1. 启动：`bash scripts/start_autopilot.sh`
2. 停止：`bash scripts/stop_autopilot.sh`

## 执行链路
1. `scripts/openclaw_autopilot.py` 请求 `OPENCLAW_RUNTIME_NEXT_URL` 获取下一步计划；
2. 每个 step 通过 `scripts/openclaw_runtime_bridge.py` 执行；
3. 失败时调用 `OPENCLAW_RUNTIME_URL` 获取 retry/skip/fail 决策；
4. 每轮更新：
   - `docs/LATEST_PROGRESS.md`
   - `data/runtime/mvp_status.json`
   - `data/runtime/bridge_*.jsonl`

## 现状
1. 当前 runtime-next 仍为 mock 规则决策；
2. 已能在服务不可用时自动拉起本地 mock 并继续执行；
3. `MVP score` 已接入自动打分，当前分数由样本质量与回流完成度驱动。

## 未完善
1. 缺少“达到成熟阈值自动降频”策略；
2. 缺少真实 OpenClaw prompt/version registry 与质量评测闭环；
3. 缺少外部通知告警（飞书/邮件）。
