# 08 — WEBUI / API / CLI BOUNDARY (P1 AUDIT, 2026-09-05)

> WebUI 是否仍持有 Product Truth 独立事实

---

## 1. WebUI 边界检查

| 能力 | 前端直接做? | 经 backend? | 判定 |
|---|---|---|---|
| Task 创建 | 否 (无前端 createTask 代码) | 是 (会话消息 → backend agent → service.create_task) | **PASS** (boundary 保持) |
| Plan 生成 | 否 | 是 (消息 → fastapi_adapter plan_development) | **PASS** — 但 plan_id 生成在 backend API 层 (7438) 非 domain 层 (P1: 位置问题) |
| PRD 生成 | 否 | 是 (generate_prd action) | **PASS** |
| Requirement | 否 | 是 (agent_loop 内联) | **PASS** |
| Discovery | 否 | 是 (service.complete_discovery) | **PASS** |
| localStorage | 仅 UI preference (未发现业务 SSOT) | — | **PASS** |

前端仅 ConversationContext 有模块锚点 (create_task 自动绑定注释) — 会话驱动,
非前端独立写。

## 2. API / CLI Contract 现状

| 能力 | Domain | Service | API | CLI |
|---|---|---|---|---|
| Task | ✅ (P0) | ✅ create_task | ✅ /api/tasks | ✅ factory task |
| Requirement | ❌ (无 domain) | 内联 | (经会话) | ? |
| PRD | ❌ (无 domain) | actions | (经会话 action) | ? |
| Plan | ❌ (无 domain) | 会话内联 | (经会话) | ? |
| Discovery | 半 (实现无数据) | ✅ complete_discovery | ? | ? |

- Requirement/PRD/Plan 无 domain → 无正规 API/CLI (P1)
- 本阶段**禁止补 API** — 仅记录

## 3. 结论

WebUI 不绕过 backend (PASS); 但 Product domain 缺失导致 API/CLI contract 不完整 (P1)。
