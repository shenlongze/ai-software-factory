"""factory-console/session/session.py — InteractiveSession 交互会话主循环 (S10-047 Task 001 + S10-048 P1)。

设计: docs/sprint10/S10-047-session-design.md §2 Session Loop
     + docs/sprint10/S10-048-intent-kernel-design.md §2.1 数据流
- 纯内置 input(), 零新依赖 (高级交互后续可加 prompt_toolkit, 非本 Sprint)
- banner → loop ("> " 提示符) → exit/quit/Ctrl+C/EOF 优雅退出, rc 0
- 输入分发: "/" 开头 → slash registry (SlashCommand 注册式);
  否则 → Intent 执行链 (S10-048 P1): IntentParser.parse → IntentRouter.route
  → [ConfirmationGate, P3 注入] → Action.execute(ExecutionContext) → Renderer 展示;
  未识别/未路由 → 明确提示 (不静默)
- 会话上下文 (Task 002): ContextManager 注入, 输入记录进 history (/cost 等数据来源)
- 纯 shell 零业务逻辑, 不接真实 LLM, 不改现有命令
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from .action import ActionRegistry, ExecutionContext
from .actions import DEFAULT_WORKSPACE, build_default_actions
from .commands import build_default_registry
from .context import ContextManager, SessionContext
from .intent import IntentObject, IntentParser, KeywordIntentParser
from .renderer import HumanRenderer, Renderer
from .router import IntentRouter, UnknownIntentError
from .slash import SlashCommandRegistry

#: 会话 banner (v0.2 — AI Workforce Operating System 命名空间)
BANNER = (
    "AI Factory v0.2 / AI Workforce Operating System\n"
    "输入 exit 或 quit 退出会话; Ctrl+C / Ctrl+D 亦可。"
)

#: 退出命令集合 (匹配即优雅退出)
EXIT_COMMANDS = frozenset({"exit", "quit"})

#: 未知输入提示前缀 (slash 未知 + Intent 未识别共用)
UNKNOWN_PREFIX = "未知命令: "

#: Intent 未识别/未路由时的指引后缀 (明确提示, 不静默)
INTENT_HINT = "试试 /help 或描述 '创建项目'"


class InteractiveSession:
    """交互会话主循环 (session shell) — Task 001 循环 + Task 003/004 slash 集成 + S10-048 P1 Intent 执行链。"""

    def __init__(
        self,
        prompt: str = "> ",
        banner: Optional[str] = None,
        context_manager: Optional[ContextManager] = None,
        registry: Optional[SlashCommandRegistry] = None,
        *,
        action_registry: Optional[ActionRegistry] = None,
        intent_router: Optional[IntentRouter] = None,
        intent_parser: Optional[IntentParser] = None,
        action_context: Optional[ExecutionContext] = None,
        confirmation_gate: Any = None,
        renderer: Optional[Renderer] = None,
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
        #: Action 注册表 (S10-048 P0) — 默认装配 3 个真实 Action (注册式)
        self.action_registry = (
            action_registry if action_registry is not None else build_default_actions()
        )
        #: Intent 路由 (P0) — 声明式映射 (intent_type → action_name, 无 if/else)
        self.intent_router = intent_router if intent_router is not None else IntentRouter()
        #: Intent 解析器 (P1) — 默认规则解析; 未来可注入 LLMIntentParser (同接口)
        self.intent_parser = intent_parser if intent_parser is not None else KeywordIntentParser()
        #: 注入式 ExecutionContext (测试/宿主定制); None → 每次派发从会话上下文构建
        self.action_context = action_context
        #: Confirmation Gate (P3 Task 注入) — None → 直接执行 (本 Phase 不阻塞)
        self.confirmation_gate = confirmation_gate
        #: 结果渲染器 (P1) — ActionResult.to_dict() → Renderer 展示
        self.renderer = renderer if renderer is not None else HumanRenderer()

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
        """命令分发: "/" 开头 → slash registry; 否则 → Intent 执行链 (S10-048 P1)。

        非 slash 输入: IntentParser.parse → IntentRouter.route → [ConfirmationGate
        (P3 注入, 未注入直接执行)] → Action.execute(ExecutionContext) → Renderer 展示。
        未识别意图 / 未路由意图 → 明确提示 (不静默)。slash 路径行为不变。
        """
        if line.startswith("/"):
            self.registry.execute(line, self.context)
            return
        intent = self.intent_parser.parse(line)
        if intent is None:
            print(f"{UNKNOWN_PREFIX}{line} — 未识别意图, {INTENT_HINT}")
            return
        if not intent.source:
            intent.source = "session"  # 设计 §2.2: 来源标注 (审计)
        try:
            action = self.intent_router.route(intent, self.action_registry)
        except UnknownIntentError as exc:
            print(f"未识别的意图: {exc} — {INTENT_HINT}")
            return
        context = self._build_action_context(intent)
        if self.confirmation_gate is not None and not self.confirmation_gate.confirm(
            action.name, intent, context
        ):
            print("已取消 — 输入 exit 或 quit 退出会话")
            return
        try:
            result = action.execute(context)
        except PermissionError as exc:
            print(f"❌ {exc}")
            return
        except Exception as exc:  # noqa: BLE001 — 失败安全: Action 异常 → 明确错误, 不崩溃会话
            print(f"❌ Action 执行失败 ({action.name}): {exc}")
            return
        print(self.renderer.render(result.to_dict()))

    def _build_action_context(self, intent: IntentObject) -> ExecutionContext:
        """装配 ExecutionContext: 注入复用 (action_context); 否则从会话上下文构建。

        workspace 缺省 → ~/.factory (与 commands.DEFAULT_PROJECTS_FILE 同口径);
        project 取会话 current_project; intent 注入供 handler 取参数。
        """
        if self.action_context is not None:
            self.action_context.intent = intent
            return self.action_context
        ctx = self.context_manager.get()
        workspace = Path(ctx.workspace) if ctx.workspace else DEFAULT_WORKSPACE
        return ExecutionContext(
            workspace=workspace,
            session=ctx,
            user="user",
            project=ctx.current_project,
            intent=intent,
        )


def main(argv: list[str] | None = None) -> int:
    """模块入口 (python -m 或直接调用): 启动交互会话。"""
    return InteractiveSession().run()


if __name__ == "__main__":
    sys.exit(main())
