# S10-046 Task 003 — Slash Command System Design

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 设计, 未修改代码
> 核心: Slash 不是新命令系统 — 是 Interactive Session Shortcut

---

## 1. 定位

```
/run  ≠  新的执行引擎
/run  ==  Interactive Session 内的快捷入口 → Command Router → 现有 Service

Slash Command
    ↓
Command Router (解析 + 上下文注入)
    ↓
Existing Service (exec.cli / org.cli / ControlPlane)
```

## 2. Slash Command 完整列表

| Slash | 等价 | 作用 | 上下文注入 |
|---|---|---|---|
| `/help` | `factory --help` | 帮助/用法 | — |
| `/project` | `factory project` | 项目列表/切换 current | current=选定 |
| `/agent` | `factory agent` | Agent 列表/选择 | current_agent |
| `/skill` | `factory skill` | Skill 列表 | — |
| `/provider` | (providers 管理) | Provider 选择 | current_provider |
| `/router` | `factory router` | Router 决策查看 | current_provider |
| `/task` | `factory task` | 任务列表 | current_project |
| `/run` | `factory run` | 执行任务 | project/agent/provider |
| `/demo` | `factory demo run` | 一键演示 | — |
| `/config` | `factory config` | 配置查看/设置 | — |
| `/log` | (logs) | 会话/执行日志 | — |
| `/audit` | `factory audit` | 审计查询 | — |
| `/cost` | (usage 统计) | 成本查看 | — |
| `/status` | `factory status` | 系统状态 | — |
| `/session` | — | 会话状态(show/reset) | — |
| `/clear` | — | 清屏 | — |
| `/exit` | — | 退出会话 | — |

## 3. 路由规则

```
用户输入 "/run --objective 'X'"
  ↓
[1] 解析: slash="run", args=["--objective", "X"]
[2] 上下文注入: project=current_project, agent=current_agent (若未显式给)
[3] 路由: Command Router → run_cmd (现有 CLI 函数) — 复用, 不重写
[4] 输出: Renderer 渲染 (同一输出层)
```

## 4. 与 Command Mode 的一致性

| 方面 | Command Mode | Slash | 一致性 |
|---|---|---|---|
| 参数语法 | argparse | 同 argparse | ✅ 同一 parser 规则 |
| 服务调用 | Service Layer | 同 Service Layer | ✅ 同一函数 |
| 输出格式 | Renderer | 同 Renderer | ✅ 同一渲染 |
| exit code | 0/1/2 | 显示状态 | ✅ 语义相同 |

**实现建议: Slash 路由 = 复用 argparse 子解析器 + 注入 current_* 到 Namespace。**

## 5. 无参数 Slash 行为

```
/project        → 列出项目 + 显示 current
/project <id>   → 切换 current_project = <id>
/agent          → 列表 + current
/agent backend-1 → 切换
/provider       → 列表 + current
```

**Slash 双态: 无参=查看, 有参=设置/执行。**

## 6. 边界

- 不新增命令系统: Slash 只映射到现有命令
- 未知 Slash → 提示可用列表(不静默)
- `/` 开头未匹配 → 当作自然语言交给 Intent Layer(Task 004)
- 禁止: Slash 内实现业务逻辑(全部在 Service Layer)

---

> Task 003 完毕 | 17 个 Slash | 双态(查看/设置) | 复用 argparse + Service Layer
