"""tests/console/test_task_exec_writeback.py — 方案A: 执行绑定 + 回写钩子 (v1.1.194)。

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

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


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


@requires_fastapi
class TestTaskExecTrace:
    def _seed_exec_files(self, root: Path, exec_ref: str, result_id: str) -> None:
        """写真实 exec/ 记录 + 证据包 (requests.json / execution_records.json / report.md)。"""
        exec_dir = root / "exec"
        exec_dir.mkdir(parents=True, exist_ok=True)
        (exec_dir / "requests.json").write_text(
            json.dumps(
                {
                    "requests": {
                        exec_ref: {
                            "id": exec_ref,
                            "task_id": "TASK-1",
                            "objective": "完善导出功能",
                            "requirement": "支持 CSV",
                            "status": "completed",
                            "created_at": "2026-08-26T04:00:00Z",
                            "output_refs": [result_id],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (exec_dir / "execution_records.json").write_text(
            json.dumps(
                [
                    {
                        "result_id": result_id,
                        "intent": "run_task",
                        "agent": "backend-1",
                        "task": "完善导出功能",
                        "result": "success",
                        "timestamp": "2026-08-26T04:05:00Z",
                        "error": "",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (exec_dir / f"{result_id}.report.md").write_text("# 执行报告", encoding="utf-8")

    def test_task_detail_attaches_exec_trace(self, tmp_path):
        """T-9: 任务详情附 exec_trace — exec_ref → EXR request → EXS result → 证据包。"""
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        self._seed_exec_files(tmp_path, "EXR-T9", "EXS-T9")
        svc.start_task_exec(pid, tid, exec_ref="EXR-T9", note="启动")
        svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-T9", exec_result="EXS-T9")
        app = _adapter.build_app(svc, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get(f"/api/projects/{pid}/backlog/task/{tid}")
            assert r.status_code == 200, r.text
            trace = r.json().get("exec_trace") or {}
            assert trace["exec_ref"] == "EXR-T9"
            assert trace["exec_result"] == "EXS-T9"
            assert trace["request"]["id"] == "EXR-T9"
            assert trace["request"]["objective"] == "完善导出功能"
            assert trace["results"][0]["result_id"] == "EXS-T9"
            assert trace["results"][0]["result"] == "success"
            assert trace["evidence"][0]["report"] == "EXS-T9.report.md"

    def test_task_detail_no_binding_honest_empty(self, tmp_path):
        """T-9 诚实降级: 无 exec_ref → exec_trace 各段空 (不编造)。"""
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        app = _adapter.build_app(svc, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get(f"/api/projects/{pid}/backlog/task/{tid}")
            trace = r.json().get("exec_trace") or {}
            assert not trace["exec_ref"]  # 空串 (无绑定)
            assert trace["request"] is None
            assert trace["results"] == []


class TestExecCheckpoint:
    """T-6 (D-2): 执行中断 checkpoint 落盘与恢复实测。"""

    def test_checkpoint_written_on_start_cleared_on_finish(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="EXR-CP", note="开始执行")
        cps = svc.list_exec_checkpoints()
        cp = next((c for c in cps if c["task_id"] == tid), None)
        assert cp is not None
        assert cp["exec_ref"] == "EXR-CP"
        assert cp["project_id"] == pid
        assert cp["started_at"]
        # 正常结束 → 清除
        svc.finish_task_exec(pid, tid, success=True, exec_ref="EXR-CP", exec_result="EXS-CP")
        cps = svc.list_exec_checkpoints()
        assert all(c["task_id"] != tid for c in cps)

    def test_interruption_recovery(self, tmp_path):
        """模拟进程崩溃 (start 后不 finish) → checkpoint 仍在 → 续跑恢复 → 清除。"""
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="EXR-CP1", note="第一次启动")
        # 崩溃: 不 finish, 直接重建 service (模拟进程重启/新进程)
        svc2 = _build_service(tmp_path)
        cps = svc2.list_exec_checkpoints()
        assert any(c["task_id"] == tid and c["exec_ref"] == "EXR-CP1" for c in cps)
        # 续跑恢复 (start 幂等) → 完成 → checkpoint 清除
        svc2.start_task_exec(pid, tid, exec_ref="EXR-CP2", note="续跑恢复")
        svc2.finish_task_exec(pid, tid, success=True, exec_ref="EXR-CP2", exec_result="EXS-CP2")
        task = svc2.get_task(pid, tid)
        assert task["status"] == "done"
        assert all(c["task_id"] != tid for c in svc2.list_exec_checkpoints())

    @pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")
    def test_api_lists_interrupted_checkpoints(self, tmp_path):
        svc = _build_service(tmp_path)
        pid, tid = _new_task(svc, tmp_path)
        svc.start_task_exec(pid, tid, exec_ref="EXR-API", note="中断中")
        app = _adapter.build_app(svc, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/exec/checkpoints")
            assert r.status_code == 200, r.text
            items = r.json().get("items") or []
            cp = next((x for x in items if x["task_id"] == tid), None)
            assert cp is not None
            assert cp["exec_ref"] == "EXR-API"
            assert cp["task_title"]  # 富化任务标题


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

    def test_run_resume_after_interruption(self, tmp_path):
        """T-8 续跑: 上次执行中断 (status=in_progress) → 再跑检测到 → 续跑 → done。
        start_task_exec 幂等 (仅更新 exec_ref); history 记录续跑 note。"""
        cli = _make_cli(tmp_path)
        pid, _slug, tid, _title = _seed_project_and_task(cli)
        svc = _build_service(cli.data_dir)
        # 模拟上次执行中断: 已绑定 + in_progress, 但未回写 (无 finish)
        svc.start_task_exec(pid, tid, exec_ref="bridge:old", note="第一次启动(中断)")
        assert svc.get_task(pid, tid)["status"] == "in_progress"
        # 续跑: 再执行成功
        cli._proxy_exec_cli = lambda: _FakeExec(
            {"ok": True, "exit_code": 0, "request_id": "EXR-RESUME", "result_id": "EXS-RESUME",
             "status": "success", "error": None}
        )
        rc = cli.task(_cli.argparse.Namespace(task_action="run", task_id=tid, project=""))
        assert rc == 0
        task = svc.get_task(pid, tid)
        assert task["status"] == "done"
        assert task["exec_ref"] == "EXR-RESUME"
        assert task["exec_result"] == "EXS-RESUME"
        notes = [h.get("result") or "" for h in task["history"]]
        assert any("续跑" in n for n in notes), notes

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
