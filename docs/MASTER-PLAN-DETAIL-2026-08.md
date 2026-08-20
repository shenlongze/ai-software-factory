# AI Factory 节点级详设 v2 — 以链路为主线（2026-08-20）

> 配套: docs/MASTER-PLAN-2026-08.md（主线）· docs/sprint10/S10-087-agent-rebuild-plan.md
> 组织方式: 先给**链路**（端到端流 + 时序 + 数据流转 + 治理插入点），再给**节点详设**（输入/输出/接口/文件/验收/风险）。
> 原则: 滚动式规划 — 链路 1（IT 工厂主链路）最细，其余先到"可开工"粒度。

---

# 第一部分：链路（Chains）

## 链路 0 — 全局总览

```
                    ┌────────────────────────────────────────────┐
                    │            AI Company OS 底座              │
                    │  员工层(Agent) · 能力层(Skill/MCP/Known/)  │
                    │  治理层(审批/预算/审计) · 学习层(画像/决策)  │
                    └────────────────────────────────────────────┘
   ┌──────────────────┼──────────────────┬───────────────────┐
   │ 链路1            │ 链路2            │ 链路3             │
   │ 想法→交付        │ 存量仓库干活     │ 自我提升循环       │
   │ (IT 工厂主链路)   │ (repo mode)     │ (跨任务, C 阶段)   │
   └──────────────────┴──────────────────┴───────────────────┘
   ┌──────────────────────────────────────────────────────────┐
   │ 链路4: 行业复制 (FactorySpec → 第二工厂)                    │
   └──────────────────────────────────────────────────────────┘
```

## 链路 1 — 想法 → 交付（IT 工厂主链路，A+B+D 串联）

### 1.1 端到端流

```
用户: "我要开发一个客户管理系统"
  │
  ▼
[L1-1] 入口会话 (session) ── 意图解析/确认 → ProductIntent
  ▼
[L1-2] Discovery 多轮 ── 需求收集 → discovery.md (artifact)
  ▼
[L1-3] 专家团队装配 (A3) ── 按行业 spec 装配 7 个 AgentEntity
  ▼
[L1-4] 多 Agent 交接 (A4) ── PM→Market→Competitive→UX→Architect→QA→SeniorPM
  │       每步: 消费上一产出 → 产出 artifact (parent_artifact 互引)
  ▼
[L1-5] 审批门 (B3) ── PRD 完成 → ReviewGate 挂起 → 用户批准
  ▼
[L1-6] 工程计划 (B5) ── Architect 深度 → engineering.json + tasks.json + execution_plan.json
  ▼
[L1-7] 审批门 (B3) ── 计划确认 → 用户批准
  ▼
[L1-8] 执行 (复用 ExecutionLoop) ── 任务循环: 规划→执行→验证→修复
  │       Agent 可调工具 (T1 MCP / T2 Skill / 内置 file/bash/git)
  ▼
[L1-9] 交付 (S10-083 底座) ── patch→apply→pytest → 代码落盘 + 测试报告
  ▼
[L1-10] 观测 (exec history / project status) ── 时间/角色/工具/模型/成本
  │
  └──▶ 执行中变更 → [L1-11] 需求变更回流 (B2) → PRD v2 + replan → 回 L1-8
```

### 1.2 时序与数据流转

| 步骤 | 触发 | 输入 | 输出 | 调用方→被调方 | 治理点 |
|---|---|---|---|---|---|
| L1-1 | 用户输入 | 文本 | ProductIntent | session→intent parser | — |
| L1-2 | ProductIntent | 需求字段 | discovery.md(v1) | conversation→artifact_registry | — |
| L1-3 | 行业 spec | spec | 7×AgentEntity | expert_factory→registry | skill 校验 |
| L1-4 | 7 专家 | 上一产出 | 7×artifact(互引) | handoff_bus→各 Agent→artifact_registry | 冲突→ReviewGate |
| L1-5 | PRD 资产 | PRD | 批准/驳回 | ReviewGate | **审批** |
| L1-6 | 批准 | PRD | engineering/tasks/execution | architect Agent→pipeline 校验 | — |
| L1-7 | 计划 | 计划资产 | 批准/驳回 | ReviewGate | **审批** |
| L1-8 | 批准 | 计划 | 每任务结果 | ExecutionLoop→DeveloperAgent | 预算/TOOL_CALL 审计 |
| L1-9 | 任务完 | patch | 代码+pytest 报告 | patch_filter→apply→pytest | — |
| L1-10 | 交付 | 事件 | timeline/status | observability | — |
| L1-11 | 用户/缺口 | 变更提议 | PRD v2+新任务 | change_control→ReviewGate→replan | **审批+预算** |

