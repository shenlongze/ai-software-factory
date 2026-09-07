# AI Factory OS — Product Intelligence Root Cause Deep Scan

**Date**: 2026-09-08
**扫描目的**: 找出 Idea → Requirement → PRD → Development Plan 处理过程中的真实代码缺陷

---

## Executive Summary

**结论类型**: F. 多个问题叠加，并给出因果优先级

**核心问题**: 系统存在 **双轨制架构**，两套会话系统完全不互通，导致用户输入无法正确传递到 Product Pipeline。

---

## 一、真实执行路径追踪

### 路径 A: WebUI Conversation (系统 A)

```
User Input "我想做一个飞机大战小游戏"
  ↓
HTTP POST /api/conversations/{conv_id}/messages
  ↓
file:6579 (fastapi_adapter.py)
  ↓
_co.send_message(root, conv_id, message, actor)
  ↓
conversation_os.send_message()
  ↓
detect_intent() → 返回 DISCUSS/DECIDE/APPROVE/EXECUTE (仅 4 种)
  ↓
_make_reply() → 返回模板文本
  ↓
RESPONSE
```

**状态存储**: `conv["state"]` (dict: goal, confirmed_decisions, current_topic)

**问题**:
- ❌ 无 ProductIntent
- ❌ 无 requirement 分析
- ❌ 无 PRD 生成
- ❌ 只返回模板，不执行真实生产

### 路径 B: WebUI Session (系统 B)

```
User Input "我想做一个飞机大战小游戏"
  ↓
HTTP POST /api/sessions/{session_id}/messages
  ↓
file:7447 (fastapi_adapter.py)
  ↓
session._dispatch(line)
  ↓
ConversationManager.handle(line)
  ↓
IntentParser.parse() → 60+ intents
  ↓
ProductIntent 流程 (DISCOVERY → CONFIRMATION)
  ↓
create_product action → product.json
  ↓
next_action="prd" → generate_prd action
  ↓
ProductIntent → PRD.md
```

**状态存储**: `ConversationManager.product_intent` + `ConversationManager.state`

**完整功能**: 是

---

## 二、双轨制 - 核心架构缺陷

### 发现 #1: 两套系统完全不互通

| 维度 | 系统 A (conversation_os) | 系统 B (session) |
|------|--------------------------|------------------|
| 入口 | `/api/conversations/*` | `/api/sessions/*` |
| Intent | 4 种 (DISCUSS/DECIDE/APPROVE/EXECUTE) | 60+ intents |
| State | conv["state"] 字典 | ConversationManager.state + product_intent |
| Product | ❌ 无 | ProductIntent (problem/user/platform/core_features) |
| PRD | ❌ 无 (只返回模板) | generate_prd → PRD.md |
| 代码量 | 505 行 | 4000+ 行 |

**ROOT CAUSE #1**: 双轨制导致用户输入可能被任意一系统处理，结果不可预测。

### 检查: 两个系统是否互通?

```bash
grep -rn "conversation_os\|ConversationManager" /factory-console/session/
# 结果: 无互通代码
```

**结论**: 两个系统是 **完全独立的代码库**，没有桥接。

---

## 三、Source of Truth 分析

### 3.1 Conversation Source of Truth

| 存储位置 | 所属系统 | Authority |
|----------|----------|-----------|
| entity store: conv.json | 系统 A | ✅ Valid |
| ConversationManager.state | 系统 B | ✅ Valid |

**问题**: 两个独立的 Conversation Source of Truth，无主从关系。

### 3.2 Product Source of Truth

| 存储位置 | 所属系统 | Authority |
|----------|----------|-----------|
| 无 | 系统 A | ❌ 不存在 |
| projects/{slug}/product.json | 系统 B | ✅ Valid |
| ConversationManager.product_intent | 系统 B | ✅ Valid (运行时) |

**问题**: 
- 系统 A 完全不知道 Product 是什么
- 系统 B 有完整的 ProductIntent 模型

### 3.3 PRD Source of Truth

