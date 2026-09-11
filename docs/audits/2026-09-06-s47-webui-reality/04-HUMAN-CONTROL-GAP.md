# 04 — HUMAN CONTROL GAP (READ-ONLY)

## Observe
- Project 阶段: 🟢 overview (status/lifecycle) + workflow 8 阶段
- 当前 Task/Run/Agent/状态: 🟡 runtime 页 + run-status (tasks 聚合);
  真时有限; workflow 详情可能 mock
- 最近发生/产出: 🟡 AfTimeline (org 事件) / workspace 产物

## Understand
- 为何执行/做了什么: 🟡 workflow viewer 阶段 + conversation 消息
- 验证结果: 🟡 AfQualityGate (org 域 checks + 禁 fake)
- Artifact/Evidence/Failure/Repair: 🟡 workspace + timeline; repair 事件
  (DevTestLoop) 后端有, 前端弱

## Intervene
- Stop/Retry/Repair: 🟡 run cancel 后端有 (run_liveness), 前端入口弱
- Request Change / Approve / Reject: 🔴 (S45 ACC-* 无 UI; org approval
  Approve 按钮仅旧域)

## Accept
- Preview: 🟢 (iframe 运行 URL)
- Review/Approve/Request Change (canonical): 🔴 BACKEND_ONLY

## Release
- Release candidate/gate/approval/release/delivery UI: 🔴 BACKEND_ONLY
  (release_truth 后端全, 前端零)

## 一致性 (Project/Conversation/Session/Run/Task)
- projectId: localStorage (af.chat.project) + URL ?project 恢复 — UI 上下文
  持久化 (非业务 truth) — 可接受
- session→run: api.sessionRuns 关联真
- 未发现 frontend 生成业务 ID / 假状态 / 第二 truth — 架构健康
- localStorage 仅 UI preference/scope (符合审计铁律)

## 实时性
- Conversation SSE: 有 (client stream)
- Runtime 事件 SSE: runtimeClient.subscribeEvents (断线重连; 无事件库→
  后端 mock error 事件→诚实演示模式)
- Task/Project 状态: polling (run-status) / 页面加载时拉取 — 非全实时
- **一个任务运行中实时看 Agent/Task/Verification**: 🟡 runtime 页 SSE +
  轮询有基础, 但缺"当前在跑什么"的可靠实时板

## 第二业务逻辑
- localStorage 仅 UI 偏好 ✓ | 无 frontend 生成 ID ✓ | mock 诚实标注 ✓
- → WebUI = Projection 确认 (重验证通过, 非继承旧结论)
