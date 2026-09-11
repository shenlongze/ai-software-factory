# 10 — Remediation Roadmap (方向, 非新架构)
P1-1 前链 Node 化 (已设计 02-IMPLEMENTATION-DESIGN, 待实施):
      requirement-analysis 试点 → E1/E2 runtime → 编排 + PRD/PLAN 模板
P1-2 工具注册层: tool schema/desc/handler 三分离增量上移注册表
      (capability_router 或 tool_registry 承接发现/授权), agent_loop 收敛
P1-3 规则代码化: description/guide 中业务策略移 gate/policy,
      prompt 只留 LLM 引导
P1-4 approve 人机边界: 会话"代批 human"语义复审 (审批需真实 UI 动作证据)
P2-1 会话 store 收敛 (conv_state/session_state/topic_ledger 合并面)
P2-2 slug 双口径统一 (单 _slugify 函数)
P2-3 session 模块碎片整理 (非功能优先级)
P2-4 legacy fallback 审计退出条件
顺序: P1-1 (架构主线, 已设计) → P1-2/3 (随 Node 化顺手) → P2 backlog
