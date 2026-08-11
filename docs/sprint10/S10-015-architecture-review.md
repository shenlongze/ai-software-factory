# S10-015 Architecture Review — Todo Tree / Workflow / Runtime Adapter

> 版本: v1.0 | 日期: 2026-08-12 | 状态: ARCHITECTURE REVIEW (只读, 不写前端代码)
> 角色: 前端架构师 | 任务: S10-015 Task 001 (Architecture Review)
> 设计依据 (唯一): docs/design/AF-UI-Architecture.md (S10-013) + docs/sprint10/S10-014-plan.md §6 (API 映射) + S10-014-completion.md
> 数据依据: **真实后端 8011 实测** (2026-08-12 01:50 前后 curl 拉取, 非 Mock)
> 约束: 不修改任何代码/后端; 本文件为唯一输出

---

## 0. 结论摘要 (TL;DR)

1. **三个 Adapter 的输入类型都需要扩展**: 现有 `api/domain.ts` (S10-014 Task 007) 的
   `toTodoTree` 假设 backlog 是"epics 内嵌 features/items 对象"结构, **与真实后端
   结构不符** (真实是 4 个平行数组 + children id 引用, Epic/Feature/Story 无 status 字段)。
2. **层级映射定案**: Epic→phase, Feature→module, Story→task(工作项叶子, 状态从子
   Task 聚合), Task→task(执行单元, 作为 Story 子节点, Context Panel 详情) —
   4 层数据压入 3 型节点, 保持树深 ≤4 (项目→阶段→模块→任务)。
3. **children 关联策略**: 只能**自上而下** (Epic.children → Feature.children →
   Story.children → Task) 用 id 反向索引组装; 悬空引用跳过; 孤儿 Epic 保留为空阶段。
4. **状态映射**: 后端 Task 六态 `todo/ready/in_progress/blocked/review/done` (比任务
   上下文声明的 5 态多 `review`), Stage 状态含 `waiting_review` (现有 STATUS_ALIASES
   缺失 → 需补充), Workflow mock 标志 `is_mock=true` 必须降级展示 (不冒充真实执行)。
5. **真实数据环境差异**: 任务上下文描述的 P-16775f9f/P-eda01eca workflow + 19 条
   timeline 事件在当前 8011 后端**不存在** (当前仅 2 项目: markpad + P-806fe6e8,
   workflows=[]、timeline=[]); 审查已按当前真实响应为准并记录差异 (见 §2.4)。
6. **Task 拆分建议**: S10-015 Task 002-007 按 Adapter 归属见 §10 (backlog 索引关联
   重构是最大工作量, 单列 Task 002)。

---

## 1. 背景与范围

### 1.1 本 Review 定位

S10-014 完成了前端地基 (Shell/路由/Design System/Domain Adapter 占位-基础版),
Todo Tree / Workflow / Runtime 三页仍是 placeholder。S10-015 的目标是让这三页
**基于真实后端数据渲染**。本 Review 在动任何代码前, 先锁定三个核心 Adapter 的:

- 输入输出契约 (真实 API 响应结构为准)
- 层级映射 (4 层 backlog → 3 型节点树)
- 状态映射表 (后端值 → DomainStatus → 人话 → 色)
- children 关联策略 (id 引用 vs 内嵌)
- 降级策略 (空数据/mock/404)
- 与现有 `api/domain.ts` 的差异 (需改的签名/需新增的类型)

### 1.2 审查方法

全部结论基于以下**真实证据**:

| 证据 | 来源 |
|---|---|
| GET /api/projects | curl 8011 实测 (2 项目) |
| GET /api/projects/P-806fe6e8/backlog | curl 8011 实测 (3 Epic/2 Feature/2 Story/3 Task) |
| GET /api/projects/P-806fe6e8/workflow | curl 8011 实测 (is_mock=true 演示工作流, 6 stages) |
| GET /api/projects/P-806fe6e8/timeline | curl 8011 实测 ([]) |
| GET /api/projects/P-806fe6e8/backlog/task/TASK-a8a01f8d | curl 8011 实测 |
| GET /api/projects/P-806fe6e8/lifecycle | curl 8011 实测 (404 lifecycle not found) |
| GET /api/dashboard | curl 8011 实测 |
| factory-org/org/management.py | TaskStatus 六态枚举 + Epic/Feature/Story/Task 模型 |
| factory-core/events/models.py | EventType 全量枚举 (org.* 受控词表) |
| factory-console/service.py | get_project_workflow / get_project_timeline / _timeline_summary / TIMELINE_TYPES / MOCK_STAGE_CHAIN |
| factory-console/web/backend/fastapi_adapter.py | 59 路由定义 + mock fallback 语义 |
| frontend src/api/domain.ts + src/models/domain.ts + src/models/types.ts | 现有 Adapter/域模型/后端类型 |

