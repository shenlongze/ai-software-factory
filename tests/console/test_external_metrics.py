"""tests/console/test_external_metrics.py — M4 监控指标聚合 (EXS → 指标/告警)。

设计依据: 设计文档 §8。
覆盖:
- aggregate_executor_metrics: 效率/效果/完成率/回修/验证 每执行器聚合
- build_alerts: 连续失败≥3 / 验证 fail(回修) / probe 不可用 / 无记录(unknown)
- HTTP: GET /api/external-ai/monitor
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-exec"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_metrics = importlib.import_module("factory-console.external_executor.metrics")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _seed(data_dir: Path):
    exec_dir = data_dir / "exec"
    exec_dir.mkdir(parents=True)
    records = [
        {"executor_id": "codex", "result_id": "EXS-1", "result": "success", "first_pass": True,
         "verify": {"result": "pass", "score": 0.9}, "rework": {"count": 0, "reasons": []},
         "duration_ms": 1000, "timestamp": "2026-08-27T00:00:01Z", "mode": "blackbox", "host_agent": ""},
        {"executor_id": "codex", "result_id": "EXS-2", "result": "success", "first_pass": True,
         "verify": {"result": "pass", "score": 0.8}, "rework": {"count": 0, "reasons": []},
         "duration_ms": 2000, "timestamp": "2026-08-27T00:00:02Z", "mode": "blackbox", "host_agent": ""},
        {"executor_id": "codex", "result_id": "EXS-3", "result": "failed", "first_pass": True,
         "verify": {"result": "unknown"}, "rework": {"count": 0, "reasons": []},
         "duration_ms": 500, "timestamp": "2026-08-27T00:00:03Z", "mode": "blackbox", "host_agent": ""},
        {"executor_id": "claude", "result_id": "EXS-4", "result": "failed", "first_pass": False,
         "verify": {"result": "fail", "score": 0.3}, "rework": {"count": 1, "reasons": ["测试挂"]},
         "duration_ms": 3000, "timestamp": "2026-08-27T00:00:04Z", "mode": "borrowed-shell", "host_agent": "arch"},
        {"executor_id": "claude", "result_id": "EXS-5", "result": "failed", "first_pass": False,
         "verify": {"result": "fail"}, "rework": {"count": 2, "reasons": ["测试挂", "需求不清"]},
         "duration_ms": 1000, "timestamp": "2026-08-27T00:00:05Z", "mode": "borrowed-shell", "host_agent": "arch"},
        {"executor_id": "claude", "result_id": "EXS-6", "result": "failed", "first_pass": False,
         "verify": {"result": "unknown"}, "rework": {"count": 2, "reasons": []},
         "duration_ms": 1000, "timestamp": "2026-08-27T00:00:06Z", "mode": "blackbox", "host_agent": ""},
    ]
    (exec_dir / "execution_records.json").write_text(json.dumps(records), encoding="utf-8")


class TestAggregate:
    def test_metrics_per_executor(self, tmp_path):
        _seed(tmp_path)
        rows = _metrics.aggregate_executor_metrics(tmp_path)
        codex = next(r for r in rows if r["executor_id"] == "codex")
        assert codex["total"] == 3 and codex["success"] == 2 and codex["failed"] == 1
        assert codex["success_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert codex["first_pass_rate"] == 1.0  # EXS-3 failed 但 first_pass True
        assert codex["verify_pass_rate"] == 1.0  # 2 pass / 2 verified
        assert codex["avg_duration_ms"] == pytest.approx((1000 + 2000 + 500) / 3, abs=1)
        assert codex["rework_total"] == 0
        claude = next(r for r in rows if r["executor_id"] == "claude")
        assert claude["total"] == 3 and claude["failed"] == 3  # 3 条全 failed
        assert claude["first_pass_rate"] == 0.0  # 全部 first_pass False
        assert claude["rework_total"] == 5
        assert claude["last_host_agent"] == ""  # 最新一条 blackbox
        # 无记录执行器不出现
        assert all(r["executor_id"] != "hermes" for r in rows)


class TestAlerts:
    def test_alerts(self, tmp_path):
        _seed(tmp_path)
        from factory_console.external_executor.registry import build_registry

        reg = build_registry(tmp_path)
        # 注册一个二进制不存在的适配器 (真实 not_found)
        from factory_console.external_executor.schema import ExternalExecutorAdapter

        reg.save(ExternalExecutorAdapter(
            id="openclaw", name="OpenClaw", binary="openclaw-not-installed",
            discovery=["/nonexistent-openclaw-dir"],
            invocation={"non_interactive": ["{prompt}"], "project_dir": "cwd"},
        ))
        alerts = _metrics.build_alerts(tmp_path, reg.list())
        types = {a["type"] for a in alerts}
        # claude 最新 3 条 (EXS-4/5/6) 全 failed → 连续 3 → consecutive_failures
        assert "consecutive_failures" in types
        assert "verify_rework" in types  # claude rework>0
        assert "not_found" in types  # openclaw 未装
        assert "no_records" in types  # codex/claude 有记录; openclaw 未发现
        # 确认 consecutive 是针对 claude (最新3条全 failed)
        cf = next(a for a in alerts if a["type"] == "consecutive_failures")
        assert cf["executor_id"] == "claude"
        nf = next(a for a in alerts if a["type"] == "not_found")
        assert nf["executor_id"] == "openclaw"


@requires_fastapi
class TestMonitorHttp:
    def test_monitor_endpoint(self, tmp_path):
        _seed(tmp_path)
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.get("/api/external-ai/monitor")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["summary"]["external"]["total"] == 6  # 3 codex + 3 claude
            codex = next(e for e in body["by_executor"] if e["key"] == "codex")
            assert codex["total"] == 3
            assert len(body["trend"]) >= 1
            assert len(body["recent"]) >= 1
            assert isinstance(body["alerts"], list)
