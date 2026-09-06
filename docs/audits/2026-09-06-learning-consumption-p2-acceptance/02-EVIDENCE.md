# 02 — EVIDENCE (P2-D FINAL ACCEPTANCE, 2026-09-06)

## Canonical domains (learning_truth.py)
derive_observation (L98) / propose_candidate (L165) / propose_promotion (L242) /
approve_promotion (L288) / apply_promotion (L368) / rollback_profile (L446) /
record_routing_decision (L500)

## Governance (governance_service.py diff)
+ learning_promotion policy (medium, approval_required=True, human) + subject
白名单 — 纯增量, 不弱化既有 (25 passed)

## Router 消费 (actions.py)
画像源 = router_profiles() (governed) → 失败回退 legacy → CapabilityRouter
persona_score 映射 (success_rate) — 零算法修改

## 唯一 writer
learning store 外部零写 (grep 仅 learning_truth); CLI 只读 list
