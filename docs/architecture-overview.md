# AI Software Factory — 架构总览 (三区 · 11 层)

> 版本: v2.1 | 日期: 2026-08-06 | 状态: 与当前代码一致 (Phase 1–6E, 2159 tests); 三区划分 (Core/Extension/Human Layer) 经 [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) 冻结确认
> 关联文档: [roadmap.md](./roadmap.md)(路线图) · [architecture.md](./architecture.md)(工程化落地版) · [design/architecture.md](./design/architecture.md)(设计稿) · `docs/adr/0001..0020`(决策记录) · [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md)(冻结报告)
>
> 本文档描述**当前已实现**的系统分层。每层 = 一组 `factory-core/` 包 + 对应 CLI 命令 + 事件词汇。所有事实均与仓库代码、git 提交历史、ADR 一致。三区归属: **Core** = ①–⑩ (通用原语) · **Extension** = ⑪ 及未来领域能力 · **Human Layer** = Phase 11 Approval Console。

---

## 1. 全景图:三区 · 11 层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ▓ Human Layer (Phase 11 · 可并行): Approval Console — Web UI 人类审核台      │
│    查看状态 / 审核 AI 输出 / 批准·驳回 / 查看 Metrics — 只读 + 审批动作        │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │ Factory API 薄层 (只读查询 + approve/reject)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  入口层 CLI (factory-core/cli)  —  18 组命令: init/task/event/status/       │
│  validate/agent/skill/workflow/runtime/execution/checkpoint/recover/        │
│  dashboard/metrics/project/workspace/git/change                             │
│  只做参数解析 → 调领域层公开 API → 人类可读输出;每次命令发一条审计事件         │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │ 命令调用 (单向向下)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ▓ Core 区 — 通用原语 (冻结确认: 零领域依赖, 不修改行为)  =  ①–⑩ 层           │
└─────────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│  ① Workspace Layer       workspace/   (6A/6B)   多项目工作区组织层            │
│     管理 workspace.yaml, 按目录发现项目, 项目注册/移除                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  ② Project Layer         project/     (5A)      示例/配置项目层 (只读)        │
│     解析 examples/<project>/project.yaml + agents/skills/workflows 映射      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ③ Task Layer            tasks/       (2)       任务生命周期与状态            │
│     任务定义 (标题/角色/工作流/项目归属) + JSON 持久化                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  ④ Workflow Layer        workflows/   (4A)      工作流定义与执行状态机        │
│     Workflow/Step 状态机 + 内置定义 + 运行记录 (run)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑤ Agent Layer           agents/ + assignment/ (3B/4B-3)  Agent 与分派       │
│     Agent/Skill 注册表 + 匹配 (role/skill/AVAILABLE) + 分配状态机             │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑥ Execution Layer       execution/   (4B-2)    执行请求生命周期              │
│     Dispatcher (选 Runtime) → Runner (PENDING→RUNNING→终态 + 工作流联动)     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑦ Runtime Layer         runtime/ + runtimes/ (4B-1/4C-1/5A.1)  Runtime 抽象 │
│     RuntimeAdapter 协议 + 注册表 + 实现 (echo/hermes) + 能力目录 (catalog)    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑧ Validation Layer      validation/  (3A/6D)   三层验证引擎                  │
│     L1 Factory / L2 Workflow / L3 Artifact (+ 6D 可注入 L4 Change)           │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑨ Recovery Layer        recovery/    (4C-3)    断点续跑与事件回放            │
│     Checkpoint 快照 + EventReplay 重建状态 + 四场景恢复                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ⑩ Observation Layer     events/ + dashboard/ + metrics/ (1/4C-4/5B/6B)      │
│     append-only 事件库 (唯一事实源) + 只读 Dashboard (16 视图) + 六域指标      │
┌─────────────────────────────────────────────────────────────────────────────┐
│  ▓ Extension 区 — 领域能力 (Skill/MCP/Runtime/Provider 声明式注册, 不修改 Core)│
└─────────────────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⑪ Git Intelligence Layer git/ + change/ + changeflow/ (6C/6D/6E)           │
│     Git 只读审计 (status/diff/commits) → 变更智能 (analyze/validate/关联)     │
│     → 变更驱动工作流 (trigger 规则 → 评估 → 触发 workflow run)                │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │ 执行出口 (唯一)
                                        ▼
                    RuntimeAdapter 实现 → 外部 Agent 进程 (hermes CLI 等)