### 1.3 串并行与回退

```
L1-1→L1-2 串行 (强制)
L1-3→L1-4 串行装配, L1-4 内部: Market/Competitive 可并行 → 共识后进 UX
L1-5 失败(驳回) → 回 L1-4 修改 (版本+1)
L1-6→L1-7 串行; 驳回 → 回 L1-6
L1-8 任务循环: 依赖图拓扑 → 无依赖可并行; 单任务失败 → 修复/重规划 (replan 上限 5)
L1-11 任何时候可插入 (用户或缺口触发) → 变更审批 → 回 L1-8
```

## 链路 2 — 存量仓库干活（repo mode，B4）

```
用户: factory repo ~/my-app "加一个导出功能"
  ▼
[R2-1] 理解 (复用 core/understanding) → 仓库报告(技术栈/结构/缺口)
  ▼
[R2-2] 计划 (ExecutionLoop Planner) → 修改方案(文件级 diff)
  ▼
[R2-3] 审批 (B3) → 用户批准修改方案
  ▼
[R2-4] 执行: 读文件→修改→写回 (Agent + 工具层)
  ▼
[R2-5] 验证: git 快照 + pytest/构建 → 失败→修复循环 (上限)
  ▼
[R2-6] 交付: 变更摘要 + 测试报告 (可提交 PR/commit)
```

## 链路 3 — 自我提升循环（C，跨任务）

```
每次任务完成 (L1-9 / R2-5)
  ▼
[C1] 经验采集: 结构化 (任务/结果/工具/耗时/成本/失败原因)
  ▼
[C2] 画像聚合: AgentProfile 累计更新
  ▼
[C3] 决策引用: 下次规划/选择时检索经验 → 注入上下文 (带 source)
  ▼
[C4] 评价回写: evaluator 分数 → 画像 → 影响选择
  ▼
[C5] 护栏: 学习开关 / 可信度(样本<5 不计权) / 预算上限 / 回滚
  └──▶ 回到 L1-3/L1-8 (下一次任务用"变强"的专家)
```

## 链路 4 — 行业复制（D2/E）

```
[D2] 从 IT 工厂提取 FactorySpec {employees, capabilities, workflows, governance, assets}
  ▼
[D3] 自举: spec 重新生成 IT 工厂 → 与原实现行为等价 (回归)
  ▼
[E1] 第二行业选型 (建议: 数据分析/办公自动化)
  ▼
[E2] factory factory new <行业> → 换 Skill+Knowledge+Workflow 实例化
  ▼
[E3] 最小闭环: 该行业一个真实任务端到端跑通 → 暴露底座缺口 → 回填
```

---

# 第二部分：节点详设（输入/输出/接口/文件/验收/风险）

> 每个节点: 目的 / 输入 / 输出 / 关键接口 / 涉及文件 / 依赖 / 验收 / 风险

## 阶段 A — 员工内核

### A1 AgentEntity 数据模型

- 目的: 一个"专家"的统一身份模型
- 输入: 装配参数 (role, provider, skills, ...)
- 输出: AgentEntity 实例 (可序列化)
- 关键接口: `AgentEntity.to_dict()/from_dict()`; 字段: `{id, role, industry, provider{id,model}, system_prompt, skills[], knowledge_ref, workflow_ref, memory_ref, tools[], evaluation_ref, profile{success_rate,quality,cost,speed, samples}}`
- 涉及文件: 新建 `factory-console/session/agent_entity.py`; 复用 exec.DeveloperAgent 字段口径
- 依赖: 无
- 验收: 可落盘/加载; 字段齐; 与 DeveloperAgent 职责边界有注释
- 风险: 与 exec 重复建模 → 定界: entity=组织身份, DeveloperAgent=执行引擎

### A2 AgentRegistry（工厂层）

- 目的: 专家注册/装配/查询的统一入口
- 输入: 行业 + role
- 输出: AgentEntity 列表/单例
- 关键接口: `register(agent)/get(role, industry)/list(industry)/remove(id)`; 行业命名空间 (it.*, ops.*)
- 涉及文件: 新建 `session/agent_registry.py`; 复用 core.agents.registry
- 依赖: A1
- 验收: 注册/取用/列表; 同 role 多 provider 并存; 持久化 (agents.json)
- 风险: 与 core registry 重复 → 薄包装 + 工厂语义

### A3 专家装配器 ExpertFactory

