"""tests/console/test_real_production_executor.py — R0 P0 Real Production Executor 测试。

覆盖 (任务 §十):
  T1 真实 NodeRun lifecycle CREATED→RUNNING→COMPLETED (磁盘状态正确)
  T2 失败 lifecycle CREATED→RUNNING→FAILED (failure evidence 存在)
  T3 execution events (NODE_RUN_STARTED / COMPLETED / FAILED, 真实产生)
  T4 真实 Artifact (真实 executor 产物内容, 非 "Default capability executed")
  T5 Verification 独立 (Agent 自报 ok 不能决定最终成功)
  T6 无假成功 (无 capability/executor → 诚实 FAILED; _default_capability 已移除)

全部为隔离单元测试 (tmp root, 注入 capability), 不触发外部 executor / 网络。
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from factory_console import production_runtime as pr  # noqa: E402
from factory_console.node_runtime import register_node  # noqa: E402
from factory_console.production_runtime import execute_task  # noqa: E402


# ---------------------------------------------------------------- helpers

def _register(root: Path, task_id: str) -> None:
    """生产路径由 golden_path 注册 node; 直接调内核的测试需显式注册。"""
    register_node(str(root), node_id=task_id, name=f"node-{task_id}",
                  node_type="plan_task",
                  input_contract={"goal": ""},
                  output_contract={"deliverable": "verified"},
                  execution_policy={"actor": "human", "source": "test"})


def _read_run(root: Path, run_id: str) -> dict[str, Any]:
    cand = list(glob.glob(str(root / "nodes" / "runs" / f"*{run_id}*.json")))
    assert cand, f"NodeRun 文件未找到: {run_id}"
    with open(cand[-1], encoding="utf-8") as fh:
        return json.load(fh)


def _read_events(root: Path) -> list[dict[str, Any]]:
    p = root / "audit" / "audit_events.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("events", d.get("items", []))


def _find_artifact(root: Path, artifact_id: str) -> dict[str, Any]:
    cand = glob.glob(str(root / "artifacts" / "ar" / f"{artifact_id}.json"))
    assert cand, f"Artifact 文件未找到: {artifact_id}"
    with open(cand[0], encoding="utf-8") as fh:
        return json.load(fh)


def _capability_success(ws: Path) -> Any:
    def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
        pdir = Path(input_data.get("project_dir") or ws)
        pdir.mkdir(parents=True, exist_ok=True)
        task = input_data.get("task") or {}
        marker = f"REAL_HTML_{task.get('id', 'T')}"
        (pdir / "index.html").write_text(
            f"<html><body>{marker}</body></html>", encoding="utf-8")
        return {
            "ok": True,
            "output": {"files": ["index.html"], "marker": marker},
            "error": "",
            "artifact_type": "code_change",
            "verification": {"result": "PASS", "source": "test file written",
                             "files": ["index.html"]},
        }

    return _fn


# ---------------------------------------------------------------- T1 成功生命周期
def test_success_lifecycle_persisted(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    input_data = {"goal": "做一个页面", "task": {"id": "T1", "title": "创建页面"},
                  "project_dir": str(ws)}
    _register(tmp_path, "T1")
    res = execute_task(str(tmp_path), "T1", project_id="conv-x",
                       input_data=input_data,
                       capability_fn=_capability_success(ws))
    assert res["state"] == "COMPLETED", res
    assert res["artifact_id"], res
    assert res["verification"] == "PASS"
    assert res["error"] is None

    run = _read_run(tmp_path, res["run_id"])
    assert run["state"] == "COMPLETED"          # 磁盘状态 = 返回值 (非 PENDING)
    assert run["started_at"] and run["completed_at"]
    assert run["executor"] == "capability"
    assert run["artifact_id"] == res["artifact_id"]
    assert isinstance(run.get("verification"), dict)
    assert run["verification"].get("verification_id")

    art = _find_artifact(tmp_path, res["artifact_id"])
    assert "REAL_HTML_T1" in json.dumps(art, ensure_ascii=False)
    assert "Default capability executed" not in json.dumps(art, ensure_ascii=False)

    evs = _read_events(tmp_path)
    started = [e for e in evs if e.get("event_type") == "NODE_RUN_STARTED"
               and str(e.get("trace_id", "")) == res["run_id"]]
    completed = [e for e in evs if e.get("event_type") == "NODE_RUN_COMPLETED"
                 and str(e.get("trace_id", "")) == res["run_id"]]
    assert started and completed, "真实 execution events 缺失"


# ---------------------------------------------------------------- T2 失败生命周期
def test_failure_lifecycle_persisted(tmp_path: Path) -> None:
    ws = tmp_path / "ws"

    def _cap_fail(input_data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "output": {}, "error": "boom: executor failed",
                "verification": {"result": "FAIL",
                                 "error": "boom: executor failed",
                                 "source": "test failure"}}

    _register(tmp_path, "T1")
    res = execute_task(str(tmp_path), "T1", project_id="conv-x",
                       input_data={"goal": "g", "task": {"id": "T1", "title": "t"},
                                   "project_dir": str(ws)},
                       capability_fn=_cap_fail)
    assert res["state"] == "FAILED", res
    assert "boom" in (res["error"] or "")

    run = _read_run(tmp_path, res["run_id"])
    assert run["state"] == "FAILED"
    assert run["failure_reason"]
    assert "boom" in run["failure_reason"]

    evs = _read_events(tmp_path)
    failed = [e for e in evs if e.get("event_type") == "NODE_RUN_FAILED"
              and str(e.get("trace_id", "")) == res["run_id"]]
    assert failed, "NODE_RUN_FAILED 事件缺失"


# ---------------------------------------------------------------- T5 Verification 独立
def test_agent_self_report_does_not_decide_success(tmp_path: Path) -> None:
    """capability ok=True 但 verification=FAIL → 最终 FAILED (Verification 独立)。"""
    ws = tmp_path / "ws"

    def _cap_self_ok(input_data: dict[str, Any]) -> dict[str, Any]:
        pdir = Path(input_data.get("project_dir") or ws)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "x.txt").write_text("self-claimed", encoding="utf-8")
        return {"ok": True, "output": "self-claimed done",
                "verification": {"result": "FAIL",
                                 "error": "verifier: 结构校验失败",
                                 "source": "real verifier"}}

    _register(tmp_path, "T1")
    res = execute_task(str(tmp_path), "T1", project_id="conv-x",
                       input_data={"goal": "g", "task": {"id": "T1", "title": "t"},
                                   "project_dir": str(ws)},
                       capability_fn=_cap_self_ok)
    assert res["state"] == "FAILED", (
        "Agent 自报 ok 不能决定最终成功: verification=FAIL 必须 FAILED")
    assert "verification" in (res["error"] or "") or "FAIL" in (res["error"] or "")


# ---------------------------------------------------------------- T6 无假成功
def test_no_capability_no_executor_is_honest_failure(tmp_path: Path) -> None:
    _register(tmp_path, "T1")
    res = execute_task(str(tmp_path), "T1", project_id="conv-x",
                       input_data={"goal": "g", "task": {"id": "T1", "title": "t"}})
    assert res["state"] == "FAILED", res
    assert "未配置执行能力" in (res["error"] or "")
    run = _read_run(tmp_path, res["run_id"])
    assert run["state"] == "FAILED"


def test_fake_default_capability_removed() -> None:
    """占位假成功 (_default_capability / 'Default capability executed') 已从内核移除。"""
    src = Path(_ROOT / "factory-console" / "production_runtime.py").read_text(
        encoding="utf-8")
    assert "_default_capability" not in src
    assert "Default capability executed" not in src


# ---------------------------------------------------------------- T4 真实 executor 产物
def test_artifact_contains_real_content(tmp_path: Path) -> None:
    """Artifact 载荷 = 真实 executor 输出 (非占位串)。"""
    ws = tmp_path / "ws"
    _register(tmp_path, "T1")
    res = execute_task(str(tmp_path), "T1", project_id="conv-x",
                       input_data={"goal": "做一个页面",
                                   "task": {"id": "T1", "title": "创建页面"},
                                   "project_dir": str(ws)},
                       capability_fn=_capability_success(ws))
    assert res["state"] == "COMPLETED"
    art = _find_artifact(tmp_path, res["artifact_id"])
    assert art.get("type") == "execution_output" or art.get("payload")
    payload = art.get("payload", {})
    assert isinstance(payload, dict)
    assert payload.get("marker") == "REAL_HTML_T1"


# ---------------------------------------------------------------- executor 解析 (诚实)
def test_build_real_executor_unknown_name_returns_none(tmp_path: Path) -> None:
    """未知 executor → None (调用方必须诚实 FAILED, 不虚构)。"""
    fn = pr.build_real_executor(str(tmp_path), executor_name="definitely-missing")
    assert fn is None
