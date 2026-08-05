# AI Software Factory — 架构设计

> 版本: v1.0 | 状态: 设计稿 | 关联文档: [runtime-design.md](./runtime-design.md)
>
> 本文档基于 MarkPad 项目的真实运行经验抽象而来,目标是定义一个**通用 AI Software Factory Runtime**(下文简称 Factory),不绑定任何具体 Agent 实现、模型或工具链。

---

## 0. 设计目标与原则

Factory 解决的核心问题:多 Agent 协作执行软件项目时,如何保证**可控(不失控)、可观测(不黑盒)、可恢复(不从头再来)、可度量(不只靠感觉)**。

设计原则(全部来自实证教训):

| 原则 | 实证来源 |
|---|---|
| **KISS — 最小模块集**,每个模块只干一件事 | 9 个模块即可覆盖全部经验模式 |
| **Orchestrator 不写代码** — 管理层只决策、委派、验收 | MarkPad 全部实现经委派完成 |
| **一切以事件为中心** — 任何状态变化都落事件流 | 截断续跑靠读 summary,若有事件流可精确恢复 |
| **自报告不可信,验证独立** — Agent 说的不算,验证引擎说了算 | 误 git checkout / 覆盖文件 2 次 |
| **文件即事实** — 文件范围声明 + 锁 + 校验,杜绝越权写 | Allowed/Forbidden 清单生效 |
| **可断点续传** — 任何时刻可中断、可恢复 | 截断续跑约 10 次 |
| **人只出现在少数闸口** — 产品冲突/架构变更/Scope 扩展才暂停 | 三挡板 |

---

## 1. Hermes 当前能力地图

> 本节记录 Hermes(MarkPad 会话中实际运行的形态)的七项核心能力,是 Factory 设计的**经验来源**,Factory 是对这些能力的抽象与补全。

### 1.1 Orchestrator(总指挥)

| 项 | 内容 |
|---|---|
| **职责** | 全局决策:拆解项目、定义任务、选择 Agent、验收结果;自己不写代码 |
| **输入** | 用户目标 / 里程碑、任务产出报告、验证引擎结论、三挡板事件 |
| **输出** | 任务定义(Task)、委派指令、批准/驳回决定、下一任务选择 |
| **当前实现** | 会话式:Orchestrator 以对话形式管理委派(sub-agent)、串行推进里程碑,手工维护任务状态 |
| **不足** | ① 任务状态散落在对话中,无持久化任务对象;② 决策依赖上下文窗口,长会话易截断;③ 无显式决策记录,事后无法回放"为什么这么决定" |

### 1.2 Agent Management(Agent 管理)

| 项 | 内容 |
|---|---|
| **职责** | 按角色生成/回收 sub-agent,注入角色指令与约束(文件范围、锁) |
| **输入** | 委派指令(角色、任务描述、Allowed/Forbidden 文件、工具上限) |
| **输出** | 运行中的 Agent 实例、会话摘要(summary)、工具迭代上限截断 |
| **当前实现** | delegate_task 动态生成;每次会话按需创建,无实例持久化;截断后读完整 summary 续跑 |
| **不足** | ① 无 Agent 注册表,不知道"当前有哪些 Agent、在干什么";② 截断后靠 summary 恢复,信息有损;③ Agent 无独立身份/历史,不可统计(如首次成功率) |

### 1.3 Skill Loading(Skill 加载)

| 项 | 内容 |
|---|---|
| **职责** | 为角色装配专业能力(开发/测试/架构/调试/产品/发布验证各加载对应 Skill) |
| **输入** | 角色标识、任务类型 |
| **输出** | 该 Agent 可用的方法集(检查清单、命令序列、质量标准) |
| **当前实现** | 手工指定 Skill;Skill 以 markdown 文档形式存在,按需加载 |
| **不足** | ① Skill 与角色绑定关系未显式声明,靠 Orchestrator 记忆;② Skill 更新无版本控制,无法追溯"某任务用了哪个版本的 Skill" |

### 1.4 Workflow Execution(工作流执行)

| 项 | 内容 |
|---|---|
| **职责** | 执行项目流程:决策门、双验证、三挡板、串行访问锁 |
| **输入** | 任务、角色、决策门定义(架构设计→审查→批准→实施) |
| **输出** | 阶段推进、闸口决定(继续/暂停)、任务完成信号 |
| **当前实现** | Orchestrator 在对话中手动执行流程:设计→审查→批准→实施;三挡板(产品冲突/架构变更/Scope 扩展)暂停 |
| **不足** | ① 流程逻辑与对话混在一起,不可复用、不可配置;② 挡板判定靠 Orchestrator 主观判断,无结构化事件触发;③ 无工作流状态机,中断后流程位置靠人脑记忆 |

