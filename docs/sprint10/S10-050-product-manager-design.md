# S10-050 — AI Product Manager Loop 设计

> 日期:2026-08-15 | Sprint: S10-050 | Phase 0 分析 + Phase 1 架构设计

---

## 1. Phase 0 — 内部分析

### 已完成能力
```
session/intent.py       IntentObject + IntentParser (create_project/run_task/show_status/list_projects)
session/conversation.py ConversationState (DISCOVERY/CLARIFICATION/CONFIRMATION/EXECUTION/DONE) + handle()
session/actions.py      create_project (薄调 org register) / list_projects / show_status / execute_task
session/router.py       IntentRouter (声明式映射)
session/audit.py        record_execution (execution_records.json)
session/confirm.py      ConfirmationGate (敏感 action 确认)
session/context.py      SessionContext (session_id/workspace/current_project/current_agent/history)
session/session.py      双入口: slash + intent→route→confirm→action
```

### 关键发现
| # | 发现 | 意义 |
|---|---|---|
| F1 | ConversationState 已有 DISCOVERY/CLARIFICATION/CONFIRMATION | 基础状态机就绪 |
| F2 | create_project action 薄调 org register | Phase 4 桥接可复用 |
| F3 | SessionContext 有 current_project | Phase 5 扩展 product_intent |
| F4 | intent "创建/做一个/开发一个" → create_project (name 参数) | 产品意图 vs 执行意图混淆 |
| F5 | 无 ProductIntent 模型 | 缺产品级资产 |
| F6 | handle() 单轮(parse→确认), 无多轮追问 | 缺澄清循环 |

### 核心缺口
```
G1: 无 ProductIntent (产品级意图模型: name/problem/user/platform/core_features)
G2: "我想做一个APP" → create_project (跳过了产品理解) — 应走 create_product
G3: 无 DISCOVERY 多轮追问 (缺什么问什么, 直到 ProductIntent 完整)
G4: 无 ProductIntent → Project 桥接 (product.json + project.json)
G5: SessionContext 无 product_intent 字段
```

### S10-050 最小实现范围
```
P0: ProductIntent 模型 (product.py)
P1: create_product intent + action (发现流程入口)
P2: Conversation DISCOVERY 多轮追问 (缺参数 → CLARIFICATION → 补齐)
P3: ProductIntent → Project 桥接 (create_project 复用, product.json 落盘)
P4: SessionContext.product_intent
```

---

## 2. Phase 1 — ProductIntent 架构设计

### 2.1 ProductIntent(产品级意图模型)

```python
@dataclass
class ProductIntent:
    name: str | None          # "ScorePocket" (缺省生成临时名)
    problem: str | None       # "台球比赛记录困难"
    user: str | None          # "台球爱好者"
    platform: str | None      # "mobile" | "web" | "desktop"
    core_features: list[str]  # ["计分", "比赛记录", "排行榜"]
    status: str = "draft"     # draft → confirmed → project_created
    raw: str = ""             # 原始输入 (审计)
    session_id: str | None = None

    REQUIRED_FIELDS = ("problem", "user", "core_features")
    def is_complete(self) -> bool: ...
    def missing_fields(self) -> list[str]: ...
    def to_dict(self) -> dict: ...
```

### 2.2 IntentObject vs ProductIntent

| 维度 | IntentObject | ProductIntent |
|---|---|---|
| 回答 | "用户想执行什么" | "用户想创造什么" |
| 触发 | run_task/create_project/show_status | create_product (Idea 级) |
| 产物 | Action 执行 | 结构化产品资产 (PRD/Architecture/Task 生成基础) |
| 生命周期 | 单次执行 | draft → confirmed → project_created |

### 2.3 产品发现流程

```
User: "我想开发一个台球计分APP"
    ↓
[1] IntentParser → create_product intent (关键词: 我想/开发/做一个 APP/产品/想法)
    ↓
[2] ConversationState → DISCOVERY
    ↓
[3] 多轮追问 (缺什么问什么):
    "这个产品解决什么问题?" (problem)
    "目标用户是谁?" (user)
    "核心功能是什么?" (core_features)
    "运行平台?" (platform) — 可选
    "产品名称?" (name) — 缺省生成临时名
    ↓
[4] ProductIntent 完整 → PRODUCT_CONFIRMATION:
    "产品: ScorePocket / 问题: ... / 用户: ... / 功能: [计分, 排名]"
    "确认创建这个产品? (y/N)"
    ↓
[5] 确认 → create_product action → Project 桥接 (create_project 复用)
    "Product Created: ScorePocket — Ready for Engineering."
```

### 2.4 Conversation 状态扩展

```python
class ConversationState(Enum):
    DISCOVERY            # 收集产品需求 (多轮追问)
    CLARIFICATION        # 澄清缺失信息 (已有)
    PRODUCT_CONFIRMATION # 确认 ProductIntent (新增)
    CONFIRMATION         # 确认执行 (已有)
    PROJECT_CREATION     # 创建项目 (新增)
    EXECUTION            # 执行 (已有)
    DONE                 # 完成 (已有)
```

### 2.5 Product Action

```python
# actions.py 新增
def create_product(context: ExecutionContext) -> ActionResult:
    """创建产品意图 → 桥接 Project (ProductIntent → create_project 复用)。
    1. 从 context.product_intent (或 intent.parameters) 构建 ProductIntent
    2. 确认后: 薄调 create_project (复用) → project.json + product.json 落盘
    3. 返回 Product Created 消息
    """

Action(
    name="create_product",
    description="创建产品 (ProductIntent → Project)",
    handler=create_product,
    permission="project",
    metadata={"sensitive": True, "category": "product"},
)
```

### 2.6 Project Bridge(产品空间)

```
projects/ScorePocket/
    product.json      # ProductIntent 落盘 (name/problem/user/platform/core_features/status)
    project.json      # org project 记录 (复用 create_project)
```

### 2.7 SessionContext 扩展

```python
# context.py
class SessionContext:
    ...
    product_intent: ProductIntent | None = None   # 当前产品意图 (Phase 5)
```

### 2.8 架构符合性

| 原则 | 符合 |
|---|---|
| 不破坏已有 Kernel | ✅ ProductIntent 是新增模型, Action 复用体系 |
| 新增能力走 Intent/Action/Service | ✅ create_product intent → action → 复用 create_project |
| 不是 Chatbot | ✅ Conversation 产出结构化 ProductIntent (产品资产) |
| 长期方向 Idea→Product→Engineering→Agent | ✅ 正是本 Sprint 目标 |

---

## 3. 文件计划

```
factory-console/session/
  product.py        (新增: ProductIntent 模型)
  intent.py         (修改: +create_product 关键词)
  actions.py        (修改: +create_product action + 桥接)
  conversation.py   (修改: DISCOVERY 多轮追问 + PRODUCT_CONFIRMATION)
  context.py        (修改: +product_intent 字段)
  router.py         (修改: create_product 映射)
  session.py        (修改: 集成 product 流程 — 最小)
tests/console/
  test_session_product.py (新增, >=40 测试)
docs/sprint10/S10-050-product-manager-loop.md (Phase 8)
```

> Phase 1 设计完毕 | ProductIntent 模型 + DISCOVERY 多轮 + 桥接 Project | 复用 create_project
