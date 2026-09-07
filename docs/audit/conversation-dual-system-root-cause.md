# AI Factory OS — Conversation 双系统根因审计报告

**审计日期**: 2026-09-08  
**审计目的**: 查清为何存在两套并行 Conversation 系统，定位根因，给出统一架构裁决

---

## 一、执行摘要 (Executive Summary)

### 核心结论

**为什么存在两套？**

根据 git history 证据：

| 系统 | 创建 Commit | 创建日期 | 设计目标 |
|------|-------------|----------|----------|
| `session/` | 8d6ab3ac (S10-047-001) | 2026-08-15 | Interactive Session (CLI 交互式会话) |
| `conversation_os` | f231db6b (K1) | 2026-08-31 | K1 Conversation OS (用户对话驱动 OS) |

**关键发现：两套系统是并行开发 16 天后各自迭代的结果，不是迁移或重构关系。**

### 根因链

```
2026-08-15: S10-047 引入 session/ (CLI 交互式会话)
     ↓
2026-08-31: K1 引入 conversation_os (不同团队/不同设计目标)
     ↓
两者分别迭代，未整合
     ↓
API: /api/conversations/* → System A
API: /api/sessions/* → System B
     ↓
Frontend 同时调用两套系统
     ↓
用户体验：上下文不连续、自然语言行为机械、Product Pipeline 不连续
```

### 架构裁决

| 组件 | 裁决 | 理由 |
|------|------|------|
| `conversation_os` | **RETIER** | 能力残缺、无 ProductIntent、无 PRD 流程 |
| `session/` | **KEEP** | 完整 Product Pipeline、60+ Intents、ConversationManager |
| `InteractiveSession` | **REDINE** | 作为 Session 的 CLI 入口，不是独立系统 |

---

## 二、真实架构 (Actual Architecture)

### 2.1 当前系统分布

```
┌─────────────────────────────────────────────────────────────┐
│                      AI Factory OS                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   Frontend (WebUI)                    │   │
│  │  AfConversationCenter ──→ /api/conversations/*       │   │
│  │  Workspace           ──→ /api/sessions/*             │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│              ┌───────────────┼───────────────┐               │
│              ↓               ↓               ↓               │
│  ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │  /api/conversations/*  │/api/sessions/*│   CLI          │  │
│  └─────────┬────────┘ └───────┬───────┘ └────────┬────────┘  │
│            │                  │                   │           │
│            ↓                  ↓                   ↓           │
│  ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ conversation_os  │ │   session/   │ │InteractiveSession│  │
│  │    (System A)    │ │  (System B)  │ │   (CLI入口)      │  │
│  │                  │ │              │ │    → session/    │  │
│  │  505 行          │ │  6700+ 行   │ └─────────────────┘  │
│  │  9 Intents       │ │  60+ Intents │                     │
│  │  简单 State      │ │  ProductIntent│                    │
│  └──────────────────┘ └──────────────┘                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 入口矩阵

| 客户端 | 入口 | 路由文件 | 目标系统 | 代码位置 |
|--------|------|----------|----------|----------|
| WebUI | POST /api/conversations/{id}/messages | fastapi_adapter.py:6572 | conversation_os | line 6579 |
| WebUI | POST /api/sessions/{id}/messages | fastapi_adapter.py:7447 | session | line 7472 |
| CLI | `factory` (无参数) | cli_factory.py:8463 | InteractiveSession → session | line 8464 |
| CLI | `factory run/...` | cli_factory.py:8468 | FactoryCLI → conversation_os | line 4465 |
| WebUI | GET /api/conversations | fastapi_adapter.py:6584 | conversation_os | line 6590 |
| WebUI | GET /api/sessions | fastapi_adapter.py:7045 | session | line 7071 |

---

## 三、System A 完整调用链 (conversation_os)

### 3.1 入口追踪

```
HTTP POST /api/conversations/{conv_id}/messages
  ↓
fastapi_adapter.py:6572 (def api_send_message)
  ↓
line 6579: _co.send_message(root, conversation_id, message, actor)
  ↓
conversation_os.py:116 (def send_message)
```

### 3.2 完整执行链

```
User Input: "我想做一个飞机大战小游戏"
  ↓
conversation_os.send_message(root, conv_id, message, actor)
  ↓
[1] get_conversation(root, conv_id)  ← 从 entity store 读取
  ↓
[2] detect_intent(message, last_intent)  ← 简单正则匹配
    - DISCUSS (讨论)
    - DECIDE (决策)
    - APPROVE (批准)
    - EXECUTE (执行)
    - ASK_STATUS (问状态)
    - CLARIFY (澄清)
  ↓
[3] create_entity("msg")  ← 创建消息实体
  ↓
[4] State 更新
    state["goal"] = ...
    state["confirmed_decisions"] = [...]
    state["current_topic"] = ...
  ↓
[5] store_entity(conv)  ← 写回 entity store
  ↓
[6] _make_reply(root, conv, message, intent, last_intent)
    - 返回固定模板
    - 根据 intent 返回不同格式的文本
  ↓
[7] create_entity("msg")  ← 系统回复
  ↓
[8] store_entity(conv)
  ↓
[9] Return {message_id, intent, reply, conversation_version}
```

### 3.3 状态模型

```python
# conversation_os.py:84
conv["state"] = {
    "goal": "",                    # 目标 (string)
    "current_topic": "",           # 当前话题
    "confirmed_decisions": [],     # 已确认决策列表
    "pending_questions": [],       # 待解决问题
    "requirements": [],            # requirements ID 列表
    "work_items": []               # 工作项
}
```

### 3.4 问题分析

| 能力 | conversation_os | 评估 |
|------|-----------------|------|
| 接收自然语言 | ✅ REAL | 支持 |
| Conversation 创建 | ✅ REAL | entity store |
| Message | ✅ REAL | msg_ 实体 |
| Context | ❌ **DEAD** | 只有 3 个字段，无结构化 |
| Project Scope | ❌ **DEAD** | 只存 string，无绑定 |
| Intent Understanding | ⚠️ **TEMPLATE** | 6 种固定 intent |
| Product Understanding | ❌ **DEAD** | 无 ProductIntent |
| Requirement Analysis | ⚠️ **PARTIAL** | 存 ID，无分析能力 |
| PRD | ❌ **DEAD** | 只返回模板，无生成 |
| Development Plan | ❌ **DEAD** | 无 |
| Agent | ❌ **DEAD** | 不调用 agent_loop |
| Tool | ❌ **DEAD** | 无 |
| Capability | ❌ **DEAD** | 无 |
| Task | ⚠️ **PARTIAL** | trigger_work 存在但简单 |
| Node/NodeRun | ❌ **DEAD** | 无 |
| Execution | ❌ **DEAD** | 无 |
| Artifact | ❌ **DEAD** | 无 |
| Verification | ❌ **DEAD** | 无 |
| Persistence | ⚠️ **PARTIAL** | entity store |

---

## 四、System B 完整调用链 (session/)

### 4.1 入口追踪

```
HTTP POST /api/sessions/{session_id}/messages
  ↓
fastapi_adapter.py:7447 (def api_session_send)
  ↓
line 7472: _agmod = _console_import("session.agent_loop")
  ↓
session/session.py:361 (def _dispatch_inner)
  ↓
session/conversation.py:338 (class ConversationManager)
```

### 4.2 完整执行链

```
User Input: "我想做一个飞机大战小游戏"
  ↓
InteractiveSession.run() / api_session_send()
  ↓
[1] session._dispatch(line)
  ↓
[2] ConversationManager.handle(line)
    ↓
    intent = IntentParser.parse(line)  ← 60+ Intents
    ↓
    [3] 如果处于 DISCOVERY/PRODUCT_CONFIRMATION:
        → conv.handle_product_answer(line)
        → 逐轮追问: 问题→用户→目标用户→核心功能
        → ProductIntent 逐步填充
        ↓
    [4] 否则:
        → IntentRouter.route(intent)
        → Action.execute(ExecutionContext)
  ↓
[5] Action 执行 (例如 create_product)
    - 从 context 提取 ProductIntent
    - 验证必填字段 (problem/user/core_features)
    - 创建 Project + product.json
  ↓
[6] 如果 next_action == "prd":
    → generate_prd action
    → ProductDocument.from_product_intent(product)
    → PRD.md 落盘
  ↓
[7] 返回响应
```

### 4.3 状态模型

```python
# session/conversation.py
class ConversationManager:
    state: ConversationState  # DISCOVERY → CLARIFICATION → CONFIRMATION → ...
    product_intent: Optional[ProductIntent]  # 核心产品意图
    pending_intent: Optional[Intent]  # 待确认的意图
    
# session/context.py
class SessionContext:
    project_id: str
    session_id: str
    product_intent: Optional[ProductIntent]
    conversation: ConversationManager
```

### 4.4 ProductIntent 定义 (完整)

```python
# session/product.py:60
@dataclass
class ProductIntent:
    name: Optional[str]           # 产品名
    problem: Optional[str]        # 解决什么问题 (必填)
    user: Optional[str]           # 目标用户 (必填)
    platform: Optional[str]       # 运行平台
    core_features: list[str]      # 核心功能列表 (必填)
    status: str = "draft"         # lifecycle: draft → confirmed → project_created
    raw: str = ""                 # 原始输入
    session_id: Optional[str]     # 来源会话
```

### 4.5 问题分析

| 能力 | session/ | 评估 |
|------|----------|------|
| 接收自然语言 | ✅ REAL | 支持 |
| Conversation 创建 | ✅ REAL | Session + ConversationManager |
| Message | ✅ REAL | msg 实体 |
| Context | ✅ REAL | 完整 ConversationManager |
| Project Scope | ✅ REAL | session.context.project_id |
| Intent Understanding | ✅ REAL | 60+ Intents + LLM |
| Product Understanding | ✅ REAL | ProductIntent 完整模型 |
| Requirement Analysis | ✅ REAL | DISCOVERY 状态多轮 |
| PRD | ✅ REAL | generate_prd → PRD.md |
| Development Plan | ✅ REAL | actions.py create_plan |
| Agent | ✅ REAL | agent_loop |
| Tool | ✅ REAL | Tool Registry |
| Capability | ✅ REAL | Capability Router |
| Task/Node/NodeRun | ✅ REAL | Node Runtime |
| Execution | ✅ REAL | Production Runtime |
| Artifact | ✅ REAL | Artifact Lifecycle |
| Verification | ✅ REAL | Verification Domain |
| Persistence | ✅ REAL | project.json / PRD.md |

---

## 五、历史时间线 (Historical Timeline)

### 5.1 系统创建

```
2026-08-15  S10-047-001 (commit 8d6ab3ac)
    引入: factory-console/session/
    目标: Interactive Session (CLI 交互式会话)
    初始文件:
      - session/__init__.py (15 行)
      - session/session.py (75 行)
    
2026-08-31  K1 (commit f231db6b)
    引入: factory-console/conversation_os.py
    目标: K1 Conversation OS (用户对话驱动 OS)
    初始能力:
      - 6 种 Intent (DISCUSS/DECIDE/APPROVE/EXECUTE/ASK_STATUS/CLARIFY)
      - 简单 State (goal/decisions/topic)
      - entity store 持久化
```

### 5.2 并行开发证据

```bash
# 两者创建时间差仅 16 天
git log --oneline --follow --diff_filter=A -- factory-console/conversation_os.py
# f231db6b feat: K1 Conversation OS Reality  (2026-08-31)

