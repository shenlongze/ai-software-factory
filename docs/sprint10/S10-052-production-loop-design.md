# S10-052 — Autonomous Software Production Loop 设计

> 日期:2026-08-15 | Sprint: S10-052 | Phase 0 分析 + Phase 1-7 设计

---

## 1. Phase 0 — 内部分析

### 复用点(S10-051)
```
pipeline.AgentAssignment.from_tasks → {"tasks": [{id, name, agent_type, agent}], "count"}
pipeline.Lifecycle                → IDEA/PRODUCT_DEFINED/ENGINEERING_READY/EXECUTION_READY/DEVELOPMENT/TESTING/DELIVERED
actions.execute_task(context)     → 薄调 exec.cli.cmd_exec_run (真实 AgentRuntime + LLM + artifact + audit)
actions.select_agent              → task → agent (frontend→flutter-dev/backend→backend-1)
audit.record_execution            → 执行审计 (execution_records.json)
```

### 当前缺口
```
G1: 无 ExecutionOrchestrator (读取 execution_plan → 任务队列 → 执行)
G2: 无 execution_state.json (任务状态持久: pending/running/completed/failed)
G3: 无 execute_project action ("开始开发" 入口)
G4: 无进度查询 ("项目进度")
G5: 无失败处理 (retry_count/max_retry, 不无限重试)
G6: Lifecycle 不自动推进 (EXECUTION_READY→DEVELOPMENT→TESTING→DELIVERED)
```

### S10-052 最小范围
```
P0: ExecutionOrchestrator (读取 plan → 顺序执行队列 → 状态管理)
P1: execution_state.json (任务状态持久化)
P2: execute_project Action ("开始开发" → 确认门 → 执行)
P3: Lifecycle 自动推进 (DEVELOPMENT/TESTING/DELIVERED)
P4: 进度查询 action ("项目进度")
P5: 失败处理 (retry_count/max_retry=1, 记录 failed, 不无限重试)
```

---

## 2. Execution Architecture

```
User: "开始开发"
    ↓
execute_project intent → ConfirmationGate (敏感)
    ↓
execute_project Action
    ↓
ExecutionOrchestrator.execute_project(project_id)
    ├─ 读 execution_plan.json (tasks + agents)
    ├─ 初始化 execution_state.json {status: development, tasks: [{id, status: pending, agent}]}
    ├─ Lifecycle → DEVELOPMENT
    ├─ Task Queue (顺序执行, 保留未来 DAG 扩展)
    │    └─ 每任务: 调 execute_task (复用 S10-049) → status: running → completed/failed
    │         ├─ 成功: artifact 记录
    │         └─ 失败: retry_count+1, max_retry=1 → failed (不无限重试)
    ├─ 全部完成 → Lifecycle → TESTING (测试门占位)
    ├─ 测试通过 → Lifecycle → DELIVERED
    └─ 返回 ExecutionResult {completed_tasks, failed_tasks, artifacts, duration, cost}
    ↓
Audit (record_execution 每任务)
```

## 3. ExecutionOrchestrator

```python
class ExecutionOrchestrator:
    def __init__(self, workspace: Path): ...

    def execute_project(self, project_id: str, *, execute_fn=None) -> ExecutionResult:
        """读取 execution_plan.json → 顺序执行 → 状态持久化 → Lifecycle 推进。"""

    def get_progress(self, project_id: str) -> dict:
        """进度查询: status/tasks total/completed/running/pending/failed/agents。"""

    def resume(self, project_id: str) -> ExecutionResult:
        """恢复: 从 execution_state.json 继续 pending/failed 任务 (支持暂停恢复)。"""

@dataclass
class ExecutionResult:
    project: str
    status: str            # development/testing/delivered/failed
    completed_tasks: int
    failed_tasks: int
    artifacts: list[str]
    duration: float
    cost: str
    errors: list[str]
```

## 4. Execution State(execution_state.json)

```json
{
  "project": "ScorePocket",
  "status": "development",
  "lifecycle": "development",
  "started_at": "...",
  "tasks": [
    {"id": "T001", "name": "数据库 Schema", "agent": "backend-1",
     "status": "completed", "artifact": "path", "retry_count": 0}
  ]
}
```

## 5. Task Queue

```
第一版: 顺序执行 (execution_plan.json 顺序)
- pending → running → completed/failed
- 每任务: 构造 execute_task intent {objective: task.name, task_id, agent_id: task.agent}
- 未来: DAG 依赖 (保留 interface: TaskQueue.next_pending() / mark_done(id))
```

## 6. Lifecycle 自动推进

```
execute_project 开始: EXECUTION_READY → DEVELOPMENT
全部任务完成 (无 failed): → TESTING
测试门通过 (占位: 无测试 → 视为通过): → DELIVERED
有 failed 任务: → 保持 DEVELOPMENT (状态 failed, 可恢复)
```

## 7. 失败处理

```
- 单任务失败: retry_count+1; retry_count < max_retry(1) → 重试一次
- 重试仍失败: status=failed, 记录 error (不阻塞其他任务? 或停止?)
  → 第一版: 记录 failed, 继续下一任务 (顺序), 最后汇总
- 不无限重试
- 预留 Repair Loop: failed 任务可由未来 repair action 重试
```

## 8. Action 注册

```
execute_project (name="execute_project", sensitive=True, category="execution")
  — "开始开发/开始执行/执行项目" → 确认门
project_progress (name="project_progress", sensitive=False, category="execution")
  — "项目进度/进度如何" → 查询
```

## 9. 架构符合性

| 原则 | 符合 |
|---|---|
| 复用 Agent Runtime | ✅ execute_task (S10-049) 薄调, 零重实现 |
| 非简单循环 | ✅ 状态管理/任务追踪/失败处理 |
| 可审计/可恢复/可观察 | ✅ audit + execution_state + progress 查询 |
| 走 Intent/Action/Service | ✅ execute_project/project_progress |
| 长期方向 | ✅ Idea→Product→Engineering→Execution→Delivery |

---

## 10. 文件计划

```
factory-console/session/
  orchestrator.py  (新增: ExecutionOrchestrator + ExecutionResult + ExecutionState)
  actions.py       (修改: +execute_project +project_progress)
  intent.py        (修改: +execute_project +project_progress 关键词)
  router.py        (修改: 映射)
  conversation.py  (修改: 最小 — 可选)
tests/console/
  test_session_orchestrator.py (新增, >=60 测试)
docs/sprint10/S10-052-autonomous-production-loop.md (Phase 10)
```

> Phase 1-7 设计完毕 | Orchestrator + State + Queue + Lifecycle + Progress + Failure | 复用 execute_task
