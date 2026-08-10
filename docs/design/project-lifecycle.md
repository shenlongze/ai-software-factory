# Project Lifecycle — Domain Model & Architecture (S10-009 修订版)

> 状态: 架构待确认 | 范围: Project Operating Model (不开发 UI, 不开始编码)
> 修订: 2026-08-11 | 依据: 架构深化讨论 (Capability Pool / Project Space 三类目录 /
> Management Domain / Execution Engine / binding 设计)

## 一、顶层结构 (确认版)

```
AI Factory
│
├── Workspace                 # 用户工作空间 (项目容器)
│   ├── Project A             # 软件项目 (生命周期主体)
│   ├── Project B
│   └── Workspace Config
│
└── Factory Capability Pool   # 公共能力池 (Factory Registry — 不属于 Project)
    ├── Organizations / Industries / Agents / Skills
    ├── MCPs / Workflows / LLM Providers / Templates
```

**Factory Capability Model (关键约束):**
- Agent / Skill / MCP / Workflow / Industry / LLM 属于 **Factory Registry (公共资源)**, 不属于 Project。
- Project 只持有 **Workflow Instance** (公共 Workflow 的实例化, 带运行参数)。
- 任何 Agent/Skill/MCP/Workflow 执行必须绑定 `project_id`; 运行数据写入对应 project runtime (禁止跨项目污染)。

## 二、Project 生命周期状态机 (S10-009 扩展)

```
                    ┌──────────────┐
  输入想法 ────────▶ │    DRAFT     │  (unnamed-project-XXX, 草稿, 无正式名)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  DISCOVERY   │  (Product Discovery Session: AI 产品经理沟通)
                    └──────┬───────┘
                           │ 产品定义完成
                           ▼
                    ┌──────────────┐
                    │PRODUCT_DEFINED│ (product-definition.md 落库)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │    DESIGN    │  (UI/UX 设计)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ ARCHITECTURE │  (技术方案)
                    └──────┬───────┘
                           │ 用户确认 (正式命名 rename)
                           ▼
                    ┌──────────────┐
                    │  CONFIRMED   │  (项目定名, 待开发)
                    └──────┬───────┘
                           │ 开始开发 (Workflow 自动执行)
                           ▼
                    ┌──────────────┐
                    │ DEVELOPMENT  │  (Software Development Workflow 执行)
                    └──────┬───────┘
                           │ 发布
                           ▼
                    ┌──────────────┐
                    │   RELEASE    │  (发布产物)
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   MAINTAIN   │  (维护期)
                    └──────────────┘

兼容保留 (旧数据宽容解析, 零破坏): ACTIVE / MAINTAINED / ARCHIVED

受控转换表 PROJECT_TRANSITIONS:
  draft → (discovery, archived)
  discovery → (product_defined, archived)
  product_defined → (design, archived)
  design → (architecture, archived)
  architecture → (confirmed, archived)
  confirmed → (development, archived)
  development → (release, archived)
  release → (maintain, archived)
  maintain → (archived,)
  active → (maintained, archived)      # 旧值兼容
  maintained → (archived,)
  archived → ()
```

## 三、数据模型 (Project)

```
Project:
  id: str                    # 稳定 id (rename 不变)
  name: str                  # 显示名 (draft = "unnamed-project-XXX")
  slug: str                  # 目录名 (rename 时更新)
  user_id: str
  goal: str                  # 原始想法
  lifecycle: ProjectState    # 状态机 (DRAFT→DISCOVERY→...→MAINTAIN)
  draft: bool = False
  product_definition_ref: str = ""   # discovery/product-definition.md
  discovery: DiscoverySession | None # Product Discovery Session (持久化)
  bindings: ProjectBindings          # Workflow/Agent/Skill/MCP binding
  created_at / updated_at
  # 既有字段保留 (S9-004): repo_path/language/framework/build/test/project_type/refs

DiscoverySession (Product Discovery Session — 沟通过程持久化):
  session_id: str
  started_at / updated_at
  ai_suggestion: {suggested_name, slug, summary, questions, ai_generated}  # suggest 起点
  questions: [ {q, asked_at, answer, answered_at} ]   # 逐条问答记录
  product_definition: str | None      # 确认后的 product-definition.md 内容
  status: active | completed          # 用户确认后 completed

ProjectBindings (Project ↔ 公共资源 binding):
  workflow_instance: {workflow_ref, version, parameters}   # 如 software-development-v1
  agents: [ {agent_ref, role} ]        # 如 PM-Agent-v2 / Flutter-Agent
  skills: [ skill_ref ]                # 如 flutter-development / test-generation
  mcps: [ mcp_ref ]
  industry: industry_ref | None
```

## 四、Project Space 目录 (唯一隔离边界)

```
workspace/projects/{project-slug}/
│
├── project.json              # Project 记录 (生命周期主体, 信源)
│
│── 1. Product Assets (产品资产)
│   ├── idea/
│   │   ├── conversation.json
│   │   └── idea.md
│   ├── discovery/
│   │   ├── conversation.json     # Product Discovery Session 持久化
│   │   └── product-definition.md
│   ├── product/                  # 产品相关 (PRD/UI 设计系统/原型)
│   ├── design/
│   ├── architecture/
│   ├── source/                   # 代码 (开发产物固定落位)
│   ├── artifacts/                # 产物 (发布/文档/测试报告)
│   └── knowledge/                # 项目知识 (domain/decisions/lessons/...)
│
│── 2. AI Runtime Data (运行上下文 — 不属于产品内容)
│   └── runtime/
│       ├── agent-execution/      # Agent 执行状态
│       ├── skill-execution/      # Skill 执行记录
│       ├── mcp-calls/            # MCP 调用记录
│       ├── workflow-instances/   # Workflow 运行实例
│       ├── state/                # 中间状态
│       └── context/              # AI 上下文
│
│── 3. Audit Data (系统审计)
│   └── log/
│       ├── workflow.log
│       ├── agent.log
│       ├── error.log
│       └── user-audit.log
│
└── 4. Management (项目管理 — Agile Scrum)
    └── management/
        ├── roadmap.md
        ├── milestone.json
        ├── sprint/
        │   ├── sprint-001.json    # Goal/Planning/Execution/Review
        │   └── ...
        ├── backlog/
        │   ├── epic.json
        │   ├── feature.json
        │   ├── story.json
        │   └── task.json
        ├── risk.json
        ├── metrics.json
        └── decisions.json         # Decision Log
```

