# START HERE

## 目标
构建一个可持续运行的「小红书内容增长闭环」：
1. 采集数据
2. 分析表现
3. 生成候选贴文
4. 预览/发布
5. 次日复盘并优化下一轮

## 我现在已经有什么
- 闭环脚手架目录：`xhs-growth-loop/`
- 采集脚本：`scripts/01_collect.sh`
- 分析脚本：`scripts/02_analyze.py`
- 候选生成脚本：`scripts/03_generate_candidates.py`
- 预览发布脚本：`scripts/04_publish_preview.sh`
- 正式发布脚本：`scripts/05_publish.sh`
- 串行入口：`scripts/run_daily_loop.sh`
- 数据库：`data/growth.db`（已建表）
- 供应商仓库：`vendors/Spider_XHS`、`vendors/XiaohongshuSkills`

## 我下一步要做什么（最短路径）
1. 确认隔离实例登录（`--port 9333`）
2. 跑真实采集并确认 `rows > 0`
3. 运行分析与候选生成
4. 用预览发布进行人工审核（已验证可到 `READY_TO_PUBLISH`）
5. 通过后再正式发布
6. 建立 7 天复盘报告

## 快速命令
```bash
cd "/Users/billlin/Documents/project/xhs-growth-loop"
.venv/bin/python vendors/XiaohongshuSkills/scripts/cdp_publish.py --account default --port 9333 check-login
bash scripts/01_collect.sh
.venv/bin/python scripts/02_analyze.py
.venv/bin/python scripts/03_generate_candidates.py
bash scripts/04_publish_preview.sh
```

## 前端入口（选题 + 多账号 + 预览触发）
```bash
cd "/Users/billlin/Documents/project/xhs-growth-loop/frontend"
npm run dev:dashboard -- --host 127.0.0.1
npm run bridge
```
打开：`http://127.0.0.1:5174/`

## 如果是新聊天窗口
直接让助手先阅读：
- `docs/START_HERE.md`
- `docs/CURRENT_STATUS.md`
- `docs/NEXT_STEPS.md`
