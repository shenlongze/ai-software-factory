# 09 — GAP ANALYSIS (P1 AUDIT, 2026-09-05)

> 断点清单 + P0/P1/P2 分类

---

## 1. 断点清单

| # | 断点 | 类型 | 证据 |
|---|---|---|---|
| G1 | PRD 无 domain entity (仅 PRD.md 规则 doc) | P1 | generate_prd (actions:511) 纯规则写 md; 无 id/lifecycle/version/req FK |
| G2 | Requirement 无 domain class (内联 dict) | P1 | agent_loop:859-877 无 service/store class |
| G3 | Requirement→PRD 断链 | P1 | 6 PRD.md 零 requirement_id |
| G4 | Discovery→Requirement 断链 | P1 | 无 conversation→req 代码 |
| G5 | Idea→Discovery 断链 (Idea 不进主链) | P1 | PI-* S9 域与主会话链不相交 |
| G6 | PRD→Plan 断链 (plan 不经 PRD) | P1 | plan_development goal→LLM 直接拆 |
| G7 | Plan 无 canonical entity (session_plans 编排状态 + PLAN-* 3 处快照) | P1 | session_plans 16 / session_topics / console_sessions 均存 PLAN-* |
| G8 | 零 product_defined (Discovery 正式链从未真实走通) | P1 | 27 项目 lifecycle 无 product_defined |
| G9 | Task 无 plan_id 部分 (ai-factory-self 156 全无) | P2 | 来源=手动/会话直接 create_task |
| G10 | Requirement status 硬编码 VALIDATED (无生命周期) | P2 | 7 条全 VALIDATED |
| G11 | Idea 2 条测试数据 | P2 | PI-001 Test Idea |
| G12 | Web 层生成 PLAN-* (7438) 非 domain 层 | P2 | fastapi_adapter:7438 |

## 2. 无 P0

无两个 canonical Product ledger / 无同 ID 双义 / 无 WebUI 绕过 / Task 无 competing
source (create_task 服务端唯一) / 不需改 P0 contract。

## 3. 根因 (单一)

**Product 域 (Requirement/PRD/Plan) 从未作为 domain entities 实现** — 它们是
"会话编排副产品" (requirements.json 内联 / PRD.md 规则 doc / session_plans 快照)。
S9 product 域 (Idea/Approval) 是独立审批系统, 未与执行主链对接。
