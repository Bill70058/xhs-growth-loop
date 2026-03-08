# XHS Growth Loop (OpenClaw + Spider_XHS + XiaohongshuSkills)

这个目录是你的小红书增长闭环脚手架：
- 采集：
  - 通道 A（自己的数据复盘）：创作者 `content-data`
  - 通道 B（市场学习数据）：关键词检索高表现帖子
- 分析：本地 SQLite + Python
- 生成：OpenClaw 调用模型产出候选贴文
- 发布：XiaohongshuSkills（建议先 `--preview` 人审）
- 复盘：次日回收数据，进入下一轮

## 0. 新会话必读
- `docs/START_HERE.md`：1 分钟了解项目目标、现状、下一步
- `docs/PROJECT_CONTEXT.md`：技术架构、数据流、依赖边界
- `docs/CURRENT_STATUS.md`：已完成项、可运行状态、风险
- `docs/NEXT_STEPS.md`：按优先级执行清单
- `docs/NEW_CHAT_HANDOFF_PROMPT.md`：新聊天窗口直接复制粘贴

## 1. 目录
- `scripts/`：每日任务脚本
- `sql/schema.sql`：SQLite 建表
- `config/.env.example`：环境变量模板
- `data/`：采集、分析、候选、发布记录
- `logs/`：任务日志
- `frontend/`：React 前端控制台（意图解析、选题、词云、账号与预览触发）

## 2. 准备
1. 复制环境变量模板：
   - `cp config/.env.example config/.env`
2. 填入本机路径与账号信息
3. 初始化数据库：
   - `sqlite3 data/growth.db < sql/schema.sql`

## 3. 每日运行
1. 采集数据
   - `bash scripts/01_collect.sh`
   - 内部会自动执行：
     - `scripts/01_collect_own.sh`
     - `scripts/01_collect_market.sh`
2. 分析表现
   - `python3 scripts/02_analyze.py`
3. 生成候选贴文（OpenClaw）
   - `python3 scripts/03_generate_candidates.py`
4. 预览发布（推荐）
   - `bash scripts/04_publish_preview.sh`
5. 人工确认后正式发布
   - `bash scripts/05_publish.sh`

## 4. 一键串行
- `bash scripts/run_daily_loop.sh`

## 5. 前端控制台（独立线程）
1. 启动前端：
   - `cd frontend`
   - `npm run dev:dashboard -- --host 127.0.0.1`
2. 启动本地桥接服务（用于写候选、触发预览）：
   - `npm run bridge`
3. 打开：`http://127.0.0.1:5174/`

详细操作见：`docs/FRONTEND_DASHBOARD.md`

## 6. OpenClaw 自动任务模板
见 `scripts/openclaw_task_templates.md`。

## 7. 合规建议
- 先用自有账号数据闭环，不做大规模未授权抓取。
- 发布先半自动（`--preview` + 人审），稳定后再自动化。
- API Key 泄露后立即轮换。
