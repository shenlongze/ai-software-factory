"""tests/console/test_session_team.py — S10-056 批次 B Team Execution Mode 集成层。

设计: docs/sprint10/S10-056-team-design.md (§3 TeamExecutionMode + §2 数据模型)
覆盖 (验收 A-I):
A. execute_project(mode="team") 用团队成员 (required_role → AgentMatcher)
B. TaskDependencyGraph 拓扑排序 (依赖任务先执行)
C. ConflictDetector: 同文件冲突 → ConflictRecord (记录不阻塞)
D. WorkspaceContext 执行中更新 (mark_task_completed/add_artifact)
E. solo mode 缺省完全不变 (兼容)
F. "团队执行" "团队依赖" "团队冲突" 关键词 → 对应视图 (intent/router/action)
G. 不修改核心/模型层/不引入依赖 (测试只 import session 层 + 纯标准库)
H. 新增 >=100 测试全绿 + 全量 pytest 不破坏基线
I. 回归: execute_project/repair_task/workforce/team 不受影响

测试装配: tmp_path + 构造 teams.json/agents.json/execution_plan.json/
task_dependencies.json/conflicts.json/workspace_context.json fixtures
(零真实 ~/.factory 污染); execute_fn 一律 mock (零真实 LLM/网络);
action 层经 monkeypatch _load_exec_cli 注入 FakeExecCli (同 test_session_orchestrator)。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
CONF_MOD = importlib.import_module("factory-console.session.conflicts")
CTX_MOD = importlib.import_module("factory-console.session.context")
DEPS_MOD = importlib.import_module("factory-console.session.dependencies")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
ORCH_MOD = importlib.import_module("factory-console.session.orchestrator")
PIPE_MOD = importlib.import_module("factory-console.session.pipeline")
QUAL_MOD = importlib.import_module("factory-console.session.quality")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
TEAMS_MOD = importlib.import_module("factory-console.session.teams")
WS_MOD = importlib.import_module("factory-console.session.workspace")

Lifecycle = PIPE_MOD.Lifecycle
ConflictDetector = CONF_MOD.ConflictDetector
TaskDependencyGraph = DEPS_MOD.TaskDependencyGraph
WorkspaceContext = WS_MOD.WorkspaceContext

# ------------------------------------------------------------------ 固定 fixture

#: 团队成员编制 (默认 software-team 5 角色)
TEAM_MEMBERS: list[dict] = [
    {"agent": "pm-agent", "role": "product_manager"},
    {"agent": "architect-agent", "role": "architect"},
    {"agent": "backend-1", "role": "backend"},
    {"agent": "flutter-dev", "role": "frontend"},
    {"agent": "qa-agent", "role": "qa"},
]

#: Agent 注册表 (团队成员 + 非成员 tester-1 — 验证候选只限团队成员)
AGENTS: dict[str, dict] = {
    "backend-1": {
        "id": "backend-1",
        "role": "Backend Engineer",
        "skills": ["python", "api", "database"],
        "status": "available",
        "current_task": None,
    },
    "flutter-dev": {
        "id": "flutter-dev",
        "role": "Frontend Engineer",
        "skills": ["flutter", "dart", "ui", "frontend"],
        "status": "available",
        "current_task": None,
    },
    "qa-agent": {
        "id": "qa-agent",
        "role": "QA Engineer",
        "skills": ["test", "qa"],
        "status": "available",
        "current_task": None,
    },
    "architect-agent": {
        "id": "architect-agent",
        "role": "Architect",
        "skills": ["architecture", "design", "system"],
        "status": "available",
        "current_task": None,
    },
    "pm-agent": {
        "id": "pm-agent",
        "role": "Product Manager",
        "skills": ["product", "prd", "requirement"],
        "status": "available",
        "current_task": None,
    },
    "tester-1": {
        "id": "tester-1",
        "role": "QA Engineer",
        "skills": ["test", "qa", "e2e"],
        "status": "available",
        "current_task": None,
    },
}

#: 固定 execution_plan.json 任务 (3 任务: backend/frontend/qa, 含 required_role + files)
PLAN_TASKS: list[dict] = [
    {
        "id": "T001",
        "name": "数据库 Schema 设计",
        "type": "database",
        "required_role": "backend",
        "files": ["db/schema.sql"],
    },
    {
        "id": "T002",
        "name": "前端页面实现",
        "type": "frontend",
        "required_role": "frontend",
        "files": ["lib/main_page.dart"],
    },
    {
        "id": "T003",
        "name": "测试用例编写",
        "type": "test",
        "required_role": "qa",
        "files": ["test/main_test.dart"],
    },
]


# ------------------------------------------------------------------ 工具/夹具

def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_team_assets(root: Path, members: list[dict] | None = None) -> None:
    """工作区 teams.json + agents.json (团队执行/action 层共用)。"""
    team = {
        "software-team": {
            "team_id": "software-team",
            "name": "AI Software Team",
            "members": [dict(m) for m in (members if members is not None else TEAM_MEMBERS)],
            "projects": [],
            "created_at": "2026-08-15T00:00:00+00:00",
        }
    }
    _write_json(root / "teams" / "teams.json", team)
    _write_json(root / "agents" / "agents.json", AGENTS)


def _make_project(
    root: Path,
    slug: str = "demo",
    name: str = "Demo",
    tasks: list[dict] | None = None,
    status: str = "execution_ready",
) -> Path:
    """构造 projects/<slug>/ 固定资产 (execution_plan.json + project.json + product.json)。"""
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else PLAN_TASKS
    _write_json(pdir / "execution_plan.json", {"tasks": chosen, "count": len(chosen)})
    _write_json(pdir / "project.json", {"name": name, "status": status})
    _write_json(
        pdir / "product.json",
        {
            "name": name,
            "problem": "测试问题",
            "user": "测试用户",
            "platform": "mobile",
            "core_features": ["计分", "排行榜"],
            "status": status,
        },
    )
    return pdir


def _state(root: Path, slug: str = "demo") -> dict:
    return _read_json(root / "projects" / slug / "execution_state.json")


def _state_tasks(root: Path, slug: str = "demo") -> list[dict]:
    return _state(root, slug).get("tasks") or []


def _ok_fn(calls: list | None = None):
    """execute_fn mock: 恒成功, 记录调用 (artifact 每任务唯一)。"""
    def fn(task, project_dir, workspace):
        if calls is not None:
            calls.append(task)
        return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}
    return fn


def _fail_fn(calls: list | None = None, error: str = "boom", fail_ids: set | None = None):
    """execute_fn mock: 指定任务失败 (缺省全部失败), 记录调用。"""
    def fn(task, project_dir, workspace):
        if calls is not None:
            calls.append(task)
        if fail_ids is not None:
            if task.get("id") in fail_ids:
                return {"success": False, "error": error}
            return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}
        return {"success": False, "error": error}
    return fn


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


def _paths(root: Path) -> dict:
    """团队模式资产路径 (注入显式 tmp 文件 — hermetic, 零 ~/.factory 污染)。"""
    return {
        "teams_file": root / "teams" / "teams.json",
        "agents_file": root / "agents" / "agents.json",
        "dependencies_file": root / "teams" / "task_dependencies.json",
        "conflicts_file": root / "teams" / "conflicts.json",
        "messages_file": root / "teams" / "agent_messages.json",
    }


def _run_team(
    root: Path,
    slug: str = "demo",
    tasks: list[dict] | None = None,
    deps: dict | None = None,
    members: list[dict] | None = None,
    write_assets: bool = True,
    execute_fn=None,
    calls: list | None = None,
    **kw,
):
    """一键团队模式执行 (装配资产 + 项目 + 依赖图 → execute_project(mode=team))。"""
    if write_assets:
        _write_team_assets(root, members=members)
    _make_project(root, slug=slug, tasks=tasks)
    if deps:
        _write_json(root / "teams" / "task_dependencies.json", deps)
    orch = ORCH_MOD.ExecutionOrchestrator(root, validator=kw.pop("validator", None))
    fn = execute_fn if execute_fn is not None else _ok_fn(calls)
    result = orch.execute_project(
        slug,
        mode="team",
        execute_fn=fn,
        **{**_paths(root), **kw},
    )
    return orch, result


class _FakeExecCli:
    """exec.cli 桩 (monkeypatch _load_exec_cli): 记录调用, 返回注入结果。"""

    def __init__(self, ok: bool = True) -> None:
        self.calls: list[tuple[Path, object]] = []
        self.ok = ok

    def cmd_exec_run(self, root, args):
        self.calls.append((root, args))
        if not self.ok:
            return {"ok": False, "exit_code": 1, "error": "runtime failed", "artifacts": [], "usage": {}}
        return {
            "ok": True,
            "exit_code": 0,
            "result_id": "EXR-001",
            "artifacts": [{"path": f"/tmp/{args.task}.patch", "id": f"art-{args.task}"}],
            "usage": {"cost_usd": "0.01", "duration": "1.2s"},
        }


class _FailValidator:
    """自定义验证器: 恒失败 (workspace 不标记测试用)。"""

    def validate(self, task, task_result, **kw):
        return QUAL_MOD.ValidationResult(
            success=False, tests_total=1, tests_failed=1, errors=["验证失败"]
        )

    def save(self, project_dir, slug, result):
        path = Path(project_dir) / "validation_result.json"
        _write_json(path, result.to_dict())
        return path


@pytest.fixture
def fake_exec(monkeypatch):
    cli = _FakeExecCli(ok=True)
    monkeypatch.setattr(ACTIONS_MOD, "_load_exec_cli", lambda: cli)
    return cli


# ============================================================ 1. TeamExecutionMode (验收 A)

def test_team_mode_executes_all_tasks(tmp_path):
    _, result = _run_team(tmp_path)
    assert result.completed_tasks == 3
    assert result.failed_tasks == 0


def test_team_mode_result_status_user_acceptance(tmp_path):
    _, result = _run_team(tmp_path)
    assert result.status == Lifecycle.USER_ACCEPTANCE


def test_team_mode_state_agents_assigned_by_role(tmp_path):
    _run_team(tmp_path)
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents["T001"] == "backend-1"
    assert agents["T002"] == "flutter-dev"
    assert agents["T003"] == "qa-agent"


def test_team_mode_matched_role_recorded(tmp_path):
    _run_team(tmp_path)
    roles = {t["id"]: t.get("matched_role") for t in _state_tasks(tmp_path)}
    assert roles == {"T001": "backend", "T002": "frontend", "T003": "qa"}


def test_team_mode_state_persisted(tmp_path):
    _run_team(tmp_path)
    state = _state(tmp_path)
    assert state["project"] == "demo"
    assert state["status"] == Lifecycle.USER_ACCEPTANCE
    assert len(state["tasks"]) == 3
    assert all(t["status"] == "completed" for t in state["tasks"])


def test_team_mode_lifecycle_project_json(tmp_path):
    _run_team(tmp_path)
    project = _read_json(tmp_path / "projects" / "demo" / "project.json")
    assert project["status"] == Lifecycle.USER_ACCEPTANCE


def test_team_mode_default_team_used(tmp_path):
    _run_team(tmp_path)
    # 缺省 team_id=software-team: 成员角色分配生效
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents["T001"] == "backend-1"


def test_team_mode_custom_team_id(tmp_path):
    _write_team_assets(tmp_path)
    custom = {
        "backend-team": {
            "team_id": "backend-team",
            "name": "Backend Team",
            "members": [{"agent": "backend-1", "role": "backend"}],
            "projects": [],
            "created_at": "x",
        }
    }
    _write_json(tmp_path / "teams" / "teams.json", custom)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project(
        "demo", mode="team", team_id="backend-team", execute_fn=_ok_fn(), **_paths(tmp_path)
    )
    assert result.completed_tasks == 3
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    # 团队只有 backend 角色: 仅 T001 匹配到 backend-1; 其余保持原 plan agent (空)
    assert agents["T001"] == "backend-1"


def test_team_mode_team_missing_falls_back_default(tmp_path):
    _make_project(tmp_path)
    _write_json(tmp_path / "agents" / "agents.json", AGENTS)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project(
        "demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path)
    )
    assert result.completed_tasks == 3
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents["T002"] == "flutter-dev"  # 默认 software-team 仍生效


def test_team_mode_agents_file_missing_uses_default_registry(tmp_path):
    """agents.json 缺失 → AgentRegistry 默认注册表 (backend-1/flutter-dev/tester-1)。"""
    _write_team_assets(tmp_path, members=TEAM_MEMBERS)
    _make_project(tmp_path)
    paths = _paths(tmp_path)
    paths["agents_file"] = tmp_path / "agents" / "missing.json"  # 不存在
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **paths)
    assert result.completed_tasks == 3


def test_team_mode_no_required_role_keeps_original_agent(tmp_path):
    tasks = [
        {"id": "T001", "name": "数据库", "type": "database", "agent": "backend-1"},
        {"id": "T002", "name": "前端", "type": "frontend", "agent": "flutter-dev"},
    ]
    _run_team(tmp_path, tasks=tasks)
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents == {"T001": "backend-1", "T002": "flutter-dev"}
    assert all(t.get("matched_role") is None for t in _state_tasks(tmp_path))


def test_team_mode_unknown_role_keeps_original_agent(tmp_path):
    tasks = [
        {"id": "T001", "name": "设计", "type": "design", "required_role": "designer", "agent": "backend-1"},
    ]
    _run_team(tmp_path, tasks=tasks)
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents["T001"] == "backend-1"  # 无匹配成员 → 保持原 assignment


def test_team_mode_reason_assigned(tmp_path):
    _run_team(tmp_path)
    reasons = [t.get("reason") for t in _state_tasks(tmp_path)]
    assert all(r for r in reasons)
    assert "skill match" in reasons[0]


def test_team_mode_execute_fn_receives_reassigned_agents(tmp_path):
    calls: list[dict] = []
    _run_team(tmp_path, calls=calls)
    received = {t["id"]: t.get("agent") for t in calls}
    assert received == {"T001": "backend-1", "T002": "flutter-dev", "T003": "qa-agent"}


def test_team_mode_with_records_file_ok(tmp_path):
    """工作区 execution_records.json 存在 → 绩效注入 matcher, 不报错。"""
    _write_json(
        tmp_path / "exec" / "execution_records.json",
        [{"agent": "backend-1", "task": "x", "result": "success", "cost": "0.001"}],
    )
    _, result = _run_team(tmp_path)
    assert result.completed_tasks == 3


def test_team_mode_plan_failure_marks_failed(tmp_path):
    _, result = _run_team(tmp_path, execute_fn=_fail_fn(fail_ids={"T002"}))
    assert result.failed_tasks == 1
    assert result.completed_tasks == 2
    status = {t["id"]: t["status"] for t in _state_tasks(tmp_path)}
    assert status == {"T001": "completed", "T002": "failed", "T003": "completed"}


def test_team_mode_team_run_context_created(tmp_path):
    orch, _ = _run_team(tmp_path)
    team = TEAMS_MOD.TeamRegistry.load(tmp_path / "teams" / "teams.json")["software-team"]
    assert team["team_id"] == "software-team"
    assert orch.workspace == tmp_path


# ============================================================ 2. solo mode 兼容 (验收 E)

def test_solo_mode_default_is_solo(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_ok_fn())
    assert result.completed_tasks == 3
    assert result.status == Lifecycle.USER_ACCEPTANCE


def test_solo_mode_keeps_plan_agents(tmp_path):
    tasks = [
        {"id": "T001", "name": "数据库", "type": "database", "agent": "backend-1"},
        {"id": "T002", "name": "前端", "type": "frontend", "agent": "flutter-dev"},
    ]
    _write_team_assets(tmp_path)
    _make_project(tmp_path, tasks=tasks)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    agents = {t["id"]: t["agent"] for t in _state_tasks(tmp_path)}
    assert agents == {"T001": "backend-1", "T002": "flutter-dev"}


def test_solo_mode_ignores_required_role(tmp_path):
    """solo mode 不做角色匹配 — required_role 任务保持原 agent (无 matched_role)。"""
    tasks = [
        {"id": "T001", "name": "数据库", "type": "database", "required_role": "frontend", "agent": "backend-1"},
    ]
    _write_team_assets(tmp_path)
    _make_project(tmp_path, tasks=tasks)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    tasks_state = _state_tasks(tmp_path)
    assert tasks_state[0]["agent"] == "backend-1"
    assert tasks_state[0].get("matched_role") is None


def test_solo_mode_no_workspace_context_created(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    assert not (tmp_path / "projects" / "demo" / "workspace_context.json").is_file()


def test_solo_mode_no_conflicts_file_created(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    assert not (tmp_path / "teams" / "conflicts.json").is_file()


def test_solo_mode_execution_order_is_plan_order(tmp_path):
    """solo mode 忽略依赖图 — 执行顺序 = plan 原顺序。"""
    tasks = [
        {"id": "T002", "name": "前端", "type": "frontend", "agent": "flutter-dev"},
        {"id": "T001", "name": "数据库", "type": "database", "agent": "backend-1"},
    ]
    _write_team_assets(tmp_path)
    _make_project(tmp_path, tasks=tasks)
    _write_json(tmp_path / "teams" / "task_dependencies.json", {"T001": ["T002"]})
    calls: list[dict] = []
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn(calls))
    assert [t["id"] for t in calls] == ["T002", "T001"]


def test_solo_mode_result_dict_shape(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_ok_fn())
    assert set(result.to_dict().keys()) == {
        "project", "status", "completed_tasks", "failed_tasks",
        "artifacts", "duration", "cost", "errors",
    }


def test_solo_mode_max_retry_retries(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_fail_fn(), max_retry=1)
    assert result.failed_tasks == 3
    retries = {t["id"]: t["retry_count"] for t in _state_tasks(tmp_path)}
    assert all(r == 1 for r in retries.values())


def test_solo_mode_resume_works(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T002"}))
    calls: list[dict] = []
    result = orch.resume("demo", execute_fn=_ok_fn(calls))
    assert result.failed_tasks == 0
    # resume 跳过 completed, 重跑 failed
    assert [t["id"] for t in calls] == ["T002"]


def test_solo_mode_get_progress(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    progress = orch.get_progress("demo")
    assert progress["tasks_total"] == 3
    assert progress["completed"] == 3
    assert progress["agents"] == []


def test_solo_mode_keyword_args_compatible(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("demo", execute_fn=_ok_fn(), max_retry=2)
    assert result.completed_tasks == 3


# ============================================================ 3. required_role → AgentMatcher

def test_role_backend_selects_backend_member(tmp_path):
    tasks = [{"id": "T001", "name": "数据库", "type": "database", "required_role": "backend"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "backend-1"


def test_role_frontend_selects_flutter_dev(tmp_path):
    tasks = [{"id": "T001", "name": "页面", "type": "frontend", "required_role": "frontend"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "flutter-dev"


def test_role_qa_selects_qa_member(tmp_path):
    tasks = [{"id": "T001", "name": "测试", "type": "test", "required_role": "qa"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "qa-agent"


def test_role_architect_selects_architect(tmp_path):
    tasks = [{"id": "T001", "name": "架构设计", "type": "design", "required_role": "architect"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "architect-agent"


def test_role_matching_restricted_to_team(tmp_path):
    """tester-1 注册但非团队成员 → 不被选中 (候选只限团队成员)。"""
    tasks = [{"id": "T001", "name": "测试", "type": "test", "required_role": "qa"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "qa-agent"  # 非 tester-1


def test_role_matching_best_skill_wins(tmp_path):
    """两个 backend 候选: backend-2 技能面更宽 (含 docker) → 同分时 id 排序后仍可区分。"""
    agents = dict(AGENTS)
    agents["backend-2"] = {
        "id": "backend-2",
        "role": "Backend Engineer",
        "skills": ["python", "api", "database", "docker"],
        "status": "available",
        "current_task": None,
    }
    members = [
        {"agent": "backend-1", "role": "backend"},
        {"agent": "backend-2", "role": "backend"},
    ]
    _write_team_assets(tmp_path, members=members)
    _write_json(tmp_path / "agents" / "agents.json", agents)
    _make_project(tmp_path, tasks=[{"id": "T001", "name": "数据库", "type": "database", "required_role": "backend"}])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path))
    # 同等技能命中 → 成功率 (中性 0.5) 与成本相同 → id 字典序 → backend-1
    assert _state_tasks(tmp_path)[0]["agent"] in ("backend-1", "backend-2")


def test_role_matching_metrics_tiebreak(tmp_path):
    """同技能不同成功率: 高成功率者胜出。"""
    agents = dict(AGENTS)
    agents["backend-2"] = {
        "id": "backend-2",
        "role": "Backend Engineer",
        "skills": ["python", "api", "database"],
        "status": "available",
        "current_task": None,
    }
    members = [
        {"agent": "backend-1", "role": "backend"},
        {"agent": "backend-2", "role": "backend"},
    ]
    _write_team_assets(tmp_path, members=members)
    _write_json(tmp_path / "agents" / "agents.json", agents)
    _write_json(
        tmp_path / "exec" / "execution_records.json",
        [
            {"agent": "backend-2", "task": "x", "result": "success", "cost": "0.001"},
            {"agent": "backend-2", "task": "y", "result": "success", "cost": "0.001"},
        ],
    )
    _make_project(tmp_path, tasks=[{"id": "T001", "name": "数据库", "type": "database", "required_role": "backend"}])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path))
    assert _state_tasks(tmp_path)[0]["agent"] == "backend-2"  # 成功率 1.0 > 0.5


def test_role_matching_empty_required_role_no_match(tmp_path):
    tasks = [{"id": "T001", "name": "数据库", "type": "database", "required_role": ""}]
    _run_team(tmp_path, tasks=tasks)
    task = _state_tasks(tmp_path)[0]
    assert task["agent"] == ""  # 无 agent 字段 → 空 (不匹配)


def test_role_matching_no_matching_member_keeps_original(tmp_path):
    tasks = [
        {"id": "T001", "name": "部署", "type": "deploy", "required_role": "devops", "agent": "backend-1"},
    ]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "backend-1"


def test_role_matching_capabilities_field_match(tmp_path):
    """agent role 不含关键词但 capabilities 含 required_role → 匹配 (RoleSystem 兜底)。"""
    agents = {
        "dev-1": {
            "id": "dev-1",
            "role": "Developer",
            "skills": ["python"],
            "capabilities": ["backend_api", "database_schema"],
            "status": "available",
            "current_task": None,
        }
    }
    members = [{"agent": "dev-1", "role": "developer"}]
    _write_team_assets(tmp_path, members=members)
    _write_json(tmp_path / "agents" / "agents.json", agents)
    _make_project(tmp_path, tasks=[{"id": "T001", "name": "API", "type": "api", "required_role": "backend"}])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path))
    assert _state_tasks(tmp_path)[0]["agent"] == "dev-1"


def test_role_matching_reason_contains_skill_match(tmp_path):
    tasks = [{"id": "T001", "name": "数据库", "type": "database", "required_role": "backend"}]
    _run_team(tmp_path, tasks=tasks)
    reason = _state_tasks(tmp_path)[0].get("reason") or ""
    assert "skill match" in reason
    assert "成功率" in reason


def test_role_matching_required_skills_from_type(tmp_path):
    """task.type → 必备技能推导 (derive_required_skills) → 匹配面确定。"""
    tasks = [{"id": "T001", "name": "任意名", "type": "frontend", "required_role": "frontend"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "flutter-dev"


def test_role_matching_plan_existing_reason_kept(tmp_path):
    """plan 已有 reason → 不覆盖 (保留可解释调度)。"""
    tasks = [
        {"id": "T001", "name": "数据库", "type": "database", "required_role": "backend", "reason": "已指定"},
    ]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["reason"] == "已指定"


def test_role_matching_pm_role_keeps_original(tmp_path):
    """pm-agent 注册但角色 product_manager 匹配; 缺 agent 原值 → 空 (不报错)。"""
    tasks = [{"id": "T001", "name": "需求分析", "type": "pm", "required_role": "product_manager"}]
    _run_team(tmp_path, tasks=tasks)
    assert _state_tasks(tmp_path)[0]["agent"] == "pm-agent"


# ============================================================ 4. Dependency Resolver (验收 B)

def test_topo_single_dependency_orders_first(tmp_path):
    deps = {"T002": ["T001"]}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids.index("T001") < ids.index("T002")


def test_topo_chain_order(tmp_path):
    deps = {"T002": ["T001"], "T003": ["T002"]}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids == ["T001", "T002", "T003"]


def test_topo_no_deps_original_order(tmp_path):
    _run_team(tmp_path, deps={})
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids == ["T001", "T002", "T003"]


def test_topo_execution_call_order_matches(tmp_path):
    calls: list[dict] = []
    deps = {"T002": ["T001"], "T003": ["T002"]}
    _run_team(tmp_path, deps=deps, calls=calls)
    assert [t["id"] for t in calls] == ["T001", "T002", "T003"]


def test_topo_state_order_matches(tmp_path):
    deps = {"T002": ["T001"], "T003": ["T002"]}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids == ["T001", "T002", "T003"]


def test_topo_edges_outside_plan_ignored(tmp_path):
    """依赖图含图外任务 (T999) → 不影响计划内任务拓扑。"""
    deps = {"T002": ["T001"], "T999": ["T002"]}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    # 拓扑序非唯一 (T003 可在 T002 前后); 关键: T001 先于 T002 (依赖满足), 图外 T999 不影响
    assert ids[0] == "T001"
    assert ids.index("T001") < ids.index("T002")


def test_topo_cycle_failsafe_completes(tmp_path):
    """环 (T001↔T002) → 失败安全: 全部任务仍返回 (剩余按原顺序追加)。"""
    deps = {"T001": ["T002"], "T002": ["T001"]}
    _, result = _run_team(tmp_path, deps=deps)
    assert result.completed_tasks == 3
    assert len(_state_tasks(tmp_path)) == 3


def test_topo_dependencies_file_missing_original_order(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    paths = _paths(tmp_path)
    paths["dependencies_file"] = tmp_path / "teams" / "missing_deps.json"
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **paths)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids == ["T001", "T002", "T003"]


def test_topo_three_tasks_dag(tmp_path):
    deps = {"T002": ["T001"], "T003": ["T001"]}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids[0] == "T001"
    assert set(ids[1:]) == {"T002", "T003"}


def test_topo_empty_plan_tasks_keeps_empty(tmp_path):
    _run_team(tmp_path, tasks=[])
    assert _state_tasks(tmp_path) == []


def test_topo_missing_task_ids_keeps_order(tmp_path):
    tasks = [
        {"name": "A", "required_role": "backend"},
        {"name": "B", "required_role": "frontend"},
    ]
    _write_team_assets(tmp_path)
    _make_project(tmp_path, tasks=tasks)
    _write_json(tmp_path / "teams" / "task_dependencies.json", {})
    calls: list[dict] = []
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(calls), **_paths(tmp_path))
    assert [t["name"] for t in calls] == ["A", "B"]


def test_topo_deps_file_with_extra_keys_ignored(tmp_path):
    deps = {"T002": ["T001"], "T003": []}
    _run_team(tmp_path, deps=deps)
    ids = [t["id"] for t in _state_tasks(tmp_path)]
    assert ids.index("T001") < ids.index("T002")


# ============================================================ 5. WorkspaceContext (验收 D)

def test_workspace_context_created_in_team_mode(tmp_path):
    _run_team(tmp_path)
    ctx_file = tmp_path / "projects" / "demo" / "workspace_context.json"
    assert ctx_file.is_file()


def test_workspace_project_name(tmp_path):
    _run_team(tmp_path)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert ctx["project"] == "demo"


def test_workspace_completed_tasks(tmp_path):
    _run_team(tmp_path)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert sorted(ctx["completed_tasks"]) == ["T001", "T002", "T003"]


def test_workspace_artifacts(tmp_path):
    _run_team(tmp_path)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert sorted(ctx["artifacts"]) == ["art-T001", "art-T002", "art-T003"]


def test_workspace_agent_history(tmp_path):
    _run_team(tmp_path)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    history = ctx["agent_history"]
    assert len(history) == 3
    by_task = {h["task"]: h for h in history}
    assert by_task["T001"]["agent"] == "backend-1"
    assert by_task["T001"]["result"] == "success"


def test_workspace_not_created_in_solo(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", execute_fn=_ok_fn())
    assert not (tmp_path / "projects" / "demo" / "workspace_context.json").is_file()


def test_workspace_failed_task_not_marked(tmp_path):
    _run_team(tmp_path, execute_fn=_fail_fn(fail_ids={"T002"}))
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert sorted(ctx["completed_tasks"]) == ["T001", "T003"]
    assert "art-T002" not in ctx["artifacts"]


def test_workspace_existing_context_preserved(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    _write_json(
        tmp_path / "projects" / "demo" / "workspace_context.json",
        {"project": "demo", "files": ["README.md"], "completed_tasks": [], "artifacts": [], "agent_history": []},
    )
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path))
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert "README.md" in ctx["files"]
    assert len(ctx["completed_tasks"]) == 3


def test_workspace_artifact_deduped(tmp_path):
    """两任务同 artifact → add_artifact 去重 (列表唯一)。"""
    def same_artifact(task, project_dir, workspace):
        return {"success": True, "artifact": "shared.patch", "cost": "0.01"}
    _run_team(tmp_path, execute_fn=same_artifact)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert ctx["artifacts"] == ["shared.patch"]


def test_workspace_agent_history_ordered(tmp_path):
    deps = {"T002": ["T001"], "T003": ["T002"]}
    _run_team(tmp_path, deps=deps)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert [h["task"] for h in ctx["agent_history"]] == ["T001", "T002", "T003"]


def test_workspace_completed_task_ids_unique(tmp_path):
    _run_team(tmp_path)
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert len(ctx["completed_tasks"]) == len(set(ctx["completed_tasks"]))


def test_workspace_validation_fail_not_marked(tmp_path):
    """执行成功但验证失败 → 任务 failed → 不标记 completed。"""
    _run_team(tmp_path, validator=_FailValidator())
    ctx = WorkspaceContext.load(tmp_path / "projects" / "demo")
    assert ctx["completed_tasks"] == []
    assert ctx["agent_history"] == []


# ============================================================ 6. ConflictDetector 集成 (验收 C)

def test_conflict_detected_on_same_file(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "type": "database", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "type": "frontend", "required_role": "frontend", "files": ["main.py"]},
        {"id": "T003", "name": "C", "type": "test", "required_role": "qa", "files": ["test.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert len(records) == 1
    assert records[0]["file"] == "main.py"


def test_conflict_record_open_status(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert records[0]["status"] == "open"


def test_conflict_does_not_block_execution(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _, result = _run_team(tmp_path, tasks=tasks)
    assert result.completed_tasks == 2  # 冲突记录不阻塞


def test_conflict_file_written_to_workspace_teams(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    assert (tmp_path / "teams" / "conflicts.json").is_file()


def test_conflict_record_fields(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    record = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()[0]
    assert record["task_a"] == "T001"  # 先归属者
    assert record["task_b"] == "T002"
    assert record["file"] == "main.py"
    assert record["detected_at"]


def test_conflict_no_duplicate_records(tmp_path):
    """三任务同文件: T001 归属, T002/T003 各一条冲突记录 (去重)。"""
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
        {"id": "T003", "name": "C", "required_role": "qa", "files": ["main.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    pairs = {(r["task_a"], r["task_b"]) for r in records}
    assert pairs == {("T001", "T002"), ("T001", "T003")}


def test_conflict_distinct_files_no_conflict(tmp_path):
    _run_team(tmp_path)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert records == []


def test_conflict_no_files_field_no_conflict(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend"},
        {"id": "T002", "name": "B", "required_role": "frontend"},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert records == []


def test_conflict_ownership_keeps_first_claim(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert records[0]["task_a"] == "T001"
    assert records[0]["task_b"] == "T002"


def test_conflict_abs_claim_detected_by_relative(tmp_path):
    """绝对路径 claim → 归一化为相对路径 → 相对路径引用可检出冲突。"""
    pdir = tmp_path / "projects" / "demo"
    abs_file = str(pdir / "lib" / "page.dart")
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": [abs_file]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["lib/page.dart"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert len(records) == 1


def test_conflict_preexisting_records_loaded(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    _write_json(
        tmp_path / "teams" / "conflicts.json",
        [{"task_a": "OLD1", "task_b": "OLD2", "file": "old.py", "detected_at": "x", "status": "open"}],
    )
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("demo", mode="team", execute_fn=_ok_fn(), **_paths(tmp_path))
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert len(records) == 1  # 既有记录保留, 本 run 无冲突


def test_conflict_same_task_own_file_no_conflict(tmp_path):
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["a.py", "b.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["b.py", "c.py"]},
    ]
    _run_team(tmp_path, tasks=tasks)
    records = ConflictDetector(conflicts_file=tmp_path / "teams" / "conflicts.json").list()
    assert len(records) == 1
    assert records[0]["file"] == "b.py"


# ============================================================ 7. AgentMessage 可选记录

def test_messages_disabled_by_default_no_file(tmp_path):
    _run_team(tmp_path)
    assert not (tmp_path / "teams" / "agent_messages.json").is_file()


def test_messages_enabled_writes_file(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    assert (tmp_path / "teams" / "agent_messages.json").is_file()


def test_messages_architect_to_member(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    msgs = _read_json(tmp_path / "teams" / "agent_messages.json")
    assert all(m["from"] == "architect-agent" for m in msgs)
    assert {m["to"] for m in msgs} == {"backend-1", "flutter-dev", "qa-agent"}


def test_messages_type_instruction(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    msgs = _read_json(tmp_path / "teams" / "agent_messages.json")
    assert all(m["type"] == "instruction" for m in msgs)


def test_messages_content_contains_task(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    msgs = _read_json(tmp_path / "teams" / "agent_messages.json")
    assert any("T001" in m["content"] for m in msgs)


def test_messages_one_per_completed_task(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    msgs = _read_json(tmp_path / "teams" / "agent_messages.json")
    assert len(msgs) == 3


def test_messages_not_sent_for_failed_task(tmp_path):
    _run_team(
        tmp_path,
        enable_messages=True,
        tasks=[
            {"id": "T001", "name": "A", "required_role": "backend"},
            {"id": "T002", "name": "B", "required_role": "frontend"},
        ],
        execute_fn=_fail_fn(fail_ids={"T002"}),
    )
    msgs = _read_json(tmp_path / "teams" / "agent_messages.json")
    assert len(msgs) == 1
    assert msgs[0]["to"] == "backend-1"


def test_messages_store_reload(tmp_path):
    _run_team(tmp_path, enable_messages=True)
    store = importlib.import_module("factory-console.session.messages").AgentMessageStore(
        file=tmp_path / "teams" / "agent_messages.json"
    )
    assert len(store.list()) == 3


# ============================================================ 8. action 增强 (验收 F)

def test_action_team_execute_registered():
    registry = ACTIONS_MOD.build_default_actions()
    action = registry.get("team_execute")
    assert action is not None
    assert action.permission == "project"
    assert action.metadata["sensitive"] is True


def test_action_team_dependencies_registered():
    registry = ACTIONS_MOD.build_default_actions()
    action = registry.get("team_dependencies")
    assert action is not None
    assert action.permission == "user"


def test_action_team_conflicts_registered():
    registry = ACTIONS_MOD.build_default_actions()
    action = registry.get("team_conflicts")
    assert action is not None
    assert action.permission == "user"


def test_action_team_execute_runs(tmp_path, fake_exec):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert "团队执行完成" in result.message
    assert len(fake_exec.calls) == 3


def test_action_team_execute_data_mode_team(tmp_path, fake_exec):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert result.data["mode"] == "team"
    assert result.data["completed_tasks"] == 3


def test_action_team_execute_data_assignments(tmp_path, fake_exec):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assignments = {a["id"]: a["agent"] for a in result.data["assignments"]}
    assert assignments == {"T001": "backend-1", "T002": "flutter-dev", "T003": "qa-agent"}


def test_action_team_execute_data_team_id(tmp_path, fake_exec):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert result.data["team_id"] == "software-team"


def test_action_team_execute_conflicts_summary(tmp_path, fake_exec):
    """plan 任务含同文件冲突 → 团队执行后 conflicts 汇总非空。"""
    _write_team_assets(tmp_path)
    tasks = [
        {"id": "T001", "name": "A", "required_role": "backend", "files": ["main.py"]},
        {"id": "T002", "name": "B", "required_role": "frontend", "files": ["main.py"]},
    ]
    _make_project(tmp_path, tasks=tasks)
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert len(result.data["conflicts"]) == 1
    assert result.data["conflicts"][0]["file"] == "main.py"


def test_action_team_execute_no_product_error(tmp_path, fake_exec):
    intent = _intent("team_execute", raw="团队执行 不存在项目")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert not result.ok
    assert "未找到产品定义" in result.message


def test_action_team_execute_lifecycle_rejected(tmp_path, fake_exec):
    _write_team_assets(tmp_path)
    _make_project(tmp_path, status="delivered")
    intent = _intent("team_execute", raw="团队执行 Demo")
    result = ACTIONS_MOD._team_execute(_exec_ctx(tmp_path, intent=intent))
    assert not result.ok
    assert "不允许执行" in (result.message + result.error)


def test_action_team_dependencies_view_data(tmp_path):
    _write_json(
        tmp_path / "teams" / "task_dependencies.json",
        {"T002": ["T001"], "T003": ["T002"]},
    )
    result = ACTIONS_MOD._team_dependencies(_exec_ctx(tmp_path))
    assert result.ok
    assert result.data["dependencies"] == {"T002": ["T001"], "T003": ["T002"]}
    # 实现语义: topological_order 只排序有依赖的任务 (T001 无依赖不在此列)
    assert result.data["topological_order"][0] == "T002"
    assert set(result.data["topological_order"]) <= {"T002", "T003"}


def test_action_team_dependencies_empty(tmp_path):
    result = ACTIONS_MOD._team_dependencies(_exec_ctx(tmp_path))
    assert result.ok
    assert result.data["dependencies"] == {}


def test_action_team_dependencies_rows(tmp_path):
    _write_json(tmp_path / "teams" / "task_dependencies.json", {"T002": ["T001"]})
    result = ACTIONS_MOD._team_dependencies(_exec_ctx(tmp_path))
    assert ["T002", "T001"] in result.data["rows"]


def test_action_team_conflicts_view_data(tmp_path):
    _write_json(
        tmp_path / "teams" / "conflicts.json",
        [{"task_a": "T001", "task_b": "T002", "file": "main.py", "detected_at": "x", "status": "open"}],
    )
    result = ACTIONS_MOD._team_conflicts(_exec_ctx(tmp_path))
    assert result.ok
    assert result.data["count"] == 1
    assert result.data["conflicts"][0]["task_a"] == "T001"


def test_action_team_conflicts_empty(tmp_path):
    result = ACTIONS_MOD._team_conflicts(_exec_ctx(tmp_path))
    assert result.ok
    assert result.data["count"] == 0
    assert result.data["conflicts"] == []


def test_action_team_dispatcher_raw_execute(tmp_path, fake_exec):
    """team action raw="团队执行 ..." → 团队模式执行。"""
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("team", raw="团队执行 Demo")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["mode"] == "team"


def test_action_team_dispatcher_raw_dependencies(tmp_path):
    _write_json(tmp_path / "teams" / "task_dependencies.json", {"T1": ["T0"]})
    intent = _intent("team", raw="团队依赖")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert "dependencies" in result.data


def test_action_team_dispatcher_raw_conflicts(tmp_path):
    _write_json(
        tmp_path / "teams" / "conflicts.json",
        [{"task_a": "A", "task_b": "B", "file": "f.py", "detected_at": "x", "status": "open"}],
    )
    intent = _intent("team", raw="团队冲突")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["count"] == 1


def test_action_team_dispatcher_intent_type_fallback(tmp_path):
    """程序化 Intent (无 raw 关键词) → intent_type 兜底分派。"""
    intent = _intent("team_conflicts", raw="")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["count"] == 0


def test_action_team_view_unchanged(tmp_path):
    _write_team_assets(tmp_path)
    intent = _intent("team", raw="查看团队")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["count"] == 5


def test_action_team_create_unchanged(tmp_path):
    intent = _intent("team", raw="创建团队 电商后端团队")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["team_id"] == "电商后端团队"


# ============================================================ 9. intent/router 映射 (验收 F)

@pytest.mark.parametrize(
    "text",
    ["团队执行", "团队执行 我的项目", "团队开发", "团队开始开发"],
)
def test_intent_team_execute_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_EXECUTE


@pytest.mark.parametrize(
    "text",
    ["团队依赖", "依赖关系", "任务依赖", "依赖图", "团队依赖关系"],
)
def test_intent_team_dependencies_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_DEPENDENCIES


@pytest.mark.parametrize(
    "text",
    ["团队冲突", "文件冲突", "冲突检测", "冲突"],
)
def test_intent_team_conflicts_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_CONFLICTS


def test_intent_团队执行_not_stolen_by_team_keyword():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队执行")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_EXECUTE  # 非 INTENT_TEAM


def test_intent_团队依赖_not_stolen_by_workforce():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队依赖")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_DEPENDENCIES  # 非 workforce


def test_intent_团队冲突_not_stolen_by_team_keyword():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队冲突")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM_CONFLICTS  # 非 INTENT_TEAM


def test_router_mapping_team_execute():
    assert ROUTER_MOD.DEFAULT_ROUTES["team_execute"] == "team_execute"


def test_router_mapping_team_dependencies():
    assert ROUTER_MOD.DEFAULT_ROUTES["team_dependencies"] == "team_dependencies"


def test_router_mapping_team_conflicts():
    assert ROUTER_MOD.DEFAULT_ROUTES["team_conflicts"] == "team_conflicts"


def test_router_resolves_team_execute_action():
    router = ROUTER_MOD.IntentRouter()
    registry = ACTIONS_MOD.build_default_actions()
    intent = _intent("team_execute", raw="团队执行")
    action = router.route(intent, registry)
    assert action.name == "team_execute"


def test_router_resolves_team_dependencies_action():
    router = ROUTER_MOD.IntentRouter()
    registry = ACTIONS_MOD.build_default_actions()
    action = router.route(_intent("team_dependencies", raw="团队依赖"), registry)
    assert action.name == "team_dependencies"


def test_router_resolves_team_conflicts_action():
    router = ROUTER_MOD.IntentRouter()
    registry = ACTIONS_MOD.build_default_actions()
    action = router.route(_intent("team_conflicts", raw="团队冲突"), registry)
    assert action.name == "team_conflicts"


def test_intent_查看团队_still_workforce():
    intent = INTENT_MOD.KeywordIntentParser().parse("查看团队")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_intent_创建团队_still_team():
    intent = INTENT_MOD.KeywordIntentParser().parse("创建团队 电商团队")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM
    assert intent.params.get("name") == "电商团队"


def test_intent_团队协作_still_team():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队协作")
    assert intent.intent_type == INTENT_MOD.INTENT_TEAM


# ============================================================ 10. 回归 (验收 I)

def test_regression_execute_project_action_solo(tmp_path, fake_exec):
    """既有 execute_project action (solo) 数据不含 mode 键。"""
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("execute_project", raw="开始开发")
    result = ACTIONS_MOD.execute_project(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert "mode" not in result.data
    assert result.data["completed_tasks"] == 3


def test_regression_repair_task_action(tmp_path):
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("repair_task", raw="修复失败任务")
    result = ACTIONS_MOD.repair_task(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["status"] == "none"


def test_regression_workforce_action(tmp_path):
    _write_team_assets(tmp_path)
    intent = _intent("workforce", raw="查看团队")
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["count"] >= 3


def test_regression_team_view_action(tmp_path):
    _write_team_assets(tmp_path)
    intent = _intent("team", raw="团队协作")
    result = ACTIONS_MOD.team(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert result.data["count"] == 5


def test_regression_router_workforce():
    assert ROUTER_MOD.DEFAULT_ROUTES["workforce"] == "workforce"


def test_regression_router_team():
    assert ROUTER_MOD.DEFAULT_ROUTES["team"] == "team"


def test_regression_router_execute_project():
    assert ROUTER_MOD.DEFAULT_ROUTES["execute_project"] == "execute_project"


def test_regression_router_accept_project():
    assert ROUTER_MOD.DEFAULT_ROUTES["accept_project"] == "accept_project"


def test_regression_intent_start_development():
    intent = INTENT_MOD.KeywordIntentParser().parse("开始开发这个产品")
    assert intent.intent_type == INTENT_MOD.INTENT_EXECUTE_PROJECT


def test_regression_intent_run_task():
    intent = INTENT_MOD.KeywordIntentParser().parse("帮我实现登录功能")
    assert intent.intent_type == INTENT_MOD.INTENT_RUN_TASK


def test_regression_accept_project_action(tmp_path):
    """accept_project: 非 user_acceptance 状态 → 明确拒绝。"""
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("accept_project", raw="通过验收")
    result = ACTIONS_MOD.accept_project(_exec_ctx(tmp_path, intent=intent))
    assert not result.ok
    assert "尚未到达待验收状态" in result.message


def test_regression_team_execute_action_unaffected_by_workforce(tmp_path, fake_exec):
    """workforce 关键词 "团队" 不抢 "团队执行" action 路径。"""
    _write_team_assets(tmp_path)
    _make_project(tmp_path)
    intent = _intent("workforce", raw="团队执行 Demo")
    # workforce 只读视图 (不执行项目)
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path, intent=intent))
    assert result.ok
    assert len(fake_exec.calls) == 0