| 存储位置 | 所属系统 | Authority |
|----------|----------|-----------|
| 只返回模板 | 系统 A | ❌ 无 |
| projects/{slug}/PRD.md | 系统 B | ✅ Valid |

---

## 四、Idea → Requirement → PRD → Plan 真实链路

### 当前实际路径 (仅系统 B)

```
用户输入 (session)
  ↓
ConversationManager.handle()
  ↓
intent = create_product (关键词匹配)
  ↓
ConversationManager.handle_product_answer() [DISCOVERY 状态]
  ↓
逐轮追问: 问题 → 用户 → 目标用户 → 核心功能
  ↓
ProductIntent 填充完成 → transition(PRODUCT_CONFIRMATION)
  ↓
用户确认 → create_product action
  ↓
Project + product.json 落盘
  ↓
next_action="prd" → generate_prd action
  ↓
ProductIntent.from_dict(product.json)
  ↓
ProductDocument.from_product_intent()
  ↓
PRD.md 落盘
```

**但是**: 
1. **这个链路只在 `/api/sessions/*` 路径生效**
2. **用户通过 `/api/conversations/*` 发送消息时，完全不经过此链路**

---

## 五、Context 连续性分析

### 5.1 系统 A (conversation_os) Context

```python
# conversation_os.py:138-154
state = conv.get("state", {})  # 从 conv 读取
# 更新:
state["confirmed_decisions"] = state.get("confirmed_decisions", []) + [message]
state["current_topic"] = _topic_of(message)
# 存储:
conv["state"] = state
store_entity(root, conv)
```

**问题**:
- 只有 3 个字段: `goal`, `confirmed_decisions`, `current_topic`
- **无 Product 概念**
- **无 Requirement 概念**
- **无 PRD 概念**

### 5.2 系统 B (Session) Context

```python
# session/conversation.py:361-428
self.product_intent: Optional[ProductIntent] = None
self.state: ConversationState  # DISCOVERY → CONFIRMATION → ...
```

**字段**:
- ProductIntent: name, problem, user, platform, core_features
- ConversationState: DISCOVERY / CLARIFICATION / PRODUCT_CONFIRMATION / ...

**优点**: 足够完整

**问题**: 
1. 只能在系统 B 使用
2. 前端如果走错了入口，就丢失 Context

---

## 六、PRD Generation 分析

### 6.1 generate_prd action (系统 B 独有)

```python
# actions.py:511-595
def generate_prd(context: ExecutionContext) -> ActionResult:
    product, slug, projects_root = _locate_product(context, scan_fallback=False)
    
    # 检查必填字段
    missing = product.missing_fields()
    if missing:
        return ActionResult(ok=False, status=STATUS_ERROR, 
            message=f"产品信息不完整, 缺失: {detail}")
    
    # PRD 生成
    prd_text = ProductDocument.from_product_intent(product)
    
    # 落盘
    _contract_set_artifact(root=context.workspace, project_id=slug, 
        artifact_type="prd", raw_text=prd_text, file="PRD.md")
```

**关键发现**:
- ✅ PRD 真正从 ProductIntent 生成
- ✅ 有完整性检查
- ✅ 落盘到 projects/{slug}/PRD.md
- ❌ **只在系统 B 可用**

### 6.2 系统 A 的 PRD

```python
# conversation_os.py: 无 PRD 相关代码
# 只返回模板:
return {"text": f"...", "status": "WILL_EXECUTE", 
        "card": _make_card("execution", message, target, confirmed)}
```

---

## 七、Root Causes 优先级排序

### ROOT CAUSE #1: 双轨制架构

**名称**: 两套独立会话系统完全不互通

**证据**:
- `/api/conversations/*` → conversation_os (505 行)
- `/api/sessions/*` → session/ (4000+ 行)
- 无任何桥接代码

**真实代码**:
- `fastapi_adapter.py:6571` → conversation_os.send_message()
- `fastapi_adapter.py:7447` → session._dispatch()

**为什么导致问题**:
> 用户发送的每条消息可能被任一系统处理，导致：
> - 同样的输入在不同时间得到完全不同的响应
> - PRD 生成只在系统 B 可用，系统 A 无法触发
> - Context 无法跨越两个系统

