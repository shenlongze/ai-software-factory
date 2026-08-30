# Context Control Plane — Contract (S35)

> 日期: 2026-08-29 | 冻结于 S35

## 1. ContextRequest
```
context_request_id / node_id / node_run_id / agent_id / workforce_id / project_id /
scope(list: node|agent|workforce|project|organization|global) /
purpose / required_capabilities /
max_input_tokens / max_memory_tokens / max_artifact_tokens /
max_history_tokens / max_tool_tokens / max_output_tokens / max_total_cost / created_at
```

## 2. ContextBudget (冻结)
```
max_input_tokens=8192 / max_memory_tokens=2048 / max_artifact_tokens=2048 /
max_history_tokens=1024 / max_tool_tokens=1024 / max_output_tokens=2048 / max_total_cost=0.01
超预算 → ContextDecision(REJECT/RANK→TRUNCATE→COMPRESS)
```

## 3. ContextResolution Pipeline (deterministic, 非 LLM)
```
Scope Validation → Permission → Policy → Candidate Retrieval
→ Relevance(deterministic) → Evidence Strength → Freshness → Scope Match → Cost
→ Ranking → Budget → Compression → ContextSnapshot
```

## 4. ContextSnapshot (冻结, 不可变)
```
snapshot_id / request_id / node_id / selected_items[] / rejected_items[] /
compressed_items[] / requested_tokens / selected_tokens / compressed_tokens /
rejected_tokens / estimated_cost / created_at / evidence_refs
历史 execution 可从 snapshot 解释 (Memory 后续变化不影响)
```

## 5. ContextDecision (冻结)
```
decision_id / status(OK|REJECTED|BUDGET_EXCEEDED|COMPRESSED|TRUNCATED) /
requested/selected/rejected/compressed tokens / estimated_cost / reason
```

## 6. JIT Context
只检索 Node 需要的 (scope + purpose 驱动); 禁止 load-all