```

**分层纪律 (与代码一致)**:

1. **依赖单向向下**:上层调用下层公开 API,禁止反向依赖与循环 import(跨包引用用函数内延迟 import,如 `validation.rules → change.analyzer`)。
2. **写操作只发生在领域层**:Workspace/Project/Task/Workflow/Agent/Execution/Runtime/Recovery 拥有写方法;Validation/Observation/Git 只读(审计事件由 CLI 命令层发出)。
3. **所有状态变更必须发事件** (ADR-0002):领域写方法返回 `(obj, Event | None)`,经 `EventLogger` 写入 ⑩ 的事件库;读命令也要发 `.viewed` 事件。
4. **执行出口唯一**:任何"启动 Agent / 跑命令"只能走 RuntimeAdapter(⑦);Git 只读铁律:零仓库写命令 (6C)。
5. **JSON store 原子写**:tmp + `os.replace`,损坏文件抛 `Corrupt*StoreError` 不静默返回空(唯一例外:git changes.json 审计增强 → 失败安全 `[]`)。
6. **三区纪律 (冻结 2026-08)**:Core 只含通用原语,零领域依赖;领域能力一律 Extension 声明式注册 (Skill/MCP/Runtime/Provider);Human Layer 只读 + 审批动作,不建第二条执行路径。

---

## 2. 三区边界与 Extension 注册模型 (冻结确认 2026-08)

> 依据 [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md): Core 边界清晰, 扩展体系完整, **冻结有效, 无需重构**。冻结后: 不修改 Core 行为; 新能力一律走 Extension 注册。

### 2.1 三区定义

| 区 | 组成 | 原则 |
|:---|:-----|:-----|
| **Core** | ①–⑩ 层 + CLI 入口 + 存储 (SQLite 事件 + JSON 状态) | 通用原语 (状态/流程/事件/验证/抽象/组织), **零领域依赖**, 冻结后不修改行为 |
| **Extension** | ⑪ Git Intelligence + 未来领域能力 (MCP/Skills/Provider/Product Intelligence/Operations) | 领域能力, 经 **Skill / MCP / Runtime / Provider 声明式注册**接入, 不修改 Core |
| **Human Layer** | Approval Console — Web UI 人类审核台 (Phase 11, 可并行) | 人类审核入口: 只读查询 + 审批动作, **无第二条执行路径** |

**边界原则**: Core = 通用原语; Extension = 领域能力。具体领域一律不进 Core —— Git/GitHub → Skill/MCP; Jira/Figma/AWS/Database → MCP; 市场/UI/Office/SEO → Skill; Monitoring/Incident → Operations; 具体 LLM → Provider。

### 2.2 Extension 注册模型 (Agent = Skills + MCP + Runtime)

```
Agent (角色配置实例)
  ├── Skills     能力声明   (flutter-development / market-analysis / excel-report / seo)
  ├── MCP Tools  外部工具   (GitHub / Jira / Figma / AWS / Google Drive)
  └── Runtime    执行方式   (Hermes CLI / Codex CLI / Claude API / Local Model)
        └── Provider      LLM 来源 (OpenAI API / Anthropic / Local)
