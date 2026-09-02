# ARTIFACT GAPS — STEP 5
- G-ART-01 HIGH: 会话链 Task → Artifact 无关联 (backlog 无 artifact_ref)
  - exec 域: ART-* → task_id (T00x) + agent_id + event_refs (完整)
  - 会话链: finish_task_exec 只写 exec_ref/exec_result, 无 artifact 引用
  - 影响: 用户/审计无法从会话链任务追到产物/验证
- 分类: TRACEABILITY_GAP
