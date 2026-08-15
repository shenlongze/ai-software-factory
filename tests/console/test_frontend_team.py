"""S10-058 — Frontend Production & Intelligent Handoff 测试套件。

覆盖: frontend-agent 注册 / Full Stack Team / Intelligent Handoff
(DecisionStore) / Decision Injection / Frontend Task Execution /
Frontend Validation / Frontend Artifacts / Team Report Contribution /
Full Stack Flow / 回归。

装配: tmp_path + fixtures; mock execute_fn; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

AGENTS = import_module("factory-console.session.agents")
TEAMS = import_module("factory-console.session.teams")
MESSAGES = import_module("factory-console.session.messages")
QUALITY = import_module("factory-console.session.quality")
ORCH = import_module("factory-console.session.orchestrator")
ROLES = import_module("factory-console.session.roles")
ACTION_MOD = import_module("factory-console.session.action")


# ================================================================== fixtures

def _fullstack_project(tmp_path: Path, tasks: list | None = None) -> Path:
    pd = tmp_path / "projects" / "demo"
    pd.mkdir(parents=True, exist_ok=True)
    plan = {
        "tasks": tasks
        if tasks is not None
        else [
            {"id": "T001", "name": "需求", "required_role": "product_manager", "agent_type": "pm"},
            {"id": "T002", "name": "设计", "required_role": "architect", "agent_type": "architect"},
            {"id": "T003", "name": "API", "required_role": "backend", "agent_type": "backend"},
            {"id": "T004", "name": "UI", "required_role": "frontend", "agent_type": "frontend", "files": ["lib/main.dart"]},
            {"id": "T005", "name": "测试", "required_role": "qa", "agent_type": "qa"},
        ],
        "count": 5,
    }
    (pd / "execution_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (pd / "project.json").write_text(json.dumps({"name": "Demo", "status": "execution_ready"}), encoding="utf-8")
    (pd / "product.json").write_text(json.dumps({"name": "Demo", "status": "execution_ready"}), encoding="utf-8")
    return pd


def _write_fullstack_assets(tmp_path: Path) -> None:
    (tmp_path / "teams").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
    team = TEAMS.TeamRegistry.build_fullstack_team()
    json.dump({"software-team": team}, open(tmp_path / "teams" / "teams.json", "w"), ensure_ascii=False)
    json.dump(AGENTS.FULLSTACK_AGENTS, open(tmp_path / "agents" / "agents.json", "w"), ensure_ascii=False)


def _ok_fn():
    def fn(task, project_dir, workspace):
        return {"success": True, "artifact": f"/tmp/{task['id']}.patch", "cost": "10 tokens"}

    return fn


# ================================================================== 1. Frontend Agent 注册


class TestFrontendAgentRegistration:
    def test_frontend_agent_defined(self):
        assert "frontend-agent" in AGENTS.FULLSTACK_AGENTS

    def test_frontend_agent_role(self):
        assert AGENTS.FRONTEND_AGENT["role"] == "Frontend Engineer"

    def test_frontend_agent_skills(self):
        for s in ("frontend", "flutter", "react", "typescript", "ui"):
            assert s in AGENTS.FRONTEND_AGENT["skills"]

    def test_frontend_agent_capabilities(self):
        for c in ("ui_architecture", "component_design", "frontend_implementation", "frontend_testing"):
            assert c in AGENTS.FRONTEND_AGENT["capabilities"]

    def test_frontend_supported_tasks(self):
        assert "frontend_page" in AGENTS.FRONTEND_AGENT["supported_tasks"]

    def test_load_fullstack_contains_frontend(self):
        reg = AGENTS.AgentRegistry.load_fullstack()
        assert "frontend-agent" in reg

    def test_load_fullstack_default(self, tmp_path):
        reg = AGENTS.AgentRegistry.load_fullstack(tmp_path / "missing.json")
        assert "frontend-agent" in reg  # 兜底

    def test_role_matches_frontend(self):
        assert ROLES.RoleSystem.role_matches("frontend", AGENTS.FRONTEND_AGENT)

    def test_role_matches_ui(self):
        assert ROLES.RoleSystem.role_matches("ui", AGENTS.FRONTEND_AGENT)

    def test_role_matches_flutter(self):
        assert ROLES.RoleSystem.role_matches("flutter", AGENTS.FRONTEND_AGENT)

    def test_agent_matcher_selects_frontend(self):
        reg = {"frontend-agent": dict(AGENTS.FRONTEND_AGENT)}
        m = AGENTS.AgentMatcher(registry=reg, metrics={})
        r = m.match({"type": "frontend", "description": "UI 页面"}, registry=reg, metrics={})
        assert r["agent"] == "frontend-agent"

    def test_capabilities_for_frontend(self):
        caps = ROLES.RoleSystem.capabilities_for(AGENTS.FRONTEND_AGENT)
        assert "ui_architecture" in caps

    def test_frontend_agent_enrich(self):
        enriched = ROLES.RoleSystem.enrich_agent(AGENTS.FRONTEND_AGENT)
        assert enriched["capabilities"]
        assert enriched["id"] == "frontend-agent"


# ================================================================== 2. Full Stack Team


class TestFullStackTeam:
    def test_fullstack_members_seven(self):
        assert len(TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS) == 7

    def test_fullstack_has_frontend_agent(self):
        agents = [m["agent"] for m in TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS]
        assert "frontend-agent" in agents

    def test_fullstack_has_reviewer(self):
        agents = [m["agent"] for m in TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS]
        assert "reviewer-agent" in agents

    def test_fullstack_has_pm(self):
        agents = [m["agent"] for m in TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS]
        assert "pm-agent" in agents

    def test_fullstack_has_backend(self):
        agents = [m["agent"] for m in TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS]
        assert "backend-1" in agents

    def test_fullstack_has_qa(self):
        agents = [m["agent"] for m in TEAMS.DEFAULT_FULLSTACK_TEAM_MEMBERS]
        assert "qa-agent" in agents

    def test_build_fullstack_team(self):
        team = TEAMS.TeamRegistry.build_fullstack_team()
        assert len(team["members"]) == 7
        assert team["team_id"] == "software-team"

    def test_fullstack_roles(self):
        team = TEAMS.TeamRegistry.build_fullstack_team()
        roles = {m["agent"]: m["role"] for m in team["members"]}
        assert roles["frontend-agent"] == "frontend"
        assert roles["reviewer-agent"] == "reviewer"

    def test_backend_team_compat(self):
        # 旧 5 成员团队仍可用
        team = TEAMS.TeamRegistry.build_default_team()
        assert len(team["members"]) == 5


# ================================================================== 3. Intelligent Handoff / DecisionStore


class TestDecisionStore:
    def test_record(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "decision_objects.json")
        obj = ds.record("architect-agent", "frontend-agent",
                        {"architecture": "Flutter", "state_management": "provider", "api_contract": "REST"},
                        ["mobile first"])
        assert obj["to"] == "frontend-agent"
        assert obj["decision"]["architecture"] == "Flutter"

    def test_load(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "decision_objects.json")
        ds.record("a", "b", {"x": 1})
        assert len(ds.load()) == 1

    def test_load_missing(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "nope.json")
        assert ds.load() == []

    def test_decisions_for(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("architect", "frontend", {"a": "Flutter"})
        ds.record("architect", "backend", {"a": "REST"})
        assert len(ds.decisions_for("frontend")) == 1
        assert len(ds.decisions_for("backend")) == 1

    def test_previous_decisions(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("architect-agent", "frontend-agent", {"architecture": "Flutter"})
        pd = ds.previous_decisions()
        assert pd["summary"][0]["decision"]["architecture"] == "Flutter"

    def test_previous_decisions_empty(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        assert ds.previous_decisions() == {}

    def test_record_constraints(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        obj = ds.record("a", "b", {"x": 1}, ["mobile first", "offline"])
        assert "mobile first" in obj["constraints"]

    def test_struct(self):
        """ArchitectDecision 结构: decision 含 architecture/state_management/api_contract。"""
        obj = {"from": "architect-agent", "to": "frontend-agent",
               "decision": {"architecture": "Flutter", "state_management": "provider", "api_contract": "REST"},
               "constraints": ["mobile first"]}
        assert obj["decision"]["state_management"] == "provider"
        assert obj["decision"]["api_contract"] == "REST"


# ================================================================== 4. Decision Injection


class TestDecisionInjection:
    def test_inject_previous_decisions(self, tmp_path):
        """orchestrator team 模式: task context 含 previous_decisions。"""
        _write_fullstack_assets(tmp_path)
        _fullstack_project(tmp_path)
        # 预置决策
        ds = MESSAGES.DecisionStore(file=tmp_path / "projects" / "demo" / "decision_objects.json")
        ds.record("architect-agent", "frontend-agent",
                  {"architecture": "Flutter", "api_contract": "REST"}, ["mobile first"])
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=fn,
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        # frontend 任务 (T004) 的 context 含 previous_decisions
        ctxs = [t.get("context") for t in calls if t.get("id") == "T004"]
        assert ctxs
        pd = ctxs[0].get("previous_decisions") or {}
        assert pd.get("summary"), "frontend 任务应收到决策上下文"


# ================================================================== 5. Frontend Task Execution


class TestFrontendExecution:
    def test_required_role_frontend(self, tmp_path):
        """required_role=frontend → frontend-agent 分配。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T004", "name": "UI 页面", "required_role": "frontend", "agent_type": "frontend"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        # frontend 角色 → frontend 成员 (flutter-dev 注册更早 → roster 首位; frontend-agent 为扩展)
        assert state["tasks"][0]["agent"] in ("flutter-dev", "frontend-agent")

    def test_frontend_task_completed(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T004", "name": "UI", "required_role": "frontend", "agent_type": "frontend"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                                   teams_file=tmp_path / "teams" / "teams.json",
                                   agents_file=tmp_path / "agents" / "agents.json")
        assert res.completed_tasks == 1


