"""S10-112 P0-11 — 对称路径一致性测试 (v1.1.81)。

同场景双入口断言对齐 (每个对称路径一个测试, 同 fixture 数据):
1. conversation vs discovery: 同输入序列 ("我想做个记账App"→逐字段→确认)
   → 同状态推进 (收集阶段 → 确认阶段, 两路径枚举名不同但阶段语义一致:
   conversation DISCOVERY == discovery DISCOVERING/CLARIFYING;
   conversation PRODUCT_CONFIRMATION == discovery READY_FOR_CONFIRMATION)
   + 同字段提取结果 (problem/user/core_features 同值)
2. CLI vs API 双入口 (同数据源同结构):
   - agent list   ↔ GET /api/agents
   - skill list   ↔ GET /api/skills
   - project list ↔ GET /api/projects
   - board 文档   ↔ /board docs 配置命令 (docs_config.json 同一数据源)

禁止空断言/跳过; 数据从实现动态读取 (不硬编码快照)。
basename 全仓库唯一 (test_s10_112_* 前缀)。
"""

from __future__ import annotations

import importlib
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_FACTORY_CORE = _REPO / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

CONV_MOD = importlib.import_module("factory-console.session.conversation")
DIS_MOD = importlib.import_module("factory-console.session.discovery")
CLI_MOD = importlib.import_module("factory-console.cli_factory")
ADAPTER_MOD = importlib.import_module("factory-console.web.backend.fastapi_adapter")
COMMANDS_MOD = importlib.import_module("factory-console.session.commands")
CONTEXT_MOD = importlib.import_module("factory-console.session.context")
BOARD_MOD = importlib.import_module("factory-console.session.board")

from fastapi.testclient import TestClient  # noqa: E402  (console venv 必装)


# ================================================================== 1. conversation vs discovery


def _run_conversation_flow(idea: str, answers: list[str]) -> dict:
    """conversation 路径 (LLM 禁用 → 规则逐字段): 输入序列 → 状态+字段提取。"""
    mgr = CONV_MOD.ConversationManager(analyzer=None)
    mgr.start_product_discovery(idea)
    states = [mgr.state]
    for answer in answers:
        mgr.handle_product_answer(answer)
        states.append(mgr.state)
    pi = mgr.product_intent
    return {
        "states": states,
        "problem": pi.problem,
        "user": pi.user,
        "core_features": list(pi.core_features),
    }


def _run_discovery_flow(idea: str, answers: list[str]) -> dict:
    """discovery 路径 (LLM 禁用 + 仅必填字段): 输入序列 → 状态+字段提取。"""
    session = DIS_MOD.DiscoverySession.start(idea, analyzer=None, ask_enhanced=False)
    states = [session.current_state]
    for answer in answers:
        result = session.process_user_input(answer)
        states.append(result["state"])
    pi = session.product_intent
    return {
        "states": states,
        "problem": pi.problem,
        "user": pi.user,
        "core_features": list(pi.core_features),
    }


class TestConversationDiscoverySymmetry:
    """同输入序列 → 同状态推进 + 同字段提取 (两发现路径对称)。"""

    def test_same_inputs_same_state_progression_and_fields(self):
        idea = "我想做个记账App"
        answers = ["记一笔账太麻烦", "个人用户", "记账、报表、预算"]
        conv = _run_conversation_flow(idea, answers)
        disc = _run_discovery_flow(idea, answers)

        # 同字段提取结果 (核心对称点: 字段归类/解析一致)
        assert conv["problem"] == disc["problem"] == "记一笔账太麻烦"
        assert conv["user"] == disc["user"] == "个人用户"
        assert conv["core_features"] == disc["core_features"] == ["记账", "报表", "预算"]

        # 同状态推进: 3 个收集阶段 → 1 个确认阶段 (两路径枚举名不同但语义一致)
        collecting_conv = {CONV_MOD.ConversationState.DISCOVERY}
        collecting_disc = {DIS_MOD.DiscoveryState.DISCOVERING, DIS_MOD.DiscoveryState.CLARIFYING}
        confirm_conv = CONV_MOD.ConversationState.PRODUCT_CONFIRMATION
        confirm_disc = DIS_MOD.DiscoveryState.READY_FOR_CONFIRMATION

        def phase_sequence(states, collecting, confirm):
            return [1 if s in collecting else (2 if s == confirm else 0) for s in states]

        conv_phases = phase_sequence(conv["states"], collecting_conv, confirm_conv)
        disc_phases = phase_sequence(disc["states"], collecting_disc, confirm_disc)
        assert conv_phases == disc_phases == [1, 1, 1, 2], (
            f"状态推进不一致: conversation={conv_phases} discovery={disc_phases}"
        )
        # 终态即确认阶段 (验收: DISCOVERY→PRODUCT_CONFIRMATION / →READY_FOR_CONFIRMATION)
        assert conv["states"][-1] == confirm_conv
        assert disc["states"][-1] == confirm_disc


