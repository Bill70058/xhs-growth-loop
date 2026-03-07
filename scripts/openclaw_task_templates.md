# OpenClaw 任务模板

## 1) 每日分析任务
请读取 `xhs-growth-loop/data/analysis/latest_summary.json`，输出：
- 今天最关键的 3 个发现
- 明天选题建议 3 条
- 风险提醒 2 条
保存为 `xhs-growth-loop/data/analysis/daily_brief.md`。

## 2) 候选贴文生成任务
基于 `xhs-growth-loop/data/analysis/latest_summary.json` 生成 5 条候选贴文。
每条必须包含：
- 标题（20-30 字）
- 正文（结构化，含开头钩子、方法、CTA）
- 标签（3-5 个）
保存到 `xhs-growth-loop/data/candidates/candidates_manual_{{date}}.json`。

## 3) 复盘优化任务
读取最近 7 天 `post_metrics_daily`，输出：
- 高表现内容的共同特征
- 低表现内容的主要问题
- 下一轮优化策略（选题、开头、发布时间、CTA）
保存为 `xhs-growth-loop/data/analysis/weekly_optimization.md`。
