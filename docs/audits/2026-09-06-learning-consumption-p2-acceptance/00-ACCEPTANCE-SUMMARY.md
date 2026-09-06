# 00 — ACCEPTANCE SUMMARY (P2-D FINAL ACCEPTANCE, 2026-09-06, READ-ONLY)

> 基线: 6853439c (P2-C committed; P2-D 未提交工作区)
> 方法: 代码取证 + fresh 测试/E2E + 历轮 stash 对照

## 判定: ACCEPT

- 5 canonical learning 域 (OBS/CAND/PROM/PROFILE/RD) 独立事实, 唯一 writer
- Governance human-in-loop (learning_promotion subject/policy; 低证据 BLOCK)
- Profile versioned immutable + rollback; Router 真实消费 (governed shape)
- **决策变化实证** (E2E-1: baseline agent-A → learning agent-B)
- Next Run → RELEASE → 新 exp 闭环 (真实 ID)
- Idempotency / Failure / Recovery / Rollback 全 PASS
- P0/P1/P2-A/P2-C zero-diff; legacy 隔离; 无 P2-D scope 泄漏
- 20/20 tests; E2E 3/3 fresh; P2-D attributable = 0

## 遵守
No code/data changes | No commit | No push | P2-D 工作区保留待 Controlled Commit
