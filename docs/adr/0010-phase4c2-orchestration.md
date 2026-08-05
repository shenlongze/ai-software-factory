# ADR-0010 — Phase 4C-2: Execution Orchestration Flow

> 日期: 2026-08-06 | 状态: Accepted

## 背景

把已有模块 (Workflow/Assignment/Execution/Runtime) 连接成自动生产流水线: workflow run TASK_ID --auto。

## 决策

### 1. OrchestrationEngine 只组装不重写
`execute_workflow(task_id)` 复用 WorkflowEngine / AgentMatcher / AgentAllocator / ExecutionService / ExecutionRunner / RuntimeAdapter — 零逻辑复制, 单一组合根 (pipeline.py)。

### 2. 失败 = Workflow FAILED, 无半完成状态
任何失败 (无匹配 Agent / 无 Runtime / 无 Adapter / 执行 FAILED) → fail_workflow → Workflow FAILED + Agent 回 AVAILABLE + Assignment FAILED。前置错误 (任务不存在/已终态) 不改状态。

### 3. 事件全序
orchestration.started → step.started → step.completed (×N) → completed / failed; 全部经 EventLogger。

### 4. 参数优先于 env
Hermes env 覆盖 (FACTORY_HERMES_CMD) 测试改用构造函数参数 (BUILTIN_ADAPTERS 单例 import 时固化)。

## 验证

- pytest 981 全绿 (908 + 73)
- CLI 冒烟: 完整 4 步链路 COMPLETED; 失败路径 (无匹配 Agent) → FAILED 无半完成
