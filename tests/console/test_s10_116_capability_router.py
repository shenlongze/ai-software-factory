"""tests/console/test_s10_116_capability_router.py — K-1 能力路由 + 员工管理契约测试。

覆盖 (设计 docs/sprint10/S10-116-k1-capability-router-plan.md §2, ≥10):
1. 统一路由确定性: 2 skill/2 agent/2 mcp 含同一 capability fixture →
   同输入同输出 (排序 priority desc → version desc → load asc → id)
2. reason 可解释: 含命中 capabilities + 排序依据
3. skill 路由注入: 有匹配 → 只注入选中 skill; 无匹配 → 全注入 (向后兼容)
4. agent 路由旧行为: 前端/flutter/ui → flutter-dev; 其余 → backend-1 (逐字节)
5. agent 新 capability 匹配: 多 agent 场景 objective 能力需求 → 正确 agent
6. MCP 路由: objective 需工具 → 选 MCP tool; factory mcp list|connect|remove
   可用 (Mock 诚实标注)
7. board 员工 tab: 渲染含 7 Agent + Skill + 装配状态 + 缺失提示; 渲染后 mtime
   不变 (只读)
8. F-4 版本元数据: 7 角色 prompt 含 prompt_version/changed_at/change_summary
9. 注册表门禁: 新 CLI 命令 (mcp) 在 build_parser 注册表可见 + 动作 choices 同步
10. 路由边界: 无交集 / 全 disabled → None; CapabilityResource 校验; 版本语义比较

basename 全仓库唯一 (test_s10_116_* 前缀)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "factory-core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "factory-core"))
if str(_ROOT / "factory-exec") not in sys.path:
    sys.path.insert(0, str(_ROOT / "factory-exec"))

CR = importlib.import_module("factory-console.session.capability_router")
ACTIONS = importlib.import_module("factory-console.session.actions")
BOARD = importlib.import_module("factory-console.session.board")
EF = importlib.import_module("factory-console.session.expert_factory")
CLI = importlib.import_module("factory-console.cli_factory")
SERVICE = importlib.import_module("factory-console.service")
INTENT = importlib.import_module("factory-console.session.intent")
DEV = importlib.import_module("exec.developer")

#: 统一 fixture: 6 资源 (2 skill + 2 agent + 2 mcp) 全含 frontend_ui capability
ROUTER_FIXTURE = [
    CR.CapabilityResource(id="skill-a", type="skill", capabilities=["frontend_ui"],
                          priority=5, version="1.0.0", load=0.0),
    CR.CapabilityResource(id="skill-b", type="skill", capabilities=["frontend_ui"],
                          priority=5, version="2.0.0", load=0.0),  # version 更高 → 胜
    CR.CapabilityResource(id="agent-a", type="agent", capabilities=["frontend_ui"],
                          priority=3, version="1.0.0", load=0.0),
    CR.CapabilityResource(id="agent-b", type="agent", capabilities=["frontend_ui"],
                          priority=3, version="1.0.0", load=0.5),  # load 更高 → 败
    CR.CapabilityResource(id="mcp-a", type="mcp", capabilities=["frontend_ui"],
                          priority=1, version="1.0.0", load=0.0),
    CR.CapabilityResource(id="mcp-b", type="mcp", capabilities=["frontend_ui"],
                          priority=2, version="1.0.0", load=0.0),  # priority 更高 → 胜
]

FULLSTACK_AGENTS_7 = {
    "backend-1": {"id": "backend-1", "role": "Backend Engineer",
                  "skills": ["python", "api", "database"], "supported_tasks": ["backend_api"]},
    "flutter-dev": {"id": "flutter-dev", "role": "Frontend Engineer",
                    "skills": ["flutter", "dart", "ui"], "supported_tasks": ["frontend_page"]},
    "tester-1": {"id": "tester-1", "role": "QA Engineer",
                 "skills": ["test", "qa"], "supported_tasks": ["test_suite"]},
    "frontend-agent": {"id": "frontend-agent", "role": "Frontend Engineer",
                       "skills": ["frontend", "react", "typescript", "ui"], "supported_tasks": ["component"]},
    "pm-1": {"id": "pm-1", "role": "Product Manager",
             "skills": ["product_strategy", "market_research"], "supported_tasks": ["product_strategy"]},
    "architect-1": {"id": "architect-1", "role": "Architect",
                    "skills": ["system_architecture", "backend_engineering"], "supported_tasks": ["system_design"]},
    "qa-lead-1": {"id": "qa-lead-1", "role": "QA Lead",
                  "skills": ["quality_assurance"], "supported_tasks": ["test_plan"]},
}


def _intent(intent_type: str = "run_task", **params):
    return INTENT.IntentObject(intent_type=intent_type, params=params, raw="x")


def _ctx(workspace: Path):
    from factory_console.session.action import ExecutionContext
    from factory_console.session.context import SessionContext

    return ExecutionContext(
        workspace=workspace,
        session=SessionContext(workspace=str(workspace)),
        intent=_intent(),
    )


def _seed_workspace(root: Path, *, agents: dict | None = None,
                    skills: dict | None = None, flat_agents: bool = False) -> Path:
    """工作区数据 (agents.json + skills.json); 返回 workspace 根。"""
    ws = root / "ws"
    (ws / "agents").mkdir(parents=True, exist_ok=True)
    (ws / "skills").mkdir(parents=True, exist_ok=True)
    if agents is not None:
        payload = agents if flat_agents else {"agents": agents}
        (ws / "agents" / "agents.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if skills is not None:
        (ws / "skills" / "skills.json").write_text(
            json.dumps({"skills": skills}, ensure_ascii=False), encoding="utf-8")
    return ws


# ================================================================== 1-2. 统一路由确定性 + reason 可解释


class TestUnifiedRouterDeterminism:
    def test_route_deterministic_same_output(self):
        """同输入同输出 (确定性): 跨类型排序 priority desc → version desc → load asc。"""
        router = CR.CapabilityRouter(ROUTER_FIXTURE)
        req = CR.CapabilityRequest(objective="做前端页面", capabilities=["frontend_ui"])
        d1 = router.route(req)
        d2 = router.route(req)
        assert d1 is not None and d2 is not None
        assert d1.resource_id == d2.resource_id == "skill-b"  # priority 5 最高; version 2.0.0 胜
        assert d1.reason == d2.reason

    def test_route_priority_then_version_then_load(self):
        """排序依据: priority desc → version desc → load asc → id。"""
        # 仅 skills: 同 priority → version 更高胜
        skills = [r for r in ROUTER_FIXTURE if r.type == "skill"]
        d = CR.CapabilityRouter(skills).route(
            CR.CapabilityRequest(capabilities=["frontend_ui"]))
        assert d.resource_id == "skill-b"
        # 仅 agents: 同 priority/version → load 更低胜
        agents = [r for r in ROUTER_FIXTURE if r.type == "agent"]
        d = CR.CapabilityRouter(agents).route(
            CR.CapabilityRequest(capabilities=["frontend_ui"]))
        assert d.resource_id == "agent-a"
        # 仅 mcps: priority 更高胜
        mcps = [r for r in ROUTER_FIXTURE if r.type == "mcp"]
        d = CR.CapabilityRouter(mcps).route(
            CR.CapabilityRequest(capabilities=["frontend_ui"]))
        assert d.resource_id == "mcp-b"

    def test_reason_explainable(self):
        """reason 可解释: 含命中 capabilities + 候选集合 + 排序依据。"""
        d = CR.CapabilityRouter(ROUTER_FIXTURE).route(
            CR.CapabilityRequest(capabilities=["frontend_ui"]))
        assert "命中 capabilities {frontend_ui}" in d.reason
        assert "排序按 priority desc → version desc → load asc → id" in d.reason
        assert "'skill-b'" in d.reason
        assert "priority=5" in d.reason and "version=2.0.0" in d.reason

    def test_version_semantic_comparison(self):
        """版本语义比较: 1.10.0 > 1.9.0 (数字段, 非字典序)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="v1", type="skill", capabilities=["x"], version="1.9.0"),
            CR.CapabilityResource(id="v2", type="skill", capabilities=["x"], version="1.10.0"),
        ])
        d = router.route(CR.CapabilityRequest(capabilities=["x"]))
        assert d.resource_id == "v2"

    def test_no_intersection_returns_none(self):
        """无交集 → None (调用方兜底)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="s1", type="skill", capabilities=["frontend_ui"]),
        ])
        assert router.route(CR.CapabilityRequest(capabilities=["database"])) is None

    def test_all_disabled_returns_none(self):
        """全 disabled → None (无可用资源, 不臆造)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="s1", type="skill", capabilities=["frontend_ui"],
                                  status="disabled"),
            CR.CapabilityResource(id="s2", type="skill", capabilities=["frontend_ui"],
                                  status="disabled"),
        ])
        assert router.route(CR.CapabilityRequest(capabilities=["frontend_ui"])) is None

    def test_resource_validation(self):
        """CapabilityResource 校验: id/type/status/load 响亮拒绝 (不静默)。"""
        import pytest

        with pytest.raises(ValueError):
            CR.CapabilityResource(id="", type="skill", capabilities=["x"])
        with pytest.raises(ValueError):
            CR.CapabilityResource(id="s1", type="robot", capabilities=["x"])
        with pytest.raises(ValueError):
            CR.CapabilityResource(id="s1", type="skill", capabilities=["x"], status="broken")
        with pytest.raises(ValueError):
            CR.CapabilityResource(id="s1", type="skill", capabilities=["x"], load=-1)

    def test_derive_capabilities_deterministic(self):
        """objective 关键词推导确定性: 同 objective 同输出, 保序去重。"""
        # "数据库"→database, "接口"→api, "数据"→data_analysis (规则表命中, 保序去重)
        assert CR.derive_capabilities("数据库接口") == ["database", "api", "data_analysis"]
        assert CR.derive_capabilities("数据库接口") == CR.derive_capabilities("数据库接口")
        assert CR.derive_capabilities("xyzabc") == []


