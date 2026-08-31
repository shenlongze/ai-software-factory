# S34-CORE-P0 — Production Core One Execution Path 收敛报告

> 日期: 2026-08-31 | 真实 E2E 证据

## 1. Root Cause

```
Web Conversation 部分工具自实现, 不调 Production Core:
- create_project → org.cli.cmd_project_register (绕过 ConsoleService)
- plan_development → 纯 LLM JSON (不落 Plan Artifact / 无审批门)
- 前端从未渲染 progress-card (计划不可见)
- Requirement 无真实落盘
```

## 2. One Execution Path 收敛

```
项目创建 (C2): Web → factory_console.api.projects.create_project (ConsoleService Core)
              = CLI (projectos) / API (POST /api/projects) 同一 Core ✅
计划落盘 (C1): plan_development → progress_card (planning 态持久化) + session_plans.json ✅
审批门 (C3):  plan_development → request_approval (appr-xxx PENDING 持久化) ✅
进度展示 (C4): 前端渲染 progress-card (后端 Source of Truth) ✅
Requirement (C5): requirements.json 真实落盘 (req_xxx, session/project 绑定) ✅
```

## 3. 真实 E2E (飞机大战)

```
用户: "我要做一个飞机大战游戏, 出个计划"
→ project_list + project_status (Domain 工具, 无 bash)
→ 识别已有 P-b0adfaa6 (不猜/不污染)
→ plan_development → 12 任务计划
→ progress_card: planning + 8 验收标准 ✅
→ approval: appr-cb850e1a13 (PENDING 持久化) ✅
→ requirement: req_33846c95b001 (requirements.json) ✅
```

## 4. 验证

```
✅ 后端: 1150 passed + 4 skipped
✅ 前端: 518/519 (af-todo-tree 历史漂移)
✅ tsc | build: PASS
✅ git clean
```

## 5. 完成标准

```
✅ C1 Plan 真实 Artifact (progress_card + session_plans)
✅ C2 Web 项目创建用 Core (ConsoleService)
✅ C3 Approval 真实 ApprovalGate (appr-xxx PENDING)
✅ C4 Workspace 显示真实 Progress (前端渲染)
✅ C5 Requirement 真实落盘 (requirements.json)
✅ CLI/API/Web 同一 Core (create/plan/approval)
✅ 飞机大战 E2E 成功
✅ 全量测试通过 | git clean
```
