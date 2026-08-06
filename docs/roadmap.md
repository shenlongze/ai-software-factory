# AI Software Factory — 路线图

> 版本: v2.0 | 日期: 2026-08-06 | 状态: 当前 (Phase 1–6E 已完成, 2159 tests;Phase 7–10 为规划, 不开发)
> 关联文档: [architecture-overview.md](./architecture-overview.md)(11 层架构) · [architecture.md](./architecture.md)(工程化落地版) · `docs/adr/0001..0020`

---

## 0. 总览

系统已从"观察层"演进为"可执行的 11 层工厂":从事件记录、任务/工作流/Agent 管理,到执行编排、验证、恢复、观测,再到 Git 变更智能与变更驱动工作流。当前所有阶段**独立可交付、可回退**,2159 个测试全绿。

未来四条主线 (Phase 7–10) 从"工厂内部执行"向外扩展:

```
已完成 (Phase 1–6E)              未来规划 (Phase 7–10)
┌─────────────────────┐          ┌──────────────────────────┐
│ 事件/任务/工作流/Agent │          │ Phase 7  Project Understanding │
│ 执行/Runtime/验证/恢复 │  ──────▶ │  看懂"任何阶段的项目"          │
│ 观测/Dashboard/指标    │          ├──────────────────────────┤
│ Git 变更智能/变更驱动   │          │ Phase 8  LLM Provider Abstraction│
└─────────────────────┘          │  解除 Hermes 单一绑定        │
                                 ├──────────────────────────┤
                                 │ Phase 9  Product Intelligence │
                                 │  想法→PRD→UI→任务            │
                                 ├──────────────────────────┤
                                 │ Phase 10 Operations       │
                                 │  部署/监控/运维/诊断          │
                                 └──────────────────────────┘
```

---

## 1. 已完成:Phase 1–6E 摘要

> 20 个实施阶段,累计 **2159 tests** 全绿;每阶段对应一次可回退提交 + 一份 ADR。详细分层见 [architecture-overview.md](./architecture-overview.md)。

| Phase | 名称 | 核心交付 | 关键提交 | 测试基线 |
|:--:|------|---------|:--:|:--:|
| 1 | Event Logger MVP | Pydantic 不可变 Event + SQLite append-only EventStore + Metrics 聚合 | `ceb5f40` | 69 |
| 2 | Factory Control CLI | Task 系统 + CLI (init/task/status/logs/validate) + Event 集成 | `f4e96f3` | 141 |
| 3A | Validation Engine | 三层验证 (L1 Factory / L2 Workflow / L3 Artifact) + Event + CLI Report | `b213a14` | 223 |
| 3B | Agent + Skill Registry | Agent/Skill 模型 + Registry (find_by_skill) + JSON 持久化 + CLI | `1590c57` | 335 |
| 4A | Workflow Engine | Workflow/Step 状态机 + Engine + 内置定义 + Task.workflow 关联 + CLI | `389d556` | 449 |
| 4B-1 | Runtime Adapter Interface | Execution 模型 + RuntimeAdapter 抽象 + RuntimeRegistry + execute_step + CLI | `4b0f36a` | 584 |
| 4B-2 | Execution Dispatch Layer | Dispatcher/Runner/Service + EchoRuntimeAdapter + Workflow 联动 + CLI | `f06f73c` | 684 |
| 4B-3 | Agent Assignment Layer | Assignment 模型 + Matcher (role/skill/AVAILABLE) + Allocator + AgentRegistry 状态 + CLI | `ec0ae1e` | 824 |
| 4C-1 | Hermes Runtime Adapter | HermesRuntimeAdapter (subprocess) + 五类失败→FAILED + runtime test | `8a0f52e` | 908 |
| 4C-2 | Execution Orchestration Flow | OrchestrationEngine + Pipeline (Workflow→Matcher→Allocator→Execution→推进) + 失败无半完成 + --auto | `a369da5` | 981 |
| 4C-3 | Checkpoint Recovery | Checkpoint + EventReplay + RecoveryService (四场景) + CLI + recovery.* 事件 | `454f10d` | 1103 |
| 4C-4 | Dashboard MVP | FactorySnapshot + Collector (只读) + Rich Renderer (六视图) + CLI dashboard | `77ea59e` | 1203 |
| 5A | Production Example Layer | examples/markpad (project/agents/skills/workflows) + 加载器 + CLI project | `1011fb6` | 1237 |
| 5A.1 | Runtime Catalog | RuntimeDefinition + Catalog (find_by_capability) + 独立 catalog.json + 默认定义 | `77abf9f` | 1335 |
| 5B | Metrics Intelligence Layer | FactoryMetrics 六域 + Collector + Calculator (first_attempt_success_rate 等) + CLI metrics + Dashboard 八视图 | `c726392` | 1395 |
| 6A | Multi Project Workspace Layer | workspace/ (Workspace+ProjectDefinition+Manager+自动发现) + CLI workspace + Dashboard Projects View + Metrics 项目隔离 | `f1e3003` | 1498 |
| 6B | Workspace Operations Dashboard | dashboard/metrics/events --workspace + Agent 利用率 + Runtime 使用率 + 13 视图 | `d78f0ca` | 1616 |
| 6C | Git Integration Layer | git/ (Client 失败安全 + Service + task↔git 关联) + CLI git + Dashboard Git View | `974e371` | 1813 |
| 6D | Change Intelligence Layer | change/ (commit 解析 + analyzer + 自动关联 + L4 Change Validation) + Dashboard Change View | `6e965f1` | 2015 |
| 6E | Change Driven Workflow Layer | changeflow/ (ChangeTrigger + 4 规则引擎 + ChangeWorkflowEngine 触发链) + CLI triggers/evaluate/workflows + Dashboard Change Flow (16 视图) | `2d596c7` | **2159** |

