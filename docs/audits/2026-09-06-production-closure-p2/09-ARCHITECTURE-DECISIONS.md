# 09 — ARCHITECTURE DECISIONS (P2 GAP AUDIT, 2026-09-06)

> 建议决策 (待人工批准, 不实施) — 最小 domain closure 优先

## AD-1 Release canonical 归属
现状: rel-* (M3, 0 数据) vs P0 chain (无 release)。
建议: **新 RELEASE-* canonical** (P0 风格, 独立 store), rel-* 降级 M3 legacy —
保持 P0 "新链第一天正确, 旧不迁移" 原则。输入 = P0 run/EXS/art/ver/EVD FK。

## AD-2 Release gate 真源
建议: gate 消费 ver-* (PASS) + EVD-* (evidence complete) + 人工 approval —
不读 M3 run.state。

## AD-3 Learning 触发点
建议: finalize_node_run (P0 执行完成) 后事件触发 exp 提取 + profile refresh
(替代 M3 orchestrator 手动) — 使学习接 P0 canonical。

## AD-4 双执行系统 (M3 production_run vs P0 run-*)
现状并存 (P0 已封板, M3 是 legacy)。Release/evaluation 若继续挂 M3 将永远
无法闭环 P0 → 必须切 P0 或标 legacy 冻结。

## 禁止 (任务书 §13)
不重写架构/不重写 event/不重写 task/P0/P1/WebUI/不引新 DB/不引新 Agent framework。
