# S47-B — Human Control Plane: Acceptance + Release + Delivery (2026-09-06)

## 1. Objective
把 S45/S46 已存在的 canonical backend capability (ACC-*/RELEASE-*) 接到
现有 WebUI — 用户能 审查 → 验收 → 发布 → 取交付物。

## 2. Existing UI reused
AfProjectShell 子页框架 / 侧栏 nav / ds 设计系统 / api client 模式 —
零重构。

## 3. Backend APIs reused
acceptance_truth (approve/request_change/list) 端点复用 (S45);
新增 canonical release 薄代理 (防接 M3 release_service rel-* 旧域)。

## 4. Files changed
backend: fastapi_adapter.py (+3 端点)
frontend: api/client.ts (+6 方法) · models/domain.ts (+2 类型) ·
pages/project/AfReviewPage.tsx (新) · AfProjectShell (+review 子页) ·
AfProjectSidebar (+验收发布 nav) · router.tsx (+review 路由) ·
test/af-review-page.test.tsx (新 8) · router/shell 断言 7→8

## 5. Acceptance implementation
项目验收列表 (canonical ACC 投影): PENDING → [Approve] / [Request
Changes (comment)]; APPROVED 状态持久 (refresh 重读); 错误保持 + 真实
错误显示; 无乐观更新。

## 6. Release implementation
[Create Release (Gate)] 仅 APPROVED ACC → backend create + gate
(require_acceptance) → GATED/REJECTED(原因显示); [Release] → backend
execute (governance BLOCK → owner 请求 + admin 批准编排) → RELEASED。

## 7. Delivery implementation
RELEASED → 产物 artifact 列表展示; canonical list 可查。

## 8. State synchronization
按钮成功后 load() 重读 canonical truth; 浏览器刷新 = 重读 → 正确。

## 9. Project isolation
releases joined by ACC source_run (project 专属); E2E 实证 S46 记录完好。

## 10. Tests
frontend af-review-page 8/8 (vitest) | router/shell 更新 | 全套 545/546
(1 pre-existing todo 时间敏感) | tsc OK | backend 188 passed。

## 11. Real E2E (HTTP API, 真实 ~/.factory)
ACC-* approve (幂等 200) → refresh APPROVED 持久 → create RELEASE
GATED (gate []) → execute RELEASED (governance 编排) → delivery list
可见; S46 RELEASE-4956b0b5 完好。负路径: 端点首版缺 exs → gate 诚实
REJECTED (missing exs) → 端点修复 (run→EXS 反查) → GATED。

## 12. Regression attribution
backend 188 passed 0 新增失败; frontend 545/546 (todo = pre-existing,
文件未碰 stash 对照); attributable = 0。

## 13. Git commit
a42541d9 feat(webui): connect acceptance release and delivery control plane
NO PUSH

## 14. Remaining P2 gaps (本 Sprint 不做)
- 真时 Agent/Task 监控板; workflow 详情 mock fallback 消除
- 任务/run → canonical ver/art/EVD 下钻; 版本化 delivery 下载
- Request Change → 自动触发新 repair run 的 UI 编排 (后端 workflow start
  已备, 需 UI 串接)
- ACC/release 审计 provenance 详情展开

## 15. Final acceptance (AC-01..20)
AC-01..19 PASS (real 后端记录 + 前端投影 + 测试 + 真实 E2E); AC-20 无第二
execution path ✓ (仅调 canonical API)。

## Verdict: S47-B COMPLETE
