# S10-050 — AI Product Manager Loop

> 日期:2026-08-15 | Sprint: S10-050 | 架构 + 流程 + 验证
> 状态: 实现完成, 真实流程验证通过

---

## 1. 为什么 AI Factory 需要 Product Manager Layer

用户不是来执行任务的。用户通常只有:
- "我想做一个 APP"
- "我有一个创业想法"
- "我想解决某个问题"

AI Factory 需要先像产品经理一样: **理解需求 → 澄清问题 → 形成 Product Intent → 创建 Project → 生成后续工程流程**。

没有 Product Manager Layer, 用户必须自己知道 project/task/agent — 门槛高, 违背 "AI Workforce Operating System" 定位。
有了它, 用户只需要表达想法。

## 2. 架构

```
User Idea ("我想开发一个台球计分APP")
    ↓
IntentParser → create_product intent
    ↓
Conversation DISCOVERY (多轮追问)
    ├─ "这个产品解决什么问题?" → problem
    ├─ "目标用户是谁?" → user
    ├─ "核心功能有哪些?" → core_features
    └─ "运行平台?" → platform (可选)
    ↓
ProductIntent 完整 (draft)
    ↓
PRODUCT_CONFIRMATION (产品摘要 + 确认 y/N)
    ↓
create_product action
    ├─ 桥接 create_project (org register, 复用)
    ├─ product.json 落盘 (projects/<slug>/product.json)
    └─ "Product Created: X — Ready for Engineering."
    ↓
(未来) PRD → Architecture → Task Generation → Agent Execution
```

## 3. ProductIntent 模型

```python
@dataclass
class ProductIntent:
    name: str | None        # "ScorePocket" (缺省临时名)
    problem: str | None     # "台球比赛记录困难"
    user: str | None        # "台球爱好者"
    platform: str | None    # "mobile" | "web" | "desktop"
    core_features: list[str]  # ["计分", "比赛记录"]
    status: str = "draft"   # draft → project_created
    raw: str                # 原始输入 (审计)
    session_id: str | None

    REQUIRED_FIELDS = ("problem", "user", "core_features")
```

**IntentObject vs ProductIntent**: IntentObject 回答 "用户想执行什么"; ProductIntent 回答 "用户想创造什么" — 是产品级结构化资产(未来 PRD/Architecture/Task Generation 基础)。

## 4. 真实验证流程(2026-08-15)

```
> 我想开发一个台球计分APP
> 这个产品解决什么问题? → 台球比赛记录困难
> 目标用户是谁? → 台球爱好者
> 核心功能有哪些? → 计分,比赛记录
> 产品: 未命名产品-xxx / 问题: ... / 目标用户: ... / 核心功能: ...
> 确认创建这个产品? (y/N) → y
> Product Created: 未命名产品-xxx — Ready for Engineering.

落盘:
  ~/.factory/projects/<slug>/product.json
    {name, problem, user, core_features, status: "project_created", raw}
  org 项目注册 (project_baselines.json 等)
```

## 5. 模块

| 模块 | 职责 | 状态 |
|---|---|---|
| product.py | ProductIntent 模型 + 临时名 + 特征解析 | ✅ |
| intent.py | +create_product 关键词 (我想/开发一个APP/产品/想法) | ✅ |
| actions.py | +create_product action (桥接 create_project) | ✅ |
| router.py | create_product 映射 | ✅ |
| conversation.py | DISCOVERY 多轮 + PRODUCT_CONFIRMATION + PROJECT_CREATION | ✅ |
| context.py | +product_intent 字段 | ✅ |
| session.py | 产品流程集成 | ✅ |

## 6. 测试

```
新增: test_session_product.py 90 测试
覆盖: ProductIntent 模型/临时名/intent 解析/action 桥接/多轮追问/缺失字段/确认/重置/Context/回归
全量: 8480 passed, 0 failed (基线 8390 → +90, 零回归)
```

## 7. 未来扩展

```
PRD Generation:   ProductIntent → 结构化 PRD (markdown)
Architecture:     ProductIntent → 技术架构建议
Task Generation:  core_features → 工程任务分解 → run_task
多轮深化:         platform 追问 + 命名建议
LLM 版:           LLMIntentParser 理解更复杂想法 (v0.3)
```

## 8. 边界

- Conversation 产出结构化产品资产(不是聊天)
- create_product 桥接复用 create_project(零复制业务)
- 新增能力走 Intent/Action/Service 体系(不破坏 Kernel)
- Core 零改动(ExecutionLoop/Router/AgentRuntime/Provider 未触碰)

---

> S10-050 文档完毕 | Product Manager Loop 落地 | 90 新测试 | 真实流程验证通过
