"""factory-console/session/session.py — InteractiveSession 交互会话主循环 (S10-047 Task 001)。

设计: docs/sprint10/S10-047-session-design.md §2 Session Loop
- 纯内置 input(), 零新依赖 (高级交互后续可加 prompt_toolkit, 非本 Sprint)
- banner → loop ("> " 提示符) → exit/quit/Ctrl+C/EOF 优雅退出, rc 0
- 输入分发 (Task 003/004 集成): "/" 开头 → slash registry (SlashCommand 注册式);
  否则 → 未知提示 (后续 Task 接 Intent 分发)
- 会话上下文 (Task 002): ContextManager 注入, 输入记录进 history (/cost 等数据来源)
- 纯 shell 零业务逻辑, 不接真实 LLM, 不改现有命令
"""

from __future__ import annotations

import sys
from typing import Optional

from .commands import build_default_registry
from .context import ContextManager, SessionContext
from .slash import SlashCommandRegistry

#: 会话 banner (v0.2 — AI Workforce Operating System 命名空间)
BANNER = (
    "AI Factory v0.2 / AI Workforce Operating System\n"
    "输入 exit 或 quit 退出会话; Ctrl+C / Ctrl+D 亦可。"
)

#: 退出命令集合 (匹配即优雅退出)
EXIT_COMMANDS = frozenset({"exit", "quit"})

#: 未知输入提示前缀 (dispatch 占位, 后续 Task 接 Slash/Intent)
UNKNOWN_PREFIX = "未知命令: "


class InteractiveSession:
    """交互会话主循环 (session shell) — Task 001 循环 + Task 003/004 slash 集成。"""

    def __init__(
        self,
        prompt: str = "> ",
        banner: Optional[str] = None,
        context_manager: Optional[ContextManager] = None,
        registry: Optional[SlashCommandRegistry] = None,
    ) -> None:
        self.prompt = prompt
        self.banner_text = banner if banner is not None else BANNER
        self.running = False
        #: 会话上下文 (Task 002) — slash 命令读写的统一上下文
        self.context_manager = context_manager or ContextManager()
        #: slash 注册表 (Task 003/004) — 默认装配基础命令; 可注入定制
        self.registry = (
            registry if registry is not None else build_default_registry(session=self)
        )

    @property
    def context(self) -> SessionContext:
        """当前会话上下文 (ContextManager 内存单例视图)。"""
        return self.context_manager.get()

    def run(self) -> int:
        """启动会话: 打印 banner → 循环读取输入 → 优雅退出返回 0。

        - exit/quit → 退出
        - 空输入 → 继续 (不退出)
        - Ctrl+C (KeyboardInterrupt) / Ctrl+D (EOFError) → 优雅退出
        - "/" 开头 → slash registry 分发 (/help /status /project /cost /exit 等)
        - 其它输入 → 未知提示 (不崩溃; 后续 Task 接 Intent)
        """
        self._banner()
        self.running = True
        while self.running:
            try:
                line = input(self.prompt)
            except (EOFError, KeyboardInterrupt):
                print()  # 换行, 避免提示符残留在行尾
                break
            cmd = line.strip()
            if cmd in EXIT_COMMANDS:
                self.running = False
            elif not cmd:
                continue  # 空输入
            else:
                self.context_manager.record(cmd)
                self._dispatch(cmd)
        return 0

    def _banner(self) -> None:
        """打印欢迎横幅 (验收: 显示 AI Factory)。"""
        print(self.banner_text)

    def _dispatch(self, line: str) -> None:
        """命令分发 (Task 003/004 集成): "/" 开头 → slash registry; 否则 → 提示。

        未知 slash → registry 明确提示 (含 /help 指引); 非 slash → 未知命令提示
        (Intent 分发为后续 Task)。
        """
        if line.startswith("/"):
            self.registry.execute(line, self.context)
        else:
            print(f"{UNKNOWN_PREFIX}{line} — 功能开发中, 输入 exit 或 quit 退出")


def main(argv: list[str] | None = None) -> int:
    """模块入口 (python -m 或直接调用): 启动交互会话。"""
    return InteractiveSession().run()


if __name__ == "__main__":
    sys.exit(main())
