# AI Enterprise Planning & Operation Model

> 状态: DESIGN ONLY (蓝图, 未实现或部分实现 — 见 ../audit/architecture-reality-audit.md)

> 日期: 2026-08-07 | 状态: 架构评审, 待确认 (Phase 17)
> 定位: AI Enterprise OS 的业务运行最高设计文档
> 引用: ai-enterprise-operating-model.md / ai-employee-runtime-model.md / ai-enterprise-nervous-system-model.md / factory-org-design.md
> 原则: Core 冻结; 不重复已有模型; 建议 != 自动执行

## 0. 三个基础模型 → 业务运行

```
Organization (16A):   定义谁工作
Employee Runtime (16B): 定义如何工作
Nervous System (16C): 定义如何沟通和记忆
→ Planning & Operation (17): AI 企业如何完成业务目标
```

---

## 1. Goal Model

### 企业目标如何进入系统

```
Human: "开发一个新的 SaaS 产品"
  → Goal (企业目标: 非技术语言, 高层意图)
  → Business Objective (业务目标: 市场/收入/指标, 可衡量)
  → Requirement (需求: 功能/约束/验收, 技术可执行)
  → Project (项目: 组织/资源/时间, 可运行)

转换过程 (Analysis + Planning 协作):
  Goal → (Analysis: 市场/风险/可行) → Objective + Requirement
  → (Planning: 拆解) → Project + Milestone + Task Graph
```

### GoalRecord

```python
class GoalRecord(Pydantic):
    id/company_id
    goal: str                 # 高层意图 (人类语言)
    objective: dict           # 业务目标 (指标/时间/预算)
    requirements: list[str]   # 需求清单
    project_id: str | None    # 落地项目
    status: new|analyzed|planned|active|completed|archived
```

---

## 2. Analysis Process

### Analysis Agent 如何工作

```
输入: Goal (或 Project 上下文)
输出:
  Market Analysis  (市场: 机会/竞争/定位)
  Risk             (风险: 技术/市场/资源, 分级 low/medium/high)
  Recommendation   (建议方案, 可解释 — 10A-2/10A-3)
  Evidence         (依据: 数据/事件/经验引用)

流程: 输入 → 分析 → 证据链 → 建议 (只推荐, 不决策)
```

### Analysis 与 Decision 的关系

```
Analysis Agent (分析岗) 输出 Analysis Report + Recommendation (建议)
Decision System (16C §4) 基于建议 + Evidence → DecisionRecord
Human/CEO 最终批准 (或授权 Manager)
Analysis 是决策的输入, 不是决策本身
```

---

## 3. Planning Model

### Planning Agent 如何产生计划

```
Goal → Plan (阶段计划) → Milestone (里程碑) → Task Graph (任务图)
```

### 多行业支持（通用计划抽象）

```
Software:  Research → Design → Develop → Test → Release
Research:  Hypothesis → Experiment → Analysis → Paper
Marketing: 调研 → 策略 → 投放 → 复盘
Business:  目标 → 拆解 → 执行 → 复盘

统一抽象: Stage (阶段) + Milestone + Task (工作单元)
行业差异 = 阶段模板 (声明式, 非硬编码)
```

### PlanRecord

```python
class PlanRecord(Pydantic):
    id/goal_id
    stages: list[Stage]       # 阶段 (模板声明)
    milestones: list[Milestone]
    task_graph: dict          # 节点+依赖 (Task Model §4)
    mode: str                 # waterfall|scrum|kanban|hybrid|mvp (调度策略, 非流程绑定)
    critical_path: list[str]
```

---

## 4. Task Model（不限于开发任务）

```python
class Task(Pydantic):
    id/project_id
    objective: str            # 目标 (要达成什么)
    input: list[str]          # 输入 (Artifact/上下文引用)
    output: str               # 输出 (交付物契约)
    requirement: str          # 验收要求
    owner: str | None         # 负责员工 (Employee)
    reviewer: str | None      # 审核员工 (Reviewer, 独立于 owner)
    dependencies: list[str]   # 前置任务
    status: pending|assigned|active|review|done|failed
```

```
核心: Task 有 Owner (执行) + Reviewer (审核) — 执行权 != 审核权
     Task 输出契约明确 → 可验收/可测试
     依赖图 → Critical Path / Parallel Group
```

---

## 5. Role Matching

