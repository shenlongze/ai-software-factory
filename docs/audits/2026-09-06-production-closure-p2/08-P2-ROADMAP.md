# 08 — P2 ROADMAP (建议 — 审计产出, 不实施)

> 排序原则: Closure Value + Truth Integrity + Traceability + Real E2E + Learning
> Consumption (任务书 §15) — 非功能数量。

## P2-A Release Truth (MUST)
- Release 实体接入 P0 canonical: release.release_id 从 rel-* 升级或映射 RELEASE-*,
  input = TASK-*/run-*/EXS + artifact_ids (P0 art-*) + verification (ver-* PASS) +
  evidence (EVD-*)
- gate = 真实 ver-* PASS 检查; Release→TASK-* FK (反查 P1 Product Truth)
- 真实 E2E: P0 全链 → release → 反查
- 替代方案: rel-* 保留 M3 legacy, 新 RELEASE-* canonical (同 D1/D2 模式)

## P2-B Production Closure E2E (MUST)
- 把 P0-F4 真实 E2E 延长到 Release 消费 (art/ver/EVD → release gate → release fact)

## P2-C Experience Bridge 规范化 (SHOULD)
- exp 提取加 production_run_id/verification_id FK (现在 source=execution_records
  字符串, 无结构化 run FK) — 使 exp→EXS→run→task 可反查

## P2-D Learning Consumption 落地 (SHOULD)
- 生产后 (finalize_node_run 成功/失败) 自动触发 refresh_agent_profiles
  (非仅 M3 orchestrator 手动)
- agent_profiles.json 真实落盘 → CapabilityRouter 真实消费
- 学习护栏 (LearningGuards) 保持

## P2-E Closed-loop 验证 (LATER)
- learning_trace 对下一次 run 的影响可度量 (before/after 决策对比)

## 依赖
P2-A ← P0 (done); P2-C ← P2-A (release FK); P2-D ← P2-C (exp FK);
P2-B 每阶段都要 (E2E 门)。
