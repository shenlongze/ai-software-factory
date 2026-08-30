# S42 Gap Analysis — Intelligence Strategy Kernel

> 日期: 2026-08-29 | HEAD: fc2fab1f (v1.1.348)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| 共享 Evaluation/Experiment/Governance/Canary/Promotion (S38) | S39 Healing + S40 Optimization 已复用 | REUSE (唯一管道) |
| Learning (S37) | 独立 evaluation (Learning [STOP] 语义, 不 Promotion) | REUSE (Adapter) |
| Plugin Registry (S31) | type=strategy 已存在 | REUSE (Strategy 注册) |
| **统一 IntelligenceStrategy Contract** | 无 | MISSING |
| **Strategy Adapter** (Learning/Healing/Optimization 统一接口) | 无 | MISSING |
| **Strategy Version in Lineage** | 无 | MISSING |
| **Strategy Execution Evidence** | 无统一 | MISSING |
| Strategy Lifecycle | Plugin Lifecycle (S31) 可复用 | REUSE |

## 设计
```
IntelligenceStrategy (统一 Contract):
  strategy_id / strategy_type(LEARNING|HEALING|OPTIMIZATION) / version /
  capabilities / input_contract / output_contract / context_requirements /
  cost_budget / execution_policy / governance_policy

注册到 S31 Plugin Kernel (type=strategy) — 不建第二套 Registry
三个 Adapter (薄, 不复制逻辑):
  LearningStrategy → learning_engine_v2 (Observation→Candidate→Evaluation→[STOP])
  HealingStrategy → self_healing (Incident→Repair→S38→Recover)
  OptimizationStrategy → optimization_engine (Opportunity→Candidate→S38→Promote)

统一执行: StrategyRequest → Context/Evidence Resolution → Strategy Execute → Candidate → Evaluation → Decision
StrategyExecutionEvidence (strategy/version/input/candidate/evaluation/governance/result/cost) → Evidence/Lineage/Audit
```

## 复用
S31 Plugin Kernel (Registry/Lifecycle) + S38 管道 + S37/S39/S40 服务

## 禁止
- 新 Intelligence 能力 / 新 Loop / 第二套 Registry/Evaluation/Governance/Promotion
- Learning 逻辑进 Core / Strategy 绕过 Governance / Strategy 直接改 Production
