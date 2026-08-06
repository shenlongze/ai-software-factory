# ADR-0029 — Phase 9d: Product Lifecycle Orchestration (产品生命周期编排)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 9c (0028, 3263 tests)

## 背景

9a-9c 已具备产品智能底座 (Idea/Artifact/Approval Gate/Provider 生成/通用人工决策),
但**阶段编排是手工的**: 用户需自己记住 Idea→Research→PRD→审批→UI→审批→
Architecture→Task 的顺序, 决策链 (Product→Architecture→Task Plan) 散落在
各产物中, 与 Core Task 执行 (tasks/workflows) 无衔接。Phase 9d 引入**产品
生命周期编排引擎**: 声明式阶段模板 + 显式推进 + 审批门暂停/恢复 + 决策链
索引 + Task 生成衔接 Core 执行。冻结约束 (同 9a-9c): **Core 零修改 /
Extension only / Event 唯一事实源 / Artifact lineage / Approval & Provider
Intelligence 复用 / 禁止复制 Workflow Core**。

设计文档: docs/design/phase9d-status.md (Stage Registry + Workflow Template
声明式 + Engine start/advance/pause-resume/completed)。

## 决策

### 1. 分层: 业务生命周期 vs 任务执行 (不复制 Workflow Core)

- **ProductLifecycle (9d)** = 业务生命周期编排: 8 阶段链 (idea→research→prd→
  approval(prd)→ui→approval(ui)→architecture→task), 跟踪当前阶段/暂停恢复/
  决策链索引。**阶段注册表声明式**: `ProductStageRegistry` + 内置
  `software_project` 模板 (BUILTIN_TEMPLATES); 未来 automation/business 模板
  经 register() 追加, 引擎零改动 — 不硬编码阶段名。
- **9c ProductWorkflow** = 审批门暂停/恢复骨架 — 本层经 ProductService 复用
  (request_approval/decide), 不复制状态机。
- **Core Workflow (tasks/workflows)** = 任务执行 — task 阶段经 `TaskStore.create`
  生成 Core Task (task.workflow 既有字段关联 feature-delivery), 之后由既有
  WorkflowEngine/OrchestrationPipeline 装配点负责; 本层**不调 WorkflowEngine、
  不复制编排逻辑**。

### 2. 阶段类型分类 (StageKind 驱动引擎行为)

| kind | 引擎行为 |
|---|---|
| artifact_generation | advance 前置校验 idea 下存在该类型 Artifact (生成由 9b 负责, 编排层只校验不生成) |
| approval | 进入即自动 request_approval (复用 9c, 门解析/队列守卫/事件全复用, 零复制) + lifecycle → paused; 经 decide 联动推进 |
| decision | 前置校验源产物 + 前序决策链 → 完成时产生 architecture_decision Artifact + 决策链记录 |
| task | 前置校验 product+architecture 决策链完整 + TaskStore 装配 → task_plan Artifact + Core Task 生成 |

### 3. 编排语义 (KISS, 显式推进)

- `start_lifecycle`: 校验 idea 存在 + 无重复实例 + 模板注册; 实例落库 →
  lifecycle.started → 首阶段 entered (running)。一个 idea 至多一个 run。
- `advance`: 手动推进非 approval 阶段 (前置校验 → 完成 stage.completed →
  下一阶段 entered); 下一阶段是 approval → 自动申请审批 + paused; 全部完成 →
  lifecycle.completed。**approval 阶段不响应 advance** — 报错提示走审批决定
  (running 态与 paused 态均提示 "advance via approval"; paused 报错同时保留
  "is not running" 语义, 引擎测试契约双命中)。
- `handle_approval_outcome`: 审批终态 approved → 决策链记录 (approval 阶段有
  decision_type 时) + 完成阶段 + 推进; 非 approved (rejected/
  changes_requested/delegated) → 停留 (生命周期保持 paused, 9c 终态可逆语义)。
- `pause`/`resume`: 手动暂停/恢复 (引擎 API; CLI 不暴露, 5 事件契约不变)。

### 4. 决策链 (Product → Architecture → Task Plan) 索引记录

`DecisionArtifact` (lifecycle.json 独立节, DEC-001 前缀) 与 Artifact 分离:
type 标识链位置, decision_id 为驱动决策的 ApprovalDecision id, source_artifact_id
为决策依据源 Artifact, approved_reference 为决策产物 Artifact id。**链序稳定**:
每类型多条取最新, 按固定类型序输出 (Dashboard/CLI/任务前置校验共用
`_decision_chain`)。task_plan 产物内容闭环: decision_chain 引用全部 3 节点
(含 task_plan 决策自身 — 记录后回填)。

### 5. Task 集成 (禁修改 Core)

task 阶段经 `TaskStore.create` (既有 API, 只调用) 生成 Core Task:
task.workflow = feature-delivery (既有字段关联), project 从 idea.context 推导
(缺省 default), 标题含 task_plan 锚点 (任务→决策链可追溯)。task 阶段前置
校验**顺序固定**: 决策链完整性先于 TaskStore 装配; task_store 未装配 → 响亮
配置缺口错误 (不静默降级)。

### 6. 事件链 (5 类型核心契约 + 2 审计)

`product.lifecycle.started → product.stage.entered ×8 → product.stage.completed
×8 → product.decision.created ×3 (product→architecture→task_plan) →
product.lifecycle.completed` (终态事件单一)。审计: status_viewed /
templates_viewed (只读, CLI 命令层发出)。approval 阶段进入后 9c 审批链事件
(approval.created→pending→required) 插在 stage.entered(approval) 之后 —
引擎服务须带 logger。

### 7. Dashboard Lifecycle View (第二十视图, 默认关零回归)

collector `include_lifecycle` 独立开关 (默认 False — 既有 dashboard 行为与
all 视图不含 Lifecycle 面板, 零回归): 生命周期计数/状态分布/当前阶段/pending
审批/决策链/next_actions。**Lifecycle View 不依赖 include_product** (独立
开关, 单独开启时仍聚合生命周期段)。失败安全: 未装配 product_store → 空快照。
Removal Isolation 源码级断言: collector 零顶层 imports product — next_actions
为与 engine._next_actions 同构的纯函数副本。

## 影响

- Core 零修改; providers/** 只读复用; tasks/workflows 只读调用
  (TaskStore.create); 9a-9c 事件与 Dashboard 输出逐位兼容。
- product/: models (ProductLifecycle/ProductStageRun/DecisionArtifact/StageKind/
  LifecycleStatus) + store (lifecycle.json 双节) + lifecycle.py (引擎) + events
  (5+2 事件辅助); cli/ (lifecycle start/status/advance/templates 命令 + decide
  挂接 handle_approval_outcome); dashboard/ (models/collector/views 第 20 视图)。
- EventType 纯增量枚举 (product.lifecycle.* / product.stage.* /
  product.decision.created)。
- 测试: 3263 (9c) → **3393 passed** (9d 新增 tests/product/
  test_product_lifecycle_*_9d.py 7 文件 + 兼容零删除)。收尾修: CLI advance
  approval 测试补一次推进 (阶段计数笔误) + 4 个 task 阶段前置测试补
  start_lifecycle (测试构造缺生命周期实例) + 引擎 paused@approval 报错信息
  双契约化。
