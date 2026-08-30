# Memory / Context Contract

> 日期: 2026-08-29 | S34 设计契约 (实现于 S35)

## 1. Memory Contract (冻结)
```
MemoryEntry:
  memory_id / scope(node|agent|workforce|project|organization|global) /
  content / source_refs[] (Evidence/Experience refs, 可追溯) /
  metadata(created_at, freshness) / permissions[] / policy

Memory Source of Truth:
  Production Evidence → Experience → Memory (非 Conversation → Memory)
  Memory 可重建 (Projection, 非第二事实源)

Memory Plugin 边界:
  Core: Scope/Permission/Policy/Governance/Lifecycle/Lineage/Budget
  Plugin: Storage/Extraction/Retrieval/Ranking/Compression/Indexing
  首个 Plugin: Local JSON (S36); 未来 Mem0/Letta/Vector/Graph

禁止:
  get_all_memory / Node 直接改 Memory / scope 继承树 / vendor 进 Core
```

## 2. Context Control Plane Contract (冻结)
```
ContextRequest:
  node_id / scope / permission / policy / token_budget / requested_types
Budget:
  max_input_tokens / max_memory_tokens / max_artifact_tokens /
  max_history_tokens / max_tool_tokens / max_output_tokens / estimated_cost
Resolution pipeline:
  Scope Filter → Permission → Policy → Retrieval → Ranking →
  Evidence/Confidence → signals → Token Budget → Compression → Context
Progressive/JIT:
  Node 判断 Context 是否足够 → NO → ContextRequest → Resolver → 增量补充 → Execute
Utility:
  Context Utility = Expected Decision Value / Token Cost
```

## 3. 安全边界 (冻结)
```
Node 可主动请求更多 Context, 但不得:
  bypass_governance / bypass_permission / directly_modify_memory / get_all_memory
所有 Memory 写: 经 Core (scope/permission/policy/audit)
所有 Context 读: 经 Context Control Plane (budget/ranking/compression)
```

## 4. 依赖
- S31 Plugin Kernel (Memory Plugin 注册/解析)
- S17 Governance (Memory 读写权限)
- S23 Evidence Model (source_refs 校验)
- S14/S15 Experience (Memory 的来源层)
