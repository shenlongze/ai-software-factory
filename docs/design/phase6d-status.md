# AI Software Factory — Phase 6D: Change Intelligence Layer

> 日期: 2026-08-06
> 前置: Phase 1-6C (1813 tests)
> 目标: Task→Execution→Git Change→Commit→Validation 自动关联

## 范围

- factory-core/change/ (models/analyzer/linker/service/events)
- Commit message parser (MP-BUG-001 → GitCommit.task_id; branch/message/execution context)
- GitBranchContext (branch/task_id/project_id/status/created_at)
- Execution Git Snapshot (before_commit/after_commit/changed_files, 兼容)
- Change Analyzer (factory change analyze TASK_ID → Files/Insertions/Deletions/Affected modules, 路径分析禁 LLM)
- Validation L4 (Task 描述 vs Git Change → PASS/FAIL/SKIP)
- Dashboard Change View
- Event: git.task.bound/git.commit.linked/change.analyzed/change.validation.completed
- 测试: 新增 ≥100, 1813 不回归

## 禁止

修改 Workflow Engine / Execution Runner / 自动 commit/push; Git 只读
