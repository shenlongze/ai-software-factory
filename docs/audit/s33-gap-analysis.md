# S33 Gap Analysis — Performance-aware Workforce Selection

> 日期: 2026-08-29 | HEAD: 51db8c36 (v1.1.339)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| Performance Profile (S30 agent_performance) | 从真实 ProductionRun/Verification/Evaluation 投影 (success/verification/evaluation/sample_count) | REAL |
| Ranking Contract | 无 | MISSING |
| Performance-aware Selection | select_agent_deterministic 仅 capability match | MISSING (无 ranking) |
| Composition Resolution (S32) | resolve_agent_composition 无 ranking | MISSING |
| Cold-start 规则 | 无 | MISSING |
| Performance Snapshot (历史可追溯) | 无 | MISSING |
| Governance 优先于 Performance | S17/S31 permission 检查存在 | 复用 (需接线) |
| LLM-based ranking | 无 (符合) | N/A |

## 设计
```
Task → Capability Requirement → Plugin Registry → Eligibility → Permission → Policy
→ Performance Ranking (deterministic, evidence-aware) → Selected Plugin
→ Workforce Composition → Execution → Verification → Evidence → Performance Update

Ranking Contract (deterministic):
- Evidence-aware score: success_rate/verification_rate/recovery_rate/evaluation_score 加权
- Sample-size aware: confidence = f(sample_count) (小样本降权, 不迷信 100%)
- Cold-start: sample_count=0 → 确定性 fallback (可被选择, 不永久锁死)
- Governance 优先级: Capability → Eligibility → Permission → Policy → Performance
Performance Snapshot: selection 时保存当时 performance (append-only, 历史可解释)
```

## 复用
S30 agent_performance + S32 resolve_agent_composition + S31 Plugin Kernel + S17 governance

## 禁止
- mock performance / fake evidence / hard-coded ranking / LLM ranking / declared score
- Performance 绕过 governance;小样本 100% 迷信;新 plugin 永久锁死
