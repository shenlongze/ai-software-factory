# 11 — WEBUI / API / CLI BOUNDARY (P1 CONTRACT, 2026-09-05)

> D17: 访问路径冻结

---

## 1. 冻结访问路径 (全部实体)

```
WebUI / CLI / Agent / Session
      ↓
API / Command (action)
      ↓
Domain Service (唯一 writer)
      ↓
Canonical Store
      ↓
Event (观察)
```

禁止:
- WebUI/Agent 直写 JSON/markdown
- 前端生成 domain id
- CLI 绕过 service 写 store

## 2. 现状审计

| 入口 | 现状 | 判定 |
|---|---|---|
| WebUI task 创建 | 经会话消息 → backend agent → service.create_task | PASS (已合规) |
| WebUI create_idea action | fastapi:7738 → **service.create_feature** (任务树 feature!) | **违规语义** — create_feature 不是 IdeaService; P1 改经 IdeaService.create_idea |
| WebUI plan 生成 | fastapi:7438 内联 plan_development + PLAN-* 生成 | **API 层生成 domain id** — P1 改调 PlanService |
| agent_loop requirement 内联 | agent_loop:859 直写 requirements.json | **agent 直写** — P1 改调 RequirementService |
| generate_prd action | actions:511 规则写 PRD.md | P1 改调 PRDService (entity + version + md 投影) |
| complete_discovery | service (合规雏形) | 扩展 entity |

## 3. REST/SSE

现状消息经会话 API (合规); P1 增加 domain 级 REST 只读端点 + command
端点 (经 service) — Implementation 期决定, 本阶段不补。

## 4. localStorage

仅 UI preference (P1 审计确认无业务 SSOT) — 保持禁令。
