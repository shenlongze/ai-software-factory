# AI Software Factory — 全系统架构审计报告 (Phase 12A-1)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 与当前代码一致 (41 commits · 4090 tests · 137 EventType)
> 审计范围: 四层架构 (Core / Extension / Intelligence / Human Console) · 模块职责 · 数据流 ·
> Event 流 · Artifact 流 · Decision 流 · Experience 流 · Core 冻结与 Extension 独立性确认
> 关联文档: [architecture-overview.md](./architecture-overview.md)(三区 11 层总览) ·
> [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md)(冻结报告) ·
> [core-boundary.md](./core-boundary.md)(Core 边界) · [extension-model.md](./extension-model.md)(扩展模型) ·
> [capability-architecture.md](./capability-architecture.md)(能力架构约束) ·
> [intelligence-layer-model.md](./intelligence-layer-model.md) · [decision-intelligence-model.md](./decision-intelligence-model.md) ·
> [recommendation-engine-model.md](./recommendation-engine-model.md) · [experience-learning-model.md](./experience-learning-model.md) ·
> [human-console-model.md](./human-console-model.md) · [human-console-ui-model.md](./human-console-ui-model.md)

**与代码一致性验证 (本报告所有事实均实测自仓库)**:

| 项 | 实测值 |
|:---|:-------|
| git 提交数 | 41 (`git log --oneline \| wc -l`) |
| 测试数 | 4090 (`pytest --collect-only -q`) |
| EventType 成员数 | 137 (26 个 namespace, `events/models.py` 枚举实测) |
| CLI 顶级命令组 | 23 (argparse 子解析器实测), 叶子命令 77 |
| 冻结边界 | Core 模块零领域 import (源码级扫描) + Removal Isolation 测试通过 |

---

## 1. 四层架构总图

系统自下而上分四层: **Core (通用原语, 冻结)** → **Extension (领域能力, 声明式注册)** →
**Intelligence (认知层, 只分析不执行)** → **Human Console (人类控制台, 只读 + 审批)**。
依赖单向向下: 上层调用下层公开 API, 禁止反向依赖与循环 import; 跨包引用一律函数内延迟 import。

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ▓ Human Console (L4 · factory-console/) — 人类控制台 (Phase 11A/11B, ADR-0034/0035) │
│     ConsoleService 七域只读聚合 (active_projects/pending_approvals/running_agents/   │
│     recent_decisions/cost_summary/experience_summary/activity)                       │
│     + api/ 7 只读路由 (projects/lifecycle/approvals/decisions/intelligence/providers)│
│     + web/ FastAPI 只读 GET 薄层 + React+TS UI (7 页面, Simple/Expert 切换)          │
│     零写 API · 不自动执行 · 不自动批准 · 审批动作走 product ApprovalGate 状态机       │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     │ 只读查询 (Event/Artifact/Decision/Recommendation/Experience)
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ▓ Intelligence (L3 · factory-core/intelligence/) — 认知层 (Phase 10A, ADR-0030..33)│
│     DecisionIntelligence (决策: 分析→选项评分→推荐→风险)                             │
│     RecommendationEngine (推荐: 四因素加权 0.35/0.30/0.20/0.15 + 解释 + 风险)        │
│     ExperienceAnalyzer (经验: 半衰期衰减 + 正负聚合) · TaskEvaluator (任务评估)       │
│     铁律: 只分析+推荐+解释, 不自动执行; 零 imports product/providers/runtime        │
│     (Removal Isolation); 高风险输出经 duck-typed ApprovalGate 提交人工审批            │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     │ 读取 Core 事件/状态 (只读) · 推荐结果由人/编排采纳
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ▓ Extension (L2 · 领域能力, 声明式注册, Core 零感知)                                 │
│     git/       Git 只读审计 (status/diff/commits, 零仓库写)                          │
│     change/    变更智能 (commit 解析→task 关联, 无 LLM, L4 验证)                     │
│     changeflow/ 变更驱动工作流 (ChangeTrigger 规则→evaluate→触发 workflow run)       │
│     providers/ LLM Provider 抽象 (注册表/选择器/用量/成本/能力目录, 不绑定任何一家)  │
│     product/   产品智能 (Idea→Artifact 阶段链→ApprovalGate 审批→Workflow 联动)      │
│     understanding/ 项目理解 (任意项目路径 → ProjectUnderstandingReport, 只读分析)    │
│     接入方式: Skill/MCP/Runtime/Provider 声明式 JSON 注册, 零 Core 代码改动          │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     │ 执行出口 (唯一) — RuntimeAdapter
                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ▓ Core (L1 · 通用原语, 2026-08 冻结, 不修改行为)                                    │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐ │
│  │ ①workspace│ ②project│ ③tasks │ ④workflows│⑤agents  │⑥execution│⑦runtime │ ⑧validation│
│  │ 工作区组织│ 项目配置│ 任务状态│ 流程状态机│Agent/分派│ 执行生命周期│ 执行抽象│ 三层验证 │
│  ├─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┼─────────┤
│  │ ⑨recovery│ ⑩events │ ⑩dashboard│ ⑩metrics│⑪orchestration│ assignment│ runtimes │   cli   │
│  │ 断点续跑 │ 事件库  │ 只读快照│ 六域指标│ 自动编排 │ 分配状态机│ Runtime实现│ 23 命令组│
│  └─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘ │
│  8 项原语: 状态管理/生命周期/调度/执行抽象/事件审计/恢复/观测/组织 — 零领域依赖      │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**核心链路** (审计主线, 与代码一致):

