# S39 Gap Analysis — Autonomous Recovery & Self-Healing

> 日期: 2026-08-29 | HEAD: c98fbe9a (v1.1.345)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| Health/Incident (S21) | health_service.py (HealthCheck/HealthIncident) | REUSE (Incident 来源) |
| Rollback (S21) | rollback_service.py | REUSE (Canary FAIL → rollback) |
| Recovery (S28) | recovery_service.py (bounded repair loop + classification + policy) | EXTEND (→ Self-Healing) |
| Learning (S37) | learning_engine_v2.py | REUSE (Recovery Evidence → Observation) |
| Promotion/Governance/Canary (S38) | promotion_service.py | REUSE (RepairCandidate → Evaluation→Governance→Canary→Promotion) |
| **统一 Incident Contract** (evidence-driven, 非 LLM) | S21 incidents 简单 | EXTEND (S39 Incident Contract) |
| **Diagnosis Contract** (FACT/HYPOTHESIS/UNKNOWN) | 无 | MISSING |
| **RepairCandidate** (Proposal, 非 Production Change) | S28 repair 直接执行 | MISSING (Contract 化) |
| **Repair Strategy Plugin** (Core 不含 repair logic) | S28 repair_fn 硬编码 | MISSING (Plugin 化) |
| Self-Healing Loop (Incident→Diagnosis→Candidate→Evaluate→Govern→Canary→Promote→Recover→Learn) | 无 | MISSING |
| 20 Architecture Invariants | S28 部分 | MISSING (显式保证) |

## 设计
```
Production Failure → Verification FAIL → Incident (evidence-driven, 非 LLM)
→ Diagnosis (FACT/HYPOTHESIS/UNKNOWN + evidence refs)
→ RepairCandidate (Proposal: repair_strategy_plugin_id/target/proposed_change/risk/cost)
→ S38 Evaluation (baseline FAIL vs candidate PASS via Replay)
→ Experiment (bounded)
→ S38 Governance (risk → human gate)
→ Canary (bounded scope/runs/cost)
→ Verification PASS → S38 Promotion
→ Recovery Evidence → S37 Learning Observation
失败: max_attempts/budget → UNRESOLVED (交 Human); Canary FAIL → S21 Rollback

Repair Strategy Plugin (type=repair): 首个 = coderepair (deterministic patch)
Core 职责: Identity/Lifecycle/Permission/Policy/Governance/Resolution/Execution/Evidence/Lineage/Audit
20 Invariants 显式 (Core 不实现 repair / repair 不能 self-elevate / 有界 / 无 Super Agent / 复用 S21+S38)
```

## 复用
S21 rollback + S28 recovery + S37 learning + S38 promotion + S31 plugin kernel

## 禁止
- 第二套 Learning/Evaluation/Experiment/Promotion/Governance/Rollback/Lineage/Evidence
- Debug Agent (Error→LLM→改码→commit)
- Central Super Agent / 无限循环 / 无界成本 / 全局 blast radius / Memory 当 SSOT