### 1.5 Validation(验证)

| 项 | 内容 |
|---|---|
| **职责** | Agent 自报告后,由独立主体验证(analyze/test/grep/read_file 等) |
| **输入** | Agent 的完成报告、涉及文件、验收标准 |
| **输出** | 验证结论(通过/失败/偏差)、证据(命令输出、diff) |
| **当前实现** | Orchestrator 独立复核:读文件、跑测试、查 diff;验证与实现主体分离 |
| **不足** | ① 验证结果不落库,无法形成质量趋势;② 靠人(Orchestrator)盯着才执行,无强制验证门;③ 对"越权写文件"类问题仅有事后发现,无事前防护 |

### 1.6 Memory(记忆)

| 项 | 内容 |
|---|---|
| **职责** | 项目知识沉淀:决策、会话、缺陷 |
| **输入** | 架构决策、会话记录、Bug 报告 |
| **输出** | docs/adr/ + docs/session/ + docs/bugs/ 结构化归档 |
| **当前实现** | 手动归档三类文档;ADRs 记录决策及理由 |
| **不足** | ① 归档靠人自觉,易漏;② 是文档不是数据库,无法按结构化字段查询;③ 知识与事件(何时、谁、为什么)分离,无法关联追溯 |

### 1.7 Task Management(任务管理)

| 项 | 内容 |
|---|---|
| **职责** | 任务拆分、分配、进度跟踪、续跑 |
| **输入** | 里程碑、模块边界、依赖关系 |
| **输出** | 可委派的任务单元、任务状态、续跑点 |
| **当前实现** | Orchestrator 手工拆解;截断续跑时"读 summary → 不 git checkout → 续跑" |
| **不足** | ① 任务无 ID/状态机/依赖图,进度不可查询;② 续跑是经验性操作(靠 summary + 人判断),不可复现;③ 任务粒度凭感觉,过大导致截断频繁(约 10 次) |

### 1.8 能力差距总结(Factory 要补的洞)

| 差距 | 对应 Factory 模块 |
|---|---|
| 任务状态无持久化、无状态机 | Task Manager |
| 无 Agent 清单与统计 | Agent Registry |
| 无结构化事件与回放 | Event Logger |
| 无统一验证门与证据链 | Validation Engine |
| 无可视化进度/阻塞 | Dashboard |
| 指标未自动收集(first_attempt_success / path_errors / human_intervention) | Event Logger + Dashboard |
| 流程不可配置复用 | Workflow Engine |

---

## 2. AI Software Factory Runtime 架构

### 2.1 架构图

```
                            ┌─────────────────────┐
                            │      Dashboard      │  可观测层
                            │  (Project/Task/Agent │
                            │   Status/Progress)   │
                            └──────────┬──────────┘
                                       │ 查询(只读)
┌──────────────┐   任务定义    ┌────────▼──────────┐
│   PO / 用户   │──────────────▶│   Orchestrator    │  决策层
│ (唯一验收人)  │              │  (不写代码)        │
└──────────────┘              └───┬───────┬───────┘
       ▲            批准/驳回/验收 │       │ 任务/闸口事件
       │                          ▼       ▼
┌──────┴───────────┐      ┌──────────────┐   ┌──────────────────┐
│  Workflow Engine │◀─────│ Task Manager │   │  Agent Registry  │
│ (决策门/挡板/状态机)│      │ (状态机/断点) │   │ (角色/实例/统计)  │
└──────┬───────────┘      └──────┬───────┘   └────────┬─────────┘
       │ 执行步骤                 │ 分配                │ 实例化
       │                ┌────────▼────────┐           │
       │                │      Agent      │◀──────────┘
       │                │ (角色 + Skill)   │
       │                └───────┬─────────┘
       │             自报告/产物  │
       ▼                        ▼
┌──────────────┐        ┌──────────────┐
│ Skill Registry│       │ Validation    │  执行层
│ (角色→Skill 表)│       │ Engine        │  (独立于 Agent)
└──────────────┘        │ (校验+证据链)  │
                        └──────┬───────┘
                               │ 写入/读取
                        ┌──────▼───────┐
                        │ Knowledge Base│  知识层
                        │ (ADR/会话/缺陷)│
                        └──────┬───────┘
                               │
                        ┌──────▼───────────────────────────────┐
                        │        Event Logger(事件总线)        │
                        │ 所有模块的唯一事实来源(Single Source │
                        │ of Truth):一切状态变化 = 事件         │
                        └──────────────────────────────────────┘
```