```
Workspace → Project → Task → Workflow → Assignment → Execution → Runtime → Provider
   → Validation → Recovery → Dashboard → Metrics → Git → Change → Changeflow
   → Understanding → Product → Intelligence → Console
```

**分层纪律 (硬规则)**:

1. 依赖单向向下, 禁止反向依赖与循环 import (跨包延迟 import, 如 `validation.rules → change.analyzer`)。
2. 写操作只发生在领域层; Validation/Observation/Git/Intelligence/Console 只读。
3. 所有状态变更必须发事件 (ADR-0002): 领域写方法返回 `(obj, Event | None)` → `EventLogger.record` → SQLite append-only 事件库; 读命令也发 `.viewed` 审计事件。
4. 执行出口唯一: 启动 Agent / 跑命令只能走 RuntimeAdapter (⑦); Git 只读铁律 (零仓库写)。
5. JSON store 原子写 (tmp + `os.replace`), 损坏抛 `Corrupt*StoreError` 不静默 (唯一例外: `git/changes.json` 失败安全 `[]`)。
6. 事件库 SQLite 只 INSERT 永不 UPDATE/DELETE, `seq` 自增回放锚点; EventType 枚举纯增量扩展 (ADR-0002 路径: 加成员不改表)。

**数据空间布局** (`.factory/`, 每扩展独立目录互不修改):

```
.factory/
├── events.db                     # SQLite append-only 事件库 (唯一事实源)
├── tasks/  workflows/  agents/   # Core 状态 (每任务一文件 / 单文件双段 / 注册表)
├── runtimes.json                 # Runtime 实例三段式: runtimes/executions/results
├── checkpoints/<task_id>.json    # 恢复快照
├── git/changes.json  snapshots.json  # Git 变更审计 (失败安全 [])
├── providers/                    # Provider 定义 + 用量
├── product/                      # Idea/Artifact/Approval/Lifecycle/Workflow
├── intelligence/                 # decisions/ recommendations/ experience 记录
└── understanding/                # 项目理解报告
```

---

## 2. 模块职责清单

### 2.1 Core 区 — 通用原语 (冻结, 零领域依赖)