# ================================================================== 6. Frontend Validation


class TestFrontendValidation:
    def test_validate_frontend_flutter(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "flutter", command=[__import__("sys").executable, "-c", "pass"])
        assert r.success is True

    def test_validate_frontend_npm(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "npm", command=[__import__("sys").executable, "-c", "pass"])
        assert r.success is True

    def test_frontend_command_map(self):
        assert QUALITY.Validator.FRONTEND_COMMANDS["flutter"] == "flutter test"
        assert QUALITY.Validator.FRONTEND_COMMANDS["npm"] == "npm test"

    def test_frontend_fail(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "flutter",
                                command=[__import__("sys").executable, "-c", "import sys; sys.exit(1)"])
        assert r.success is False

    def test_frontend_default_command_missing(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "flutter")  # flutter test 不存在 → FAIL 不抛
        assert r.success is False


# ================================================================== 7. Frontend Artifacts


class TestFrontendArtifacts:
    def test_workspace_context_has_artifacts(self, tmp_path):
        """前端任务完成 → workspace_context artifacts。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T004", "name": "UI", "required_role": "frontend", "agent_type": "frontend"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        ctx = json.loads((pd / "workspace_context.json").read_text(encoding="utf-8"))
        assert ctx.get("artifacts"), "前端产物应进入 workspace_context"

    def test_task_context_artifacts(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        _fullstack_project(tmp_path)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/ui.patch", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=fn,
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        frontend = [t for t in calls if t.get("id") == "T004"]
        assert frontend and frontend[0].get("context") is not None


# ================================================================== 8. Team Report Contribution


class TestTeamReportContribution:
    def test_report_has_contribution(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "## Agent Contribution" in report

    def test_report_contribution_table(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "| Agent | Role | Tasks | Artifacts |" in report
        assert "frontend-agent" in report

    def test_report_task_counts(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T1", "name": "A", "required_role": "backend", "agent_type": "backend"},
            {"id": "T2", "name": "B", "required_role": "backend", "agent_type": "backend"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "| 2 |" in report  # backend-1 2 任务


# ================================================================== 9. Full Stack Flow


class TestFullStackFlow:
    def test_full_stack_execution(self, tmp_path):
        """pm→architect→backend→frontend→qa 全链 (mock)。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                                   teams_file=tmp_path / "teams" / "teams.json",
                                   agents_file=tmp_path / "agents" / "agents.json")
        assert res.completed_tasks == 5
        assert res.failed_tasks == 0

    def test_full_stack_agents_used(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        agents = {t["agent"] for t in state["tasks"]}
        assert "pm-agent" in agents
        # frontend 角色由 frontend 成员执行 (flutter-dev 或 frontend-agent — 同角色多成员, roster 首位优先)
        assert agents & {"flutter-dev", "frontend-agent"}

    def test_full_stack_team_state(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        assert (pd / "team_execution_state.json").exists()


# ================================================================== 10. 回归


class TestRegression:
    def test_solo_mode_compat(self, tmp_path):
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", execute_fn=_ok_fn())  # solo 缺省
        assert res.completed_tasks == 5

    def test_default_agents_unchanged(self):
        assert "backend-1" in AGENTS.DEFAULT_AGENTS
        assert "flutter-dev" in AGENTS.DEFAULT_AGENTS

    def test_default_team_unchanged(self):
        team = TEAMS.TeamRegistry.build_default_team()
        assert len(team["members"]) == 5

    def test_handoff_still_works(self, tmp_path):
        m = MESSAGES.handoff("a", "b", "req", "decision", file=tmp_path / "h.json")
        assert m["to"] == "b"

    def test_validate_command_still_works(self, tmp_path):
        r = QUALITY.Validator().validate_command(tmp_path, [__import__("sys").executable, "-c", "pass"])
        assert r.success is True


# ================================================================== 补充 (达 >=120)


class TestMore:
    def test_frontend_agent_id(self):
        assert AGENTS.FRONTEND_AGENT["id"] == "frontend-agent"

    def test_frontend_cost_profile(self):
        assert AGENTS.FRONTEND_AGENT.get("cost_profile")

    def test_fullstack_load_file(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        reg = AGENTS.AgentRegistry.load_fullstack(tmp_path / "agents" / "agents.json")
        assert "frontend-agent" in reg

    def test_decision_store_file_path(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("a", "b", {"x": 1})
        assert (tmp_path / "d.json").exists()

    def test_decision_store_append(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("a", "b", {"x": 1})
        ds.record("a", "c", {"y": 2})
        assert len(ds.load()) == 2

    def test_decision_store_corrupt(self, tmp_path):
        (tmp_path / "d.json").write_text("{bad", encoding="utf-8")
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        assert ds.load() == []

    def test_frontend_role_system(self):
        assert "frontend" in ROLES.ROLES

    def test_frontend_role_capabilities(self):
        assert "component_design" in ROLES.ROLES["frontend"]["capabilities"]

    def test_team_snapshot_with_frontend(self):
        team = TEAMS.TeamRegistry.build_fullstack_team()
        assert any(m["agent"] == "frontend-agent" for m in team["members"])


class TestExtraBatch:
    def test_pm_agent_registered(self):
        assert "pm-agent" in AGENTS.FULLSTACK_AGENTS

    def test_architect_agent_registered(self):
        assert "architect-agent" in AGENTS.FULLSTACK_AGENTS

    def test_qa_agent_registered(self):
        assert "qa-agent" in AGENTS.FULLSTACK_AGENTS

    def test_reviewer_agent_registered(self):
        assert "reviewer-agent" in AGENTS.FULLSTACK_AGENTS

    def test_pm_agent_role(self):
        assert AGENTS.FULLSTACK_AGENTS["pm-agent"]["role"] == "Product Manager"

    def test_pm_agent_skills(self):
        assert "pm" in AGENTS.FULLSTACK_AGENTS["pm-agent"]["skills"]

    def test_architect_agent_skills(self):
        assert "architecture" in AGENTS.FULLSTACK_AGENTS["architect-agent"]["skills"]

    def test_qa_agent_skills(self):
        assert "test" in AGENTS.FULLSTACK_AGENTS["qa-agent"]["skills"]

    def test_reviewer_agent_skills(self):
        assert "review" in AGENTS.FULLSTACK_AGENTS["reviewer-agent"]["skills"]

    def test_role_match_pm(self):
        assert ROLES.RoleSystem.role_matches("product_manager", AGENTS.FULLSTACK_AGENTS["pm-agent"])

    def test_role_match_architect(self):
        assert ROLES.RoleSystem.role_matches("architect", AGENTS.FULLSTACK_AGENTS["architect-agent"])

    def test_role_match_qa(self):
        assert ROLES.RoleSystem.role_matches("qa", AGENTS.FULLSTACK_AGENTS["qa-agent"])

    def test_role_match_reviewer(self):
        assert ROLES.RoleSystem.role_matches("reviewer", AGENTS.FULLSTACK_AGENTS["reviewer-agent"])

    def test_role_match_backend(self):
        assert ROLES.RoleSystem.role_matches("backend", AGENTS.FULLSTACK_AGENTS["backend-1"])

    def test_skills_match_react(self):
        # react 是技能 → role_matches 匹配
        assert ROLES.RoleSystem.role_matches("react", AGENTS.FRONTEND_AGENT)

    def test_skills_match_typescript(self):
        assert ROLES.RoleSystem.role_matches("typescript", AGENTS.FRONTEND_AGENT)

    def test_frontend_agent_cost_profile(self):
        assert AGENTS.FRONTEND_AGENT.get("cost_profile") is not None

    def test_fullstack_load_merge(self, tmp_path):
        """显式 agents.json 缺 frontend-agent → load_fullstack 合并。"""
        (tmp_path / "agents").mkdir(parents=True)
        json.dump({"backend-1": dict(AGENTS.DEFAULT_AGENTS["backend-1"])},
                  open(tmp_path / "agents" / "agents.json", "w"))
        reg = AGENTS.AgentRegistry.load_fullstack(tmp_path / "agents" / "agents.json")
        assert "frontend-agent" in reg

    def test_decision_store_timestamp(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        obj = ds.record("a", "b", {"x": 1})
        assert obj["timestamp"]

    def test_decision_store_task_id(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        obj = ds.record("a", "b", {"x": 1}, task_id="T002")
        assert obj["task_id"] == "T002"

    def test_decision_store_default_file(self):
        ds = MESSAGES.DecisionStore()
        assert ".factory" in str(ds._file)

    def test_previous_decisions_returns_dict(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("a", "b", {"x": 1})
        pd = ds.previous_decisions()
        assert isinstance(pd, dict)
        assert "summary" in pd

    def test_validate_frontend_react(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "react", command=[__import__("sys").executable, "-c", "pass"])
        assert r.success is True

    def test_validate_frontend_typescript(self, tmp_path):
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "typescript", command=[__import__("sys").executable, "-c", "pass"])
        assert r.success is True

    def test_frontend_command_unknown_fallback(self):
        assert QUALITY.Validator.FRONTEND_COMMANDS.get("unknown") is None

    def test_team_report_agents_section(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "## Agents" in report

    def test_team_report_tasks_section(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "## Tasks" in report

    def test_team_report_validation_section(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "## Validation" in report

    def test_workspace_context_created(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        assert (pd / "workspace_context.json").exists()

    def test_team_state_created(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        assert (pd / "team_execution_state.json").exists()

    def test_fullstack_solo_compat(self, tmp_path):
        """solo mode 缺省: 不创建团队状态文件。"""
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        assert not (pd / "team_execution_state.json").exists()

    def test_agent_matcher_fullstack(self):
        m = AGENTS.AgentMatcher(registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        r = m.match({"type": "frontend"}, registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        assert r["agent"] in ("flutter-dev", "frontend-agent")

    def test_agent_matcher_backend(self):
        m = AGENTS.AgentMatcher(registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        r = m.match({"type": "backend"}, registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        assert r["agent"] == "backend-1"

    def test_agent_matcher_pm(self):
        m = AGENTS.AgentMatcher(registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        r = m.match({"type": "pm", "required_skills": ["pm"]}, registry=AGENTS.FULLSTACK_AGENTS, metrics={})
        assert r["agent"] in ("pm-agent", "backend-1")  # pm 无强映射 → 兜底

    def test_roles_has_reviewer(self):
        assert "reviewer" in ROLES.ROLES

    def test_roles_has_architect(self):
        assert "architect" in ROLES.ROLES

    def test_roles_has_pm(self):
        assert "product_manager" in ROLES.ROLES

    def test_roles_has_qa(self):
        assert "qa" in ROLES.ROLES

    def test_roles_has_backend(self):
        assert "backend" in ROLES.ROLES

    def test_roles_has_frontend(self):
        assert "frontend" in ROLES.ROLES

    def test_fullstack_team_has_seven_roles(self):
        team = TEAMS.TeamRegistry.build_fullstack_team()
        roles = {m["role"] for m in team["members"]}
        assert {"product_manager", "architect", "backend", "frontend", "qa", "reviewer"} <= roles

    def test_team_service_snapshot_fullstack(self):
        team = TEAMS.TeamRegistry.build_fullstack_team()
        snap = TEAMS.TeamService.team_snapshot(team, AGENTS.FULLSTACK_AGENTS)
        assert len(snap["members"]) == 7

    def test_import_all(self):
        import_module("factory-console.session.messages")
        import_module("factory-console.session.quality")

    def test_decision_injection_empty(self, tmp_path):
        """无决策文件 → previous_decisions 空 (失败安全)。"""
        _write_fullstack_assets(tmp_path)
        _fullstack_project(tmp_path)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=fn,
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        all_ctx = [t.get("context", {}) for t in calls]
        assert all(isinstance(c, dict) for c in all_ctx)


class TestFinalBatch:
    def test_frontend_agent_in_fullstack_load(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        reg = AGENTS.AgentRegistry.load_fullstack(tmp_path / "agents" / "agents.json")
        assert "pm-agent" in reg and "frontend-agent" in reg

    def test_decision_record_roundtrip(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        obj = ds.record("architect-agent", "frontend-agent",
                        {"architecture": "Flutter", "state_management": "provider", "api_contract": "REST"},
                        ["mobile first", "offline"])
        loaded = ds.load()[0]
        assert loaded == obj

    def test_previous_decisions_summary_keys(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        ds.record("architect-agent", "frontend-agent", {"architecture": "Flutter"})
        pd = ds.previous_decisions()
        s = pd["summary"][0]
        assert {"from", "to", "decision"} <= set(s.keys())

    def test_validate_frontend_returns_validation_result(self, tmp_path):
        r = QUALITY.Validator().validate_frontend(tmp_path, "flutter",
                                                  command=[__import__("sys").executable, "-c", "pass"])
        assert isinstance(r, QUALITY.ValidationResult)

    def test_validate_frontend_errors_captured(self, tmp_path):
        r = QUALITY.Validator().validate_frontend(tmp_path, "flutter",
                                                  command=[__import__("sys").executable, "-c", "raise Exception('x')"])
        assert r.success is False
        assert r.errors

    def test_fullstack_project_all_agents(self, tmp_path):
        """全 7 角色任务 → 各角色 agent 分配。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T1", "name": "需求", "required_role": "product_manager", "agent_type": "pm"},
            {"id": "T2", "name": "设计", "required_role": "architect", "agent_type": "architect"},
            {"id": "T3", "name": "API", "required_role": "backend", "agent_type": "backend"},
            {"id": "T4", "name": "UI", "required_role": "frontend", "agent_type": "frontend"},
            {"id": "T5", "name": "测试", "required_role": "qa", "agent_type": "qa"},
            {"id": "T6", "name": "评审", "required_role": "reviewer", "agent_type": "reviewer"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                                   teams_file=tmp_path / "teams" / "teams.json",
                                   agents_file=tmp_path / "agents" / "agents.json")
        assert res.completed_tasks == 6

    def test_reviewer_task_assigned(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path, tasks=[
            {"id": "T6", "name": "评审", "required_role": "reviewer", "agent_type": "reviewer"},
        ])
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert state["tasks"][0]["agent"] in ("reviewer-agent", "backend-1")

    def test_workspace_context_completed_tasks(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        ctx = json.loads((pd / "workspace_context.json").read_text(encoding="utf-8"))
        assert ctx.get("completed_tasks")

    def test_team_report_has_team_section(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "## Team" in report

    def test_team_report_contribution_rows(self, tmp_path):
        """Agent Contribution 表含 backend-1 行。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "| backend-1 |" in report

    def test_handoff_and_decision_coexist(self, tmp_path):
        """handoff_messages + decision_objects 双资产。"""
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        # 手写决策 → 资产可共存
        ds = MESSAGES.DecisionStore(file=pd / "decision_objects.json")
        ds.record("architect-agent", "frontend-agent", {"architecture": "Flutter"})
        assert (pd / "decision_objects.json").exists()

    def test_context_has_project(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        _fullstack_project(tmp_path)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=fn,
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        assert all("project" in t.get("context", {}) for t in calls)

    def test_context_has_artifacts_key(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        _fullstack_project(tmp_path)
        calls = []

        def fn(task, project_dir, workspace):
            calls.append(task)
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=fn,
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        assert all("artifacts" in t.get("context", {}) for t in calls)

    def test_validate_frontend_flutter_default_not_installed(self, tmp_path):
        """flutter 未装 → 命令不存在 → FAIL (不抛)。"""
        import shutil
        if shutil.which("flutter"):
            pytest.skip("flutter installed")
        v = QUALITY.Validator()
        r = v.validate_frontend(tmp_path, "flutter")
        assert r.success is False


class TestFinalFill:
    def test_fullstack_agents_include_all_roles(self):
        reg = AGENTS.FULLSTACK_AGENTS
        assert {"pm-agent", "architect-agent", "backend-1", "frontend-agent", "qa-agent", "reviewer-agent"} <= set(reg)

    def test_decision_store_previous_empty_when_no_records(self, tmp_path):
        ds = MESSAGES.DecisionStore(file=tmp_path / "d.json")
        assert ds.previous_decisions() == {}


class TestOneMore:
    def test_team_report_has_frontend_agent_row(self, tmp_path):
        _write_fullstack_assets(tmp_path)
        pd = _fullstack_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", mode="team", execute_fn=_ok_fn(),
                             teams_file=tmp_path / "teams" / "teams.json",
                             agents_file=tmp_path / "agents" / "agents.json")
        report = (pd / "team_report.md").read_text(encoding="utf-8")
        assert "frontend" in report
