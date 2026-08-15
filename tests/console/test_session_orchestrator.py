"""tests/console/test_session_orchestrator.py — S10-052 Autonomous Production Loop (Phase 1-8)。

设计: docs/sprint10/S10-052-production-loop-design.md
覆盖 (验收 A-K):
A. ExecutionOrchestrator: 读 execution_plan.json → 顺序执行 (execute_fn mock)
B. Task Queue: pending → running → completed (状态持久化)
C. ExecutionState: execution_state.json load/save/持久化
D. execute_project Action: "开始开发" → 确认门 → 执行
E. Lifecycle: EXECUTION_READY → DEVELOPMENT → (全完成) → TESTING → DELIVERED
F. Progress Query: project_progress 返回 status/total/completed/running/pending/failed/agents
G. Failure Handling: 失败 → retry(1次) → failed, 不无限重试; 可 resume
H. 复用 execute_task 逻辑 (execute_fn 注入/mock, 不重实现 Agent Runtime)
I. 不修改核心/不引入依赖
J. 新增 >=60 测试全绿 + 全量 pytest 不破坏基线
K. 回归: 现有 create_product/execute_task/prepare_project 不受影响

测试装配 (同 test_session_pipeline/test_session_agent_execution):
- workspace 一律 tmp_path (零 ~/.factory 污染); execute_fn 一律 mock (零真实 LLM/网络)
- execution_plan.json 固定 fixture (3 任务: backend-1/flutter-dev/backend-1)
- action 层经 monkeypatch _load_exec_cli 注入 FakeExecCli (真实桥接链:
  orchestrator → execute_task → cmd_exec_run 桩)
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
CONF_MOD = importlib.import_module("factory-console.session.confirm")
CTX_MOD = importlib.import_module("factory-console.session.context")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
ORCH_MOD = importlib.import_module("factory-console.session.orchestrator")
PIPE_MOD = importlib.import_module("factory-console.session.pipeline")
PROD_MOD = importlib.import_module("factory-console.session.product")
ROUTER_MOD = importlib.import_module("factory-console.session.router")
SESS_MOD = importlib.import_module("factory-console.session.session")

Lifecycle = PIPE_MOD.Lifecycle

# ------------------------------------------------------------------ 固定 fixture

#: 固定 execution_plan.json 任务 (3 任务, 覆盖 backend-1/flutter-dev/backend-1)
PLAN_TASKS: list[dict] = [
    {"id": "T001", "name": "数据库 Schema 设计", "agent_type": "backend", "agent": "backend-1"},
    {"id": "T002", "name": "前端页面实现", "agent_type": "frontend", "agent": "flutter-dev"},
    {"id": "T003", "name": "测试用例编写", "agent_type": "qa", "agent": "backend-1"},
]


def _make_project(
    root: Path,
    slug: str = "scorepocket",
    name: str = "ScorePocket",
    tasks: list[dict[str, str]] | None = None,
    status: str = "execution_ready",
    *,
    project_json: bool = True,
    product_json: bool = True,
    plan_json: bool = True,
) -> Path:
    """构造 projects/<slug>/ 固定资产 (execution_plan.json + project.json + product.json)。"""
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    chosen = tasks if tasks is not None else PLAN_TASKS
    if plan_json:
        (pdir / "execution_plan.json").write_text(
            json.dumps({"tasks": chosen, "count": len(chosen)}, ensure_ascii=False),
            encoding="utf-8",
        )
    if project_json:
        (pdir / "project.json").write_text(
            json.dumps({"name": name, "status": status}, ensure_ascii=False),
            encoding="utf-8",
        )
    if product_json:
        # 完整产品字段 (prepare_project 完整性校验需要 problem/user/core_features)
        (pdir / "product.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "problem": "测试问题",
                    "user": "测试用户",
                    "platform": "mobile",
                    "core_features": ["计分", "排行榜"],
                    "status": "execution_ready",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return pdir


def _exec_ctx(root: Path, **kw) -> ACT_MOD.ExecutionContext:
    """默认 ExecutionContext (tmp workspace + 独立 SessionContext, 零污染)。"""
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        user="user",
        **kw,
    )


def _make_ok_fn(calls: list | None = None):
    """execute_fn mock: 恒成功, 记录调用。"""
    def fn(task, project_dir, workspace):
        if calls is not None:
            calls.append(task)
        return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}
    return fn


def _make_fail_fn(calls: list | None = None, error: str = "boom"):
    """execute_fn mock: 恒失败, 记录调用。"""
    def fn(task, project_dir, workspace):
        if calls is not None:
            calls.append(task)
        return {"success": False, "error": error}
    return fn


def _make_flaky_fn(calls: list | None = None, fail_until: int = 1):
    """execute_fn mock: 前 fail_until 次失败, 之后成功 (重试恢复场景)。"""
    state = {"n": 0}

    def fn(task, project_dir, workspace):
        state["n"] += 1
        if calls is not None:
            calls.append(task)
        if state["n"] <= fail_until:
            return {"success": False, "error": "flaky"}
        return {"success": True, "artifact": f"art-{task.get('id')}"}
    return fn


class _FakeExecCli:
    """exec.cli 桩 (monkeypatch _load_exec_cli): 记录调用, 返回注入结果。"""

    def __init__(self, ok: bool = True) -> None:
        self.calls: list[tuple[Path, object]] = []
        self.ok = ok

    def cmd_exec_run(self, root, args):
        self.calls.append((root, args))
        if not self.ok:
            return {
                "ok": False,
                "exit_code": 1,
                "error": "runtime failed",
                "artifacts": [],
                "usage": {},
            }
        return {
            "ok": True,
            "exit_code": 0,
            "result_id": "EXR-001",
            "artifacts": [{"path": f"/tmp/{args.task}.patch", "id": f"art-{args.task}"}],
            "usage": {"cost_usd": "0.01", "duration": "1.2s"},
        }


class _FakeOrgCli:
    """org.cli 桩 (monkeypatch _load_org_cli): create_product 桥接用 (同 pipeline 测试)。"""

    def cmd_project_register(self, root, args):
        return {
            "ok": True,
            "project": {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


class _SpyGate:
    """Session 集成探针 gate: 记录 confirm 调用, 返回注入决策。"""

    def __init__(self, decision: bool = True) -> None:
        self.decision = decision
        self.calls: list[tuple[str, object, object]] = []

    def confirm(self, action_name, intent, context):
        self.calls.append((action_name, intent, context))
        return self.decision


class _RecordingOrchestrator(ORCH_MOD.ExecutionOrchestrator):
    """记录 _set_lifecycle 调用序列 (Lifecycle 推进断言)。"""

    def __init__(self, workspace: Path) -> None:
        super().__init__(workspace)
        self.lifecycle_calls: list[str] = []

    def _set_lifecycle(self, project_dir, slug, status):
        self.lifecycle_calls.append(status)
        return super()._set_lifecycle(project_dir, slug, status)


@pytest.fixture
def fake_org(monkeypatch):
    org = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: org)
    return org


@pytest.fixture
def fake_exec(monkeypatch):
    cli = _FakeExecCli(ok=True)
    monkeypatch.setattr(ACTIONS_MOD, "_load_exec_cli", lambda: cli)
    return cli


# ================================================================== 1. ExecutionResult (验收数据契约)


def test_result_defaults():
    r = ORCH_MOD.ExecutionResult(project="ScorePocket")
    assert r.status == "development"
    assert r.completed_tasks == 0
    assert r.failed_tasks == 0
    assert r.artifacts == []
    assert r.duration == 0.0
    assert r.cost == ""
    assert r.errors == []


def test_result_fields_set():
    r = ORCH_MOD.ExecutionResult(
        project="ScorePocket",
        status="delivered",
        completed_tasks=3,
        failed_tasks=0,
        artifacts=["a.patch"],
        duration=1.5,
        cost="0.01",
        errors=[],
    )
    assert r.project == "ScorePocket"
    assert r.status in ("user_acceptance", "delivered")
    assert r.completed_tasks == 3
    assert r.artifacts == ["a.patch"]
    assert r.duration == 1.5
    assert r.cost == "0.01"


def test_result_to_dict_contract_keys():
    r = ORCH_MOD.ExecutionResult(project="ScorePocket")
    view = r.to_dict()
    assert set(view) == {
        "project",
        "status",
        "completed_tasks",
        "failed_tasks",
        "artifacts",
        "duration",
        "cost",
        "errors",
    }


def test_result_to_dict_values():
    r = ORCH_MOD.ExecutionResult(
        project="S", status="failed", completed_tasks=1, failed_tasks=2,
        artifacts=["x"], duration=3.0, cost="0.1", errors=["e"],
    )
    assert r.to_dict()["status"] == "failed"
    assert r.to_dict()["failed_tasks"] == 2
    assert r.to_dict()["errors"] == ["e"]


def test_result_lists_are_isolated_copies():
    r = ORCH_MOD.ExecutionResult(project="S", artifacts=["a"], errors=["e"])
    view = r.to_dict()
    view["artifacts"].append("zzz")
    assert r.artifacts == ["a"]


def test_result_status_values_follow_lifecycle():
    """status 取值: delivered (全完成) / failed (存在失败, 可 resume)。"""
    assert Lifecycle.DELIVERED == "delivered"
    assert Lifecycle.DEVELOPMENT == "development"
    assert Lifecycle.TESTING == "testing"
    assert Lifecycle.EXECUTION_READY == "execution_ready"


# ================================================================== 2. ExecutionState (验收 C)


def test_state_defaults():
    s = ORCH_MOD.ExecutionState(project="ScorePocket")
    assert s.status == "development"
    assert s.lifecycle == "development"
    assert s.started_at == ""
    assert s.tasks == []


def test_state_to_dict_keys():
    s = ORCH_MOD.ExecutionState(project="ScorePocket")
    assert set(s.to_dict()) == {"project", "status", "lifecycle", "started_at", "tasks"}


def test_state_from_dict_roundtrip():
    data = {
        "project": "ScorePocket",
        "status": "development",
        "lifecycle": "development",
        "started_at": "2026-08-15T00:00:00+00:00",
        "tasks": [
            {"id": "T001", "name": "x", "agent": "backend-1", "status": "completed"}
        ],
    }
    s = ORCH_MOD.ExecutionState.from_dict(data)
    assert s.project == "ScorePocket"
    assert s.status == "development"
    assert s.tasks[0]["status"] == "completed"
    assert s.to_dict() == data


def test_state_from_dict_missing_fields_defaults():
    s = ORCH_MOD.ExecutionState.from_dict({"project": "S"})
    assert s.status == "development"
    assert s.lifecycle == "development"
    assert s.tasks == []


def test_state_from_dict_unknown_keys_ignored():
    s = ORCH_MOD.ExecutionState.from_dict(
        {"project": "S", "future_field": 1, "tasks": [{"id": "T1"}]}
    )
    assert s.project == "S"
    assert len(s.tasks) == 1


def test_state_save_creates_file(tmp_path):
    p = tmp_path / "execution_state.json"
    s = ORCH_MOD.ExecutionState(project="S", tasks=[{"id": "T1", "status": "pending"}])
    s.save(p)
    assert p.is_file()


def test_state_save_creates_parent_dirs(tmp_path):
    p = tmp_path / "a" / "b" / "execution_state.json"
    ORCH_MOD.ExecutionState(project="S").save(p)
    assert p.is_file()


def test_state_load_roundtrip(tmp_path):
    p = tmp_path / "execution_state.json"
    s = ORCH_MOD.ExecutionState(
        project="ScorePocket",
        status="delivered",
        lifecycle="delivered",
        started_at="ts",
        tasks=[{"id": "T001", "name": "n", "agent": "a", "status": "completed"}],
    )
    s.save(p)
    loaded = ORCH_MOD.ExecutionState.load(p)
    assert loaded is not None
    assert loaded.project == "ScorePocket"
    assert loaded.status in ("user_acceptance", "delivered")
    assert loaded.lifecycle in ("user_acceptance", "delivered")
    assert loaded.tasks == s.tasks


def test_state_load_missing_returns_none(tmp_path):
    assert ORCH_MOD.ExecutionState.load(tmp_path / "nope.json") is None


def test_state_load_corrupt_raises(tmp_path):
    p = tmp_path / "execution_state.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ORCH_MOD.ExecutionStateError):
        ORCH_MOD.ExecutionState.load(p)


def test_state_save_utf8_chinese_readable(tmp_path):
    p = tmp_path / "execution_state.json"
    s = ORCH_MOD.ExecutionState(
        project="台球计分", tasks=[{"id": "T001", "name": "数据库 Schema 设计"}]
    )
    s.save(p)
    raw = p.read_text(encoding="utf-8")
    assert "台球计分" in raw  # ensure_ascii=False: 中文可读


# ================================================================== 3. 定位与 plan 加载 (验收 A)


def test_locate_project_by_slug(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    pdir, slug = orch._locate_project("scorepocket")
    assert slug == "scorepocket"
    assert pdir == tmp_path / "projects" / "scorepocket"


def test_locate_project_by_name(tmp_path):
    """按 product name 定位 (macOS 大小写不敏感 FS: 用非 slug 中文名避免歧义)。"""
    _make_project(tmp_path, name="台球计分APP")
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    pdir, slug = orch._locate_project("台球计分APP")
    assert slug == "scorepocket"
    assert (pdir / "execution_plan.json").is_file()


def test_locate_project_missing_raises(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    with pytest.raises(ORCH_MOD.ProjectNotFoundError):
        orch._locate_project("ghost")


def test_locate_project_missing_projects_root_raises(tmp_path):
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path / "empty")
    with pytest.raises(ORCH_MOD.ProjectNotFoundError):
        orch._locate_project("scorepocket")


def test_load_plan_reads_tasks(tmp_path):
    pdir = _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    plan = orch._load_plan(pdir)
    assert plan["count"] == 3
    assert plan["tasks"][0]["id"] == "T001"
    assert plan["tasks"][1]["agent"] == "flutter-dev"


def test_load_plan_missing_raises(tmp_path):
    pdir = _make_project(tmp_path, plan_json=False)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    with pytest.raises(ORCH_MOD.PlanNotFoundError):
        orch._load_plan(pdir)


def test_load_plan_empty_tasks_raises(tmp_path):
    pdir = _make_project(tmp_path, tasks=[])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    with pytest.raises(ORCH_MOD.PlanNotFoundError):
        orch._load_plan(pdir)


# ================================================================== 4. execute_project 快乐路径 (验收 A/B/E)


def test_execute_project_creates_state_file(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state_file = tmp_path / "projects" / "scorepocket" / "execution_state.json"
    assert state_file.is_file()


def test_execute_project_initializes_all_pending(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn(calls))
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert [t["status"] for t in state.tasks] == ["completed"] * 3


def test_execute_project_order_follows_plan(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn(calls))
    assert [t["id"] for t in calls] == ["T001", "T002", "T003"]


def test_execute_project_passes_project_dir_and_workspace(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    seen: list = []

    def fn(task, project_dir, workspace):
        seen.append((str(project_dir), str(workspace)))
        return {"success": True}

    orch.execute_project("scorepocket", execute_fn=fn)
    expected_dir = str(tmp_path / "projects" / "scorepocket")
    assert all(d == expected_dir for d, _ in seen)
    assert all(w == str(tmp_path) for _, w in seen)


def test_execute_project_completed_count(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.completed_tasks == 3
    assert result.failed_tasks == 0


def test_execute_project_artifacts_collected(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.artifacts == ["art-T001", "art-T002", "art-T003"]


def test_execute_project_cost_aggregated(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.cost == "0.01 · 0.01 · 0.01"


def test_execute_project_errors_empty_on_success(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.errors == []


def test_execute_project_result_status_delivered(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.status in ("user_acceptance", "delivered")


def test_execute_project_started_at_set(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None and state.started_at


def test_execute_project_duration_non_negative(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert result.duration >= 0.0


# ================================================================== 5. Task Queue 状态转换 (验收 B)


def test_queue_pending_to_running_persisted(tmp_path):
    """execute_fn 读 state 文件: 首任务执行期间状态为 running, 其余 pending。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    snapshots: list[list[str]] = []

    def fn(task, project_dir, workspace):
        state = ORCH_MOD.ExecutionState.load(Path(project_dir) / "execution_state.json")
        snapshots.append([t["status"] for t in state.tasks])
        return {"success": True}

    orch.execute_project("scorepocket", execute_fn=fn)
    assert snapshots[0] == ["running", "pending", "pending"]
    assert snapshots[1] == ["completed", "running", "pending"]
    assert snapshots[2] == ["completed", "completed", "running"]


