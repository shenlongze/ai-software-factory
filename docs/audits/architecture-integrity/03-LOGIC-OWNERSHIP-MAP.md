# 03 — Logic Ownership Map
Action | Canonical Owner | Other Impl | Risk
继续/resume | (无 — 会话 resolver) | node_runtime 无前链 | P1 偏离2
create_task | agent_loop handler+gate | service | 已 gate
approve | governance_service | agent_loop 代批(execute_plan 内 decided_by=human) | P1 授权语义在会话
verify | node_runtime finalize + ver-* | workflow runner | 同源 OK
save requirement | agent_loop save_product_record | product_truth service | 工具层封装 OK(描述含业务 P1)
结论: approve 代批(会话层 decided_by=human 模拟用户) = 治理语义需人机边界复审
