# NEXT STEPS

## P0（今天就做）
1. 固化隔离实例执行口径（避免误用默认浏览器）：
   - 启动隔离实例并固定端口 `9333`
   - 采集与预览命令统一显式传 `--port 9333`
2. 跑一次真实采集并确认非空：
   - `python3 vendors/XiaohongshuSkills/scripts/cdp_publish.py --account default --port 9333 content-data --csv-file data/raw/content_data_$(date +%F).csv`
3. 分析与候选生成：
   - `python3 scripts/02_analyze.py`
   - `python3 scripts/03_generate_candidates.py`
4. 预览发布并人工审核（使用 9333）：`python3 vendors/XiaohongshuSkills/scripts/publish_pipeline.py --account default --port 9333 --preview ...`
5. 把本次运行结果写入 `CURRENT_STATUS.md`（是否非空、是否到 `READY_TO_PUBLISH`）。

## P1（本周完成）
1. 给 `scripts/01_collect.sh`、`scripts/04_publish_preview.sh`、`scripts/05_publish.sh` 增加 `XHS_CDP_PORT` 环境变量支持。
2. 给 `publish_records` 补写入逻辑（预览/发布都入库：time、candidate_id、status、note_link）。
3. 增加失败重试与告警（采集失败、发布失败、空数据）。
4. 将候选生成升级为“模板 + 历史高分特征”混合策略。

## P2（两周内）
1. 增加 A/B 机制：同主题多开头版本对比。
2. 增加每周复盘报告（自动输出 top/bottom 内容特征）。
3. 接入 OpenClaw 自动任务（日报、候选生成、周复盘）。
4. 增加“账号状态巡检”任务（每日首次运行前检查 creator 登录是否失效）。

## 完成判定
- 每天至少稳定输出：
  - 1 份非空数据摘要（或明确空数据原因）
  - 3 条候选贴文
  - 1 次预览发布
- 每周能看到策略更新痕迹，而不是重复同一模板。
