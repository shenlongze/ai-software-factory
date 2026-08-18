"""factory-console/session/session.py — InteractiveSession 交互会话主循环 (S10-047 Task 001 + S10-048 P1)。

设计: docs/sprint10/S10-047-session-design.md §2 Session Loop
     + docs/sprint10/S10-048-intent-kernel-design.md §2.1 数据流
- 纯内置 input(), 零新依赖 (高级交互后续可加 prompt_toolkit, 非本 Sprint)
- banner → loop ("> " 提示符) → exit/quit/Ctrl+C/EOF 优雅退出, rc 0
- 输入分发: "/" 开头 → slash registry (SlashCommand 注册式);
  否则 → Intent 执行链 (S10-048 P1+P4): IntentParser.parse → IntentRouter.route
  → ConfirmationGate (P4 默认装配, 敏感 action 确认后执行)
  → Action.execute(ExecutionContext) → Renderer 展示;
  未识别/未路由 → 明确提示 (不静默)
- 会话上下文 (Task 002): ContextManager 注入, 输入记录进 history (/cost 等数据来源)
- S10-050 P5: create_product intent / 产品流程进行中 → conversation 产品发现
  (DISCOVERY 多轮追问 → PRODUCT_CONFIRMATION → 确认 → create_product action 桥接)
- 纯 shell 零业务逻辑, 不接真实 LLM, 不改现有命令
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from .action import ActionRegistry, ActionResult, ExecutionContext
from .actions import DEFAULT_WORKSPACE, build_default_actions
from .commands import build_default_registry
from .confirm import ConfirmationGate
from .context import ContextManager, SessionContext
from .conversation import ConversationManager, ConversationState
from .intent import (
    INTENT_CREATE_PRODUCT,
    INTENT_CREATE_PROJECT,
    INTENT_CURRENT_PROJECT,
    IntentObject,
    IntentParser,
    KeywordIntentParser,
)
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
        conversation_manager: Optional[ConversationManager] = None,
        chat_service: Any = None,
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
        #: Confirmation Gate (P4 最小治理) — 默认装配 ConfirmationGate:
        #: 敏感 action (create_project/run_task) 经确认流, 拒绝 → "已取消";
        #: 测试可注入定制 gate / confirm_fn (不阻塞 input)
        self.confirmation_gate = (
            confirmation_gate if confirmation_gate is not None else ConfirmationGate()
        )
        # S10-051 P3 (验收 G): prepare_project 为敏感组合 Action (生成 4 资产 +
        # 生命周期变更) — 纳入会话确认门。仅扩展本实例的集合 (拷贝),
        # 不改 ConfirmationGate 类默认集合 {create_project, run_task} (基线不动)
        # S10-052 P2 (验收 D): execute_project 同纳入确认门 ("开始开发" → 确认后才执行)
        if isinstance(self.confirmation_gate, ConfirmationGate):
            self.confirmation_gate.sensitive_actions = set(
                self.confirmation_gate.sensitive_actions
            ) | {"prepare_project", "execute_project"}
        #: 结果渲染器 (P1) — ActionResult.to_dict() → Renderer 展示
        self.renderer = renderer if renderer is not None else HumanRenderer()
        #: 会话状态机 (S10-050 P5) — 产品流程 (DISCOVERY 多轮) 由 conversation 接管;
        #: 可注入定制 (测试); 默认装配 (同 intent_parser)
        self.conversation = (
            conversation_manager
            if conversation_manager is not None
            else ConversationManager(parser=self.intent_parser)
        )
        #: S10-075 L2: 普通问答服务 (intent 未识别 → LLM 问答)
        if chat_service is None:
            from .chat import ChatService

            chat_service = ChatService()
        self.chat_service = chat_service

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

        非 slash 输入:
        - S10-050 P5: 产品流程进行中 (conversation.product_intent 存在, 状态
          DISCOVERY/PRODUCT_CONFIRMATION) → 输入直接进产品流程 (多轮追问 / 确认)
        - create_product intent → 产品发现流程 (DISCOVERY 多轮追问), 不走普通
          action 路由 (ProductIntent 完整 + 用户确认后才执行 create_product)
        - 其余: IntentParser.parse → IntentRouter.route → ConfirmationGate
          (P4 默认装配, 敏感 action 确认通过才执行) → Action.execute(ExecutionContext)
          → Renderer 展示。未识别意图 / 未路由意图 → 明确提示 (不静默)。
        slash 路径行为不变。
        """
        if line.startswith("/"):
            self.registry.execute(line, self.context)
            return
        conv = self.conversation
        # S10-050 P5: 产品流程进行中 → 答案直接进产品流程 (不重复解析意图)
        if conv.product_intent is not None and conv.state in (
            ConversationState.DISCOVERY,
            ConversationState.PRODUCT_CONFIRMATION,
        ):
            if conv.state == ConversationState.PRODUCT_CONFIRMATION:
                resp = conv.handle_product_confirm(line, confirm_fn=self._create_product_fn)
            else:
                resp = conv.handle_product_answer(line)
            print(resp.message)
            return
        intent = self.intent_parser.parse(line)
        if intent is None:
            # S10-075 L2: 普通自然语言 → 真实 LLM 问答 (不再是 "未知命令")
            answer = self.chat_service.answer(line)
            print(answer)
            return
        if not intent.source:
            intent.source = "session"  # 设计 §2.2: 来源标注 (审计)
        # S10-050 P1: 产品意图 → 产品发现流程 (多轮追问), 不走普通 action 路由
        if intent.intent_type == INTENT_CREATE_PRODUCT:
            resp = conv.start_product_discovery(line)
            print(resp.message)
            return
        # S10-076: 当前项目查询 → 只读展示会话当前项目 (绝不创建/写)
        if intent.intent_type == INTENT_CURRENT_PROJECT:
            self._show_current_project()
            return
        # S10-076: Action Safety — 高副作用 Action 参数不完整 → 自然语言提示,
        # 不进入 Domain/Pydantic validation error
        if intent.intent_type == INTENT_CREATE_PROJECT:
            params = intent.parameters or {}
            if not (params.get("name") or "").strip() and not (params.get("goal") or "").strip():
                print(
                    "我理解你想创建项目, 但还需要一些信息:\n"
                    "  • 项目名称 (例如: 创建项目 记账App)\n"
                    "  • 或项目目标 (例如: 创建项目 goal=做一个记账软件)\n"
                    "补充完整后我立即执行。"
                )
                return
        try:
            action = self.intent_router.route(intent, self.action_registry)
        except UnknownIntentError as exc:
            print(f"未识别的意图: {exc} — {INTENT_HINT}")
            return
        context = self._build_action_context(intent)
        # S10-049 P0: 确认判定以 intent 类型为准 (run_task ∈ 敏感集合 →
        # ConfirmationGate 确认流; create_project 等 action.name == intent 类型不变)
        if self.confirmation_gate is not None and not self.confirmation_gate.confirm(
            intent.intent_type, intent, context
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
        # S10-049 P5: agent.execute_task 长耗时执行 — 展示 AgentExecutionResult 摘要
        # (agent/artifact/cost/duration); 其余 Action 走通用 Renderer
        # S10-052 P2: execute_project 结果含 cost 键 → 同走摘要渲染 (避免成本分支吞消息)
        if action.name in ("agent.execute_task", "execute_project"):
            self._render_execution(action.name, result)
            return
        print(self.renderer.render(result.to_dict()))

    def _create_product_fn(self, product_intent: Any) -> str:
        """产品确认回调 (S10-050 P5): 执行 create_product action → 展示消息。

        conversation 零依赖 Action — 由宿主 (session) 注入: 产品意图写入
        SessionContext.product_intent → 装配 ExecutionContext → 路由 create_product
        action → 返回消息 (失败 → 抛异常, conversation 侧重置并明确提示)。
        """
        intent = IntentObject(
            intent_type=INTENT_CREATE_PRODUCT,
            params={"name": getattr(product_intent, "name", None)},
            raw=getattr(product_intent, "raw", "") or "",
            source="session",
        )
        self.context.product_intent = product_intent  # SessionContext.product_intent (P5)
        context = self._build_action_context(intent)
        action = self.action_registry.get("create_product")
        if action is None:
            raise RuntimeError("create_product Action 未注册")
        result = action.execute(context)
        if result.ok:
            # S10-076: 产品创建成功 → 写会话当前项目上下文 (后续 "刚刚创建的项目呢" 可用)
            data = result.data if isinstance(result.data, dict) else {}
            project = data.get("project")
            if isinstance(project, dict):
                self.context.current_project = str(
                    project.get("id") or project.get("slug") or project.get("name") or ""
                )
                self.context.metadata["last_created_project"] = self.context.current_project
            elif project is not None:
                self.context.current_project = str(
                    getattr(project, "id", "") or getattr(project, "slug", "") or getattr(project, "name", "")
                )
                self.context.metadata["last_created_project"] = self.context.current_project
            return result.message
        raise RuntimeError(result.message or "产品创建失败")

    def _render_execution(self, action_name: str, result: ActionResult) -> None:
        """Agent 执行结果摘要展示 (S10-049 P5) — agent/artifact/cost/duration。

        不走通用 Renderer (data 含 cost 键会触发成本分支, 丢失 agent/artifact/
        duration): 成功 → ✔ 消息 + 摘要行; 失败 → ❌ 明确错误 (验收 E)。
        """
        data = result.data if isinstance(result.data, dict) else {}
        execution = data.get("execution") or {}
        if not isinstance(execution, dict):
            execution = {}
        if result.ok:
            print(f"✔ {result.message}")
            for key in ("agent", "artifact", "cost", "duration"):
                if execution.get(key):
                    print(f"  {key}: {execution[key]}")
        else:
            print(f"❌ {result.message}")

    def _show_current_project(self) -> None:
        """S10-076: 只读展示会话当前项目 (不创建/写)。"""
        ctx = self.context
        project = ctx.current_project
        if not project:
            last = ctx.metadata.get("last_created_project")
            if last:
                project = str(last)
        if not project:
            print(
                "当前还没有项目上下文。\n"
                "你可以:\n"
                "  • 描述产品想法 (例如: 我想做一个记账 App) — 我会带你完成 Discovery → 项目创建\n"
                "  • 输入 /project 查看已有项目"
            )
            return
        print(f"当前项目: {project}")
        print(f"状态: 已就绪 (Project Ready For Engineering)")
        print("需要的话, 我可以继续帮你查看项目详情或开始开发。")

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
