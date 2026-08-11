# S10-011 Execution Engine — Architecture Design

> 状态: 待确认 | 日期: 2026-08-11 | 基线: a82de51 (pytest 6976)
> 依据: AF-PRD-v1.md 4.7-4.9 + docs/design/execution-engine.md + S10-010 现状
> 范围: Execution Engine 基础 (禁 UI/Agent 实现/MCP/LLM/PRD 修改)

## 一、核心数据流 (确认)

```
Task (management/backlog)
  ↓
Scheduler          (选 READY + dependency 满足 + priority 排序 + 并发 ≤ 5)
  ↓
Dispatcher         (绑定 agent/skill/mcp → 生成 Workflow Instance)
  ↓
Workflow Instance  (workflow-instance/ 生命周期 CREATED→RUNNING→SUCCESS/FAILED/CANCELLED)
  ↓
Executor (stub)    (本 Sprint 不实现真实 Agent — 只建执行框架; 注入点预留)
  ↓
Runtime            (runtime/ 执行状态)
  ↓
Result             (成功 → Task IN_PROGRESS→REVIEW→DONE; 失败 → BLOCKED)
  ↓
Audit Log          (logs/ 不可变审计: 谁/何时/执行什么/输入/输出/结果)
```

## 二、7 项设计确认

### 1. Scheduler 架构

```
输入: 项目 Task 列表 (READY + dependency 满足)
规则: priority (P0>P1>P2>P3) → dependency (必须满足) → status (仅 READY)
      → Blocked 不执行 → 同项目 max_parallel_tasks=5 (workspace/settings 可覆盖)
输出: ExecutionPlan { tasks: [{task_id, agent_hint, order}], parallel_batch: [...] }
实现: org/execution.py Scheduler 纯函数 (plan_tasks) — 无副作用, 可测试
```

### 2. Dispatcher 架构

```
输入: ExecutionPlan 单任务 + ProjectBindings (agent/skill/mcp)
行为: 校验 binding 存在 (agent 缺失 → 可执行但无 agent 标注) → 创建 Workflow Instance
      → 分配 executor (本 Sprint: ExecutionStub — 注入点, 真实 Agent S10-012+)
实现: dispatch_task(task, bindings) → WorkflowInstance
```

### 3. Agent/Skill/MCP binding

```
复用 S10-009 Project.bindings (预留字段)
本 Sprint: bindings 读取 + 校验 (存在性), 不实现真实 Agent 选择
dispatch 时记录 instance.agent/skill/mcp 引用 (来自 bindings 或空)
```

### 4. Workflow Instance 生命周期

```
状态: CREATED → RUNNING → SUCCESS / FAILED / CANCELLED
目录: workspace/projects/{slug}/workflow-instance/{instance_id}.json
字段: instance_id/task_id/workflow_id/agent/skill/mcp/status/start_time/end_time/result
受控转换表 (非法拒绝)
```

### 5. Runtime 数据模型

```
目录: workspace/projects/{slug}/runtime/
  task-execution/{task_id}.json   (当前任务执行状态)
  agent-execution/{instance_id}.json
  workflow-execution/{instance_id}.json
语义: 运行上下文 (可恢复); 不存业务状态 (management 职责)
```

### 6. Log/Audit 模型

```
目录: workspace/projects/{slug}/logs/audit.log (追加不可变)
记录: {time, actor, action, entity, input, output, result}
actor: scheduler|dispatcher|executor|user|system
本 Sprint: 写审计条目 (原子追加) + 读取 (list)
```

### 7. 并发控制模型 (S10-011 必做 — B1/B2 前置)

```
per-project 文件锁 (threading.RLock + 进程内互斥):
  ExecutionLock: acquire(project_id) / release
  写操作 (task 状态更新/scheduler plan/workflow instance 创建) 持锁
  解决: 多 Agent 同时修改同一 Project (read-modify-write 竞争)
  (跨进程锁 S10-012+ 再评估; 本 Sprint 单进程服务)
```

## 三、Task 拆分 (每 Task: 设计→实现→测试→commit→Quality)

```
Task 001 Execution Domain Model   (org/execution.py: WorkflowInstance/ExecutionPlan/
                                   ExecutionLock 实体 + 状态机 + runtime/audit 写入)
Task 002 Scheduler                (plan_tasks: READY+依赖+priority+并行≤5)
Task 003 Dispatcher               (dispatch_task: binding 校验 + instance 创建)
Task 004 Workflow Instance Runtime (生命周期执行: RUNNING→SUCCESS/FAILED + runtime 更新
                                   + Task 状态更新 IN_PROGRESS→REVIEW/DONE 或 BLOCKED)
Task 005 Concurrency Lock          (per-project 锁集成: scheduler/dispatch/状态更新持锁)
Task 006 Notification + Audit     (audit.log 全链路记录 + notification 预留接口)
```

## 四、禁止

```
❌ UI / Agent 具体实现 / MCP 实现 / LLM 调用 / 修改 PRD
✅ 只建 Execution Engine 基础 (执行框架 + 注入点)
```

## 五、验收 (本 Sprint)

```
场景1: READY 任务 → scheduler 选出 (priority 排序) → dispatch → instance CREATED
       → execute stub → SUCCESS → Task DONE + audit 记录
场景2: 依赖未满足 → 不入选/拒绝 (manual 执行返回原因)
场景3: Blocked → 不执行
场景4: 并发 6 任务 → 只执行 5 (max_parallel) + 锁生效 (同项目写串行)
场景5: 失败 → Task BLOCKED + instance FAILED + audit 记录
```
