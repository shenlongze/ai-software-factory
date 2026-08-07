# Phase 16 Pre-Architecture Review — AI Organization Foundation

> 日期: 2026-08-07 | 状态: 架构评审, 待确认
> 前置: Phase 15 COMPLETE (06a1b63, 4244 tests, Desktop dmg 分发就绪)
> 约束: Core/Runtime/Desktop 零修改 — 只设计

## 1. Vision Alignment

```
AI Software Factory 从"管理软件生产"升级为"管理 AI 组织"

Human Leadership → AI Executive → AI Department → AI Professional Agents
→ Workflow Execution → Experience Learning

Phase 16 证明: "一个人拥有一个 AI 公司" (MVP)
长期: AI Global Enterprise Operating System (21+)
```

## 2. Agent 定义重新确认

**Agent 不是 LLM。Agent 是组织中的专业员工（角色化）。**

```
Agent = Identity + Role + Responsibility + Capability + Knowledge
      + Experience + Authority + Performance
```

### 关键问答

**Q: Agent 是否可以多领域能力？**
```
可以, 但按岗位裁剪 (Role 决定能力集)。如 Developer Agent 可含 flutter+java 能力,
但 QA 能力不配给 Developer。能力多 ≠ 万能 Agent (岗位边界仍存在)。
```

**Q: Role 与 Capability 如何分离？**
```
Role = 职位 (组织定义: 职责/权限/考核维度)
Capability = 技能 (可组合的声明能力, capability.yaml)
Role 引用 Capability 集 (Role.capabilities), 分离设计:
  - Role 变更不动 Agent 技能
  - 新技能可加到任意 Role
  - 权限 (Authority) 绑定 Role, 不绑技能
```

**Q: 一个 Agent 是否可以承担多个 Role？**
```
可以 (一人多岗): Agent.roles = [Developer, Reviewer] — 但需防利益冲突:
  执行权 != 审核权 (Developer+Reviewer 同 Agent 被拒; Developer+QA 同 Agent 被拒)
  多 Role 时 Authority = 各 Role 权限并集, 冲突 Role 组合禁止 (组织规则)
```

**Q: 如何动态招聘/培养/替换 Agent？**
```
招聘: 从 Agent Registry 装配 (Role + Capability + Provider 偏好 + Skill)
培养: 经验积累 (ExperienceRecord) → Performance 提升 → 更多任务
替换: 同 Role 新 Agent 接任 (Experience 是组织的, 不随员工流失 — 组织级经验库)
解雇: Authority 撤销 + 任务 reassign
```

## 3. Organization Model

```
Company → Department → Position/Role → Employee(Agent) → Capability
```

### 关键问答

**Q: 一人公司如何建模？**
```
Company(AI Software Company) = 1 部门 + 5 岗位 + Human CEO
Human 兼任 Founder/CEO/Operator (Human Leadership 层)
```

**Q: 大企业多部门如何扩展？**
```
Company → [Engineering/Product/QA 部门] → 每部门 Role 集 → 多 Agent
部门 = 组织子树 (嵌套), Role 可跨部门复用 (全局 Role 注册表)
```

**Q: 企业之间如何隔离？**
```
Company 为隔离单元 (同 Multi Organization §7):
  Company.id 前缀数据空间 + 权限边界 + 知识库 + 经验库独立
  <data_root>/organizations/<company_id>/
```

**Q: 企业知识库如何绑定？**
```
Company.knowledge 绑定 (Knowledge System §4):
  <data_root>/organizations/<company_id>/knowledge/
  员工 (Agent) 只读其所属公司知识, 跨公司禁止
```

## 4. Knowledge System（企业知识资产）

```
Company Knowledge:
  企业文化/产品/客户/市场/技术栈/文档/历史项目
```

### 模型

```python
class KnowledgeItem(Pydantic):
    id/company_id
    domain: str          # culture|product|customer|market|stack|docs|history
    content: str
    source: str          # 来源 (文档/对话/Artifact/人工)
    version: int
    updated_at/created_at
    tags: list[str]
```

