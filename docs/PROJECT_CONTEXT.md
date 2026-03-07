# PROJECT CONTEXT

## 1) 技术架构
- Orchestrator：OpenClaw（任务编排、总结、策略建议）
- Collector A：Spider_XHS（PC/API 采集）
- Collector B + Publisher：XiaohongshuSkills（CDP 浏览器自动化采集与发布）
- Storage：SQLite（`data/growth.db`）
- Pipeline：Shell + Python 脚本

## 2) 数据流
1. `01_collect.sh` 执行双通道采集：
   - `01_collect_own.sh`：采集你自己的发文数据（复盘）
   - `01_collect_market.sh`：按关键词采集市场内容（学习）
2. `02_analyze.py` 汇总双通道数据并产出 `data/analysis/latest_summary.json`
3. `03_generate_candidates.py` 读分析结果，生成候选贴文到 `data/candidates/*.json`
4. `04_publish_preview.sh` 读取第 1 条候选，用 `--preview` 预填充发布
5. `05_publish.sh` 执行正式发布

## 2.1) 浏览器与端口约定
- 自动化链路使用隔离 Chrome 用户目录：`/Users/billlin/Google/Chrome/XiaohongshuProfiles/default`
- 当前稳定调试端口：`9333`
- 不复用日常默认 Chrome 数据目录（受 Chrome CDP 限制）

## 3) 数据表
- `post_metrics_daily`：每日笔记表现
- `candidate_posts`：候选贴文池
- `publish_records`：发布记录

## 4) 运行模式
- 安全演练：`DRY_RUN=1 bash scripts/run_daily_loop.sh`
- 真实跑批：`bash scripts/run_daily_loop.sh`
- 人工稳定执行（推荐）：
  1. `python3 vendors/XiaohongshuSkills/scripts/cdp_publish.py --account default --port 9333 check-login`
  2. `python3 vendors/XiaohongshuSkills/scripts/cdp_publish.py --account default --port 9333 content-data --csv-file ...`
  3. `python3 vendors/XiaohongshuSkills/scripts/publish_pipeline.py --account default --port 9333 --preview ...`

## 5) 合规边界
- 优先使用自有账号与可授权数据。
- 默认半自动发布（先预览后确认）。
- 不在文档中保存 API Key 明文。