| 模块 | 一句话职责 | 关键 API |
|:-----|:-----------|:---------|
| `workspace/` | 多项目工作区组织: workspace.yaml 管理 + 托管目录发现 + 跨项目聚合 | `WorkspaceManager.create/load/list/get/add/remove`; `WorkspaceStore`(原子写); `loader.discover_project_ids`(托管目录优先于 examples); `config.load/dump` |
| `project/` | 把 `examples/<project>/` 的 YAML 配置解析为 Pydantic 模型 (只读) | `loader.discover_projects()`; `load_project(dir, name) → ProjectConfig`(坏配置抛 `ProjectLoadError`); `default_examples_dir()`(支持 `FACTORY_EXAMPLES_DIR`) |
| `tasks/` | 任务定义 (id/标题/角色/workflow/项目归属) + 状态 + 每任务一文件 JSON 持久化 | `TaskStore`; `Task` 模型(`workflow` 默认 `"feature-delivery"`, `project` 默认 `"default"`); `_id_sane` 校验 (`""`/`.`/`..`/`/`/`\\` 拒绝) |
| `workflows/` | 声明式工作流定义 + 运行记录 + 状态机 (Workflow/Step) | `WorkflowEngine.create_workflow/start_workflow/execute_step/complete_step/fail_workflow`; `WorkflowStore`(单文件双段 `{workflows, runs}`); 内置定义 `feature-delivery`/`bug-fix`/`release`; `next_pending_step()` |
| `agents/` | Agent 身份与 Skill 能力目录注册 | `AgentRegistry.add/find_by_skill/set_status/mark_working/mark_available`(状态原语不发事件, 占用审计走 assignment 事件); `SkillRegistry` |
| `assignment/` | Agent 匹配与分配生命周期 (ASSIGNED→WORKING→COMPLETED/FAILED/RELEASED) | `AgentMatcher.candidates/best`(① role 精确 ② skills 命中 ≥1 必填 ③ AVAILABLE, 命中数降序+id 升序确定性排序); `AgentAllocator.assign/start/complete/fail/release`(validate-then-mutate, 无半完成) |
| `execution/` | 执行请求 PENDING→终态: 选 Runtime → 调 Adapter → 落结果 | `ExecutionDispatcher.dispatch`(resolve_runtime_id → get_adapter → execute → 校验 `result.request_id == request.id`); `ExecutionRunner.run`(生命周期 owner: PENDING→RUNNING+started→dispatch→SUCCESS/FAILED+completed/failed→save→best-effort 工作流联动); `ExecutionService.run/status`(组合根) |
| `orchestration/` | 把 Workflow+Agent+Execution 串成一次委派闭环 (自动链路) | `OrchestrationEngine.execute_workflow`: matcher.best → execute_step → allocator.assign(execution_id 回填) → allocator.start → service.run → 推进/失败; 任一步失败 → Workflow FAILED + agent 释放 |
| `runtime/` | 统一执行出口抽象: Adapter 协议 + 身份注册表 + 能力目录 | `RuntimeAdapter.execute(request) → ExecutionResult`(ABC 单方法); `RuntimeRegistry.register/get/list/remove/resolve_runtime_id`; `RuntimeStore`(runtimes.json 三段式, results 按 request_id 1:1); `HermesRuntimeAdapter`(subprocess, `FACTORY_HERMES_CMD`/`TIMEOUT`, 五类失败→FAILED 永不抛); `RuntimeCatalog` + `CatalogStore`(内置定义不可覆盖) |
| `runtimes/` | RuntimeAdapter 具体实现 (echo/mock/hermes) | `EchoRuntimeAdapter` / `MockRuntimeAdapter` / `HermesRuntimeAdapter`(均实现 `execute`) |
| `validation/` | 三层验证引擎: L1 Factory / L2 Workflow / L3 Artifact (+ 可选注入 L4 Change) | `ValidationEngine.validate`(可选 ctor `change_service=None`, 缺省 checks==6); `rules.rule_change`(延迟 import `change.analyzer` 破环); `ValidationReport.to_text()/by_level`; `RULE_NAMES`/`REASON_BY_RULE` |
| `recovery/` | 任务级 checkpoint 快照 + 事件回放重建状态 + 四场景恢复 | `CheckpointStore`(`.factory/checkpoints/<task_id>.json`, 路径穿越防护); `EventReplay.from_store(task_id)`(`_HANDLERS` 分发表, 未知类型忽略, 终态不回退); `RecoveryService.checkpoint/recover`; `resume_ok` 四场景 (RUNNING workflow→继续 / RUNNING execution→PENDING 可重试 / WORKING agent→AVAILABLE+RELEASED / 已完成→拒绝) |
| `events/` | SQLite append-only 事件库 = 唯一事实源 | `EventLogger.record`(所有事件唯一入口, 领域代码禁止直写 store); `EventStore`(by_task/投影/回放); `EventType` 137 成员; `Event` Pydantic 模型 |
| `dashboard/` | 只读快照渲染 (Rich, 无 web) — 16 视图 | `DashboardCollector`(DI 六 store, 只读, `include_git`/`include_changeflow`/`include_workspace` 缺省关) + `FactorySnapshot` + `DashboardRenderer`(`--json` 同源) |
| `metrics/` | 六域指标聚合 (tasks/executions/agents/workflows/validation/failures) + 项目隔离 | `MetricsCollector`(复用 event/task/agent/workflow/runtime store, project_id 隔离) + `FactoryMetrics` + `Calculators` 纯函数 + `workspace.py`(agent 利用率/runtime 使用率/项目比较) |
| `cli/` | 命令入口: 参数解析 → 领域公开 API → 人类可读输出, 每次命令发审计事件 | `cli/main.py build_parser()`(23 顶级命令组 / 77 叶子命令); `cli/commands.py`(全部命令实现, 领域包一律延迟导入) |

> 注: `dashboard/models.py` 引用 `git.models` 类型 — 仅用于 git/change/changeflow 三个可选视图的渲染类型 (collector 的 `include_git` 缺省关, 属只读观测扩展点, 不构成 Core→Extension 业务依赖); `cli/commands.py` 是组合根, 对领域包只允许函数内延迟导入 (有测试断言)。

### 2.2 Extension 区 — 领域能力 (删除任一模块系统仍运行)

| 模块 | 一句话职责 | 关键 API |
|:-----|:-----------|:---------|
| `git/` | Git 只读审计: status/diff/commits, 零仓库写命令 | `GitClient`(subprocess 只读, **失败安全永不抛**: FileNotFoundError→"git command not found"/超时→"git timed out"; 子进程 env 强制 `LC_ALL=C`); `GitService.get_status/get_changes/get_commits/bind_task_change`; `GitChangeStore`(`git/changes.json` 追加式, 损坏读→`[]`) |
| `change/` | 变更智能: commit 消息解析 (MP-XXX→task_id)、路径级分析 (无 LLM)、L4 验证 | `CommitLinker`(三来源: message > execution context > branch, `parse_task_id`/`normalize_task_id`); `ChangeAnalyzer`(模块链推断 + `l4_checks`/`l4_verdict` 纯函数); `ChangeService`(`snapshots.json`) |
| `changeflow/` | 变更驱动工作流: ChangeTrigger 规则 → evaluate → 创建 workflow run | `ChangeWorkflowEngine.evaluate(task_id, trigger=None, execute=None)`(PASS/SKIP→0, FAIL→3, ERROR→1); `change workflows` 列触发链 |
| `providers/` | LLM Provider 抽象: 定义/注册表/选择器/用量/成本/能力目录/反馈, 不绑定具体模型 | `ProviderRegistry.register/remove/set_default/get/list/find_by_capability/count/ids/default/resolve`; `ProviderSelector.resolve`(配置层 → 定义解析); `CostAwareSelector.recommend`(能力/成本/用量多因素); `ProviderUsage` + `UsageStore`(`provider.usage.recorded`); `capability.py`/`costs.py`/`feedback.py`/`definitions.py`/`adapters/` |
| `product/` | 产品智能: Idea → Artifact 阶段链 → ApprovalGate 审批 → ProductWorkflow 联动 | `ProductService.create_idea/create_artifact/get_artifact/get_or_create_gate/request_approval/decide_approval/approval_queue/approval_history/start_workflow/workflow_resume/revise_artifact/artifact_version_history/create_decision_artifact/get_decision_chain`; `Artifact` 抽象; `ProductStore`(`.factory/product/` 独立数据空间) |
| `understanding/` | 项目理解: 任意项目路径 → ProjectUnderstandingReport (阶段/技术栈/文档/风险/建议) | `UnderstandingService.analyze(path) → ProjectUnderstandingReport`(校验路径 → 发 started → 分析 → completed/failed); `analyzers/artifact_detector.py`(`ArtifactDetector.detect` + `scan_extensions` + `scan_manifests`)、`document_analyzer.py`、`project_analyzer.py` |

