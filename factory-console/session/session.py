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

import json
import re
import sys

import logging

logger = logging.getLogger("factory.session")
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
    INTENT_GENERATE_PRD,
    INTENT_RENAME_PROJECT,
    INTENT_RESUME_PROJECT,
    IntentObject,
    IntentParser,
    KeywordIntentParser,
)
from .llm_intent import LLMIntentParser
from .renderer import HumanRenderer, Renderer, render_message
from .router import IntentRouter, UnknownIntentError
from .slash import SlashCommandRegistry

#: 会话 banner (版本单源: pyproject.toml, S10-098 修复 v0.2 硬编码;
#:  连字符目录非包 → 不依赖相对导入, 独立读 pyproject)
def _session_version() -> str:
    # 源码态 (仓库根有 pyproject) → pyproject 优先; 安装态 → metadata
    try:
        import tomllib
        from pathlib import Path as _P
        _pp = _P(__file__).resolve().parent.parent.parent / "pyproject.toml"
        if _pp.is_file():
            return tomllib.loads(_pp.read_text(encoding="utf-8"))["project"]["version"]
    except Exception:  # noqa: BLE001
        pass
    try:
        from importlib.metadata import version as _v
        return _v("ai-software-factory")
    except Exception:  # noqa: BLE001
        return "0.0.0-dev"


BANNER = (
    f"AI Factory v{_session_version()} / AI Workforce Operating System\n"
    "输入 exit / 退出 结束会话; Ctrl+C / Ctrl+D 亦可。"
)

#: 退出命令集合 (匹配即优雅退出) — S10-103: 单一来源 discovery_guide.EXIT_COMMANDS
#: (conversation 不能 import session — 循环依赖; 集合内容不变)
from .discovery_guide import EXIT_COMMANDS  # noqa: E402

#: 未知输入提示前缀 (slash 未知 + Intent 未识别共用)
UNKNOWN_PREFIX = "未知命令: "

#: Intent 未识别/未路由时的指引后缀 (明确提示, 不静默)
INTENT_HINT = "试试 /help 或描述 '创建项目'"

#: 会话回复间分割线 (S10-104 — 纯装饰, REPL 层; run() 每轮 _dispatch 后打印;
#: 退出/空输入不打印; 非交互 CLI 不受影响)
SEPARATOR = "─" * 46

