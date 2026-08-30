# Promotion Contract & Governance (S38)

> 日期: 2026-08-29 | 冻结于 S38

## 1. Promotion Lifecycle (冻结)
```
CANDIDATE → EVALUATING → EVALUATED → GOVERNED → CANARY → PROMOTED
失败路径: → REJECTED | → INCONCLUSIVE | → ROLLED_BACK
非法迁移拒绝; append-only history
```

## 2. PromotionSnapshot (冻结, immutable)
```
snapshot_id / candidate / baseline / evaluation / experiment / comparison /
policy / governance decision / canary result / actor / timestamp / versions
回答: 为什么系统采用这个能力?
```

## 3. Governance Modes (冻结)
```
AUTO_APPROVE (LOW risk, evidence 充分)
REVIEW_REQUIRED (MEDIUM)
HUMAN_APPROVAL_REQUIRED (HIGH/CRITICAL — 不可绕过 Human Gate)
REJECT
Risk 分类: LOW/MEDIUM/HIGH/CRITICAL (blast_radius/permission_scope/production_impact/capability_change)
```

## 4. Promotion Policy Plugin (冻结)
```
Core 负责 Governance enforcement (Permission/Policy/Lifecycle/Lineage/Audit)
Plugin 负责 Evaluation/Experiment/Comparison strategy (替换不修改 Core)
```

## 5. Canary (冻结)
```
CANDIDATE → EVALUATED → GOVERNED → CANARY → PROMOTED
Canary 限制: scope/traffic(runs)/cost/duration
Canary Verification: 真实 Evidence → Canary vs Baseline
Regression → REJECT 或 ROLLBACK (复用 S21 rollback_service, 不建第二套)
```

## 6. 安全边界 (冻结)
```
Learning 不能直接修改 Production/Agent/Skill/Plugin/Workflow/Policy
一切改变经 Promotion Contract
Evaluation 不能绕过 Governance
High-risk 不能绕过 Human Approval
Historical Evidence immutable
```
