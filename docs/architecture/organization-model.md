# AI Software Factory — Organization Model

> 日期: 2026-08-07 | 状态: 设计 (Phase 16 实现)
> 定位: Organization Engine — 公司/部门/角色/AI 员工/权限

## 核心概念

```
Company (公司)
  └── Department (部门)
        └── Role (职位)
              └── Employee = Agent (专业 AI 员工)
                    └── Authority (权限边界)
```

## Agent 是什么？（不是 prompt，是专业 AI 员工）

```
Agent = Role + Capability + Experience + Responsibility

- Role:      职位定义 (Developer/Architect/Tester/Security/Deploy/Data...)
- Capability: 专业能力声明 (capability.yaml: 能做什么/不能做什么)
- Experience: 工作履历 (ExperienceRecord: 成功/失败/评分/衰减)
- Responsibility: 职责与权限 (Authority 矩阵)
```

## 数据模型

```python
class Company(Pydantic):
    id/name/type (software|ecommerce|finance|...)/parent (集团)
    departments: list[Department]

class Department(Pydantic):
    id/name/company_id
    roles: list[RoleRef]

class Role(Pydantic):
    id/name (developer|architect|tester|security|deploy|data)
    capabilities: list[str]      # 声明能力
    permissions: list[str]       # read_source/modify_workspace/run_test...
    forbidden: list[str]         # production_access/secret_access...

class Agent(Pydantic):           # 专业 AI 员工
    id/name
    role_id
    provider_preferences: dict   # 用哪个 Provider (10A-3 推荐)
    skills: list[str]
    experience_summary: dict     # 成功率/成本/评分 (10A-4)
    status: active|paused|archived

class Authority(Pydantic):
    agent_id/resource/action/effect (allow|deny)  # 默认 deny
```

## Organization Engine 职责

```
factory-org/ (Phase 16, 新 Extension)
├── models.py      Company/Department/Role/Agent/Authority
├── registry.py    Agent Registry (注册/查询/分配 — 复用 assignment 4B-3)
├── hiring.py      "雇佣" AI 员工 (从 Skill/Provider 生态装配 Agent)
├── authority.py   权限解析 (默认 deny, 矩阵校验)
└── events.py      org.* 事件 (org.company.created/agent.hired/agent.assigned...)
```

## 不同行业如何扩展？

```
行业 = 组织模板 (Phase 20):
  Software Company:   Department(Engineering/Product/QA) + Role(Dev/Arch/Test) + Policy
  E-commerce Company: Department(商品/运营/客服) + Role(分析/运营/客服)
  Finance Company:    Department(风控/交易/合规) + Role(分析/审计)
  Manufacturing:      Department(设计/生产/质检) + Role(工艺/排程/质检)

模板 = Organization + Workflow + Role + Agent + Policy (声明式组合, 零新引擎)
```

## 透明与可控

```
透明: 每 Agent 行为 = Event (org.*/task.*/execution.*) + Audit 只追加
可控: Authority 默认 deny; 高危操作 (production/secret) → Approval (9c)
      员工 (Agent) 无权限 = 硬拒绝; 越权尝试 = 审计记录
```

## 与现有能力复用

```
agents/ (已有)      → Agent 定义基础
skills/ (已有)      → 员工技能
providers/ (8A-10A) → 员工智能来源 (四因素推荐)
assignment (4B-3)   → 任务分配
approval (9c)       → 人事/操作审批
experience (10A-4)  → 员工履历
```
