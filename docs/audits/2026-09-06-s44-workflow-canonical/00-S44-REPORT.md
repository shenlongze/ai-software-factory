# S44 — Workflow → Canonical Production Truth 双链合一 (2026-09-06)

## 1. Objective
把现有真实用户生产 Workflow (workflow_runner) 的 finalize 接入冻结 canonical
P0 链 (PB-1) — 不重写 Workflow, 不建第二套 truth。

## 2. Preflight Findings
- 用户旅程: WebUI POST /api/projects{idea} → chat/start → workflow_runner
  (后台线程) → factory-exec DeveloperAgent (真实 LLM) → dist zip
- run_id = R{ms} (M3); report.json 落盘后 _thread_main 结束 — 无 canonical 吸收
- canonical P0 stores 同 root (~/.factory): nodes/verifications/evidence/artifacts
- 断链点: workflow finalize 事件从未进入 canonical (零 finalize_node_run 引用)

## 3. Root Cause
workflow_runner 是 M3 时代独立链 (org.workflow + factory-exec + ReleaseAgent),
与 P0-P2D canonical 并行, 无吸收适配层。

## 4. Integration Boundary
_thread_main (report 落盘后, 单一收尾) → workflow_canonical_bridge.
absorb_workflow_to_canonical (薄 adapter)。

## 5. Files Changed
- factory-console/workflow_canonical_bridge.py (新)
- factory-console/workflow_runner.py (_thread_main + absorb 调用, 失败安全)
- tests/console/test_s44_workflow_canonical.py (新, 7)

## 6. Canonical Mapping
Workflow finalize (report) → TASK-workflow-{run_id} (确定性) → run-* (create_
node_run trigger=workflow) → EXS-* (record_invocation executor=factory-exec) →
art-* (finalize 吸收) → ver-* (method=workflow_acceptance) → EVD-* (真实
acceptance stdout)

## 7. Idempotency
确定性 task_id + EXS 探测 → 重复 finalize 返回 already_absorbed (E2E 实证 1→1)

## 8. Failure Semantics
- workflow failed/cancelled → ver FAIL (不伪造)
- COMPLETED 但 acceptance gap → ver FAIL (诚实)
- 吸收异常 → 返回 absorbed=False, 不覆盖 report (失败安全)

## 9. Provenance
EVD → ver → art → EXS → run → TASK-workflow-{run_id} → (workflow report)
全 canonical FK

## 10. Fresh E2E Evidence (隔离 tmp)
TASK-workflow-R-fresh-e2e → run-a1af6d0e6f64 → EXS-709eb653 →
art-01e0a80d996e → ver-16e9cdb372 PASS (workflow_acceptance) → EVD-b4f7077c21
幂等 1→1; failure → ver FAIL

## 11. Tests
S44 tests: 7/7 | Full backend: 2767 passed + 20 pre-existing (stash 对照
20=20 零差异) | S44 attributable = 0 | Frontend: 未动

## 12. Acceptance Criteria
AC1 PASS (不再平行 — finalize 进 canonical) | AC2 PASS (TASK→run→EXS→art→ver→EVD) |
AC3 PASS (真实 records) | AC4 PASS (provenance 全 FK) | AC5 PASS (幂等) |
AC6 PASS (失败不伪造) | AC7 PASS (workflow 原逻辑未动, 吸收失败安全) |
AC8 PASS (7/7 + 回归) | AC9 PASS (fresh E2E) | AC10 PASS (零第二 store)

## 13. Git
HEAD before: 7c6f0ed3 | commit: (S44) | HEAD after 见 git log
status: 3 S44 文件 committed; unrelated 保留

## 14. Out of Scope (未碰)
Agent Runtime / MCP / Knowledge / Workforce / SRE / Action Control Plane /
WebUI 大重构 / P0-P2D 冻结域 — 全零改动
