# S10-046 Task 002 — CLI vs Interactive Terminal Architecture

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 架构设计, 未修改代码
> 核心原则: 一个 CLI, 两种模式, 共享 Service Layer, 禁止第二套执行系统

---

## 1. 三个概念定义

| 概念 | 定义 | 示例 |
|---|---|---|
| **CLI (Command Mode)** | 单条命令, 一次性执行, 适合脚本/CI/明确操作 | `factory run --objective "..."` |
| **Terminal** | 交互式会话界面, 保持上下文, 适合探索/多步操作 | `factory`(进入会话) |
| **Session** | 交互会话中的状态容器(current project/agent/conversation) | 会话内 `/project` 切换 |

## 2. 架构图

```
                      factory
                         |
            ┌────────────┴────────────┐
            |                         |
    Command Mode               Interactive Session
    (factory xxx)              (factory — 进入)
            |                         |
            |   ┌─────────────────────┘
            |   |
            |   |  Slash Command      Intent Layer      Session Context
            |   |  (/run, /project)   ("帮我做X")        (current project...)
            |   |
            └───┴─────────────────────┘
                        |
                 Same Service Layer
                        |
              ┌─────────┼──────────┐
              |         |          |
      Execution     Project     ControlPlane
      (exec CLI)    (org CLI)   (providers/config)
              |         |          |
        Agent / Skill / Router / Runtime
```

## 3. 何时用什么?

| 场景 | 用哪种 | 理由 |
|---|---|---|
| 脚本/CI/自动化 | Command Mode | 单条、可编程、exit code |
| 明确单步操作 | Command Mode | `factory run --objective "..."` 快速 |
| 探索/学习 | Interactive Session | 有上下文, 可试错, 有补全 |
| 多步工作流 | Interactive Session | 保持 current project/agent |
| 自然语言意图 | Interactive Session | Intent Layer 只在会话内 |
| 远程/无终端 | Command Mode | SSH/容器中不可交互 |

## 4. 共享 Service Layer(关键)

```
Command Mode:    factory run --objective "X"
                    → 解析 → ServiceLayer.run(objective="X")
Interactive:     /run --objective "X"   或   "帮我做X"
                    → Slash/Intent → ServiceLayer.run(objective="X")

两条路最终调用同一 Service Layer — 不创建第二套执行系统。
```

**约束:**
- 所有新入口(Slash/Intent)只做"参数解析 + 上下文注入", 业务逻辑全部在 Service Layer
- Service Layer = 现有 exec.cli / org.cli / ControlPlane 能力(薄代理复用)
- 禁止: 在交互模式内重新实现 run/project 等执行逻辑

## 5. 会话内上下文注入

```
Interactive Session 持有:
  current_project / current_agent / current_provider / recent_tasks

/run --objective "X"      → ServiceLayer.run(project=current_project, agent=current_agent, ...)
"给当前项目加测试"          → Intent → 注入 current_project → ServiceLayer
```

**这就是交互模式的价值: 用户不用重复指定 context, 系统记住。**

## 6. 迁移路径(向后兼容)

```
v0.2:  factory 无参数 → 进入 Interactive Session (新增)
       factory xxx → 完全不变 (Command Mode 兼容)
       /run → 会话内调 ServiceLayer (与 factory run 同源)
```

---

> Task 002 完毕 | 一 CLI 两模式 | 共享 Service Layer | 交互模式注入会话上下文
