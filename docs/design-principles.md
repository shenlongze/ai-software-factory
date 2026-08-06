# AI Software Factory — Design Principles

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 与 Phase 6E 实现对齐
> 关联文档: [vision.md](./vision.md) · [lifecycle-model.md](./lifecycle-model.md) · [architecture.md](./architecture.md)
>
> 本文档归纳 AI Software Factory 的 7 条核心设计原则。每条原则给出**含义**(为什么)、
> **工程体现**(在 factory-core 里怎么落地)与**实例**(项目中的真实模式)。
> 原则是"魂": 代码可以重构, 原则不能破坏。

---

## ① Event is source of truth — 事件是唯一事实源

### 含义

系统的任何事实只能有一个来源: **append-only 的事件流**。状态是事件的投影, 不是独立存储的真相。错误不能靠"改掉历史"修正, 只能靠"追加新事件"纠正 —— 历史永远可审计, 回放永远可复现。

### 工程体现

- `events` 表 (SQLite) 是**唯一强制持久化**的存储; `seq` 自增主键是回放锚点, 事件只 INSERT, 永不 UPDATE/DELETE (ADR-0001/0002)。
- **状态不落表, 由事件投影得出**: tasks/agents 表只存定义性数据 (role/scope/acceptance/dependencies), status 一律投影。
- **所有 CLI 行为必须产生 Event** — 连读命令都发事件 (`task.viewed` / `system.logs_viewed` / `system.status_viewed`), 优先级高于"读命令不发事件"的旧约定 (ADR-0002)。
- 指标不建统计表, 全部由事件聚合 (first_attempt_success / path_errors / human_intervention)。

### 实例

- `cmd_task_status` 返回"任务详情 + 最近事件时间线": 状态与历史都从事件查询重建。
- 执行记录 `execution.created → started → completed/failed` 是执行的唯一事实; 任何视图 (CLI/Dashboard/审计) 只读事件。
- L4 Change Validation 判定基于 `git.commit.linked` / `change.analyzed` 等事件与 git 证据, 不信任任何自报告。

---

## ② Everything is observable — 一切可观测

### 含义

任何时刻都能回答: **系统现在在做什么? 做过什么? 结果如何? 谁做的?** 可观测是"可管理"的前提 —— 看不见的生产线无法管理。

### 工程体现

- CLI `event logs` (倒序时间线, 可过滤, `--workspace` 跨项目) + `factory status` 总览。
- Dashboard 16 个视图 (Phase 4C4/6B/6E), 覆盖任务/工作流/执行/分配/运行时/验证/恢复/指标/项目/工作区/git/变更/变更流。
- 每个领域都有只读查询命令且全部发审计事件: `task.viewed` / `agent.viewed` / `workflow.viewed` / `runtime.viewed` / `execution.viewed` / `project.viewed` / `git.status.viewed` / `change.trigger.viewed` / `dashboard.viewed` ...
- 执行过程可追踪: 工具调用、单步编排 (`orchestration.step.started/completed`)、单条验证规则 (`validation.rule.*`) 都有事件。

### 实例

- `git status/diff/commits` 是**只读**查询, 仍发 `git.status.viewed` / `git.change.detected` 审计事件 —— 谁在什么时候看过什么都可审计。
- `dashboard --view changeflow` (第 16 视图) 把触发器、评估、工作流链三张表渲染出来, 数据源全是事件聚合。
- 任务时间线 (最近 5 条事件) 直接嵌入 `task status` 输出, 回答"这个任务现在卡在哪"。

---

## ③ AI execution must be replaceable — AI 执行必须可替换

### 含义

Factory 不绑定任何 Agent 框架或模型。**执行 Agent 是可插拔的部件**: 换 Runtime = 换 Adapter, 核心零改动。模型会变、框架会变, 工厂的组织能力不变。

### 工程体现