### 2.3 Intelligence 区 — 认知层 (只分析 + 推荐 + 解释, 不执行)

| 模块 | 一句话职责 | 关键 API |
|:-----|:-----------|:---------|
| `intelligence/models.py` | 认知层数据模型: Decision/Recommendation/ExperienceRecord/Evidence | `Decision`(id/decision_type/subject_id/options/recommendation/confidence/risk/evidence/status/approval_request_id); `Recommendation`(target_type/target_id/score/reasoning/evidence/confidence/risk); `ExperienceRecord`(domain 五域/result/score/confidence/freshness/usage_count); `Evidence`(六来源 + `lineage_ref()` = `"{source_type}:{source_id}"`) |
| `intelligence/decision.py` | 决策引擎: 分析→选项评分→推荐→风险→Decision Artifact | `DecisionIntelligence.analyze/evaluate_options/recommend/assess_risk/build_decision/bind_approval/decide/result`; 无证据 → `NoEvidenceError` 拒绝 (零事件); 权重 capability 0.40/cost 0.25/performance 0.20/experience 0.15 (归一化, 缺失因素中性 0.5) |
| `intelligence/recommend.py` | 推荐引擎: provider/agent/skill/workflow 四类执行资源统一评分 + 解释 + 风险 | `RecommendationEngine.recommend(context) → RecommendationResult`(capability 0.35/performance 0.30/cost 0.20/experience 0.15, 权重配置化; `quality_target` 过滤, 全被过滤 → 无推荐 + risk=high + requires_approval); `to_decision`; `ReasoningItem(factor, direction, text)` 机读解释 |
| `intelligence/experience.py` | 经验层: 记录事实 + 只读分析 (半衰期衰减/正负聚合) | `ExperienceAnalyzer.records/aggregate/analyze/record_experience`; `decay_freshness(age, half_life) = 0.5 ** (age/half_life)`(缺省 30 天); `aggregate = clamp01(mean(sign × score×confidence×freshness))`, sign = +1 成功 / −1 失败 |
| `intelligence/evaluate.py` | 任务评估: 按 task_type+capability 过滤 → 分组 → 正负聚合 → 推荐每类封顶 5 | `TaskEvaluator.evaluate(requirement) → TaskEvaluation`(推荐 agent/provider/skill, 有效分 ≥ 0.5 中性门槛, Confidence + Reasons + Risks) |
| `intelligence/store.py` | 认知层独立数据空间 (`.factory/intelligence/`) | `DecisionStore`(list_by_subject) / `RecommendationStore`(list_by_target) / `ExperienceStore`; 基类 `_JsonRecordStore`(原子写, 损坏抛 `CorruptIntelligenceStoreError`) |

### 2.4 Human Console 区 — 人类控制台 (只读 + 审批, 无第二条执行路径)

| 模块 | 一句话职责 | 关键 API |
|:-----|:-----------|:---------|
| `factory-console/service.py` | ConsoleService 七域只读聚合 (项目/审批/Agent/决策/成本/经验/活动), 按 `idea.context["project"]` 项目隔离 | `dashboard()`; `list_projects()`; `project_lifecycle(project_id)`; `list_approvals()`; `get_decision(decision_id)`; `list_recent_decisions()`; `list_recommendations()`; `list_experience()`; `list_providers()` — 全部只读, 零写 API |
| `factory-console/api/` | 7 个只读路由: projects/lifecycle/approvals/decisions/intelligence/providers | 路由函数为纯函数返回 Pydantic 响应模型, **无 FastAPI/Web 依赖**; 11B 的 fastapi_adapter 只做 HTTP 绑定 (只读 GET) |
| `factory-console/web/` | 11B Web UI: FastAPI 只读薄层 + React+TS 前端 | 7 页面 (Projects/Lifecycle/Approvals/Decisions/Recommendations/Experience/Providers), Simple/Expert 切换, 只读 api client (92 Vitest) |
| `factory-console/models.py` / `events.py` | 响应模型 + 审计事件 | `console.viewed` / `console.dashboard.viewed` / `console.approval.opened` (仅 3 个 console.* 事件) |

---

## 3. 数据流: Task → Execution → Result → Event 主链路