- 目的: "造专家" — Skill+Knowledge+Workflow → AgentEntity
- 输入: `assemble(role, skills[], knowledge_ref, workflow_ref, provider)`; 行业 spec
- 输出: 校验通过的 AgentEntity
- 关键接口: `ExpertFactory.assemble(...)/validate(agent)`; 校验: skill 存在、workflow 可执行、knowledge 可挂载
- 涉及文件: 新建 `session/expert_factory.py`; 复用 skills registry, workflow_engine
- 依赖: A1, A2
- 验收: 装配出 7 个软件行业专家; 缺 skill → 明确报错
- 风险: skill 目录与 exec capability 语义不一致 → 先建 glossary

### A4 HandoffBus

- 目的: 多 Agent 交接/共识/分工
- 输入: 角色依赖拓扑 + 上一产出 artifact
- 输出: 下一 Agent 输入 (handoff 消息 + 引用) + 新 artifact (parent_artifact)
- 关键接口: `route(role_graph)/send(producer→consumer)/decide(conflict)`; 消息结构 `{from,to,artifacts[],decisions[],constraints[]}`
- 涉及文件: 新建 `session/handoff_bus.py`; 复用 handoff_messages.json 结构, ConflictResolver, ReviewGate
- 依赖: A3
- 验收: PM→…→SeniorPM 依次消费; 资产含 parent_artifact; 冲突挂起等审批
- 风险: 循环依赖/死锁 → 拓扑校验 + 超时

### A5 软件行业 7 角色实例化

- 目的: 用 A3/A4 替换 ProductPipeline 的"换提示词"
- 输入: 行业 spec (it)
- 输出: 7×AgentEntity + 可跑的交接链
- 关键接口: `build_it_factory()`; 产出仍走 artifact_registry
- 涉及文件: 新建 `session/factories/it.py`; 改 `actions.product_pipeline` 接 A4
- 依赖: A4
- 验收: `让PM分析` 走真 Agent 链; 资产 created_by=agent_id
- 风险: 7 次 LLM 成本 → 预算护栏先行

### A6 多 LLM 配合

- 目的: 规划/执行/评审分工路由
- 输入: provider 配置 + 阶段
- 输出: 路由后的 provider/model
- 关键接口: `route_for(stage)` (planner/executor/reviewer)
- 涉及文件: 改 LLMRouter 或新建 `session/model_routing.py`
- 依赖: A5
- 验收: 同专家可按阶段路由不同模型 (可配置+断言)
- 风险: 模型行为不一致 → 默认同模型

## 阶段 B — IT 工厂深度

### B1 PRD 深度化

- 输入: ProductIntent + discovery.md + 专家链产出
- 输出: PRD.md (背景/用户故事/功能需求 P0..Pn+验收标准/非功能/数据风险)
- 接口: SeniorPM Agent 生成 + schema 校验 (LLM 失败→模板兜底)
- 文件: 新建 `session/prd_deep.py`; 复用 ProductDocument 兜底
- 验收: PRD 含用户故事+功能编号+验收标准 (结构断言)
- 风险: 幻觉 → 字段锚定 (不得编造 ProductIntent 外事实)

### B2 需求变更回流 ChangeControl

- 输入: ChangeProposal{source,what,why,affected_artifacts,affected_tasks}
- 输出: 资产 v+1 + 新/改任务 + plan_version+1 + 血缘
- 接口: `propose()→impact()→approve()→apply()`
- 文件: 新建 `session/change_control.py`; 复用 ReplanningEngine/ReviewGate/artifact_registry
- 验收: 执行中"加个导出" → PRD v2 + 新任务 + 血缘完整
- 风险: 变更风暴 → 合并 + 上限 + 预算

### B3 审批门

- 输入: 待审节点 (Discovery/PRD/Architecture)
- 输出: 批准/驳回 → 继续/回退
- 接口: ReviewGate.request/approve/reject + 会话接线
- 文件: 改 session.py 交互流
- 验收: PRD 未批准不进入工程; Architecture 未批准不进入执行
- 风险: 过度审批 → mandatory 仅 PRD

### B4 存量仓库模式 repo mode

- 输入: `factory repo <path> "<目标>"`
- 输出: 修改 + 测试报告 + 变更摘要
- 接口: understand→plan→approve→edit→test→fix 循环
- 文件: 新建 `factory-console/cli_repo.py` + `session/repo_mode.py`; 复用 core/understanding, ExecutionLoop
- 验收: 对现有仓库真实修改 + 测试绿
- 风险: 破坏性修改 → git 快照 + 审批

### B5 工程计划深度化