```

- **Skill**: 能力声明, 独立于 Agent (SkillRegistry 已有); Agent = 角色 + skill 集 + MCP 工具集 + runtime 偏好
- **MCP**: 外部工具接入 (当前 `mcp/` 目录占位, 规划中)
- **Runtime**: 执行器 (⑦ RuntimeAdapter 已抽象; 执行出口唯一)
- **Provider**: LLM 来源 (Phase 8 实现; Runtime 可对接多 Provider)
- **注册方式**: 新增任何能力不修改 Core —— OpenClaw skill / Codex plugin / MCP server / 第三方 Agent = **声明式注册 (JSON)**

### 2.3 Event 唯一事实源与 Namespace 扩展

确认: **未来所有层 (含 Extension 与 Human Layer) 都产生 Event**, 复用 Core Event Logger (SQLite append-only)。EventType 枚举纯增量扩展 (ADR-0002 路径: 加成员不改表):

```
现有:   task.* / workflow.* / agent.* / assignment.* / execution.* / runtime.* / validation.*
        recovery.* / dashboard.* / metrics.* / workspace.* / project.* / git.* / change.* / system.*
未来:   idea.* / research.* / prd.* / ui.* / deployment.* / incident.* / approval.*
```

### 2.4 Approval Gate 模型 (Human Layer 核心)

```
ApprovalGate = { phase, required: mandatory|recommended|optional, approver, evidence, status: pending|approved|denied }
```

| 节点 | 级别 | 说明 |
|:-----|:----:|:-----|
| Idea | optional | 想法收集可自动 |
| PRD | **mandatory** | 产品方向确认 |
| UI Design | **mandatory** | 视觉方向确认 |
| Architecture | recommended | 大重构必须, 小改动可选 |
| Code | optional | AI 自主, 人工抽查 |
| Deploy | **mandatory** | 发布授权 |
| Incident | optional | 告警自动, 重大事故人工 |

实现: Approval 为 Gate 原语 (pending→approved/denied→Event); CLI validate 退出码语义 + Web UI 审核台 (Phase 11) 等价, 走同一事件/状态机。

---

## 3. 各层详解

### ① Workspace Layer — 多项目工作区组织层

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 6A (`f1e3003`) + 6B (`d78f0ca`), ADR-0016/0017 |
| 包 | `factory-core/workspace/` |
| 职责 | 在 `project/` 之上组织多项目:工作区定义、托管项目目录解析、项目注册/移除;Dashboard/Metrics/Event 按 `--workspace` 聚合比较 |
| 关键 API | `WorkspaceManager.create/load/list/get/add/remove`;`WorkspaceStore`(原子写 `<root>/workspace.yaml`);`loader.discover_project_ids`(托管目录优先于 examples 自动发现);`config.load/dump` |
| 关键事件 | `workspace.created` / `workspace.viewed` / `project.registered` / `project.removed` / `workspace.dashboard.viewed` / `workspace.metrics.viewed` / `workspace.events.viewed`(读操作不内部发事件,由 CLI 命令层发) |
| CLI | `factory workspace init|show`;`factory dashboard/metrics/event logs --workspace` |
| 与上下层 | 上层:CLI。下层:复用 `project.loader` 解析项目(不复制解析逻辑);产出 ProjectDefinition 供 Dashboard/Metrics 项目隔离 |

**数据流**: `workspace init` → 写 `workspace.yaml` → `list_projects()` 发现托管目录 + examples 双源 → Dashboard Projects View / Metrics 比较表消费 → 各统计按 `project_id` 隔离 (task→project 映射, 孤儿记录不计入)。

### ② Project Layer — 示例/配置项目层 (只读)

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 5A (`1011fb6`), ADR-0013 |
| 包 | `factory-core/project/` |
| 职责 | 把 `examples/<project>/` 下的 YAML 配置文件 (project/agents/skills/workflows) 解析为 Pydantic 模型;是"真实项目 → Factory 注册物"的示例落地 |
| 关键 API | `loader.discover_projects()`(扫 `examples/*/project.yaml`);`load_project(dir, name) → ProjectConfig`(project.yaml 必填,其余可选 → 空列表;坏配置抛 `ProjectLoadError` 不静默);`default_examples_dir()`(支持 `FACTORY_EXAMPLES_DIR` 覆盖) |
| 关键事件 | `project.viewed`(CLI 命令层发, payload 含 project/lang/映射计数) |
| CLI | `factory project list|show <name>` (`--json`;exit 7 未找到 / 1 配置坏 / 2 用法) |
| 与上下层 | 上层:Workspace 层复用其 loader;下层:定义性数据 (agents/skills/workflows 映射) 是 ④⑤ 注册物的配置来源——但引擎注册须经引擎 API/CLI 显式注册 (config → registry 1:1 断言) |

### ③ Task Layer — 任务生命周期层

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 2 (`f4e96f3`), 后续各阶段增量扩展 |
| 包 | `factory-core/tasks/` |
| 职责 | 任务定义 (id/标题/角色/workflow 关联/项目归属)、状态追踪、JSON 持久化 (每任务一文件) |
| 关键 API | `TaskStore`(one-file-per-task, 原子写);`Task` Pydantic 模型(`Task.workflow` 默认 `"feature-delivery"`, `project` 默认 `"default"`);`_id_sane` 校验拒绝 `""`/`.`/`..`/`/`/`\` |
| 关键事件 | `task.created` / `task.updated` / `task.viewed`(3B+ 逐步扩展) |
| CLI | `factory task create|list|status|update` |
| 与上下层 | 上层:CLI。下层:被 ④ Workflow(按 `task.workflow` 选定义)、⑤ Agent(assign 到 task)、⑧ Validation、⑨ Recovery(按 task_id 回放)、⑩⑪ (按 task 聚合/关联) 引用——Task id 是全系统主键之一 |

### ④ Workflow Layer — 工作流定义与执行状态机

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 4A (`389d556`), ADR-0004;4B-1/4B-2 增加执行联动 |
| 包 | `factory-core/workflows/` |
| 职责 | 声明式流程定义 (Workflow = 有序 Step 列表)、运行记录 (WorkflowRun)、状态机推进 (CREATED→RUNNING→COMPLETED/FAILED, Step PENDING→RUNNING→COMPLETED/FAILED) |
| 关键 API | `WorkflowEngine.create_workflow/start_workflow/execute_step/complete_step/fail_workflow`;`WorkflowStore`(单文件双段 `{workflows, runs}`);内置定义 `feature-delivery` / `bug-fix` / `release` 等;`next_pending_step()` |
| 关键事件 | `workflow.created` / `workflow.started` / `workflow.step.started` / `workflow.step.completed` / `workflow.completed` / `workflow.failed` / `workflow.viewed` |
| CLI | `factory workflow list|add|run|status`(`run` 支持 `--auto` 全自动编排,见 ⑥) |
| 与上下层 | 上层:CLI 与 ⑥ Orchestration。下层:⑧ Validation 校验 L2 工作流规则;⑨ Recovery 回放重建 Workflow/Step 状态;⑪ changeflow 触发后创建 run |

**状态机要点**: 只有第一个非 COMPLETED 的 step 可启动;只有 RUNNING 的 step 可完成;终态拒绝一切(显式 `StepNotReadyError`);`start_workflow` 会立即自动启动第一步。

### ⑤ Agent Layer — Agent/Skill 注册与分派

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 3B (`1590c57`) agents/skill;Phase 4B-3 (`ec0ae1e`) assignment, ADR-0008 |
| 包 | `factory-core/agents/` + `factory-core/assignment/` |
| 职责 | Agent 身份 (id/role/skills/status/current_task)、Skill 能力目录、按角色/技能匹配候选、分配生命周期 (ASSIGNED→WORKING→COMPLETED/FAILED/RELEASED) |
| 关键 API | `AgentRegistry.add/find_by_skill/set_status/mark_working/mark_available`(状态原语**不发事件**,占用审计走 assignment 事件 payload);`AgentMatcher.candidates/best`(① role 精确 ② skills 命中 ≥1 必填技能 ③ AVAILABLE,按命中数降序+id 升序确定性排序);`AgentAllocator.assign/start/complete/fail/release`(validate-then-mutate,无半完成状态) |
| 关键事件 | `agent.registered` / `agent.viewed` / `skill.registered` / `skill.viewed` / `agent.assignment.viewed` / `assignment.created/started/completed/failed/released` |
| CLI | `factory agent add|list|assign|assignments|release`;`factory skill add|list` |
| 与上下层 | 上层:⑥ Orchestration (matcher.best → allocator)。下层:被 ④ Workflow Step 的 `required_role/required_skill` 约束;被 ⑨ Recovery 重置 (WORKING→AVAILABLE + assignment RELEASED) |

### ⑥ Execution Layer — 执行请求生命周期

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 4B-2 (`f06f73c`), ADR-0007;编排在 4C-2 (`a369da5`) |
| 包 | `factory-core/execution/` + `factory-core/orchestration/` |
| 职责 | 把"执行请求"从 PENDING 推进到终态:选 Runtime → 调 Adapter → 落结果;Orchestration 把 ④⑤⑥ 串成自动链路 (一次委派闭环) |
| 关键 API | `ExecutionDispatcher.dispatch`(resolve_runtime_id → get_adapter → adapter.execute → 校验 `result.request_id == request.id`);`ExecutionRunner.run`(生命周期 owner:PENDING→RUNNING+execution.started→dispatch→SUCCESS/FAILED+execution.completed/failed→save→best-effort 工作流联动 complete_step/fail_workflow);`ExecutionService.run/status`(组合根);`OrchestrationEngine`(`execute_workflow`: matcher.best → execute_step → allocator.assign(execution_id 回填) → allocator.start → service.run → 推进/失败) |
| 关键事件 | `execution.started` / `execution.completed` / `execution.failed` / `execution.viewed` / `orchestration.started` / `orchestration.step.started` / `orchestration.step.completed` / `orchestration.completed` / `orchestration.failed` |
| CLI | `factory execution list|run|status`;`factory workflow run --auto` |
| 与上下层 | 上层:CLI/⑪ changeflow executor (functools.partial(run_orchestration))。下层:⑦ Runtime。失败语义:resolve 阶段失败传播 (请求留 PENDING 可再试);dispatch 阶段失败转 FAILED (存储不留卡死 RUNNING);编排任一步失败 → Workflow FAILED + agent 释放,无半完成 |

### ⑦ Runtime Layer — Runtime 抽象与实现

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 4B-1 (`4b0f36a`) 接口/注册表;4C-1 (`8a0f52e`) Hermes Adapter;5A.1 (`77abf9f`) Catalog, ADR-0006/0009/0014 |
| 包 | `factory-core/runtime/` + `factory-core/runtimes/` |
| 职责 | 统一执行出口:Adapter 协议 + 身份注册表 + 具体实现 (echo/mock/hermes) + 能力目录 (catalog: 描述"有什么",不执行) |
| 关键 API | `RuntimeAdapter.execute(request) → ExecutionResult`(ABC 单方法);`RuntimeRegistry.register/get/list/remove/resolve_runtime_id`(显式 id 必须已注册否则 `RuntimeNotFoundError`,无 id 则选第一个 AVAILABLE);`RuntimeStore`(三段式 `runtimes.json`: runtimes/executions/results, results 按 request_id 1:1);`HermesRuntimeAdapter`(subprocess hermes CLI, `FACTORY_HERMES_CMD`/`TIMEOUT` env, 构造参数 > env > 默认, 五类失败→FAILED 永不抛);`RuntimeCatalog` + `CatalogStore`(`catalog.json` 与实例文件同目录隔离, 内置定义不可覆盖) |
| 关键事件 | `runtime.registered` / `runtime.viewed` / `runtime.catalog.registered/removed/viewed` |
| CLI | `factory runtime add|list|test`;`factory runtime catalog list|show <id>` |
| 与上下层 | 上层:⑥ Execution(唯一调用方)。无下层 (执行出口指向外部进程)。分层:Catalog=能力描述 ≠ Registry=实例可用 ≠ Runtime=执行器,永不合并 |

### ⑧ Validation Layer — 三层验证引擎

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 3A (`b213a14`) L1/L2/L3;6D (`6e965f1`) 注入式 L4 Change, ADR-0019 |
| 包 | `factory-core/validation/` |
| 职责 | 独立于 Agent 自报告的验证:L1 Factory(工厂内部一致性)、L2 Workflow(工作流规则)、L3 Artifact(产物证据);6D 起可选注入 L4 Change(变更一致性) |
| 关键 API | `ValidationEngine.validate(...)`(可选 ctor 参数 `change_service=None`,缺省 checks==6;硬编码规则循环后条件追加 L4);`rules.rule_change`(延迟 import `change.analyzer` 破环,复用 l4_checks/l4_verdict 纯函数);`ValidationReport`(`to_text()`/`by_level` 只渲染 L1/L2/L3,但 `result` 计入 L4:任一 FAIL→总 FAIL);`RULE_NAMES`/`REASON_BY_RULE` |
| 关键事件 | `validation.started` / `validation.rule.completed` / `validation.completed` / `validation.failed`(rule.completed 的 result 列被 Metrics/Dashboard 消费) |
| CLI | `factory validate <task_id>` (exit 3 验证失败 / 7 未找到 / 2 用法) |
| 与上下层 | 上层:CLI(人工验收)、Dashboard/Metrics(只读聚合验证结论)。下层:读取 ③④⑤ 状态与 ⑪ change 证据;不修改任何状态 (只读铁律) |

### ⑨ Recovery Layer — 断点续跑与事件回放

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 4C-3 (`454f10d`), ADR-0011 |
| 包 | `factory-core/recovery/` |
| 职责 | 任务级 checkpoint 快照;从事件库回放重建 Workflow/Step/Assignment/Execution/Agent 状态;四种恢复场景;幂等 |
| 关键 API | `CheckpointStore`(`.factory/checkpoints/<task_id>.json`, 路径穿越防护, 原子写);`EventReplay.from_store(task_id)`(`_HANDLERS` 分发表, 未知类型忽略, 终态不回退);`RecoveryService.checkpoint(task_id)`(快照+事件锚点原子落盘);`recover(task_id)`(回放→对比→纠正→RecoveryResult);`resume_ok` 语义:四场景 RUNNING workflow→继续当前步 / RUNNING execution→PENDING 可重试 / WORKING agent→AVAILABLE+assignment RELEASED / 已完成→拒绝) |
| 关键事件 | `recovery.started` / `recovery.completed` / `recovery.failed`(纠正走持久化原语,不再发业务事件,审计由 recovery.* 承担) |
| CLI | `factory checkpoint create|list`;`factory recover TASK_ID` (exit 7 未找到 / 1 内部 / 2 用法) |
| 与上下层 | 上层:CLI。下层:只读 ⑩ 事件库 (EventStore.by_task) + 各 store 的持久化原语;被 ④⑤⑥ 的状态作为重建目标 |

### ⑩ Observation Layer — 事件库 + Dashboard + Metrics (只读)

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 1 (`ceb5f40`) 事件库;4C-4 (`77ea59e`) Dashboard;5B (`c726392`) Metrics;6B (`d78f0ca`) workspace 聚合, ADR-0012/0015/0017 |
| 包 | `factory-core/events/` + `factory-core/dashboard/` + `factory-core/metrics/` |
| 职责 | append-only 事件库 = 唯一事实源;只读快照渲染 (Rich, 无 web);六域指标聚合;workspace 维度比较 |
| 关键 API | `EventLogger.record`(所有事件唯一入口,领域代码禁止直写 EventStore);`EventStore`(SQLite append-only, `by_task`/投影/回放);`DashboardCollector`(DI 六 store, 只读, `include_git`/`include_changeflow`/`include_workspace` 缺省关)+ `FactorySnapshot` + `DashboardRenderer`(VIEWS 16 个视图, `--json` 同源);`MetricsCollector`(复用 event/task/agent/workflow/runtime store, project_id 隔离)+ `FactoryMetrics` 六域 (tasks/executions/agents/workflows/validation/failures) + `Calculators` 纯函数 + `workspace.py` (agent 利用率/runtime 使用率/项目比较) |
| 关键事件 | `system.status_viewed` / `system.logs_viewed` / `dashboard.viewed` / `metrics.viewed` / `*.viewed` 族 |
| CLI | `factory status`;`factory event logs`;`factory dashboard [--view ...] [--limit N] [--project P] [--workspace] [--json]`;`factory metrics [--project P] [--workspace] [--json]` |
| 与上下层 | 上层:CLI。下层:读取全部领域 store (只读方法);Dashboard/Metrics 输出必须同源 (复用同一 MetricsCollector, 防止两出口数字打架)。16 视图: overview/tasks/agents/workflows/executions/recovery + catalog + metrics + projects + workspace 组(4) + git + change + changeflow |

**只读双层保证**: collector 只调 store 读接口 + 审计事件由 CLI 命令层发——两层任一缺失即破坏"指标查询不改状态"铁律;测试用字节级快照 (过滤 SQLite WAL 侧文件) 断言。

### ⑪ Git Intelligence Layer — Git 审计 + 变更智能 + 变更驱动工作流

| 项 | 内容 |
|---|---|
| 阶段 / 提交 | Phase 6C (`974e371`) git;6D (`6e965f1`) change;6E (`2d596c7`) changeflow, ADR-0018/0019/0020 |
| 包 | `factory-core/git/` + `factory-core/change/` + `factory-core/changeflow/` |
| 职责 | (**Extension 区**, 可选接入) ① Git 只读审计 (status/diff/commits, 零仓库写命令); ② 变更智能:commit 消息解析 (MP-XXX→task_id)、路径级变更分析 (无 LLM)、L4 变更验证、task↔git 自动关联; ③ 变更驱动工作流:ChangeTrigger 规则 → evaluate → 创建 workflow run → 执行 |
| 关键 API | `GitClient`(subprocess 只读, **失败安全永不抛**: FileNotFoundError→"git command not found"/超时→"git timed out";子进程 env 强制 `LC_ALL=C`+`LANG=C` 每次现算);`GitService.get_status/get_changes/get_commits/bind_task_change`;`GitChangeStore`(`git/changes.json` 追加式, 损坏读→`[]` 失败安全);`CommitLinker`(三来源: message > execution context > branch, `parse_task_id`/`normalize_task_id`);`ChangeAnalyzer`(模块链推断 + `l4_checks`/`l4_verdict` 纯函数);`ChangeService`(`snapshots.json`);`ChangeWorkflowEngine.evaluate(task_id, trigger=None, execute=None)`(execute 缺省=按 executor 装配判定;PASS/SKIP→0, FAIL→3, ERROR→1;`change workflows` 列触发链) |
| 关键事件 | `git.status_viewed` / `git.diff_viewed` / `git.commits_viewed` / `git.task.bound` / `git.commit.linked` / `change.analyzed` / `change.validation.completed` / `change.trigger.created` / `change.trigger.evaluated` / `change.workflow.started` / `change.workflow.completed` / `change.viewed` |
| CLI | `factory git status|diff|commits`;`factory change commits|analyze|validate|triggers register|list|evaluate|workflows` |
| 与上下层 | 上层:CLI + ⑩ Dashboard (git/change/changeflow 三视图)。下层:只读 ③ Task (关联引用) + ⑧ Validation (L4 注入) + ④ Workflow (触发 run)。L4 契约:任一 FAIL→总 FAIL;clean 仓库无证据→SKIP 不误报;`analyze()` 的 files 来自**已绑定变更** (`get_changes(task_id)`),非裸工作区 diff |

---

## 4. 端到端数据流 (一条完整链路)

```
factory task create MP-BUG-001                → ③ Task (task.created)
factory workflow add --id release             → ④ Workflow (workflow.created)
factory change triggers register ...          → ⑪ changeflow (trigger.created)
git commit "MP-BUG-001 fix ..."               → (外部 git 只读被审计)
factory change validate MP-BUG-001            → ⑪ analyze + ⑧ L4 (PASS/FAIL/SKIP)
factory change evaluate MP-BUG-001            → ⑪ evaluate → ④ workflow run 创建
factory workflow run --auto ...               → ⑥ Orchestration:
                                                ⑤ matcher.best → ④ execute_step
                                                → ⑥ allocator.assign → runner.run
                                                → ⑦ RuntimeRegistry.resolve → Adapter.execute
                                                → (hermes/echo 子进程执行)
                                                → 结果写 ⑦ RuntimeStore → ④ complete_step
factory validate MP-BUG-001                   → ⑧ 三层验证 (独立于自报告)
factory checkpoint create MP-BUG-001          → ⑨ 快照 (recovery.completed)
factory recover MP-BUG-001                    → ⑨ 回放重建 → resume_ok
factory dashboard --view changeflow           → ⑩ 只读渲染 (16 视图之一)
factory metrics --workspace                   → ⑩ 六域指标 + 项目比较
factory git status --project markpad          → ⑪ 只读 Git 审计
```

事件流方向与命令调用相反:任何写操作 → `EventLogger.record` → SQLite 事件库 (⑩),供 Dashboard/Metrics/Recovery/Git 关联消费。

---

## 5. 阶段 → 层 映射表

| Phase | 名称 | 层 | 测试基线 |
|:--:|---|:--:|:--:|
| 1 | Event Logger MVP | ⑩ | 69 |
| 2 | Factory Control CLI | ③ + CLI | 141 |
| 3A | Validation Engine | ⑧ | 223 |
| 3B | Agent + Skill Registry | ⑤ | 335 |
| 4A | Workflow Engine | ④ | 449 |
| 4B-1 | Runtime Adapter Interface | ⑦ | 584 |
| 4B-2 | Execution Dispatch Layer | ⑥ | 684 |
| 4B-3 | Agent Assignment Layer | ⑤ | 824 |
| 4C-1 | Hermes Runtime Adapter | ⑦ | 908 |
| 4C-2 | Execution Orchestration Flow | ⑥ | 981 |
| 4C-3 | Checkpoint Recovery | ⑨ | 1103 |
| 4C-4 | Dashboard MVP | ⑩ | 1203 |
| 5A | Production Example Layer | ② | 1237 |
| 5A.1 | Runtime Catalog | ⑦ | 1335 |
| 5B | Metrics Intelligence Layer | ⑩ | 1395 |
| 6A | Multi Project Workspace Layer | ① | 1498 |
| 6B | Workspace Operations Dashboard | ① + ⑩ | 1616 |
| 6C | Git Integration Layer | ⑪ | 1813 |
| 6D | Change Intelligence Layer | ⑪ + ⑧ | 2015 |
| 6E | Change Driven Workflow Layer | ⑪ + ④ | **2159** |

> 区归属: Phase 1–6E 全部阶段中, ①–⑩ 层相关 = **Core 区**; Phase 6C/6D/6E (Git 集成) = **Extension 区** (可选能力, Core 零依赖)。
> 后续演进方向 (Phase 7–11, 冻结确认: Phase 8 与 Phase 11 可并行) 见 [roadmap.md](./roadmap.md); 三区边界与 Extension 注册模型见上文 §2, 冻结结论见 [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md)。
