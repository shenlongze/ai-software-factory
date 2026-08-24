# AI Software Factory — 完整产品方案书（终极版）

> 版本: v3.0 | 状态: 战略设计完成 | 更新: 2026-08-21

---

## 目录

1. [产品定位与核心理念](#一产品定位与核心理念)
2. [模块化热插拔架构设计](#二模块化热插拔架构设计)
3. [复杂任务拆解体系](#三复杂任务拆解体系)
4. [多 Agent 编排与调用体系](#四多-agent-编排与调用体系)
5. [审计与可观测体系](#五审计与可观测体系)
6. [治理与合规体系](#六治理与合规体系)
7. [学习与自我进化体系](#七学习与自我进化体系)
8. [RAG 知识检索体系](#八rag-知识检索体系)
9. [工具生态与集成体系](#九工具生态与集成体系)
10. [行业工厂体系](#十行业工厂体系)
11. [全部交互场景设计](#十一全部交互场景设计)
12. [演进路线图](#十二演进路线图)
13. [完整术语表](#十三完整术语表)
14. [旧版保留章节（不丢失）](#十四旧版保留章节不丢失)
15. [竞品深度对比分析](#十五竞品深度对比分析)
16. [竞品优势吸收与技能定位补充](#十六竞品优势吸收与技能定位补充)
17. [自我进化体系专项设计](#十七自我进化体系专项设计)
18. [数据主权与隐私合规体系](#十八数据主权与隐私合规体系)
19. [知识图谱与结构化知识体系](#十九知识图谱与结构化知识体系)
20. [安全威胁模型与纵深防御体系](#二十安全威胁模型与纵深防御体系)
21. [国产化ERP对标与企业级就绪](#二十一国产化erp对标与企业级就绪)
22. [SDK 化与商业化路线](#二十二sdk-化与商业化路线)
23. [附录: 完整架构图索引](#附录-完整架构图索引)

## 一、产品定位与核心理念

### 1.1 一句话定义

> **AI Software Factory 是一个能够创建、管理、运行和进化 AI 公司的操作系统。**
> **英文名: AI Organization Operating System（AI Company OS）· 中文名: 数字企业运行模型**

### 1.2 核心论断与定位

**一句话类比**：

> LangChain 创建 AI 员工，LangGraph 编排 AI 工作流，而 **AI Software Factory 建立和管理整个 AI 生产组织**。

**核心论断**：

> **AI Factory 是"造专家的工厂"，不是某一个专家。**

- **造专家 = 领域智能产业（AI Domain Intelligence）**
  `Skill + MCP + Knowledge + Workflow + Evaluation + Learning = 领域智能产业`
- **专业的人做专业的事**：多 LLM 配合、多 Agent 协作，全自动完成任务
- **自我提升，但必须可控**（学习闭环 + 审批/预算/审计治理）
- **适用全行业，软件开发只是第一个行业实例**：
  IT 工厂（现在）→ 运维工厂 / 电商运营工厂 / 自媒体工厂 / 数据分析工厂 / 办公自动化工厂
- **民主化**：AI Software Factory 让**每个人**都能经营一家 AI 公司

**铁律**：

> 任何外部工具（skill / MCP / OpenClaw / Hermes…）都不能成为 AI Factory 完成任务的**必要条件**——它们是增强层，不是依赖层。

### 1.3 核心能力全景图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           AI Software Factory 核心能力全景                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        用户交互层                                            │   │
│  │        自然语言目标 │ 进度查看 │ 审计查询 │ 治理配置 │ 经验审查             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        核心引擎层                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 任务拆解引擎  │→│ 多Agent编排   │→│ 执行调度引擎  │                   │   │
│  │  │ (DAG拆解)    │  │ (协作编排)    │  │ (串行/并行)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │         │                    │                    │                          │   │
│  │         └────────────────────┼────────────────────┘                          │   │
│  │                              ▼                                               │   │
│  │  ┌───────────────────────────────────────────────────────────────────────┐  │   │
│  │  │                      Agent 执行层                                    │  │   │
│  │  │  Planner │ Executor │ Reviewer │ Debugger │ Governor │ Learner      │  │   │
│  │  │  (ReAct 循环 + 工具调用)                                             │  │   │
│  │  └───────────────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        横切能力层                                          │   │
│  │                                                                             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │   │
│  │  │ 审计系统  │  │ 治理系统  │  │ RAG系统   │  │ 学习系统  │              │   │
│  │  │ (全链路)  │  │ (合规/成本)│  │ (三级检索)│  │ (经验)    │              │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        行业工厂层                                           │   │
│  │  软件开发工厂 │ 运维工厂 │ 电商工厂 │ 自媒体工厂 │ 数据分析工厂 │ ...      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```




### 1.4 当前实现状态对照（工程锚点）

> 2026-08-21 由工程团队标注：本方案书各章在真实代码库中的落地状态。
> 图例: ✅ 已实现 · 🚧 部分实现 · 📐 仅设计（蓝图）
> 基线: v1.1.10 · 全量测试 11981+ passed · 三部门循环 M2 完成（T1-T5 专家真干活）

| 章节 | 状态 | 真实实现依据（代码） | 待补（里程碑） |
|---|---|---|---|
| 一 产品定位 | ✅ | 愿景已对齐（本 §1.1-1.3） | 自我进化闭环（M4） |
| 二 模块化热插拔 | 🚧 | `exec/mcp.py`（MCPClient 协议+Registry）、`session/tools.py`（工具发现） | 统一消息总线/插件规范（M2+） |
| 三 复杂任务拆解 | 🚧 | `session/pipeline.py`（TaskTree/FeatureTaskGenerator，确定性 DAG 雏形） | 模板库/质量评估（M3） |
| 四 多 Agent 编排 | ✅ | AgentEntity（`session/agent_entity.py`）/ AgentRegistry（`session/agent_registry.py`）/ ExpertFactory（`session/expert_factory.py`）/ HandoffBus（`session/handoff_bus.py`）· 7 角色真干活（T1-T5） | ux/qa 深化 + 记忆回流（M3/M4） |
| 五 审计与可观测 | ✅ | `audit/audit_event.py`（50 事件）、`session/observability.py`（exec history/status）、`team_state.py`（团队进度） | 递归进度视图/节点控制（§5.10, M3c+）· 实时监控/告警（M4） |
| 六 治理与合规 | ✅ | ReviewGate / ConfirmationGate / budget / ApprovalGate（分级审批，M1a） | — |
| 七 学习与自我进化 | 🚧 | `memory/`（experience/learning/retrieval/auto_learn）、`exec/evaluator.py` | 经验→画像→决策闭环（M4） |
| 八 RAG 知识检索 | 🚧 | `memory/retrieval.py`（经验检索） | 领域知识库（T4） |
| 九 工具生态与集成 | 🚧 | `session/tools.py`（发现 3 CLI+2 MCP）、StdioMCPClient（M1）、skills 注册表 | 消息平台 9.5（P0 5 渠道） |
| 十 行业工厂 | 🚧 | create_product / pipeline / `repo_mode.py`（IT 工厂） | FactorySpec+第二行业（M5/M6） |
| 十一 交互场景 | 🚧 | InteractiveSession（CLI REPL ✅）、React 壳（Web 📐） | Web/IDE 入口（M7） |
| 十二 演进路线 | ✅ | 对齐 `docs/MASTER-PLAN-2026-08.md`（M1-M7） | — |
| 十三 术语表 | ✅ | 文档 | — |
| 附录 架构图索引 | ✅ | 文档 | — |
| 十四 旧版保留 | ✅ | 历史文档归档 | — |
| 十五 竞品深度对比 | ✅ | 文档（2026-08-21） | — |
| 十六 竞品优势吸收 | 🚧 | MCP✅ / 沙箱✅ / 工具发现✅ / BYOK📐 | 四层记忆/GEPA（M4） |
| 十七 自我进化体系 | 🚧 | 自修复✅（replan/repair）、自发现✅（tools）、自监控✅（observability） | 五维闭环接线（M4） |
| 十八~二十一 数据/知识/安全/企业级 | 📐 | 本补充章节（2026-08-21 设计） | 随对应里程碑落地 |

**要点**：9 项已实现（一/四/五/六/十二/十三/附录/十四/十五），其余 10 章为"部分实现"，"仅设计"的完整闭环（学习闭环、消息平台、第二行业、Web 入口）正是 M3-M7 里程碑要补的。

### 1.4.5 层级流程模型（公司 → 工厂 → 项目 → 任务，每层有适合的流程）★

> 2026-08-24 补充（Founder 关键判断: 现在的流程太死板/单层——后面会有建立公司、
> 建立行业、建立项目等）: AI Factory 是 **AI 公司操作系统**, 不是"项目创建工具"。
> 正确架构 = **四层层级 + 每层有适合的流程**（决策型 LLM 深度 / 配置型模板 / 半结构化 / 结构化）。

**四层模型**

```
AI 公司（组织层）: Company → Department → Role → Employee（AI Agent）
  └─ 行业工厂（行业层）: FactorySpec = Skill + MCP + Knowledge + Workflow + Evaluation + Learning
      └─ 项目（项目层）: product → PRD → engineering → tasks
          └─ 任务（执行层）: 拆解 → 调度 → 执行 → 证据（M3 四部曲）
```

**每层流程性质（死板程度随层级递减）**

| 层 | 流程性质 | 交互方式 | 当前状态 |
|---|---|---|---|
| **公司层** | **决策型** — LLM 深度对话 | "我想开个 AI 软件公司" → LLM 理解 → 装配公司模板（部门/角色/预算/治理） | 🚧 数据模型+CLI 有（org/models.py + factory-org），对话未接 |
| **工厂层** | **配置型** — 选行业加载模板 | 选行业 → 加载 FactorySpec（Skill/知识/流程开箱即用） | 📐 FactorySpec 设计（§10） |
| **项目层** | **半结构化** — LLM 理解 + 规则兜底 | 产品发现：LLM 一次理解产出定义 + 智能追问（S10-099 进行中） | ✅ 流程有，LLM 介入 Sprint 中 |
| **任务层** | **结构化** — 规则 + 调度 | 拆解→调度→执行→证据（本来就该结构化） | ✅ M3 完成 |

**为什么每层性质不同（不是一刀切模板）**

```
高层 = 决策（用户自己都不知道要什么细节）→ LLM 深度理解 + 主动分析
低层 = 执行（任务明确可验证）→ 结构化规则 + 调度
中间 = 半结构化 → LLM 理解 + 规则兜底
死板程度: 公司(最灵活) → 工厂 → 项目 → 任务(最结构化)
```

**对话接入现状与目标**

```
现状: 对话只有一个入口 = 产品发现 → 创建项目（单层, 死板）
目标: 对话完整层级 — "建立公司" → "创建软件工厂" → "新建项目" → "开始开发"
     每层走适合的流程（公司=LLM 深度, 工厂=模板配置, 项目=LLM+规则, 任务=结构化）
org 层数据模型 + CLI 已存在（factory-org company create / employee hire / knowledge add）
→ 缺的是把各层 CLI/模型接进对话 + 每层 LLM 理解
```

**与现有机制关系**
- 多项目隔离（§7.2.2）: 公司 = 组织根, 项目挂公司下, 知识三层隔离（公司级/工厂级/项目级）
- 行业工厂（§10）: 工厂 = 行业配置层, 项目实例化工厂
- 治理（§6）: 公司级治理策略（预算/审批/合规）下发给工厂/项目

**结论**: AI Factory 从"项目工具"走向"公司 OS"的关键 = **四层流程引擎**——
公司（决策型 LLM）→ 工厂（配置型模板）→ 项目（半结构化）→ 任务（结构化）。
org 数据模型/CLI 已有, 逐层接进对话即完成跃迁。死板 ≠ 该有, 每层应有适合的流程。

---

**层级可扩展设计（2026-08-24 Founder 追问: 只有四层么? 需要预留口子么?）**

四层不是终点——**已知至少 3 个扩展**, 预留口子必须做, 但正确方式 =
**通用层级树 + 类型注册表**, 不是固定 N 层。

**已知扩展（org 已部分预留）**

| 扩展层 | 位置 | 说明 | 预留状态 |
|---|---|---|---|
| **集团**（公司之上） | parent_company | 多公司/集团递归嵌套 | ✅ org 已预留（Phase 21+） |
| **部门/团队**（公司之下） | Department | 组织单元（Solo 扁平 / Enterprise 嵌套） | ✅ org 已建模 |
| **工作流**（项目之内） | — | 项目内多流程实例并行（如 bug 流 + 功能流同时跑） | 📐 需设计 |
| 未来未知层 | — | 无法预知（租户/地域/生态...） | 靠通用机制兜底 |

**预留口子设计（通用层级树, 不是固定 N 层）**

```
1. 通用层级树: 每层 = 一个"节点类型", 注册表可加
   现在注册: company / factory / project / task
   未来注册: group / department / workflow / <新层>
2. 统一实体接口: 每层共享 {id, name, parent, type, flow_type}
   → 遍历/权限/数据隔离/审计 全通用（不用为每层重写）
3. 流程类型注册: 每层声明 flow_type（decision/config/semi/structured）
   → 新层自选流程类型, 不硬编码
4. 数据隔离沿祖先链: 知识/数据隔离 = 沿祖先链逐层过滤（N 层通用,
   不写死"三层"）——公司级/工厂级/项目级是当前实例, 不是上限
5. 对话入口注册: 每层可注册"创建对话流程"（"建立公司"/"创建工厂"/...）
   → 新层接对话 = 注册一个流程, 不改造核心
```

**一句话**: 预留口子不是"猜未来有几层", 而是**"任意层都能加"的机制**——
通用层级树 + 类型注册 + 统一接口 + 祖先链隔离。org 的 parent_company/
Department 已是这个机制的雏形, 泛化它即可。

---

**组织树 × 工作树正交（2026-08-24 Founder 澄清: 项目可能多部门协作/一部门一项目/
前期只要项目后期才要部门）**

核心: **组织（公司/部门）与 工作（项目/任务）不是严格父子, 是两套正交维度 + 关联**。

```
组织树（归属）:   Company → Department（可选, Solo 扁平可无部门）
工作树（拆解）:   Project → Task（M3 拆解）
关联（谁负责）:   Project ↔ Department（多对多, 可选）· Project.company_id（归属, 可选）
```

**渐进式使用（前期简单, 后期增强）**

```
Solo（前期）:  Project（无组织归属）→ 创建即用, 零配置
Enterprise（后期）: Company → Department → 关联 Project（挂组织, 无损升级）
升级路径: Project 后期挂 company/department —— 数据不动, 只加关联
  例: 前期"我想做个记账 App" → 直接建项目; 半年后"成立公司, 记账户归财务部"
      → 创建 Company + Department → 把项目关联过去（无迁移）
```

**多对多关联（项目 ↔ 部门）**

```
一个项目多部门: 跨部门协作（前端部 + 后端部共做一项目）
一个部门多项目: 部门负责多个项目
不关联: Solo 项目（无部门归属）
模型: project_departments 关联（或 Project.department_ids[]）, 多对多可选
```

**统一入口 + 便捷（一个入口创建任意层）**

```
一个"创建"入口（CLI + 对话）: factory create <type>
  company / department / project / task / (未来: group/workflow)
项目创建可选关联: --company X --departments A,B（不填 = Solo 最简）
便捷铁律: 前期默认最简（只建项目即可用）, 组织是"可选增强"不是"必填前置"
对话: "建个记账项目" → 直接建（Solo）· "成立公司把记账项目挂财务部" → 建组织+关联
```

**设计原则总结**

```
1. 组织与工作正交（不是父子）: 公司/部门管"归属", 项目/任务管"干活"
2. 渐进式: 先项目后组织, 无损升级（数据不动只加关联）
3. 多对多可选: 项目↔部门 协作/负责/独立 都支持
4. 统一入口: 一个 create 创建任意层, 前期最简后期增强
5. 与 §1.4.5 通用层级树衔接: 组织树/工作树都是"通用节点", 关联是额外边
```


### 1.5 可行性评估与实施取舍（把蓝图变成可执行计划）

> 2026-08-21 补充: 本方案书 21 章是"愿景+能力蓝图"；但缺**商业、成本、组织、指标、风险**五件套。
> 本节补上，使蓝图可执行、可测量、可取舍。

#### 1.5.1 总体可行性判断

- **作为愿景蓝图**：完整、可存档 ✅（21 章覆盖能力/治理/学习/工具/行业/安全/企业级）。
- **作为近期交付计划**：**严重超载** ❌——21 章多数是设计；终态（AI 时代的 SAP / 224 智能体 / 50+ 平台 / 企业级认证）是 SAP 用 50 年、数万工程师、数千亿投入达到的。当前 AI Factory = 120K 行、1 团队、v1.1.8。
- **结论**：必须分三档执行，只承诺近期档；其余存档为愿景，不承诺时间。

#### 1.5.2 实施取舍：三档优先级

| 档 | 时间 | 内容 | 明确**不做** |
|---|---|---|---|
| **近期** | ≤6 个月 | IT 工厂做透：repo/证据/审批/积压清道夫 + M2 多 Agent 实体 + M4 学习闭环 + 消息平台 P0（5 渠道） | 不做第二行业、不做知识图谱、不做企业认证 |
| **中期** | 1-2 年 | 行业复制（FactorySpec）+ 知识图谱简化版 + 安全合规框架 | 不做 50+ 全平台、不做国产化认证 |
| **长期（愿景）** | 不承诺 | AI 时代 SAP / 50+ 平台 / 国产化 ERP 对标 / "每人一家 AI 公司" | 仅作愿景与演进方向 |

**取舍原则**：每个里程碑以"一个真实用户场景跑通"为验收，不造壳；每轮新增能力必须能演示、能审计、能回滚。

#### 1.5.3 成本模型（多 Agent 的单位经济）

- **成本结构**：核心成本 = LLM token（多 Agent = 每次任务多次调用）。例：产品管线 7 角色 = 7 次 LLM 调用；一次"积压清道夫" sweep = N 个 issue × 每 issue 若干次调用（分诊/修复/证据/审批）。
- **可控手段**：预算护栏（budget.py）、规划/执行/评审分档路由（弱模型规划、强模型执行）、确定性兜底（依赖修复不调 LLM）、并行控制。
- **单位经济目标**：单个 issue 修复的综合边际成本应显著低于"人工修复成本"，否则"积压清道夫"不成立——这是 E7 ROI 的量化基础。

#### 1.5.4 商业模式（定位"AI 时代的 SAP"怎么赚钱）

- **定位**：不卖平台，卖"一件干完的活"（Backlog Sweeper）+ 治理信任（证据包 + 审批 + 记忆）。
- **客户分层**：
  - ① 个人/小团队：self-host 开源核心，免费或低价（获客 + 生态）
  - ② 中小企业：订阅制，按"干完的活"计价（如按 issue 修复/按 Agent 使用量）
  - ③ 大型企业：私有化部署 + 合规（数据主权/审计/SSO），年度许可（对标 SAP 企业级收费）
- **差异化护城河**（别人抄不动的组合）：**证据包 + 分级审批 + 组织记忆** —— 面向"敢不敢让 AI 进生产"的信任空白。
- **生态收入（长期）**：Agent/技能市场（组合、分享、交易，对标 SAP ABAP 生态 + OpenClaw 插件生态）。

#### 1.5.5 组织与人力（增量路径）

| 阶段 | 团队 | 交付 |
|---|---|---|
| 阶段一 | 1-2 人 + LLM agent 循环（当前 Claude/Hermes/Codex） | IT 工厂深度（近期档全部） |
| 阶段二 | 3-5 人（工程 + 1 产品 + 1 安全） | 行业复制 + 安全合规框架 |
| 阶段三 | 10+（工程/产品/安全/生态/BD） | 企业级认证 + Agent 生态 + 第二行业 |

**现实提醒**：21 章全部落地不是"再加几个 sprint"，而是"一家公司的多年投入"。近期只聚焦"IT 工厂一件干完的活"。

#### 1.5.6 量化成功指标（OKR/验收）

- **技术**：tests 全绿（基线 11856+）；每里程碑 1 个真实 E2E 场景跑通；修复成功率、失败恢复率、每任务成本可查。
- **产品**：新用户首次完成一件任务的时长；证据包是否让用户"看完就敢批"（可用性验收）。
- **商业**：付费转化率、续费率、ARR、单位经济（单活边际成本 < 人工成本）。

#### 1.5.7 集中风险清单

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 多 Agent 成本失控 | 高 | 高 | budget 护栏 + 分档路由 + 确定性兜底 |
| LLM 生成质量不可靠 | 高 | 高 | evaluator 5 层评分 + 模板兜底 + 事实锚定 |
| 设计与实现漂移 | 高 | 高 | §1.4 状态对照为锚点，每里程碑对照 |
| 竞品免费挤压 | 中 | 高 | 治理差异化（证据/审批/记忆），不拼"谁更会写码" |
| 企业不信任 AI 进生产 | 中 | 高 | 证据包 + 分级审批 + 数据主权，先切"没人干的活" |
| 范围过大导致失焦 | 高 | 高 | 三档取舍 + 每个里程碑一个真实场景 |
| 人力不足 | 高 | 高 | 聚焦 IT 工厂，LLM agent 循环补人力 |
| 合规/资质（信创/SOC2/等保） | 中 | 高 | 中期再议，近期不承诺企业认证 |


---

### 1.6 全文链路与思想总览（21 章一张图）★

> 2026-08-22 补充: 各章有内部流，缺一张"端到端主线"——本节把 21 章串成一条链路 + 思想主线。

#### 1.6.1 思想主线（五要素）

```
造专家（员工层）→ 有治理（可信层）→ 会学习（进化层）→ 可复制（行业层）→ 独立但统一（产品层）
```

#### 1.6.2 全文链路（想法 → 交付 → 进化 → 企业级）

```
用户想法（§一 定位）
  → 模块化架构承载（§二：热插拔→模块地图→模块即产品→统一契约→数据同步）
  → 任务拆解到原子（§三：3.7 递归原子 → 3.8 Plan+关键节点 → 3.9 整链调度）
  → 多 Agent 团队（§四：装配→分配 4.8→协作交接 4.7→执行）
  → 证据/审计（§五：5.1-5.6 审计+证据+追溯回放）
  → 可视化/监控（§五：5.7 可视化 → 5.8 监控 → 5.9 监控vs审计）
  → 治理卡口（§六：审批/预算/审计/闭环）
  → 学习进化（§七 学习 → §十七 自我进化五维）
  → 知识支撑（§八 RAG/存储分档 → §十九 知识图谱）
  → 工具/消息渠道（§九：工具生态 → 消息平台）
  → 行业工厂落地（§十：IT → 运维/电商/自媒体/数据/办公）
  → 交互（§十一：CLI/Web/IDE）
  → 演进路线（§十二：M1-M7）
  → 企业级（§十八 数据主权 → §二十 安全 → §二十一 国产化ERP）

参照系: §十五 竞品对比 · §十六 优势吸收
执行锚:  §1.4 状态对照 · §1.5 可行性取舍 · §2.10-2.11 统一契约
```

#### 1.6.3 完整性评估

| 维度 | 覆盖 | 完整 |
|---|---|---|
| 思想（为什么） | §一 定位/愿景/铁律 + §1.5 取舍 | ✅ |
| 架构（怎么承载） | §二 模块化全链路 | ✅ |
| 能力（做什么） | §三~§九 拆解/团队/观测/治理/学习/知识/工具 | ✅ |
| 落地（在哪用） | §十 行业 + §十一 交互 + §十二 路线 | ✅ |
| 差异化纵深 | §十五~§二十一 竞品/进化/主权/安全/企业级 | ✅ |
| 执行锚 | §1.4 状态 + §1.5 取舍 + 待办清单（M2-M7） | ✅ |

**结论**：21 章覆盖"思想→架构→能力→落地→纵深→执行锚"完整闭环；每章有"设计+实现锚点+完成度"；无空壳、无超前、无错位。


### 1.7 产品验收标准（什么才算"做到 / 做好"）★

> 2026-08-22 补充（用户提问）: 产品验收标准此前零散——补**集中、可度量**的八大维度 + 里程碑验收。

#### 1.7.1 八大维度验收标准（产品级，可度量）

| 维度 | 验收标准 | 量化目标 |
|---|---|---|
| **功能** | 想法→交付全链路跑通（一句话→7专家→PRD→工程→代码→测试） | 真实场景 1 个 |
| **性能** | 任务延迟 / 并行 / 吞吐 | 原子任务 ≤10min · 并行 ≥3 · p95 达标 |
| **质量** | 任务成功率 / 测试通过率 | 成功率 >80% · 交付测试全绿（基线 11856+） |
| **安全** | 8 威胁防御覆盖（§20） | 高风险必批 · 沙箱隔离 · 无已知高危漏洞 |
| **可用性** | 首次完成任务时长 / 证据可批性 | 新人 <30min 完成一件活 · 证据让用户"看完敢批" |
| **治理** | 审批 / 预算 / 审计闭环 | 全动作可审计 · 超预算阻断 · PRD/计划必批 |
| **数据** | 事实源/投影一致 · 升级无痛 | 同步滞后 <60s · 升档不丢数据（§8.5.8） |
| **商业** | 单位经济 | 单活边际成本 < 人工成本（§1.5.3） |
| **演进** | 自我能力闭环 | 第二次同类任务引用第一次经验（M4 验收） |

#### 1.7.2 验收方式（不靠"写完文档"）

```
真实 E2E: 用户环境跑锚点场景（"我要做CRM" 全链路）
自动化:   tests 全绿基线 + 契约测试套件（§2.11.4 独立产品门槛）
安全:     SAST/依赖扫描/渗透（§20.12）
自我完善: A/B 验证（§17.16）
状态联动: 📐 → ✅ 以验收通过为准，§1.4 随验收更新
```

#### 1.7.3 里程碑验收（对齐 §12 + 待办清单）

| 里程碑 | 验收锚点 |
|---|---|
| M1/M1a/M1b ✅ | repo 改文件+测试绿 · 证据包可见 · 审批分级 · 清道夫闭环 |
| M2 | `让PM分析` → 7 专家真实产出，parent_artifact 互引，created_by=agent_id |
| M3 | 递归拆到原子 · 关键路径/并行调度 · 需求变更 PRD v2 |
| M4 | 第二次同类任务引用经验 · 低样本不主导 · 修复成功率 >80% |
| M5 | 一句话→交付全链路 · Web 仪表盘 · 消息 P0 5 渠道 · 执行重放 |
| M6 | 第二行业同底座最小闭环 |
| M7 | IDE 内调内核 · 沙箱长任务 |

#### 1.7.4 验收原则

```
1. 验收 = 真实可演示结果，不是文件/API/状态显示
2. 每个里程碑独立验收；不过验收 → 不进入下一里程碑
3. 量化目标（成功率/延迟/成本）进 CI 或 E2E 断言
4. 📐 变 ✅ 的唯一凭证 = 验收通过（§1.4 联动）
```

## 二、模块化热插拔架构设计

> 2026-08-21 补充: 系统基础架构 — 每个模块独立、可热插拔、可替换、可单独配置与版本管理。


> 本文档定义AI Factory的模块化架构，确保**每个模块独立、可热插拔、可替换、可版本独立演进**。这是"一切皆插件"架构的系统化落地。


### 2.1 热插拔架构核心原则

#### 2.1.1 设计原则

| 原则 | 说明 | 体现 |
|---|---|---|
| **零信任依赖** | 核心引擎不信任任何模块，假设模块可能失效 | 所有模块调用都有超时、重试、降级、熔断 |
| **接口契约** | 模块间仅通过标准化接口通信 | 接口版本化，向后兼容 |
| **动态注册** | 模块运行时注册，无需重启 | 服务发现 + 心跳检测 |
| **隔离运行** | 模块故障不影响其他模块 | 进程级/容器级隔离 |
| **独立版本** | 每个模块独立版本管理 | 模块可独立升级/回滚 |
| **优雅降级** | 模块不可用时系统仍可工作 | 降级策略 + 默认实现 |

#### 2.1.2 模块独立性定义

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          模块独立性的五个维度                                       │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 部署独立 (Deployment Independence)                                      │   │
│  │    • 每个模块可独立部署                                                    │   │
│  │    • 模块可以运行在独立的进程/容器中                                        │   │
│  │    • 模块版本独立                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 2. 配置独立 (Configuration Independence)                                   │   │
│  │    • 每个模块有自己的配置                                                 │   │
│  │    • 配置可动态更新，无需重启                                              │   │
│  │    • 配置变更自动生效                                                      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 3. 生命周期独立 (Lifecycle Independence)                                   │   │
│  │    • 模块可独立启动/停止/重启                                              │   │
│  │    • 模块启动顺序不影响整体                                                 │   │
│  │    • 模块崩溃不影响其他模块                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 4. 数据独立 (Data Independence)                                             │   │
│  │    • 每个模块有自己的数据存储                                               │   │
│  │    • 不直接读写其他模块的数据                                               │   │
│  │    • 通过接口交换数据                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 5. 故障独立 (Failure Independence)                                         │   │
│  │    • 模块故障不传播                                                         │   │
│  │    • 故障模块自动隔离                                                       │   │
│  │    • 降级策略确保核心功能可用                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 2.2 模块化架构全景

#### 2.2.1 模块全景图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                      AI Factory 模块化架构（热插拔全景）                             │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         入口层模块 (Gateway Layer)                          │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ CLI模块     │  │ TUI模块     │  │ Web模块     │  │ IM适配器    │       │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         核心调度层 (Orchestration Layer)                    │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │Orchestrator │  │  Scheduler  │  │  Planner    │  │  Governor   │       │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Agent执行层 (Execution Layer)                       │   │
│  │                                                                             │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │   │
│  │  │ Planner  │  │Executor │  │Reviewer │  │Debugger │  │Governor │         │   │
│  │  │ (可插拔) │  │ (可插拔)│  │ (可插拔)│  │ (可插拔)│  │ (可插拔)│         │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘         │   │
│  │                                                                             │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐                       │   │
│  │  │ Learner │  │ Healer  │  │ Monitor │  │Improver │                       │   │
│  │  │ (可插拔)│  │ (可插拔)│  │ (可插拔)│  │ (可插拔)│                       │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         能力层 (Capability Layer)                          │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ RAG模块     │  │ Tool模块    │  │ LLM模块     │  │ Skill模块    │       │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                        │   │
│  │  │ MCP模块     │  │ Sandbox模块 │  │ Notifier模块 │                        │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │                        │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         基础设施层 (Infrastructure Layer)                   │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ Service     │  │ Module      │  │ Message     │  │ Config      │       │   │
│  │  │ Discovery   │  │ Registry    │  │ Bus         │  │ Center      │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 完整模块清单

| 层级 | 模块 | 是否必选 | 可插拔 | 说明 |
|---|---|---|---|---|
| **入口层** | CLI | ❌ | ✅ | 至少一个入口 |
| | TUI | ❌ | ✅ | |
| | Web | ❌ | ✅ | |
| | IM Adapter | ❌ | ✅ | |
| **调度层** | Orchestrator | ✅ | ❌ | 核心引擎，不可替换 |
| | Scheduler | ✅ | ⚠️ | 可换调度算法 |
| | Planner | ✅ | ⚠️ | 可换拆解策略 |
| | Governor | ❌ | ✅ | 可换治理实现 |
| **执行层** | Planner Agent | ❌ | ✅ | |
| | Executor Agent | ✅ | ⚠️ | 至少一个执行者 |
| | Reviewer Agent | ❌ | ✅ | |
| | Debugger Agent | ❌ | ✅ | |
| | Learner Agent | ❌ | ✅ | |
| | Healer | ❌ | ✅ | |
| | Monitor | ❌ | ✅ | |
| | Improver | ❌ | ✅ | |
| **能力层** | RAG | ❌ | ✅ | |
| | Tool | ❌ | ✅ | |
| | LLM | ✅ | ⚠️ | 至少一个Provider |
| | Skill | ❌ | ✅ | |
| | MCP | ❌ | ✅ | |
| | Sandbox | ❌ | ✅ | |
| | Notifier | ❌ | ✅ | |
| **基础层** | Service Discovery | ✅ | ❌ | 基础服务 |
| | Module Registry | ✅ | ❌ | 基础服务 |
| | Message Bus | ✅ | ❌ | 基础服务 |
| | Config Center | ✅ | ❌ | 基础服务 |


### 2.3 热插拔机制详细设计

#### 2.3.1 模块注册与发现

```python
#### ============ 模块注册表 ============

class ModuleMetadata:
    """模块元数据"""
    name: str
    version: str
    description: str
    dependencies: List[str]  # 依赖的其他模块
    capabilities: List[str]  # 提供的能力
    health_check: Optional[str]  # 健康检查端点
    config_schema: Dict  # 配置Schema
    status: str  # active | inactive | degraded

class ModuleRegistry:
    """
    模块注册表——所有模块在此注册
    支持：动态注册/注销、健康检查、依赖管理
    """
    
    def __init__(self):
        self._modules: Dict[str, ModuleMetadata] = {}
        self._instances: Dict[str, Any] = {}
        self._health_status: Dict[str, str] = {}
        self._listeners: List[ModuleEventListener] = []
    
    # ========== 注册/注销 ==========
    
    def register(self, name: str, instance: Any, metadata: ModuleMetadata) -> bool:
        """
        注册模块
        
        热插拔支持：
        - 如果模块已存在，替换实例（无需重启）
        - 版本检查：新版本必须兼容
        - 依赖检查：依赖模块必须已注册
        """
        if name in self._modules:
            # 版本检查
            if not self._is_version_compatible(metadata.version, self._modules[name].version):
                raise VersionIncompatibleError(
                    f"Module {name}: version {metadata.version} incompatible with existing {self._modules[name].version}"
                )
            # 热替换
            self._unregister_module(name, graceful=True)
        
        # 依赖检查
        for dep in metadata.dependencies:
            if dep not in self._modules:
                raise MissingDependencyError(f"Missing dependency: {dep}")
        
        self._modules[name] = metadata
        self._instances[name] = instance
        self._health_status[name] = "starting"
        
        # 通知监听器
        self._notify(ModuleEvent(type="registered", name=name, version=metadata.version))
        
        return True
    
    def unregister(self, name: str, graceful: bool = True) -> bool:
        """注销模块（热拔插）"""
        if name not in self._modules:
            return False
        
        # 检查是否有其他模块依赖此模块
        dependents = self._find_dependents(name)
        if dependents and graceful:
            # 通知依赖者正在注销
            for dep in dependents:
                self._notify_dependency_deprecating(dep, name)
        
        return self._unregister_module(name, graceful)
    
    def _unregister_module(self, name: str, graceful: bool) -> bool:
        """执行注销"""
        # 1. 停止模块（优雅关闭）
        instance = self._instances.get(name)
        if instance and hasattr(instance, 'shutdown'):
            instance.shutdown()
        
        # 2. 移除
        del self._modules[name]
        del self._instances[name]
        del self._health_status[name]
        
        # 3. 通知
        self._notify(ModuleEvent(type="unregistered", name=name))
        
        return True
    
    # ========== 查询 ==========
    
    def get(self, name: str) -> Optional[Any]:
        """获取模块实例"""
        return self._instances.get(name)
    
    def get_metadata(self, name: str) -> Optional[ModuleMetadata]:
        """获取模块元数据"""
        return self._modules.get(name)
    
    def list_available(self) -> List[ModuleMetadata]:
        """列出所有已注册模块"""
        return list(self._modules.values())
    
    def find_by_capability(self, capability: str) -> List[str]:
        """按能力查找模块"""
        return [
            name for name, meta in self._modules.items()
            if capability in meta.capabilities
        ]
    
    # ========== 健康检查 ==========
    
    async def health_check_all(self) -> Dict[str, str]:
        """检查所有模块健康状态"""
        results = {}
        for name, instance in self._instances.items():
            results[name] = await self._health_check_module(name, instance)
        self._health_status.update(results)
        return results
    
    async def _health_check_module(self, name: str, instance: Any) -> str:
        """检查单个模块健康"""
        if not hasattr(instance, 'health_check'):
            return "unknown"
        
        try:
            result = await asyncio.wait_for(
                instance.health_check(),
                timeout=5.0
            )
            return "healthy" if result else "unhealthy"
        except Exception:
            return "unhealthy"
    
    # ========== 事件监听 ==========
    
    def add_listener(self, listener: ModuleEventListener):
        """添加模块事件监听器"""
        self._listeners.append(listener)
    
    def _notify(self, event: ModuleEvent):
        for listener in self._listeners:
            listener.on_module_event(event)
```

#### 2.3.2 模块接口标准

```python
#### ============ 模块接口标准 ============

class Module(ABC):
    """所有模块的基类"""
    
    # ========== 模块元信息 ==========
    
    @property
    @abstractmethod
    def module_name(self) -> str:
        """模块名称（唯一标识）"""
        pass
    
    @property
    @abstractmethod
    def module_version(self) -> str:
        """模块版本（语义化版本）"""
        pass
    
    @property
    @abstractmethod
    def module_description(self) -> str:
        """模块描述"""
        pass
    
    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """模块提供的能力列表"""
        pass
    
    @property
    def dependencies(self) -> List[str]:
        """依赖的其他模块名称"""
        return []
    
    @property
    def config_schema(self) -> Dict:
        """配置Schema（用于配置验证和动态更新）"""
        return {}
    
    # ========== 生命周期 ==========
    
    @abstractmethod
    async def start(self) -> None:
        """启动模块"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止模块"""
        pass
    
    async def restart(self) -> None:
        """重启模块（默认实现：stop + start）"""
        await self.stop()
        await self.start()
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    # ========== 配置管理 ==========
    
    async def update_config(self, config: Dict) -> bool:
        """
        动态更新配置（无需重启）
        
        返回：是否更新成功
        """
        # 默认实现：验证 → 应用
        if self._validate_config(config):
            self._apply_config(config)
            return True
        return False
    
    def _validate_config(self, config: Dict) -> bool:
        """验证配置（子类可覆盖）"""
        return True
    
    def _apply_config(self, config: Dict) -> None:
        """应用配置（子类可覆盖）"""
        pass
    
    # ========== 状态查询 ==========
    
    async def get_status(self) -> ModuleStatus:
        """获取模块详细状态"""
        return ModuleStatus(
            name=self.module_name,
            version=self.module_version,
            state=self._state,
            healthy=await self.health_check(),
            uptime=self._uptime,
            metrics=await self.get_metrics(),
        )
    
    async def get_metrics(self) -> Dict:
        """获取模块指标（子类可覆盖）"""
        return {}
    
    # ========== 版本兼容性 ==========
    
    @classmethod
    def is_compatible_with(cls, version: str) -> bool:
        """检查是否兼容指定版本"""
        # 默认：Major版本相同即兼容
        current = cls.module_version.fget(cls).split('.')
            target = version.split('.')
        return current[0] == target[0]
```

#### 2.3.3 模块间通信机制

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          模块间通信机制（解耦 + 热插拔友好）                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         通信方式                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式1: 消息总线 (Message Bus) — 推荐                              │   │   │
│  │  │   • 发布/订阅模式                                                  │   │   │
│  │  │   • 模块间完全解耦                                                  │   │   │
│  │  │   • 支持异步通信                                                   │   │   │
│  │  │   • 消息持久化（模块重启后恢复）                                    │   │   │
│  │  │   • 示例: Orchestrator 发布任务 → Executor 订阅执行               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式2: 接口调用 (RPC) — 适合同步请求                                │   │   │
│  │  │   • 通过 Registry 获取目标模块实例                                   │   │   │
│  │  │   • 直接调用接口方法                                                │   │   │
│  │  │   • 必须包含超时 + 降级                                             │   │   │
│  │  │   • 示例: Orchestrator 调用 Planner.get_plan()                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式3: 共享存储 (Shared Storage) — 适合状态共享                     │   │   │
│  │  │   • 通过 Working Memory 共享状态                                     │   │   │
│  │  │   • 不直接依赖其他模块                                              │   │   │
│  │  │   • 示例: 所有 Agent 读写 Working Memory                            │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         通信保障机制                                        │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  超时控制     │  │  重试机制     │  │  降级策略     │                   │   │
│  │  │  (Timeout)   │  │  (Retry)      │  │  (Fallback)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  熔断机制     │  │  背压控制     │  │  死信队列     │                   │   │
│  │  │  (Circuit    │  │  (Backpressure)│  │  (Dead       │                   │   │
│  │  │   Breaker)   │  │               │  │   Letter)    │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.3.4 消息总线实现

```python
#### ============ 消息总线 ============

from typing import Dict, Any, Callable, Awaitable, List
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import uuid

@dataclass
class Message:
    """消息对象"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # 消息类型
    source: str  # 发送模块名
    target: Optional[str] = None  # 目标模块名（None=广播）
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.now)
    ttl: int = 300  # 生存时间（秒）
    priority: int = 5  # 优先级 1-10
    correlation_id: Optional[str] = None  # 关联ID

class MessageBus:
    """
    消息总线——模块间通信的中央通道
    
    特性：
    - 发布/订阅模式
    - 支持点对点和广播
    - 消息持久化（可选）
    - 死信队列
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Message], Awaitable[None]]]] = {}
        self._dead_letter_queue: List[Message] = []
        self._is_running = False
    
    def subscribe(self, message_type: str, handler: Callable[[Message], Awaitable[None]]) -> str:
        """
        订阅消息
        
        参数：
            message_type: 消息类型（* 表示所有消息）
            handler: 处理函数
        
        返回：订阅ID（用于取消订阅）
        """
        if message_type not in self._subscribers:
            self._subscribers[message_type] = []
        self._subscribers[message_type].append(handler)
        return f"{message_type}_{len(self._subscribers[message_type])-1}"
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        # 实现略
        pass
    
    async def publish(self, message: Message) -> None:
        """
        发布消息
        
        热插拔支持：
        - 目标模块不存在 → 放入死信队列
        - 目标模块未启动 → 缓存消息，待模块启动后重发
        """
        # 1. TTL检查
        if (datetime.now() - message.timestamp).seconds > message.ttl:
            return  # 消息过期
        
        # 2. 查找目标
        if message.target:
            # 点对点
            await self._send_to_target(message)
        else:
            # 广播
            await self._broadcast(message)
    
    async def _send_to_target(self, message: Message) -> None:
        """发送到指定目标"""
        handlers = self._subscribers.get(message.type, [])
        handlers += self._subscribers.get("*", [])  # 通配符
        
        for handler in handlers:
            try:
                await asyncio.wait_for(handler(message), timeout=10.0)
            except asyncio.TimeoutError:
                # 超时 → 放入死信队列
                self._dead_letter_queue.append(message)
            except Exception:
                # 其他异常 → 记录日志，继续
                pass
    
    async def _broadcast(self, message: Message) -> None:
        """广播消息"""
        for msg_type, handlers in self._subscribers.items():
            if msg_type == message.type or msg_type == "*":
                for handler in handlers:
                    try:
                        await asyncio.wait_for(handler(message), timeout=10.0)
                    except Exception:
                        pass
    
    async def replay_dead_letter(self) -> None:
        """重放死信队列（模块恢复后）"""
        dead_messages = self._dead_letter_queue.copy()
        self._dead_letter_queue = []
        for msg in dead_messages:
            await self.publish(msg)
```

#### 2.3.5 降级与熔断机制

```python
#### ============ 降级与熔断 ============

class CircuitBreaker:
    """
    熔断器——防止级联故障
    
    状态：
    - CLOSED: 正常（允许调用）
    - OPEN: 熔断（拒绝调用）
    - HALF_OPEN: 半开（尝试恢复）
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,   # 失败次数阈值
        timeout_seconds: int = 60,    # 熔断超时时间
        half_open_max_calls: int = 3, # 半开状态最大调用数
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls
        
        self._state = "CLOSED"
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0
    
    async def call(self, func: Callable, fallback: Callable = None) -> Any:
        """
        调用受保护函数
        
        热插拔支持：
        - 模块不可用 → 自动熔断 → 调用降级函数
        """
        if self._state == "OPEN":
            if self._should_attempt_half_open():
                self._state = "HALF_OPEN"
                self._half_open_calls = 0
            else:
                # 熔断中 → 直接降级
                return await self._fallback(fallback)
        
        try:
            result = await func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                self._failure_count = 0
                self._last_failure_time = datetime.now()
            return await self._fallback(fallback)
    
    def _should_attempt_half_open(self) -> bool:
        if self._last_failure_time is None:
            return True
        elapsed = (datetime.now() - self._last_failure_time).seconds
        return elapsed > self.timeout_seconds
    
    def _on_success(self):
        if self._state == "HALF_OPEN":
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                self._state = "CLOSED"
                self._failure_count = 0
        else:
            self._failure_count = 0
    
    def _on_failure(self):
        self._failure_count += 1
        if self._state == "CLOSED" and self._failure_count >= self.failure_threshold:
            self._state = "OPEN"
            self._last_failure_time = datetime.now()
    
    async def _fallback(self, fallback: Callable) -> Any:
        """调用降级函数"""
        if fallback:
            return await fallback()
        return None


class FallbackRegistry:
    """降级策略注册表"""
    
    def __init__(self):
        self._fallbacks: Dict[str, Callable] = {}
    
    def register(self, module_name: str, fallback: Callable):
        self._fallbacks[module_name] = fallback
    
    def get(self, module_name: str) -> Optional[Callable]:
        return self._fallbacks.get(module_name)
    
    def get_default(self, module_name: str) -> Callable:
        """获取默认降级策略"""
        return lambda: {
            "status": "degraded",
            "message": f"Module {module_name} unavailable, using default fallback"
        }
```


### 2.4 各模块独立配置与版本管理

#### 2.4.1 模块配置管理

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          模块配置管理                                              │
│                                                                                     │
│  配置结构:                                                                         │
│                                                                                     │
│  ~/.factory/modules/                                                               │
│  ├── orchestrator/                                                                 │
│  │   └── config.yaml          # Orchestrator 配置                                 │
│  ├── executor/                                                                     │
│  │   ├── config.yaml          # Executor 配置                                     │
│  │   └── v1/                  # 版本v1配置                                        │
│  ├── rag/                                                                          │
│  │   ├── config.yaml          # RAG 配置                                          │
│  │   └── custom/                                                                   │
│  │       └── vector_store.yaml # 自定义向量库配置                                 │
│  ├── llm/                                                                          │
│  │   ├── config.yaml          # LLM 配置                                          │
│  │   ├── deepseek.yaml        # DeepSeek 专属配置                                 │
│  │   └── providers/           # Provider 插件目录                                  │
│  │       └── custom_provider.py                                                    │
│  └── ...                                                                           │
│                                                                                     │
│  配置热加载:                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 1. 监听配置目录变化                                                        │   │
│  │ 2. 检测到配置变更 → 验证新配置                                             │   │
│  │ 3. 验证通过 → 应用新配置（无需重启）                                       │   │
│  │ 4. 验证失败 → 回滚到旧配置 + 告警                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.4.2 版本兼容性管理

```python
#### ============ 版本兼容性管理 ============

class VersionManager:
    """模块版本管理器"""
    
    def __init__(self):
        self._versions: Dict[str, str] = {}
        self._compatibility_matrix: Dict[Tuple[str, str], bool] = {}
    
    def register_version(self, module: str, version: str):
        """注册模块版本"""
        self._versions[module] = version
    
    def set_compatibility(self, module_a: str, version_a: str, 
                          module_b: str, version_b: str, 
                          compatible: bool):
        """设置两个模块版本的兼容性"""
        key = (f"{module_a}@{version_a}", f"{module_b}@{version_b}")
        self._compatibility_matrix[key] = compatible
    
    def check_compatibility(self, module_a: str, module_b: str) -> bool:
        """检查两个模块当前版本是否兼容"""
        version_a = self._versions.get(module_a)
        version_b = self._versions.get(module_b)
        
        if not version_a or not version_b:
            return False
        
        key = (f"{module_a}@{version_a}", f"{module_b}@{version_b}")
        return self._compatibility_matrix.get(key, False)
    
    def get_compatible_versions(self, module: str, target_version: str) -> List[str]:
        """获取与指定版本兼容的所有版本"""
        compatible = []
        for version in self._versions.values():
            if self._is_compatible(target_version, version):
                compatible.append(version)
        return compatible
    
    def _is_compatible(self, v1: str, v2: str) -> bool:
        """语义化版本兼容性检查（Major相同即兼容）"""
        try:
            m1 = int(v1.split('.')[0])
            m2 = int(v2.split('.')[0])
            return m1 == m2
        except Exception:
            return v1 == v2
```

#### 2.4.3 热插拔场景示例

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          热插拔场景示例                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景1: 替换LLM Provider                                                    │   │
│  │                                                                             │   │
│  │  1. 注册新Provider: llm.register("openai", OpenAIProvider())               │   │
│  │  2. 系统检测到新Provider                                                    │   │
│  │  3. 验证新Provider健康: health_check() → ✓                                │   │
│  │  4. 切换默认Provider: llm.set_default("openai")                           │   │
│  │  5. 正在运行的任务继续使用旧Provider                                       │   │
│  │  6. 新任务使用新Provider                                                    │   │
│  │  7. 旧Provider在无任务后自动回收                                            │   │
│  │                                                                             │   │
│  │  影响: 零中断                                                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景2: RAG模块升级                                                         │   │
│  │                                                                             │   │
│  │  1. 新版本RAG模块: rag_v2.py                                                │   │
│  │  2. 注册新模块: registry.register("rag_v2", RAGV2())                       │   │
│  │  3. 版本检查: v1.0.0 → v2.0.0 (Major变更) → 不兼容                        │   │
│  │  4. 系统通知: "RAG v2.0.0 与现有模块不兼容，请确认升级"                    │   │
│  │  5. 用户确认升级                                                           │   │
│  │  6. 系统逐步迁移: 新任务使用v2，旧任务继续用v1                            │   │
│  │  7. v1无任务后自动停止                                                      │   │
│  │                                                                             │   │
│  │  影响: 任务级别的平滑迁移                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景3: 模块故障自动隔离                                                     │   │
│  │                                                                             │   │
│  │  1. Monitor检测到Executor模块健康检查失败                                  │   │
│  │  2. 熔断器自动开启: CircuitBreaker.open()                                 │   │
│  │  3. 系统切换: 新任务使用备用Executor (降级)                                │   │
│  │  4. 正在运行的任务: 等待当前任务完成，不中断                               │   │
│  │  5. 故障模块自动重启: executor.restart()                                   │   │
│  │  6. 健康检查通过: 熔断器半开 → 逐步恢复                                    │   │
│  │                                                                             │   │
│  │  影响: 单个模块故障不影响整体                                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景4: 新增行业工厂                                                         │   │
│  │                                                                             │   │
│  │  1. 下载工厂模板: factory_template_ecommerce.yaml                          │   │
│  │  2. 注册工厂: factory.register("ecommerce", EcommerceFactory())            │   │
│  │  3. 系统自动: 加载Skill → 注册MCP → 初始化知识库                          │   │
│  │  4. 工厂立即可用: factory.use("ecommerce")                                │   │
│  │                                                                             │   │
│  │  影响: 新能力即插即用                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 2.5 与现有架构的整合清单

| 项目 | 原设计 | 新增设计 | 是否兼容 |
|---|---|---|---|
| **模块注册** | 无 | ModuleRegistry | ✅ 新增 |
| **模块接口** | 部分（Tool/Agent接口） | 统一Module接口 | ⚠️ 需适配 |
| **消息通信** | 间接（Working Memory） | MessageBus | ✅ 补充 |
| **熔断降级** | 无 | CircuitBreaker | ✅ 新增 |
| **版本管理** | 无 | VersionManager | ✅ 新增 |
| **健康检查** | 无 | health_check() | ✅ 新增 |
| **配置热加载** | 无 | Config监听 | ✅ 新增 |
| **模块生命周期** | 无 | start/stop/restart | ✅ 新增 |


### 2.6 实施优先级

| 优先级 | 能力 | 说明 |
|---|---|---|
| **P0** | ModuleRegistry | 模块管理基础 |
| **P0** | Module接口标准 | 所有模块统一接口 |
| **P0** | 健康检查 | 基础监控 |
| **P1** | MessageBus | 模块间通信 |
| **P1** | 配置热加载 | 动态配置 |
| **P1** | 熔断降级 | 鲁棒性 |
| **P2** | 版本管理 | 兼容性 |
| **P2** | 自动发现 | 服务发现 |


*本文档定义AI Factory的模块化热插拔架构，确保所有模块可独立部署、升级、替换，系统整体不中断。*


### 2.7 积木式架构（对标 SAP 可组合架构）

> 2026-08-21 补充: 借鉴 SAP "可组合架构 + Clean Core + 最佳实践库" — L1 技术积木 / L2 能力积木 / L3 行业积木三层。

这是一个**从"做什么"到"怎么做"的关键跃迁**。

SAP的"搭积木"体现在三个层面：**技术层面**（模块化架构）、**产品层面**（预置最佳实践库）、**生态层面**（合作伙伴可扩展）。AI Factory要实现对标，需要在这三个层面同时构建能力。

---

#### 一、核心理念：积木式架构的三个层次

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          积木式架构三层次                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 行业积木（面向用户）                                                    │   │
│  │   • 行业工厂模板（软件开发工厂/运维工厂/电商工厂...）                       │   │
│  │   • 用户就像搭积木一样组合行业能力                                          │   │
│  │   • 对标：SAP Best Practices + 行业解决方案                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 能力积木（面向扩展者）                                                  │   │
│  │   • Skill（原子能力）、Workflow（流程模板）、Knowledge（知识包）            │   │
│  │   • 开发者可自由组合、扩展、发布新能力                                      │   │
│  │   • 对标：SAP BTP + ABAP生态 + 扩展点                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 技术积木（面向架构师）                                                  │   │
│  │   • 模块化热插拔架构（§二）——所有组件可替换                                │   │
│  │   • 统一接口契约——模块间通过标准接口通信                                    │   │
│  │   • 对标：SAP S/4HANA可组合架构 + Clean Core                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

#### 二、怎么做：分步实施路径

#### 第一步：夯实技术积木（L1）——让系统本身可拆可装

这是对标SAP"可组合架构"的基础。**我们已经设计了§二模块化热插拔架构，现在要做的是将其推向企业级标准。**

#### 2.1 定义"积木"的接口标准

| 积木类型 | 接口标准 | 说明 |
|---|---|---|
| **Agent积木** | `AgentInterface` | 任何Agent实现此接口即可被编排调度 |
| **Tool积木** | `ToolInterface` | 任何工具实现此接口即可被Agent调用 |
| **Skill积木** | `SkillInterface` | 任何Skill实现此接口即可被复用和组合 |
| **Knowledge积木** | `KnowledgeInterface` | 任何知识源实现此接口即可被RAG检索 |
| **Factory积木** | `FactoryInterface` | 任何行业工厂实现此接口即可被实例化 |

#### 2.2 建立"积木注册中心"

```python
#### 对标SAP的"服务注册"能力
class BrickRegistry:
    """
    积木注册中心 —— 所有能力积木在此注册、发现、版本管理
    对标SAP BTP的Service Registry
    """
    
    def register_brick(self, brick: Brick) -> RegistrationResult:
        """注册积木 —— 上线新能力"""
        # 自动检测接口兼容性
        # 自动版本管理
        # 自动发布到市场
        
    def discover_bricks(self, capability: str) -> List[Brick]:
        """发现积木 —— 按能力搜索"""
        # 按能力标签搜索
        # 按质量评分排序
        # 按使用热度推荐
        
    def compose_bricks(self, bricks: List[Brick]) -> CompositionResult:
        """组合积木 —— 自动检测依赖冲突和兼容性"""
        # 依赖关系自动解析
        # 版本兼容性自动检查
        # 自动生成组合方案
```

#### 2.3 实现"Clean Core"战略

SAP的"Clean Core"理念——核心保持标准化，扩展在外围。

| SAP Clean Core理念 | AI Factory对应实现 |
|---|---|
| 核心ERP保持整洁 | 核心引擎（Orchestrator/Scheduler）保持标准，不修改 |
| 扩展通过官方扩展点 | 所有自定义通过Skill/MCP/Agent注册实现，不修改核心 |
| 平滑升级不受定制影响 | 核心引擎可独立升级，不破坏已注册的积木 |
| 最佳实践自动更新 | 行业工厂模板可在线更新，不影响用户定制内容 |

---

#### 第二步：构建能力积木（L2）——让能力和知识可组合

这是对标SAP"最佳实践库"和"ABAP生态"的关键。

#### 2.4 定义积木的"粒度"

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          能力积木的粒度体系                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 微型积木（Micro-Brick）——最小组件                                           │   │
│  │   • 单个Tool：read_file, search_code, run_command                          │   │
│  │   • 单个Prompt模板                                                          │   │
│  │   • 单个评估规则                                                            │   │
│  │   • 类比：SAP的单个API/Function Module                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 中积木（Mid-Brick）——可独立使用的能力                                      │   │
│  │   • 单个Skill：analyze_memory_leak, generate_test_cases                    │   │
│  │   • 单个Workflow模板：bug_fix_workflow, feature_development               │   │
│  │   • 单个知识包：SpringBoot最佳实践、K8s运维手册                           │   │
│  │   • 类比：SAP的Best Practice / 预配置流程                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 宏积木（Macro-Brick）——完整行业解决方案                                    │   │
│  │   • 行业工厂：软件开发工厂、运维工厂、电商工厂...                         │   │
│  │   • 包含：Skills + Workflows + Knowledge + MCP + Evaluation + Learning   │   │
│  │   • 类比：SAP的Industry Solution（如SAP for Retail）                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.5 建立"积木市场"（Brick Marketplace）

对标SAP的SAP Store和ABAP社区。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          积木市场（Brick Marketplace）                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 官方积木                                                                   │   │
│  │   • AI Factory官方开发和维护                                                │   │
│  │   • 经过严格测试和验证                                                      │   │
│  │   • 对标：SAP官方Best Practices                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 社区积木                                                                   │   │
│  │   • 合作伙伴和开发者贡献                                                    │   │
│  │   • 经社区审核和评分                                                        │   │
│  │   • 对标：SAP ABAP社区 + 第三方扩展                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 企业私密积木                                                               │   │
│  │   • 企业内部开发的专属积木                                                  │   │
│  │   • 仅企业内部可见和使用                                                    │   │
│  │   • 对标：SAP客户自开发 + 内部最佳实践库                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  积木质量评分体系:                                                                  │
│   • 使用次数 × 权重    (反映受欢迎程度)                                            │
│   • 成功率 × 权重      (反映可靠性)                                                │
│   • 用户评分 × 权重    (反映满意度)                                                │
│   • 维护活跃度          (反映持续维护能力)                                          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.6 积木的组合与编排

```python
#### 积木组合引擎 —— 用户搭积木的"胶水"
class BrickComposer:
    """
    积木组合引擎
    对标SAP Workflow + BTP Integration Suite
    """
    
    def compose(self, bricks: List[Brick]) -> ComposedSolution:
        """
        组合多个积木为一个完整方案
        
        输入: [read_file Skill, analyze_code Skill, generate_test Skill]
        输出: "代码分析+测试生成" 组合方案
        """
        # 1. 依赖分析：自动检测积木间的依赖关系
        # 2. 接口匹配：自动适配输入输出格式
        # 3. 冲突检测：检测并解决兼容性问题
        # 4. 编排生成：生成可执行的DAG
        
    def template_from_solution(self, solution: ComposedSolution) -> Template:
        """
        将组合方案固化为模板（形成新的积木）
        
        对标SAP：将成功实施案例固化为Best Practice
        """
        # 1. 提取通用模式
        # 2. 参数化可变部分
        # 3. 生成新积木
        # 4. 提交到市场
```

---

#### 第三步：封装行业积木（L3）——让用户像搭积木一样搭建AI工厂

这是对标SAP"行业解决方案"的最终体现。

#### 3.1 行业工厂模板的积木化定义

```yaml
#### 行业工厂模板 —— 一个"宏积木"
factory_template:
  name: "软件开发工厂"
  version: "2.0.0"
  
  # 构成积木列表
  components:
    - skill: "analyze_code"        # 从积木市场引用
    - skill: "generate_test"
    - skill: "refactor_code"
    - workflow: "bug_fix_workflow"
    - workflow: "feature_workflow"
    - knowledge: "design_patterns"
    - knowledge: "code_style_guide"
    - mcp: "github"
    - mcp: "docker"
    - evaluation: "code_quality_rules"
    - learning: "software_dev_learning"
  
  # 组合规则 —— 定义积木如何协同
  composition:
    - workflow.feature_workflow -> uses skills: [analyze_code, generate_test]
    - workflow.bug_fix_workflow -> uses skills: [analyze_code, refactor_code]
    - all workflows -> use knowledge: design_patterns
```

#### 3.2 用户搭积木的体验流程

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          用户搭积木体验                                             │
│                                                                                     │
│  Step 1: 选择基础模板                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  📦 选择行业模板                                                           │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐              │   │
│  │  │ 软件开发   │ │ 运维      │ │ 电商      │ │ 数据分析  │              │   │
│  │  │ ★★★★☆    │ │ ★★★☆☆    │ │ ★★★★☆    │ │ ★★★☆☆    │              │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────────┘              │   │
│  │  用户选择: 软件开发                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  Step 2: 按需添加能力积木                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  🔧 当前模板包含的积木:                                                    │   │
│  │  ✅ analyze_code (Skill)                                                   │   │
│  │  ✅ generate_test (Skill)                                                  │   │
│  │  ✅ bug_fix_workflow (Workflow)                                            │   │
│  │  ⬜ security_scan (Skill) — 从市场添加                                     │   │
│  │  ⬜ k8s_deploy (MCP) — 从市场添加                                          │   │
│  │                                                                             │   │
│  │  [添加积木] [移除积木] [查看积木详情]                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  Step 3: 自动检测兼容性                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  🔄 兼容性检查                                                            │   │
│  │  ✅ 所有积木依赖已满足                                                    │   │
│  │  ✅ 版本兼容性通过                                                        │   │
│  │  ✅ 无冲突                                                               │   │
│  │  ⚠️  security_scan需要额外配置: 提供代码扫描规则                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  Step 4: 一键生成定制工厂                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │  🏭 生成定制工厂                                                           │   │
│  │  名称: 我的软件开发工厂 (v1.0.0)                                           │   │
│  │  包含: 5个Skill, 3个Workflow, 2个MCP, 1个知识库                          │   │
│  │  状态: ✅ 就绪                                                            │   │
│  │                                                                             │   │
│  │  [启动工厂] [导出模板] [分享到市场]                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

#### 三、对标SAP的"积木式"能力矩阵

| SAP能力 | AI Factory对标实现 | 当前状态 | 目标状态 |
|---|---|---|---|
| **SAP Best Practices**（预置流程模板） | 行业工厂模板库（软件/运维/电商/...） | 🚧 基础 | 📐 完整库 |
| **SAP S/4HANA可组合架构** | 模块化热插拔架构（§二） | ✅ 已设计 | ✅ 已实现 |
| **SAP Clean Core**（核心整洁，扩展在外） | 核心引擎+Skill/MCP扩展机制 | 🚧 设计 | 📐 完善 |
| **SAP BTP集成平台** | 积木注册中心 + 组合引擎 | 📐 设计 | 📐 完善 |
| **SAP Fiori统一UI** | CLI/TUI/Web/IM统一交互（§十一） | 🚧 部分 | 📐 完善 |
| **SAP Business Data Cloud** | 统一知识图谱 + 数据平面（§十九） | 📐 设计 | 📐 完善 |
| **SAP Joule AI副驾** | 自然语言→目标→自动编排 | 📐 设计 | 📐 完善 |
| **SAP Store应用市场** | 积木市场（Skill/Workflow/Template） | 📐 设计 | 📐 完善 |
| **SAP Industry Solutions** | 行业工厂套件 | 📐 设计 | 📐 完善 |

---

#### 四、总结：从"做什么"到"怎么做"的行动清单

#### 短期（立即可启动）

| 序号 | 行动项 | 产出 | 优先级 |
|---|---|---|---|
| 1 | **定义Brick接口标准** | `BrickInterface`规范文档 | P0 |
| 2 | **实现积木注册中心** | 可运行的BrickRegistry模块 | P0 |
| 3 | **定义积木市场数据模型** | 市场API + 前端设计 | P1 |
| 4 | **封装3-5个基础Skill** | 首批官方Skill积木 | P0 |

#### 中期（3-6个月）

| 序号 | 行动项 | 产出 | 优先级 |
|---|---|---|---|
| 5 | **实现积木组合引擎** | 可组合和固化为模板 | P0 |
| 6 | **建立官方行业工厂模板库** | 软件/运维/电商3个工厂 | P0 |
| 7 | **启动积木市场MVP** | 可浏览/下载/评分 | P1 |
| 8 | **建立开发者文档和SDK** | 让第三方可开发积木 | P1 |

#### 长期（6-12个月）

| 序号 | 行动项 | 产出 | 优先级 |
|---|---|---|---|
| 9 | **建立积木质量认证体系** | 官方认证流程 | P1 |
| 10 | **启动合作伙伴计划** | 生态网络 | P1 |
| 11 | **实现行业工厂在线更新** | 持续交付新能力 | P2 |
| 12 | **对标完整企业级功能矩阵** | 全面企业就绪 | P2 |

---

**一句话总结**：对标SAP不是"复制SAP"，而是**复制SAP的成功范式**——将50年行业知识积累转化为"积木式"的可组合能力，让用户像搭积木一样构建自己的AI工厂，而非从零开始造轮子。
### 2.8 真实代码模块地图（工程模块化设计）

> 2026-08-22 补充: 概念层（§2.1-§2.7）落地到**真实代码模块** — 4 大仓 + 子模块职责/依赖/状态/能力映射。防"设计与实现漂移"。

#### 2.8.1 四大仓职责

| 仓 | 职责 | 边界铁律 |
|---|---|---|
| **factory-core** | 领域原语（events/tasks/workflows/execution/validation/agents/understanding/change…） | 冻结，只读复用，不因 console 需求改 |
| **factory-console** | 人类控制面（session/CLI/API/audit/memory/资产/工具） | 薄调度，不复制 core 业务 |
| **factory-exec** | Agent 运行时（DeveloperAgent/ExecutionLoop/Evaluator/沙箱/MCP/patch） | 执行引擎，零业务 |
| **factory-org** | 组织/项目数据（org/projects/space） | 数据面，被 console 代理 |

#### 2.8.2 核心子模块地图（真实代码 + 状态）

| 模块（真实路径） | 职责 | 状态 |
|---|---|---|
| `session/artifact_registry.py` | 版本化资产（v+n 递增） | ✅ |
| `session/evidence.py` | 证据包（diff+test+决策） | ✅ |
| `session/repo_mode.py` | 存量仓库模式（理解→改→测→修） | ✅ |
| `session/workloads/backlog_sweeper.py` | 积压清道夫（分诊→修复→证据→审批→报告） | ✅ |
| `session/product_intelligence.py` | 8 分析引擎（市场/竞品/画像/MVP…） | ✅ |
| `session/pipeline.py` | PRD/工程/任务规则生成（确定性兜底） | ✅ |
| `session/conversation.py` | 发现状态机（控制短语/多段填充） | ✅ |
| `session/observability.py` | 执行历史/项目状态 | ✅ |
| `session/tools.py` | 工具发现（AI CLI + MCP server） | ✅ |
| `session/conflicts.py` | 交接冲突解析（S10-057） | ✅ |
| `session/review_gate.py` | 审批门（request/approve/reject） | ✅ |
| `exec/developer.py` | DeveloperAgent（provider/结构化输出） | ✅ |
| `exec/execution_loop.py` | 计划/执行/决策循环（LLMPlanner） | ✅ |
| `exec/evaluator.py` | 5 层候选评分 | ✅ |
| `exec/approval.py` | 分级审批（爆炸半径） | ✅ |
| `exec/mcp.py` | MCP 客户端（Mock + Stdio 真连） | ✅ |
| `exec/sandbox.py` | 项目副本沙箱（原仓库零影响） | ✅ |
| `exec/patch_filter.py` | patch 白名单过滤/交付校验 | ✅ |
| `console/memory/` | 经验/学习/检索（experience/learning/retrieval） | ✅ |
| `console/audit/` | 审计链（33+ 事件 + 血缘） | ✅ |
| `org/` | 组织/项目数据（projects/space） | ✅ |
| `session/agent_entity.py`（M2 新建） | 专家实体（role/provider/skills/knowledge/eval/memory/profile） | ✅ |
| `session/agent_registry.py`（M2） | 工厂层专家注册（行业命名空间 it.*） | ✅ |
| `session/expert_factory.py`（M2） | 专家装配器（7 角色，缺 skill 明确报错） | ✅ |
| `session/handoff_bus.py`（M2） | 多 Agent 交接总线（血缘互引+冲突挂起） | ✅ |
| `session/channels/`（M5+） | 消息平台适配器（50+ 长期） | 📐 |

#### 2.8.3 模块依赖原则（无循环）

```
factory-core ← factory-console ← factory-exec ← factory-org
（console 经 core_loader 延迟加载 core/exec；Removal Isolation；禁循环 import）
```

#### 2.8.4 21 章 ↔ 模块映射

| 章节 | 主模块 | 状态 |
|---|---|---|
| §一 定位 | 文档（§1.4 状态锚点） | ✅ |
| §二 模块化 | 全模块 + core/agents | 🚧 |
| §三 任务拆解 | `session/pipeline.py` + `session/orchestrator.py` | 🚧 |
| §四 多 Agent | `exec/*` + M2（agent_entity/handoff_bus） | 🚧 |
| §五 审计可观测 | `console/audit` + `session/observability.py` | ✅ |
| §六 治理 | `review_gate/confirm/budget/exec/approval` | ✅ |
| §七 学习进化 | `console/memory` + `exec/evaluator.py` | 🚧 |
| §八 RAG | `console/memory/retrieval.py` | 🚧 |
| §九 工具/消息 | `session/tools.py` + `exec/mcp.py` | 🚧 |
| §十 行业工厂 | `org` + `session/workloads` | 🚧 |
| §十一 交互 | `session/`（CLI ✅ / Web 📐） | 🚧 |
| §十二 路线 | 文档（MASTER-PLAN） | ✅ |
| §十三 术语 | 文档 | ✅ |
| §十五 竞品 | 文档 | ✅ |
| §十六 优势吸收 | `exec/mcp` + `session/tools` + M4（memory） | 🚧 |
| §十七 自我进化 | `exec/evaluator` + `console/memory` | 🚧 |
| §十八~廿一 | 文档/未来（合规/知识图谱/安全/企业级） | 📐 |

#### 2.8.5 模块化落地原则

1. **新能力先落模块**（指定归属路径），不散落临时文件
2. **每模块三件套**：边界注释 + 接口 + 测试（不造壳）
3. **状态随 §1.4 同步更新**（✅/🚧/📐）
4. **删除/重构先更新本地图**（模块级变更先行文档化）

### 2.9 模块即产品（Product Line — 每个模块可独立成产品）

> 2026-08-22 补充: 高度升级 — 模块不只是代码单元，而是**可独立交付、独立收费、独立进化的产品单元**。
> AI Factory = **产品组合平台（Platform of Products）**：内核 + 多条产品线；每个能力模块都有"独立成产品"的潜力（如治理 → AI 治理平台）。

#### 2.9.1 产品线总览（模块 → 独立产品）

| 模块 | 独立产品形态 | 目标客户 | 商业模式 | 与平台关系 | 优先级 |
|---|---|---|---|---|---|
| **治理/合规**（review_gate/approval/budget） | **AI 治理平台**（组织所有 AI 的审批/预算/合规） | 企业 CTO/合规/审计 | SaaS / 私有化 | 内嵌 + 独立部署 | **P0（信任层）** |
| **证据/审计**（evidence/audit） | **AI 变更审计与证据链** | 审计/合规/研发管理 | 订阅 | 内嵌 + 独立 | P0 |
| **积压清道夫**（backlog_sweeper） | **存量代码清理服务** | 企业研发 | 按件 / 订阅 | 独立产品（首个 wedge） | P0 |
| **多 Agent 编排**（handoff/exec） | **AI 工作流编排**（对标 LangGraph） | 开发者 / ISV | 开源 + 云 | 平台内核 | P1 |
| **知识/RAG**（memory/retrieval） | **企业知识库** | 知识密集企业 | 订阅 | 内嵌 + 独立 | P1 |
| **消息渠道**（channels） | **AI 员工渠道平台** | 运营 / 客服 | 按渠道 | 独立 | P2 |
| **自我进化/记忆**（memory/learning） | **AI 经验学习平台** | AI 平台团队 | 订阅 | 内嵌 | P2 |
| **行业工厂**（factory_spec/workloads） | **每行业一条产品线**（IT/Ops/电商/自媒体/数据/办公） | 行业客户 | 按行业 | 独立产品线 | P1+ |

#### 2.9.2 产品化判定标准（什么模块值得独立成产品）

1. **独立价值**：单独拿出来，客户是否愿意付钱（不依赖平台叙事）？
2. **独立边界**：模块边界清晰，可独立部署 / 独立 API / 独立存储 / 独立版本？
3. **独立市场**：是否有独立客户群与竞品（如治理 → 合规工具市场）？
4. **平台复用**：独立后仍被内核复用（不分裂、不重复造）？
5. **经济性**：独立运营成本 vs 独立收入（单位经济成立）？

#### 2.9.3 治理模块的产品化（示例：用户点名）

- **独立产品**："AI 治理平台"——管理组织里**所有 AI**（不论用 Claude/Codex/自建），提供审批门、预算护栏、审计证据链、合规报告。
- **卖点**：企业"敢用 AI"的信任层；现有工具（Claude Code/Codex/Devin）都**不做治理**——真空地带。
- **形态**：API + 控制台 + 与任何 AI 工具集成（不是只服务 AI Factory 自身）。
- **与平台**：内核内嵌（AI Factory 用它治理自己）+ 独立售卖（卖给用其他 AI 的组织）。

#### 2.9.4 产品组合策略（Platform of Products）

```
内核（多 Agent / 执行 / 记忆 / 资产）＝平台底座
  ├─ 产品线 1: 积压清道夫（wedge，先卖）
  ├─ 产品线 2: AI 治理平台（信任层，P0）
  ├─ 产品线 3: AI 变更审计（证据链，P0）
  ├─ 产品线 4: AI 工作流编排（P1）
  ├─ 产品线 5: 企业知识库（P1）
  ├─ 产品线 6: AI 员工渠道（P2）
  └─ 产品线 7+: 行业工厂（每行业一条线）
```

**演进路径**：先 wedge（清道夫，一件干完的活）→ 信任层（治理+证据，敢签字）→ 平台化（内核开放 API，孵化更多产品线）。

#### 2.9.5 对架构的影响（模块边界 = 产品边界）

1. **模块间只经 API 通信**（不共享内部状态/直接 import 业务）——独立成产品的前提
2. **每模块三件套升级为**：独立 API + 独立存储 + 独立版本 + 独立文档
3. **模块设计时就要问**："如果这个模块单独卖，客户能上手吗？"——从模块设计第一天就按产品标准
4. **与 §2.8 的关系**：代码模块地图是"实现视图"，产品线是"交付视图"；两者 1:1 对应（模块 = 潜在产品）

### 2.10 平台统一设计规范（统一字段/接口/返回值 — 集成零摩擦）

> 2026-08-22 补充（用户原则，最高优先级）: 模块**虽独立成产品，但相对 AI Factory 统一设计**——
> 字段、接口、返回值一律统一，**不给后面集成找麻烦**。独立产品回集成平台 = 零适配，不是返工。

#### 2.10.1 统一数据契约（字段）

| 维度 | 统一规范 | 现状 |
|---|---|---|
| **ID** | 统一前缀语义：`P-`(项目) `APR-`(审批) `ev-`(证据包) `EXS-`(执行) `mcp-`(连接) `session-`(会话) `task-`(任务) + 全局唯一 | ✅ 已统一 |
| **时间** | 一律 ISO 8601 UTC（`created_at/updated_at/decided_at/applied_at`…） | ✅ 已统一 |
| **状态** | 统一生命周期枚举：`pending→approved/rejected` · `draft→confirmed` · `low/medium/high` · `ok/error` | ✅ 已统一 |
| **元数据** | 所有实体带 `source / version / created_by`（谁造的、哪个版本、来源） | ✅ 已统一 |
| **血缘** | 审计字段 `event_id / parent_event_id / artifact_reference` 贯穿所有实体 | ✅ 已统一（S10-083/084） |

#### 2.10.2 统一接口契约

| 层 | 统一规范 | 现状 |
|---|---|---|
| **Action 层** | `ActionResult{ok, status, message, data, error}`（全模块统一返回壳） | ✅ 已统一 |
| **API 层** | REST `/api/v1` + Pydantic response models；资源命名 `<module>/<id>`；只读/写语义分离 | ✅ 已统一 |
| **CLI 层** | `factory <module> <action> [--json]` 统一命令树 | ✅ 已统一 |
| **模块间** | 只经 API / 事件总线通信，**不直接 import 对方业务**（独立成产品的前提） | ✅ 已统一 |

#### 2.10.3 统一返回值

- **成功**: `{ok: true, status, message, data}` —— data 为结构化结果
- **失败**: `{ok: false, status, message, error}` —— 明确错误，不吞、不伪装、不崩溃
- **列表**: `{count, items/rows, header}` 统一分页/表格
- **错误码**: 统一错误分类（校验/未找到/冲突/依赖缺失/治理拦截…）—— 🚧 错误码表待统一
- **失败安全**: 任何模块故障 → 明确错误回上层，不中断平台

#### 2.10.4 集成原则（独立产品回平台 = 零摩擦）

1. **纳入门槛**：独立产品要进平台生态，必须通过**契约测试**（字段 schema / 接口 / 返回值断言）——不是"接进来再适配"
2. **契约版本化**：模块升级向后兼容（version 字段）；破坏性变更先升版本再迁移
3. **统一注册**：产品线经平台内核开放 API 挂载（`/api/v1/` 统一入口），不各自开洞
4. **集成测试**：每个独立产品回集成跑一次契约测试套件（§2.10.2-2.10.3 全断言）

#### 2.10.5 现状对照（已统一 vs 待统一）

| 状态 | 项 |
|---|---|
| ✅ 已统一 | ActionResult · 审计事件 · artifact 版本化 · API Pydantic 响应 · ID 前缀 · UTC 时间 · 血缘字段 |
| 🚧 待统一 | **错误码表**（集中定义+文档）· **契约测试套件**（独立产品集成门槛）· 模块 API 命名收敛审计 |

> 落地：M2 起每个新模块（agent_entity/expert_factory/handoff_bus…）**第一天就按本规范实现**（ActionResult + 统一字段 + 契约测试），不欠债。

### 2.11 统一数据模型与契约（核心实体 + API + 错误码 + 契约测试）

> 2026-08-22 补充: §2.10 原则的具体落地 —— 核心实体统一字段、API 端点统一、错误码统一、
> 契约测试作为独立产品纳入平台的强制门槛。

#### 2.11.1 核心实体统一数据模型（通用字段 + 各实体字段）

**通用字段（所有实体）**：`id / created_at(UTC) / updated_at / source / version / created_by / status`

| 实体 | 前缀 | 专属字段 |
|---|---|---|
| **AgentEntity**（专家） | `agt-` | `role / industry / provider{id,model} / system_prompt / skills[] / knowledge_ref / workflow_ref / memory_ref / tools[] / evaluation_ref / profile{success_rate,quality,cost,speed,samples}` |
| **FactorySpec**（行业工厂） | `fac-` | `industry / employees[] / capabilities[] / workflows[] / governance / assets[]` |
| **EvidenceBundle**（证据包） | `ev-` | `project_id / task_id / agent_id / diff / test_results[] / logs[] / decisions[] / artifacts[]` |
| **ApprovalRequest**（审批） | `APR-` | `bundle_id / risk_level(low/medium/high) / required_roles[] / decided_by / decided_at` |
| **Artifact**（资产） | `art-` | `type / version / parent_artifact / content_ref / event_id` |
| **ChannelMessage**（消息） | `msg-` | `platform / conversation / sender / text / ts` |
| **ExecutionTask**（任务） | `task-` | `project_id / agent_id / status / error / code_files` |

#### 2.11.2 统一 API 端点（/api/v1 全景）

```
/api/v1
  /agents            GET/POST    专家列表/创建
  /agents/{id}       GET/PATCH   专家详情/画像更新
  /factories         GET/POST    工厂列表/实例化
  /tasks             POST        跑任务 (idea|repo|autonomous)
  /tasks/{id}        GET         任务状态 (+ SSE /events)
  /projects/{id}/artifacts|timeline|status   GET
  /approvals         GET/POST    审批列表/请求
  /approvals/{id}    PATCH       审批决策 (approve/reject)
  /evidence          GET/POST    证据包
  /tools             GET/POST    /tools/{name}/call
  /channels          GET/POST    消息渠道
  /memory/experience|agents       GET
  /health | /version  GET
```
响应一律 `{ok, status, message, data}`（成功）/ `{ok, status, message, error}`（失败）。

#### 2.11.3 统一错误码

| 码 | 语义 | 场景 |
|---|---|---|
| `E400` | 参数/校验错误 | 缺字段、非法值 |
| `E401` | 权限不足 | 未授权访问 |
| `E402` | **治理拦截** | 审批未过 / 预算超限 / 审计拒绝 |
| `E404` | 未找到 | 实体/端点不存在 |
| `E409` | 冲突 | 重复创建 / 状态冲突 |
| `E410` | 依赖缺失 | LLM 不可用 / 工具缺失 / 数据缺失 |
| `E500` | 内部错误 | 未预期异常（失败安全，不吞不伪装） |

错误响应: `{ok:false, status:"error", message:"人类可读", error:{code:"E402", detail:"..."}}`

#### 2.11.4 契约测试套件（独立产品纳入平台的强制门槛）

| 套件 | 断言 | 目的 |
|---|---|---|
| **schema 测试** | 实体字段齐全、类型正确、枚举合法 | 字段统一 |
| **接口测试** | 端点存在、方法正确、路径/参数一致 | 接口统一 |
| **返回值测试** | `{ok,status,message,data|error}` 结构一致 | 返回值统一 |
| **错误码测试** | 失败场景返回正确错误码（E4xx/E5xx） | 错误统一 |
| **血缘测试** | event_id/parent_event_id/artifact_reference 链完整 | 可审计 |

> 门槛: 任何独立产品（治理/证据/清道夫/知识/渠道…）要纳入 AI Factory 平台生态，**必须先通过契约测试套件**；不通过 = 不纳入（先适配再进，而不是进来再修）。

### 2.12 模块间数据同步与通信（分布式模块化的关键）★

> 2026-08-22 补充（用户关键判断）: 模块独立成产品（各自存储）后，**跨模块数据同步与通信**是核心问题——
> 不解决 = 模块分裂、数据不一致、集成返工。

#### 2.12.1 通信模式（三种，按场景选）

| 模式 | 适用 | 特点 |
|---|---|---|
| **同步 RPC**（API 调用） | 请求-响应（查询/单点命令） | 实时、简单；调用方等待；失败即知 |
| **异步事件**（消息总线） | 状态变更通知 / 模块解耦 | 不阻塞、可重放、最终一致 |
| **事件溯源** | 跨模块血缘/审计 | 全链路可追溯（§5.6） |

**选择规则**：查询/强实时 → RPC；状态变更/解耦 → 事件；要审计追溯 → 事件溯源。

#### 2.12.2 数据一致性（模块各有存储的前提）

**原则**：每个模块持有自己的数据（独立产品的前提）；跨模块一致性 = **最终一致（eventual consistency）**，不追求跨库强一致（2PC 太贵）。

| 模式 | 解决什么 | 说明 |
|---|---|---|
| **Outbox 模式** | 防丢事件 | 本地事务写业务 + outbox 表 → 后台发事件（业务与事件同事务） |
| **事件重放** | 新模块/故障恢复 | 消息总线可重放 → 重建/补齐状态 |
| **幂等消费** | 防重复 | 每个事件带 id，消费端幂等（重复投递安全） |
| **CDC / 快照同步** | 大表增量 | 批量数据用增量/快照同步 |
| **Saga / 补偿** | 跨模块多步事务 | 长事务拆本地事务 + 补偿，不做分布式锁 |

#### 2.12.3 通信可靠性

```
重试 + 指数退避 → 死信队列（处理失败）→ 熔断/降级（§2 已有）
超时 + 降级（降级不假装成功）
```

#### 2.12.4 与统一契约 / 现状衔接

| 项 | 现状 |
|---|---|
| 统一事件格式（id/timestamp/source/version + 血缘） | ✅ §2.10-11 已定义 |
| 消息总线 / 降级熔断 | 📐 §2.3.4/2.3.5 设计 |
| HandoffBus 交接消息（§4.7） | 📐 M2 |
| audit / 证据 / 资产事件驱动落盘 | ✅ 已实现（事件驱动雏形） |
| Outbox / 幂等 / 死信 / Saga | 📐 未系统化（M3/M5 模块化底座） |

#### 2.12.5 落地优先级

- **M2**：HandoffBus 交接消息（模块内协作通信）
- **M3/M5**：跨模块消息总线 + Outbox + 幂等 + 死信（作为模块化底座，独立产品接入同一总线）

### 2.13 服务生命周期管理（注册 / 发现 / 运行 / 执行 / 治理 / 监控）★

> 2026-08-24 补充（Founder: board 一键启动 + 随启动组件 + 服务注册/发现/运行/执行/治理/监控规则）。
> 核心: **"注册 + 懒加载" ≠ "全部常驻"** — 随启动的是入口/可见性, 不是资源/初始化。

**现状（注册/发现/运行 ✅ 已有）**: `cli_services.py` Services Registry
- ServiceDef 协议（id/label/start/stop/status + 可选 wait_ready/port/log_path/rollback）
- _SERVICES 注册表: register 即被发现（factory service list / factory start <id>）
- **缺: 执行/治理/监控 规则**

**服务生命周期 6 阶段规则**

| 阶段 | 规则 | 现状 |
|---|---|---|
| **① 注册 Register** | 服务实现 ServiceDef 协议 + register() → 进注册表 | ✅ 已有 |
| **② 发现 Discover** | register 即被发现; `factory service list` 枚举 | ✅ 已有 |
| **③ 运行 Run** | start/stop/status + wait_ready 健康检查 + rollback 失败回滚 | ✅ 已有 |
| **④ 执行 Execute** | 服务暴露能力（actions/endpoints）; 统一契约（§2.11）调用 | 📐 设计 |
| **⑤ 治理 Govern** | 启停控制 + 服务审计事件 + 权限（哪些服务用户可启停） | 📐 设计 |
| **⑥ 监控 Monitor** | 健康/指标/日志; service status + 监控面板（§5.8） | 📐 设计 |

**随启动组件装配（懒加载 + 失败隔离）**

```
factory start
  → 扫描注册表, 发现"随启动"服务（board/dashboard/notifier...）
  → 注册（命令/端点可见）→ 懒加载（首次访问才初始化, 不常驻资源）
  → 失败隔离（服务装配失败不影响主程序, rollback）
  → 热插拔（新服务实现 ServiceDef + register 一行即可）
```

**④ 执行规则（能力调用协议）**

```
服务暴露能力 = actions（会话命令）+ endpoints（HTTP 端点）
调用统一契约: 输入/输出/错误码（§2.11）
board 示例: /board 会话命令（文本面板）+ /api/board Web 端点（懒加载渲染）
```

**⑤ 治理规则**

```
启停: factory service start/stop <id>（明确控制）
审计: 服务启停/能力调用落审计事件（谁/何时/什么服务）
权限: 服务分级（核心服务用户可启停 / 组件服务按需）
```

**⑥ 监控规则**

```
健康: service status（wait_ready 检查）
指标: 服务存活/调用量/延迟（§5.8 时序存储）
面板: 监控面板聚合服务状态（§5.10 递归进度）
```

**落地**: board 服务（id="board"）实现 ServiceDef + register → 随 start 提供
/api/board 端点（懒加载）+ 会话 /board 命令（已有）。未来 dashboard/通知/日志
同机制注册。

## 三、复杂任务拆解体系

### 3.1 什么是"复杂任务"

**定义**：需要多步推理、多工具协作、跨领域知识、迭代试错的非确定性任务。

#### 复杂任务 vs 简单任务

| 维度 | 简单任务 | 复杂任务 |
|---|---|---|
| **步骤数** | 1-3 步 | 10+ 步 |
| **确定性** | 确定性强 | 不确定，需探索 |
| **依赖** | 无/少依赖 | 复杂依赖关系 |
| **失败恢复** | 重试即可 | 需换策略/回退 |
| **知识需求** | 通用知识 | 领域专业 + 上下文 |
| **工具需求** | 1 个工具 | 多工具组合 |
| **人机协同** | 无需 | 关键节点需确认 |
| **验证** | 简单检查 | 多维度验证 |

#### 复杂任务典型特征

```
复杂任务特征检测
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 特征1: 多步骤                                                       得分   │
│   □ 需要 3 个以上步骤 (1分)                                               │
│   □ 步骤有依赖关系 (1分)                                                  │
│   □ 步骤可并行 (1分)                                                     │
│   ─────────────────                                                      │
│   得分 ≥ 2 → 复杂                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 特征2: 不确定性                                                   得分     │
│   □ 有多种可能方案 (1分)                                                  │
│   □ 需要试错迭代 (1分)                                                    │
│   □ 结果难以预判 (1分)                                                    │
│   ─────────────────                                                      │
│   得分 ≥ 2 → 复杂                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 特征3: 知识密集                                                   得分     │
│   □ 需要领域专业知识 (1分)                                                │
│   □ 需要读取大量上下文 (1分)                                              │
│   □ 需要 RAG 检索 (1分)                                                  │
│   ─────────────────                                                      │
│   得分 ≥ 2 → 复杂                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 任务拆解的核心机制


> 本流程为**目标态 LLM 深度拆解**（M3）；当前实现为确定性拆解（§3.6：FeatureTaskGenerator 功能→Epic→任务四件套）。
```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              任务拆解全流程                                        │
│                                                                                     │
│  用户输入目标                                                                      │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 1: 意图理解                                                           │   │
│  │   - 目标分类：诊断型 / 构建型 / 修改型 / 探索型                            │   │
│  │   - 复杂度评估：简单 / 中等 / 复杂 / 极复杂                                │   │
│  │   - 领域识别：软件开发 / 运维 / 电商 / ...                                 │   │
│  │   - 约束提取：时间 / 成本 / 质量 / 安全                                    │   │
│  │   - 歧义检测：哪些地方不清晰？需要澄清？                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 2: 上下文获取                                                         │   │
│  │   - RAG L3 检索：项目级文档/代码                                             │   │
│  │   - RAG L2 检索：行业知识                                                    │   │
│  │   - RAG L1 检索：平台经验                                                    │   │
│  │   - 工具发现：哪些工具可用？                                                 │   │
│  │   - 历史关联：之前是否做过类似任务？                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 3: 任务拆解 (核心)                                                     │   │
│  │                                                                             │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │   │ Step 3.1: 生成候选子任务列表                                       │   │   │
│  │   │   - 基于目标类型使用对应的拆解模板                                 │   │   │
│  │   │   - LLM 生成 N 个子任务 (N=3-20)                                   │   │   │
│  │   │   - 每个子任务带：描述、工具需求、知识需求                         │   │   │
│  │   └─────────────────────────────────────────────────────────────────────┘   │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │   │ Step 3.2: 依赖关系推断                                             │   │   │
│  │   │   - 任务间依赖：A 需要 B 的输出                                     │   │   │
│  │   │   - 资源依赖：A 和 B 都需要同一个文件                              │   │   │
│  │   │   - 时序依赖：A 必须在 B 之前执行                                   │   │   │
│  │   │   - 条件依赖：如果 X 则执行 Y                                       │   │   │
│  │   │   - 输出: DAG (有向无环图)                                          │   │   │
│  │   └─────────────────────────────────────────────────────────────────────┘   │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │   │ Step 3.3: 可行性验证                                               │   │   │
│  │   │   - 每个任务是否有可用工具？                                        │   │   │
│  │   │   - 资源是否可访问？                                                │   │   │
│  │   │   - 是否有循环依赖？(检测并修正)                                    │   │   │
│  │   │   - 是否需要用户澄清？(标记)                                        │   │   │
│  │   └─────────────────────────────────────────────────────────────────────┘   │   │
│  │   ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │   │ Step 3.4: 任务粒度调整                                             │   │   │
│  │   │   - 太粗粒度的任务 → 继续拆分                                       │   │   │
│  │   │   - 太细粒度的任务 → 合并                                           │   │   │
│  │   │   - 目标: 每个任务 1-10 分钟可完成                                  │   │   │
│  │   └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 4: 任务标注                                                           │   │
│  │   - 风险等级：low / medium / high / critical                               │   │
│  │   - Agent 角色：planner / executor / reviewer / debugger                   │   │
│  │   - 用户介入：是否需要审批                                                │   │
│  │   - 超时时间：预估执行时间                                                │   │
│  │   - 优先级：高 / 中 / 低                                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Phase 5: 输出 DAG                                                            │   │
│  │   - 结构化 JSON                                                              │   │
│  │   - 人类可读摘要                                                             │   │
│  │   - 用户确认/调整                                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 拆解模板库（按任务类型）

#### 诊断型任务模板

```
目标: "服务响应变慢" / "内存泄漏" / "CPU 飙升"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 诊断型拆解模板                                                              │
│                                                                             │
│  T1: 信息收集                                                               │
│    ├── 采集日志 (read_file, run_command)                                   │
│    ├── 采集监控指标 (MCP)                                                  │
│    └── 采集堆栈/堆dump (run_command)                                       │
│                                                                             │
│  T2: 数据分析 (依赖 T1)                                                    │
│    ├── 日志模式识别                                                        │
│    ├── 异常点定位                                                          │
│    └── 趋势分析                                                            │
│                                                                             │
│  T3: 假设生成 (依赖 T2)                                                    │
│    ├── 生成 3-5 个可能原因                                                 │
│    └── 每个原因附证据链                                                    │
│                                                                             │
│  T4: 假设验证 (依赖 T3)   [可并行]                                         │
│    ├── 验证假设1 → 搜索代码 / 运行测试                                     │
│    ├── 验证假设2 → 搜索代码 / 运行测试                                     │
│    └── 验证假设3 → 搜索代码 / 运行测试                                     │
│                                                                             │
│  T5: 根因定位 (依赖 T4)                                                    │
│    ├── 确认真正的根因                                                      │
│    └── 输出根因分析报告                                                    │
│                                                                             │
│  T6: 修复方案 (依赖 T5)   [需用户审批]                                     │
│    ├── 生成修复代码                                                        │
│    └── 验证修复有效性                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 构建型任务模板

```
目标: "实现用户登录功能"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 构建型拆解模板                                                              │
│                                                                             │
│  T1: 需求澄清 (需用户交互)                                                  │
│    ├── 目标用户是谁？                                                      │
│    ├── 支持哪些登录方式？                                                  │
│    ├── 是否需要记住密码？                                                  │
│    └── 是否需要第三方登录？                                                │
│                                                                             │
│  T2: 技术设计 (依赖 T1)                                                    │
│    ├── 选择技术栈                                                          │
│    ├── 数据库设计                                                          │
│    ├── API 设计                                                            │
│    └── 安全方案                                                            │
│                                                                             │
│  T3: 代码实现 (依赖 T2)   [可并行]                                         │
│    ├── T3a: 数据库层 (write_file)                                          │
│    ├── T3b: 业务逻辑层 (write_file)                                        │
│    ├── T3c: API 层 (write_file)                                            │
│    └── T3d: 前端集成 (write_file)                                          │
│                                                                             │
│  T4: 测试编写 (依赖 T3)   [可并行]                                         │
│    ├── T4a: 单元测试 (write_file)                                          │
│    └── T4b: 集成测试 (write_file)                                          │
│                                                                             │
│  T5: 验证执行 (依赖 T4)                                                    │
│    ├── 运行单元测试 (run_command)                                          │
│    ├── 运行集成测试 (run_command)                                          │
│    └── 修复失败的测试                                                      │
│                                                                             │
│  T6: 部署配置 (依赖 T5)   [需用户审批]                                     │
│    ├── 生成部署配置                                                        │
│    └── 部署到测试环境                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 修改型任务模板

```
目标: "升级 Spring Boot 版本"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 修改型拆解模板                                                              │
│                                                                             │
│  T1: 影响面分析                                                             │
│    ├── 搜索所有引用旧版本的文件 (search_code)                              │
│    ├── 分析依赖树 (run_command)                                            │
│    └── 识别 Breaking Changes                                               │
│                                                                             │
│  T2: 升级计划 (依赖 T1)                                                    │
│    ├── 确定升级路径 (是否有中间版本)                                       │
│    ├── 确定需要修改的文件列表                                              │
│    └── 风险评估                                                            │
│                                                                             │
│  T3: 执行修改 (依赖 T2)   [可并行]                                         │
│    ├── T3a: 修改 build.gradle/pom.xml (write_file)                         │
│    ├── T3b: 修改代码 (write_file)                                          │
│    └── T3c: 修改配置 (write_file)                                          │
│                                                                             │
│  T4: 验证 (依赖 T3)                                                        │
│    ├── 编译检查 (run_command)                                              │
│    ├── 运行测试 (run_command)                                              │
│    └── 回归测试                                                            │
│                                                                             │
│  T5: 审查 (依赖 T4)                                                        │
│    ├── Reviewer Agent 审查修改                                             │
│    ├── 质量评估                                                            │
│    └── 输出审查报告                                                        │
│                                                                             │
│  T6: 提交 (依赖 T5)   [需用户审批]                                         │
│    ├── 生成 commit message                                                 │
│    └── 提交 PR / MR                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 探索型任务模板

```
目标: "这个遗留系统是干什么的？"
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 探索型拆解模板                                                              │
│                                                                             │
│  T1: 结构扫描                                                               │
│    ├── 扫描目录结构 (run_command)                                          │
│    ├── 识别文件类型分布                                                    │
│    └── 识别主要模块                                                        │
│                                                                             │
│  T2: 代码理解 (依赖 T1)   [可并行]                                         │
│    ├── T2a: 读取核心文件 (read_file)                                       │
│    ├── T2b: 分析调用关系 (search_code)                                     │
│    └── T2c: 识别设计模式 (分析推理)                                        │
│                                                                             │
│  T3: 知识整理 (依赖 T2)                                                    │
│    ├── 生成架构图                                                          │
│    ├── 生成模块说明                                                        │
│    └── 识别关键流程                                                        │
│                                                                             │
│  T4: 文档生成 (依赖 T3)                                                    │
│    ├── 生成 README                                                         │
│    ├── 生成 API 文档                                                       │
│    └── 生成运维手册                                                        │
│                                                                             │
│  T5: 用户交付 (依赖 T4)                                                    │
│    ├── 输出文档集合                                                        │
│    └── 标注待确认项                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 拆解质量评估

| 评估维度 | 评分标准 | 权重 |
|---|---|---|
| **完整性** | 是否覆盖目标的所有方面 | 25% |
| **粒度** | 每个任务是否可独立执行 | 20% |
| **依赖正确性** | 依赖关系是否准确 | 20% |
| **可行性** | 每个任务是否有可用工具 | 15% |
| **可测性** | 每个任务是否有验收标准 | 10% |
| **风险标注** | 风险是否准确评估 | 10% |

```
拆解质量评分 = Σ(维度得分 × 权重)
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 评分 → 行动                                                                 │
│                                                                             │
│  得分 ≥ 0.9 → 直接采用                                                     │
│  0.7 ≤ 得分 < 0.9 → 轻微调整                                               │
│  0.5 ≤ 得分 < 0.7 → 重新拆解 (换模板)                                     │
│  得分 < 0.5 → 请求用户澄清 + 重新拆解                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.5 DAG 数据结构完整定义（目标态设计）

> 当前实现为确定性任务树（§3.6 的 FeatureTaskGenerator/TaskTree）；本 DAG（input_schema/output_schema/inputs_from）是 LLM 深度拆解（M3）时的完整形态。

```python
# ============ 完整 DAG 数据结构 ============

class TaskDAG:
    """完整任务 DAG"""
    
    # 元信息
    id: str                          # DAG 唯一 ID
    goal: str                        # 原始目标
    goal_type: str                   # 诊断型 | 构建型 | 修改型 | 探索型
    complexity: str                  # 简单 | 中等 | 复杂 | 极复杂
    domain: str                      # 软件开发 | 运维 | 电商 | ...
    version: str                     # DAG 版本
    
    # 任务列表
    tasks: List[SubTask]
    
    # 依赖关系 (邻接表)
    dependencies: Dict[str, List[str]]  # {"T2": ["T1"], "T3": ["T2"]}
    
    # 并行组
    parallel_groups: List[List[str]]    # [["T2", "T3"], ["T4", "T5"]]
    
    # 关键路径
    critical_path: List[str]            # 最长的依赖链
    
    # 统计
    estimated_duration: int             # 预估总耗时 (秒)
    estimated_cost: float               # 预估总成本 (USD)
    total_tasks: int
    
    # 状态
    status: str                         # pending | running | paused | done | failed
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class SubTask:
    """单个子任务"""
    
    id: str                              # "T1"
    description: str                     # 人类可读描述
    detailed_instructions: str           # 给 Agent 的详细指令
    
    # 依赖
    depends_on: List[str]                # ["T0", "T2"]
    condition: str | None                # 执行条件表达式
    
    # 执行配置
    assigned_agent: str                  # planner | executor | reviewer | debugger
    tools: List[str]                     # ["read_file", "search_code"]
    rag_required: bool                   # 是否需要 RAG 检索
    
    # 输入输出
    input_schema: Dict                   # 期望的输入格式
    output_schema: Dict                  # 期望的输出格式
    inputs_from: List[str]               # 依赖哪些任务的输出
    
    # 约束
    timeout_seconds: int                 # 超时时间
    max_retries: int                     # 最大重试次数
    retry_strategy: str                  # immediate | exponential | skip
    
    # 治理
    risk_level: str                      # low | medium | high | critical（实现为 3 级 §6.3.6，critical 为扩展位）
    requires_approval: bool              # 是否需要用户审批
    approval_required_before: str | None # 执行前/执行后
    
    # 验收标准
    acceptance_criteria: List[str]       # 如何判断任务成功
    
    # 元数据
    priority: int                        # 1-10, 10 最高
    estimated_duration: int              # 预估时长 (秒)
    confidence: float                    # 拆解置信度
    fallback_task: str | None            # 失败后的备选任务
    
    # 状态 (运行时)
    status: str                          # pending | ready | running | success | failed | retrying | skipped
    started_at: datetime | None
    completed_at: datetime | None
    retry_count: int
    error: str | None
    output: Any | None
```


### 3.6 任务拆解实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 确定性任务树 | `session/pipeline.py`：TaskTree / FeatureTaskGenerator（功能级 Epic/Task） | ✅ |
| 依赖图/拓扑 | `session/orchestrator.py`（依赖解析/拓扑/重规划） | ✅ |
| DAG 数据结构 | `execution_state.json`（tasks/status/error/依赖） | ✅ |
| 拆解模板库 / 拆解质量评估 | 本文档 3.3/3.4（设计） | 📐 |

**完成度**：确定性任务拆解 + 依赖图已实现（✅）；LLM 深度拆解模板库/质量评估/**递归拆到原子（§3.7）**待补（📐，M3）。

### 3.7 递归拆解与原子任务（能力边界驱动）★

> 2026-08-22 补充（用户关键判断）: 任务拆解不是一层 DAG，而是**递归分层直到"拆到不能拆"**——
> 因为**当前 Agent 只能执行原子任务**，没有执行复杂任务的能力。拆解深度 = Agent 能力边界。

#### 3.7.0 为什么任务拆解是 Agent 成败的关键（行业失败模式 × AI Factory 应对）★

> 2026-08-24 补充（Founder 关键判断）: **多数 Agent 都折在任务拆解上**——不是模型不够强，
> 是拆解这一步决定了后面所有执行的可能性。拆解失败 = 后面全崩。

**行业 8 大失败模式（为什么折在这里）**

| # | 失败模式 | 症状 | 根因 |
|---|---|---|---|
| 1 | **拆得太粗** | 任务还是复合的（"实现后端 API"）→ 一次做不完 → 失败 | LLM 一步生成 5-8 个任务，粒度 = LLM 直觉 |
| 2 | **无限递归** | 拆到没完没了，成本爆炸 | 无深度/数量上限 |
| 3 | **拆执脱节** | 计划是计划，执行是执行（DAG 没人消费） | 拆解器与执行器不衔接 |
| 4 | **依赖猜错** | 并行冲突 / 死锁 / 顺序错 | LLM 猜依赖边，无验证 |
| 5 | **不可验证** | 无法判断"完成" | 任务无验收标准 |
| 6 | **上下文爆炸** | 越执行越乱（超长上下文 loop） | 每任务带全量上下文 |
| 7 | **无恢复** | 一任务失败 → 整链崩 | 无 repair / replan |
| 8 | **粒度不匹配** | 强 agent 被拆死 / 弱 agent 被撑爆 | 固定粒度不随能力 |

**AI Factory 8 应对（对照）**

| 失败模式 | AI Factory 设计 | 状态 |
|---|---|---|
| 拆太粗 | §3.7.3 四条件拆到原子（单agent/单文件/可验证/≤10min） | ✅ M3a |
| 无限递归 | _max_depth=5 + _max_tasks=64 + 环检测 | ✅ M3a |
| 拆执脱节 | 拆解落盘 → 关键路径(M3b) → 调度(M3c) 全链消费 | 🚧 M3c 待做 |
| 依赖猜错 | 技术层确定性推断 + 环检测 + LLM 辅助(失败跳过) | ✅ M3b |
| 不可验证 | 每原子带 verify_cmd + 验收标准 | ✅ M3a |
| 上下文爆炸 | 每节点独立上下文（§4.12 Node Runtime） | 📐 M3 工程化 |
| 无恢复 | Repair/Replan + S10-060 动态 DAG | ✅ |
| 粒度不匹配 | 深度 = 能力边界（动态收敛） | ✅ M3a |

**诚实: AI Factory 拆解还有 2 个最大短板**

1. **拆解质量评估缺失**（§2.4 📐）: 现在拆得好不好没有评分——"这个拆解合理吗"无法回答
2. **LLM 深度拆解未接**: 确定性技术层模板兜底可靠但机械；LLM 深度拆解（M3 计划）还没做

**结论**: 任务拆解不是"生成任务列表"，是**生产可执行的原子单元 + 依赖图 + 验收标准 +
恢复机制**。AI Factory 已覆盖 6/8 失败模式（M3a/M3b）；剩下 **M3c 衔接 + 拆解质量评估
（§2.4）** 是把"不折在拆解上"从设计变成事实的最后两块。

#### 3.7.1 核心原则

- **递归拆解**：复杂任务 → 子任务 → 子子任务 → … → **原子任务**（叶子）
- **拆解深度 = Agent 能力边界**：一个任务若能由单个 Agent 在**一次执行内**完成（单工具/单文件/可验证/≤10 分钟）→ 原子，停止拆；否则继续递归
- **动态变浅**：Agent 能力越强 → 需要拆的层越少（拆解深度随能力自动收敛，不是固定层数）

#### 3.7.2 层级结构（树状 DAG）

```
业务目标 (Level 0)
 └─ 子任务 (Level 1)        模块/功能
     └─ 子子任务 (Level 2)   Epic
         └─ 原子任务 (Level n)  单文件 / 单工具 / 可验证 ← 唯一进执行队列
```
- **叶子（原子任务）**：进执行队列，由 ExecutionLoop 执行
- **非叶子（编排节点）**：**有自己完整的编排 Loop**（委派子节点→观察子节点证据→汇总验证→自身证据→恢复），只是不做原子动作（§4.12.9）
- 每层任务都有 输入 / 输出 / 验收标准

#### 3.7.3 原子任务判定标准（"拆到不能拆"的判定）

| 判定 | 条件 |
|---|---|
| 单 Agent 可执行 | 当前能力边界内（一个 DeveloperAgent 一次执行） |
| 单工具 / 单文件 | 一次工具调用，或单个文件修改（非"实现整个模块"） |
| 可验证 | 有明确输入/输出/验收标准（测试可断言） |
| 时间盒 | 预估 ≤ 10 分钟（一个执行周期） |

不满足任一 → 继续拆（递归）。

#### 3.7.4 与当前实现的衔接

- `FeatureTaskGenerator` 产出"功能 → Epic → 4 任务（db/api/frontend/test）"——**这些仍偏复合**（如"后端 API 实现"不是原子任务）
- **M3 递归拆解**：LLM 按 3.7.3 判定递归拆到原子 → 落 `execution_state` 叶子任务 → 执行器逐个执行
- **为何现在"一步一个坑"**：任务粒度太粗（复合任务），Agent 一次做不完 → 失败。**拆到原子 = 直接提高执行成功率**（这也应作为 §12 成功标准之一）

### 3.8 任务规划与关键节点（Plan + Gate）★

> 2026-08-22 补充（用户关键判断）: 拆完任务**不能直接执行**——先对每个任务做 Plan，
> 并**判断关键节点**（哪些要卡、哪些要审、哪些是成败枢纽）。

#### 3.8.1 任务级 Plan（拆解 → 执行 之间必须有一层规划）

拆解产出"原子任务清单"，但每个任务执行前先 Plan：

```
原子任务
  → Plan {目标, 输入(依赖输出), 执行步骤, 工具, 输出, 验证方式, 预计成本, 风险}
  → Decision (LLMPlanner): FINAL(直接执行) / ACTION_REQUIRED(需动作/工具)
  → 执行 (ExecutionLoop) → 验证 → 通过→下游 / 失败→修复或重规划
```

- **真实实现**：`exec/execution_loop.py` LLMPlanner 已做任务级 plan（Decision 可审计，落 `decision_created` 事件）✅
- **演进**：M3 把 Plan 从"单任务决策"升级为"整链计划"（关键路径 + 依赖就绪 + 资源分配）

#### 3.8.2 关键节点判定（哪些节点必须卡）

| 节点类型 | 判定 | 动作 |
|---|---|---|
| **关键路径节点** | 最长依赖链上的任务（决定总工期） | 优先调度；失败立即影响交付 |
| **人工决策节点** | 需要人类判断（需求/架构/范围） | ReviewGate 审批（request/approve/reject） |
| **高风险节点** | 爆炸半径大（删除/依赖升级/基础设施） | ApprovalGate 分级必批（§6.3） |
| **依赖汇聚节点** | 多路依赖在此汇合（merge point） | 校验全部输入就绪 + 冲突检查 |
| **质量验证节点** | 测试/验收标准 | 验证通过才放行下游 |
| **快照/回滚点** | 关键阶段完成 | git 快照（对接 §5.6 L4 回放） |
| **成本节点** | 预算水位 | BudgetEnforcer review/block（§6.2） |

#### 3.8.3 Plan → 关键节点 → 执行流

```
原子任务 → Plan(LLMPlanner) → 关键节点判定
  ├─ 人工决策? → ReviewGate (通过才继续)
  ├─ 高风险?   → ApprovalGate (approve 才执行)
  ├─ 预算超限? → BudgetEnforcer (block 停止)
  ├─ 关键路径? → 标记优先 + 失败即告警
  └─ 质量门?   → 测试/验收通过才下游
  → 执行 → 验证 → 快照点 → 下一任务
```

#### 3.8.4 与实现衔接

| 环节 | 现状 |
|---|---|
| 任务级 Plan（LLMPlanner Decision） | ✅ 已实现 |
| 审批/风险/预算节点卡口 | ✅ 已实现（ReviewGate/ApprovalGate/BudgetEnforcer） |
| 整链计划（关键路径/依赖汇聚） | 📐 M3 |
| 快照/回滚点 | 📐 M4/S10-085 |

### 3.9 整链计划与执行调度（M3）★

> 2026-08-22 补充: 原子任务就绪后，不能简单顺序跑——需要**整链计划**（关键路径 + 依赖调度 + 并行 +
> Agent 分配 + 进度恢复）。这是 3.8.4 标记的 M3 缺口。

#### 3.9.1 关键路径分析

- 从原子任务 DAG 计算**关键路径**（最长依赖链）→ 决定总工期
- 关键路径任务标记 `CRITICAL`：优先调度、优先分配资源；失败立即影响交付 → 提前告警

#### 3.9.2 依赖驱动调度

```
原子任务 DAG
  → 拓扑排序 → 就绪队列（依赖全部完成的任务）
  → 并行度: 无依赖冲突的任务按资源/预算/LLM 并发上限并行
  → 冲突: 同文件/同资源 → ConflictResolver 串行化（session/conflicts.py 已有）
```

#### 3.9.3 Agent 分配

- 任务 → AgentMatcher（`session/agents.py`，按 role/skill/成功率匹配）✅ 已实现
- 负载均衡：忙碌 Agent 排队；画像优先（M4 后按 AgentProfile 排序）

#### 3.9.4 进度与恢复

| 环节 | 机制 | 状态 |
|---|---|---|
| 进度 | 每原子任务完成 → `execution_state` 更新 + 事件 | ✅ |
| 失败 | 修复 / ReplanningEngine 重规划（8 决策） | ✅ |
| 中断 | `resume/needs_resume` 续跑 | ✅ |
| 快照点 | git 快照（对接 §5.6 L4） | 📐 M4/S10-085 |

#### 3.9.5 与实现衔接（M3 待补）

- ✅ 已实现：拓扑 / ReplanningEngine / AgentMatcher / resume / ConflictResolver
- 📐 M3：关键路径计算 · 并行调度器 · 冲突自动串行化 · 资源配额

## 四、多 Agent 编排与调用体系

### 4.1 Agent 角色体系

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Agent 角色体系                                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          Coordinator (协调者)                                │   │
│  │  职责: 任务分发、进度协调、冲突解决、资源分配                               │   │
│  │  工具: 工作记忆读写、Agent 调度                                             │   │
│  │  特点: 单一全局，作为"大脑"                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                                 │
│      ┌─────────────┬─────────────┼─────────────┬─────────────┐                      │
│      │             │             │             │             │                      │
│      ▼             ▼             ▼             ▼             ▼                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                      │
│  │Planner  │ │Executor │ │Reviewer │ │Debugger │ │Governor │                      │
│  │(规划者) │ │(执行者) │ │(审查者) │ │(调试者) │ │(治理者) │                      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘                      │
│      │             │             │             │             │                      │
│      └─────────────┴─────────────┼─────────────┴─────────────┘                      │
│                                  │                                                   │
│                          ┌───────┴───────┐                                           │
│                          │   Learner    │                                           │
│                          │  (学习者)    │                                           │
│                          └───────────────┘                                           │
│                                                                                     │
│  每个 Agent 的详细规格:                                                             │
│                                                                                     │
│  ┌─────────────┬──────────────────┬─────────────────┬──────────────────────────┐   │
│  │ Agent       │ 核心能力         │ 专属工具        │ 典型场景                  │   │
│  ├─────────────┼──────────────────┼─────────────────┼──────────────────────────┤   │
│  │ Coordinator │ 编排调度         │ 工作记忆API     │ 任何任务启动时            │   │
│  │ Planner     │ 任务拆解+策略    │ 搜索+读取       │ 复杂任务开始              │   │
│  │ Executor    │ 工具调用+执行    │ 所有工具        │ 编码/文件操作             │   │
│  │ Reviewer    │ 质量审查+评估    │ 搜索+比较       │ 代码审查/方案评估         │   │
│  │ Debugger    │ 根因分析+修复    │ 读/写/执行      │ Bug修复/测试失败          │   │
│  │ Governor    │ 审计+合规+成本   │ 审计API        │ 全流程监控                │   │
│  │ Learner     │ 复盘+经验提炼    │ 记忆API        │ 任务完成后                │   │
│  └─────────────┴──────────────────┴─────────────────┴──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 每个 Agent 的详细能力定义

#### Coordinator（协调者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Coordinator 规格                                                           │
│                                                                             │
│ 职责:                                                                      │
│  1. 接收 DAG，验证完整性                                                    │
│  2. 调度任务执行 (串行/并行)                                                │
│  3. 监控任务状态，处理异常                                                  │
│  4. 动态调整计划 (重规划)                                                   │
│  5. 管理 Agent 生命周期                                                     │
│  6. 汇报进度给用户                                                          │
│                                                                             │
│ 输入:                                                                      │
│  - TaskDAG (完整 DAG)                                                      │
│  - 用户目标 (原始)                                                         │
│  - 可用 Agent 列表                                                         │
│                                                                             │
│ 输出:                                                                      │
│  - 执行计划 (Execution Plan)                                               │
│  - 进度报告 (实时)                                                         │
│  - 最终结果 (聚合)                                                         │
│                                                                             │
│ 决策逻辑:                                                                  │
│  1. 调度策略: 优先级 → 依赖关系 → 资源可用性                               │
│  2. 冲突处理: 资源冲突 → 加锁等待 / 资源抢占                               │
│  3. 异常处理: 任务失败 → 重试 / 降级 / 跳过 / 请求用户                     │
│  4. 动态调整: 新信息发现 → 重规划 → 更新 DAG                               │
│                                                                             │
│ 输出格式:                                                                  │
│  ExecutionPlan = {                                                         │
│    "tasks": [                                                              │
│      {"id": "T1", "status": "scheduled", "assigned_to": "executor"},      │
│      {"id": "T2", "status": "pending", "depends_on": ["T1"]}              │
│    ],                                                                      │
│    "schedule": [                                                           │
│      {"batch": 1, "tasks": ["T1"]},                                       │
│      {"batch": 2, "tasks": ["T2", "T3"]},                                 │
│    ]                                                                       │
│  }                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Planner（规划者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Planner 规格                                                                │
│                                                                             │
│ 职责:                                                                      │
│  1. 接收用户目标，进行拆解                                                  │
│  2. 选择合适的拆解模板                                                     │
│  3. 生成候选 DAG                                                           │
│  4. 验证 DAG 可行性                                                        │
│  5. 优化 DAG (减少冗余，提升效率)                                          │
│  6. 输出人类可读的计划说明                                                  │
│                                                                             │
│ 输入:                                                                      │
│  - 用户目标 (自然语言)                                                     │
│  - 项目上下文 (RAG 检索结果)                                               │
│  - 可用工具列表                                                             │
│  - 可用的 Agent 角色                                                       │
│                                                                             │
│ 输出:                                                                      │
│  - TaskDAG (结构化)                                                        │
│  - PlanSummary (人类可读)                                                  │
│  - RiskAssessment (风险评估)                                               │
│                                                                             │
│ 决策逻辑:                                                                  │
│  1. 目标分析: 分类 → 匹配模板 → 自定义调整                                 │
│  2. 任务生成: 基于模板 + LLM 推理 → 候选任务                               │
│  3. 依赖推断: 从任务间输入输出关系推断                                      │
│  4. 可行性验证: 工具匹配 → 资源匹配 → 依赖无环                             │
│  5. 优化: 合并相似任务 → 调整粒度 → 识别并行机会                           │
│                                                                             │
│ 输出示例:                                                                  │
│  PlanSummary = {                                                           │
│    "overview": "本计划包含 6 个任务，分 3 个阶段执行",                     │
│    "stages": [                                                             │
│      {"name": "分析阶段", "tasks": ["T1", "T2"], "estimated": "5min"},    │
│      {"name": "修复阶段", "tasks": ["T3", "T4"], "estimated": "10min"},   │
│      {"name": "验证阶段", "tasks": ["T5", "T6"], "estimated": "5min"}     │
│    ],                                                                      │
│    "total_estimated": "20min",                                             │
│    "risks": [                                                              │
│      {"task": "T3", "risk": "high", "mitigation": "需要用户审批"}         │
│    ]                                                                       │
│  }                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Executor（执行者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Executor 规格                                                              │
│                                                                             │
│ 职责:                                                                      │
│  1. 接收子任务，执行 ReAct 循环                                            │
│  2. 调用工具完成具体操作                                                    │
│  3. 处理执行过程中的异常                                                    │
│  4. 输出执行结果和证据                                                      │
│                                                                             │
│ 输入:                                                                      │
│  - SubTask (单个子任务)                                                    │
│  - 上游任务输出 (inputs_from)                                              │
│  - RAG 检索结果                                                             │
│                                                                             │
│ 输出:                                                                      │
│  - 任务输出 (符合 output_schema)                                           │
│  - 执行轨迹 (每一步做了什么)                                                │
│  - 置信度评分                                                               │
│                                                                             │
│ ReAct 循环:                                                                │
│  1. Think: 分析当前状态，生成计划                                          │
│  2. Act: 调用工具或推理                                                    │
│  3. Observe: 观察结果                                                       │
│  4. Reflect: 评估是否达成目标                                              │
│  5. Decide: 继续 / 重试 / 完成 / 请求帮助                                  │
│                                                                             │
│ 工具调用规范:                                                              │
│  - 必须验证参数                                                            │
│  - 必须处理异常                                                            │
│  - 必须记录审计                                                            │
│  - 高风险操作必须请求审批                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Reviewer（审查者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Reviewer 规格                                                              │
│                                                                             │
│ 职责:                                                                      │
│  1. 审查 Executor 的输出质量                                                │
│  2. 评估是否符合验收标准                                                    │
│  3. 提出改进建议                                                            │
│  4. 拒绝不合格结果 (触发重做)                                               │
│  5. 输出质量报告                                                            │
│                                                                             │
│ 输入:                                                                      │
│  - 原始任务描述                                                             │
│  - Executor 输出                                                            │
│  - 验收标准                                                                 │
│  - 上下文 (RAG 检索)                                                       │
│                                                                             │
│ 输出:                                                                      │
│  - ReviewResult: pass | fail | conditional                                │
│  - QualityScore: 0-100                                                     │
│  - Comments: 审查意见                                                       │
│  - Recommendations: 改进建议                                                │
│                                                                             │
│ 审查维度:                                                                  │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ 维度         权重   检查内容                                       │    │
│  ├────────────────────────────────────────────────────────────────────┤    │
│  │ 完整性       30%    是否完成了所有要求                             │    │
│  │ 正确性       30%    逻辑是否正确，是否有错误                       │    │
│  │ 质量         20%    代码质量/文档质量/性能                        │    │
│  │ 一致性       10%    是否与上下文一致                               │    │
│  │ 安全性       10%    是否有安全隐患                                 │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│ 决策逻辑:                                                                  │
│  1. 分数 ≥ 80 → 通过                                                       │
│  2. 60 ≤ 分数 < 80 → 有条件通过 (需微调)                                  │
│  3. 分数 < 60 → 失败，退回 Executor 重做                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Debugger（调试者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Debugger 规格                                                              │
│                                                                             │
│ 职责:                                                                      │
│  1. 接收错误/失败信息                                                       │
│  2. 分析根因 (Root Cause Analysis)                                         │
│  3. 提出修复方案                                                             │
│  4. 执行修复 (或委托 Executor)                                              │
│  5. 验证修复有效                                                            │
│  6. 输出根因分析和修复报告                                                  │
│                                                                             │
│ 输入:                                                                      │
│  - 错误信息 (日志/堆栈/异常)                                                │
│  - 失败的上下文 (代码/配置/数据)                                            │
│  - 历史故障记录 (RAG)                                                      │
│                                                                             │
│ 输出:                                                                      │
│  - RootCause: 根因分析                                                     │
│  - FixPlan: 修复方案                                                        │
│  - FixedCode: 修复后的代码 (可选)                                           │
│  - ValidationResult: 验证结果                                               │
│                                                                             │
│ 调试流程:                                                                  │
│  1. 信息收集: 收集所有可用信息 (日志/堆栈/状态)                            │
│  2. 假设生成: 基于模式匹配 → 3-5 个可能原因                                │
│  3. 假设验证: 逐个验证 → 定位真正根因                                       │
│  4. 方案设计: 设计修复方案 (多个备选)                                       │
│  5. 方案实施: 执行修复或委托                                                │
│  6. 验证: 确认修复有效                                                      │
│  7. 经验记录: 记录到经验库                                                  │
│                                                                             │
│ 故障模式库 (内置):                                                          │
│  - NullPointerException → 检查空指针                                        │
│  - OutOfMemoryError → 检查内存泄漏                                          │
│  - ConnectionTimeout → 检查网络/超时配置                                    │
│  - 404 Not Found → 检查路由/文件路径                                        │
│  - Permission Denied → 检查权限                                             │
│  - 测试失败 → 分析失败用例                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Governor（治理者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Governor 规格                                                              │
│                                                                             │
│ 职责:                                                                      │
│  1. 审计所有操作 (全链路)                                                   │
│  2. 成本管控 (预算/告警/熔断)                                               │
│  3. 合规检查 (操作是否在允许范围内)                                         │
│  4. 权限验证 (用户是否有权执行)                                             │
│  5. 风险拦截 (高风险操作需审批)                                             │
│  6. 异常检测 (异常模式识别)                                                 │
│                                                                             │
│ 输入:                                                                      │
│  - 所有操作请求                                                             │
│  - 治理规则 (预算/权限/白名单)                                              │
│  - 用户身份                                                                 │
│                                                                             │
│ 输出:                                                                      │
│  - Action: allow | deny | require_approval                                 │
│  - AuditRecord: 审计记录                                                    │
│  - CostReport: 成本报告                                                     │
│  - Alert: 告警信息                                                          │
│                                                                             │
│ 治理规则示例:                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ 规则类型    │ 规则内容                                            │    │
│  ├────────────────────────────────────────────────────────────────────┤    │
│  │ 预算       │ 单任务成本 ≤ $1.0                                   │    │
│  │ 预算       │ 月总成本 ≤ $100                                     │    │
│  │ 权限       │ write_file 需要用户审批                              │    │
│  │ 权限       │ run_command 需要用户审批                             │    │
│  │ 白名单     │ 只能操作 /project/* 目录                             │    │
│  │ 白名单     │ 只能执行 /usr/bin/* 命令                            │    │
│  │ 异常       │ 连续 3 次失败 → 告警                                │    │
│  │ 异常       │ 单任务超过 30 分钟 → 告警                           │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│ 成本追踪:                                                                  │
│  - 每次 LLM 调用 → 记录 Token 消耗 → 累积成本                             │
│  - 每个工具调用 → 记录执行时间 → 资源成本                                  │
│  - 实时汇总 → 展示给用户                                                   │
│  - 超出阈值 → 告警/熔断                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Learner（学习者）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Learner 规格                                                               │
│                                                                             │
│ 职责:                                                                      │
│  1. 任务完成后自动复盘                                                      │
│  2. 提取成功模式和失败教训                                                  │
│  3. 生成可复用的 Skill                                                      │
│  4. 更新知识库                                                              │
│  5. 检测经验冲突                                                            │
│                                                                             │
│ 输入:                                                                      │
│  - 完整的任务执行数据 (DAG + 轨迹 + 结果)                                  │
│  - 现有经验库                                                               │
│                                                                             │
│ 输出:                                                                      │
│  - ExperienceItem: 经验项 (待审)                                           │
│  - SkillTemplate: 技能模板 (可选)                                          │
│  - ConflictReport: 冲突报告 (如有)                                         │
│                                                                             │
│ 学习质量评估:                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │ 评估维度      │ 标准                                              │    │
│  ├────────────────────────────────────────────────────────────────────┤    │
│  │ 泛化性        │ 是否适用于同类任务                                │    │
│  │ 可操作性      │ 是否可转化为具体建议                              │    │
│  │ 证据充分性    │ 是否有足够证据支持                                │    │
│  │ 唯一性        │ 是否与已有经验重复                                │    │
│  │ 时效性        │ 是否仍适用                                        │    │
│  └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Agent 协作模式

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              Agent 协作模式                                        │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式1: 顺序协作 (Sequential)                                                │   │
│  │                                                                             │   │
│  │  Planner → Executor → Reviewer → Executor (修正) → Done                    │   │
│  │                                                                             │   │
│  │ 适用: 有明确依赖链的任务                                                     │   │
│  │ 示例: 代码生成 → 审查 → 修正                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式2: 并行协作 (Parallel)                                                  │   │
│  │                                                                             │   │
│  │       ┌─→ Executor A ──┐                                                    │   │
│  │  Planner ──→ Executor B ──→ Aggregator → Done                              │   │
│  │       └─→ Executor C ──┘                                                    │   │
│  │                                                                             │   │
│  │ 适用: 可独立并行执行的任务                                                   │   │
│  │ 示例: 同时修改多个文件                                                      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式3: 辩论协作 (Debate)                                                     │   │
│  │                                                                             │   │
│  │  Planner ──→ Executor A (方案A)                                             │   │
│  │          ──→ Executor B (方案B)  ──→ Reviewer ──→ Vote ──→ Done            │   │
│  │          ──→ Executor C (方案C)                                             │   │
│  │                                                                             │   │
│  │ 适用: 有多种可行方案需要选择                                                 │   │
│  │ 示例: 架构方案选择、技术选型                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式4: 审查协作 (Review)                                                     │   │
│  │                                                                             │   │
│  │  Executor → Reviewer ──→ 通过 → Done                                       │   │
│  │                 │                                                           │   │
│  │                 └─→ 不通过 → Executor (修正) → Reviewer (再次审查)         │   │
│  │                                                                             │   │
│  │ 适用: 对质量要求高的场景                                                     │   │
│  │ 示例: 代码审查、文档审阅                                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式5: 委托协作 (Delegation)                                                 │   │
│  │                                                                             │   │
│  │  Coordinator ──→ Planner ──→ T1 → Executor A                               │   │
│  │                    │                                                        │   │
│  │                    ├──→ T2 → Executor B                                    │   │
│  │                    │                                                        │   │
│  │                    └──→ T3 → Executor C                                    │   │
│  │                                                                             │   │
│  │ 适用: 复杂任务需要专业分工                                                   │   │
│  │ 示例: 软件开发 (前端/后端/测试)                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 模式6: 迭代协作 (Iterative)                                                  │   │
│  │                                                                             │   │
│  │  Planner → Executor → Debugger → Executor (修正) → Reviewer → Done          │   │
│  │      ↑______________________________________________|                      │   │
│  │                                                                             │   │
│  │ 适用: 需要多轮迭代优化的场景                                                  │   │
│  │ 示例: 性能调优、Bug 修复                                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Agent 间通信机制

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          Agent 通信机制                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         通信架构                                            │   │
│  │                                                                             │   │
│  │                        ┌─────────────────────┐                              │   │
│  │                        │   Message Bus       │                              │   │
│  │                        │   (消息总线)        │                              │   │
│  │                        └──────────┬──────────┘                              │   │
│  │                                   │                                         │   │
│  │         ┌─────────────────────────┼─────────────────────────┐              │   │
│  │         │                         │                         │              │   │
│  │         ▼                         ▼                         ▼              │   │
│  │  ┌───────────┐            ┌───────────┐            ┌───────────┐          │   │
│  │  │ Coordinator│            │  Planner  │            │ Executor  │          │   │
│  │  └───────────┘            └───────────┘            └───────────┘          │   │
│  │                                                                             │   │
│  │  通信方式: 间接通信 (通过工作记忆 + 消息总线)                               │   │
│  │  优势: 可审计、可追溯、解耦                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         消息格式                                            │   │
│  │                                                                             │   │
│  │  {                                                                          │   │
│  │    "id": "msg_123456",                                                      │   │
│  │    "from": "planner",                                                       │   │
│  │    "to": "executor",            // 指定接收者 (可选, 不指定则广播)          │   │
│  │    "type": "task_assignment",   // 消息类型                                 │   │
│  │    "correlation_id": "task_T2", // 关联的任务 ID                           │   │
│  │    "payload": {                                                             │   │
│  │      "task_id": "T2",                                                       │   │
│  │      "description": "分析代码结构",                                          │   │
│  │      "input": {...},                                                        │   │
│  │      "deadline": "2026-08-21T12:00:00Z"                                    │   │
│  │    },                                                                       │   │
│  │    "priority": 5,                 // 1-10                                    │   │
│  │    "ttl": 300,                    // 5分钟过期                              │   │
│  │    "timestamp": "2026-08-21T10:00:00Z"                                     │   │
│  │  }                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         消息类型                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┬──────────────────────────────────────────────────────┐  │   │
│  │  │ 类型           │ 说明                                                │  │   │
│  │  ├───────────────┼──────────────────────────────────────────────────────┤  │   │
│  │  │ task_assignment│ 分配任务给某个 Agent                                │  │   │
│  │  │ task_completed │ 任务完成，通知上游                                  │  │   │
│  │  │ task_failed   │ 任务失败，通知协调器                                │  │   │
│  │  │ request_help  │ 请求其他 Agent 帮助                                  │  │   │
│  │  │ status_update │ 状态更新                                            │  │   │
│  │  │ approval_request│ 请求用户审批                                       │  │   │
│  │  │ approval_response│ 用户审批响应                                      │  │   │
│  │  │ require_review │ 请求 Review                                        │  │   │
│  │  │ review_result  │ 审查结果                                           │  │   │
│  │  │ ask_clarification│ 请求澄清                                          │  │   │
│  │  │ inform        │ 信息通知 (广播)                                      │  │   │
│  │  └───────────────┴──────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         通信约束                                            │   │
│  │                                                                             │   │
│  │  1. 所有通信必须通过 Message Bus，禁止 Agent 直接调用                       │   │
│  │  2. 所有通信记录到审计日志                                                  │   │
│  │  3. 消息有 TTL，过期自动清理                                                │   │
│  │  4. 支持消息优先级 (高优先级消息优先处理)                                   │   │
│  │  5. 消息持久化 (重启后恢复)                                                 │   │
│  │  6. 防止消息风暴 (限流措施)                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 Agent 生命周期管理

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          Agent 生命周期                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         状态转换图                                          │   │
│  │                                                                             │   │
│  │                    ┌─────────┐                                              │   │
│  │                    │ CREATED │ (Agent 创建)                                 │   │
│  │                    └────┬────┘                                              │   │
│  │                         │ 初始化                                             │   │
│  │                         ▼                                                   │   │
│  │                    ┌─────────┐                                              │   │
│  │                    │  IDLE   │ (等待任务)                                   │   │
│  │                    └────┬────┘                                              │   │
│  │                         │ 分配任务                                           │   │
│  │                         ▼                                                   │   │
│  │                    ┌─────────┐                                              │   │
│  │             ┌─────│ RUNNING │─────┐                                        │   │
│  │             │     └─────────┘     │                                        │   │
│  │             │                     │                                        │   │
│  │          任务完成              出错                                         │   │
│  │             │                     │                                        │   │
│  │             ▼                     ▼                                        │   │
│  │        ┌─────────┐        ┌─────────────┐                                  │   │
│  │        │  DONE   │        │   ERROR     │                                  │   │
│  │        └─────────┘        └──────┬──────┘                                  │   │
│  │             │                    │                                          │   │
│  │             │              ┌─────┴─────┐                                   │   │
│  │             │              │           │                                   │   │
│  │             │          重试成功     重试失败                                │   │
│  │             │              │           │                                   │   │
│  │             │              ▼           ▼                                   │   │
│  │             │        ┌─────────┐  ┌─────────────┐                         │   │
│  │             │        │ RUNNING │  │   FAILED    │                         │   │
│  │             │        └─────────┘  └──────┬──────┘                         │   │
│  │             │                            │                                 │   │
│  │             └────────────┬───────────────┘                                 │   │
│  │                          │                                                 │   │
│  │                          ▼                                                 │   │
│  │                    ┌─────────┐                                             │   │
│  │                    │  IDLE   │ (回到空闲, 等待下一任务)                    │   │
│  │                    └─────────┘                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         生命周期事件                                        │   │
│  │                                                                             │   │
│  │  ┌───────────────┬──────────────────────────────────────────────────────┐  │   │
│  │  │ 事件           │ 触发条件                                            │  │   │
│  │  ├───────────────┼──────────────────────────────────────────────────────┤  │   │
│  │  │ on_created    │ Agent 实例化完成                                    │  │   │
│  │  │ on_assigned   │ 分配到任务                                          │  │   │
│  │  │ on_started    │ 开始执行任务                                        │  │   │
│  │  │ on_progress   │ 执行进度更新 (每步)                                 │  │   │
│  │  │ on_completed  │ 任务成功完成                                        │  │   │
│  │  │ on_failed     │ 任务失败                                            │  │   │
│  │  │ on_retry      │ 重试任务                                            │  │   │
│  │  │ on_timeout    │ 超时                                                │  │   │
│  │  │ on_blocked    │ 被阻塞 (等待资源/用户)                              │  │   │
│  │  │ on_resumed    │ 恢复执行                                            │  │   │
│  │  │ on_terminated │ 终止 (主动或被动)                                   │  │   │
│  │  └───────────────┴──────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 4.6 多 Agent 编排实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 单 Agent 执行运行时 | `exec/developer.py` + `execution_loop.py` + `agent_runtime.py` | ✅ |
| 7 角色资产链（当前实现） | `session/pipeline_runner.py`（S10-084，单模型换提示词） | 🚧 |
| 专家实体/注册/装配 | `agent_entity/agent_registry/expert_factory`（M2） | 📐 |
| 交接总线 | `handoff_bus.py`（M2）+ `session/conflicts.py`（冲突，已存在） | 📐 |
| 多 LLM 分工路由 | 设计（A6 后置） | 📐 |

**完成度**：单 Agent 执行真实（✅）；"真团队"（实体+装配+交接）是 M2 主线（📐）。

### 4.7 多 Agent 协作 × 调度执行（衔接 §3.9）★

> 2026-08-22 补充: §3.9 的整链调度如何驱动多 Agent 协作——调度决定"谁就绪、给谁、何时并发"，
> 协作决定"产物如何交接、如何共识"。

#### 4.7.1 调度驱动协作（DAG → 协作执行）

```
§3.9 整链调度（关键路径 / 依赖 / 并行 / 资源）
  → 就绪原子任务（依赖全部完成）
  → Agent 分配（AgentMatcher：role/skill/成功率）
  → 协作执行：
      顺序依赖 → 交接链（HandoffBus：PM→Market→…→SeniorPM）
      无依赖   → 并行协作（多 Agent 同时，各产 artifact）
      冲突     → ConflictResolver 串行化
  → 每步产物 → artifact（parent_artifact 互引）
  → 关键节点卡口（§3.8：审批 / 风险 / 质量）
  → 下一批就绪任务
```

#### 4.7.2 调度情形 → 协作模式映射

| §3.9 调度情形 | 协作模式 | 机制 |
|---|---|---|
| 顺序依赖链 | 顺序协作（Sequential） | HandoffBus 交接（上一产出 → 下一输入） |
| 无依赖并行 | 并行协作（Parallel） | 多 Agent 同时执行，产物独立落盘 |
| 依赖汇聚节点 | 评审/共识 | 多路产物 → ConflictResolver / ReviewGate |
| 任务失败 | 修复协作 | ReplanningEngine → 修复 Agent / 重规划 |

#### 4.7.3 交接语义（HandoffBus 在调度中的位置）

- **交接 = 调度中的"顺序边"**：下游 Agent 消费上游产物（`parent_artifact` 引用），不重复理解
- 交接消息：`{from, to, artifacts[], decisions[], constraints[]}`
- **关键节点（§3.8）可挂在任意交接点**：如 PM→Market 前审需求、QA 后审测试报告

#### 4.7.4 实现衔接

| 环节 | 状态 |
|---|---|
| AgentMatcher / ConflictResolver / artifact_registry / ReplanningEngine / LLMPlanner | ✅ 已有 |
| AgentEntity / HandoffBus（交接执行） | 📐 M2 |
| 整链调度器驱动协作（§3.9 就绪队列 → HandoffBus 触发） | 📐 M3 |

**结论**：§3.9 决定"调度节奏"，§4.7 决定"协作方式"——两者在 M2/M3 由 `HandoffBus` + 整链调度器合成"一个会协作的 AI 团队"。

### 4.8 多 Agent 分配机制（task → best agent）★

> 2026-08-22 补充: 此前"分配"仅零散提及（§3.9.3/§4.7.1）；真实实现 `AgentMatcher` 已很成熟，
> 本节给出完整的分配设计并与实现锚定。

#### 4.8.1 分配目标

每个任务 → **最佳 Agent**（最大化成功率/质量，最小化成本/耗时），且**可解释**（为什么派给这个 Agent）。

#### 4.8.2 评分模型（真实实现 AgentMatcher）

```
score = skill 匹配（必备技能命中率）
      × 成功率因子（0.5 + 0.5 × 历史成功率）
      × 成本归一化（1 / avg_cost，最便宜 Agent = 1.0）
reason: "skill match 92% (python/api/database), 成功率 95%"
```

- **skill 匹配**：任务类型 → 必备技能推导 → 对 Agent 技能集合命中率（无硬编码关键词决策）
- **成功率**：来自真实执行记录（AgentMetrics）
- **成本**：Agent 平均成本归一化
- **可解释**：分配理由随执行记录/审计可查

#### 4.8.3 数据源（失败安全）

| 源 | 内容 | 状态 |
|---|---|---|
| AgentRegistry | 每个 Agent 的 skills/role/成本画像（agents.json） | ✅ |
| AgentMetrics | 真实执行记录 → 成功率/成本（load_from_records） | ✅ |
| 惰性加载 | 缺失/损坏 → 默认注册表/空 metrics（不抛） | ✅ |

#### 4.8.4 分配时机（静态 + 动态）

```
静态分配: 执行前 AgentAssignment（pipeline.py: task → agent，✅ 已实现）
动态分配: 调度时（§3.9 就绪队列）按当前真实数据实时匹配（📐 M3）
```

#### 4.8.5 扩展规则（设计）

- **画像优先**：M4 后按 AgentProfile（成功率/质量/成本/速度）排序（对齐 §7.5）
- **负载均衡**：忙碌 Agent 排队；同分取空闲
- **硬约束**：角色（required_role）、成本预算、高安全任务限白名单 Agent
- **回退**：无匹配 → 默认 Agent / 明确报错（不静默）

#### 4.8.6 实现衔接

| 环节 | 状态 |
|---|---|
| AgentMatcher（评分/可解释） | ✅ 已实现 |
| AgentAssignment / select_agent（静态分配） | ✅ 已实现 |
| 动态分配（调度时实时匹配） | 📐 M3 |
| 画像优先 / 负载均衡 | 📐 M4 |

### 4.9 数据来源与冷启动（分配/学习/画像的数据从哪来）★

> 2026-08-22 补充: 分配评分、学习画像、经验检索依赖的数据，归纳为**两类来源**：初始配置（人工/预置种子）+ 运行自产（系统执行时产生，越用越准）。

#### 4.9.1 数据来源总表

| 数据 | 来源 | 谁产生 | 状态 |
|---|---|---|---|
| Agent 角色/技能/成本画像 | `agents.json`（`~/.factory/agents/`）默认注册表（backend-1/flutter-dev/tester-1 预置）+ 用户可改 | 人工/预置种子 | ✅ |
| 成功率/绩效 | `execution_records.json` → `AgentMetrics.compute` → `agent_metrics.json` | **系统自产**（每次执行） | ✅ |
| 成本 | `ExecutionResult.usage`（input/output tokens + estimated_cost）由 Provider 返回并落库 | **系统自产** | ✅ |
| 经验 | `memory/extraction.py` 从 execution_records/repair_task/replanning_decisions 提取（FAILURE/SUCCESS 模式） | **系统自产** | ✅ |
| 审计/血缘 | 系统事件（audit 33+ 类型） | **系统自产** | ✅ |
| 项目/仓库 | `org/projects.json` + 用户仓库 | 用户 + 系统 | ✅ |
| 领域知识库 | 设计（T4） | 待接入 | 📐 |

#### 4.9.2 两类来源的本质

```
A. 初始配置（种子，人工/预置）:
   agents.json（角色/技能/成本画像）— 冷启动的"起点"，只此一处需人工/默认

B. 运行自产（数据飞轮，系统自己产生）:
   每次执行 → execution_records → 成功率/成本/经验/审计
   → 分配更准（AgentMatcher）· 画像更可信（AgentProfile）· 经验更丰富（RAG）
   → 越用越准（自我进化闭环的原料）
```

#### 4.9.3 冷启动问题（诚实）

- 新 Agent 无历史成功率 → AgentMatcher 用默认因子（`0.5 + 0.5 × 历史`，历史=0 → 0.5）兜底
- 成本用默认 `avg_cost`；样本不足不计权（§7.5 可信度护栏）
- **数据飞轮前提**：先用起来（预置种子 + 默认兜底）→ 产生数据 → 分得更准。这是"先跑通再变强"的原因，也是 M4 前分配"够用即可"的原因

#### 4.9.4 与统一契约的关系

- 所有自产数据都经统一契约（§2.10-11）：事件/记录带 `id/timestamp/source/version` + 血缘 → 可追溯、可重放（§5.6）
- 外部数据源（知识库/第三方）未来经同一契约接入（T4/M5）

### 4.10 当前 7 角色实现实况（🚧 的真相，M2 升级基线）

> 2026-08-22 补充: §4.6 标"7 角色当前是提示词 🚧"——本节把这句话变成可核对的实况，
> 并标出哪些是真实能力、哪些是占位模板（M2 升级的精确对象）。

#### 4.10.1 实现方式（当前 `session/pipeline_runner.py`）

```
7 角色 = ROLES 元组 (pm/market/competitive/ux/architect/qa/prd)
每个角色:
  _generate: llm_fn(同一模型) 换 7 个 prompt   ← "换提示词" 的真相
  失败/无 LLM → _deterministic: 9-23 行规则模板 ← 兜底
无 Agent 实体 · 无角色记忆/技能/评价 · 角色间不消费上一产出（无交接）
```

#### 4.10.2 逐角色实况（真实能力 vs 占位）

| 角色 | 产物 | LLM 模式 | 确定性兜底 | 真实性 |
|---|---|---|---|---|
| pm | product | prompt | 12 行模板（定位/价值/能力/非目标） | 🟡 模板 |
| market | market_analysis | prompt | **复用 ProductIntelligenceEngine**（真市场规模/趋势） | 🟢 真引擎 |
| competitive | competitive_analysis | prompt | **复用 ProductIntelligenceEngine**（真竞品/差异化） | 🟢 真引擎 |
| ux | ux_flow | prompt | 12 行模板（流程/页面/信息架构占位） | 🔴 占位 |
| architect | architecture | prompt | 16 行模板（platform→架构规则） | 🟡 规则 |
| qa | test_plan | prompt | 10 行模板（测试层级占位） | 🔴 占位 |
| prd | prd | prompt | **复用 ProductDocument**（6 节 PRD） | 🟡 规则 |

**结论**：7 角色中 **2 个有真引擎兜底（market/competitive）**，3 个规则/模板（pm/architect/prd），2 个纯占位（ux/qa）；LLM 模式全是"同一模型换 prompt"。

#### 4.10.3 M2 升级基线（把 🚧 变 ✅ 的精确对象）

| 升级 | 从 | 到（M2） |
|---|---|---|
| 实体 | 无 | AgentEntity（role/provider/skills/eval/memory/profile） |
| 装配 | 无 | ExpertFactory 装配 + 校验（缺 skill 报错） |
| 交接 | 顺序写 artifact，互不消费 | HandoffBus（下游消费上游产出，parent_artifact） |
| 评价/记忆 | 无 | evaluation_ref / memory_ref 挂载（M4 闭环） |
| 占位角色 | ux/qa 模板 | 接真引擎/LLM 深度（M3 深度化） |


### 4.11 上下文管理体系（Agent 工作的"工作台"）★

> 2026-08-22 补充（用户关键判断）: 上下文管理是 Agent 能干活的前提——文档此前仅零散提及
> （build_prompt / 检索 / 交接），现补**系统设计**：分层 / 窗口管理 / 检索策略 / 跨任务 / 隔离。

#### 4.11.1 上下文分层（五层）

```
L0 会话/项目上下文: 项目状态 · 当前目标 · 关键决策（持久化）
L1 任务上下文:      任务 Plan（§3.8）· 输入 · Agent 角色/技能
L2 检索上下文:      RAG 检索的相关经验/知识/文件（§8.5/§17.12）
L3 交互上下文:      工具结果 · 本任务内 LLM 往返历史
L4 交接上下文:      上游 Agent 产出（HandoffBus §4.7）
```

#### 4.11.2 上下文窗口管理（token 预算分配）

```
窗口分配（按优先级占 token）:
  任务核心(L1) > 检索相关(L2 top-k) > 项目状态(L0 摘要) > 历史(L3 滚动摘要)
超出 → 截断/压缩/摘要化:
  长历史 → 滚动摘要（保留结论/决策，丢弃过程）
成本: 上下文 = token = 成本（§6.2 预算模型联动）
```

#### 4.11.3 检索进上下文的策略（衔接 §8.5/§17.12）

- 检索结果按 相关度 × 置信度 取 top-k（不塞满窗口）
- 数据分级（§8.5.9）：只进高价值内容；原始日志/临时不进
- **引用可审计**：进上下文的内容带 source（§17.12 决策回路）

#### 4.11.4 跨任务 / 跨会话上下文

```
项目级: project state 持久化（execution_state/artifacts）——跨任务自动带
长期:   经验/画像（memory）——检索进上下文（§17.12）
会话:   仅会话内存（不持久，隐私 §18）
交接:   HandoffBus 消息 = 显式上下文传递（§4.7，带 parent_artifact）
```

#### 4.11.5 上下文隔离与安全

- 每项目/每会话隔离（§18 数据主权）；敏感内容脱敏后进上下文
- 越权内容不进上下文（权限门 §6.3）

#### 4.11.6 实现对照

| 项 | 状态 |
|---|---|
| 基础 prompt 组装（`exec/developer.py build_prompt`） | ✅ 已实现 |
| RAG 检索进上下文（memory/retrieval） | ✅ 已实现 |
| 交接上下文（HandoffBus 消息） | 📐 M2 |
| 滚动摘要 / 窗口预算分配 / 跨任务自动上下文 | 📐 M3/M4 |

**结论**：基础上下文（prompt+检索）✅；**上下文管理闭环**（分层分配/摘要/交接/隔离）是 M2-M4 的一部分——没有它，Agent 做复杂任务会"记不住前面"。


#### 4.11.7 上下文成本管理（上下文 = token = 成本，必须控）★

> 2026-08-22 补充（用户指出）: 上下文直接决定成本——不只"管理窗口"，还要**成本管理**。

**成本控制策略**

| 策略 | 机制 |
|---|---|
| 最小化 | 只带必要上下文（§4.11.3 top-k + 数据分级），不塞满窗口 |
| 压缩/摘要 | 长历史 → 滚动摘要（省 token，保留决策） |
| 检索限流 | top-k 上限（如 k≤8），相关度阈值过滤噪音 |
| **缓存复用** | 相同项目上下文缓存（跨任务复用，不重复计费） |
| 模型分级 | 简单任务用便宜模型（§T5），重活才大模型 |
| 降级 | 预算水位高 → 减少检索/用摘要/切小模型（§6.2 review/block 联动） |

**成本指标**

```
每任务上下文成本（token × 单价）
上下文占比 = 上下文 token / 总 token（检测"上下文膨胀"：占比 > 60% → 警告）
上下文缓存命中率（命中 → 省 token）
```

**与 §6.2 联动**：上下文成本计入预算维度（llm 类）；超预算 → 降级策略自动生效。

#### 4.11.8 上下文质量管理（不是越多越好，噪音上下文毁输出）★

**质量维度**

| 维度 | 问题 | 机制 |
|---|---|---|
| 相关性 | 噪音上下文稀释注意力 | 检索 top-k × 相关度阈值（§4.11.3） |
| 新鲜度 | 旧决策 vs 新状态冲突 | 时间戳排序；新状态优先 + 标注"已过时" |
| 冲突 | 上下文自相矛盾 | 冲突检测 → 以最新/权威为准 + 标注 |
| 冗余 | 重复内容浪费窗口 | 去重（同源合并） |
| 摘要保真 | 摘要丢关键决策 | 摘要强制保留 决策/结论/约束（不丢过程） |

**质量评估与反馈**

```
上下文质量分（相关度/新鲜度/冲突数 合成）
  → 与输出质量关联（§17.16 完善对象之一）
  → 输出差 → 调整检索/摘要策略（自我完善 §17.16）
```

**落地**：top-k/数据分级 ✅（§4.11.3）；缓存复用/冲突检测/质量分/成本指标 📐 M3/M4


#### 4.11.9 上下文规则与格式（可落地规范：格式 / 预算 / 阈值 / 公式）★

> 2026-08-22 补充（用户要求细化规则/格式/形式）: 上下文管理从"定性"到"定量规范"。

**① ContextItem 统一格式**

```json
{ "id": "ctx-001", "layer": "L2", "type": "retrieval",
  "source": "memory/experience", "priority": 7,
  "tokens": 850, "content": "...", "ref": "exp-xxx",
  "timestamp": "UTC", "confidence": 0.92 }
```

**② 窗口 token 预算（默认分配规则）**

```
总预算 = min(模型窗口 × 0.8, 配置上限)
  L1 任务核心   30%   （不可丢）
  L0 项目状态   15%   （摘要化后）
  L2 检索       25%   （top-k ≤ 8，每条 ≤ 2000 token）
  L3 交互历史   20%   （滚动摘要）
  L4 交接       10%   （HandoffContext）
  预留          10%   （工具结果/系统）
超出 → 丢弃优先级: L3 > L2 > L0 > L4 > L1（L1 永不丢）
```

**③ 检索规则（阈值）**

```
top-k ≤ 8 · 相关度 ≥ 0.6 · 置信度 ≥ 0.5（样本<5 不计）
每条 ≤ 2000 token（超 → 截断）
排序分 = 相关度 × 置信度 × 新鲜度(1/(天数+1))
```

**④ 滚动摘要格式**

```json
{ "version": 3, "window": {"from": "ts1", "to": "ts2"},
  "decisions": ["..."], "conclusions": ["..."],
  "open_issues": ["..."], "constraints": ["..."],
  "dropped_tokens": 12000 }
触发: 历史 token > 窗口 20% 或 轮次 > N
规则: 保留 决策/结论/未决/约束，丢弃 过程/工具输出细节
```

**⑤ 交接上下文格式（HandoffContext）**

```json
{ "from_agent": "pm", "to_agent": "market",
  "task_id": "task-001", "artifacts": ["art-001"],
  "decisions": ["..."], "constraints": ["..."],
  "pending_issues": ["..."], "context_ref": "art-001",
  "token_budget": 2000 }
```

**⑥ 成本规则**

```
上下文成本 = Σ(item tokens) × 单价
上下文占比 = 上下文 token / 总 token；> 60% → 警告 + 强制压缩
L0 项目缓存命中率目标 > 50%（跨任务复用）
```

**⑦ 质量规则（公式）**

```
质量分 = 0.5×相关度 + 0.2×新鲜度 + 0.2×(1 - 冲突数/总项) + 0.1×去重率
质量分 < 0.6 → 触发检索/摘要策略调整（§17.16 自我完善）
冲突处理: 同 key 多值 → 最新时间戳优先 + 标注 superseded
```


### 4.12 核心执行原语：Every Node Is Autonomous（节点自治 ★）★

> 2026-08-23 补充（外部架构评审 + Founder 确认）: 把"每个节点独立完整闭环"钉死为 AI Factory 的**核心执行原则**——
> 不是"很多 Agent 的软件"，而是**统一的 AI 劳动力生产模型**（Autonomous Node Runtime 承载所有岗位）。

#### 4.12.1 定义：节点 = 自治生产单元（Self-contained Autonomous Production Unit）

```
Node = Role + Context + Objective + Tools + Loop + Verification + Evidence
```

#### 4.12.2 节点的 10 项自治属性

| # | 属性 | 说明 |
|---|---|---|
| 1 | 明确目标 | Objective（做什么） |
| 2 | 独立上下文 | 自己的 Context（§4.11，不无限膨胀） |
| 3 | 自己的 Agent | Role（谁来做） |
| 4 | 自己的工具 | Tools（用什么） |
| 5 | 自己的执行 Loop | Execute/Delegate |
| 6 | 自己的验证机制 | Verify（怎么算对） |
| 7 | 自己的失败恢复 | Repair/Replan（§17.13） |
| 8 | 自己的 Evidence | 证据（§5.1-5.6） |
| 9 | 自己的完成条件 | 明确验收（§1.7） |
| 10 | 可递归创建子节点 | 复杂 → 拆 Child Nodes |

#### 4.12.3 节点生命周期（标准原语）

```
Context + Goal + Constraints
  → Planning
  → Execute / Delegate（复杂 → 递归创建 Child Nodes）
  → Observe
  → Verify
  → Evidence Produced
  → PASS → COMPLETE
  → REPAIR / REPLAN（失败恢复，对应 ReplanningEngine ✅）
```

#### 4.12.4 递归分解原则（复杂度用递归，不用扩上下文）

```
Node
 ├─ 简单 → 自己完成
 └─ 复杂 → 创建 Child Nodes（各自完整闭环）→ 汇总 → 父节点验证 → 完成
```

**解决的核心问题**：复杂度通过递归分解，而非不断扩大单个 Agent 的上下文和 Loop（传统 Agent 越 loop 越乱）。

#### 4.12.5 父节点验证铁律（Parent Never Trusts Child）

```
Child 声称完成 ≠ 完成
Child → Evidence → Child Verification → Parent Verification
（对应 §5.6 可追溯/可重放 + §1.7 验收，杜绝"自报告即事实"）
```

#### 4.12.6 与 AI 公司岗位的对应

```
产品任务 → 市场研究 / 产品策略 / PRD / UX / 架构 / 后端 / 前端 / QA / DevOps
每一个 = 节点 = Role + Context + Objective + Tools + Loop + Verification + Evidence
```

#### 4.12.7 统一 Node Runtime（承载整个 AI 公司所有岗位）

```
Production Flow: Idea → Brainstorm → PRD → Task Tree
  → Autonomous Node Runtime（统一执行原语）
  → Recursive Node（Execute / Verify / Evidence / Repair / Replan / Loop）
```

**价值**：一套 Runtime 承载所有角色——不重复造"每个 Agent 的执行器"，只换 角色/上下文/目标/工具/证据。

#### 4.12.8 与现有实现映射

| 节点要素 | 现有实现 | 状态 |
|---|---|---|
| 执行（Execute） | DeveloperAgent / ExecutionLoop / repo_mode | ✅ |
| 验证（Verify） | evaluator / pytest | ✅ |
| 证据（Evidence） | EvidenceBundle | ✅ |
| 修复（Repair） | quality.repair / ReplanningEngine | ✅ |
| 重规划（Replan） | ReplanningEngine（8 决策） | ✅ |
| 递归（Recursive） | §3.7 递归原子拆解 | 📐 M3 |
| 统一 Node Runtime（标准化） | 各节点分散实现 | 📐 M3 工程化 |

**结论**：节点自治的**大部分原语已实现**（执行/验证/证据/修复/重规划 ✅）；缺的是把它们**标准化为统一 Node Runtime** + **递归闭环**（M3 工程化）。


#### 4.12.9 全层级自治：每一层都有 Loop（不只叶子）★

> 2026-08-23 修正（Founder 关键判断）: 递归分解不是"只有叶子有 loop"——**子任务 / 子子任务 / 子子子任务…每一层节点都是 Autonomous Node，都有自己的完整 Loop**。

```
复杂任务 Node（有自己的 Loop）
 └─ 子任务 Node（有自己的 Loop）
     └─ 子子任务 Node（有自己的 Loop）
         └─ 子子子任务 Node / 原子（有自己的 Loop）
每一层: 自己的 Context/Goal/Constraints → Plan → Execute/Delegate
      → Observe → Verify → Evidence → PASS/Repair/Replan → Complete
```

**非叶子节点 vs 叶子节点（区别只在"执行方式"，不在"是否自治"）**

| | 叶子（原子）节点 | 非叶子（组合）节点 |
|---|---|---|
| 执行 | 直接做原子动作（单工具/单文件） | **委派**给子节点（Delegate） |
| Loop | 执行 Loop | **编排 Loop**（委派→观察子节点 Evidence→汇总验证→自身 Evidence→恢复） |
| 验证 | 原子验收 | 汇总验证（子节点证据链 + 自身完成条件） |
| Evidence | 自身证据 | 自身证据 + 子节点证据聚合 |
| 恢复 | Repair/Replan 单节点 | 子节点失败→重派/重组/换策略（§17.13） |

**修正 §3.7.2 口径**：非叶子节点"不直接执行"≠"没有 loop"——它有完整的**编排 Loop**（委派、观察、汇总验证、自身证据、恢复），只是不做原子动作。


#### 4.12.10 任务的维度：Tree(1维) + DAG(依赖) + 调度(N维) ★

> 2026-08-23 补充（Founder 关键判断）: 拆分+loop 解决约 70% 问题，但**树无法表达依赖**——
> 树是 1 维（父子层级），任务是 N 维（拆解+依赖+时序+资源+状态+价值）。

**10.1 Tree 是 1 维（只表达拆解）**

```
只表达: 父子层级（复杂→子任务→子子任务…）
无法表达: 兄弟依赖 · 汇聚点 · 并行关系 · 关键路径 · 反向依赖
```

**10.2 任务是 N 维**

| 维 | 表达 | 载体 |
|---|---|---|
| 拆解 | 父子层级 | Tree（§3.7 递归） |
| **依赖** | 谁依赖谁（横向） | **DAG**（§3.5 inputs_from / output_schema） |
| 时序 | 顺序 / 并行 / 关键路径 | 调度器（§3.9） |
| 资源 | Agent / 工具 / 预算 / LLM | AgentMatcher + budget |
| 状态 | 未开始 / 运行 / 完成 / 失败 / 阻塞 | execution_state |
| 价值 | P0/P1 / 优先级 | tasks.json |

**10.3 树 + DAG 结合（完整任务模型）**

```
拆解树（层级组织）
  + 依赖边（横向 DAG: inputs_from = 消费哪些节点的输出）
  = 带层级的 DAG（有向无环图，节点带父子层级）

节点 loop 内:
  消费 inputs_from（依赖节点的输出）→ 执行 → 产出 outputs → 触发下游节点
父节点:
  等所有子节点满足依赖 + 各自验证 → 汇总验证 → 自身 Evidence
```

**10.4 70% vs 30%（诚实边界）**

```
70%: 独立单线任务（一功能一拆，节点自治 loop 足够）
30%: 有依赖的复杂项目（API→前端→测试 · 汇聚 · 关键路径 · 共享模块）
     → 必须 DAG 依赖调度（§3.9 拓扑/并行/关键路径）
```

**10.5 与现有实现映射**

| 项 | 状态 |
|---|---|
| 节点自治 Loop（执行/验证/证据/恢复） | ✅ 已实现 |
| DAG 数据结构（inputs_from） | 📐 目标态（§3.5） |
| 依赖驱动调度（拓扑/并行/关键路径） | 📐 M3（§3.9） |

**结论**：**节点自治（树）解决"能不能做"；DAG 依赖（图）解决"先做哪个/谁等谁"**——两者正交、缺一不可，合起来才是完整任务模型。

**10.6 概念对照：Tree / DAG / Workflow / Task Graph / Plan（概念分层）**

> 2026-08-23 补充（Founder 提问）: 五个词经常混用——它们不是同一维度的东西，
> 而是"模板 → 拆解 → 依赖 → 决策"四层的不同载体。先分层，再谈实现。

| 概念 | 英文 | 本质 | 维度 | 回答的问题 | 载体 |
|---|---|---|---|---|---|
| **任务树** | Task Tree | 拆解结构（父子层级） | 1 维 | 一件事怎么拆成子事？ | §3.7 递归拆解 |
| **依赖图** | DAG | 依赖结构（有向无环边） | 横向 | 谁等谁？谁先做？ | §3.5 TaskDAG / `session/dependencies.py` |
| **任务图** | Task Graph | 任务+关系的统称（Tree 是特例、DAG 是常用形态） | 混合 | 本次任务的全部节点与关系长什么样？ | 带层级 DAG（§4.12.10.3） |
| **工作流** | Workflow | 可复用流程模板（预定义步骤序列） | 复用 | 这类任务的标准做法是什么？ | FactorySpec.workflows / §7.2 |
| **执行计划** | Plan | 执行前决策（怎么做/卡在哪/何时做） | 决策 | 就绪后先做哪个、怎么并行、哪里要卡？ | §3.8 任务级 + §3.9 整链 |

**Workflow vs Task Graph（模板 vs 实例——最容易混的一对）**

```
Workflow（模板/类）:  需求→设计→编码→测试→部署    ← 可复用的"标准做法"
    │  实例化到具体项目（绑定目标/仓库/Agent/状态）
    ▼
Task Graph（实例/对象）: 本次任务的节点 + 依赖 + 运行时状态
    = 拆解树（父子） + 依赖边（DAG） + 状态/证据/耗时（可回放）
```

- **Workflow 是"蓝图"**：不绑定具体项目，随 FactorySpec 分发、跨项目复用（bug_fix_workflow / feature_development）。
- **Task Graph 是"本次运行"**：绑定具体目标，节点带状态/证据/耗时，可审计回放（§5.6）。
- **DAG 是两者共用的数学骨架**：Workflow 内部的模板依赖、Task Graph 内部的实例依赖，都是 DAG（无环 + 有向边）。
- **Task Tree 是"怎么拆"的组织视图**（父子层级）；**DAG 是"谁等谁"的执行视图**（横向依赖）；两者叠加 = 带层级 DAG = 本项目 Task Graph 的完整形态。

**plan + tree + workflow（一句话链路）**

```
目标 → 匹配 Workflow 模板（复用标准做法）
     → 实例化 + 递归拆解 → Task Tree（拆到原子，§3.7）
     → 补依赖边 → Task Graph（带层级 DAG，§4.12.10.3）
     → 整链 Plan（§3.8 任务级 + §3.9 关键路径/卡口/资源）
     → 调度执行（拓扑/并行/串行）→ 证据/审批/交付
```

**结论**：**Tree 管"拆"、DAG 管"等"、Workflow 管"复用"、Plan 管"决策"**——四者正交互补；
"Task Graph"是树与 DAG 叠加后的完整任务形态（带层级 DAG），不是第五个独立概念。

**10.7 完整任务模型补全：边语义 / 动态演化 / 状态机 / 资源映射 / 模板嵌套 / Plan 边界**

> 2026-08-23 补充（Founder 追问"这样就完整了？"）: 10.6 只回答了"静态结构"层，
> 完整任务模型还差 6 块——其中 3 块代码已实现，但概念层没有点破。

**① DAG 的边有两种语义（控制流 vs 数据流，正交）**

```
depends_on（控制边）: T2 必须在 T1 之后执行        → 时序
inputs_from（数据边）: T2 消费 T1 的输出            → 数据
```

| 组合 | 含义 | 例子 |
|---|---|---|
| 只有控制边 | T1 先做、T2 后做，但 T2 不用 T1 数据 | 串行构建步骤（lint → build） |
| 只有数据边 | T2 需要 T1 输出，但可提前准备 | 预取/流式消费 |
| 两者叠加 | 完整 DAG = 控制 DAG + 数据 DAG | §3.5 SubTask 同时含 depends_on + inputs_from |

> 代码现状：`session/dependencies.py` 已实现控制依赖（拓扑/环检测 ✅）；inputs_from 数据边是 M3 目标态（📐）。

**② 静态图 vs 动态图（图是边执行边演化的活图）**

```
静态: Workflow 模板 / Task Graph 实例（画完再跑）
动态: 执行中失败 → Repair/Replan → 增删节点/边 → 图结构变化
```

> S10-060 已实现动态 DAG：add_task / remove_task / modify_task + 环检测（成环拒绝）✅。
> 结论：**任务图不是一次画完的蓝图，是带状态、可演化的运行时对象**。

**③ 节点状态机（任务图 = 结构 + 状态快照）**

```
pending → ready → running → success
                   ↘ failed → retrying → ready
                              ↘ skipped（降级/跳过）
阻塞: 依赖未就绪（控制边未满足）
```

> 代码现状：§3.5 SubTask.status + `execution_state.json`（tasks/status/error/依赖）✅ 已实现。

**④ 节点 → 资源映射（执行者维）**

```
SubTask.assigned_agent / tools / rag_required / timeout / budget
   → AgentMatcher（角色+能力+工具+预算）→ AgentEntity
```

> 每个节点独立上下文 + 独立工具集（§4.12.1/§4.12.4），映射在创建任务图时确定，失败重规划时可改派（§17.13）。

**⑤ Workflow 可嵌套（模板层也递归）**

```
Workflow 模板节点本身可以是子 Workflow：
  bug_fix_workflow
    ├─ reproduce_workflow（子模板）
    ├─ fix_task（原子）
    └─ test_workflow（子模板）
与任务树递归同构：模板层递归 + 实例层递归 = 同一套递归原语
```

**⑥ Plan 与 Workflow 的边界（翻译层 + 决策层）**

```
Workflow = 静态标准做法（模板，跨项目复用）
Task Graph = 本次实例（结构 + 状态 + 证据）
Plan = 实例化时的动态决策（LLMPlanner: FINAL / ACTION_REQUIRED）
     = Workflow 与 Task Graph 之间的"翻译层 + 决策层"（§3.8）
```

**结论（完整任务模型 = 6 层）**

```
结构层    Tree（拆解）+ DAG（依赖）
语义层    控制边（时序）+ 数据边（数据）
状态层    节点状态机（pending→...→success/failed）
资源层    节点→Agent/工具/预算 映射
演化层    静态蓝图 → 动态重规划（增删节点/边）
决策层    Plan（关键路径/卡口/资源分配）
```

10.6 是"静态结构"层的完整，加上 10.7 才是**完整任务模型**。

## 五、审计与可观测体系

### 5.1 审计架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              审计架构                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审计数据采集层                                      │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ Agent 行为采集 │  │ 工具调用采集   │  │ 用户交互采集   │                   │   │
│  │  │  (推理/决策)   │  │  (读/写/执行)  │  │  (输入/审批)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ LLM 调用采集   │  │ 成本数据采集   │  │ 系统事件采集   │                   │   │
│  │  │  (请求/响应)   │  │  (Token/费用)  │  │  (启动/停止)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审计存储层                                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    Audit Store (审计存储)                            │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │   │
│  │  │  │ 事件日志  │  │ 决策链    │  │ 成本明细  │  │ 操作轨迹  │       │   │   │
│  │  │  │ (时序)   │  │ (树结构)  │  │ (账单)   │  │ (链路)   │       │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审计查询层                                          │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 事件查询      │  │ 决策追溯      │  │ 成本分析      │                   │   │
│  │  │ (时间/类型)   │  │ (为什么这样做) │  │ (花在哪)      │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 影响分析      │  │ 合规报告      │  │ 审计导出      │                   │   │
│  │  │ (谁影响的)    │  │ (是否合规)    │  │ (JSON/CSV)    │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 审计事件完整模型

```python
# ============ 完整审计事件模型 ============

class AuditEvent:
    """单个审计事件"""
    
    # 基础信息
    id: str                              # 事件唯一 ID
    session_id: str                      # 会话 ID
    project_id: str                      # 项目 ID
    task_id: str                         # 任务 ID
    subtask_id: str | None               # 子任务 ID
    
    # 时间
    timestamp: datetime                  # 事件时间
    duration_ms: int | None              # 执行耗时 (毫秒)
    
    # 事件类型
    event_type: str                      # 见下方枚举
    
    # 事件源
    source_type: str                     # agent | user | system | tool
    source_id: str                       # agent_name | user_id | tool_name
    
    # 事件内容
    action: str                          # 具体操作
    input: Dict | str | None             # 输入参数
    output: Dict | str | None            # 输出结果
    error: str | None                    # 错误信息 (如果有)
    
    # 决策信息
    reasoning: str | None                # 为什么这样做
    alternatives: List[str] | None       # 考虑过的其他方案
    confidence: float | None             # 执行前置信度
    
    # 成本信息
    cost: AuditCost | None               # 成本明细
    
    # 审批信息
    approval: AuditApproval | None       # 审批记录
    
    # 关联信息
    correlation_id: str | None           # 关联的事件 ID
    parent_id: str | None                # 父事件 ID
    
    # 元数据
    metadata: Dict[str, Any] | None


class AuditCost:
    """审计成本明细"""
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    cost_usd: float
    currency: str = "USD"


class AuditApproval:
    """审批记录"""
    requested_at: datetime
    responded_at: datetime | None
    status: str                          # pending | approved | rejected | timeout
    approved_by: str | None              # user_id
    note: str | None


# ============ 事件类型枚举 ============

class AuditEventType:
    """审计事件类型"""
    
    # Agent 生命周期
    AGENT_CREATED = "agent.created"
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_RETRY = "agent.retry"
    
    # Agent 推理
    AGENT_THINK = "agent.think"          # 思考步骤
    AGENT_DECIDE = "agent.decide"        # 决策步骤
    AGENT_ACT = "agent.act"              # 行动步骤
    AGENT_OBSERVE = "agent.observe"      # 观察步骤
    AGENT_REFLECT = "agent.reflect"      # 反思步骤
    
    # 工具调用
    TOOL_CALL = "tool.call"
    TOOL_SUCCESS = "tool.success"
    TOOL_FAILURE = "tool.failure"
    
    # LLM 调用
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"
    
    # 用户交互
    USER_INPUT = "user.input"
    USER_APPROVAL = "user.approval"
    USER_REJECTION = "user.rejection"
    
    # 任务
    TASK_START = "task.start"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETE = "task.complete"
    TASK_FAIL = "task.fail"
    TASK_BLOCK = "task.block"
    TASK_UNBLOCK = "task.unblock"
    
    # 系统
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
```

### 5.3 可观测性设计

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              可观测性设计                                          │
│                                                                                     │
│  三个支柱:                                                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 支柱1: 日志 (Logs)                                                          │   │
│  │                                                                             │   │
│  │  结构化日志格式:                                                             │   │
│  │  {                                                                          │   │
│  │    "level": "INFO",                                                         │   │
│  │    "timestamp": "2026-08-21T10:00:00Z",                                    │   │
│  │    "logger": "agent.executor",                                              │   │
│  │    "message": "Executing tool read_file",                                  │   │
│  │    "task_id": "T2",                                                         │   │
│  │    "tool": "read_file",                                                     │   │
│  │    "path": "src/main.py"                                                    │   │
│  │  }                                                                          │   │
│  │                                                                             │   │
│  │  日志级别: DEBUG < INFO < WARNING < ERROR < CRITICAL                       │   │
│  │                                                                             │   │
│  │  日志输出: 文件 + 控制台 (可选远程)                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 支柱2: 指标 (Metrics)                                                        │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐    │   │
│  │  │ 指标类型        │ 示例                                               │    │   │
│  │  ├─────────────────────────────────────────────────────────────────────┤    │   │
│  │  │ Counter (计数)   │ 任务总数、工具调用次数、LLM调用次数              │    │   │
│  │  │ Gauge (当前值)   │ 当前运行任务数、当前成本、队列长度               │    │   │
│  │  │ Histogram (分布) │ 任务执行时长、LLM响应时长、工具调用时长          │    │   │
│  │  │ Summary (汇总)   │ 成功率、平均成本、Token分布                      │    │   │
│  │  └─────────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 支柱3: 追踪 (Traces)                                                        │   │
│  │                                                                             │   │
│  │  分布式追踪:                                                                 │   │
│  │                                                                             │   │
│  │  Trace: session_abc123                                                      │   │
│  │   ├── Span: orchestrator.run                                                │   │
│  │   │    ├── Span: planner.plan                                               │   │
│  │   │    └── Span: scheduler.schedule                                         │   │
│  │   │         ├── Span: executor.execute (T1)                                 │   │
│  │   │         │    ├── Span: agent.think                                     │   │
│  │   │         │    ├── Span: agent.act (read_file)                           │   │
│  │   │         │    └── Span: agent.observe                                   │   │
│  │   │         ├── Span: executor.execute (T2)                                 │   │
│  │   │         │    └── ...                                                   │   │
│  │   │         └── Span: governor.audit                                        │   │
│  │   └── Span: learner.learn                                                   │   │
│  │                                                                             │   │
│  │  每个 Span 包含: 名称、开始/结束时间、标签、日志、父子关系                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.4 用户可查看的审计视图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          用户审计视图                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 视图1: 时间线视图                                                           │   │
│  │                                                                             │   │
│  │  10:00:00  [系统] 任务开始: 修复登录接口 Bug                                 │   │
│  │  10:00:05  [Planner] 拆解完成: 6 个子任务                                   │   │
│  │  10:00:10  [Executor] 执行 T1: 读取日志文件                                 │   │
│  │  10:00:12  [Executor] T1 完成, 读取 234 行日志                              │   │
│  │  10:00:15  [Executor] 执行 T2: 分析错误模式                                 │   │
│  │  10:00:20  [Executor] T2 完成, 定位到 NullPointerException                  │   │
│  │  10:00:25  [Debugger] 执行 T3: 根因分析                                    │   │
│  │  10:00:40  [Debugger] T3 完成, 根因: UserService 未初始化                   │   │
│  │  10:00:45  [Governor] 请求审批: 修改 UserService.java                       │   │
│  │  10:01:00  [用户] 审批通过                                                  │   │
│  │  10:01:05  [Executor] 执行 T4: 修复代码                                     │   │
│  │  10:01:20  [Executor] T4 完成, 修改 1 个文件                                │   │
│  │  10:01:25  [Reviewer] 执行 T5: 审查修复                                     │   │
│  │  10:01:30  [Reviewer] T5 完成, 评分 85/100, 通过                           │   │
│  │  10:01:35  [Executor] 执行 T6: 运行测试                                     │   │
│  │  10:01:40  [Executor] T6 完成, 测试通过                                     │   │
│  │  10:01:45  [系统] 任务完成!                                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 视图2: 决策树视图                                                           │   │
│  │                                                                             │   │
│  │  目标: 修复登录接口 Bug                                                      │   │
│  │  ├── 决策1: 采用什么诊断策略?                                               │   │
│  │  │   ├── 选项A: 先看日志 (选择) → 定位到 NullPointerException              │   │
│  │  │   ├── 选项B: 先复现问题 → 未选择                                        │   │
│  │  │   └── 选项C: 直接看代码 → 未选择                                        │   │
│  │  ├── 决策2: 如何修复?                                                       │   │
│  │  │   ├── 选项A: 增加空值检查 (选择) → 修改 UserService.java                │   │
│  │  │   └── 选项B: 重构初始化逻辑 → 未选择 (风险更高)                         │   │
│  │  └── 决策3: 如何验证?                                                       │   │
│  │      ├── 选项A: 运行单元测试 (选择) → 通过                                 │   │
│  │      └── 选项B: 手动测试 → 未选择                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 视图3: 成本明细视图                                                         │   │
│  │                                                                             │   │
│  │  ┌────────────┬──────────────┬──────────────┬──────────────┬───────────┐  │   │
│  │  │ 任务       │  LLM调用次数  │  Token总数   │  费用(USD)   │  占比     │  │   │
│  │  ├────────────┼──────────────┼──────────────┼──────────────┼───────────┤  │   │
│  │  │ T1: 读取日志│ 1            │ 1,234        │ 0.002        │  5%       │  │   │
│  │  │ T2: 分析   │ 2            │ 4,567        │ 0.008        │  20%      │  │   │
│  │  │ T3: 根因   │ 3            │ 8,901        │ 0.015        │  38%      │  │   │
│  │  │ T4: 修复   │ 2            │ 3,456        │ 0.006        │  15%      │  │   │
│  │  │ T5: 审查   │ 2            │ 4,234        │ 0.007        │  18%      │  │   │
│  │  │ T6: 验证   │ 1            │ 1,234        │ 0.002        │  5%       │  │   │
│  │  ├────────────┼──────────────┼──────────────┼──────────────┼───────────┤  │   │
│  │  │ 总计       │ 11           │ 23,626       │ 0.040        │  100%     │  │   │
│  │  └────────────┴──────────────┴──────────────┴──────────────┴───────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 5.5 审计与可观测实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 审计事件 | `audit/audit_event.py`：33+ 事件类型 + 血缘字段（artifact_reference/parent_event_id）+ hash 链防篡改 | ✅ |
| 事件发射 | `audit/audit_emitter.py`：`emit()` 失败安全（审计故障不中断业务） | ✅ |
| 执行时间线 | `session/observability.py`：`execution_timeline`（时间/角色/模型/token/cost） | ✅ |
| 项目状态 | `project_status`（阶段/任务/失败原因/证据） | ✅ |
| 证据包 | `session/evidence.py`：EvidenceBundle + `EVIDENCE_BUNDLE_CREATED` | ✅ |
| CLI 视图 | `factory exec history / project status / evidence show` | ✅ |
| 实时监控/告警 | 设计（无实时指标流） | 📐 |
| 用户审计控制台（Web） | 设计（Web 入口 M7） | 📐 |

**完成度**：审计链 + 可观测 + 证据包已实现（✅）；缺实时监控告警与 Web 控制台（📐）。

### 5.6 可追溯与回放（证据链的最后一环）

> 2026-08-22 补充: 可追溯已实现；回放分三档，补齐"执行重放 + 快照回滚"后，企业才能"看完证据 → 重演一遍 → 敢签字"。

#### 5.6.1 可追溯（已实现 ✅）

```
最终结果 ← 执行记录(request/result/patch 按 id 可查)
        ← 审计链(audit_id/trace_id/correlation_id/parent_event_id + hash 防篡改)
        ← 证据包(diff+test+决策+变更文件)
        ← 决策链(S10-069)
```

- 从"一个交付结果"可一路回溯：**谁(agent) · 何时 · 做了什么 · 为什么(决策链) · 成本 · 依赖哪个产物(artifact_reference)**

#### 5.6.2 回放三档（⚠️ 现状 1.5/3）

| 档 | 能力 | 现状 |
|---|---|---|
| L1 时间线视图 | 按序重建事件（`execution_timeline` / `factory exec history`） | ✅ 已实现 |
| L2 续跑 | 从失败/中断处恢复（`resume/needs_resume`） | ✅ 已实现 |
| L3 **执行重放** | 同输入重跑 → 复现 / 与上次对比（dry-run 或重执行） | 📐 未实现 |
| L4 **快照/回滚** | 项目级 git 快照 → 回到某历史状态 | 📐 未实现（S10-085 规划） |

#### 5.6.3 重放引擎设计（补齐 L3/L4）

```
执行记录（输入/决策/patch/结果/usage，已存储）
  → 重放请求 replay-<exec_id>：dry-run（逐事件重建展示）或 re-exec（同输入重跑）
  → 对比报告：两次执行的 patch diff / 测试结果 / 成本 / 决策差异
  → 快照：每执行节点 git 快照（项目级，S10-085）
  → 回滚：approval 后置可逆（快照恢复 + 审计 ROLLBACK 事件）
```

| 项 | 状态 |
|---|---|
| 执行记录（重放的原料） | ✅ 已有（request/result/patch/usage） |
| 重放引擎（dry-run / re-exec / 对比） | 📐 建议并入 S10-085 或 M4 |
| 项目快照/回滚 | 📐 S10-085 |

#### 5.6.4 为什么必须补齐

- **治理闭环**：审批"看过证据"还不够——企业要求"重演一遍确认"（尤其合规/金融）
- **事故复盘**：出问题时能回放当时步骤，定位根因（对接 §17 自我修复/§20 安全事件响应）
- **信任差异化**："可追溯 + 可重放 + 可回滚"是"企业敢让 AI 进生产"的完整三件套（§9.3 治理平台卖点）

### 5.7 可视化体系（完整设计）★

> 2026-08-22 补充并深化: 可视化不是"几个图表"，而是**从数据到决策的完整呈现体系**——
> 架构分层 / 图表映射 / 交互 / 多端 / 性能 / 权限 / 告警 / 视图规格 / 设计系统。

#### 5.7.1 可视化架构（四层）

```
数据层: 统一契约数据（observability / audit / evidence / agents / budget / execution_state）
  → 聚合层: 时序聚合 · 分组 · 降采样 · 指标计算（成功率/成本/延迟）
  → 视图层: 图表组件库 · 布局 · 主题（状态色与文档一致）
  → 交互层: 下钻 · 筛选 · 搜索 · 实时流 · 导出 · 对比
```

#### 5.7.2 数据 → 可视化形态映射

| 数据 | 形态 | 图表类型 |
|---|---|---|
| 执行时间线 | 事件流 | 时间线 / 甘特图 |
| 任务 DAG | 依赖关系 | 有向图（dagre 分层） |
| 关键路径 | 时序依赖 | 甘特图 + 关键路径红色高亮 |
| Agent 画像 | 多维能力 | 雷达图 / 条形图 |
| 成本 | 时序 | 折线 / 面积图 + 预算水位线 |
| 血缘 | 关系 | 桑基图 / 力导向图 |
| 成功率/失败率 | 趋势 | 折线 + 置信区间 / 堆叠柱 |
| 团队负载 | 分布 | 热力图 / 堆叠条形 |
| 审批队列 | 状态 | 看板列 / 漏斗 |
| 消息渠道（M5） | 分布 | 渠道漏斗 / 时段热力 |

#### 5.7.3 交互能力

```
下钻: 点击事件/任务 → 详情面板（证据/决策/日志）
筛选: 时间 · 项目 · Agent · 状态 · 风险等级
搜索: 全局（任务/事件/证据/审计）
实时流: SSE/WebSocket 增量更新（执行中进度）
导出: PNG / CSV / PDF 报告
对比: 两次执行 diff 可视化（§5.6 重放 L3）
```

#### 5.7.4 多端适配

| 端 | 形态 | 状态 |
|---|---|---|
| CLI 文本 | 表格/树/摘要 | ✅ 已实现 |
| Web 仪表盘 | 响应式（宽屏多列/窄屏堆叠） | 📐 M5 |
| 大屏（运营中心） | 概览 + 告警 | 📐 M5+ |
| IDE 内联 | 代码旁上下文 | 📐 M7 |
| 移动 | 只读摘要 | 📐 M7+ |

#### 5.7.5 性能设计

```
增量渲染: 只更新变化部分（不整页重绘）
虚拟滚动: 大列表（执行记录/审计 万级）
聚合降采样: 原始事件 → 分钟/小时桶（时间线缩放）
懒加载: 按需查询（下钻才取详情）
查询缓存: 热点视图结果缓存 + 失效策略
```

#### 5.7.6 权限与安全

- 视图按角色（§6.3 RBAC 落地后）：Auditor 才能看审计/血缘；Viewer 只读
- 数据脱敏：原始 LLM 日志/敏感字段在可视化层脱敏（§18 数据主权）
- **可视化操作本身可审计**：谁、何时、看了什么视图（console.viewed 事件已支持）

#### 5.7.7 告警联动

```
监控指标 → 阈值 → 告警 → 可视化高亮（红/黄）→ 消息渠道推送（§9.5）
  → 点击告警 → 下钻到相关证据/审计链（对接 §20 事件响应）
```

#### 5.7.8 视图详细规格（核心 4 视图示例；其余同构）

**V1 项目看板**
```
用途: 项目级健康总览（哪些有 PRD/管线/证据/状态）
图表: 表格 + 状态徽章（✅/🚧/📐）+ 文档完成度进度条
字段: id/名称/PRD/管线资产/工程计划/状态/最近执行
交互: 点击 → 项目详情（时间线/证据/审批）
数据源: §1.4 状态 + observability.project_status；刷新: 手动 + 事件触发
```

**V2 执行时间线**
```
用途: 一次执行全链路回放（§5.6 L1）
图表: 甘特图/事件流（谁/何时/工具/模型/成本），失败节点红色
交互: 缩放（秒→分钟桶）· 点击 → 证据/决策 · 过滤（Agent/结果）
数据源: execution_timeline；刷新: 实时流（执行中）
```

**V3 任务 DAG + 关键路径**
```
用途: 拆解结构 + 调度状态（§3.9）
图表: 有向图（dagre 分层），关键路径红色，并行分支分色，完成/失败/运行中状态
交互: 点击任务 → Plan/验收/Agent；拖动视角；导出图
数据源: execution_state + §3.9 调度器；刷新: 事件触发
```

**V4 Agent 团队视图**
```
用途: "造专家"的团队概览（§4.8/§4.9）
图表: 角色卡片 + 雷达图（成功率/质量/成本/速度）+ 负载热力
交互: 点击 Agent → 画像详情/分配历史；筛选行业/角色
数据源: agents + AgentMetrics/Profile；刷新: 任务完成触发
```

（V5 证据查看器 / V6 审批中心 / V7 审计探索器 / V8 成本面板 / V9 监控告警 —— 同构设计，数据源 §5.7.2）

#### 5.7.9 设计系统

- 统一 UI token（颜色/字体/间距/圆角）复用既有前端 design/ 体系
- **状态色与文档一致**：✅ 绿 / 🚧 黄 / 📐 灰；风险色：low 绿 / medium 黄 / high 红（与 §6 分级同语义）
- 图表库选型：轻量、可树摇（减少 bundle）——M5 落地时定

#### 5.7.10 落地路线

```
CLI 文本视图 ✅（已实现）
  → Web 仪表盘（V1-V9，M5 随 Web 入口打通）
  → 实时监控/大屏/告警联动（M5+）
  → IDE 内联/移动（M7+）
```
### 5.8 监控系统设计（平台自身的健康与性能）★

> 2026-08-22 补充: 监控此前仅零散提及（§5.5 一句、§5.7.7 告警联动、§17 自我监控）——
> 补**完整监控设计**：监控什么 / 指标 / 采集 / 存储 / 告警 / 自监控 / 联动。

#### 5.8.1 监控对象与维度（6 类）

| 对象 | 监控内容 | 指标示例 |
|---|---|---|
| 系统健康 | 服务/进程/端口/磁盘 | 后端 8011 · 前端 5180 · 内存/磁盘水位 |
| **LLM** | provider 可用性/延迟/失败/成本 | 调用延迟 · 错误率 · token/成本 |
| 执行 | 任务成功率/耗时/失败 | 成功/失败 · 平均时长 · 重规划率 |
| Agent | 画像/负载/分配 | 负载 · 成功率趋势 · 排队 |
| 数据 | 存储增长/同步滞后 | 事实源/投影体积 · 同步延迟（§8.5.8） |
| 业务 | 交付产出/审批时效 | 清道夫修复数 · 审批响应时长 |

#### 5.8.2 指标体系（RED / USE + 业务）

```
RED（请求视角）: Rate(吞吐) · Errors(错误率) · Duration(延迟)
USE（资源视角）: Utilization(利用率) · Saturation(饱和) · Errors(错误)
业务指标: 任务成功率 · 每任务成本 · 审批时效 · 修复产出
```

#### 5.8.3 采集机制（事件驱动 + 周期探针 + 日志）

```
事件驱动: 复用 audit/exec 事件（执行完成/失败/审批/资产）→ 已是事实源 ✅
周期探针: 心跳/健康检查（服务/LLM/数据同步）——📐
日志: 结构化日志（模块/级别/时间）——📐
```

#### 5.8.4 指标存储（对接 §8.5.9 数据分级）

- 指标存**聚合摘要**（按分钟/小时桶），不存原始流（§8.5.9：监控=聚合同步）
- 原始事件留事实源（可重放 §5.6）；指标库可重建
- 时序存储：M5 落地（轻量时序库或 DB 聚合表）

#### 5.8.5 告警规则与分级

```
规则: 阈值（延迟>X/错误率>Y）· 趋势（连续 N 次失败）· 多条件组合
分级: info(提示) / warn(警告) / critical(阻断, 触发 §20 事件响应)
通道: CLI（当前）→ 消息渠道（§9.5 P0 后）→ Web 告警中心（M5）
抑制/去重: 同源告警聚合，避免风暴
```

#### 5.8.6 自监控（§17 自我监控落地）

- AI Factory **监控自己的运行**：LLM/执行/成本/数据同步 全部纳入 5.8.1
- 监控数据本身进事实源（可审计）→ 告警决策可回放（§5.6）
- 对接自我修复（§17）：critical 告警 → 自动修复/人工介入

#### 5.8.7 联动（监控不是孤岛）

```
监控指标 → 告警 → 可视化高亮（§5.7 V9）→ 消息推送（§9.5）
       → 事件响应（§20）→ 自我修复（§17）→ 证据+审计（闭环）
```

#### 5.8.8 实现状态与落地

| 项 | 状态 |
|---|---|
| 事件采集（执行/审计/资产） | ✅ 已实现（事实源） |
| 健康检查/心跳探针 | 🚧 部分（doctor/status） |
| 实时指标 + 时序存储 + 告警规则 | 📐 M5 |
| 告警通道（消息渠道） | 📐 M5（§9.5 落地后） |
| 自监控闭环（critical→修复） | 📐 M5+ |

#### 5.8.9 具体指标清单（指标ID / 定义 / 来源 / 默认阈值 / 采集）★

| 指标ID | 名称 | 定义 | 来源 | 默认阈值 | 采集 |
|---|---|---|---|---|---|
| `llm.latency_p95` | LLM p95 延迟 | 5 分钟窗口内调用延迟 p95 | provider 调用记录 | warn >30s / critical >60s | 每次调用 |
| `llm.error_rate` | LLM 错误率 | 5 分钟窗口失败/总数 | provider 调用记录 | warn >5% / critical >20% | 5 分钟 |
| `llm.cost_per_task` | 每任务成本 | usage 聚合（token×单价） | budget + usage | 超预算 → block（§6.2） | 每次 |
| `exec.success_rate` | 任务成功率 | 滑动窗口 100 任务 | execution_records | warn <80% / critical <50% | 每次 |
| `exec.duration_p95` | 任务 p95 耗时 | 滑动窗口 100 任务 | execution_records | warn >10min / critical >30min | 每次 |
| `exec.replan_rate` | 重规划率 | replan 次数/任务数 | replanning_decisions | warn >30% | 每次 |
| `exec.retry_rate` | 重试率 | 重试/任务数 | execution_state | warn >40% | 每次 |
| `agent.load` | Agent 负载 | 排队任务数 | agents 队列 | warn >3 / critical >10 | 30s 探针 |
| `agent.success_rate` | Agent 成功率 | 画像滑动窗口 | AgentMetrics | warn <70% | 每次 |
| `data.sync_lag` | 投影同步滞后 | 事实源→投影事件时间差 | §8.5.8 同步器 | warn >60s / critical >10min | 60s 探针 |
| `storage.growth` | 存储增速 | 日增体积 | 文件系统 | warn 超配额 70% | 1h 探针 |
| `system.health` | 服务健康 | 端口/进程可达 | 心跳 | 失败 → critical | 30s 探针 |

#### 5.8.10 具体告警规则（条件 / 级别 / 动作）★

| 规则 | 条件 | 级别 | 动作 |
|---|---|---|---|
| llm.unavailable | 连续 3 次调用失败 | critical | 切备用 provider（§T5）+ 告警 |
| llm.slow | p95 >30s 连续 5 个窗口 | warn | 告警 + 降级提示（§2 熔断） |
| exec.fail_burst | 连续 5 任务失败 | critical | 停止队列 + 告警 + 事件响应（§20） |
| cost.over_budget | 预算消耗 ≥100% | critical | block 全部 action（§6.2）+ 告警 |
| sync.stale | 同步滞后 >60s | warn | 告警 + 触发投影重放（§8.5.8） |
| agent.starved | 某 Agent 负载 >10 持续 5 窗口 | warn | 告警 + 建议扩容/改分配（§4.8） |
| storage.quota | 磁盘使用 >70% | warn | 告警 + 建议归档/清理（§8.5.9） |

**告警去重/抑制**：同源同级别 10 分钟内只发一次；critical 不抑制。

#### 5.8.11 探针与健康检查

| 探针 | 目标 | 频率 | 超时 |
|---|---|---|---|
| health | `GET /health`（后端 8011 / 前端 5180） | 30s | 5s |
| llm | provider ping（最小请求） | 60s | 10s |
| sync | 投影滞后查询（§8.5.8） | 60s | 5s |
| storage | 数据目录体积/配额 | 1h | 5s |

#### 5.8.12 时序存储 Schema（M5 落地）

```
metrics/{day}/{metric_id}.jsonl  （或 DB 时序表）
每行: {metric_id, ts, value, labels{project_id, agent_id, provider_id}, source, version}
聚合: 分钟桶 + 小时桶（§8.5.9 分级：只存聚合，原始留事实源）
保留: 聚合 90 天；原始事实源永久（§8.5.8）
```

#### 5.8.13 监控 API 与 CLI

```
CLI:
  factory monitor status          — 当前健康（服务/LLM/同步）
  factory monitor alerts          — 活跃告警列表
  factory monitor metrics <id>    — 单指标时序（如 llm.latency_p95）
API:
  GET /api/v1/monitor/health
  GET /api/v1/monitor/metrics?ids=...&from=&to=
  GET /api/v1/monitor/alerts?level=critical
```

### 5.9 监控 vs 审计：边界与审计报告 ★

> 2026-08-22 补充（用户提问）: 监控与审计常被混淆——本节明确边界、系统体现、以及**审计报告**的设计。

#### 5.9.1 本质区别（一句话各表）

| 维度 | 监控 Monitoring | 审计 Audit |
|---|---|---|
| 回答 | "现在系统还好吗？（健康/性能/成本）" | "发生过什么？谁干的？为什么？可证明吗？" |
| 时间视角 | 现在→未来（运维，前瞻） | 过去（取证，回看） |
| 数据 | 指标 metrics（聚合摘要，可重建） | 事件 events（血缘链，**不可变**） |
| 消费者 | 运维/系统自身（告警→修复） | 人类/合规/信任（审核→签字） |
| 保留 | 聚合 90 天（§5.8.12） | **永久**（事实源，hash 防篡改，§5.1） |
| 变更响应 | 触发自我修复（§17） | 触发追溯/重放（§5.6） |

#### 5.9.2 系统如何体现（各自独立）

```
监控（§5.8）: metrics 时序 · 探针 · 告警规则 · factory monitor · V9 监控视图
审计（§5.1-5.6）: audit_event 链(hash+血缘) · evidence 证据包 · 审计探索器 ·
              决策链 · 审计报告（本节）
联动: 监控异常 → correlation_id 关联审计链 → 审计报告作证据（§20 事件响应）
```

**分离原则（关键）**：监控数据可丢可重建（投影）；审计数据不可变永久（事实源）——即 §8.5.8 分层。

#### 5.9.3 审计报告（Audit Report）设计 ★

**用途**：把审计链/证据/审批/决策**汇集成人类可读、可签字**的报告——给 CTO/合规审、事故复盘、监管。

**报告内容**

| 章节 | 内容 | 数据源 |
|---|---|---|
| 概览 | 时间范围 · 事件数 · 项目数 · 结论摘要 | audit 统计 |
| 事件时间线 | 关键事件流（谁/何时/做了什么） | audit_event + 血缘 |
| 决策链 | 关键决策 + 理由 + 证据引用 | 决策链 + evidence |
| 证据包索引 | 本次范围所有证据包（diff/测试/审批） | evidence.py |
| 审批记录 | 审批请求/决策/审批人/理由 | approval/review_gate |
| 风险事件 | 高风险动作/失败/告警关联 | audit + monitor 关联 |
| 合规对照 | 对照检查项（数据主权/权限/审计） | §18/§20 |

**形态与生成**

```
CLI:  factory audit report --from <date> --to <date> [--project X] [--json|--md|--pdf]
API:  GET /api/v1/audit/report?from=&to=
定时: 周报/月报（自动生成，推送到消息渠道 §9.5）
按需: 审批后 / 事故后 / 监管要求
```

**审计报告纪律**

- 报告**只汇总事实源**（不可变），不引入监控聚合（避免"报告了可能被改的数据"）
- 报告本身可审计：谁生成了报告、何时（audit 事件）
- 报告可作为证据包的一种（`art-` 资产，血缘链引用）

#### 5.9.4 实现状态

| 项 | 状态 |
|---|---|
| 审计链/证据/决策链（报告的数据） | ✅ 已实现 |
| `factory audit report` + 报告生成器 | 📐 M5 |
| 定时周报/月报 + 消息推送 | 📐 M5（§9.5 落地后） |

### 5.10 递归进度管理体系（每层节点都有进度 / 视图 / 控制 / 调整）★

> 2026-08-24 补充（Founder 关键判断）: 项目有进度、子任务有进度、子子任务有进度、
> 子子子任务也有进度——**但凡是单一节点，都有进度**。进度不是"顶层聚合一次"，
> 而是**递归存在于每个节点**（对齐 §4.12.9 全层级 loop：每层都是 Autonomous Node）。

#### 5.10.1 核心原则：每节点都是完整进度单元

```
项目 Node（进度 = 子任务聚合）
 └─ 子任务 Node（进度 = 子子任务聚合）
     └─ 子子任务 Node（进度 = 子子子任务聚合）
         └─ 原子 Node（进度 = 自身执行状态）
每一层: 进度状态 + 进度数据 + 视图 + 控制 + 调整（完整闭环，缺一不可）
```

**与"每节点自治"同构**（§4.12.9）: 节点自治解决"能不能做"；递归进度解决
"做到哪了 / 谁在干 / 下一步谁"——两者都是递归的、每层完整的。

#### 5.10.2 每节点进度模型（5 要素）

| 要素 | 原子节点 | 组合节点（聚合） |
|---|---|---|
| **进度状态** | pending / ready / running / success / failed / blocked | 子节点状态聚合（有 running → running；全 success → success；有 failed → failed/partial） |
| **进度百分比** | 自身 0 / 100（运行中按阶段估算） | Σ(子节点进度 × 权重) / Σ权重（权重 = est_minutes 或价值 P0/P1） |
| **剩余时间** | 自身 est_minutes − 已耗 | 剩余子树关键路径（§3.9.1，复用 critical_path） |
| **视图** | 单节点详情（证据/日志/耗时） | 树/全景 + 下钻到任意层 |
| **控制** | pause / resume / cancel / retry | 递归控制（暂停父 = 暂停整棵子树，§5.10.5） |

#### 5.10.3 进度数据来源与落盘（事实源 + 投影）

- **事实源（唯一）**: 原子节点状态机 `execution_state`（pending→ready→running→success/failed）——只有原子任务真正执行，状态是事实
- **组合节点进度 = 运行时聚合（投影）**: 不重复落盘，避免"多份进度数据不一致"（§8.5.8 事实源 + 投影原则）
- 落盘: `execution_state.json`（原子，事实）+ 聚合视图（可缓存投影，标记 `computed_at`）
- 进度查询 = 读事实源 → 按树结构聚合 → 返回视图（不依赖额外状态文件）

#### 5.10.4 递归视图（3 层，§5.7 可视化体系承载）

| 视图 | 内容 | 载体 |
|---|---|---|
| **全景视图** | 整棵任务树进度（每层聚合）+ 关键路径红色高亮 + 谁在干/下一步 | 树形进度图 / 甘特图（§5.7.2） |
| **节点视图** | 单节点进度详情（状态/百分比/剩余/子节点/控制按钮） | 下钻面板 |
| **原子视图** | 单任务执行细节（证据/日志/耗时/成本/重试） | 任务详情（§5.4 审计视图） |

交互（§5.7.3）: 下钻任意层 · 筛选（按状态/Agent/风险）· 实时流（执行中进度）· 导出。

#### 5.10.5 递归控制（每节点可控）

```
原子级:   pause（暂停当前） / resume / cancel（终止+留证据） / retry（重试失败）
组合级:   递归语义 —— 暂停父 = 暂停整棵子树（保存现场，含各子节点状态）
         resume 父 = 恢复整棵子树（从暂停/失败点续跑）
         cancel 父 = 终止子树全部节点 + 保留证据包（§5.6 可回放）
```

- 恢复机制: 断点续跑（resume 从失败/暂停点继续，复用 orchestrator.resume）
- 控制动作全部落审计事件（`TASK_PAUSED / TASK_RESUMED / TASK_CANCELLED` 扩展）

#### 5.10.6 递归调整（流程修改）

| 层级 | 调整能力 | 机制 |
|---|---|---|
| 原子级 | 改任务（描述/agent/文件/验证命令/估时） | 节点修改 → 影响分析 → 重排 |
| 组合级 | 增删子节点 / 改依赖边 / 重排子树 | S10-060 动态 DAG（增删+环检测）+ ChangeControl（§10.5.1 变更回流, M3-6） |
| 跨层 | 上移/下移任务（变更粒度） | 重新拆解（M3a DecomposeEngine 重跑子树） |

**调整影响传播**: 父节点进度重算 → 下游依赖重算 → 关键路径重算（M3b）→
调度重排（M3c）→ 全部落审计（谁改的/改了什么/何时）。

#### 5.10.7 与现有实现映射

| 项 | 状态 |
|---|---|
| 原子节点状态机（事实源） | ✅ 已实现（execution_state） |
| 团队级进度统计 | ✅ 已实现（team_state.progress: total/completed/running/percent） |
| 关键路径 / 总工期（剩余时间基础） | ✅ 已实现（critical_path.estimated_duration, M3b） |
| 调度轮次（下一步基础） | ✅ 已实现（scheduler.schedule_rounds, M3c） |
| 动态 DAG 调整（组合级增删/环检测） | ✅ 已实现（S10-060） |
| **组合节点进度聚合**（每层百分比/剩余） | 📐 本设计（聚合器, 小切片可做） |
| **递归视图**（全景/节点/原子） | 📐 §5.7 可视化 + 本设计（M5 Web 承载） |
| **递归控制**（节点级 pause/resume/cancel/retry） | 🚧 团队级已有, 节点级待补 |
| **ChangeControl 变更回流**（跨层调整） | 📐 M3-6 |

**结论**: 递归进度管理的**数据地基已全部就位**（状态机/关键路径/调度轮次/动态 DAG），
缺的是**聚合器 + 视图 + 节点级控制**三个薄层——不是重设计，是把已有数据按树结构
组织成"每层可看可管可调"的完整进度单元。

### 5.11 多维度统一视图模型（同一任务 · 不同维度 · 数据统一）★

> 2026-08-24 补充（Founder 关键判断）: 同一个任务，在不同维度都应该可以查看——
> **结果不同而已**。需要**数据统一、结构完整**，将来监控大屏 / 驾驶舱直接复用。

#### 5.11.1 核心原则：一个事实源，N 个投影

```
同一任务（TaskEntity 唯一事实）
  ├─ 执行维度: 状态机（pending→running→success/failed）
  ├─ 进度维度: 百分比 / 剩余时间（§5.10 递归进度）
  ├─ 成本维度: 花费 / 预算水位（cost_ledger）
  ├─ 时间维度: 耗时 / 甘特 / 关键路径（§3.9）
  ├─ 依赖维度: DAG / 上下游 / 汇聚点（§3.5）
  ├─ 资源维度: Agent / 工具 / 文件
  └─ 血缘维度: 证据 / 审计链 / 决策链（§5.2）
每一维 = 同一 TaskEntity 的**投影视图**（查询时计算，不重复存储）
```

**与 §5.10 的关系**: §5.10 是**纵向递归**（每层节点都有进度）；§5.11 是**横向多维度**
（每节点有多种视角）。两者叠加 = 完整视图矩阵: **每层节点 × 每个维度** 都可查看。

#### 5.11.2 统一任务实体（TaskEntity Schema — 所有维度的单一结构）

```python
class TaskEntity:  # 唯一事实，所有维度消费同一 schema
    # 定义维
    id: str; name: str; parent: str; children: list[str]
    depth: int; type: str            # compound | atomic
    # 执行维
    status: str                      # pending/ready/running/success/failed/blocked
    # 资源维
    agent_type: str; assigned_agent: str; target_file: str
    verify_cmd: str; est_minutes: int
    # 成本维（运行时）
    actual_cost: float; budget: float
    # 时间维（运行时）
    started_at: str; completed_at: str; duration_seconds: int
    # 依赖维
    depends_on: list[str]; dependents: list[str]
    # 血缘维
    evidence_refs: list[str]; audit_events: list[str]
```

- 原子任务 = `execution_state` 事实；组合节点 = 树结构 + 子节点聚合投影
- **同一 schema 服务所有端**：CLI / Web / 大屏 / 消息渠道（§9.5）——禁止各端自造数据结构

#### 5.11.3 多维投影层（view layer — 查询时计算，不落盘）

```
API:  GET /api/v1/tasks/{id}?view=execution|progress|cost|timeline|deps|resources|lineage
      支持组合: ?view=progress+cost（大屏组合渲染）
投影 = 纯函数: TaskEntity → 视图 dict（可缓存投影，标 computed_at）
渲染 = §5.7 图表映射（甘特/树/雷达/折线/热力）
```

- 投影只读，**不写回事实源**（防"视图改了事实"）
- 新增维度 = 先扩 TaskEntity schema（§2.11 契约测试）再出投影——结构先行

#### 5.11.4 监控大屏 / 驾驶舱（消费统一数据，不新增数据源）

```
数据层:  统一 TaskEntity + 事件流（audit）+ 聚合器（dashboard collector）
聚合层:  按维度聚合（进度/成本/时间/依赖/资源/血缘）
视图层:  大屏组件 — 树形进度 · 甘特关键路径 · 成本雷达 · Agent 负载热力 · 血缘桑基
接入:    统一查询 API（view 参数化）— 大屏 = 多个投影的组合渲染
```

- **大屏 = 投影视图的组合**，不是独立数据系统
- 多端复用: 同一 TaskEntity 服务 CLI 文本 / Web 大屏 / 消息推送（§9.5）
- 已有地基: `factory-core/dashboard/` DashboardCollector（FactorySnapshot /
  TaskSnapshot / AgentSnapshot / MetricsSnapshot）✅

#### 5.11.5 数据统一铁律（防"大屏一套、CLI 一套"）

1. **事实源唯一**: execution_state（执行）/ 树（结构）/ audit（事件）/ cost_ledger（成本）
2. **投影只读计算**: 任何视图都是 TaskEntity 的投影，不写回事实源
3. **统一入口**: 任何维度视图 = TaskEntity + view 参数（禁止各端自造数据通路）
4. **结构完整**: TaskEntity schema 契约化（§2.11.4 契约测试）——新增维度先扩 schema 再出视图

#### 5.11.6 数据统一的可信机制（推敲 / 验证 / 审计 / 回溯）★

> 2026-08-24 补充（Founder 关键判断）: 数据统一不是口号——必须**经得起推敲、
> 验证、审计、回溯**。任何视图都要能回答: 这个数字从哪来？怎么验证？谁看过？
> 能回放到什么程度？

**① 推敲（可验证性）— 投影是纯函数，可随时重算对账**

```
投影 = f(TaskEntity)：同输入必同输出（确定性）
一致性校验器（Consistency Validator）:
  任何视图对照事实源重算 → diff
  ├─ 定期对账（事件后 / 定时）
  ├─ 按需（校验命令: factory validate-views）
  └─ 不一致 → 告警 + 审计事件（VIEW_INCONSISTENCY_DETECTED）+ 校验报告落盘
```

**② 验证（Verification）— 三层验证**

| 层 | 验证什么 | 机制 |
|---|---|---|
| schema 契约 | TaskEntity 结构合规（字段/类型/枚举） | §2.11.4 契约测试（新增维度先扩 schema 再出视图） |
| 投影正确性 | view=f(entity) 输出与预期一致 | 投影单元测试（每 view 一种，手算对照） |
| 数据一致性 | 投影 vs 事实源对账无 diff | Consistency Validator（重算 diff） |

**③ 审计（Audit）— 视图访问 + 数据变更双审计**

```
视图访问审计: 谁（user/agent/大屏）· 何时 · 什么 view · 什么参数
             → VIEW_ACCESSED 事件（大屏轮询也记录——知道"谁在看什么"）
数据变更审计: 事实源任何变更走审计链（§5.2 已有，hash 防篡改）
审计报告:    可含视图访问统计（§5.9.3 扩展）
```

**④ 回溯（Traceability）— 双向追溯 + 时间旅行**

```
视图 → 数据:  视图数字 → TaskEntity 字段 → 事实源行（execution_state/树/成本/事件）
数据 → 证据:  任务状态 → 审计事件链（hash 链防篡改 §5.2）→ 证据包（diff+test+决策）
时间旅行:     事件溯源重建任意时刻状态（§5.6 回放 L4）
             ——"昨天 14:00 这个任务显示什么"可回答
每视图响应带 sources: [...] 字段（数据来源引用）——推敲入口
```

**可信机制与现有实现**

| 机制 | 状态 |
|---|---|
| 审计链 hash 防篡改 + 事件溯源 | ✅ 已实现（audit_event.py sha256 链 + §5.6） |
| 契约测试（schema） | ✅ 已实现（§2.11.4, M2-6） |
| 投影纯函数（可重算） | 📐 本设计（投影层 §5.11.3 落地时天然满足） |
| Consistency Validator（对账） | 📐 本设计（小切片可做） |
| 视图访问审计（VIEW_ACCESSED） | 📐 本设计（M5 接入） |
| 视图响应 sources 字段 | 📐 本设计（schema 扩展） |

**结论**: "数据统一"的可信闭环 = **纯函数投影（可重算）→ 一致性对账（可验证）→
双审计（可审计）→ 血缘+回放（可回溯）**。每层都是薄机制，复用已有审计链 /
契约测试 / 回放（§5.2 / §5.6 / §2.11.4），不是新造体系。

#### 5.11.7 与现有实现映射

| 项 | 状态 |
|---|---|
| DashboardCollector（FactorySnapshot/TaskSnapshot/AgentSnapshot） | ✅ 已实现（factory-core/dashboard/） |
| 执行状态 / 关键路径 / 调度轮次 / 递归进度数据 | ✅ 已实现（execution_state / critical_path / scheduler / team_state） |
| **TaskEntity 统一 schema**（全维度单一结构） | 📐 本设计（对齐 §2.11 契约） |
| **多维投影 API**（view 参数化） | 📐 M5（Web/API 层打通时） |
| **大屏 / 驾驶舱组件** | 📐 §5.7 可视化 + 本设计（M5） |

**结论**: 驾驶舱不是新数据源，是**同一 TaskEntity 的多投影组合**。先把 schema 契约化，
任何端（CLI/Web/大屏/消息）都消费同一结构——正是"统一设计，零摩擦集成"（§2.9）的落地。

### 5.12 回滚体系设计（代码 / 数据 / 配置 / 知识 / 审批 / 流程）★

> 2026-08-24 补充（Founder 关键判断）: "回滚"没有专门设计——现有只有 §5.6 L4
> git 快照（M4-6）零散提及。回滚不是单点功能，是**多类型 × 多粒度 × 有审批 ×
> 可审计**的完整体系；且与递归进度（§5.10）/ 可信机制（§5.11.6）闭环衔接。

#### 5.12.1 回滚类型矩阵（回滚什么）

| 类型 | 回滚对象 | 机制 | 状态 |
|---|---|---|---|
| **代码/文件** | 源码变更（diff/patch/PR） | git 快照恢复 / revert PR | 📐 §5.6 L4（S10-085） |
| **数据** | execution_state / plan.json / schedule.json / decomposition.json | 数据快照恢复 / 事件溯源重建 | 📐 本设计 |
| **配置** | 模块配置（§2.4 独立版本） | 配置版本回滚 | 📐 §2.4（模块可独立回滚） |
| **知识/经验** | 经验库 / AgentProfile 画像 | 经验版本号回滚（§7.2 机制3） | 📐 §7.2 |
| **审批决策** | 已批准的决策 | 后置可逆（快照恢复 + ROLLBACK 事件，§5.6） | 📐 §5.6 |
| **流程/任务** | 任务树/DAG/调度状态 | 子树回滚 + 重排（§5.10.6 递归调整） | 📐 本设计 |

#### 5.12.2 回滚粒度递归（对齐 §5.10 每节点自治）

```
项目级回滚: 整个项目 → 上一可用状态（git + 数据 + 配置全量）
 └─ 子树回滚: 某功能/模块 → 子树快照（子任务及以下）
     └─ 原子级回滚: 单任务 → 该任务状态 + 文件变更
每层节点都可回滚——回滚粒度与进度粒度同构（每层都是完整单元）
```

- **原子级**: 撤销单任务的文件变更 + 状态回退（pending）
- **子树级**: 某 feature 的 db/api/frontend/test 一起回退 → 重跑
- **项目级**: 全量回到历史快照（git + execution_state + plan + 配置）

#### 5.12.3 回滚机制三选（按场景）

| 机制 | 适用 | 原理 | 成本 |
|---|---|---|---|
| **快照恢复** | 项目/子树级、确定性回退 | git 快照 + 数据快照（L4） | 高（存快照） |
| **事件溯源重放** | 精确到某时刻、审计友好 | 事件链重放到 T 时刻 = 状态重建（§5.6 回放 L3/L4） | 中（重放计算） |
| **事务补偿** | 原子级、部分完成 | 逆操作（删除已写文件/撤销审批） | 低 |

选择规则: 需要"精确回到某时刻" → 事件溯源；需要"整体退版本" → 快照；
单任务局部撤销 → 事务补偿。

#### 5.12.4 回滚安全（回滚也是高风险操作）

- **回滚 = 变更** → 走 ApprovalGate 分级审批（§6.3）：代码回滚 medium+，项目级回滚 high
- **回滚前强制快照**（当前状态先存档 → 可撤销回滚）
- 回滚边界: 只回滚**事实源**（execution_state/代码/配置），投影视图自动重算（§5.11 纯函数）
- 禁止回滚绕过审计: 回滚本身落 ROLLBACK 事件 + 变更前后对比（§5.11.6 可信机制）

#### 5.12.5 回滚后继续（回滚不是终点）

```
回滚到节点 → 用户确认 → 调整（改任务/改依赖/换方案 §5.10.6）
→ 重新拆解（M3a 重跑子树）→ 重新调度（M3c）→ 重新执行
→ 进度视图自动重算（§5.10 聚合）→ 全链路审计
```

- 回滚 + 调整 + 重跑 = 完整闭环（与 §5.10.5 控制 / §5.10.6 调整衔接）
- 每次回滚记录"原因"（谁/为何/回滚到哪）→ 决策记忆回流（M4 E5）

#### 5.12.6 跨模型任务回滚（多模型协作链上的回滚）★

> 2026-08-24 补充（Founder 追问）: 跨模型的任务回滚怎么处理？——多 LLM 协作链
> （A 产出 → B 消费 → C 再消费），回滚一个节点的产出，下游消费它的资产怎么办？

**① 核心原则：回滚对象 = 资产 / 节点（模型无关）**

```
模型是可替换执行者（AgentEntity, agt- 前缀）；回滚不绑定"哪个模型"。
回滚对象 = 该节点产出的 资产/状态/证据（PRD/架构/代码/证据包）。
跨模型链 = 资产血缘链（HandoffBus parent_artifact/parent_event_id）
         → 血缘链就是回滚的影响传播图（✅ 已实现 handoff_bus.py）
```

**② 级联回滚三策略（按风险选）**

| 策略 | 行为 | 适用 |
|---|---|---|
| **硬级联** | 回滚到根: 目标节点及所有下游资产全部回滚 | 高风险 / 审计严格 |
| **软级联** | 只回滚目标节点; 下游资产标 `stale`（失效）→ 按需重跑 | 高效，有风险 |
| **层分离** | 决策层保留（PRD/架构），只回滚实现层 | 需求不变、实现错误 |

**③ 定点移除（只干掉中间节点 4，保留 1-3 和 5）★**

> 2026-08-24 补充（Founder 追问）: 12345 回滚到 3 是 123；**只干掉 4** 有办法么？
> 有——定点移除（surgical removal）+ 依赖重接（reroute）。关键看 4→5 的边类型。

```
1→2→3→4→5，只干掉 4

第一步: 判定 4→5 的边类型（§4.12.10.7 控制边 vs 数据边）
第二步: 按类型处理

  控制边（5 只是"4 之后做"，不消费 4 的数据）
    → 移除 4 + 依赖重接 3→5 → 1→2→3→5（5 保留，无需重跑）

  数据边（5 消费 4 的产出）→ 三选一:
    a. 5 改消费 3 的输出（兼容 → reroute + 5 重跑）
    b. 5 标 stale（输入源没了，按需重跑/移除）
    c. 5 一并移除（4 的产出是 5 的必要输入）

第三步: 资产与血缘
    → 4 的产出资产归档（不删除，留证据）标记 removed/superseded
    → 血缘链更新（下游 parent_artifact 改指 3）
    → 审计: NODE_REMOVED + REROUTED + 原因（谁/为何/只删4）
```

**与级联回滚的区别**: 级联 = 撤销节点及其下游（回溯）；定点移除 = **删除节点 +
重接依赖**（手术），1-3 与 5 的原产出保留不动。二者是回滚谱系的两端，
中间还有"层分离"（§5.12.6 ②）。

**代码基础（✅ 已实现，组装即可）**:
- `dependencies.remove_task`（移除节点 + 清理引用）· `remove_dependency` ·
  `add_dependency`（重接 3→5，带环检测）· `topological_order`（重排）
- 资产版本 v+n + 血缘（handoff_bus / artifact_registry）

**定点移除的判定规则（可断言）**:
| 条件 | 动作 |
|---|---|
| 4→5 是控制边 | reroute 3→5，5 保留 |
| 4→5 是数据边且 3 输出兼容 | reroute + 5 重跑 |
| 4→5 是数据边且不兼容 | 5 标 stale |
| 5 无其他上游且 4 是唯一输入 | 5 一并移除 |

**③ 资产失效传播（软级联的核心）**

```
回滚节点 A 的产出
  → 血缘链查下游: 所有 consumed_from(A) 的资产（B/C 的产出）
  → 标记 stale + 审计事件（ASSET_STALE_MARKED）
  → 消费前校验: 任何任务消费资产前检查血缘有效性
    （上游被回滚 → 拒绝消费 + 提示重跑）——防"基于失效资产的继续执行"
```

**④ 消费前血缘校验（防脏数据下钻）**

- 每个资产消费点: 校验 parent_artifact 链上无 stale / 无回滚
- 发现失效 → 阻断 + 明确提示（哪个上游被回滚、建议重跑哪个节点）
- 校验是纯函数（§5.11 可信机制）→ 可审计、可对账

**⑤ 跨模型重跑（回滚后继续，不绑定原模型）**

- 回滚后重跑 = **新执行**，AgentMatcher 按能力表重新选模型（可换更强/换原模型）
- 模型可替换性 = "造专家的工厂，不绑专家"的落地（§1.1）
- 重跑产出 → 新资产版本（v+n, ArtifactRegistry ✅）→ 血缘链更新

**⑥ 跨模型一致性保障**

- 回滚只动事实源（execution_state / 资产），投影视图自动重算（§5.11 纯函数）
- 审计: ROLLBACK + ASSET_STALE_MARKED + 重跑事件全记录（谁 / 为何 / 回滚到哪 / 换没换模型）
- 决策记忆回流（M4 E5）: 回滚原因入库——"同类跨模型问题下次提前拦截"

**⑦ 实现映射**

| 项 | 状态 |
|---|---|
| 资产血缘链（parent_artifact / parent_event_id） | ✅ 已实现（handoff_bus.py） |
| 资产版本 v+n（ArtifactRegistry） | ✅ 已实现 |
| stale 标记 + 消费前血缘校验 | 📐 本设计（薄层，可小切片） |
| 级联回滚三策略 | 📐 本设计（接 §5.12 回滚体系） |
| 跨模型重跑（换模型） | 📐 本设计（AgentMatcher 已有基础） |

**结论**: 跨模型回滚 = **血缘链驱动的影响传播 + 三策略级联 + 消费前校验 + 模型无关重跑**。
关键洞察: 模型是可替换执行者，回滚对象是资产——不是"回滚某个模型"，而是
"撤销某个资产的产出 + 让下游失效 + 重新执行"。

#### 5.12.7 与现有实现映射

| 项 | 状态 |
|---|---|
| 沙箱应用（原仓库零影响 → 可丢弃） | ✅ 已实现（exec/sandbox.py） |
| 审计链 hash + 事件溯源（回滚的可回溯基础） | ✅ 已实现（audit_event.py + §5.6） |
| 快照/回滚（git 快照 L4） | 📐 M4-6（S10-085） |
| 数据快照/恢复（execution_state/plan） | 📐 本设计（M4 或独立切片） |
| 子树/原子级回滚 + 重排 | 📐 本设计（M3c 调度后 + M4） |
| ROLLBACK 事件 + 回滚审批 | 📐 本设计 |

**结论**: 回滚体系 = **多类型（代码/数据/配置/知识/审批/流程）× 递归粒度（原子/
子树/项目）× 三机制（快照/事件溯源/补偿）× 审批安全 × 全审计**。与 §5.10
（进度控制）、§5.11（可信机制）闭环——"可看、可控、可回滚"三件套齐了，
企业才敢让 AI 进生产（§9.3 治理平台卖点）。

### 5.13 沙箱体系设计（AI 改代码的安全执行地基）★

> 2026-08-24 补充（Founder 指出: 沙箱一直没系统设计过）: 沙箱不是可选功能，是
> **AI 执行安全的地基**——AI 改代码必须先在隔离环境证明自己，才能碰真实仓库。
> 信任 = 先隔离验证，再放行。

#### 5.13.1 沙箱的本质

```
AI 在真实仓库上直接改 = 不可信（可能改坏/泄密/删库）
AI 在沙箱内改 = 可证明（diff+test+决策 都在隔离环境产生）
放行条件: 沙箱内证据 → 审批 → patch_filter 白名单 → 才应用到真实仓库
沙箱 = "AI 先证明自己，再被信任"的机制载体
```

#### 5.13.2 沙箱层级（隔离边界逐级加强）

| 层级 | 隔离什么 | 状态 |
|---|---|---|
| **目录沙箱**（项目副本） | 文件系统（原仓库零影响） | ✅ M1（exec/sandbox.py） |
| **进程沙箱** | 进程/命令执行（沙箱内命令受限） | 🚧 部分 |
| **网络沙箱** | 网络访问（默认禁外网） | 📐 |
| **凭证沙箱** | API key/密钥不注入沙箱（用引用/env） | 🚧 |
| **容器/云端沙箱** | 完整环境隔离（多 Agent 独立沙箱） | 📐 M7 |

#### 5.13.3 沙箱生命周期（证明 → 放行）

```
创建（项目副本: 原仓库零影响）
  → 执行（AI 在沙箱内改代码 / 跑真实测试）
  → 证据（diff + test + 决策链, 沙箱内产生）
  → 审批（证据包给人看, 分级审批 §6.3）
  → 应用（patch_filter 白名单 → 真实仓库）
  → 验证（真实环境 pytest）→ 交付
失败 / 放弃 → 丢弃沙箱 = 天然回滚（原仓库零影响, §5.12）
```

#### 5.13.4 沙箱安全铁律（五条）

```
1. 默认禁外网: 沙箱内无网络 → 防数据外泄/防拉毒依赖
2. 凭证不注入: API key/密钥用引用或环境占位, 不落沙箱文件
3. 权限降级: 沙箱内最小权限（只读真实仓库, 只写沙箱副本）
4. 资源限制: 超时 / 磁盘上限 / 进程数上限（防失控）
5. 产出不可信: 沙箱内任何产出都是"候选"→ 必须审批 + patch_filter
   白名单才进真实仓库（防恶意/错误 patch）
```

#### 5.13.5 沙箱与已有机制的关系（不是孤岛）

| 机制 | 与沙箱的关系 |
|---|---|
| 证据 + 审批（M1a） | 沙箱产出证据 → 审批门 → 应用（闭环已通） |
| 回滚（§5.12） | 沙箱 = 天然回滚（丢弃即还原） |
| 可信机制（§5.11） | 沙箱内事实源 → 投影视图（沙箱状态可看可审计） |
| 变更治理门（§10.5.7.5） | 沙箱 diff = 影响面分析的第一步 |
| 定点移除（§5.12.6③） | 沙箱内撤销 = 直接丢弃重来 |

#### 5.13.6 沙箱演进路线

```
M1 目录沙箱（✅ 已实现）→ 进程/网络/凭证隔离（🚧/📐）
→ M5 自主沙箱（长任务自主完成）→ M7 云端沙箱（多 Agent 独立沙箱, 对标竞品）
```

#### 5.13.7 与现有实现映射

| 项 | 状态 |
|---|---|
| 目录沙箱（create/copy_dir/apply_patch/diff/export_patch） | ✅ 已实现（exec/sandbox.py） |
| patch_filter 白名单（交付校验） | ✅ 已实现 |
| 沙箱证据 → 审批 → 应用闭环 | ✅ M1a（证据包 + 分级审批） |
| 网络 / 进程 / 凭证隔离 | 🚧 / 📐 |
| 容器 / 云端沙箱（多 Agent 独立） | 📐 M7（对标竞品沙箱隔离） |

**结论**: 沙箱是 AI 执行安全的**地基**（先隔离验证再放行），不是可选功能。
M1 目录沙箱已实现且与证据/审批/回滚闭环；后续按 §5.13.6 演进（进程/网络/
凭证隔离 → 云端沙箱），每级都守住 §5.13.4 五条铁律。

#### 5.13.8 沙箱粒度设计（沙箱 = 执行边界，不是任务层级）★

> 2026-08-24 补充（Founder 探讨: 一个项目一个沙箱，是否每个任务/子任务都要沙箱？——
> 结论: **每层都沙箱 = 过度设计**。正确原则: 沙箱粒度 = 执行边界）。

**核心原则: 只有执行点需要沙箱**

```
项目（compound）→ 不执行，只编排 → 不需要沙箱
子任务（compound）→ 不执行，只委派 → 不需要沙箱
原子任务（atomic）→ 真正执行（改文件/跑命令）→ 才需要沙箱
```

组合节点不产生代码变更（只委派子节点），给它沙箱 = 复制了项目但没人写——纯浪费。

**沙箱粒度 = 执行模式**

| 执行模式 | 沙箱粒度 | 为什么 |
|---|---|---|
| **顺序执行**（现状） | 项目级 1 个沙箱，任务累积 diff | 任务依次做，互不干扰 |
| **并行执行**（M3c 调度后） | **原子级独立沙箱**（每轮并行任务各自沙箱） | A 改 x.py 时 B 也在改 → 防冲突污染 |
| **高风险任务** | 独立沙箱隔离验证 | 爆炸半径大的操作单独证明 |
| **组合节点** | 永不沙箱 | 不执行，无变更 |

```
项目沙箱（只读基线）
  ├─ 任务A 沙箱 → diff_A → 证据_A      （并行时各自独立）
  ├─ 任务B 沙箱 → diff_B → 证据_B
  └─ 合并全部 diff → 审批 → 应用到真实仓库
```

**何时从"项目级"升级到"原子级"**

- 触发条件: **M3c 并行调度真正执行时**（任务并行跑 → 必须原子级沙箱，否则
  同一文件并发修改互相踩）
- 顺序模式保持项目级（现状零变化）
- 高风险任务独立沙箱是例外策略（无论顺序/并行）

**防过度设计自查（每加一个沙箱层前问）**

```
1. 这个节点执行吗？（不执行 → 不要沙箱）
2. 它与其它任务并行吗？（不并行 → 共享项目沙箱）
3. 它风险高吗？（不高 → 不独立沙箱）
三问都否 → 不加沙箱层
```

**结论**: 沙箱粒度 = 执行边界（顺序=项目级 / 并行=原子级 / 高风险=独立），
不是任务层级。组合节点永不沙箱——**"每层都有沙箱"是过度设计**，正确做法是
在 M3c 并行执行落地时配套原子级沙箱。

## 六、治理与合规体系

### 6.1 治理全景

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              治理全景                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         治理维度                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  成本治理     │  │  权限治理     │  │  合规治理     │                   │   │
│  │  │  • 预算控制   │  │  • 角色权限   │  │  • 操作合规   │                   │   │
│  │  │  • 成本告警   │  │  • 操作审批   │  │  • 数据隐私   │                   │   │
│  │  │  • 成本优化   │  │  • 白名单     │  │  • 行业规范   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  质量治理     │  │  风险治理     │  │  安全治理     │                   │   │
│  │  │  • 质量标准   │  │  • 风险分级   │  │  • 安全扫描   │                   │   │
│  │  │  • 审查机制   │  │  • 熔断机制   │  │  • 敏感信息   │                   │   │
│  │  │  • 验收标准   │  │  • 降级策略   │  │  • 审计追踪   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         治理执行流程                                        │   │
│  │                                                                             │   │
│  │  操作请求                                                                   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 1: 身份验证 (Authentication)                                   │   │   │
│  │  │   用户是谁？→ 验证身份                                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 2: 权限验证 (Authorization)                                    │   │   │
│  │  │   用户是否有权执行此操作？→ 检查角色权限                             │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 3: 风险评估 (Risk Assessment)                                  │   │   │
│  │  │   此操作风险等级？→ low | medium | high | critical                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 4: 审批流程 (Approval Flow)                                    │   │   │
│  │  │   高风险操作 → 请求审批 / 低风险操作 → 自动放行                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 5: 执行与审计 (Execute & Audit)                                │   │   │
│  │  │   执行操作 + 完整记录审计                                            │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 成本治理详细设计

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              成本治理详细设计                                       │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         成本模型                                            │   │
│  │                                                                             │   │
│  │  总成本 = Σ(LLM调用成本) + Σ(工具执行成本)                                 │   │
│  │                                                                             │   │
│  │  LLM调用成本 = (Prompt Token数 × Prompt单价) +                             │   │
│  │                 (Completion Token数 × Completion单价)                       │   │
│  │                                                                             │   │
│  │  工具执行成本 = (执行时间 × 资源单价) (暂不计)                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         成本控制策略                                        │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 级别1: 告警 (Alert)                                                  │   │   │
│  │  │ 触发: 成本 > 阈值的 70%                                              │   │   │
│  │  │ 动作: 通知用户、显示当前成本                                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 级别2: 限流 (Throttle)                                              │   │   │
│  │  │ 触发: 成本 > 阈值的 90%                                              │   │   │
│  │  │ 动作: 降低并行度、使用更便宜的模型                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 级别3: 熔断 (Circuit Break)                                         │   │   │
│  │  │ 触发: 成本 > 阈值 (100%)                                             │   │   │
│  │  │ 动作: 暂停所有任务、请求用户审批后续                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         成本优化策略                                        │   │
│  │                                                                             │   │
│  │  1. 缓存: 相同查询使用缓存结果，减少重复 LLM 调用                          │   │
│  │  2. 模型选择: 简单任务用小模型，复杂任务用大模型                           │   │
│  │  3. 批量处理: 合并多个小请求为一个批处理请求                               │   │
│  │  4. 提前终止: 达到目标后立即停止，不继续生成                               │   │
│  │  5. 结果缓存: 相同/类似问题直接返回历史结果                                 │   │
│  │  6. Token 预算: 每个任务设置 Token 上限                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 6.3 权限与审批模型

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         权限与审批模型                                             │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         角色定义                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┬──────────────────────────────────────────────────────┐  │   │
│  │  │ 角色           │ 权限范围                                            │  │   │
│  │  ├───────────────┼──────────────────────────────────────────────────────┤  │   │
│  │  │ Owner         │ 全部权限: 创建/删除项目、修改治理规则、管理用户     │  │   │
│  │  │ Admin         │ 管理权限: 审批高风险操作、查看所有审计              │  │   │
│  │  │ Operator      │ 执行权限: 运行任务、查看项目审计                    │  │   │
│  │  │ Viewer        │ 只读权限: 查看进度和审计                            │  │   │
│  │  │ Auditor       │ 审计权限: 查看完整审计，无操作权限                  │  │   │
│  │  └───────────────┴──────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审批流程                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 操作类型        │ 审批要求                                          │   │   │
│  │  ├─────────────────────────────────────────────────────────────────────┤   │   │
│  │  │ read_file      │ 自动放行                                          │   │   │
│  │  │ search_code    │ 自动放行                                          │   │   │
│  │  │ write_file     │ 需要用户审批 (可配置为自动放行)                   │   │   │
│  │  │ run_command    │ 需要用户审批 (高危命令额外审批)                   │   │   │
│  │  │ delete_file    │ 需要用户审批 + 二次确认                           │   │   │
│  │  │ deploy         │ 需要用户审批 + 指定审批人                         │   │   │
│  │  │ architecture   │ 需要用户审批 (架构决策)                           │   │   │
│  │  │ cost_high      │ 自动告警 + 用户审批                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  审批方式:                                                                  │   │
│  │  1. 终端交互: CLI 提示 (y/n/edit)                                         │   │
│  │  2. 异步通知: 消息推送 + 用户回复 (未来)                                   │   │
│  │  3. 自动批准: 低风险 + 用户配置 "自动放行"                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


#### 6.3.5 审批门实现（已实现，对照代码）

| 门 | 职责 | 实现 |
|---|---|---|
| **ConfirmationGate** | 敏感 action（create_project/run_task/prepare/execute）执行前 y/N 确认 | ✅ `confirm.py` |
| **ReviewGate** | 评审请求（request/approve/reject/cancel），`risk=low/medium/high` | ✅ `review_gate.py` |
| **ApprovalGate** | patch 应用前必批；`classify_risk`（爆炸半径）→ risk_level + required_roles | ✅ `exec/approval.py`（M1a） |

#### 6.3.6 分级审批规则（已实现）

| 爆炸半径 | risk_level | required_roles | 触发 |
|---|---|---|---|
| 低（单文件常规修改） | low | developer | 自动推荐 |
| 中（跨文件/核心配置） | medium | tech_lead | 技术负责人批准 |
| 高（删除/依赖升级/基础设施） | high | tech_lead + compliance | 人工必批 |

#### 6.3.7 审批方式（部分实现）

| 方式 | 状态 |
|---|---|
| 终端交互（y/n/edit） | ✅ 已实现 |
| 消息渠道异步审批（IM 卡片） | 📐（§9.5 消息平台落地后） |
| 低风险自动放行（用户配置） | ✅ 部分（ConfirmationGate 非敏感放行） |

> 角色表（Owner/Admin/Operator/Viewer/Auditor）为 **RBAC 设计（📐 未实现）**；当前以三道门 + 统一契约（§2.10）为准。

### 6.4 治理闭环：决策记忆回流（E5，完成治理的最后一块）

> 治理不只是"卡门"，还要让治理过的决策**回流为组织记忆**，越用越准、越用越省——但仍可控。

```
审批决策 (approve/reject + 理由)
  → DECISION_LEARNED 事件（事件类型已建，未接线）
  → 组织记忆（经验库）
  → 下次同类任务决策时引用（少审 / 快审 / 更准）
  → 护栏：低样本不计权 · 学习开关 · 预算上限（C5 复用）
```

| 项 | 状态 |
|---|---|
| `DECISION_LEARNED` 事件类型 | ✅ 已建（M1a） |
| 审批决策 → 事件落库 | ✅ ReviewGate/ApprovalGate 决策可审计 |
| 决策 → 组织记忆回流接线 | 📐（M4 学习闭环一并实现） |
| 下次决策引用（少审/快审） | 📐（M4） |

### 6.5 成本治理闭环（自动执行）

```
执行 → usage 采集（token/cost）→ 聚合 → BudgetEnforcer 判定
  → ok/warn 放行 · review 评审 · block 禁止
  → 审计事件 + 告警
  → 每任务成本可查（§五 可观测）
  → 单位经济回填（§1.5.3）
```

| 环节 | 状态 |
|---|---|
| BudgetEnforcer 四级判定（ok/warn/review/block） | ✅ 已实现 |
| 按 action 计费维度（llm/execute/retry/repair/replan/new_task） | ✅ 已实现 |
| 自动告警/阻断接线（执行链上生效） | 🚧 部分（预算检查已挂，告警推送待 §9.5 消息渠道） |
| 成本聚合报表 / 单位经济回填 | 📐 |

### 6.6 治理完成度总表（可度量）

| 治理件 | 能力 | 状态 |
|---|---|---|
| **审批** | ConfirmationGate（敏感 action）· ReviewGate（评审）· ApprovalGate（patch 分级必批） | ✅ |
| **预算** | BudgetEnforcer 四级 + 分维度计费 | ✅ |
| **审计** | 33+ 事件 + 血缘（artifact_reference/parent_event）+ 决策链 | ✅ |
| **权限** | 三道门 + 统一契约；RBAC 角色表 | 🚧（RBAC 📐） |
| **合规** | 数据主权（§十八）· 认证对标（§21）· 治理拦截错误码 E402 | 🚧（认证/信创 📐） |
| **闭环** | 决策记忆回流（E5）· 成本自动告警 | 📐（M4） |

**"完成治理" = 审批 ✅ + 预算 ✅ + 审计 ✅ 已闭环；权限/合规/闭环随 M4/§9.5/§18/§21 落地。**

### 6.7 治理作为独立产品（AI 治理平台）的边界

- **治理平台管"所有 AI"**，不只是 AI Factory 自身——任何组织用 Claude/Codex/自建 Agent，都能挂进来做审批/预算/审计/合规。
- **集成方式**：统一契约（§2.10）——外部 AI 通过 `/api/v1/approvals|budget|audit` + 事件回调接入，不侵入内部。
- **边界**：治理平台只做"决策与护栏"，**不执行任务**（执行权 != 审核权铁律）——这是它能独立成产品又不越权的根本。

## 七、学习与自我进化体系

### 7.1 学习架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              学习架构                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         数据采集层                                          │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 任务执行数据   │  │ 审计事件数据   │  │ 用户反馈数据   │                   │   │
│  │  │ (DAG+轨迹)    │  │ (全链路)      │  │ (评分/评价)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         分析提炼层                                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 复盘分析器 (Retrospective Analyzer)                                 │   │   │
│  │  │   • 成功/失败总结                                                    │   │   │
│  │  │   • 关键决策分析                                                    │   │   │
│  │  │   • 异常模式识别                                                    │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 模式提取器 (Pattern Extractor)                                      │   │   │
│  │  │   • 成功模式提取                                                    │   │   │
│  │  │   • 失败教训提取                                                    │   │   │
│  │  │   • 可复用 Skill 生成                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         经验存储层                                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                     Experience Store (经验库)                        │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │   │
│  │  │  │成功模式   │  │失败教训   │  │领域知识   │  │Skill模板  │       │   │   │
│  │  │  │(待审)    │  │(待审)    │  │(待审)    │  │(待审)    │       │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                              │
│                                      ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审查激活层                                          │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 人工审查      │  │ 自动验证      │  │ 经验激活      │                   │   │
│  │  │ (用户批准)    │  │ (交叉验证)    │  │ (注入RAG)    │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 经验模型

```python
# ============ 完整经验模型 ============

class ExperienceItem:
    """经验项"""
    
    id: str
    type: str                          # success_pattern | failure_lesson | domain_knowledge | skill_template | anti_pattern
    
    # 内容
    title: str
    description: str
    detailed_content: str              # 详细内容
    
    # 适用条件
    conditions: ExperienceConditions
    
    # 证据
    evidence: ExperienceEvidence
    
    # 状态
    status: str                        # pending_review | active | deprecated | rejected
    confidence: float                  # 0-1
    version: int
    
    # 元数据
    created_at: datetime
    created_by: str                    # system | user
    reviewed_at: datetime | None
    reviewed_by: str | None
    review_comment: str | None
    deprecated_at: datetime | None
    deprecation_reason: str | None
    
    # 效果追踪
    usage_count: int
    success_rate: float
    last_used_at: datetime | None


class ExperienceConditions:
    """经验适用条件"""
    task_types: List[str]              # ["diagnostic", "build", "modify"]
    domains: List[str]                 # ["software_dev", "devops"]
    tools_available: List[str]         # 需要哪些工具
    complexity_range: Tuple[int, int]  # 1-10 复杂度范围


class ExperienceEvidence:
    """经验证据"""
    from_task_ids: List[str]           # 来自哪些任务
    sample_count: int
    success_count: int
    failure_count: int
    success_rate: float
    correlation_score: float
```

### 7.2.1 经验标签与跨项目共享体系（五维标签 × 标签上下文检索 × 防幻觉）★

> 2026-08-24 补充（Founder 讨论: 经验可共享, 但需标签防混淆; 前后端双项目场景）。
> 核心: **经验共享是组织记忆特性; 混淆/幻觉靠"标签上下文"守住**——匹配单元是
> 任务的技术栈上下文, 不是项目边界。

**① 目标**

```
经验共享（组织记忆价值）✅ 但绝不混淆 / 绝不幻觉
手段: 多维标签 + 按标签上下文检索 + 来源标注 + 置信度门槛
```

**② 五维标签（枚举值, 避免自由文本）**

```
标签 = { 域 × 技术栈 × 任务类型 × 项目 × 通用度 }
```

| 维度 | 取值（枚举） | 作用 |
|---|---|---|
| 域 domain | coding / ops / data / office / general | 行业工厂维度 |
| 技术栈 stack | frontend_react / frontend_vue / backend_python / backend_java / db / mobile_flutter / devops / general | **防前后端混淆的关键** |
| 任务类型 task_type | bugfix / feature / refactor / perf / test / docs | 场景匹配 |
| 项目 project | 来源 slug（唯一标识） | 项目特定经验隔离 |
| 通用度 generality | **universal**（全共享）/ **stack**（同栈共享）/ **project**（仅项目内） | 共享边界 |

**③ 打标: 自动三层 + 保守校验（防打错）**

```
第 1 层 规则打标（确定性）: 项目←来源任务 · 任务类型←任务元数据 ·
  技术栈←文件扩展名/agent_type
第 2 层 LLM 补标（辅助）: 规则无法确定的域/技术栈 → LLM 判断
第 3 层 校验门（铁律）: 规则 vs LLM 冲突 → 保守降级为 general
  铁律: 打错标签比不打更危险 → 不确定就标 general, 靠检索场景再细分
```

**④ 标签纠错（打错怎么办）**

```
检索后反馈闭环:
  同栈任务命中且有用 → 置信度↑, 标签保持
  异栈任务命中但判定无关 → 标签收紧（stack → project）
  同标签长期低置信 → 标记待复核（人工/LLM 重审）
配合 §7.3 学习护栏: 低样本不主导
```

**⑤ 检索匹配（按标签上下文, 防污染）**

```
当前任务 → 提取标签上下文 {domain, stack, task_type, project}
匹配规则（通用度决定边界）:
  universal → 全项目可用（编码规范）
  stack     → 仅同技术栈任务可用（React 经验只给前端任务）
  project   → 仅同项目可用（"项目A登录慢查询"只给 A）
  + domain / task_type 匹配加分
置信度 = 匹配标签数 / 期望标签数
  < 0.5 → 不注入（防低质量参考）· ≥ 0.5 → 注入且带来源标注
```

**⑥ 来源标注（防幻觉, 铁律）**

```
任何注入的经验带 {source_project, tags, confidence}
上下文分两区:
  本项目事实区: workspace_context / 项目文件 / 项目内资产
  跨项目参考区: 标签命中的他项目经验（只作参考）
LLM 提示词强制:
  "参考区内容不得断言为本项目存在的事实; 不确定 → 明确说'需要确认'"
```

**⑦ 两种项目形态的满足性（Founder 场景）★**

```
场景 A: 两个独立项目（前端项目 + 后端项目）
  前端 React 经验 → 跨项目给 B 的前端任务（stack 匹配, 跨项目 ✅）
  后端 Python 经验 → A 的后端任务（同理 ✅）
  项目特定经验（"A 登录慢查询"）→ 仅 A（project 维度 ✅）

场景 B: 一个项目含前端 + 后端（monorepo/单产品双栈）
  项目 X 的前端任务 → 只拿前端经验（stack 不匹配 → 同项目后端经验不注入 ✅）
  项目 X 的后端任务 → 只拿后端经验（同理 ✅）

关键: 匹配单元是"任务的技术栈上下文", 不是"项目边界"——
  stack 维度同时解决 跨项目共享(A) 和 项目内隔离(B)。
```

**⑧ 与现有模型关系（落点）**

```
ExperienceItem.conditions 已有 task_types/domains 雏形
  → 扩展 tags = {domain, stack, task_type, project, generality}
  → 检索 search() 升级: 标签上下文匹配 + 置信度阈值 + 来源标注
  → 上下文注入: 事实/参考两区分离 + LLM 提示词（§4.11 衔接）
  → 与 §7.3 学习护栏（置信度/低样本不主导）闭环
```

**结论**: 经验共享不靠"全量共享"也不靠"项目隔离", 而是**按标签上下文共享**——
通用经验全共享、同栈经验跨项目共享、项目特定经验仅项目内。stack 维度
一维同时满足"两项目共享"与"单项目双栈隔离"。

### 7.2.2 多项目隔离边界与全局共享层（共享 × 隔离 = 完整边界）★

> 2026-08-24 补充（Founder 询问: 创建多个项目, 项目间有影响吗? 上下文/记忆是否混淆?）:
> 结论——**项目执行隔离, 组织层共享**; 共享靠标签（§7.2.1）, 隔离靠边界（本节）。

**① 隔离边界表**

| 层 | 位置 | 隔离级别 | 说明 |
|---|---|---|---|
| 项目数据 | `projects/<slug>/` | ✅ 项目级 | product/project/execution_state/plan/schedule/decomposition/workspace_context 各自独立 |
| **沙箱** | 复制单个项目 | ✅ 天然隔离 | 项目 A 的沙箱改动碰不到项目 B（§5.13） |
| 文件锁 | 项目目录 | ✅ 项目级 | `_locks_file` 按项目 |
| 执行 | 项目目录 | ✅ 项目级 | orchestrator 按 slug 定位 |
| Agent 员工 | `~/.factory/agents/` | ⚠️ 全局共享 | 所有项目共享同一批"员工"（同一组织, 正常） |
| 组织记忆（经验） | `~/.factory/memory/` | ⚠️ 全局共享 | 项目 A 经验项目 B 可复用（§7.2.1 标签控制） |
| 审计 | `~/.factory/audit/` | ⚠️ 全局共享 | 所有项目混存一个文件（project_id 字段区分） |

**② 三个守则（防混淆, 必须守）**

```
守则 1: 审计/视图必须按 project_id 过滤
  → §5.11 多维视图的 view 参数带项目过滤, 禁止"看项目 A 混入 B"
守则 2: 经验共享必须过标签（§7.2.1）
  → 通用全共享 / 同栈跨项目共享 / 项目特定仅项目内
  → 低置信不注入 + 来源标注（防幻觉）
守则 3: 全局文件并发写要锁
  → 多项目同时执行 → 审计/经验并发写同一文件
  → AuditStore 原子落盘 + 写锁（确认并发安全）
```

**③ 共享与隔离的关系（一体两面）**

```
§7.2.1 共享: 经验按标签上下文共享（组织记忆价值）
§7.2.2 隔离: 项目数据/沙箱/执行严格隔离（互不破坏）
两者叠加 = 完整边界:
  改不坏（沙箱/数据隔离）· 学得到（经验共享）· 不混淆（标签+过滤）· 可追溯（审计按项目）
```

**④ 与幻觉防护的衔接**

```
上下文（本项目事实）: 项目级隔离 ✅（workspace_context 在项目目录）
记忆（跨项目参考）: 标签匹配 + 来源标注 + 置信度门槛（§7.2.1 ⑤⑥）
幻觉防线: 事实区/参考区分离 + LLM 提示词强制"参考不得断言为本项目事实"
```

**结论**: 多项目 = **执行隔离（数据/沙箱/锁）+ 组织共享（员工/记忆/审计）**。
隔离防破坏, 共享造价值, 标签防混淆, 过滤防串台——四者缺一不可。

### 7.3 学习可控性机制

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         学习可控性机制                                             │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制1: 双盲验证                                                             │   │
│  │  新经验在 3-5 个任务中验证 → 通过验证 → 进入审查流程                       │   │
│  │  未通过验证 → 自动丢弃或标记为低置信度                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制2: 人类在环                                                             │   │
│  │  所有经验必须经过人工审查 → 批准/拒绝/修改                                  │   │
│  │  用户可选择: 自动批准低风险经验 / 全部人工审查                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制3: 版本回滚                                                             │   │
│  │  经验有版本号，可回滚到之前版本                                              │   │
│  │  经验失效后自动标记 deprecated，不影响已有引用                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制4: 冲突检测                                                             │   │
│  │  新经验与现有经验冲突 → 告警 → 请求用户裁定                                │   │
│  │  冲突类型: 矛盾 / 重复 / 过时                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制5: A/B 测试                                                             │   │
│  │  将任务随机分配到: 使用新经验组 / 对照组                                    │   │
│  │  对比效果 → 效果显著提升 → 全量推广                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 机制6: 审计追踪                                                             │   │
│  │  记录谁、何时、为什么应用了某条经验                                          │   │
│  │  经验应用效果可追溯                                                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 7.4 学习内容类型与示例

| 类型 | 定义 | 示例 |
|---|---|---|
| **成功模式** | 什么方法在什么条件下有效 | "在诊断内存泄漏时，先获取 heap dump 再分析引用链，成功率为 90%" |
| **失败教训** | 什么做法要避免 | "不要在生产环境直接修改配置，应先备份" |
| **领域知识** | 行业专业知识 | "Spring Boot 应用中，@Component 默认是单例模式" |
| **Skill 模板** | 可复用的能力模板 | "Python 内存分析 Skill: 使用 memory-profiler + pympler" |
| **反模式** | 常见的错误套路 | "服务假死时不要急于重启，应先 dump 堆栈" |
| **决策规则** | 特定决策的判断规则 | "当测试失败率 > 20% 时，优先回滚而非继续修复" |
| **工作流模板** | 可复用的流程模板 | "标准 Bug 修复流程: 复现 → 定位 → 修复 → 验证 → 提交" |
| **工具组合** | 工具搭配使用的模式 | "性能分析: 先用 profiler 定位热点，再用 flamegraph 可视化" |


### 7.5 学习实现对照与完成度（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 经验存储 | `console/memory/experience_store.py`（五域经验） | ✅ |
| 经验提取 | `memory/extraction.py` + `auto_learn.py` | ✅ |
| 学习引擎 | `memory/learning_engine.py` + `learning_trace.py` | ✅ |
| 检索 | `memory/retrieval.py`（经验检索） | ✅ |
| 推荐 | `memory/recommendation.py`（四因素评分） | ✅ |
| 评价 | `exec/evaluator.py`（5 层候选评分） | ✅ |
| **闭环接线**（经验→画像→决策引用→回写） | 设计（M4 自我提升闭环） | 📐 |
| 可信度护栏 / 学习开关 | 设计（M4 C5） | 📐 |

**完成度**：学习**存储/提取/检索/推荐/评价**已实现（✅）；**闭环**（画像/决策引用/回写/护栏）待 M4。

## 八、RAG 知识检索体系

### 8.1 RAG 架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              RAG 架构                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        三级检索体系                                        │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ L1: 平台级 RAG                                                       │   │   │
│  │  │   • 内容: 系统架构文档、治理规则、审计经验                            │   │   │
│  │  │   • 范围: 所有项目共享                                                │   │   │
│  │  │   • 更新: 系统升级时                                                  │   │   │
│  │  │   • 检索时机: 始终可用                                                │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                    │                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ L2: 领域级 RAG                                                       │   │   │
│  │  │   • 内容: 行业工厂知识 (设计模式/运维手册/运营方法论)                 │   │   │
│  │  │   • 范围: 该工厂所有项目共享                                          │   │   │
│  │  │   • 更新: 工厂模板升级时                                              │   │   │
│  │  │   • 检索时机: 该工厂任务运行时                                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                    │                                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ L3: 项目级 RAG (用户外挂)                                            │   │   │
│  │  │   • 内容: 代码仓库、设计文档、历史故障报告、会议纪要                  │   │   │
│  │  │   • 范围: 仅当前项目                                                  │   │   │
│  │  │   • 更新: 用户主动更新 / 文件变更监听                                 │   │   │
│  │  │   • 检索时机: 任务需要上下文时                                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        检索流程                                            │   │
│  │                                                                             │   │
│  │  查询 (Query)                                                               │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 1: 查询增强                                                     │   │   │
│  │  │   • 意图识别: 这是代码问题/文档问题/运维问题?                       │   │   │
│  │  │   • 查询扩展: 同义词、相关术语、多语言                               │   │   │
│  │  │   • 历史关联: 之前是否问过类似问题                                   │   │   │
│  │  │   • 上下文注入: 当前任务 + 项目信息                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 2: 路由选择                                                     │   │   │
│  │  │   • 判断查询类型 → 决定检索哪一级                                    │   │   │
│  │  │   • 优先级: L3 > L2 > L1                                            │   │   │
│  │  │   • 可同时检索多级后融合                                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 3: 多路召回                                                     │   │   │
│  │  │   • 向量检索: 语义相似度 (Chroma)                                    │   │   │
│  │  │   • 关键词检索: BM25 精确匹配                                        │   │   │
│  │  │   • 结构化检索: 元数据过滤 (文件类型/时间/作者)                      │   │   │
│  │  │   • 每种召回 Top-20                                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 4: 重排融合                                                     │   │   │
│  │  │   • RRF 融合: 合并多路结果                                            │   │   │
│  │  │   • 重排序: 小模型精排 (Cross-Encoder)                              │   │   │
│  │  │   • 多样性: 避免结果过于集中                                          │   │   │
│  │  │   • 时效性: 新文档更高权重                                            │   │   │
│  │  │   • 输出 Top-5                                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │      │                                                                      │   │
│  │      ▼                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 5: 上下文注入                                                   │   │   │
│  │  │   • 注入 Agent 工作记忆                                              │   │   │
│  │  │   • 标记来源 (文件路径 + 位置 + 置信度)                              │   │   │
│  │  │   • 生成检索摘要                                                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 文档切分策略

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         文档切分策略                                                │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 按文件类型切分                                                              │   │
│  │                                                                             │   │
│  │  ┌───────────────┬──────────────────────────────────────────────────────┐  │   │
│  │  │ 文件类型       │ 切分策略                                            │  │   │
│  │  ├───────────────┼──────────────────────────────────────────────────────┤  │   │
│  │  │ .py / .js     │ 函数级 + 类级 (保留导入和docstring)                 │  │   │
│  │  │ .java / .go   │ 函数级 + 类级                                        │  │   │
│  │  │ .md / .rst    │ 章节级 (按标题)                                      │  │   │
│  │  │ .json         │ 字段级 (顶层key拆分)                                 │  │   │
│  │  │ .yaml/.yml    │ 文档级 / 顶级key拆分                                  │  │   │
│  │  │ .sql          │ 语句级 (按 ; 分隔)                                   │  │   │
│  │  │ .txt / .log   │ 段落级 (空行分隔)                                     │  │   │
│  │  │ 其他文本      │ 滑动窗口 (512 tokens, overlap 20%)                   │  │   │
│  │  └───────────────┴──────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 元数据提取                                                                  │   │
│  │                                                                             │   │
│  │  每个 Chunk 附带:                                                           │   │
│  │   • source: 文件路径                                                        │   │
│  │   • type: 代码/文档/配置/日志                                               │   │
│  │   • language: Python/Java/...                                               │   │
│  │   • module: 模块名                                                          │   │
│  │   • function: 函数名 (代码文件)                                             │   │
│  │   • class: 类名 (代码文件)                                                  │   │
│  │   • line_start: 起始行号                                                    │   │
│  │   • line_end: 结束行号                                                      │   │
│  │   • timestamp: 文件修改时间                                                  │   │
│  │   • author: 文件作者                                                        │   │
│  │   • project_id: 项目 ID                                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 RAG 更新策略

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         RAG 更新策略                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 更新方式                                                                    │   │
│  │                                                                             │   │
│  │  ┌───────────────┬──────────────────────────────────────────────────────┐  │   │
│  │  │ 更新方式       │ 说明                                                │  │   │
│  │  ├───────────────┼──────────────────────────────────────────────────────┤  │   │
│  │  │ 增量更新      │ 只更新变化的文件 (基于 MD5 检测)                    │  │   │
│  │  │ 全量重建      │ 重建整个索引 (版本升级/数据损坏)                    │  │   │
│  │  │ 定时刷新      │ 每小时/每天自动检查更新                              │  │   │
│  │  │ 手动触发      │ 用户执行 factory rag update                          │  │   │
│  │  │ 文件监听      │ 监听文件变化，实时更新 (可选)                        │  │   │
│  │  └───────────────┴──────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 更新策略选择                                                                │   │
│  │                                                                             │   │
│  │  文件变化量 < 20% → 增量更新                                                │   │
│  │  文件变化量 ≥ 20% → 全量重建                                                │   │
│  │  首次索引 → 全量重建                                                        │   │
│  │  版本升级 → 全量重建                                                        │   │
│  │  数据损坏 → 全量重建                                                        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 8.4 RAG 实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 经验检索 | `console/memory/retrieval.py`（经验库检索） | ✅ |
| 三级 RAG（文档切分/知识图谱/规则库） | 本文档 7.x（设计） | 📐 |
| 领域知识库 | 设计（T4 增强层） | 📐 |

**完成度**：经验检索已实现（✅）；三级 RAG/领域知识库为设计（📐）。

### 8.5 RAG 与知识库的配置分档与升级路径 ★

> 2026-08-22 补充（用户提问）: 有 4 种部署形态（纯 AI Factory / +DB / +RAG / +RAG+DB），
> 调用链各不相同；纯 AI Factory（档 1）后期数据体量上来要能**无痛渐进升级**。

#### 8.5.1 四种配置档位

| 档 | 组成 | 适用 | 检索能力 |
|---|---|---|---|
| 1 纯 AI Factory | 本地文件（JSON/内存）+ LLM 上下文 | 单机/轻量/POC | 无检索，靠 LLM 上下文 + 简单文件读取 |
| 2 + 数据库 | 结构化存储（SQLite/Postgres：projects/agents/experience/audit） | 数据落地/可查询 | 结构化查询（SQL），无语义检索 |
| 3 + RAG | 向量检索（文档/经验 → embeddings） | 需语义检索 | 语义检索（向量） |
| 4 + RAG + DB | 向量库 + 结构化库 + 三级 RAG | 生产/企业级 | 结构化 + 语义 + 混合检索 |

#### 8.5.2 调用链（每档的检索路径）

```
档1: 调用 → LLM 上下文（prompt 内嵌少量文件/经验）→ 生成
档2: 调用 → SQL 查询（结构化）→ 结果进上下文 → 生成
档3: 调用 → 向量检索（embedding 相似度）→ 命中文档/经验进上下文 → 生成
档4: 调用 → 混合检索（结构化 + 向量 + 图谱）→ 融合排序 → 上下文 → 生成
```

#### 8.5.3 设计原则（配置解耦，调用统一）

- **同一调用接口**：`retrieve(context) → refs[]`，内部按档位路由实现——Agent/业务代码**不感知档位**
- **存储抽象**：`KnowledgeStore` 接口（文件 / SQLite / Postgres / 向量库可插拔，§2 热插拔）
- **经验检索 = 轻量 RAG**（现有 ✅）：execution_records → 经验 → 检索；档 3/4 才升级为向量化

#### 8.5.4 档 1 → 档 4 的升级路径（数据体量上来怎么办）

```
数据体量小: 档1 够用（JSON + 内存 + LLM 上下文）
  ↓ 增长信号: 文件多 / 检索慢 / 上下文塞不下 / 回答不准确
  ↓ 渐进升级（不改调用代码，只换存储实现）:
    档2 加 DB    → 结构化查询（项目/经验/审计按需查）
    档3 加 RAG   → 经验/文档向量化 → 语义检索
    档4 完整     → 三级 RAG + 图谱 + 混合检索
量化触发阈值: 文件数 > N / 检索延迟 > T / 命中率 < M（M5 定义）
```

**关键**：从 1 到 4 是**无痛渐进**——调用接口统一（`retrieve` 抽象），数据源从"文件/内存"换成"DB/向量库"，Agent 与业务代码零改动。

#### 8.5.5 与现状衔接

| 项 | 状态 |
|---|---|
| 经验检索（execution_records → memory/retrieval） | ✅ = 档 1-2 轻量检索 |
| 三级 RAG / 知识库 | 📐 = 档 3-4 |
| `KnowledgeStore` 存储抽象（可插拔） | 📐 M5 |

#### 8.5.6 两种所有权模式：自建 vs 外挂 ★

> 2026-08-22 补充（用户提问）: 除档位外，还有**所有权**维度——RAG/DB 由 AI Factory **自己创建管理**，
> 还是**外挂**企业已有的库。企业级部署必须两者都支持。

**档位 × 所有权矩阵**

| | 自建（AI Factory 创建） | 外挂（BYO 企业已有） |
|---|---|---|
| **档2 +DB** | 首次运行自动创建 SQLite/Postgres（零配置） | 连接企业已有 Postgres/MySQL（`db_url` 适配） |
| **档3 +RAG** | 内置向量库（文件/经验自动向量化） | 连接企业向量库（pgvector/Milvus/Weaviate 适配） |
| **档4 完整** | 自建结构化 + 自建向量 + 三级 RAG | 企业 DB + 企业向量库 + 企业知识库混合接入 |

**调用链差异**

```
自建: retrieve → AI Factory 内部存储（自己创建的库）→ 结果进上下文
外挂: retrieve → KnowledgeStore 适配器 → 企业已有库（凭证连接）→ 结果进上下文
```

**设计原则**

| 原则 | 说明 |
|---|---|
| KnowledgeStore 接口 | 自建实现 + 外挂适配器都是它的实现——业务代码无差别（§8.5.3 统一） |
| **数据主权** | 外挂模式数据留在企业侧，不强制上云/复制（§18 数据主权） |
| **凭证安全** | 外挂连接凭证加密存储（§2 凭证设计 + §20.6） |
| 冷启动 | 自建零配置开箱即用；外挂需用户提供连接参数 + 健康检查 |

**选择标准**

```
自建: 轻量/独立部署/无既有基础设施/想开箱即用
外挂: 企业已有库/合规要求数据留在原地/想复用企业知识资产
```

#### 8.5.7 与现状衔接（新增两维）

| 项 | 状态 |
|---|---|
| 经验检索（自建文件/内存） | ✅ = 自建档1-2 轻量 |
| 自建 SQLite/Postgres | 📐 M5（KnowledgeStore 落地） |
| 外挂适配器（Postgres/向量库） | 📐 M5+（企业级） |

#### 8.5.8 存储模块数据同步（事实源 + 投影；不是"历史迁移"）★

> 2026-08-22 更正（用户关键判断）: 档1→档2/3 不是"迁移历史数据"，而是**新增存储模块后的数据同步**——
> 文件存储不被替换，而是**事实源（Source of Truth）**；DB/向量是它的**投影（Projection）**，持续同步。

**存储分层（所有存储都是模块，遵循 §2.12 模块间数据同步）**

```
事实源（Source of Truth）: 文件/事件（原始数据，审计，不可变）
   = 档1 的自然存储，永久保留（事件溯源 §5.6）
投影（Projections）: 由事实源事件驱动构建
   = DB（结构化查询投影）· Vector（语义检索投影）· 图谱（关系投影）
```

**同步机制（不是搬走，是多份一致）**

```
事实源写（本地事务 + Outbox）→ 事件（§2.12）
  → DB 投影模块消费 → 更新结构化索引
  → Vector 投影模块消费 → 更新向量索引（新内容 embedding）
  → 图谱投影（M5）→ 更新关系
  幂等（统一 id）· 可重放（重建投影）· 事件溯源（事实源不可变）
```

**新增存储模块时的"一次性回填"**（这是模块加入的初始化，不是历史迁移）

```
加入 DB 模块: 从事实源扫描 → 全量建结构化索引（幂等）
加入 Vector 模块: 从事实源扫描 → 全量 embedding → 建向量索引
之后: 持续事件同步（新数据自动进各投影）
```

**关键设计**

| 项 | 说明 |
|---|---|
| 事实源唯一 | 文件/事件不可变，是唯一权威；投影可随时丢弃重建（从事实源重放） |
| 投影可重建 | DB/向量坏/删 → 从事实源重放重建（§2.12 事件重放） |
| 一致性 | 事实源最终一致地推到各投影；查询投影允许短暂滞后 |
| 命令 | `factory storage sync --replay`（重建任一投影；M5） |
| 与 §2.12 统一 | Outbox / 幂等 / 事件重放 / 死信 全部复用 |

**结论**：档1 数据不会"丢"，也不会"被搬走"——它作为事实源永久存在；DB/RAG 只是它的可重建投影。升级 = 加投影模块 + 事件同步，不是历史迁移。

#### 8.5.9 数据分级与同步策略（有用的拿走，没用的不同步）★

> 2026-08-22 补充（用户关键判断）: 同步不是"全量照搬"——数据按价值分级，
> **有用的进投影，没用的同步过去浪费空间/成本**（尤其向量化昂贵）。

**数据分类表（每类决定：是否同步 + 策略）**

| 数据类 | 示例 | 同步到投影？ | 策略 |
|---|---|---|---|
| 高价值结构化 | 项目资产 / PRD / artifacts / 证据包 / 审批决策 / 经验 | ✅ 全量 | DB + 向量（核心资产） |
| 执行结果摘要 | execution_records（成功/失败/成本/耗时） | ✅ 摘要 | DB（绩效/画像/分配） |
| 决策链 | plan / replan / decisions | ✅ 全量 | DB + 图谱（为什么这么做） |
| **原始 LLM 日志** | prompts / 完整 outputs | ❌ **不同步** | 隐私 + 体积；只留审计引用（脱敏） |
| **大 blob** | patch 文件 / 媒体 / 大文档 | ⚠️ **只留元数据+引用** | 内容按需取，不同步全量进向量 |
| 临时 / 缓存 | 中间产物 / 构建缓存 | ❌ 不同步 | 用完即弃（不占投影） |
| 审计事件 | audit 全链 | ✅ 索引 | DB 索引，原文留事实源（不可变） |
| 监控指标 | 实时指标 | ⚠️ 聚合后 | 存聚合摘要，不存原始流 |

**同步策略（由数据价值驱动）**

```
全量同步   → 高价值（资产/决策/经验/审批）
摘要同步   → 执行结果/监控（降采样，保留统计）
引用同步   → 大 blob（只同步元数据 + content_ref，内容按需取）
不同步     → 原始 LLM 日志/临时/缓存（隐私 + 省空间 + 省成本）
```

**关键设计**

| 项 | 说明 |
|---|---|
| 价值驱动 | 同步范围按数据价值分级配置，不是一刀切全量 |
| 成本意识 | 向量化只对"值得检索"的内容（经验/知识/决策），日志/临时不向量化 |
| 隐私 | 原始 LLM 输入输出不同步投影（脱敏 + 审计引用，§18 数据主权） |
| 可配置 | `factory storage policy`（每数据类：sync/summary/reference/skip）M5 |
| 与 §8.5.8 衔接 | 事实源保留全部；投影只含"值得同步"的子集 |

**结论**：事实源 = 全部数据（不可变）；投影 = **价值筛选后的子集**——有用的拿走，没用的不同步，空间/成本/隐私三赢。

## 九、工具生态与集成体系

### 9.1 工具生态架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              工具生态架构                                           │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        核心引擎层                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                     Tool Registry (工具注册表)                       │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │   │
│  │  │  │ 注册     │  │ 查询      │  │ 调用      │  │ 审计      │       │   │   │
│  │  │  │ (register)│  │ (lookup)   │  │ (execute)  │  │ (audit)   │       │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│        ┌───────────┬───────────────┼───────────────┬───────────┐                  │
│        │           │               │               │           │                  │
│        ▼           ▼               ▼               ▼           ▼                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐ ┌─────────┐ ┌──────────┐               │
│  │ 内置工具 │ │  Skill  │ │  MCP 协议  │ │Hermes   │ │OpenClaw  │               │
│  │ (Built-in)│ │ (自定义)│ │ (Model     │ │         │ │          │               │
│  │          │ │         │ │  Context   │ │         │ │          │               │
│  │ read_file│ │ 分析Skill│ │  Protocol) │ │ 多步    │ │ 浏览器   │               │
│  │ write_file│ │ 生成Skill│ │            │ │ 工作流   │ │ 自动化   │               │
│  │ search   │ │ 重构Skill│ │ GitHub    │ │         │ │          │               │
│  │ run_cmd  │ │         │ │ Jira       │ │         │ │          │               │
│  │          │ │         │ │ Docker     │ │         │ │          │               │
│  │          │ │         │ │ K8s        │ │         │ │          │               │
│  └─────────┘ └─────────┘ └─────────────┘ └─────────┘ └──────────┘               │
│                                                                                     │
│  原则: 任何外部工具都不是必要条件                                                    │
│        内置工具 → Skill → MCP → Hermes → OpenClaw (能力递增，依赖性递增)          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 工具集成方式对比

| 方式 | 实现复杂度 | 能力范围 | 性能 | 依赖性 | MVP 支持 |
|---|---|---|---|---|---|
| **内置工具** | 低 | 基础 (读/写/执行/搜索) | 高 | 无 | ✅ |
| **Skill** | 中 | 领域专用、可组合 | 中 | 项目内 | ⚠️ Sprint 5 |
| **MCP 协议** | 中 | 外部服务接入 | 中 | 外部服务 | ⚠️ Sprint 4 |
| **Hermes** | 低 | 多步骤任务编排 | 中 | 无 | ⚠️ Sprint 4 |
| **OpenClaw** | 高 | 浏览器/桌面自动化 | 低 | 外部工具 | ❌ Sprint 6+ |

### 9.3 内置工具详细规格

| 工具 | 功能 | 参数 | 输出 | 副作用 | 风险 | 超时 |
|---|---|---|---|---|---|---|
| **read_file** | 读取文件 | path, max_lines, encoding | content, metadata | read | low | 10s |
| **write_file** | 写入/修改 | path, content, mode | result, diff | write | high | 10s |
| **search_code** | 搜索代码 | query, path, file_pattern, max_results | matches | read | low | 30s |
| **run_command** | 执行命令 | command, cwd, timeout, env | stdout, stderr, exit_code | execute | high | 60s |

### 9.4 工具调用完整流程

```
Agent 决策调用工具
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1: 工具查找                                                           │
│   1. 在 Registry 中按名称查找                                              │
│   2. 找不到 → 尝试 Skill 查找                                              │
│   3. 找不到 → 尝试 MCP 查找                                                │
│   4. 都找不到 → 返回错误: 工具不可用                                       │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 2: 参数验证                                                           │
│   1. 检查必需参数是否齐全                                                  │
│   2. 检查参数类型是否正确                                                   │
│   3. 检查参数值是否在合法范围内                                             │
│   4. 检查文件路径是否在项目范围内 (路径遍历防护)                           │
│   5. 检查命令是否在白名单中 (命令注入防护)                                 │
│   6. 验证失败 → 返回错误: 参数无效                                         │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3: 权限检查                                                           │
│   1. 用户是否有权使用此工具？                                               │
│   2. 风险等级是否可接受？                                                   │
│   3. 是否需要审批？→ 请求用户审批                                           │
│   4. 审批超时或拒绝 → 返回错误: 权限不足                                   │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 4: 执行                                                               │
│   1. 创建执行上下文 (工作目录、环境变量)                                   │
│   2. 执行工具                                                              │
│   3. 监控超时                                                              │
│   4. 捕获异常                                                              │
│   5. 记录执行过程                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 5: 结果处理                                                           │
│   1. 解析执行结果                                                          │
│   2. 提取关键信息                                                          │
│   3. 计算执行耗时                                                          │
│   4. 记录审计日志                                                          │
│   5. 返回 ToolResult                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```


### 9.5 消息平台与社区集成体系

> 补充 (2026-08-21): AI 员工出现在用户日常渠道 — 50+ 消息平台 + 社区/社群。
> 定位: 不是"又一个机器人框架", 而是让 AI Factory 的 Agent/任务结果/审批/证据
> 直达用户所在的 WhatsApp/Telegram/Slack/Discord/微信等渠道, 并运营社区。

#### 9.5.1 价值与定位

```
用户在哪, AI 员工就在哪
  ├─ 消息入口: 在聊天里直接给 AI 派活 (发需求/查进度/审批)
  ├─ 任务出口: Agent 完成 → 证据包/结果推送到渠道
  ├─ 审批联动: 高风险动作 → 渠道内一键审批 (ReviewGate 多渠道化)
  └─ 社区运营: 发帖/回复/舆情监控/FAQ 知识回流
```

#### 9.5.2 平台矩阵（50+）

| 分类 | 平台（示例） | 数量 |
|---|---|---|
| 即时通讯 1:1 | WhatsApp、Telegram、微信、Line、Viber、Signal、KakaoTalk、QQ、iMessage、飞书、钉钉 | ~15 |
| 团队协作 | Slack、Microsoft Teams、Discord、Mattermost、Rocket.Chat、Flock、Zulip、Twist、钉钉群、飞书群 | ~12 |
| 社区/社群 | Discord 服务器、Telegram 频道/群、微信群、Slack Workspace、Discourse、NodeBB、Reddit、知乎、贴吧、微博超话、X/Twitter 社区、Facebook 群组 | ~15 |
| 邮件/表单 | SMTP/IMAP、Gmail、Outlook、Typeform、Google Forms | ~6 |
| 语音/其他 | Twilio 电话/短信、WhatsApp Business API、SMS 网关 | ~5 |
| **合计** | | **50+** |

#### 9.5.3 架构（复用 §二 模块化热插拔 + 消息总线）

```
统一消息抽象层 MessageChannel 协议
  ├─ Channel Adapter: 每个平台一个插件 (热插拔 §二, 独立可替换)
  ├─ 入站: 消息 → 归一化 (ChannelMessage{platform, conversation, sender, text, ts})
  │        → 消息总线 (§2.3.4) → 意图解析 → Agent 路由 (§四)
  ├─ 出站: Agent/任务结果 → 渲染器 → 推送到渠道
  └─ 会话上下文: 按 (platform, conversation) 隔离 → 接记忆 (§七)
```

#### 9.5.4 能力清单

- **消息能力**: 收/发/编辑/删除、媒体附件、消息历史同步
- **会话能力**: 1:1 / 群组路由、@AI 触发、会话级上下文、多 Agent 分派
- **任务联动**: 聊天内派活 ("帮我看看 PR" / "现在进度如何") → 路由到 Agent → 结果+证据包推送
- **审批联动**: 高风险动作 → 渠道内 ReviewGate 审批卡 (approve/reject)
- **定时能力**: 定时巡检/日报/提醒推送
- **社区运营**: 发帖/回复/置顶、舆情监控（关键词/情绪）、FAQ 沉淀 → Knowledge 库 (§八 RAG)
- **通知**: 任务完成/失败/预算告警 → 指定渠道

#### 9.5.5 安全与治理（铁律）

- **凭证**: 平台 token/secret 加密存储（复用 §二 沙箱与凭证安全设计）
- **权限**: 渠道 → Agent 能力白名单；消息触发的敏感动作必须走审批（ReviewGate）
- **审计**: 每条入站/出站消息 + 渠道触发任务落 TOOL_CALL/审计事件
- **不依赖**: 消息平台是增强入口，不是 AI Factory 完成任务的必要条件（核心仍走 CLI/API）

#### 9.5.6 落地优先级

| 批次 | 平台 | 说明 |
|---|---|---|
| P0 | WhatsApp / Telegram / Slack / Discord / 微信 | 5 个核心渠道打通闭环（入站派活→Agent→证据推送→渠道审批） |
| P1 | +20: Teams、飞书、钉钉、邮件(SMTP/IMAP)、Line、Reddit、Discourse… | 团队/社区主力 |
| P2 | 50+ 长尾 | 插件化批量接入（复用 §二 热插拔 + MCP） |

#### 9.5.7 与现有设计的关系

- 复用: §二 消息总线/插件接口 · §四 Agent 路由 · §七 记忆/学习 · §八 RAG(FAQ 回流) · §十六 五(5.1) OpenClaw 多渠道吸收(放大为 50+)
- 新增: session/channels/ 适配器层 + 消息归一化 + 渠道内审批渲染

### 9.6 工具生态实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 工具发现 | `session/tools.py`：AI CLI（codex/hermes/openclaw/claude）+ MCP server 配置扫描 | ✅ |
| 真 MCP 客户端 | `exec/mcp.py`：StdioMCPClient（JSON-RPC，替换 Mock） | ✅ |
| Skill 注册表 | `core/agents/skills.py` | ✅ |
| 消息平台（50+） | §9.5 设计（P0 5 渠道待做） | 📐 |

**完成度**：工具发现 + MCP 真连 + Skill 已实现（✅）；消息平台为设计（📐，M5）。

## 十、行业工厂体系

### 10.1 工厂定义

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              工厂定义                                              │
│                                                                                     │
│  工厂 = Skill + MCP + Knowledge + Workflow + Evaluation + Learning                  │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 工厂模板结构                                                                 │   │
│  │                                                                             │   │
│  │  {                                                                          │   │
│  │    "factory_id": "software_dev_v1",                                         │   │
│  │    "name": "软件开发工厂",                                                   │   │
│  │    "version": "1.0.0",                                                      │   │
│  │                                                                             │   │
│  │    // 1. Skill 定义                                                         │   │
│  │    "skills": [                                                              │   │
│  │      {"name": "analyze_code", "description": "...", "entry": "..."},       │   │
│  │      {"name": "generate_test", "description": "...", "entry": "..."}       │   │
│  │    ],                                                                       │   │
│  │                                                                             │   │
│  │    // 2. MCP 配置                                                           │   │
│  │    "mcp_servers": [                                                         │   │
│  │      {"name": "github", "url": "mcp://github.com"},                         │   │
│  │      {"name": "docker", "url": "mcp://docker.local"}                        │   │
│  │    ],                                                                       │   │
│  │                                                                             │   │
│  │    // 3. 知识库配置                                                         │   │
│  │    "knowledge_base": {                                                      │   │
│  │      "collections": ["design_patterns", "architecture_best_practices"]     │   │
│  │    },                                                                       │   │
│  │                                                                             │   │
│  │    // 4. 工作流模板                                                         │   │
│  │    "workflows": [                                                           │   │
│  │      {"name": "bug_fix", "dag": {...}},                                    │   │
│  │      {"name": "feature_dev", "dag": {...}}                                 │   │
│  │    ],                                                                       │   │
│  │                                                                             │   │
│  │    // 5. 评价标准                                                           │   │
│  │    "evaluation": {                                                          │   │
│  │      "code_quality": {"metrics": ["complexity", "coverage"]},              │   │
│  │      "performance": {"metrics": ["latency", "throughput"]}                 │   │
│  │    },                                                                       │   │
│  │                                                                             │   │
│  │    // 6. 学习配置                                                           │   │
│  │    "learning": {                                                            │   │
│  │      "auto_review": true,                                                   │   │
│  │      "experience_store": "~/.factory/memory/experiences.json"              │   │
│  │    }                                                                        │   │
│  │  }                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 各行业工厂详细场景

#### 软件开发工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 软件开发工厂 — 完整场景                                                             │
│                                                                                     │
│  场景1: 新功能开发                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "实现用户登录功能，支持手机号+验证码"                                 │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 需求澄清 → 交互式确认登录方式、验证码类型、记住密码等               │   │
│  │   T2: 技术设计 → 选择框架、设计数据库表、设计API                           │   │
│  │   T3a: 数据库层实现 → 创建 User 表、验证码表                               │   │
│  │   T3b: 业务逻辑层 → 实现发送验证码、验证登录逻辑                           │   │
│  │   T3c: API 层 → 实现 /login、/send-code 接口                               │   │
│  │   T4: 测试生成 → 单元测试、集成测试                                         │   │
│  │   T5: 验证执行 → 运行测试、修复失败                                         │   │
│  │   T6: 部署配置 → 生成部署脚本、Dockerfile                                  │   │
│  │                                                                             │   │
│  │ 输出: 完整登录功能代码 + 测试 + 部署配置                                    │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Reviewer → Debugger                       │   │
│  │ 所需工具: read_file, write_file, search_code, run_command                  │   │
│  │ 所需知识: 设计模式、框架文档、安全最佳实践                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  场景2: Bug 修复                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "生产环境报 NullPointerException，需要定位并修复"                     │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 日志收集 → 获取错误日志和堆栈                                         │   │
│  │   T2: 代码分析 → 定位报错位置和调用链                                       │   │
│  │   T3: 根因分析 → 为什么会出现 NPE？                                         │   │
│  │   T4: 修复设计 → 设计修复方案 (多个备选)                                    │   │
│  │   T5: 执行修复 → 修改代码 (需用户审批)                                      │   │
│  │   T6: 验证 → 编译检查、运行相关测试                                          │   │
│  │   T7: 审查 → Reviewer 审查修复质量                                           │   │
│  │                                                                             │   │
│  │ 输出: 根因分析报告 + 修复代码 + 测试通过                                    │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Debugger → Planner → Executor → Reviewer                       │   │
│  │ 所需工具: read_file, search_code, write_file, run_command                  │   │
│  │ 所需知识: 错误模式、调试技巧、代码规范                                      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 运维工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 运维工厂 — 完整场景                                                                 │
│                                                                                     │
│  场景: 故障根因定位 + 修复                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "服务 A 的响应时间突然从 100ms 升到 5s，请帮我定位"                   │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 指标采集 → 获取服务 A 的 CPU/内存/网络/错误率等指标                   │   │
│  │   T2: 日志分析 → 采集错误日志、访问日志                                     │   │
│  │   T3: 链路追踪 → 分析调用链，定位瓶颈节点                                    │   │
│  │   T4: 关联分析 → 同时段有什么变更？流量突增？                               │   │
│  │   T5: 根因定位 → 综合判断，给出根因                                         │   │
│  │   T6: 修复建议 → 建议具体修复措施 (需用户审批)                               │   │
│  │   T7: 修复执行 → 执行修复 (需用户审批)                                       │   │
│  │   T8: 验证恢复 → 确认响应时间恢复正常                                        │   │
│  │   T9: 经验记录 → 记录到故障经验库                                            │   │
│  │                                                                             │   │
│  │ 输出: 根因分析报告 + 修复方案 + 恢复验证结果                                │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Debugger → Governor → Learner            │   │
│  │ 所需工具: read_log, query_metrics, trace_chain, run_command               │   │
│  │ 所需知识: 运维手册、故障模式库、SRE 最佳实践                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 电商运营工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 电商运营工厂 — 完整场景                                                             │
│                                                                                     │
│  场景: 选品分析 + 投放优化                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "帮我分析下个月应该重点推哪些品类"                                    │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 市场数据采集 → 获取行业数据、竞品数据、热搜趋势                        │   │
│  │   T2: 竞品分析 → 分析竞品品类、价格、评价                                    │   │
│  │   T3: 用户分析 → 分析用户画像、需求偏好                                      │   │
│  │   T4: 趋势预测 → 预测品类发展趋势                                            │   │
│  │   T5: 选品建议 → 给出推荐品类列表 + 理由                                      │   │
│  │   T6: 投放策略 → 针对推荐品类的投放建议 (需用户确认)                         │   │
│  │   T7: 预算分配 → 建议预算分配方案 (需用户审批)                               │   │
│  │                                                                             │   │
│  │ 输出: 选品报告 + 投放策略 + 预算分配建议                                    │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Reviewer → Governor                       │   │
│  │ 所需工具: query_sales, analyze_trend, scrape_competitor, suggest_bidding   │   │
│  │ 所需知识: 电商运营方法论、品类规律、广告最佳实践                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 自媒体工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 自媒体工厂 — 完整场景                                                               │
│                                                                                     │
│  场景: 内容策划 + 脚本生成 + 多平台分发                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "帮我策划下个月的抖音选题并生成脚本"                                  │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 热点分析 → 获取当前热点话题、趋势词                                   │   │
│  │   T2: 竞品分析 → 分析同类账号的热门内容                                      │   │
│  │   T3: 用户画像 → 分析目标受众偏好                                            │   │
│  │   T4: 选题策划 → 生成 10 个选题 + 优先级排序                                │   │
│  │   T5: 脚本生成 → 为 Top 3 选题生成详细脚本                                   │   │
│  │   T6: 脚本审查 → 评审脚本质量 (需用户确认)                                  │   │
│  │   T7: 多平台适配 → 适配小红书、B站、公众号格式                               │   │
│  │   T8: 发布策略 → 建议发布时间和发布顺序                                      │   │
│  │                                                                             │   │
│  │ 输出: 选题清单 + 脚本 + 多平台适配内容 + 发布建议                           │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Reviewer → Learner                        │   │
│  │ 所需工具: query_trends, analyze_content, generate_script, format_converter  │   │
│  │ 所需知识: 平台算法、热门规律、脚本写作规范                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 数据分析工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 数据分析工厂 — 完整场景                                                             │
│                                                                                     │
│  场景: 数据清洗 + 报表生成 + 异常检测                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "这个季度所有销售数据清洗后生成运营报表"                              │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 数据发现 → 识别数据源、表结构、数据量                                 │   │
│  │   T2: 质量检查 → 检查缺失值、异常值、重复值                                 │   │
│  │   T3: 清洗规则 → 制定清洗规则 (缺失处理、异常修正)                         │   │
│  │   T4: 执行清洗 → 运行清洗任务 (需用户审批)                                  │   │
│  │   T5: 质量验证 → 验证清洗后数据质量                                         │   │
│  │   T6: 指标计算 → 计算 KPI: GMV、转化率、客单价、复购率                     │   │
│  │   T7: 图表生成 → 生成趋势图、对比图、分布图                                 │   │
│  │   T8: 报告排版 → 生成完整运营报表 (自动发送)                                │   │
│  │   T9: 异常标注 → 标注异常数据点并给出解释                                    │   │
│  │                                                                             │   │
│  │ 输出: 清洗后数据集 + 运营报表 + 异常分析                                    │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Reviewer → Governor                       │   │
│  │ 所需工具: read_data, apply_transform, generate_chart, format_report        │   │
│  │ 所需知识: 数据质量规范、指标体系、报表设计规范                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 办公自动化工厂

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 办公自动化工厂 — 完整场景（会议/邮件/审批，对齐 §10.2 全景 + §9.5 消息渠道）       │
│                                                                                     │
│  场景: 会议纪要与行动项 + 邮件分拣 + 审批流自动化                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 输入: "把今天的产品会录音转成纪要，提取行动项分派到人，                       │   │
│  │       并把待批的报销单统一催办"                                               │   │
│  │                                                                             │   │
│  │ 流程:                                                                       │   │
│  │   T1: 会议识别 → 定位会议录音/文字稿、与会人、时间线                        │   │
│  │   T2: 转写与清洗 → 语音转文字、去除口语/重复、分段                          │   │
│  │   T3: 纪要结构化 → 议题/结论/行动项/负责人/截止时间                         │   │
│  │   T4: 行动项分派 → 匹配负责人、生成待办（需用户审批）                       │   │
│  │   T5: 邮件分拣 → 分类（需回复/知会/垃圾）、打标签、按优先级排序              │   │
│  │   T6: 草拟回复 → 生成回复草稿（需用户审批）                                 │   │
│  │   T7: 审批流处理 → 报销/请假单按规则路由、超期催办（Governor 把关）         │   │
│  │   T8: 日历同步 → 会议/截止时间自动入日历、冲突检测                          │   │
│  │   T9: 周报汇总 → 汇总本周行动项完成情况、未完成原因                          │   │
│  │                                                                             │   │
│  │ 输出: 会议纪要 + 行动项看板 + 邮件分类结果 + 审批催办单 + 周报              │   │
│  │                                                                             │   │
│  │ 涉及 Agent: Planner → Executor → Reviewer → Governor                        │   │
│  │ 所需工具: transcribe, summarize, classify_email, draft_reply,               │   │
│  │           route_approval, sync_calendar, format_report                      │   │
│  │ 所需知识: 会议纪要规范、邮件礼仪、审批流规则、周报模板                      │   │
│  │ 治理铁律: 行动项分派/草拟回复/审批路由一律先审批后执行（§6.3）              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 工厂扩展机制

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         工厂扩展机制                                                │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 扩展方式1: 模板定制                                                         │   │
│  │  用户选择基础模板 → 调整参数 → 生成定制版                                    │   │
│  │  示例: 软件开发工厂 → 调整编码规范 → 定制开发流程                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 扩展方式2: 插件扩展                                                         │   │
│  │  用户开发新 Skill → 注册到工厂 → 扩展能力                                   │   │
│  │  示例: 添加 K8s 部署 Skill → 软件开发工厂支持 K8s 部署                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 扩展方式3: 学习扩展                                                         │   │
│  │  工厂运行中自动学习 → 积累领域经验 → 工厂自我进化                           │   │
│  │  示例: 修复多个 Bug 后 → 工厂自动优化 Bug 修复流程                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 扩展方式4: 市场扩展                                                         │   │
│  │  用户发布新工厂模板 → 其他用户使用 → 社区贡献                               │   │
│  │  示例: 用户发布"跨境电商工厂" → 其他电商用户使用并改进                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 10.4 行业工厂实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| IT 工厂（想法→工程→执行） | `actions.create_product` + `pipeline.py` + `repo_mode.py` + `workloads/backlog_sweeper.py` | ✅ |
| 积压清道夫（首个可售卖工作负载） | `backlog_sweeper.py`（分诊→修复→证据→审批→报告） | ✅ |
| FactorySpec 模板 / 第二行业 | 设计（M5/M6） | 📐 |
| 运维/电商/自媒体/数据/办公工厂 | 本文档 9.x 场景（设计） | 📐 |

**完成度**：IT 工厂闭环已实现（✅）；行业复制（FactorySpec + 第二行业）为设计（📐，M5/M6）。


### 10.5 软件工厂专项细化（第一阶段 V1 产品 ★）

> 2026-08-23 补充（Founder 指示）: 软件工厂 = AI Factory 第一个行业实例（V1 产品）。
> 本节把"软件工厂"从通用行业章里**细化到可执行**——业务全景 / 角色团队 / 行业知识 / 资产标准 / 工程规范 / V1 里程碑。

#### 10.5.1 软件工厂业务全景流程（细化到每一步）

| 步骤 | 输入 | 角色 | 输出 | 治理点 | 验收 |
|---|---|---|---|---|---|
| 1 想法 | 一句话 | 用户+PM | ProductIntent + discovery.md | — | 需求字段齐 |
| 2 专家装配 | ProductIntent | ExpertFactory | 7 专家（agt-it-*） | skill 校验 | 缺 skill 报错 |
| 3 交接分析 | 7 专家 | HandoffBus（PM→市场→竞品→UX→架构→QA→PRD） | 7 资产（互引） | 冲突→ReviewGate | parent_artifact 链 |
| 4 PRD | 分析资产 | SeniorPM | PRD（背景/故事/功能P0../验收） | **PRD 审批门** | 用户批准 |
| 5 工程计划 | PRD | Architect | engineering/tasks/execution_plan | 计划审批（recommended） | 计划可执行 |
| 6 任务拆解 | 计划 | TechLead | 原子任务（递归拆到不能拆） | — | 原子可执行 |
| 7 执行 | 原子任务 | 后端/前端/QA Agent | patch → 代码 | 预算+审计 | 单文件/单工具 |
| 8 证据/审批 | 变更 | EvidenceBundle + ApprovalGate | diff+测试+决策 | **分级审批** | 证据完整 |
| 9 交付 | 批准 | Release | 代码落盘+测试报告 | — | pytest 绿 |
| 10 运维/迭代 | 反馈 | PM | 变更提议 | **需求变更回流** | PRD v2 |

#### 10.5.2 软件工厂角色团队（软件行业专属）

| 角色 | 职责 | 技能（示例） | 工具 | 状态 |
|---|---|---|---|---|
| PM | 需求/范围/价值 | 需求分析、优先级 | discovery/PRD | 🚧（4.10：提示词→M2实体✅） |
| Market | 市场/竞品 | 行业分析 | ProductIntelligence | ✅ 真引擎 |
| UX | 交互/信息架构 | 流程设计 | ux 模板 | 🔴 占位（M3 深化） |
| Architect | 技术选型/架构 | python/node/flutter/架构模式 | architecture | 🟡 规则（M3 深化） |
| QA | 测试方案/质量 | 单元/集成/安全 | test_plan | 🔴 占位（M3） |
| 后端工程师 | API/业务逻辑 | python/node/go + 框架 | DeveloperAgent | ✅ |
| 前端工程师 | 页面/交互 | flutter/react | DeveloperAgent | ✅ |
| DevOps | 构建/部署（M3+） | CI/CD | 待接 | 📐 |

#### 10.5.3 软件工厂行业知识（技术栈/规范，可复用模板）

```
平台→技术栈（§pipeline 规则已支持）:
  mobile → Flutter + Backend API
  web    → Web 前端 + Backend API
  desktop→ Desktop + Backend API
后端: Python(FastAPI/Django) / Node(Express) / Go / Java(Spring)
数据库: SQLite(默认) / PostgreSQL / MySQL（§8.5 外挂）
测试: pytest（默认执行器）
```

#### 10.5.4 软件工厂资产标准（每类产物的"长什么样"）

| 资产 | 标准（验收可断言） |
|---|---|
| discovery.md | 问题/用户/核心功能/风险（draft） |
| PRD.md | 背景 + 用户故事 + 功能 P0..Pn + 验收标准（**M3 LLM 深度化**） |
| architecture.md | 技术选型 + 系统设计 + 数据模型 + 风险 |
| tasks.json | 功能→Epic→原子任务（M3 递归拆解） |
| 代码 | 单文件/单工具可验证（原子任务粒度） |
| test_report | pytest 结果 + 覆盖率（真实运行） |
| evidence 包 | diff + 测试 + 决策 + 变更文件（✅ 已实现） |

#### 10.5.5 软件工厂工程规范（V1 打磨）

```
代码: 原子任务粒度（一次一个文件/工具）· 语法校验 + pytest 通过才交付
测试: 每功能至少 1 测试（test_main.py 模式）· 失败→修复循环（§17.13）
审批: patch 应用前必批（§6.3）· 高风险（删除/依赖/基础设施）compliance 必批
PR/交付: 证据包完整 + 测试绿 → 才允许 PR/落盘（M1 收尾: 审批→PR 链路）
变更: 执行中需求变更 → ChangeProposal → PRD v2 + replan（M3）
```

#### 10.5.6 V1 软件工厂里程碑（对齐 §1.7 + 待办清单）

| V1 版本 | 内容 | 验收锚点 |
|---|---|---|
| **V1.0 可信闭环**（≈M3） | 真实 E2E 全链路（你环境）· PRD 深度化 · 递归原子拆解 · 需求变更回流 | "我要做CRM"→真实代码落盘→pytest 绿→变更 PRD v2 |
| **V1.1 可用**（≈M5） | expert build CLI · Web 仪表盘 · 消息 P0 5 渠道 · 执行重放 | 用户能用 CLI/Web 造专家、看证据、跑清道夫 |
| **V1.2 完整**（≈M6+） | 审批→PR 链路 · 记忆回流 E5 · 快照回滚 · 第二行业复制 | 一单"积压清道夫"真实走完：issue→修复→证据→审批→PR |


#### 10.5.7 软件工厂项目管理方法论（敏捷 · 验收优先 · 增量迭代 ★）

> 2026-08-23 补充（Founder 原则 1-3）: 软件工厂内部项目管理——**敏捷 + 验收标准先行 + 增量小步快跑**。

**7.1 敏捷（Agile）落地**

```
迭代(Sprint): 固定节奏（默认 2 周，可调），每迭代交付一个可演示结果
Backlog:     需求/功能进 backlog（积压清道夫 = backlog 引擎）
用户故事:     PRD 深度化后每功能 = 用户故事（作为…我希望…从而…）+ 验收标准
迭代回顾:     每迭代复盘 → 经验入库（§17.11 学习）
三部门 8 步 = 敏捷循环放大版: Claude=PO(产品) · Hermes=架构 · Codex=工程
```

**7.2 验收优先（Acceptance-First）——铁律：先写验收标准，再开发**

```
每个功能/原子任务: 先定义验收标准（Given/When/Then 或可断言检查），再开发
验收标准进 tasks.json（任务自带验收）→ 执行后按断言判定（不"先做再补"）
呼应: §1.7 产品验收标准 · §3.7 原子任务（"可验证"= 原子判定之一）
```

**7.3 增量迭代 · 小步快跑**

```
垂直切片: 一个功能从 需求→PRD→任务→代码→测试 全通，再做下一个（不横切全做）
MVP 优先: 先最小可用（MvpPlan §4 引擎已有），再迭代加功能
小步:    原子任务粒度（§3.7）→ 每步可验证/可回滚 → 快速反馈
防大爆炸: 不做一次性大集成；每迭代一个可演示增量
```

**7.4 与现有机制整合**

| 敏捷要素 | 系统落地 |
|---|---|
| Sprint / 迭代 | 三部门 8 步循环 + 里程碑 M1-M7 |
| Backlog | 积压清道夫（§10.5.1 步骤 10）+ 待办清单 |
| 用户故事 | PRD 深度化（M3，§10.5.4 PRD 标准） |
| 验收标准 | §1.7 八大维度 + tasks.json 任务验收 + 契约测试（§2.11.4） |
| 回顾 / 学习 | §17.11 经验学习（每迭代复盘入库） |
| 小步迭代 | §3.7 原子任务 + 垂直切片 |


**7.5 变更治理门（AI 改代码的信任机制）★**

> 2026-08-24 补充（Founder 核心关切）: 新增功能**一定会**影响已完成的旧功能——
> 三条恐惧: ① AI 改不全（改 A 破坏 B）② 简单问题复杂化（过度设计）③ 复杂问题
> 简单化（丢边界/安全）。信任不能靠模型自觉，要靠**制度化的变更治理门**。

**三个恐惧与对症机制**

| 恐惧 | 根因 | 对症机制 |
|---|---|---|
| **改不全**（改 A 破坏 B，B 调用方没改） | 影响面不透明，无自动发现 | 影响面分析 + 契约测试 + 调用方扫描 + 全量回归 |
| **简单问题复杂化**（过度设计） | AI 倾向加抽象/加层/加配置 | 最小改动纪律 + 复杂度护栏 + 验收锚定需求 |
| **复杂问题简单化**（丢边界/安全） | AI 为过测试而简化 | 铁律不简化 + 失败路径测试 + 删除审查 |

**① 改不全 → 影响面分析（Impact Analysis，改前强制）**

```
改任何模块前，强制回答:
  1. 谁 import 我？（调用方扫描: grep/静态依赖图 → 影响清单）
  2. 谁读我的数据文件？（execution_state / plan.json / 资产 → 消费方清单）
  3. 我改接口/返回值/错误码了吗？（→ 契约测试必须同步过）
  4. 我的改动向后兼容吗？（不兼容 → bump 版本 + 迁移说明）
输出: 影响面清单 → 相关测试全跑（不只是新功能测试）
```

**② 改不全 → 契约测试门槛（§2.11.4 已有）**

```
每个模块第一天: schema/接口/返回值/错误码/血缘 契约测试
改接口 → 契约测试红 → 禁止合入
契约测试 = 模块间"免疫系统": 任何一方改坏契约，立刻暴露
```

**③ 改不全 → 全量回归铁律（已有）**

```
任何合入前: 全量回归 0 新增失败（环境类 flaky 独立确认）
+ 定向回归: 受影响模块 + 调用方 + 数据消费方 全跑
```

**④ 简单问题复杂化 → 最小改动 + 复杂度护栏**

```
最小改动纪律: 每个 Sprint 规格强制"复用不重造 + 最小改动"（Codex 写 scope 锚定）
复杂度护栏（新模块/新抽象审查）:
  - 行数/接口数上限（超限 → 设计评审）
  - "能否不加这个抽象"自查: 每加一层，问能否用已有层
  - 验收锚定需求: 只奖励"需求满足"，不奖励"做了更多"
```

**⑤ 复杂问题简单化 → 铁律不简化 + 失败路径测试**

```
铁律不简化（五类禁止为"简单"而删）:
  安全 · 审批 · 审计 · 数据主权 · 失败安全
失败路径测试（防乐观简化）: 每个模块必须测故障路径
  - LLM 失败 / 无 key / 文件损坏 / 权限拒绝 / 空输入 / 环 / 死锁
  - 只测 happy path = 简化过头信号
删除审查（Review 必问）:
  - 你删了什么？为什么删？
  - 删了之后失败路径还测吗？铁律还成立吗？
```

**⑥ 统一收口: 变更治理门（Change Governance Gate）——6 关**

```
任何新功能合入前必须过 6 关:
  [ ] ① 影响面分析报告（谁会被影响: 调用方 + 数据消费方清单）
  [ ] ② 契约测试全过（接口没破坏）
  [ ] ③ 定向回归（受影响模块+调用方）+ 全量回归 0 新增失败
  [ ] ④ 最小改动审查（没有过度设计, 复用已存在）
  [ ] ⑤ 铁律不简化审查（安全/审批/审计/主权/失败安全 没被删）
  [ ] ⑥ 边界声明核对（Sprint 规格 §8 边界没被越）
6 关全过 → 合入; 任一不过 → 回退/修复
执行人: Hermes Code Review（独立验证, 不轻信自报告）
```

**⑦ 与三部门循环的关系**

```
Claude: 产品/验收（锚定需求 → 防过度设计）
Hermes: 架构 + 变更治理门 6 关（独立验证）
Codex:  实现 + 影响面分析 + 契约测试（自证, 但 Hermes 独立复核）
你:     实测（最终信任锚点——自动化替代不了人工验收）
```

**结论**: 三恐惧不是靠"AI 自觉"，是**制度化的 6 关变更治理门**——影响面透明
（防改不全）、最小改动+护栏（防复杂化）、铁律+失败路径（防简化）。**AI 改代码
的信任 = 机制保证，不是模型保证**——这正是 AI Factory 治理的差异化（§6 治理）。

**7.6 范围与关联管理（范围膨胀 + 关联失控的治理）★**

> 2026-08-24 补充（Founder 反思: 改东西范围越来越大, 关联越来越多, 如何正确管理）:
> 范围膨胀不可怕, 可怕的是**无记录的范围膨胀**。核心 = 5 纪律 + 范围声明模板。

**① 范围纪律: 一个 Sprint 只做一件事**

```
一个 Sprint = 一个能力点 + 明确边界（边界声明）
发现"连带改动" → 记录到待办清单（不顺手做）—— 顺手的"顺便改"是范围膨胀主源
四不铁律: 不乱改 / 不扩展 / 不影响 / 统一修改（S10-098）
```

**② 依赖纪律: 改前影响面分析（变更治理门第①关）**

```
改动前强制回答:
  谁 import 我？（调用方扫描）· 谁读我的数据？（数据消费方）
  我改接口/契约了吗？（契约测试必须过 §2.11.4）
工具: grep 调用方 · 契约测试（模块免疫系统）· dependencies 依赖图
```

**③ 回归纪律: 定向 + 全量**

```
每轮: 定向（受影响模块 + 调用方 + 数据消费方）→ 全量 0 新增
受影响模块清单化: 改动文件 → 调用方 → 数据消费方 → 测试范围（可审计）
```

**④ 版本纪律: 功能 minor / 修复 patch**

```
patch（1.1.x）: 修复 / 小增强
minor（1.2.x）: 新能力（LLMIntentParser / 发现 LLM 化 等应归 minor）
major（2.x）:   SDK / 商业化
问题: 连续 7 个 patch 都在加功能, 应区分 修复(patch) vs 功能(minor)
```

**⑤ 关联可视化: 波及面记录**

```
每次改动记录: 改了什么 → 影响了谁 → 为什么 → 验证了什么
= 变更治理门第①关输出的制度化 → "失控"变"可追溯演进"
```

**范围声明模板（每个 Sprint 提示词必带）**

```
【范围声明】
- 本 Sprint 做: <X>（唯一能力点）
- 明确不做: <Y, Z>（边界）
- 连带发现（进 backlog 不顺手做）: <记录项>
- 波及面预期: 改 <文件> → 影响 <调用方/消费方> → 验证 <测试范围>
```

**结论**: 范围管理的答案不是"减少改动", 而是**记录 + 边界 + 影响面分析 + 版本区分**。
已有机制（待办清单/契约测试/全量回归/变更治理门/版本）就是答案, 缺的是执行纪律。

**7.7 改全保障（完整性校验：如何不遗漏关联改动）★**

> 2026-08-24 补充（Founder 核心担忧: 怕改不全, 有遗漏）: 改不全的根源 =
> **依赖"人记关联", 不依赖"机器校验关联"**。解法 = 把"关联"变成可测试的契约,
> 任何漏改 → 测试红 → 合入前拦截（不是事后发现）。

**核心原则: 靠自动校验抓遗漏, 不靠人记**

```
人的记忆不可靠（改了 conversation 忘 discovery, 加了 intent 忘 router）
自动校验可靠: 任何"漏改" → 测试红 → 当场发现
```

**4 个自动校验机制**

| # | 机制 | 抓什么遗漏 | 现状 |
|---|---|---|---|
| ① | **契约测试**（§2.11.4 模块免疫系统） | 接口改了 → 消费方契约红 | ✅ 已有（需全接口覆盖） |
| ② | **注册表一致性测试** | 新增命令/意图/action/事件/API → 注册表没同步 → 红 | 🚧 雏形（test_all_subcommands_registered 抓过 create 遗漏） |
| ③ | **对称路径一致性测试** | conversation/discovery、CLI/API 改一个没同步另一个 | 🚧 部分（S10-100 对齐过两路径） |
| ④ | **影响面清单自动化** | 改文件 → 调用方/消费方/对称路径没验证 | 📐 手工 grep |

**② 注册表一致性（最有效）— 各注册表一个测试**

```
AI Factory 的注册表: CLI 子命令 · 意图类型 · action 名 · API 端点 · 审计事件 · 模块清单
每个注册表 = 一个测试: 断言"注册表 vs 实现"一致
真实案例: test_all_subcommands_registered 抓到 create 命令漏同步测试
         （新增命令必须同步注册表, 否则红）
```

**③ 对称路径一致性 — 改一个必须同步另一个**

```
对称实现: conversation/discovery · CLI/API · org/console · 审计/监控
对称性测试: 同场景 → 两路径行为断言一致（S10-100 两路径对齐是范例）
```

**改全保障发布门（合入前）**

```
[ ] ① 契约测试全过（接口没破坏）
[ ] ② 注册表一致性过（命令/意图/action/事件/API 全注册）
[ ] ③ 对称路径一致性过（conversation/discovery、CLI/API 对齐）
[ ] ④ 定向回归（受影响 + 调用方 + 对称路径）→ 全量 0 新增
= 变更治理门 6 关 + 完整性校验
```

**结论**: 改不全 = 人记关联不可靠; 解法 = 关联契约化 + 机器校验。
注册表一致性测试（②）+ 对称路径测试（③）是最高性价比——**遗漏从"事后发现"
变成"合入前拦截"**。待办清单 P0（注册表一致性套件 + 对称路径套件）。

#### 10.5.8 全流程节点拆解与设计理由（每个节点：如何/依据/优势/缺点/为什么这么弄）★

> 2026-08-23 补充（Founder 指示）: 软件工厂每个流程节点都要"可解释"——不只是做什么，还要为什么这么弄、代价是什么。

##### 节点 1：想法（Idea）

- **拆解**: 一句话 → ProductIntent（problem/user/core_features）→ discovery.md
- **如何**: InteractiveSession → 意图解析 → Discovery 多轮/批量（S10-050/065，已实现）
- **依据**: 想法入口要低门槛；先澄清再动手，避免"想当然做错方向"
- **优势**: 低门槛 · 结构化 · 可审计（discovery 资产）
- **缺点/代价**: 依赖用户表达；字段化收集偏表单（对话化缓解）
- **为什么这么弄（vs 直接建项目）**: 直接建 = 方向没澄清就投入；先 discovery = 10 分钟澄清省 10 天返工

##### 节点 2：专家装配（ExpertAssembly）

- **拆解**: 行业 spec → 选 7 角色 → ExpertFactory.assemble → 校验（skill/workflow/knowledge）→ AgentEntity（agt-it-*）
- **如何**: M2 已实现；缺 skill → 明确报错；无 LLM → 确定性兜底（M1b 模式）
- **依据**: "造专家的工厂"愿景——角色是**可复用资产**，不是每次重新发明
- **优势**: 角色可复用/可扩展/行业可复制 · 校验防"空转专家" · 可挂 技能/知识/评价/记忆 → 能"越用越强"
- **缺点/代价**: 装配与校验复杂度 · 7 角色需维护 · 本地模型弱时专家"能力不足"（§18.9 拆更细补偿）
- **为什么这么弄（vs 单一大模型换提示词）**: 单一模型+提示词 = 无记忆/无画像/无法演进/无法独立成产品；专家实体 = 组织化资产，可独立产品化（§2.9）

##### 节点 3：交接分析（Handoff）

- **拆解**: PM→市场→竞品→UX→架构→QA→PRD；每步消费上一产出 → parent_artifact 互引
- **如何**: HandoffBus（M2 已实现）；冲突→ReviewGate；消息 {from,to,artifacts,decisions,constraints}
- **依据**: "专业的人做专业的事"；每角色独立产出，避免单一 prompt 混战
- **优势**: 可追溯（谁产出什么）· 可并行（市场/竞品）· 角色可替换 · 每产出=资产
- **缺点/代价**: 7 次 LLM = 7 倍成本 · 串行慢 · 交接信息丢失风险（上下文 L4，§4.11）
- **为什么这么弄（vs 一次 prompt 全生成）**: 一次生成 = 无法审计/无法分工/无法进化；交接 = 组织化协作，每个产出可独立验收/复用

##### 节点 4：PRD（审批门）

- **拆解**: SeniorPM 生成 → ReviewGate 审批 → 通过才进工程
- **如何**: PRD 深度化（M3：用户故事/验收标准）+ 审批门（已实现）
- **依据**: PRD 是"承诺"，必须人确认——企业敢签字的前提
- **优势**: 高风险节点人控 · 防止"AI 自说自话做错方向" · 可审计（审批记录）
- **缺点/代价**: 审批慢 · 用户不一定有时间细看（§5.9 审计报告缓解）
- **为什么这么弄（vs 无审批自动进）**: 无审批 = 失控，方向错了全错；PRD 门 = 关键节点治理（§6.3）

##### 节点 5：工程计划

- **拆解**: Architect → engineering.json / tasks.json / execution_plan.json
- **如何**: pipeline 规则（已实现）+ M3 LLM 深度化（带确定性校验兜底）
- **依据**: 计划先行，不边做边想；计划是执行的地图
- **优势**: 可预估 · 可拆分 · 可分配（AgentMatcher）
- **缺点/代价**: 规则计划偏模板 · LLM 计划可能不可执行（须确定性校验）
- **为什么这么弄**: 计划用 LLM 深化、用规则兜底——既深度又可执行

##### 节点 6：任务拆解（原子）

- **拆解**: 递归拆到原子（§3.7）；原子判定：单 Agent/单工具/可验证/≤10min
- **如何**: M3 递归引擎；当前 FeatureTaskGenerator 确定性（M1b）
- **依据**: Agent 只能执行原子任务（能力边界）——粗任务做不完 = "一步一个坑"
- **优势**: 提高成功率 · 每步可验证/可回滚 · 并行机会多
- **缺点/代价**: 任务多 = 管理开销 · 拆解本身要成本（LLM）
- **为什么这么弄（vs 粗粒度任务）**: 粗任务 Agent 一次做不完 → 失败/重做；原子 = 能力匹配，成功率优先

##### 节点 7：执行

- **拆解**: 原子任务 → Plan（LLMPlanner）→ 关键节点判定（§3.8）→ ExecutionLoop → patch → 验证
- **如何**: M1 repo_mode + DeveloperAgent + ExecutionLoop（已实现）
- **依据**: 执行不是黑盒——"计划→执行→验证→修复"循环
- **优势**: 可控 · 可追踪 · 失败可修（§17.13）· 成本可查
- **缺点/代价**: 单任务串行慢 · LLM 质量波动（evaluator 兜底）
- **为什么这么弄**: 每个原子任务先 Plan 再执行，关键节点卡口（审批/预算/质量）——不裸奔

##### 节点 8：证据 / 分级审批

- **拆解**: EvidenceBundle（diff+test+决策）→ ApprovalGate（爆炸半径分级）
- **如何**: M1a 已实现（low/medium/high → developer/tech_lead/compliance）
- **依据**: "企业敢签字" = 证据 + 审批；没有证据的黑盒 AI 企业不敢用
- **优势**: 可审计 · 可追溯 · 可重放（§5.6）· 分级省审批
- **缺点/代价**: 证据组装成本 · 审批可能成瓶颈（异步消息审批 §9.5 缓解）
- **为什么这么弄（vs 无证据直接应用）**: 无证据 = 黑盒 = 不敢签字；证据+分级 = 信任基础 + 差异化

##### 节点 9：交付（测试绿）

- **拆解**: patch 应用（sandbox）→ pytest 真实运行 → 代码落盘 → PR/交付
- **如何**: M1 sandbox + patch_filter + 真实 pytest（已实现）
- **依据**: "代码存在 ≠ 能力"——真实验证才算交付
- **优势**: 可演示 · 可信 · 失败可见（§5.6 回放）
- **缺点/代价**: 测试覆盖有限 · 真实环境验证依赖用户实测（§1.7 A 维度）
- **为什么这么弄**: 沙箱应用（原仓库零影响）+ 真实测试 → 交付可回滚、可复现

##### 节点 10：运维 / 变更回流

- **拆解**: 反馈 → ChangeProposal → 影响分析 → 审批 → PRD v2 + replan → 继续
- **如何**: M3 ChangeControl（propose→impact→approve→v+1→replan）
- **依据**: 需求是渐进明细的（Phase 17 反馈闭环）；变更要受控
- **优势**: 需求可演进 · 变更可审计 · 每版可追溯（资产 v+n）
- **缺点/代价**: 变更流程开销（合并/上限缓解）
- **为什么这么弄（vs 需求一次定死）**: 需求会变，一次定死 = 交付即过时；受控变更 = 可演进 + 可审计 + 渐进明细

## 十一、全部交互场景设计

### 11.1 交互场景总览

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              交互场景总览                                           │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景1: 任务启动与执行                                                      │   │
│  │  用户: "帮我修复这个 Bug"                                                   │   │
│  │  系统: 分析 → 拆解 → 执行 → 汇报                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景2: 进度查看                                                            │   │
│  │  用户: "现在到哪了？"                                                       │   │
│  │  系统: 显示当前进度、已完成任务、正在执行的任务                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景3: 审批与确认                                                          │   │
│  │  系统: "需要您批准修改 UserService.java"                                    │   │
│  │  用户: 批准/拒绝/修改                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景4: 审计查询                                                            │   │
│  │  用户: "看看这个任务花了多少钱" / "为什么选择了这个方案"                    │   │
│  │  系统: 显示成本明细 / 显示决策链                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景5: 干预与修正                                                          │   │
│  │  用户: "等一下，这个方向不对，换个方式"                                     │   │
│  │  系统: 暂停 → 重新规划 → 继续执行                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景6: 经验审查                                                            │   │
│  │  系统: "从刚才的任务中总结了一条经验，请审查"                               │   │
│  │  用户: 批准/拒绝/修改                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景7: 配置管理                                                            │   │
│  │  用户: "调整预算上限" / "添加 MCP 服务"                                     │   │
│  │  系统: 更新配置 → 确认生效                                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景8: 工厂管理                                                            │   │
│  │  用户: "创建一个数据分析工厂" / "查看所有工厂"                              │   │
│  │  系统: 实例化工厂 → 显示工厂列表                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景9: 系统诊断                                                            │   │
│  │  用户: "检查一下系统状态" / "为什么这么慢"                                  │   │
│  │  系统: 运行诊断 → 显示系统健康报告                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 场景10: 学习与改进                                                         │   │
│  │  用户: "看看有什么可改进的"                                                 │   │
│  │  系统: 分析历史任务 → 生成改进建议                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 11.2 详细交互流程

#### 场景1: 任务启动

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 交互流程: 任务启动                                                                 │
│                                                                                     │
│  [用户] 输入: "帮我修复登录接口的 NPE 异常"                                        │
│                                                                                     │
│  [系统] 正在分析...                                                                │
│  [系统] 识别任务类型: 诊断型 + 修改型                                              │
│  [系统] 评估复杂度: 中等 (需要 8-12 步)                                            │
│  [系统] 识别领域: 软件开发                                                          │
│                                                                                     │
│  [系统] 正在检索上下文...                                                          │
│  [系统] 从项目 RAG 找到: 登录模块代码、历史故障记录                                │
│  [系统] 从领域 RAG 找到: 常见 NPE 模式、修复最佳实践                              │
│                                                                                     │
│  [系统] 正在拆解任务...                                                            │
│  [系统] 生成 DAG:                                                                  │
│     T1: 获取错误日志和堆栈                                                         │
│     T2: 分析报错位置和调用链                                                       │
│     T3: 定位根因 (为什么 NPE)                                                     │
│     T4: 设计修复方案                                                               │
│     T5: 执行修复 (需审批)                                                         │
│     T6: 运行测试验证                                                               │
│     T7: 审查修复质量                                                               │
│     T8: 提交代码 (需审批)                                                         │
│                                                                                     │
│  [系统] 预估时间: 15-20 分钟                                                       │
│  [系统] 预估成本: $0.05-0.10                                                      │
│                                                                                     │
│  [系统] 是否继续？(y/n)                                                            │
│  [用户] y                                                                          │
│                                                                                     │
│  [系统] 开始执行...                                                                │
│  [系统] ▶ T1: 获取错误日志和堆栈 (Executor)                                       │
│  [系统]   → 读取 /var/log/app.log                                                  │
│  [系统]   → 找到 NPE 堆栈: UserService.login 第 45 行                             │
│  [系统]   ✅ T1 完成 (2s)                                                          │
│                                                                                     │
│  [系统] ▶ T2: 分析报错位置和调用链 (Executor)                                      │
│  [系统]   → 读取 UserService.java                                                  │
│  [系统]   → 分析调用链: Controller → Service → DAO                                │
│  [系统]   ✅ T2 完成 (3s)                                                          │
│                                                                                     │
│  [系统] ▶ T3: 定位根因 (Debugger)                                                  │
│  [系统]   → 发现 UserService 的 userRepository 未初始化                            │
│  [系统]   → 根因: @Autowired 注解缺失                                              │
│  [系统]   ✅ T3 完成 (5s)                                                          │
│                                                                                     │
│  [系统] ▶ T4: 设计修复方案 (Planner)                                               │
│  [系统]   → 方案A: 添加 @Autowired (推荐, 最小改动)                                │
│  [系统]   → 方案B: 重构初始化逻辑 (更彻底, 风险更高)                               ││  [系统]   ✅ T4 完成 (4s)                                                          │
│                                                                                     │
│  [系统] ▶ T5: 执行修复 (需审批)                                                    │
│  [系统]   方案A: 在 UserService.java 第 28 行添加 @Autowired                       │
│  [系统]   ┌─────────────────────────────────────────────────────────────────┐      │
│  [系统]   │ 变更预览:                                                       │      │
│  [系统]   │   - @Service                                                     │      │
│  [系统]   │   + @Service                                                     │      │
│  [系统]   │   + @Autowired                                                  │      │
│  [系统]   │   private UserRepository userRepository;                         │      │
│  [系统]   └─────────────────────────────────────────────────────────────────┘      │
│  [系统]   批准此修改？(y/n/edit)                                                  │
│  [用户] y                                                                          │
│                                                                                     │
│  [系统]   → 写入 UserService.java                                                  │
│  [系统]   ✅ T5 完成 (2s)                                                          │
│  [系统] ▶ T6: 运行测试验证 (Executor)                                              │
│  [系统]   → 运行 mvn test                                                         │
│  [系统]   → 测试通过: 234/234                                                    │
│  [系统]   ✅ T6 完成 (10s)                                                         │
│                                                                                     │
│  [系统] ▶ T7: 审查修复质量 (Reviewer)                                              │
│  [系统]   → 完整性: 100%                                                          │
│  [系统]   → 正确性: 100%                                                          │
│  [系统]   → 质量: 95%                                                             │
│  [系统]   → 综合评分: 95/100, 通过                                               │
│  [系统]   ✅ T7 完成 (5s)                                                          │
│                                                                                     │
│  [系统] ▶ T8: 提交代码 (需审批)                                                    │
│  [系统]   Commit: fix: 修复 UserService NPE 异常                                   │
│  [系统]   提交此修改？(y/n)                                                        │
│  [用户] y                                                                          │
│  [系统]   → 创建 PR #123                                                          │
│  [系统]   ✅ T8 完成 (3s)                                                          │
│                                                                                     │
│  [系统] ✅ 任务完成!                                                               │
│  [系统] 总耗时: 14分32秒                                                           │
│  [系统] 总成本: $0.072                                                            │
│  [系统] 修改文件: 1 个                                                             │
│  [系统] 测试: 234 通过, 0 失败                                                    │
│                                                                                     │
│  [系统] 是否查看详细审计？(y/n)                                                    │
│  [用户] n                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 场景2: 进度查看

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 交互流程: 进度查看                                                                 │
│                                                                                     │
│  [用户] 输入: "现在到哪了？"  (或 status / progress)                                │
│                                                                                     │
│  [系统] 正在汇总执行状态 (execution_state.json)...                                 │
│  [系统] ┌───────────────────────────────────────────────────────────────────┐      │
│  [系统] │ 任务看板: 总进度 62%  (5/8 完成)                                  │      │
│  [系统] │   ✅ T1 获取日志      (2s)   ✅ T2 分析调用链  (3s)                │      │
│  [系统] │   ✅ T3 定位根因      (5s)   ✅ T4 设计修复方案 (4s)               │      │
│  [系统] │   ▶ T5 执行修复      (运行中 45% — 等待审批)                      │      │
│  [系统] │   ⏳ T6 运行测试      (依赖 T5)   ⏳ T7 审查质量  (依赖 T6)        │      │
│  [系统] │   ⏳ T8 提交代码      (依赖 T7)                                    │      │
│  [系统] └───────────────────────────────────────────────────────────────────┘      │
│                                                                                     │
│  [系统] 当前卡点: T5 需要您的审批 (变更预览已就绪)                                  │
│  [系统] 下一步计划 (what's next): T5 通过后 → T6 测试 → T7 审查 → T8 提交          │
│  [系统] 成本水位: $0.045 / 预算 $0.10  (45%)                                      │
│                                                                                     │
│  [用户] progress                                                                    │
│  [系统] 详细进度:                                                                    │
│  [系统]   T1 ✅ 证据: log 片段 · 耗时 2s · 成本 $0.003                             │
│  [系统]   T5 ▶ 状态 running · 等待审批 · 已用 0/2 次重试                          │
│  [系统]   T6 ⏳ 状态 blocked (依赖 T5 未完成)                                      │
│                                                                                     │
│  [系统] 说明: 节点状态机 pending→ready→running→success/failed (§3.5);              │
│  [系统]        阻塞 = 控制边 (depends_on) 未满足 — 依赖驱动调度 (§3.9)。           │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 场景3: 审批与确认

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 交互流程: 审批与确认 (ApprovalGate 分级审批)                                        │
│                                                                                     │
│  [系统] 主动推送: "需要您批准以下变更"                                               │
│  [系统] ┌── 变更预览 ──────────────────────────────────────────────────────┐      │
│  [系统] │  文件: UserService.java 第 28 行                                    │      │
│  [系统] │  - @Service                                                         │      │
│  [系统] │  + @Service                                                         │      │
│  [系统] │  + @Autowired                                                       │      │
│  [系统] │  风险等级: medium (单文件局部修改) → 需 tech_lead 级批准 (§6.3.6)   │      │
│  [系统] └────────────────────────────────────────────────────────────────────┘      │
│  [系统] 请选择: approve / reject / edit                                             │
│                                                                                     │
│  ── 分支 A: 批准 ──                                                               │
│  [用户] approve                                                                     │
│  [系统] → 应用 patch → 运行验证 → 证据包落审计 (approval_approved 事件)          │
│  [系统] → 放行下游: T6 测试 → T7 审查 → T8 提交                                    │
│                                                                                     │
│  ── 分支 B: 拒绝 ──                                                               │
│  [用户] reject                                                                      │
│  [系统] 请输入拒绝原因 (将写入审计 + 回写决策记忆):                                │
│  [用户] 不想动私有字段注入，改用构造器注入                                          │
│  [系统] → 挂起 T5 → 重规划 (S10-060 动态 DAG: 替换修复方案节点)                  │
│  [系统] → 新方案: 构造器注入 → 重新生成预览 → 再次请求审批                        │
│                                                                                     │
│  ── 分支 C: 修改 ──                                                               │
│  [用户] edit                                                                        │
│  [系统] 请直接修改变更内容 (diff 模式):                                            │
│  [用户] (编辑 diff)                                                                │
│  [系统] → 重新生成预览 → 再次请求审批                                              │
│                                                                                     │
│  [系统] 全部通过后: 证据包 (diff+test+决策链) 存档 → 审计事件链完整 (§5.2)。       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 场景4: 审计查询

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 交互流程: 审计查询 (成本 / 决策链 / 轨迹回放)                                        │
│                                                                                     │
│  [用户] 输入: "看看这个任务花了多少钱"  (或 cost)                                   │
│  [系统] 成本明细 (按任务, §5.4):                                                     │
│  [系统]   T1 $0.003 · T2 $0.004 · T3 $0.007 · T4 $0.005                           │
│  [系统]   T5 $0.002 (审批暂停) · T6 $0.010 · T7 $0.006 · T8 $0.003                │
│  [系统]   合计: $0.072 · 预算 $0.10 · 水位 72% (BudgetEnforcer 未告警)            │
│                                                                                     │
│  [用户] 输入: "为什么选择了这个方案"  (或 why)                                     │
│  [系统] 决策链 (decision 事件, §5.2):                                               │
│  [系统]   T4 决策: 方案A 添加 @Autowired                                            │
│  [系统]   依据: 最小改动 · 符合项目依赖注入规范 · 命中历史经验 2 条 (评分 0.92)    │
│  [系统]   否决: 方案B 重构初始化逻辑 (风险高 · 影响面大)                           │
│  [系统]   决策人: Planner (agt-it-planner-1) · 证据: diff + 测试                   │
│                                                                                     │
│  [用户] 输入: trace T5                                                             │
│  [系统] 执行轨迹回放 (§5.6):                                                        │
│  [系统]   10:00:12  T1 ✅ 读取 /var/log/app.log                                    │
│  [系统]   10:00:20  T5 ⏸ 审批等待 (ApprovalGate)                                   │
│  [系统]   10:02:01  T5 ✅ 批准 (approval_approved) · 应用 patch                    │
│  [系统]   10:02:11  T6 ✅ mvn test 234/234                                         │
│  [系统]   → 可导出完整审计报告 (§5.9) 供追溯/合规。                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 场景5: 干预与修正

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 交互流程: 干预与修正 (暂停 → 重规划 → 继续)                                          │
│                                                                                     │
│  [用户] 输入: "等一下，这个方向不对，换个方式"  (或 pause)                          │
│  [系统] → 暂停当前任务 (savepoint: 执行状态 + 已产出证据)                          │
│  [系统] 当前进度: T4 刚完成 · T5-T8 未开始                                          │
│                                                                                     │
│  [用户] 换个方向: 不要加注解，改用构造器注入，顺便把日志也一起修                    │
│  [系统] → 重规划 (S10-060 动态 DAG):                                               │
│  [系统]   修改 T5: 修复方案 → 构造器注入                                            │
│  [系统]   新增 T5b: 补充日志改造 (依赖 T5)                                          │
│  [系统]   T6-T8 保持不变 (依赖自动重算)                                            │
│  [系统]   ✓ 无环检测通过 (cycle_detect)                                            │
│  [系统] ┌── 计划变更预览 ──────────────────────────────────────────────────┐      │
│  [系统] │  改 T5 · 增 T5b · 预估 +3 分钟 · +$0.012                           │      │
│  [系统] └────────────────────────────────────────────────────────────────────┘      │
│  [系统] 确认重规划？(y/n)                                                          │
│  [用户] y                                                                          │
│  [系统] → resume → 继续执行 T5 (新方案)                                            │
│                                                                                     │
│  [系统] 其他干预命令: stop (终止并保留证据) · retry (重试失败节点)。               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 11.3 对话交互指令集

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          对话交互指令集                                             │
│                                                                                     │
│  分类                  指令                       说明                              │
│  ────────────────────────────────────────────────────────────────────────────────  │
│  任务控制              run <目标>                启动新任务                        │
│                        pause                     暂停当前任务                      │
│                        resume                    恢复暂停的任务                    │
│                        stop                      终止当前任务                      │
│                        retry                     重试失败的任务                    │
│                                                                                     │
│  进度查询              status                    查看总体进度                      │
│                        progress                  查看详细进度                      │
│                        what's next               查看下一步计划                    │
│                                                                                     │
│  审计查询              audit                     查看审计日志                      │
│                        cost                      查看成本明细                      │
│                        why                       查看决策原因                      │
│                        trace <task>              查看任务执行轨迹                  │
│                                                                                     │
│  审批操作              approve                   批准当前审批                      │
│                        reject                    拒绝当前审批                      │
│                        edit                      修改审批内容                      │
│                                                                                     │
│  经验管理              learnings                 查看经验列表                      │
│                        review <id>               审查某条经验                      │
│                        apply <id>                手动应用某条经验                  │
│                                                                                     │
│  配置管理              config                    查看配置                          │
│                        config set <key> <value>  修改配置                          │
│                        budget                    查看预算使用情况                  │
│                                                                                     │
│  工厂管理              factories                 查看工厂列表                      │
│                        use <factory>             切换工厂                          │
│                        create <factory>          创建新工厂                        │
│                                                                                     │
│  系统诊断              doctor                    系统诊断                          │
│                        health                    健康检查                          │
│                        logs                      查看日志                          │
│                                                                                     │
│  帮助                 help                      显示帮助                          │
│                        help <command>           查看命令详情                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 11.4 用户界面层次

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          用户界面层次                                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 界面层次1: CLI (命令行)                                                    │   │
│  │  适用: 高级用户、自动化脚本                                                │   │
│  │  交互方式: 命令 + 参数                                                     │   │
│  │  示例: factory run -p project -o "目标"                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 界面层次2: TUI (终端交互界面)                                              │   │
│  │  适用: 日常使用、查看进度                                                  │   │
│  │  交互方式: 键盘导航 + 命令输入                                             │   │
│  │  元素: 进度条、任务列表、日志面板、成本显示                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 界面层次3: Web UI (未来)                                                   │   │
│  │  适用: 团队协作、可视化管理                                                │   │
│  │  交互方式: 点击 + 表单输入                                                  │   │
│  │  元素: 仪表盘、任务可视化、审计查询、配置管理                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 界面层次4: API (未来)                                                      │   │
│  │  适用: 集成到其他系统、自动化流程                                          │   │
│  │  交互方式: RESTful API + WebSocket                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 11.5 交互场景实现对照（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| CLI 交互 | `session/InteractiveSession`（意图/发现/命令/会话记忆） | ✅ |
| 对话指令集 | `/project /help /status` + 自然语言意图（多轮修复后） | ✅ |
| Web（React 壳） | `factory-console/web/`（React + FastAPI） | 🚧 |
| IDE 插件 / 自主沙箱 | 设计（M7 入口扩展） | 📐 |

**完成度**：CLI 交互完整（✅）；Web 壳待打通（🚧）；IDE/自主为设计（📐）。

### 11.6 命令体系总纲（统一命名规范 + 多端/运维/资源命令不混乱）★

> 2026-08-24 补充（Founder: 后面还有很多运维命令 service list / llm list / todo list 等,
> 命令会越来越多, 必须体系化）: 命令 = `factory <域> <动词>` 统一结构 +
> 会话 `/命令` 快捷入口; 新增命令 = 新域 + 标准动词, 有规律可循。

**命令结构（统一）**

```
factory <域> <动词> [参数]      # 运维/资源/数据命令（长命令, 脚本友好）
/命令 [参数]                    # 会话快捷入口（交互, 少打字）
自然语言                        # LLM 理解意图 → 自动映射到命令（v1.1.20）
```

**域分类（5 类, 每类一组命令）**

| 域类 | 域 | 说明 |
|---|---|---|
| **系统** | init config doctor start stop status version | 环境/配置/诊断/启停 |
| **资源** | service llm agent skill tool project | 服务/LLM/员工/技能/工具/项目 清单与状态 |
| **数据** | todo backlog evidence audit memory knowledge | 任务/积压/证据/审计/记忆/知识 查询 |
| **执行** | run repo workload exec | 跑任务/存量仓库/积压清道夫/执行记录 |
| **展示** | board dashboard | 监控面板（todolist/依赖图/生命线） |

**域分类（6 类, 含组织域 — 2026-08-24 补充）**

| 域类 | 域 | 说明 |
|---|---|---|
| **系统** | init config doctor start stop status version | 环境/配置/诊断/启停 |
| **资源** | service llm agent skill tool project | 服务/LLM/员工/技能/工具/项目 清单与状态 |
| **数据** | todo backlog evidence audit memory knowledge | 任务/积压/证据/审计/记忆/知识 查询 |
| **执行** | run repo workload exec | 跑任务/存量仓库/积压清道夫/执行记录 |
| **组织** | company department industry(factory) | 公司/部门/行业工厂（§1.4.5 层级） |
| **展示** | board dashboard | 监控面板（todolist/依赖图/生命线） |

```
组织域命令示例（域 + 动词 + --company 作用域）:
  factory company list / create --name X
  factory department list --company C-1 / create --company C-1 --name X
  factory industry list / create --template software_dev
  factory project list --company C-1        # 资源命令带组织作用域
```

**资源隔离规则（组织层级 × 资源可见性 — "烂事"的核心, 必须设计）**

| 资源 | 隔离级别 | 规则 |
|---|---|---|
| 公司级（agent/project/knowledge/audit/experience） | **公司隔离** | A 公司看不见 B 公司（company_id 隔离, §7.2.2） |
| 部门级（project/employee） | 部门可选 | 部门间可选隔离或公司内共享（department_id 可选） |
| 行业级（skill/workflow/knowledge/template） | 行业隔离 | 行业工厂专属（FactorySpec 隔离） |
| 全局（system config/内置 Skill） | 共享 | 所有组织可见 |

```
命令作用域规则: 组织域命令默认带 --company/--factory 作用域;
资源命令(list/show)可加 --company/--department 过滤（缺省 = 当前上下文/全部）
隔离实现: company_id/department_id/factory_id 字段 + 查询过滤（§7.2.2 守则1）
```

**动词规范（统一动作词）**

```
list（枚举）· show（详情）· create（创建）· start/stop（启停）·
status（状态）· config（配置）· test（测试）· export（导出）· delete（删除）
```

**命令总览（一条命令看全部, 解决"记不住/不知道有哪"）**

```
factory help          → 按域分类列出全部命令 + 示例
factory <域> --help   → 该域所有动词
```

**新增命令规则（零混乱）**

```
1. 归属一个域（service/llm/todo/...）→ 域下加动词
2. 动词用标准集（list/show/create/...）→ 不发明新动词
3. 会话快捷 /命令（可选, 高频操作才加）→ 映射到长命令
4. 自然语言 → LLM 意图映射（v1.1.20 已有）→ 用户不用记命令
```

**多端访问（§11.6 衔接）**

```
启动: factory start（统一）→ 打印所有端地址（Web/移动/Pad 响应式同一地址）
访问: 浏览器/手机打开地址 · 会话 factory → /命令
内部: service list 等是"诊断命令"（开发/运维用）, 用户日常不需要
```

**结论**: 命令体系 = **域 × 动词 矩阵 + 总览命令 + LLM 意图映射**——
命令再多也有规律（service list / llm list / todo list 同构），
用户不记命令（自然语言 + help 总览），新增不混乱（域+标准动词）。

## 十二、演进路线图

> 2026-08-22 更新: 演进路线对齐 [docs/MASTER-PLAN-2026-08.md](../../docs/MASTER-PLAN-2026-08.md)（M1-M7 里程碑 + 三部门循环）；旧 v0.x Phase 规划已废弃。

### 12.1 当前路线（里程碑 → 版本）

| 里程碑 | 版本 | 内容 | 状态 |
|---|---|---|---|
| M1 内核切片 | v1.1.5 | repo 模式 + 工具发现 + 真 MCP 客户端 | ✅ 已交付 |
| M1a 证据包 + 分级审批 | v1.1.6 | EvidenceBundle + ApprovalGate 分级 | ✅ 已交付 |
| M1b 积压清道夫 | v1.1.7 | BacklogSweeper（分诊→修复→证据→审批→报告） | ✅ 已交付 |
| 三部门循环 | v1.1.8 | Claude 用户价值评估 · M2 准备 | 🚧 进行中 |
| M2 员工内核 | v1.1.9 | AgentEntity + AgentRegistry + 专家装配器 + HandoffBus | ✅ 已交付 |
| 专家真干活 (S10-088) | v1.1.10 | 生产路径接真实 LLM + 交接消费上一产出 + PRD 消费专家资产 + build_team 落盘 | ✅ 已交付 |
| M3 IT 工厂深度 | v1.2.0 | PRD 深度化 + 需求变更回流 + 审批门 + repo 深度 | 📐 待做 |
| M4 自我提升闭环 | v1.2.1 | 经验→画像→决策引用 + 评价回写 + 护栏 | 📐 待做 |
| M5 真实 E2E + 模板 | v1.2.2 | 全链路演示 + FactorySpec 自举 + Web 入口 | 📐 待做 |
| M6 第二行业 | v1.2.x | 同一底座复制（数据分析/办公自动化） | 📐 待做 |
| M7 入口扩展 | v1.3.x | IDE 插件 + 自主沙箱 | 📐 待做 |

### 12.2 长期愿景（不承诺时间）

```
近期(≤6月): IT 工厂做透 (M2-M4)
中期(1-2年): 行业复制 + 知识图谱简化版 + 安全合规框架 (M5-M6)
长期: AI 时代的 SAP / 50+ 消息平台 / 国产化 ERP 认证 / "每人一家 AI 公司"
```

### 12.3 成功标准（量化，见 §1.5.6）

- 每个里程碑: 1 个真实用户场景跑通（演示/审计/回滚）
- 技术: tests 全绿（基线 11856+）· 修复成功率 · 失败恢复率 · 每任务成本可查
- 产品: 新用户首次完成任务时长 · 证据包让用户"看完就敢批"
- 商业: 付费转化 · 续费 · ARR · 单活边际成本 < 人工成本

## 十三、完整术语表

| 术语 | 英文 | 定义 |
|---|---|---|
| **Agent** | Agent | 具有特定角色和能力的 AI 执行单元 |
| **DAG** | Directed Acyclic Graph | 有向无环图，用于表示任务依赖关系 |
| **任务树** | Task Tree | 只表达父子层级的拆解结构（1 维，§3.7） |
| **任务图** | Task Graph | 任务+关系的统称；本项目 = 拆解树 + DAG 依赖边（带层级 DAG，§4.12.10） |
| **工作流** | Workflow | 可复用的流程模板（领域专属步骤序列，如 需求→设计→编码→测试→部署 的 DAG，§7.2） |
| **执行计划** | Plan | 任务执行前的决策层：目标/步骤/工具/验证/成本/风险 + 整链关键路径与调度（§3.8/§3.9） |
| **ReAct** | Reasoning + Acting | Agent 的思考-行动-观察-反思循环 |
| **RAG** | Retrieval-Augmented Generation | 检索增强生成，三级体系 |
| **MCP** | Model Context Protocol | 模型上下文协议，外部工具接入标准 |
| **Skill** | Skill | 可复用的原子能力封装 |
| **Hermes** | Hermes | 多步骤任务编排工具 |
| **OpenClaw** | OpenClaw | 浏览器/桌面自动化工具 |
| **工厂** | Factory | 面向特定行业的 AI 组织配置包 |
| **领域智能** | Domain Intelligence | Skill + MCP + Knowledge + Workflow + Evaluation + Learning |
| **工作记忆** | Working Memory | Agent 间共享的上下文存储 |
| **治理** | Governance | 成本、权限、合规、风险、安全的管控体系 |
| **审计** | Audit | 全链路事件记录和追溯 |
| **可观测** | Observability | 日志 + 指标 + 追踪 |
| **经验** | Experience | 从任务中提炼的可复用知识 |
| **复盘** | Retrospective | 任务完成后的总结和反思 |
| **编排** | Orchestration | 多 Agent 的任务分配和协作管理 |
| **熔断** | Circuit Breaker | 成本/错误超限时的自动保护 |
| **降级** | Degradation | 资源不足时的能力降级 |
| **证据包** | EvidenceBundle | AI 变更的可审计证据（diff+测试+决策+变更文件） |
| **积压清道夫** | BacklogSweeper | 自动处理存量 issue 队列（分诊→修复→证据→审批→报告） |
| **分级审批** | Tiered Approval | 按爆炸半径 low/medium/high 分级，高风险必须人工批准 |
| **专家装配器** | ExpertFactory | Skill+Knowledge+Workflow → 装配领域专家 Agent |
| **专家实体** | AgentEntity | 一个专家的统一身份（role/provider/skills/knowledge/eval/memory） |
| **交接总线** | HandoffBus | 多 Agent 间产出交接/共识/冲突处理 |
| **工厂模板** | FactorySpec | 行业工厂的声明式规格（employees/capabilities/workflows/governance/assets） |
| **消息渠道** | Channel | 消息平台适配器（WhatsApp/Telegram/Slack…） |
| **热插拔** | Hot-Plug | 模块可独立替换/独立演进（对标 SAP 可组合架构） |
| **Clean Core** | Clean Core | 核心保持标准，扩展走外围（SAP 借鉴） |
| **五维自我进化** | Self-Evolution | 自我学习/监控/完善/发现/修复 |
| **数据主权** | Data Sovereignty | 数据本地部署与控制权（企业级信任基石） |
| **领域智能** | Domain Intelligence | Skill+MCP+Knowledge+Workflow+Evaluation+Learning=领域智能产业 |
| **AI Company OS** | AI Organization OS | 创建/管理/运行/进化 AI 公司的操作系统 |
| **造专家的工厂** | Expert Factory | 核心定位：产出可复用的领域专家，而非单一专家 |
| **审批** | Approval | 高风险操作的用户确认流程 |


## 附录: 完整架构图索引

| 图 | 位置 |
|---|---|
| 核心能力全景图 | §1.2 |
| 任务拆解全流程 | §3.2 |
| 拆解模板 (诊断/构建/修改/探索) | §3.3 |
| Agent 角色体系 | §4.1 |
| 6 个 Agent 详细规格 | §4.2 |
| Agent 协作模式 (6 种) | §4.3 |
| Agent 通信机制 | §4.4 |
| Agent 生命周期 | §4.5 |
| 审计架构 | §5.1 |
| 可观测性设计 (3 支柱) | §5.3 |
| 用户审计视图 (3 种) | §5.4 |
| 治理全景 | §6.1 |
| 成本治理详细设计 | §6.2 |
| 权限与审批模型 | §6.3 |
| 学习架构 | §7.1 |
| 学习可控性机制 (6 种) | §7.3 |
| RAG 架构 | §8.1 |
| RAG 检索流程 | §8.1 |
| 工具生态架构 | §9.1 |
| 工具调用完整流程 | §9.4 |
| 工厂定义 | §10.1 |
| 各行业工厂场景 | §10.2 |
| 交互场景总览 | §11.1 |
| 详细交互流程 | §11.2 |
| 对话交互指令集 | §11.3 |
| 用户界面层次 | §11.4 |
| 演进路线图 | §12.1 |

---

*文档结束*

---

这份文档覆盖了 **复杂任务拆解、多 Agent 编排与调用、审计、治理、学习、RAG、工具生态、行业工厂、交互场景** 的全部详细设计，每个部分都有：
- 架构图
- 流程图
- 详细规格
- 数据结构
- 交互示例
- 场景描述

还有需要补充的方向吗？

---

## 十四、旧版保留章节（不丢失）

> 以下为旧版（v2 结构）独有内容，终极版重构时保留，避免丢失。

#### 十三.1 战略愿景与行业覆盖（旧版 §二）

#### 二、战略愿景与行业覆盖

#### 2.1 验证路径

```
Phase 0-1: 引擎打磨（当前）
    └── 软件开发全生命周期作为验证场
         ├── 需求分析 → 设计 → 编码 → 测试 → 部署
         └── 验证能力：拆解 · 调度 · 推理 · 工具 · 反馈

Phase 2: 横向迁移
    └── 行业工厂化
         ├── 运维工厂（监控/告警/故障修复）
         ├── 电商运营工厂（选品/投放/客服）
         ├── 自媒体工厂（选题/脚本/多平台发布）
         ├── 数据分析工厂（ETL/清洗/报表）
         └── 办公自动化工厂（会议/邮件/审批）

Phase 3: 生态化
    └── 工厂模板市场 + 行业智能包分发
```

#### 2.2 行业工厂全景图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                             行业工厂全景图                                          │
│                                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────────┐ │
│  │   IT 工厂           │  │   运维工厂           │  │   电商运营工厂               │ │
│  │                     │  │                     │  │                              │ │
│  │ • 代码生成/重构     │  │ • 监控异常检测      │  │ • 选品分析                  │ │
│  │ • 架构设计          │  │ • 故障根因定位      │  │ • 广告投放优化              │ │
│  │ • 代码审查          │  │ • 自动修复          │  │ • 智能客服                  │ │
│  │ • 技术债务管理      │  │ • 容量规划          │  │ • 竞品追踪                  │ │
│  │ • 依赖升级          │  │ • 告警降噪          │  │ • 库存预测                  │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────────────┘ │
│                                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────────┐ │
│  │   自媒体工厂         │  │   数据分析工厂       │  │   办公自动化工厂             │ │
│  │                     │  │                     │  │                              │ │
│  │ • 选题策划          │  │ • 数据清洗/ETL     │  │ • 会议纪要与行动跟踪        │ │
│  │ • 脚本生成          │  │ • 报表自动生成      │  │ • 邮件分类与自动回复        │ │
│  │ • 视频/图文制作     │  │ • 异常检测          │  │ • 审批流自动化              │ │
│  │ • 多平台适配发布    │  │ • 趋势预测          │  │ • 文档智能整理              │ │
│  │ • 数据分析优化      │  │ • A/B测试分析      │  │ • 日程智能调度              │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────────────┘ │
│                                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────────┐ │
│  │   安全工厂           │  │   财务工厂           │  │   HR 工厂                    │ │
│  │                     │  │                     │  │                              │ │
│  │ • 漏洞扫描分析      │  │ • 账务自动核对      │  │ • 简历智能筛选              │ │
│  │ • 安全事件响应      │  │ • 财报生成          │  │ • 面试辅助                  │ │
│  │ • 合规审计          │  │ • 预算分析优化      │  │ • 员工培训                  │ │
│  │ • 渗透测试辅助      │  │ • 风险预警          │  │ • 绩效分析                  │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.3 每个工厂的构成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        行业工厂 = 六大要素                                  │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
│  │   Skill     │  │    MCP      │  │  Knowledge  │  │  Workflow   │      │
│  │  原子能力    │  │  外部工具   │  │  行业知识库  │  │  工作流模板  │      │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐                                         │
│  │ Evaluation  │  │  Learning   │                                         │
│  │  评价标准    │  │  经验积累   │                                         │
│  └─────────────┘  └─────────────┘                                         │
│                                                                             │
│  Skill + MCP + Knowledge + Workflow + Evaluation + Learning                │
│                              = 领域智能产业                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```



#### 十三.2 领域智能产业架构（旧版 §七）

#### 七、领域智能产业架构

#### 7.1 领域智能定义

> **Skill + MCP + Knowledge + Workflow + Evaluation + Learning = 领域智能产业**

#### 7.2 六大要素详解

| 要素 | 说明 | 在软件开发工厂的体现 |
|---|---|---|
| **Skill** | 可调用的原子能力 | `analyze_code`, `generate_test`, `refactor`, `deploy` |
| **MCP** | 外部工具/服务连接器 | GitHub, Jira, Docker, Kubernetes, AWS |
| **Knowledge** | 行业知识库 | 设计模式、架构最佳实践、编码规范 |
| **Workflow** | 领域专属工作流模板 | 需求→设计→编码→测试→部署 的 DAG |
| **Evaluation** | 领域专属评价标准 | 代码质量评分、测试覆盖率、性能基准 |
| **Learning** | 领域经验累积机制 | 该领域的踩坑记录、最优解、反模式 |

#### 7.3 工厂模板结构

```python
#### 行业工厂模板定义
{
    "factory_id": "software_dev_v1",
    "name": "软件开发工厂",
    "version": "1.0.0",
    
    # 1. Skill 定义
    "skills": [
        {
            "name": "analyze_code",
            "description": "分析代码质量、复杂度、依赖",
            "input_schema": {...},
            "output_schema": {...},
        },
        # ... 更多 Skill
    ],
    
    # 2. MCP 配置
    "mcp_servers": [
        {"name": "github", "url": "mcp://github.com"},
        {"name": "docker", "url": "mcp://docker.local"},
    ],
    
    # 3. 知识库
    "knowledge_base": {
        "type": "vector_db",
        "collections": [
            "design_patterns",
            "architecture_best_practices",
            "code_style_guides",
        ]
    },
    
    # 4. 工作流模板
    "workflow_templates": [
        {
            "name": "bug_fix_workflow",
            "tasks": ["T1:诊断", "T2:定位", "T3:修复", "T4:验证", "T5:提交"],
            "dependencies": {"T1": [], "T2": ["T1"], ...}
        }
    ],
    
    # 5. 评价标准
    "evaluation": {
        "code_quality": {"metrics": ["complexity", "coverage", "duplication"]},
        "performance": {"metrics": ["latency", "throughput", "error_rate"]},
    },
    
    # 6. 经验库
    "experience_store": {
        "success_patterns": [],
        "failure_lessons": [],
        "domain_knowledge": [],
    }
}
```

#### 7.4 工厂实例化流程

```
用户选择行业工厂模板
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 1: 模板加载                                                           │
│   - 加载该工厂的 Skill/MCP/Knowledge/Workflow/Evaluation/Learning 配置    │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 2: 用户定制                                                           │
│   - 挂载项目级 RAG（代码仓库、文档）                                       │
│   - 配置 MCP 连接（GitHub Token、K8s 等）                                  │
│   - 调整评价标准阈值                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 3: 工厂启动                                                           │
│   - 初始化 Agent 团队（按角色）                                            │
│   - 加载知识库                                                             │
│   - 准备就绪，等待用户目标输入                                             │
└─────────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step 4: 持续进化                                                           │
│   - 任务执行 → 复盘 → 经验积累                                            │
│   - 工厂越用越聪明                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```



#### 十三.3 与现有生态的对比与定位（旧版 §十）

#### 十、与现有生态的对比与定位

#### 10.1 全景对比

| 对比维度 | LangChain | LangGraph | AutoGen | Devin | **AI Software Factory** |
|---|---|---|---|---|---|
| **定位** | Agent 构建框架 | Agent 工作流编排 | 多 Agent 协作框架 | AI 软件工程师 | **AI 组织管理系统** |
| **用户** | 开发者 | 开发者 | 开发者 | 开发者 | **任何人** |
| **粒度** | 单个 Agent | 多 Agent 工作流 | 多 Agent 对话 | 单 Agent | **多 Agent + 多任务 + 多行业** |
| **记忆** | 无 | 会话内 | 会话内 | 会话内 | **跨任务 + 跨项目 + 可控** |
| **治理** | 无 | 无 | 基础 | 无 | **审计 · 预算 · 权限 · 可解释** |
| **学习** | 无 | 无 | 无 | 无 | **经验积累 + 人工审查** |
| **行业** | 通用（需开发） | 通用（需开发） | 通用（需开发） | 软件开发 | **预置行业工厂 + 可扩展** |
| **工具生态** | 丰富 | 丰富 | 丰富 | 有限 | **多生态集成（MCP/Skill/Hermes/OpenClaw）** |
| **成本管控** | 无 | 无 | 无 | 无 | **预算 + 熔断 + 优化** |

#### 10.2 差异化定位

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          差异化定位                                        │
│                                                                             │
│  LangChain/LangGraph 专注于 "怎么造 Agent 和编排工作流"                   │
│  AutoGen 专注于 "怎么让 Agent 之间对话协作"                               │
│  Devin 专注于 "用 AI 做软件开发"                                          │
│                                                                             │
│  AI Software Factory 专注于 "怎么开一家 AI 公司"                          │
│    ├── 不是造单个 Agent，而是管理 Agent 组织                              │
│    ├── 不是做单个软件，而是覆盖全行业                                     │
│    ├── 不是一次性执行，而是持续学习进化                                   │
│    └── 不是开发者工具，而是人人可用的操作系统                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 10.3 关键原则重申

> **任何外部工具都不能成为 AI Factory 完成任务的必要条件。**

| 含义 | 体现 |
|---|---|
| **工具可替换** | 不绑死 MCP/Skill/Hermes/OpenClaw，缺了照样工作 |
| **自包含核心** | 引擎核心不依赖任何第三方服务（LLM API 是动力源） |
| **工具是插件** | 所有工具都是可插拔的"外设"，不是"内脏" |
| **鲁棒性** | 某个工具挂了，引擎能自动换其他方案，不会整体瘫痪 |



#### 十三.4 旧版附录

#### 附录

#### A. 术语表
> 旧版归档（2026-08-23 标注）：现行以 **§十三 完整术语表** 为准，本节保留历史不更新。

| 术语 | 定义 |
|---|---|
| **Agent** | 具有特定角色和能力的 AI 执行单元 |
| **DAG** | 有向无环图，用于表示任务依赖关系 |
| **ReAct** | Reasoning + Acting，Agent 的思考-行动循环模式 |
| **RAG** | Retrieval-Augmented Generation，检索增强生成 |
| **MCP** | Model Context Protocol，模型上下文协议 |
| **Skill** | 可复用的原子能力封装 |
| **工厂** | 面向特定行业的 AI 组织配置包 |
| **领域智能** | Skill + MCP + Knowledge + Workflow + Evaluation + Learning |

#### B. 架构图索引
> 旧版归档（2026-08-23 标注）：现行以 **附录: 完整架构图索引** 为准（编号已同步 21 章），本节保留历史不更新。

| 图 | 位置 |
|---|---|
| 四层架构图 | §2.1 |
| 行业工厂全景图 | §2.2 |
| RAG 三级体系 | §3.2 |
| ReAct 循环细化 | §3.5 |
| 失败恢复策略树 | §3.6 |
| 学习层次金字塔 | §3.9 |
| 多 Agent 协作架构 | §4.1 |
| 治理架构 | §5.1 |
| 学习循环 | §6.1 |
| 工具生态架构 | §8.1 |

---

*文档结束*

---

这份文档是否达到了你期望的「思路、方向、功能、全貌」的完整度？还需要补充哪些方向？


---

## 十五、竞品深度对比分析

> 2026-08-21 补充: 系统梳理 2026 年 AI 编程与 Agent 领域核心竞品 (Claude Code / Codex / Cursor / DeepSeek Harness / OpenClaw / Hermes / pi-agent / FactoryKit / Devin)。


> 知己知彼，百战不殆。本文系统梳理2026年AI编程与Agent领域的核心竞品，分析其优势、劣势，以及AI Factory可以从中吸取什么。

---

### 一、市场全景：2026年的Agent生态

#### 1.1 市场格局概览

2026年的AI编程工具市场已从"代码补全插件"演进为**形态丰富的Agent生态**。核心分水岭在于**IDE派 vs 终端派**：

| 流派 | 代表产品 | 核心哲学 | 用户界面 |
|---|---|---|---|
| **IDE派** | Cursor, Devin Desktop, Copilot | AI嵌入编辑器，人机协同 | IDE插件/独立IDE |
| **终端派** | Claude Code, Codex CLI, DeepSeek TUI | AI自主执行，人只做审查 | CLI/TUI |
| **平台派** | OpenClaw, Hermes | Agent编排与基础设施 | 多渠道接入 |

根据OpenRouter 2026年4月数据，**六大主流编程工具日处理超1.4T tokens**：

| 工具 | 日Token量 | 形态 | 开源/闭源 |
|---|---|---|---|
| **OpenClaw** | 822B | 自主Agent平台 | MIT开源 |
| **Kilo Code** | 302B | VS Code扩展 | 开源 |
| **Claude Code** | 166B | 终端CLI Agent | 闭源 |
| **Cline** | 97.2B | VS Code Agent | 开源 |
| **Hermes Agent** | 64B | 终端自学习Agent | MIT开源 |
| **Roo Code** | 20.9B | IDE Agent | 开源 |

> **核心洞察**：2026年没有单一产品是完整的"AI Software Factory"。工厂需要**组装多个层**：编码Agent层 + 沙箱环境层 + 验证层 + 部署层。这正是AI Factory的机会所在。


### 二、核心竞品深度分析

#### 2.1 Claude Code（Anthropic）

**定位**：终端CLI Agent的开创者，能力标杆

**核心数据**：
- 形态：终端CLI（Anthropic官方）
- 默认模型：Claude Sonnet 4.6 / Opus 4.7
- 上下文：200K
- 价格：月费$20起，Max计划$100-200/月

**核心优势**：
1. **代码质量标杆**：代码生成、调试、重构能力无明显对手
2. **产品成熟度高**：支持内置skills、斜杠命令（`/init`、`/review`、`/security-review`）、插件管理
3. **企业友好**：支持企业TLS代理，信任OS CA证书
4. **子Agent支持**：2025年7月已支持subagents，2026年4月增加并行初始化

**核心痛点**：
1. **成本高昂**：Sonnet 4.6输出$15/M token，Opus 4.7输出$25/M
2. **上下文限制**：200K在大型monorepo前会爆
3. **国内使用门槛**：面临网络、账号、支付三重门槛
4. **仅止于编码Agent**：不提供沙箱环境、验证流水线、部署路径

**对AI Factory的启示**：
- ✅ **可吸取**：成熟的产品体验、Skill插件体系、子Agent机制
- ⚠️ **需超越**：成本（AI Factory可以用模型路由降本）、完整流水线（编码+验证+部署闭环）

---

#### 2.2 Codex CLI（OpenAI）

**定位**：OpenAI官方的终端自主Agent

**核心数据**：
- 形态：终端CLI（OpenAI官方）
- 默认模型：GPT-5.5 / GPT-5.4 mini
- 上下文：1M（GPT-5.5）
- 特点：可运行40分钟自主会话无需干预

**核心优势**：
1. **超长上下文**：1M上下文窗口适合大型代码库
2. **高自主性**：可长时间无人值守运行
3. **可观测性**：支持OpenTelemetry追踪、review分析
4. **多实例支持**：Codex可配置多个命名实例并行

**核心痛点**：
1. **代码质量略逊**：编辑不如Claude代码地道，模糊指令下易过度重构
2. **缺少内省能力**：没有Claude Code的`/context`自省，调试困难
3. **生态绑定**：强依赖OpenAI生态

**对AI Factory的启示**：
- ✅ **可吸取**：长上下文处理、高自主性模式、可观测性设计
- ⚠️ **需超越**：模型可插拔（不绑定单一Provider）

---

#### 2.3 Cursor

**定位**：AI原生IDE之王，最赚钱的AI编程工具

**核心数据**：
- 形态：独立IDE（基于VS Code）
- 核心功能：Composer（跨文件修改）、云Agent、移动端
- 价格：Hobby免费，Pro $20/月，Pro+ $60/月，Ultra $200/月

**核心优势**：
1. **IDE原生体验**：迁移成本低，开发者无需改变习惯
2. **项目级理解**：Composer能理解整个项目结构跨文件修改
3. **功能演进快**：2026年加入云Agent、移动端、CLI

**核心痛点**：
1. **AI辅助而非自主**：仍需要人"在驾驶位"
2. **国内需要稳定网络**

**对AI Factory的启示**：
- ✅ **可吸取**：优秀的UX设计、项目级上下文理解
- ⚠️ **需超越**：从"助手"到"自主组织"的跃迁

---

#### 2.4 DeepSeek Harness / TUI

**定位**：价格颠覆者 + Agent调度层

**核心数据**：
- DeepSeek TUI：社区项目（Rust编写），MIT开源，2026年1月发布，破10K GitHub Stars
- DeepSeek Harness：官方Agent工作台，8月13日开源，首日破3万Star
- 价格：V4 Flash $0.14/M输入，$0.28/M输出（约为Claude Opus的1/90）

**核心优势（Harness）**：
1. **"一切皆插件"架构**：模型、工具、技能、会话、沙箱全部可替换
2. **子Agent收编能力**：可将Claude Code和Codex作为子Agent调度
3. **64天12293次提交**：极快迭代速度

**核心优势（TUI）**：
1. **成本极致**：比Claude便宜35-90倍
2. **原生子Agent编排**：Coordinator可拆解任务并发执行子Agent

**核心痛点**：
1. **质量差距**：密集推理和遗留代码场景与Claude有差距
2. **安全风险**：社区出现冒充DeepSeek-TUI的恶意仓库

**对AI Factory的启示**：
- ✅ **可吸取**：插件化架构（"一切皆可替换"的设计哲学）、子Agent编排机制、成本优势（模型路由）
- 🚀 **机会**：DeepSeek Harness做的是"Agent工作台"，AI Factory做的是"Agent公司"——组织层级的跃迁

---

#### 2.5 OpenClaw

**定位**：开源AI Agent的"网关之王"

**核心数据**：
- 形态：跨平台自主Agent平台
- 许可：MIT，可自托管
- 集成：50+消息平台（长期路线目标；近期 P0 落地 5 渠道：WhatsApp/Telegram/Slack/Discord/微信）
- 生态：ClawHub市场，13000+社区Skill
- OpenRouter日榜：#1全球（822B tokens/天）

**核心优势**：
1. **集成能力（长期路线目标）**：50+平台接入，"连接一切"（近期 P0 5 渠道，见 §9.5.6）
2. **生态庞大**：13000+社区Skill
3. **可预测性强**：权限、审批机制明确，适合团队使用
4. **上手简单**：30分钟内可部署运行

**核心痛点**：
1. **记忆能力有限**：本质是纯文本持久化
2. **无自学习能力**：Skill需人工编写
3. **安全风险**：2026年3月4天内披露9个CVE（含CVSS 9.9）
4. **Skill质量参差**：13000+社区Skill质量不均可控

**对AI Factory的启示**：
- ✅ **可吸取**：多渠道集成能力、明确的权限审批机制
- ⚠️ **需超越**：自学习能力（OpenClaw没有）、经验质量管控

---

#### 2.6 Hermes Agent（Nous Research）

**定位**：自进化AI Agent的"黑马"

**核心数据**：
- 研发方：Nous Research（Hermes、Nomos、Psyche系列开源模型开发实验室）
- 形态：终端自学习Agent
- 许可：MIT开源
- 内置Skill：118个（审核通过）
- GitHub：连续多周Trending榜首，22K+ Stars
- OpenRouter日榜：Top 50（64B tokens/天）

**核心优势**：
1. **自学习闭环**：完成任务后自动提取模式，生成可复用Skill文件
2. **三层记忆架构**：Session Memory → Persistent Memory → Skill Memory（配合FTS5全文检索和LLM摘要）
3. **用户建模（Honcho）**：构建多维用户理解，包含沟通风格、决策模式、项目上下文
4. **技能进化算法（GEPA）**：基于ICLR 2026 Oral论文，用遗传-帕累托提示词进化而非RL，无需梯度更新即可提升技能库
5. **中小模型优化**：在中小模型上表现突出，更适合本地/低成本部署

**核心痛点**：
1. **集成能力有限**：仅支持~15个平台（OpenClaw的1/3）
2. **部署复杂度较高**：2-4小时上手
3. **生态不如OpenClaw成熟**
4. **记忆设计被Anthropic"参考"**：社区认为Hermes自进化能力催生了Claude Code的自动任务完成判断功能

**对AI Factory的启示**：
- ✅ **可吸取**：**这是最关键的借鉴对象**！自学习闭环（任务→复盘→Skill生成→下次复用）、分层记忆架构、用户建模
- 🚀 **超越方向**：Hermes是"个体自进化"，AI Factory要做"组织自进化"——跨任务、跨Agent、跨项目的经验沉淀

---

#### 2.7 pi-agent

**定位**：开源终端Agent，隐私优先

**核心数据**：
- 形态：终端CLI + Web Demo
- 许可：开源（PyPI）
- 特点：支持Ollama本地模型，代码不出机器

**核心优势**：
1. **隐私优先**：支持完全本地运行（Ollama），适合敏感代码
2. **多Provider支持**：Groq免费、Gemini免费、OpenRouter、Ollama本地
3. **内置工具丰富**：`update_plan`、`delegate`、`remember`（持久记忆）、`analyze_data`、`make_slides`
4. **MCP集成**：支持标准MCP Server连接

**对AI Factory的启示**：
- ✅ **可吸取**：BYOK模式、本地优先设计、MCP标准化集成
- ⚠️ **需超越**：pi-agent是单Agent工具，AI Factory要做多Agent组织

---

#### 2.8 FactoryKit

**定位**："被部署的软件工厂"——前向部署工程师模式

**核心数据**：
- 形态：企业服务（非产品）
- 模式：工程师驻场3个月，在客户基础设施上部署工厂
- 架构：云端沙箱隔离 → 按任务选择Agent（Claude Code/Codex/Grok）→ 凭证动态注入 → 自动提交PR → Passmark浏览器QA验证 → PR附带录屏

**核心优势**：
1. **真正端到端**：不只是编码Agent，而是"Issue → 验证通过的PR"完整闭环
2. **沙箱隔离**：每个任务在独立云端沙箱运行，不碰本地环境
3. **凭证安全**：代理不持有真实凭证，动态注入且限定仓库范围
4. **验证机制**：浏览器QA录屏附在PR上，人类审查时直接可见
5. **多仓库支持**：单任务跨多个仓库返回协调好的PR

**核心痛点**：
1. **仅限企业客户**：定制化服务，价格昂贵
2. **平台限制**：仅GitHub，仅标准Web应用（不支持移动端）
3. **任务时间**：简单~5分钟，中等10-15分钟，复杂20-30分钟

**对AI Factory的启示**：
- ✅ **可吸取**：**这是最接近AI Factory愿景的竞品！** 完整闭环设计、沙箱隔离、凭证安全、验证机制
- 🚀 **超越方向**：FactoryKit是"企业定制服务"，AI Factory要做"人人可用的操作系统"

#### 2.9 Devin（Cognition）

**定位**："第一个自主软件工程师"

**核心数据**：
- 形态：自主Agent平台
- 目标：计划、编写、测试、交付生产代码
- 部署：企业版，有名客户

**对AI Factory的启示**：
- ⚠️ **关键差距**：Devin是"单Agent软件工程师"，AI Factory是"AI组织管理系统"——多Agent协作的层面完全不同


### 三、全方位对比矩阵

| 维度 | Claude Code | Codex CLI | Cursor | DeepSeek Harness/TUI | OpenClaw | Hermes | **AI Factory（目标）** |
|---|---|---|---|---|---|---|---|
| **核心定位** | 终端编码Agent | 终端编码Agent | IDE+Agent | Agent工作台/调度层 | 跨平台网关 | 自进化Agent运行时 | **AI组织管理系统** |
| **多Agent协作** | 有限 | 有限 | 无 | ✅ 原生子Agent编排 | ✅ 多Agent编排 | 有限 | ✅ **组织级协作** |
| **自学习能力** | 有限 | 有限 | 无 | 有限 | 无 | ✅ **核心卖点** | ✅ **组织级学习** |
| **任务拆解** | 有限 | 有限 | 有限 | ✅ 核心能力 | 有限 | 有限 | ✅ **核心能力** |
| **审计/治理** | 有限 | 有限 | 无 | 有限 | ✅ 明确机制 | 有限沙盒 | ✅ **核心能力** |
| **工具生态** | 插件 | OpenAI生态 | IDE插件 | 一切皆插件 | 13000+ Skill | 118个自生成Skill | **多生态集成** |
| **成本** | 高 | 中 | 中 | 极低 | 中 | 中 | **路由优化** |
| **跨行业** | ❌ 仅编程 | ❌ 仅编程 | ❌ 仅编程 | ❌ 仅编程 | ❌ 仅编程/自动化 | ❌ 仅编程/自动化 | ✅ **核心愿景** |
| **完整闭环** | ❌ 止于代码 | ❌ 止于代码 | ❌ 止于代码 | ❌ 工作台 | ❌ 消息路由 | ❌ 代码 | ✅ **Issue→PR闭环** |


### 四、关键趋势与洞察

#### 趋势1：Agent"调度层"正在成为兵家必争之地

> **"模型可以换，执行任务的Agent可以换，但组织模型、调度Agent、管理任务和工具的那层工作环境，一旦用顺手就很难搬。"**

DeepSeek Harness的策略非常清晰：**做Agent时代的调度层**。它把Claude Code和Codex变成自己的"子Agent插件"。Kimi Code同样支持Sub-agents拆出独立上下文并行处理，Agent Swarm支持批量任务多Agent并行。

**对AI Factory的启示**：这正是AI Factory的核心定位——不只是"调度层"，而是"AI组织操作系统"。

---

#### 趋势2："自学习"正成为拉开差距的关键能力

Hermes Agent的崛起证明了**自学习是下一代Agent的核心竞争力**。

- OpenClaw（13000+ Skill）vs Hermes（118个自生成Skill）
- Hermes在OpenRouter日Token量已多次反超OpenClaw
- 社区叙事统一认为Hermes"重新定义了开源Agent的方向"

**核心差异**：OpenClaw是"人写的Skill市场"，Hermes是"Agent自己长出来的Skill"。

**对AI Factory的启示**：学习能力不是"可有可无"的功能，而是**核心护城河**。

---

#### 趋势3：分层架构——没有单一产品是完整工厂

> **"No single product today is a complete AI software factory. A factory is assembled from a handful of layers."**

完整的AI软件工厂需要多层组装：
1. **编码Agent层**：Claude Code / Codex / Cursor
2. **沙箱环境层**：e2b / Daytona / Modal
3. **验证层**：Playwright / Passmark
4. **部署层**：SST / Nitric / Encore

**对AI Factory的启示**：我们的机会在于——**整合这些层，提供统一的操作系统体验**，而不是重新发明每一层。

---

#### 趋势4：成本是压倒性的差异化因素

DeepSeek V4 Flash的成本是Claude Opus 4.7的**1/90**。Kimi Code K3的编程场景缓存命中率超90%，大幅降低成本。

**对AI Factory的启示**：模型路由（简单任务用便宜模型，复杂任务用强模型）是AI Factory的天然优势。


### 五、可吸取的具体设计元素

#### 5.1 从DeepSeek Harness吸取

| 设计元素 | 描述 | AI Factory如何采纳 |
|---|---|---|
| **"一切皆插件"架构** | 模型、工具、技能、会话、沙箱全部可替换 | 采用插件化架构，核心引擎不绑定任何组件 |
| **子Agent收编** | 将Claude Code/Codex作为子Agent调度 | AI Factory支持任意Agent作为"执行单元" |
| **快速迭代** | 64天12293次提交 | 保持高迭代速度，MVP快速验证 |

#### 5.2 从Hermes吸取

| 设计元素 | 描述 | AI Factory如何采纳 |
|---|---|---|
| **自学习闭环** | 任务→复盘→Skill生成→下次复用 | 核心学习机制，但升级为"组织级学习" |
| **分层记忆** | Session → Persistent → Skill Memory | 引入分层记忆架构，增加"组织级"层 |
| **用户建模** | 多维用户理解（沟通风格、决策模式） | 引入用户画像，个性化任务执行 |
| **技能进化算法** | GEPA（遗传-帕累托提示词进化） | 研究GEPA算法，应用于Skill自动优化 |

#### 5.3 从OpenClaw吸取

| 设计元素 | 描述 | AI Factory如何采纳 |
|---|---|---|
| **多渠道集成** | 50+消息平台（长期目标）；P0 5 渠道 | 支持多入口交互（CLI/TUI/Web/IM） |
| **权限审批机制** | 明确的权限控制和审批流程 | 治理模块的核心设计参考 |
| **Skill市场** | ClawHub 13000+ Skill | 未来建立"工厂模板市场" |

#### 5.4 从FactoryKit吸取

| 设计元素 | 描述 | AI Factory如何采纳 |
|---|---|---|
| **完整闭环** | Issue → 验证通过 → PR | 端到端流水线设计 |
| **沙箱隔离** | 每个任务独立云端沙箱 | 安全执行环境设计 |
| **凭证安全** | 代理不持有真实凭证 | 安全架构参考 |
| **验证录屏** | PR附带浏览器QA录屏 | 验证机制设计 |

#### 5.5 从pi-agent吸取

| 设计元素 | 描述 | AI Factory如何采纳 |
|---|---|---|
| **BYOK模式** | 用户自带模型Key | 支持多Provider、自带Key |
| **本地优先** | 支持Ollama完全本地运行 | 支持本地部署选项 |
| **MCP集成** | 标准MCP Server接入 | 工具生态的标准化接口 |


### 六、AI Factory的核心差异与优势

基于竞品分析，AI Factory的**差异化定位**可以明确为：

#### 6.1 从"Agent"到"AI组织"的跃迁

| 维度 | 竞品（Agent） | AI Factory（AI组织） |
|---|---|---|
| **管理对象** | 单个Agent | 多个Agent组成的组织 |
| **协作模式** | Agent内部循环 | Agent间协作（Planner→Executor→Reviewer→Debugger→Governor→Learner） |
| **记忆范围** | 会话内/单Agent | 跨Agent、跨项目、跨任务 |
| **学习方式** | 单Agent学习 | 组织级学习（经验跨Agent共享） |
| **治理维度** | 单Agent权限 | 组织级治理（成本/权限/合规/审计） |

#### 6.2 竞品"做不到"的AI Factory能力

| 能力 | 竞品现状 | AI Factory定位 |
|---|---|---|
| **跨行业** | 所有竞品仅限于编程/自动化 | 行业工厂体系（软件开发→运维→电商→自媒体→数据分析→...） |
| **组织级学习** | Hermes是个体学习，OpenClaw无学习 | 跨Agent、跨项目、跨任务的经验沉淀与复用 |
| **完整闭环** | 多数止于代码/PR | Issue → 拆解 → 多Agent协作 → 验证 → 部署 → 复盘 → 学习 |
| **治理体系** | 仅有权限审批 | 成本治理 + 权限治理 + 合规治理 + 风险治理 + 安全治理 |
| **工具生态** | 绑定单一生态 | Skill + MCP + Hermes + OpenClaw 多生态集成，**不绑定任何工具** |


### 七、关键结论

1. **最大机会**：2026年没有完整"AI软件工厂"产品。市场是"组装件"而非"成品"，这是AI Factory的最大窗口。

2. **最大威胁**：DeepSeek Harness正在卡位"Agent调度层"。如果它扩展到"组织管理"层，将直接竞争。Kimi Code的Agent Swarm也在做多Agent并行。

3. **最需借鉴**：Hermes的自学习闭环 + FactoryKit的端到端闭环 + DeepSeek的插件化架构。

4. **最需建立**：跨行业的"领域智能"封装能力 + 组织级学习能力 + 完整的治理体系。这些都是竞品目前不具备的。

5. **最终定位**：AI Factory不是"又一个Agent工具"，而是**AI公司的操作系统**——这个定位是目前市场上完全空白的。


---

## 十六、竞品优势吸收与技能定位补充

> 2026-08-21 补充: 从 DeepSeek Harness / Hermes / OpenClaw / FactoryKit / pi-agent 吸取的设计元素如何在 AI Factory 落地 (插件架构/子Agent收编/四层记忆/GEPA技能进化/多渠道/沙箱/BYOK/MCP)。


> 本文档用于补充到主设计文档中，详细说明从各竞品吸取的设计元素如何在AI Factory中落地实现。

---

### 一、概述：我们吸收了哪些竞品优势

基于对DeepSeek Harness、Hermes、OpenClaw、FactoryKit、pi-agent、Claude Code、Codex CLI等竞品的深度分析，AI Factory将系统性地吸收以下核心优势：

| 竞品 | 吸收的核心能力 | 在AI Factory中的落地 |
|---|---|---|
| **DeepSeek Harness** | "一切皆插件"架构、子Agent收编 | 插件化核心引擎、任意Agent作为执行单元 |
| **Hermes** | 自学习闭环、分层记忆、用户建模、GEPA算法 | 组织级学习系统、四层记忆架构、用户画像、Skill自进化 |
| **OpenClaw** | 多渠道集成、权限审批、Skill市场 | 多入口交互、治理模块、工厂模板市场 |
| **FactoryKit** | 完整闭环、沙箱隔离、凭证安全、验证录屏 | 端到端流水线、安全执行环境、验证机制 |
| **pi-agent** | BYOK模式、本地优先、MCP集成 | 多Provider支持、本地部署、标准化工具接口 |
| **Claude Code** | 产品成熟度、Skill插件、子Agent | 用户体验设计、插件体系 |
| **Codex CLI** | 长上下文、自主性、可观测性 | 上下文管理、高自主模式、OpenTelemetry集成 |

---

### 二、技能与定位总览

#### 2.1 AI Factory的技能树

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          AI Factory 完整技能树                                     │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 核心引擎技能（由DeepSeek Harness启发）                                 │   │
│  │                                                                             │   │
│  │  1.1 插件化架构      → 一切皆插件，核心不绑定任何组件                       │   │
│  │  1.2 子Agent调度     → 任意Agent可作为执行单元                              │   │
│  │  1.3 任务拆解引擎    → 复杂任务→DAG子任务                                   │   │
│  │  1.4 多Agent编排     → 6种协作模式（顺序/并行/辩论/审查/委托/迭代）        │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 学习与进化技能（由Hermes启发）                                          │   │
│  │                                                                             │   │
│  │  2.1 自学习闭环      → 任务→复盘→经验→复用（组织级）                       │   │
│  │  2.2 四层记忆架构    → Session → Project → Organization → Platform Memory  │   │
│  │  2.3 用户画像建模    → 沟通风格、决策模式、偏好学习                         │   │
│  │  2.4 Skill自动进化   → 基于GEPA算法的Skill优化                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 交互与集成技能（由OpenClaw + pi-agent启发）                            │   │
│  │                                                                             │   │
│  │  3.1 多入口交互      → CLI / TUI / Web / IM（多渠道）                      │   │
│  │  3.2 BYOK模式        → 多Provider支持，用户自带Key                         │   │
│  │  3.3 本地优先部署    → 支持Ollama完全本地运行                               │   │
│  │  3.4 MCP标准化集成   → 标准MCP Server接入                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L4: 治理与安全技能（由OpenClaw + FactoryKit启发）                          │   │
│  │                                                                             │   │
│  │  4.1 完整审计追踪    → 全链路事件记录、决策链追溯                          │   │
│  │  4.2 权限审批体系    → 角色权限、风险分级、审批流程                        │   │
│  │  4.3 沙箱隔离执行    → 每个任务独立安全沙箱                                │   │
│  │  4.4 凭证安全        → 动态注入、不持有真实凭证                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L5: 验证与交付技能（由FactoryKit启发）                                     │   │
│  │                                                                             │   │
│  │  5.1 端到端闭环      → Issue → 拆解 → 执行 → 验证 → 交付                   │   │
│  │  5.2 验证录屏        → 执行过程录制，供人工审查                             │   │
│  │  5.3 质量审查体系    → 多维度质量评分（完整性/正确性/质量/一致性/安全性）  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L6: 行业扩展技能（AI Factory独有）                                         │   │
│  │                                                                             │   │
│  │  6.1 工厂模板体系    → 行业工厂定义、模板市场                               │   │
│  │  6.2 领域智能封装    → Skill+MCP+Knowledge+Workflow+Evaluation+Learning   │   │
│  │  6.3 跨行业迁移      → 软件开发→运维→电商→自媒体→数据分析                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2 核心定位对比

| 定位维度 | DeepSeek Harness | Hermes | OpenClaw | **AI Factory** |
|---|---|---|---|---|
| **核心身份** | Agent工作台 | 自进化Agent运行时 | 跨平台网关 | **AI组织操作系统** |
| **管理对象** | Agent调度 | 单Agent | 消息路由 | **AI公司（多Agent组织）** |
| **学习范围** | 无 | 单Agent个体学习 | 无 | **组织级跨任务学习** |
| **行业覆盖** | 仅编程 | 仅编程/自动化 | 仅编程/自动化 | **全行业（工厂化）** |
| **治理维度** | 有限 | 有限 | 权限审批 | **完整治理体系** |


### 三、从DeepSeek Harness吸取的详细设计

#### 3.1 "一切皆插件"架构

**设计原则**：核心引擎零依赖，所有组件均可替换。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          插件化架构设计                                             │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        核心引擎（零依赖）                                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │   Orchestrator│  │   Scheduler   │  │  Working      │                   │   │
│  │  │   (编排器)    │  │   (调度器)    │  │  Memory       │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                    ┌───────────────┼───────────────┐                              │
│                    │               │               │                              │
│                    ▼               ▼               ▼                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        插件层（全部可替换）                                  │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ Model       │  │ Tool        │  │ Skill       │  │ Agent       │       │   │
│  │  │ Provider    │  │ Registry    │  │ Registry    │  │ Registry    │       │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │   │
│  │  │ RAG         │  │ Knowledge   │  │ Sandbox     │  │ Notifier    │       │   │
│  │  │ Provider    │  │ Store       │  │ Provider    │  │ Provider    │       │   │
│  │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │  │ (可插拔)    │       │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**接口定义**：

```python
#### 插件接口标准
class PluginRegistry:
    """插件注册表——所有组件都通过此注册"""
    
    def register_model_provider(self, name: str, provider: ModelProvider): ...
    def register_tool(self, name: str, tool: Tool): ...
    def register_skill(self, name: str, skill: Skill): ...
    def register_agent(self, name: str, agent_class: Type[Agent]): ...
    def register_rag_provider(self, name: str, provider: RAGProvider): ...
    def register_sandbox_provider(self, name: str, provider: SandboxProvider): ...
    def register_notifier(self, name: str, notifier: Notifier): ...

#### 核心引擎只依赖这些接口，不依赖具体实现
class Orchestrator:
    def __init__(self, registry: PluginRegistry):
        self.registry = registry
        # 所有组件通过registry获取，不硬编码
```

**落地清单**：

| 插件类型 | MVP | Beta | GA |
|---|---|---|---|
| Model Provider | DeepSeek | + Anthropic, OpenAI | + Ollama, 自定义 |
| Tool Registry | 4个内置工具 | + 5个扩展工具 | + MCP标准接入 |
| Skill Registry | ❌ | ✅ 简单Skill | ✅ 完整Skill系统 |
| Agent Registry | 单Agent | + Planner, Executor | + 全部6种Agent |
| RAG Provider | 内置Chroma | + Pinecone, Milvus | + 自定义向量库 |
| Sandbox Provider | 本地 | + Docker | + 云端沙箱 |
| Notifier | CLI | + TUI | + Web, IM |

---

#### 3.2 子Agent收编机制

**设计原则**：AI Factory可以调度任何外部Agent作为"执行单元"。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          子Agent收编架构                                           │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         AI Factory核心引擎                                  │   │
│  │                                                                             │   │
│  │  ┌───────────────┐                                                         │   │
│  │  │  Task Planner │ → 拆解任务 → 分配子任务                                 │   │
│  │  └───────────────┘                                                         │   │
│  │         │                                                                   │   │
│  │         ▼                                                                   │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    Agent Router（Agent路由器）                       │   │   │
│  │  │                                                                     │   │   │
│  │  │  决策: 当前子任务 → 选择最佳执行Agent                              │   │   │
│  │  │                                                                     │   │   │
│  │  │  路由规则:                                                          │   │   │
│  │  │  • 代码生成任务 → 选择Claude Code / Codex                          │   │   │
│  │  │  • 简单文件操作 → 选择内置Executor                                │   │   │
│  │  │  • 架构设计任务 → 选择DeepSeek Harness                             │   │   │
│  │  │  • 成本敏感任务 → 选择DeepSeek TUI                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│        ┌───────────────────────────┼───────────────────────────┐                  │
│        │                           │                           │                  │
│        ▼                           ▼                           ▼                  │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐             │
│  │  Claude Code    │     │  DeepSeek      │     │  Codex CLI      │             │
│  │  适配器         │     │  Harness适配器  │     │  适配器         │             │
│  │                 │     │                 │     │                 │             │
│  │ • 格式转换     │     │ • 格式转换     │     │ • 格式转换     │             │
│  │ • 上下文注入   │     │ • 上下文注入   │     │ • 上下文注入   │             │
│  │ • 结果提取     │     │ • 结果提取     │     │ • 结果提取     │             │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘             │
│        │                           │                           │                  │
│        ▼                           ▼                           ▼                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                          外部Agent实例                                      │  │
│  │              Claude Code / DeepSeek Harness / Codex CLI                    │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**适配器接口**：

```python
class AgentAdapter(ABC):
    """子Agent适配器接口——让任意Agent可被AI Factory调度"""
    
    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """返回该Agent的能力列表: ['code_generation', 'code_review', 'debugging']"""
        pass
    
    @abstractmethod
    def get_cost_model(self) -> Dict[str, float]:
        """返回成本模型: {'prompt_per_m': 0.14, 'completion_per_m': 0.28}"""
        pass
    
    @abstractmethod
    async def execute(self, task: SubTask, context: Dict) -> AgentResult:
        """执行子任务，返回标准化结果"""
        pass
    
    @abstractmethod
    def get_supported_tools(self) -> List[str]:
        """返回该Agent支持的工具列表"""
        pass

#### 内置适配器
class ClaudeCodeAdapter(AgentAdapter): ...
class DeepSeekHarnessAdapter(AgentAdapter): ...
class CodexCLIAdapter(AgentAdapter): ...
class BuiltinExecutorAdapter(AgentAdapter): ...
```

**落地清单**：

| 适配器 | 优先级 | 说明 |
|---|---|---|
| Builtin Executor | P0 | AI Factory内置执行器 |
| Claude Code Adapter | P1 | 调用Claude Code作为子Agent |
| DeepSeek Harness Adapter | P1 | 调用DeepSeek Harness作为子Agent |
| Codex CLI Adapter | P1 | 调用Codex CLI作为子Agent |
| Hermes Adapter | P2 | 调用Hermes作为子Agent |
| pi-agent Adapter | P2 | 调用pi-agent作为子Agent |


### 四、从Hermes吸取的详细设计

#### 4.1 自学习闭环（组织级）

**设计原则**：不仅是单Agent学习，而是跨Agent、跨项目、跨任务的组织级学习。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          组织级自学习闭环                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         执行阶段                                            │   │
│  │                     (多Agent协作完成任务)                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         复盘阶段（Learner Agent）                           │   │
│  │                                                                             │   │
│  │  输入: 完整任务执行数据（DAG + 所有Agent轨迹 + 审计日志）                  │   │
│  │                                                                             │   │
│  │  输出:                                                                      │   │
│  │  • 任务级复盘: 本次任务踩了哪些坑                                           │   │
│  │  • 模式级提炼: 这类问题的通用解决模式                                       │   │
│  │  • Skill级沉淀: 哪些操作可固化为Skill                                      │   │
│  │  • 组织级洞察: 协作效率、Agent瓶颈、流程优化                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         经验提炼（Learner Agent）                           │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 成功模式      │  │ 失败教训      │  │ 领域知识      │                   │   │
│  │  │ (可复用)     │  │ (要避免)     │  │ (可学习)     │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ Skill模板     │  │ 工作流模板    │  │ 协作模式模板   │                   │   │
│  │  │ (可复用)     │  │ (可复用)     │  │ (可复用)     │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         审查与激活（用户 + 系统）                           │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 自动验证: 在3-5个任务中验证经验有效性                               │   │   │
│  │  ├─────────────────────────────────────────────────────────────────────┤   │   │
│  │  │ 人工审查: 用户批准/拒绝/修改经验                                    │   │   │
│  │  ├─────────────────────────────────────────────────────────────────────┤   │   │
│  │  │ 经验激活: 注入到RAG+Skill库，后续任务自动引用                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         复用阶段                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ Planner引用   │  │ Executor引用  │  │ Coordinator   │                   │   │
│  │  │ (拆解时使用)  │  │ (执行时使用)  │  │ (编排时使用)  │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 4.2 四层记忆架构

**设计原则**：从Hermes的三层记忆升级为四层组织级记忆。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          四层记忆架构                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L4: Platform Memory（平台级记忆）                                           │   │
│  │   • 内容: 所有项目的经验聚合、治理规则、系统架构知识                         │   │
│  │   • 范围: AI Factory全局                                                    │   │
│  │   • 更新: 系统升级 + 经验审查通过后                                          │   │
│  │   • 存储: 向量库 + 关系库                                                   │   │
│  │   • 示例: "内存泄漏的通用诊断模式"、"NPE的最佳修复方法"                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L3: Organization Memory（组织级/工厂级记忆）                               │   │
│  │   • 内容: 某个工厂（如软件开发工厂）的所有项目经验                          │   │
│  │   • 范围: 该工厂所有项目共享                                                │   │
│  │   • 更新: 工厂内任务完成后 + 经验审查                                       │   │
│  │   • 存储: 工厂级向量库                                                       │   │
│  │   • 示例: "这个团队常用的代码风格"、"项目的架构决策历史"                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L2: Project Memory（项目级记忆）                                            │   │
│  │   • 内容: 当前项目的代码、文档、历史决策、历史故障                          │   │
│  │   • 范围: 仅当前项目                                                        │   │
│  │   • 更新: 项目任务完成后 + 用户挂载                                        │   │
│  │   • 存储: 项目级向量库 + 文件系统                                           │   │
│  │   • 示例: "代码仓库结构"、"PRD文档"、"之前修复过的Bug"                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L1: Session Memory（会话级记忆）                                            │   │
│  │   • 内容: 当前任务的DAG、Agent状态、中间产出、对话历史                       │   │
│  │   • 范围: 仅当前会话                                                        │   │
│  │   • 更新: 实时更新                                                          │   │
│  │   • 存储: 内存 + 工作记忆文件                                                │   │
│  │   • 示例: "当前执行到T3"、"T2的输出结果"、"用户的最后一次指令"              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**记忆接口**：

```python
class MemoryLayer(ABC):
    """记忆层接口"""
    
    @abstractmethod
    async def store(self, key: str, value: Any, metadata: Dict) -> None: ...
    @abstractmethod
    async def retrieve(self, query: str, top_k: int) -> List[MemoryItem]: ...
    @abstractmethod
    async def search(self, filters: Dict) -> List[MemoryItem]: ...
    @abstractmethod
    def get_layer_name(self) -> str: ...

#### 各层实现
class PlatformMemory(MemoryLayer): ...
class OrganizationMemory(MemoryLayer): ...
class ProjectMemory(MemoryLayer): ...
class SessionMemory(MemoryLayer): ...

#### 记忆管理器——自动路由到正确层级
class MemoryManager:
    def __init__(self):
        self.layers = {
            "platform": PlatformMemory(),
            "organization": OrganizationMemory(),
            "project": ProjectMemory(),
            "session": SessionMemory(),
        }
    
    async def store_with_routing(self, data: Any, scope: str) -> None:
        """根据scope自动路由到正确的记忆层"""
        layer = self.layers.get(scope, self.layers["session"])
        await layer.store(data)
    
    async def retrieve_with_routing(self, query: str, scopes: List[str]) -> List[MemoryItem]:
        """从多个层级检索，按优先级合并"""
        results = []
        for scope in scopes:
            layer = self.layers.get(scope)
            if layer:
                results.extend(await layer.retrieve(query, top_k=5))
        return self._merge_and_rerank(results)
```

#### 4.3 用户画像建模

**设计原则**：系统学习用户的沟通风格、决策模式和偏好，个性化任务执行。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          用户画像建模                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 用户画像维度                                                               │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 沟通风格 (Communication Style)                                      │   │   │
│  │  │   • 详细程度: 喜欢详细解释 vs 喜欢简洁指令                          │   │   │
│  │  │   • 术语偏好: 技术深度 vs 业务语言                                  │   │   │
│  │  │   • 反馈方式: 直接指出问题 vs 委婉建议                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 决策模式 (Decision Pattern)                                         │   │   │
│  │  │   • 风险偏好: 保守型 vs 进取型                                      │   │   │
│  │  │   • 决策速度: 快速决策 vs 审慎决策                                  │   │   │
│  │  │   • 依赖偏好: 自主决策 vs 需要确认                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 技术偏好 (Technical Preference)                                     │   │   │
│  │  │   • 语言/框架偏好: Python vs Java vs Go...                          │   │   │
│  │  │   • 代码风格: 详细注释 vs 简洁风格                                  │   │   │
│  │  │   • 测试策略: TDD vs 后补测试                                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 上下文模式 (Context Pattern)                                        │   │   │
│  │  │   • 项目历史: 曾参与过的项目类型                                    │   │   │
│  │  │   • 成功案例: 哪些类型的任务用户认为做得好                          │   │   │
│  │  │   • 失败案例: 哪些类型的任务用户不满意                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 画像学习与更新机制                                                         │   │
│  │                                                                             │   │
│  │  用户交互 → 行为提取 → 模式分析 → 画像更新                                 │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 显式反馈     │  │ 隐式行为     │  │ 会话上下文     │                   │   │
│  │  │ (用户评分)   │  │ (操作日志)   │  │ (对话历史)    │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │        │                    │                    │                          │   │
│  │        └────────────────────┼────────────────────┘                          │   │
│  │                             ▼                                               │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 画像分析器                                                          │   │   │
│  │  │   • 聚类分析: 用户属于哪类行为模式                                  │   │   │
│  │  │   • 趋势分析: 用户偏好是否在变化                                    │   │   │
│  │  │   • 冲突检测: 用户行为与画像不一致时触发更新                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**用户画像数据结构**：

```python
class UserProfile:
    user_id: str
    version: int  # 画像版本
    
    # 沟通风格
    communication: CommunicationStyle
    
    # 决策模式
    decision: DecisionPattern
    
    # 技术偏好
    technical: TechnicalPreference
    
    # 上下文模式
    context: ContextPattern
    
    # 元数据
    last_updated: datetime
    total_interactions: int
    confidence: float  # 画像置信度


class CommunicationStyle:
    detail_preference: float  # 0-1, 1=非常详细
    technical_depth: float    # 0-1, 1=非常技术
    feedback_directness: float  # 0-1, 1=直接指出


class DecisionPattern:
    risk_preference: float    # 0-1, 0=保守, 1=激进
    decision_speed: float     # 0-1, 0=审慎, 1=快速
    autonomy_preference: float  # 0-1, 0=需确认, 1=自主


class TechnicalPreference:
    preferred_languages: List[str]
    code_style: str  # 'verbose' | 'concise' | 'standard'
    test_strategy: str  # 'tdd' | 'post' | 'minimal'
```

#### 4.4 Skill自动进化（GEPA算法）

**设计原则**：Skill不是人工编写的，而是通过进化算法自动优化的。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          Skill自动进化（基于GEPA）                                 │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ GEPA = Genetic-Pareto Prompt Evolution (遗传-帕累托提示词进化)             │   │
│  │                                                                             │   │
│  │  核心思想: 通过遗传算法优化Skill的提示词，而非人工调优                    │   │
│  │  优势: 无需梯度更新，可在小样本上快速迭代                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  进化流程:                                                                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 种群初始化                                                         │   │
│  │   • 从经验库中提取Skill模板作为初始种群                                    │   │
│  │   • 每个Skill包含: 目标描述 + 步骤 + 约束 + 示例                          │   │
│  │   • 种群大小: 20-50个候选Skill                                             │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 适应度评估 (Pareto Multi-Objective)                                │   │
│  │                                                                             │   │
│  │  评估维度:                                                                  │   │
│  │   • 成功率: 使用该Skill的任务成功率                                         │   │
│  │   • 效率: 使用该Skill的任务平均耗时                                         │   │
│  │   • 成本: 使用该Skill的任务平均成本                                         │   │
│  │   • 质量: 使用该Skill的任务产出质量评分                                    │   │
│  │   • 泛化性: 在不同类型任务上的表现一致性                                    │   │
│  │                                                                             │   │
│  │  Pareto前沿: 保留在所有维度上不被支配的候选                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 遗传操作                                                           │   │
│  │                                                                             │   │
│  │  选择: 从Pareto前沿中按适应度加权选择父代                                   │   │
│  │  交叉: 交换两个Skill的部分步骤/约束                                         │   │
│  │  变异: 随机修改步骤、调整参数、改变顺序                                     │   │
│  │  精英保留: 保留Pareto前沿中的最优个体                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 4: 验证与部署                                                         │   │
│  │                                                                             │   │
│  │  新Skill → 在3-5个任务上验证 → 验证通过 → 部署到Skill库                     │   │
│  │  验证失败 → 回到种群继续进化                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 5: 迭代                                                               │   │
│  │  每完成 10-20 个任务触发一次进化迭代                                       │   │
│  │  进化代数: 10-50代                                                        │   │
│  │  最佳Skill保存到经验库                                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Skill数据结构**：

```python
class Skill:
    id: str
    name: str
    version: int
    generation: int  # GEPA第几代
    
    # 内容
    goal: str  # 这个Skill解决什么问题
    steps: List[str]  # 执行步骤
    constraints: List[str]  # 约束条件
    examples: List[Dict]  # 示例
    
    # 表现数据
    success_rate: float
    avg_duration: float
    avg_cost: float
    quality_score: float
    
    # 进化数据
    parent_ids: List[str]  # 父代Skill ID
    mutation_type: str  # 变异类型
    fitness_score: float  # 适应度评分
```


### 五、从OpenClaw吸取的详细设计

#### 5.1 多渠道集成

**设计原则**：用户可通过任何渠道与AI Factory交互。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          多渠道集成架构                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          用户交互渠道                                      │   │
│  │                                                                             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │   │
│  │  │   CLI    │  │   TUI     │  │   Web     │  │    IM     │              │   │
│  │  │  (终端)   │  │  (终端UI)  │  │ (浏览器)  │  │ (消息)    │              │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         适配器层                                            │   │
│  │                                                                             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │   │
│  │  │ CLI       │  │ TUI       │  │ Web       │  │ IM        │              │   │
│  │  │ Adapter   │  │ Adapter   │  │ Adapter   │  │ Adapter   │              │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         核心引擎                                            │   │
│  │                     (统一消息处理)                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         通知渠道                                            │   │
│  │                                                                             │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐              │   │
│  │  │ Telegram  │  │  Slack    │  │   Email   │  │ WebSocket │              │   │
│  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**适配器接口**：

```python
class ChannelAdapter(ABC):
    """渠道适配器接口"""
    
    @abstractmethod
    def get_channel_type(self) -> str: ...
    
    @abstractmethod
    async def send_message(self, message: Message) -> None: ...
    
    @abstractmethod
    async def receive_message(self) -> AsyncGenerator[Message, None]: ...
    
    @abstractmethod
    async def send_approval_request(self, request: ApprovalRequest) -> ApprovalResponse: ...

class IMAdapter(ChannelAdapter):
    """IM渠道适配器"""
    
    def __init__(self, platform: str):  # 'telegram', 'slack', 'discord', 'wechat'
        self.platform = platform
```

**落地清单**：

| 渠道 | MVP | Beta | GA |
|---|---|---|---|
| CLI | ✅ | ✅ | ✅ |
| TUI | ✅ | ✅ | ✅ |
| Web | ❌ | ⚠️ 基础版 | ✅ 完整版 |
| Telegram | ❌ | ✅ | ✅ |
| Slack | ❌ | ✅ | ✅ |
| Discord | ❌ | ❌ | ✅ |
| 微信 | ❌ | ❌ | ✅ |

#### 5.2 权限审批机制

**设计原则**：明确的权限控制和审批流程，确保安全可控。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          权限审批机制                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 审批流程                                                                   │   │
│  │                                                                             │   │
│  │  操作请求 ──→ 风险分级 ──→ 审批判断                                        │   │
│  │                    │           │                                            │   │
│  │                    ▼           ▼                                            │   │
│  │              ┌─────────┐ ┌─────────────┐                                    │   │
│  │              │ Low     │ │  自动放行   │                                    │   │
│  │              ├─────────┤ ├─────────────┤                                    │   │
│  │              │ Medium  │ │  需审批     │ ──→ 发送审批请求                   │   │
│  │              ├─────────┤ ├─────────────┤                                    │   │
│  │              │ High    │ │  需审批     │ ──→ 发送审批 + 二次确认            │   │
│  │              ├─────────┤ ├─────────────┤                                    │   │
│  │              │Critical │ │  需审批     │ ──→ 指定审批人 + 紧急通知          │   │
│  │              └─────────┘ └─────────────┘                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 审批方式                                                                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ CLI交互      │  │ TUI弹窗      │  │ 消息通知      │                   │   │
│  │  │ (终端输入)   │  │ (界面点击)    │  │ (Telegram)    │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  审批响应: approve | reject | edit | timeout                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 六、从FactoryKit吸取的详细设计

#### 6.1 端到端闭环

**设计原则**：从Issue到验证通过的交付物，完整闭环。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          端到端闭环设计                                            │
│                                                                                     │
│  用户输入 (Issue/目标)                                                              │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 阶段1: 理解与拆解                                                          │   │
│  │   • 意图分类 → 任务拆解 → 生成DAG                                          │   │
│  │   • 输出: 执行计划 (人类可读)                                               │   │
│  │   • 用户确认: "这是你想要的吗？"                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 阶段2: 执行与协作                                                          │   │
│  │   • 多Agent协作执行 (Planner→Executor→Reviewer→Debugger)                   │   │
│  │   • 高风险操作 → 用户审批                                                   │   │
│  │   • 实时进度汇报                                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 阶段3: 验证与审查                                                          │   │
│  │   • 自动化验证 (运行测试/编译检查)                                          │   │
│  │   • Reviewer Agent质量审查                                                  │   │
│  │   • 录制执行过程 (供人工复查)                                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 阶段4: 交付                                                               │   │
│  │   • 生成PR/MR (含变更摘要、测试结果、录屏)                                 │   │
│  │   • 提交审查 (用户最终确认)                                                 │   │
│  │   • 部署到目标环境 (可选)                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 阶段5: 复盘与学习                                                          │   │
│  │   • 自动复盘 → 经验提炼 → 入库(待审)                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 6.2 沙箱隔离与凭证安全

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          沙箱隔离与凭证安全                                        │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 沙箱隔离设计                                                               │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                  云端沙箱 (每个任务独立)                            │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐          │   │   │
│  │  │  │ 临时工作目录  │  │ 隔离的网络    │  │ 受限的资源    │          │   │   │
│  │  │  │ (任务完后删除)│  │ (仅需访问)    │  │ (CPU/内存)    │          │   │   │
│  │  │  └───────────────┘  └───────────────┘  └───────────────┘          │   │   │
│  │  │                                                                     │   │   │
│  │  │  生命周期: 任务开始 → 创建 → 执行 → 清理                           │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 凭证安全设计                                                               │   │
│  │                                                                             │   │
│  │  原则: 代理不持有真实凭证，动态注入且限定范围                              │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 用户真实凭证 (Vault/环境变量)                                       │   │   │
│  │  │         │                                                          │   │   │
│  │  │         ▼                                                          │   │   │
│  │  │ 凭证管理器 (Credential Manager)                                    │   │   │
│  │  │   • 生成临时凭证                                                   │   │   │
│  │  │   • 限定权限 (仅当前任务所需)                                      │   │   │
│  │  │   • 限定时间 (任务结束后失效)                                      │   │   │
│  │  │   • 注入沙箱环境                                                   │   │   │
│  │  │         │                                                          │   │   │
│  │  │         ▼                                                          │   │   │
│  │  │ Agent执行 (只能使用临时凭证)                                      │   │   │
│  │  │   • 看不到真实凭证                                                 │   │   │
│  │  │   • 权限被严格限定                                                 │   │   │
│  │  │   • 操作被审计记录                                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 七、从pi-agent吸取的详细设计

#### 7.1 BYOK模式与本地优先

**设计原则**：用户可自带模型Key，支持完全本地部署。

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          BYOK模式与本地优先设计                                     │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ BYOK模式 (Bring Your Own Key)                                             │   │
│  │                                                                             │   │
│  │  用户可以选择:                                                              │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 选项1: 使用AI Factory内置服务                                        │   │   │
│  │  │   • 开箱即用，无需配置                                               │   │   │
│  │  │   • 按用量付费                                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 选项2: 自带Key (BYOK)                                               │   │   │
│  │  │   • 使用自己的API Key                                               │   │   │
│  │  │   • 支持: DeepSeek, OpenAI, Anthropic, Groq, OpenRouter           │   │   │
│  │  │   • 数据不出AI Factory，但调用外部API                              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 选项3: 完全本地 (Ollama)                                            │   │   │
│  │  │   • 所有模型在本地运行                                               │   │   │
│  │  │   • 代码完全不离开机器                                               │   │   │
│  │  │   • 适合敏感代码场景                                                 │   │   │
│  │  │   • 性能取决于本地硬件                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Provider配置示例                                                           │   │
│  │                                                                             │   │
│  │  # ~/.factory/providers.json                                               │   │
│  │  {                                                                          │   │
│  │    "active": "deepseek",                                                    │   │
│  │    "providers": {                                                           │   │
│  │      "deepseek": {"api_key": "sk-xxx", "model": "deepseek-chat"},          │   │
│  │      "anthropic": {"api_key": "sk-xxx", "model": "claude-3-sonnet"},       │   │
│  │      "openai": {"api_key": "sk-xxx", "model": "gpt-4"},                    │   │
│  │      "ollama": {"base_url": "http://localhost:11434", "model": "llama3"},  │   │
│  │      "openrouter": {"api_key": "sk-xxx", "model": "anthropic/claude-3"}    │   │
│  │    },                                                                       │   │
│  │    "routing": {                                                             │   │
│  │      "default": "deepseek",                                                 │   │
│  │      "complex_tasks": "anthropic",                                          │   │
│  │      "simple_tasks": "ollama",                                              │   │
│  │      "local_only": "ollama"                                                 │   │
│  │    }                                                                        │   │
│  │  }                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 7.2 MCP标准化集成

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          MCP标准化集成                                             │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ MCP (Model Context Protocol) 集成                                          │   │
│  │                                                                             │   │
│  │  通过标准MCP Server接入外部工具，无需为每个工具单独适配                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ MCP Server发现与连接                                                       │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式1: 本地配置                                                      │   │   │
│  │  │   # ~/.factory/mcp_config.json                                        │   │   │
│  │  │   {                                                                   │   │   │
│  │  │     "servers": [                                                      │   │   │
│  │  │       {"name": "github", "command": "npx", "args": ["@modelcontextprotocol/server-github"]}, │   │   │
│  │  │       {"name": "jira", "command": "npx", "args": ["@modelcontextprotocol/server-jira"]},   │   │   │
│  │  │       {"name": "docker", "command": "docker", "args": ["run", "-i", "mcp/docker"]}          │   │   │
│  │  │     ]                                                                  │   │   │
│  │  │   }                                                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式2: 自动发现                                                      │   │   │
│  │  │   • 扫描标准路径 (~/.mcp/servers/)                                   │   │   │
│  │  │   • 发现后自动注册                                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 方式3: 动态注册                                                      │   │   │
│  │  │   • 工厂模板自带MCP配置                                              │   │   │
│  │  │   • 实例化时自动注册                                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 工具统一接口                                                                │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Tool Registry                                                        │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                      │   │   │
│  │  │  │ 内置工具   │  │ Skill     │  │ MCP工具   │                      │   │   │
│  │  │  │ (read_file)│  │ (analyze) │  │ (GitHub)  │                      │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘                      │   │   │
│  │  │                                                                     │   │   │
│  │  │  所有工具通过统一接口调用:                                          │   │   │
│  │  │  tool_registry.call("github.create_pr", params)                    │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 八、整合：AI Factory完整定位总结

#### 8.1 最终定位

> **AI Software Factory = 从"Agent"到"AI组织"的跃迁**

| 维度 | DeepSeek Harness | Hermes | OpenClaw | FactoryKit | **AI Factory** |
|---|---|---|---|---|---|
| **身份** | Agent工作台 | 自进化Agent | 网关 | 企业服务 | **AI组织操作系统** |
| **核心能力** | 调度 | 学习 | 连接 | 闭环 | **组织治理+学习+协作** |
| **管理范围** | 单次任务 | 单Agent | 消息路由 | 单项目 | **跨项目/跨Agent/跨任务** |
| **学习范围** | ❌ | 个体 | ❌ | ❌ | **组织级学习** |
| **行业覆盖** | 编程 | 编程 | 编程/自动化 | 编程 | **全行业工厂化** |

#### 8.2 竞品优势吸收清单

| 来源 | 吸收的能力 | AI Factory落地方式 |
|---|---|---|
| DeepSeek Harness | 插件化架构、子Agent收编 | PluginRegistry + AgentAdapter |
| Hermes | 自学习闭环、分层记忆、用户画像、GEPA | LearnerAgent + 4层记忆 + UserProfile + Skill进化 |
| OpenClaw | 多渠道集成、权限审批 | ChannelAdapter + ApprovalFlow |
| FactoryKit | 端到端闭环、沙箱隔离、凭证安全 | 5阶段闭环 + Sandbox + CredentialManager |
| pi-agent | BYOK、本地优先、MCP | ProviderConfig + Ollama + MCPRegistry |

#### 8.3 核心差异化

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          AI Factory 核心差异化                                      │
│                                                                                     │
│  1. 组织级治理                                                                      │
│     └── 不仅是审计，而是完整的治理体系（成本+权限+合规+风险+安全）                │
│                                                                                     │
│  2. 组织级学习                                                                      │
│     └── 不仅是单Agent学习，而是跨Agent、跨项目、跨任务的经验沉淀                   │
│                                                                                     │
│  3. 跨行业工厂化                                                                    │
│     └── 不仅是软件开发，而是任何行业的"一键AI化"                                   │
│                                                                                     │
│  4. 插件化无绑定                                                                    │
│     └── 不绑定任何模型、工具、Agent、基础设施，全部可替换                          │
│                                                                                     │
│  5. 端到端闭环                                                                      │
│     └── 从Issue到验证通过的交付物，完整闭环                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

*本文档用于补充AI Factory主设计文档，详细说明从竞品吸收的设计元素及落地方式。*


---


### 九、竞品优势吸收 × 实现状态（每项吸收到底落地没有）★

> 2026-08-22 补充: 吸收设计不空谈——逐项核对真实实现，标注 🚧/📐 与里程碑。

| 吸收项（来源） | 设计（§十六 章节） | 实现状态 |
|---|---|---|
| 一切皆插件（DeepSeek Harness） | 3.1 插件接口标准 | 🚧 部分（MCP 协议+Registry 有；统一插件规范 §2.11 待 M2） |
| 子 Agent 收编（DeepSeek） | 3.2 | 📐 M2（AgentEntity/Registry） |
| 自学习闭环（Hermes） | 4.1 | 🚧（memory 提取 ✅；闭环 M4） |
| 四层记忆（Hermes） | 4.2 | 🚧（经验库 = L1-L2 雏形；画像/组织记忆 M4） |
| 用户画像建模（Hermes） | 4.3 | 📐 M4 |
| Skill 自动进化 GEPA（Hermes） | 4.4 | 📐 M4 |
| 多渠道集成（OpenClaw） | 5.1 | 🚧（工具发现 ✅；消息平台 P0 M5） |
| 权限审批（OpenClaw） | 5.2 | ✅ 已实现（三道门 §6.3） |
| 端到端闭环（FactoryKit） | 6.1 | ✅ 已实现（M1 repo/证据/审批/清道夫） |
| 沙箱隔离与凭证安全（FactoryKit） | 6.2 | ✅ 已实现（sandbox + env 引用） |
| BYOK 本地优先（pi-agent） | 7.1 | 🚧（provider 支持；本地 LLM §18.9 📐） |
| MCP 标准化（pi-agent） | 7.2 | ✅ 已实现（StdioMCPClient，M1） |

**结论**：12 项吸收中 **4 项已实现**（权限/闭环/沙箱/MCP）、5 项部分（插件/学习/记忆/渠道/BYOK）、3 项设计（收编/画像/GEPA）——吸收不是口号，已落地近半，其余排 M2/M4/M5。

## 十七、自我进化体系专项设计

> 2026-08-21 补充: 五维自我进化能力 (自我学习/自我监控/自我完善/自我发现/自我修复) 的设计与实现路径 — AI Factory 核心差异化。
> 编号说明（2026-08-23 审计标注）: 本节前 9 小节用中文编号（一~九：总览/学习/监控/完善/发现/修复/联动/竞品/优先级），第 10 小节起为代码锚点与细化规划（17.10-17.17）——17.1-17.9 不存在是有意为之，非缺失。


> 本文档补充AI Factory的核心差异化能力：**自我学习、自我监控、自我完善、自我发现、自我修复**。这是从"被动执行"到"主动进化"的关键跃迁，也是AI Factory区别于所有竞品的核心护城河。

---

### 一、五维自我进化能力总览

#### 1.1 能力全景

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         五维自我进化能力全景                                        │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        自我学习 (Self-Learning)                            │   │
│  │  从经验中提炼知识，让系统越来越聪明                                        │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ 任务复盘    │  │ 模式提取    │  │ Skill生成   │  │ 知识沉淀    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        自我监控 (Self-Monitoring)                          │   │
│  │  实时感知自身状态，主动发现问题                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ 健康检查    │  │ 性能监控    │  │ 成本监控    │  │ 异常检测    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        自我完善 (Self-Improvement)                        │   │
│  │  基于监控发现，主动优化自身                                                │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ 性能优化    │  │ 成本优化    │  │ 质量优化    │  │ 架构演进    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        自我发现 (Self-Discovery)                          │   │
│  │  主动探索新机会，预见潜在问题                                              │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ 能力边界探测│  │ 机会识别    │  │ 风险预警    │  │ 趋势感知    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        自我修复 (Self-Healing)                            │   │
│  │  检测到问题后自动恢复，无需人工干预                                        │   │
│  │                                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │   │
│  │  │ 任务自愈    │  │ 系统自愈    │  │ 配置自愈    │  │ 回滚自愈    │      │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        五维联动机制                                          │   │
│  │                                                                             │   │
│  │  自我监控 ──发现异常──→ 自我修复 ──修复完成──→ 自我学习 ──优化经验──→ 自我完善 │   │
│  │      │                                                                      │   │
│  │      └──发现瓶颈──→ 自我完善 ──优化完成──→ 自我发现 ──探索新边界──→ 自我学习   │   │
│  │                                                                             │   │
│  │  每个维度都不是孤立的，而是形成闭环进化飞轮                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 1.2 与竞品的本质区别

| 能力 | Claude Code | DeepSeek Harness | Hermes | OpenClaw | **AI Factory** |
|---|---|---|---|---|---|
| 自我学习 | 有限（会话内） | 有限 | ✅ 核心能力 | ❌ | ✅ **组织级** |
| 自我监控 | ❌ | 有限 | ❌ | ❌ | ✅ **系统级** |
| 自我完善 | ❌ | ❌ | ❌ | ❌ | ✅ **主动优化** |
| 自我发现 | ❌ | ❌ | ❌ | ❌ | ✅ **主动探索** |
| 自我修复 | 有限（重试） | 有限（重试） | ❌ | ❌ | ✅ **自动恢复** |

**核心差异**：竞品多为"被动响应"，AI Factory是"主动进化"。


### 二、自我学习 (Self-Learning) —— 详细设计

#### 2.1 学习层次与闭环

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          自我学习闭环（详细）                                      │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        执行层                                              │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  任务执行     │  │  Agent协作    │  │  工具调用     │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        数据采集层                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 执行轨迹采集  │  │ 决策链采集    │  │ 结果采集      │                   │   │
│  │  │ (每步操作)   │  │ (为什么)     │  │ (成功/失败)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 成本采集     │  │ 时间采集      │  │ 用户反馈采集  │                   │   │
│  │  │ (Token/费用) │  │ (耗时)       │  │ (评分/评价)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        分析提炼层（Learner Agent）                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 1. 成功分析                                                          │   │   │
│  │  │    • 哪些决策导致了成功？                                            │   │   │
│  │  │    • 成功的关键因素是什么？                                          │   │   │
│  │  │    • 可以复用的模式是什么？                                          │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 2. 失败分析                                                          │   │   │
│  │  │    • 失败的根本原因是什么？                                          │   │   │
│  │  │    • 哪些决策导致了失败？                                            │   │   │
│  │  │    • 下次如何避免？                                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 3. 差异分析                                                          │   │   │
│  │  │    • 成功与失败案例的关键差异是什么？                                │   │   │
│  │  │    • 不同场景的最佳策略是什么？                                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 4. 模式提取                                                          │   │   │
│  │  │    • 识别重复出现的问题模式                                          │   │   │
│  │  │    • 提取通用的解决方案模式                                          │   │   │
│  │  │    • 构建模式库                                                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        知识产出层                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 成功模式      │  │ 失败教训      │  │ 领域知识      │                   │   │
│  │  │ (可复用)     │  │ (要避免)     │  │ (可学习)     │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ Skill模板     │  │ 工作流模板    │  │ 决策规则      │                   │   │
│  │  │ (可复用)     │  │ (可复用)     │  │ (可应用)     │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        审查激活层                                            │   │
│  │                                                                             │   │
│  │  自动验证 → 人工审查 → 经验激活 → 注入系统                                 │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2 学习深度层次

| 层次 | 名称 | 说明 | 示例 |
|---|---|---|---|
| L1 | 任务级学习 | 本次任务踩了什么坑、做对了什么 | "NPE修复中，先看堆栈再定位代码成功率更高" |
| L2 | 模式级学习 | 这类问题的通用解决模式 | "诊断内存泄漏的标准流程：heap dump→引用链→代码定位" |
| L3 | Skill级学习 | 可固化为Skill的操作模式 | "analyze_memory_leak_v3 Skill" |
| L4 | 流程级学习 | 工作流/协作模式的优化 | "Bug修复流程从5步优化为4步" |
| L5 | 战略级学习 | 组织架构/治理规则的优化 | "发现Executor Agent经常超载，需要拆分" |

#### 2.3 学习触发条件

| 触发条件 | 时机 | 优先级 |
|---|---|---|
| 任务完成 | 每次任务结束后 | 高 |
| 任务失败 | 任务失败后 | 最高 |
| 用户评分低 | 用户评分 < 3/5 | 最高 |
| 异常检测 | 检测到异常模式 | 高 |
| 定期触发 | 每N个任务 | 中 |
| 用户主动 | 用户命令"复盘" | 高 |


### 三、自我监控 (Self-Monitoring) —— 详细设计

#### 3.1 监控架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          自我监控架构                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         监控维度                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  健康监控     │  │  性能监控     │  │  成本监控     │                   │   │
│  │  │  (Health)    │  │  (Performance)│  │  (Cost)      │                   │   │
│  │  │              │  │               │  │              │                   │   │
│  │  │ • 系统状态   │  │ • 响应时间    │  │ • Token消耗   │                   │   │
│  │  │ • 组件可用性 │  │ • 吞吐量     │  │ • API费用    │                   │   │
│  │  │ • 错误率     │  │ • 并发数     │  │ • 资源使用   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  质量监控     │  │  安全监控     │  │  行为监控     │                   │   │
│  │  │  (Quality)   │  │  (Security)   │  │  (Behavior)   │                   │   │
│  │  │              │  │               │  │              │                   │   │
│  │  │ • 任务成功率 │  │ • 异常访问    │  │ • Agent行为   │                   │   │
│  │  │ • 产出质量   │  │ • 敏感操作    │  │ • 协作效率   │                   │   │
│  │  │ • 用户满意度 │  │ • 凭证安全    │  │ • 决策质量   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         监控执行层                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 1. 指标采集                                                        │   │   │
│  │  │    • 实时拉取指标                                                   │   │   │
│  │  │    • 事件驱动采集                                                   │   │   │
│  │  │    • 定期采样                                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 2. 异常检测                                                        │   │   │
│  │  │    • 静态阈值告警                                                   │   │   │
│  │  │    • 动态基线检测                                                   │   │   │
│  │  │    • 趋势异常检测                                                   │   │   │
│  │  │    • 模式异常检测                                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 3. 告警分级                                                        │   │   │
│  │  │    • CRITICAL: 系统不可用 → 立即通知                                │   │   │
│  │  │    • WARNING: 性能下降 → 通知+记录                                  │   │   │
│  │  │    • INFO: 状态变化 → 记录                                          │   │   │
│  │  │    • DEBUG: 详细信息 → 仅日志                                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         监控存储                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 指标时序库    │  │ 事件日志      │  │ 告警记录      │                   │   │
│  │  │ (Prometheus)  │  │ (Elasticsearch)│  │ (AlertManager)│                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 3.2 关键监控指标

#### 健康指标

| 指标 | 说明 | 告警阈值 | 检查频率 |
|---|---|---|---|
| `system_status` | 系统整体状态 | != "healthy" | 1分钟 |
| `components_availability` | 各组件可用性 | < 99.9% | 1分钟 |
| `llm_availability` | LLM API可用性 | < 95% | 1分钟 |
| `memory_usage` | 内存使用率 | > 80% | 1分钟 |
| `disk_usage` | 磁盘使用率 | > 80% | 5分钟 |

#### 性能指标

| 指标 | 说明 | 告警阈值 | 检查频率 |
|---|---|---|---|
| `task_duration_p95` | 任务P95耗时 | > 30分钟 | 任务级 |
| `task_duration_p99` | 任务P99耗时 | > 60分钟 | 任务级 |
| `llm_response_p95` | LLM P95响应 | > 10秒 | 请求级 |
| `agent_queue_length` | Agent队列长度 | > 10 | 1分钟 |
| `concurrent_tasks` | 并发任务数 | > 5 | 1分钟 |

#### 成本指标

| 指标 | 说明 | 告警阈值 | 检查频率 |
|---|---|---|---|
| `daily_cost` | 日成本 | > 预算日限额 | 小时 |
| `monthly_cost` | 月成本 | > 预算月限额 | 天 |
| `task_avg_cost` | 任务平均成本 | > 1美元 | 任务级 |
| `cost_per_agent` | 各Agent成本占比 | 单Agent > 40% | 天 |

#### 质量指标

| 指标 | 说明 | 告警阈值 | 检查频率 |
|---|---|---|---|
| `task_success_rate` | 任务成功率 | < 85% | 窗口级 |
| `user_satisfaction` | 用户满意度 | < 3.5/5 | 任务级 |
| `review_score_avg` | 审查平均分 | < 70/100 | 窗口级 |
| `retry_rate` | 重试率 | > 20% | 窗口级 |

#### 3.3 异常检测算法

```python
#### 异常检测策略
class AnomalyDetector:
    """多策略异常检测"""
    
    def __init__(self):
        self.strategies = [
            StaticThresholdStrategy(),      # 静态阈值
            DynamicBaselineStrategy(),       # 动态基线
            TrendAnomalyStrategy(),          # 趋势异常
            PatternAnomalyStrategy(),        # 模式异常
            SeasonalityStrategy(),           # 季节性异常
        ]
    
    def detect(self, metric: str, value: float, context: Dict) -> AnomalyResult:
        """综合多策略检测"""
        results = []
        for strategy in self.strategies:
            result = strategy.detect(metric, value, context)
            results.append(result)
        
        # 投票决策
        return self._vote(results)


class DynamicBaselineStrategy:
    """动态基线检测"""
    
    def __init__(self, window: int = 100):
        self.history = []
        self.window = window
    
    def detect(self, metric: str, value: float, context: Dict) -> AnomalyResult:
        self.history.append(value)
        if len(self.history) > self.window:
            self.history.pop(0)
        
        if len(self.history) < 10:
            return AnomalyResult(is_anomaly=False)
        
        mean = sum(self.history) / len(self.history)
        std = self._calc_std(self.history, mean)
        
        # 3-sigma 规则
        is_anomaly = abs(value - mean) > 3 * std
        return AnomalyResult(
            is_anomaly=is_anomaly,
            score=abs(value - mean) / (std + 0.001),
            mean=mean,
            std=std
        )
```


### 四、自我完善 (Self-Improvement) —— 详细设计

#### 4.1 完善闭环

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          自我完善闭环                                              │
│                                                                                     │
│  自我监控发现瓶颈/问题                                                              │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 问题分析                                                           │   │
│  │   • 问题是什么？为什么发生？                                               │   │
│  │   • 影响范围有多大？                                                       │   │
│  │   • 根本原因是什么？                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: 方案生成                                                           │   │
│  │   • 生成多个优化方案                                                       │   │
│  │   • 评估每个方案的风险/收益                                                │   │
│  │   • 选择最优方案                                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: 方案审批                                                           │   │
│  │   • 低风险优化 → 自动执行                                                │   │   │
│  │   • 中风险优化 → 通知用户后执行                                        │   │   │
│  │   • 高风险优化 → 请求用户审批                                            │   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 4: 方案执行                                                           │   │
│  │   • 执行优化操作                                                           │   │
│  │   • 记录执行过程                                                           │   │
│  │   • 回滚准备                                                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 5: 效果验证                                                           │   │
│  │   • 验证问题是否解决                                                       │   │
│  │   • 评估是否有副作用                                                       │   │
│  │   • 记录优化效果                                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│       │                                                                             │
│       ▼                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ Step 6: 经验沉淀                                                           │   │
│  │   • 记录优化过程                                                           │   │
│  │   • 提炼可复用的优化模式                                                   │   │
│  │   • 注入学习系统                                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 4.2 自我完善场景

| 场景 | 触发条件 | 优化动作 | 风险级别 |
|---|---|---|---|
| **性能优化** | 任务耗时 > 阈值 | 调整并行度、切换模型、优化Prompt | 中 |
| **成本优化** | 成本 > 阈值 | 模型路由优化、缓存策略、批量处理 | 中 |
| **质量优化** | 成功率 < 阈值 | 优化拆解策略、增加审查环节 | 高 |
| **资源配置** | 资源使用率 > 阈值 | 扩容、负载均衡、任务调度优化 | 低 |
| **流程优化** | 协作效率低 | 调整Agent分工、优化协作模式 | 高 |
| **知识优化** | 经验冲突/过时 | 更新知识库、废弃旧经验 | 低 |

#### 4.3 完善效果追踪

```python
class ImprovementTracker:
    """优化效果追踪器"""
    
    def track(self, improvement: Improvement) -> None:
        """记录优化操作"""
        self.store.save({
            "id": improvement.id,
            "type": improvement.type,
            "trigger": improvement.trigger,
            "action": improvement.action,
            "risk_level": improvement.risk_level,
            "status": "pending" | "executing" | "done" | "rolled_back" | "failed",
            "duration_ms": improvement.duration,
            "before_metrics": improvement.before,
            "after_metrics": improvement.after,
            "improvement_rate": improvement.improvement_rate,
            "side_effects": improvement.side_effects,
            "learned_lesson": improvement.lesson,
        })
    
    def analyze_effectiveness(self) -> EffectivenessReport:
        """分析优化有效性"""
        improvements = self.store.query_all()
        return {
            "total_count": len(improvements),
            "success_rate": self._calc_success_rate(improvements),
            "avg_improvement": self._calc_avg_improvement(improvements),
            "best_improvement": self._find_best(improvements),
            "failure_analysis": self._analyze_failures(improvements),
            "recommendations": self._generate_recommendations(improvements),
        }
```


### 五、自我发现 (Self-Discovery) —— 详细设计

#### 5.1 发现架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          自我发现架构                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         发现方向                                            │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 1. 能力边界探测                                                      │   │   │
│  │  │    • 当前能力能解决什么问题？                                       │   │   │
│  │  │    • 能力边界在哪里？                                               │   │   │
│  │  │    • 需要哪些新能力？                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 2. 机会识别                                                          │   │   │
│  │  │    • 哪些新场景可以用AI Factory解决？                               │   │   │
│  │  │    • 哪些流程可以自动化？                                           │   │   │
│  │  │    • 哪些痛点用户还没有提到？                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 3. 风险预警                                                          │   │   │
│  │  │    • 哪些模式正在恶化？                                             │   │   │
│  │  │    • 哪些隐患可能爆发？                                             │   │   │
│  │  │    • 哪些趋势需要关注？                                             │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 4. 趋势感知                                                          │   │   │
│  │  │    • 技术趋势：新模型、新工具                                       │   │   │
│  │  │    • 用户趋势：使用模式变化                                         │   │   │
│  │  │    • 行业趋势：新场景、新需求                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         发现机制                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 数据分析      │  │ 实验探索      │  │ 用户反馈      │                   │   │
│  │  │ (挖掘模式)   │  │ (A/B测试)    │  │ (收集需求)   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 社区监控      │  │ 技术扫描      │  │ 自我实验      │                   │   │
│  │  │ (竞品/趋势)  │  │ (新工具/模型) │  │ (探索新能力) │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         发现输出                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │ 发现报告      │  │ 建议清单      │  │ 预警通知      │                   │   │
│  │  │ (结构化)     │  │ (可执行)     │  │ (及时)       │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 5.2 发现触发机制

| 触发类型 | 频率 | 说明 | 输出 |
|---|---|---|---|
| **定期扫描** | 每天 | 分析历史数据，发现模式 | 发现报告 |
| **异常驱动** | 事件触发 | 异常发生时，探索原因 | 根因+改进建议 |
| **用户驱动** | 按需 | 用户主动要求"探索新能力" | 探索结果 |
| **外部触发** | 事件触发 | 新工具/模型发布时 | 集成建议 |
| **边界探测** | 每周 | 主动测试能力边界 | 能力报告 |

#### 5.3 发现输出示例

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ 发现报告 #2026-08-21                                                            │
│                                                                                     │
│ 📊 数据分析发现:                                                                  │
│   • 用户任务中 30% 涉及"数据库优化"，但当前Skill未覆盖                           │
│   • 失败任务中 40% 发生在"代码审查"阶段                                          │
│   • 用户投诉中 25% 提到"响应时间慢"                                              │
│                                                                                     │
│ 🚀 机会识别:                                                                      │
│   • 新场景: "数据库优化" 可以成为新的Skill                                        │
│   • 新流程: "代码审查" 阶段需要引入更严格的检查                                   │
│   • 新工具: 可以接入 "sql-analyzer" 工具提升优化能力                             │
│                                                                                     │
│ ⚠️ 风险预警:                                                                      │
│   • 趋势: 模型成本正在上升，建议引入模型路由优化                                  │
│   • 隐患: Agent队列长度增长趋势，可能影响吞吐量                                   │
│   • 边界: 当前无法处理 > 1000行的大文件                                          │
│                                                                                     │
│ 📌 建议清单:                                                                      │
│   • [P0] 开发"数据库优化"Skill                                                    │
│   • [P1] 增强"代码审查"阶段的检查规则                                             │
│   • [P1] 接入"sql-analyzer"工具                                                   │
│   • [P2] 优化模型路由策略                                                         │
│   • [P2] 实现大文件分片处理                                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 六、自我修复 (Self-Healing) —— 详细设计

#### 6.1 修复架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          自我修复架构                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         修复类型                                            │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                   │   │
│  │  │  任务自愈     │  │  系统自愈     │  │  配置自愈     │                   │   │
│  │  │  (Task)      │  │  (System)     │  │  (Config)     │                   │   │
│  │  │              │  │               │  │              │                   │   │
│  │  │ • 失败重试   │  │ • 服务重启   │  │ • 配置回滚   │                   │   │
│  │  │ • 降级执行   │  │ • 资源恢复   │  │ • 重新加载   │                   │   │
│  │  │ • 换策略     │  │ • 连接重建   │  │ • 校验修复   │                   │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘                   │   │
│  │                                                                             │   │
│  │  ┌───────────────┐  ┌───────────────┐                                      │   │
│  │  │  数据自愈     │  │  状态自愈     │                                      │   │
│  │  │  (Data)      │  │  (State)      │                                      │   │
│  │  │              │  │               │                                      │   │
│  │  │ • 数据修复   │  │ • 状态恢复   │                                      │   │
│  │  │ • 缓存重建   │  │ • 事务补偿   │                                      │   │
│  │  └───────────────┘  └───────────────┘                                      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         修复流程                                            │   │
│  │                                                                             │   │
│  │  检测到问题                                                                   │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 1: 问题分类                                                      │   │   │
│  │  │   • 这个问题的类型是什么？                                           │   │   │
│  │  │   • 严重程度如何？                                                   │   │   │
│  │  │   • 影响范围有多大？                                                 │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 2: 修复策略选择                                                  │   │   │
│  │  │   • 是否有已知修复方案？                                             │   │   │
│  │  │   • 是否需要用户介入？                                               │   │   │
│  │  │   • 能否自动修复？                                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 3: 修复执行                                                      │   │   │
│  │  │   • 执行修复操作                                                     │   │   │
│  │  │   • 监控修复过程                                                     │   │   │
│  │  │   • 记录修复日志                                                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 4: 修复验证                                                      │   │   │
│  │  │   • 问题是否解决？                                                   │   │   │
│  │  │   • 是否有副作用？                                                   │   │   │
│  │  │   • 是否需要回滚？                                                   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │       │                                                                       │   │
│  │       ▼                                                                       │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ Step 5: 学习沉淀                                                      │   │   │
│  │  │   • 记录修复过程                                                     │   │   │
│  │  │   • 提炼修复模式                                                     │   │   │
│  │  │   • 预防类似问题                                                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 6.2 修复策略决策树

```
问题检测
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 问题分类                                                                   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 类型: 任务失败                                                       │   │
│  │   ├── 瞬时失败 (网络超时/限流) → 自动重试 (3次)                    │   │
│  │   ├── 逻辑失败 (LLM错误) → 换模型/换策略                           │   │
│  │   ├── 资源失败 (内存不足) → 降级执行/通知用户                      │   │
│  │   └── 安全失败 (权限不足) → 立即停止/请求审批                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 类型: 系统异常                                                       │   │
│  │   ├── 服务无响应 → 健康检查 → 自动重启                             │   │
│  │   ├── 连接断开 → 重连 → 重建连接池                                 │   │
│  │   ├── 资源耗尽 → 清理→ 扩容                                         │   │
│  │   └── 配置错误 → 回滚到上一版本                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 类型: 数据异常                                                       │   │
│  │   ├── 数据不一致 → 事务回滚 → 补偿                                  │   │
│  │   ├── 数据损坏 → 从备份恢复                                          │   │
│  │   ├── 缓存失效 → 重建缓存                                            │   │
│  │   └── 索引损坏 → 重建索引                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 6.3 修复效果评估

| 评估维度 | 指标 | 目标 |
|---|---|---|
| **修复成功率** | 自动修复成功 / 总修复尝试 | > 90% |
| **修复速度** | 从检测到修复完成平均时间 | < 30秒 |
| **误修复率** | 不必要修复 / 总修复 | < 5% |
| **副作用率** | 修复导致新问题 / 总修复 | < 2% |
| **用户满意度** | 用户对自动修复的评价 | > 4/5 |


### 七、五维联动与进化飞轮

#### 7.1 进化飞轮

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          五维进化飞轮                                              │
│                                                                                     │
│                              ┌─────────────────┐                                   │
│                              │   自我学习       │                                   │
│                              │  (Learning)     │                                   │
│                              │  积累经验知识    │                                   │
│                              └────────┬────────┘                                   │
│                                       │                                            │
│          ┌────────────────────────────┼────────────────────────────┐              │
│          │                            │                            │              │
│          ▼                            ▼                            ▼              │
│  ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐       │
│  │   自我发现       │        │   自我完善       │        │   自我修复       │       │
│  │  (Discovery)   │◄───────│  (Improvement)   │◄───────│  (Healing)      │       │
│  │  探索新机会     │        │  优化自身能力    │        │  恢复系统健康    │       │
│  └─────────────────┘        └─────────────────┘        └─────────────────┘       │
│          │                            │                            │              │
│          └────────────────────────────┼────────────────────────────┘              │
│                                       │                                            │
│                                       ▼                                            │
│                              ┌─────────────────┐                                   │
│                              │   自我监控       │                                   │
│                              │  (Monitoring)   │                                   │
│                              │  感知系统状态    │                                   │
│                              └─────────────────┘                                   │
│                                       │                                            │
│                                       ▼                                            │
│                          ┌─────────────────────────┐                              │
│                          │  发现问题 → 触发修复    │                              │
│                          │  发现机会 → 触发完善    │                              │
│                          │  新经验 → 触发学习      │                              │
│                          │  学习成果 → 触发发现    │                              │
│                          └─────────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

#### 7.2 五维联动场景

| 场景 | 触发维度 | 联动维度 | 效果 |
|---|---|---|---|
| **任务失败率突增** | 自我监控（异常检测） | 自我修复（自动处理）→ 自我学习（总结经验）→ 自我完善（优化流程） | 失败率回归正常 |
| **新场景出现** | 自我发现（机会识别） | 自我学习（积累知识）→ 自我完善（新增能力） | 能力边界扩展 |
| **成本持续上升** | 自我监控（成本告警） | 自我完善（优化路由）→ 自我学习（沉淀策略） | 成本回归合理 |
| **用户满意度下降** | 自我监控（质量告警） | 自我发现（根因分析）→ 自我完善（质量提升）→ 自我学习（沉淀经验） | 满意度提升 |
| **系统性能退化** | 自我监控（性能告警） | 自我修复（自动恢复）→ 自我完善（性能优化） | 性能恢复 |


### 八、与竞品的本质区别总结

| 能力 | 竞品 | AI Factory | 本质差异 |
|---|---|---|---|
| **自我学习** | 会话内/单Agent学习 | **组织级跨任务学习** | 从个体到组织 |
| **自我监控** | 有限/不存在 | **系统级多维监控** | 从被动到主动 |
| **自我完善** | 不存在 | **自动优化闭环** | 从静态到动态 |
| **自我发现** | 不存在 | **主动探索机制** | 从响应到前瞻 |
| **自我修复** | 简单重试 | **智能自愈体系** | 从恢复到达尔文式进化 |


### 九、落地优先级

| 能力 | MVP | Beta | GA | 说明 |
|---|---|---|---|---|
| 自我学习 | ⚠️ 基础复盘 | ✅ 完整闭环 | ✅ 组织级学习 | 先做任务级复盘 |
| 自我监控 | ⚠️ 基础指标 | ✅ 多维监控 | ✅ 智能异常检测 | 先做核心指标 |
| 自我完善 | ❌ | ⚠️ 简单优化 | ✅ 完整闭环 | 先做低风险优化 |
| 自我发现 | ❌ | ❌ | ✅ 完整能力 | 最后实现 |
| 自我修复 | ⚠️ 失败重试 | ✅ 任务级自愈 | ✅ 系统级自愈 | 先做任务级 |

---

*本文档补充AI Factory主设计文档，详细说明五维自我进化能力的设计与实现路径。*


---

### 17.10 五维自我进化 × 代码锚点（2026-08-22）

| 维 | 真实实现 | 状态 |
|---|---|---|
| 自我学习 | `console/memory/`（experience/extraction/learning/retrieval） | ✅ 存储/检索，闭环 📐 |
| 自我监控 | `session/observability.py` + `audit/`（事后查询） | ✅ 事后，实时告警 📐 |
| 自我完善 | `exec/evaluator.py`（5 层评分） | ✅ 评分，回写决策 📐 |
| 自我发现 | `session/tools.py`（AI CLI + MCP 发现） | ✅ |
| 自我修复 | `session/replanning.py` + `quality.py`（repair） | ✅ |

**完成度**：五维**单点全部已实现**（✅）；五维**闭环接线**（画像/决策引用/回写/护栏）待 M4。


### 17.11 自我学习详细规划（学什么 / 来源 / 流程 / 触发 / 反馈）★

> 2026-08-22 补充（用户指出缺详细规划）: 自我学习从概念到可落地。

**学什么**

| 对象 | 内容 | 存储 |
|---|---|---|
| 经验 | 成功/失败模式（任务/工具/成本/失败原因） | memory/experience |
| Agent 画像 | 成功率/质量/成本/速度（滑动窗口） | agents/AgentMetrics |
| 决策模式 | 审批/重规划决策 + 理由 | decision 链 |
| 知识 | 从执行产物提炼的规则/关系 | 知识图谱（§19，M5） |

**流程**（提取 ✅ → 聚合 → 校验 → 可检索）

```
执行完成/失败 → 提取（memory/extraction ✅ 已有）
  → 存储经验库 → 聚合画像 → 可信度校验（样本<5 不计权 §7.5）
  → 可供检索（RAG §8.5）
```

**触发**：任务完成（自动）· 审批决策（E5）· 修复完成（§17.13）· 用户纠错

**反馈**：学习结果 → 影响下次决策（经 §17.12 检索+判断回路）

**落地**：提取/存储 ✅；画像聚合/可信度/反馈闭环 📐 M4

### 17.12 自我检索 + 判断 + 学习（决策回路）详细规划 ★

> 用户点名：这是"越用越聪明"的核心——**决策时检索相关经验 → 判断 → 执行 → 学习回填**。

**回路流程**

```
新任务 → 特征化（类型/工具/目标）
  → 检索（RAG 档1-4 + 知识图谱）：相似历史（成功/失败/成本）
  → 判断：相似度匹配 + 参考成功率 + 成本评估 + 风险标注
  → 决策：采用（参考历史方案）/ 调整 / 放弃（证据+理由可审计）
  → 执行 → 结果（成功/失败/成本/耗时）
  → 学习回填：更新案例置信度 / Agent 画像（成功+1/失败+1）
```

**机制明细**

| 环节 | 机制 | 状态 |
|---|---|---|
| 检索 | 经验库检索（memory/retrieval） | ✅ 已有 |
| 判断 | 相似度 + 成功率参考 + 成本/风险评估 | 📐 M4 |
| 决策可审计 | decision_created 事件 + 引用哪些经验（source） | 📐 M4 |
| 学习回填 | 结果 → 画像/案例置信度更新 | 📐 M4 |
| 护栏 | 低样本不计权 / 学习开关 / 预算上限（§7.3/C5） | 📐 M4 |

**落地**：检索 ✅；判断回路/回填/护栏 📐 M4（待办清单 M4-1/4-2）

### 17.13 自我修复详细规划（检测 → 诊断 → 策略 → 应用 → 验证 → 学习）★

**流程**

```
失败检测（任务失败/测试失败/监控告警 critical §5.8）
  → 根因诊断（classify_failure ✅ 已有：超时/校验/补丁/LLM）
  → 策略选择：重试（快）→ 修 patch → 重规划（§6.2）→ 换 Agent（§4.8）→ 人工（风险高）
  → 应用 → 验证（测试/验收）→ 通过→继续；失败→升级策略
  → 学习：失败模式 + 修复策略入库（§17.11），下次更快
```

**策略决策树（已有 + 增强）**

```
失败 → 重试（1-3 次）→ 仍败 → 根因诊断
  ├─ LLM/网络 → 切 provider / 降级（§T5）
  ├─ 补丁问题 → 重新生成 patch（DeveloperAgent）
  ├─ 计划问题 → ReplanningEngine（8 决策 ✅）
  ├─ Agent 不匹配 → 换 Agent（AgentMatcher ✅）
  └─ 风险高/反复 → 人工介入（ReviewGate）
```

**落地**：检测/重试/重规划/换Agent ✅；根因→策略智能映射（LLM）+ 修复效果学习 📐 M4

### 17.14 自我能力全景（六种，状态汇总）★

| 自我能力 | 现状 | 落地 |
|---|---|---|
| 自我监控 | 采集 ✅（§5.8）；实时指标/告警 📐 | M5 |
| 自我发现 | 工具发现 ✅（session/tools） | ✅ |
| 自我完善 | 评价 ✅（evaluator）；回写决策 📐 | M4 |
| 自我学习 | 提取/存储 ✅（memory）；闭环 📐 | M4 |
| 检索+判断+学习 | 检索 ✅；回路 📐 | M4 |
| 自我修复 | 基础 ✅（repair/replan）；智能诊断 📐 | M4 |

**结论**：六种自我能力**单点大多已实现**（✅），缺的是**闭环接线**（M4 自我提升闭环统一落地：检索判断 → 学习回填 → 修复学习 → 画像驱动）。


### 17.15 学习 vs 训练（当前不训练；何时才需要训练）★

> 2026-08-22 补充（用户提问）: 明确"自我学习"与"LLM 训练"的关系——**当前学习 ≠ 训练**，
> 训练是数据积累到一定程度后的可选升级，不是必要条件。

#### 17.15.1 本质区别

| | 学习 Learning（当前） | 训练 Training（未来可选） |
|---|---|---|
| 改什么 | **系统知识/画像/编排**（模型权重不动） | **模型权重**（参数更新） |
| 成本 | 低（存储 + 检索） | 高（GPU / 数据管道） |
| 生效 | 即时（执行后立即可用） | 慢（批量 / 离线） |
| 可控 | 易（回滚知识/画像） | 难（模型版本化 + 评估门 + 回滚） |
| 当前状态 | ✅ 部分实现（提取/检索/画像） | 📐 未做 |

#### 17.15.2 当前"学习"的实质（三层，都不动模型）

```
上下文级: RAG 检索经验/知识 → 进上下文（§8.5）
系统级:   Agent 画像 → 分配/预算/排序（§4.8/4.9）
编排级:   提示/计划/决策引用优化（§17.12 决策回路）
→ 模型权重从未改变 → "系统在变聪明"，不是"模型在变聪明"
```

#### 17.15.3 何时才需要训练（前置条件）

| 触发信号 | 说明 |
|---|---|
| 数据飞轮成熟（§4.9） | 高质量数据（成功/失败/审批/纠错）积累足够 |
| 同类型任务重复率高 | 值得为"领域专家模型"投入训练成本 |
| 推理成本高 / 通用模型不够专 | 微调小模型替代大模型（降本增效） |
| 提示优化先试 | 先 GEPA/提示自动优化（§16），不足再训练 |

**训练路径（可选）**：用积累的经验数据微调**领域小模型**（如软件修复专家模型），
或仅做**提示/规则优化**——训练不是必需项。

**训练治理（比知识级学习更强的护栏）**：模型版本化 · 评估门（对比基准）· 可回滚 ·
数据脱敏（§18）· 预算——训练是大动作，必须更严。

#### 17.15.4 结论

```
当前: 学习 = 系统层（知识/画像/编排），模型不动，即时、低本、易控 ✅
未来: 训练 = 模型层（可选升级），数据飞轮成熟后才触发，需更强治理 📐
```


### 17.16 自我完善详细规划（评估驱动，让系统越用越好）★

> 2026-08-22 补充（用户指出自我完善未细规划）: 完善不是"凭空改进"，是**评估驱动**——执行→评分→低分项→精准改进→验证。

**完善什么（改进对象，具体）**

| 对象 | 评估指标 | 改进动作 |
|---|---|---|
| Agent 提示 | evaluator score / 成功率 | 提示优化（GEPA，§16.4） |
| 技能调用策略 | 工具成功率/耗时 | 换技能 / 调整调用顺序 |
| 任务拆解模板 | 任务成功率/重规划率 | 模板调整（§3.3） |
| Agent 分配 | 分配后成功率 | 调整 AgentMatcher 权重（§4.8） |
| 计划质量 | plan_critic / 返工率 | 计划策略改进 |

**闭环（评估驱动）**

```
执行 → evaluator 评分（5 层：validation/patch/scope/regression/requirement ✅）
  → 低分/连续低分 → 定位改进对象 → 提出改进（GEPA/模板/权重）
  → 验证（A/B：改进前后对比）→ 通过才采纳 → 学习（改进记录入库）
  → 失败/无提升 → 回滚改进（不改坏现有）
```

**触发**：连续 N 次低分 · 成功率下降 · 用户纠错 · 成本异常

**护栏**：改进需**验证门**（A/B 对比才采纳）· 可回滚 · 样本可信度（§7.5）

**落地**：evaluator ✅；改进回路（定位→改进→A/B→采纳）📐 M4

### 17.17 自我修复深化（失败分类 / 策略矩阵 / 指标）★

> 2026-08-22 补充（用户指出）: 17.13 有框架，补**具体失败分类 → 精确策略 → 指标**。

**失败分类（具体）**

| 失败类型 | 判定 | 修复策略 | 上限 |
|---|---|---|---|
| 超时 | 执行 > 阈值 | 重试（1-3）→ 换小任务/拆更细（§3.7） | 3 次 |
| LLM 错误 | provider 报错/空响应 | 切备用 provider（§T5）→ 降级确定性（§3 兜底） | 2 次 |
| 校验失败 | 输出不达标 | 反馈重生成（DeveloperAgent） | 2 次 |
| patch 应用失败 | git apply 报错 | 重新生成 patch → 白名单检查（§20.12） | 2 次 |
| 测试失败 | pytest 红 | 失败信息回喂 → 修复 → 重跑 | 3 次 |
| 依赖缺失 | 工具/包不存在 | 安装/换工具 → 重试 | 2 次 |
| 权限拦截 | 审批/预算 block | 人工介入（ReviewGate）——**不自动绕过** | 0 |

**修复指标（可度量）**

```
修复成功率 · 平均修复耗时 · 复发率（同一任务再次失败）· 升级到人工率
目标: 修复成功率 > 80% · 复发率 < 10% · 升级人工率 < 20%（M4 验收）
```

**修复学习**：失败模式 + 成功策略入库（§17.11）→ 下次同类失败**预判策略**（§17.12 检索判断）

**落地**：失败检测/重试/重规划 ✅（ReplanningEngine/quality.repair/classify_failure）；精确策略映射（LLM）+ 指标回填 + 预判学习 📐 M4

## 十八、数据主权与隐私合规体系

> 2026-08-21 补充: 数据主权/隐私合规、知识图谱、安全纵深防御、国产化 ERP 与企业级就绪四章。

> 本补充文档对应《AI Software Factory — 完整产品方案书（终极版）》v3.0 的扩展章节。
> 新增三个章节：**数据主权与隐私合规体系**、**知识图谱与结构化知识体系**、**安全威胁模型与纵深防御体系**。
> 同时补充：**国产化ERP对标与企业级就绪** 战略说明。

---


> 本节定义AI Factory在**数据主权、隐私保护、合规认证**方面的设计原则与实现机制。
> 核心约束：**企业数据不出内网，完全本地部署，模型可选本地或专线API。**

### 18.1 核心原则

| 原则 | 说明 | 实现方式 |
|---|---|---|
| **数据主权归客户** | 所有数据（代码、文档、经验、审计）归属客户，AI Factory不占有 | 本地部署 + 数据不离开客户VPC |
| **零信任数据访问** | 任何数据访问都需要显式授权和审计 | 基于角色的访问控制 + 操作审计 |
| **数据不出内网** | 企业代码、文档、经验知识不离开客户网络边界 | 完全本地部署 + 内网隔离 |
| **模型可本地化** | LLM推理可在本地运行，也可通过专线调用外部API | 支持Ollama/DeepSeek本地部署 + 专线API |
| **合规可认证** | 系统设计满足等保、GDPR、SOC2等合规要求 | 合规架构 + 可审计 |

### 18.2 部署模式

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          企业部署模式（数据不出内网）                               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                        企业内网 / VPC                                       │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    AI Factory 完整部署                              │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │   │
│  │  │  │ 任务引擎  │  │ Agent池   │  │ 审计系统  │  │ RAG/知识  │       │   │   │
│  │  │  │ (本地)   │  │ (本地)   │  │ (本地)   │  │ (本地)   │       │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌─────────────────────────────────────────────────────────────┐   │   │   │
│  │  │  │              数据存储（全部本地）                            │   │   │   │
│  │  │  │  代码仓库 │ 项目文档 │ 审计日志 │ 经验库 │ 配置            │   │   │   │
│  │  │  └─────────────────────────────────────────────────────────────┘   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                    │                                        │   │
│  │                    ┌───────────────┴───────────────┐                        │   │
│  │                    │                               │                        │   │
│  │                    ▼                               ▼                        │   │
│  │  ┌─────────────────────────────┐  ┌─────────────────────────────────┐     │   │
│  │  │ 模式A: 完全本地推理          │  │ 模式B: 专线API推理             │     │   │
│  │  │  • Ollama/DeepSeek本地部署  │  │  • 通过专线/私有连接调用API     │     │   │
│  │  │  • 代码完全不离开内网       │  │  • 数据不经过公网               │     │   │
│  │  │  • 适合高敏感场景           │  │  • 适合需要最强模型能力         │     │   │
│  │  └─────────────────────────────┘  └─────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 数据流向（全部在内网闭环）                                                  │   │
│  │                                                                             │   │
│  │  用户输入 → AI Factory引擎 → 本地LLM/专线API → 结果输出 → 本地存储        │   │
│  │      ↑                         ↓                                            │   │
│  │      └──────── 所有数据不离开企业网络边界 ─────────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 18.3 数据分类与保护

| 数据类别 | 内容 | 存储位置 | 加密要求 | 生命周期 |
|---|---|---|---|---|
| **代码资产** | 项目源码、配置文件、脚本 | 本地代码仓库 | AES-256 静态加密 | 跟随项目生命周期 |
| **知识资产** | RAG向量库、经验库、Skill | 本地向量数据库 | AES-256 + 访问控制 | 永久保留（可手动清理） |
| **审计日志** | 全量操作记录、决策链 | 本地审计存储 | 防篡改 + 加密 | 6年（合规要求） |
| **用户数据** | 用户画像、偏好、配置 | 本地配置库 | 加密 + 最小化采集 | 用户主动删除时清除 |
| **临时数据** | 任务中间状态、缓存 | 内存/临时存储 | 任务结束后清除 | 任务结束后 ≤ 24小时 |

### 18.4 合规认证对标

| 合规标准 | 适用场景 | AI Factory对标设计 | 认证状态 |
|---|---|---|---|
| **等保2.0（三级）** | 中国企业 | 数据加密、审计日志、身份认证、访问控制 | 架构对齐，待认证 |
| **GDPR** | 欧洲业务 | 数据最小化、用户删除权、审计追踪 | 架构对齐 |
| **SOC2 Type II** | 美国企业 | 安全、可用性、处理完整性、保密性、隐私 | 架构对齐 |
| **HIPAA** | 医疗行业（未来） | PHI数据隔离、访问控制、审计 | 架构预留 |
| **ISO 27001** | 国际通用 | 信息安全管理体系 | 架构对齐 |

### 18.5 用户数据控制权

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          用户数据控制权                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 数据访问                                                                   │   │
│  │  • 用户可随时查看所有被收集的数据                                           │   │
│  │  • 用户可导出全部数据（JSON/CSV格式）                                       │   │
│  │  • 用户可查询"我的数据被用在了哪里"                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 数据删除                                                                   │   │
│  │  • 用户可删除单个任务数据                                                  │   │
│  │  • 用户可删除整个项目数据                                                  │   │
│  │  • 用户可删除个人画像和偏好                                                │   │
│  │  • 删除后数据不可恢复（符合"被遗忘权"）                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 数据迁移                                                                   │   │
│  │  • 用户可完整导出项目数据                                                  │   │
│  │  • 支持跨实例迁移（导出→导入）                                              │   │
│  │  • 无厂商锁定                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```



### 18.6 加密与密钥管理

| 层 | 要求 |
|---|---|
| 静态加密 | 代码/知识/审计 AES-256；密钥经系统密钥环（不落明文，§20.6） |
| 传输加密 | 内网/专线 TLS 1.2+；出网仅脱敏推理载荷 |
| 密钥管理 | 主密钥可 KMS/硬件密钥；轮换策略（90 天） |
| 脱敏 | 出网载荷脱敏（§8.5.9：原始 LLM 日志不投影/不出网） |

### 18.7 与存储分档衔接（§8.5）

- **自建**（AI Factory 创建库）：数据主权天然归客户（本地）
- **外挂**（企业已有库）：数据留在企业侧，AI Factory 只做适配器（§8.5.6）
- **数据分级**（§8.5.9）：原始 LLM 日志/敏感字段不投影、不出网——隐私与主权的一致实现

### 18.8 实现对照与落地

| 项 | 状态 |
|---|---|
| 本地部署 + 数据不出内网（架构） | ✅ 架构支持（本地文件/自建存储） |
| 数据分类/加密/保留（§18.3） | 🚧 部分（加密/保留待 M5 数据层落地） |
| 用户五项权利 + 导出/删除 API | 📐 M5 |
| 合规认证（等保/SOC2/GDPR 对齐） | 📐 长期（企业级阶段） |


### 18.9 本地 LLM 的架构影响（部署 A 模式的完整设计）★

> 2026-08-22 补充（用户提问）: §18.2 A 模式提了"本地 LLM"，但其**连带影响**需完整设计——
> 能力→任务粒度、成本模型、性能、学习/训练联动、混合路由。

#### 18.9.1 支持的本地 LLM 形态

```
Ollama / llama.cpp / vLLM / DeepSeek 本地 / 内网模型网关
Provider 适配（§9/T5）：本地 provider 走统一 ProviderInterface（exec/developer 已支持）
```

#### 18.9.2 能力 → 原子任务粒度联动（关键）

- 本地模型能力通常弱于云端大模型 → **任务必须拆得更细**（§3.7"拆解深度 = Agent 能力边界"的直接体现）
- 双向联动：**能力配置 → 原子任务判定标准**（本地: 单函数/单工具；云端: 可到模块级）
- 意义：同一产品，本地部署自动适配更细的拆解，云端自动放宽——**能力自适应**

#### 18.9.3 成本模型适配

```
云端 API: token 计费（§6.2 现有预算模型）
本地 LLM: 无 token 计费 → 预算从"token 成本"改为"硬件/时间配额"
  （推理时长 × 并发上限 × 显存占用；单位经济 §1.5.3 用硬件摊销）
```

#### 18.9.4 性能与并行（联动 §3.9）

- 本地推理吞吐/显存受限 → **§3.9 并行度受本地容量约束**（队列限流）
- 大模型任务（PRD/架构深度）可排队或路由云端（18.9.7）

#### 18.9.5 数据主权

- 本地 LLM = **数据完全不出网**（A 模式最大化，§18.1 铁律）✅

#### 18.9.6 学习 / 训练联动（本地更可控）

- 本地数据飞轮积累的数据**不出网** → 未来可**微调本地模型**（§17.15）
- 本地训练更可控：数据不外流、版本/回滚自主、无需外部平台

#### 18.9.7 混合路由（本地为主 + 云端按需）

```
路由策略（§T5 模型路由）:
  敏感任务（代码/审计/隐私）→ 本地
  重活（PRD 深度/复杂拆解）→ 云端 API（或本地大模型）
  成本敏感 → 本地；质量敏感 → 云端
按任务复杂度/隐私级别/成本 三级路由
```

#### 18.9.8 实现状态

| 项 | 状态 |
|---|---|
| 本地 provider 适配（Ollama/OpenAI 兼容） | 🚧 部分（provider 接口支持，Ollama 已有提及） |
| 能力→原子粒度自适应 / 成本配额 / 混合路由 | 📐 M3/M5 |
| 本地微调链路 | 📐 长期（§17.15 前置条件） |

## 十九、知识图谱与结构化知识体系

> 本节定义AI Factory的**知识图谱**和**结构化知识**架构，使系统不仅具备"检索非结构化文档"的能力（RAG），更拥有"理解实体关系、应用规则、推理决策"的智能。

### 19.1 知识分层架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          知识分层架构                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L4: 元知识 (Meta-Knowledge)                                                │   │
│  │   • 关于知识的知识：知识的版本、来源、置信度、适用范围                      │   │
│  │   • 知识图谱自身的管理和演化                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 规则知识 (Rule Knowledge)                                               │   │
│  │   • 结构化规则：If-Then决策规则、约束条件、审批规则                          │   │
│  │   • 流程模板：工作流DAG模板、协作模式模板                                    │   │
│  │   • 评价标准：质量评分规则、验收条件                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 关系知识 (Relational Knowledge)                                        │   │
│  │   • 实体关系图谱：任务↔Agent↔工具↔文件↔决策的关联                           │   │
│  │   • 依赖关系：代码依赖、服务依赖、任务依赖                                   │   │
│  │   • 影响关系：修改影响范围、决策影响链                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 事实知识 (Factual Knowledge) — 对应RAG                                 │   │
│  │   • 非结构化文档：代码、设计文档、日志、会议纪要                             │   │
│  │   • 经验描述：成功模式、失败教训、领域知识                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 19.2 知识图谱数据模型

```python
#### ============ 知识图谱核心模型 ============

class KnowledgeEntity:
    """知识实体——图谱中的节点"""
    
    id: str
    type: str                          # Task | Agent | Tool | File | Decision | Skill | Rule | Pattern
    name: str
    description: str
    properties: Dict[str, Any]
    
    # 上下文
    project_id: str | None
    factory_id: str | None
    
    # 元数据
    created_at: datetime
    updated_at: datetime
    version: int
    confidence: float


class KnowledgeRelation:
    """知识关系——图谱中的边"""
    
    id: str
    source_id: str                     # 源实体ID
    target_id: str                     # 目标实体ID
    relation_type: str                 # depends_on | triggers | resolves | applied_to | derived_from | conflicts_with
    
    # 关系属性
    weight: float                      # 关系强度
    context: str | None                # 关系上下文描述
    evidence: List[str]               # 证据来源
    
    # 元数据
    created_at: datetime
    confidence: float


#### ============ 关系类型枚举 ============

class RelationType:
    """知识关系类型"""
    
    # 依赖关系
    DEPENDS_ON = "depends_on"          # A依赖B
    TRIGGERS = "triggers"              # A触发B
    RESOLVES = "resolves"              # A解决B
    
    # 应用关系
    APPLIED_TO = "applied_to"          # A应用于B
    DERIVED_FROM = "derived_from"      # A衍生自B
    
    # 冲突关系
    CONFLICTS_WITH = "conflicts_with"  # A与B冲突
    SUPERSEDES = "supersedes"          # A取代B
    
    # 关联关系
    RELATED_TO = "related_to"          # A与B相关
    INSTANCE_OF = "instance_of"        # A是B的实例
```

### 19.3 结构化规则库

```python
#### ============ 结构化规则 ============

class StructuredRule:
    """结构化规则——可执行的决策逻辑"""
    
    id: str
    name: str
    type: str                          # decision | constraint | approval | evaluation
    
    # 规则条件（可执行表达式）
    condition: str                     # Python表达式或DSL
    condition_params: Dict[str, Any]  # 条件参数
    
    # 规则动作
    action: str                        # 执行的动作
    action_params: Dict[str, Any]     # 动作参数
    
    # 规则元数据
    priority: int                      # 优先级（数字越大越高）
    confidence: float                  # 置信度 0-1
    source: str                        # 来源：system | learned | user_defined
    
    # 审计
    created_at: datetime
    updated_at: datetime
    version: int
    enabled: bool


#### ============ 规则示例 ============

RULES = [
    {
        "id": "rule_001",
        "name": "高风险操作需审批",
        "type": "approval",
        "condition": "task.risk_level == 'high' or task.risk_level == 'critical'",
        "action": "request_approval",
        "action_params": {"approval_level": "manager"},
        "priority": 10,
        "confidence": 1.0,
        "source": "system",
        "enabled": True
    },
    {
        "id": "rule_002",
        "name": "成本超限熔断",
        "type": "decision",
        "condition": "running_cost > budget_limit * 0.9",
        "action": "circuit_breaker",
        "action_params": {"mode": "throttle", "throttle_to": 0.5},
        "priority": 20,
        "confidence": 1.0,
        "source": "system",
        "enabled": True
    },
    {
        "id": "rule_learned_001",
        "name": "NPE优先检查空指针",
        "type": "decision",
        "condition": "error_type == 'NullPointerException'",
        "action": "suggest_fix",
        "action_params": {"strategy": "check_npe_pattern"},
        "priority": 5,
        "confidence": 0.85,
        "source": "learned",
        "enabled": True
    }
]
```

### 19.4 知识进化机制

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          知识进化闭环                                              │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 任务执行 → 产生新数据                                                       │   │
│  │   • 新任务实例、新决策、新结果                                               │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 知识提取                                                                   │   │
│  │   • 从任务中提取实体（Task/Agent/Tool/File）                                │   │
│  │   • 从轨迹中提取关系（depends_on/triggers/resolves）                        │   │
│  │   • 从结果中提取模式（成功/失败模式）                                       │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 知识融合                                                                   │   │
│  │   • 新知识 vs 已有知识 → 去重/合并/版本                                     │   │
│  │   • 冲突检测 → 告警 → 人工裁定                                             │   │
│  │   • 置信度评估 → 低置信度标记待审                                           │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 知识存储                                                                   │   │
│  │   • 图数据库存储实体和关系                                                   │   │
│  │   • 规则库存储结构化规则                                                     │   │
│  │   • 经验库存储非结构化描述                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 知识应用                                                                   │   │
│  │   • Planner 拆解时引用规则和模式                                             │   │
│  │   • Executor 执行时查询相关经验                                              │   │
│  │   • Governor 决策时应用规则                                                  │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 19.5 知识查询接口

```python
#### ============ 知识查询接口 ============

class KnowledgeGraph:
    """知识图谱查询接口"""
    
    # ========== 实体查询 ==========
    
    def get_entity(self, entity_id: str) -> KnowledgeEntity:
        """获取实体详情"""
        pass
    
    def search_entities(self, query: str, entity_type: str = None) -> List[KnowledgeEntity]:
        """搜索实体"""
        pass
    
    def get_related_entities(self, entity_id: str, relation_type: str = None, depth: int = 1) -> List[KnowledgeEntity]:
        """获取关联实体（支持深度遍历）"""
        pass
    
    # ========== 关系查询 ==========
    
    def get_relations(self, entity_id: str, relation_type: str = None) -> List[KnowledgeRelation]:
        """获取实体所有关系"""
        pass
    
    def find_path(self, source_id: str, target_id: str) -> List[KnowledgeRelation]:
        """查找两个实体之间的关联路径"""
        pass
    
    # ========== 规则查询 ==========
    
    def get_rules(self, condition: str = None, type: str = None) -> List[StructuredRule]:
        """获取匹配的规则"""
        pass
    
    def evaluate_rules(self, context: Dict[str, Any]) -> List[StructuredRule]:
        """评估上下文匹配的规则，返回触发的规则列表"""
        pass
    
    # ========== 知识推荐 ==========
    
    def recommend_skills(self, task_context: Dict[str, Any]) -> List[Skill]:
        """基于任务上下文推荐可复用的Skill"""
        pass
    
    def recommend_workflows(self, goal: str, domain: str) -> List[WorkflowTemplate]:
        """基于目标和领域推荐工作流模板"""
        pass
    
    def predict_risks(self, plan: TaskDAG) -> List[RiskPrediction]:
        """基于历史知识预测任务风险"""
        pass
```



### 19.6 知识图谱实现对照与落地

| 项 | 状态 |
|---|---|
| 经验库（轻量图谱雏形：经验/模式检索） | ✅ 已实现（memory/experience + retrieval） |
| 图谱数据模型（§19.2 节点/关系/关系类型） | 📐 设计（无实现） |
| 结构化规则库 / 查询接口（§19.3/19.5） | 📐 设计 |
| 知识进化闭环（§19.4） | 📐 设计 |
| 与 RAG 分档衔接（档4 图谱投影，§8.5） | 📐 M5 |
| 与统一契约衔接（节点/关系带血缘，§2.10） | 📐 随 M5 |

**落地建议（M5 简化版）**：先从 artifact/evidence/decision **自动建节点与关系**（不人工维护），
图谱作为"查询投影"（§8.5.8），数据分级（§8.5.9）只同步高价值关系。

## 二十、安全威胁模型与纵深防御体系

> 本节定义AI Factory面临的**安全威胁模型**，以及相应的**纵深防御策略**。
> AI Agent系统的攻击面与传统系统有本质区别，需要专门设计。

### 20.0 安全本质总纲（30 秒理解安全防什么）★

> 2026-08-24 补充（Founder 询问: 安全主要是防什么?）: 20 节太庞大, 先给本质——
> 一句话 + 四类 + 三层防线, 读完本节再进威胁模型细节。

**一句话**

```
AI Factory 安全防的是: AI 在无人监管下做错事、被坏人利用, 造成的四类伤害。
```

**四类防御对象**

| 防什么 | 具体场景 | 对应机制 | 状态 |
|---|---|---|---|
| **① 防 AI 做坏事** | 改坏代码 / 删库 / 引入漏洞 / 被提示词注入操控 | 沙箱隔离（§5.13）+ 审批门（§6.3）+ patch 白名单 + 指令隔离 | ✅ 核心已实现 |
| **② 防机密外流** | 项目代码/客户数据被 AI 发给外部 / 被偷走 | 凭证不落明文 + 网络隔离 + 数据主权（§18） | 🚧 部分 |
| **③ 防环境被破坏** | AI 逃出沙箱碰真实系统 / 资源耗尽成本爆炸 | 沙箱多层隔离 + 预算熔断 + 超时 | ✅ 核心已实现 |
| **④ 防 Agent 串通 / 供应链带毒** | 多 Agent 合谋绕过审批 / Skill/MCP 被植入恶意 | 交叉审计 + 依赖扫描 + 白名单 | 📐 M4+ |

**三层防线**

```
执行层:  AI 改不坏（沙箱 → 审批 → patch 白名单）
数据层:  机密出不去（凭证隔离 → 网络隔离 → 数据主权）
治理层:  坏人利用不了（审计链 → 权限 → 监控 → 事件响应）
```

**AI 特有安全 vs 传统安全**

```
AI 特有（传统系统没有, AI Factory 安全的核心战场）:
  提示词注入 / 越狱 / Agent 串通 / 幻觉导致的危险操作
传统（所有系统都有, 已覆盖）:
  命令注入 / 路径遍历 / 资源耗尽 / 凭证泄露
```

**沙箱在安全里的位置**

```
沙箱 = 执行层的基石（防 AI 做坏事 + 防逃逸破坏）
完整安全 = 执行层(沙箱) + 数据层(凭证/网络) + 治理层(审计/审批/监控)
```

**一句话总结**

> 安全主要防三件事: **AI 改不坏（执行层）、机密出不去（数据层）、坏人利用不了
> （治理层）**。其中"AI 特有的攻击"（提示词注入/串通/幻觉）是最需要持续投入的
> 战场——因为这是传统安全工具不覆盖的。

### 20.1 威胁模型全景

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          AI Factory 威胁模型                                       │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         攻击面分类                                          │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 1. Agent层攻击                                                      │   │   │
│  │  │    • 提示词注入 (Prompt Injection)                                   │   │   │
│  │  │    • 越狱攻击 (Jailbreak)                                            │   │   │
│  │  │    • Agent欺骗 (Deceptive Agent)                                     │   │   │
│  │  │    • 多Agent串通 (Collusion)                                         │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 2. 工具层攻击                                                       │   │   │
│  │  │    • 工具滥用 (Tool Misuse)                                          │   │   │
│  │  │    • 命令注入 (Command Injection)                                    │   │   │
│  │  │    • 路径遍历 (Path Traversal)                                       │   │   │
│  │  │    • 资源耗尽 (Resource Exhaustion)                                  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 3. 数据层攻击                                                       │   │   │
│  │  │    • 凭证泄露 (Credential Theft)                                     │   │   │
│  │  │    • 审计绕过 (Audit Bypass)                                         │   │   │
│  │  │    • 数据外泄 (Data Exfiltration)                                    │   │   │
│  │  │    • 数据篡改 (Data Tampering)                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ 4. 系统层攻击                                                       │   │   │
│  │  │    • 沙箱逃逸 (Sandbox Escape)                                       │   │   │
│  │  │    • 容器逃逸 (Container Escape)                                     │   │   │
│  │  │    • 服务拒绝 (DoS)                                                  │   │   │
│  │  │    • 供应链攻击 (Supply Chain)                                       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 20.2 纵深防御架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          纵深防御架构（七层）                                      │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L7: 审计与溯源                                                             │   │
│  │  全链路审计 + 异常行为检测 + 安全事件溯源                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L6: 治理与合规                                                             │   │
│  │  权限最小化 + 规则引擎 + 合规检查 + 预算熔断                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L5: Agent安全                                                              │   │
│  │  输入验证 + 输出过滤 + 指令白名单 + 行为边界                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L4: 工具安全                                                               │   │
│  │  参数验证 + 命令白名单 + 路径隔离 + 超时控制                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 数据安全                                                               │   │
│  │  加密存储 + 传输加密 + 最小化采集 + 访问控制                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 沙箱隔离                                                               │   │
│  │  任务级隔离 + 网络隔离 + 资源限制 + 临时环境                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 网络与基础设施                                                         │   │
│  │  内网部署 + 零信任网络 + 安全基线 + 漏洞管理                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 20.3 核心攻击的专项防御

| 威胁 | 描述 | 防御策略 | 实现方式 |
|---|---|---|---|
| **提示词注入** | 恶意指令混入用户输入，诱导Agent执行危险操作 | 输入净化 + 指令隔离 | System Prompt与User Prompt严格分离；检测并过滤恶意指令模式 |
| **命令注入** | 通过工具参数执行恶意系统命令 | 命令白名单 + 参数校验 | 禁止危险命令（rm -rf、curl外部、eval）；参数严格转义 |
| **路径遍历** | 读写系统敏感文件 | 路径沙箱 + 白名单 | 限制操作在项目目录内；禁止访问/etc/、/proc/等 |
| **凭证泄露** | Agent访问过程中泄露API密钥 | 动态注入 + 不可见 | Agent不持有真实凭证；临时凭证限定范围+时效 |
| **审计绕过** | 攻击者试图清除或伪造审计日志 | 防篡改 + 外部存储 | 审计日志WORM存储；实时同步到独立审计系统 |
| **沙箱逃逸** | 从隔离环境逃逸到宿主机 | 多层隔离 + 最小权限 | 容器+Docker；非root运行；禁用特权模式 |
| **资源耗尽** | 通过大量操作消耗系统资源 | 配额 + 熔断 | 每个任务有资源配额；超限自动熔断 |
| **多Agent串通** | 多个被攻陷Agent协同作恶 | 交叉审计 + 异常检测 | 检测异常协作模式；Agent间不直接通信 |

### 20.4 Agent安全设计

```python
#### ============ Agent安全设计 ============

class AgentSecurityGuard:
    """Agent安全守卫——执行前/执行后安全检查"""
    
    def __init__(self):
        self.input_validator = InputValidator()
        self.output_filter = OutputFilter()
        self.command_whitelist = CommandWhitelist()
        self.path_sandbox = PathSandbox()
        self.behavior_monitor = BehaviorMonitor()
    
    # ========== 输入验证 ==========
    
    def validate_user_input(self, user_input: str) -> ValidationResult:
        """
        验证用户输入，防止提示词注入
        
        检测模式:
        - 系统指令覆盖尝试 ("ignore previous instructions")
        - 越狱模式 ("jailbreak", "developer mode")
        - 角色扮演攻击 ("pretend you are")
        - 编码注入 (base64, hex编码的恶意指令)
        """
        if self.input_validator.detect_jailbreak(user_input):
            return ValidationResult(valid=False, reason="jailbreak_detected")
        if self.input_validator.detect_system_override(user_input):
            return ValidationResult(valid=False, reason="system_override_attempt")
        return ValidationResult(valid=True)
    
    # ========== 输出过滤 ==========
    
    def filter_agent_output(self, output: str) -> str:
        """
        过滤Agent输出，防止敏感信息泄露
        
        检测模式:
        - API密钥格式 (sk-*, AKIA*, etc.)
        - 密码/凭证格式
        - 内部IP/域名
        - 源代码中硬编码的密钥
        """
        return self.output_filter.redact_sensitive(output)
    
    # ========== 工具权限控制 ==========
    
    def check_tool_permission(self, tool_name: str, params: Dict) -> PermissionResult:
        """检查工具调用权限"""
        # 高危命令检查
        if tool_name == "run_command":
            command = params.get("command", "")
            if not self.command_whitelist.is_allowed(command):
                return PermissionResult(allowed=False, reason="command_not_in_whitelist")
        
        # 路径检查
        if tool_name == "write_file" or tool_name == "read_file":
            path = params.get("path", "")
            if not self.path_sandbox.is_within_boundary(path):
                return PermissionResult(allowed=False, reason="path_outside_sandbox")
        
        return PermissionResult(allowed=True)
```

### 20.5 安全事件响应

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          安全事件响应流程                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 检测                                                                       │   │
│  │   • 实时日志分析                                                           │   │
│  │   • 异常行为检测                                                            │   │
│  │   • 规则告警触发                                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 分类                                                                       │   │
│  │   • 事件类型：Agent异常 / 工具滥用 / 数据泄露 / 系统入侵                    │   │
│  │   • 严重级别：P0(紧急) / P1(严重) / P2(一般) / P3(观察)                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 隔离                                                                       │   │
│  │   • P0/P1: 立即隔离受影响任务/Agent/沙箱                                    │   │
│  │   • 暂停相关任务                                                            │   │
│  │   • 通知管理员                                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 取证                                                                       │   │
│  │   • 冻结现场（保全证据）                                                    │   │
│  │   • 导出完整审计日志                                                        │   │
│  │   • 分析根因                                                                │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 恢复                                                                       │   │
│  │   • 清理受影响资源                                                          │   │
│  │   • 回滚到安全状态                                                          │   │
│  │   • 恢复任务（如需要）                                                      │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ 改进                                                                       │   │
│  │   • 更新安全规则                                                            │   │
│  │   • 修复漏洞                                                                │   │
│  │   • 经验沉淀（防止复发）                                                    │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```


### 20.6 安全实现对照与完成度（2026-08-22）

| 能力 | 真实实现 | 状态 |
|---|---|---|
| 沙箱隔离 | `exec/sandbox.py`：项目副本，原仓库零影响；git 校验 | ✅ |
| patch 白名单 | `exec/patch_filter.py`：过滤状态文件 + 交付校验 | ✅ |
| 审批门 | `exec/approval.py` + `review_gate.py`：应用前必批 + 分级 | ✅ |
| 凭证安全 | config/providers 只写 env 引用（不落明文 key） | ✅ |
| 数据隔离 | HOME 重定向 / data_dir 独立（测试与多工作区） | ✅ |
| 威胁模型/纵深防御/事件响应 | 本文档 20.1-20.5（设计） | 📐 |
| 数据主权/合规认证 | §十八/§21（设计，企业级阶段） | 📐 |

**完成度**：运行时安全（沙箱/patch/审批/凭证/隔离）已实现（✅）；威胁模型/纵深防御/合规认证为企业级阶段（📐，M5+）。


### 20.7 威胁 × 实现状态（20.3 的 8 威胁逐一落地核对）★

> 2026-08-22 补充: 8 个核心威胁的防御策略**哪些已实现、哪些待补**——让安全从"设计"到"可核对"。

| 威胁 | 防御策略 | 实现状态 |
|---|---|---|
| 提示词注入 | 输入净化 + 指令隔离（System/User Prompt 分离） | 🚧 部分（结构分离有，恶意模式过滤 📐） |
| 命令注入 | 命令白名单 + 参数校验 | 🚧 部分（工具白名单有，危险命令过滤 📐） |
| 路径遍历 | 路径沙箱 + 白名单 | ✅ 已实现（exec/sandbox.py 项目副本隔离） |
| 凭证泄露 | 动态注入 + 不可见 | ✅ 已实现（config/providers 只写 env 引用） |
| 审计绕过 | 防篡改 + 外部存储 | 🚧 部分（hash 链防篡改 ✅；WORM 外部存储 📐） |
| 沙箱逃逸 | 多层隔离 + 最小权限 | ✅ 已实现（sandbox + git 校验；容器加固 📐） |
| 资源耗尽 | 配额 + 熔断 | ✅ 已实现（budget.py 四级 + 熔断 §2） |
| 多 Agent 串通 | 交叉审计 + 异常检测 | 📐 设计（审计链有，异常协作检测 📐 M4） |

### 20.8 安全横切衔接（安全不是孤岛）★

```
安全 × §2 模块化: 模块边界=攻击面边界; 模块只经 API（§2.10 收窄攻击面）
安全 × §6 治理:   风险分级=审批卡口（§6.3 高低风险必批）
安全 × §18 主权:   数据不出内网 + 加密/脱敏（§18.6）
安全 × §5 审计:    hash 链 + 血缘（防篡改证据）
安全 × §5.8 监控:  critical 告警 → 事件响应（§20.5）
安全 × §17 修复:   安全告警 → 自动修复/人工介入（§17.13）
```

**结论**：8 威胁中 **4 已实现**（路径/凭证/沙箱/资源），3 部分（注入/命令/审计WORM），1 设计（Agent串通检测，M4）；安全作为横切贯穿模块/治理/主权/审计/监控/修复。


### 20.9 STRIDE 威胁模型系统化（8 威胁之外的系统化补充）★

| STRIDE | 威胁 | AI Factory 具体场景 | 缓解 |
|---|---|---|---|
| S 仿冒 | 伪造 Agent/用户身份 | 工具调用冒充可信 Agent | 身份令牌 + 审计（谁调了什么） |
| T 篡改 | 修改数据/证据 | 审计日志/证据包被改 | hash 链（✅）+ 只读事实源（§8.5.8） |
| R 否认 | 抵赖操作 | Agent 说"我没改这个文件" | 全链路审计 + 证据包（✅ 已实现） |
| I 信息泄露 | 敏感数据外泄 | LLM 输出含 API key/客户数据 | 脱敏 + 出网载荷最小化（§18.6） |
| D 拒绝服务 | 资源耗尽/拖垮 | 恶意任务刷爆预算 | budget 四级 block（✅）+ 熔断（§2） |
| E 提权 | 越权操作 | 低权限 Agent 删文件 | 权限门 + 审批（§6.3）+ 沙箱（✅） |

### 20.10 LLM 特有安全（AI 场景专属，常规安全之外）★

| 风险 | 场景 | 检测/缓解规则（具体） |
|---|---|---|
| **提示词注入** | 文档/代码里藏恶意指令 | 检测规则: "忽略之前指令/你是..." 等模式 → 隔离标记；System/User Prompt 分离（🚧→M3 规则库） |
| **数据外泄** | LLM 输出含敏感信息 | 出网载荷最小化 + 输出脱敏扫描（API key/密钥/身份证模式）；敏感任务路由本地（§18.9.7） |
| **幻觉作为安全风险** | 模型自信地给出错误安全结论 | 关键决策强制"证据引用"（§17.12 决策回路 source）+ 高影响任务人工复核 |
| **越狱/绕过** | 多轮对话诱导越权 | 敏感动作持续审批（不因上下文"已信任"而跳过）；越狱模式检测 |
| **供应链** | Skill/MCP/依赖带毒 | Skill/MCP 白名单注册（§9.6）+ 依赖扫描（§20.12）+ 沙箱运行 |

### 20.11 纵深防御分层具体控制（每层可核对）★

| 层 | 控制（具体） | 状态 |
|---|---|---|
| 网络 | 内网隔离（§18.2 C 模式）· TLS 1.2+ · 出网白名单 | ✅/📐 |
| 主机 | 非 root 运行 · 最小权限 · 资源配额（budget） | ✅ |
| 应用 | 只经 API（§2.10）· 命令/路径白名单 · 输入净化 | 🚧 |
| 数据 | 静态加密 AES-256 · 脱敏 · 数据分级（§8.5.9） | 🚧 |
| 身份 | 凭证 env 引用 · 审批门 · RBAC（📐） | ✅/📐 |
| 供应链 | Skill/MCP 白名单 · 依赖扫描 | 🚧 |

### 20.12 安全测试与验证（进工程管线）★

| 测试 | 内容 | 时机 | 状态 |
|---|---|---|---|
| SAST 静态扫描 | 代码安全缺陷（注入/越权） | 每次交付 | 📐 M3 |
| 依赖扫描 | 第三方依赖漏洞（CVE） | 每次构建 | 📐 M3 |
| 提示词注入测试 | 对抗样本集（恶意文档/指令） | 每次 Agent 流程改动 | 📐 M3 |
| 渗透测试 | 越权/路径遍历/注入实际攻击 | 发布前 | 📐 M5 |
| 合规检查 | 等保/数据主权对照项 | 定期 | 📐 长期 |

**落地**：安全测试接入 `factory security test`（M3）；结果进证据包（§5.6）可审计。

### 20.13 安全事件响应具体流程（20.5 深化）★

```
告警（critical，§5.8）→ 分级（S1 高危/S2 中/S3 低）
  → 响应: S1 自动隔离（停队列/断工具）+ 通知（§9.5）+ 人工介入
  → 溯源: correlation_id 关联审计链 → 定位根因（§5.6 回放）
  → 修复: 自我修复（§17.13）或人工补丁
  → 复盘: 事件报告（§5.9 审计报告风险章）+ 规则/防御更新（§17.11 学习）
  → SLA: S1 15 分钟内响应 · S2 2 小时 · S3 24 小时
```

## 二十一、国产化ERP对标与企业级就绪

> 本节说明AI Factory的**最终企业级定位**：对标国产化ERP系统（如用友、金蝶、浪潮），对标SAP的流程深度与组织覆盖，最终成为中国企业AI转型的数字企业运行模型。

### 21.1 定位升级

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          定位升级：从工具到企业级AI操作系统                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         之前的定位                                         │   │
│  │                    面向个人/团队的AI自动化工具                              │   │
│  │  用户：开发者、产品经理、创业者                                            │   │
│  │  场景：软件开发、简单任务自动化                                            │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         新的定位（企业级）                                  │   │
│  │                     面向企业的AI操作系统（对标ERP）                        │   │
│  │                                                                             │   │
│  │  用户：CIO、CTO、企业运营负责人、业务部门                                  │   │
│  │  场景：                                                                     │   │
│  │    • 全流程自动化（研发→运维→运营→财务→人事）                              │   │
│  │    • 组织级AI治理（预算、审计、合规、安全）                                 │   │
│  │    • 跨部门AI协作（多工厂协同、资源共享）                                   │   │
│  │    • 数据主权（本地部署、数据不出内网）                                     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 21.2 与国产化ERP的对标

| 对比维度 | 传统ERP（用友/金蝶/SAP） | AI Factory（企业级） |
|---|---|---|
| **核心对象** | 企业资源（人、财、物、产、供、销） | 企业AI能力（Agent、Skill、知识、流程） |
| **管理内容** | 业务流程、财务、库存、人力资源 | AI任务、AI员工、AI知识、AI治理 |
| **运行模式** | 人驱动流程（人录入、人审批、人执行） | AI驱动流程（AI执行、AI审批辅助、人监督） |
| **覆盖范围** | 企业运营全流程 | 企业AI运营全流程（不替代ERP，是ERP的AI增强层） |
| **数据主权** | 本地部署、数据归企业 | 本地部署、数据不出内网 |
| **合规对标** | 等保、GDPR、SOX | 等保、GDPR、SOC2 |
| **组织管理** | 部门、岗位、权限 | Agent组织、角色、权限 |

### 21.3 与SAP的对比

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          AI Factory vs SAP                                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ SAP（全球ERP标杆）                                                         │   │
│  │   • 最佳实践库：行业最佳业务实践沉淀                                        │   │
│  │   • 流程引擎：企业流程标准化和自动化                                        │   │
│  │   • 数据底座：统一数据模型和主数据管理                                      │   │
│  │   • 合规框架：全球合规要求内置                                              │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│                                    ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │ AI Factory（AI时代的企业操作系统）                                         │   │
│  │   • 智能最佳实践库：AI经验的持续沉淀和复用 → 对标SAP最佳实践库              │   │
│  │   • Agent流程引擎：多Agent协作的标准化流程 → 对标SAP流程引擎                │   │
│  │   • 知识底座：统一知识图谱和经验模型 → 对标SAP统一数据模型                  │   │
│  │   • 治理框架：AI治理（成本/审计/安全） → 对标SAP合规框架                    │   │
│  │   • 行业工厂：预置行业AI模板 → 对标SAP行业解决方案                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 21.4 SAP 深度对标：四大支柱与 AI Factory 借鉴

> 2026-08-21 补充: SAP 的优势不在单一技术点，而在其构建的"商业操作系统"式完整体系 — AI Factory 从"工具"向"企业级 AI 操作系统"进化时需深度借鉴。

SAP 的优势不在于单一的技术点，而在于其构建的"商业操作系统"式的完整体系。核心优势可归纳为四大支柱：

#### 支柱一：全球最佳实践的知识沉淀（Know-How）

- **50 年行业知识的结晶**：SAP 真正的护城河在于 50 年来与全球各行业顶尖企业合作、积累并总结出的**最佳管理实践**——不仅是工具，更是先进管理思想的载体。
- **开箱即用的流程模板**：云 ERP 内置**超过 800 个最佳实践范围项目**和预配置的行业业务流程；SAP Activate 方法论可让企业在**约两个月**内完成实施，将员工手工作业从 **5-6 小时缩减至 1 小时**。
- **"Clean Core"战略**：核心 ERP 保持"整洁"与标准化，仅对差异化流程做外围扩展，确保持续平滑接收 SAP 全球智慧与创新，不被定制锁死在旧版本。

#### 支柱二：模块化与可组合的架构（Flexibility）

- **从"一体化"到"可组合"**：可组合架构（Composable Architecture），模块化、可互换组件，独立演进，保持灵活可扩展。
- **统一技术底座（BTP）**：数据库/分析/应用开发/集成统一承载，为上层应用提供一致技术支撑。
- **"套件优先"+"AI 优先"**：统一语义模型与界面确保模块无缝协作；用 AI 重构业务逻辑而非打补丁。

#### 支柱三：数据与 AI 深度融合的智能平台（Intelligence）

- **业务数据云（BDC）**：统一管理 SAP 及第三方数据，形成统一"语义层"，为 AI 奠定数据基础。
- **SAP 知识图谱**：一张结构化的"业务地图"，让 AI 理解每个业务实体、流程及其复杂关系，决策有坚实业务上下文。
- **Joule 副驾 + AI 智能体**：生成式 AI 副驾跨应用自然语言完成复杂任务；已部署 **224 个 AI 智能体 + 51 个业务助手**，主动识别异常、分析根因、触发处理——目标：**自主运营企业（Autonomous Enterprise）**，从"人工驱动流程"迈向"AI 驱动业务结果"。

#### 支柱四：庞大而稳固的生态与网络效应（Ecosystem）

- **客户基础**：全球 **77%+ 交易**经 SAP 处理，**世界 500 强 80%+** 是其客户。
- **网络效应**：全球商业网络连接企业及其供应链上下游，客户越多网络价值越高、粘性越强。
- **生态护城河**：管理软件的高迁移成本 + 庞大实施伙伴网络，构成难以撼动的生态护城河。

#### 对 AI Factory 的借鉴：从"工具"到"操作系统"

1. **从"流程模板"到"智能工厂模板"**：把 AI Factory 各行业（软件/运维/电商…）成功案例固化、标准化为可复用的"行业智能工厂模板"，让新用户快速起步。
2. **构建"可组合"的 AI 能力平台**：Agent、工具、知识库设计为可插拔、可独立演进的模块，统一内核编排，避免"烟囱式"发展。
3. **打造"数据+知识"双轮驱动的智能底座**：对标 BDC 与知识图谱，构建统一知识与数据平面，让 Agent 理解企业全局业务语义与关系——自主运营的前提。
4. **定义"AI 优先"的下一代交互范式**：像 Joule 一样，用户用自然语言描述**业务目标**（"帮我优化月末结账流程"），系统自动编排 Agent 完成，而非手动下指令。
5. **培育"Agent 生态"，形成网络效应**：由开发者、合作伙伴、用户组成 Agent 与技能生态，AI 能力像乐高积木般可组合、分享、交易。
6. **坚守"数据主权"与"安全合规"**：本地部署、数据主权、安全合规作为核心设计原则——赢得大型企业与关键基础设施客户信任的基石。

#### 总结：AI 时代的 SAP

SAP 的成功，是"**深厚的行业知识（最佳实践）+ 灵活的技术架构（可组合）+ 智能的数据与 AI 平台 + 强大的生态网络**"四者协同的结果。

**AI Factory 不应只做一个"自动化工具"，而应立志成为"AI 时代的 SAP"** —— 一个能够承载、编排并进化企业级 AI 能力的"操作系统"。核心竞争力的构建，也必须围绕这四大支柱展开，而非仅仅关注单一的技术或功能。

### 21.5 国产化适配清单

| 适配维度 | 要求 | AI Factory实现 |
|---|---|---|
| **国产CPU** | 支持鲲鹏、飞腾、龙芯、海光 | 镜像支持ARM64/x86_64，适配国产芯片 |
| **国产OS** | 支持麒麟、统信UOS、欧拉 | 适配国产操作系统，提供RPM/DEB包 |
| **国产数据库** | 支持达梦、金仓、神通、OceanBase | 数据库抽象层，支持国产数据库 |
| **国产中间件** | 支持东方通、宝兰德、金蝶天燕 | 兼容国产Java中间件部署 |
| **国密算法** | 支持SM2/SM3/SM4 | 加密模块支持国密算法替换AES |
| **等保合规** | 满足等保2.0三级 | 内置等保三级安全能力 |
| **信创认证** | 信创目录产品认证 | 持续推动认证 |

### 21.6 企业级功能矩阵

| 功能域 | 企业级能力 | 对标参考 |
|---|---|---|
| **组织管理** | 多部门、多角色、多权限、多工厂 | 用友U8/U9组织架构 |
| **流程管理** | 流程设计、审批流、流程监控 | SAP Workflow |
| **知识管理** | 企业知识库、经验沉淀、最佳实践库 | SAP Best Practices |
| **审计管理** | 全链路审计、合规报告、审计追溯 | SAP Audit Information System |
| **预算管理** | 成本预算、费用控制、资源配额 | SAP Controlling (CO) |
| **安全管理** | 等保三级、国密、安全事件响应 | 企业安全基线 |
| **运维管理** | 监控告警、日志管理、备份恢复 | SAP Solution Manager |

### 21.7 企业部署架构

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                          企业级部署架构                                            │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          企业数据中心/私有云                                │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    管理区                                            │   │   │
│  │  │  运维控制台 │ 审计控制台 │ 合规管理 │ 配置中心                        │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    AI Factory 集群                                  │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐                      │   │   │
│  │  │  │ 控制节点  │  │ 计算节点  │  │ 计算节点  │  (高可用集群)         │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘                      │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    数据区                                            │   │   │
│  │  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │   │   │
│  │  │  │ 元数据库  │  │ 审计库    │  │ 向量库    │  │ 文件存储  │       │   │   │
│  │  │  │ (国产DB)  │  │ (国产DB)  │  │ (本地)   │  │ (本地)   │       │   │   │
│  │  │  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                             │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    LLM 推理区                                       │   │   │
│  │  │                                                                     │   │   │
│  │  │  ┌─────────────────────────┐  ┌─────────────────────────────────┐  │   │   │
│  │  │  │ 模式A: 本地推理集群      │  │ 模式B: 专线API网关             │  │   │   │
│  │  │  │  (DeepSeek/Ollama)      │  │  (安全专线连接外部模型服务)    │  │   │   │
│  │  │  └─────────────────────────┘  └─────────────────────────────────┘  │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  关键约束：                                                                        │
│  1. 所有组件部署在企业内网/VPC，不暴露公网                                        │
│  2. 数据跨组件流转不离开企业网络边界                                               │
│  3. 管理员访问需通过堡垒机+双因素认证                                              │
│  4. 所有访问记录审计追踪                                                           │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 21.8 企业级实施路线图

| 阶段 | 目标 | 核心交付 | 周期 |
|---|---|---|---|
| **POC阶段** | 验证核心能力 | 单节点部署 + 软件开发工厂 | 1-2个月 |
| **试点阶段** | 企业内试点 | 高可用集群 + 审计+治理 + 多部门 | 3-6个月 |
| **推广阶段** | 全企业推广 | 多工厂 + 经验沉淀 + 合规认证 | 6-12个月 |
| **平台阶段** | 持续运营 | 企业级最佳实践库 + 行业模板 | 持续 |

---

*本补充文档与主文档 v3.0 完全兼容，新增章节编号为 十八、十九、二十、二十一。*

### 21.9 企业级实现对照与落地

| 项 | 状态 |
|---|---|
| SAP 深度对标（21.3/21.4 战略） | ✅ 文档（战略借鉴） |
| 与国产化 ERP 对标 / 适配清单 / 功能矩阵（21.2/21.5/21.6） | 📐 战略文档 |
| 企业部署架构（21.7） | ✅ 架构对齐（§18.2 三种部署模式） |
| 企业级实施路线（21.8） | 📐 长期 |
| 企业级认证（信创/SOC2/等保） | 📐 长期（资质工程） |
| 企业级产品能力（多租户/RBAC/SSO/合规） | 📐 M7+ |

**结论**：企业级章节是**战略与对标文档**（✅ 已有）；落地（认证/多租户/合规）为企业级阶段（📐 长期）——按 §1.5 三档取舍，不承诺近期。
---

## 二十二、SDK 化与商业化路线（从内部系统到可交付产品）★

> 2026-08-24 补充（Founder 战略问题）: 如何强化架构达到 SDK 标准、让别人使用、可商业化。
> 先立架构体检基线（合理/真实/可靠），再给 SDK 差距 + 4 阶段路线 + API 盘点 + 商业化。

### 22.0 架构体检基线（2026-08-24 终审）★

**客观数据**: 130,786 行代码 / 508 测试文件 / 12030+ passed / v1.1.14 / 712 commits /
21 章 10000+ 行文档 / §1.4 状态 13✅ 10🚧 4📐

**三维评估**

| 维度 | 结论 | 证据 |
|---|---|---|
| **合理** | ✅ | ChatGPT 独立验证方向（自有 Runtime / Universal Node / Recursive Loop = §4.12+M3a）· 四仓分层自洽 · 8 失败模式 6/8 有设计应对 |
| **真实** | ⚠️ 内核真、外围部分真 | 130K 行可跑（M1-M3 内核/证据/审批/沙箱/审计/记忆）· 7 角色 2 占位（ux/qa）· API HTTP 绑定部分 · 调度器未接管真实执行 · **设计 > 实现** |
| **可靠** | ⚠️ 基线可靠、生产级未证明 | 测试 0 失败 / 失败恢复 / 确定性兜底 / 可追溯 ✅ · 长任务 / 多项目并发 / 故障演练 / 真实负载 未证明 |

**三个必须认清的弱点**
1. **M3 调度器还没接管真实执行**（execute_project 仍顺序旧路径）——"设计真实"与"执行真实"的最大裂缝
2. **文档 > 实现**（§1.4 状态表是防误读的关键, 需持续维护）
3. **无生产级证明**（一切验证都在沙箱内测试, 无真实用户/长任务/故障演练背书）

### 22.1 与主流框架的定位（ChatGPT 独立验证）★

ChatGPT 2026 框架分析结论: AI Factory **不应选任何框架当核心**, 应自有
Native Runtime + Universal Node + Recursive Node Loop, 外部框架只当执行器（Adapter）。

| 对比项 | 吻合度 |
|---|---|
| 自有 Runtime / Universal Node / Recursive Loop / Evidence-Verification-Event | ✅ 完全吻合（§4.12 + M3a 已实现） |
| 治理/安全/记忆/交付/行业复制 | ✅ **超出**（ChatGPT 架构缺失, AI Factory 有） |
| 框架适配器层（Claude SDK / OpenAI SDK / LangGraph 作为可插拔执行器） | 🟡 可吸收（T 系列扩展, 不改变内核） |

定位一句话: LangChain 造 Agent, LangGraph 编排 Agent 工作流, **AI Factory 建立和管理
整个 AI 生产组织**——AI Factory 是比"框架"高一个维度的存在（内核+治理+安全+记忆+交付+行业）。

### 22.2 SDK 差距分析（当前 vs SDK 标准）

| SDK 标准 | 现状 |
|---|---|
| 可安装（pip） | ✅ ai-software-factory v1.1.14（package-dir 映射 + console script） |
| 稳定 public API | 🚧 四仓可 import, 但**未定义对外稳定面** |
| SDK 文档（API reference / quickstart） | ❌ 只有方案书, 无 SDK 文档 |
| 可嵌入（Headless） | 🚧 库可调, 但入口是 CLI 思维 |
| 错误码对外契约 | 🚧 E4xx 有, 未文档化为对外契约 |
| 插件生态 | 📐 Skill/MCP 雏形, 无正式插件 API |
| 部署形态 | 🚧 pip, 无容器/云形态 |

### 22.3 4 阶段路线

```
阶段 1 内核收尾 (M3 完成→v1.2): 调度器接管真实执行 · 并行线程化 · 原子沙箱 · M4 学习闭环
阶段 2 SDK 化 (v1.2.x): public API 边界 · SDK 文档 · 错误码契约 · Headless · 版本承诺
阶段 3 可扩展/生态 (v1.3): 插件 API · 事件订阅 · 模板市场
阶段 4 商业化 (v2): 开源核心+商业增值拆分 · 第一个付费场景 · 部署形态
```

### 22.4 API 能力盘点与缺口

**现状（比想象中强）**:
- 22 API 模块 / 125+ 路由函数（项目/审计/执行/记忆/审批/积压/调试/技能/工作流/工具/运行时/会话/智能）
- 79 个 HTTP 端点（FastAPI adapter 2018 行: projects/discovery/backlog/sprints/milestones/approvals/decisions...）
- **统一入口 ✅**（单 FastAPI app + /api 前缀 + 统一 HTTPException）

**缺口（对外成熟度不够）**:

| 缺口 | 说明 |
|---|---|
| 统一入口版本化 | /api/v1 前缀未落实（§2.11.2 设计） |
| 认证/授权 | 0 认证（本地可跑, 对外裸奔） |
| 统一错误码契约 | HTTPException 404/409/400, 非 §2.11.3 E4xx 体系 |
| public API 边界 | 稳定对外面 / internal 未定义（别人不敢依赖） |
| **API 监控** | **无**（只有业务审计"谁调了", 无性能指标"调得怎样"） |

**审计 vs 监控边界（§5.9）**: 审计记"谁调了什么"（✅ 有: console.viewed 等事件）;
监控记"调用量/延迟/错误率"（❌ 无: 需补中间件 + §5.8 时序存储）。

#### 22.4.1 能力 → API 映射总表（60 能力 × API 状态）★

> 2026-08-24 补充（Founder 追问: 全部能力有哪些, 哪些 API 没有）: 原则 = **每个能力
> 必须 CLI + API 双暴露**（§22.1）。审计结果: 60 能力中 **19 有 API（32%）· 41 缺（68%）**。

**✅ 有 API 的能力（19 个 — 项目/审批/运行主流程）**

| 能力 | API 端点 |
|---|---|
| create_project / create_product | POST /api/projects |
| list_projects | GET /api/projects |
| rename_project | PATCH /api/projects/{id} |
| discovery_start | POST /api/projects/{id}/discovery/answer·complete |
| prepare_project | POST /api/projects/{id}/confirm |
| execute_project | POST /api/projects/{id}/start |
| show_status | GET /api/projects/{id}/status |
| project_progress | GET /api/projects/{id}/run-status |
| project_timeline | GET /api/projects/{id}/timeline |
| review_view | GET /api/review-feedback · /api/approvals |
| review_approve | POST /api/approvals/{id}/approve |
| review_reject | POST /api/approvals/{id}/reject |
| agent.execute_task | POST /api/runtime/execute |
| production_session_view | GET/POST /api/runtime-sessions |
| backlog / sprints / milestones | /api/projects/{id}/backlog·sprints·milestones |
| workflows / artifacts / tools / skills / mcp | 对应资源端点 |

**❌ 缺 API 的能力（41 个 — 治理/可观测/学习/团队全缺）**

| 能力族 | 数量 | 缺失清单 |
|---|---|---|
| 审计族 | 10 | audit_events · audit_trace · audit_chain · audit_decision · audit_explain · audit_task · audit_agent · audit_cost · audit_export · audit_stats |
| 调试族 | 9 | debug_analyze · debug_history · debug_recommend · debug_stats · debug_session · debug_root_cause · debug_repair · debug_validate · debug_resume |
| 记忆族 | 5 | memory_search · memory_learn · memory_stats · memory_analyze_agent · memory_export |
| 产品智能族 | 5 | product_intelligence · product_market · product_persona · product_mvp · product_value |
| 团队族 | 4 | team_execute · team_dependencies · team_conflicts · team |
| 工厂治理族 | 3 | factory_status · factory_budget · factory_review |
| 产品流程族 | 3 | generate_prd · product_pipeline · project_docs |
| 执行治理族 | 2 | repair_task · accept_project |
| 其他 | 5 | workforce · task_owner · agent_reason · resume_project · review_cancel |

**判断**: 主流程（建项目→拆解→执行→审批）✅ 通了; 治理/可观测/学习/团队
（企业最需要对外集成的）❌ 全没 API——API 化原则只执行了 1/3。

**补 API 优先级**: 审计族(10) → 记忆族(5) → 调试族(9) → 产品智能(5) →
团队(4) → 工厂治理(3) → 产品流程(3) → 执行治理(2) → 其他(5)。
——审计/记忆是企业最需要的对外能力, 优先补。

**能力→端点映射表 = SDK 文档骨架**（每个能力: CLI ✅ / API ✅|❌ 状态列）。

### 22.5 商业化模式（三选, 可叠加）

```
A. 开源核心 + 云 SaaS: SDK 免费, 云上跑收订阅（对标 LangChain + LangSmith）
B. 自托管许可证: 企业内网部署, 按席位/项目收（治理/合规敏感行业）
C. 支持 + 定制: 大客户实施 + 行业工厂定制
验证路径: 先一个付费场景（积压清道夫/治理平台 §6.7）→ 1 个客户跑通 → 再扩
信任三件套（证据/审批/回滚）已是企业付费前提 ✅
```

### 22.6 下一步清单（按优先级）

```
[ ] 1. M3 收尾: 调度器接管真实执行（架构真实性最大裂缝）
[ ] 2. public API 边界定义 + SDK quickstart（30 分钟跑通"拆解→调度"示例）
[ ] 3. API 补全: /api/v1 + 认证 + E4xx 契约 + API 监控中间件
[ ] 4. SDK 文档（API reference）+ Headless 示例 + 插件 API 第一版
[ ] 5. 商业化拆分决策（开源核心 vs 企业版边界）+ 第一个付费场景
```

**结论**: AI Factory 已具备 SDK 的**地基**（可安装/版本/契约/模型）, 缺的是
**"对外承诺"**: 稳定 public API + SDK 文档 + Headless 可嵌入 + 插件生态 + API 监控。
商业化不必等全部做完——**内核收尾 + 一个付费场景**就够启动。

### 22.7 架构 S-R-U-C-T 五维评测体系（安全 × 可靠 × 易用 × 完整 × 值得信赖）★

> 2026-08-24 Founder 定级 P0: 评测可靠性不能靠感觉, 要靠**可执行的评测体系 + 证明等级**。

**7 个评测维度**

| 维度 | 评测什么 | 方法 | 当前状态 |
|---|---|---|---|
| ① 正确性 | 做对了吗 | 全量回归 + 契约测试 + 属性测试（随机输入不崩） | ✅ 12030 passed |
| ② 鲁棒性 | 坏了能恢复吗 | **故障注入矩阵**（LLM/沙箱/审批/数据/环境 5 类故障 → 断言行为） | ❌ 无 |
| ③ 一致性 | 数据对吗 | 投影对账（§5.11.6）· 审计链 hash 校验 · 状态机合法性 | 🚧 审计链✅ 对账📐 |
| ④ 性能 | 快吗/省吗 | 单任务耗时成本 · 长任务稳定性 · 并发吞吐 · 资源水位 | 🚧 零散 |
| ⑤ 安全 | 被攻破吗 | 8 威胁 × 防御实测（§20.7）· 沙箱逃逸测试 | 🚧 部分 |
| ⑥ 长期 | 跑得久吗 | 24h 长跑 · 多项目并发 · 内存泄漏 · 万级事件数据增长 | ❌ 无 |
| ⑦ 用户价值 | 有用吗 | 端到端场景成功率 · 修复成功率 · 每任务成本可查 | 🚧 有演示 |

**故障注入矩阵（鲁棒性关键）**

```
每类故障注入 → 断言系统行为（恢复/降级/失败安全）
  LLM:    无 key / 超时 / 返回垃圾 / 断连
  沙箱:   逃逸尝试 / 磁盘满 / 权限拒绝
  审批:   拒绝 / 挂起 / 并发审批
  数据:   文件损坏 / 缺字段 / 非法状态
  环境:   进程被杀 / 网络断 / 并发写
  断言: 不崩 + 明确错误 + 可恢复 + 审计记录
```

**可靠性证明等级（L0-L3）**

```
L0 测试绿:  全量回归 0 失败 + 契约测试过          ← 现在有（基线）
L1 故障恢复: 故障注入矩阵全过                     ← 最大缺口（要有）
L2 长跑稳定: 24h 长任务 + 多项目并发 + 数据增长    ← 要有
L3 生产证据: 真实用户场景跑通 + 可演示            ← 目标
```

**发布门（每版本必须达到的等级）**

```
patch 版本: L0
minor 版本: L0 + L1（故障注入）
major / 商业化: L0 + L1 + L2 + L3
```

**落地**: 建故障注入测试套件（test_reliability/）· 一致性校验器（§5.11.6 设计实现）·

---

**扩展为三维（2026-08-24 Founder 追问: 如何评测 安全 + 可靠 + 易用）**
**① 安全评测（S0-S3）**

| 维度 | 评测什么 | 方法 |
|---|---|---|
| 机密性 | 数据/凭证不泄露 | 凭证扫描 · 网络隔离测试 · 权限绕过测试 |
| 完整性 | 数据/代码不被篡改 | 审计链 hash 校验 · 沙箱逃逸测试 |
| 可用性 | 不被搞瘫 | 资源耗尽测试 · 熔断测试 |
| AI 特有 | 提示词注入/越狱/串通 | 注入测试 · 越狱 payload 测试 |

```
证明等级:
  S0 基线:   无已知高危漏洞 + 审批/审计在（现在: ✅ 部分）
  S1 威胁核对: §20.7 8 威胁 × 防御实测（逐项）
  S2 渗透实测: 沙箱逃逸 / 提示词注入 / 权限绕过 真实攻击测试
  S3 认证:    SOC2 / 等保 / 信创
```

**② 可靠评测（L0-L3, 见上）**: L0 测试绿 → L1 故障恢复 → L2 长跑稳定 → L3 生产证据。

**③ 易用评测（U0-U3）**

| 维度 | 评测什么 | 方法 |
|---|---|---|
| 上手快 | 从 0 到第一个产品跑通多久 | 新人计时测试（30 分钟目标） |
| 可理解 | 心智模型清晰吗 | 首次使用后能否解释"它怎么工作" |
| 可发现 | 命令/API 找得到吗 | help 完整度 · 自动补全 · 文档搜索 |
| 可容错 | 出错能自解吗 | 错误信息含"下一步"提示（非裸 traceback） |
| 可撤销 | 误操作能回滚吗 | 撤销/恢复路径测试（§5.12） |
| 可引导 | 有引导吗 | onboarding 流程 · 示例 · 模板 |

```
证明等级:
  U0 可用:   CLI 能跑通核心流程（现在: ✅）
  U1 可学:   新人 30 分钟跑通一个产品（计时测试 — 未做过）
  U2 可发现: help/命令/API 自文档化完整
  U3 可依赖: 错误可自解 + 可撤销 + 有引导（无需看源码）
```

**三维合一发布门**

```
patch 版本:     S0 + L0 + U0
minor 版本:     S1 + L1 + U1
major / 商业化: S2/S3 + L2/L3 + U2/U3
```



---

**扩展为五维（2026-08-24 Founder 追问: 还有"完整"和"值得信赖"）**

**④ 完整度评测（Completeness, C0-C3）**

| 评测什么 | 方法 |
|---|---|
| 能力覆盖 | 能力→API 映射核对（§22.4.1: 60 能力 × API 状态） |
| 流程闭环 | 想法→交付→运维→记忆 端到端走通率 |
| 数据闭环 | 拆解→计划→调度→执行→证据→审批→交付→记忆 数据流通 |
| 8 层覆盖 | 能力/编排/执行/记忆/治理/可观测/安全/交付 × 设计/实现/测试 |
| 异常路径 | 失败/恢复/回滚分支全有处理 |

```
证明等级:
  C0 主流程通: 想法→交付 最小闭环（现在 ✅: 拆解→关键路径→调度→沙箱→证据→审批）
  C1 能力全覆盖: 60 能力 × API 全有 + 8 层设计实现（现在 ❌: API 只 32%）
  C2 异常全覆盖: 失败/恢复/回滚路径全测
  C3 生态完整: 插件/模板/多行业
```

**⑤ 值得信赖评测（Trustworthiness, T0-T3）** — 信任 = 可验证+可审计+可解释+可控

| 评测什么 | 方法 |
|---|---|
| 可验证 | 每个交付有证据包（EvidenceBundle） |
| 可审计 | 全链路事件 + hash 防篡改 |
| 可解释 | 每个决策有 why（决策链） |
| 可控 | 高风险全审批 + 变更可回滚 |
| 数据主权 | 数据不出内网 |

```
证明等级:
  T0 可追溯: 审计链完整 + 事件可查（现在 ✅）
  T1 可验证: 交付有证据包 + 决策有解释（现在 🟡 部分）
  T2 可控制: 高风险全审批 + 变更全可回滚（审批✅ 回滚📐）
  T3 可证明: 第三方可审计（SOC2 型）+ 数据主权认证
```

**五维合一发布门**

```
patch:        S0 + L0 + U0 + C0 + T0
minor:        S1 + L1 + U1 + C1 + T1
major/商业化: S2/L2/U2/C2/T2（+ 认证 S3/L3/U3/C3/T3）
```



---

### 22.8 五维真实状态体检（2026-08-24 基线，每里程碑更新）★

> 基于证据（不吹捧）: 当前 = **垂直主流程真实可用的 MVP+**。

| 维 | 当前 | 真实有（证据） | 缺（证明级） |
|---|---|---|---|
| 安全 S0 | ✅ 基线 | 沙箱目录隔离+git 校验 · 审批门分级 · patch 白名单 · 凭证 env 引用 · 审计 hash 链 | 8 威胁仅 4 实测；沙箱网络/进程/凭证 3 层隔离；注入/串通检测 |
| 可靠 L0 | ✅ 基线 | 12030 passed/0 failed · 失败恢复(repair/replan) · 无 LLM 诚实降级 | 故障注入矩阵 · 一致性校验器 · 24h 长跑/多项目并发 |
| 易用 U0 | ✅ 基线 | CLI 全命令 · help · 中文错误信息 | 新人计时测试 · quickstart/示例 · onboarding 引导 |
| 完整 C0 | ✅ 基线 | 想法→PRD→拆解→关键路径→调度→沙箱→证据→审批 垂直链路可跑 | 60 能力 API 只 32% · 8 层治理/可观测深化 · 回滚(设计) |
| 信赖 T0 | ✅ 基线 | 审计链 hash 防篡改 · 血缘(parent_artifact) · 证据包(M1a) | 证据覆盖率非 100% · 决策解释非全链路 · 回滚未实现 |

**定位**: "能跑的产品原型 + 22 章完整设计蓝图", 不是"可交付的 SDK/商业化产品"。

---

### 22.9 五维升级路线（X0 基线 → X1 证明 → X2 强化 → X3 认证）★

**安全 S**: S1 威胁核对（8 威胁实测, P0-6）+ 沙箱 3 层隔离（§5.13.4）→ S2 渗透实测 → S3 认证（SOC2/等保）

**可靠 L**: L1 故障注入矩阵（P0-2）+ 一致性校验器（P0-3）→ L2 24h 长跑+并发（P0-4）→ L3 生产证据

**易用 U**: U1 新人 30 分钟跑通 + quickstart/示例（P0-7）→ U2 help/API 自文档化 → U3 错误可自解+引导

**完整 C**: C1 60 能力 × API 100%（§22.4.1 补 41 缺口, P0-8）+ 8 层核对 → C2 异常全覆盖（回滚 M4-6）→ C3 生态（插件/模板/多行业）

**信赖 T**: T1 证据覆盖率 100% + 决策解释全链路（P0-9）→ T2 回滚实现 + 审批全率核对 → T3 第三方审计

---

### 22.10 五维升级执行 Plan（4 波，每波 = 可验证的等级跃迁）★

```
波 1 — M3 收尾 + 地基（当前~v1.2）
  ① 调度器接管真实执行（架构真实性最大裂缝）
  ② 故障注入矩阵 L1 建起（P0-2）——可靠升 L1 的起点
  ③ 回滚实现提前（M4-6, 信赖 T2 的基础）

波 2 — 五维证明级（v1.2.x, P0 全清）
  ④ 安全 S1: 8 威胁实测 + 沙箱 3 层隔离（P0-6）
  ⑤ 可靠 L1 完成: 故障注入全过 + 一致性校验器（P0-2/P0-3）
  ⑥ 易用 U1: 新人 30 分钟跑通 + quickstart + 示例（P0-7）
  ⑦ 完整 C1: 41 个缺 API 补齐（P0-8, 审计→记忆→调试→产品智能→团队→工厂）
  ⑧ 信赖 T1: 证据覆盖率 100% + 决策解释全链路（P0-9）
  发布门: minor = S1+L1+U1+C1+T1 ✅

波 3 — SDK 化（v1.3, §22.3 阶段 2/3）
  ⑨ public API 边界 + SDK 文档（能力→端点映射 = 骨架）
  ⑩ Headless 模式 + 插件 API 第一版
  ⑪ API 补全: /api/v1 + 认证 + E4xx + API 监控

波 4 — 商业化（v2, §22.3 阶段 4）
  ⑫ 第一个付费场景（积压清道夫/治理平台）跑通 1 客户
  ⑬ 长跑+并发 L2 + 渗透 S2（生产级证据）
  ⑭ 开源核心 + 企业版拆分 + 认证（S3/T3）
  发布门: major = S2/L2/U2/C2/T2 + 认证 ✅
```

**每波验收**: 五维对应等级实测表 + 全量回归 + 用户实测——"可靠"从感觉变成每波可证明的跃迁。
24h 长跑 + 并发脚本 · 安全 8 威胁实测核对 · 发布门自动化。待办清单 P0-1~P0-5。