```
Task → Requirement Profile (required_role/capabilities/experience/performance/availability)
  → Employee Recommendation (org Registry find_by_capability/role + 经验加权 16A/16B)
  → Agent Selection (候选 Employee 的 Agent Instance + Provider 四因素 10A-3)
  → Execution Recommendation (推荐 + 解释)

原则: Recommendation != Automatic Execution
     (自动分配 = 高价值功能, 但需 Approval 策略确认 — Phase 17 实现时定)
```

---

## 6. Workflow Model（通用, 不绑 Scrum）

```
企业流程 = 阶段模板 (声明式):
  Software / Research / Marketing / Operations / Business

通用 Workflow 抽象:
  Stage (阶段: 输入→活动→输出/验收门)
  Gate (门: 阶段间检查, 可设 Approval)
  Artifact (阶段产物)
  Event (阶段状态变化)

调度策略独立于流程: 同一 Workflow 可配 waterfall/scrum/kanban 执行模式
(不绑定单一管理方法 — ai-enterprise-operating-model.md §13)
```

---

## 7. Multi Agent Operation

```
多员工协作必须通过:
  Communication (16C: 组织意图, 全记录)
  Artifact (产物传递)
  Event (状态事实)
  Decision (决策+证据)

禁止: Agent 私下协商 / 不可审计黑盒协作
```

```
例: PM → Architect → Developer → QA 协作
  每步 Communication + Artifact + Event + Decision (16C §5 全链追踪)
```

---

## 8. Human Leadership

| 角色 | 可自动执行 | 必须人工批准 |
|:-----|:-----------|:------------|
| CEO | — | 产品方向/重大投资/组织变更 |
| Manager | 计划内调度/资源分配建议 | 计划变更/范围扩大 |
| Expert | 专业执行 (实现/测试) | 架构变更/外部依赖/发布 |
| Operator | 日常运维/监控 | 成本增加/生产操作 |

```
铁律: AI 越权 = 拒绝 + 审计; 危险 = 硬拒绝; 重大 = 必经人
(ai-company-operating-model.md 权限边界延续)
```

---

## 9. Planning 与 Nervous System

```
Planning 如何读神经系统:
  Communication Memory → 历史意图/约束/部门沟通 (16C)
  Decision Memory → 历史决策 + 依据 (不重复决策)
  Experience Memory → 同类目标的历史经验 (成功率/成本/坑)
  Knowledge Memory → 领域知识 (16A)

Planning 如何写神经系统:
  每步计划/里程碑/分配 = Communication (通知相关方)
  状态变化 = Event
  产物 = Artifact
  计划依据 = Decision Record

循环: 读记忆 → 计划 → 执行 → 新记忆 → 下一轮更准
```

---

## 10. Phase 18 Execution Dependency

```
Execution Runtime 需要接口:
  Agent Runtime    (16B: AgentInstance 执行身份, Employee→Agent 映射)
  Provider         (8A: LLM 抽象, 四因素推荐)
  Tool             (16B §9: 工具权限, Git/IDE/Browser)
  Sandbox          (执行边界: 工作副本, 不碰用户环境)

Execution 流程 (Phase 18):
  Task → Agent Runtime → Sandbox → Patch/Artifact → Validation → Review → Approval → Apply
  每步产生 Event → 16C 神经系统记忆
```

```
Execution Runtime 不感知 Organization (只执行):
  Organization 语义 (Role/权限) 在 Planning/门禁层解析
  Runtime 是命令执行器 (与 15 裁决 B 同哲学: Managed Services + Command)
```

---

## 11. 数据模型提案（新增, 不重复）

```python
class GoalRecord(Pydantic):      # §1
class PlanRecord(Pydantic):      # §3 (含 Stage/Milestone/TaskGraph)
class Task(Pydantic):            # §4 (Owner/Reviewer 分离)
class RequirementProfile(Pydantic):  # §5
```

## 12. 边界

```
✅ Core 冻结 (Goal/Plan 走 org.planning.* 事件, 不碰 Core Task 类型)
✅ 无重复模型 (Employee/Agent/Communication/Decision 复用 16A/16B/16C)
✅ 建议 != 自动执行 (Analysis/Planning/Role Matching 全部建议制)
✅ 多行业通用 (阶段模板, 不绑 Scrum)
```

## 13. 结论

```
17 定义 AI 企业如何完成业务目标: Goal→Analysis→Planning→Task→Matching→Workflow→Operation
为 Phase 18 (Execution Runtime) 提供业务语义层
等待确认后进入实现 (17-1: Goal/Plan/Task 模型 + org.planning.* 事件 + 模板)
```