def test_queue_running_to_completed_final_state(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert all(t["status"] == "completed" for t in state.tasks)


def test_queue_artifacts_persisted_per_task(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert [t["artifact"] for t in state.tasks] == [
        "art-T001", "art-T002", "art-T003",
    ]


def test_queue_agents_preserved(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert [t["agent"] for t in state.tasks] == [
        "backend-1", "flutter-dev", "backend-1",
    ]


def test_queue_retry_count_zero_on_success(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert all(t["retry_count"] == 0 for t in state.tasks)


def test_queue_task_ids_names_preserved(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[0]["id"] == "T001"
    assert state.tasks[0]["name"] == "数据库 Schema 设计"


def test_queue_error_none_on_success(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert all(t["error"] is None for t in state.tasks)


# ================================================================== 6. Lifecycle 推进 (验收 E)


def test_lifecycle_development_during_execution(tmp_path):
    """执行期间 project.json status = development (EXECUTION_READY → DEVELOPMENT)。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    seen: list[str] = []

    def fn(task, project_dir, workspace):
        data = json.loads((Path(project_dir) / "project.json").read_text(encoding="utf-8"))
        seen.append(data["status"])
        return {"success": True}

    orch.execute_project("scorepocket", execute_fn=fn)
    assert seen == ["development"] * 3


def test_lifecycle_project_json_delivered_final(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    data = json.loads(
        (tmp_path / "projects" / "scorepocket" / "project.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["status"] in ("user_acceptance", "delivered")


def test_lifecycle_product_json_delivered_final(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    data = json.loads(
        (tmp_path / "projects" / "scorepocket" / "product.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["status"] in ("user_acceptance", "delivered")


def test_lifecycle_preserves_project_json_fields(tmp_path):
    pdir = _make_project(tmp_path)
    (pdir / "project.json").write_text(
        json.dumps({"id": "p1", "repo_path": "/tmp/repo", "status": "execution_ready"}),
        encoding="utf-8",
    )
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["id"] == "p1"
    assert data["repo_path"] == "/tmp/repo"
    assert data["status"] in ("user_acceptance", "delivered")


def test_lifecycle_project_json_created_if_missing(tmp_path):
    pdir = _make_project(tmp_path, project_json=False)
    assert not (pdir / "project.json").exists()
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    data = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    assert data["status"] in ("user_acceptance", "delivered")
    assert data["name"] == "scorepocket"


def test_lifecycle_state_status_delivered(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert state.status in ("user_acceptance", "delivered")
    assert state.lifecycle in ("user_acceptance", "delivered")


def test_lifecycle_transition_sequence(tmp_path):
    """完整推进序列: EXECUTION_READY → DEVELOPMENT → TESTING → DELIVERED。"""
    _make_project(tmp_path)
    orch = _RecordingOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert orch.lifecycle_calls == ["development", "testing", "validation_pass", "user_acceptance"]


# ================================================================== 7. 失败处理 (验收 G)


def test_failure_retries_once(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    result = orch.execute_project("scorepocket", execute_fn=_make_fail_fn(calls))
    assert len(calls) == 2  # 首次 + 重试 1 次
    assert result.failed_tasks == 1
    assert result.completed_tasks == 0


def test_failure_no_infinite_retry(tmp_path):
    """默认 max_retry=1: 每任务至多 2 次调用, 不无限重试。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn(calls))
    assert len(calls) == 6  # 3 任务 × 2 次


def test_failure_status_failed_in_state(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert state.tasks[0]["status"] == "failed"


def test_failure_error_recorded(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn(error="磁盘写失败"))
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert "磁盘写失败" in state.tasks[0]["error"]


def test_failure_retry_count_recorded(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[0]["retry_count"] == 1


def test_failure_continues_next_tasks(tmp_path):
    """失败不阻塞: 记录 failed 后继续下一任务 (设计 §7 第一版)。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn(calls))
    assert [t["id"] for t in calls] == ["T001", "T001", "T002", "T002", "T003", "T003"]
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert [t["status"] for t in state.tasks] == ["failed"] * 3


def test_failure_result_status_failed(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    assert result.status == "failed"


def test_failure_failed_tasks_count(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    assert result.failed_tasks == 3
    assert result.completed_tasks == 0


def test_failure_errors_list_populated(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project(
        "scorepocket", execute_fn=_make_fail_fn(error="boom")
    )
    assert len(result.errors) == 3
    assert all("boom" in e for e in result.errors)


def test_failure_lifecycle_stays_development(tmp_path):
    """设计 §6: 有 failed → 保持 DEVELOPMENT (可恢复), 不推进 TESTING。"""
    _make_project(tmp_path)
    orch = _RecordingOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    assert orch.lifecycle_calls == ["development"]
    data = json.loads(
        (tmp_path / "projects" / "scorepocket" / "project.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["status"] == "development"


def test_failure_retry_succeeds_marks_completed(tmp_path):
    """flaky: 首次失败 → 重试成功 → completed, retry_count=1。"""
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    result = orch.execute_project(
        "scorepocket", execute_fn=_make_flaky_fn(fail_until=1)
    )
    assert result.status in ("user_acceptance", "delivered")
    assert result.completed_tasks == 1
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[0]["status"] == "completed"
    assert state.tasks[0]["retry_count"] == 1


def test_failure_max_retry_zero_no_retry(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn(calls), max_retry=0)
    assert len(calls) == 1


def test_failure_max_retry_two_retries_twice(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn(calls), max_retry=2)
    assert len(calls) == 3
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[0]["retry_count"] == 2


def test_failure_execute_fn_raising_treated_as_failure(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)

    def boom(task, project_dir, workspace):
        raise RuntimeError("runtime exploded")

    result = orch.execute_project("scorepocket", execute_fn=boom)
    assert result.failed_tasks == 1
    assert "runtime exploded" in result.errors[0]


def test_failure_execute_fn_none_treated_as_failure(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)

    def none_fn(task, project_dir, workspace):
        return None

    result = orch.execute_project("scorepocket", execute_fn=none_fn)
    assert result.failed_tasks == 1
    assert "任务执行失败" in result.errors[0]


def test_failure_execute_fn_non_dict_treated_as_failure(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)

    def str_fn(task, project_dir, workspace):
        return "not-a-dict"

    result = orch.execute_project("scorepocket", execute_fn=str_fn)
    assert result.failed_tasks == 1
    assert "非 dict" in result.errors[0]


# ================================================================== 8. get_progress (验收 F)


def test_progress_not_started_when_no_state(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    p = orch.get_progress("scorepocket")
    assert p["status"] == "not_started"
    assert p["tasks_total"] == 0
    assert p["completed"] == 0 and p["failed"] == 0


def test_progress_after_full_run(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    p = orch.get_progress("scorepocket")
    assert p["status"] in ("user_acceptance", "delivered")
    assert p["lifecycle"] in ("user_acceptance", "delivered")
    assert p["tasks_total"] == 3
    assert p["completed"] == 3
    assert p["pending"] == 0 and p["running"] == 0 and p["failed"] == 0


def test_progress_agents_unique_sorted(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    p = orch.get_progress("scorepocket")
    assert p["agents"] == ["backend-1", "flutter-dev"]


def test_progress_after_failure_counts_failed(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    p = orch.get_progress("scorepocket")
    assert p["failed"] == 3
    assert p["completed"] == 0
    assert p["status"] == "development"  # 保持 DEVELOPMENT, 可恢复


def test_progress_midrun_running_count(tmp_path):
    """执行中查询: running=1, pending=剩余。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    seen: list[dict] = []

    def fn(task, project_dir, workspace):
        seen.append(orch.get_progress("scorepocket"))
        return {"success": True}

    orch.execute_project("scorepocket", execute_fn=fn)
    assert seen[0]["running"] == 1
    assert seen[0]["pending"] == 2
    assert seen[0]["completed"] == 0


def test_progress_missing_project_raises(tmp_path):
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    with pytest.raises(ORCH_MOD.ProjectNotFoundError):
        orch.get_progress("ghost")


def test_progress_returns_project_and_lifecycle(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    p = orch.get_progress("scorepocket")
    assert p["project"] == "scorepocket"
    assert p["lifecycle"] in ("user_acceptance", "delivered")


def test_progress_readonly_no_execution(tmp_path):
    """get_progress 纯只读: 不产生 state 文件、不执行任务。"""
    pdir = _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    before = sorted(p.name for p in pdir.iterdir())
    orch.get_progress("scorepocket")
    after = sorted(p.name for p in pdir.iterdir())
    assert before == after
    assert not (pdir / "execution_state.json").exists()


# ================================================================== 9. resume (验收 G)

def test_resume_without_state_raises(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    with pytest.raises(ORCH_MOD.ExecutionStateError):
        orch.resume("scorepocket", execute_fn=_make_ok_fn())


def test_resume_skips_completed_tasks(tmp_path):
    """全部完成后再 resume → 不重跑任何任务。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    calls: list = []
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn(calls))
    assert len(calls) == 3
    calls.clear()
    result = orch.resume("scorepocket", execute_fn=_make_ok_fn(calls))
    assert calls == []
    assert result.status in ("user_acceptance", "delivered")
    assert result.completed_tasks == 3


def test_resume_reruns_failed_tasks(tmp_path):
    """失败后 resume: 仅重跑 failed 任务 (completed 跳过)。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    calls: list = []
    result = orch.resume("scorepocket", execute_fn=_make_ok_fn(calls))
    assert [t["id"] for t in calls] == ["T001", "T002", "T003"]
    assert result.status in ("user_acceptance", "delivered")
    assert result.completed_tasks == 3
    assert result.failed_tasks == 0


def test_resume_partial_failure_only_reruns_failed(tmp_path):
    """部分失败: 成功任务保留, resume 只重跑失败的那个。"""
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    order = {"n": 0}

    def flaky(task, project_dir, workspace):
        order["n"] += 1
        if task["id"] == "T002":
            return {"success": False, "error": "frontend broke"}
        return {"success": True, "artifact": f"art-{task['id']}"}

    orch.execute_project("scorepocket", execute_fn=flaky)
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[1]["status"] == "failed"
    calls: list = []
    result = orch.resume("scorepocket", execute_fn=_make_ok_fn(calls))
    assert [t["id"] for t in calls] == ["T002"]
    assert result.status in ("user_acceptance", "delivered")
    assert result.completed_tasks == 3


def test_resume_resets_failed_retry_count(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    orch.resume("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state.tasks[0]["status"] == "completed"
    assert state.tasks[0]["retry_count"] == 0


def test_resume_failure_again_stays_failed(tmp_path):
    _make_project(tmp_path, tasks=[PLAN_TASKS[0]])
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    result = orch.resume("scorepocket", execute_fn=_make_fail_fn())
    assert result.status == "failed"
    assert result.failed_tasks == 1


def test_resume_state_file_updated(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    orch.resume("scorepocket", execute_fn=_make_ok_fn())
    state = ORCH_MOD.ExecutionState.load(
        tmp_path / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert state.status in ("user_acceptance", "delivered")
    assert all(t["status"] == "completed" for t in state.tasks)


def test_needs_resume_true_after_failure(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_fail_fn())
    assert orch.needs_resume("scorepocket") is True


def test_needs_resume_false_fresh(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    assert orch.needs_resume("scorepocket") is False


def test_needs_resume_false_after_full_success(tmp_path):
    _make_project(tmp_path)
    orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
    orch.execute_project("scorepocket", execute_fn=_make_ok_fn())
    assert orch.needs_resume("scorepocket") is False


# ================================================================== 10. 注册 / 意图 / 路由 (验收 D 前置)


def test_registry_has_execute_project():
    action = ACTIONS_MOD.build_default_actions().get("execute_project")
    assert action is not None
    assert action.handler is ACTIONS_MOD.execute_project


def test_execute_project_metadata_sensitive():
    action = ACTIONS_MOD.build_default_actions().get("execute_project")
    assert action.metadata.get("sensitive") is True
    assert action.metadata.get("category") == "execution"
    assert action.permission == "project"


def test_registry_has_project_progress():
    action = ACTIONS_MOD.build_default_actions().get("project_progress")
    assert action is not None
    assert action.handler is ACTIONS_MOD.project_progress


def test_project_progress_metadata_not_sensitive():
    action = ACTIONS_MOD.build_default_actions().get("project_progress")
    assert action.metadata.get("sensitive") is False
    assert action.metadata.get("category") == "execution"
    assert action.permission == "user"


def test_router_maps_execute_project():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["execute_project"] == "execute_project"
    assert routes["project_progress"] == "project_progress"


def test_router_resolves_execute_project():
    reg = ACTIONS_MOD.build_default_actions()
    intent = INTENT_MOD.IntentObject(intent_type="execute_project", raw="开始开发")
    action = ROUTER_MOD.IntentRouter().route(intent, reg)
    assert action.name == "execute_project"


def test_router_resolves_project_progress():
    reg = ACTIONS_MOD.build_default_actions()
    intent = INTENT_MOD.IntentObject(intent_type="project_progress", raw="项目进度")
    action = ROUTER_MOD.IntentRouter().route(intent, reg)
    assert action.name == "project_progress"


@pytest.mark.parametrize("text", ["开始开发", "开始执行", "执行项目", "开始开发这个产品"])
def test_intent_execute_project_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_EXECUTE_PROJECT
    assert intent.raw == text


@pytest.mark.parametrize("text", ["项目进度", "进度如何", "执行到哪了"])
def test_intent_project_progress_keywords(text):
    intent = INTENT_MOD.KeywordIntentParser().parse(text)
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_PROJECT_PROGRESS
    assert intent.raw == text


def test_intent_execute_project_priority_over_product():
    """\"开始开发这个产品\" → execute_project (不被 create_product \"产品\" 抢)。"""
    intent = INTENT_MOD.KeywordIntentParser().parse("开始开发这个产品")
    assert intent.intent_type == INTENT_MOD.INTENT_EXECUTE_PROJECT


def test_intent_execute_project_constants():
    assert INTENT_MOD.INTENT_EXECUTE_PROJECT == "execute_project"
    assert INTENT_MOD.INTENT_PROJECT_PROGRESS == "project_progress"


# ================================================================== 11. execute_project Action (验收 D)


def test_action_execute_project_no_product_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.execute_project(_exec_ctx(root))
    assert result.ok is False
    assert "未找到产品定义" in result.message


def test_action_execute_project_delivered_refused(tmp_path):
    _make_project(tmp_path, status="delivered")
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok is False
    assert "delivered" in result.message


@pytest.mark.parametrize("status", ["testing", "idea", "product_defined", "engineering_ready"])
def test_action_execute_project_non_executable_status_refused(tmp_path, status):
    """Lifecycle 门: 仅 EXECUTION_READY/DEVELOPMENT 可执行。"""
    _make_project(tmp_path, status=status)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok is False
    assert "不允许执行" in result.error


def test_action_execute_project_runs_via_bridge(fake_exec, tmp_path):
    """D: 经真实桥接链 (orchestrator → execute_task → cmd_exec_run 桩) 全执行。"""
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok, result.message
    assert result.data["completed_tasks"] == 3
    assert result.data["status"] in ("user_acceptance", "delivered")
    assert len(fake_exec.calls) == 3


def test_action_execute_project_message_completed(fake_exec, tmp_path):
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert "项目执行完成: scorepocket — 3 任务完成" in result.message


def test_action_execute_project_bridge_passes_task_fields(fake_exec, tmp_path):
    """桥接参数: objective=任务名 / task_id / agent_id 正确透传 (验收 H)。"""
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    ACTIONS_MOD.execute_project(ctx)
    root, args = fake_exec.calls[0]
    assert args.task == "T001"
    assert "数据库 Schema 设计" in args.objective
    assert args.agent == "backend-1"
    root2, args2 = fake_exec.calls[1]
    assert args2.task == "T002"
    assert args2.agent == "flutter-dev"


def test_action_execute_project_failure_message(fake_exec, tmp_path):
    fake_exec.ok = False
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok is False
    assert "任务失败" in result.message
    assert result.data["failed_tasks"] == 3


def test_action_execute_project_missing_plan_error(tmp_path):
    _make_project(tmp_path, plan_json=False)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok is False
    assert "execution_plan.json" in result.message


def test_action_execute_project_resume_path(fake_exec, tmp_path):
    """失败后再次 \"开始开发\" → needs_resume → resume (不重跑已完成)。"""
    fake_exec.ok = False
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    first = ACTIONS_MOD.execute_project(ctx)
    assert first.ok is False
    assert len(fake_exec.calls) == 6  # 3 任务 × (1 次 + 1 次重试)
    fake_exec.ok = True
    second = ACTIONS_MOD.execute_project(ctx)
    assert second.ok, second.message
    assert len(fake_exec.calls) == 9  # resume 重跑 3 个 failed (各 1 次)
    assert second.data["status"] in ("user_acceptance", "delivered")


def test_action_execute_project_scan_fallback_lookup(fake_exec, tmp_path):
    """无 current_project → 扫描 projects/*/product.json 兜底。"""
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)  # 不设 current_project
    result = ACTIONS_MOD.execute_project(ctx)
    assert result.ok, result.message


# ================================================================== 12. project_progress Action (验收 F)


def test_action_progress_no_product_error(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.project_progress(_exec_ctx(root))
    assert result.ok is False
    assert "未找到产品定义" in result.message


def test_action_progress_not_started(tmp_path):
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    result = ACTIONS_MOD.project_progress(ctx)
    assert result.ok
    assert result.data["status"] == "not_started"
    assert "尚未开始执行" in result.message


def test_action_progress_after_run(fake_exec, tmp_path):
    _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    ACTIONS_MOD.execute_project(ctx)
    result = ACTIONS_MOD.project_progress(ctx)
    assert result.ok
    assert result.data["completed"] == 3
    assert result.data["tasks_total"] == 3
    assert result.data["agents"] == ["backend-1", "flutter-dev"]
    assert "3/3 完成" in result.message


def test_action_progress_readonly_does_not_execute(tmp_path):
    """进度查询零副作用: 不产生 state, 不调 Runtime。"""
    pdir = _make_project(tmp_path)
    ctx = _exec_ctx(tmp_path)
    ctx.session.current_project = "scorepocket"
    ACTIONS_MOD.project_progress(ctx)
    assert not (pdir / "execution_state.json").exists()


# ================================================================== 13. 确认门 + Session (验收 D)

def test_session_gate_includes_execute_project():
    sess = SESS_MOD.InteractiveSession()
    assert isinstance(sess.confirmation_gate, CONF_MOD.ConfirmationGate)
    assert "execute_project" in sess.confirmation_gate.sensitive_actions


def test_session_gate_excludes_project_progress():
    sess = SESS_MOD.InteractiveSession()
    assert "project_progress" not in sess.confirmation_gate.sensitive_actions


def test_gate_class_default_untouched():
    """回归护栏: ConfirmationGate 类默认敏感集合保持基线 {create_project, run_task}。"""
    assert CONF_MOD.ConfirmationGate().sensitive_actions == {
        "create_project",
        "run_task",
    }


def test_gate_execute_project_rejected(capsys):
    gate = CONF_MOD.ConfirmationGate()
    gate.sensitive_actions = set(gate.sensitive_actions) | {"execute_project"}
    intent = INTENT_MOD.IntentObject(intent_type="execute_project", raw="开始开发")
    assert gate.confirm("execute_project", intent, confirm_fn=lambda: "n") is False
    assert "将执行: execute_project" in capsys.readouterr().out


def test_gate_execute_project_approved(capsys):
    gate = CONF_MOD.ConfirmationGate()
    gate.sensitive_actions = set(gate.sensitive_actions) | {"execute_project"}
    intent = INTENT_MOD.IntentObject(intent_type="execute_project", raw="开始开发")
    assert gate.confirm("execute_project", intent, confirm_fn=lambda: "y") is True


def test_session_dispatch_execute_project_rejected(fake_exec, capsys, tmp_path):
    """端到端: 确认拒绝 → \"已取消\", 不产生 execution_state.json。"""
    _make_project(tmp_path)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(tmp_path)),
        confirmation_gate=_SpyGate(decision=False),
    )
    sess._dispatch("开始开发")
    out = capsys.readouterr().out
    assert "已取消" in out
    assert not (tmp_path / "projects" / "scorepocket" / "execution_state.json").exists()


def test_session_dispatch_execute_project_approved(fake_exec, capsys, tmp_path):
    """端到端: 确认通过 → 执行 → delivered 消息 + state 文件。"""
    _make_project(tmp_path)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(tmp_path)),
        confirmation_gate=_SpyGate(decision=True),
    )
    sess._dispatch("开始开发")
    out = capsys.readouterr().out
    assert "项目执行完成" in out
    assert (tmp_path / "projects" / "scorepocket" / "execution_state.json").is_file()
    project = json.loads(
        (tmp_path / "projects" / "scorepocket" / "project.json").read_text(
            encoding="utf-8"
        )
    )
    assert project["status"] in ("user_acceptance", "delivered")


def test_session_gate_receives_execute_project_intent(fake_exec, capsys, tmp_path):
    _make_project(tmp_path)
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(tmp_path)),
        confirmation_gate=spy,
    )
    sess._dispatch("开始开发")
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "execute_project"


def test_session_dispatch_project_progress(fake_exec, capsys, tmp_path):
    """\"项目进度\" → 非敏感查询 → 进度消息 (无确认)。"""
    _make_project(tmp_path)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(tmp_path)),
        confirmation_gate=_SpyGate(decision=True),
    )
    sess._dispatch("项目进度")
    out = capsys.readouterr().out
    assert "尚未开始执行" in out


def test_session_full_chain_start_development(fake_exec, capsys, tmp_path):
    """全链路: 准备工程 → \"开始开发\" → 确认 → 执行 → DELIVERED。"""
    _make_project(tmp_path)
    spy = _SpyGate(decision=True)
    sess = SESS_MOD.InteractiveSession(
        context_manager=CTX_MOD.ContextManager(workspace=str(tmp_path)),
        confirmation_gate=spy,
    )
    sess._dispatch("准备开发")  # 幂等: prepare_project 重写 4 资产 (fixture 已含)
    sess._dispatch("开始开发")
    out = capsys.readouterr().out
    assert "Project Ready For Engineering." in out
    assert "项目执行完成" in out


# ================================================================== 14. 完整 Demo Flow (验收 E/D)


def test_demo_full_pipeline_execute(fake_org, fake_exec, tmp_path):
    """create_product → prepare_project → execute_project → DELIVERED (全真实 Action)。"""
    root = tmp_path / "ws"
    root.mkdir()
    product = PROD_MOD.ProductIntent(
        name="ScorePocket",
        problem="台球比赛计分麻烦",
        user="台球爱好者",
        core_features=["计分", "比赛记录", "排行榜"],
        raw="我想开发一个台球计分APP",
    )
    ctx = _exec_ctx(root)
    ctx.session.product_intent = product
    created = ACTIONS_MOD.create_product(ctx)
    assert created.ok, created.message
    prepared = ACTIONS_MOD.prepare_project(ctx)
    assert prepared.ok, prepared.message
    executed = ACTIONS_MOD.execute_project(ctx)
    assert executed.ok, executed.message
    assert executed.data["status"] in ("user_acceptance", "delivered")
    assert executed.data["completed_tasks"] == 6  # S10-055 功能级任务 (3 Epic × 2)


def test_demo_project_json_delivered(fake_org, fake_exec, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分"]
    )
    ACTIONS_MOD.create_product(ctx)
    ACTIONS_MOD.prepare_project(ctx)
    ACTIONS_MOD.execute_project(ctx)
    project = json.loads(
        (root / "projects" / "scorepocket" / "project.json").read_text(
            encoding="utf-8"
        )
    )
    assert project["status"] in ("user_acceptance", "delivered")


def test_demo_progress_after_execution(fake_org, fake_exec, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分", "排行榜"]
    )
    ACTIONS_MOD.create_product(ctx)
    ACTIONS_MOD.prepare_project(ctx)
    ACTIONS_MOD.execute_project(ctx)
    progress = ACTIONS_MOD.project_progress(ctx)
    assert progress.data["completed"] == progress.data["tasks_total"]
    assert progress.data["completed"] == 4  # S10-055 功能级任务 (2 feature × 2)
    assert progress.data["status"] in ("user_acceptance", "delivered")
    assert "flutter-dev" in progress.data["agents"]


def test_demo_execution_state_file_exists(fake_org, fake_exec, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分"]
    )
    ACTIONS_MOD.create_product(ctx)
    ACTIONS_MOD.prepare_project(ctx)
    ACTIONS_MOD.execute_project(ctx)
    state = ORCH_MOD.ExecutionState.load(
        root / "projects" / "scorepocket" / "execution_state.json"
    )
    assert state is not None
    assert state.status in ("user_acceptance", "delivered")
    assert len(state.tasks) == 2  # S10-055 功能级任务 (记录比分 + 界面交互)


def test_demo_reject_after_delivered(fake_org, fake_exec, tmp_path):
    """已交付 → 再次 \"开始开发\" → 明确拒绝 (不重跑)。"""
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分"]
    )
    ACTIONS_MOD.create_product(ctx)
    ACTIONS_MOD.prepare_project(ctx)
    ACTIONS_MOD.execute_project(ctx)
    again = ACTIONS_MOD.execute_project(ctx)
    assert again.ok is False
    assert "不允许执行" in again.error


# ================================================================== 15. 回归 (验收 K)


def test_regression_create_product_unchanged(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分"]
    )
    result = ACTIONS_MOD.create_product(ctx)
    assert result.message == "Product Created: ScorePocket — Ready for Engineering."


def test_regression_execute_task_unchanged(fake_exec, tmp_path):
    ctx = _exec_ctx(tmp_path, intent=INTENT_MOD.IntentObject(
        intent_type="run_task", params={"objective": "登录功能", "task_id": "T9"}
    ))
    result = ACTIONS_MOD.execute_task(ctx)
    assert result.ok
    assert result.data["execution"]["agent"] == "backend-1"
    assert len(fake_exec.calls) == 1


def test_regression_prepare_project_unchanged(fake_org, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _exec_ctx(root)
    ctx.session.product_intent = PROD_MOD.ProductIntent(
        name="ScorePocket", problem="p", user="u", core_features=["计分"]
    )
    ACTIONS_MOD.create_product(ctx)
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    assert result.message == "Project Ready For Engineering."
    pdir = root / "projects" / "scorepocket"
    for name in ("PRD.md", "engineering.json", "tasks.json", "execution_plan.json"):
        assert (pdir / name).is_file(), f"缺少资产: {name}"


def test_regression_run_task_intent_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("帮我实现登录功能")
    assert intent.intent_type == INTENT_MOD.INTENT_RUN_TASK
    assert intent.parameters["objective"] == "登录功能"


def test_regression_product_intent_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("我想开发一个台球计分APP")
    assert intent.intent_type == INTENT_MOD.INTENT_CREATE_PRODUCT


def test_regression_prepare_project_intent_unchanged():
    intent = INTENT_MOD.KeywordIntentParser().parse("准备开发")
    assert intent.intent_type == INTENT_MOD.INTENT_PREPARE_PROJECT
