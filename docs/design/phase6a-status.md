# AI Software Factory — Phase 6A: Multi Project Workspace Layer

> 日期: 2026-08-06
> 前置: Phase 1-5B (1395 tests)
> 目标: 一个 Factory Workspace 管理多个项目 (markpad/scorepocket/timeon)

## 范围

- factory-core/workspace/ (models/manager/store/loader/config)
- Workspace (id/name/version/root_path/projects) + ProjectDefinition 增强 (runtime_preferences/status)
- WorkspaceManager (create/load/list/get/add/remove)
- workspace.yaml + projects/*/project.yaml 自动发现
- CLI: workspace init + project list/show 增强 (Status)
- Task project_id 兼容 (旧 Task 可读)
- Dashboard Projects View (每项目计数 + success rate)
- Metrics project 过滤
- Event: workspace.* + project.*
- 测试: 新增 ≥80, 1395 不回归

## 禁止

修改 Task 核心模型破坏兼容 / Workflow Engine / Runtime Adapter / Execution Runner / 复制 Project 逻辑
Project=上层组织单位, Task 经 project_id 关联
