# ADR-0016 — Phase 6A: Multi Project Workspace Layer

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Factory 从单项目 (examples/markpad) 升级为多项目 Workspace (markpad/scorepocket/timeon)。

## 决策

### 1. Workspace = 上层组织单位
workspace.yaml (name + projects 列表) 定义工作区; projects/*/project.yaml 每项目定义。workspace loader 复用 project.loader (不复制解析逻辑)。

### 2. ProjectDefinition 增强
+runtime_preferences/status (默认值, 向后兼容)。

### 3. 发现顺序
managed workspace/projects/ 优先 + examples 兜底 (Phase 5A 兼容)。配置损坏 fail-hard (明确报错, 绝不静默空)。

### 4. Task project_id 兼容
Task.project 字段沿用 (Phase 2 起存在); 旧 Task 可读; 不存在 project 不报错。

### 5. Dashboard/Metrics 项目维度
Projects View (每项目 task/workflow/execution 计数 + success rate); metrics --project 归属过滤。

### 6. 测试文件唯一 basename
跨目录同名测试模块 (test_store/test_loader/test_models) 触发 pytest 收集冲突 → workspace 测试用 test_workspace_* 前缀。

## 验证

- pytest 1498 全绿 (1395 + 103)
- CLI 冒烟: workspace init/show + project list/show (source: workspace)
- 事件: workspace.created/viewed, project.registered/removed
