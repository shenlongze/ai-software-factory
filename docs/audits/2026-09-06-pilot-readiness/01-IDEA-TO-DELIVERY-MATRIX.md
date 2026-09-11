# 01 — IDEA-TO-DELIVERY MATRIX (2026-09-06, READ-ONLY)

逐阶段: REAL/PARTIAL/SHELL/MOCK/DEAD/MISSING + 代码证据

| Stage | Status | Code Path | Evidence |
|---|---|---|---|
| 1. IDEA 提交 | REAL | WebUI POST /api/projects {idea} → create_project; project chat | fastapi_adapter.py:184+ / api/workflow_start.py:105 |
| 2. 理解/Discovery | PARTIAL | ProjectSpace idea/discovery 资产; complete_discovery (service.py:1598) | 无 LLM 澄清循环; chat=idea 更新+start |
| 3. Requirement | MISSING (旅程) | canonical REQ-* 在 product_truth (P1, tmp-only) | workflow_runner 链 B 无 REQ 步 (WF-DESIGN 直接) |
| 4. PRD | PARTIAL (旅程) | WF-DESIGN stage (architect agent) 产 PRD.md | 链 B PRD=设计产物 (非 canonical PRD-*) |
| 5. Plan | PARTIAL | 链 B: design workflow → WF-APP plan | 非 canonical PLAN-* (M3 workflow) |
| 6. Task Tree | PARTIAL | DevTestLoopRunner (execution_loop) | 内部修复循环, 非 canonical TASK-* 树 |
| 7. Execute | REAL | workflow_runner._real_chain → DeveloperAgent (真实 LLM patch) | 历史成功 (P-69c4f155) |
| 8. Verify | PARTIAL | DevTestLoopRunner 修复轮 ≤2; smoke_check.py | 确定性冒烟 (非 canonical ver-*) |
| 9. Repair/Retry | REAL (有限) | DevTestLoopRunner max_repair_rounds=2; loop runner | 上限 2 轮, 有 failed_reason |
| 10. Product | REAL | dist zip (app.js+html+css+tests) | 2 个真实 zip |
| 11. Acceptance | MISSING | 无 preview/review/用户验收 UI 流程 | 完成即终 |
| 12. Release/Delivery | PARTIAL | ReleaseAgent (M3) + dist zip | 非 canonical RELEASE-*; 无 git tag/deploy |

## 关键结论
- 用户旅程 = workflow_runner 链 (M3 workflow 域) — 真实可产成品 (历史证明)
- canonical 链 (P0-P2D) = 独立账本层, E2E 验证, **未接用户旅程**
- Requirement/Acceptance 两环缺失 (旅程内); canonical PRD/PLAN/REQ 未并入旅程
