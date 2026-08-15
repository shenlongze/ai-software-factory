"""tests/console/test_session_team_models.py — S10-056 批次 A Agent Team 数据模型层。

设计: docs/sprint10/S10-056-team-design.md (§2 数据模型 / §4 数据资产)
覆盖 (验收 A-K):
A. AgentTeam: team_id/name/members/roles/projects/created_at + member_roles/has_member
B. TeamRegistry: create/get/list/has/assign_project/add_member/build_default/load/save;
   默认 software-team 5 成员
C. RoleSystem: 8 角色 (product_manager/architect/backend/frontend/qa/reviewer/devops/
   tester) capabilities 推导; role_matches; enrich_agent 不破坏原字段
D. TaskDependencyGraph: add/get/拓扑排序/空依赖顺序兼容/无环
E. WorkspaceContext: files/completed_tasks/artifacts/agent_history 全字段
F. AgentMessageStore: send/messages_for (architect→backend 指令模型)
G. ConflictDetector: 同文件多任务 → ConflictRecord (open, 不解决)
H. 全部资产落盘 (team.json/teams.json/task_dependencies.json/workspace_context.json/
   agent_messages.json/conflicts.json)
I. 不修改核心/不引入依赖 (测试只 import session 层 + 纯标准库)
J. >=80 测试全绿 + 全量 pytest 不破坏基线
K. 回归: 不影响现有 agents (AgentRegistry 兼容)

测试装配: tmp_path + 构造 json fixtures (零真实 ~/.factory 污染, 零 LLM/网络);
全部 API 一律注入显式 tmp 文件路径, 保持 hermetic。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

AGENTS_MOD = importlib.import_module("factory-console.session.agents")
CONF_MOD = importlib.import_module("factory-console.session.conflicts")
DEPS_MOD = importlib.import_module("factory-console.session.dependencies")
MSGS_MOD = importlib.import_module("factory-console.session.messages")
ROLES_MOD = importlib.import_module("factory-console.session.roles")
TEAMS_MOD = importlib.import_module("factory-console.session.teams")
WS_MOD = importlib.import_module("factory-console.session.workspace")

AgentTeam = TEAMS_MOD.AgentTeam
TeamRegistry = TEAMS_MOD.TeamRegistry
RoleSystem = ROLES_MOD.RoleSystem
TaskDependencyGraph = DEPS_MOD.TaskDependencyGraph
WorkspaceContext = WS_MOD.WorkspaceContext
AgentMessage = MSGS_MOD.AgentMessage
AgentMessageStore = MSGS_MOD.AgentMessageStore
FileOwnership = CONF_MOD.FileOwnership
ConflictRecord = CONF_MOD.ConflictRecord
ConflictDetector = CONF_MOD.ConflictDetector
AgentRegistry = AGENTS_MOD.AgentRegistry


# ------------------------------------------------------------------ 工具/夹具

def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _team_file(tmp_path: Path) -> Path:
    return tmp_path / "teams" / "teams.json"


def _proj_dir(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "demo"


def _backend_agent() -> dict:
    return {"id": "backend-1", "role": "Backend Engineer", "skills": ["python", "api"]}


def _frontend_agent() -> dict:
    return {"id": "flutter-dev", "role": "Frontend Engineer", "skills": ["flutter", "ui"]}


# ================================================================ A. AgentTeam

def test_team_defaults_empty_lists():
    team = AgentTeam(team_id="t1", name="T1")
    assert team.members == []
    assert team.projects == []
    assert team.created_at is None


def test_team_fields():
    team = AgentTeam(
        team_id="t1",
        name="T1",
        members=[{"agent": "a1", "role": "backend"}],
        projects=["p1"],
        created_at="2026-01-01T00:00:00+00:00",
    )
    assert team.team_id == "t1"
    assert team.name == "T1"
    assert team.projects == ["p1"]
    assert team.created_at == "2026-01-01T00:00:00+00:00"


def test_team_member_roles_basic():
    team = AgentTeam(
        team_id="t1",
        name="T1",
        members=[
            {"agent": "a1", "role": "backend"},
            {"agent": "a2", "role": "frontend"},
        ],
    )
    assert team.member_roles() == {"a1": "backend", "a2": "frontend"}


def test_team_member_roles_empty():
    team = AgentTeam(team_id="t1", name="T1")
    assert team.member_roles() == {}


def test_team_member_roles_skips_invalid_members():
    team = AgentTeam(
        team_id="t1",
        name="T1",
        members=[{"agent": "a1", "role": "backend"}, "not-a-dict", {"role": "qa"}],
    )
    assert team.member_roles() == {"a1": "backend"}


def test_team_member_roles_missing_role_empty_string():
    team = AgentTeam(team_id="t1", name="T1", members=[{"agent": "a1"}])
    assert team.member_roles() == {"a1": ""}


def test_team_has_member_true():
    team = AgentTeam(team_id="t1", name="T1", members=[{"agent": "a1", "role": "qa"}])
    assert team.has_member("a1")


def test_team_has_member_false():
    team = AgentTeam(team_id="t1", name="T1", members=[{"agent": "a1", "role": "qa"}])
    assert not team.has_member("nobody")


def test_team_has_member_empty_id_false():
    team = AgentTeam(team_id="t1", name="T1", members=[{"agent": "a1", "role": "qa"}])
    assert not team.has_member("")
    assert not team.has_member(None)


def test_team_to_dict_keys():
    team = AgentTeam(team_id="t1", name="T1")
    data = team.to_dict()
    assert set(data) == {"team_id", "name", "members", "projects", "created_at"}


def test_team_to_dict_members_copied():
    members = [{"agent": "a1", "role": "backend"}]
    team = AgentTeam(team_id="t1", name="T1", members=members)
    data = team.to_dict()
    data["members"].append({"agent": "x", "role": "x"})
    assert team.members == members


def test_team_from_dict_roundtrip():
    raw = {
        "team_id": "t1",
        "name": "T1",
        "members": [{"agent": "a1", "role": "backend"}],
        "projects": ["p1"],
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    team = AgentTeam.from_dict(raw)
    assert team.to_dict() == raw


def test_team_from_dict_missing_fields_defaults():
    team = AgentTeam.from_dict({})
    assert team.team_id == ""
    assert team.name == ""
    assert team.members == []
    assert team.projects == []
    assert team.created_at is None


def test_team_from_dict_alt_id_key():
    team = AgentTeam.from_dict({"id": "legacy-id", "name": "Legacy"})
    assert team.team_id == "legacy-id"


def test_team_from_dict_filters_non_dict_members():
    team = AgentTeam.from_dict({"members": [{"agent": "a1", "role": "qa"}, "bad"]})
    assert team.members == [{"agent": "a1", "role": "qa"}]


def test_team_from_dict_none_fail_safe():
    team = AgentTeam.from_dict(None)
    assert team.members == []
    assert team.projects == []


# ============================================================ B. TeamRegistry

def test_registry_create_returns_team(tmp_path):
    team = TeamRegistry.create("t1", "Team One", teams_file=_team_file(tmp_path))
    assert team["team_id"] == "t1"
    assert team["name"] == "Team One"
    assert team["members"] == []
    assert team["projects"] == []


def test_registry_create_persists(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "Team One", teams_file=tf)
    assert TeamRegistry.has("t1", teams_file=tf)
    assert TeamRegistry.get("t1", teams_file=tf)["name"] == "Team One"


def test_registry_create_empty_team_id_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.create("", "Team", teams_file=_team_file(tmp_path))


def test_registry_create_name_falls_back_to_id(tmp_path):
    team = TeamRegistry.create("t1", "", teams_file=_team_file(tmp_path))
    assert team["name"] == "t1"


def test_registry_create_with_members(tmp_path):
    team = TeamRegistry.create(
        "t1",
        "Team One",
        members=[{"agent": "a1", "role": "backend"}],
        teams_file=_team_file(tmp_path),
    )
    assert team["members"] == [{"agent": "a1", "role": "backend"}]


def test_registry_get_missing_returns_none(tmp_path):
    assert TeamRegistry.get("ghost", teams_file=_team_file(tmp_path)) is None


def test_registry_list_sorted(tmp_path):
    tf = _team_file(tmp_path)
    _write_json(
        tf,
        {
            "beta": {"team_id": "beta", "name": "B", "members": [], "projects": [], "created_at": "x"},
            "alpha": {"team_id": "alpha", "name": "A", "members": [], "projects": [], "created_at": "x"},
        },
    )
    ids = [t["team_id"] for t in TeamRegistry.list(teams_file=tf)]
    assert ids == ["alpha", "beta"]


def test_registry_list_missing_file_default_team(tmp_path):
    teams = TeamRegistry.list(teams_file=_team_file(tmp_path))
    assert len(teams) == 1
    assert teams[0]["team_id"] == "software-team"


def test_registry_has_true_after_create(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    assert TeamRegistry.has("t1", teams_file=tf)


def test_registry_has_false(tmp_path):
    assert not TeamRegistry.has("ghost", teams_file=_team_file(tmp_path))


def test_registry_has_default_team_on_missing_file(tmp_path):
    assert TeamRegistry.has("software-team", teams_file=_team_file(tmp_path))


def test_registry_assign_project_appends(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    team = TeamRegistry.assign_project("t1", "scorepocket", teams_file=tf)
    assert team["projects"] == ["scorepocket"]


def test_registry_assign_project_dedupe(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    TeamRegistry.assign_project("t1", "scorepocket", teams_file=tf)
    team = TeamRegistry.assign_project("t1", "scorepocket", teams_file=tf)
    assert team["projects"] == ["scorepocket"]


def test_registry_assign_project_missing_team_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.assign_project("ghost", "p1", teams_file=_team_file(tmp_path))


def test_registry_add_member_appends(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    team = TeamRegistry.add_member("t1", "a1", "backend", teams_file=tf)
    assert {"agent": "a1", "role": "backend"} in team["members"]


def test_registry_add_member_updates_existing_role(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", members=[{"agent": "a1", "role": "backend"}], teams_file=tf)
    team = TeamRegistry.add_member("t1", "a1", "architect", teams_file=tf)
    assert team["members"] == [{"agent": "a1", "role": "architect"}]


def test_registry_add_member_missing_team_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.add_member("ghost", "a1", "backend", teams_file=_team_file(tmp_path))


def test_registry_add_member_empty_agent_raises(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    with pytest.raises(ValueError):
        TeamRegistry.add_member("t1", "", "backend", teams_file=tf)


def test_registry_add_member_persists(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    TeamRegistry.add_member("t1", "a1", "qa", teams_file=tf)
    reloaded = TeamRegistry.load(tf)
    assert {"agent": "a1", "role": "qa"} in reloaded["t1"]["members"]


def test_registry_build_default_team_id(tmp_path):
    team = TeamRegistry.build_default_team()
    assert team["team_id"] == "software-team"
    assert team["name"] == "AI Software Team"


def test_registry_build_default_team_5_members(tmp_path):
    team = TeamRegistry.build_default_team()
    assert len(team["members"]) == 5


def test_registry_build_default_team_roles(tmp_path):
    team = TeamRegistry.build_default_team()
    roles = {m["agent"]: m["role"] for m in team["members"]}
    assert roles == {
        "pm-agent": "product_manager",
        "architect-agent": "architect",
        "backend-1": "backend",
        "flutter-dev": "frontend",
        "qa-agent": "qa",
    }


def test_registry_default_team_members_constant():
    assert len(TEAMS_MOD.DEFAULT_TEAM_MEMBERS) == 5
    agents = [m["agent"] for m in TEAMS_MOD.DEFAULT_TEAM_MEMBERS]
    assert agents == ["pm-agent", "architect-agent", "backend-1", "flutter-dev", "qa-agent"]


def test_registry_default_team_constant():
    assert TEAMS_MOD.DEFAULT_TEAM["team_id"] == "software-team"
    assert TEAMS_MOD.DEFAULT_TEAM["name"] == "AI Software Team"
    assert len(TEAMS_MOD.DEFAULT_TEAM["members"]) == 5
    assert TEAMS_MOD.DEFAULT_TEAM["projects"] == []


def test_registry_default_team_id_name_constants():
    assert TEAMS_MOD.DEFAULT_TEAM_ID == "software-team"
    assert TEAMS_MOD.DEFAULT_TEAM_NAME == "AI Software Team"


def test_registry_load_missing_file_falls_back_default(tmp_path):
    registry = TeamRegistry.load(_team_file(tmp_path))
    assert set(registry) == {"software-team"}


def test_registry_load_corrupt_file_falls_back_default(tmp_path):
    path = _write_json(_team_file(tmp_path), "{corrupt json")
    registry = TeamRegistry.load(path)
    assert set(registry) == {"software-team"}


def test_registry_load_empty_file_falls_back_default(tmp_path):
    path = _write_json(_team_file(tmp_path), {})
    registry = TeamRegistry.load(path)
    assert set(registry) == {"software-team"}


def test_registry_load_valid_file(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    registry = TeamRegistry.load(tf)
    assert registry["t1"]["name"] == "T1"


def test_registry_save_creates_file(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", teams_file=tf)
    assert tf.is_file()
    data = _read_json(tf)
    assert data["t1"]["team_id"] == "t1"


def test_registry_save_load_roundtrip(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "T1", members=[{"agent": "a1", "role": "backend"}], teams_file=tf)
    TeamRegistry.assign_project("t1", "p1", teams_file=tf)
    registry = TeamRegistry.load(tf)
    assert registry["t1"]["members"] == [{"agent": "a1", "role": "backend"}]
    assert registry["t1"]["projects"] == ["p1"]


def test_registry_created_at_preserved_roundtrip(tmp_path):
    tf = _team_file(tmp_path)
    created = TeamRegistry.create("t1", "T1", teams_file=tf)
    reloaded = TeamRegistry.get("t1", teams_file=tf)
    assert reloaded["created_at"] == created["created_at"]


def test_registry_add_team_overwrite(tmp_path):
    tf = _team_file(tmp_path)
    TeamRegistry.create("t1", "Old", teams_file=tf)
    TeamRegistry.add_team(
        {"team_id": "t1", "name": "New", "members": [], "projects": [], "created_at": "x"},
        teams_file=tf,
    )
    assert TeamRegistry.get("t1", teams_file=tf)["name"] == "New"


def test_registry_add_team_empty_id_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.add_team({"team_id": "", "name": "X"}, teams_file=_team_file(tmp_path))


def test_registry_default_file_path():
    assert str(TeamRegistry.DEFAULT_FILE).endswith(".factory/teams/teams.json")


# ================================================================ C. RoleSystem

def test_roles_eight_roles():
    assert len(ROLES_MOD.ROLES) == 8


def test_roles_design_seven_roles_present():
    for role in (
        "product_manager",
        "architect",
        "backend",
        "frontend",
        "qa",
        "reviewer",
        "devops",
    ):
        assert role in ROLES_MOD.ROLES, role


def test_roles_each_has_capabilities():
    for role, spec in ROLES_MOD.ROLES.items():
        assert spec["capabilities"], role


def test_roles_each_has_skills():
    for role, spec in ROLES_MOD.ROLES.items():
        assert spec["skills"], role


def test_capabilities_for_explicit_capabilities():
    agent = {"role": "backend", "capabilities": ["custom_cap"]}
    assert RoleSystem.capabilities_for(agent) == ["custom_cap"]


def test_capabilities_for_known_role():
    caps = RoleSystem.capabilities_for({"role": "backend"})
    assert "backend_api" in caps
    assert "database_schema" in caps


def test_capabilities_for_role_keyword_match():
    caps = RoleSystem.capabilities_for({"role": "Backend Engineer"})
    assert "backend_api" in caps
    assert "service_implementation" in caps


def test_capabilities_for_qa_role():
    caps = RoleSystem.capabilities_for({"role": "QA Engineer"})
    assert "test_suite" in caps


def test_capabilities_for_unknown_role_skills_fallback():
    caps = RoleSystem.capabilities_for({"role": "Mystery", "skills": ["python"]})
    assert "backend_api" in caps


def test_capabilities_for_unknown_role_unknown_skills_empty():
    caps = RoleSystem.capabilities_for({"role": "Mystery", "skills": ["unrelated"]})
    assert caps == []


def test_capabilities_for_empty_agent_empty():
    assert RoleSystem.capabilities_for({}) == []


def test_capabilities_for_none_empty():
    assert RoleSystem.capabilities_for(None) == []


def test_role_matches_exact():
    assert RoleSystem.role_matches("backend", {"role": "backend"})


def test_role_matches_case_insensitive():
    assert RoleSystem.role_matches("Backend", {"role": "backend"})


def test_role_matches_keyword_in_role():
    assert RoleSystem.role_matches("backend", {"role": "Backend Engineer"})


def test_role_matches_reverse_keyword():
    assert RoleSystem.role_matches("Backend Engineer", {"role": "backend"})


def test_role_matches_capability_contains():
    assert RoleSystem.role_matches(
        "frontend_page", {"role": "Frontend Engineer", "skills": ["flutter"]}
    )


def test_role_matches_false():
    assert not RoleSystem.role_matches("devops", {"role": "backend"})


def test_role_matches_empty_required_true():
    assert RoleSystem.role_matches("", {"role": "backend"})
    assert RoleSystem.role_matches(None, {"role": "backend"})


def test_role_matches_unknown_required_false():
    assert not RoleSystem.role_matches("mystery_role", {"role": "backend"})


def test_role_matches_none_agent_false():
    assert not RoleSystem.role_matches("backend", None)


def test_enrich_agent_adds_capabilities():
    enriched = RoleSystem.enrich_agent(_backend_agent())
    assert "capabilities" in enriched
    assert "backend_api" in enriched["capabilities"]


def test_enrich_agent_keeps_all_original_fields():
    agent = _backend_agent()
    enriched = RoleSystem.enrich_agent(agent)
    for key, value in agent.items():
        assert enriched[key] == value


def test_enrich_agent_does_not_mutate_input():
    agent = _backend_agent()
    RoleSystem.enrich_agent(agent)
    assert "capabilities" not in agent


def test_enrich_agent_explicit_capabilities_kept():
    agent = {"role": "backend", "capabilities": ["custom"]}
    assert RoleSystem.enrich_agent(agent)["capabilities"] == ["custom"]


def test_enrich_agent_unknown_role_skills_fallback():
    enriched = RoleSystem.enrich_agent({"role": "Mystery", "skills": ["flutter"]})
    assert "frontend_page" in enriched["capabilities"]


# ===================================================== D. TaskDependencyGraph

def test_dep_add_dependency():
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    assert g.get("frontend") == ["backend_api"]


def test_dep_add_multiple_dependencies():
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    g.add_dependency("frontend", "auth")
    assert g.get("frontend") == ["backend_api", "auth"]


def test_dep_add_dependency_dedupe():
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    g.add_dependency("frontend", "backend_api")
    assert g.get("frontend") == ["backend_api"]


def test_dep_get_missing_empty():
    g = TaskDependencyGraph()
    assert g.get("ghost") == []


def test_dep_get_returns_copy():
    g = TaskDependencyGraph()
    g.add_dependency("a", "b")
    deps = g.get("a")
    deps.append("zzz")
    assert g.get("a") == ["b"]


def test_dep_has_true():
    g = TaskDependencyGraph()
    g.add_dependency("a", "b")
    assert g.has("a")
    assert g.has("b")


def test_dep_has_false():
    assert not TaskDependencyGraph().has("ghost")


def test_dep_to_dict():
    g = TaskDependencyGraph({"a": ["b", "c"]})
    assert g.to_dict() == {"a": ["b", "c"]}


def test_dep_from_dict():
    g = TaskDependencyGraph.from_dict({"a": ["b"]})
    assert g.get("a") == ["b"]


def test_dep_from_dict_invalid_empty():
    assert TaskDependencyGraph.from_dict(None).to_dict() == {}
    assert TaskDependencyGraph.from_dict("junk").to_dict() == {}
    assert TaskDependencyGraph.from_dict(["list"]).to_dict() == {}


def test_dep_constructor_init():
    g = TaskDependencyGraph({"a": ["b"]})
    assert g.get("a") == ["b"]


def test_dep_save_creates_file(tmp_path):
    path = tmp_path / "task_dependencies.json"
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    g.save(path)
    assert path.is_file()
    assert _read_json(path) == {"frontend": ["backend_api"]}


def test_dep_save_load_roundtrip(tmp_path):
    path = tmp_path / "task_dependencies.json"
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    g.add_dependency("ranking", "match")
    g.save(path)
    loaded = TaskDependencyGraph.load(path)
    assert loaded.get("frontend") == ["backend_api"]
    assert loaded.get("ranking") == ["match"]


def test_dep_load_missing_empty(tmp_path):
    g = TaskDependencyGraph.load(tmp_path / "nope.json")
    assert g.to_dict() == {}


def test_dep_load_corrupt_empty(tmp_path):
    path = _write_json(tmp_path / "task_dependencies.json", "{bad")
    assert TaskDependencyGraph.load(path).to_dict() == {}


def test_dep_default_file_path():
    assert str(TaskDependencyGraph.DEFAULT_FILE).endswith(
        ".factory/teams/task_dependencies.json"
    )


def test_dep_topological_order_simple_chain():
    g = TaskDependencyGraph({"c": ["b"], "b": ["a"]})
    order = g.topological_order(["a", "b", "c"])
    assert order.index("a") < order.index("b") < order.index("c")


def test_dep_topological_order_deps_first():
    g = TaskDependencyGraph()
    g.add_dependency("frontend", "backend_api")
    order = g.topological_order(["frontend", "backend_api"])
    assert order == ["backend_api", "frontend"]


def test_dep_topological_order_empty_deps_original_order():
    g = TaskDependencyGraph()
    assert g.topological_order(["a", "b", "c"]) == ["a", "b", "c"]


def test_dep_topological_order_no_graph_original_order():
    g = TaskDependencyGraph({"x": ["y"]})
    assert g.topological_order(["p", "q", "r"]) == ["p", "q", "r"]


def test_dep_topological_order_unknown_tasks_preserved():
    g = TaskDependencyGraph({"frontend": ["backend_api"]})
    order = g.topological_order(["frontend", "extra1", "backend_api", "extra2"])
    assert order.index("backend_api") < order.index("frontend")
    assert set(order) == {"frontend", "extra1", "backend_api", "extra2"}


def test_dep_topological_order_partial_deps():
    g = TaskDependencyGraph({"b": ["a"], "d": ["c"]})
    order = g.topological_order(["a", "b", "c", "d"])
    assert order.index("a") < order.index("b")
    assert order.index("c") < order.index("d")


def test_dep_topological_order_cycle_fail_safe():
    g = TaskDependencyGraph({"a": ["b"], "b": ["a"]})
    order = g.topological_order(["a", "b"])
    assert set(order) == {"a", "b"}


def test_dep_topological_order_cycle_all_tasks_returned():
    g = TaskDependencyGraph({"a": ["b"], "b": ["a"], "c": ["a"]})
    order = g.topological_order(["a", "b", "c"])
    assert set(order) == {"a", "b", "c"}


def test_dep_topological_order_empty_input():
    assert TaskDependencyGraph({"a": ["b"]}).topological_order([]) == []


def test_dep_topological_order_self_loop_ignored():
    g = TaskDependencyGraph()
    g.add_dependency("a", "a")
    assert g.topological_order(["a", "b"]) == ["a", "b"]


def test_dep_topological_order_stable_independent():
    g = TaskDependencyGraph({"b": ["a"]})
    order = g.topological_order(["x", "y", "a", "b", "z"])
    assert order.index("x") < order.index("y") < order.index("a") < order.index("z")
    assert order.index("a") < order.index("b")


# ======================================================== E. WorkspaceContext

def test_ws_init_structure():
    ctx = WorkspaceContext.init("scorepocket")
    assert set(ctx) == {"project", "files", "completed_tasks", "artifacts", "agent_history"}


def test_ws_init_empty_lists():
    ctx = WorkspaceContext.init("scorepocket")
    assert ctx["project"] == "scorepocket"
    assert ctx["files"] == []
    assert ctx["completed_tasks"] == []
    assert ctx["artifacts"] == []
    assert ctx["agent_history"] == []


def test_ws_add_file(tmp_path):
    pdir = _proj_dir(tmp_path)
    ctx = WorkspaceContext.add_file(pdir, "main.py")
    assert ctx["files"] == ["main.py"]


def test_ws_add_file_appends_second(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.add_file(pdir, "a.py")
    ctx = WorkspaceContext.add_file(pdir, "b.py")
    assert ctx["files"] == ["a.py", "b.py"]


def test_ws_add_file_dedupe(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.add_file(pdir, "a.py")
    ctx = WorkspaceContext.add_file(pdir, "a.py")
    assert ctx["files"] == ["a.py"]


def test_ws_mark_task_completed(tmp_path):
    pdir = _proj_dir(tmp_path)
    ctx = WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    assert ctx["completed_tasks"] == ["T001"]


def test_ws_mark_task_completed_history_entry(tmp_path):
    pdir = _proj_dir(tmp_path)
    ctx = WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    assert ctx["agent_history"] == [
        {"agent": "backend-1", "task": "T001", "result": "success"}
    ]


def test_ws_mark_task_completed_dedupe_task(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    ctx = WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    assert ctx["completed_tasks"] == ["T001"]
    assert len(ctx["agent_history"]) == 2


def test_ws_mark_task_completed_multiple_tasks(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    ctx = WorkspaceContext.mark_task_completed(pdir, "T002", "flutter-dev", "success")
    assert ctx["completed_tasks"] == ["T001", "T002"]
    assert len(ctx["agent_history"]) == 2


def test_ws_add_artifact(tmp_path):
    pdir = _proj_dir(tmp_path)
    ctx = WorkspaceContext.add_artifact(pdir, "EXS-001.patch")
    assert ctx["artifacts"] == ["EXS-001.patch"]


def test_ws_add_artifact_dedupe(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.add_artifact(pdir, "a.patch")
    ctx = WorkspaceContext.add_artifact(pdir, "a.patch")
    assert ctx["artifacts"] == ["a.patch"]


def test_ws_snapshot_returns_copy(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.add_file(pdir, "main.py")
    snap = WorkspaceContext.snapshot(pdir)
    snap["files"].append("hacked.py")
    assert WorkspaceContext.snapshot(pdir)["files"] == ["main.py"]


def test_ws_save_creates_file(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.save(pdir, WorkspaceContext.init("demo"))
    assert (pdir / "workspace_context.json").is_file()


def test_ws_save_load_roundtrip(tmp_path):
    pdir = _proj_dir(tmp_path)
    ctx = WorkspaceContext.init("demo")
    ctx["files"] = ["main.py"]
    ctx["completed_tasks"] = ["T001"]
    ctx["artifacts"] = ["a.patch"]
    ctx["agent_history"] = [{"agent": "backend-1", "task": "T001", "result": "success"}]
    WorkspaceContext.save(pdir, ctx)
    loaded = WorkspaceContext.load(pdir)
    assert loaded == ctx


def test_ws_load_missing_fail_safe(tmp_path):
    ctx = WorkspaceContext.load(_proj_dir(tmp_path))
    assert ctx["project"] == ""
    assert ctx["files"] == []
    assert ctx["completed_tasks"] == []
    assert ctx["artifacts"] == []
    assert ctx["agent_history"] == []


def test_ws_load_corrupt_fail_safe(tmp_path):
    pdir = _proj_dir(tmp_path)
    _write_json(pdir / "workspace_context.json", "{bad")
    ctx = WorkspaceContext.load(pdir)
    assert ctx["files"] == []
    assert ctx["agent_history"] == []


def test_ws_load_preserves_all_fields(tmp_path):
    pdir = _proj_dir(tmp_path)
    WorkspaceContext.add_file(pdir, "main.py")
    WorkspaceContext.mark_task_completed(pdir, "T001", "backend-1", "success")
    WorkspaceContext.add_artifact(pdir, "a.patch")
    loaded = WorkspaceContext.load(pdir)
    assert loaded["files"] == ["main.py"]
    assert loaded["completed_tasks"] == ["T001"]
    assert loaded["artifacts"] == ["a.patch"]
    assert loaded["agent_history"][0]["agent"] == "backend-1"


def test_ws_load_filters_non_dict_history(tmp_path):
    pdir = _proj_dir(tmp_path)
    _write_json(
        pdir / "workspace_context.json",
        {"project": "demo", "agent_history": [{"agent": "a", "task": "T1"}, "junk"]},
    )
    assert WorkspaceContext.load(pdir)["agent_history"] == [{"agent": "a", "task": "T1"}]


def test_ws_file_name_constant():
    assert WS_MOD.WORKSPACE_CONTEXT_FILE_NAME == "workspace_context.json"
    assert WorkspaceContext.FILE_NAME == "workspace_context.json"


# ===================================================== F. AgentMessageStore

def test_msg_send_returns_dict(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    msg = store.send("architect-agent", "backend-1", "instruction", "Implement REST API")
    assert isinstance(msg, dict)
    assert set(msg) == {"from", "to", "type", "content", "timestamp"}


def test_msg_send_fields(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    msg = store.send("architect-agent", "backend-1", "instruction", "Do it")
    assert msg["from"] == "architect-agent"
    assert msg["to"] == "backend-1"
    assert msg["type"] == "instruction"
    assert msg["content"] == "Do it"
    assert msg["timestamp"]


def test_msg_send_default_type(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    msg = store.send("a", "b", content="hi")
    assert msg["type"] == "message"


def test_msg_messages_for_inbox(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    store.send("architect-agent", "backend-1", "instruction", "API")
    msgs = store.messages_for("backend-1")
    assert len(msgs) == 1
    assert msgs[0]["from"] == "architect-agent"


def test_msg_messages_for_empty(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    assert store.messages_for("backend-1") == []


def test_msg_messages_for_other_agent_empty(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    store.send("architect-agent", "backend-1", "instruction", "API")
    assert store.messages_for("qa-agent") == []


def test_msg_messages_for_order(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    store.send("a1", "b1", "m", "first")
    store.send("a2", "b1", "m", "second")
    msgs = store.messages_for("b1")
    assert [m["content"] for m in msgs] == ["first", "second"]


def test_msg_list_all(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    store.send("a1", "b1", "m", "one")
    store.send("a2", "b2", "m", "two")
    assert len(store.list()) == 2


def test_msg_list_empty(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    assert store.list() == []


def test_msg_save_creates_file(tmp_path):
    path = tmp_path / "agent_messages.json"
    store = AgentMessageStore(path)
    store.send("a", "b", "instruction", "x")
    assert path.is_file()
    data = _read_json(path)
    assert data[0]["from"] == "a"
    assert data[0]["to"] == "b"


def test_msg_save_load_roundtrip(tmp_path):
    path = tmp_path / "agent_messages.json"
    store = AgentMessageStore(path)
    store.send("architect-agent", "backend-1", "instruction", "API")
    reloaded = AgentMessageStore(path)
    assert len(reloaded.list()) == 1
    assert reloaded.list()[0]["content"] == "API"


def test_msg_load_missing_empty(tmp_path):
    store = AgentMessageStore(tmp_path / "nope.json")
    assert store.list() == []


def test_msg_load_corrupt_empty(tmp_path):
    path = _write_json(tmp_path / "agent_messages.json", "{bad")
    store = AgentMessageStore(path)
    assert store.list() == []


def test_msg_load_non_list_empty(tmp_path):
    path = _write_json(tmp_path / "agent_messages.json", {"not": "list"})
    store = AgentMessageStore(path)
    assert store.list() == []


def test_msg_architect_to_backend_instruction(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    store.send("architect-agent", "backend-1", "instruction", "Implement REST API")
    inbox = store.messages_for("backend-1")
    assert inbox and inbox[0]["type"] == "instruction"
    assert "REST API" in inbox[0]["content"]


def test_msg_default_file_path():
    assert str(AgentMessageStore.DEFAULT_FILE).endswith(
        ".factory/teams/agent_messages.json"
    )


def test_msg_dataclass_roundtrip():
    msg = AgentMessage(from_="a", to="b", type="instruction", content="c")
    assert AgentMessage.from_dict(msg.to_dict()) == msg


def test_msg_dataclass_from_dict_missing():
    msg = AgentMessage.from_dict({})
    assert msg.from_ == ""
    assert msg.to == ""
    assert msg.type == "message"
    assert msg.content == ""
    assert msg.timestamp


def test_msg_send_returns_same_as_list(tmp_path):
    store = AgentMessageStore(tmp_path / "agent_messages.json")
    sent = store.send("a", "b", "m", "x")
    assert store.list()[0] == sent


# ========================================================= G/H. Conflicts

def test_own_claim(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", ["main.py"])
    assert ownership.owned_by("main.py") == "T001"


def test_own_owned_by_unknown_none(tmp_path):
    ownership = FileOwnership()
    assert ownership.owned_by("main.py") is None


def test_own_claim_multiple_files(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", ["a.py", "b.py"])
    assert ownership.owned_by("a.py") == "T001"
    assert ownership.owned_by("b.py") == "T001"


def test_own_claim_same_task_again(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", ["main.py"])
    ownership.claim(_proj_dir(tmp_path), "T001", ["main.py"])
    assert ownership.owned_by("main.py") == "T001"


def test_own_claim_different_task_overwrites(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", ["main.py"])
    ownership.claim(_proj_dir(tmp_path), "T002", ["main.py"])
    assert ownership.owned_by("main.py") == "T002"


def test_own_clear(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", ["main.py"])
    ownership.clear()
    assert ownership.owned_by("main.py") is None


def test_own_claim_empty_files(tmp_path):
    ownership = FileOwnership()
    ownership.claim(_proj_dir(tmp_path), "T001", [])
    assert ownership.to_dict() == {}


def test_own_absolute_path_normalized(tmp_path):
    ownership = FileOwnership()
    pdir = _proj_dir(tmp_path)
    pdir.mkdir(parents=True, exist_ok=True)
    absolute = pdir / "main.py"
    ownership.claim(pdir, "T001", [str(absolute)])
    assert ownership.owned_by(str(absolute)) == "T001"
    assert ownership.owned_by("main.py") == "T001"


def test_own_projects_isolated(tmp_path):
    ownership = FileOwnership()
    p1 = _proj_dir(tmp_path)
    p2 = tmp_path / "projects" / "other"
    ownership.claim(p1, "T001", ["main.py"])
    ownership.claim(p2, "T002", ["main.py"])
    assert ownership.owned_by("main.py") == "T001"


def test_conf_detect_no_conflict_single(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    records = detector.detect(_proj_dir(tmp_path), "T001", ["main.py"])
    assert records == []
    assert detector.list() == []


def test_conf_detect_same_file_conflict(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    records = detector.detect(pdir, "T002", ["main.py"])
    assert len(records) == 1
    assert records[0].task_a == "T001"
    assert records[0].task_b == "T002"
    assert records[0].file == "main.py"


def test_conf_record_fields():
    record = ConflictRecord(task_a="T001", task_b="T002", file="main.py")
    assert record.detected_at
    assert record.status == "open"


def test_conf_status_open_constant():
    assert CONF_MOD.CONFLICT_STATUS_OPEN == "open"
    assert ConflictRecord(task_a="a", task_b="b", file="f").status == "open"


def test_conf_detect_same_task_no_conflict(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    assert detector.detect(pdir, "T001", ["main.py"]) == []


def test_conf_detect_partial_conflict(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["a.py", "b.py"])
    records = detector.detect(pdir, "T002", ["a.py", "c.py"])
    assert len(records) == 1
    assert records[0].file == "a.py"


def test_conf_detect_dedupe(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    detector.detect(pdir, "T002", ["main.py"])
    assert detector.detect(pdir, "T002", ["main.py"]) == []
    assert len(detector.list()) == 1


def test_conf_detect_multiple_tasks_conflict(tmp_path):
    detector = ConflictDetector(tmp_path / "conflicts.json")
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    detector.detect(pdir, "T002", ["main.py"])
    detector.detect(pdir, "T003", ["main.py"])
    assert len(detector.list()) == 2


def test_conf_detect_claims_unowned(tmp_path):
    ownership = FileOwnership()
    detector = ConflictDetector(tmp_path / "conflicts.json", ownership=ownership)
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    assert ownership.owned_by("main.py") == "T001"


def test_conf_save_creates_file(tmp_path):
    path = tmp_path / "conflicts.json"
    detector = ConflictDetector(path)
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    detector.detect(pdir, "T002", ["main.py"])
    assert path.is_file()
    data = _read_json(path)
    assert data[0]["task_a"] == "T001"
    assert data[0]["task_b"] == "T002"
    assert data[0]["status"] == "open"


def test_conf_save_load_roundtrip(tmp_path):
    path = tmp_path / "conflicts.json"
    detector = ConflictDetector(path)
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    detector.detect(pdir, "T002", ["main.py"])
    reloaded = ConflictDetector(path)
    assert len(reloaded.list()) == 1
    assert reloaded.list()[0]["file"] == "main.py"


def test_conf_load_missing_empty(tmp_path):
    detector = ConflictDetector(tmp_path / "nope.json")
    assert detector.list() == []


def test_conf_load_corrupt_empty(tmp_path):
    path = _write_json(tmp_path / "conflicts.json", "{bad")
    assert ConflictDetector(path).list() == []


def test_conf_load_non_list_empty(tmp_path):
    path = _write_json(tmp_path / "conflicts.json", {"not": "list"})
    assert ConflictDetector(path).list() == []


def test_conf_default_file_path():
    assert str(ConflictDetector.DEFAULT_FILE).endswith(".factory/teams/conflicts.json")


def test_conf_record_roundtrip():
    record = ConflictRecord(task_a="T001", task_b="T002", file="main.py")
    restored = ConflictRecord.from_dict(record.to_dict())
    assert restored.task_a == "T001"
    assert restored.task_b == "T002"
    assert restored.file == "main.py"
    assert restored.status == "open"


def test_conf_record_from_dict_missing_status_open():
    record = ConflictRecord.from_dict({"task_a": "a", "task_b": "b", "file": "f"})
    assert record.status == "open"


def test_conf_not_auto_resolved_after_reload(tmp_path):
    path = tmp_path / "conflicts.json"
    detector = ConflictDetector(path)
    pdir = _proj_dir(tmp_path)
    detector.detect(pdir, "T001", ["main.py"])
    detector.detect(pdir, "T002", ["main.py"])
    reloaded = ConflictDetector(path)
    assert reloaded.list()[0]["status"] == "open"


def test_conf_record_to_dict_keys():
    data = ConflictRecord(task_a="a", task_b="b", file="f").to_dict()
    assert set(data) == {"task_a", "task_b", "file", "detected_at", "status"}


# ============================================================ I/K. 回归

def test_regression_new_modules_importable():
    for mod in (
        TEAMS_MOD,
        ROLES_MOD,
        DEPS_MOD,
        WS_MOD,
        MSGS_MOD,
        CONF_MOD,
    ):
        assert mod.__name__.startswith("factory-console.session.")


def test_regression_agent_registry_unchanged(tmp_path):
    agents_file = _write_json(
        tmp_path / "agents.json",
        {"backend-1": {"id": "backend-1", "role": "Backend Engineer", "skills": ["python"]}},
    )
    registry = AgentRegistry.load(agents_file)
    assert registry["backend-1"]["role"] == "Backend Engineer"
    assert registry["backend-1"]["supported_tasks"] == [
        "backend_api",
        "database_schema",
        "test",
    ]


def test_regression_agent_registry_default_agents():
    """DEFAULT_AGENTS 常量不变 (S10-055 基线 3 Agent — 不读真实 ~/.factory)。"""
    assert set(AGENTS_MOD.DEFAULT_AGENTS) == {"backend-1", "flutter-dev", "tester-1"}
    assert AGENTS_MOD.DEFAULT_AGENTS["tester-1"]["skills"] == ["test", "qa"]


def test_regression_team_roles_compatible_with_default_agents():
    """默认团队成员角色与 RoleSystem 推导打通 (backend-1/flutter-dev 同 id)。"""
    team = TeamRegistry.build_default_team()
    roles = {m["agent"]: m["role"] for m in team["members"]}
    assert RoleSystem.role_matches(roles["backend-1"], _backend_agent())
    assert RoleSystem.role_matches(roles["flutter-dev"], _frontend_agent())
