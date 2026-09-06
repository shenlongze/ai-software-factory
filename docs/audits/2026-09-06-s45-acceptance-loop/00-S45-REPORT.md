# S45 — Acceptance Loop: 用户验收闭环 (2026-09-06)

## 1. Objective
把 "机器验证完成" 与 "用户认可" 连接 — Verification PASS ≠ User Accepted;
Request Change 必须产生真实生产动作。

## 2. Preflight
- 无现 acceptance 域 (MISSING) | artifact API 在 (project artifacts)
- ver PASS 后 → release_truth 手动; gate 无 acceptance 概念
- 产品 = workflow dist zip + S44 吸收 canonical art-*

## 3. Product/Artifact Model
art-* (canonical, version 字段) + ver-* PASS + EVD-* (P0 链, S44 workflow 吸收)

## 4. Acceptance Contract
ACC-* (acceptance/acceptance.json); 绑定 artifact_id+version+verification_id
+source_run_id (禁模糊批准); reviewer/decision/comment/history 审计全

## 5. State Machine
PENDING → APPROVED | CHANGE_REQUESTED | SUPERSEDED;
APPROVED → CHANGE_REQUESTED | SUPERSEDED; SUPERSEDED 终态 (禁回 APPROVED);
approve 要求 ver PASS (禁批准未验证); approve/request-change 幂等

## 6. API
GET /api/projects/{pid}/acceptances; POST /api/acceptances/{id}/approve;
POST /api/acceptances/{id}/request-change — backend canonical, WebUI 投影

## 7. UI
本 Sprint 不加 (WebUI 投影原则; 验收 UI 后续 Sprint — 后端域/API 已备)

## 8. Approve Flow
ACC PENDING → approve(reviewer) → ver PASS 检查 → APPROVED (幂等)

## 9. Change Request Flow
ACC any → request_change(comment) → CHANGE_REQUESTED (旧批准失效)

## 10. Repair Flow
真实新 run/EXS/art(V2)/ver/EVD → begin_acceptance(V2) PENDING (不继承) →
supersede_older → approve

## 11. Release Gate Integration
gate_release(require_acceptance=True): 每 art 须 ACC APPROVED →
未验收 REJECTED (acceptance_not_approved); 默认 False 保 P2-A 兼容 (backward
test PASS)

## 12. Idempotency
approve 重复 → 现有 APPROVED (1 fact); change 同 comment 重复 → 现有;
begin 同 (art,ver) → 现有

## 13. Failure Semantics
ver FAIL → approve 拒绝; repair 失败 → 无 ACC (不伪造); CHANGE_REQUESTED→
APPROVED 拒绝 (须新版本)

## 14. Provenance
ACC → art → ver → EVD → EXS → run → TASK (全 FK; V1/V2 独立并存)

## 15. Fresh E2E — Approve (真实 IDs, 隔离 tmp)
ACC-…-de115074 PENDING (art-8d2c1f63 ver-f3b5f274) → approve user → APPROVED
→ release gate require_acceptance → GATED

## 16. Fresh E2E — Change → Repair → Approve
V1 APPROVED → Request Change (改成深色主题) → CHANGE_REQUESTED → 真实 repair
run → V2 (art-5961f687 新 ver-9dbe39fa) → V2 ACC PENDING (不继承) → approve →
APPROVED → V2 release gate GATED; V1+V2 artifacts 并存无覆盖; EVD per ver

## 17. Tests
S45: 16/16 | S44: 7/7 | P0 F1-F4: 55/55 | P1: 15/15 | P2-A: 14/14 |
P2-C: 15/15 | P2-D: 20/20 | Full backend: 2344 passed + 4 pre-existing |
Frontend: 未动

## 18. Regression Attribution
S45 attributable regressions = 0 (stash 对照 20=20 identical)

## 19. Acceptance Criteria
AC1-AC16 全 PASS (canonical fact/真实 approve/change→真实 production/
新 ACC cycle/旧批准不迁移/release 阻塞+放行/双 E2E/幂等/WebUI 投影/零第二套)

## 20. Git
HEAD before 9b33ba47 → commit S45 → (git log) | NO PUSH | unrelated 保留

## 21. Out of Scope (零改动)
Agent Runtime / MCP / Knowledge / Workforce / SRE / Action Control Plane /
大规模 WebUI 重构 / P0-P2D 冻结域