- **执行出口唯一**: 任何"启动 Agent / 跑命令 / 调工具"只能走 `RuntimeAdapter` 协议 (或 Validation/MCP 封装), 不裸调 subprocess 散落各处 (architecture.md 三条硬规则之一)。
- `runtimes/` 可插拔目录: hermes 适配器 (默认, 实跑) + mock (测试) + 预留 claude_code 等; `runtime/registry.py` 注册, `config` 选默认, CLI `--runtime` 可覆盖 (ADR-0006/0009)。
- **三层分离** (Phase 5A1, ADR-0014): `runtimes/` Catalog = 能力描述 (catalog.json), `runtime/` Registry = 实例可用状态 (runtimes.json), Adapter = 执行器。目录不派发、注册不执行。
- 分配器 (AgentAllocator) 按运行时偏好与可用性选执行器, 同一任务换 Runtime 零核心改动。

### 实例

- `factory runtime add/list/test` + `runtime catalog list/show`: 注册、测试、查看能力目录全走声明式数据。
- 收尾契约: Change 规则④ (runtime.pref) 的输入是 `RuntimeRegistry` AVAILABLE 集合 —— 规则只看"有什么执行器可用", 不管执行器内部是什么。
- ADR-0006 测试约束: 同一任务通过 ≥2 种 Runtime 执行, 核心代码零改动。

---

## ④ Human approval at product decisions — 人工批准产品决策

### 含义

**产品决策 (做什么、要不要、能不能上线) 的最终裁决权在人。** AI 可以执行、可以建议, 但涉及产品冲突、架构变更、Scope 扩展的闸口必须由人拍板。自动化不能静默改变产品方向。

### 工程体现

- **Orchestrator = 决策接口**: 第一版由 CLI 承载人工决策循环 (`task create/approve/reject/resume`); P1 的 LLM 驱动是**同一个决策接口的另一个实现**, 接口先定好, 人还是 LLM 只是实现选择 (architecture.md §2.2)。
- **三挡板** (产品冲突 / 架构变更 / Scope 扩展): 命中挡板 → `task.blocked` + 上报, 人裁决后才继续。
- 所有人类决策发 `human.*` 事件 (`human.decision`), 构成 human_intervention 指标的原始数据。
- 验证失败不是自动"重试到过", 而是打回三选一: 1 修复 / 2 换法 / 3 上报 (validation-model.md §2)。

### 实例

- Validation 越权写 → `validation.blocked` → 人工核查证据链 → approve (继续) / reject (返工回路)。
- `change evaluate` 的触发与执行解耦: 规则 PASS 可启动目标工作流, 但执行失败只审计不误报 —— 判定是机器的, 最终交付决策链上仍保留人工环节。
- 决策门 (Decision Gate): 无决策记录不进入开发 (validation-model.md §3.1), 决策记录本身是产品判断的证据。

---

## ⑤ Runtime separated from intelligence — 运行时与智能分离

### 含义

**"思考" (决策/编排) 与"干活" (执行/工具) 是两层, 必须分离。** 智能层决定做什么、怎么做、由谁做; 运行时层只负责执行委派并报告结果。两者通过契约 (事件 + 结果) 通信, 不互相渗透。

### 工程体现

- **决策侧**: Orchestrator (人/LLM) + Workflow Engine (流程状态机) + AgentAllocator (分配策略) + ChangeWorkflowEngine (触发规则) —— 全部是纯逻辑, 不直接执行。
- **执行侧**: ExecutionService 管理执行请求生命周期 (`execution.created → started → completed/failed`), 派发给 Runtime Adapter 执行, 结果以事件 + 产物返回。
- **复用不复制** (ADR-0020): changeflow 只组装既有 WorkflowEngine / WorkflowStore / OrchestrationPipeline, 不修改 workflows/execution/orchestration 核心; 规则输入 = ChangeService, 不复制 L4 判定逻辑。
- 规则恒定 `RULES = (validation.l4, commit.linked, required.files, runtime.pref)` 全为纯函数, 输入装配失败安全。

### 实例

