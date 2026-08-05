# AI Software Factory — Phase 6E: Change Driven Workflow Layer

> 日期: 2026-08-06
> 前置: Phase 1-6D (2015 tests)
> 目标: Git Change 成为 Workflow 驱动事件

## 范围

- factory-core/changeflow/ (models/rules/engine/triggers/events)
- ChangeTrigger (id/event_type/project_id/task_type/required_validation/target_workflow)
- Change Rule Engine (L4 PASS/Commit linked/Required files/Project runtime pref → PASS/FAIL/SKIP)
- ChangeWorkflowEngine (change event → evaluate → create workflow run → execute next)
- CLI: change triggers list / change evaluate TASK_ID / change workflows TASK_ID
- Event: change.trigger.created/evaluated/workflow.started/completed
- Dashboard Change Flow View
- examples/markpad 扩展 (feature/bug-fix/release 完整链路)
- 测试: 新增 ≥120, 2015 不回归

## 禁止

修改 Workflow Engine / Execution Runner / Git 只读 / 不自动 merge/push