# ================================================================== 2. CLI vs API 双入口


def _make_cli(root: Path) -> CLI_MOD.FactoryCLI:
    """隔离数据目录 = root 的 FactoryCLI (与 API factory_root 同数据源)。"""
    cfg = CLI_MOD.ConfigProvider(
        environ={"DATA_DIR": str(root)},
        env_file=root / "env",
        user_config_file=root / "cfg.json",
    )
    return CLI_MOD.FactoryCLI(cfg, root=root)


def _run_cli(root: Path, *argv: str) -> str:
    """运行 CLI 命令并捕获 stdout (rc 必须 0)。"""
    cli = _make_cli(root)
    args = CLI_MOD.build_parser().parse_args(list(argv))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.run(args)
    assert rc == 0, f"CLI {' '.join(argv)} rc={rc}: {buf.getvalue()}"
    return buf.getvalue()


def _seed_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _api_client(root: Path):
    """真实 ConsoleService 装配的 API client (同一 factory_root 数据源)。"""
    service = ADAPTER_MOD.build_console_service(root)
    app = ADAPTER_MOD.build_app(service, factory_root=str(root))
    return TestClient(app)


class TestCliApiSymmetry:
    def test_agent_list_matches_api_agents(self, tmp_path: Path):
        """agent list ↔ GET /api/agents: 同 agents.json 数据源, 输出结构一致。"""
        root = tmp_path / "factory"
        _seed_json(root / "agents" / "agents.json", {"agents": {
            "a1": {"id": "a1", "name": "Alice", "role": "pm", "skills": ["x", "y"]},
            "a2": {"id": "a2", "name": "Bob", "role": "dev", "skills": ["z"]},
        }})

        cli_out = _run_cli(root, "agent", "list")
        cli_rows = re.findall(r"  - (\S+) \| (.+?) \| role=(\S+) \| skills=\[([^\]]*)\]", cli_out)
        assert cli_rows, f"CLI agent list 未解析出行: {cli_out}"
        cli_by_id = {row[0]: {"name": row[1], "role": row[2], "skills": row[3]} for row in cli_rows}

        with _api_client(root) as client:
            resp = client.get("/api/agents")
            assert resp.status_code == 200
            data = resp.json()
            api_agents = data["agents"]
            assert data["count"] == len(api_agents) == len(cli_by_id)

        api_by_id = {a["id"]: a for a in api_agents}
        assert set(api_by_id) == set(cli_by_id), (
            f"CLI/API agent id 集合不一致: CLI={sorted(cli_by_id)} API={sorted(api_by_id)}"
        )
        for aid in cli_by_id:
            assert api_by_id[aid]["name"] == cli_by_id[aid]["name"], aid
            assert api_by_id[aid]["role"] == cli_by_id[aid]["role"], aid
            assert ", ".join(api_by_id[aid]["skills"]) == cli_by_id[aid]["skills"], aid

    def test_skill_list_matches_api_skills(self, tmp_path: Path):
        """skill list ↔ GET /api/skills: skills.json 注册条目两入口结构一致。"""
        root = tmp_path / "factory"
        _seed_json(root / "skills" / "skills.json", {"skills": {
            "flutter": {"id": "flutter", "name": "Flutter", "category": "mobile", "version": "1.0"},
            "backend": {"id": "backend", "name": "后端开发", "category": "backend", "version": "2.1"},
        }})

        cli_out = _run_cli(root, "skill", "list")
        cli_rows = re.findall(
            r"  - (\S+) \| (.+?) \| category=(\S+) \| v(\S*)", cli_out
        )
        assert cli_rows, f"CLI skill list 未解析出行: {cli_out}"
        cli_by_id = {row[0]: {"name": row[1], "category": row[2], "version": row[3]} for row in cli_rows}

        with _api_client(root) as client:
            resp = client.get("/api/skills")
            assert resp.status_code == 200
            data = resp.json()
            api_skills = data["skills"]
            assert data["count"] == len(api_skills)

        api_by_id = {s["id"]: s for s in api_skills}
        # 两入口共享数据源: skills.json 注册条目在 CLI 与 API 中同结构出现
        for sid in cli_by_id:
            assert sid in api_by_id, f"skill {sid} 在 CLI 有但 API 缺失"
            api = api_by_id[sid]
            assert api["name"] == cli_by_id[sid]["name"], sid
            assert api["category"] == cli_by_id[sid]["category"], sid
            assert str(api.get("version", "")) == cli_by_id[sid]["version"], sid

    def test_project_list_matches_api_projects(self, tmp_path: Path, monkeypatch):
        """project list ↔ GET /api/projects: org/projects.json 同数据源结构一致。"""
        # 隔离 workspace 示例项目自动发现 (仅扫空目录 → 无外部干扰)
        monkeypatch.setenv("FACTORY_EXAMPLES_DIR", str(tmp_path / "empty-examples"))
        (tmp_path / "empty-examples").mkdir(parents=True, exist_ok=True)
        root = tmp_path / "factory"
        _seed_json(root / "org" / "projects.json", {"projects": {
            "p1": {"id": "p1", "name": "记账App"},
            "p2": {"id": "p2", "name": "台球计分"},
        }})

        cli_out = _run_cli(root, "project", "list")
        cli_rows = re.findall(r"  (\S+)  (\S.*)$", cli_out, re.M)
        assert cli_rows, f"CLI project list 未解析出行: {cli_out}"
        cli_by_id = {row[0]: row[1] for row in cli_rows}

        with _api_client(root) as client:
            resp = client.get("/api/projects")
            assert resp.status_code == 200
            api_projects = resp.json()
            assert api_projects, "API projects 为空"

        api_by_id = {p["id"]: p for p in api_projects}
        assert set(cli_by_id) <= set(api_by_id), (
            f"CLI 项目在 API 缺失: {sorted(set(cli_by_id) - set(api_by_id))}"
        )
        for pid in cli_by_id:
            assert api_by_id[pid]["name"] == cli_by_id[pid], pid

    def test_board_docs_config_matches_command(self, tmp_path: Path):
        """board 文档 ↔ docs 配置命令: /board docs 命令与 /api/board/docs/config
        同一 docs_config.json 数据源 (命令写 → 页面可见; API 写 → 命令可见)。"""
        root = tmp_path / "factory"
        slug = "demo"
        _seed_json(root / "projects" / slug / "product.json", {"name": "Demo产品", "status": "idea"})

        command = COMMANDS_MOD.BoardCommand()
        context = CONTEXT_MOD.SessionContext(workspace=str(root))

        # 1) /board docs add-dir 写入 → API 配置页 (GET) 可见
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = command.execute(f"docs add-dir {slug} docs", context)
        assert rc == 0, buf.getvalue()
        cfg_after_command = BOARD_MOD.read_docs_config(root, slug)
        assert "docs" in cfg_after_command["dirs"], f"命令写入未落库: {cfg_after_command}"

        with _api_client(root) as client:
            page = client.get(f"/api/board/docs/config?project={slug}")
            assert page.status_code == 200
            assert "docs" in page.text, "命令写入的目录未出现在 board 配置页"

        # 2) API POST 写配置 → /board docs list 命令可见
        with _api_client(root) as client:
            resp = client.post(
                f"/api/board/docs/config?project={slug}&dirs=docs%0Adocs%2Fspec&exts=.md,.json"
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body.get("ok") is True
        cfg_after_api = BOARD_MOD.read_docs_config(root, slug)
        assert cfg_after_api["dirs"] == ["docs", "docs/spec"]
        assert cfg_after_api["exts"] == [".md", ".json"]

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = command.execute(f"docs list {slug}", context)
        assert rc == 0, buf.getvalue()
        out = buf.getvalue()
        assert "docs" in out and "docs/spec" in out
        assert ".md, .json" in out

        # 3) 命令宣称的子动作全部实现 (文档宣称的命令存在 — 用法串在实现源码)
        cmds_src = (_REPO / "factory-console" / "session" / "commands.py").read_text(
            encoding="utf-8"
        )
        for sub_action in ("list", "add-dir", "add-ext", "rm-dir"):
            assert sub_action in cmds_src, f"/board docs {sub_action} 命令未实现"