- `execution run` 执行 pending execution, 状态推进与 Agent 内部行为完全解耦 —— 换 Agent 不换执行层, 换执行层不换 Agent。
- Orchestration 流水线 (`orchestration.pipeline.execute_workflow`) 做"匹配 → 分配 → 执行"编排, 每一步是独立事件, 执行细节全部下沉到 Adapter。
- Agent Registry 只登记身份与技能装配 (Agent/Skill), 不参与执行; Execution 只派发执行, 不做决策。

---

## ⑥ Recovery by replay — 恢复 = 事件回放

### 含义

恢复不依赖任何对话记忆或口头 summary。**任务状态是磁盘事实 (checkpoint), 恢复 = 从最近检查点回放事件链, 核对产物, 从断点续跑。** 截断/失败可以零丢失恢复。

### 工程体现

- `recovery/` 模块三件套: `checkpoint.py` (检查点落盘) / `replay.py` (事件回放) / `service.py` (恢复编排)。
- **恢复协议**: 断点续跑只认落盘状态 + 产物; 恢复时先核对产物存在, 不存在则从最近停靠点重做 (roadmap Phase 3 契约)。
- CLI `checkpoint create/list` + `recover`; 每次 checkpoint 一条事件, 恢复操作发 `recovery.started/completed/failed`。
- 回放锚点 = `events.seq` 单调递增; 恢复 = `SELECT ... ORDER BY seq` 回放 → 找最近 `system.checkpoint` → 校验 git 状态一致 → 续跑。

### 实例

- 模拟截断 3 次, 恢复后均从最近真实停靠点继续, 无重复劳动 (Phase 3 验收标准)。
- `recover` 命令基于 checkpoint 快照恢复任务, 产物缺失自动回退到最近停靠点重做。
- 执行续跑: run 已 RUNNING → OrchestrationEngine._ensure_run 走续跑分支, 天然支持 target != task.workflow 的链式交付 (ADR-0020 决策 2)。

---

## ⑦ Incremental evolution, zero core destruction — 增量演进, 零核心破坏

### 含义

工厂以**增量**方式演进: 每个 Phase 独立可交付、可回退, 绝不以"重写核心"为代价换取新能力。**新能力必须复用既有核心, 且不能破坏旧行为** —— 测试只增不减, 兼容永远优先。

### 工程体现

- **测试只增不减**: 每个 Phase 收尾都有失败测试的契约裁定, 测试总数单调增长 (如 Phase 6E: 2155 → 2159 全绿, 含 10 个契约修复, 0 删除)。
- **复用不复制**: changeflow 只组装既有引擎, 不修改 workflows/execution/orchestration 核心 (ADR-0020 明令)。
- **失败安全**: 新层永不把异常级联到核心 —— evaluate 永不抛 (触发失败转 ERROR 评估)、触发器文件损坏 → 空列表、ChangeService 异常 → 规则 SKIP 证据为空 (绝不误报 FAIL)。
- **旧兼容**: 新功能默认关闭 (`include_git` / `include_change` / `include_changeflow` 缺省关, 零回归); 旧 Task 无 git 关联 → L4 SKIP; Task.project 字段沿用旧约定。
- **扩展点全部声明式**: 新角色 = JSON、新 Skill = SKILL.md + meta.json、新工作流 = JSON、新 MCP 工具 = JSON, 零核心代码改动 (architecture.md §7)。
- **可回退点**: 每个 Phase 都定义回退点 (停掉/关闭某能力, 系统行为退回上一阶段且无残留异常)。

### 实例

- ADR-0020 收尾裁定: 10 个失败测试中 9 个是"测试期望与新契约矛盾"→ 修测试不修核心; 1 个是测试用了不存在的 API → 修测试。
- VIEWS 精确集合断言随视图扩展 (15→16) 数学上必然失败 —— 第五犯先例时最小化更新 + ADR 记录, 而非改断言框架。
- 一个 Phase 一个 ADR, 每个 ADR 记录"收尾失败测试的契约裁定", 演进过程本身就是可审计的决策历史。