**已完成部分的全局能力** (对应原 MVP 四痛点):
- **可观测**:事件日志 + 16 视图 Dashboard + 六域指标 + workspace 比较 (P1/P4C-4/P5B/P6B)
- **可管理**:任务状态机 + Agent/Skill/Workflow 注册 + 分配生命周期 (P2/P3A/P3B/P4A/P4B-3)
- **可执行**:Runtime 抽象 + 执行编排 + 断点恢复 + 三层验证 (P4B-1/P4B-2/P4C-1/P4C-2/P4C-3)
- **可智能**:项目/工作区配置 + Git 变更审计 → 变更分析 → 变更驱动工作流 (P5A/P5A.1/P6A/P6C/P6D/P6E)

---

## 2. Phase 7 — Project Understanding Layer:看懂任何阶段的项目

> 状态: ⬜ 规划中 | 依赖: 全部已完成阶段 (尤其 ② Project ⑤ Agent ⑧ Validation ⑪ Git)

**背景**:Factory 目前"知道"项目是通过 5A/6A 的显式 YAML 配置 (examples/ 或 workspace.yaml 托管)。遇到一个**没有配置、处于任意阶段**的真实代码仓库 (刚初始化 / 半成品 / 老项目),Factory 无法回答"这项目是什么、进行到哪了、还缺什么、下一步该干嘛"。本阶段补上"项目理解"这一认知层。

**目标**:
1. 输入一个任意 git 仓库,自动产出该项目的事实清单与生命周期阶段判断。
2. 任何阶段的项目都能给出"缺失信息分析 + 下一步动作建议",无需人工写配置文件。

**包含** (规划,不开发):
- **Project Inspection**: 只读扫描仓库 (复用 6C GitClient 失败安全模式) — 语言/技术栈识别、目录结构、包管理文件、README/文档、CI 配置、git 历史形态。
- **Artifact Detection**: 检测已存在产物 (源码模块、测试、构建配置、部署清单、文档),标注完整度。
- **Lifecycle Stage Detection**: 依据 artifact 证据 + git 历史模式判定阶段 (idea / scaffold / active-dev / stable / legacy / dead),映射到 Factory 工作流词汇 (feature-delivery / bug-fix / release)。
- **Missing Information Analysis**: 对照该阶段应有的信息清单,输出缺失项 (无测试 / 无 README / 无 CI / 无项目配置 / 无验收标准)。
- **Next Action Recommendation**: 按缺失项严重度排序,产出建议动作;可生成"项目配置文件草稿" (ProjectConfig) 让用户一键采纳 → 项目进入 Factory 管理。

**模块** (规划): `factory-core/understanding/` (inspection.py / detection.py / lifecycle.py / analysis.py / recommender.py),复用 `project.loader` 与 `git.client`;CLI `factory project inspect <repo> [--json]`;Dashboard 新增 "Project Understanding" 视图;事件 `project.inspection.completed` / `project.stage.detected` / `project.analysis.completed`。

**验收方向**:
- [ ] 对 3 种人工构造的仓库 (空 init / 半成品 / 完整工程) 输出阶段判断准确 (人工标注对照)
- [ ] 检测结果可回放、可审计 (事件链完整),全程只读 (字节级快照断言,沿用 4C-4 技术)
- [ ] 缺失信息清单与下一步建议可一键转化为 ProjectConfig 草稿
- [ ] 全量测试 ≥ 既有 + 120,零回归

