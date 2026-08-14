# S10-047 Task 001 — Interactive Session Runtime 设计

> 日期:2026-08-14 | Sprint: S10-047 Workforce Terminal | 设计 + 实现前置审查
> 目标: 新增 factory 无参数 → Interactive Session(session shell, 不接真实 LLM)

---

## 1. 集成点(审查确认)

```
main(argv)  →  build_parser() → parse_args → FactoryCLI.run(args)

改造:
  无参数 (factory / factory interactive):
    → 进入 InteractiveSession.run() (session shell)
  有参数 (factory run ...):
    → 完全不变 (兼容 v0.1.0)
```

## 2. Session Loop

```python
class InteractiveSession:
    def run(self) -> int:
        self._banner()
        while self.running:
            try:
                line = input("> ")          # prompt
            except (EOFError, KeyboardInterrupt):
                print(); break               # Ctrl+D / Ctrl+C → 退出
            cmd = line.strip()
            if cmd in ("exit", "quit"):      # 退出命令
                self.running = False
            elif not cmd:
                continue                      # 空输入
            else:
                self._dispatch(cmd)           # → Slash / Intent (后续 Task)
        return 0
```

## 3. 文件位置(新目录)

```
factory-console/session/            (新包: 交互会话)
  __init__.py
  session.py        — InteractiveSession (loop)
  context.py        — SessionContext + ContextManager (Task 002)
  slash.py          — SlashCommandRegistry (Task 003)
  commands.py       — 基础 slash 命令 (Task 004)
  intent.py         — IntentObject + IntentParser (Task 005)
  renderer.py       — Renderer 接口 (Task 006)
  completion.py     — CompletionProvider (Task 007)
```

> 独立新包, 不侵入现有 cli_factory.py 逻辑; main 只加一个分支。

## 4. 本次实现范围(Task 001)

- [x] InteractiveSession 骨架(loop/exit/quit/Ctrl+C)
- [x] banner 显示 (AI Factory v0.2 ...)
- [x] _dispatch 占位(未知输入 → 提示, 后续接 Slash/Intent)
- [ ] 不接真实 LLM
- [ ] 不改现有命令

## 5. 测试

```
tests/console/test_session_runtime.py:
  - session 启动 (banner 含 "AI Factory")
  - exit/quit → 退出 (rc 0)
  - 空输入 → 继续
  - 未知输入 → 提示 (不崩溃)
  - Ctrl+C/EOF → 优雅退出
```

## 6. 边界

- 纯 session shell, 零业务逻辑(dispatch 后续接 Service Layer)
- 不引入依赖(prompt 用内置 input; 高级交互后续可加 prompt_toolkit, 非本 Sprint)
- 不修改现有命令

---

> Task 001 设计完毕 | 集成点: main 无参数分支 | 新包 factory-console/session/ | 纯 shell 零逻辑
