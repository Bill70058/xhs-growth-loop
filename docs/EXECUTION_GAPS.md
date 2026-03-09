# EXECUTION GAPS（自动执行未完成项）

更新时间：2026-03-09

## 已完成到可运行
1. OpenClaw 候选生成已接入，带重试、幂等键、质量校验、回退。
2. A/B 自动决策已上线基础版（Thompson Sampling + rule score 融合）。
3. 发布回流已同步到实验臂，并支持奖励更新写入 bandit 参数。
4. 前端已可视化策略实验与 bandit 统计。
5. 一键执行脚本已可自动探活并拉起本地 OpenClaw mock。
6. 已接入 Runtime Bridge：
   - 遇到步骤失败会将阻塞信息上报到 OpenClaw runtime 接口
   - 根据返回决策自动重试并记录轨迹到 `data/runtime/`
7. 已接入 Autopilot 连续执行：
   - `openclaw_autopilot.py` 可按 OpenClaw runtime-next 决策持续推进
   - 每轮自动产出 `docs/LATEST_PROGRESS.md`

## 尚未完成（需要后续继续）
1. **note_id 级归因已部分完成，仍有覆盖率缺口**：
   - 已实现 note_id 优先匹配 + 标题回退。
   - 仍需提高 `publish_records.note_id` 的真实可提取比例，减少回退路径。
2. **真实 OpenClaw 服务替换 mock 未完成**：
   - 现阶段默认可用 mock，真实服务上线后需切换并验证产出质量。
3. **自动告警闭环未完成**：
   - 采集失败、登录失效、发布失败尚未接统一通知通道（如飞书/邮件）。
4. **账号状态巡检自动化未完成**：
   - 前端仍通过“登录该账号”手动触发。
5. **策略淘汰与新臂生成未完成**：
   - 仅有基础 Bandit 更新，尚未自动淘汰低效臂和生成新臂。
6. **真实 Runtime 决策器未完成**：
   - 当前 `/runtime-help` 主要为 mock 规则回包，尚未接入真实问题诊断与策略建议服务。
7. **Autopilot 仍缺更强停止条件**：
   - 当前以循环次数/continue 标志为主，缺“达到成熟 MVP 自动降频”策略。

## 建议的继续执行顺序
1. 提升 note_id 提取覆盖率（发布结果结构化解析 + 入库校验）。
2. 接入真实 OpenClaw 服务并固化 prompt registry（含 runtime 决策模板）。
3. 加入告警通道与失败重试策略分级。
4. 增加策略淘汰与新臂自动生成逻辑。
