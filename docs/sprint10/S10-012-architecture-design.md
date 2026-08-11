# S10-012 Factory Capability Pool — Architecture Design

> 状态: 待确认 | 日期: 2026-08-11 | 基线: 0557790 (pytest 7160)
> 依据: AF-PRD-v1.md 3 (Factory Capability Pool) + project-lifecycle.md + S10-011 现状
> 范围: 公共能力池 (禁 UI/前端/真实 LLM 调用)

## 一、核心原则 (确认)

```
Project 不拥有 Agent/Skill/MCP/Workflow — 只进行 binding (引用)
Factory Capability Pool = 公共注册表 (Registry), 独立于项目空间

Workspace
├── Projects (workspace/projects/{slug}/)
└── Factory Capability Pool (workspace/capabilities/ 或独立目录)
    ├── industries/ ├── skills/ ├── agents/ ├── mcps/ ├── workflows/ └── llm-configs/
```

## 二、核心模型 (确认)

```
Skill: id/name/description/category/input_schema/output_schema/version/enabled
Agent: id/name/role/description/skill_bindings/workflow_bindings/llm_config
MCP:   id/name/type/endpoint/auth_config/capabilities
WorkflowTemplate: id/name/industry/steps/required_agents/required_skills
Industry: id/name/description/workflow_templates
LLMConfig: id/provider/model/endpoint/parameters
```

## 三、Registry 架构

```
CapabilityRegistry (org/capabilities.py):
  目录信源: workspace/capabilities/{kind}/{id}.json (kind: skills/agents/mcps/workflows/industries/llm-configs)
  CRUD: register/get/list/update/delete + enabled 过滤 + 版本 (skill.version)
  默认种子: 预置标准能力 (software-development workflow/PM/Architect/Developer/QA 角色 +
    flutter-development/backend-development 等 skill — 只建实体不实现逻辑)
  懒迁移: 无目录 → 首次访问创建 (与 ProjectSpace 同模式)
```

## 四、Binding 集成 (v1.1 — 用户补充 2026-08-11)

```
Project.capability_bindings: [{type: agent|skill|mcp|workflow, id, version?}] (引用, 非复制)
  → version 必须支持 (能力持续升级, 历史 Project/Workflow/Runtime 保持可复现)
  → 校验: binding 引用的能力必须存在于 Registry (缺失 → 可标注警告, 不崩溃)
  → S10-009 Project 已预留 bindings 字段; 本 Sprint 对齐语义为 capability_bindings
```

## 四b. Capability 生命周期 (v1.1 — 用户补充)

```
CapabilityState: DRAFT → ACTIVE → DEPRECATED → ARCHIVED (受控单向, archived 终态)
  enabled (bool) 保留为运行开关 (ACTIVE 且 enabled=true 才可被 binding 选用)
  所有 Capability 实体 (Skill/Agent/MCP/WorkflowTemplate/Industry/LLMConfig) 统一生命周期
  历史 binding (含 version) 不受实体 DEPRECATED/ARCHIVED 影响 (可复现)
```

## 五、Execution Engine 集成 (Task 007)

```
Dispatcher 改造:
  binding → CapabilityRegistry 解析 → Agent/Skill/MCP/Workflow 实体
  → WorkflowInstance 记录 agent/skill/mcp (来自 Registry 实体而非裸字符串)
  兼容: 旧 binding (裸字符串) 仍可执行 (Registry 无对应 → 保留字符串标注)
```

## 六、Task 拆分 (每 Task: 设计→实现→测试→commit→Quality)

```
Task 001 Capability Domain Model   (org/capabilities.py 六实体 + 状态/校验)
Task 002 Skill Registry            (skills/ CRUD + version + enabled)
Task 003 Agent Registry            (agents/ CRUD + skill/workflow bindings + llm_config)
Task 004 MCP Registry              (mcps/ CRUD + auth_config 占位)
Task 005 Workflow Template         (workflows/ CRUD + steps/required_agents/skills)
Task 006 Industry + LLM Config     (industries/ + llm-configs/ CRUD + 种子)
Task 007 Execution Engine Binding  (Dispatcher 集成 Registry + project capability_bindings + 兼容)
```

## 七、验收 (本 Sprint)

```
场景1: 注册 Skill/Agent/MCP/Workflow/Industry/LLM → 列表/读取 (目录信源)
场景2: 项目 capability_bindings 引用 → 校验 (缺失警告不崩溃)
场景3: Dispatcher: binding → Registry 解析 → instance 记录实体
场景4: 种子能力存在 (software-development workflow + 标准角色)
场景5: 旧项目 (无 bindings) 零破坏 (pytest 全量回归)
```

## 八、禁止

```
❌ UI / 前端 / 真实 LLM 调用 / Agent 逻辑实现 / MCP 连接
✅ 只建 Factory 员工池 (实体 + 注册表 + 引用集成)
```
