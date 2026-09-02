# AGENT CONTROL GAPS — STEP 5
- G-AGENT-01 HIGH: 
  - 局部执行器路由 (gateway._pick_executor→router.route) 真实 (classify+score, execution_records 100)
  - OS 级 Agent Control (7 角色 dev/pm/arch/tester 动态选择 + 会话链绑定) 部分 UNKNOWN:
    execution_records agent=pm-agent/architect-agent/qa-agent 有记录, 触发入口 (会话/CLI?) 未反查
  - 会话链 chain_next→gateway_execute 无显式 agent_id (走 route 默认)
- 分类: CONTROL_PLANE_GAP
- 证据: AGENT_CONTROL_FORENSICS.md