**核心思想:所有模块只通过两条通道交互 —— ① 直接调用(控制流,上游→下游);② Event Logger(信息流,所有状态变化以事件发布)。任何模块不直接修改他模块的状态,只发事件。**

### 2.2 模块规格

#### M1 Orchestrator(决策中枢)

| 项 | 内容 |
|---|---|
| **职责** | 全局决策:目标拆解、任务审批、结果验收、三挡板判定、向 PO 上报 |
| **输入** | PO 目标、任务完成事件+验证结论、闸口事件(产品冲突/架构变更/Scope 扩展) |
| **输出** | 任务定义、批准/驳回/返工决定、验收结论、挡板上报 |
| **依赖** | Task Manager(取任务)、Validation Engine(取结论)、Event Logger(订阅事件) |
| **约束** | 不写代码、不直接操作文件;一切执行委派给 Agent |

#### M2 Task Manager(任务状态机)

| 项 | 内容 |
|---|---|
| **职责** | 任务生命周期管理:拆解、分配、状态迁移、断点续传、依赖排序 |
| **输入** | 任务定义、委派结果、完成事件、续传指令 |
| **输出** | 任务状态(见 runtime-design §4.1)、可执行任务队列、续传点(checkpoint) |
| **依赖** | Agent Registry(找 Agent)、Event Logger(发布状态事件)、Workflow Engine(触发流程) |
| **关键设计** | 任务状态机: `pending → assigned → running → verifying → done | blocked | failed`;任何状态迁移必须发事件;每次委派前记录 checkpoint(任务+上下文引用),截断/失败后从 checkpoint 续跑,不依赖对话记忆 |

#### M3 Agent Registry(Agent 注册表)

| 项 | 内容 |
|---|---|
| **职责** | 注册/实例化/回收 Agent;记录角色、Skill 绑定、运行统计 |
| **输入** | 角色定义、任务分配请求、Agent 生命周期事件 |
| **输出** | Agent 实例、角色→Skill 映射、指标(first_attempt_success、path_errors、human_intervention) |
| **依赖** | Skill Registry(取 Skill)、Event Logger(发布生命周期事件) |
| **关键设计** | Agent 有全局唯一 ID,存活期跨任务;统计按 agent_id 聚合,支撑"哪个角色最不可靠"这类度量 |

#### M4 Skill Registry(Skill 注册表)

| 项 | 内容 |
|---|---|
| **职责** | 管理 Skill 元数据:名称、版本、适用角色、触发条件 |
| **输入** | Skill 注册(版本化)、角色装配请求 |
| **输出** | 角色可用 Skill 清单、Skill 版本快照(随任务归档) |
| **依赖** | Event Logger(发布加载事件) |
| **关键设计** | Skill 有版本;任务归档时记录所用 Skill 版本,保证可复现 |

#### M5 Workflow Engine(流程引擎)

| 项 | 内容 |
|---|---|
| **职责** | 执行可配置流程:决策门(设计→审查→批准→实施)、双验证、三挡板、串行锁 |
| **输入** | 流程定义(声明式)、任务、事件(Agent 完成、验证结果) |
| **输出** | 流程推进指令、闸口决定(继续/暂停/返回)、锁的获取/释放 |
| **依赖** | Task Manager、Validation Engine、Event Logger |
| **关键设计** | 流程=状态机+守卫条件;三挡板注册为监听器:事件命中挡板(产品冲突/架构变更/Scope 扩展)→ 暂停并上报 PO;关键文件锁(如 editor_page/block_editor)以资源锁实现,同一资源串行访问 |

#### M6 Knowledge Base(知识库)

| 项 | 内容 |
|---|---|
| **职责** | 结构化沉淀:决策(ADR)、会话/任务轨迹、缺陷、经验教训 |
| **输入** | 事件流(自动沉淀)、归档指令(人工/PO 决策) |
| **输出** | 可查询的知识(按项目/任务/时间/类型)、决策依据 |
| **依赖** | Event Logger(消费事件,自动归档) |
| **关键设计** | 事件流是"流水",Knowledge Base 是"沉淀":按规则从事件自动生成 ADR/Bug 记录;人工只补充判断,不补抄 |

