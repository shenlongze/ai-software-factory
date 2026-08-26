"""tests/console/test_monitor.py — 统一监控运维 (D 系列, v1.1.134)。

覆盖 (factory-console/monitor.py + GET /api/monitor + /api/projects/{id}/monitor):
- collect_system: 端口/版本/数据目录
- collect_project: 质量分/任务统计/产出物版本/文档数 (文件信源, 失败安全)
- save/read_snapshots: 快照历史
- HTTP: /api/monitor 系统+项目; /api/projects/{id}/monitor
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_monitor = importlib.import_module("factory-console.monitor")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


class TestMonitor:
    def test_collect_system(self, tmp_path):
        m = _monitor.collect_system(tmp_path, "1.1.134", model_line="deepseek-chat")
        assert m["version"] == "1.1.134"
        assert m["frontend"]["port"] == 5180
        assert "up" in m["frontend"]
        assert m["data_dir"] == str(tmp_path)
        assert "deepseek-chat" in m["model"]

    def test_collect_project(self, tmp_path):
        pdir = tmp_path / "projects" / "P-1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "quality.json").write_text(json.dumps({"score": 0.72}), encoding="utf-8")
        (pdir / "management" / "backlog" / "task.json").parent.mkdir(parents=True, exist_ok=True)
        (pdir / "management" / "backlog" / "task.json").write_text(
            json.dumps({"tasks": {"T-1": {"status": "todo"}, "T-2": {"status": "done"}}}), encoding="utf-8"
        )
        pm = _monitor.collect_project(tmp_path, "P-1", name="测试", lifecycle="development")
        assert pm["quality"] == 0.72
        assert pm["tasks"] == {"todo": 1, "done": 1}
        assert pm["lifecycle"] == "development"
        # 缺失项目 → None
        assert _monitor.collect_project(tmp_path, "NOPE") is None

    def test_snapshots_roundtrip(self, tmp_path):
        assert _monitor.save_snapshot(tmp_path, {"system": {"version": "1"}}) is True
        assert _monitor.save_snapshot(tmp_path, {"system": {"version": "2"}}) is True
        snaps = _monitor.read_snapshots(tmp_path, limit=10)
        assert len(snaps) == 2
        assert snaps[0]["system"]["version"] == "2"  # 最新在前
        assert _monitor.snapshot_count(tmp_path) == 2
        assert (tmp_path / _monitor.SNAPSHOT_FILE).is_file()

    def test_snapshots_pagination(self, tmp_path):
        for i in range(25):
            _monitor.save_snapshot(tmp_path, {"system": {"version": f"{i}"}})
        assert _monitor.snapshot_count(tmp_path) == 25
        p1 = _monitor.read_snapshots(tmp_path, limit=10, offset=0)
        p2 = _monitor.read_snapshots(tmp_path, limit=10, offset=10)
        assert len(p1) == 10 and len(p2) == 10
        # 最新在前: p1[0] = v24, p2[0] = v14
        assert p1[0]["system"]["version"] == "24"
        assert p2[0]["system"]["version"] == "14"
        p3 = _monitor.read_snapshots(tmp_path, limit=10, offset=20)
        assert len(p3) == 5


@requires_fastapi
class TestMonitorHttp:
    def test_api_monitor(self, tmp_path):
        (tmp_path / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/monitor")
            assert r.status_code == 200
            body = r.json()
            assert body["system"]["version"]
            assert isinstance(body["projects"], list)
            assert isinstance(body["snapshots"], list)

    def test_api_project_monitor(self, tmp_path):
        (tmp_path / "projects" / "p1").mkdir(parents=True, exist_ok=True)
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/projects/p1/monitor")
            assert r.status_code == 200
            assert r.json()["project"]["project_id"] == "p1"
            assert r.json()["system"]["version"]
            assert c.get("/api/projects/NOPE/monitor").status_code == 404


class TestAlerts:
    def test_alerts_detected(self):
        system = {"frontend": {"up": False}, "backend": {"up": True}}
        projects = [
            {"project_id": "p1", "name": "A", "failed": 2, "quality": 0.8},
            {"project_id": "p2", "name": "B", "failed": 0, "quality": 0.2},
        ]
        alerts = _monitor.check_alerts(system, projects)
        msgs = {a["message"] for a in alerts}
        assert any("前端" in m for m in msgs)  # critical
        assert any("失败运行实例" in m for m in msgs)  # warning
        assert any("质量分偏低" in m for m in msgs)  # warning
        assert all(a["level"] in ("critical", "warning") for a in alerts)

    def test_no_alerts_when_healthy(self):
        system = {"frontend": {"up": True}, "backend": {"up": True}}
        projects = [{"project_id": "p1", "name": "A", "failed": 0, "quality": 0.8}]
        assert _monitor.check_alerts(system, projects) == []
