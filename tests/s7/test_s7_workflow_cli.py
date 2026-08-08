"""tests/s7/test_s7_workflow_cli.py — factory-org workflow CLI (Integration, S7-003)。

覆盖 (任务清单: CLI list/show/run/status + create 前置):
- create: 人类输出 + --json 形状 (ok/workflow/event_seq) + 缺项目 rc 7 +
  重复 id rc 1 + org.workflow.created 事件
- list: 清单 count + --project 过滤 + org.workflow.viewed 审计 (ADR-0002)
- show: 详情 (workflow + stages + artifacts) + 未找到 rc 7 + viewed 审计
- run: 未注入 executor → rc 1 响亮拒绝 (编排壳诚实边界); monkeypatch 注入
  executor → 全链完成 (org.workflow.completed 事件); 未找到 rc 7
- status: 阶段状态计数 status_counts + viewed 审计

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org + factory-exec)。
阶段/工作流种子经生命周期直接落库 (org CLI 无 stage 子命令; logger=None
零事件, factory.db 只含 CLI 行为事件)。

"""

from __future__ import annotations

import contextlib
import io
import json as _json
from pathlib import Path

import pytest

from events.store import EventStore


def run_cli(root: Path, *argv: str) -> int:
    from org.cli import main

    return main(["--root", str(root), *argv])


def run_cli_json(root: Path, *argv: str) -> tuple[int, dict]:
    from org.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["--root", str(root), "--json", *argv])
    return rc, _json.loads(buf.getvalue())


def cli_event_types(root: Path) -> list[str]:
    store = EventStore(root / "factory.db")
    try:
        return [e.type.value for e in store.query()]
    finally:
        store.close()


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """CLI 工厂根 (root/org 数据空间 + root/factory.db 事件库)。"""
    return tmp_path / "factory"


def _seed_project(root: Path, project_id: str = "P-1", name: str = "Build App") -> None:
    from org.projects import ProjectLifecycle, ProjectStore

    ProjectLifecycle(ProjectStore(root / "org")).create_project(name, project_id=project_id)


def _seed_workflow(root: Path, *, workflow_id: str = "WF-1",
                   project_id: str = "P-1", name: str = "Ship v1",
                   stages: list[tuple[str, str, dict]] | None = None) -> None:
    """种子: workflow + 阶段 (logger=None 零事件; 只落数据空间)。"""
    from org.projects import ProjectStore
    from org.workflow import WorkflowLifecycle

    lc = WorkflowLifecycle(ProjectStore(root / "org"))
    lc.create_workflow(project_id, name, workflow_id=workflow_id)
    for stage_id, role_id, kw in (stages or []):
        lc.create_stage(workflow_id, role_id, stage_id=stage_id, **kw)


def _inject_executor(monkeypatch, executor=None):
    """monkeypatch _build_workflow_runner 注入 executor (S7-005 接入点)。"""
    from org.projects import ProjectStore
    from org.workflow import WorkflowLifecycle, WorkflowRunner

    def fake_builder(root, logger):
        return WorkflowRunner(
            WorkflowLifecycle(ProjectStore(root / "org"), logger=logger),
            executor=executor,
            logger=logger,
        )

    monkeypatch.setattr("org.cli._build_workflow_runner", fake_builder)


def _code_executor(stage, context):
    return {"artifact_type": "code", "metadata": {"files": ["a.py"], "changes": "x"}}


class TestCliCreate:
    def test_create_human_output(self, cli_root, capsys):
        _seed_project(cli_root)
        rc = run_cli(cli_root, "workflow", "create", "--project", "P-1",
                     "--name", "Ship v1", "--id", "WF-1")
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 工作流创建成功" in out
        assert "WF-1" in out
        assert "Ship v1" in out
        assert "draft" in out

    def test_create_json_shape(self, cli_root):
        _seed_project(cli_root)
        rc, data = run_cli_json(cli_root, "workflow", "create", "--project", "P-1",
                                "--name", "Ship v1", "--id", "WF-1")
        assert rc == 0
        assert data["ok"] is True
        assert data["workflow"]["id"] == "WF-1"
        assert data["workflow"]["project_id"] == "P-1"
        assert data["workflow"]["status"] == "draft"
        assert data["event_seq"] == 1
        assert "org.workflow.created" in cli_event_types(cli_root)

    def test_create_missing_project_rc7(self, cli_root):
        rc, data = run_cli_json(cli_root, "workflow", "create",
                                "--project", "P-999", "--name", "W")
        assert rc == 7
        assert "project not found" in data["error"]

    def test_create_duplicate_rc1(self, cli_root):
        _seed_project(cli_root)
        _seed_workflow(cli_root)
        rc, data = run_cli_json(cli_root, "workflow", "create", "--project", "P-1",
                                "--name", "Again", "--id", "WF-1")
        assert rc == 1
        assert "already exists" in data["error"]


