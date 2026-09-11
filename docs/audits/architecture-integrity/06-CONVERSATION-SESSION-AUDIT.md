# 06 — Conversation/Session Audit
- Conversation 层 (governor/resolver/guide/conv_state/exec_state/topic_ledger)
  在【模拟】Node 行为: 判 continue/恢复 active work/next_action/执行指令 —
  会话自持工作状态, 与 node_runtime 分层冲突 (偏离2 P1)
- Session store 多: console_sessions(消息) + conv_state(语义) +
  session_state + session_plans + session_exec + session_topics + chat.json
  同会话域 6+ store, 部分边界清楚(消息 vs 执行态), 部分重叠(P2 收敛面)
- 正确定位: Conversation = human interface (意图→NodeRun); 执行事实归 NodeRun