### 如何学习/更新/检索/授权

```
学习: 从 Artifact/文档/历史项目提取 (Analysis Agent, 建议 → 人工确认入库)
更新: 版本化 + 人工确认 (知识变更 = 决策, 9c Approval)
检索: 语义检索 (未来 Analysis Agent); 本阶段: 标签/全文/领域过滤 (纯函数)
授权: 公司级隔离; 员工只读所属公司知识; 敏感域 (财务/客户) 按 Role 权限
不绑定 LLM: 知识 = 结构化存储 (JSON), 检索 = 确定性规则; LLM 只作为未来的分析/提取建议者
```

## 5. AI Employee Learning

```
Knowledge: 知道什么 (公司知识/文档)
Experience: 做过什么 (历史任务/结果 — ExperienceRecord 五域)
Performance: 做得怎么样 (成功率/成本/评分 — 10A-4)
```

### 闭环

```
Task → Execution → Result → Evaluation → Experience → Better Employee
  ↓
Evaluation: 谁评? 双重: QA Agent 验证 (客观) + Human/Review (主观) + 自动指标 (测试/成本)
  ↓
Experience 回流: 员工 experience_summary 更新 → 未来分配加权 (推荐 10A-3)
  ↓
Better Employee: 高绩效 → 更多/更难任务; 低绩效 → 培训 (知识补) 或降权
```

## 6. Human Leadership Model

```
Human = Founder/CEO/Manager/Operator (不是普通用户)
```

### 决策边界

| 层级 | AI 可以决定 | AI 可以建议 | 必须 Human Approval |
|:-----|:-----------|:-----------|:-------------------|
| 战略 (CEO) | — | 市场/方向分析 | 产品方向/重大投资/裁员 |
| 组织 (PM) | 计划内任务调度 | 计划/风险/重规划 | 计划变更/范围扩大 |
| 执行 (Dev) | 实现细节/技术选型建议 | 方案/架构 | 架构变更/外部依赖 |
| 质量 (QA) | 测试结论 | 修复建议 | 发布/合并 |
| 资源 (Operator) | 日常运维 | 优化建议 | 成本增加/生产操作 |

```
原则: AI 越权 = 拒绝 + 审计; 危险 = 硬拒绝; 重大 = 必经人
```

## 7. Planning 与 Project Management

```
Analysis Agent ≠ Project Manager Agent (agent-role-model.md §3)
```

```
Goal → Planning (PM) → Task Graph → Dependency → Critical Path
→ Parallel Execution → Monitoring → Dynamic Replanning
```

### 方法论支持

```
Scrum:     Sprint 拆解/Backlog/燃尽 — PM 生成, 迭代推进
Kanban:    列状态 (To Do/In Progress/Review/Done) + WIP 限制
Waterfall: 阶段串行 + 里程碑 (Go/No-Go 门)
Hybrid:    阶段框架 + 迭代执行
MVP:       范围裁剪优先 → 最小可行 → 快迭代
```
（Phase 17 Planning 实现; Phase 16 只定义 PM Role 与输出契约）

## 8. Multi Organization（为未来准备）

```
Enterprise: Company → Departments (嵌套)
Personal:   One-person Company → AI Departments
Multi-tenant: Company A / Company B (并行)
```

### 四重隔离

```
数据隔离: <data_root>/organizations/<company_id>/ (独立数据空间)
权限隔离: Authority 绑定 Company + Role (跨公司拒绝)
知识隔离: Company.knowledge 不可跨公司检索
经验隔离: ExperienceRecord.company_id 前缀 (经验是公司的, 不是跨公司的)
```

## 9. Execution Boundary（Phase 17/18 前置原则）

```
Agent 不直接修改环境:
Agent → Sandbox (工作副本) → Artifact (diff/patch) → Validation (测试/范围)
→ Approval (Human/Policy) → Apply (merge)
执行权 != 审核权; 可暂停/可恢复/可审计
```

## 10. Phase 16 MVP 范围裁剪

