"""tests/console/test_task_exec_writeback.py — 方案A: 执行绑定 + 回写钩子 (v1.1.153)。

Founder 2026-08-26: "任务会自动更新状态么 → 选 A (执行绑定 + 回写)"。
覆盖 (service.start_task_exec / finish_task_exec + org.management.Task 字段 +
cli_factory.FactoryCLI.task run):
- Task 模型: exec_ref/exec_result 字段 (to_dict 含, 持久化)
- start_task_exec: todo → in_progress (走合法路径) + exec_ref + 审计 exec:start;
  幂等 (已是 in_progress 仅更新 exec_ref); 依赖未满足 → ValueError 拒绝启动
- finish_task_exec: 成功 → done (in_progress→review→done) + exec_ref/exec_result +
  审计 exec:completed; 失败 → blocked + 审计 exec:failed; 未启动过 → 先走到
  in_progress 再回写; 已是目标态 → 幂等 (仅更新绑定字段 + 审计)
- 状态机路径 BFS: todo→done 合法 (不跳级), done→todo 无路径 (拒绝)
- CLI task run: 启动前绑定/执行后回写 (mock exec CLI), 成功 → done / 失败 → blocked
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_service = importlib.import_module("factory-console.service")
_cli = importlib.import_module("factory-console.cli_factory")


def _build_service(root: Path):
    return _adapter.build_console_service(root, event_logger=None)


def _new_task(svc: Any, root: Path) -> tuple[str, str]:
    """建项目 + 建任务 → (project_id, task_id)。"""
    proj = svc.create_project("执行绑定演示", name="Exec Writeback Demo")
    assert proj is not None and proj.id
    task = svc.create_task(proj.id, title="完善导出功能", description="给 X 完善导出")
    assert task is not None and task["id"]
    return proj.id, task["id"]


class TestTaskModel:
    def test_task_has_exec_fields(self):
        from org.management import Task

        t = Task(id="TASK-1", title="t", exec_ref="EXR-1", exec_result="EXS-1")
        d = t.to_dict()
        assert d["exec_ref"] == "EXR-1"
        assert d["exec_result"] == "EXS-1"

    def test_task_exec_fields_persist(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="bridge:TASK-x", note="启动")
        svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-1", exec_result="EXS-1")
        # 重建 service → 字段仍落盘 (目录信源)
        svc2 = _build_service(tmp_path)
        task = svc2.get_task(pid, tid)
        assert task["exec_ref"] == "EXR-1"
        assert task["exec_result"] == "EXS-1"
        assert task["status"] == "done"


class TestStartTaskExec:
    def test_start_transitions_to_in_progress_with_bind(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        t = svc.start_task_exec(pid, tid, exec_ref="bridge:TASK-x", note="启动测试")
        assert t["status"] == "in_progress"
        assert t["exec_ref"] == "bridge:TASK-x"
        actions = [h["action"] for h in t["history"]]
        assert "exec:start" in actions
        # 不跳级: history 有中间步 (todo→ready→in_progress)
        assert len([a for a in actions if a == "exec:start"]) == 2

    def test_start_idempotent_when_already_in_progress(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="bridge:1")
        t = svc.start_task_exec(pid, tid, exec_ref="bridge:2")
        assert t["status"] == "in_progress"
        assert t["exec_ref"] == "bridge:2"
        # 不重复转换 (仅更新 exec_ref) — 无新增 exec:start
        assert [h["action"] for h in t["history"]].count("exec:start") == 2

    def test_start_rejects_unmet_dependency(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, _ = _new_task(svc, tmp_path)
        dep = svc.create_task(pid, title="前置任务")
        task = svc.create_task(pid, title="后置任务", dependency=[dep["id"]])
        with pytest.raises(ValueError):
            svc.start_task_exec(pid, task["id"])


class TestFinishTaskExec:
    def test_finish_success_to_done(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="bridge:TASK-x")
        t = svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-9", exec_result="EXS-9")
        assert t["status"] == "done"
        assert t["exec_ref"] == "EXR-9"
        assert t["exec_result"] == "EXS-9"
        actions = [h["action"] for h in t["history"]]
        assert "exec:completed" in actions
        assert "exec:progress" in actions  # in_progress→review 中间步不跳级

    def test_finish_failure_to_blocked(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid)
        t = svc.finish_task_exec(pid, tid, success=False, error="provider 5xx")
        assert t["status"] == "blocked"
        assert any("provider 5xx" in (h.get("result") or "") for h in t["history"])
        assert any(h["action"] == "exec:failed" for h in t["history"])

    def test_finish_from_todo_walks_to_done(self, tmp_path):
        """未 start 直接 finish 成功 → todo→ready→in_progress→review→done (合法路径)。"""
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        t = svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-1", exec_result="EXS-1")
        assert t["status"] == "done"
        assert t["exec_ref"] == "EXR-1"

    def test_finish_idempotent_when_done(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-1", exec_result="EXS-1")
        t = svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-2", exec_result="EXS-2")
        assert t["status"] == "done"
        assert t["exec_ref"] == "EXR-2"
        # 不重复转换 — 无新增 exec:progress
        assert [h["action"] for h in t["history"]].count("exec:progress") == 1


class TestStatusPath:
    def test_bfs_path_todo_to_done(self):
        from org.management import TASK_TRANSITIONS, TaskStatus

        svc = object.__new__(_service.ConsoleService)
        path = svc._status_path(TASK_TRANSITIONS, TaskStatus.TODO, TaskStatus.DONE)
        assert path == [TaskStatus.READY, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.DONE]

    def test_bfs_path_none_for_done_to_todo(self):
        from org.management import TASK_TRANSITIONS, TaskStatus

        svc = object.__new__(_service.ConsoleService)
        assert svc._status_path(TASK_TRANSITIONS, TaskStatus.DONE, TaskStatus.TODO) is None


class _FakeExec:
    """mock exec CLI: cmd_exec_run 返回预设 dict。"""

    def __init__(self, result: dict):
        self.result = result

    def cmd_exec_run(self, root: Any, args: Any) -> dict:
        return self.result


def _make_cli(tmp_path: Path) -> _cli.FactoryCLI:
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
    cfg = _cli.ConfigProvider(user_config_file=cfg_file, environ={})
    return _cli.FactoryCLI(cfg)


def _seed_project_and_task(cli: _cli.FactoryCLI) -> tuple[str, str, str, str]:
    """建项目+任务 → (project_id, slug, task_id, task_title); 复用 CLI data_dir 同源。"""
    svc = _build_service(cli.data_dir)
    proj = svc.create_project("CLI 绑定演示", name="CLI Exec Demo")
    task = svc.create_task(proj.id, title="完善导出功能", description="给 X 完善导出")
    # slug 目录名 = _find_task 的 project (workspace/projects/<slug>)
    from org.space import ProjectSpaceStore

    slug = ProjectSpaceStore(cli.data_dir).get_slug(proj.id)
    assert slug is not None
    return proj.id, str(slug), task["id"], task["title"]


class TestCliTaskRunWriteback:
    def test_run_success_writes_back_done(self, tmp_path):
        cli = _make_cli(tmp_path)
        pid, _slug, tid, _title = _seed_project_and_task(cli)
        cli._proxy_exec_cli = lambda: _FakeExec(
            {"ok": True, "exit_code": 0, "request_id": "EXR-88", "result_id": "EXS-88",
             "status": "success", "error": None}
        )
        rc = cli.task(_cli.argparse.Namespace(task_action="run", task_id=tid, project=""))
        assert rc == 0
        svc = _build_service(cli.data_dir)
        task = svc.get_task(pid, tid)
        assert task["status"] == "done"
        assert task["exec_ref"] == "EXR-88"
        assert task["exec_result"] == "EXS-88"
        actions = [h["action"] for h in task["history"]]
        assert "exec:start" in actions and "exec:completed" in actions

    def test_run_failure_writes_back_blocked(self, tmp_path):
        cli = _make_cli(tmp_path)
        pid, _slug, tid, _title = _seed_project_and_task(cli)
        cli._proxy_exec_cli = lambda: _FakeExec(
            {"ok": False, "exit_code": 1, "request_id": "EXR-99", "result_id": "",
             "status": "failed", "error": "provider 5xx"}
        )
        rc = cli.task(_cli.argparse.Namespace(task_action="run", task_id=tid, project=""))
        assert rc == 1
        svc = _build_service(cli.data_dir)
        task = svc.get_task(pid, tid)
        assert task["status"] == "blocked"
        assert task["exec_ref"] == "EXR-99"
        assert any("provider 5xx" in (h.get("result") or "") for h in task["history"])