```
factory task create MP-BUG-001                → ③ TaskStore 落盘 (每任务一文件, 原子写)
                                                 → EventLogger.record(task.created) → events.db
factory workflow run --auto --task MP-BUG-001 → ⑥ OrchestrationEngine.execute_workflow:
  ① AgentMatcher.best (role 精确 → skills ≥1 命中 → AVAILABLE, 确定性排序)   [orchestration.started]
  ② WorkflowEngine.execute_step (Step PENDING→RUNNING)                       [workflow.step.started]
  ③ AgentAllocator.assign (execution_id 回填) → allocator.start               [assignment.created/started]
  ④ ExecutionService.run → ExecutionRunner:
       PENDING → RUNNING                                                      [execution.created/started]
       ExecutionDispatcher.dispatch:
         RuntimeRegistry.resolve_runtime_id (显式 id 必须已注册 / 无 id 选第一个 AVAILABLE)
         → RuntimeAdapter.execute(request)                                    [runtime.* 已注册身份]
           · HermesRuntimeAdapter: subprocess hermes CLI (FACTORY_HERMES_CMD/TIMEOUT,
             构造参数 > env > 默认; 五类失败 → FAILED 永不抛)
           · EchoRuntimeAdapter / MockRuntimeAdapter: 测试/演示执行
       → ExecutionResult 校验 result.request_id == request.id                 [execution.completed/failed]
       → RuntimeStore 落 results (按 request_id 1:1)
  ⑤ best-effort 工作流联动: complete_step / fail_workflow                    [workflow.step.completed /
                                                                               workflow.completed|failed]
  ⑥ 事件回流: 一切写操作 → EventLogger.record → SQLite events.db (append-only, seq 自增)
  ⑦ 消费方 (只读):
       Dashboard/Metrics   → 事件/状态聚合 (16 视图 / 六域指标, 同源复用 MetricsCollector)
       Recovery            → EventReplay 回放重建 Workflow/Step/Assignment/Execution/Agent 状态
       Git/Change          → CommitLinker 把 commit 关联回 task_id (git.task.bound / git.commit.linked)
       Validation          → 三层验证 L1/L2/L3 (+ 可选 L4 change 证据)
       Intelligence/Console→ 只读消费事件与 Artifact 做分析/推荐/展示
```

**失败语义 (与代码一致)**: resolve 阶段失败传播 (请求留 PENDING 可再试); dispatch 阶段失败转 FAILED (存储不留卡死 RUNNING); 编排任一步失败 → Workflow FAILED + agent 释放 (assignment.failed/released), 无半完成状态。

---

## 4. Event 流: 137 事件 · 26 namespace

**实测枚举清单** (`events/models.py`, `EventType` 137 成员)。任何状态变更都发事件; 读操作由 CLI 命令层发 `.viewed` 审计事件; 事件方向与命令调用相反 (写 → 事件库 → 只读消费)。

| namespace | 数量 | 事件 |
|:----------|:----:|:-----|
| `task.*` | 6 | created / updated / viewed / start / fail / end |
| `workflow.*` | 7 | created / started / step.started / step.completed / completed / failed / viewed |
| `agent.*` (含 `assignment.*`) | 10 | registered / updated / viewed / released / removed / assignment.created / assignment.started / assignment.completed / assignment.failed / assignment.viewed |
| `skill.*` | 3 | registered / removed / viewed |
| `execution.*` | 5 | created / started / completed / failed / viewed |
| `orchestration.*` | 5 | started / step.started / step.completed / completed / failed |
| `runtime.*` | 6 | registered / removed / viewed / catalog.registered / catalog.removed / catalog.viewed |
| `validation.*` | 5 | started / rule.started / rule.completed / completed / failed |
| `recovery.*` | 3 | started / completed / failed |
| `checkpoint` | 1 | checkpoint |
| `dashboard.*` | 1 | dashboard.viewed |
| `metrics.*` | 1 | metrics.viewed |
| `workspace.*` | 5 | created / viewed / dashboard.viewed / metrics.viewed / events.viewed |
| `project.*` | 3 | registered / removed / viewed |
| `system.*` | 3 | init / status_viewed / logs_viewed |
| `session.*` | 1 | session.close |
| `tool.*` | 1 | tool.call |
| `git.*` | 5 | status.viewed / commit.viewed / commit.linked / task.bound / change.detected |
| `change.*` | 7 | analyzed / validation.completed / trigger.created / trigger.evaluated / trigger.viewed / workflow.started / workflow.completed |
| `provider.*` | 9 | registered / removed / viewed / selected / execution.started / execution.completed / execution.failed / usage.recorded / feedback.created |
| `product.*` | 15 | decision.created / stage.entered / stage.completed / lifecycle.started / lifecycle.completed / lifecycle.status_viewed / lifecycle.templates_viewed / workflow.started / workflow.status_viewed / generation.started / generation.completed / generation.failed / experience.recorded / experience.viewed / approval_experience.recorded |
| `idea.*` | 3 | idea.created / idea.updated / idea.viewed (由 product 模块的 idea 命令发出) |
| `understanding.*` | 4 | started / completed / failed / viewed |
| `intelligence.*` | 14 | decision.created / decision.analysis.started / decision.analysis.completed / decision.option.evaluated / recommendation.started / recommendation.candidate.evaluated / recommendation.completed / recommendation.created / recommendation.explained / experience.recorded / experience.analyzed / feedback.learned / task.evaluated / viewed |
| `approval.*` | 11 | created / pending / required / approved / denied / rejected / granted / changes_requested / delegated / resumed / viewed |
| `console.*` | 3 | console.viewed / console.dashboard.viewed / console.approval.opened |
| **合计** | **137** | 26 namespace |

