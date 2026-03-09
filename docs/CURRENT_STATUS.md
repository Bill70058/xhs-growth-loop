# CURRENT STATUS

更新时间：2026-03-09

## 已完成
1. 项目脚手架已创建并可运行。
2. `.env` 已按本机路径配置完成。
3. SQLite 已初始化，3 张核心表已创建。
4. 两个依赖仓库已克隆：
   - `vendors/Spider_XHS`
   - `vendors/XiaohongshuSkills`
5. 两侧 Python 依赖已安装完成。
6. 已跑通 dry run（不触发真实发布）。
7. 已跑通真实链路的关键节点（基于隔离实例 `port=9333`）：
   - 创作者登录校验成功
   - 采集命令成功执行
   - 预览填充成功，状态 `FILL_STATUS: READY_TO_PUBLISH`
8. 已确认并修复多用户浏览器导致的执行偏差：
   - 默认业务浏览器与自动化浏览器分离
   - `XiaohongshuSkills` 账号配置回归隔离模式为默认
9. 已补齐 `publish_records` 自动入库（预览/发布都写入状态与日志）。
10. 已补齐空 `content-data` 降级链路：
   - `02_analyze.py` 支持 `own_data_status` 标记
   - `03_generate_candidates.py` 支持市场数据驱动生成
11. 已上线 React 前端控制台（`frontend/`）：
   - 意图输入解析（OpenClaw/LLM/规则兜底）
   - 候选可点击选择并触发预览
   - 多账号创建、选择、登录触发（右上角账号区）
12. 已完成 Phase 1 策略学习落地（2026-03-09）：
   - 新增实验表：`experiment_runs`、`experiment_arms`
   - 候选生成升级为“Thompson Sampling + 规则打分融合排序 + selected 标记”
   - 发布脚本改为优先发布 `selected=true`（无则取最高分）
   - `02_analyze.py` 已支持 `publish_records -> experiment_arms` 回流同步
13. 已完成前端策略看板可视化（2026-03-09）：
   - 展示 `strategy_learning`、`experiment_sync`
   - 展示 Arm 状态分布、分数与策略结构
14. 已完成前端“一键市场采集”能力（2026-03-09）：
   - bridge 新增 `/api/collect-market`
   - 解析选题后可直接触发 `01_collect_market.sh`
15. 候选生成已接 OpenClaw 优先链路（2026-03-09）：
   - `03_generate_candidates.py` 支持 `OPENCLAW_CANDIDATE_*` 配置
   - OpenClaw 不可用时自动降级到本地模板并记录 `openclaw_error`
   - 已增加重试、幂等请求键、prompt version、质量校验
16. 已增加独立奖励回写脚本（2026-03-09）：
   - `scripts/06_update_rewards.py`：按 T+1/T+2 指标更新 `result_label/engagement_rate`
   - 同步更新 `policy_arm_stats`，形成可持续学习参数
17. 已增加链路健康检查与自执行脚本（2026-03-09）：
   - `scripts/00_healthcheck.py`：检查 Python、DB、CDP、OpenClaw 可用性
   - `scripts/run_openclaw_generate.sh`：自动探活并执行“分析->奖励更新->生成->分析->前端同步”
18. 已上线自检报告（2026-03-09）：
   - `scripts/07_self_audit.py` 自动生成 `docs/SELF_AUDIT.md`
   - 自动识别当前策略不足（样本量、待归因等）
19. 已上线 OpenClaw Runtime Bridge（2026-03-09）：
   - `scripts/openclaw_runtime_bridge.py` 支持失败阻塞上报、OpenClaw 决策回传、自动重试
   - `scripts/run_openclaw_generate.sh` 已切换为桥接执行关键步骤
   - 默认使用 `OPENCLAW_RUNTIME_URL=/runtime-help`，并输出执行轨迹到 `data/runtime/`
20. 已完成 note_id 优先归因改造（2026-03-09）：
   - `publish_records` 新增 `note_id`
   - 发布脚本自动从 note_link/raw_result 提取并写入 `note_id`
   - 奖励更新优先按 `post_metrics_daily.post_id` 精确匹配，失败后才回退标题匹配
21. 已上线连续执行 Autopilot（2026-03-09）：
   - `scripts/openclaw_autopilot.py` 基于 `OPENCLAW_RUNTIME_NEXT_URL` 拉取下一步计划
   - 每一步走 `openclaw_runtime_bridge.py`（失败时自动回传 OpenClaw 决策）
   - 自动更新 `docs/LATEST_PROGRESS.md` 和 `data/runtime/mvp_status.json`

## 可验证产物
- 分析结果：`data/analysis/latest_summary.json`
- 候选贴文：`data/candidates/candidates_YYYY-MM-DD.json`
- 前端数据：`frontend/public/data/dashboard.json`
- 运行日志：`logs/` 下当日日志
- 预览成功日志关键词：`FILL_STATUS: READY_TO_PUBLISH`
- 自动进度报告：`docs/LATEST_PROGRESS.md`

## 当前风险
1. 真实采集依赖账号登录态与页面结构稳定性。
2. 自动发布存在平台风控风险，建议持续使用 `--preview` 人审。
3. 虽已接入 Thompson Sampling，但可用奖励样本仍偏少，策略参数尚处冷启动阶段。
4. `content-data` 可能长期为空（账号侧无数据），需依赖市场流作为主驱动。
5. OpenClaw 候选服务若未启动，当前会走自动回退（可用但策略增益受限）。
6. T+1/T+2 已支持 note_id 优先归因，但真实发布日志中 note_id 覆盖率仍受外部返回格式影响。
7. 历史旧发布记录（未带 run_id）会被标记为 `legacy_pending_publish_records`，不再强行回流。
8. Runtime Bridge 当前使用 mock 决策策略，真实 OpenClaw 决策规则仍需上线。

## 已知约束
- 项目路径含空格，脚本中路径必须加引号。
- 未在文档中保存任何密钥；密钥仅通过环境变量或交互输入。
- Chrome 限制：CDP 调试不能使用默认浏览数据目录；必须使用非默认 `user-data-dir`（隔离实例）。
- 当前稳定执行口径：在隔离实例下使用 `--port 9333`。

## 未完善功能清单
1. 账号切换后的登录状态巡检还未自动化（当前通过手动“登录该账号”触发）。
2. note_id 覆盖率仍不足，奖励回流仍有部分落到标题回退路径。
3. 需要真实 OpenClaw 服务替代 mock，并引入 prompt/version registry。
4. 缺少统一告警机制（采集空数据、登录失效、发布失败）。