# ================================================================== 3. skill 路由注入


class TestSkillRouting:
    def test_route_skills_selects_matching(self):
        """有匹配 → 只返回选中 skill + 可解释 reason。"""
        selected, reason = CR.route_skills("写个接口", ["backend_development", "software_testing"])
        assert selected == ["backend_development"]
        assert "命中 capabilities" in reason

    def test_route_skills_no_match_falls_back_all(self):
        """无匹配 → 全量 skills 兜底 (向后兼容全注入)。"""
        selected, reason = CR.route_skills("xyzabc", ["backend_development", "software_testing"])
        assert selected == ["backend_development", "software_testing"]
        assert "兜底全注入" in reason

    def test_build_prompt_injects_only_selected(self):
        """developer.py 注入改造: 有匹配 → 只注入路由选中 + reason。"""
        da = DEV.DeveloperAgent(_FakeProvider())
        prompt = da.build_prompt(objective="写个接口", skills=["backend_development", "software_testing"])
        assert "You have skill backend_development" in prompt
        assert "selected by router:" in prompt
        assert "software_testing" not in prompt

    def test_build_prompt_no_match_injects_all(self):
        """向后兼容: 无匹配 → 全注入 (现状, 零变化)。"""
        da = DEV.DeveloperAgent(_FakeProvider())
        prompt = da.build_prompt(objective="xyzabc", skills=["backend_development", "software_testing"])
        assert "You have the following skills: backend_development, software_testing" in prompt
        assert "Apply these skills" in prompt

    def test_route_skills_external_registry_capabilities(self, tmp_path):
        """skills.json 外部注册 capabilities → 路由可用 (B-1 资源域)。"""
        skills_file = tmp_path / "skills.json"
        skills_file.write_text(json.dumps({
            "skills": {
                "db_skill": {"id": "db_skill", "name": "数据库技能",
                             "capabilities": ["database"], "version": "2.1.0"},
            }
        }), encoding="utf-8")
        selected, reason = CR.route_skills("数据库 schema 设计", ["db_skill", "other_skill"],
                                           skills_file=skills_file)
        assert selected == ["db_skill"]
        assert "version=2.1.0" in reason