**影响**: P0 - 整个产品定义流程

**属于**: Architecture

---

### ROOT CAUSE #2: 系统 A 缺乏 Product Model

**名称**: conversation_os 完全不知道 Product 是什么

**证据**:
```python
# conversation_os.py:182-183
state = conv.get("state", {})
goal = state.get("goal", "")  # 只是一个 string
```

**为什么导致问题**:
- 无 ProductIntent
- 无法执行 requirement 分析
- 无法生成 PRD

**影响**: P0

**属于**: State / Product Model Missing

---

### ROOT CAUSE #3: 系统 A 无 PRD/Plan 生成能力

**名称**: conversation_os 只返回模板，不执行真实生产

**证据**:
```python
# conversation_os.py:202-246
if intent == "EXECUTE":
    return {"text": f"明白,目标是「{target}」...", 
            "status": "WILL_EXECUTE", "card": _make_card("execution", ...)}
```

对比系统 B:
```python
# router.py:28
"generate_prd": "generate_prd"
# actions.py:511-595
def generate_prd(context):
    prd_text = ProductDocument.from_product_intent(product)
    _contract_set_artifact(artifact_type="prd", raw_text=prd_text)
```

**影响**: P0

**属于**: PRD Pipeline Broken

---

### ROOT CAUSE #4: 缺少统一 Context Provider

**名称**: 无单一入口决定使用哪套系统

**证据**:
- WebUI 同时暴露两个 API 端点
- 前端可能调用错误
- 无重定向逻辑

**影响**: P1

**属于**: Architecture

---

### ROOT CAUSE #5: Frontend 可能泄漏业务状态

**证据**:
```typescript
// state/workspace.tsx
export interface WorkspaceProject {
  id: string;
  name: string;
  // ...
}
setProject: (project: WorkspaceProject | null) => void;
```

**问题**: Frontend 存储 project 状态，如果与 Backend 不一致会导致问题

**影响**: P2

**属于**: Frontend State Leak

---

## 八、Root Cause Chain

```
用户输入
    ↓
选择错误入口 (/api/conversations/* or /api/sessions/*)
    ↓
如果 → /api/conversations/*:
    ↓
    conversation_os 处理
    ↓
    state 只有 goal/confirmed_decisions/current_topic
    ↓
    无 ProductIntent → 无法生成 PRD
    ↓
    返回模板 → 用户感到"AI 不懂我"
    
如果 → /api/sessions/*:
    ↓
    session 处理
    ↓
    有 ProductIntent → 生成 PRD
    ↓
    正常
```

**关键问题**: 用户无法控制走哪个入口，系统也没有自动路由。

---

## 九、Minimal Corrective Boundary

回答 Q10: "如果今天不允许增加任何新功能，只允许修改现有代码，最少需要改变哪几个根节点，才能让 Idea → Requirement → PRD → Plan 真正工作？"

### 方案: 统一入口 + 桥接

1. **修改 conversation_os.py** - 集成系统 B 的 Product/PRD 能力
   - 或: 
