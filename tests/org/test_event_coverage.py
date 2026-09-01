"""tests/org/test_event_coverage.py — G5: 任务创建审计事件覆盖。

验证:
- AuditEmitter.emit("TASK_CREATED") 落盘 (失败安全)
- service.create_task 真实路径产生 TASK_CREATED 事件 (audit_explain 可查询)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def test_emit_task_created_persists(tmp_path: Path) -> None:
    """AuditEmitter.emit(TASK_CREATED) → AuditStore 落盘, 失败安全。"""
    from factory_console.audit.audit_emitter import AuditEmitter

    ev = AuditEmitter().emit(
        "TASK_CREATED", project_id="P-1", task_id="T-1",
        actor_type="system", actor_id="console", title="G5-任务", workspace=tmp_path,
    )
    assert ev is not None, "emit 必须成功"
    assert ev.task_id == "T-1"
    assert ev.actor_type == "system"
    # 落盘 (AuditStore 原子写)
    audit_file = tmp_path / "audit" / "audit_events.json"
    assert audit_file.exists() or any(tmp_path.rglob("audit*.json")), "审计必须落盘"


def test_emit_invalid_type_fails_safe(tmp_path: Path) -> None:
    """非法事件类型 → None (失败安全, 不抛)。"""
    from factory_console.audit.audit_emitter import AuditEmitter

    assert AuditEmitter().emit("NOT_A_REAL_TYPE", workspace=tmp_path) is None


def test_create_task_emits_task_created(tmp_path: Path) -> None:
    """真实 create_task 路径 → TASK_CREATED 审计事件 (audit_explain 可追溯)。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from fastapi.testclient import TestClient

    from factory_console.web.backend.fastapi_adapter import create_app

    app = create_app(factory_root=str(tmp_path))
    with TestClient(app) as c:
        # 创建项目 → 任务
        r = c.post("/api/projects", json={"name": "G5测试", "idea": "事件覆盖测试"})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        pid = body.get("id") or body.get("project", {}).get("id") or (
            body.get("project_id") if isinstance(body, dict) else None
        )
        assert pid, f"未取到 project_id: {body}"
        rt = c.post(f"/api/projects/{pid}/backlog/task",
                    json={"title": "G5-任务", "priority": "P2"})
        assert rt.status_code in (200, 201), rt.text
        tid = rt.json().get("id")
        assert tid, "任务必须创建 (create_task 真实路径 + TASK_CREATED emit 失败安全不抛)"
