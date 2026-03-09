# FRONTEND DASHBOARD

更新时间：2026-03-09

## 目标
在不影响隔离浏览器（`port=9333`）和主采集发布链路的前提下，提供：
1. 意图输入与选题解析（OpenClaw / LLM / 规则兜底）
2. 候选贴文可视化与词云反馈
   - 策略实验看板（run、状态分布、arm score、bandit pulls/wins）
   - Runtime 执行看板（重试次数、失败步骤、决策动作、步骤轨迹）
3. 一键写入候选池、触发预览发布
4. 多账号创建、选择、登录触发

## 启动
```bash
cd "/Users/billlin/Documents/project/xhs-growth-loop/frontend"
npm run dev:dashboard -- --host 127.0.0.1
npm run bridge
```
浏览器打开：`http://127.0.0.1:5174/`

## 核心流程
1. 在“意图输入”区域输入连续文本（例如：`跨境电商，小白入门跨境电商，实习生找工作`）。
2. 选择解析链路：
   - 优先 OpenClaw（可配置 URL）
   - 或填入 ds/豆包/千问/gpt API Key
   - 若前两者不可用，自动降级本地规则解析
3. 选择建议选题，生成草稿（标题自动限制 20 字）。
4. 可点击“一键市场采集”，按当前解析出的关键词触发 `01_collect_market.sh`。
4. 在“候选贴文（点击选择）”中点选要采用的稿件。
5. 点击“写入候选池”保存到 `data/candidates/`。
6. 点击“进入预览发布”触发 `scripts/04_publish_preview.sh`。

## 多账号操作
账号模块在界面**右上角**：
1. 选择账号（显示格式：`别名(账号名)`）。
2. 点击“登录该账号”触发该账号登录流程（隔离浏览器扫码）。
3. 新建账号：
   - 填 `账号名`（必填，如 `work`）
   - 填 `别名`（可选）
   - 点击“新增账号”
4. 点击“刷新”更新账号列表。

说明：预览发布会使用右上角当前选中的账号。

## 桥接服务接口（本机）
- `GET /health`：健康检查
- `GET /api/accounts`：账号列表
- `POST /api/add-account`：新增账号
- `POST /api/login-account`：触发账号登录
- `POST /api/save-drafts`：写入候选池
- `POST /api/preview-draft`：触发预览发布
- `POST /api/collect-market`：按关键词触发市场采集

## 常见问题
1. 点击“新增账号”无反应：
   - 检查 bridge 是否运行：`npm run bridge`
   - 检查账号名是否为空（为空会提示）
   - 强刷页面：`Cmd+Shift+R`
2. 下拉只有 `default`：
   - 先新增账号后点“刷新”
   - 或检查 `vendors/XiaohongshuSkills/config/accounts.json`
3. 预览触发失败：
   - 先确认右上角账号已登录
   - 查看页面日志区与 `logs/` 下最近日志
4. 策略看板里 Runtime 一直为空：
   - 先执行 `bash scripts/run_openclaw_generate.sh` 或 `bash scripts/run_daily_loop.sh`
   - 检查 `data/runtime/bridge_latest.json` 是否存在
