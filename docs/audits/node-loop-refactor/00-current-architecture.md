# 00 Current Architecture (2026-09-07 取证)
- node_runtime.py: NodeRun 契约 (PENDING→RUNNING→VERIFYING→COMPLETED/FAILED;
  execute_node_run 有 REPAIRING 尝试循环; finalize 终态幂等; verify 物化
  ver-*; artifact absorb art-*)。实际 node: task-execution (执行段)。
- product_truth: IDEA/DISC/REQ/PRD/PLAN 记录 (domain fact) — 无 NodeRun。
- agent_loop 3840 行: tool_schemas 35 + dispatch 35 + governor/resolver/
  guide/conv_state/exec 指令 — Conversation 层模拟前链 Node 行为。
- 会话 store: conv_state/session_state/session_plans/session_topics/
  exec_state/chat.json — 工作状态散落。
- 前端: projection (健康)。