```
不做完整 ERP。只证明: "一个人拥有一个 AI 公司"

Company:     AI Software Company (组织模板)
Roles:       CEO (Human) + PM Agent + Developer Agent + QA Agent
Workflow:    Goal → Organization → Assign → Execute → Review → Experience

MVP 交付:
  org/ 模块 (Company/Department/Role/Agent/Authority 模型 + store + 事件)
  Agent Registry 装配 (4 角色)
  组织模板: software_company (声明式)
  Goal → 分配 → 任务 → 经验回流 (复用 4B/9d/10A)
  测试 ≥120
```

## 11. Architecture Model

```
Human Console (现有, 扩展 Org 视图)
  ↓
Organization Layer (新增 Extension: factory-org/)
  ├── models: Company/Department/Role/Agent/Authority/Knowledge
  ├── registry: Agent Registry (招聘/分配/替换)
  ├── knowledge: 企业知识库 (公司隔离)
  └── events: org.* 事件
  ↓
Intelligence (复用 10A: 推荐/决策/经验)
  ↓
Core (冻结: Task/Workflow/Execution/Event 原语)
```

## 12. Core Impact Analysis

```
Core 零修改:
  - org/ 是纯 Extension (独立数据空间/测试/Removal Isolation)
  - 复用: tasks (任务), assignment (分配), workflows (流程), events (审计),
          intelligence (推荐/经验), approval (9c 人事审批), product (生命周期)
  - Event 新增 org.* namespace (org.company.created/agent.hired/agent.assigned/...)
  - Runtime/Desktop 零修改 (Org 经 Console API 只读展示, 业务在 org/ 层)
```

## 13. Data Model Proposal

```python
class Company(Pydantic): id/name/type/template_id/parent/status
class Department(Pydantic): id/company_id/name/roles: list[RoleRef]
class Role(Pydantic): id/company_id/name/capabilities/authority/conflicts (防执行+审核同人)
class Agent(Pydantic): id/company_id/name/roles/provider_prefs/skills/experience_summary/status
class Authority(Pydantic): agent_id/resource/action/effect (allow|deny, 默认 deny)
class KnowledgeItem(Pydantic): id/company_id/domain/content/source/version/tags
```

## 14. Security Boundary

```
- 默认 deny (未声明权限 = 拒绝)
- 公司隔离 (数据/权限/知识/经验四重)
- 高危操作 (生产/机密/成本) → Approval (9c)
- 执行权 != 审核权 (Role 冲突组合禁止)
- 审计: 全部 org.* 事件 + Audit 只追加
```

## 15. MVP Scope（详细）

```
Phase 16 MVP (16A):
  factory-org/ Extension:
    models (Company/Department/Role/Agent/Authority) + store (独立空间) + events
    Agent Registry (注册/查询/分配 — 复用 4B-3)
    组织模板: software_company (CEO/PM/Developer/QA)
    Knowledge 基础 (公司知识条目 + 公司隔离)
  CLI: org company create / org agent hire / org assign / org status
  Console: Org 视图 (只读)
  Goal→Assign→Execute→Review→Experience 演示 (markpad 组织)
  测试 ≥120
```

## 16. Risks

```
1. 范围膨胀 (ERP 化) → MVP 铁律: 只 4 角色 1 模板
2. Agent 多角色冲突 → Role 冲突规则先行
3. 知识库空洞 → MVP 知识最小集 (产品/技术栈/文档)
4. 组织隔离复杂度 → 公司前缀数据空间先行 (先单公司, 多公司架构预留)
5. 过度抽象 → 复用现有 (assignment/experience/approval), 不造新轮子
```

## 17. 结论

```
Phase 16 将 Factory 从"软件生产管理"升级为"AI 组织管理"
MVP 证明: 一个人 + AI 公司 (CEO=人, PM/Dev/QA=AI 员工) 跑通完整闭环
Core/Runtime/Desktop 零修改; 全部 org/ Extension 化
等待确认后进入 Phase 16A 实现
```