---

## 2. 数据源确认 (真实 API 响应)

### 2.1 Backlog — GET /api/projects/{project_id}/backlog

**真实响应** (P-806fe6e8 ScorePocket, 2026-08-12 01:50 实测, 节选):

```json
{
  "project_id": "P-806fe6e8",
  "epics": [
    {"id": "EPIC-6ffd3c02", "name": "计分核心", "description": "台球计分",
     "children": [], "created_at": "2026-08-11T17:49:45.602701Z", "updated_at": "..."},
    {"id": "EPIC-89bcd292", "name": "UI 界面", "description": "Flutter 界面",
     "children": [], "created_at": "...", "updated_at": "..."},
    {"id": "EPIC-c6cac2d8", "name": "计分核心", "description": "台球计分核心功能",
     "children": ["FEAT-39a91953", "FEAT-f6d9c303"], "created_at": "...", "updated_at": "..."}
  ],
  "features": [
    {"id": "FEAT-39a91953", "name": "用户系统", "description": "注册登录",
     "children": ["STORY-9f928023"], "created_at": "...", "updated_at": "..."},
    {"id": "FEAT-f6d9c303", "name": "比赛管理", "description": "创建比赛/计分",
     "children": ["STORY-317aed7b"], "created_at": "...", "updated_at": "..."}
  ],
  "stories": [
    {"id": "STORY-9f928023", "name": "用户注册", "description": "手机号注册",
     "children": ["TASK-a8a01f8d", "TASK-e10a6043"], "created_at": "...", "updated_at": "..."},
    {"id": "STORY-317aed7b", "name": "创建比赛", "description": "新比赛",
     "children": ["TASK-425bf30b"], "created_at": "...", "updated_at": "..."}
  ],
  "tasks": [
    {"id": "TASK-425bf30b", "title": "计分逻辑", "description": "实时计分",
     "priority": "P0", "status": "todo", "assignee": "", "dependency": [],
     "created_at": "...", "updated_at": "...", "history": []},
    {"id": "TASK-a8a01f8d", "title": "实现注册 API", "description": "POST /api/register",
     "priority": "P1", "status": "todo", "assignee": "", "dependency": [],
     "created_at": "...", "updated_at": "...", "history": []},
    {"id": "TASK-e10a6043", "title": "实现登录 API", "description": "POST /api/login JWT",
     "priority": "P1", "status": "todo", "assignee": "", "dependency": [],
     "created_at": "...", "updated_at": "...", "history": []}
  ]
}
```

**结构确认 (对照 factory-org/org/management.py 模型):**

| 实体 | 字段 | 有 status? | 有回溯字段? | 层级关联 |
|---|---|---|---|---|
| Epic | id/name/description/children/created_at/updated_at | ❌ 无 | ❌ 无 | children = Feature id 引用 |
| Feature | id/name/description/children/created_at/updated_at | ❌ 无 | ❌ 无 (无 epic_id) | children = Story id 引用 |
| Story | id/name/description/children/created_at/updated_at | ❌ 无 | ❌ 无 (无 feature_id) | children = Task id 引用 |
| Task | id/title/description/priority/status/assignee/dependency/created_at/updated_at/history | ✅ 六态 | — | 叶子 |

⚠️ **与任务上下文声明的差异**:
- 上下文说 "epic_id/feature_id/story_id 可能为 None" — **实际响应根本没有这些字段**,
  唯一关联途径是自上而下的 `children` id 引用。
- 上下文说 Task 状态机 "todo→ready→in_progress (合法: ['ready','blocked'])" —
  **实际 (management.py TaskStatus) 是六态**: `todo / ready / in_progress / blocked /
  review / done`, 含 `review` (等待人工审核)。前端必须覆盖 review 态。
- Epic/Feature/Story **无 status/进度字段** → 树节点状态只能从子 Task 聚合, 不能读自身。
- 真实数据存在**孤儿 Epic** (EPIC-6ffd3c02/EPIC-89bcd292, children=[]) 与重复命名
  (两个"计分核心") — 前端必须能处理空阶段, 且如实展示 (不臆造)。

### 2.2 Workflow — GET /api/projects/{project_id}/workflow

**真实响应** (P-806fe6e8, 2026-08-12 01:50 实测, 节选):

