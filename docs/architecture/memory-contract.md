# Memory Contract (S35)

> 日期: 2026-08-29 | 冻结于 S35

## 1. MemoryPlugin Contract (冻结)
```
MemoryPlugin 注册到 S31 Plugin Kernel (type=memory)
Core 负责: Identity/Scope/Permission/Policy/Governance/Lifecycle/Lineage/Budget
Plugin 负责: Storage/Index/Retrieval/Embedding/Ranking/Compression
Core 不得 import 具体实现 (Mem0/Letta/Chroma/FAISS — 全禁止)
```

## 2. MemoryEntry (冻结)
```
memory_id / scope(node|agent|workforce|project|organization|global) /
content / source_type(evidence|experience|manual) / source_id /
created_at / confidence / version / permissions[] / policy
provenance 必保留: source/source_type/source_id
```

## 3. MemoryCandidate (冻结)
```
candidate_id / content / scope / source_refs[] / policy / status(PENDING|PROMOTED|REJECTED)
流程: Production Evidence → Experience → Memory Candidate → Policy → Validation → Memory
不自动长期化 (S35 只做 Candidate → governed persistence)
```

## 4. Memory Scope (冻结)
Scope 是 Query Dimension, 非继承树。
ContextRequest 显式声明 requested scopes; 未经授权 scope → MEMORY_ACCESS_DENIED。

## 5. LocalMemoryPlugin (冻结, v1)
确定性检索 (scope 过滤 + provenance + version); 无 fake vector/semantic。
支持: put/get/query/list/disable + audit + lineage。
