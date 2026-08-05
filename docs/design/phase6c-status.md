# AI Software Factory — Phase 6C: Git Integration Layer

> 日期: 2026-08-06
> 前置: Phase 1-6B (1616 tests)
> 目标: Task 与 Git 变更建立可追踪关系 (Git 只读 + 审计)

## 范围

- factory-core/git/ (models/client/service/events)
- GitContext/GitChange/GitCommit 模型
- GitClient (subprocess git: status/diff/log/current_branch/current_commit, 失败安全返回)
- GitService (get_status/get_changes/get_commits/bind_task_change)
- CLI: git status/diff/commits
- Task ↔ git change 关联 (旧 Task 兼容)
- Dashboard Git View
- Event: git.status.viewed/change.detected/commit.viewed
- 测试: 新增 ≥80, 1616 不回归

## 禁止

修改 Workflow Engine / Execution Runner / 自动 push/merge/rebase
Git 只读 + 审计