class _FakeProvider:
    def generate(self, req):
        return "ok"


# ================================================================== 4-5. agent 路由


class TestAgentRouting:
    def test_old_keyword_behavior_preserved(self):
        """旧行为逐字节保留: 前端/flutter/ui → flutter-dev; 其余 → backend-1。"""
        for objective in ("实现前端页面", "写个 flutter 组件", "修复 ui 布局", "优化界面交互"):
            assert ACTIONS.select_agent(_intent("run_task", objective=objective)) == "flutter-dev"
        assert ACTIONS.select_agent(_intent("run_task", objective="实现登录功能")) == "backend-1"
        assert ACTIONS.select_agent(_intent("run_task", objective="")) == "backend-1"
        assert ACTIONS.select_agent(None) == "backend-1"
        assert ACTIONS.select_agent(_intent("run_task", agent_id="custom-1")) == "custom-1"

    def test_capability_match_multi_agent(self, tmp_path):
        """新 capability 匹配: 多 agent + 关键词未命中 → objective 能力需求选正确 agent。"""
        agents = {
            "backend-1": {"id": "backend-1", "role": "Backend Engineer",
                          "skills": ["python", "api", "database"], "priority": 0},
            "db-specialist": {"id": "db-specialist", "role": "Database Engineer",
                              "skills": ["database", "sql"], "priority": 2},
        }
        ws = _seed_workspace(tmp_path, agents=agents, flat_agents=True)
        # "数据库 schema 设计" → database → db-specialist (priority 2 > 0)
        assert ACTIONS.select_agent(_intent("run_task", objective="数据库 schema 设计"), _ctx(ws)) == "db-specialist"
        # 未命中能力 → 默认 backend-1 (现状)
        assert ACTIONS.select_agent(_intent("run_task", objective="实现登录功能"), _ctx(ws)) == "backend-1"
        # 显式 agent_id 仍优先
        assert ACTIONS.select_agent(_intent("run_task", objective="数据库 schema 设计", agent_id="custom-9"), _ctx(ws)) == "custom-9"

    def test_agent_registry_capability_resources(self, tmp_path):
        """AgentRegistry.to_capability_resources: capabilities = skills + supported_tasks (只读)。"""
        from factory_console.session.agents import AgentRegistry

        agents_file = tmp_path / "agents.json"
        agents_file.write_text(json.dumps({
            "backend-1": {"id": "backend-1", "role": "Backend Engineer",
                          "skills": ["python", "api", "database"],
                          "supported_tasks": ["backend_api", "database_schema"]},
            "flutter-dev": {"id": "flutter-dev", "role": "Frontend Engineer",
                            "skills": ["flutter", "ui"],
                            "supported_tasks": ["frontend_page"]},
        }), encoding="utf-8")
        resources = AgentRegistry.to_capability_resources(agents_file)
        by_id = {r.id: r for r in resources}
        assert "backend-1" in by_id and by_id["backend-1"].type == "agent"
        assert "api" in by_id["backend-1"].capabilities
        assert "frontend_page" in by_id["flutter-dev"].capabilities
        assert all(r.type == "agent" for r in resources)


