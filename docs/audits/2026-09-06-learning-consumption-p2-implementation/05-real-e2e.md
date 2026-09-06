# 05 — REAL E2E (P2-D IMPL, 2026-09-06)

3/3 PASS (fresh, 真实 service, 隔离 tmp):

E2E-1 闭环: baseline 路由 agent-A (中性) → 3 真实 anchored exp (agent-B,
真实 P0 run+EXS+ver+P2-C bridge) → OBS×3 → CAND → PROM (admin approval) →
PROFILE-agent-B-v1 (rate 1.0) → **real select_agent 决策变化 agent-B** →
RD 记录 → next run → RELEASE → 新 exp (闭环); trace RD→profile→PROM→CAND;
store 实证 5 文件
E2E-2 幂等: obs/cand/prom/apply/RD 全 1→1
E2E-3 治理门: 低证据 approve BLOCK / legacy exp 拒绝 / human-in-loop