**边界**:只理解、不改写仓库 (零写命令铁律沿用 6C);阶段判断是"证据驱动的建议",不替代人工决策。

---

## 3. Phase 8 — LLM Provider Abstraction:解除 Hermes 绑定

> 状态: ⬜ 规划中 | 依赖: Phase 7 (理解仓库后才能跨提供方执行)

**背景**:执行出口 ⑦ Runtime 已有抽象 (RuntimeAdapter),但当前唯一真实实现是 `HermesRuntimeAdapter` (subprocess hermes CLI)。"不绑定单一 Agent 框架"是设计稿的既定原则,本阶段把 LLM 提供方做成一等抽象,让同一套 Workflow/Task/Validation 逻辑跑在任何提供方上。

**目标**:
1. 新增 **LLM Interface** 协议层:统一"指令 + 上下文 + 文件范围 + 验收标准 → 结构化结果"的调用契约 (对齐 4B-1 的 Adapter 协议风格)。
2. 提供 **Providers** 适配集:至少 Hermes (现有)、Codex CLI、OpenAI 兼容 API、Claude、Local LLM (如 llama.cpp/vLLM),可插拔注册。
3. 执行同一工作流可在不同 Provider 间切换,Factory 核心零改动。

**架构** (规划):

```
Factory 核心 (Task/Workflow/Orchestration/Validation)
        │  唯一执行出口 (不直连任何 LLM)
        ▼
┌──────────────────────────────────────────────┐
│  LLM Interface (协议: execute(request)→result) │
│  request: 目标/上下文/文件范围/验收标准/checkpoint│
└───────┬──────────┬──────────┬──────────┬──────┘
        ▼          ▼          ▼          ▼
   hermes-provider codex-provider openai-provider local-provider
   (subprocess CLI) (subprocess)  (HTTP API)  (HTTP/GGUF)
```

**模块** (规划): `factory-core/providers/` (interface.py / registry.py / store.py 复用 4B-1 三段式模式 / adapters/ 各实现),`llm` 概念并入现有 `runtime/` 命名空间或独立 `llm/` 包 (实施时按 ADR 裁定);CLI `factory provider list|add|test|use`;配置 `FACTORY_PROVIDER` 环境变量 + 默认提供方;事件 `provider.registered` / `provider.usage.started/completed/failed`。

**验收方向**:
- [ ] 同一 4 步 feature-delivery 工作流在 ≥3 个 Provider 上跑通,零核心代码改动 (沿用 4C-2 全链冒烟)
- [ ] Provider 失败语义统一 (五类失败→FAILED,沿用 4C-1 模式);未选提供方时行为与今日一致 (默认 hermes,向后兼容)
- [ ] 提供方切换只读审计可查 (provider.usage.* 事件带 provider_id)
- [ ] 全量测试 ≥ 既有 + 150,零回归

**边界**:Provider 是执行器,不承载决策 (决策仍归 Orchestration/人工);Local LLM 仅作可行性验证,不承诺质量。

---

## 4. Phase 9 — Product Intelligence Layer:想法 → 任务

> 状态: ⬜ 规划中 | 依赖: Phase 7 (项目理解) + Phase 8 (多 Provider 执行)

**背景**:当前 Factory 从"已有任务定义"开始。产品起点 (想法/需求) 到任务定义之间 (调研、PRD、UI、架构、任务拆解) 完全靠人工。本阶段把"产品化决策链"引入 Factory:用 7 的项目理解 + 8 的多 Provider 能力,把一句话想法推进到可执行任务清单。

**目标**:
1. **Idea → Research**:输入产品想法,产出市场/竞品分析 (复用 5B 的只读聚合纪律,数据源为外部检索,证据入事件库)。
2. **Research → PRD**:基于调研生成结构化 PRD (目标/用户/范围/验收标准),**用户批准门**后才继续 (三挡板人闸口原则)。
3. **PRD → UI → Architecture**:PRD 批准后生成 UI 原型与架构方案 (均作为"候选产物"提交,不直接写码)。
4. **Architecture → Tasks**:架构方案自动拆解为任务清单 (task.create 候选),人工确认后进入 ④ 工作流执行。

**流程** (规划):

```
Idea ──▶ Research ──▶ PRD ──▶ [用户批准] ──▶ UI 原型 + 架构方案
        (市场/竞品)   (结构化)     ▲人闸口         │
                                          ▼
                                任务拆解 ──▶ 确认 ──▶ Factory 执行
                                          (④ Workflow + ⑥ Orchestration)
```

