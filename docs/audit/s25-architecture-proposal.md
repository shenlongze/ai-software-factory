# S25 Architecture Proposal — Adaptive Workforce & Optimization Validation

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. WorkforceVariant Contract (冻结)
```
variant_id / experiment_id / variant_type(control|treatment) /
change_definition / base_workforce / effective_configuration / created_at / status
effective_configuration 必须可执行:
  control:   {roles: [developer]}
  treatment: {roles: [developer, reviewer]}  (reviewer = 额外验证节点)
```

## 2. Variant→Production 注入 (冻结)
```
variant.effective_configuration → build_variant_executor_factory(root, variant)
  → execute_production_run(run_id, executor_factory=variant_factory)
  → 真实执行路径差异 (control: 1 节点; treatment: 2 节点)
```

## 3. Assignment Contract (冻结)
```
assignment_id / experiment_id / variant_id / production_run_id / created_at
ProductionRun 记录 experiment_id/variant_id/assignment_id (可反查)
```

## 4. Governance (冻结)
```
Optimization Proposal → Governance approval → Variant Activation → Experiment
未批准 → run blocked (测试证明)
```

## 5. Lineage (冻结, 复用 S24)
```
proposal → experiment → variants → assignment → production_run → evaluation → measurement → outcome
```

## 6. 边界
- Variant 只改生产输入 (executor_factory/workflow 配置), 不改 Production Truth
- 不建第二套 engine/governance/evaluation/lineage

## 7. CLI/API
```
factory optimization proposal | variant <exp> <type> | assign <variant> <run> | experiment ...
POST /api/optimization/variants | POST /api/optimization/assignments | POST /api/optimization/experiments/{id}/activate
```
