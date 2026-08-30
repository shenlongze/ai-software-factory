# Learning Lifecycle & Governance (S37)

> 日期: 2026-08-29 | 冻结于 S37

## 1. Lifecycle 状态机 (冻结)
```
OBSERVED → HYPOTHESIS → CANDIDATE → EVALUATING → VALIDATED
                                           → REJECTED
                                           → SUPERSEDED
合法迁移表:
  OBSERVED → (HYPOTHESIS, REJECTED)
  HYPOTHESIS → (CANDIDATE, REJECTED)
  CANDIDATE → (EVALUATING, REJECTED, SUPERSEDED)
  EVALUATING → (VALIDATED, REJECTED, SUPERSEDED)
  VALIDATED → (SUPERSEDED)
  REJECTED → ()
非法迁移拒绝; history append-only
```

## 2. Governance Boundary (冻结, 最重要)
```
Learning [STOP at Candidate/Evaluation]
禁止自动: modify Production/Skill/Plugin/Workflow/Policy/AgentProfile/Workforce/Core
任何 Promotion → S38 显式
```

## 3. LLM 边界 (冻结)
```
LLM proposes → Core validates (Evidence validation → Governance)
绝不: LLM → direct Production change
```

## 4. Plugin Architecture (冻结)
```
Learning Plugin (type=learning): discovery/inference/pattern/hypothesis
Core: Permission/Policy/Governance/Lifecycle/Lineage/Audit
替换不修改 Core
```

## 5. 安全测试 (冻结)
```
test_learning_does_not_modify_production
test_learning_requires_evidence
test_unknown_is_not_learning_fact
test_conflict_is_preserved
test_learning_plugin_replace_without_core_change
```
