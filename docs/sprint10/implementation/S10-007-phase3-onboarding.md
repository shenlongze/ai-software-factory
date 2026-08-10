# S10-007 — 阶段三: 首次启动体验（Completion Report）

> 日期: 2026-08-10 | 状态: 完成 (待人工审核) | vitest 290 + tsc 零错 + pytest 6649

## 体验流程 (用户视角)

```
启动 AI Factory (./factory start)
  ↓
Welcome 首屏: "你想创建什么软件?"
  - 副标题: 输入一句话, AI 团队为你开发
  - 示例 chips: [一个记账 App] [一个待办清单 App] [一个博客网站] (点击填入)
  - Chat 输入框 + [开始生产]
  ↓
创建 Project → 进入项目工作台
  ↓
🚀 开始开发 按钮 (run-status none 时显示)
  ↓
POST /start → 真实 Agent 链启动
  ↓
运行状态条: 待启动 → 开发中 (X/6 阶段进度) → 完成 (calls/tokens/成本) / 失败 (原因+重试)
```

## 交付内容

```
1. Welcome 首屏 (WorkspaceView): 大标题/副标题/示例 chips/输入框 — 首次无项目进入
   (有项目 → 保留已有项目列表, 不挡老用户)
2. RunStatusBar (新增): 项目工作台顶部
   - none → 🚀 开始开发按钮 → POST startWorkflow
   - 3s 轮询 run-status → 状态条 (pending/running 阶段进度/completed totals/failed 原因+重试)
   - 503 (key 缺失) → "未配置 LLM API Key — 见 .env.example 或 ./factory config"
   - 终态自动停止轮询; 查询失败停止 + 重试 (避免错误风暴)
   - 纯真实 API, 无 mock fallback
3. types: RunStatusResponse/RunInfo/RunStageInfo (对齐后端 report/progress 契约)
```

## 测试

```
+6 (run-status-bar.test.tsx: 开始开发按钮 none/点击 POST start/503 key 引导/
  running 进度/completed totals/failed+重试) + 更新 1 旧断言 (Welcome 首屏)
共 vitest 290 (284+6) + tsc 零错 + pytest 6649 不动
```

## 截图

```
/tmp/s10-007-phase3/welcome.png (Welcome 首屏: 标题 + chips + 输入框)
```

## 下一步

```
阶段四: 真实用户验收 (最高优先级 — 模拟无程序经验用户: 输入一句需求 → 获得软件结果)
```