2. **修改 fastapi_adapter.py** - 将 /api/conversations/* 请求重定向到 session 系统
   - 或:
3. **修改 WebUI** - 只使用 /api/sessions/* 入口，废弃 conversation API

**最简单的修复**: 修改 `conversation_os.py`，让它调用 `session/ConversationManager` 的能力。

**但是**: 这需要大量重构，因为两套系统设计理念完全不同。

---

## 十、回答用户的 10 个关键问题

### Q1: 为什么用户自然语言不能连续表达 Idea？

**根因**: 
- 系统 A 只存储 `goal` (string)，无结构化 Product Intent
- 用户无法积累结构化的 product 信息

### Q2: 为什么第二句话经常不能正确继承第一句话？

**根因**:
- 系统 A 的 `state["confirmed_decisions"]` 只是简单 append
- 无 ProductIntent 概念，无法正确关联
- 如果走错系统，Context 完全丢失

### Q3: 为什么系统会机械地进入固定阶段？

**根因**:
- 系统 A 只有 4 种 Intent，过于简单
- 系统 B 有状态机但只在 `/api/sessions/*` 可用

### Q4: 为什么 AI 有时候会错误理解用户意图？

**根因**:
- 系统 A 的 Intent 检测是简单正则匹配
- 系统 B 的 KeywordIntentParser 也是硬编码规则
- 无真正 NLP 理解

### Q5: 为什么 Requirement → PRD → Plan 之间可能出现语义断裂？

**根因**:
- PRD 确实从 ProductIntent 生成 (系统 B)
- 但如果用户经过系统 A，PRD 不存在
- 两套系统数据不互通

### Q6: 当前真正的 Product Source of Truth 是什么？

**答案**: 
- **系统 B**: `projects/{slug}/product.json` (ProductIntent 序列化)
- **系统 A**: 无 Product Source of Truth

### Q7: 当前真正的 Conversation Source of Truth 是什么？

**答案**: 
- **系统 A**: entity store conv.json
- **系统 B**: Session object (内存) + SessionStore

### Q8: 当前真正的 Project Scope Source of Truth 是什么？

**答案**: 
- `projects/{slug}/project.json` (系统 B)
- Frontend URL hash `#/workspace?project=id`

### Q9: 到底有多少套旧逻辑仍然参与生产路径？

**答案**: 
- 至少 **2 套独立系统** (conversation_os vs session)
- 多个残留: 
  - `_ACTIVE_WORK_PROMPT` (已在本次 Kernel Inversion 中禁用)
  - 38 个 tool dispatch (agent_loop.py)
  - 多个 Intent Parser 实现

### Q10: 最少需要改变什么让 Idea → PRD → Plan 工作？

**答案**: 
1. 统一会话入口 (废弃或桥接 conversation_os)
2. 让所有用户请求都经过系统 B
3. 或在 conversation_os 中集成 ProductIntent 支持

---

## 十一、What NOT to Change

根据用户要求，本轮不执行：
- ❌ 修改业务代码
- ❌ 新增功能
- ❌ 架构美化
- ❌ 创建新 Runtime
- ❌ 创建新 Product 模块
- ❌ 修改 Prompt
- ❌ 修测试

---

## 十二、Recommended Fix Order

如果用户决定修复，优先级：

1. **P0**: 统一会话入口 (修改 fastapi_adapter 或 WebUI)
2. **P0**: conversation_os 集成 ProductIntent 或重定向到 session
3. **P1**: 消除双 Source of Truth
4. **P2**: 清理残留 Legacy 代码

---

## 十三、总结

### 当前 Reality Architecture

```
User Input
  ↓
[选择入口 - 随机/不可控]
  ↓
/api/conversations/* → conversation_os (系统 A)
  ↓
Intent: 4 种 (DISCUSS/DECIDE/APPROVE/EXECUTE)
  ↓
State: {goal, confirmed_decisions, current_topic}
  ↓
Response: 模板
  ↓ [如果想生成 PRD]
  ❌ 不支持

OR

/api/sessions/* → session (系统 B)
  ↓
Intent: 60+ (create_product, generate_prd, etc.)
  ↓
ConversationManager + ProductIntent
  ↓
Requirement Analysis (多轮 DISCOVERY)
  ↓
create_product → product.json
  ↓
generate_prd → PRD.md
  ↓
✅ 支持
```

### Desired Architecture

```
User Input
  ↓
[统一入口]
  ↓
ConversationManager
  ↓
ProductIntent (DISCOVERY 多轮)
  ↓
Requirement Analysis Node
  ↓
PRD Generation
  ↓
Development Plan Generation
  ↓
Production Runtime
```

### Gap

- ❌ 统一入口 (双轨制)
- ❌ 跨系统数据桥接
- ❌ Frontend 入口管理

---

**报告结束**

本次扫描发现了核心架构问题：**双轨制导致用户在 Idea → PRD 流程中存在不可预测性**。这不是简单的代码质量问题，而是架构设计问题。需要统一会话系统才能解决。