#: next_action → 中文产出标签 (S10-104 — 宿主信号注释用; 产出引擎 backlog)
NEXT_ACTION_LABELS: dict[str, str] = {
    "prd": "PRD文档",
    "feature_list": "功能清单",
    "html": "HTML页面",
    "docs": "文档",
}


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
        #: Intent 解析器 (P1) — 默认 LLM 理解 + 规则兜底 (LLMIntentParser → None
        #: 时回退 KeywordIntentParser, 诚实降级不伪造)
        self.intent_parser = (
            intent_parser if intent_parser is not None else LLMIntentParser()
        )
        self._rule_parser = KeywordIntentParser()  # 规则兜底 (LLM 失败/无 key)
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
        - S10-104: 每轮 _dispatch 后打印 SEPARATOR 分割线 (纯装饰, REPL 层;
          退出/空输入路径不打印)
        """
        self._banner()
        self._restore_session_state()
        self.running = True
        while self.running:
            try:
                line = self._read_input_line(self.prompt)
            except (EOFError, KeyboardInterrupt):
                print()  # 换行, 避免提示符残留在行尾
                break
            cmd = line.strip()
            if cmd in EXIT_COMMANDS:
                print("已退出会话 — 再见!")
                self.running = False
            elif not cmd:
                continue  # 空输入
            else:
                self.context_manager.record(cmd)
                self._dispatch(cmd)
                # S10-104: 每轮回复间分割线 (纯装饰; 退出/空输入路径不打印 —
                # 产品流 exit_requested 已置 running=False)
                if self.running:
                    print(SEPARATOR)
        self._save_session_state()
        return 0

    def _banner(self) -> None:
        """打印欢迎横幅 (验收: 显示 AI Factory)。"""
        print(self.banner_text)

    def _read_input_line(self, prompt: str) -> str:
        """多行输入 (S10-105 简单检测): 行尾 '\\' → 续行 (提示 '… '), 直到无 '\\';
        拼接 '\n'。prompt_toolkit 缺失 → input() 降级 (诚实, 验收: 无 prompt_toolkit 降级)。"""
        line = input(prompt)
        if not line.endswith("\\"):
            return line
        parts = [line.rstrip("\\")]
        while True:
            more = input("… ")
            if not more.endswith("\\"):
                parts.append(more)
                break
            parts.append(more.rstrip("\\"))
        return "\n".join(parts)

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
            # S10-084: 需求整理 (summary_only) → discovery.md 资产落盘 (失败安全)
            if getattr(resp, "summary_only", False) and getattr(resp, "product_snapshot", None):
                self._write_discovery_artifact(resp.product_snapshot)
            # 逃生 (passthrough) — 产品流程已让位 (product_intent=None),
            # 原输入交回普通意图链处理 (不再当字段答案)
            if getattr(resp, "passthrough", False):
                self._dispatch(line)
            elif getattr(resp, "exit_requested", False):
                # S10-103: 发现/确认中 exit/quit/再见/退出会话 → 优雅退出
                # (退出/取消 等控制短语仍由 conversation 层先处理, 不走到这里)
                print("已退出会话 — 再见!")
                self.running = False
            else:
                message = resp.message
                # S10-102/104: 确认+下一步 → 宿主接线 — 创建成功后执行 next_action
                # ("prd" → generate_prd; 失败注明, 不阻断创建; feature_list/html/docs
                #  → 信号注释 (产出引擎 backlog); develop/create 只传信号)
                if getattr(resp, "next_action", None) == "prd":
                    message = f"{message}\n{self._run_prd_after_create()}"
                elif getattr(resp, "next_action", None) in (
                    "feature_list", "html", "docs",
                ):
                    label = NEXT_ACTION_LABELS.get(
                        resp.next_action, resp.next_action
                    )
                    message = (
                        f"{message}\n[已记录] 将生成{label} — 产出引擎 backlog"
                    )
                render_message(message)
            return
        intent = self.intent_parser.parse(line)
        if intent is None:
            intent = self._rule_parser.parse(line)  # LLM 未识别 → 规则兜底
        if intent is None:
            # 命令/帮助类查询 → 真实命令列表 (不再交给 LLM 编故事)
            if self._maybe_show_command_help(line):
                return
            # S10-075 L2: 普通自然语言 → 真实 LLM 问答 (不再是 "未知命令")
            answer = self.chat_service.answer(line)
            render_message(answer)
            return
        if not intent.source:
            intent.source = "session"  # 设计 §2.2: 来源标注 (审计)
        # S10-050 P1: 产品意图 → 产品发现流程 (多轮追问), 不走普通 action 路由
        if intent.intent_type == INTENT_CREATE_PRODUCT:
            resp = conv.start_product_discovery(line)
            render_message(resp.message)
            return
        # S10-076: 当前项目查询 → 只读展示会话当前项目 (绝不创建/写)
        if intent.intent_type == INTENT_CURRENT_PROJECT:
            self._show_current_project()
            return
        # S10-081 P2: 自然语言改名 → 复用 confirm_project 事务 (确认门后执行)
        if intent.intent_type == INTENT_RENAME_PROJECT:
            self._rename_project_via_nl(intent, line)
            return
        # "继续 旅行记账" → 从输入解析项目名并切换当前项目; 无名称/未匹配 → 落回普通路由
        if intent.intent_type == INTENT_RESUME_PROJECT:
            if self._try_resume_with_name(line):
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
            # S10-082: Unknown Intent 安全降级 → ChatService (用户永远看不到
            # UnknownIntentError / intent 名 / route 不存在)
            logger.debug("intent %r 无路由 → chat 降级: %s", intent.intent_type, exc)
            answer = self.chat_service.answer(line)
            render_message(answer)
            return
        context = self._build_action_context(intent)
        # S10-049 P0: 确认判定以 intent 类型为准 (run_task ∈ 敏感集合 →
        # ConfirmationGate 确认流; create_project 等 action.name == intent 类型不变)
        if self.confirmation_gate is not None and not self.confirmation_gate.confirm(
            intent.intent_type, intent, context
        ):
            print("已取消本次操作")
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
        render_message(self.renderer.render(result.to_dict()))

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

    def _run_prd_after_create(self) -> str:
        """S10-102 确认+下一步 (next_action="prd"): 创建成功后生成 PRD。

        复用 context.product_intent / current_project (create_product 已落盘
        projects/<slug>/product.json + 会话当前项目) → 执行 generate_prd action;
        成功 → "已生成 PRD: projects/<slug>/PRD.md"; 失败 → 注明原因 (不阻断创建)。
        develop/create next_action 只传信号, 宿主执行留待后续 Sprint。
        """
        try:
            intent = IntentObject(
                intent_type=INTENT_GENERATE_PRD,
                params={},
                raw="生成PRD",
                source="session",
            )
            action = self.action_registry.get("generate_prd")
            if action is None:
                return "PRD 生成失败: generate_prd Action 未注册"
            result = action.execute(self._build_action_context(intent))
            if result.ok:
                data = result.data if isinstance(result.data, dict) else {}
                prd_file = str(data.get("prd_file") or "").strip()
                return f"已生成 PRD: {prd_file}" if prd_file else "已生成 PRD"
            return f"PRD 生成失败: {result.message or result.error or '未知错误'}"
        except Exception as exc:  # noqa: BLE001 — 失败安全: 注明原因, 不阻断创建
            return f"PRD 生成失败: {exc}"

    def _session_state_file(self) -> Path:
        """会话状态文件 (workspace 或 ~/.factory / session_state.json)。"""
        ws = getattr(self.context, "workspace", None) or DEFAULT_WORKSPACE
        return Path(ws) / "session_state.json"

    def _restore_session_state(self) -> None:
        """恢复上次会话的当前项目 (失败安全: 无文件/损坏 → 静默)。"""
        try:
            state_file = self._session_state_file()
            if state_file.is_file():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                pid = str(data.get("current_project") or "")
                if pid:
                    self.context.current_project = pid
                    print(f"已恢复上次项目: {pid} (输入 /project 可切换)")
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def _save_session_state(self) -> None:
        """保存会话状态 (当前项目) — 下次会话自动恢复 (失败安全)。"""
        try:
            state_file = self._session_state_file()
            state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "current_project": getattr(self.context, "current_project", "") or "",
                "session_id": getattr(self.context, "session_id", "") or "",
            }
            state_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def _write_discovery_artifact(self, snapshot: dict) -> None:
        """S10-084 P0: "整理需求不创建" → discovery.md 版本化资产落盘 (失败安全)。

        从 ConversationResponse.product_snapshot (ProductIntent.to_dict) 构建
        discovery 资产, 复用 ArtifactRegistry + ARTIFACT_CREATED 审计血缘。
        任何故障 → 静默 (不打断已返回的需求整理消息)。
        """
        try:
            if not isinstance(snapshot, dict) or not snapshot.get("name"):
                return
            # 与 _build_action_context 同口径: 会话未显式设 workspace → DEFAULT_WORKSPACE
            workspace = getattr(self.context, "workspace", None) or DEFAULT_WORKSPACE
            if not workspace:
                return
            from .artifact_registry import ArtifactRegistry
            from .pipeline import _slugify  # 复用同名 slug 口径 (纯函数)

            slug = _slugify(str(snapshot.get("name") or "")) or "unnamed"
            features = snapshot.get("core_features") or []
            if isinstance(features, list):
                features_text = "、".join(str(f) for f in features)
            else:
                features_text = str(features or "")
            content = (
                "# 需求整理 (discovery)\n\n"
                f"- 产品: {snapshot.get('name') or '(未命名)'}\n"
                f"- 问题: {snapshot.get('problem') or '(未填写)'}\n"
                f"- 目标用户: {snapshot.get('user') or '(未填写)'}\n"
                f"- 核心功能: {features_text or '(未填写)'}\n"
                f"- 平台: {snapshot.get('platform') or '(未指定)'}\n"
                f"- 状态: draft\n"
                f"- 来源: conversation {self.context.session_id}\n"
            )
            source = str(getattr(self.context, "session_id", "") or "")
            registry = ArtifactRegistry(workspace, slug)
            record = registry.write(
                "discovery",
                content,
                created_by="user+ai",
                source=source,
                status="draft",
            )
            # 审计血缘 (失败安全)
            try:
                from ..audit.audit_emitter import AuditEmitter
                AuditEmitter(workspace=workspace).emit(
                    "ARTIFACT_CREATED",
                    project_id=slug,
                    actor_type="user",
                    actor_id="user",
                    artifact_reference=record.content_ref,
                    artifact_type="discovery",
                    artifact_version=record.version,
                )
            except Exception:  # noqa: BLE001 — 审计故障不中断
                pass
        except Exception:  # noqa: BLE001 — 失败安全: 落盘故障不打断需求整理消息
            pass

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

    def _maybe_show_command_help(self, line: str) -> bool:
        """命令/帮助类输入 → 展示真实命令 (slash + CLI), 返回 True 已处理。

        覆盖: "help/帮助/命令/指令/怎么用/使用说明/项目管理的命令" → /help;
        "project/项目" (裸词) → /project 真实项目清单。
        """
        norm = (line or "").strip().strip("，。？！!?、/ 	").lower()
        if norm in ("project", "项目"):
            self.registry.execute("/project", self.context)
            return True
        help_hits = ("help", "commands", "命令", "指令", "帮助", "怎么用", "使用说明")
        if norm in help_hits or any(k in norm for k in ("命令", "指令", "怎么用", "使用说明")):
            self.registry.execute("/help", self.context)
            return True
        return False

    def _try_resume_with_name(self, raw_line: str) -> bool:
        """'继续 <项目名>' → 解析项目名, 匹配并切换当前项目后继续 (返回 True 已处理)。

        无项目名 (裸 '继续开发') → 返回 False, 落回普通路由 (由 execute_project
        给出无当前项目的明确提示); 名称未匹配 → 打印提示并返回 True。
        """
        name = str(raw_line or "").strip()
        for prefix in ("继续开发", "继续执行", "继续", "resume"):
            if name.lower().startswith(prefix.lower()):
                name = name[len(prefix):].strip()
                break
        name = name.strip("，。,. ")
        if not name:
            return False
        pid = self._match_project(name)
        if not pid:
            print(f"未找到项目 '{name}' — 输入 /project 查看项目清单")
            return True
        self.context.current_project = pid
        print(f"已切换到项目: {pid}")
        self._dispatch("继续开发")
        return True

    def _match_project(self, name: str) -> str:
        """按名称/ID 匹配项目 (org/projects.json; 名称包含或 ID 相等)。"""
        from .commands import read_projects

        workspace = getattr(self.context, "workspace", None) or DEFAULT_WORKSPACE
        projects = read_projects(Path(workspace) / "org" / "projects.json")
        for proj in projects:
            pid = str(proj.get("id") or "")
            pname = str(proj.get("name") or "")
            if pid == name or pname == name:
                return pid
        # 宽松包含匹配 (唯一命中才用, 避免歧义)
        hits = [
            str(proj.get("id") or "")
            for proj in projects
            if name in str(proj.get("name") or "") or str(proj.get("name") or "") in name
        ]
        if len(hits) == 1:
            return hits[0]
        return None

    def _rename_project_via_nl(self, intent: Any, raw_line: str) -> None:
        """S10-081 P2: 自然语言改名 — 复用 service.confirm_project 事务。

        name 参数 (关键词后文本); 无 name → 引导; 有 name → 确认门 → 执行。
        """
        name = ""
        params = getattr(intent, "parameters", None) or {}
        name = str(params.get("name") or "").strip()
        # 清理 "改名叫/改名为/名称改成/项目改名" 残留 (参数提取可能含)
        for w in ("改名叫", "改名为", "名称改成", "名字改成", "项目改名", "改名字"):
            if name.startswith(w):
                name = name[len(w):].strip()
                break
        if not name:
            print(
                "你想给项目改名? 告诉我新名称即可, 例如:\n"
                "  • 这个项目改名叫 记账助手\n"
                "  • 把项目名称改成 台球计分"
            )
            return
        pid = self.context.current_project
        # "P-xxx 改名叫 新名" → 从原始输入解析项目 ID (指引承诺的写法, 真正生效)
        raw = str(raw_line or "").strip()
        for kw in ("改名叫", "改名为", "名称改成", "名字改成", "项目改名", "改名字"):
            idx = raw.find(kw)
            if idx > 0:
                candidate = raw[:idx].strip().strip("，。,. ")
                # 只认项目 ID 形态 (P-xxx) — 避免把 "项目改名叫 X" 的 "项目" 当 ID
                if re.match(r"^P-[\w-]+$", candidate):
                    pid = candidate
                break
        if not pid:
            print(
                "当前没有正在开发的项目。\n"
                "你可以: 输入 /project 查看已有项目, 或用 'P-xxx 改名叫 新名' 指定。"
            )
            return
        if self.confirmation_gate is not None and not self.confirmation_gate.confirm(
            INTENT_RENAME_PROJECT, intent, None
        ):
            print("已取消本次操作")
            return
        # 执行: 走 rename_project action (org + product.json, 任何状态可改;
        # 修复: 旧路径导入 web 模块失败, 且 confirm_project 有生命周期确认门限制)
        intent2 = IntentObject(
            intent_type=INTENT_RENAME_PROJECT,
            params={"project_id": str(pid), "name": name},
            raw=raw_line,
            source="session",
        )
        action = self.action_registry.get("rename_project")
        if action is None:
            print("❌ 项目改名失败: rename_project Action 未注册")
            return
        result = action.execute(self._build_action_context(intent2))
        print(result.message)

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