# ================================================================== 6. MCP 路由 + CLI


class TestMCPRouting:
    def test_route_mcp_selects_tool(self):
        """objective 需工具 → 选 MCP tool (诚实标注 Mock 可用)。"""
        tools = [
            {"id": "github.create_issue", "name": "github.create_issue",
             "description": "create a github issue", "server": "demo"},
            {"id": "echo", "name": "echo", "description": "echo back input", "server": "demo"},
        ]
        d = CR.route_mcp("帮我创建一个 github issue", tools)
        assert d is not None
        assert d.resource_id == "github.create_issue"
        assert "mcp.github" in d.reason or "命中 capabilities" in d.reason

    def test_route_mcp_no_tool_intent_none(self):
        """无工具意图 → None (不臆造)。"""
        tools = [{"id": "echo", "name": "echo", "description": "echo", "server": "demo"}]
        assert CR.route_mcp("实现登录功能", tools) is None
        assert CR.route_mcp("用工具调用一下", []) is None

    def test_mcp_service_connect_list_remove_roundtrip(self, tmp_path):
        """Service 层真实往返 (MockMCPClient): connect → list → remove。"""
        from exec.mcp import MCPRegistry
        from exec.tool import ToolExecutor, ToolRegistry

        ws = tmp_path / "exec-ws"
        ws.mkdir(parents=True)
        executor = ToolExecutor(ToolRegistry.with_system_tools(), workspace_root=ws)
        registry = MCPRegistry(tool_registry=executor.registry)
        service = SERVICE.ConsoleService(mcp_registry=registry, tool_executor=executor)

        created = service.create_mcp_connection("demo", "mock://demo")
        assert created is not None and created["id"].startswith("mcp-")
        assert [t["id"] for t in created["tools"]] == ["echo"]
        conns = service.mcp_connections()
        assert any(c["id"] == created["id"] for c in conns)
        assert service.remove_mcp_connection(created["id"]) is True
        assert service.remove_mcp_connection(created["id"]) is False  # 已移除
        assert all(c["id"] != created["id"] for c in service.mcp_connections())

    def test_mcp_cli_list_connect_remove(self, tmp_path, monkeypatch, capsys):
        """factory mcp list|connect|remove CLI (复用 Service; Mock 诚实标注)。"""
        data_dir = tmp_path / ".factory"
        data_dir.mkdir()
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
        from factory_console.config import ConfigProvider

        cli = CLI.FactoryCLI(ConfigProvider(user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}),
                             root=tmp_path / "repo")
        monkeypatch.setattr(SERVICE.ConsoleService, "mcp_connections",
                            lambda self: [{"id": "mcp-1", "name": "demo", "server_url": "mock://demo",
                                           "transport": "mock", "enabled": True}])
        monkeypatch.setattr(SERVICE.ConsoleService, "mcp_tools",
                            lambda self: [{"id": "echo", "name": "echo", "server": "demo"}])

        parser = CLI.build_parser()
        # list
        rc = cli.run(parser.parse_args(["mcp"]))
        out = capsys.readouterr().out
        assert rc == 0 and "mcp-1" in out and "echo" in out and "Mock 诚实标注" in out
        # connect
        monkeypatch.setattr(SERVICE.ConsoleService, "create_mcp_connection",
                            lambda self, name, url, transport="mock": {
                                "id": "mcp-9", "name": name, "server_url": url,
                                "transport": transport, "enabled": True,
                                "tools": [{"id": "echo", "name": "echo", "server": name}]})
        rc = cli.run(parser.parse_args(["mcp", "connect", "--name", "demo2", "--url", "mock://demo2"]))
        out = capsys.readouterr().out
        assert rc == 0 and "mcp-9" in out and "tools: echo" in out
        # connect 缺参 → rc 1
        rc = cli.run(parser.parse_args(["mcp", "connect"]))
        assert rc == 1
        # remove
        monkeypatch.setattr(SERVICE.ConsoleService, "remove_mcp_connection", lambda self, cid: cid == "mcp-1")
        rc = cli.run(parser.parse_args(["mcp", "remove", "--id", "mcp-1"]))
        out = capsys.readouterr().out
        assert rc == 0 and "已移除" in out
        rc = cli.run(parser.parse_args(["mcp", "remove", "--id", "nope"]))
        assert rc == 1


    def test_mcp_cli_roundtrip_persisted(self, tmp_path, capsys):
        """真实 CLI 往返 (Mock + 持久化): connect → list (跨调用一致) → remove。"""
        data_dir = tmp_path / ".factory"
        data_dir.mkdir()
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
        from factory_console.config import ConfigProvider

        cli = CLI.FactoryCLI(
            ConfigProvider(user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}),
            root=tmp_path / "repo",
        )
        parser = CLI.build_parser()
        rc = cli.run(parser.parse_args(["mcp", "connect", "--name", "demo", "--url", "mock://demo"]))
        assert rc == 0
        store = data_dir / "mcp" / "connections.json"
        assert store.is_file()
        cid = json.loads(store.read_text(encoding="utf-8"))[0]["id"]
        # 第二次独立调用 (新 ConsoleService) 仍可见 → 持久化重放
        rc = cli.run(parser.parse_args(["mcp"]))
        out = capsys.readouterr().out
        assert rc == 0 and "demo" in out and "echo" in out and "Mock 诚实标注" in out
        rc = cli.run(parser.parse_args(["mcp", "remove", "--id", cid]))
        out = capsys.readouterr().out
        assert rc == 0 and "已移除" in out
        rc = cli.run(parser.parse_args(["mcp"]))
        out = capsys.readouterr().out
        assert rc == 0 and "无 MCP 连接" in out


