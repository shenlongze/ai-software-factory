# S35 Gap Analysis — Context & Memory Runtime Foundation

> 日期: 2026-08-29 | HEAD: 4235702f (v1.1.341)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| ContextRequest/ContextBudget/ContextSnapshot | 无生产级 (agent_kernel 无独立 context 层) | MISSING |
| Context Resolver (deterministic pipeline) | 无 | MISSING |
| Context Cost accounting | 无 (estimated 可接受) | MISSING |
| Memory Plugin Contract | 无 (S34 设计文档有) | MISSING |
| LocalMemoryPlugin | 无 | MISSING |
| Memory provenance/versioning | 无 | MISSING |
| Experience (S14/S15) | production_experience.py (meta sidecar + lineage) | REAL (Memory 来源) |
| Evidence (S23) | production_intelligence.py (refs 校验) | REAL |
| Plugin Kernel (S31) | plugin_kernel.py | REAL (Memory Plugin 接入点) |
| Governance (S17) | governance_service.py | REAL |
| JIT Context | 无 | MISSING |
| Context/Memory 事件 | 无 | MISSING |

## 设计
```
ContextRequest (node_id/scope/purpose/budget 字段)
→ Scope Validation → Permission → Policy → Candidate Retrieval
→ Relevance/Evidence/Freshness/ScopeMatch/Cost → Ranking → Budget
→ Compression → ContextSnapshot (可追溯, 历史不可变)
MemoryPlugin Contract (Core 管 Governance, Plugin 管 Storage)
LocalMemoryPlugin: deterministic retrieval (scope/provenance/version)
MemoryCandidate → Policy → Validation → Memory (不自动长期化)
JIT: 只取 Node 需要的 (禁 load-all)
```

## 复用
S31 Plugin Kernel (Memory Plugin 注册/解析) + S17 governance + S23 evidence refs + S14/S15 experience

## 禁止
- LLM-based ranking 作为必需依赖 / 复杂 Vector/Graph DB / 自动对话记忆 / 无限 Context
- Node 直接读/改 Memory / 绕过 permission/policy / vendor 进 Core