> 注: `agent.*` 前缀同时覆盖 `assignment.*` 事件 (枚举值形如 `agent.assignment.created`); `idea.*` 与 `approval.*` 由 product 模块发出 (idea 命令 / ApprovalGate 状态机), 但枚举上为独立 namespace; 所有未来层 (Extension/Intelligence/Console) 复用 Core Event Logger, EventType 纯增量扩展。

**事件链示例 (可审计闭环)**:

```
执行:   task.created → assignment.created → execution.started → execution.completed → workflow.completed
决策:   intelligence.decision.created → intelligence.decision.analysis.started → ...option.evaluated
        → intelligence.decision.analysis.completed → approval.created → approval.approved
经验:   intelligence.feedback.learned → intelligence.experience.analyzed → intelligence.task.evaluated
```

---

## 5. Artifact 流: product/Artifact 抽象 → Decision / Recommendation / Experience

### 5.1 Artifact 抽象 (product/models.py)

任何产品阶段产物都落在统一 `Artifact` 抽象上:

```
Artifact:
  id / type (product_idea/product_decision/research/prd/ui/architecture/...)
  content (dict) / status (created/pending/completed/failed/approved/denied/...)
  created_by (human | agent id | provider id)
  provider_id / agent_id      ← AI Artifact Lineage: 生成来源 Provider/Agent
  source_events [event_id]    ← Lineage: 生成事件链 (唯一事实源引用)
  version (重生成递增) / supersedes (版本链前驱 id, 禁覆盖历史)
  confidence (0-1, 审核优先级/经验学习数据接口) / created_at
```

**流**: `ProductService.create_idea` → `create_artifact`(product_idea) → 阶段产物 (research/prd/ui/…) → `get_or_create_gate`(按 artifact_type 归类, prd/ui mandatory) → `request_approval`(pending) → `decide_approval`(approved/denied) → `start_workflow` → `workflow_resume`; `revise_artifact` 生成新版本 (`supersedes` 链), `artifact_version_history` 可回看; 通过/拒绝走 `product.approval_experience.recorded` 沉淀审批经验。

### 5.2 Intelligence 产物 (独立数据空间 `.factory/intelligence/`)

| 产物 | 语义 | 关键字段 |
|:-----|:-----|:---------|
| `Decision` | 决策推荐产物 (分析/选项/评分/证据) | decision_type / subject_id / options / recommendation / confidence / risk / evidence / status(open→recommended→accepted/rejected) / approval_request_id |
| `Recommendation` | 推荐 + 结构化解释 (必须支持解释) | target_type(provider/agent/skill/workflow) / target_id / score / reasoning(逐条) / evidence / confidence / risk |
| `ExperienceRecord` | 统一经验 (五域: provider/agent/workflow/project/decision) | result(success/failure) / score / confidence / freshness / usage_count / last_used / evidence |

### 5.3 Evidence 六来源 (防 AI 自我循环, 事实优先)

```
artifact | event | experience | external_data | human_input | provider_output
lineage_ref() = f"{source_type}:{source_id}"   (如 event:<event_id> / artifact:<artifact_id>)
```

前五类是事实 (Factory 内部只读数据/外部事实/人工输入), `provider_output` 是 AI 建议 — 建议不是依据。每个 Decision/Recommendation 附 evidence 链 → 可审计、可追溯、可证伪; 决策全链强制证据, 无证据即 `NoEvidenceError` 拒绝 (零事件)。

---

## 6. Decision 流: Context → Options → Score → Recommend → Approval

```
DecisionContext (evidence_sources 非空, 否则 NoEvidenceError — 禁无证据)
  │  [intelligence.decision.created / analysis.started]
  ▼
analyze(context)                       → DecisionAnalysis (intelligence.decision.analysis.completed)
  │
  ▼
evaluate_options(options)              → 每选项四因素加权评分 (intelligence.decision.option.evaluated)
      score = clamp01( Σ factor_i × weight_i )
      权重: capability 0.40 / cost 0.25 / performance 0.20 / experience 0.15 (normalize_weights 归一)
      缺失因素 → 中性 0.5 (冷启动不偏见); 无四因素明细 → 采用 context 评估分 (注明"未做规则加权")
      选项无自身证据 → 继承 context 证据链 (inherit_context_evidence=True)
  │
  ▼
recommend()                            → 推荐选项 (top option key, confidence 分数差距+证据覆盖+因素完整度)
  │
  ▼
assess_risk()                          → 风险等级 (无候选/严重短板 → high; 竞争激烈/低置信度 → medium)
  │
  ▼
build_decision()                       → Decision Artifact (open → recommended)
  │
  ▼
bind_approval()                        → 高风险/低置信度 → 9c ApprovalGate:
       request_approval(artifact_id, gate_id, *, by, note) — duck-typed 注入
       (引擎零 imports product/ — Removal Isolation, 装配方 CLI/测试注入; 低风险不提交审批)
       approval_request_id 回填 Decision; 人 decide → 结果回写 Decision:
       open → recommended → accepted (人工采纳) / rejected (人工否决)
```