```json
{
  "id": "mock-wf-P-806fe6e8",
  "project_id": "P-806fe6e8",
  "project_name": "ScorePocket",
  "name": "Mock Workflow (演示数据)",
  "status": "active",
  "failed_reason": "",
  "created_at": "2026-08-11T17:52:06.202422+00:00",
  "started_at": "2026-08-11T17:52:06.202422+00:00",
  "completed_at": null,
  "stages": [
    {"id": "mock-product-manager", "workflow_id": "mock-wf-P-806fe6e8",
     "role_id": "product-manager", "name": "Product", "order": 1,
     "status": "completed", "depends_on": [], "input_artifacts": [],
     "output_artifacts": [], "approval_required": false,
     "artifact": {"id": "mock-art-product-manager", "type": "product",
                  "ref": "mock://product", "status": "validated",
                  "producer_role": "product-manager", "producer_agent": "", ...},
     "pending_approval": null},
    {"id": "mock-ui-designer", "role_id": "ui-designer", "name": "UX/UI",
     "order": 2, "status": "completed", "depends_on": ["product-manager"], ...},
    {"id": "mock-architect", "role_id": "architect", "name": "Architecture",
     "order": 3, "status": "waiting_review", "approval_required": true,
     "artifact": null, "pending_approval": null, ...},
    {"id": "mock-developer", "role_id": "developer", "name": "Code",
     "order": 4, "status": "pending", ...},
    {"id": "mock-tester", "role_id": "tester", "name": "Test", "order": 5,
     "status": "pending", ...},
    {"id": "mock-devops", "role_id": "devops", "name": "Release", "order": 6,
     "status": "pending", ...}
  ],
  "pending_approvals": [],
  "template": [],
  "is_mock": true
}
```

**结构确认 (对照 fastapi_adapter.py + service.py):**

- 后端语义: 项目存在但**无真实 workflow 运行** → 返回 **mock 工作流** (`is_mock=true`,
  名称 "Mock Workflow (演示数据)", `MOCK_STAGE_CHAIN` 6 阶段链), **不是 404**;
  项目不存在 → 404 `{"detail":"project not found"}` (实测 P-16775f9f 即此)。
- stage 字段 = `StageSummary` (types.ts 已有): id/role_id/name/order/status/depends_on/
  approval_required/artifact/pending_approval (+ 真实运行时的 agent_id/duration_s 来自
  `GET /api/workflows/{id}/stages` → StageRunSummary)。
- **stage.status 受控词**: mock 用 `completed / waiting_review / pending`; 真实 org
  Stage 为 `pending / ready / running / blocked / completed / failed` (大写枚举小写化)。
  `waiting_review` 现有 `STATUS_ALIASES` 未覆盖 → **必须补** (→ review 语义)。
- role_id 受控: product-manager / ui-designer / architect / developer / tester / **devops**
  — 现有 `ROLE_LABELS` 缺 `devops` → 需补 (→ 发布工程师)。
- stage name 是英文 (Product/UX/UI/Architecture/Code/Test/Release), 现有
  `STAGE_NAME_LABELS` 按 name 映射的键不含这些英文 → **映射应优先 role_id** (已有),
  name 仅作兜底/展示副标题。

### 2.3 Timeline — GET /api/projects/{project_id}/timeline

**真实响应** (P-806fe6e8, 实测): `[]` (诚实空态 — 该项目尚无任何 org 运行事件)。

**结构确认 (对照 service.py `_timeline_summary` + types.ts `TimelineEventSummary`):**

```json
{"id": "evt-<seq>", "seq": 61, "project_id": "P-xxx", "type": "stage",
 "event_type": "org.workflow.stage_started", "stage_id": "stage-xxx",
 "agent_id": "product-manager", "artifact_id": null, "gate_id": null,
 "message": "阶段开始 ScorePocket", "status": "completed", "payload": {...},
 "created_at": "2026-08-11T17:52:06.202422Z"}
```

- `type` 五类: `user | stage | artifact | review | error` (TIMELINE_TYPES 投影)。
- `event_type` 受控词表 (factory-core/events/models.py EventType + TIMELINE_TYPES 20 项):
  - user: org.project.created / registered / lifecycle_changed
  - stage: org.workflow.created / started / stage_ready / stage_started / stage_completed / completed
  - error: org.workflow.failed / org.artifact.failed
  - artifact: org.artifact.created / updated / validated / consumed / archived
  - review: org.approval.created / approved / rejected
  - (另有 org.execution.* 6 项 + org.project.task_linked / org.sprint.* / org.stage.created /
    org.artifact.viewed / org.workflow.viewed 等, 不进 Timeline 或按需宽松映射)
- `message` 后端已生成人话动词 (如 "阶段开始" + name 详情; error 带 reason)。
- `agent_id` 服务端已投影为 payload.role_id (如 "product-manager") — 前端仍需转人话。
- `status` = event.result or event.stage (如 "completed"/"validated")。

### 2.4 ⚠️ 数据环境差异记录 (上下文声明 vs 实测)

