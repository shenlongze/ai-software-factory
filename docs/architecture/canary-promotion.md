# Canary Promotion (S38)

> 日期: 2026-08-29 | 冻结于 S38

## 1. Canary 流程 (冻结)
```
PromotionCandidate (EVALUATED + GOVERNED)
→ Canary 创建 (scope/max_runs/max_cost/max_duration)
→ Canary 执行 (真实 runs, 产生 Evidence)
→ Canary vs Baseline 比较
→ PASS → PROMOTED (PromotionSnapshot 生成)
→ FAIL (Regression) → ROLLBACK (复用 S21) 或 REJECT
```

## 2. Canary 限制 (冻结)
```
scope: 受限范围 (单 node / 单 workforce / 低流量)
max_runs: 有界 (防无限实验)
max_cost: 有界
max_duration: 有界
超限 → STOP
```

## 3. Canary Verification (冻结)
```
真实 Production Evidence (非 mock)
Canary success/verification/recovery vs Baseline
Regression 检测: delta < 0 → FAIL
```

## 4. Rollback 复用 (冻结)
```
Canary FAIL → 调 S21 rollback_service (不建第二套 Rollback)
Promotion 与 Rollback: Lineage + Audit + Snapshot
```
