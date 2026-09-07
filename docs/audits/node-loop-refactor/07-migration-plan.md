# 07 Migration Plan
- 保留: node_runtime 全、product_truth 全、TASK execution 全、gate/scope
- 扩展: node_runtime (WAIT/decision/checkpoint/resume) — 兼容旧 run
- 新增: requirement-analysis node executor (会话工具: node_run_start/
  node_run_ask/node_run_resume 或 dispatch 集成)
- 旁路: governor/resolver 执行指导 (Phase3)
- 不迁移旧 conversation 状态; rollback: 新节点停用即回旧路径
- 每 Phase: targeted + 回归 335+1 CLI + 真实 E2E