| 项 | 任务上下文声明 | 当前 8011 实测 (2026-08-12) | 影响 |
|---|---|---|---|
| 项目数 | 6 (markpad/ledger-app 多实例/P-806fe6e8) | 2 (markpad, P-806fe6e8 ScorePocket/idea) | Adapter 不得依赖具体项目; 空态必须健壮 |
| Workflow 数据 | P-16775f9f (active) + P-eda01eca (completed) | `/api/workflows` → []; P-16775f9f/P-eda01eca 均为 "project not found" | 真实路径: 项目存在无 workflow → **is_mock=true 演示流** |
| Timeline 事件 | P-16775f9f 19 事件 | P-806fe6e8 → [] (诚实空态) | 空数组必须渲染空态, 不报错 |
| Task 状态机 | 5 态 (todo/ready/in_progress/blocked/done) | **6 态** (+ review) | 状态映射表需含 review |
| children 字段 | "epic_id/feature_id/story_id 可能为 None" | 无任何回溯字段, 仅 children id 引用 | 关联策略 = 自上而下 id 索引 |

结论: 上下文数据快照来自 S10-014 完成时的后端状态; 当前后端 (HOME=/Users/agentdev,
`~/.factory`, PID 41299 监听 8011) 已被重置为 2 项目 + ScorePocket backlog。
**本 Review 全部设计以实测响应为准** (前端 Adapter 本来就只依赖响应结构, 不依赖具体数据,
因此设计结论不受影响, 反而验证了降级路径的真实性: mock workflow + 空 timeline + 孤儿 Epic
都是**当前就会触发**的路径, 不是理论场景)。

---

## 3. Todo Tree Domain Adapter 设计

### 3.1 输入输出契约

```
输入:  GET /api/projects/{project_id}/backlog  (BacklogResponseInput, 新类型)
        + GET /api/projects/{project_id}        (ProjectSummary, 现有)
        (+ 可选 runtime 信号增强 — 本期可不接)
输出:  TodoTree { root: TreeNode }              (现有 models/domain.ts)
```

**新类型 BacklogResponseInput (需新增, 对齐真实响应):**

```ts
export interface BacklogItemInput {           // Epic/Feature/Story 共用
  id?: string | null;
  name?: string | null;
  description?: string | null;
  children?: string[] | null;                  // id 引用 (非对象!)
  created_at?: string | null;
  updated_at?: string | null;
}
export interface BacklogTaskInput {            // Task (唯一有 status 的层)
  id?: string | null;
  title?: string | null;
  description?: string | null;
  priority?: string | null;                    // P0-P3
  status?: string | null;                      // 六态
  assignee?: string | null;
  dependency?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
  history?: Array<Record<string, unknown>> | null;
}
export interface BacklogResponseInput {
  project_id?: string | null;
  epics?: BacklogItemInput[] | null;
  features?: BacklogItemInput[] | null;
  stories?: BacklogItemInput[] | null;
  tasks?: BacklogTaskInput[] | null;
}
```

### 3.2 层级映射 (4 层数据 → 3 型节点)

用户心智 (S10-013 §4.2): 项目 → 阶段 → 模块 → 任务, 树深 ≤4。
真实数据 4 层: Epic → Feature → Story → Task。映射定案:

| 后端层 | 节点 | 说明 |
|---|---|---|
| Epic | **phase** | 用户心智的"产品阶段/能力域" (S10-014 §5.2 已定 epic→阶段) |
| Feature | **module** | 用户可感知功能域 |
| Story | **task** (工作项叶子, 可展开) | 用户故事 = 需求工作项; 状态/进度从子 Task 聚合 |
| Task | **task** (Story 的子节点) | 真正执行单元; 展示在 Story 展开后, 详情进 Context Panel |

- 为什么 Story → task 而非折叠进 module: 真实数据中 Story 是 Feature 直接子层且
  Task 挂在 Story 下 (Feature.children 引用的就是 Story id), 折叠会丢粒度且无法
  自上而下组装。TreeNode 三型 (phase/module/task) 允许递归 children, 因此
  "task 型节点带 task 型子节点" 合法 — 视觉上即"用户注册 🔄 50% → 实现注册 API ✅"。
- **Story 无 status** → task 节点状态 = 子 Task 聚合 (aggregateStatus 复用);
  **Task 有 status** → 直接映射。
- 完成度聚合 (§4.5): 叶子 Task 权重 = 优先级 (P0 最高, 建议 P0=4/P1=3/P2=2/P3=1,
  缺省 P2); Story/Feature/Epic = 子节点加权均值; 无子 → 0%。

### 3.3 children 关联策略 (核心)

真实结构**无回溯字段 + children 为 id 引用** → 只能自上而下组装:

