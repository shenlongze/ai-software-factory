# 16 — LEGACY ISOLATION (P2-D CONTRACT, 2026-09-06)

- intelligence/experiences.json (85, S9) = LEGACY — 不重定义 canonical;
  新 OBS/CAND 不读它
- learning_engine_v2 (intelligence/obs/cand/hyp) = legacy 基础组件;
  P2-D 新建 canonical OBS/CAND store 后隔离 (不迁移 0 数据)
- learning_trace (852) = M3 审计 — 保留不碰
- 84 条 legacy exp (无 anchor) = 不作新链输入 (缺 FK)
- PatternLearner/refresh = 计算逻辑保留, writer authority 收敛
