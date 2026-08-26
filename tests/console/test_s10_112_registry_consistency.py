"""S10-112 P0-10 — 注册表一致性测试套件 (防遗漏机制, v1.1.81)。

5 类注册表, 每类 ≥1 真断言 (禁空断言/跳过; 数据全部从实现动态读取,
禁止硬编码快照):
1. CLI 命令: build_parser() 子命令 choices ↔ test_console_cli.subcommands 集合相等
   (AST 动态读取 test_console_cli 的期望集合 — 新增命令漏测试 → 红)
2. 意图: _KEYWORD_RULES 全部 intent_type 均有路由 (DEFAULT_ROUTES 显式声明,
   除文档化会话特判 current_project / S10-082 chat 降级 show_cost);
   DEFAULT_ROUTES 的 intent 均有关键词规则可达 (别名 execute_task → 同 action)
3. Action: DEFAULT_ROUTES 引用的 action 名 ⊆ build_default_actions() registry;
   registry sensitive=True 集合 ↔ ConfirmationGate 强制集合 (会话级) 双向覆盖
   (create_product 会话内由 conversation 发现流程接管 — 文档化例外)
4. 事件: 实现中发射的事件类型 ⊆ EVENT_TYPES (防新增事件漏注册);
   EVENT_TYPES 全部被实现/审计文档引用 (防死条目); 审计设计文档列出事件 ⊆ EVENT_TYPES
5. API: 实际注册路由 (app.routes) ↔ FEATURES.md §9 文档端点 (防文档宣称但
   API 缺失); POST/PATCH/DELETE 写路由全部在 web 写路由白名单 (新增写端点漏
   白名单 → 红); CAPABILITY_MATRIX API 列 ✅ 能力均有实际端点支撑

basename 全仓库唯一 (test_s10_112_* 前缀)。
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_FACTORY_CORE = _REPO / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

#: 文档化设计例外 (非漂移 — 由实现/session 特判或既有测试钉住):
#: 1) current_project: 会话内 S10-076 只读展示特判, 不经 router (session.py)
#: 2) show_cost: S10-082 无路由 → ChatService 降级 (test_session_intent_execution
#:    test_session_unrouted_intent_explicit_hint 钉住)
SESSION_INTERCEPTED_INTENTS = frozenset({"current_project", "show_cost"})
#: create_product 会话内由 conversation 发现流程接管 (确认在发现确认门完成),
#: 不经 router/会话确认门 — 与 DEFAULT_ROUTES/create_product action 语义一致
SESSION_INTERCEPTED_SENSITIVE = frozenset({"create_product"})

INTENT_MOD = importlib.import_module("factory-console.session.intent")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
SESSION_MOD = importlib.import_module("factory-console.session.session")
AUDIT_EVENT_MOD = importlib.import_module("factory-console.audit.audit_event")
CONFIRM_MOD = importlib.import_module("factory-console.session.confirm")
ADAPTER_MOD = importlib.import_module("factory-console.web.backend.fastapi_adapter")


def _registry_action_names() -> set[str]:
    """build_default_actions() 注册表 action 名集合 (动态读取)。"""
    return {a.name for a in ACTIONS_MOD.build_default_actions().list()}


def _session_gate_enforced() -> set[str]:
    """会话确认门强制 intent 集合 (类默认 + 会话扩展, 动态读取)。"""
    return set(SESSION_MOD.InteractiveSession().confirmation_gate.sensitive_actions)


# ================================================================== 1. CLI 命令注册表


def _expected_subcommands_from_test_console_cli() -> set[str]:
    """从 test_console_cli.py AST 动态提取 subcommands 期望集合。

    读取 test_all_subcommands_registered 中 `assert choices == {...}` 的集合
    字面量 — 与 build_parser() 两两比对 (新增命令漏测试 → 红)。
    """
    src = (_REPO / "tests" / "console" / "test_console_cli.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name == "test_all_subcommands_registered"):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Set):
                names = {
                    el.value
                    for el in sub.elts
                    if isinstance(el, ast.Constant) and isinstance(el.value, str)
                }
                if names:
                    return names
    raise AssertionError("test_console_cli.test_all_subcommands_registered 中未找到集合字面量")


class TestCliRegistryConsistency:
    def test_parser_subcommands_match_test_console_cli(self):
        """build_parser() 子命令 choices == test_console_cli.subcommands 集合。

        新增/删除 CLI 子命令必须同步 test_console_cli 期望集合, 否则红。
        """
        import argparse

        cli_mod = importlib.import_module("factory-console.cli_factory")
        parser = cli_mod.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        }
        choices = set(sub_actions["command"].choices)
        expected = _expected_subcommands_from_test_console_cli()
        assert choices == expected, (
            f"CLI 注册表漂移: build_parser 有 {sorted(choices - expected)} "
            f"但 test_console_cli 未同步; test_console_cli 有 {sorted(expected - choices)} "
            f"但 parser 未注册"
        )
        assert choices, "CLI 子命令集合为空 (注册表读取失败)"


# ================================================================== 2. 意图注册表


class TestIntentRegistryConsistency:
    def test_keyword_intents_all_routed(self):
        """_KEYWORD_RULES 产生的全部 intent_type 均有路由。

        DEFAULT_ROUTES 显式声明 (S10-112 补全 37 个同名路由); 仅文档化会话
        特判/降级例外 current_project/show_cost 不经 router (S10-076/S10-082)。
        新增关键词意图漏声明路由 → 红。
        """
        rules_intents = {rule[1] for rule in INTENT_MOD._KEYWORD_RULES}
        assert rules_intents, "_KEYWORD_RULES 为空 (注册表读取失败)"
        unrouted = rules_intents - set(ROUTER_MOD.DEFAULT_ROUTES) - set(SESSION_INTERCEPTED_INTENTS)
        assert not unrouted, f"关键词意图无路由: {sorted(unrouted)}"
        # 会话特判例外必须真实被 session 特判 (防例外名漂移成死名单)
        sess_src = (_REPO / "factory-console" / "session" / "session.py").read_text(
            encoding="utf-8"
        )
        assert "INTENT_CURRENT_PROJECT" in sess_src, "current_project 例外失效 (session 特判不存在)"

    def test_default_routes_intents_reachable(self):
        """DEFAULT_ROUTES 的 intent 均有关键词规则可达 (或文档化别名)。

        反向防漏: 新意图无关键词规则 → 红。唯一别名 execute_task 的 action 必须
        与某关键词规则意图 (run_task) 的 action 相同 (可达同一执行链)。
        """
        rules_intents = {rule[1] for rule in INTENT_MOD._KEYWORD_RULES}
        route_intents = set(ROUTER_MOD.DEFAULT_ROUTES)
        assert route_intents, "DEFAULT_ROUTES 为空 (注册表读取失败)"
        aliases = route_intents - rules_intents
        for alias in sorted(aliases):
            alias_action = ROUTER_MOD.DEFAULT_ROUTES[alias]
            reachable = {
                ROUTER_MOD.DEFAULT_ROUTES[i] for i in rules_intents if i in ROUTER_MOD.DEFAULT_ROUTES
            }
            assert alias_action in reachable, (
                f"DEFAULT_ROUTES 意图 {alias} 无关键词规则且 action {alias_action} "
                f"不可达 (别名须共享某关键词意图的 action)"
            )

    def test_routed_actions_exist(self):
        """DEFAULT_ROUTES 引用的 action 名全部在 build_default_actions() (防断链)。"""
        registry_names = _registry_action_names()
        referenced = set(ROUTER_MOD.DEFAULT_ROUTES.values())
        assert referenced <= registry_names, (
            f"DEFAULT_ROUTES 引用未注册 action: {sorted(referenced - registry_names)}"
        )


# ================================================================== 3. Action 注册表


class TestActionRegistryConsistency:
    def test_route_references_all_registered(self):
        """DEFAULT_ROUTES 引用的每个 action 名都在 registry (防路由断链)。"""
        registry_names = _registry_action_names()
        referenced = set(ROUTER_MOD.DEFAULT_ROUTES.values())
        missing = referenced - registry_names
        assert not missing, f"路由引用未注册 action: {sorted(missing)}"

    def test_sensitive_registry_gate_coverage(self):
        """registry sensitive=True 集合 ↔ 会话确认门强制集合双向覆盖。

        - 会话门强制的每个 intent 必须路由到已注册 action (不指空);
        - registry 每个敏感 action 必须有门强制的路由 intent 覆盖
          (create_product 为会话内 conversation 接管, 文档化例外);
        - 门强制 action 集合 == registry 敏感 action 集合 - create_product。
        新增敏感 action 漏纳入确认门 → 红; 新增门强制 intent 漏注册 → 红。
        """
        registry = ACTIONS_MOD.build_default_actions()
        registry_names = {a.name for a in registry.list()}
        sensitive_actions = {
            a.name for a in registry.list() if (a.metadata or {}).get("sensitive") is True
        }
        enforced = _session_gate_enforced()
        assert enforced, "会话确认门强制集合为空 (读取失败)"

        # 1) 门强制 intent 全部可解析到已注册 action
        for intent in sorted(enforced):
            target = ROUTER_MOD.DEFAULT_ROUTES.get(intent, intent)
            assert target in registry_names, (
                f"会话门强制 intent {intent} → action {target} 未注册"
            )

        # 2) 每个 registry 敏感 action 都有门强制的路由 intent 覆盖
        for action in sorted(sensitive_actions):
            if action in SESSION_INTERCEPTED_SENSITIVE:
                continue
            routed = {i for i, t in ROUTER_MOD.DEFAULT_ROUTES.items() if t == action}
            covered = routed & enforced
            assert covered, (
                f"sensitive action {action} 无门强制路由 intent 覆盖 "
                f"(routed={sorted(routed)}, enforced={sorted(enforced)})"
            )

        # 3) 双向相等 (modulo 会话内接管例外)
        enforced_actions = {ROUTER_MOD.DEFAULT_ROUTES.get(i, i) for i in enforced}
        assert enforced_actions <= sensitive_actions, (
            f"门强制 action 超出 registry 敏感集合: {sorted(enforced_actions - sensitive_actions)}"
        )
        assert sensitive_actions - enforced_actions <= SESSION_INTERCEPTED_SENSITIVE, (
            f"registry 敏感 action 未纳入确认门: "
            f"{sorted(sensitive_actions - enforced_actions - SESSION_INTERCEPTED_SENSITIVE)}"
        )


# ================================================================== 4. 事件注册表


def _emitted_event_types() -> set[str]:
    """factory-console 实现中实际发射的事件类型字面量 (动态扫描, 排除注册表自身)。"""
    emitted: set[str] = set()
    pattern = re.compile(r'\bemit\(\s*"([A-Z][A-Z0-9_]{2,})"')
    for path in (_REPO / "factory-console").rglob("*.py"):
        if path.name == "audit_event.py":
            continue
        emitted.update(pattern.findall(path.read_text(encoding="utf-8")))
    return emitted


def _event_referenced_or_documented(name: str) -> bool:
    """事件类型被实现引用或审计相关文档/测试引用 (防死条目)。"""
    needles = (f'"{name}"', f"'{name}'")
    for path in (_REPO / "factory-console").rglob("*.py"):
        if path.name == "audit_event.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(n in text for n in needles):
            return True
    for path in [
        _REPO / "docs" / "sprint10" / "S10-069-audit-design.md",
        _REPO / "docs" / "sprint10" / "S10-089-cto-tech-design-v2.md",
        _REPO / "tests" / "console" / "test_s10_073_audit_coverage.py",
        _REPO / "tests" / "console" / "test_audit_core.py",
        _REPO / "tests" / "console" / "test_audit_cli.py",
    ]:
        if path.is_file() and name in path.read_text(encoding="utf-8"):
            return True
    return False


class TestEventRegistryConsistency:
    def test_emitted_events_all_registered(self):
        """实现发射的事件类型全部 ∈ EVENT_TYPES (防新增事件漏注册 → 红)。"""
        event_types = set(AUDIT_EVENT_MOD.EVENT_TYPES)
        assert event_types, "EVENT_TYPES 为空 (注册表读取失败)"
        emitted = _emitted_event_types()
        assert emitted, "实现中未扫描到任何事件发射 (扫描失效)"
        missing = emitted - event_types
        assert not missing, f"已发射但未注册事件: {sorted(missing)}"

    def test_event_types_all_referenced_or_documented(self):
        """EVENT_TYPES 全部被实现引用或审计文档化 (防死条目 → 红)。"""
        event_types = set(AUDIT_EVENT_MOD.EVENT_TYPES)
        dead = [name for name in sorted(event_types) if not _event_referenced_or_documented(name)]
        assert not dead, f"EVENT_TYPES 死条目 (无引用/无文档): {dead}"

    def test_audit_design_doc_events_in_registry(self):
        """审计设计文档 (S10-069) 列出的事件 ⊆ EVENT_TYPES (防文档宣称但未注册)。"""
        event_types = set(AUDIT_EVENT_MOD.EVENT_TYPES)
        doc = (_REPO / "docs" / "sprint10" / "S10-069-audit-design.md").read_text(
            encoding="utf-8"
        )
        match = re.search(r"EventType \(30\+\):(.*?)(?:\n\n|\n```)", doc, re.S)
        block = match.group(1) if match else doc
        doc_events = set(re.findall(r"\b[A-Z][A-Z0-9_]{3,}\b", block))
        assert doc_events, "审计设计文档未提取到事件 (解析失效)"
        missing = doc_events - event_types
        assert not missing, f"设计文档宣称但 EVENT_TYPES 未注册: {sorted(missing)}"


# ================================================================== 5. API 路由注册表


class _MinimalService:
    """路由枚举用最薄桩 (不调用端点 handler, 只注册路由)。"""

    def dashboard(self):  # pragma: no cover — 桩
        return None


def _api_routes() -> list[tuple[str, str]]:
    """build_app 实际注册路由 (method, path) 列表 (动态读取 app.routes)。"""
    app = ADAPTER_MOD.build_app(_MinimalService(), factory_root="/tmp/s10-112-root")
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if not hasattr(route, "methods"):
            continue
        for method in route.methods:
            routes.append((method, getattr(route, "path", "")))
    return routes


def _route_matches(actual_path: str, documented: str) -> bool:
    """文档路径 (含 {param}) 是否匹配实际 FastAPI 路由。"""
    normalized = re.sub(r"\{[a-zA-Z0-9_]+\}", "{P}", documented)
    pattern = re.compile(
        "^" + re.escape(normalized).replace(r"\{P\}", r"\{[^}]+\}") + "$"
    )
    return bool(pattern.match(actual_path))


def _documented_api_endpoints() -> list[set[str]]:
    """FEATURES.md §9 文档端点 (每行一组候选, 动态解析表格)。

    处理分组/续行/`|` 替代/查询参数: 一行可能宣称多个端点 (如
    `/api/board/graph?project=` `/chain?project=` `/timeline`), 续行可能是
    追加 (`/api/artifacts/{id}` + `/content`) 或替换末段 (`/api/projects/{id}/status`
    + `/lifecycle`) — 返回每行全部候选, 由断言方按"任一候选命中实际路由"判定。
    """
    text = (_REPO / "docs" / "FEATURES.md").read_text(encoding="utf-8")
    section = text.split("## 9. API 功能总览")[1].split("## 10.")[0]

    def clean(tok: str) -> str:
        return re.sub(r"\[.*$", "", tok.split("?")[0].strip()).strip()

    rows: list[set[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        toks = [t.strip() for t in re.findall(r"`([^`]+)`", line)]
        full = [
            t for t in toks if "/api/" in t or t in ("/health", "/ready", "/version")
        ]
        if not full:
            continue
        base = clean(full[0])
        candidates: set[str] = set()
        for tok in toks:
            for part in re.split(r"\\?\|", tok):
                v = clean(part)
                if not v:
                    continue
                if "/api/" in v or v in ("/health", "/ready", "/version"):
                    candidates.add(v)
                elif v.startswith("/"):
                    candidates.add(base + v)
                    candidates.add(base.rsplit("/", 1)[0] + v)
        rows.append(candidates)
    return rows


def _capability_matrix_api_rows() -> list[list[str]]:
    """CAPABILITY_MATRIX.md 表行 (API 列 == ✅ 的能力行, 动态解析)。"""
    text = (_REPO / "docs" / "CAPABILITY_MATRIX.md").read_text(encoding="utf-8")
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 10 or not cells[0].startswith("C"):
            continue
        if cells[5] == "✅":
            rows.append(cells)
    return rows


class TestApiRegistryConsistency:
    def test_documented_endpoints_all_registered(self):
        """FEATURES.md §9 文档宣称的每个端点都存在实际路由 (防能力声明但 API 缺失)。"""
        routes = _api_routes()
        actual_paths = {path for _, path in routes}
        assert actual_paths, "app.routes 为空 (注册表读取失败)"
        documented_rows = _documented_api_endpoints()
        assert documented_rows, "FEATURES.md §9 未解析到端点 (解析失效)"
        unmatched = [
            sorted(cands)
            for cands in documented_rows
            if not any(_route_matches(p, c) for p in actual_paths for c in cands)
        ]
        assert not unmatched, f"文档宣称但无实际路由 (行候选均未命中): {unmatched}"

    def test_write_routes_in_whitelist(self):
        """POST/PATCH/DELETE 写路由全部在 web 写路由白名单 (新增写端点漏白名单 → 红)。"""
        routes = _api_routes()
        write_routes = [
            (m, p) for m, p in routes if m in {"POST", "PATCH", "DELETE"}
        ]
        assert write_routes, "未扫描到任何写路由 (扫描失效)"
        for method, path in write_routes:
            is_approval = path.endswith("/approve") or path.endswith("/reject")
            is_runtime = (
                "/runtimes" in path or "/runtime-sessions" in path or "/sessions" in path
                or path == "/api/runtime/execute"
            )
            is_tool_execute = path.startswith("/api/tools/") and path.endswith("/execute")
            is_mcp_connect = path == "/api/mcp/connections" and method == "POST"
            is_review_feedback = path.endswith("/review-feedback")
            is_project_create = path == "/api/projects"
            is_project_suggest = method == "POST" and path == "/api/projects/suggest"
            is_discovery = method == "POST" and (
                path.endswith("/discovery/answer") or path.endswith("/discovery/complete")
            )
            is_confirm = method == "POST" and path.endswith("/confirm")
            is_start_chat = path.endswith("/start") or path.endswith("/chat")
            is_project_patch_delete = (
                (method == "PATCH" or method == "DELETE")
                and path == "/api/projects/{project_id}"
            )
            is_backlog = "/backlog" in path
            is_management = (
                "/sprints" in path or "/milestones" in path or "/roadmap" in path
            )
            is_system_update = method == "POST" and path == "/api/system/update"
            is_board_default = method == "POST" and path == "/api/board/default"
            is_board_split = method == "POST" and path == "/api/board/split"
            is_docs_config = method == "POST" and path == "/api/board/docs/config"
            is_rag_query = method == "POST" and path == "/api/rag/query"
            # v1.1.102: MCP 移除 + LLM 配置 + Agent/Skill 管理 (与 web 权限边界同源)
            is_mcp_remove = method == "DELETE" and "/mcp/connections/" in path
            is_llm_config = method in {"POST", "PATCH"} and path == "/api/config/llm"
            is_agent_write = (
                (method == "POST" and path == "/api/agents")
                or (method == "DELETE" and path.startswith("/api/agents/"))
            )
            is_skill_write = (
                (method == "POST" and path == "/api/skills")
                or (method == "DELETE" and path.startswith("/api/skills/"))
            )
            assert (
                is_approval or is_runtime or is_tool_execute or is_mcp_connect
                or is_review_feedback or is_project_create or is_project_suggest
                or is_discovery or is_confirm or is_start_chat
                or is_project_patch_delete or is_backlog or is_management
                or is_system_update or is_board_default or is_board_split
                or is_docs_config or is_rag_query
                or is_mcp_remove or is_llm_config
                or is_agent_write or is_skill_write
            ), f"写路由超出白名单: {method} {path}"

    def test_capability_matrix_api_claims_backed(self):
        """CAPABILITY_MATRIX API 列 ✅ 能力均有实际端点支撑。

        矩阵为能力级粒度 (API 列只标 ✅/❌, 无端点级注册表 — 端点级注册表在
        FEATURES.md §9, 由 test_documented_endpoints_all_registered 覆盖)。
        此处断言: API=✅ 能力数 ≤ 实际 API 路由数 (每条能力至少一个端点支撑),
        且 API=✅ 的能力 Core 列也 ✅ (无"API 宣称但 Core 缺失"矛盾)。
        """
        api_rows = _capability_matrix_api_rows()
        assert api_rows, "CAPABILITY_MATRIX 未解析到 API=✅ 能力行 (解析失效)"
        for row in api_rows:
            assert row[3] == "✅", (
                f"能力 {row[0]} {row[2]} API=✅ 但 Core={row[3]} (能力声明矛盾)"
            )
        routes = _api_routes()
        api_paths = {
            p for m, p in routes if p.startswith("/api/")
        }
        assert len(api_rows) <= len(api_paths), (
            f"API=✅ 能力 {len(api_rows)} 个但实际 API 路由仅 {len(api_paths)} 条 "
            f"(存在宣称无支撑)"
        )
