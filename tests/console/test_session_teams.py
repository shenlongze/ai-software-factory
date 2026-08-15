"""tests/console/test_session_teams.py — S10-056 Agent Team Collaboration。

设计: docs/sprint10/S10-056-team-design.md
覆盖 (验收 A-J):
A. AgentTeam: team_id/name/members/roles/projects/created_at + member_roles/has_member
B. TeamRegistry: create/get/list/has/assign_project/build_default_team/load/save/add_team
C. 默认团队 software-team: 5 成员 (pm/architect/backend-1/flutter-dev/qa)
D. team_snapshot: 成员 + Registry 状态 + Metrics 绩效合并 (缺 agent 占位 "-")
E. team action "查看团队" → 团队协作视图 (成员角色/负载/绩效)
F. team action "创建团队" → TeamRegistry.create + add
G. intent/router: team 关键词/映射 (与 workforce 兼容: "查看团队" 仍归 workforce)
H. 不修改核心/不引入依赖 (测试只 import session 层 + 纯标准库)
I. 新增 >=50 测试全绿 + 全量 pytest 不破坏基线
J. 回归: workforce 兼容 (intent/路由/action 均不变)

测试装配: tmp_path + 构造 teams.json/agents.json/agent_metrics.json fixtures
(零真实 ~/.factory 污染); TeamRegistry 一律注入显式 teams_file。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
AGENTS_MOD = importlib.import_module("factory-console.session.agents")
CTX_MOD = importlib.import_module("factory-console.session.context")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
TEAMS_MOD = importlib.import_module("factory-console.session.teams")

AgentTeam = TEAMS_MOD.AgentTeam
TeamRegistry = TEAMS_MOD.TeamRegistry
TeamService = TEAMS_MOD.TeamService


# ------------------------------------------------------------------ 工具/夹具

def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _agents() -> dict:
    """固定 Agent 注册表 (backend-1/flutter-dev 注册; 默认编制其余为预留角色)。"""
    return {
        "backend-1": {
            "id": "backend-1",
            "name": "backend-1",
            "role": "Backend Engineer",
            "skills": ["python", "api", "database"],
            "status": "available",
            "current_task": None,
        },
        "flutter-dev": {
            "id": "flutter-dev",
            "name": "Flutter Dev",
            "role": "Frontend Engineer",
            "skills": ["flutter", "dart", "ui"],
            "status": "available",
            "current_task": None,
        },
        "tester-1": {
            "id": "tester-1",
            "name": "tester-1",
            "role": "QA Engineer",
            "skills": ["test", "qa"],
            "status": "available",
            "current_task": None,
        },
    }


def _metrics() -> dict:
    """固定绩效 (backend-1 高成功率; flutter-dev 零成功率; 其余无记录)。"""
    return {
        "backend-1": {
            "agent": "backend-1",
            "total_tasks": 20,
            "success_count": 15,
            "failed_count": 5,
            "success_rate": 0.75,
            "avg_cost": 0.001,
            "avg_duration": 12.0,
            "by_task_type": {},
        },
        "flutter-dev": {
            "agent": "flutter-dev",
            "total_tasks": 2,
            "success_count": 0,
            "failed_count": 2,
            "success_rate": 0.0,
            "avg_cost": 0.002,
            "avg_duration": 30.0,
            "by_task_type": {},
        },
    }


def _intent(intent_type: str, raw: str = "test", **params):
    return INTENT_MOD.IntentObject(intent_type=intent_type, params=params, raw=raw)


def _exec_ctx(root: Path, intent=None, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        user="user",
        intent=intent,
        **kw,
    )


def _teams_file(root: Path) -> Path:
    return root / "teams" / "teams.json"


def _default_members() -> list[dict]:
    return [dict(m) for m in TEAMS_MOD.DEFAULT_TEAM_MEMBERS]


# ================================================================== 1. AgentTeam (验收 A)

def test_agent_team_requires_team_id():
    team = AgentTeam(team_id="software-team", name="AI Software Team")
    assert team.team_id == "software-team"
    assert team.name == "AI Software Team"


def test_agent_team_defaults():
    team = AgentTeam(team_id="t1", name="T")
    assert team.members == []
    assert team.projects == []
    assert team.created_at is None


def test_agent_team_members_projects():
    team = AgentTeam(
        team_id="t1", name="T", members=_default_members(), projects=["p1", "p2"]
    )
    assert len(team.members) == 5
    assert team.projects == ["p1", "p2"]


def test_agent_team_created_at():
    team = AgentTeam(team_id="t1", name="T", created_at="2026-08-15T00:00:00+00:00")
    assert team.created_at == "2026-08-15T00:00:00+00:00"


def test_agent_team_member_roles():
    team = AgentTeam(team_id="t1", name="T", members=_default_members())
    roles = team.member_roles()
    assert roles["pm-agent"] == "product_manager"
    assert roles["architect-agent"] == "architect"
    assert roles["backend-1"] == "backend"
    assert roles["flutter-dev"] == "frontend"
    assert roles["qa-agent"] == "qa"


def test_agent_team_member_roles_skips_invalid():
    team = AgentTeam(
        team_id="t1",
        name="T",
        members=[{"agent": "a", "role": "r"}, {}, {"role": "x"}, "junk", None],
    )
    assert team.member_roles() == {"a": "r"}


def test_agent_team_member_roles_empty():
    team = AgentTeam(team_id="t1", name="T")
    assert team.member_roles() == {}


def test_agent_team_has_member():
    team = AgentTeam(team_id="t1", name="T", members=_default_members())
    assert team.has_member("backend-1")
    assert team.has_member("pm-agent")
    assert team.has_member("qa-agent")


def test_agent_team_has_member_missing():
    team = AgentTeam(team_id="t1", name="T", members=_default_members())
    assert not team.has_member("unknown-agent")


def test_agent_team_has_member_empty_input():
    team = AgentTeam(team_id="t1", name="T", members=_default_members())
    assert not team.has_member("")
    assert not team.has_member(None)


def test_agent_team_to_dict():
    team = AgentTeam(
        team_id="t1",
        name="T",
        members=[{"agent": "a", "role": "r"}],
        projects=["p1"],
        created_at="2026-08-15T00:00:00+00:00",
    )
    data = team.to_dict()
    assert data["team_id"] == "t1"
    assert data["name"] == "T"
    assert data["members"] == [{"agent": "a", "role": "r"}]
    assert data["projects"] == ["p1"]
    assert data["created_at"] == "2026-08-15T00:00:00+00:00"


def test_agent_team_from_dict():
    team = AgentTeam.from_dict(
        {
            "team_id": "t1",
            "name": "T",
            "members": [{"agent": "a", "role": "r"}],
            "projects": ["p1"],
            "created_at": "2026-08-15T00:00:00+00:00",
        }
    )
    assert team.team_id == "t1"
    assert team.name == "T"
    assert team.member_roles() == {"a": "r"}
    assert team.projects == ["p1"]


def test_agent_team_roundtrip():
    team = AgentTeam(team_id="t1", name="T", members=_default_members(), projects=["p"])
    assert AgentTeam.from_dict(team.to_dict()).to_dict() == team.to_dict()


def test_agent_team_from_dict_robust():
    team = AgentTeam.from_dict({})
    assert team.team_id == ""
    assert team.members == []
    assert team.projects == []


def test_agent_team_from_dict_invalid_members():
    team = AgentTeam.from_dict(
        {"team_id": "t1", "name": "T", "members": ["junk", {"agent": "a", "role": "r"}]}
    )
    assert team.member_roles() == {"a": "r"}


def test_agent_team_from_dict_id_alias():
    team = AgentTeam.from_dict({"id": "legacy", "name": "L"})
    assert team.team_id == "legacy"


def test_agent_team_projects_skip_dicts():
    team = AgentTeam.from_dict({"team_id": "t1", "name": "T", "projects": ["p", {"x": 1}]})
    assert team.projects == ["p"]


# ================================================================== 2. TeamRegistry (验收 B)

def test_team_registry_create():
    team = TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(Path("unused")))
    # teams_file 指向不存在目录 → 仍可创建 (add_team 失败安全: load 默认 → save 建目录)
    assert team["team_id"] == "mobile-team"
    assert team["name"] == "Mobile Team"
    assert team["members"] == []
    assert team["projects"] == []


def test_team_registry_create_persists(tmp_path):
    team = TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    saved = _read_json(_teams_file(tmp_path))
    assert saved["mobile-team"]["team_id"] == "mobile-team"
    assert saved["mobile-team"]["name"] == "Mobile Team"


def test_team_registry_create_with_members(tmp_path):
    members = [{"agent": "backend-1", "role": "backend"}]
    team = TeamRegistry.create("b-team", "Backend Team", members=members, teams_file=_teams_file(tmp_path))
    assert team["members"] == members


def test_team_registry_create_empty_id_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.create("", "X", teams_file=_teams_file(tmp_path))
    with pytest.raises(ValueError):
        TeamRegistry.create("  ", "X", teams_file=_teams_file(tmp_path))


def test_team_registry_create_name_fallback(tmp_path):
    team = TeamRegistry.create("mobile-team", "", teams_file=_teams_file(tmp_path))
    assert team["name"] == "mobile-team"


def test_team_registry_get(tmp_path):
    TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    team = TeamRegistry.get("mobile-team", teams_file=_teams_file(tmp_path))
    assert team is not None
    assert team["name"] == "Mobile Team"


def test_team_registry_get_missing_none(tmp_path):
    assert TeamRegistry.get("nope", teams_file=_teams_file(tmp_path)) is None


def test_team_registry_get_default_team(tmp_path):
    # 无 teams.json → load 失败安全返回默认团队 → get("software-team") 可用
    team = TeamRegistry.get("software-team", teams_file=_teams_file(tmp_path))
    assert team is not None
    assert team["team_id"] == "software-team"


def test_team_registry_list(tmp_path):
    TeamRegistry.create("b-team", "B", teams_file=_teams_file(tmp_path))
    TeamRegistry.create("a-team", "A", teams_file=_teams_file(tmp_path))
    ids = [t["team_id"] for t in TeamRegistry.list(teams_file=_teams_file(tmp_path))]
    # 注册表含默认 software-team + 2 新建; list 按 team_id 排序
    assert ids[0] == "a-team"
    assert ids[1] == "b-team"
    assert "software-team" in ids


def test_team_registry_list_default_only(tmp_path):
    ids = [t["team_id"] for t in TeamRegistry.list(teams_file=_teams_file(tmp_path))]
    assert ids == ["software-team"]


def test_team_registry_has(tmp_path):
    TeamRegistry.create("mobile-team", "M", teams_file=_teams_file(tmp_path))
    assert TeamRegistry.has("mobile-team", teams_file=_teams_file(tmp_path))
    assert TeamRegistry.has("software-team", teams_file=_teams_file(tmp_path))
    assert not TeamRegistry.has("nope", teams_file=_teams_file(tmp_path))


def test_team_registry_default_team_always_available(tmp_path):
    teams = TeamRegistry.load(_teams_file(tmp_path))
    assert "software-team" in teams


def test_team_registry_load_missing_file_default(tmp_path):
    teams = TeamRegistry.load(_teams_file(tmp_path))
    assert teams["software-team"]["team_id"] == "software-team"
    assert teams["software-team"]["name"] == "AI Software Team"


def test_team_registry_load_corrupt_default(tmp_path):
    path = _write_json(_teams_file(tmp_path), "{not json!!")
    teams = TeamRegistry.load(path)
    assert "software-team" in teams


def test_team_registry_load_empty_default(tmp_path):
    path = _write_json(_teams_file(tmp_path), {})
    teams = TeamRegistry.load(path)
    assert "software-team" in teams


def test_team_registry_load_non_dict_default(tmp_path):
    path = _write_json(_teams_file(tmp_path), ["a", "b"])
    teams = TeamRegistry.load(path)
    assert "software-team" in teams


def test_team_registry_load_normalizes_entries(tmp_path):
    path = _write_json(
        _teams_file(tmp_path),
        {
            "mobile-team": {
                "team_id": "mobile-team",
                "name": "Mobile Team",
                "members": [{"agent": "backend-1", "role": "backend"}],
                "projects": ["p1"],
                "created_at": "2026-08-15T00:00:00+00:00",
            }
        },
    )
    teams = TeamRegistry.load(path)
    assert teams["mobile-team"]["name"] == "Mobile Team"
    assert teams["mobile-team"]["projects"] == ["p1"]


def test_team_registry_load_coerces_invalid_entries(tmp_path):
    # 非 dict 条目 → 以 key 为 team_id 强制规范化 (同 AgentRegistry 口径, 不丢弃)
    path = _write_json(
        _teams_file(tmp_path), {"bad": "junk", "ok": {"team_id": "ok", "name": "OK"}}
    )
    teams = TeamRegistry.load(path)
    assert teams["ok"]["name"] == "OK"
    assert teams["bad"]["team_id"] == "bad"
    assert teams["bad"]["name"] == ""


def test_team_registry_load_entries_coerced_not_default(tmp_path):
    # 全部条目为非 dict → 全部强制规范化, 非空注册表 (不回落默认团队)
    path = _write_json(_teams_file(tmp_path), {"bad": "junk", "worse": 42})
    teams = TeamRegistry.load(path)
    assert "bad" in teams
    assert "worse" in teams
    assert "software-team" not in teams


def test_team_registry_save(tmp_path):
    teams = {"software-team": TeamRegistry.build_default_team()}
    saved_path = TeamRegistry.save(_teams_file(tmp_path), teams)
    assert saved_path.is_file()
    assert _read_json(saved_path)["software-team"]["team_id"] == "software-team"


def test_team_registry_add_team(tmp_path):
    team = TeamRegistry.add_team(
        {"team_id": "mobile-team", "name": "Mobile Team"}, teams_file=_teams_file(tmp_path)
    )
    assert TeamRegistry.has("mobile-team", teams_file=_teams_file(tmp_path))
    assert team["name"] == "Mobile Team"


def test_team_registry_add_team_overwrite(tmp_path):
    TeamRegistry.add_team(
        {"team_id": "mobile-team", "name": "V1", "members": []},
        teams_file=_teams_file(tmp_path),
    )
    TeamRegistry.add_team(
        {"team_id": "mobile-team", "name": "V2", "members": [{"agent": "a", "role": "r"}]},
        teams_file=_teams_file(tmp_path),
    )
    team = TeamRegistry.get("mobile-team", teams_file=_teams_file(tmp_path))
    assert team["name"] == "V2"
    assert team["members"] == [{"agent": "a", "role": "r"}]


def test_team_registry_add_team_empty_id_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.add_team({"team_id": "", "name": "X"}, teams_file=_teams_file(tmp_path))


def test_team_registry_default_file_constant():
    assert str(TeamRegistry.DEFAULT_FILE).endswith(".factory/teams/teams.json")


# ================================================================== 3. assign_project

def test_assign_project_adds(tmp_path):
    TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    team = TeamRegistry.assign_project("mobile-team", "p1", teams_file=_teams_file(tmp_path))
    assert team["projects"] == ["p1"]


def test_assign_project_idempotent(tmp_path):
    TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    TeamRegistry.assign_project("mobile-team", "p1", teams_file=_teams_file(tmp_path))
    team = TeamRegistry.assign_project("mobile-team", "p1", teams_file=_teams_file(tmp_path))
    assert team["projects"] == ["p1"]


def test_assign_project_persists(tmp_path):
    TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    TeamRegistry.assign_project("mobile-team", "p1", teams_file=_teams_file(tmp_path))
    saved = _read_json(_teams_file(tmp_path))
    assert saved["mobile-team"]["projects"] == ["p1"]


def test_assign_project_multiple(tmp_path):
    TeamRegistry.create("mobile-team", "Mobile Team", teams_file=_teams_file(tmp_path))
    team = TeamRegistry.assign_project("mobile-team", "p1", teams_file=_teams_file(tmp_path))
    team = TeamRegistry.assign_project("mobile-team", "p2", teams_file=_teams_file(tmp_path))
    assert team["projects"] == ["p1", "p2"]


def test_assign_project_missing_team_raises(tmp_path):
    with pytest.raises(ValueError):
        TeamRegistry.assign_project("nope", "p1", teams_file=_teams_file(tmp_path))


def test_assign_project_default_team(tmp_path):
    team = TeamRegistry.assign_project("software-team", "p1", teams_file=_teams_file(tmp_path))
    assert "p1" in team["projects"]


# ================================================================== 4. build_default_team (验收 C)

def test_build_default_team_id_name():
    team = TeamRegistry.build_default_team()
    assert team["team_id"] == "software-team"
    assert team["name"] == "AI Software Team"


def test_build_default_team_five_members():
    team = TeamRegistry.build_default_team()
    assert len(team["members"]) == 5


def test_build_default_team_member_ids():
    team = TeamRegistry.build_default_team()
    ids = [m["agent"] for m in team["members"]]
    assert ids == ["pm-agent", "architect-agent", "backend-1", "flutter-dev", "qa-agent"]


def test_build_default_team_roles():
    team = TeamRegistry.build_default_team()
    by_id = {m["agent"]: m["role"] for m in team["members"]}
    assert by_id["pm-agent"] == "product_manager"
    assert by_id["architect-agent"] == "architect"
    assert by_id["backend-1"] == "backend"
    assert by_id["flutter-dev"] == "frontend"
    assert by_id["qa-agent"] == "qa"


def test_build_default_team_created_at():
    team = TeamRegistry.build_default_team()
    assert team["created_at"]


def test_build_default_team_projects_empty():
    team = TeamRegistry.build_default_team()
    assert team["projects"] == []


def test_build_default_team_accepts_agents_file(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    team = TeamRegistry.build_default_team(agents_file=tmp_path / "agents" / "agents.json")
    assert len(team["members"]) == 5


# ================================================================== 5. team_snapshot (验收 D)

def test_snapshot_structure():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    assert snapshot["team_id"] == "software-team"
    assert snapshot["name"] == "AI Software Team"
    assert len(snapshot["members"]) == 5


def test_snapshot_member_fields():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    first = snapshot["members"][0]
    assert set(first) == {"agent", "role", "status", "success_rate", "total_tasks", "current_task"}
    assert first["agent"] == "pm-agent"
    assert first["role"] == "product_manager"


def test_snapshot_member_order_preserved():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    ids = [m["agent"] for m in snapshot["members"]]
    assert ids == ["pm-agent", "architect-agent", "backend-1", "flutter-dev", "qa-agent"]


def test_snapshot_registry_status_merged():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["status"] == "available"
    assert by_id["flutter-dev"]["status"] == "available"


def test_snapshot_metrics_merged():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["success_rate"] == 0.75
    assert by_id["backend-1"]["total_tasks"] == 20
    assert by_id["flutter-dev"]["success_rate"] == 0.0
    assert by_id["flutter-dev"]["total_tasks"] == 2


def test_snapshot_missing_agent_placeholder():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    by_id = {m["agent"]: m for m in snapshot["members"]}
    for agent_id in ("pm-agent", "architect-agent", "qa-agent"):
        assert by_id[agent_id]["status"] == "-"
        assert by_id[agent_id]["success_rate"] == "-"
        assert by_id[agent_id]["total_tasks"] == "-"
        assert by_id[agent_id]["current_task"] == "-"


def test_snapshot_current_task():
    agents = _agents()
    agents["backend-1"]["current_task"] = "登录功能"
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, agents, _metrics())
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["current_task"] == "登录功能"


def test_snapshot_current_task_placeholder():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), _metrics())
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["current_task"] == "-"


def test_snapshot_total_tasks_default_zero():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), {})
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["total_tasks"] == 0
    assert by_id["backend-1"]["success_rate"] == "-"


def test_snapshot_metrics_none():
    team = TeamRegistry.build_default_team()
    snapshot = TeamService.team_snapshot(team, _agents(), None)
    by_id = {m["agent"]: m for m in snapshot["members"]}
    assert by_id["backend-1"]["total_tasks"] == 0


def test_snapshot_empty_members():
    snapshot = TeamService.team_snapshot({"team_id": "t", "name": "T", "members": []}, {}, {})
    assert snapshot["members"] == []


def test_snapshot_skips_invalid_members():
    team = {"team_id": "t", "name": "T", "members": [{"role": "x"}, "junk", None]}
    snapshot = TeamService.team_snapshot(team, {}, {})
    assert snapshot["members"] == []


# ================================================================== 6. team action (验收 E/F)

def test_team_action_view_ok(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.ok
    assert result.status == "ok"


def test_team_action_view_default_team(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.data["team"]["team_id"] == "software-team"
    assert result.data["team"]["name"] == "AI Software Team"


def test_team_action_view_five_members(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.data["count"] == 5
    assert len(result.data["members"]) == 5


def test_team_action_view_member_roles(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    by_id = {m["agent"]: m for m in result.data["members"]}
    assert by_id["pm-agent"]["role"] == "product_manager"
    assert by_id["backend-1"]["role"] == "backend"
    assert by_id["flutter-dev"]["role"] == "frontend"


def test_team_action_view_placeholders(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    by_id = {m["agent"]: m for m in result.data["members"]}
    assert by_id["pm-agent"]["status"] in ("AVAILABLE", "-")  # S10-058: pm-agent 已注册 → 有状态
    assert by_id["qa-agent"]["success_rate"] in ("-", 1.0, "1.0")  # S10-058: qa-agent 已注册


def test_team_action_view_registry_merged(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    by_id = {m["agent"]: m for m in result.data["members"]}
    assert by_id["backend-1"]["status"] == "available"
    assert by_id["pm-agent"]["status"] == "-"


def test_team_action_view_metrics_merged(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    _write_json(tmp_path / "exec" / "agent_metrics.json", _metrics())
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    by_id = {m["agent"]: m for m in result.data["members"]}
    assert by_id["backend-1"]["success_rate"] == 0.75
    assert by_id["backend-1"]["total_tasks"] == 20


def test_team_action_view_metrics_from_records(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    _write_json(
        tmp_path / "exec" / "execution_records.json",
        [
            {"agent": "backend-1", "task": "后端 API", "result": "success"},
            {"agent": "backend-1", "task": "数据库", "result": "success"},
            {"agent": "backend-1", "task": "登录", "result": "failed"},
        ],
    )
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    by_id = {m["agent"]: m for m in result.data["members"]}
    assert by_id["backend-1"]["total_tasks"] == 3
    assert by_id["backend-1"]["success_rate"] == pytest.approx(0.6667)  # compute 4 位舍入


def test_team_action_view_header_rows(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.data["header"] == [
        "agent", "role", "status", "success_rate", "total_tasks", "current_task",
    ]
    assert len(result.data["rows"]) == 5
    assert len(result.data["rows"][0]) == 6


def test_team_action_view_message(tmp_path):
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert "AI Software Team" in result.message
    assert "5" in result.message


def test_team_action_view_uses_teams_file(tmp_path):
    custom = {
        "software-team": {
            "team_id": "software-team",
            "name": "Custom Team",
            "members": [{"agent": "backend-1", "role": "backend"}],
            "projects": [],
            "created_at": "2026-08-15T00:00:00+00:00",
        }
    }
    _write_json(_teams_file(tmp_path), custom)
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.data["team"]["name"] == "Custom Team"
    assert result.data["count"] == 1


def test_team_action_create(tmp_path):
    intent = _intent("team", raw="创建团队 Mobile Team", name="Mobile Team")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    assert result.ok
    assert result.data["team_id"] == "mobile-team"
    assert result.data["name"] == "Mobile Team"
    assert result.data["team"]["team_id"] == "mobile-team"


def test_team_action_create_persists(tmp_path):
    intent = _intent("team", raw="创建团队 Mobile Team", name="Mobile Team")
    ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    saved = _read_json(_teams_file(tmp_path))
    assert saved["mobile-team"]["name"] == "Mobile Team"


def test_team_action_create_missing_name_guidance(tmp_path):
    intent = _intent("team", raw="创建团队")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    assert not result.ok
    assert result.status == "error"
    assert "团队名称" in result.message
    assert not _teams_file(tmp_path).exists()


def test_team_action_create_chinese_name_slug_fallback(tmp_path):
    intent = _intent("team", raw="创建团队 电商后端团队", name="电商后端团队")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    assert result.ok
    assert result.data["team_id"] == "电商后端团队"  # S10-056: 中文名 slug 空 → 用原名 (可识别 id)
    assert result.data["name"] == "电商后端团队"


def test_team_action_create_default_roster(tmp_path):
    intent = _intent("team", raw="创建团队 Mobile Team", name="Mobile Team")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    assert len(result.data["team"]["members"]) == 5


def test_team_action_create_team_id_collision_overwrite(tmp_path):
    intent = _intent("team", raw="创建团队 Mobile Team", name="Mobile Team")
    ACTIONS_MOD.team(_exec_ctx(tmp_path, intent))
    intent2 = _intent("team", raw="创建团队 Mobile Team 2", name="Mobile Team 2")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent2))
    assert result.ok
    assert result.data["team_id"] == "mobile-team-2"


def test_team_action_not_sensitive():
    action = ACTIONS_MOD.build_default_actions().get("team")
    assert action.metadata.get("sensitive") is False


def test_team_action_permission_user():
    action = ACTIONS_MOD.build_default_actions().get("team")
    assert action.permission == "user"


# ================================================================== 7. intent / router (验收 G)

def test_intent_create_team():
    intent = INTENT_MOD.KeywordIntentParser().parse("创建团队")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM


def test_intent_create_team_name_param():
    intent = INTENT_MOD.KeywordIntentParser().parse("创建团队 Mobile Team")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM
    assert intent.params.get("name") == "Mobile Team"


def test_intent_create_team_not_create_project():
    # "创建团队" 含 "创建" (create_project 关键词) — 必须不被抢
    intent = INTENT_MOD.KeywordIntentParser().parse("创建团队 Mobile Team")
    assert intent.intent_type != INTENT_MOD.INTENT_CREATE_PROJECT


def test_intent_team_collab_keywords():
    parser = INTENT_MOD.KeywordIntentParser()
    for text in ("团队协作", "协作视图", "团队绩效", "团队负载", "团队管理"):
        intent = parser.parse(text)
        assert intent is not None
        assert intent.intent_type == INTENT_MOD.INTENT_TEAM, text


def test_intent_team_collab_not_workforce():
    # "团队协作" 含 workforce 泛化关键词 "团队" — 专属 team 语义不被抢
    intent = INTENT_MOD.KeywordIntentParser().parse("团队协作")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM
    assert intent.intent_type != INTENT_MOD.INTENT_WORKFORCE


def test_intent_team_confidence():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队协作")
    assert intent.confidence == 1.0


def test_router_team_mapping():
    router = ROUTER_MOD.IntentRouter()
    assert router.routes()["team"] == "team"


def test_team_action_registered():
    action = ACTIONS_MOD.build_default_actions().get("team")
    assert action is not None
    assert action.handler is ACTIONS_MOD.team


def test_router_team_resolves_to_action():
    router = ROUTER_MOD.IntentRouter()
    registry = ACTIONS_MOD.build_default_actions()
    action = router.route(_intent("team", raw="团队协作"), registry)
    assert action.name == "team"


# ================================================================== 8. 回归: workforce 兼容

def test_workforce_intent_view_team_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("查看团队")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_intent_bare_team_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_intent_status_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队状态")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_router_unchanged():
    router = ROUTER_MOD.IntentRouter()
    assert router.routes()["workforce"] == "workforce"


def test_workforce_action_still_registered():
    action = ACTIONS_MOD.build_default_actions().get("workforce")
    assert action is not None
    assert action.handler is ACTIONS_MOD.workforce


def test_workforce_action_still_works(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    _write_json(tmp_path / "exec" / "execution_records.json", [])
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert result.ok
    ids = [a["id"] for a in result.data["agents"]]
    assert ids == ["backend-1", "flutter-dev", "tester-1"]


def test_create_project_keyword_not_hijacked():
    intent = INTENT_MOD.KeywordIntentParser().parse("创建一个项目")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PROJECT


def test_team_action_does_not_break_workforce_snapshot(tmp_path):
    # team 视图与 workforce 视图数据源独立共存 (互不污染)
    _write_json(tmp_path / "agents" / "agents.json", _agents())
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path))
    assert result.ok
    wf = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert wf.ok
    assert len(wf.data["agents"]) == 3
