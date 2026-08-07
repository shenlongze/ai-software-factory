# Phase 16 Organization Model Review

> 日期: 2026-08-07 | 状态: 架构评审汇总, 待确认
> 前置: Phase 15 COMPLETE + Phase 16 Pre-Review (956bf10)

## 1. 总览

```
目标: AI Software Factory 从 Runtime 产品 → AI Organization Operating System
范围: 只设计, 不编码; Core/Runtime/Desktop 零修改
产出: agent-employee-model.md / knowledge-learning-model.md / ai-company-operating-model.md / 本文
```

## 2. 统一组织模型

```
Company (parent 支持集团嵌套)
  ├── Department (可选, Solo 扁平 / Enterprise 嵌套)
  │     └── Position/Role (全局 Role 注册表)
  │           └── Employee (Agent)
  │                 └── Capability + Knowledge + Authority + Experience + Performance

Solo 与 Enterprise 同一模型 (层级深度可配置), 不允许两个系统
```

## 3. 权限模型

```
Default Deny | Authority 绑定 Role (非 Agent) | 高危必经 Approval
执行权 != 审核权 | Role 冲突组合禁 (Developer+Reviewer/QA)
Human CEO 唯一最终权
```

## 4. 关键设计决策汇总

```
1. Capability ≠ Role: 多技能员工, 职位定权限
2. Agent Lifecycle: 招聘 (HR Agent 建议) → 培训/外部装配 → 入职 (Approval 高权限) → 绩效 → 替换
3. 知识三层隔离: 通用能力 (Global) / 企业知识 (Company) / 项目知识 (Project)
4. 三类学习: Knowledge (人工确认入库) / Experience (自动+Review) / Performance (推荐加权)
5. Analysis ≠ PM: 顾问 vs 组织者; 方法不绑定 (Scrum/Kanban/Waterfall/Hybrid/MVP)
6. 公司隔离: 数据/权限/知识/经验四重
7. MVP: AI Software Company (CEO=Human + PM/Dev/QA), 测试 ≥120
8. 长期: AI Organization Operating System (ERP/CRM/HRM 融合方向, 不现在实现)
```

## 5. 8 问回答索引

```
1. AI 员工是什么?      → agent-employee-model.md §1-2 (专业员工, 非 LLM+Prompt)
2. 公司如何创建?      → ai-company-operating-model.md §1 (模板实例化)
3. 一人公司如何运行?  → ai-company-operating-model.md §2 (Solo Mode, 同一模型)
4. 企业知识如何隔离?  → knowledge-learning-model.md §1 (三层隔离)
5. AI 如何学习?       → knowledge-learning-model.md §3 (三类学习, 可审计)
6. AI 如何招聘/培养?  → agent-employee-model.md §4 (HR Agent + Approval)
7. 项目如何管理?      → ai-company-operating-model.md §4 (Planning ≠ PM, 多方法)
8. 如何扩展到集团?    → ai-company-operating-model.md §5 (递归嵌套 + 行业模板)
```

## 6. 架构影响

```
factory-org/ (Phase 16A Extension):
  models: Company/Department/Role/Agent/Authority/KnowledgeItem
  registry: Agent Registry (招聘/分配/替换)
  knowledge: 企业知识库 (三层隔离)
  events: org.* (org.company.created/agent.hired/agent.trained/authority.granted/...)
  复用: assignment(4B)/experience(10A)/approval(9c)/product(9d)/intelligence(10A)
Core/Runtime/Desktop 零修改
```

## 7. 风险

```
范围膨胀 (ERP 化) → MVP 铁律 (Software Company 单一模板)
权限误配 → Role 绑定 + 冲突规则 + 审计
知识空洞 → MVP 最小知识集
多公司复杂度 → 公司前缀数据空间先行
```

## 8. 结论

```
Phase 16 设计确认: Factory 管理"AI 组织"而非"AI 任务"
MVP 证明: 一个人 + AI 公司跑通 Goal→Org→Assign→Execute→Review→Experience
等待确认后进入 Phase 16A 实现
```
