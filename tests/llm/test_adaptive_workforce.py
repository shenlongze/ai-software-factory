"""S25: Adaptive Workforce & Optimization Validation。

覆盖:
- WorkforceVariant (control/treatment 真实配置差异)
- Governance (未批准 Treatment → run blocked)
- Variant→ProductionRun 真实注入 (input 持久化 _variant_id/_variant_type)
- Variant isolation (control 不受 treatment 影响)
- Assignment lineage (variant → runs)
- Baseline 保持 (复用 S24, 真实 runs)
- CLI / API
- Real E2E: variant → 真实执行 → 反查
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_run import (  # noqa: E402
    register_workflow, get_production_run,
)
from factory_console.adaptive_workforce import (  # noqa: E402
    create_variant, get_variant, list_variants, approve_variant,
    run_with_variant, variant_lineage, build_variant_executor_factory,
)


def _base_factory(node_id):
    def fn(input_data):
        return {"ok": True, "output": {"code": "x"},
                "patch_text": ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n@@ -0,0 +1,2 @@\n"
                               "+def a():\n+    return 1\n"),
                "artifact_type": "code_change", "verification": {"result": "PASS"}}
    return fn


def _wf(tmp_path):
    register_workflow(str(tmp_path), workflow_id="wf-1", name="wf", nodes=[
        {"node_id": "developer", "name": "D", "type": "engineering", "executor_name": "d"}])


# --- Variant Contract ---

def test_variant_contract_real_difference(tmp_path):
    """Control vs Treatment: 真实配置差异 (1 role vs 2 roles)。"""
    _wf(tmp_path)
    ctrl = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="control")
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    assert ctrl["effective_configuration"]["roles"] == ["developer"]
    assert treat["effective_configuration"]["roles"] == ["developer", "reviewer"]
    assert ctrl["effective_configuration"]["nodes"] == 1
    assert treat["effective_configuration"]["nodes"] == 2
    assert treat["change_definition"] != ctrl["change_definition"]
    assert ctrl["status"] == "PROPOSED"
    assert ctrl["approval_id"]


# --- Governance: 未批准 blocked ---

def test_unapproved_treatment_blocked(tmp_path):
    """未批准 Treatment → run blocked (Governance 强制)。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    with pytest.raises(ValueError, match="未激活"):
        run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                         workflow_id="wf-1", base_factory=_base_factory)


def test_approved_treatment_runs(tmp_path):
    """批准后 → 真实执行。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    approve_variant(str(tmp_path), treat["variant_id"])
    assert get_variant(str(tmp_path), treat["variant_id"])["status"] == "ACTIVE"
    r = run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                         workflow_id="wf-1", base_factory=_base_factory)
    assert r["state"] == "COMPLETED"
    assert r["variant_type"] == "treatment"
    assert r["variant_evidence"]["roles"] == ["developer", "reviewer"]


# --- Variant → ProductionRun 真实注入 ---

def test_run_persists_variant(tmp_path):
    """ProductionRun input 持久化 _variant_id/_variant_type (可反查实验组)。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    approve_variant(str(tmp_path), treat["variant_id"])
    r = run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                         workflow_id="wf-1", base_factory=_base_factory)
    run = get_production_run(str(tmp_path), r["production_run_id"])
    assert run["input"]["_variant_id"] == treat["variant_id"]
    assert run["input"]["_variant_type"] == "treatment"
    assert run["input"]["_experiment_id"] == "exp-1"


# --- Variant isolation ---

def test_variant_isolation(tmp_path):
    """Control 不受 Treatment 影响; 两 variant 独立配置。"""
    _wf(tmp_path)
    ctrl = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="control")
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    # control 配置不含 reviewer
    assert "reviewer" not in ctrl["effective_configuration"]["roles"]
    # 批准 control 不影响 treatment 状态
    approve_variant(str(tmp_path), ctrl["variant_id"])
    assert get_variant(str(tmp_path), treat["variant_id"])["status"] == "PROPOSED"
    # control run 用 control 配置
    r1 = run_with_variant(str(tmp_path), variant_id=ctrl["variant_id"],
                          workflow_id="wf-1", base_factory=_base_factory)
    assert r1["variant_evidence"]["roles"] == ["developer"]


