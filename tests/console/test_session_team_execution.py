"""tests/console/test_session_team_execution.py — S10-057 Team Production Validation 集成层。

设计: docs/sprint10/S10-057-team-production-design.md (§P0-P5 + §2 数据资产)
覆盖 (验收 A-J):
A. ConflictResolver: 同文件冲突 → strategy (dependency_delay/task_reorder/
   serial_execution) + conflict_resolution.json
B. TeamExecutionState: team_execution_state.json init/update/get/pause/resume/
   progress/save/load
C. Agent Handoff: architect 完成 → handoff_messages.json
   (requirement/decision/constraints) → backend
D. Workspace Context 注入: 任务执行前上下文 (completed/artifacts/messages/
   decisions) 透传 task["context"]
E. Team Validation: All Complete → QA → pytest → PASS → DELIVERED
   (Repair Loop 保持; DELIVERED 经 accept_project — S10-055 验收门兼容)
F. team_report.md 生成 (team/tasks/agents/artifacts/validation)
G. solo mode 完全兼容
H. 不修改核心/不引入依赖 (测试只 import session 层 + 纯标准库)
I. 新增 >=120 测试全绿 + 全量 pytest 不破坏基线
J. 回归: execute_project/repair_task/accept_project 不受影响

测试装配: tmp_path + fixtures (teams/agents/execution_plan/dependencies/conflicts);
execute_fn 一律 mock (零真实 LLM/网络); Team Validation 命令门经注入 FakeValidator
控制 (validate_command 不跑真实命令 — 除单条真实 pytest 子进程冒烟, 用 sys.executable
确保环境无关)。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

CONF_MOD = importlib.import_module("factory-console.session.conflicts")
MSG_MOD = importlib.import_module("factory-console.session.messages")
ORCH_MOD = importlib.import_module("factory-console.session.orchestrator")
PIPE_MOD = importlib.import_module("factory-console.session.pipeline")
QUAL_MOD = importlib.import_module("factory-console.session.quality")
TEAMS_MOD = importlib.import_module("factory-console.session.teams")
TS_MOD = importlib.import_module("factory-console.session.team_state")
WS_MOD = importlib.import_module("factory-console.session.workspace")

Lifecycle = PIPE_MOD.Lifecycle
ConflictResolver = CONF_MOD.ConflictResolver
HandoffMessage = MSG_MOD.HandoffMessage
HandoffStore = MSG_MOD.HandoffStore
TeamExecutionState = TS_MOD.TeamExecutionState
WorkspaceContext = WS_MOD.WorkspaceContext
ValidationResult = QUAL_MOD.ValidationResult

# ------------------------------------------------------------------ 固定 fixture

#: 团队成员编制 (默认 software-team 5 角色 — 同 S10-056 口径)
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

#: 固定 execution_plan.json 任务 (3 任务: backend/frontend/qa, required_role + files)
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

#: 架构→后端→QA 流水线任务 (依赖 + requirement/constraints — Handoff 输入)
ARCH_PLAN_TASKS: list[dict] = [
    {
        "id": "T001",
        "name": "系统架构设计",
        "type": "architecture",
        "required_role": "architect",
        "files": ["docs/architecture.md"],
    },
    {
        "id": "T002",
        "name": "REST API 实现",
        "type": "backend_api",
        "required_role": "backend",
        "requirement": "Implement REST API per architecture.md",
        "constraints": "遵循架构设计, 使用 Python",
        "files": ["api/main.py"],
    },
    {
        "id": "T003",
        "name": "端到端测试",
        "type": "test",
        "required_role": "qa",
        "requirement": "验证 API 端到端可用",
        "files": ["test/api_test.py"],
    },
]

#: 同文件冲突任务 (T001/T002 共享 src/app.py — ConflictResolver 输入)
CONFLICT_TASKS: list[dict] = [
    {"id": "T001", "name": "模块 A", "type": "backend", "required_role": "backend",
     "files": ["src/app.py"]},
    {"id": "T002", "name": "模块 B", "type": "backend", "required_role": "backend",
     "files": ["src/app.py"]},
    {"id": "T003", "name": "测试", "type": "test", "required_role": "qa",
     "files": ["test/app_test.py"]},
]


# ------------------------------------------------------------------ 工具/夹具

def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_team_assets(root: Path, members: list[dict] | None = None) -> None:
    """工作区 teams.json + agents.json (团队执行共用)。"""
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


def _state_tasks(root: Path, slug: str = "demo") -> list[dict]:
    return (_read_json(root / "projects" / slug / "execution_state.json").get("tasks") or [])


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


def _paths(root: Path) -> dict:
    """团队模式资产路径 (注入显式 tmp 文件 — hermetic, 零 ~/.factory 污染)。"""
    return {
        "teams_file": root / "teams" / "teams.json",
        "agents_file": root / "agents" / "agents.json",
        "dependencies_file": root / "teams" / "task_dependencies.json",
        "conflicts_file": root / "teams" / "conflicts.json",
        "messages_file": root / "teams" / "agent_messages.json",
    }


class FakeValidator:
    """注入 Validator: validate_command 受控 (不跑真实命令); validate 走 mock 语义。"""

    def __init__(self, command_ok: bool = True, command_errors: list | None = None):
        self.command_ok = command_ok
        self.command_errors = list(command_errors or [])
        self.command_calls: list[tuple] = []
        self._real = QUAL_MOD.Validator()

    def validate_command(self, project_dir, command, **kw):
        self.command_calls.append((project_dir, command))
        if self.command_ok:
            return ValidationResult(
                success=True, tests_total=1, tests_passed=1, tests_failed=0
            )
        return ValidationResult(
            success=False,
            tests_total=1,
            tests_passed=0,
            tests_failed=1,
            errors=self.command_errors or ["fake validation failed"],
        )

    def validate(self, task, task_result, **kw):
        return self._real.validate(task, task_result, **kw)

    def save(self, project_dir, slug, result):
        return self._real.save(project_dir, slug, result)


def _run_team(
    root: Path,
    slug: str = "demo",
    tasks: list[dict] | None = None,
    deps: dict | None = None,
    members: list[dict] | None = None,
    write_assets: bool = True,
    execute_fn=None,
    calls: list | None = None,
    validator: Any | None = None,
    **kw,
):
    """一键团队模式执行 (装配资产 + 项目 + 依赖图 → execute_project(mode=team))。"""
    if write_assets:
        _write_team_assets(root, members=members)
    _make_project(root, slug=slug, tasks=tasks)
    if deps:
        _write_json(root / "teams" / "task_dependencies.json", deps)
    orch = ORCH_MOD.ExecutionOrchestrator(root, validator=validator)
    fn = execute_fn if execute_fn is not None else _ok_fn(calls)
    result = orch.execute_project(
        slug,
        mode="team",
        execute_fn=fn,
        **{**_paths(root), **kw},
    )
    return orch, result


# ============================================================ 1. ConflictResolver (验收 A)

class TestConflictResolverStrategies:
    """策略: dependency_delay / task_reorder / serial_execution (验收 A)。"""

    def test_resolve_default_strategy_dependency_delay(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "src/app.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}],
        )
        assert payload["strategy"] == "dependency_delay"
        assert payload["ordered_tasks"] == ["T1", "T2", "T3"]
        assert payload["resolutions"][0]["strategy"] == "dependency_delay"
        assert payload["resolutions"][0]["file"] == "src/app.py"

    def test_resolve_dependency_delay_reorders_when_b_first(self, tmp_path):
        """依赖延迟: task_b 在计划中先于 task_a → 重排为 a 在前 (b 延迟到 a 后)。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "src/app.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T2"}, {"id": "T1"}, {"id": "T3"}],
        )
        assert payload["ordered_tasks"] == ["T1", "T2", "T3"]
        assert payload["ordered_tasks"].index("T1") < payload["ordered_tasks"].index("T2")

    def test_resolve_task_reorder_strategy_label(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "src/app.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T2"}, {"id": "T1"}],
            strategy="task_reorder",
        )
        assert payload["strategy"] == "task_reorder"
        assert payload["resolutions"][0]["strategy"] == "task_reorder"
        assert payload["ordered_tasks"] == ["T1", "T2"]

    def test_resolve_serial_execution_groups(self, tmp_path):
        """同文件串行: serial_groups 含同文件任务组 (按计划顺序)。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "src/app.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T2"}, {"id": "T1"}, {"id": "T3"}],
            strategy="serial_execution",
        )
        assert payload["strategy"] == "serial_execution"
        assert payload["ordered_tasks"] == ["T1", "T2", "T3"]
        assert ["T1", "T2"] in payload["serial_groups"]

    def test_serial_execution_multiple_files_groups(self, tmp_path):
        conflicts = [
            {"file": "a.py", "task_a": "T1", "task_b": "T2"},
            {"file": "b.py", "task_a": "T2", "task_b": "T3"},
        ]
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(conflicts, [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}],
                                   strategy="serial_execution")
        groups = payload["serial_groups"]
        assert ["T1", "T2"] in groups
        assert ["T2", "T3"] in groups

    def test_resolve_per_file_strategy_dict(self, tmp_path):
        """strategy dict: 按文件覆盖策略 (未列出文件 → 缺省)。"""
        conflicts = [
            {"file": "a.py", "task_a": "T1", "task_b": "T2"},
            {"file": "b.py", "task_a": "T2", "task_b": "T3"},
        ]
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            conflicts, [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}],
            strategy={"a.py": "serial_execution"},
        )
        by_file = {r["file"]: r["strategy"] for r in payload["resolutions"]}
        assert by_file["a.py"] == "serial_execution"
        assert by_file["b.py"] == "dependency_delay"

    def test_resolve_unknown_strategy_falls_back(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T1"}, {"id": "T2"}],
            strategy="merge_magic",
        )
        assert payload["strategy"] == "dependency_delay"
        assert payload["resolutions"][0]["strategy"] == "dependency_delay"

    def test_resolve_no_conflicts_original_order(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve([], [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}])
        assert payload["resolutions"] == []
        assert payload["ordered_tasks"] == ["T1", "T2", "T3"]
        assert payload["serial_groups"] == []

    def test_resolve_empty_plan(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve([{"file": "a.py", "task_a": "T1", "task_b": "T2"}], [])
        assert payload["ordered_tasks"] == []
        assert len(payload["resolutions"]) == 1  # 记录保留, 排序不适用

    def test_resolve_unknown_task_ids_ignored_in_order(self, tmp_path):
        """冲突引用计划外任务 → 记录保留, 排序不受影响。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "a.py", "task_a": "ghost", "task_b": "T2"}],
            [{"id": "T1"}, {"id": "T2"}],
        )
        assert len(payload["resolutions"]) == 1
        assert payload["ordered_tasks"] == ["T1", "T2"]

    def test_resolve_dedupe_conflicts(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [
                {"file": "a.py", "task_a": "T1", "task_b": "T2"},
                {"file": "a.py", "task_a": "T1", "task_b": "T2"},
            ],
            [{"id": "T1"}, {"id": "T2"}],
        )
        assert len(payload["resolutions"]) == 1

    def test_resolve_ignores_empty_conflict_dicts(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve([{}, None, {"file": "a.py", "task_a": "T1", "task_b": "T2"}],
                                   [{"id": "T1"}, {"id": "T2"}])
        assert len(payload["resolutions"]) == 1

    def test_resolve_keeps_dependency_order(self, tmp_path):
        """重排不破坏既有依赖顺序 (无冲突的依赖任务保持相对顺序)。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "a.py", "task_a": "T2", "task_b": "T4"}],
            [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}, {"id": "T4"}],
        )
        order = payload["ordered_tasks"]
        assert order.index("T1") < order.index("T2") < order.index("T3") < order.index("T4")

    def test_resolve_chain_conflicts_no_cycle_crash(self, tmp_path):
        """链式冲突 (T1→T2, T2→T3) → 稳定排序, 不抛。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [
                {"file": "a.py", "task_a": "T1", "task_b": "T2"},
                {"file": "b.py", "task_a": "T2", "task_b": "T3"},
            ],
            [{"id": "T1"}, {"id": "T2"}, {"id": "T3"}],
        )
        assert payload["ordered_tasks"] == ["T1", "T2", "T3"]

    def test_resolve_conflict_record_dict_input(self, tmp_path):
        """ConflictRecord.to_dict() 兼容输入 (验收 A)。"""
        record = CONF_MOD.ConflictRecord(task_a="T1", task_b="T2", file="src/app.py")
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve([record.to_dict()], [{"id": "T2"}, {"id": "T1"}])
        assert payload["ordered_tasks"] == ["T1", "T2"]
        assert payload["resolutions"][0]["task_a"] == "T1"
        assert payload["resolutions"][0]["strategy"] == "dependency_delay"

    def test_resolve_writes_resolution_file(self, tmp_path):
        res_file = tmp_path / "conflict_resolution.json"
        resolver = ConflictResolver(resolution_file=res_file)
        resolver.resolve([{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
                         [{"id": "T1"}, {"id": "T2"}])
        assert res_file.is_file()
        data = _read_json(res_file)
        assert data["strategy"] == "dependency_delay"
        assert data["resolutions"][0]["task_a"] == "T1"
        assert data["ordered_tasks"] == ["T1", "T2"]

    def test_save_load_roundtrip(self, tmp_path):
        res_file = tmp_path / "conflict_resolution.json"
        resolver = ConflictResolver(resolution_file=res_file)
        resolver.resolve([{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
                         [{"id": "T2"}, {"id": "T1"}], strategy="serial_execution")
        loaded = ConflictResolver(resolution_file=res_file)
        assert loaded.list() == resolver.list()
        assert loaded.ordered_tasks() == ["T1", "T2"]
        assert loaded.serial_groups() == [["T1", "T2"]]

    def test_load_missing_file_empty(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "nope.json")
        assert resolver.list() == []
        assert resolver.ordered_tasks() == []
        assert resolver.serial_groups() == []

    def test_load_corrupt_file_empty(self, tmp_path):
        res_file = tmp_path / "conflict_resolution.json"
        res_file.write_text("{corrupt", encoding="utf-8")
        resolver = ConflictResolver(resolution_file=res_file)
        assert resolver.list() == []

    def test_save_creates_parent_dirs(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "a" / "b" / "conflict_resolution.json")
        resolver.resolve([], [{"id": "T1"}])
        assert (tmp_path / "a" / "b" / "conflict_resolution.json").is_file()

    def test_strategy_constants(self):
        assert ConflictResolver.STRATEGY_DEPENDENCY_DELAY == "dependency_delay"
        assert ConflictResolver.STRATEGY_TASK_REORDER == "task_reorder"
        assert ConflictResolver.STRATEGY_SERIAL_EXECUTION == "serial_execution"
        assert ConflictResolver.DEFAULT_STRATEGY == "dependency_delay"

    def test_detect_and_resolve_same_file_conflict(self, tmp_path):
        """计划级预检测: 同文件任务 → 冲突被检测并解决。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.detect_and_resolve(
            [
                {"id": "T1", "files": ["src/app.py"]},
                {"id": "T2", "files": ["src/app.py"]},
                {"id": "T3", "files": ["test/x.py"]},
            ]
        )
        assert len(payload["resolutions"]) == 1
        assert payload["resolutions"][0]["file"] == "src/app.py"
        assert payload["resolutions"][0]["task_a"] == "T1"
        assert payload["resolutions"][0]["task_b"] == "T2"

    def test_detect_and_resolve_no_shared_files(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.detect_and_resolve(
            [
                {"id": "T1", "files": ["a.py"]},
                {"id": "T2", "files": ["b.py"]},
            ]
        )
        assert payload["resolutions"] == []
        assert payload["ordered_tasks"] == ["T1", "T2"]

    def test_detect_and_resolve_serial_strategy(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.detect_and_resolve(
            [
                {"id": "T1", "files": ["src/app.py"]},
                {"id": "T2", "files": ["src/app.py"]},
            ],
            strategy="serial_execution",
        )
        assert payload["strategy"] == "serial_execution"
        assert ["T1", "T2"] in payload["serial_groups"]

    def test_detect_and_resolve_ignores_tasks_without_files(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.detect_and_resolve([{"id": "T1"}, {"id": "T2", "files": ["a.py"]}])
        assert payload["resolutions"] == []

    def test_detect_and_resolve_does_not_touch_conflicts_file(self, tmp_path):
        """预检测不写 conflicts.json (归属仅内存模拟)。"""
        conflicts_file = tmp_path / "conflicts.json"
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        resolver.detect_and_resolve(
            [{"id": "T1", "files": ["a.py"]}, {"id": "T2", "files": ["a.py"]}]
        )
        assert not conflicts_file.is_file()

    def test_list_returns_copies(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        resolver.resolve([{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
                         [{"id": "T1"}, {"id": "T2"}])
        entry = resolver.list()[0]
        entry["strategy"] = "mutated"
        assert resolver.list()[0]["strategy"] != "mutated"

    def test_ordered_tasks_returns_copies(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        resolver.resolve([], [{"id": "T1"}, {"id": "T2"}])
        order = resolver.ordered_tasks()
        order.append("T9")
        assert "T9" not in resolver.ordered_tasks()

    def test_serial_groups_returns_copies(self, tmp_path):
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        resolver.resolve([{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
                         [{"id": "T1"}, {"id": "T2"}], strategy="serial_execution")
        groups = resolver.serial_groups()
        groups[0].append("T9")
        assert "T9" not in resolver.serial_groups()[0]

    def test_serial_group_order_follows_resolved_order(self, tmp_path):
        """串行分组按重排后顺序排列。"""
        resolver = ConflictResolver(resolution_file=tmp_path / "conflict_resolution.json")
        payload = resolver.resolve(
            [{"file": "a.py", "task_a": "T1", "task_b": "T2"}],
            [{"id": "T2"}, {"id": "T1"}],
            strategy="serial_execution",
        )
        assert payload["serial_groups"] == [["T1", "T2"]]


# ============================================================ 2. TeamExecutionState (验收 B)

class TestTeamExecutionState:
    """team_execution_state.json init/update/get/pause/resume/progress (验收 B)。"""

    def test_init_structure(self, tmp_path):
        state = TeamExecutionState.init(
            tmp_path, "software-team",
            [{"id": "T1", "agent": "backend-1"}, {"id": "T2", "agent": "qa-agent"}],
        )
        assert state["team"] == "software-team"
        assert state["status"] == "running"
        assert state["tasks"]["T1"] == {"agent": "backend-1", "status": "pending", "artifact": ""}
        assert state["tasks"]["T2"]["status"] == "pending"

    def test_init_writes_file(self, tmp_path):
        TeamExecutionState.init(tmp_path, "software-team", [{"id": "T1"}])
        assert (tmp_path / "team_execution_state.json").is_file()
        data = _read_json(tmp_path / "team_execution_state.json")
        assert data["status"] == "running"

    def test_update_status_agent_artifact(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1", "agent": "a1"}])
        state = TeamExecutionState.update(tmp_path, "T1", "completed", agent="a1", artifact="art-1")
        assert state["tasks"]["T1"]["status"] == "completed"
        assert state["tasks"]["T1"]["artifact"] == "art-1"

    def test_update_unknown_task_appends(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [])
        state = TeamExecutionState.update(tmp_path, "T9", "running", agent="a9")
        assert state["tasks"]["T9"]["status"] == "running"
        assert state["tasks"]["T9"]["agent"] == "a9"

    def test_update_persists(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        TeamExecutionState.update(tmp_path, "T1", "completed", artifact="x")
        loaded = TeamExecutionState.load(tmp_path)
        assert loaded["tasks"]["T1"]["status"] == "completed"
        assert loaded["tasks"]["T1"]["artifact"] == "x"

    def test_update_empty_task_id_failure_safe(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        state = TeamExecutionState.update(tmp_path, "", "running")
        assert "" in state["tasks"]
        assert state["tasks"]["T1"]["status"] == "pending"

    def test_get_missing_file_default(self, tmp_path):
        state = TeamExecutionState.get(tmp_path)
        assert state["status"] == "running"
        assert state["tasks"] == {}

    def test_load_missing_file_none(self, tmp_path):
        assert TeamExecutionState.load(tmp_path) is None

    def test_load_corrupt_file_none(self, tmp_path):
        (tmp_path / "team_execution_state.json").write_text("{bad", encoding="utf-8")
        assert TeamExecutionState.load(tmp_path) is None

    def test_snapshot_returns_copy(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        snap = TeamExecutionState.snapshot(tmp_path)
        snap["tasks"]["T1"]["status"] = "completed"
        assert TeamExecutionState.get(tmp_path)["tasks"]["T1"]["status"] == "pending"

    def test_snapshot_structure(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1", "agent": "a1"}])
        snap = TeamExecutionState.snapshot(tmp_path)
        assert snap["team"] == "t"
        assert snap["tasks"]["T1"]["agent"] == "a1"

    def test_pause_sets_paused(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        state = TeamExecutionState.pause(tmp_path)
        assert state["status"] == "paused"
        assert TeamExecutionState.is_paused(tmp_path)

    def test_resume_sets_running(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        TeamExecutionState.pause(tmp_path)
        state = TeamExecutionState.resume(tmp_path)
        assert state["status"] == "running"
        assert not TeamExecutionState.is_paused(tmp_path)

    def test_is_paused_missing_file_false(self, tmp_path):
        assert TeamExecutionState.is_paused(tmp_path) is False

    def test_pause_missing_file_default(self, tmp_path):
        """暂停缺省状态 (无文件) → 缺省骨架 paused, 不抛。"""
        state = TeamExecutionState.pause(tmp_path)
        assert state["status"] == "paused"
        assert (tmp_path / "team_execution_state.json").is_file()

    def test_resume_missing_file_default(self, tmp_path):
        state = TeamExecutionState.resume(tmp_path)
        assert state["status"] == "running"

    def test_progress_counts(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [
            {"id": "T1"}, {"id": "T2"}, {"id": "T3"}, {"id": "T4"},
        ])
        TeamExecutionState.update(tmp_path, "T1", "completed")
        TeamExecutionState.update(tmp_path, "T2", "running")
        TeamExecutionState.update(tmp_path, "T3", "failed")
        prog = TeamExecutionState.progress(tmp_path)
        assert prog["total"] == 4
        assert prog["completed"] == 1
        assert prog["running"] == 1
        assert prog["pending"] == 1
        assert prog["failed"] == 1
        assert prog["percent"] == 25

    def test_progress_empty(self, tmp_path):
        prog = TeamExecutionState.progress(tmp_path)
        assert prog["total"] == 0
        assert prog["percent"] == 0
        assert prog["paused"] is False

    def test_progress_all_completed(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}, {"id": "T2"}])
        TeamExecutionState.update(tmp_path, "T1", "completed")
        TeamExecutionState.update(tmp_path, "T2", "completed")
        prog = TeamExecutionState.progress(tmp_path)
        assert prog["completed"] == 2
        assert prog["percent"] == 100

    def test_progress_paused_flag(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        TeamExecutionState.pause(tmp_path)
        prog = TeamExecutionState.progress(tmp_path)
        assert prog["paused"] is True
        assert prog["status"] == "paused"

    def test_set_status(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        TeamExecutionState.set_status(tmp_path, "completed")
        assert TeamExecutionState.get(tmp_path)["status"] == "completed"

    def test_set_status_missing_default(self, tmp_path):
        TeamExecutionState.set_status(tmp_path, "failed")
        assert TeamExecutionState.get(tmp_path)["status"] == "failed"

    def test_save_normalizes_legacy_list_tasks(self, tmp_path):
        """前向兼容: tasks 为列表 (含 id) → 归一化为 dict 索引。"""
        TeamExecutionState.save(tmp_path, {
            "team": "t", "status": "running",
            "tasks": [{"id": "T1", "agent": "a1", "status": "completed", "artifact": "x"}],
        })
        state = TeamExecutionState.get(tmp_path)
        assert state["tasks"]["T1"]["agent"] == "a1"
        assert state["tasks"]["T1"]["status"] == "completed"

    def test_save_roundtrip(self, tmp_path):
        state = TeamExecutionState.init(tmp_path, "t", [{"id": "T1", "agent": "a1"}])
        state["validation"] = {"qa_review": "approved"}
        TeamExecutionState.save(tmp_path, state)
        loaded = TeamExecutionState.load(tmp_path)
        assert loaded["validation"]["qa_review"] == "approved"

    def test_init_overwrites_fresh(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        TeamExecutionState.update(tmp_path, "T1", "completed")
        TeamExecutionState.init(tmp_path, "t2", [{"id": "T1"}, {"id": "T2"}])
        state = TeamExecutionState.get(tmp_path)
        assert state["team"] == "t2"
        assert state["tasks"]["T1"]["status"] == "pending"
        assert len(state["tasks"]) == 2

    def test_file_name_constant(self):
        assert TeamExecutionState.FILE_NAME == "team_execution_state.json"
        assert TeamExecutionState.STATUS_PAUSED == "paused"

    def test_validation_field_preserved(self, tmp_path):
        TeamExecutionState.init(tmp_path, "t", [{"id": "T1"}])
        state = TeamExecutionState.get(tmp_path)
        state["validation"] = {"command": "pytest", "success": True}
        TeamExecutionState.save(tmp_path, state)
        assert TeamExecutionState.get(tmp_path)["validation"]["success"] is True


# ============================================================ 3. Agent Handoff (验收 C)

class TestAgentHandoff:
    """architect 完成 → handoff_messages.json (requirement/decision/constraints) (验收 C)。"""

    def test_handoff_function_returns_message(self, tmp_path):
        msg = MSG_MOD.handoff(
            "architect-agent", "backend-1",
            "Implement REST API per architecture.md", "设计完成", "遵循架构",
            file=tmp_path / "handoff_messages.json",
        )
        assert msg["type"] == "handoff"
        assert msg["from"] == "architect-agent"
        assert msg["to"] == "backend-1"
        assert msg["requirement"] == "Implement REST API per architecture.md"
        assert msg["decision"] == "设计完成"
        assert msg["constraints"] == "遵循架构"

    def test_handoff_function_writes_file(self, tmp_path):
        ho_file = tmp_path / "handoff_messages.json"
        MSG_MOD.handoff("a", "b", "req", "dec", file=ho_file)
        assert ho_file.is_file()
        data = _read_json(ho_file)
        assert data[0]["from"] == "a"
        assert data[0]["requirement"] == "req"

    def test_handoff_defaults(self, tmp_path):
        msg = MSG_MOD.handoff("a", "b", "req", "dec", file=tmp_path / "h.json")
        assert msg["constraints"] == ""
        assert msg["task_id"] == ""
        assert "timestamp" in msg

    def test_handoff_with_task_id(self, tmp_path):
        msg = MSG_MOD.handoff("a", "b", "req", "dec", task_id="T2",
                              file=tmp_path / "h.json")
        assert msg["task_id"] == "T2"

    def test_handoff_message_roundtrip(self):
        msg = HandoffMessage(from_="a", to="b", requirement="r", decision="d",
                             constraints="c", task_id="T1")
        data = msg.to_dict()
        back = HandoffMessage.from_dict(data)
        assert back.from_ == "a"
        assert back.requirement == "r"
        assert back.constraints == "c"
        assert back.task_id == "T1"
        assert back.type == "handoff"

    def test_handoff_message_from_dict_missing_fields(self):
        back = HandoffMessage.from_dict({"from": "a"})
        assert back.to == ""
        assert back.type == "handoff"

    def test_handoff_message_from_dict_non_dict(self):
        back = HandoffMessage.from_dict(None)
        assert back.from_ == ""

    def test_store_send_and_list(self, tmp_path):
        store = HandoffStore(file=tmp_path / "handoff_messages.json")
        store.send("a", "b", "req1", "dec1")
        store.send("a", "c", "req2", "dec2")
        msgs = store.list()
        assert len(msgs) == 2
        assert msgs[0]["to"] == "b"
        assert msgs[1]["to"] == "c"

    def test_store_messages_for(self, tmp_path):
        store = HandoffStore(file=tmp_path / "handoff_messages.json")
        store.send("a", "backend-1", "r1", "d1")
        store.send("x", "backend-1", "r2", "d2")
        store.send("a", "qa-agent", "r3", "d3")
        inbox = store.messages_for("backend-1")
        assert len(inbox) == 2
        assert all(m["to"] == "backend-1" for m in inbox)

    def test_store_save_load_roundtrip(self, tmp_path):
        ho_file = tmp_path / "handoff_messages.json"
        store = HandoffStore(file=ho_file)
        store.send("a", "b", "req", "dec", constraints="c", task_id="T2")
        loaded = HandoffStore(file=ho_file)
        assert len(loaded.list()) == 1
        assert loaded.list()[0]["constraints"] == "c"

    def test_store_load_missing_file_empty(self, tmp_path):
        store = HandoffStore(file=tmp_path / "nope.json")
        assert store.list() == []

    def test_store_load_corrupt_file_empty(self, tmp_path):
        ho_file = tmp_path / "handoff_messages.json"
        ho_file.write_text("[corrupt", encoding="utf-8")
        store = HandoffStore(file=ho_file)
        assert store.list() == []

    def test_store_append_preserves_existing(self, tmp_path):
        ho_file = tmp_path / "handoff_messages.json"
        store1 = HandoffStore(file=ho_file)
        store1.send("a", "b", "r1", "d1")
        store2 = HandoffStore(file=ho_file)
        store2.send("a", "c", "r2", "d2")
        assert len(store2.list()) == 2

    def test_store_save_creates_parent_dirs(self, tmp_path):
        store = HandoffStore(file=tmp_path / "a" / "b" / "h.json")
        store.send("a", "b", "r", "d")
        assert (tmp_path / "a" / "b" / "h.json").is_file()

    def test_handoff_message_type_constant(self):
        assert MSG_MOD.HANDOFF_TYPE == "handoff"
        assert HandoffStore.DEFAULT_FILE.name == "handoff_messages.json"

    def test_store_messages_for_returns_copies(self, tmp_path):
        store = HandoffStore(file=tmp_path / "h.json")
        store.send("a", "b", "r", "d")
        inbox = store.messages_for("b")
        inbox[0]["requirement"] = "mutated"
        assert store.messages_for("b")[0]["requirement"] == "r"

    def test_handoff_type_is_agent_message_compatible(self, tmp_path):
        """handoff 落盘格式与 agent_messages.json 列表结构兼容 (可统一消费)。"""
        ho_file = tmp_path / "handoff_messages.json"
        MSG_MOD.handoff("architect-agent", "backend-1", "req", "dec", file=ho_file)
        data = _read_json(ho_file)
        assert isinstance(data, list)
        assert data[0]["from"] == "architect-agent"
        assert data[0]["type"] == "handoff"


# ============================================================ 4. Workspace Context 注入 (验收 D)

class TestWorkspaceInjection:
    """任务执行前上下文 (completed/artifacts/messages/decisions) 透传 (验收 D)。"""

    def _team(self, root, tasks=None, deps=None, **kw):
        return _run_team(root, tasks=tasks, deps=deps, calls=[], **kw)

    def test_context_injected_into_task(self, tmp_path):
        calls = []
        _, result = _run_team(tmp_path, calls=calls)
        assert result.completed_tasks == 3
        for task in calls:
            assert isinstance(task.get("context"), dict)
            assert task["context"]["project"] == "demo"

    def test_context_completed_tasks_grows(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls)
        first, second, third = calls
        assert first["context"]["completed_tasks"] == []
        assert second["context"]["completed_tasks"] == ["T001"]
        assert third["context"]["completed_tasks"] == ["T001", "T002"]

    def test_context_artifacts_grows(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls)
        assert calls[0]["context"]["artifacts"] == []
        assert calls[1]["context"]["artifacts"] == ["art-T001"]
        assert calls[2]["context"]["artifacts"] == ["art-T001", "art-T002"]

    def test_context_messages_empty_when_disabled(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls)
        assert calls[0]["context"]["messages"] == []

    def test_context_messages_when_enabled(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls, enable_messages=True)
        # 每个任务完成 → architect 指令消息 (第 2/3 任务上下文可见)
        assert len(calls[1]["context"]["messages"]) == 1
        assert calls[1]["context"]["messages"][0]["type"] == "instruction"

    def test_context_decisions_for_backend(self, tmp_path):
        """架构任务完成 → backend 任务上下文 decisions 含交接 (验收 C+D)。"""
        calls = []
        _run_team(
            tmp_path,
            tasks=ARCH_PLAN_TASKS,
            deps={"T002": ["T001"], "T003": ["T002"]},
            calls=calls,
        )
        by_id = {t["id"]: t for t in calls}
        backend_ctx = by_id["T002"]["context"]
        assert len(backend_ctx["decisions"]) == 1
        handoff = backend_ctx["decisions"][0]
        assert handoff["from"] == "architect-agent"
        assert handoff["requirement"] == "Implement REST API per architecture.md"

    def test_context_decisions_empty_without_deps(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls)
        assert calls[0]["context"]["decisions"] == []

    def test_context_isolated_per_task_copy(self, tmp_path):
        calls = []
        _run_team(tmp_path, calls=calls)
        # 修改一个任务的 context 不影响其他任务
        calls[0]["context"]["completed_tasks"].append("XXX")
        assert "XXX" not in calls[1]["context"]["completed_tasks"]

    def test_context_not_injected_in_solo_mode(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        calls = []
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn(calls))
        assert all("context" not in t for t in calls)

    def test_context_project_name(self, tmp_path):
        calls = []
        _run_team(tmp_path, slug="scorepocket", calls=calls)
        assert calls[0]["context"]["project"] == "scorepocket"


# ============================================================ 5. Team Execution 集成 (验收 E/G)

class TestTeamExecutionIntegration:
    """team mode 完整流程: 角色→依赖→执行→验证 (验收 E)。"""

    def test_team_mode_full_run(self, tmp_path):
        _, result = _run_team(tmp_path)
        assert result.completed_tasks == 3
        assert result.failed_tasks == 0
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_team_mode_assigns_members_by_role(self, tmp_path):
        _run_team(tmp_path)
        tasks = _state_tasks(tmp_path)
        agents = {t["id"]: t["agent"] for t in tasks}
        assert agents["T001"] == "backend-1"
        assert agents["T002"] == "flutter-dev"
        assert agents["T003"] == "qa-agent"

    def test_team_mode_matched_role_recorded(self, tmp_path):
        _run_team(tmp_path)
        tasks = _state_tasks(tmp_path)
        assert {t["matched_role"] for t in tasks} == {"backend", "frontend", "qa"}

    def test_team_mode_dependencies_order(self, tmp_path):
        calls = []
        _run_team(
            tmp_path,
            tasks=ARCH_PLAN_TASKS,
            deps={"T002": ["T001"], "T003": ["T002"]},
            calls=calls,
        )
        ids = [t["id"] for t in calls]
        assert ids == ["T001", "T002", "T003"]

    def test_team_mode_dependencies_partial(self, tmp_path):
        """部分依赖: 仅 T003 依赖 T001 → T003 在 T001 后, T002 位置不变。"""
        calls = []
        _run_team(
            tmp_path,
            tasks=ARCH_PLAN_TASKS,
            deps={"T003": ["T001"]},
            calls=calls,
        )
        ids = [t["id"] for t in calls]
        assert ids.index("T001") < ids.index("T003")

    def test_team_state_file_created(self, tmp_path):
        _run_team(tmp_path)
        ts_file = tmp_path / "projects" / "demo" / "team_execution_state.json"
        assert ts_file.is_file()
        data = _read_json(ts_file)
        assert data["team"] == "software-team"
        assert data["status"] == "completed"

    def test_team_state_per_task_updates(self, tmp_path):
        _run_team(tmp_path)
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["tasks"]["T001"]["status"] == "completed"
        assert data["tasks"]["T001"]["agent"] == "backend-1"
        assert data["tasks"]["T001"]["artifact"] == "art-T001"
        assert data["tasks"]["T003"]["status"] == "completed"

    def test_team_state_progress_after_run(self, tmp_path):
        _run_team(tmp_path)
        prog = TeamExecutionState.progress(tmp_path / "projects" / "demo")
        assert prog["total"] == 3
        assert prog["completed"] == 3
        assert prog["percent"] == 100

    def test_handoff_file_created_with_deps(self, tmp_path):
        _run_team(
            tmp_path,
            tasks=ARCH_PLAN_TASKS,
            deps={"T002": ["T001"], "T003": ["T002"]},
        )
        ho_file = tmp_path / "projects" / "demo" / "handoff_messages.json"
        assert ho_file.is_file()
        data = _read_json(ho_file)
        assert len(data) == 2  # T001→T002, T002→T003
        first = data[0]
        assert first["from"] == "architect-agent"
        assert first["to"] == "backend-1"
        assert first["requirement"] == "Implement REST API per architecture.md"
        assert first["constraints"] == "遵循架构设计, 使用 Python"

    def test_handoff_not_created_without_deps(self, tmp_path):
        _run_team(tmp_path)
        assert not (tmp_path / "projects" / "demo" / "handoff_messages.json").is_file()

    def test_conflict_resolution_file_created_on_same_file(self, tmp_path):
        """同文件冲突 → conflict_resolution.json (验收 A 集成)。"""
        _run_team(tmp_path, tasks=CONFLICT_TASKS)
        res_file = tmp_path / "projects" / "demo" / "conflict_resolution.json"
        assert res_file.is_file()
        data = _read_json(res_file)
        assert data["strategy"] == "dependency_delay"
        assert len(data["resolutions"]) == 1
        assert data["resolutions"][0]["file"] == "src/app.py"
        assert data["resolutions"][0]["task_a"] == "T001"
        assert data["resolutions"][0]["task_b"] == "T002"

    def test_conflict_resolution_no_conflict_empty(self, tmp_path):
        _run_team(tmp_path)
        data = _read_json(tmp_path / "projects" / "demo" / "conflict_resolution.json")
        assert data["resolutions"] == []
        assert data["ordered_tasks"] == ["T001", "T002", "T003"]

    def test_conflict_execution_order_safe(self, tmp_path):
        """冲突任务串行执行 (无并行) — 顺序与重排后计划一致。"""
        calls = []
        _run_team(tmp_path, tasks=CONFLICT_TASKS, calls=calls)
        ids = [t["id"] for t in calls]
        assert ids.index("T001") < ids.index("T002")

    def test_conflict_serial_groups_recorded(self, tmp_path):
        _run_team(tmp_path, tasks=CONFLICT_TASKS)
        data = _read_json(tmp_path / "projects" / "demo" / "conflict_resolution.json")
        assert ["T001", "T002"] in data["serial_groups"]

    def test_team_mode_workspace_context_created(self, tmp_path):
        _run_team(tmp_path)
        ctx_file = tmp_path / "projects" / "demo" / "workspace_context.json"
        assert ctx_file.is_file()
        ctx = _read_json(ctx_file)
        assert ctx["project"] == "demo"
        assert set(ctx["completed_tasks"]) == {"T001", "T002", "T003"}
        assert "art-T001" in ctx["artifacts"]

    def test_team_mode_empty_plan(self, tmp_path):
        _, result = _run_team(tmp_path, tasks=[])
        assert result.completed_tasks == 0
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_team_mode_failure_repair_loop(self, tmp_path):
        """失败 → repair_task.json + lifecycle DEVELOPMENT (Repair Loop 保持)。"""
        _, result = _run_team(tmp_path, execute_fn=_fail_fn(fail_ids={"T002"}))
        assert result.failed_tasks == 1
        assert result.status == "failed"
        repairs = QUAL_MOD.RepairManager.load_repairs(tmp_path / "projects" / "demo")
        assert len(repairs) == 1
        assert repairs[0]["original_task_id"] == "T002"
        assert repairs[0]["status"] == "pending"

    def test_team_mode_failure_team_state_failed(self, tmp_path):
        _run_team(tmp_path, execute_fn=_fail_fn(fail_ids={"T001"}))
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["status"] == "failed"
        assert data["tasks"]["T001"]["status"] == "failed"

    def test_team_mode_failed_task_retry(self, tmp_path):
        """失败 → retry 1 次 (max_retry=1) → 仍失败 → failed。"""
        calls = []
        _, result = _run_team(
            tmp_path,
            execute_fn=_fail_fn(calls=calls, fail_ids={"T001"}),
        )
        assert result.failed_tasks >= 1
        t001_calls = [t for t in calls if t["id"] == "T001"]
        assert len(t001_calls) == 2  # 首次 + 1 次重试

    def test_accept_project_team_mode_delivered(self, tmp_path):
        """USER_ACCEPTANCE → accept_project → DELIVERED (验收 E 终态)。"""
        orch, result = _run_team(tmp_path)
        assert result.status == Lifecycle.USER_ACCEPTANCE
        assert orch.accept_project("demo") is True
        state = _read_json(tmp_path / "projects" / "demo" / "execution_state.json")
        assert state["lifecycle"] == Lifecycle.DELIVERED

    def test_team_mode_qa_task_completes_review(self, tmp_path):
        """qa 角色任务 (T003) 完成 → 团队评审通过 (QA Review 前置条件)。"""
        _, result = _run_team(tmp_path)
        tasks = _state_tasks(tmp_path)
        qa_task = next(t for t in tasks if t["required_role"] == "qa")
        assert qa_task["status"] == "completed"
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_team_mode_enable_messages_agent_messages(self, tmp_path):
        _run_team(tmp_path, enable_messages=True)
        msg_file = tmp_path / "teams" / "agent_messages.json"
        assert msg_file.is_file()
        data = _read_json(msg_file)
        assert len(data) == 3  # 每任务一条 instruction

    def test_team_run_uses_default_team(self, tmp_path):
        """teams.json 缺失 → 默认 software-team (失败安全)。"""
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project(
            "demo", mode="team", execute_fn=_ok_fn(),
            teams_file=tmp_path / "missing" / "teams.json",
            agents_file=tmp_path / "missing" / "agents.json",
            dependencies_file=tmp_path / "missing" / "deps.json",
            conflicts_file=tmp_path / "teams" / "conflicts.json",
        )
        assert result.completed_tasks == 3


# ============================================================ 6. Team Validation (验收 E)

class TestTeamValidation:
    """All Complete → QA → pytest → PASS → DELIVERED (Repair Loop 保持) (验收 E)。"""

    def test_validation_command_pass_reaches_user_acceptance(self, tmp_path):
        validator = FakeValidator(command_ok=True)
        _, result = _run_team(tmp_path, validator=validator,
                              validation_command="pytest")
        assert result.status == Lifecycle.USER_ACCEPTANCE
        assert validator.command_calls == [(tmp_path / "projects" / "demo", "pytest")]

    def test_validation_command_fail_keeps_development(self, tmp_path):
        validator = FakeValidator(command_ok=False, command_errors=["tests failed"])
        _, result = _run_team(tmp_path, validator=validator,
                              validation_command="pytest")
        assert result.status == "failed"
        state = _read_json(tmp_path / "projects" / "demo" / "execution_state.json")
        assert state["lifecycle"] == Lifecycle.DEVELOPMENT

    def test_validation_fail_creates_repair(self, tmp_path):
        """命令门失败 → repair 记录 (Repair Loop 保持)。"""
        validator = FakeValidator(command_ok=False)
        _run_team(tmp_path, validator=validator, validation_command="pytest")
        repairs = QUAL_MOD.RepairManager.load_repairs(tmp_path / "projects" / "demo")
        assert any("team-validation" in (r.get("original_task_id") or "") for r in repairs)

    def test_validation_command_not_called_by_default(self, tmp_path):
        validator = FakeValidator(command_ok=False)
        _, result = _run_team(tmp_path, validator=validator)
        assert validator.command_calls == []
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_validation_command_not_called_on_failed_tasks(self, tmp_path):
        """存在失败任务 → 命令门不执行 (先修复)。"""
        validator = FakeValidator(command_ok=True)
        _, result = _run_team(
            tmp_path,
            execute_fn=_fail_fn(fail_ids={"T001"}),
            validator=validator,
            validation_command="pytest",
        )
        assert validator.command_calls == []
        assert result.status == "failed"

    def test_validation_record_in_team_state(self, tmp_path):
        validator = FakeValidator(command_ok=True)
        _run_team(tmp_path, validator=validator, validation_command="pytest")
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["validation"]["qa_review"] == "approved"
        assert data["validation"]["command"] == "pytest"
        assert data["validation"]["success"] is True

    def test_validation_fail_record_in_team_state(self, tmp_path):
        validator = FakeValidator(command_ok=False, command_errors=["boom"])
        _run_team(tmp_path, validator=validator, validation_command="pytest")
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["validation"]["success"] is False
        assert data["validation"]["errors"] == ["boom"]
        assert data["status"] == "failed"

    def test_real_pytest_command_gate(self, tmp_path):
        """真实 pytest 子进程命令门 (sys.executable — 环境无关, 无网络)。"""
        pdir = _make_project(tmp_path)
        (pdir / "test_dummy.py").write_text(
            "def test_ok():\n    assert True\n", encoding="utf-8"
        )
        _write_team_assets(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project(
            "demo", mode="team", execute_fn=_ok_fn(),
            validation_command=[sys.executable, "-m", "pytest", "-q", "--no-header"],
            **_paths(tmp_path),
        )
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_real_pytest_command_gate_failure(self, tmp_path):
        pdir = _make_project(tmp_path)
        (pdir / "test_dummy.py").write_text(
            "def test_bad():\n    assert False\n", encoding="utf-8"
        )
        _write_team_assets(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project(
            "demo", mode="team", execute_fn=_ok_fn(),
            validation_command=[sys.executable, "-m", "pytest", "-q", "--no-header"],
            **_paths(tmp_path),
        )
        assert result.status == "failed"
        repairs = QUAL_MOD.RepairManager.load_repairs(pdir)
        assert any("team-validation" in (r.get("original_task_id") or "") for r in repairs)

    def test_repair_loop_after_validation_failure(self, tmp_path):
        """命令门失败 → repair → 重跑 → 全绿 (Repair Loop 保持, 验收 E)。"""
        validator = FakeValidator(command_ok=False)
        orch, _ = _run_team(tmp_path, validator=validator, validation_command="pytest")
        assert orch.get_progress("demo")["status"] == Lifecycle.DEVELOPMENT
        # 修复 (mock 重跑) → 命令门转绿
        validator.command_ok = True
        orch2 = ORCH_MOD.ExecutionOrchestrator(tmp_path, validator=validator)
        result = orch2.execute_project(
            "demo", mode="team", execute_fn=_ok_fn(),
            validation_command="pytest", **_paths(tmp_path),
        )
        assert result.status == Lifecycle.USER_ACCEPTANCE


# ============================================================ 7. pause/resume (验收 B)

class TestPauseResume:
    """TeamExecutionState pause/resume + orchestrator 暂停停止 (验收 B)。"""

    @staticmethod
    def _pause_on_fn(pause_id: str):
        """execute_fn mock: 指定任务执行时暂停团队 (完成后停止队列)。"""
        def fn(task, project_dir, workspace):
            if task.get("id") == pause_id:
                TeamExecutionState.pause(project_dir)
            return {"success": True, "artifact": f"art-{task.get('id')}"}
        return fn

    def test_pause_stops_queue(self, tmp_path):
        _, result = _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        assert result.status == "paused"
        assert result.completed_tasks == 2
        assert result.failed_tasks == 0

    def test_pause_keeps_lifecycle_development(self, tmp_path):
        _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        state = _read_json(tmp_path / "projects" / "demo" / "execution_state.json")
        assert state["lifecycle"] == Lifecycle.DEVELOPMENT

    def test_pause_team_state_paused(self, tmp_path):
        _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["status"] == "paused"
        assert data["tasks"]["T001"]["status"] == "completed"
        assert data["tasks"]["T003"]["status"] == "pending"

    def test_pause_progress_partial(self, tmp_path):
        _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        prog = TeamExecutionState.progress(tmp_path / "projects" / "demo")
        assert prog["paused"] is True
        assert prog["completed"] == 2
        assert prog["pending"] == 1

    def test_resume_then_complete(self, tmp_path):
        """pause → resume → 重新执行 → 全部完成 → USER_ACCEPTANCE。"""
        _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        TeamExecutionState.resume(tmp_path / "projects" / "demo")
        assert not TeamExecutionState.is_paused(tmp_path / "projects" / "demo")
        _, result = _run_team(tmp_path, execute_fn=_ok_fn())
        assert result.completed_tasks == 3
        assert result.status == Lifecycle.USER_ACCEPTANCE
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["status"] == "completed"

    def test_pause_on_last_task_queue_exhausted(self, tmp_path):
        """最后一个任务执行中暂停 → 队列已尽 (暂停检查在下次迭代前, 无下次) →
        全部完成 → user_acceptance (暂停不破坏已完成的执行)。"""
        _, result = _run_team(tmp_path, execute_fn=self._pause_on_fn("T003"))
        assert result.completed_tasks == 3
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_orchestrator_resume_flips_team_state(self, tmp_path):
        """orchestrator.resume(): 团队状态 paused → running。"""
        _run_team(tmp_path, execute_fn=self._pause_on_fn("T002"))
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.resume("demo", execute_fn=_ok_fn())
        data = _read_json(tmp_path / "projects" / "demo" / "team_execution_state.json")
        assert data["status"] == "running"


# ============================================================ 8. team_report.md (验收 F)

class TestTeamReport:
    """team_report.md 生成 (team/tasks/agents/artifacts/validation) (验收 F)。"""

    def test_report_generated_in_team_mode(self, tmp_path):
        _run_team(tmp_path)
        report = tmp_path / "projects" / "demo" / "team_report.md"
        assert report.is_file()
        text = report.read_text(encoding="utf-8")
        assert text.startswith("# Team Report — demo")

    def test_report_has_team_section(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Team" in text
        assert "software-team" in text
        assert "AI Software Team" in text
        assert "architect-agent" in text

    def test_report_has_tasks_section(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Tasks" in text
        assert "T001" in text
        assert "数据库 Schema 设计" in text
        assert "backend-1" in text
        assert "completed" in text

    def test_report_has_agents_section(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Agents" in text
        assert "backend-1 (backend)" in text
        assert "qa-agent (qa)" in text

    def test_report_has_artifacts_section(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Artifacts" in text
        assert "art-T001" in text
        assert "art-T003" in text

    def test_report_has_validation_section(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Validation" in text
        assert "passed=3" in text

    def test_report_validation_command_section(self, tmp_path):
        validator = FakeValidator(command_ok=True)
        _run_team(tmp_path, validator=validator, validation_command="pytest")
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "团队验证 (pytest): PASS" in text

    def test_report_validation_failure_section(self, tmp_path):
        validator = FakeValidator(command_ok=False, command_errors=["boom"])
        _run_team(tmp_path, validator=validator, validation_command="pytest")
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "团队验证 (pytest): FAIL" in text
        assert "boom" in text

    def test_report_conflicts_section(self, tmp_path):
        _run_team(tmp_path, tasks=CONFLICT_TASKS)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Conflicts" in text
        assert "src/app.py" in text
        assert "T001 vs T002" in text
        assert "dependency_delay" in text

    def test_report_no_conflicts_placeholder(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Conflicts" in text
        assert "无冲突" in text

    def test_report_handoffs_section(self, tmp_path):
        _run_team(
            tmp_path,
            tasks=ARCH_PLAN_TASKS,
            deps={"T002": ["T001"], "T003": ["T002"]},
        )
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Handoffs" in text
        assert "architect-agent → backend-1" in text
        assert "Implement REST API per architecture.md" in text

    def test_report_no_handoffs_placeholder(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "## Handoffs" in text
        assert "无交接" in text

    def test_report_not_generated_in_solo_mode(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        assert not (tmp_path / "projects" / "demo" / "team_report.md").is_file()

    def test_report_paused_status(self, tmp_path):
        _run_team(tmp_path, execute_fn=_pause_on_t002())
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "- 状态: paused" in text

    def test_report_lifecycle_line(self, tmp_path):
        _run_team(tmp_path)
        text = (tmp_path / "projects" / "demo" / "team_report.md").read_text(encoding="utf-8")
        assert "- Lifecycle: user_acceptance" in text


def _pause_on_t002():
    """独立辅助: T002 执行时暂停 (供 test_report_paused_status 复用)。"""
    def fn(task, project_dir, workspace):
        if task.get("id") == "T002":
            TeamExecutionState.pause(project_dir)
        return {"success": True, "artifact": f"art-{task.get('id')}"}
    return fn


# ============================================================ 9. 回归 (验收 G/J)

class TestRegressions:
    """solo mode 完全兼容 + execute_project/repair/accept 不受影响 (验收 G/J)。"""

    def test_solo_default_mode_full_run(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project("demo", execute_fn=_ok_fn())
        assert result.completed_tasks == 3
        assert result.status == Lifecycle.USER_ACCEPTANCE

    def test_solo_no_team_assets_created(self, tmp_path):
        """solo: 不创建 team_execution_state/handoff/conflict_resolution/report。"""
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        pdir = tmp_path / "projects" / "demo"
        assert not (pdir / "team_execution_state.json").is_file()
        assert not (pdir / "handoff_messages.json").is_file()
        assert not (pdir / "conflict_resolution.json").is_file()
        assert not (pdir / "team_report.md").is_file()

    def test_solo_keeps_plan_agents(self, tmp_path):
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

    def test_solo_ignores_required_role(self, tmp_path):
        tasks = [{"id": "T001", "name": "数据库", "type": "database",
                  "required_role": "frontend", "agent": "backend-1"}]
        _write_team_assets(tmp_path)
        _make_project(tmp_path, tasks=tasks)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        t = _state_tasks(tmp_path)[0]
        assert t["agent"] == "backend-1"
        assert t.get("matched_role") is None

    def test_solo_failure_behavior(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T001"}))
        assert result.status == "failed"
        assert result.completed_tasks == 2
        repairs = QUAL_MOD.RepairManager.load_repairs(tmp_path / "projects" / "demo")
        assert len(repairs) == 1

    def test_solo_accept_project(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        assert orch.accept_project("demo") is True
        assert orch.get_progress("demo")["lifecycle"] == Lifecycle.DELIVERED

    def test_solo_get_progress(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        prog = orch.get_progress("demo")
        assert prog["completed"] == 3
        assert prog["validation"]["passed"] == 3

    def test_solo_get_feature_progress(self, tmp_path):
        tasks = [
            {"id": "T001", "name": "A", "type": "backend", "agent": "backend-1",
             "feature": "F1"},
            {"id": "T002", "name": "B", "type": "frontend", "agent": "flutter-dev",
             "feature": "F1"},
        ]
        _write_team_assets(tmp_path)
        _make_project(tmp_path, tasks=tasks)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        fp = orch.get_feature_progress("demo")
        assert fp["features"][0]["name"] == "F1"
        assert fp["completed"] == 2

    def test_solo_needs_resume(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T001"}))
        assert orch.needs_resume("demo") is True
        assert orch.needs_resume("missing-project") is False

    def test_solo_resume_continues(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T001"}))
        result = orch.resume("demo", execute_fn=_ok_fn())
        assert result.status == Lifecycle.USER_ACCEPTANCE
        assert result.completed_tasks == 3

    def test_repair_task_flow(self, tmp_path):
        """RepairManager.repair: pending → completed (Repair Loop 保持)。"""
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T002"}))
        mgr = QUAL_MOD.RepairManager()
        out = mgr.repair(tmp_path / "projects" / "demo", execute_fn=_ok_fn())
        assert out["status"] == "completed"
        state = _read_json(tmp_path / "projects" / "demo" / "execution_state.json")
        t002 = next(t for t in state["tasks"] if t["id"] == "T002")
        assert t002["status"] == "completed"

    def test_execution_state_structure_unchanged_solo(self, tmp_path):
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_ok_fn())
        state = _read_json(tmp_path / "projects" / "demo" / "execution_state.json")
        assert set(state.keys()) == {"project", "status", "lifecycle", "started_at", "tasks"}
        t = state["tasks"][0]
        assert t["status"] == "completed"
        assert t["validation"] == "passed"

    def test_team_mode_workspace_existing_context_preserved(self, tmp_path):
        """已存在 workspace_context.json → 不覆盖 (保留既有上下文)。"""
        pdir = _make_project(tmp_path)
        _write_json(pdir / "workspace_context.json",
                    {"project": "demo", "files": ["keep.txt"], "completed_tasks": [],
                     "artifacts": [], "agent_history": []})
        _run_team(tmp_path, write_assets=False)
        ctx = _read_json(pdir / "workspace_context.json")
        assert "keep.txt" in ctx["files"]

    def test_team_mode_default_team_zero_config(self, tmp_path):
        """零配置 team mode (缺省 teams/agents) → 默认团队执行成功。"""
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        result = orch.execute_project(
            "demo", mode="team", execute_fn=_ok_fn(),
            teams_file=tmp_path / "nope" / "teams.json",
            agents_file=tmp_path / "nope" / "agents.json",
            dependencies_file=tmp_path / "nope" / "deps.json",
            conflicts_file=tmp_path / "nope" / "conflicts.json",
        )
        assert result.completed_tasks == 3

    def test_team_state_file_absent_in_solo_resume(self, tmp_path):
        """solo resume 不新建 team_execution_state.json。"""
        _write_team_assets(tmp_path)
        _make_project(tmp_path)
        orch = ORCH_MOD.ExecutionOrchestrator(tmp_path)
        orch.execute_project("demo", execute_fn=_fail_fn(fail_ids={"T001"}))
        orch.resume("demo", execute_fn=_ok_fn())
        assert not (tmp_path / "projects" / "demo" / "team_execution_state.json").is_file()

    def test_validation_result_json_after_team_run(self, tmp_path):
        _run_team(tmp_path)
        vf = tmp_path / "projects" / "demo" / "validation_result.json"
        assert vf.is_file()
        data = _read_json(vf)
        assert data["success"] is True
        assert data["tests_passed"] == 3
