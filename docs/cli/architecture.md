# CLI Architecture — AI Factory

> 位置: docs/cli/architecture.md | Sprint: S10-047 | CLI v0.2 演进方向

---

## 1. 架构总览

```
factory (单入口)
  │
  ├── Command Mode (有参数)          ← v0.1 兼容
  │     factory run / project / demo ...
  │
  └── Interactive Session (无参数)    ← v0.2 新增
        ├── Slash Command Registry   (/help /status /project /cost /exit)
        ├── Intent Layer             (KeywordIntentParser → IntentObject)
        ├── Session Context          (内存: current project/agent)
        ├── Completion Provider      (Slash 补全, 未来扩展)
        └── Renderer                 (Human / JSON)
              │
              └── Same Service Layer (exec/org/ControlPlane)
                    │
                    └── Core (Agent/Router/Runtime/Provider — 冻结)
```

## 2. 模块清单(session 包)

| 模块 | 职责 | 状态 |
|---|---|---|
| session.py | InteractiveSession (loop/dispatch) | ✅ |
| context.py | SessionContext + ContextManager | ✅ |
| slash.py | SlashCommand(ABC) + Registry | ✅ |
| commands.py | /help /status /project /cost /exit | ✅ |
| intent.py | IntentObject + IntentParser(ABC) + Keyword mock | ✅ |
| renderer.py | Renderer(ABC) + Human/Json | ✅ |
| completion.py | CompletionProvider(ABC) + Slash 补全 | ✅ |

## 3. 分层原则(不可违反)

```
1. CLI 不包含业务逻辑
   CLI (解析/展示) → Service Layer (业务) → Core (执行)
   新入口 (Slash/Intent) 只做"解析 + 上下文注入", 调同一 Service

2. 禁止第二套执行系统
   /run == factory run == ServiceLayer.run — 同一函数

3. Core 冻结
   ExecutionLoop / AgentRuntime / Router / Provider / Kernel 零改动

4. 向后兼容
   v0.1 全部命令永不变; 新能力是"加法"
```

## 4. 演进路线

| 版本 | 能力 | 状态 |
|---|---|---|
| v0.1 | Command Mode (17+ 命令) | ✅ 发布 |
| v0.2 | Interactive Session + Slash + Context + Intent(基础) + Completion(基础) | 🔄 本 Sprint |
| v0.3 | Intent(LLM) + Memory + 多轮对话 + 更多 Slash | 🔮 |
| v1.0 | Organization + Governance + 全会话化 | 🔮 |

## 5. 关键决策记录

| # | 决策 | 理由 |
|---|---|---|
| D1 | 无参数 → Session, 有参数 → Command | 不破坏脚本; 交互是加法 |
| D2 | 内置 input (非 prompt_toolkit) | 零依赖; 高级交互后续评估 |
| D3 | Intent 不生成 shell 命令 | 安全: 结构化对象 + Policy 验证 |
| D4 | Session Context 内存实现 | v0.2 简单; 持久化后续加 |
| D5 | Renderer 纯函数 (dict→text) | 输出与逻辑解耦; --json 统一 |

---

> CLI v0.2 架构完成 | 一 CLI 两模式 | Service Layer 单一来源 | Core 冻结
