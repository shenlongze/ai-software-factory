"""MU-CORE-13: Plugin Closure（Capability → Plugin → Provider → Execution → Verify/Evidence/Outcome）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org"),
           str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import os_core_capability as cap  # noqa: E402
from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import os_core_evidence as ev  # noqa: E402
from factory_console import os_core_execution as ex  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_outcome as out  # noqa: E402
from factory_console import os_core_plugin as plug  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_resolution as res  # noqa: E402
from factory_console import os_core_runtime as rt  # noqa: E402
from factory_console import os_core_task as task  # noqa: E402
from factory_console import os_core_task_node as tn  # noqa: E402
from factory_console import os_core_verification as ver  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _cap(root: str, name: str = "Backend Development") -> str:
    existing = next((c for c in cap.list_capabilities(root) if c["name"] == name), None)
    return (existing or cap.create_capability(root, name=name))["capability_id"]


def _fixture(root: str, company: str = "Acme", cap_id: str | None = None) -> dict:
    cid = osco.create_company(root, name=company)["id"]
    project = proj.create_project(root, name=f"{company} P", company_id=cid)
    w = work.create_work(root, project_id=project["id"], name=f"{company} Work")
    cap_id = cap_id or _cap(root)
    dom = next((d for d in prof.list_professional_domains(root)
                if d["name"] == "Software Engineering"), None)
    if dom is None:
        dom = prof.create_professional_domain(root, name="Software Engineering")
    pr = prof.resolve_professional_role(root, "Backend Engineer")
    if pr is None:
        pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                           name="Backend Engineer", capability_refs=[cap_id])
    wfk = wf.create_workforce(root, name=f"{company} Team", company_id=cid, capability_refs=[cap_id])
    wf.set_workforce_status(root, wfk["workforce_id"], "active")
    person = ident.create_identity(root, identity_type="human", company_id=cid,
                                   display_name=f"{company} Dev")
    wf.add_member(root, wfk["workforce_id"], person["identity_id"])
    t = task.create_task(root, work_id=w["work_id"], name="Task")
    node = tn.create_task_node(root, task_id=t["task_id"], name="Node",
                               required_capability_refs=[cap_id])
    resolution = res.resolve_task_node(root, node["task_node_id"])
    return {"company": cid, "project": project["id"], "work": w["work_id"],
            "capability": cap_id, "task": t["task_id"], "task_node": node["task_node_id"],
            "resolution": resolution["resolution_id"], "workforce": wfk["workforce_id"],
            "identity": person["identity_id"]}


def _ok_fn(cmd: str):
    def _fn(_i):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {"ok": p.returncode == 0, "output": p.stdout, "error": p.stderr,
                "artifact_type": "report"}
    return _fn


def _exec(root: str, f: dict) -> dict:
    return ex.create_execution(root, task_node_id=f["task_node"],
                               resolution_id=f["resolution"],
                               actor_identity_id=f["identity"], workforce_id=f["workforce"])


# ---------------------------------------------------------------- T1-T8 contract / binding

def test_t1_t8_plugin_contract_and_capability_binding(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _cap(root)
    p = plug.register_capability_plugin(root, plugin_id="p.local", name="Local Provider",
                                        capability_refs=[c], implementation_ref="provider:local")
    assert p["plugin_id"] == "p.local" and p["status"] == "ENABLED"          # T1/T4
    assert p["capability_refs"] == [c]
    assert plug.get_plugin_contract(root, "p.local")["implementation_ref"] == "provider:local"  # T2/T3
    # T8: 注册 plugin 不创建 Capability
    assert len(cap.list_capabilities(root)) == 1
    # T6: unknown capability rejected
    with pytest.raises(ValueError):
        plug.register_capability_plugin(root, plugin_id="p.bad", name="Bad",
                                        capability_refs=["CAP-nope"],
                                        implementation_ref="provider:local")
    # T7: retired capability rejected
    cap.set_capability_status(root, c, "retired")
    with pytest.raises(ValueError):
        plug.register_capability_plugin(root, plugin_id="p.retired", name="R",
                                        capability_refs=[c], implementation_ref="provider:local")
    cap.set_capability_status(root, c, "active")


# ---------------------------------------------------------------- T9-T15 resolution

def test_t9_t14_resolution_deterministic(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _cap(root)
    plug.register_capability_plugin(root, plugin_id="p.zzz", name="Z", capability_refs=[c],
                                    implementation_ref="provider:local")
    plug.register_capability_plugin(root, plugin_id="p.aaa", name="A", capability_refs=[c],
                                    implementation_ref="provider:local")
    r1 = plug.resolve_capability_plugin(root, c)
    assert r1["resolved"] is True and r1["plugin_id"] == "p.aaa"            # T9/T10 稳定排序
    assert plug.resolve_capability_plugin(root, c)["plugin_id"] == "p.aaa"
    # T14: capability mismatch → unresolved
    c2 = _cap(root, "Data Analysis")
    assert plug.resolve_capability_plugin(root, c2)["resolved"] is False
    # T11: no candidate
    assert plug.resolve_capability_plugin(root, "CAP-nope")["resolved"] is False


def test_t12_t13_lifecycle_excludes(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _cap(root)
    plug.register_capability_plugin(root, plugin_id="p.s", name="S", capability_refs=[c],
                                    implementation_ref="provider:local")
    plug.set_plugin_lifecycle(root, "p.s", "DISABLED")                      # T12
    assert plug.resolve_capability_plugin(root, c)["resolved"] is False
    plug.set_plugin_lifecycle(root, "p.s", "ENABLED")
    plug.set_plugin_lifecycle(root, "p.s", "RETIRED")                       # T13
    assert plug.resolve_capability_plugin(root, c)["resolved"] is False


def test_t15_company_scope_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _cap(root)
    a = _fixture(root, "Company A", c)["company"]
    b = _fixture(root, "Company B", c)["company"]
    plug.register_capability_plugin(root, plugin_id="p.a", name="A", capability_refs=[c],
                                    implementation_ref="provider:local", scope="company",
                                    company_id=a)
    assert plug.resolve_capability_plugin(root, c, company_id=a)["resolved"] is True
    assert plug.resolve_capability_plugin(root, c, company_id=b)["resolved"] is False  # T15
    with pytest.raises(ValueError):     # company 不存在拒绝
        plug.register_capability_plugin(root, plugin_id="p.x", name="X", capability_refs=[c],
                                        implementation_ref="provider:local", scope="company",
                                        company_id="C-nope")


# ---------------------------------------------------------------- T16-T25 execution / retry

def test_t16_t20_plugin_execution_trace(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    plug.register_capability_plugin(root, plugin_id="p.local", name="Local",
                                    capability_refs=[f["capability"]],
                                    implementation_ref="provider:local")
    e = _exec(root, f)
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id="p.local",
                                      executor_fn=_ok_fn("echo plugin-ok"))
    done = ex.get_execution(root, e["execution_id"])
    assert done["status"] == "succeeded" and done["node_run_id"]                  # T16
    assert done["plugin_id"] == "p.local"                                          # T19
    assert done["implementation_ref"] == "provider:local"                          # T20
    # T17/T18/T37: 无第二 Execution store
    assert not (tmp_path / "ops" / "plugins" / "executions.json").exists()
    assert (tmp_path / "execution" / "executions.json").is_file()


def test_t21_t25_failure_retry_preserves(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    plug.register_capability_plugin(root, plugin_id="p.local", name="Local",
                                    capability_refs=[f["capability"]],
                                    implementation_ref="provider:local")
    e1 = _exec(root, f)
    rt.run_execution_via_node_runtime(root, e1["execution_id"], prompt="fail", plugin_id="p.local",
                                      executor_fn=_ok_fn("exit 1"))
    e2 = _exec(root, f)
    rt.run_execution_via_node_runtime(root, e2["execution_id"], prompt="ok", plugin_id="p.local",
                                      executor_fn=_ok_fn("echo retry"))
    d1, d2 = ex.get_execution(root, e1["execution_id"]), ex.get_execution(root, e2["execution_id"])
    assert d1["status"] == "failed" and d2["status"] == "succeeded"                # T21/T22
    assert d1["node_run_id"] != d2["node_run_id"]                                  # T23
    assert ex.get_execution(root, e1["execution_id"])["status"] == "failed"        # T24
    assert tn.get_task_node(root, f["task_node"])["task_node_id"] == f["task_node"]  # T25


# ---------------------------------------------------------------- T26-T33 verification/evidence/governance

def test_t26_t29_verification_evidence_outcome(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    plug.register_capability_plugin(root, plugin_id="p.local", name="Local",
                                    capability_refs=[f["capability"]],
                                    implementation_ref="provider:local")
    e = _exec(root, f)
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id="p.local",
                                      executor_fn=_ok_fn("echo ok"))
    # T26: 执行成功 ≠ Outcome accepted (不自动)
    assert out.list_outcomes(root, execution_id=e["execution_id"]) == []
    v = ver.create_verification(root, execution_id=e["execution_id"], status="failed")
    evd = ev.create_evidence(root, execution_id=e["execution_id"], type="command_output",
                             source="node_runtime", locator=f"output:{e['execution_id']}",
                             verification_id=v["verification_id"])
    o = out.create_outcome(root, execution_id=e["execution_id"], status="rejected",
                           verification_refs=[v["verification_id"]], evidence_refs=[evd["evidence_id"]])
    assert o["status"] == "rejected"                                              # T27
    assert Path(ev.resolve_evidence(root, evd["evidence_id"])["resolved_path"]).is_file()  # T28
    with pytest.raises(ValueError):                                               # T29
        ev.create_evidence(root, execution_id=e["execution_id"], type="log",
                           source="llm", locator="llm says done")


def test_t30_t33_governance_rejections(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    other = _fixture(root, "Company B")["company"]
    plug.register_capability_plugin(root, plugin_id="p.local", name="Local",
                                    capability_refs=[f["capability"]],
                                    implementation_ref="provider:local")
    plug.register_capability_plugin(root, plugin_id="p.co", name="Co", capability_refs=[f["capability"]],
                                    implementation_ref="provider:local", scope="company",
                                    company_id=other)
    e = _exec(root, f)
    for pid, expect in (("p.nope", "不存在"), ("p.local", None)):
        try:
            rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id=pid,
                                              executor_fn=_ok_fn("echo x"))
        except ValueError as exc:
            assert expect in str(exc)
    # T31: DISABLED plugin 拒绝
    plug.set_plugin_lifecycle(root, "p.local", "DISABLED")
    with pytest.raises(ValueError):
        rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id="p.local",
                                          executor_fn=_ok_fn("echo x"))
    # T32: RETIRED 拒绝
    plug.set_plugin_lifecycle(root, "p.local", "RETIRED")
    with pytest.raises(ValueError):
        rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id="p.local",
                                          executor_fn=_ok_fn("echo x"))
    # T33: company mismatch 拒绝 (p.co 属于 Company B, TaskNode 属于 Company A)
    with pytest.raises(ValueError):
        rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x", plugin_id="p.co",
                                          executor_fn=_ok_fn("echo x"))


# ---------------------------------------------------------------- T34-T38 architecture

def test_t34_t38_architecture_boundaries(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    # T34: Scheduler 仍是调度者 (plugin 不调度)
    from factory_console import os_core_scheduler as sch
    r = sch.schedule_node(root, f["task_node"])
    assert r["scheduled"] is True
    # T35/T36: plugin boundary 不 import Scheduler/Execution Runtime/Provider
    src = (Path("factory-console") / "os_core_plugin.py").read_text()
    assert "os_core_scheduler" not in src and "external_executor" not in src and "subprocess" not in src
    # T37: plugin store 无 execution
    plug.register_capability_plugin(root, plugin_id="p.local", name="Local",
                                    capability_refs=[f["capability"]],
                                    implementation_ref="provider:local")
    assert not (tmp_path / "ops" / "plugins" / "executions.json").exists()
    # T38: Resolution 与 Execution 分离 (resolution store 无 executions)
    assert (tmp_path / "resolution" / "resolutions.json").is_file()
    assert not (tmp_path / "resolution" / "executions.json").exists()
