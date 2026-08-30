# AI Factory OS — Target Architecture

> 日期: 2026-08-29 | 设计文档 (基于 S0.5-S33 真实审计)

## 1. OS Planes (最终)
```
┌─────────────────────────────────────────────────────┐
│                 Governance Plane                    │
│  Identity/Lifecycle/Permission/Policy/Approval/Audit │
└──────────────┬──────────────────┬───────────────────┘
               ↓                  ↓
┌──────────────┴──────┐  ┌────────┴───────────────────┐
│  Production Plane   │  │  Workforce Plane            │
│  Run/Node/Artifact  │  │  Org/Dept/Workforce/Agent   │
│  Verify/Recovery    │  │  Composition/Selection      │
│  Release/Rollback   │  │  Performance                │
└──────────────┬──────┘  └────────┬───────────────────┘
               ↓                  ↓
┌──────────────┴──────────────────┴───────────────────┐
│                Evidence Plane                       │
│  Verification/Evaluation/Classification/Reliability │
│  RCA/Performance Projection/Snapshot                │
└──────────────┬──────────────────────────────────────┘
               ↓
┌──────────────┴──────────────────────────────────────┐
│              Intelligence Plane (S35+)              │
│  Memory/Context Control Plane/Learning/Promotion    │
└─────────────────────────────────────────────────────┘
```

## 2. Plane 职责定义
| Plane | Owns | Does NOT Own |
|-------|------|-------------|
| Production | Run/Node/Artifact 生命周期 + 执行 + 验证 + 恢复 | 能力实现 (Plugin) |
| Workforce | 组织层级 + AgentProfile + Composition + Selection | 具体执行 |
| Plugin | Registry/Resolver/Lifecycle/Governance | 业务能力 |
| Evidence | 验证/评估/分类/可靠性/性能投影 | 决策 |
| Intelligence | Memory/Context/Learning/Promotion (S35+) | Production Truth |
| Governance | Permission/Policy/Approval/Audit | 执行 |

## 3. Core vs Plugin 边界 (冻结)
### Core (OS Kernel)
```
Identity / Lifecycle / Permission / Policy / Governance / Resolution /
Execution Contract / Evidence Contract / Lineage / Audit / Transaction
```
### Plugin (Capability)
```
Agent / Skill / Tool / Model / Provider / Runtime / Executor / Memory /
Retriever / Reranker / Compressor / Evaluator / Experimenter / Observer / Repairer
```
**原则: Core governs capability; Core does not implement capability.**

## 4. Independent Node 保护
```
Node → Context Request → Context Resolution → Execute → Verify → Evidence → Experience
禁止: get_all_memory / bypass_governance / bypass_permission / directly_modify_memory
```

## 5. Evolution Loop (最终闭环)
```
Production → Evidence → Experience → Memory → Learning → Candidate
→ Evaluation → Experiment → Governance → Promotion → Better Workforce → Better Production
```

## 6. 不变量 (15 条, 见 review 文档 §5)
13/15 已满足;2 条 (Context 受治理 + 无无限 Context) 由 S35 Context Control Plane 建立。
