# S10-058 — Frontend Production & Intelligent Handoff 设计

> 日期:2026-08-15 | Sprint: S10-058 | 设计
> 目标: Backend-centric Team → Full Stack AI Software Company

---

## 1. 架构

```
已有 (S10-057): PM → Architect → Backend → QA → Delivery
    ↓
新增:
  Frontend Agent (frontend-agent: UI/component/frontend 生产)
  Intelligent Handoff (Architect Decision Object → Agent Context → 行为驱动)
  Full Stack Team (software-team 7 成员: pm/architect/backend-1/frontend-agent/qa-agent/reviewer-agent)
  Frontend Validation (flutter test / npm test)
  Frontend Artifacts (components/screens/assets → workspace_context)
  Team Report Upgrade (Agent Contribution 表)
```

## 2. Frontend Agent

```
frontend-agent:
  role: Frontend Engineer
  skills: [frontend, flutter, react, typescript, ui]
  capabilities: [ui_architecture, component_design, frontend_implementation, frontend_testing]
  supported_tasks: [frontend_page, ui_interaction, component, screen]
  required_role="frontend" → 匹配
```

## 3. Intelligent Handoff (Decision Object)

```
旧: Architect → message record (记录但无驱动)
新: Architect → Decision Object → Agent Context → 执行前自动读取

ArchitectDecision:
  {from, to, decision: {architecture, state_management, api_contract}, constraints}

AgentExecutionContext.previous_decisions:
  Frontend Agent 收到:
    Architect decided: Frontend=Flutter, API=REST, Backend=already completed
  → 根据上下文执行
```

## 4. ScorePocket Full Stack Pilot

```
Backend:  score API + match API
Frontend: score screen + match screen + ranking UI
QA:       backend tests + frontend tests
→ 完整应用结构
```

## 5. Frontend Validation

```
Backend: pytest (已有 validate_command)
Frontend: flutter test / npm test (FrontendValidator 统一)
```

## 6. 模块计划

```
factory-console/session/
  agents.py      (修改: +frontend-agent DEFAULT + capabilities)
  teams.py       (修改: DEFAULT_TEAM + reviewer-agent + frontend-agent)
  messages.py    (修改: Handoff 升级 → Decision Object)
  orchestrator.py (修改: previous_decisions 注入 + FrontendValidator + 前端 artifacts)
  quality.py     (修改: +FrontendValidator 或 validate_command 扩展)
tests/console/test_frontend_team.py (新增, >=120 测试)
docs/sprint10/S10-058-frontend-production.md
```

## 7. 边界

- 不破坏 S10-049~057 (backend-only team 兼容)
- Frontend 是新增能力
- 所有决策资产化 (decision_objects.json)
- 所有执行真实验证

---

> 设计完毕 | Frontend Agent + Intelligent Handoff + Full Stack Team