# ================================================================== 7. board 员工 tab (只读)


class TestBoardEmployeesTab:
    def test_render_employees_html_and_read_only(self, tmp_path):
        """员工 tab: 7 Agent + Skill + 装配状态 + 缺失提示; 渲染后 mtime 不变。"""
        agents = dict(FULLSTACK_AGENTS_7)
        agents["broken-agent"] = {"id": "broken-agent", "role": "Broken",
                                  "skills": ["missing_skill_xyz"]}
        skills = {
            "product_strategy": {"id": "product_strategy", "name": "产品策略", "category": "product", "version": "1.0.0"},
            "quality_assurance": {"id": "quality_assurance", "name": "质量保障", "category": "quality", "version": "1.0.0"},
        }
        ws = _seed_workspace(tmp_path, agents=agents, skills=skills)
        files = [ws / "agents" / "agents.json", ws / "skills" / "skills.json"]
        before = {f: f.stat().st_mtime_ns for f in files}

        html = BOARD.render_employees_html(ws)
        after = {f: f.stat().st_mtime_ns for f in files}
        # 只读铁律: 渲染后 mtime 不变
        assert before == after
        # 内容: 标题 + agent + skill + 装配状态 + 缺失提示 + 7 角色
        assert "👥 员工" in html
        assert "backend-1" in html and "flutter-dev" in html
        assert "product_strategy" in html and "quality_assurance" in html
        assert "⚠️缺skill:missing_skill_xyz" in html
        assert "7 角色定义" in html
        for role in EF.PIPELINE_ROLES:
            assert role in html
        assert "prompt_version" in html
        assert "只读展示" in html

    def test_render_employees_failure_safe(self, tmp_path):
        """无数据 → 内置默认注册表 + EXPERT_SKILLS, 不崩 (失败安全)。"""
        ws = tmp_path / "empty-ws"
        ws.mkdir(parents=True)
        html = BOARD.render_employees_html(ws)
        assert "👥 员工" in html
        assert "backend-1" in html  # 默认注册表兜底
        assert "product_strategy" in html  # EXPERT_SKILLS 兜底


