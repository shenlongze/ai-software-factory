# 06 — PROMOTION CONTRACT (P2-D CONTRACT, 2026-09-06)

## D3: Promotion (冻结 — 最重要治理边界)

- ID: PROM-{hex8}; SSOT: <root>/learning/promotions.json
- Writer: PromotionService (唯一)

## 规则
- Candidate → Promotion → Profile 变更 (唯一生效路径)
- Promotion 记录: candidate_id + observation_ids[] + experience_ids[] +
  evidence_count + approver (human/auto) + timestamp + reason +
  previous_value + new_value + status (APPLIED/REJECTED/ROLLED_BACK)
- **默认 Human-in-the-loop**: 影响路由的 profile 变更需 governance approval
  (auto 仅低风险/高证据场景, 契约明列阈值)
- 可回滚 (ROLLED_BACK); 全审计
- 依据: evidence_count ≥ MIN_SAMPLES(3) + quality ≥ 0.5 (guards 既有语义)

## Reality: 无现有 promotion 域 (PatternLearner=统计非治理) — 全新建
