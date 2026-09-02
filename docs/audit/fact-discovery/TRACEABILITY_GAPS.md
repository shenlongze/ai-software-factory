# TRACEABILITY GAPS — STEP 5
反向追踪断点:
| 反向边 | 状态 |
|--------|------|
| Artifact→Run | PROVEN (exec: ART-* ↔ EXS-*) |
| Artifact→Task | PARTIAL (exec T00x; 会话链 TASK-* 无) |
| Task→Plan | PROVEN (会话链 plan_id) |
| Plan→Requirement | ABSENT (无引用) |
| Requirement→User | PARTIAL (req.session_id→session, session→user 未验证) |
| Experience→Execution | PARTIAL (写入关联, 无读取消费) |
- G-TRACE-01 (并入 G-REQ-01/G-ART-01): 用户需求无法完整反查到产物
