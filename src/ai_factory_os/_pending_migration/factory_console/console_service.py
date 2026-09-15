"""Console 服务装配 —— 从 fastapi_adapter 剥出的"非 HTTP"部分。

为什么单独成文件（2026-09-15）:
    Founder 裁决：「api 可以根据 cli 创建接口服务，现在可以将 api 都删除，但是 cli 是地基」
    ⇒ `fastapi_adapter.py`（7,339 行 / 377 端点）作为**手写 HTTP 层**整体删除。
    但 CLI 一直在用它的六个**非 HTTP** 符号:
        build_console_service（147 行装配器）· _console_import · DEFAULT_ROOT ·
        DEFAULT_PORT · _factory_version · _read_json_map
    ⇒ 先把这些剥到本文件（CLI 继续可用），再删掉 fastapi_adapter 本体。

★ 顺带修掉一个存量 bug:
    `_read_json_map` 原先定义在 fastapi_adapter 某个函数**内部**（嵌套函数, 4521 行）,
    而 `cli_factory.py:3573` 却 `from ...fastapi_adapter import _read_json_map` ——
    那个 import **必抛 ImportError**（`factory local-ai run` 因此必崩）, 且没有 try 兜底。
    这里把它提为**模块级**, 该命令随之可用。
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:                       # py<3.11
    import tomli as tomllib                       # type: ignore[no-redef]

try:
    from legacy_paths import REPO_ROOT as _REPO_ROOT
    _factory_version = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
except Exception:  # noqa: BLE001 — 版本读取失败 → dev 标记（不阻断）
    _factory_version = "0.0.0-dev"


def _console_import(name: str):
    """S10-074: 部署态包名 factory_console; 源码态兼容连字符目录。

    判断: factory_console 模块位置 — 仓库内占位转发包 (源码态) → 连字符
    真实目录; site-packages (部署态) → factory_console。
    """
    import importlib.util as _util
    try:
        _spec = _util.find_spec("factory_console")
        _loc = str(_spec.origin or "") if _spec is not None else ""
    except (ImportError, ValueError):  # noqa: BLE001
        _loc = ""
    _is_repo_stub = "factory_console/__init__.py" in _loc.replace("\\", "/") and "site-packages" not in _loc
    _mod = ("factory-console" if _is_repo_stub else "factory_console") + (f".{name}" if name else "")
    return importlib.import_module(_mod)


#: 默认后端端口 (uvicorn 启动提示用; vite dev proxy 同源约定)
DEFAULT_PORT = 8011


#: 默认工厂根 (与 cli.context.DEFAULT_ROOT 同口径: ~/.factory)
DEFAULT_ROOT = Path.home() / ".factory"


def build_console_service(
    factory_root: str | Path,
    *,
    event_logger: Any = None,
    agent_executor: Any = None,
) -> Any:
    """按工厂根装配 ConsoleService (镜像 cli.commands._open_console_service)。

    全部 store 依赖可选 (失败安全: 缺任一 store → Console 按空数据处理);
    延迟导入 Core 包保 Removal Isolation (删除任一 Core 包不影响 Console 加载)。
    factory-console 包名含连字符 → importlib 按路径加载 (同 CLI 模式)。

    S10-016 Task 002: agent_executor 可选注入 (exec.agent_executor — 全链路
    编排; 生产装配不传 → ConsoleService 自装配: 复用本装配的 store +
    workflow_runner 真实 Provider (LLM key 已配置时); 无已配置 Provider →
    诚实 FAILED, 不伪造 LLM 结果)。

    S9-002: 装配 org 数据空间 (root/org — ProjectStore + WorkflowLifecycle,
    与 factory-org 演示/CLI 同目录口径); event_logger 提供时注入带事件库的
    生命周期 (org.approval.* 决定事件 source="console" 落库审计); org 缺失
    → 跳过注入 (失败安全, 读命令永不因 org 缺失失败)。
    """
    root = Path(factory_root)
    root.mkdir(parents=True, exist_ok=True)
    repo_root = REPO_ROOT  # .../ai-software-factory/
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        # S10-074: 部署态 factory_console / 源码态连字符 (统一 helper)
        module = _console_import("")
    except Exception as exc:  # 缺装/损坏 → 装配失败 (调用方决定兜底)
        raise RuntimeError("factory-console 未安装 (缺 factory-console/ 包)") from exc

    from ai_factory_os.plugins.agents.registry import AgentRegistry
    from ai_factory_os.plugins.agents.store import AgentStore

    from ai_factory_os.services.learning.store import DecisionStore, ExperienceStore, RecommendationStore

    from product.store import ProductStore

    from providers.registry import ProviderRegistry
    from providers.store import ProviderStore
    from providers.usage import UsageStore

    from ai_factory_os.services.work.store import TaskStore

    from ai_factory_os.infrastructure.storage.manager import WorkspaceManager

    # S9-002: org 数据空间 (root/org — 与 factory-org CLI 同目录口径; 失败安全)
    project_store = None
    workflow_lifecycle = None
    project_space = None
    try:
        org_dir = repo_root / "src" / "ai_factory_os" / "services" / "organization"
        if org_dir.is_dir() and str(org_dir) not in sys.path:
            sys.path.insert(0, str(org_dir))
        from ai_factory_os.services.organization.projects import ProjectStore
        from ai_factory_os.services.organization.space import ProjectSpaceStore
        from ai_factory_os.services.organization.workflow import WorkflowLifecycle

        project_store = ProjectStore(root / "org")
        workflow_lifecycle = WorkflowLifecycle(project_store, logger=event_logger)
        # S10-009 Task 4: Project Space (root/workspace — 目录信源:
        # workspace/projects/{slug}/project.json + idea/discovery 资产;
        # 失败安全: 缺 space → draft/发现流程 503)
        project_space = ProjectSpaceStore(root)
    except Exception:
        project_store = None
        workflow_lifecycle = None
        project_space = None

    # S10-004: Runtime 数据空间 (root/runtimes — 独立于 org, 原子写 JSON;
    # 失败安全: 装配失败 → None, runtime 操作按空/不存在处理)
    runtime_store = None
    runtime_screenshot_store = None
    try:
        _runtime_stores = _console_import("runtime_store")
        runtime_store = _runtime_stores.RuntimeInstanceStore(root / "runtimes")
        runtime_screenshot_store = _runtime_stores.RuntimeScreenshotStore(root / "runtimes")
    except Exception:
        runtime_store = None
        runtime_screenshot_store = None

    # S10-006: 审核反馈数据空间 (root/review_feedback.json — Feedback Loop
    # Reject 意见落库; 失败安全: 装配失败 → None, 反馈保存/查询按空处理)
    review_feedback_store = None
    try:
        _feedback_module = _console_import("review_feedback")
        review_feedback_store = _feedback_module.ReviewFeedbackStore(root)
    except Exception:
        review_feedback_store = None

    # S10-006.5 P1-A: 对话记录数据空间 (root/chat.json — POST /projects/{id}/chat
    # 消息落库; 失败安全: 装配失败 → None, 消息记录跳过, 对话/启动不受影响)
    conversation_store = None
    try:
        _chat_module = _console_import("chat_store")
        conversation_store = _chat_module.ConversationStore(root / "chat.json")
    except Exception:
        conversation_store = None

    # S10-016: Runtime Session 数据空间 (root/runtime-sessions — Agent 执行
    # 会话独立数据空间, 原子写 JSON; 挂 factory-exec 到 sys.path (同
    # workflow_runner._setup_sys_path 模式 — 8011 启动命令未挂 factory-exec,
    # 延迟导入 exec.runtime_session 需该目录可寻址); 失败安全: 装配失败 →
    # None, session 操作按空/404 处理)
    session_store = None
    try:
        exec_dir = repo_root / "src" / "legacy" / "factory-exec"
        if exec_dir.is_dir() and str(exec_dir) not in sys.path:
            sys.path.insert(0, str(exec_dir))
        _session_module = importlib.import_module("exec.runtime_session")
        session_store = _session_module.RuntimeSessionStore(root / "runtime-sessions")
    except Exception:
        session_store = None

    return module.ConsoleService(
        workspace_manager=WorkspaceManager(root),
        task_store=TaskStore(root / "tasks"),
        agent_registry=AgentRegistry(AgentStore(root / "agents")),
        product_store=ProductStore(root / "product"),
        decision_store=DecisionStore(root / "intelligence"),
        recommendation_store=RecommendationStore(root / "intelligence"),
        experience_store=ExperienceStore(root / "intelligence"),
        usage_store=UsageStore(root / "providers"),
        provider_registry=ProviderRegistry(ProviderStore(root / "providers")),
        project_store=project_store,
        workflow_lifecycle=workflow_lifecycle,
        # S10-009 Task 4: Project Space (root/workspace — draft/idea/discovery
        # 资产目录信源; 失败安全: 缺 space → draft/发现流程按存储不可用处理)
        project_space=project_space,
        # S10-004: Runtime 实例/截图持久化 (root/runtimes; 失败安全)
        runtime_store=runtime_store,
        runtime_screenshot_store=runtime_screenshot_store,
        # S10-006: 审核反馈持久化 (root/review_feedback.json — Feedback Loop
        # Reject 意见落库; 失败安全: 装配失败 → None, 保存/查询按空处理)
        review_feedback_store=review_feedback_store,
        # S10-006.5 P1-A: 对话记录持久化 (root/chat.json — 消息落库; 失败安全)
        conversation_store=conversation_store,
        # S10-016: Runtime Session 持久化 (root/runtime-sessions — Agent 执行
        # 会话; 失败安全: 装配失败 → None, session 操作按空/404 处理)
        session_store=session_store,
        # S10-016 Task 002: AgentExecutor 编排层 (注入优先; 缺省 None →
        # service 自装配 — 复用本装配 store + workflow_runner 真实 Provider,
        # 无已配置 LLM key → 诚实 FAILED 不伪造结果)
        agent_executor=agent_executor,
    )


#: 从 fastapi_adapter 的嵌套定义提为模块级 —— 原先 CLI 从模块级 import 它必抛 ImportError。
# ------------------------------------------- 设置 — Agent / Skill 管理 (v1.1.102)
def _read_json_map(path: Any) -> dict[str, Any]:
    import json as _json

    try:
        d = _json.loads(Path(path).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空 (失败安全)
        d = {}
    return d if isinstance(d, dict) else {}