- 输入: PRD + 架构资产
- 输出: engineering.json (架构理由/模块/依赖)
- 接口: Architect Agent 生成 + EngineeringPlan 确定性校验
- 文件: 改 `session/pipeline.py` 或新建 `session/engineering_deep.py`
- 验收: engineering.json 含架构理由+依赖 (非纯模板)
- 风险: LLM 计划不可执行 → 任务图仍走确定性校验

## 阶段 C — 自我提升

### C1 经验采集
- 输入: execution/evaluation 事件; 输出: 结构化经验
- 接口: `extract(execution_result, evaluation) → Experience`
- 文件: 新建 `session/experience_extractor.py`; 复用 experience store
- 验收: 每次执行自动落一条可检索经验

### C2 Agent 画像
- 输入: 经验流; 输出: AgentProfile (累计)
- 接口: `aggregate(agent_id) → profile`
- 文件: 新建 `session/agent_profile.py`
- 验收: 画像字段随执行更新

### C3 决策引用
- 输入: 规划/选择上下文; 输出: 注入的检索经验 (带 source)
- 接口: `retrieve_for(task) → refs[]`
- 文件: 新建 `session/decision_memory.py`; 复用 retrieval (S10-067)
- 验收: 第二次同类任务引用第一次经验 (replay 断言)

### C4 评价回写
- 输入: evaluator 分数; 输出: 画像更新 + 选择排序
- 接口: `feedback(score, agent_id)`
- 文件: 改选择器; 复用 evaluator
- 验收: 高画像 agent 被优先选择

### C5 可控护栏
- 输入: 学习配置; 输出: 约束
- 接口: 开关/可信度(样本<5 不计权)/预算上限/回滚
- 文件: 新建 `session/learning_guard.py`
- 验收: 低样本不主导; 超预算阻断

## 阶段 D — E2E + 工厂抽象

### D1 真实 E2E
- 输入: 锚点场景; 输出: 全链路演示
- 验收: 一句话→专家交接→深度 PRD→工程→代码落盘→pytest 绿→历史可查
- 风险: 真实 LLM 质量 → 失败即记录修复

### D2 FactorySpec
- 输入: IT 工厂实例; 输出: spec 模型
- 接口: `FactorySpec{employees, capabilities, workflows, governance, assets}` + `factory factory new <industry>`
- 文件: 新建 `session/factory_spec.py`
- 验收: 从 IT 提取 spec 且可重新实例化

### D3 自举验证
- 接口: spec 驱动实例 vs 手工实例测试等价
- 验收: 行为一致 (回归)

## 阶段 E — 第二行业
### E1 选型 → E2 实例化 → E3 最小闭环
- 建议先数据分析/办公自动化; 验收: 同一底座第二行业最小任务端到端

## 增强层
### T1 MCP 真连接: stdio/http 真客户端, 替换 Mock; 验收: 连本机真实 MCP 调用成功
### T2 Skill 调用链: Agent 循环内发现→调用→回写
### T3 本机 AI CLI 发现/委托: factory tools list; **仅增强, 不依赖**
### T4 知识库: knowledge store + 检索 + 挂载专家
### T5 多 provider 基础设施: 健康/降级

---

# 第三部分：治理插入点与数据资产总表

## 治理插入点
| 环节 | 治理 |
|---|---|
| 装配 (A3) | skill/workflow 校验 |
| 交接 (A4) | 冲突→ReviewGate |
| PRD (B1) | 审批门 (mandatory) |
| 执行 (L1-8) | 预算 + TOOL_CALL 审计 |
| 变更 (B2) | 审批 + 预算 |
| 学习 (C) | 开关 + 可信度 + 上限 |

## 数据资产流转
| 资产 | 产生节点 | 消费节点 | 存储 |
|---|---|---|---|
| discovery.md | L1-2 | L1-4 (PM) | artifacts/<slug>/discovery/ |
| product/market/.../prd.md | L1-4 | L1-5/L1-6 | artifacts/<slug>/<type>/v<n>/ |
| engineering.json/tasks.json/execution_plan.json | L1-6 | L1-8 | projects/<slug>/ |
| execution_state.json | L1-8 | L1-9/L1-10 | projects/<slug>/ |
| 经验/画像 | C1/C2 | C3/C4 | experience/ + agents/ |
| FactorySpec | D2 | E2 | factory_specs/ |

---

**开工建议**: 从 A1→A2→A3→A4→A5 按链路 1 的 L1-1~L1-5 打通第一段（想法→专家交接→PRD），再续 B/C/D。
