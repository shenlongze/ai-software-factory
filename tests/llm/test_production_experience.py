"""S14: Experience & Learning Foundation — Evidence-backed 生产经验。

覆盖:
1. Experience contract (evidence_refs/source refs)
2. Evidence requirement
3. deterministic extraction
4. confidence calculation
5. persistence
6. lifecycle (ACTIVE/SUPERSEDED/INVALIDATED)
7. active retrieval
8. invalidated filtering
9. superseded filtering
10. deterministic ranking
11. retrieval reproducibility
12. idempotent extraction
13. outcome recording
14. confidence update
15. CLI
16. API
17. production evidence → experience E2E
18. experience → retrieval E2E
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_experience import (  # noqa: E402
    extract, retrieve, list_experiences, get_experience, supersede, invalidate,
    record_outcome, _tokenize,
)
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
    _write,
)
from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run,
)
from factory_console.professional_workflow import (  # noqa: E402
    BUILTIN_CALC_TESTS, verify_code_with_pytest,
)


def _success_production(tmp_path) -> str:
    """成功 ProductionRun (COMPLETED + verification PASS)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")

    def factory(node_id):
        def fn(input_data):
            patch = (f"diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
                     "@@ -0,0 +1,2 @@\n+def a():\n+    return 1\n")
            return {"ok": True, "output": {"code": "a"}, "patch_text": patch,
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS", "tests": 1}}
        return fn
    done = execute_production_run(str(tmp_path), run["run_id"], executor_factory=factory,
                                  artifact_root=str(tmp_path))
    assert done["state"] == "COMPLETED"
    return run["run_id"]


def _repair_production(tmp_path) -> str:
    """带 Repair 的 ProductionRun (attempt1 FAIL → repair → attempt2 PASS)。"""
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "dev", "name": "dev", "type": "engineering", "executor_name": "dev"}])
    run = create_production_run(str(tmp_path), "wf-1")
    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")
    bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")

    def exec_fn(input_data):
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        ver = verify_code_with_pytest(good_code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": good_code},
                "patch_text": "", "artifact_type": "code_change", "verification": ver,
                "content": good_code}
    nr = create_node_run(str(tmp_path), "dev", input_data={"_code": bad_code})
    done_a = execute_node_run(str(tmp_path), nr["run_id"], executor_fn=exec_fn,
                              executor_name="dev", artifact_root=str(tmp_path),
                              max_attempts=2, repair_fn=repair_fn)
    assert done_a["state"] == "COMPLETED"
    prun = get_production_run(str(tmp_path), run["run_id"])
    prun["state"] = "COMPLETED"
    prun["status"] = "COMPLETED"
    prun["node_runs"] = [{"node_id": "dev", "run_id": nr["run_id"],
                          "state": "COMPLETED", "artifact_id": done_a["artifact_id"]}]
    prun["artifacts"] = [done_a["artifact_id"]]
    _write(str(tmp_path), prun)
    return run["run_id"]


def _failed_production(tmp_path) -> str:
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "a", "name": "A", "type": "engineering", "executor_name": "a"}])
    run = create_production_run(str(tmp_path), "wf-1")

    def bad_factory(node_id):
        def fn(input_data):
            return {"ok": False, "error": "boom", "artifact_type": "report",
                    "verification": {"result": "FAIL"}}
        return fn
    execute_production_run(str(tmp_path), run["run_id"], executor_factory=bad_factory,
                           artifact_root=str(tmp_path))
    return run["run_id"]


# --- 1/2. contract + evidence requirement ---

