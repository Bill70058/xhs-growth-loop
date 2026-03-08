# CURRENT STATUS

更新时间：2026-03-08

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

## 可验证产物
- 分析结果：`data/analysis/latest_summary.json`
- 候选贴文：`data/candidates/candidates_2026-03-08.json`
- 前端数据：`frontend/public/data/dashboard.json`
- 运行日志：`logs/` 下当日日志
- 预览成功日志关键词：`FILL_STATUS: READY_TO_PUBLISH`

## 当前风险
1. 真实采集依赖账号登录态与页面结构稳定性。
2. 自动发布存在平台风控风险，建议持续使用 `--preview` 人审。
3. 候选生成虽已支持市场驱动，但仍是规则/轻策略版，未接策略学习与 A/B 自动决策。
4. `content-data` 可能长期为空（账号侧无数据），需依赖市场流作为主驱动。

## 已知约束
- 项目路径含空格，脚本中路径必须加引号。
- 未在文档中保存任何密钥；密钥仅通过环境变量或交互输入。
- Chrome 限制：CDP 调试不能使用默认浏览数据目录；必须使用非默认 `user-data-dir`（隔离实例）。
- 当前稳定执行口径：在隔离实例下使用 `--port 9333`。

## 未完善功能清单
1. 前端“解析输入 -> 采集市场数据”仍是命令预览，尚未一键触发采集。
2. 账号切换后的登录状态巡检还未自动化（当前通过手动“登录该账号”触发）。
3. 候选生成脚本尚未接 LLM 真实策略与历史高分特征。
4. 缺少统一告警机制（采集空数据、登录失效、发布失败）。
