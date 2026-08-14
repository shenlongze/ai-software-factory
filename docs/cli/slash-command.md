# Slash Command — AI Factory CLI

> 位置: docs/cli/slash-command.md | Sprint: S10-047 | CLI v0.2

---

## 什么是 Slash Command

Interactive Session 内的快捷命令。**不是新命令系统** — 是现有 Service 的快捷入口。

```
Slash Command (/run)
    ↓
Command Router (解析 + 上下文注入)
    ↓
Existing Service (exec/org/ControlPlane)
```

## 可用命令(v0.2 基础版)

| Slash | 作用 | 参数 |
|---|---|---|
| `/help` | 显示可用命令 | — |
| `/status` | 会话状态 (session/workspace/项目/Agent) | — |
| `/project` | 项目列表/切换当前项目 | `[<id>]` |
| `/cost` | 成本/用量信息 (占位) | — |
| `/exit` | 退出会话 | — |

## 使用示例

```
> /help                    # 列出命令
> /status                  # 查看会话状态
> /project                 # 项目列表
> /project P-xxx           # 切换当前项目
> /exit                    # 退出
```

## 设计

### 注册式(无硬编码 if)

```python
class SlashCommand(ABC):
    name: str
    description: str
    def execute(self, args: str, context: SessionContext) -> int: ...

class SlashCommandRegistry:
    def register(self, cmd: SlashCommand) -> None: ...
    def get(self, name: str) -> SlashCommand | None: ...
    def list(self) -> list[SlashCommand]: ...
    def execute(self, line: str, context) -> int: ...
```

### 双态语义

```
/project        → 无参 = 查看列表
/project <id>   → 有参 = 切换 current_project
```

### 未来扩展

| Slash | 状态 |
|---|---|
| /agent /skill /provider /router | 🔮 v0.3 |
| /task /run /demo /config /log | 🔮 v0.3 |
| /audit /session /clear | 🔮 v0.3 |

## 原则

- 未知 Slash → "未知命令: /xxx — 输入 /help"
- Slash 内不实现业务逻辑(全部在 Service Layer)
- 参数语法与 Command Mode 一致(argparse 规则)

---

> Slash Command v0.2 基础版完成(5 命令) | 注册式设计
