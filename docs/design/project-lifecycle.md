# Project Lifecycle — Domain Model & Architecture (S10-008)

> 状态: 架构待确认 | 范围: Project Lifecycle Domain Model (不开发 UI)
> 对齐: S10-008 任务书 (状态机/目录/Draft/rename/Discovery 持久化)

## 一、顶层结构

```
AI Factory
│
├── Workspace                 # 用户工作空间 (项目容器)
│   ├── Project A             # 软件项目 (生命周期主体)
│   ├── Project B
│   └── Workspace Config
│
└── Factory Capability Pool   # 公共能力池 (后续 Sprint 扩展)
    ├── Organizations / Industries / Agents / Skills
    ├── MCPs / Workflows / LLM Providers / Templates
```

> 重要: Workspace 只是容器。Project 才是生命周期主体。Idea/Discovery 属于 Project,
> 不做 Workspace 级 Idea Pool。

## 二、状态图 (Project State Machine)

```
                    ┌────────────┐
  输入想法 ────────▶ │  IDEA      │  (草稿创建, 无正式名)
                    └─────┬──────┘
                          │ 确认进入沟通
                          ▼
                    ┌────────────┐
                    │ DISCOVERY  │  (AI 产品经理沟通: 方向/痛点/画像/场景/
                    └─────┬──────┘   功能/MVP/使用方式/商业)
                          │ 用户确认 (正式命名)
                          ▼
                    ┌────────────┐
                    │ CONFIRMED  │  (产品定义落库, 待开发)
                    └─────┬──────┘
                          │ 开始开发 (workflow 自动执行)
                          ▼
                    ┌────────────┐
                    │DEVELOPMENT │  (Software Development Workflow 执行)
                    └─────┬──────┘
                          │ 发布
                          ▼
                    ┌────────────┐
                    │  RELEASE   │  (发布产物, 可维护)
                    └────────────┘

兼容保留 (旧数据): ACTIVE / MAINTAINED / ARCHIVED (宽容解析, 零破坏)
受控转换表 PROJECT_TRANSITIONS:
  idea → (discovery, archived)
  discovery → (confirmed, archived)
  confirmed → (development, archived)
  development → (release, archived)
  release → (archived,)
  active → (maintained, archived)      # 旧值兼容
  maintained → (archived,)
  archived → ()
```

## 三、数据模型 (Project)

```
Project:
  id: str                    # 稳定 id (P-xxx 或 slug; rename 不变)
  name: str                  # 显示名 (draft 阶段 = "unnamed-project-XXX")
  slug: str                  # 目录名 (rename 时更新)
  user_id: str
  goal: str                  # 原始想法
  lifecycle: ProjectState    # 状态机 (IDEA/DISCOVERY/CONFIRMED/DEVELOPMENT/RELEASE/...)
  draft: bool = False        # 草稿标记 (未确认命名)
  product_definition_ref: str = ""   # discovery/product-definition.md (确认产物)
  discovery: DiscoveryData | None    # 沟通记录 (questions/answers/summary)
  created_at / updated_at
  # 既有字段保留 (S9-004): repo_path/language/framework/build/test/project_type/refs

DiscoveryData:
  questions: [ {q: str, asked_at, answer: str|None, answered_at} ]
  product_definition: str | None   # 确认后 product-definition.md 内容/引用
  ai_suggestion: {suggested_name, slug, summary, ai_generated}  # suggest 起点
```

## 四、文件结构 (Project 目录)

```
workspace/
  projects/
    {slug}/                       # draft: unnamed-project-001 (未确认)
      project.json                # Project 记录 (生命周期主体, 信源)
      idea/
        conversation.json         # 想法沟通原始记录
        idea.md                   # 想法描述
      discovery/
        conversation.json         # AI 产品沟通记录 (questions/answers)
        product-definition.md     # 产品定义 (用户确认后生成)
      product/                    # 产品相关 (后续)
      design/                     # 设计 (后续)
      architecture/               # 架构 (后续)
      workflow-instance/          # workflow 实例 (run 引用/状态)
      source/                     # 代码 (开发产物固定落位)
      artifacts/                  # 产物 (发布/文档/测试报告)
      knowledge/                  # 项目知识 (后续)
```

## 五、API 变化

```
POST /api/projects/suggest       {idea} → AI 提议 (名称/理解/问题)     [已有]
POST /api/projects               {idea} → 创建 DRAFT (unnamed, DISCOVERY)
                                   {idea, name?} → 旧兼容: 直接 confirmed
POST /api/projects/{id}/discovery/answer  {question, answer} → 记录沟通 (DISCOVERY)
POST /api/projects/{id}/confirm  {name} → 正式命名:
                                   1. 校验 slug 唯一/合法
                                   2. rename 目录 (unnamed→{slug})
                                   3. 更新 project.json/索引/引用 (artifact/history)
                                   4. lifecycle: discovery → confirmed
GET  /api/projects/{id}          → Project 详情 (含 discovery 状态)
GET  /api/projects               → 列表 (draft 标记)
PATCH/DELETE /api/projects/{id}  [已有, 兼容]
POST /api/projects/{id}/start    [已有 — confirmed 后启动 workflow 自动执行]
```

## 六、Migration 方案 (零破坏)

```
现状: org/projects.json 集中式 (id 索引) — 旧项目 ledger-app/markpad 等
方案 A (采纳): 目录信源 + 索引兼容
  1. 新项目 → workspace/projects/{slug}/ 目录 (project.json 为信源)
  2. org/projects.json 保留为只读索引 (读取兼容旧项目 + 目录项目镜像)
  3. 旧项目懒迁移: 首次访问时回填目录镜像 (不主动搬移, 零风险)
  4. 前端列表 = org 索引 ∪ 目录扫描 (dedupe by id)
兼容保证: 场景3 (MarkPad/AI Factory/TimeOn 等既有项目) 完全不受影响
```

## 七、验收场景 (S10-008)

```
场景1: 输入 "我想做一个台球计分App" → 不创建正式项目
       → 创建 Draft (unnamed-project-XXX, lifecycle=DISCOVERY, draft=true)
       → AI 提问产品问题 (suggest/discovery 沟通)
场景2: 确认名称 ScorePocket → 目录 renamed → scorepocket/
       → project.json/索引/引用更新 → lifecycle=CONFIRMED
场景3: 既有项目 (MarkPad/AI Factory/TimeOn) 读取不受影响
```

## 八、实施范围 (S10-008, 不开发 UI)

```
Task 1: Domain Model (ProjectState 扩展 + DiscoveryData + draft/slug 字段)
Task 2: 目录结构 (workspace/projects/{slug}/ 布局 + project.json 读写)
Task 3: Draft 创建 (POST /api/projects {idea} → draft)
Task 4: rename 机制 (POST /confirm → 目录/索引/引用更新)
Task 5: Discovery 持久化 (conversation.json + product-definition.md + answer 端点)
完成: 场景 1/2/3 测试 + 文档 → 暂停 (不开发 UI)
```