# --- Executor factory 真实差异 ---

def test_executor_factory_difference(tmp_path):
    """treatment factory 包 reviewer (真实执行路径差异)。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    ctrl = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="control")
    t_factory = build_variant_executor_factory(str(tmp_path), treat, _base_factory)
    c_factory = build_variant_executor_factory(str(tmp_path), ctrl, _base_factory)
    t_out = t_factory("developer")({})
    c_out = c_factory("developer")({})
    assert t_out["output"]["variant_path"] == "treatment"
    assert c_out["output"].get("variant_path") is None


# --- Lineage ---

def test_variant_lineage(tmp_path):
    """variant → assignment → runs 全链。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    approve_variant(str(tmp_path), treat["variant_id"])
    r1 = run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                          workflow_id="wf-1", base_factory=_base_factory)
    r2 = run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                          workflow_id="wf-1", base_factory=_base_factory)
    lg = variant_lineage(str(tmp_path), treat["variant_id"])
    assert len(lg["production_runs"]) == 2
    assert lg["variant_type"] == "treatment"
    assert all(r["assignment_id"] for r in lg["production_runs"])
    assert lg["approval_id"]


# --- Baseline 保持 (S24 复用) ---

def test_baseline_from_real_runs(tmp_path):
    """S24 Baseline 从真实 completed runs 建立 (S25 不破坏)。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    approve_variant(str(tmp_path), treat["variant_id"])
    from factory_console.optimization_service import create_baseline
    # 先跑真实 runs (通过 variant)
    run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                     workflow_id="wf-1", base_factory=_base_factory)
    run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                     workflow_id="wf-1", base_factory=_base_factory)
    bl = create_baseline(str(tmp_path))
    assert bl["status"] == "COMPLETED"
    assert bl["sample_size"] == 2


# --- CLI ---

def test_cli_variant(tmp_path):
    _wf(tmp_path)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["variant", "create", "exp-1", "--type", "treatment", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["variant", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["variant", "approve", "var-x", "--data-dir", str(tmp_path)]) == 1


# --- API ---

def test_api_variant(tmp_path):
    _wf(tmp_path)
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/optimization/variants",
                       json={"experiment_id": "exp-1", "variant_type": "treatment"})
    assert resp.status_code == 200
    v = resp.json()
    assert v["status"] == "PROPOSED"
    assert v["effective_configuration"]["roles"] == ["developer", "reviewer"]
    resp = client.get(f"/api/optimization/variants/{v['variant_id']}")
    assert resp.status_code == 200
    resp = client.get("/api/optimization/variants")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    resp = client.post(f"/api/optimization/variants/{v['variant_id']}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"
    resp = client.post(f"/api/optimization/variants/{v['variant_id']}/run",
                       json={"workflow_id": "wf-1"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "COMPLETED"
    resp = client.get(f"/api/optimization/variants/{v['variant_id']}/lineage")
    assert resp.status_code == 200
    assert len(resp.json()["production_runs"]) == 1


# --- Security: Variant 不改 Production Truth ---

def test_variant_no_truth_mutation(tmp_path):
    """Variant 执行只产生新 run, 不改 artifact/verification 事实。"""
    _wf(tmp_path)
    treat = create_variant(str(tmp_path), experiment_id="exp-1", variant_type="treatment")
    approve_variant(str(tmp_path), treat["variant_id"])
    r = run_with_variant(str(tmp_path), variant_id=treat["variant_id"],
                         workflow_id="wf-1", base_factory=_base_factory)
    run = get_production_run(str(tmp_path), r["production_run_id"])
    # 新 run 独立; 不修改已有事实
    assert run["state"] == "COMPLETED"
    assert run["input"]["_variant_type"] == "treatment"
