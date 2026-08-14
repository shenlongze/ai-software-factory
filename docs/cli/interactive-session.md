# Interactive Session — AI Factory CLI

> 位置: docs/cli/interactive-session.md | Sprint: S10-047 | CLI v0.2 演进

---

## 什么是 Interactive Session

输入 `factory`(无参数)进入 AI 交互会话 — AI Workforce Operating System Terminal。

```
AI Factory v0.2 / AI Workforce Operating System
输入 exit 或 quit 退出会话; Ctrl+C / Ctrl+D 亦可。
>
```

## 入口

```bash
factory            # 无参数 → Interactive Session
factory run ...    # 有参数 → Command Mode (完全不变, 兼容 v0.1.0)
```

## 会话能力

| 能力 | 说明 | 状态 |
|---|---|---|
| Session Loop | 输入→解析→分发→渲染 | ✅ v0.2 |
| Slash Command | /help /status /project /cost /exit | ✅ v0.2 |
| Session Context | current project/agent 记忆(内存) | ✅ v0.2 |
| Intent Layer | 自然语言→IntentObject(Keyword mock) | 🔄 基础版 v0.2 |
| Completion | TAB 补全接口 | 🔄 基础版 v0.2 |
| LLM Intent | 真实自然语言理解 | 🔮 v0.3 |

## 退出方式

```
exit / quit          — 命令退出
Ctrl+C               — 中断
Ctrl+D (EOF)         — 退出
```

## 架构

```
factory
 ├── Command Mode (有参数 — 脚本/CI)
 └── Interactive Session (无参数)
      ├── Slash Command → Registry → Service Layer
      ├── Intent → Parser → IntentObject → (未来) Policy → Service
      ├── SessionContext (内存)
      └── Renderer (Human/JSON)
           ↓
      Same Service Layer (exec/org/ControlPlane — 零复制)
```

## 设计原则

1. 一 CLI 两模式, 共享 Service Layer
2. Slash/Intent 只是入口, 业务逻辑全在 Service
3. 不创建第二套执行系统
4. 向后兼容: v0.1 命令永不变

---

> Interactive Session v0.2 基础版完成 | 详见 architecture.md