```
1. 构建 id → 节点 反向索引 (epics/features/stories/tasks 各一张 Map, 或统一 Map)
2. 对每个 Epic: children.map(id => featureIndex.get(id)) → 子 Feature
3. 对每个 Feature: children.map(id => storyIndex.get(id)) → 子 Story
4. 对每个 Story: children.map(id => taskIndex.get(id)) → 子 Task
5. 悬空引用 (index.get 返回 undefined) → 跳过该引用 (不崩溃, 不占位)
6. 孤儿 Epic (children=[]) → 保留为空阶段 (progress 0, status pending,
   标题旁可显示"暂无任务"弱提示 — 如实展示, 因为用户可能刚建 Epic)
7. 兜底: 若全部 4 数组均空 → 项目级降级树 (现有 fallbackRoot 逻辑, §3.5)
```

- 不做"从下往上" (Task 无 epic/feature 归属字段, 无法反查)。
- 不修改后端 (§6.3 原则): 索引在 Adapter 内构建, 纯函数。

### 3.4 状态映射 (Task 六态)

| 后端 Task.status | DomainStatus | 人话 | 色 (S10-013 §9.2) |
|---|---|---|---|
| todo | pending | 待办 | 灰 |
| ready | pending | 待办 (就绪) | 灰 |
| in_progress | running | 执行中 | 蓝 (呼吸) |
| blocked | blocked | 阻塞 | 紫 |
| review | review | 待审核 | 橙 |
| done | completed | 完成 | 绿 |
| 缺失/未知 | pending (fallback) | 待办 | 灰 |

Epic/Feature/Story 无自身 status → 节点状态 = 子节点聚合 (aggregateStatus:
failed > blocked > running > review > completed > pending, 现有实现复用)。

### 3.5 降级策略 (Todo Tree)

| 场景 | 行为 |
|---|---|
| backlog 4 数组全空 / 结构不匹配 | 项目级降级树 (现有 fallbackRoot: 3 阶段从 lifecycle/workflow 信号派生) — **保持** |
| 有 epics 但 children 全悬空 | 空阶段树 (阶段存在, 无子任务, 0%) |
| 单引用悬空 | 跳过该子引用 |
| Epic/Feature/Story 无 status | 子节点聚合; 无子 → pending |
| 后端 404 (项目不存在) | 调用方 (页面) 处理错误态, Adapter 不抛异常 (返回降级树 + 标记) |

---

## 4. Workflow Adapter 设计

### 4.1 输入输出契约

```
输入:  GET /api/projects/{project_id}/workflow  → WorkflowDetail (现有 types.ts, 含 is_mock)
       (可选) GET /api/workflows/{workflow_id}/stages → StageRunSummary[] (agent_id/duration_s)
输出:  WorkflowPipeline { templateId, templateName, stages: WorkflowStage[] }  (现有 domain)
       + 新增 isMock?: boolean  (mock 降级标记)
```

现有签名 `toWorkflowPipeline(project?, workflowDetail?, stages?)` **兼容**真实响应
(workflowDetail 即 WorkflowDetail 形状, 内嵌 stages)。需扩展:

### 4.2 映射表

| 后端 stage 字段 | Domain 字段 | 规则 |
|---|---|---|
| order | order | 缺省 index+1 (现有) |
| name | name | **优先 role_id → 人话** (现有 ROLE_LABELS); name 兜底 (需补英文名映射或直接显示) |
| role_id | agentName | ROLE_LABELS[role_id] ?? role_id; 真实运行时 agent_id (= role_id, 服务端投影) 优先 |
| status | status | 见 §4.3 |
| artifact.type | currentTask | artifactTypeLabel (现有) |
| artifact.ref | artifact | 现有 |
| duration_s (StageRunSummary) | duration | 现有 |
| pending_approval.status === 'pending' | status=review | 现有 (审批门覆盖) |

### 4.3 状态映射 (Stage)

| 后端 stage.status | DomainStatus | 人话 | 色 |
|---|---|---|---|
| completed | completed | 完成 | 绿 |
| running / started | running | 执行中 | 蓝 |
| waiting_review ⚠️ | **review** | 等待人工 | 橙 (审批门高亮) |
| pending / ready | pending | 待执行 | 灰 |
| blocked | blocked | 阻塞 | 紫 |
| failed / error | failed | 失败 | 红 |
| 未知/缺失 | pending | 待执行 | 灰 |

⚠️ **现有 STATUS_ALIASES 缺 `waiting_review`** (mock 阶段链实测值) → 补 `waiting_review: 'review'`。
⚠️ 真实 org Stage 状态 (pending/ready/running/blocked/completed/failed) 均已覆盖。

### 4.4 role_id → 人话 Agent 名 (需补 devops)

| role_id | 人话 | 现有? |
|---|---|---|
| product-manager / pm / planner | 产品经理 | ✅ |
| ui-designer / designer | UI 设计师 | ✅ |
| architect | 架构师 | ✅ |
| developer / backend-dev / full-stack-dev | 开发工程师 | ✅ |
| tester / qa-engineer | 测试工程师 | ✅ |
| **devops** ⚠️ | **发布工程师** | ❌ 需补 |