# ================================================================== 8. F-4 提示词版本元数据


class TestPromptVersioning:
    def test_all_role_definitions_have_version_metadata(self):
        """8 个 ROLE_DEFINITIONS 全含 prompt_version/changed_at/change_summary。"""
        for role, spec in EF.ROLE_DEFINITIONS.items():
            assert spec.get("prompt_version") == "1.0.0", role
            assert spec.get("changed_at") == "2026-08-25", role
            assert spec.get("change_summary"), role

    def test_seven_pipeline_roles_covered(self):
        """7 角色管线 (PIPELINE_ROLES) 全部可追溯 (设计 §2 第 8 条)。"""
        assert len(EF.PIPELINE_ROLES) == 7
        for role in EF.PIPELINE_ROLES:
            assert "prompt_version" in EF.ROLE_DEFINITIONS[role]
            assert "changed_at" in EF.ROLE_DEFINITIONS[role]
            assert "change_summary" in EF.ROLE_DEFINITIONS[role]


# ================================================================== 9. 注册表门禁


class TestRegistryGate:
    def test_mcp_command_registered_in_parser(self):
        """新 CLI 命令 mcp 在 build_parser 注册表可见 + 动作 choices 同步。"""
        import argparse

        parser = CLI.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        }
        choices = set(sub_actions["command"].choices)
        assert "mcp" in choices
        mcp_parser = sub_actions["command"].choices["mcp"]
        # mcp 动作是位置参数 choices (nargs="?", 非子解析器) — 直接查 parser 参数
        action_names = {
            a.dest for a in mcp_parser._actions
        }
        assert "mcp_action" in action_names
        mcp_action = next(a for a in mcp_parser._actions if a.dest == "mcp_action")
        assert list(mcp_action.choices) == ["list", "connect", "remove"]
        for flag in ("--id", "--name", "--url", "--transport"):
            assert any(getattr(a, "option_strings", None) and flag in a.option_strings
                       for a in mcp_parser._actions), flag

    def test_cli_subcommand_set_synced(self):
        """P0-10 门禁: build_parser 子命令 == test_console_cli 期望集合 (动态读取)。"""
        import ast

        src = (_ROOT / "tests" / "console" / "test_console_cli.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        expected: set[str] = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "test_all_subcommands_registered"):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Set):
                    expected = {el.value for el in sub.elts
                                if isinstance(el, ast.Constant) and isinstance(el.value, str)}
        import argparse

        parser = CLI.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        }
        actual = set(sub_actions["command"].choices)
        assert expected, "test_console_cli 期望集合未解析到"
        assert actual == expected

    def test_existing_intent_action_registries_unchanged(self):
        """新增 mcp CLI 不破坏既有 intent/action 注册表 (P0-10 同步)。"""
        from factory_console.session import router as ROUTER_MOD

        routes = ROUTER_MOD.IntentRouter().routes()
        assert routes["run_task"] == "agent.execute_task"
        assert routes["create_project"] == "create_project"
        registry = ACTIONS.build_default_actions()
        assert registry.get("agent.execute_task") is not None


# ================================================================== 10. 回归: 既有关键契约不破坏


class TestRegression:
    def test_developer_and_agents_import_ok(self):
        """关键模块可导入 + 既有断言不破坏 (回归冒烟)。"""
        assert DEV.DeveloperAgent is not None
        assert ACTIONS.select_agent(_intent("run_task", objective="帮我实现登录界面")) == "flutter-dev"
        assert ACTIONS.select_agent(_intent("run_task", objective="实现后端 API")) == "backend-1"

    def test_contract_suite_has_at_least_10_tests(self):
        """契约套件 ≥10 测试 (设计 §2 验收 7)。"""
        import re

        src = Path(__file__).read_text(encoding="utf-8")
        test_count = len(re.findall(r"^    def test_", src, re.M))
        assert test_count >= 10, f"契约测试仅 {test_count} 个 (需 ≥10)"
