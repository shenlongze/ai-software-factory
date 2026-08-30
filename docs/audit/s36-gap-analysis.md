# S36 Gap Analysis — Context Intelligence & Memory Optimization

> 日期: 2026-08-29 | HEAD: 5ec42def (v1.1.342)

## GAP Audit (S35 现状)
| 能力 | 现状 | 判定 |
|------|------|------|
| ContextRequest/Budget/Resolver/Snapshot | context_runtime.py | REAL (S35) |
| MemoryPlugin Contract + LocalMemoryPlugin | context_runtime.py | REAL (S35) |
| MemoryCandidate → Promote | context_runtime.py | REAL (S35) |
| ContextUtility (relevance/evidence/freshness/confidence/cost 统一) | 无 | MISSING |
| 确定性 Context Ranking (utility-aware) | S35 仅简单 relevance 评分 | PARTIAL |
| Budget 分配 (utility ranking → 选最优组合) | S35 顺序截断 | PARTIAL |
| Progressive Context (追加受预算, snapshot 记录) | 无 | MISSING |
| ContextFeedback (success/failure/unknown) | 无 | MISSING |
| Memory Lifecycle (CANDIDATE→ACTIVE→SUPERSEDED→RETIRED) | 无 (仅 version) | MISSING |
| Memory Freshness (valid_until/superseded) | 无 | MISSING |
| Memory Conflict Detection | 无 | MISSING |
| Context Strategy Plugin (替换测试) | 无 | MISSING |
| Context Efficiency Metrics | 无 | MISSING |

## 设计
```
ContextUtility Contract: score = w1*relevance + w2*evidence + w3*freshness + w4*confidence + w5*scope_match - w6*cost
Budget-aware Selection: utility desc 累计, 选最优组合 (非顺序截断)
Progressive: ContextRequest(追加) 受剩余 budget; 总 cost <= budget; snapshot 记录全部
ContextFeedback: context_id/node_run_id/execution_result/usefulness(unknown 诚实)
Memory Lifecycle: CANDIDATE→ACTIVE→SUPERSEDED→RETIRED (audit + lineage)
Memory Freshness: valid_until + superseded_by; 过期 → 不自动进 Context
Memory Conflict: 同 scope 同主题冲突 → CONFLICT (evidence/confidence/freshness 参与; 无法解决 → unresolved)
ContextStrategy Plugin: rank 策略 plugin 化 (Core 零修改替换)
```

## 复用
S35 context_runtime + S31 Plugin Kernel + S17 governance

## 禁止
- LLM ranking 必需 / Autonomous Learning / Self-Healing / 自动生产修改
- 删除历史 Memory / last-write-wins 冲突 / 伪指标