### 4.5 降级策略 (Workflow) — is_mock 是本期新增核心

| 场景 | 行为 |
|---|---|
| 404 / null (项目无 workflow 且后端无 mock) | templateName='未启动', stages=[] (现有) — 保持 |
| **is_mock=true** ⚠️ (实测当前必中) | **降级**: 不渲染成真实执行流。建议 WorkflowPipeline 新增 `isMock?: boolean`; 页面显示"演示数据/未启动"标识 (标注非真实运行), 节点状态仍可展示 (帮助预览模板形状) 但弱化 (灰化/水印) |
| stage.status 未知 | pending 降级 (现有) |
| stages 缺失 | 空数组 (现有) |

⚠️ 设计决策记录: 后端 mock 工作流 status='active' 且 2 阶段 completed — 若前端直接渲染
会给用户"项目已执行到架构阶段"的错误认知。**必须**以 is_mock 标记降级 (诚实原则,
与后端 docstring "诚实标注, 不冒充真实" 一致)。

---

## 5. Runtime Adapter 设计

### 5.1 输入输出契约

```
输入:  GET /api/projects/{project_id}/timeline → TimelineEventSummary[] (现有 types.ts)
       (可选) SSE /api/events/stream 增量 → EventSummary (现有, 结构兼容)
输出:  RuntimeActivity[] { time, actor, action, result, projectName? }  (现有 domain)
```

现有签名 `toRuntimeActivity(events?: unknown[] | null, projectName?: string | null)`
**兼容** TimelineEventSummary (created_at/message/status/agent_id/event_type 读取已有)。
需扩展:

### 5.2 映射表

| TimelineEventSummary | RuntimeActivity | 规则 |
|---|---|---|
| created_at | time | 现有 (created_at ?? timestamp ?? time) |
| agent_id (已投影 role_id) | actor | **需转人话**: ROLE_LABELS[agent_id] ?? agent_id (新增; 现在直接显示 "product-manager") |
| message (后端人话动词, 优先) | action | 现有 (message || EVENT_ACTION_LABELS[event_type] || event_type) — 保持 |
| event_type | action (无 message 时) | EVENT_ACTION_LABELS 补 org.approval.* 3 项 + org.project.* 3 项 (见 §5.3) |
| status (= result or stage) | result | 现有 (str) — 可选增强: 转人话 (completed→完成) |
| type (user/stage/artifact/review/error) | (过滤/分组用) | 可选: 供前端 Timeline 分组 |

### 5.3 EVENT_ACTION_LABELS 补齐清单 (对照 TIMELINE_TYPES 20 项)

现有已覆盖: org.workflow.created/started/stage_ready/stage_started/stage_completed/
completed/failed; org.artifact.created/updated/validated/consumed; error。
**需新增**:

| event_type | 人话 |
|---|---|
| org.project.created | 项目创建 |
| org.project.registered | 项目注册 |
| org.project.lifecycle_changed | 生命周期流转 |
| org.artifact.failed | 产物失败 |
| org.artifact.archived | 产物归档 |
| org.approval.created | 审批待处理 |
| org.approval.approved | 审批通过 |
| org.approval.rejected | 审批驳回 |
| (宽松) org.execution.started/completed/failed | 开始执行/执行完成/执行失败 |

### 5.4 降级策略 (Runtime)

| 场景 | 行为 |
|---|---|
| 空数组 (实测当前) | → [] (现有) — 页面渲染"暂无活动"空态 |
| 非数组 / null | → [] (现有) |
| 未知 event_type | message 优先; 无 message → 原样显示 event_type (现有) |
| agent_id 未知 role | 原样显示 (现有) |
| 后端 404 (项目不存在) | 调用方错误态, Adapter 返回 [] |

---

## 6. Task Detail 数据流

### 6.1 输入输出契约

```
输入:  GET /api/projects/{project_id}/backlog/task/{task_id} → Task 实体 (真实实测)
       (可选) GET /api/projects/{project_id}/timeline 过滤 task 相关事件 (增强)
输出:  TaskDetail { id, title, status, statusLabel, agent?, owner?, startedAt?,
                    completedAt?, nextAction?, blockedReason?, history: Activity[], artifacts: [] }
```

**真实 Task 响应** (TASK-a8a01f8d 实测): `{id, title, description, priority, status,
assignee, dependency, created_at, updated_at, history}`。

### 6.2 映射确认