**模块** (规划): `factory-core/product/` (idea.py / research.py / prd.py / ui.py / architecture.py / breakdown.py),产物模型 (PRDDraft / UISpec / ArchitectureSpec / TaskBreakdown) 走 Pydantic + JSON store 既有模式;CLI `factory product idea|research|prd|ui|architecture|breakdown`;事件 `product.*` 族 (`product.idea.created` / `product.research.completed` / `product.prd.created` / `product.prd.approved` / `product.prd.rejected` / `product.breakdown.completed`);Dashboard 新增 "Product" 视图。

**验收方向**:
- [ ] 一条示例想法 (中文) 全链路:idea → research → PRD → 用户批准 → UI/架构 → ≥3 个任务,每步事件链完整
- [ ] 未经用户批准的 PRD 不可能进入 UI/架构 (人闸口强制,状态机断言)
- [ ] 任务拆解结果可直接批量 `task create` 并被 ④ 执行;产物 (PRD/UI/架构) 落盘可审计
- [ ] 全量测试 ≥ 既有 + 150,零回归

**边界**:产品判断 (是否值得做、批准/驳回) 永远是人;LLM 只产出候选与证据。Research 的外部数据需标注来源与时效。

---

## 5. Phase 10 — Operations Layer:开发 → 部署 → 运维

> 状态: ⬜ 规划中 | 依赖: Phase 7–9 (理解项目 + 多 Provider 执行 + 产品任务链)

**背景**:Factory 已覆盖"开发"环节 (任务 → 执行 → 验证 → 变更)。项目交付后还需要部署、监控、健康检查、故障处置。本阶段把运维纳入 Factory:让"开发→部署→监控→维护"闭环,且运维动作与开发一样可审计、可回放、可恢复。

**目标**:
1. **Deployment**:把 release 工作流延伸到部署 (构建 → 环境发布 → 回滚预案),复用 ⑪ changeflow 触发链。
2. **Monitoring**:服务健康检查与指标采集 (对接既有 ⑩ Metrics 体系,新增服务维度)。
3. **Incident Workflow**:故障 → 事件流 → AI 诊断 (复用 ⑨ Recovery 回放思路分析故障链) → 处置建议 → 人工确认。
4. **Maintenance**:定期巡检 (依赖/安全/过期资产) 生成维护工单。

**模块** (规划): `factory-core/operations/` (deploy.py / monitor.py / health.py / incident.py / diagnosis.py / maintenance.py);健康检查走只读探测 (复用 GitClient 失败安全模式:探测失败→结构化错误,永不裸抛);CLI `factory ops deploy|health|incidents|diagnose|maintain`;事件 `ops.*` 族 (`ops.deploy.started/completed/failed` / `ops.health.reported` / `ops.incident.created` / `ops.incident.resolved` / `ops.diagnosis.completed`);Dashboard 新增 "Operations" 视图。

**验收方向**:
- [ ] 一条示例部署:release 工作流完成 → 部署 → 健康检查 → (模拟故障) incident 创建 → AI 诊断 → 人工确认解决,事件链完整
- [ ] 健康检查只读 (字节级快照断言),故障诊断可回放 (复用 EventReplay)
- [ ] 部署可回滚 (预案为先),任何运维动作可审计、可恢复
- [ ] 全量测试 ≥ 既有 + 150,零回归

**边界**:运维动作默认**建议模式**——AI 诊断只出建议,破坏性操作 (删/改生产) 必须人工确认;生产环境接入不在本阶段范围 (本地/演示环境验证)。

---

## 6. 节奏与退出标准

| 阶段 | 名称 | 预估工作量 | 依赖 | 测试目标 |
|:--:|------|:--:|------|:--:|
| Phase 7 | Project Understanding Layer | 2–3 迭代 | 已完成全部 | ≥ 2279 |
| Phase 8 | LLM Provider Abstraction | 2–3 迭代 | Phase 7 | ≥ 2429 |
| Phase 9 | Product Intelligence Layer | 2–3 迭代 | Phase 7+8 | ≥ 2579 |
| Phase 10 | Operations Layer | 2–3 迭代 | Phase 7+8+9 | ≥ 2729 |

**全局退出标准** (在已完成四项能力上扩展为八项):**可观测** (任何时刻能答系统状态) · **可恢复** (截断零丢失) · **可信** (完成声明全有证据) · **可复用** (新坑不再重复) · **可理解** (任何阶段项目一看就懂) · **可替换** (Provider 即插即拔) · **可产品化** (想法到任务有据可依) · **可运维** (部署监控故障有人管)。

> 每阶段遵循既有纪律:基线先跑 (`.venv/bin/pytest -q`) → 阶段设计文档 + ADR → 自底向上实现 → 全量验证 + CLI 冒烟 → 提交推送。规划内容以本文件为准,实施细节以当阶段 design/ 文档与 ADR 为准。
