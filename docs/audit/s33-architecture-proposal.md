# S33 Architecture Proposal — Performance-aware Workforce Selection

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Ranking Contract (冻结, deterministic)
```
score = w1*success_rate + w2*verification_rate + w3*recovery_rate + w4*evaluation_norm
confidence = sample_count / (sample_count + K)  (evidence-aware, 小样本降权)
ranking_score = score * confidence
相同输入 → 相同排序 (测试断言)
```

## 2. Selection Pipeline (冻结)
```
Capability → Eligibility → Permission → Policy → Performance Ranking → Selected
Governance 永远优先于 Performance (高性能不能绕过 permission/policy)
```

## 3. Cold-start (冻结)
```
sample_count == 0 → confidence = 0 → 确定性 fallback:
  优先选择有 evidence 的 plugin; 全部无 evidence → 按注册顺序 (可被选择, 不锁死)
```

## 4. Performance Snapshot (冻结, append-only)
```
selection 时保存当时 performance (success/verification/sample_count/score)
历史 Selection 可从 snapshot 解释 (不受后续变化影响)
```

## 5. 真实替换实验 (冻结)
```
Plugin A (好 evidence) vs Plugin B (差 evidence) → A 被选
改变 B evidence (真实 runs 改善) → B 被选
Selection 变化来自 Evidence, 非 hard-coded
```

## 6. CLI/API
```
factory workforce select <cap> | factory workforce ranking <cap> |
factory plugin performance <plugin> | factory plugin performance-history <plugin>
POST /api/workforces/select-ranked | GET /api/plugins/{id}/performance | GET /api/plugins/{id}/performance-history
```