| 真实字段 | TaskDetail | 规则 |
|---|---|---|
| id / title | id / title | 直映 |
| status (六态) | status / statusLabel | toDomainStatus (现有) |
| assignee | owner | 现有 `owner: t.owner ?? t.assignee` — ⚠️ 真实 assignee='' (空串) 应归一为 undefined (否则显示空负责人) |
| created_at / updated_at | startedAt / completedAt? | ⚠️ 真实模型**无 started_at/completed_at** — 降级 undefined; 可选用 created_at 显示"创建时间" |
| history (HistoryEntry {time,actor,action,result}) | history: Activity[] | 现有 toActivity 兼容 (time/actor/action/result 直读) |
| next_action / blocked_reason | nextAction / blockedReason | ⚠️ 真实模型无此字段 → undefined (现有降级); 待后端补充前不臆造 |
| priority / description / dependency | — | **domain 无对应字段** → 决策: TaskDetail 是否新增? 见 §6.3 |

### 6.3 设计决策: TaskDetail 是否扩字段

S10-013 §4.4 Context Panel 展示字段 = 状态/完成人/Agent/开始/完成/下一步/阻塞/历史/产物
— 不含 priority/description/dependency。但 Backlog 页/树节点 tooltip 有价值。
**建议**: 本期不动 domain (保持 §6.1 契约), 将 priority/description/dependency 作为
TaskDetail 可选扩展 (`priority?: string`, `description?: string`, `dependency?: string[]`)
列入 Task 005 可选增强, 不阻塞 MVP。

### 6.4 降级策略 (Task Detail)

| 场景 | 行为 |
|---|---|
| task 缺失 / 404 | Adapter 返回默认空对象 (现有); 页面显示"任务不存在或已删除" (诚实) |
| 字段缺失 | undefined / [] (现有) |
| history 空 | [] (现有) |

---

## 7. 状态映射总表 (后端值 → DomainStatus → 人话 → 色)

| 后端值 | 来源 | DomainStatus | 人话 | 色 |
|---|---|---|---|---|
| todo | Task | pending | 待办 | 灰 |
| ready | Task/Stage | pending | 待办 (就绪) | 灰 |
| in_progress | Task | running | 执行中 | 蓝 |
| running / active / started | Stage/Workflow | running | 执行中 | 蓝 |
| blocked | Task/Stage | blocked | 阻塞 | 紫 |
| review | Task | review | 待审核 | 橙 |
| **waiting_review** ⚠️ | Stage (mock 实测) | review | 等待人工 | 橙 |
| pending_approval.pending | Stage 审批门 | review | 待审核 | 橙 |
| done / completed / success / validated | Task/Stage/Artifact | completed | 完成 | 绿 |
| failed / error | Task/Stage/Workflow | failed | 失败 | 红 |
| 缺失/未知 | 任意 | pending (fallback) | 待办 | 灰 |

⚠️ 需补别名: `waiting_review → review` (现有 STATUS_ALIASES 缺失, 实测必中)。

---

## 8. 与现有 api/domain.ts 的差异清单 (需改签名/新增类型)

| # | 函数 | 现状 (S10-014 Task 007) | 差异 | 动作 |
|---|---|---|---|---|
| 1 | toTodoTree | 输入 BacklogInput{epics} + BacklogNodeInput{features/items/children 对象数组}; 读 epic.features / feature.items — **与真实结构不符, 树恒为空** | 真实 = 4 平行数组 + children id 引用; Epic/Feature/Story 无 status | **重构**: 新增 BacklogResponseInput/BacklogItemInput/BacklogTaskInput 类型; id 反向索引组装; 节点状态从子 Task 聚合; 孤儿 Epic 保留 |
| 2 | toWorkflowPipeline | 输入 WorkflowDetail + StageRunSummary[] — 形状兼容 | is_mock 未处理; waiting_review 未映射; devops 角色未映射; 英文 stage name | **增强**: 新增 WorkflowPipeline.isMock; STATUS_ALIASES 补 waiting_review; ROLE_LABELS 补 devops; name 映射优先 role_id |
| 3 | toRuntimeActivity | 输入 unknown[] 兼容 TimelineEventSummary — 形状兼容 | actor 未转人话; EVENT_ACTION_LABELS 缺 org.approval.*/org.project.*/org.artifact.failed | **增强**: actor 走 ROLE_LABELS; 补齐事件标签表; (可选) status 人话 |
| 4 | toTaskDetail | 输入 TaskDetailInput 宽松 — 兼容真实字段 | assignee='' 未归一 undefined; priority/description/dependency 未映射 | **小改**: 空串归一; (可选) 扩 domain 字段 |
| 5 | models/domain.ts | WorkflowPipeline 无 isMock | 需要 | 新增 `isMock?: boolean` |
| 6 | models/types.ts | Backlog 类型缺失 | 需要 | 新增 BacklogResponseInput 系列 (或并入 domain.ts) |
| 7 | api/client.ts | 需确认 59 路由封装覆盖 | backlog/workflow/timeline/task-detail 封装 | 确认/补封装 (Task 002) |