**Decision ≠ Approval**: Decision = AI 推荐产物 (只分析+推荐+解释, **无任何执行指令字段**); Approval = 人工闸门状态机 (pending/approved/rejected/changes_requested/delegated)。执行决策权在人。

---

## 7. Experience 流: Task → Recommendation → Execution → Usage → Result → Experience → Better Recommendation

```
Task 完成 (execution.completed / workflow.completed)
  │
  ▼
record_experience()                    → ExperienceRecord 落库 (只记录不执行)
       domain: provider/agent/workflow/project/decision
       result: success | failure (负样本 = 反事实记录, 防只记成功的偏差)
       effective_score = score × confidence × freshness      [intelligence.feedback.learned]
       freshness = 0.5 ^ (age_days / 30)  (半衰期 30 天, 使用即刷新锚点)
  │
  ▼
ExperienceAnalyzer.aggregate()         → 正负聚合: clamp01(mean(sign × effective_score))
       sign = +1 成功 / −1 失败; 全失败 → 0.0 (低于中性门槛不推荐)
       成功经验能克服单次失败 (多次 0.9 + 单次 0.3 → 0.5 过门槛)   [intelligence.experience.analyzed]
  │
  ▼
TaskEvaluator.evaluate(requirement)    → 按 task_type+capability 过滤 → 按 (subject_type, subject_id) 分组
       → 推荐 agent/provider/skill (每类封顶 5, 有效分 ≥ 0.5) + Confidence + Reasons + Risks
                                                                  [intelligence.task.evaluated]
  │
  ▼
RecommendationEngine (下一次推荐)       → experience 因素 = min(aggregate, capability)
       (历史经验是对能力的背书, 不是能力的替代 — 经验分 ≤ 能力分)
       无记录 (冷启动) → 候选声明经验分, 缺省 0.5 中性 (新候选不被惩罚)
  │
  ▼
Provider Usage 回流                    → provider.usage.recorded → Cost/Performance 因素
       (CostAwareSelector / RecommendationEngine 的 cost 0.20 + performance 0.30 因素)
  │
  ▼
下一次 Task → 更准的 Recommendation    → 闭环: 执行结果沉淀为经验事实, 经验影响未来推荐与评估
```

**边界铁律 (Experience ≠ Self Modification)**: 只记录事实 + 只读分析; 显式不做 自动修改权重/自动生成 Skill/自我复制/自动重构 Core/基于自身输出自我强化 (全部留给未来 Self Evolution 阶段, 需版本化+回滚+人工闸门)。

---

## 8. Core 冻结 / Extension 独立 / Removal Isolation 确认

### 8.1 Core 冻结 (零修改验证)

**结论: 冻结有效, 无需重构。** 依据 `architecture-freeze-2026-08.md` (20 Phase 审查, 冻结确认) + 本次审计的源码级验证。

- **Core = 8 项通用原语** (core-boundary.md): 状态管理 (tasks/workflows/agents/assignment/execution) · 生命周期 (workflows/recovery) · 调度 (orchestration/assignment) · 执行抽象 (runtime RuntimeAdapter 接口, 不实现具体 Runtime) · 事件审计 (events, append-only 唯一事实源) · 恢复 (recovery checkpoint+replay) · 观测基础 (dashboard/metrics 只读聚合) · 组织 (workspace/project)。
- **冻结纪律**: 冻结后不修改 Core 行为; 新能力一律走 Extension 声明式注册 (Skill/MCP/Runtime/Provider JSON, 零 Core 代码改动); 新能力判定流程 Q1 (通用原语还是领域能力) 一票否决。
- **源码级零领域依赖验证** (本次实测, 全量扫描 `factory-core/` 除 cli 组合根外):
  - `tasks/ workflows/ agents/ assignment/ execution/ orchestration/ runtime/ runtimes/ validation/ recovery/ events/ metrics/ workspace/ project/` — **零顶层 imports** `git/change/changeflow/providers/product/intelligence/understanding/console`。
  - 唯一例外两项且均不构成业务依赖: `dashboard/models.py` 引用 `git.models` (仅 git/change/changeflow 三视图的渲染类型, `include_git` 缺省关); `cli/commands.py` 是组合根, 对领域包只允许函数内延迟导入 (有测试断言 `test_product_removal.py::test_cli_commands_has_no_top_level_product_import`)。
- **行为冻结验证**: 41 个提交全部可回放 (每个 Phase 有独立测试基线: 69 → 4090); 当前 4090 tests 全绿 = 冻结后零行为回归。

### 8.2 Extension 独立 (删除任一 Extension 系统仍运行)

**结论: 任一 Extension 模块可独立安装/禁用/删除, Core 照常运行。** 各模块有独立测试 + 独立数据空间 (`capability-architecture.md` 约束 8: "删除一个模块 → 系统还能启动, Core 还能运行")。