git log --oneline --follow --diff_filter=A -- factory-console/session/__init__.py
# 8d6ab3ac S10-047-001 interactive session  (2026-08-15)
```

### 5.3 后续演进

| 时间 | System A (conversation_os) | System B (session/) |
|------|---------------------------|---------------------|
| 2026-08-31 | K1 发布 | S10-047 开发中 |
| 2026-09-01 | 消息卡片功能 | Agent Loop 集成 |
| 2026-09-06 | Kernel Inversion 修改 | Product Pipeline 完善 |
| 2026-09-08 | 触发 Production Runtime | 60+ Intents + Actions |

**结论：两套系统从创建之初就是独立并行开发，从未整合。**

---

## 六、职责矩阵 (Responsibility Matrix)

| 能力 | conversation_os | session/ | 差异原因 |
|------|-----------------|----------|----------|
| 接收自然语言 | ✅ REAL | ✅ REAL | 共同需求 |
| Conversation 创建 | ✅ REAL | ✅ REAL | 共同需求 |
| Context 完整性 | ❌ DEAD (3 字段) | ✅ REAL (完整) | 设计差异 |
| Project Scope | ❌ DEAD | ✅ REAL | 设计差异 |
| Intent 检测 | 6 种 | 60+ 种 | 复杂度差异 |
| ProductIntent | ❌ DEAD | ✅ REAL | **核心差异** |
| Requirement 多轮 | ❌ DEAD | ✅ REAL | **核心差异** |
| PRD 生成 | ❌ DEAD (模板) | ✅ REAL | **核心差异** |
| Plan 生成 | ❌ DEAD | ✅ REAL | **核心差异** |
| Agent 调用 | ❌ DEAD | ✅ REAL | Runtime 差异 |
| Node Runtime | ❌ DEAD | ✅ DELEGATED | Runtime 差异 |
| Verification | ❌ DEAD | ✅ REAL | 完整性差异 |

---

## 七、State/Context 对比 (State Comparison)

### 7.1 conversation_os 的 State Source

| 状态项 | 存储位置 | 类型 | Authority |
|--------|----------|------|-----------|
| Conversation | entity store: conv-{id}.json | JSON | ✅ Valid |
| Messages | conv["messages"] | list | ✅ Valid |
| State | conv["state"] | dict (3 字段) | ⚠️ PARTIAL |
| Project | 无 | N/A | ❌ DEAD |
| Product | 无 | N/A | ❌ DEAD |
| PRD | 无 | N/A | ❌ DEAD |

### 7.2 session/ 的 State Source

| 状态项 | 存储位置 | 类型 | Authority |
|--------|----------|------|-----------|
| Session | SessionStore | Object | ✅ Valid |
| Conversation | ConversationManager.state | Enum | ✅ Valid |
| Messages | session.messages | list | ✅ Valid |
| ProductIntent | ConversationManager.product_intent | DataClass | ✅ Valid |
| Project | project.json | JSON | ✅ Valid |
| PRD | projects/{slug}/PRD.md | File | ✅ Valid |

### 7.3 关键问题：Context 连续性

**问题 A**: 用户第 2 句话时，System A 从哪里获得第 1 句话的信息？

```python
# conversation_os.py:124-127
state = conv.get("state", {})  # 从 conv JSON 读取
goal = state.get("goal", "")    # 只是 string
# 第二句话只能读到这些简单字段
```

**问题 B**: 用户第 2 句话时，System B 从哪里获得第 1 句话的信息？

```python
# session/conversation.py:361-428
# ConversationManager 持有完整 ProductIntent
self.product_intent: Optional[ProductIntent] = None
# 逐轮填充: problem → user → core_features → platform
```

**结论**:
- System A: Context 严重不完整，只有 3 个字段
- System B: Context 完整，有 ProductIntent 包含所有产品信息

---

## 八、Product Intelligence 对比

### 8.1 Idea 存在哪里？

| 系统 | Idea 存储 | 评估 |
|------|-----------|------|
| conversation_os | `state["goal"]` (string) | ❌ 只是目标描述，无结构 |
| session/ | `ProductIntent` (完整 dataclass) | ✅ 包含 name/problem/user/platform/core_features |

### 8.2 Requirement 分析

| 系统 | 能力 | 实现 |
|------|------|------|
| conversation_os | ❌ DEAD | 无对应功能 |
| session/ | ✅ REAL | ConversationManager.DISCOVERY 状态多轮追问 |

### 8.3 PRD 生成

| 系统 | PRD 生成 | 入口 |
|------|----------|------|
| conversation_os | ❌ DEAD | 无，只有模板 |
| session/ | ✅ REAL | `generate_prd` action → PRD.md |

| 系统 | PRD 来源 | 实现 |
|------|----------|------|
| conversation_os | N/A | 模板 |
| session/ | ProductIntent | `ProductDocument.from_product_intent(product)` |

### 8.4 Development Plan

| 系统 | Plan 生成 | 实现 |
|------|-----------|------|
| conversation_os | ❌ DEAD | 无 |
| session/ | ✅ REAL | `create_plan` action → engineering.json |

**结论**: System A **完全没有** Product Intelligence Pipeline，System B 有完整链路。

---

## 九、CLI/API/WebUI 路由分析

### 9.1 CLI 路由

| 命令 | 入口 | 最终系统 |
|------|------|----------|
| `factory` (无参数) | cli_factory.py:8463 | InteractiveSession → session |
| `factory --interactive` | cli_factory.py:8463 | InteractiveSession → session |
| `factory run ...` | cli_factory.py:8468 | conversation_os (部分子命令) |
| `factory init ...` | cli_factory.py:8468 | conversation_os |

**关键发现**: CLI 交互模式走 System B，但其他子命令可能调用 System A。

### 9.2 API 路由

| 端点 | Handler | 目标系统 |
|------|---------|----------|
| POST /api/conversations | api_create_conversation | conversation_os |
| POST /api/conversations/{id}/messages | api_send_message | conversation_os |
| GET /api/conversations | api_conversations | conversation_os |
| POST /api/sessions | api_create_session | session |
| POST /api/sessions/{id}/messages | api_session_send | session |

### 9.3 Frontend 路由

| 前端组件 | API 调用 | 目标系统 |
|----------|----------|----------|
| ConversationPage | /api/conversations/* | conversation_os |
| AfConversationCenter | /api/conversations/{id}/messages | conversation_os |
| Workspace (AfWorkspaceShell) | /api/sessions/* | session |

**关键发现**: Frontend 同时使用两套系统！这是用户体验不一致的根源。

---

## 十、Root Cause Chain (根因链)

### 10.1 架构分叉点

```
                    ┌─────────────────────────────────────────┐
                    │         2026-08-15                      │
                    │    S10-047 Interactive Session          │
                    │      session/ 创建                       │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         2026-08-31                      │
                    │    K1 Conversation OS                   │
                    │  conversation_os 创建                   │
                    │  (与 session/ 并行, 无整合)              │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         后续迭代                        │
                    │  System A: 505 行, 6 intents            │
                    │  System B: 6700+ 行, 60+ intents        │
                    │  从未整合, 各自迭代                      │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         Frontend 同时调用两套            │
                    │  /api/conversations/* → System A        │
                    │  /api/sessions/* → System B             │
                    └─────────────────┬───────────────────────┘
                                      │
                    ┌─────────────────▼───────────────────────┐
                    │         用户体验问题                     │
                    │  1. 上下文不连续 (System A 只有 3 字段)  │
                    │  2. 回答机械 (System A 是模板)           │
                    │  3. Product Pipeline 不可用 (System A)   │
                    │  4. PRD/Plan 不连续 (System A 无)        │
                    └─────────────────────────────────────────┘
```

### 10.2 具体根因列表

| # | 根因 | 证据 | 影响 |
|---|------|------|------|
| 1 | 两套系统并行开发，未整合 | git history: 16 天间隔分别创建 | P0 |
| 2 | System A 缺乏 ProductIntent | 代码: 无 ProductIntent 定义 | P0 |
| 3 | System A Context 不完整 | 代码: 只有 3 字段 (goal/decisions/topic) | P0 |
| 4 | System A 无 PRD/Plan 生成 | 代码: 无对应 action | P0 |
| 5 | Frontend 同时调用两套系统 | api/client.ts: 同时调用两个 API | P0 |
| 6 | API 入口设计分裂 | fastapi_adapter.py: 两套独立路由 | P1 |
| 7 | session/ 定义为 "Runtime" 而非 "Conversation OS" | session/__init__.py: "Workforce Terminal 交互" | P2 |

---

## 十一、隐藏第三系统检查

### 11.1 检查结果

搜索关键词: `conversation`, `session`, `chat`, `dialog`, `interaction`

**发现的系统**:

| 系统 | 位置 | 说明 |
|------|------|------|
| conversation_os | factory-console/conversation_os.py | System A |
| session/ | factory-console/session/ | System B |
| InteractiveSession | factory-console/session/session.py:115 | System B 的 CLI 入口 |

**结论**: 不存在第三套独立的 Conversation Runtime。InteractiveSession 是 session 的 CLI 前端，不是独立系统。

---

## 十二、架构裁决 (Architectural Verdict)

### 12.1 System A (conversation_os)

| 评估维度 | 得分 | 说明 |
|----------|------|------|
| Architecture fit | ❌ | 能力残缺 |
| Context continuity | ❌ | 只有 3 字段 |
| Product Intelligence | ❌ | 无 |
| Persistence | ⚠️ | 部分 |
| Extensibility | ❌ | 难以扩展 |
| API consistency | ❌ | 与 System B 不一致 |
| CLI consistency | ⚠️ | 部分命令 |
| WebUI consistency | ❌ | 不完整 |
| Real production path | ❌ | 不是真正生产路径 |

**裁决**: **RETIER**

**理由**:
1. Context 只有 3 个字段，用户信息严重丢失
2. 无 ProductIntent，无法进行产品定义
3. 无 PRD/Plan 生成能力
4. 不是真正生产路径
5. 应该被 session/ 替代

### 12.2 System B (session/)

| 评估维度 | 得分 | 说明 |
|----------|------|------|
| Architecture fit | ✅ | 完整 Conversation OS |
| Context continuity | ✅ | ProductIntent 完整 |
| Product Intelligence | ✅ | 完整 Pipeline |
| Persistence | ✅ | 项目级持久化 |
| Extensibility | ✅ | Action/Intent 可扩展 |
| API consistency | ✅ | 完整 REST API |
| CLI consistency | ✅ | InteractiveSession |
| WebUI consistency | ⚠️ | 部分组件使用 |
| Real production path | ✅ | Node Runtime 集成 |

**裁决**: **KEEP**

**理由**:
1. 有完整 ProductIntent 模型
2. 有完整 Requirement 分析流程
3. 有 PRD/Plan 生成能力
4. 有 60+ Intents，能力完整
5. 是真正的生产路径

### 12.3 InteractiveSession

| 评估维度 | 得分 | 说明 |
|----------|------|------|
| Architecture fit | ✅ | 作为 session CLI 入口 |
| Context continuity | ✅ | 复用 session |
| Product Intelligence | ✅ | 同 session |

**裁决**: **REFINE** (重新定义边界)

**理由**:
1. InteractiveSession 是 session 的 CLI 入口，不是独立系统
2. 应该明确定义为 "Session Runtime CLI Interface"
3. 不应与 "Conversation OS" 混淆

---

## 十三、目标架构 (Desired Architecture)

### 13.1 统一后的架构

```
                    ┌────────────────────────────────────────┐
                    │           AI Factory OS                 │
                    │                                        │
                    │         Conversation OS                 │
                    │    (Product Understanding + Context)    │
                    └──────────────────┬─────────────────────┘
                                       │
           ┌───────────────────────────┼───────────────────────────┐
           │                           │                           │
           ↓                           ↓                           ↓
    ┌─────────────┐            ┌─────────────┐            ┌─────────────┐
    │    CLI      │            │    API      │            │   WebUI     │
    │Interactive  │            │ /api/co...  │            │Workspace    │
    │  Session    │            │             │            │             │
    └──────┬──────┘            └──────┬──────┘            └──────┬──────┘
           │                          │                          │
           └──────────────────────────┼──────────────────────────┘
                                      ↓
                            ┌─────────────────┐
                            │  Session/Life   │
                            │    Cycle        │
                            └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │ Product Intent  │
                            │    Context      │
                            └────────┬────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          ↓                          ↓                          ↓
   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
   │    Idea     │          │  Require-   │          │     PRD     │
   │             │ ──────→  │    ment     │ ──────→  │             │
   └─────────────┘          └─────────────┘          └──────┬──────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │  Development    │
                                                    │     Plan        │
                                                    └────────┬────────┘
                                                             │
                                                    ┌────────▼────────┐
                                                    │ Production      │
                                                    │   Runtime       │
                                                    └─────────────────┘
```

### 13.2 统一原则

> **One OS, One Conversation Runtime, Multiple Clients**

```text
WebUI ─┐
CLI   ─┼──→ Unified Conversation API/Runtime (session/)
API   ─┘
```

### 13.3 概念澄清

| 概念 | 定义 | 持久化 |
|------|------|--------|
| **Conversation** | 用户的长期工作/认知空间 | 可选，用于多 Session 聚合 |
| **Session** | 一次技术交互/连接/生命周期 | 每次 CLI/API 连接 |
| **ProductIntent** | 结构化的产品理解 | projects/{slug}/product.json |
| **PRD** | 产品需求文档 | projects/{slug}/PRD.md |
| **Plan** | 开发计划 | projects/{slug}/engineering.json |

**注意**: 原 conversation_os 中的 "Conversation" 概念应重新定义为 "Session"，与 session/ 统一。

---

## 十四、修复建议 (但本次不执行)

如果用户决定修复，建议顺序：

1. **P0**: 统一 API 入口 - 将 `/api/conversations/*` 重定向到 `/api/sessions/*`
2. **P0**: Frontend 整合 - 移除对 `/api/conversations/*` 的调用，全部走 session
3. **P1**: 统一 CLI - 移除 conversation_os 调用，全部走 InteractiveSession
4. **P2**: 代码清理 - 删除 conversation_os 或标记为 deprecated
5. **P2**: 文档更新 - 更新设计文档反映统一架构

---

## 十五、结论

### 回答用户的 10 个问题

1. **为什么用户自然语言不能连续表达 Idea？**
   → System A (conversation_os) 只有 3 个 State 字段，无法累积产品理解

2. **为什么第二句话经常不能正确继承第一句话？**
   → System A 没有 ProductIntent，只有简单 goal string

3. **为什么系统会机械地进入固定阶段？**
   → 只有 System B 有真正阶段 (DISCOVERY → CONFIRMATION)，System A 过于简单

4. **为什么 AI 有时候会错误理解用户意图？**
   → System A 只有 6 种 Intent，System B 有 60+

5. **为什么 Requirement → PRD → Plan 之间可能出现语义断裂？**
   → System A 完全不支持这条链路，System B 支持但可能需要增强

6. **当前真正的 Product Source of Truth 是什么？**
   → System B: `projects/{slug}/product.json` + ConversationManager.product_intent

7. **当前真正的 Conversation Source of Truth 是什么？**
   → System B: ConversationManager
   → System A: entity store (能力不足)

8. **当前真正的 Project Scope Source of Truth 是什么？**
   → `projects/{slug}/project.json`

9. **到底有多少套旧逻辑仍然参与生产路径？**
   → 主要 2 套 (conversation_os + session/)
   → conversation_os 是旧逻辑，应该退役

10. **最少需要改变什么让 Idea → PRD → Plan 真正工作？**
    → 统一入口：所有请求走 session/
    → Frontend 整合：移除 conversation_os 调用
    → 保留 session/ 作为唯一 Conversation Runtime

---

## 十五、目标领域模型 (Target Domain Model)

### 15.1 核心发现：当前架构问题

经过前三阶段审计，发现的核心问题：

| 问题 | 表现 |
|------|------|
| Intent 固定化 | conversation_os 只有 6 种 Intent，无法覆盖自然语言 |
| Requirement 固定流程 | session/ 强制按 problem→user→core_features 顺序询问 |
| Product State 分裂 | conversation_os 无 ProductIntent，session/ 有但只存在于内存 |
| State 与 Runtime 混淆 | Session 同时承担业务状态和运行时生命周期 |
| 缺少 Product Understanding 层 | 只有 Entity (conv_) 和 Action (generate_prd)，缺少结构化理解 |

---

## 十六、Conversation 模型 (Conversation Model)

### 16.1 Conversation 是什么？

**定义：Conversation 是用户与 AI 之间的持续工作空间，是产品认知的业务边界。**

Current 问题：
- conversation_os: Conversation = Entity (conv_ 前缀)
- session/: Conversation = 内存状态机

**正确模型应该是：**

```
Conversation (业务边界)
├── id: UUID (全局唯一)
├── project_id: 关联的 Project
├── created_at / updated_at
├── messages: List[Message]
├── productUnderstanding: ProductUnderstanding
│   ├── ideas: List[Idea]
│   ├── requirements: List[Requirement]
│   ├── decisions: List[Decision]
│   ├── constraints: List[Constraint]
│   ├── questions: List[OpenQuestion]
│   ├── preferences: List[Preference]
│   └── status: understanding | confirmed | production
├── context: ConversationContext
├── metadata: Dict
└── lifecycle: CREATING | ACTIVE | SUSPENDED | CLOSED
```

### 16.2 Conversation 的核心职责

| 职责 | 说明 |
|------|------|
| 持有 Product Understanding | 用户想做什么的事实来源 |
| 管理 Messages | 原始输入事件 |
| 追踪 Open Questions | 还有哪些问题未解决 |
| 持有 Decisions | 用户确认的决策 |
| 引用 Artifacts | PRD/Plan/Evidence 等 |
| 提供 Conversation Scope | 确保跨 Session 的上下文连续性 |

---

## 十七、Session 模型 (Session Model)

### 17.1 Session 是什么？

**定义：Session 是用户与系统之间的一次具体交互的生命周期管理。**

Current 问题：
- session/ 把业务状态放在 Session (product_intent 在内存)
- Session 不应该拥有 Product Truth

**正确模型应该是：**

```
Session (Runtime 生命周期)
├── id: UUID
├── conversation_id: 关联的 Conversation
├── created_at / last_active / ended_at
├── connection: ConnectionState
├── runtime_context: RuntimeContext
│   ├── model: LLM model
│   ├── temperature: float
│   ├── max_tokens: int
│   └── checkpoint: Optional[Checkpoint]
├── streaming_state: StreamingState
├── execution_context: ExecutionContext
└── lifecycle: CONNECTING | ACTIVE | IDLE | DISCONNECTED | ERROR
```

### 17.2 Session 的核心职责

| 职责 | 说明 |
|------|------|
| 管理 LLM 连接 | 请求/响应/流式 |
| 处理 Request Lifecycle | 启动/暂停/恢复/终止 |
| 保存 Checkpoint | 允许恢复 |
| 管理 Runtime 状态 | 当前执行的 Node/Action |
| 临时缓存 | 不需要持久化的运行时数据 |

### 17.3 Session 不应该拥有

| 状态 | 应该归属 |
|------|----------|
| Product Intent | Conversation |
| Requirements | Conversation |
| Decisions | Conversation |
| PRD | Artifact (由 Conversation 引用) |
| Project Scope | Project |

---

## 十八、Product Understanding 模型 (Product Understanding Model)

### 18.1 Product Understanding 是什么？

**定义：Product Understanding 是用户产品定义的结构化表达，是Conversation 的核心状态。**

Current 问题：
- conversation_os: 只有 goal string
- session/ 有 ProductIntent 但只是简单 dataclass，不完整

**正确模型应该是：**

```
ProductUnderstanding
├── id: UUID
├── conversation_id: FK
├── status: DRAFT | IN_PROGRESS | CONFIRMED | PRODUCTION | ARCHIVED
│
├── ideas: List[Idea]
│   ├── id: UUID
│   ├── content: str (原始用户输入)
│   ├── source: Message (来源消息)
│   ├── confidence: float (AI 置信度 0-1)
│   ├── confirmed: bool (是否用户确认)
│   ├── created_at: datetime
│   └── metadata: Dict
│
├── requirements: List[Requirement]
│   ├── id: UUID
│   ├── content: str
│   ├── source_idea_id: UUID (来自哪个 Idea)
│   ├── type: FUNCTIONAL | NON_FUNCTIONAL | CONSTRAINT | PREFERENCE
│   ├── priority: CRITICAL | HIGH | MEDIUM | LOW
│   ├── status: DRAFT | CONFIRMED | IMPLEMENTED | REJECTED
│   ├── confirmed_by_user: bool
│   ├── confirmed_at: Optional[datetime]
│   └── metadata: Dict
│
├── decisions: List[Decision]
│   ├── id: UUID
│   ├── statement: str (用户原话)
│   ├── interpretation: str (AI 理解)
│   ├── confirmed: bool
│   ├── confirmed_at: datetime
│   ├── affects: List[str] (影响的 requirements/ideas)
│   └── rationale: Optional[str]
│
├── constraints: List[Constraint]
│   ├── id: UUID
│   ├── content: str
│   ├── type: PLATFORM | TECHNICAL | BUSINESS | LEGAL
│   ├── confirmed: bool
│   └── source: Message
│
├── questions: List[OpenQuestion]
│   ├── id: UUID
│   ├── content: str
│   ├── context: str (为什么问这个问题)
│   ├── answer: Optional[str]
│   ├── answered_at: Optional[datetime]
│   └── priority: float
│
├── preferences: List[Preference]
│   ├── content: str
│   ├── type: UI | UX | PERFORMANCE | COST
│   └── confirmed: bool
│
├── assumptions: List[Assumption]
│   ├── content: str
│   ├── confidence: float
│   └── validated: Optional[bool]
│
├── risks: List[Risk]
│   ├── description: str
│   ├── likelihood: LOW | MEDIUM | HIGH
│   └── mitigation: Optional[str]
│
├── future_ideas: List[FutureIdea]
│   ├── content: str
│   ├── mentioned_at: Message
│   ├── priority: Optional[float]
│   └── backlog_status: BACKLOG | CONSIDERED | REJECTED
│
└── platform: Optional[str]
    user: Optional[str]
    name: Optional[str]
    core_features: List[str]
```

### 18.2 关键区别：Confirmed vs Inferred

| 类型 | 确认方式 | 优先级 |
|------|----------|--------|
| 用户明确说的 | 直接记录 | 高 |
| 用户说"对/是的/同意" | 确认现有推断 | 高 |
| AI 从上下文推断 | 需要后续确认 | 低 |
| AI 从模式识别 | 需要后续确认 | 低 |

---

## 十九、Requirement Analysis 模型 (Requirement Analysis Model)

### 19.1 当前问题

Current Implementation:
- session/ 的 Requirement Analysis 是固定问卷
- `_PRODUCT_FIELD_ORDER = ("problem", "user", "core_features")`
- 强制按顺序询问

**这与自然语言交互目标冲突！**

### 19.2 正确模型应该是：Adaptive Clarification Process

```
RequirementAnalysis (自适应澄清过程)
│
├── understanding: ProductUnderstanding
│
├── questions: List[PendingQuestion]
│   ├── id: UUID
│   ├── text: str
│   ├── reason: str (为什么问这个问题)
│   ├── importance: float
│   ├── context: Dict (当前理解状态)
│   └── answered: bool
│
├── sufficiency_checker: SufficiencyChecker
│   ├── required_dimensions: Set[str]
│   ├── current_dimensions: Set[str]
│   └── missing_dimensions: Set[str]
│
└── strategy: ClarificationStrategy
    ├── missing_info: Set[str]
    ├── uncertainty_dimensions: Dict[str, float]
    └── next_question_selection: QuestionSelector
```

### 19.3 Sufficiency Criteria

系统需要判断"信息是否足够"，而不是盲目问完所有问题。

```
Sufficient When:
├── problem: 明确
├── user: 明确
├── core_features: 至少 1 个
└── Platform: 可选 (有默认值)
```

### 19.4 不应该要求

- 不要求固定的字段顺序
- 不要求问完所有字段才开始
- 不要求用户严格按照 Idea→Requirement→PRD 流程
- 可以从任何维度开始理解
- 可以随时补充信息

---

## 二十、PRD 模型 (PRD Model)

### 20.1 当前问题

- session/ 有 generate_prd action
- conversation_os 只有模板

### 20.2 正确模型

```
PRD (Product Understanding 的 Formalized Artifact)
│
├── id: UUID
├── slug: str
├── project_id: FK
├── conversation_id: FK
│
├── product_understanding_id: FK
│   (PRD 从 Product Understanding 派生，非独立实体)
│
├── version: str (semver)
├── status: DRAFT | REVIEW | APPROVED | PUBLISHED | ARCHIVED
│
├── content: PRDContent
│   ├── overview: OverviewSection
│   │   ├── name: str
│   │   ├── problem: str
│   │   ├── target_users: str
│   │   └── value_proposition: str
│   │
│   ├── functional_requirements: List[FR]
│   │   ├── id
│   │   ├── title
│   │   ├── description
│   │   ├── priority
│   │   └── source_requirement_id
│   │
│   ├── non_functional_requirements: List[NFR]
│   ├── constraints: List[str]
│   ├── user_stories: List[UserStory]
│   ├── acceptance_criteria: Dict[str, List[str]]
│   └── future_considerations: List[str]
│
├── lineage: Lineage
│   ├── derived_from_understanding_id: UUID
│   ├── derived_at: datetime
│   ├── derived_by: str (LLM/规则/人类)
│   ├── source_decisions: List[UUID]
│   └── source_requirements: List[UUID]
│
├── metadata: PRDMetadata
│   ├── complexity: SIMPLE | MEDIUM | COMPLEX
│   ├── generated_at: datetime
│   ├── generated_by: str
│   └── last_modified: datetime
│
└── artifacts: List[Artifact]
    (PRD 可能引用的其他 Artifact)
```

### 20.3 关键点

| 原则 | 说明 |
|------|------|
| PRD 不是 Conversation 的替代品 | PRD 是 Product Understanding 的 formal view |
| PRD 从 Product Understanding 派生 | 不是独立创建，而是转换 |
| PRD 应该可版本化 | 用户可以要求"简单版"、"详细版" |
| PRD 应该可追溯 | 每个 section 应该能追溯到 requirement/decision |

---

## 二十一、Development Plan 模型 (Development Plan Model)

### 21.1 正确模型

```
DevelopmentPlan
│
├── id: UUID
├── slug: str
├── project_id: FK
├── prd_id: FK
├── conversation_id: FK
│
├── version: str
├── status: DRAFT | REVIEW | APPROVED | IN_PROGRESS | COMPLETED
│
├── content: PlanContent
│   ├── phases: List[Phase]
│   │   ├── name: str
│   │   ├── description: str
│   │   ├── start_date: Optional[date]
│   │   ├── duration_days: int
│   │   ├── deliverables: List[str]
│   │   └── tasks: List[TaskReference]
│   │
│   ├── tasks: List[Task]
│   │   ├── id: UUID
│   │   ├── title: str
│   │   ├── description: str
│   │   ├── assignee: Optional[AgentSpec]
│   │   ├── dependencies: List[UUID]
│   │   ├── priority: int
│   │   ├── estimated_hours: float
│   │   └── acceptance_criteria: List[str]
│   │
│   ├── resources: ResourcePlan
│   ├── risks: List[RiskMitigation]
│   └── milestones: List[Milestone]
│
└── lineage: Lineage
    ├── derived_from_prd_id: UUID
    ├── derived_from_decisions: List[UUID]
    └── generated_at: datetime
```

### 21.2 触发时机

用户说：
- "就按这个做"
- "开始开发"
- "生成计划"
- "开始吧"

系统才应该从 Product Understanding + PRD 生成 Development Plan。

---

## 二十二、Project 模型 (Project Model)

### 22.1 定义

```
Project
│
├── id: UUID
├── slug: str (URL-safe)
├── name: str
├── description: Optional[str]
│
├── conversation_id: FK (可选，关联的业务 Conversation)
├── product_understanding_id: FK (可选)
├── prd_id: FK (可选)
├── development_plan_id: FK (可选)
│
├── workspace: Workspace
│   ├── path: Path
│   ├── repo_url: Optional[str]
│   └── environments: List[Environment]
│
├── governance: Governance
│   ├── risk_level: LOW | MEDIUM | HIGH | CRITICAL
│   ├── approvals_required: List[ApprovalType]
│   └── compliance: List[str]
│
├── lifecycle: CONCEPT | PLANNING | DEVELOPMENT | VALIDATION | PRODUCTION | ARCHIVED
│
├── created_at / updated_at / created_by
└── metadata: Dict
```

### 22.2 Project vs Product vs Conversation

| 概念 | 定义 | 持久化 |
|------|------|--------|
| Project | 用户工作的容器/软件项目 | 长期 |
| Product | 用户想创造的东西 (通过 Product Understanding 表达) | 长期 |
| Conversation | 用户与 AI 的交互会话 | 可以很长 |
| Session | 一次运行时交互 | 短期 |

---

## 二十三、Production Runtime 边界 (Production Runtime Boundary)

### 23.1 核心原则

**Production Runtime 不负责"用户到底想做什么"，只负责"如何可靠生产"。**

```
User Intent / "What"
         │
         ▼
    Conversation
         │
         ▼
  Product Understanding
         │
         ▼
   Confirmed Definition (PRD)
         │
         ▼
    Development Plan
         │
         ▼
  ┌───────────────────────────────────────────────┐
  │         Production Runtime                    │
  │  (只负责 How，不负责 What)                     │
  │                                               │
  │  - Task Decomposition                         │
  │  - Node Creation                              │
  │  - NodeRun Execution                          │
  │  - Artifact Generation                        │
  │  - Verification                               │
  │  - Evidence Collection                        │
  │  - Recovery / Retry                           │
  │  - Learning                                   │
  └───────────────────────────────────────────────┘
```

### 23.2 Production Runtime 职责

| 职责 | 说明 |
|------|------|
| Task Decomposition | 把 Plan 分解为 Task |
| Node Creation | 创建执行节点 |
| NodeRun Execution | 运行节点 |
| Artifact Generation | 生成产物 |
| Verification | 验证结果 |
| Evidence Collection | 收集证据 |
| Recovery | 失败恢复 |

### 23.3 Production Runtime 不负责

| 排除项 | 说明 |
|--------|------|
| Product Understanding | Conversation 负责 |
| Requirement Analysis | Conversation 负责 |
| PRD Generation | Domain Service 负责 |
| Plan Generation | Domain Service 负责 |
| User Intent Interpretation | Conversation 负责 |

---

## 二十四、State Ownership Matrix (状态所有权矩阵)

### 24.1 当前问题

| 状态 | conversation_os | session/ | 问题 |
|------|-----------------|----------|------|
| Conversation | Entity (conv_) | 内存 | 分裂 |
| Messages | msg_ Entity | 内存 | 分裂 |
| ProductIntent | ❌ | 内存 | 不持久化 |
| Requirements | Entity (req_) | 内存 | 分裂 |
| Decisions | Entity (decision_) | 内存 | 分裂 |
| PRD | ❌ | Action 输出 | 无统一 |
| Plan | ❌ | Action 输出 | 无统一 |

### 24.2 正确所有权

| State | Owner | SSOT | Persistence | API Access |
|-------|-------|------|-------------|------------|
| Conversation | ConversationManager | ✅ | Project storage | /api/conversations |
| ProductUnderstanding | Conversation | ✅ | Project storage | Via Conversation |
| Messages | Conversation | ✅ | Project storage | /api/conversations/{id}/messages |
| Requirements | ProductUnderstanding | ✅ | Project storage | Via Conversation |
| Decisions | ProductUnderstanding | ✅ | Project storage | Via Conversation |
| PRD | Artifact | ✅ | File storage | /api/artifacts |
| Plan | Artifact | ✅ | File storage | /api/artifacts |
| Session | SessionManager | ❌ | Memory | /api/sessions/{id} |
| RuntimeState | ProductionRuntime | ❌ | Memory | /api/runs |

---

## 二十五、API Boundary (API 边界)

### 25.1 当前问题

- `/api/conversations/*` → conversation_os
- `/api/sessions/*` → session/

两个独立的 Runtime API。

### 25.2 正确 API 层次

```
/api
├── /projects
│   └── CRUD Project
│
├── /conversations          ← Primary Business API
│   ├── GET/POST /conversations
│   ├── GET/PATCH /conversations/{id}
│   ├── GET/POST /conversations/{id}/messages
│   ├── GET /conversations/{id}/understanding    ← Product Understanding
│   ├── GET /conversations/{id}/requirements
│   ├── GET /conversations/{id}/decisions
│   ├── POST /conversations/{id}/confirm         ← Confirm understanding
│   └── POST /conversations/{id}/generate-prd    ← Generate PRD
│
├── /sessions               ← Runtime Lifecycle API
│   ├── POST /sessions (create conversation session)
│   ├── GET/POST /sessions/{id}/messages
│   ├── GET /sessions/{id}/state
│   ├── POST /sessions/{id}/checkpoint
│   └── POST /sessions/{id}/resume
│
├── /arts
│   ├── /prds
│   ├── /plans
│   └── /artifacts
│
├── /runtime
│   ├── /runs
│   ├── /tasks
│   └── /nodes
│
└── /governance
    ├── /approvals
    └── /policies
```

### 25.3 关键点

- Conversation 是业务核心入口
- Session 是 Conversation 的 Runtime 实例
- Artifacts (PRD/Plan) 通过 Conversation 引用

---

## 二十六、CLI/WebUI Boundary (CLI/WebUI 边界)

### 26.1 正确架构

```
CLI / WebUI ──────→ Unified Conversation API ────→ Conversation Domain
       │                                           │
       │                                    ┌──────┴──────┐
       │                                    │             │
       │                              Project        Session
       │                                    │             │
       │                                    ▼             ▼
       │                              Storage       Runtime
       │
       └──── 不同的 UI 展开展示，而不是不同的业务逻辑
```

### 26.2 原则

- CLI 和 WebUI 只是不同入口
- 不应该各自拥有自己的业务 Runtime
- 所有业务逻辑通过统一 API 处理

---

## 二十七、Natural Language Interaction Model (自然语言交互模型)

### 27.1 完整场景分析

**场景：飞机大战小游戏**

| Turn | 用户输入 | Message | Product Understanding 变化 |
|------|----------|---------|---------------------------|
| 1 | "我想做一个飞机大战小游戏。" | Idea(content="我想做一个飞机大战小游戏。") | ideas += [Idea]; status=DRAFT |
| 2 | "手机端。" | Message(content="手机端。") | platform=["mobile"]; pending_question="user是什么?" |
| 3 | "不要登录，打开就能玩。" | Message(content="不要登录，打开就能玩。") | constraints += ["无需登录", "打开即玩"] |
| 4 | "以后可以加排行榜。" | Message(content="以后可以加排行榜。") | future_ideas += [FutureIdea(priority=0.3)] |
| 5 | "你觉得还有什么问题？" | Message(content="你觉得还有什么问题？") | AI 生成 OpenQuestion list |
| 6 | "操作就用虚拟摇杆吧。" | Message(content="操作就用虚拟摇杆吧。") | constraints += ["虚拟摇杆操作"]; decisions += [Decision] |
| 7 | "整理成 PRD。" | Intent(GENERATE_PRD) | system generates PRD artifact |
| 8 | "PRD 简单一点。" | Message(content="PRD 简单一点。") | 修改 PRD.content.complexity = SIMPLE; regenerate |
| 9 | "就按这个做。" | Intent(EXECUTE) | system generates Development Plan; 进入 Production Runtime |

### 27.2 关键设计点

| 设计点 | 说明 |
|--------|------|
| 连续理解 | 每个 Message 都更新 Product Understanding |
| Confirmed vs Inferred | decisions 需要确认，ideas 可以是推断 |
| Open Questions | 系统主动追踪未解决的问题 |
| Future Ideas | 用户提到但未确认的放到 backlog |
| Adaptive Questions | 只问缺失的信息，不是固定问卷 |
| PRD Generation | 从 Product Understanding 派生，不是独立 Workflow |
| Plan Generation | 用户明确说要做了才生成 Plan |

---

## 二十八、Target Architecture (目标架构)

### 28.1 完整架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            User (Natural Language)                       │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Conversation API Layer                              │
│  /api/conversations/* ← 统一业务入口                                      │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────┐
│                      Conversation Layer                                  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  ConversationManager                                             │    │
│  │  ├── id: UUID                                                    │    │
│  │  ├── project_id: FK                                              │    │
│  │  ├── messages: List[Message]                                     │    │
│  │  └── productUnderstanding: ProductUnderstanding ──── SSOT      │    │
│  │       ├── ideas: List[Idea]                                      │    │
│  │       ├── requirements: List[Requirement]                        │    │
│  │       ├── decisions: List[Decision]                              │    │
│  │       ├── constraints: List[Constraint]                          │    │
│  │       ├── questions: List[OpenQuestion]                          │    │
│  │       ├── futureIdeas: List[FutureIdea]                          │    │
│  │       └── status: DRAFT → CONFIRMED → PRODUCTION                │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  AdaptiveClarificationProcess                                    │    │
│  │  ├── sufficiency_checker: SufficiencyChecker                    │    │
│  │  ├── question_selector: QuestionSelector                        │    │
│  │  └── missing_info: Set[str]                                     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  PRD Generator ──→ ProductUnderstanding ──→ PRD Artifact        │    │
│  │  Plan Generator ──→ PRD ──→ DevelopmentPlan                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Session Layer                                     │
│  (Runtime lifecycle, 不持有 Product Truth)                               │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  SessionManager                                                   │    │
│  │  ├── conversation_id: FK                                         │    │
│  │  ├── runtime_context: RuntimeContext                             │    │
│  │  ├── checkpoint: Checkpoint                                      │    │
│  │  └── lifecycle: CONNECTING → ACTIVE → IDLE → DISCONNECTED       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Production Runtime Layer                             │
│  (只负责 How，不负责 What)                                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  ProductionRuntime                                                │    │
│  │  ├── Task Decomposition                                          │    │
│  │  ├── Node Creation → NodeRun Execution                           │    │
│  │  ├── Artifact Generation                                         │    │
│  │  ├── Verification → Evidence                                     │    │
│  │  └── Recovery / Learning                                         │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 28.2 数据流

```
用户输入
    ↓
Message (record)
    ↓
AI Interpretation (infer ideas, requirements, questions)
    ↓
Product Understanding (update)
    ↓
Sufficiency Check (am I missing something?)
    ↓
If missing → Ask adaptive question
If sufficient → Ready for formalization
    ↓
User: "整理成 PRD"
    ↓
PRD Generator → PRD Artifact
    ↓
User: "就按这个做"
    ↓
Plan Generator → Development Plan
    ↓
Production Runtime → Task Tree → Node → NodeRun → Artifacts → Verification
```

---

## 二十九、conversation_os 与 session/ 最终谁负责什么

### 29.1 结论

**选项 B: conversation_os 上层 Conversation Domain，session/ 下降为 Session Runtime**

理由：
- session/ 已有完整的 ConversationManager + ProductIntent + Actions
- conversation_os 是一个过于简化的 facade，缺少核心能力
- 应该基于 session/ 的代码构建新的 Conversation Layer
- session/ 需要去除业务状态，只保留 Runtime 生命周期管理

### 29.2 迁移路径

1. **Phase 1**: 基于 session/conversation.py 构建新的 ConversationManager (包含完整的 ProductUnderstanding)
2. **Phase 2**: 将 session/ 的 Runtime 能力 (Session, SessionManager) 转换为纯生命周期管理
3. **Phase 3**: 统一 API: `/api/conversations/*` → New Conversation; `/api/sessions/*` → Runtime
4. **Phase 4**: 废弃 conversation_os.py (功能已被覆盖)
5. **Phase 5**: 清理旧的 Entity 定义 (如果不再需要)

---

## 三十、Architectural Invariants (架构不变式)

### 30.1 核心原则

```
1. Conversation 是持续产品认知的业务边界
   - Product Understanding 必须存在于 Conversation 级别
   - Session 不持有 Product Truth

2. Message 不是 Product Truth
   - Message 只是输入事件
   - Product Understanding 是 AI interpretation + user confirmation

3. Intent 不是 Product Truth
   - Intent 是 Command Routing 机制
   - 用户实际定义了什么看 Product Understanding

4. UI 不是任何业务状态的 SSOT
   - WebUI/CLI 只是展示层
   - 所有状态通过 Backend API 统一管理

5. Requirement Analysis 必须是 Adaptive
   - 不能是固定问卷
   - 系统判断缺失什么才问什么
   - 不要求用户遵循固定 Workflow

6. PRD 是 Product Understanding 的 Formalized Artifact
   - 不是 Conversation 的替代
   - 从 Product Understanding 派生
   - 可以多版本

7. Development Plan 是生产规划
   - 用户明确说要做了才生成
   - 从 PRD 派生

8. Production Runtime 不负责解释用户想做什么
   - 只负责如何可靠生产
   - What/Why 由 Conversation 负责
   - How 由 Production Runtime 负责

9. 一个业务事实只能有一个 SSOT
   - 不能有多个地方声称自己是 Product Truth
   - Conversation.productUnderstanding 是唯一

10. CLI / API / WebUI 不得拥有不同业务 Runtime
    - 只能是不同入口
    - 业务逻辑统一在 Backend

11. Internal Structured, External Natural
    - 内部高度结构化
    - 外部不限制用户说话方式

12. 产品理解允许持续演化
    - 用户可以随时补充信息
    - 不要求一次性完整描述

13. User-confirmed Decision 优先级高于 AI Inference
    - 用户确认的决策不可被 AI 覆盖
    - AI 只能建议，不能代替用户决定

14. Conversation 可以长期持续，Session 可以多次创建
    - Session 是临时的 Runtime 生命周期
    - Conversation 是持久的业务边界
```

--- 

## 三十一、Current Code Architecture (当前代码架构)

### 31.1 当前存在的系统

经过完整代码审计，当前系统中实际存在以下 Runtime：

| System | File | Entry | State Storage | SSOT | Consumers |
|--------|------|-------|---------------|------|-----------|
| conversation_os | conversation_os.py | /api/conversations/* | Entity Store (conv_, msg_, req_, decision_) | 是 (K1) | WebUI |
| session/ (Runtime) | session/session.py | /api/sessions/*, CLI | SessionContext (内存) | 部分 | CLI, API |
| ConversationManager | session/conversation.py | internal | ConversationManager.product_intent (内存) | 是 (S10) | session/, CLI |

**结论：实际存在 3 套状态的 Runtime！**

### 31.2 API 分裂现状

```
FastAPI Routes:
- /api/conversations/* → conversation_os.py (K1, S43 Entity)
- /api/sessions/* → Session Runtime
- /api/projects/* → Project
- /api/production-runs/* → Production Runtime
```

### 31.3 session/ 代码职责分解

| 模块 | 实际职责 |Target 分类 |
|------|----------|------------|
| conversation.py | ConversationManager (业务状态机) | Conversation Domain |
| intent.py / intent_core.py | Intent Parser & 60+ 种 Intent | Application (Router) |
| context.py / context_builder.py | SessionContext (运行时数据) | Session Runtime |
| product.py / product_intelligence.py | ProductIntent 定义 | Product Understanding |
| discovery.py / discovery_intelligence.py | Product Discovery 多轮追问 | Requirement Analysis |
| actions.py | Action 执行器 | Product/Plan/PRD |
| agent_loop.py | Production Execution | Production Runtime |
| llm_gateway.py | LLM 调用 | Runtime Support |

---

## 三十二、Session Responsibility Decomposition

### 32.1 核心发现：session/ 混合了多个领域

**当前问题：**
session/ 目录同时包含：
- Conversation Domain (conversation.py)
- Session Runtime (context.py)
- Product Understanding (product.py)
- Requirement Analysis (discovery.py)
- PRD/Plan Generation (actions.py)
- Production Runtime (agent_loop.py)

**这正是架构混乱的根源！**

### 32.2 Product Intent 当前存储位置

```
Session Runtime 中:
├── ConversationManager.product_intent (内存)
├── SessionContext.product_intent (内存)
└── 结论: NOT PERSISTENT (session 结束丢失)
```

**GAP: Product Understanding 不持久化！**

### 32.3 Intent 当前控制流程

```
用户输入
    ↓
Intent Parser (60+ INTENTS)
    ↓
INTENT_CREATE_PRODUCT → start_product_discovery
    ↓
DISCOVERY 状态机 (固定字段顺序: problem → user → core_features)
    ↓
INTENT_GENERATE_PRD → generate_prd action
    ↓
PRD.md 文件
```

**GAP: Intent Enum 控制 Workflow State Machine！**

---

## 三十三、Product Understanding Reality Audit

### 33.1 当前 Product Understanding 实现

| 概念 | 当前实现 | 位置 | 持久化 |
|------|----------|------|--------|
| ideas | ❌ 无 | - | - |
| requirements | ProductIntent (只有 5 个字段) | session/conversation.py | ❌ 内存 |
| decisions | decision_ Entity | conversation_os.py | ✅ Entity Store |
| constraints | 无 | - | - |
| questions | _product_pending (固定队列) | session/conversation.py | ❌ 内存 |
| future_ideas | ❌ 无 | - | - |
| assumptions | ❌ 无 | - | - |
| scope | ❌ 无 | - | - |
| platform | product_intent.platform | 内存 | ❌ |
| user | product_intent.user | 内存 | ❌ |
| core_features | product_intent.core_features | 内存 | ❌ |

**结论：Product Understanding 严重不完整，且不持久化！**

### 33.2 当前 PRD 实现

```
generate_prd action:
├── 输入: ProductIntent
├── 输出: PRD.md (纯文本文件)
├── 位置: projects/<slug>/PRD.md
└── 结论: 是文件，非结构化对象，无版本控制
```

---

## 三十四、Context Continuity Audit

### 34.1 场景追踪：飞机大战

| Turn | 用户输入 | 当前实际处理 |
|------|----------|--------------|
| 1 | "飞机大战" | 用户需说"创建产品"触发 INTENT_CREATE_PRODUCT |
| 2 | "手机端" | 必须在 DISCOVERY 流程中，回答特定问题 |
| 3 | "不要登录" | 同上 |
| 4 | "加排行榜" | 被忽略或必须回答问题 |
| 5 | "还有什么问题" | 系统继续问必填问题 |
| 6 | "摇杆操作" | 同上 |
| 7 | "整理成 PRD" | 需说"生成PRD"触发 INTENT_GENERATE_PRD |
| 8 | "简单一点" | 需重新触发 PRD 生成，并传入参数 |
| 9 | "就按这个做" | 需说"开始执行"触发 INTENT_EXECUTE_PROJECT |

**GAP: 用户不能自然说话，必须使用特定 Keyword/Intent！**

---

## 三十五、Intent Control Audit

### 35.1 Intent 当前控制权

```
INTENT_CREATE_PRODUCT
    ↓
ConversationManager.start_product_discovery()
    ↓
DISCOVERY 状态机
    ↓
INTENT_GENERATE_PRD
    ↓
actions.generate_prd()
    ↓
INTENT_EXECUTE_PROJECT
    ↓
Production Runtime
```

**ARCHITECTURAL VIOLATION: Intent Enum 成了 Workflow State Machine！**

---

## 三十六、PRD Reality Audit

### 36.1 当前 PRD 实现

| 属性 | 当前 | Target |
|------|------|--------|
| 版本化 | ❌ | ✅ |
| 持久化 | ✅ 文件 | ✅ 结构化 |
| 可追溯 | ❌ | ✅ 追溯到 Product Understanding |
| 可编辑 | ❌ 手动 | ✅ API |
| 可再生 | ❌ | ✅ |
| 审查 | ❌ | ✅ |

---

## 三十七、Development Plan Reality Audit

### 37.1 当前 Plan 实现

User 说"就按这个做"，当前流程：
1. 用户说"开始执行"
2. Intent=INTENT_EXECUTE_PROJECT
3. action=execute_project
4. 生成 Task Tree
5. 进入agent_loop执行

**GAP: 没有先建立 Development Plan！**

---

## 三十八、Production Runtime Boundary Audit

### 38.1 当前边界

经过代码审计，当前 Production Runtime (agent_loop.py)：
- ✅ 负责 Task Decomposition
- ✅ 负责 Node Execution
- ✅ 负责 Artifact Generation
- ✅ 负责 Verification & Evidence

**但**：
- ❌ 没有与 Conversation 正确解耦
- ❌ 还是通过 Intent 触发，不是通过 Plan 触发

---

## 三十九、State Ownership Reality

### 39.1 当前状态所有权矩阵

| State | Current Owner | SSOT | Persistence | GAP |
|-------|---------------|------|-------------|-----|
| Conversation | conversation_os Entity | 是 | ✅ | 与 session/ 分裂 |
| Messages | conversation_os Entity | 是 | ✅ | 与 session/ 分裂 |
| ProductIntent | ConversationManager (内存) | 是 | ❌ | Session 结束丢失 |
| Decisions | conversation_os Entity | 是 | ✅ | 与 session/ 分裂 |
| Requirements | conversation_os Entity | 是 | ✅ | 与 session/ 分裂 |
| PRD | projects/PRD.md | 是 | ✅ | 非结构化 |
| DevelopmentPlan | 无 | - | - | 不存在 |
| SessionState | SessionContext (内存) | 是 | ❌ | Session 结束丢失 |

### 39.2 关键问题

**一个业务事实存在多个 SSOT：**
- conversation_os 有 decisions, requirements (Entity)
- session/ 有 product_intent (内存)

**这就是双系统分裂的证据！**

---

## 四十、API Reality

### 40.1 当前 API 结构

```
/api/conversations/*     → conversation_os (K1)
/api/sessions/*          → session/ Runtime
/api/projects/*          → Project
/api/production-runs/*   → Production Runtime
```

**问题：Conversation API 和 Session API 是两个平行 Runtime！**

---

## 四十一、CLI Reality

### 41.1 当前 CLI 入口

```
factory command
    ↓
Session (session.py)
    ↓
ConversationManager
    ↓
Intent routing
```

**问题：CLI 直接进入 session/，不使用 conversation_os**

---

## 四十二、WebUI Reality

### 42.1 当前 WebUI 调用

```
WebUI:
- /api/conversations/* → conversation_os (Session 页面)
- /api/sessions/* → session/ (Runtime 页面)
- /api/projects/* → Project
```

**问题：WebUI 同时使用两个系统，没有统一！**

---

## 四十三、Third Runtime Audit

### 43.1 Runtime Inventory

| # | System | Verdict |
|---|--------|---------|
| 1 | conversation_os (K1) | 应该废弃，功能被 session/ 覆盖 |
| 2 | session/ ConversationManager | 应该演化为统一 Conversation |
| 3 | Production Runtime (agent_loop) | 应该独立，只负责执行 |

**结论：不是 2 套，是 3 套（conversation_os, session 内部 conversation, production runtime）**

---

## 四十四、Target Code Architecture

### 44.1 推荐目录结构

```
factory-console/
├── domain/                    # 领域模型 (Pure business concepts)
│   ├── conversation/
│   │   ├── models.py          # Conversation, Message, ProductUnderstanding
│   │   └── types.py           # Idea, Requirement, Decision, etc.
│   ├── product/
│   │   └── models.py          # PRD, DevelopmentPlan
│   └── project/
│       └── models.py          # Project
│
├── application/               # 应用服务 (Use cases)
│   ├── conversation/
│   │   ├── service.py         # ConversationService
│   │   ├── understanding.py   # ProductUnderstandingService
│   │   └── formalization.py   # PRD/Plan generation
│   └── production/
│       └── service.py         # ProductionService
│
├── runtime/                   # 运行时 (Execution)
│   ├── session/
│   │   └── manager.py         # SessionManager (Lifecycle only)
│   └── production/
│       ├── runtime.py         # ProductionRuntime
│       ├── execution.py       # Node execution
│       └── verification.py    # Verification
│
├── adapters/                  # 适配器 (Ports)
│   ├── api/
│   │   └── routes.py          # Unified API routes
│   ├── cli/
│   │   └── commands.py        # CLI commands
│   └── web/
│       └── handlers.py        # WebUI handlers
│
└── persistence/               # 持久化
    ├── entity_store.py        # Generic Entity Store
    ├── conversation_repo.py   # Conversation Repository
    └── project_repo.py        # Project Repository
```

### 44.2 关键拆分原则

| 原则 | 说明 |
|------|------|
| Domain ≠ Runtime | Conversation 属于 domain，不是 runtime |
| Session = Lifecycle | Session 只管连接，不管业务 |
| Product Understanding = Domain | 必须在 domain 层，持久化 |
| Production = Runtime | 只负责执行，不负责理解 |

---

## 四十五、Migration Decision Matrix

| 代码 | 当前位置 | 目标位置 | 决策 | 原因 |
|------|----------|----------|------|------|
| ConversationManager | session/conversation.py | domain/conversation/service.py | MOVE | 核心 Conversation 逻辑 |
| Intent Parser | session/intent.py | application/conversation/router.py | REFACTOR | 只是路由，不是业务 |
| ProductIntent | session/product.py | domain/conversation/models.py | MOVE | Product Understanding |
| Discovery Logic | session/discovery.py | application/conversation/understanding.py | REFACTOR | 自适应澄清 |
| generate_prd | session/actions.py | application/conversation/formalization.py | MOVE | PRD 生成 |
| execute_project | session/actions.py | application/production/service.py | MOVE | Production 启动 |
| SessionContext | session/context.py | runtime/session/manager.py | MOVE | 只保留 lifecycle |
| Production Runtime | session/agent_loop.py | runtime/production/ | MOVE | 执行层 |

---

## 四十六、Migration Sequence

### Phase 1: 冻结 (禁止新功能)

- 冻结 conversation_os 新功能
- 冻结 session/ 新业务逻辑

### Phase 2: 建立 Product Understanding SSOT

1. 创建 domain/conversation/models.py
   - ProductUnderstanding (完整字段)
   - Idea, Requirement, Decision, Constraint, Question, FutureIdea
2. 创建 persistence/conversation_repo.py
   - 持久化 ProductUnderstanding
3. 迁移 session/product.py → domain/conversation/models.py
4. 测试：session 结束后 Product Understanding 仍然存在

### Phase 3: 统一 Conversation Service

1. 创建 application/conversation/service.py
   - 包装 ConversationManager 功能
   - 从 ProductUnderstanding SSOT 读取
2. 修改 API: /api/conversations/* → new service
3. 测试：API 和 CLI 使用同一 SSOT

### Phase 4: 统一 PRD/Plan

1. 创建 application/conversation/formalization.py
   - PRD 从 ProductUnderstanding 派生
   - Development Plan 从 PRD 派生
2. 结构化 PRD/Plan 存储
3. 测试："PRD 简单点" 修改复杂度，重新生成

### Phase 5: 统一 Production 入口

1. 修改 actions 中 execute_project
   - 接受 PRD/Plan 作为输入
   - 不再从 Intent 直接触发
2. 测试："就按这个做" → Plan → Production

### Phase 6: 统一 CLI

1. 迁移 factory 命令到新的 ConversationService
2. 测试：CLI 和 API 行为一致

### Phase 7: 统一 WebUI

1. WebUI 全部调用 /api/conversations/*
2. 移除 /api/sessions/* 直接调用
3. 测试：WebUI 显示的与 API 一致

### Phase 8: 退役 conversation_os

1. 删除 conversation_os.py
2. 旧的 Entity 迁移到 ProductUnderstanding
3. 测试：功能完全正常

### Phase 9: 清理

1. 合并重复代码
2. 移除 Intent 对 Workflow 的控制
3. 建立最终架构

---

## 四十七、Implementation Boundaries

### 47.1 必须保持不变

1. Production Runtime (agent_loop.py) 的执行能力
2. LLM Gateway 的调用能力
3. Entity Store 的持久化能力
4. CLI 交互模式

### 47.2 必须重构

1. session/conversation.py → domain/conversation/service.py
2. session/context.py → runtime/session/manager.py
3. Intent 路由 → 只是路由，不控制流程

### 47.3 必须新增

1. ProductUnderstanding 完整模型 (ideas, requirements, decisions...)
2. ConversationRepository (持久化)
3. PRD/Plan 结构化存储
4. Adaptive Clarification Process

### 47.4 必须删除

1. conversation_os.py (功能被覆盖)
2. 旧的双写状态

---

## 四十八、Code-Level Architectural Invariants

在第三阶段 15 条基础上，补充代码级不变式：

```
16. Product Intent 必须持久化
    - Session 结束不能丢失
    - 必须在 Project/Conversation 级别

17. Intent 只能是 Router，不能是 State Machine
    - if intent == INTENT_CREATE_PRODUCT: do_something()
    - 禁止: intent → 固定状态迁移

18. PRD 必须是结构化对象，不是文件
    - 可以导出为文件
    - 必须能通过 API 读取/修改

19. Development Plan 必须来自 PRD/确认的产品定义
    - 不能从 Intent 直接触发
    - 必须在 Confirmed 之后

20. Conversation 必须是长期存在
    - 不依赖 Session 存在
    - Session 可以多次创建/销毁

21. 一个 Project 可以有多个 Conversation
    - 但只能有一个当前活跃的 Product Understanding

22. Production Runtime 禁止解释用户需求
    - 只接受明确的 Task/Plan 输入

23. Context 构建必须基于 Product Understanding
    - 不是每次重新推测
    - 连续性由 Understanding 保证

24. WebUI 不能自己维护业务状态
    - 所有状态来自 API
    - 只做展示和用户输入

25. API 必须统一
    - /api/conversations 是主入口
    - /api/sessions 是 Runtime 生命周期
```

---

## 最终结论

### Current Architecture (当前架构)

```
User
  ↓
K1 conversation_os ←→ session/ConversationManager (两套并行)
  ↓                    ↓
Entity Store       Memory (product_intent)
  ↓                    ↓
PRD.md (文件)       丢失
  ↓
Production Runtime
```

### Target Architecture (目标架构)

```
User
  ↓
Unified API Layer
  ↓
Conversation Service (Product Understanding SSOT)
  ↓              ↓              ↓
PRD Service   Plan Service   Session Runtime(只 Lifecycle)
  ↓              ↓
Production Runtime (只负责 How)
```

### GAP (差距)

| # | Gap | Severity |
|---|-----|----------|
| 1 | Product Intent 不持久化 | CRITICAL |
| 2 | Intent 控制 Workflow State Machine | CRITICAL |
| 3 | 两套 API 并行 (conversation_os + session) | CRITICAL |
| 4 | PRD 是文件不是结构化对象 | HIGH |
| 5 | 无 Development Plan 阶段 | HIGH |
| 6 | Conversation 不持久化 | HIGH |
| 7 | Product Understanding 不完整 | HIGH |
| 8 | Context 每轮重建 | MEDIUM |
| 9 | Requirement Analysis 固定问卷 | MEDIUM |
| 10 | WebUI 同时调用两个 API | MEDIUM |

### Migration Strategy

按照第四十六节的 9 阶段迁移：
1. 冻结新功能
2. 建立 Product Understanding SSOT
3. 统一 Conversation Service
4. 统一 PRD/Plan
5. 统一 Production 入口
6. 统一 CLI
7. 统一 WebUI
8. 退役 conversation_os
9. 清理

**关键不变式：**

```
1. 不允许新增第二套 Conversation Runtime
2. 不允许 Session 持有 Product Truth
3. 不允许 Intent Enum 成为 Product State Machine
4. 不允许 UI 成为业务事实源
5. Product Understanding 是唯一事实源
6. Conversation > Session (Conversation 持久，Session 可重建)
```

---

## 第四阶段审计完成

报告位置: `docs/audit/conversation-dual-system-root-cause.md`

第三阶段架构审计已完成。

报告位置: `docs/audit/conversation-dual-system-root-cause.md`

### 回答 10 个核心问题

1. **Conversation 是什么？** 用户与 AI 之间的持续工作空间，是产品认知的业务边界

2. **Session 是什么？** 用户与系统之间的一次具体交互的生命周期管理

3. **Product Understanding 是什么？** 用户产品定义的结构化表达，包含 ideas/requirements/decisions/constraints/questions/future_ideas

4. **Project 是什么？** 用户工作的容器，关联 Conversation/Product/PRD/Plan

5. **Requirement Analysis 是什么？** Adaptive Clarification Process，系统判断缺失什么信息才问什么问题

6. **PRD 是什么？** Product Understanding 的 Formalized Artifact，从理解派生，非独立创建

7. **Development Plan 是什么？** 从确认的 PRD 生成的生产规划，用户明确说要做了才生成

8. **Production Runtime 是什么？** 只负责 How to reliably produce，不负责 What to produce

9. **conversation_os 与 session/ 最终谁负责什么？**
   - session/ 应该演化为完整的 Conversation Layer
   - conversation_os 应该废弃 (功能已被覆盖)
   - session/ 的 Runtime 部分下降到纯 Session 生命周期管理

10. **从用户自然语言到 Production Runtime 的唯一正确架构是什么？**
   ```
   User Input → Message → AI Interpretation → Product Understanding (Adaptive)
   → (User: "整理成 PRD") → PRD Artifact
   → (User: "就按这个做") → Development Plan → Production Runtime
   → Task Tree → Node → NodeRun → Artifact → Verification → Evidence
   ```

### 11.1 conversation_os 创立时的真正原因

**核心发现：K1 设计者不知道 session/ 已经具备的能力**

证据链：

1. **时间线**：
   - 2026-08-24: session/ LLM 化 (S10-100)
   - 2026-08-25: session/ LLM 关键修复 (S10-118)
   - 2026-08-29: K1 Gap Analysis 完成
   - 2026-08-31: K1 创建 conversation_os

2. **K1 Gap Analysis 评估对象**：
   - 报告 `k1-conversation-os-report.md` 和 `k1-gap-analysis.md` 中**完全没有提到 "session"** 这个词
   - 评估的是 "chat_store 落库 (无理解)" — S15 之前的旧会话系统
   - 与 S10-047 后的 session/ 无关

3. **两个系统设计目标不同**：

   | 系统 | 原始设计目标 |
   |------|--------------|
   | session/ (S10-047) | "Workforce Terminal 交互会话包 (纯标准库交互 shell, 零依赖, 不接真实 LLM)" |
   | conversation_os (K1) | "普通用户通过对话驱动 OS (讨论→决策→执行→结果→继续)" |

4. **根本差异**：
   - session/: CLI 专用，命令行交互
   - conversation_os: API/Web 用户，对话驱动

### 11.2 为什么选择新建而不是复用？

**答案：设计者当时没有意识到 session/ 已经足够强大**

- K1 Gap Analysis 只看到 "底层 Work 链已有，上层对话理解 MISSING"
- 没有检查 session/ 当时的实际能力（ConversationManager + ProductIntent）
- 错误地认为需要新建一个 "Conversation OS" 来补全缺失的能力
- 实际上 session/ 在 8 月 25 日已经具备：
  - ConversationManager (多轮对话状态机)
  - ProductIntent (产品意图理解)
  - LLM 化 (S10-100)
  - 60+ Intents

### 11.3 K1 设计的真正目标

从 `k1-gap-analysis.md` 可以看出：

```
底层 Work 链 (12-22) 全 REUSE (S3-S43 已建)
Conversation 理解层 (1-11, 23-25) 全 MISSING — K1 核心
```

K1 只想补全 "对话理解层"，但错误地认为需要全新创建。

---

## 十二、概念模型冲突 (Conceptual Model Conflict)

### 12.1 Conversation 定义冲突

| 概念 | conversation_os | session/ |
|------|-----------------|----------|
| Conversation | 独立 Entity (S43 conv_ 前缀) | Session 内的状态管理 |
| Message | msg_ Entity | 内存 history |
| State | 简单 dict (goal/decisions/topic) | 完整 ConversationState 枚举 |
| Context | 无 | ConversationManager + SessionContext |
| Intent | 6 种固定 | 60+ 种，支持 LLM |
| Product | 无 | ProductIntent |

### 12.2 根本冲突

- **conversation_os**: 把 Conversation 当作 Entity 存储
- **session/**: 把 Conversation 当作状态机 + 内存对象

---

## 十三、架构错误总结 (Root Architectural Mistake)

### 13.1 第一个错误架构决策

```
错误 1: 把 session/ 只当作 CLI 工具
        ↓
错误 2: 没有认识到 session/ 已经是完整的 Conversation Runtime
        ↓
错误 3: K1 创建了新的 conversation_os，而不是扩展 session/
        ↓
错误 4: 没有建立 Conversation → Session 的层级关系
        ↓
错误 5: API 直接暴露两个 Runtime (/api/conversations vs /api/sessions)
        ↓
错误 6: WebUI 同时依赖两个事实源
```

### 13.2 正确的做法应该是

```
方案 A: 扩展 session/ 为 API
  - 让 session/ 支持 /api/sessions/*
  - 保持 ConversationManager 作为核心
  - 不需要新的 conversation_os

方案 B: 建立层级关系
  - Conversation (Entity) → 业务层面
  - Session (Runtime) → 执行层面
  - Runtime (Execution) → 生产层面
```

---

## 十四、最终边界建议 (Final Boundary Recommendation)

### 14.1 正确概念模型

```
┌─────────────────────────────────────────┐
│         User (Natural Language)          │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Conversation Layer               │
│  (Entity: conv_ 前缀, 可追溯)            │
│  - Messages                             │
│  - Intent (LLM 理解)                    │
│  - State (goal/decisions/topic)         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Session Layer                    │
│  - Session (lifecycle)                   │
│  - ProductIntent (产品理解)              │
│  - ConversationManager (状态机)          │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Runtime Layer                    │
│  - Production Runtime                    │
│  - Node Runtime                          │
│  - Agent Loop                            │
└─────────────────────────────────────────┘
```

### 14.2 修复建议

1. **统一 Conversation 入口**: 全部走 Session Runtime
2. **废弃 conversation_os**: 其 Entity 能力可以保留，Intent/State 能力需要迁移到 session/
3. **API 统一**: `/api/conversations` 重定向到 `/api/sessions`
4. **CLI 统一**: InteractiveSession 复用完整 Product Pipeline

---

## 附录 A: 调用链文件位置

### System A (conversation_os)

```
入口: factory-console/web/backend/fastapi_adapter.py:6572
  → line 6579: _co.send_message(root, conversation_id, message, actor)
    → factory-console/conversation_os.py:116 (def send_message)
      → line 129: detect_intent(message, last_intent)
      → line 138-154: State 更新
      → line 157: _make_reply(root, conv, message, intent, last_intent)
        → line 178-253: 模板回复生成
```

### System B (session/)

```
入口1 (CLI): factory-console/cli_factory.py:8463
  → line 8464: InteractiveSession().run()
    → factory-console/session/session.py:115 (class InteractiveSession)
      → line 361: _dispatch_inner(line)

入口2 (API): factory-console/web/backend/fastapi_adapter.py:7447
  → line 7472: _agmod = _console_import("session.agent_loop")
    → factory-console/session/agent_loop.py
      → 通过 Session 调用 ConversationManager
```

---

## 附录 B: 文件清单

### System A

| 文件 | 行数 | 职责 |
|------|------|------|
| conversation_os.py | 505 | 完整系统 |

### System B

| 文件 | 行数 | 职责 |
|------|------|------|
| session/__init__.py | 15 | 包导出 |
| session/session.py | 913 | InteractiveSession |
| session/conversation.py | 1668 | ConversationManager |
| session/actions.py | 4133 | Action 集合 |
| session/agent_loop.py | 227044 (227KB) | Agent Loop |
| session/intent.py | 393 | Intent 定义 |
| session/router.py | ~200 | Intent 路由 |
| session/context.py | ~500 | SessionContext |
| session/product.py | 171 | ProductIntent |

## 四十九、Product Understanding Implementation

**日期**: 2026-09-08 | **阶段**: S49 / Phase 5 (第四阶段审计后首次实施) | **状态**: ✅ Implemented + Tested

### 实施目标 (S49 §一)

> 先建立真正持久化的 Product Understanding SSOT, 让自然语言 Conversation 可以连续积累产品认知。

### 落地文件 (全部新增, 零 legacy 修改于 conversation_os/session/production_runtime)

| 文件 | 职责 | 状态 |
|------|------|------|
| `factory-console/product_understanding.py` | Conversation+Message+Fact domain + 原子 JSON store | ✅ Verified (单测覆盖) |
| `factory-console/conversation_app.py` | ConversationApplicationService / ProductUnderstandingService / 确定性 NL 解释器 / sufficiency | ✅ Verified |
| `factory-console/application_formalization.py` | PRD Domain (从 Understanding 派生, versioned, provenance) | ✅ Verified |
| `factory-console/web/backend/fastapi_adapter.py` | 新 Conversation Domain API 端点 (legacy 不动) | ✅ Verified (6 API tests) |
| `tests/console/test_product_understanding_ssot.py` | Test A–F + P0/P1 (17 tests) | ✅ 17 passed |
| `tests/console/test_product_understanding_api.py` | Application Layer API (6 tests) | ✅ 6 passed |

### 概念冻结 (S49 §一)

- **Conversation ≠ Session**: Conversation = 长期业务/认知空间 (持久化); Session = 交互生命周期 (可结束/重建)。
- **Product Understanding ≠ Intent**: Intent 只描述"这句话想干什么", 绝不作为 Product 状态机 SSOT。
  本域代码零 INTENT 引用 (测试断言无 `INTENT_` 依赖)。

---

## 五十、Product Understanding Persistence

### 存储模型

```
<root>/conversations/{conv-id}.json    ← 单文件原子一致 (RLock + tmp + os.replace)
├── id / title / status (OPEN|ARCHIVED) / created_by / created_at / updated_at
├── messages: [{id, role, content, created_at}]   ← append-only
├── understanding: {version: int, facts: {fact_id: Fact}}
│     Fact: id / conversation_id / type / content / status
│           / source_message_id / confidence / provenance
│           / supersedes[] / superseded_by / created_at / updated_at
└── prds: [PRD records] (versioned, §五十四)
```

### Fact 类型与状态 (S49 §二)

- **type** ∈ `IDEA | REQUIREMENT | CONSTRAINT | DECISION | QUESTION | FUTURE_IDEA` (可扩展注册表)
- **status** ∈ `PROPOSED | CONFIRMED | SUPERSEDED | REJECTED`; 有效 = PROPOSED/CONFIRMED
- 每 Fact 至少含 `id/conversation_id/type/content/status/source_message_id/created_at/updated_at/confidence/provenance` — 与 S49 §二字段清单一致

### 持久化语义

- conversation/messages/facts/version 单文件原子写 — 重启后一次读全恢复 (Test B ✅)
- `understanding.version` 单调递增 — PRD provenance 锚点 (Test F ✅)

---

## 五十一、Conversation Domain Implementation

### Application Layer (S49 §十三/§十四 唯一入口)

```
ConversationApplicationService   — conversation 生命周期 (create/get/list/messages/close)
ProductUnderstandingService      — process_user_message(NL → facts) / snapshot / context
                                   / facts / sufficiency_gaps / adaptive_question
```

- CLI/API/WebUI 未来统一经 **Application Service** → Domain; 禁止直达 session internals / conversation_os / AgentLoop。
- 本阶段 conversation 创建经 ApplicationService (domain 直建); HTTP 端点挂载于 `/api/conversations/{id}/product-understanding*` — 与 legacy `conv_*` (conversation_os) 路径共存不冲突 (S49 §十三: API 只建 Boundary, 不一次性迁移; legacy 端点未动)。

### API 端点 (新增, 全部读面或白名单写面)

```
POST /api/conversations/{id}/product-understanding/messages   NL → Understanding 增量更新
GET  /api/conversations/{id}/product-understanding            Understanding 快照
GET  /api/conversations/{id}/product-understanding/context    Context (持久化 Understanding 构建)
GET  /api/conversations/{id}/messages                         消息列表 (Application Layer)
POST /api/conversations/{id}/prd                              PRD 派生 (需已有 Understanding)
GET  /api/conversations/{id}/prd                              PRD 列表 (provenance 可见)
```

- 写路由白名单已同步 (tests/console/test_s10_112_registry_consistency.py +2 豁免)。
- 未知 conversation → 404; 空 Understanding 派生 PRD → 400 (诚实拒绝, 无假成功)。

---

## 五十二、Adaptive Clarification Implementation

### 从固定问卷 → Sufficiency-based (S49 §五)

- **旧**: `_PRODUCT_FIELD_ORDER = (problem → user → core_features)` 固定顺序问卷。
- **新**: `ProductUnderstandingService.sufficiency_gaps(conv)` — 从**当前快照**发现真正缺失:
  - 无 IDEA → "先确定核心想法"
  - 无 REQUIREMENT 且内容无平台信息 → "运行平台还没定"
  - 无 DECISION 且无交互描述 → "交互方式还没定"
  - `adaptive_question(conv, asked)` — 只问尚未答过的缺口, 不问完所有字段 (测试: 回答后不再重复同一问题 ✅)

### 测试证据

- `TestAdaptiveClarification` 2 tests: gap 检测非固定问卷 + 已回答不重复 ✅
- 注意: 本阶段**不实现完整 Requirement Analysis Node 轮询** (requirement_analysis_node 已存在并
  有 Human Decision 门 — 那是 production 前深潜分析); S49 的 sufficiency 是 conversation 层的轻量澄清。

---

## 五十三、Context Continuity Implementation

### Context 构建 (S49 §六)

`ProductUnderstandingService.context(conv)` → `product_understanding.build_context`:

```
Conversation (title/status)
  + recent_messages (窗口, 缺省 8)
  + understanding version
  + effective facts (by_type 分组 + 扁平, budget 截断)
```

- **禁止**: 重读最近 N 条消息 → 猜产品是什么。Context 明确从持久化 Understanding 构建。
- 测试: `TestContextFromUnderstanding` ✅ — close 后 context 仍含 facts + recent messages。

### Session Restart 连续性 (S49 §七, 核心验收)

- Session1: NL 4–5 句 → facts 累积 → `close_conversation` (ARCHIVED)
- Session2: 新 service 实例 (同 root) → `get_conversation` 完整恢复 → 继续自然对话
- 测试: `TestSessionRestart` 3 tests ✅ (恢复 facts / 追问知道产品 / 不重问"请描述产品")

---

## 五十四、PRD Domain Foundation

### PRD 模型 (S49 §八)

```
PRD-{id}  (record 存于 conversation 文档 prds[])
├── conversation_id
├── version: int (1, 2, ...)
├── status: draft → approved (→ archived 边界, 未实现完整 workflow — 属后续 Phase)
├── source_product_understanding_version   ← provenance (Test F)
├── content: {overview, functional_requirements, constraints, decisions,
│            future_considerations, open_questions, provenance{facts[]}}
├── structured_content                     ← section → 内容映射 (结构化对象, 非文件)
├── created_at / updated_at / actor / history[]
└── 渲染: render_prd_markdown(prd)        ← 保留文件 Artifact 能力 (只读派生)
```

### 关键语义

- **PRD 从 Understanding 派生** (create_prd 读 snapshot → derive_prd_sections), 不是独立创建/反向猜测文件。
- 空 Understanding → `ValueError` (拒绝无源 PRD)。
- 修改 = `update_prd` 从**最新** Understanding 重新派生 → 新 version (draft only)。
- approved → 不可原地改 (走新 PRD/版本化)。
- **不破坏现有 `PRD.md` Artifact**: 结构化 PRD Domain Object → `render_prd_markdown` 渲染投影 (未来接 workspace 输出)。

---

## 五十五、Application Layer Boundary

### 状态所有权冻结 (S49 §十二)

| Domain | SSOT | 本阶段落点 |
|--------|------|-----------|
| Conversation | Conversation Domain | `product_understanding.py` conversation 文档 |
| Message | Conversation | 同上 messages[] |
| Product Understanding | Conversation/Product Domain | `product_understanding.py` facts[] |
| Requirement/Constraint/Decision/Question/Future Idea | Product Understanding | facts (type 区分) |
| PRD | PRD Domain/Artifact | conversation 文档 prds[] (versioned) |
| Development Plan | Plan Domain | ⏳ 未实现 (S49 §九: 只建边界不实现) |
| Session | Session Runtime | ⏳ legacy session/ 未动 (后续迁移) |
| Task/Node/NodeRun/Artifact/Evidence | Production Runtime | ✅ 未触碰 (保持现状) |

- 单一 writer 原则: Fact 唯一 writer = `upsert_fact`; PRD 唯一 writer = `create_prd/update_prd/approve_prd`。
- 不存在 Frontend + Session memory + JSON + Intent 共同拥有同一状态。

---

## 五十六、E2E Natural Language Validation

### Test A–F 结果 (tests/console/test_product_understanding_ssot.py — 17 passed)

| Test | 内容 | 结果 |
|------|------|------|
| Test A | NL 连续理解: 飞机大战 → 手机端 → 不要登录 → 排行榜(future) → 虚拟摇杆(decision) | ✅ 全类型 fact 累积 |
| Test B | Session Restart: S1 写入+close → S2 加载完整恢复 | ✅ facts+version 恢复 |
| Test C | 无 keyword: 输入全是普通中文, 禁内部命令 | ✅ banned 词扫描为 0 |
| Test D | 修改非新增重复: 重申约束不产生冲突 fact (supersession) | ✅ 1 effective + SUPERSEDED 历史 |
| Test E | Context Continuity: S2 追问基于 PU 回答, 不"请描述产品" | ✅ |
| Test F | PRD 从 Understanding 派生: source_product_understanding_version 可追踪 | ✅ v1→v2 单调 |

### API 层 (test_product_understanding_api.py — 6 passed)

NL → messages → understanding 快照 / 404 / messages roundtrip / context / PRD create+list / 空 Understanding 拒绝。

---

## 五十七、Session Restart Validation

### 复验链 (S49 §十七, 真实执行)

```
User NL ×5 → Understanding (5 facts, ver 5) → sufficiency (信息足够)
  → PRD v1 (src_uv 5) → 修改 ("不要内购") → PRD v2 (src_uv 6, version 2)
  → close → Session Restart → facts 恢复 (6, ver 6) → 继续 NL 对话 → 回答引用持久化理解
```

- ✅ 自动化测试: TestSessionRestart (3) + TestContextFromUnderstanding (1) + 完整链脚本复验。
- ⚠️ **限制声明** (S49 验收纪律 — 自动化 ≠ 人工): 以上为**自动化验证** (确定性规则解释器);
  真实 LLM 解释 + WebUI 人工会话验收 (中文 IME) 属用户实测环节, 未在本阶段自动化内冒充完成。

---

## 五十八、Remaining Migration Gaps

### 已实现 vs 未迁移 (诚实清单)

| 项 | 状态 | 说明 |
|----|------|------|
| Product Understanding 持久化 SSOT | ✅ Implemented | conversation-scoped facts + version |
| Session Restart 连续性 | ✅ Verified (自动化) | 真实 WebUI 人工验收待用户 |
| Intent → Workflow State Machine 残留 | ⚠️ legacy 存在 | session/conversation.py + conversation_os.py 内旧路径**未删除** (S49 §十禁令); 新域无此模式 |
| Product Intent 仅内存存储 | ⚠️ legacy 存在 | session/ConversationManager.product_intent 仍内存; 新域已持久化, 未接替旧路径 (Phase 3 统一 Conversation Service 迁移) |
| conversation_os / session/ 双轨 API | ⚠️ 未统一 | legacy /api/conversations (conv_*) 与 /api/sessions 保留; 新域端点共存 |
| CLI → session/ | ⚠️ 未迁移 | factory CLI 仍走 InteractiveSession (Phase 6) |
| WebUI 依赖两套 API | ⚠️ 未迁移 | 前端仍调 conversation_os + session (Phase 7) |
| Development Plan 域 | ⏳ 未开始 | 仅声明边界 (PRD → Plan → Production 链留后续 Phase) |
| requirement_analysis_node 固定倾向 | ✅ 未新增 | S49 用 sufficiency 轻量澄清; RA Node 7 维已有 Human Decision 门 (此前阶段) |
| 历史数据迁移 | ⏳ 未开始 | 无历史 conversation understanding (新域为空起步) |

### 架构裁决复核

- ✅ 未引入第二套平行事实系统: 新域为第四阶段 §29 裁决的 conversation_os → RETIRE 替代本体
  (目标架构), 非平行另一套; product_truth (正式资产层) 与新域 (认知层) 语义分离, 未来
  formalize 时衔接。
- ✅ Context 从持久化 Understanding 构建, 不再猜。
- ✅ 用户只自然说话: 内部结构化 (domain/fact/supersession/provenance), 外部无 keyword/round 感。

---

**S49 / Phase 5 实施完成** (2026-09-08)

实现报告并入本审计文档 (四十九~五十八); 计划文档: `docs/audits/2026-09-08-s49-plan.md`。

**核心结论**: Product Understanding 已从内存/固定问卷变为持久化、conversation-scoped、可 supersede 的事实 SSOT;
Conversation Domain + Application Layer 边界已建立; Session Restart 连续性已验证 (自动化);
legacy (conversation_os/session) 按 S49 §十禁令保留未删, 迁移路径按第四阶段 Migration Sequence 顺延。

---

