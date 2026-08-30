"""S39: Autonomous Recovery & Self-Healing。

覆盖:
- Incident (evidence-driven, 非 LLM; 来源白名单)
- Diagnosis (FACT/HYPOTHESIS/UNKNOWN)
- RepairCandidate (Proposal; Plugin 解析)
- Repair Strategy Plugin (type=repair; disabled 拒绝; 替换不修改 Core)
- Self-Healing 完整闭环 (Incident→Diagnosis→RepairCandidate→Evaluation→Governance→Canary→Promotion→Recovery Evidence)
- Human Gate (HIGH/CRITICAL non-human → UNRESOLVED)
- Canary FAIL → ROLLED_BACK (S21 语义)
- Recovery Evidence → S37 Learning
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.plugin_kernel import (  # noqa: E402
    bootstrap, register_plugin, plugin_status,
)
from factory_console.self_healing import (  # noqa: E402
    create_incident, create_diagnosis, create_repair_candidate,
    register_repair_plugin, _coderepair_plugin, run_self_healing,
    recovery_status, recovery_history, incidents, REPAIR_PLUGINS,
    _transition,
)


def _setup(tmp_path):
    bootstrap(str(tmp_path))
    register_plugin(str(tmp_path), plugin_id="repair.coderepair", name="CodeRepair",
                    version="1.0", type="repair", capabilities=["repair.code"],
                    permissions=["repair.execute"])
    plugin_status(str(tmp_path), "repair.coderepair", target="ENABLED")
    register_repair_plugin("repair.coderepair", _coderepair_plugin)


def _good_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"repaired": True},
                "patch_text": ("diff --git a/fix.py b/fix.py\n--- /dev/null\n+++ b/fix.py\n"
                               "@@ -0,0 +1 @@\n+def fixed():\n+    return True\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _bad_factory(node_id):
    def fn(input_data):
        raise RuntimeError("repair crashed")
    return fn


# --- Incident 必须来自真实 Evidence ---

def test_incident_requires_evidence(tmp_path):
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r1",
                          node_id="n1", failure_type="syntax_error")
    assert inc["incident_id"].startswith("inc-")
    assert inc["evidence_refs"] == ["verification:r1"]
    assert inc["status"] == "DETECTED"
    with pytest.raises(ValueError, match="非法 incident 来源"):
        create_incident(str(tmp_path), source="llm", production_run_id="r",
                        node_id="n", failure_type="x")


# --- Incident Lifecycle ---

def test_incident_lifecycle(tmp_path):
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="x")
    with pytest.raises(ValueError, match="非法状态迁移"):
        _transition(str(tmp_path), inc["incident_id"], target="RECOVERED")  # DETECTED→RECOVERED 非法
    _transition(str(tmp_path), inc["incident_id"], target="TRIAGED")
    st = recovery_status(str(tmp_path), inc["incident_id"])
    assert st["status"] == "TRIAGED"
    assert len(st["history"]) >= 1


# --- Diagnosis (FACT/HYPOTHESIS/UNKNOWN) ---

def test_diagnosis(tmp_path):
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="x")
    dia = create_diagnosis(str(tmp_path), inc["incident_id"], kind="FACT",
                           statement="pytest failed", evidence_refs=["verification:r"])
    assert dia["kind"] == "FACT"
    assert dia["evidence_refs"] == ["verification:r"]
    with pytest.raises(ValueError):
        create_diagnosis(str(tmp_path), inc["incident_id"], kind="GUESS",
                         statement="x", evidence_refs=[])


# --- RepairCandidate (Proposal) ---

def test_repair_candidate(tmp_path):
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="x")
    rc = create_repair_candidate(str(tmp_path), inc["incident_id"],
                                 repair_strategy_plugin_id="repair.coderepair",
                                 target="node", proposed_change="fix", risk="MEDIUM")
    assert rc["candidate_id"].startswith("rc-")
    assert rc["repair_strategy_plugin_id"] == "repair.coderepair"
    with pytest.raises(ValueError):
        create_repair_candidate(str(tmp_path), inc["incident_id"],
                                repair_strategy_plugin_id="repair.coderepair",
                                target="n", proposed_change="x", risk="EXTREME")


# --- Repair Plugin 治理 (disabled 拒绝) ---

def test_repair_plugin_disabled(tmp_path):
    _setup(tmp_path)
    plugin_status(str(tmp_path), "repair.coderepair", target="DISABLED")
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="x")
    with pytest.raises(PermissionError, match="未启用"):
        run_self_healing(str(tmp_path), inc["incident_id"],
                         executor_factory=_good_factory, artifact_root=str(tmp_path),
                         risk="LOW")
    plugin_status(str(tmp_path), "repair.coderepair", target="ENABLED")


# --- Self-Healing 完整闭环 (成功) ---

def test_self_healing_recovered(tmp_path):
    _setup(tmp_path)
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r1",
                          node_id="n1", failure_type="syntax_error",
                          severity="MEDIUM", detail="fix")
    result = run_self_healing(str(tmp_path), inc["incident_id"],
                              executor_factory=_good_factory, artifact_root=str(tmp_path),
                              risk="MEDIUM")
    assert result["status"] == "RECOVERED"
    assert result["diagnosis_id"]
    assert result["candidate_id"]
    assert result["promotion_snapshot"]
    st = recovery_status(str(tmp_path), inc["incident_id"])
    assert st["status"] == "RECOVERED"
    # 完整 lifecycle 链
    tos = [h["to"] for h in st["history"]]
    assert tos == ["TRIAGED", "DIAGNOSING", "REPAIR_PROPOSED", "REPAIR_EVALUATING",
                   "GOVERNED", "CANARY", "RECOVERED"]


# --- Human Gate (HIGH/CRITICAL non-human → UNRESOLVED) ---

def test_self_healing_human_gate(tmp_path):
    _setup(tmp_path)
    inc = create_incident(str(tmp_path), source="health", production_run_id="r",
                          node_id="n", failure_type="core_crash", severity="CRITICAL")
    result = run_self_healing(str(tmp_path), inc["incident_id"],
                              executor_factory=_good_factory, artifact_root=str(tmp_path),
                              risk="CRITICAL", human_actor="system")
    assert result["status"] == "UNRESOLVED"
    assert "human_gate" in result["reason"]


# --- Canary FAIL → ROLLED_BACK (S21 语义) ---

def test_self_healing_canary_fail_rollback(tmp_path):
    _setup(tmp_path)
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="test_fail", severity="LOW")
    result = run_self_healing(str(tmp_path), inc["incident_id"],
                              executor_factory=_bad_factory, artifact_root=str(tmp_path),
                              risk="LOW")
    assert result["status"] == "ROLLED_BACK"
    assert "canary_failed" in result["reason"]
    assert recovery_status(str(tmp_path), inc["incident_id"])["status"] == "ROLLED_BACK"


# --- Repair Plugin 替换 (Core 零修改) ---

def test_repair_plugin_replacement(tmp_path):
    _setup(tmp_path)
    register_plugin(str(tmp_path), plugin_id="repair.alt", name="Alt", version="2.0",
                    type="repair", capabilities=["repair.code"], permissions=["repair.execute"])
    plugin_status(str(tmp_path), "repair.alt", target="ENABLED")

    def alt_plugin(action, payload):
        if action == "diagnose":
            return {"kind": "HYPOTHESIS", "confidence": "inferred"}
        if action == "repair":
            return {"patch": "alt-patch", "repair_strategy": "alt.v2"}
        return {}
    register_repair_plugin("repair.alt", alt_plugin)
    assert "repair.alt" in REPAIR_PLUGINS  # 注册成功 (Core 零修改)
    # 直接调用验证
    assert REPAIR_PLUGINS["repair.alt"]("repair", {})["repair_strategy"] == "alt.v2"


# --- Recovery Evidence → S37 Learning ---

def test_recovery_evidence_learning(tmp_path):
    _setup(tmp_path)
    inc = create_incident(str(tmp_path), source="verification", production_run_id="r",
                          node_id="n", failure_type="pattern_x", severity="LOW")
    result = run_self_healing(str(tmp_path), inc["incident_id"],
                              executor_factory=_good_factory, artifact_root=str(tmp_path),
                              risk="LOW")
    assert result["status"] == "RECOVERED"
    # Recovery Evidence 进入 S37 Observation (不直接改 Production)
    from factory_console.learning_engine_v2 import observations
    obs = observations(str(tmp_path), pattern_key="pattern_x")
    assert any(o["source_type"] == "recovery" for o in obs)


# --- CLI ---

def test_cli_heal(tmp_path):
    _setup(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["heal", "incident", "--run-id", "r1", "--failure-type", "x",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["heal", "history", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_heal(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/incidents",
                       json={"source": "verification", "production_run_id": "r1",
                             "node_id": "n1", "failure_type": "x"})
    assert resp.status_code == 200
    inc = resp.json()
    assert inc["incident_id"].startswith("inc-")
    resp = client.post("/api/incidents",
                       json={"source": "llm", "production_run_id": "r",
                             "node_id": "n", "failure_type": "x"})
    assert resp.status_code == 400  # 非法来源
    resp = client.get("/api/incidents")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    resp = client.get(f"/api/incidents/{inc['incident_id']}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "DETECTED"