**隔离原则:**
- runtime 和 log 不属于产品内容 — 不进 PRD/代码生成/知识库索引。
- 所有 Agent/Skill/MCP/Workflow 执行绑定 project_id, 运行数据写入对应 project runtime (如 `scorepocket/runtime/`, 禁止 `workspace/runtime/` 跨项目污染)。

## 五、API 变化

```
POST /api/projects/suggest       {idea} → Product Discovery Session 起点
                                   (AI 提议名称/理解/问题 — 持久化为 discovery session)
POST /api/projects               {idea} → 创建 DRAFT (unnamed, DRAFT)
                                   {idea, name?} → 旧兼容: 直接 CONFIRMED
POST /api/projects/{id}/discovery/answer  {question, answer} → 沟通持久化
POST /api/projects/{id}/discovery/complete → product_defined (生成 product-definition.md)
POST /api/projects/{id}/confirm  {name} → rename 事务 (见六) → CONFIRMED
GET  /api/projects/{id}          → Project 详情 (含 discovery/bindings)
GET  /api/projects/{id}/bindings → binding 配置 (workflow/agents/skills/mcps)
PATCH/DELETE /api/projects/{id}  [已有, 兼容]
POST /api/projects/{id}/start    [已有 — confirmed 后启动 workflow]
```

## 六、rename 机制 (事务流程)

```
POST /api/projects/{id}/confirm {name}
  1. 校验: name/slug 合法 + 唯一 (目标 slug 不存在)
  2. 快照: 记录 rename 前状态 (回滚点)
  3. 写 project.json: name/slug/lifecycle=confirmed/draft=false
  4. 目录 rename: unnamed-project-XXX → {slug} (原子 os.replace)
  5. 索引更新: workspace 索引 (org/projects.json 镜像)
  6. 引用更新 (事务内):
     - workflow-instance 引用
     - runtime 绑定
     - knowledge 索引
     - search index
     - artifact/history 引用
  7. 提交; 任一步失败 → 回滚到快照 (目录/索引/引用全部还原)
  返回 {project_id, name, slug, lifecycle: confirmed}
```

## 七、Project ↔ Workflow/Agent/Skill/MCP binding

```
公共资源 (Factory Registry): Software Development Workflow
  Requirement Analysis → PM Agent → UI Agent → Architect Agent →
  Developer Agent → Tester Agent → Release Agent

项目实例 (binding):
  scorepocket/management/bindings.json (或 project.json.bindings):
    workflow_instance:
      workflow_ref: software-development-v1
      parameters: { industry: software }
    agents:
      - { agent_ref: PM-Agent-v2, role: product }
      - { agent_ref: Architect-Agent-v3, role: architecture }
      - { agent_ref: Flutter-Agent, role: developer }
    skills: [ flutter-development, test-generation ]
    mcps: []
    industry: software

执行约束: 所有 Agent 任务必须绑定 project_id + sprint_id + task_id;
runtime 保存执行过程; management 保存业务状态 (禁止项目管理状态存 runtime)。
```

## 八、Migration 方案 (零破坏)

```
现状: org/projects.json 集中式 (id 索引) — 旧项目 ledger-app/markpad 等
方案 A (采纳): 目录信源 + 索引兼容
  1. 新项目 → workspace/projects/{slug}/ 目录 (project.json 为信源)
  2. org/projects.json 保留为只读索引 (旧项目兼容 + 目录项目镜像)
  3. 旧项目懒迁移: 首次访问回填目录镜像 (零风险)
  4. 前端列表 = org 索引 ∪ 目录扫描 (dedupe by id)
兼容保证: 既有项目 (MarkPad/AI Factory/TimeOn) 完全不受影响
```

## 九、验收场景

```
场景1: 输入 "我想做一个台球计分App" → 创建 Draft (unnamed, DRAFT)
       → Product Discovery Session 启动 → AI 提问 (持久化 conversation.json)
场景2: 确认名称 ScorePocket → rename 事务 (目录/索引/引用全更新) → CONFIRMED
场景3: 既有项目 (MarkPad/AI Factory/TimeOn) 读取不受影响
场景4: Agent 执行绑定 project_id, runtime 数据隔离 (scorepocket/runtime/)
```

## 十、实施范围 (S10-009, 不开发 UI)

```
Task 1: Domain Model (状态机 DRAFT→...→MAINTAIN + DiscoverySession + bindings)
Task 2: Project Space 目录 (三类 + management/)
Task 3: Draft 创建 + Product Discovery Session 持久化
Task 4: rename 事务机制
Task 5: Management Domain 骨架 (backlog/sprint/task 数据模型 — 见
        project-management-system.md)
Task 6: Execution Engine 骨架 (任务调度/agent 绑定 — 见 execution-engine.md)
完成: 场景 1/2/3/4 测试 + 文档 → 暂停 (不开发 UI)
```