| Extension | 独立性证据 (测试/源码) |
|:----------|:-----------------------|
| `git/ change/ changeflow/` | Dashboard `include_git`/`include_changeflow` 缺省关; Validation L4 无证据 → SKIP 不误报 (clean 仓库不 FAIL); task/workflow/execution/event 核心路径零 import git |
| `providers/` | Provider 是 Runtime 之上的可选 LLM 来源; 删除后 Runtime echo/hermes 直跑; store 零顶层 events imports (解耦铁律) |
| `product/` | `tests/product/test_product_removal.py` + `test_product_lifecycle_removal_9d.py`: store 零顶层 events imports; dashboard collector 零顶层 product imports; CLI 延迟导入; 删除 product 包后 `dashboard --view product` 仍 rc 0 (空快照, 旧链路) |
| `understanding/` | `capability-architecture.md` 约束 4: 删除 understanding → 系统仍运行 (零 Core 依赖); 独立目录 + 独立测试 + 独立数据空间 |
| `intelligence/` | `tests/intelligence/test_intelligence_removal.py` (见 §8.3); 决策引擎零 imports product/providers/runtime/events.store, 审批服务由装配方注入 (duck-typed) |
| `factory-console/` | `tests/console/test_console_isolation.py`: 零写快照 (全部读方法前后数据空间逐字节一致, 唯一例外 events.db 的 CLI 审计事件); 删除 factory-console → Factory 照常运行; `human-console-model.md` "零写 API / 不自动执行 / 不自动批准" |

### 8.3 Removal Isolation (模拟删除包)

**结论: 运行期删除任一 Extension 包, Core 模块正常导入与工作。** 测试证据:

1. **源码级**: Core 各模块零 imports intelligence/product (`_core_py_files()` 全量扫描断言); `intelligence/store.py` 零顶层 imports events/product/providers/runtime (纯 stdlib + 公共接口); `intelligence/models.py` 零 imports product/providers/runtime。
2. **运行期**: `monkeypatch builtins.__import__` 对目标包抛 `ImportError` (模拟删除) → Core 模块正常导入/工作 (test_intelligence_removal)。
3. **数据空间隔离**: 删除 `<root>/intelligence/` 数据空间不影响 Core store 数据; 各扩展写各自 `.factory/<ext>/` 目录, 禁止修改其他模块数据文件。
4. **独立可导入**: intelligence 包独立可导入 (不依赖 CLI/dashboard 装配); console 路由函数无 FastAPI/Web 依赖, 未来挂薄层即 handler 主体。

---

## 9. CLI 命令全景 (实测: 23 顶级命令组 / 77 叶子命令)

| 命令组 | 叶子命令 | 审计事件 |
|:-------|:---------|:---------|
| `init` | `init` | system.init |
| `task` | create / list / status / update | task.created / task.viewed / task.updated |
| `event` | logs | system.logs_viewed / workspace.events.viewed |
| `status` | status | system.status_viewed |
| `validate` | validate | validation.* |
| `agent` | add / list / assign / assignments / release | agent.* / assignment.* |
| `skill` | add / list | skill.* |
| `workflow` | list / add / run / status | workflow.* |
| `runtime` | add / list / test / catalog list / catalog show | runtime.* |
| `execution` | list / run / status | execution.* |
| `checkpoint` | create / list | recovery.started/completed |
| `recover` | recover | recovery.* |
| `dashboard` | dashboard | dashboard.viewed |
| `metrics` | metrics | metrics.viewed |
| `project` | list / show | project.viewed |
| `provider` | list / show / test / usage / stats / compare / recommend | provider.* |
| `product` | idea create/list/show · approval request/decide/list/history · workflow start/status/resume · generate · experience list/record · lifecycle start/status/advance/templates | product.* / approval.* |
| `intelligence` | decision create / recommend / experience list / experience evaluate | intelligence.* |
| `workspace` | init / show | workspace.* |
| `git` | status / diff / commits | git.* |
| `change` | commits / analyze / validate / triggers register/list / evaluate / workflows | change.* |
| `understand` | understand | understanding.* |
| `console` | dashboard / approvals | console.* |

---

## 10. 审计结论

| 项 | 结论 |
|:---|:-----|
| 四层架构 | Core / Extension / Intelligence / Human Console 边界清晰, 依赖单向向下, 与代码一致 |
| Core 冻结 | 冻结有效 (2026-08 冻结报告 + 41 提交回放 + 4090 测试全绿 + 源码级零领域 import 扫描) |
| Extension 独立 | 六个 Extension + Console 均可独立删除, 系统照常运行 (Removal Isolation 测试 + 数据空间隔离) |
| Event 唯一事实源 | 137 事件 / 26 namespace, append-only SQLite, 所有写操作发事件, 读操作发 .viewed 审计 |
| 认知层边界 | Intelligence 只分析/推荐/解释, 不自动执行, 零 imports 领域模块, 审批经 duck-typed ApprovalGate |
| Human Layer | Console 只读 + 审批, 无第二条执行路径; Web UI 与 CLI 走同一事件/状态机 (审批等价性) |
| 后续演进 | 新能力一律走 Extension 声明式注册 (Skill/MCP/Runtime/Provider), 零 Core 破坏 |