class TestCliList:
    def test_list_empty_count_and_viewed(self, cli_root):
        rc, data = run_cli_json(cli_root, "workflow", "list")
        assert rc == 0
        assert data["count"] == 0
        assert data["workflows"] == []
        assert "org.workflow.viewed" in cli_event_types(cli_root)  # 读命令审计

    def test_list_by_project_filter(self, cli_root):
        _seed_project(cli_root, project_id="P-1", name="App A")
        _seed_project(cli_root, project_id="P-2", name="App B")
        _seed_workflow(cli_root, workflow_id="WF-1", project_id="P-1", name="Ship v1")
        _seed_workflow(cli_root, workflow_id="WF-2", project_id="P-2", name="Ship v2")
        rc, data = run_cli_json(cli_root, "workflow", "list")
        assert rc == 0
        assert data["count"] == 2
        rc, data = run_cli_json(cli_root, "workflow", "list", "--project", "P-1")
        assert data["count"] == 1
        assert data["workflows"][0]["id"] == "WF-1"


class TestCliShow:
    def test_show_detail_with_stages(self, cli_root):
        _seed_project(cli_root)
        _seed_workflow(cli_root, stages=[("STG-1", "product-manager", {}),
                                        ("STG-2", "developer", {"depends_on": ["STG-1"]})])
        rc, data = run_cli_json(cli_root, "workflow", "show", "WF-1")
        assert rc == 0
        assert data["workflow"]["id"] == "WF-1"
        assert data["stage_count"] == 2
        assert [s["id"] for s in data["stages"]] == ["STG-1", "STG-2"]
        assert data["artifacts"] == []
        assert "org.workflow.viewed" in cli_event_types(cli_root)

    def test_show_not_found_rc7(self, cli_root):
        rc, data = run_cli_json(cli_root, "workflow", "show", "WF-999")
        assert rc == 7
        assert "workflow not found" in data["error"]


class TestCliRun:
    def test_run_without_executor_rc1(self, cli_root):
        """编排壳诚实边界: 未注入 executor 且需执行 → rc 1 响亮拒绝。"""
        _seed_project(cli_root)
        _seed_workflow(cli_root, stages=[("STG-1", "developer", {})])
        rc, data = run_cli_json(cli_root, "workflow", "run", "WF-1")
        assert rc == 1
        assert "no executor" in data["error"]

    def test_run_with_executor_completes(self, cli_root, monkeypatch):
        """注入 executor (monkeypatch 接入点) → 全链完成 + 事件闭环。"""
        _seed_project(cli_root)
        _seed_workflow(cli_root, stages=[("STG-1", "developer", {})])
        _inject_executor(monkeypatch, executor=_code_executor)
        rc, data = run_cli_json(cli_root, "workflow", "run", "WF-1")
        assert rc == 0
        assert data["ok"] is True
        assert data["workflow"]["status"] == "completed"
        assert data["stages"][0]["status"] == "completed"
        events = cli_event_types(cli_root)
        assert "org.workflow.completed" in events
        assert "org.workflow.stage_completed" in events
        # run 本身不审计 viewed (仅 list/show/status 读命令审计, ADR-0002)

    def test_run_not_found_rc7(self, cli_root):
        rc, data = run_cli_json(cli_root, "workflow", "run", "WF-999")
        assert rc == 7
        assert "workflow not found" in data["error"]


class TestCliStatus:
    def test_status_counts(self, cli_root, monkeypatch):
        _seed_project(cli_root)
        _seed_workflow(cli_root, stages=[("STG-1", "product-manager", {}),
                                        ("STG-2", "developer", {"depends_on": ["STG-1"]})])
        _inject_executor(monkeypatch, executor=_code_executor)
        run_cli(cli_root, "workflow", "run", "WF-1")
        rc, data = run_cli_json(cli_root, "workflow", "status", "WF-1")
        assert rc == 0
        assert data["workflow"]["status"] == "completed"
        assert data["status_counts"] == {"completed": 2}
        assert "org.workflow.viewed" in cli_event_types(cli_root)

    def test_status_human_output(self, cli_root, capsys):
        _seed_project(cli_root)
        _seed_workflow(cli_root)
        rc = run_cli(cli_root, "workflow", "status", "WF-1")
        out = capsys.readouterr().out
        assert rc == 0
        assert "工作流状态: WF-1 [draft]" in out
        assert "(无阶段)" in out
