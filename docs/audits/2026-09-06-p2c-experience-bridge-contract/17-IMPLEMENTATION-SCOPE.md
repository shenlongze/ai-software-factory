# 17 — IMPLEMENTATION SCOPE (P2-C CONTRACT, 2026-09-06)

## IN SCOPE (未来 P2-C Impl)
- Experience schema 扩展 (task_run_id/exs_id/release_id/source_id)
- ExperienceBridge (唯一 writer; (source, source_id) 幂等)
- Trigger 接线: finalize 调用侧 (agent_loop) + release execute 调用侧
- CLI trace (exp→production 反查, 可选)
- 测试 + 真实 E2E C1-C6
- legacy 标记 (84 条 source 标注 M3; 不迁移)

## OUT OF SCOPE (P2-D)
Observation / Candidate / Promotion / AgentProfile / Router consumption /
workforce adaptation / next-execution learning / closed-loop optimization
