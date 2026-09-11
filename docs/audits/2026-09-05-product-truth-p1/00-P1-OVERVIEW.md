# 00 — P1 OVERVIEW (2026-09-05, READ-ONLY GAP AUDIT)

> 阶段: P1 Product Truth Chain — READ-ONLY GAP AUDIT
> 基线: F0-F4 committed (d849a108 / 794e24d7 / 69ca3367)
> 范围: User Intent → Idea → Discovery → Requirement → PRD → Plan → Task (→ P0 Execution Truth)
> 产出: 本目录 11 份审计报告; 零代码/零数据/零 git 改动

---

## 1. 判定摘要

| 段 | Maturity | 判定 |
|---|---|---|
| Idea | **M2** (存在但脱节) | product/ideas.json PI-* (2 条测试) = S9 product 审批域实体, 与主会话链脱节 |
| Idea→Discovery | **M2→M1** | discovery 会话存在 (1 项目 lifecycle=discovery) 但零 product-definition 产物 |
| Discovery | **M2** | complete_discovery 完整实现但真实 0 产物; 27 项目零 product_defined |
| Discovery→Requirement | **MISSING** | discovery conversation → requirement 无链接代码 |
| Requirement | **M2** | req_{hex12} 内联落盘 7 条 (VALIDATED), 无 domain class/store/service |
| Requirement→PRD | **MISSING** | PRD.md 不关联 requirement_id (6 个 PRD.md 零 req 引用) |
| PRD | **M1** | PRD.md 纯规则 doc (pipeline.ProductDocument), 无 domain entity/id/lifecycle/version |
| PRD→Plan | **MISSING→M1** | plan_development 不经 PRD (直接 goal→LLM 拆任务) |
| Plan | **M2** | session_plans.json = session 编排状态 (16, 4 带 req_id, 无 plan_id 实体) |
| Plan→Task | **M2-PARTIAL** | chain_start 用 plan 生成 Task 注入 plan_id (部分项目有 PLAN-*, 部分无) |
| Task | **M4** (P0 冻结) | TASK-* canonical |
| Task→TaskRun | P0-F4 PASS | 已封板 |

## 2. 核心结论

Product Truth Chain **不闭环**: Idea→Discovery→Requirement→PRD→Plan 每段或
MISSING 或 M1/M2, 仅 Plan→Task→(P0) 有真实链接 (且 plan 无 PRD/requirement 上游)。

## 3. 无 P0 触发 (检查)

- 无多个 canonical Product ledger (各段或单账本或缺失, 无两套都自称 canonical)
- 无 WebUI 绕过 backend 修改 Product Truth (只经会话 API)
- Task 上游: 部分 Task 无 plan_id (ai-factory-self 156 任务全无) — 但 task 创建
  是服务端 create_task (非多 competing source — 有 session/plan 两种来源)
- P0 Task/TaskRun/EXS/Artifact/Verification/Evidence contract 未触及

**P1 级**: PRD/Requirement 无 canonical domain; 多段断链 (见 09-GAP-ANALYSIS)。