def test_experience_contract(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    assert e["id"].startswith("exp-")
    assert e["source_production_run_id"] == rid
    assert e["source_evaluation_id"].startswith("eval-")
    assert e["evidence_refs"]["production_run_id"] == rid
    assert e["evidence_refs"]["artifacts"], "evidence_refs 非空"
    assert e["status"] == "ACTIVE"
    assert "confidence" in e


# --- 3. deterministic extraction ---

def test_deterministic_extraction(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    assert e["type"] == "DEBUG_EXPERIENCE"  # 有 repair → debug 经验
    assert "repair" in e["problem"].lower()
    # 成功生产 → SUCCESS_PATTERN
    rid2 = _success_production(tmp_path)
    e2 = extract(str(tmp_path), rid2)
    assert e2["type"] == "SUCCESS_PATTERN"


# --- 4. confidence ---

def test_confidence(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    # 成功 + verification + lineage + workspace → 100 (conf 1.0)
    assert e["confidence"] == 1.0
    # 失败生产 → 低 confidence
    rid2 = _failed_production(tmp_path)
    e2 = extract(str(tmp_path), rid2)
    assert e2["confidence"] < 0.5
    assert e2["status"] == "CANDIDATE"


# --- 5. persistence ---

def test_persistence(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    loaded = get_experience(str(tmp_path), e["id"])
    assert loaded is not None
    assert loaded["source_production_run_id"] == rid
    assert len(list_experiences(str(tmp_path))) >= 1


# --- 6/8/9. lifecycle + filtering ---

def test_lifecycle_filtering(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    eid = e["id"]
    # invalidate → retrieve 排除
    invalidate(str(tmp_path), eid, reason="test invalid")
    assert get_experience(str(tmp_path), eid)["status"] == "INVALIDATED"
    assert retrieve(str(tmp_path), "calculator divide pytest") == []
    # supersede → retrieve 排除
    rid2 = _success_production(tmp_path)
    e2 = extract(str(tmp_path), rid2)
    supersede(str(tmp_path), e2["id"], "exp-new", reason="newer")
    assert get_experience(str(tmp_path), e2["id"])["status"] == "SUPERSEDED"
    assert e2["id"] not in [x["id"] for x in retrieve(str(tmp_path), "production")]


# --- 7. active retrieval ---

def test_retrieval_finds_active(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    results = retrieve(str(tmp_path), "calculator divide pytest failure")
    assert any(x["id"] == e["id"] for x in results), "相关经验必须被检索到"


# --- 10/11. deterministic ranking + reproducibility ---

def test_retrieval_deterministic(tmp_path):
    rid = _repair_production(tmp_path)
    extract(str(tmp_path), rid)
    r1 = retrieve(str(tmp_path), "calculator divide")
    r2 = retrieve(str(tmp_path), "calculator divide")
    assert [x["id"] for x in r1] == [x["id"] for x in r2], "同 query → 同顺序"


# --- 12. idempotent extraction ---

def test_idempotent_extraction(tmp_path):
    rid = _repair_production(tmp_path)
    e1 = extract(str(tmp_path), rid)
    e2 = extract(str(tmp_path), rid)
    assert e1["id"] == e2["id"], "幂等: 不重复生成"
    # force 重新提取 → 新 id (但旧记录仍在)
    e3 = extract(str(tmp_path), rid, force=True)
    assert e3["id"] != e1["id"]


# --- 13/14. outcome + confidence update ---

def test_outcome_confidence(tmp_path):
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    eid = e["id"]
    # 2 成功 1 失败 → confidence 更新 (一次成功 ≠ 100%)
    record_outcome(str(tmp_path), eid, "prun-future-1", success=True)
    record_outcome(str(tmp_path), eid, "prun-future-2", success=True)
    after = record_outcome(str(tmp_path), eid, "prun-future-3", success=False)
    assert after["success_count"] == 2
    assert after["failure_count"] == 1
    assert after["confidence"] < 1.0, "统计置信度拉低"


# --- 15. CLI ---

def test_cli_experience(tmp_path):
    rid = _repair_production(tmp_path)
    extract(str(tmp_path), rid)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["experience", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["experience", "extract", rid, "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["experience", "retrieve", "calculator divide", "--data-dir", str(tmp_path)]) == 0


# --- 16. API ---

def test_api_experience(tmp_path):
    rid = _repair_production(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    # extract
    resp = client.post(f"/api/production-runs/{rid}/experience", json={})
    assert resp.status_code == 200
    eid = resp.json()["id"]
    # list
    resp = client.get("/api/experiences")
    assert resp.status_code == 200
    assert any(x["id"] == eid for x in resp.json()["items"])
    # get
    resp = client.get(f"/api/experiences/{eid}")
    assert resp.status_code == 200
    # retrieve (匹配 repair 经验内容)
    resp = client.post("/api/experiences/retrieve", json={"context": "repair production"})
    assert resp.status_code == 200
    assert any(x["id"] == eid for x in resp.json()["items"])


# --- 17/18. E2E: evidence → experience → retrieval ---

def test_evidence_to_experience_retrieval_e2e(tmp_path):
    """Production evidence → Experience → Retrieval 全链。"""
    rid = _repair_production(tmp_path)
    e = extract(str(tmp_path), rid)
    # 检索 "repair" 上下文 → 找到
    results = retrieve(str(tmp_path), "repair production")
    assert any(x["id"] == e["id"] for x in results)
    # evidence 可回溯
    assert get_experience(str(tmp_path), e["id"])["evidence_refs"]["evaluation_id"]
