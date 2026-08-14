# S10-048 — Intent Execution Kernel 设计

> 日期:2026-08-15 | Sprint: S10-048 | Phase 0 分析 + Phase 1 架构设计

---

## 1. Phase 0 — 内部分析

### 已完成能力(S10-047)
```
session/session.py      InteractiveSession (loop/_dispatch)
session/context.py      SessionContext + ContextManager (内存)
session/slash.py        SlashCommand(ABC) + Registry (注册式)
session/commands.py     /help /status /project /cost /exit
session/intent.py       IntentObject + IntentParser(ABC) + KeywordIntentParser
session/renderer.py     Renderer(ABC) + Human/Json
session/completion.py   CompletionProvider + Slash 补全
```

### 当前缺口
| # | 缺口 | 影响 |
|---|---|---|
| G1 | **Intent 未接入 Session**: `_dispatch` 非 slash → "功能开发中" | 自然语言无法触发执行 |
| G2 | **无 Action Registry**: Intent 无法映射到能力 | 无执行入口 |
| G3 | **无 Intent Router**: type→action 无可扩展路由 | 需硬编码 |
| G4 | **无 Execution Context**: 用户/权限/审计缺失 | 无治理基础 |
| G5 | **无 Confirmation Gate**: 敏感 Action 无确认 | 无治理流程 |
| G6 | **无 Conversation 状态**: 无法多轮澄清 | 自然语言不完整 |

### S10-048 最小实现范围
```
P0: Intent Router + Action Registry + Execution Context + 3 真实 Action
P1: Session 集成 (自然语言 → Action → Service → 展示)
P2: Conversation state model (DISCOVERY/CLARIFICATION/CONFIRMATION/EXECUTION)
P3: Confirmation Gate (create_project 确认流)
```

---

## 2. Phase 1 — 架构设计

### 2.1 数据流(第一条真实执行链)

```
用户输入: "创建一个台球计分APP"
    ↓
Session._dispatch (非 slash)
    ↓
IntentParser.parse → IntentObject
    {type: "create_project", parameters: {name: "台球计分APP"}, confidence: 0.9}
    ↓
IntentRouter.route(intent) → Action 实例
    ↓
ActionRegistry.get("create_project") → CreateProjectAction
    ↓
ExecutionContext (workspace/session/permission)
    ↓
ConfirmationGate (敏感 → 用户确认)
    ↓
Action.execute(context) → 调 Service Layer (project_cmd/org)
    ↓
Renderer.render(result) → 展示
    ↓
Factory Runtime (真实执行)
```

### 2.2 Intent Object(统一结构, 复用 intent.py 扩展)

```python
@dataclass
class IntentObject:
    intent_type: str          # "create_project" | "run_task" | ...
    parameters: dict          # {"name": "台球计分APP", ...}
    confidence: float
    source: str               # "cli" | "chat" | "agent" | "api" | "session"
    raw: str                  # 原始输入
    metadata: dict            # 扩展: user_id/workspace/session_id
```

### 2.3 Action Registry(能力注册, 非 Command)

```python
@dataclass
class Action:
    name: str                 # "create_project"
    description: str
    handler: Callable[[ExecutionContext], ActionResult]
    permission: str           # "user" | "project" | "admin"
    metadata: dict

class ActionRegistry:
    def register(self, action: Action) -> None: ...
    def get(self, name: str) -> Action | None: ...
    def list(self) -> list[Action]: ...

class ExecutionContext:
    workspace: Path
    session: SessionContext
    user: str
    project: str | None
    def require(self, permission: str) -> None: ...   # 权限检查
```

### 2.4 Intent Router(可扩展, 无 if/else)

```python
class IntentRouter:
    # 注册表: intent_type → action_name (声明式映射)
    _mapping: dict[str, str] = {
        "create_project": "create_project",
        "list_projects": "list_projects",
        "show_status": "show_status",
    }
    def register_route(self, intent_type: str, action_name: str) -> None: ...
    def route(self, intent: IntentObject, registry: ActionRegistry) -> Action: ...
    # 未路由 → UnknownIntentError (明确, 不静默)
```

### 2.5 Confirmation Gate(最小治理)

```python
class ConfirmationGate:
    sensitive_actions: set[str] = {"create_project", "run_task"}
    def confirm(self, action_name: str, intent: IntentObject, context) -> bool:
        # 敏感 → 打印计划 + 请求确认 (y/N)
        # 非敏感 → 直接放行
```

### 2.6 Conversation State(基础模型)

```python
class ConversationState(Enum):
    DISCOVERY       # 收集需求
    CLARIFICATION   # 澄清缺失信息
    CONFIRMATION    # 确认执行计划
    EXECUTION       # 执行中
    DONE

class ConversationManager:
    state: ConversationState
    pending_intent: IntentObject | None
    history: list[dict]
    def transition(self, new_state) -> None: ...
    def handle(self, text) -> ConversationResponse: ...  # 基础 flow
```

### 2.7 架构符合性检查

| AI Factory 长期原则 | 符合 |
|---|---|
| CLI 不含业务逻辑 | ✅ Action 调 Service Layer (project_cmd/org), 不复制 |
| 一 CLI 两模式共享 Service | ✅ Session 内 Intent → Action → 同一 Service |
| 不制造假能力 | ✅ 3 个 Action 全部连真实 Service |
| 可扩展 | ✅ Router/Action/Conversation 全注册式 |
| 治理方向 | ✅ Confirmation Gate + ExecutionContext.permission |

---

## 3. 文件计划

```
factory-console/session/
  intent.py        (扩展: IntentObject.source/metadata; 已有 ABC 保留)
  action.py        (新增: Action + ActionRegistry + ExecutionContext + ActionResult)
  router.py        (新增: IntentRouter)
  confirm.py       (新增: ConfirmationGate)
  conversation.py  (新增: ConversationManager + ConversationState)
  session.py       (修改: _dispatch 接 intent → router → action; 集成 confirm)
tests/console/
  test_session_action.py
  test_session_router.py
  test_session_confirm.py
  test_session_conversation.py
  test_session_intent_execution.py (端到端: 自然语言 → Action → Service)
docs/sprint10/S10-048-intent-kernel.md (本设计)
```

> Phase 1 设计完毕 | 最小范围: Router + Action Registry + Context + 3 Action + Confirm + Conversation 基础
