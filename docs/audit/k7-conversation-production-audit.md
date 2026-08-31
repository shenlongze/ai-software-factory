# K7 Conversation Production Audit

> 日期: 2026-08-29

## Conversation 作为 OS Entry Point — PASS
- 理解自然语言 (Intent 6 类, deterministic)
- 多轮上下文 (state 驱动, 不跑题不遗忘)
- 区分聊天/讨论/决策/执行 (Intent 边界)
- 需要时创建 Work (EXECUTE intent → trigger_work)
- 查询实时状态 (ASK_STATUS → 真实投影)
- 呈现失败 (explain_failure evidence-backed)
- 请求 Approval (K3 approve gate)
- Replan/Resume (J8/J10)

## 用户不需要知道内部对象 — PASS
- 用户语言: "帮我做记账" → 系统处理全部底层
- 不暴露 Agent/Plugin/Runtime 术语 (K5 clarity)
