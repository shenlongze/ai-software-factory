# 07 — PROFILE / CAPABILITY CONTRACT (P2-D CONTRACT, 2026-09-06)

## D4: Profile = Learning 输出 (非 SSOT)

- Profile SSOT: <root>/memory/agent_profiles.json (既有位置 — refresh 落盘点)
  → 但 P2-D 使写入仅经 PromotionService (禁 refresh 直写 = 禁无治理写入)
- Profile 字段: agent_id + capability + success_rate + quality_score +
  sample_count + confidence + **profile_version** + updated_at
- Capability/Agent/Skill/Tool 关系: Profile 描述 Agent 对 task_class 的能力;
  不产代码修改 (Learning 不改 prompt/code/tool/router — 安全边界)

## Reality: 现有 refresh_agent_profiles (PatternLearner.learn_agent → 直写)
= 无治理写入路径 — P2-D 收敛: refresh 逻辑保留为聚合计算, 写入改经
PromotionService (治理门)
