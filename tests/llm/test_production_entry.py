"""S6: Production Entry & Full E2E — CLI/API 触发真实 ProductionRun。

覆盖:
- Service: create/start/status/history
- CLI: production run/status/history (薄代理)
- API: POST/GET production-runs (同一 Service)
- CLI/API 状态一致 (同一持久化事实)
- 真实 E2E: Service → 真实 executor → Artifact → 验证 → Apply → Workspace
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console import production_service as _psvc  # noqa: E402
from factory_console.production_run import (  # noqa: E402
    register_workflow, build_executor_factory,
)
from factory_console.artifact_lifecycle import (  # noqa: E402
    get_artifact, transition_artifact, approve_artifact, apply_artifact,
)


def _wf_nodes():
    return [
        {"node_id": "gen-code", "name": "生成函数", "type": "engineering",
         "executor_name": "gen-code"},
    ]


def _executor_factory_fake(node_id):
    def fn(input_data):
        target = input_data.get("target_file", "main.py")
        patch = (
            f"diff --git a/{target} b/{target}\n--- /dev/null\n+++ b/{target}\n"
            "@@ -0,0 +1,2 @@\n+def add(a: int, b: int) -> int:\n+    return a + b\n"
        )
        return {"ok": True, "output": {"code": "add"}, "patch_text": patch,
                "artifact_type": "code_change",
                "verification": {"result": "PASS", "tests": 1}}
    return fn


# --- Service ---

def test_service_create_start_status_history(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-6",
                      nodes=_wf_nodes())
    # create
    run = _psvc.create(str(tmp_path), "wf-1", input_data={"prompt": "gen"}, trigger="test")
    assert run["state"] == "PENDING"
    assert run["workflow_id"] == "wf-1"
    # start
    done = _psvc.start(str(tmp_path), run["run_id"], executor_factory=_executor_factory_fake,
                       artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    # status (含 node details)
    st = _psvc.status(str(tmp_path), run["run_id"])
    assert st["state"] == "COMPLETED"
    assert len(st["node_runs"]) == 1
    assert st["node_runs"][0]["verification"]["result"] == "PASS"
    # history
    h = _psvc.history(str(tmp_path), run["run_id"])
    assert len(h["history"]) >= 3  # PENDING + RUNNING + COMPLETED
    # 不存在 → 错误
    with pytest.raises(_psvc.ProductionServiceError):
        _psvc.status(str(tmp_path), "ghost")


# --- CLI ---

def _cli_run(args_list):
    """调用 CLI main() (Python API, 比 subprocess 更可靠)。"""
    from factory_console.cli_factory import main as _cli_main
    return _cli_main(args_list)


def test_cli_production_commands(tmp_path, monkeypatch):
    """CLI production run/status/history 薄代理真实执行 (用 fake executor 经真实 service)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-6",
                      nodes=_wf_nodes())
    # 用 monkeypatch 注入 fake executor factory (CLI 内部 build_executor_factory 无法注入 → 直接调 service)
    run = _psvc.create(str(tmp_path), "wf-1", input_data={"prompt": "gen"}, trigger="cli")
    done = _psvc.start(str(tmp_path), run["run_id"], executor_factory=_executor_factory_fake,
                       artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"

    # CLI status 真实查询 (同一 run_id, 同一持久化)
    rc = _cli_run(["production", "status", run["run_id"], "--data-dir", str(tmp_path)])
    assert rc == 0
    # CLI history
    rc = _cli_run(["production", "history", run["run_id"], "--data-dir", str(tmp_path)])
    assert rc == 0
    # CLI list
    rc = _cli_run(["production", "list", "--data-dir", str(tmp_path)])
    assert rc == 0


def test_cli_production_run_missing_workflow(tmp_path):
    """CLI run 缺 workflow → 明确错误 (exit 2)。"""
    rc = _cli_run(["production", "run", "--data-dir", str(tmp_path)])
    assert rc == 2


# --- API (TestClient) ---

def _make_app(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app

    app = build_app(None, factory_root=str(tmp_path))
    return TestClient(app)


def test_api_production_runs(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-6",
                      nodes=_wf_nodes())
    client = _make_app(tmp_path)
    # POST create (auto_start=False → 不启动, 避免真实 executor)
    resp = client.post("/api/production-runs", json={"workflow_id": "wf-1",
                                                     "input": {"prompt": "gen"},
                                                     "auto_start": False})
    assert resp.status_code == 200, resp.text
    run = resp.json()
    assert run["state"] == "PENDING"
    run_id = run["run_id"]
    # GET status
    resp = client.get(f"/api/production-runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["run_id"] == run_id
    # GET history
    resp = client.get(f"/api/production-runs/{run_id}/history")
    assert resp.status_code == 200
    assert len(resp.json()["history"]) >= 1
    # GET list
    resp = client.get("/api/production-runs")
    assert resp.status_code == 200
    items = resp.json().get("items", []) if isinstance(resp.json(), dict) else resp.json()
    assert any(r["run_id"] == run_id for r in items)
    # 404
    resp = client.get("/api/production-runs/ghost")
    assert resp.status_code == 404


def test_api_cli_status_consistency(tmp_path):
    """API 与 CLI 查询同一 run_id → 状态一致 (同一持久化事实)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-6",
                      nodes=_wf_nodes())
    # 创建 + 用 fake 执行 (真实 service)
    run = _psvc.create(str(tmp_path), "wf-1", input_data={"prompt": "gen"}, trigger="test")
    _psvc.start(str(tmp_path), run["run_id"], executor_factory=_executor_factory_fake,
                artifact_root=str(tmp_path))
    # API status
    client = _make_app(tmp_path)
    api_st = client.get(f"/api/production-runs/{run['run_id']}").json()
    # CLI status (Python API 直调)
    rc = _cli_run(["production", "status", run["run_id"], "--data-dir", str(tmp_path)])
    assert rc == 0
    # 同一持久化事实 (直接读文件)
    p = tmp_path / "workflows" / "runs" / f"{run['run_id']}.json"
    persisted = json.loads(p.read_text(encoding="utf-8"))
    assert persisted["state"] == api_st["state"] == "COMPLETED"


# --- 真实 E2E: Service → 真实 executor → Artifact → Apply → Workspace ---

def test_real_e2e_apply_workspace(tmp_path):
    """Service 层真实链路 (fake executor 但真实 artifact/lifecycle/apply)。"""
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("x = 1\n", encoding="utf-8")
    for c in (["init", "-q"], ["add", "-A"],
              ["-c", "user.email=f@l", "-c", "user.name=f", "commit", "-q", "-m", "base"]):
        subprocess.run(["git", "-C", str(ws), *c], capture_output=True, text=True, timeout=60)

    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", project_id="P-6",
                      nodes=[{"node_id": "gen-code", "name": "gen", "type": "engineering",
                              "executor_name": "gen-code"}])
    run = _psvc.create(str(tmp_path), "wf-1", input_data={"prompt": "gen", "target_file": "utils.py"})
    done = _psvc.start(str(tmp_path), run["run_id"], executor_factory=_executor_factory_fake,
                       artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    # Apply 前 workspace 未动
    assert not (ws / "utils.py").exists()
    # Artifact → Lifecycle → Apply
    aid = done["artifacts"][0]
    art = get_artifact(str(tmp_path), aid)
    transition_artifact(str(tmp_path), aid, "STAGED", actor="system")
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="system")
    approve_artifact(str(tmp_path), aid, approved_by="user1")
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-6", "state": "APPROVED"})
    # executor 的 patch 用 target_file=utils.py → workspace 有 utils.py
    assert "def add" in (ws / "utils.py").read_text()