#### M7 Validation Engine(验证引擎)

| 项 | 内容 |
|---|---|
| **职责** | 独立验证 Agent 产物:验收标准检查、文件范围核对、测试执行、diff 审计;产出证据链 |
| **输入** | 完成事件、涉及文件清单、验收标准、文件范围声明(Allowed/Forbidden) |
| **输出** | 验证结论(pass/fail/偏差)、证据(命令输出/diff/测试报告) |
| **依赖** | Knowledge Base(验收标准)、Event Logger(发布验证事件) |
| **关键设计** | 独立于 Agent 运行;对文件系统操作先做范围校验(越权即拦截+记录 path_errors);对 git 类危险操作(commit/checkout/覆盖)强制走预检与备份 |

#### M8 Event Logger(事件日志器 / 事件总线)

| 项 | 内容 |
|---|---|
| **职责** | 收集、持久化、分发所有事件;提供回放与指标聚合;是系统的 Single Source of Truth |
| **输入** | 各模块的 append-only 事件 |
| **输出** | 事件流(供 Dashboard 查询、Knowledge Base 沉淀、Orchestrator 决策) |
| **依赖** | 无(最底层基础设施) |
| **关键设计** | append-only、不可变;事件带时间戳与来源;支持按 project/task/agent 索引;指标(first_attempt_success/path_errors/human_intervention)由事件聚合得出,不另建统计表 |

#### M9 Dashboard(仪表盘)

| 项 | 内容 |
|---|---|
| **职责** | 可观测性:展示项目/任务/Agent 状态、进度、当前动作、阻塞点、指标 |
| **输入** | Event Logger 的只读查询 |
| **输出** | 实时视图(Project/Task/Agent/Status/Current Action/Progress/Last Event/Next Action) |
| **依赖** | Event Logger(唯一依赖) |
| **关键设计** | 无状态、只读;不做任何写操作;视图由事件流投影(projection)生成,重启可重建 |

### 2.3 模块依赖图(简)

```
Orchestrator ──▶ Task Manager ──▶ Agent Registry ──▶ Skill Registry
     │                │  │              │
     │                │  └──────────────▶ Agent(执行)
     │                ▼  ▼              │
     └─────────▶ Workflow Engine ◀──────┘
                      │
Validation Engine ◀───┘   (验证 Agent 产物)
      │
Knowledge Base ◀──────── (沉淀)
      │
Event Logger ◀────────── (一切模块发布事件到这里)
      ▲
Dashboard(只读查询)
```

---

## 3. 与实证素材的对应关系

| 实证模式 | Factory 中的落点 |
|---|---|
| Orchestrator 委派、不写代码 | M1 Orchestrator + M2 Task Manager |
| 多角色 Agent 加载专业 Skill | M3 Agent Registry + M4 Skill Registry |
| 双验证(自报告 + 独立复核) | M7 Validation Engine + 工作流"验证门" |
| Decision Gate(设计→审查→批准→实施) | M5 Workflow Engine 决策门 |
| 文件范围声明(Allowed/Forbidden) | M7 Validation Engine 范围校验 |
| 关键文件锁(串行访问) | M5 Workflow Engine 资源锁 |
| 截断续跑(summary + 不 checkout + 续跑) | M2 Task Manager checkpoint 续传 + M8 事件回放 |
| 三挡板暂停 | M5 Workflow Engine 挡板监听器 |
| 用户 = PO 最终验收 | M1 Orchestrator 上报 PO 闸口 |
| ADR/会话/Bug 归档 | M6 Knowledge Base 自动沉淀 |

## 4. 已知不足的解决映射

| 不足 | 解法(设计层面) |
|---|---|
| 截断频繁(~10 次) | Task Manager 强制任务粒度上限(单任务预估工具调用 ≤ N,超出自动再拆)+ checkpoint 续传 |
| 自报告不可信(误 checkout/覆盖 2 次) | Validation Engine 前置范围校验 + 操作备份 + 危险操作预检;自报告仅作"声明",结论以验证证据为准 |
| 无可观测性 | Event Logger + Dashboard 全覆盖:任何 Agent 的动作、进度、阻塞都是事件 |
| 指标未自动收集 | first_attempt_success / path_errors / human_intervention 由事件聚合自动生成,零人工上报 |

> 继续阅读 [runtime-design.md](./runtime-design.md):数据流、事件驱动设计、Dashboard 规格、数据模型、扩展点。