现有可复用资产: `STATUS_ALIASES` (补 1 键)、`ROLE_LABELS` (补 1 键)、`aggregateStatus`
(节点状态聚合)、`aggregateProgress` (均值聚合 — 需升级为优先级加权)、`fallbackRoot`/
`deriveFallbackPhases` (项目级降级树)、`toActivity` (history 投影)、`EVENT_ACTION_LABELS`
(补 8 键)、`artifactTypeLabel`。

---

## 9. 降级策略汇总

| 层 | 场景 | 降级 | 状态 |
|---|---|---|---|
| TodoTree | backlog 全空 | 项目级降级树 (lifecycle 派生 3 阶段) | ✅ 已有 |
| TodoTree | 孤儿/悬空引用 | 空阶段 / 跳过引用 | 🆕 新增 |
| TodoTree | Epic/Feature/Story 无 status | 子节点聚合 | 🆕 新增 |
| Workflow | 404/null | 未启动 + 空 stages | ✅ 已有 |
| Workflow | is_mock=true (实测必中) | 演示数据标识, 不冒充真实 | 🆕 新增 |
| Workflow | 未知 stage status | pending | ✅ 已有 |
| Runtime | 空/非数组 (实测为空) | [] + 空态 UI | ✅ 已有 |
| Runtime | 未知 event_type | message 优先, 原样兜底 | ✅ 已有 |
| TaskDetail | 404/缺失 | 空对象 + 页面提示 | ✅ 已有 |
| TaskDetail | 字段缺失 (next_action 等后端无) | undefined, 不臆造 | ✅ 已有 |

---

## 10. Task 拆分建议 (S10-015 Task 002-007 Adapter 归属)

| Task | 内容 | Adapter 归属 | 依赖 |
|---|---|---|---|
| **Task 002** | Backlog 真实接入: BacklogResponseInput 类型 + id 反向索引 + toTodoTree 重构 (children 关联/孤儿处理/子节点聚合) + client 封装 backlog/workflow/timeline/task-detail | Todo Tree (核心重构, 工作量最大) | 本 Review |
| **Task 003** | TodoTree 组件: 阶段→模块→任务树渲染 (状态色/进度条/展开折叠/状态过滤/焦点) + 优先级加权完成度聚合 + 空态 | Todo Tree UI | Task 002 |
| **Task 004** | WorkflowPipeline 组件 + toWorkflowPipeline 增强 (is_mock 降级/waiting_review/devops/role 优先名) + WorkflowPipeline.isMock | Workflow | Task 002 (client) |
| **Task 005** | Runtime Timeline 组件 + toRuntimeActivity 增强 (actor 人话/事件标签补齐) + TaskDetail 空串归一 (+ 可选 priority/description 扩展) | Runtime + Task Detail | Task 002 (client) |
| **Task 006** | TaskDetailPanel (Context Panel) 真实数据渲染 + 树节点点击联动 | Task Detail UI | Task 002/005 |
| **Task 007** | Quality Gate: vitest 全量 + 覆盖率 + pytest 后端零影响 + 真实联调浏览器验证 (含 is_mock/空 timeline/孤儿 Epic 三降级路径实测) | 全量 | 002-006 |

---

## 11. 风险与决策记录

| # | 风险/决策 | 结论 |
|---|---|---|
| 1 | 上下文数据环境与实测不符 (workflow/timeline 数据不存在) | 以实测为准; 恰好证明降级路径 (is_mock/空态) 是当前必触路径, 必须实现 |
| 2 | toTodoTree 现有实现遇真实结构恒为空树 | Task 002 必须重构输入类型与关联策略 (最高优先级) |
| 3 | 后端 mock workflow 会冒充真实进度 | is_mock 降级为硬性要求 (WorkflowPipeline.isMock) |
| 4 | Story 层折叠 vs 保留 | 保留为 task 型节点 (带子 Task), 树深仍 ≤4 |
| 5 | TaskDetail 缺 next_action/blocked_reason/started_at | 后端模型无此字段; 前端 undefined 降级, 不臆造; 待后端补字段后自动生效 |
| 6 | 完成度权重 | 叶子按 priority 加权 (P0>P1>P2>P3), 阶段/模块均值; 与 S10-013 §4.5 一致 |
| 7 | 孤儿 Epic (重复命名数据) | 如实保留空阶段; 数据治理属后端/产品后续, 前端不隐藏不合并 |

---

> 状态: Review 完成 (S10-015 Task 001) | 下一步: 按 §10 Task 002-007 实施
> 约束遵守: 未修改任何代码/后端; 唯一输出 = 本文件
