"""MU-CORE-10: Execution Runtime + Verification/Evidence/Outcome 最小闭环 (T1-T30 适用项)。"""
from __future__ import annotations

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
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_resolution as res  # noqa: E402
from factory_console import os_core_runtime as rt  # noqa: E402
from factory_console import os_core_task as task  # noqa: E402
from factory_console import os_core_task_node as tn  # noqa: E402
from factory_console import os_core_verification as ver  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _get_or_create_cap(root: str, name: str) -> str:
    existing = next((c for c in cap.list_capabilities(root) if c["name"] == name), None)
    return (existing or cap.create_capability(root, name=name))["capability_id"]


def _chain(root: str, company: str = "Acme") -> dict:
    company_id = osco.create_company(root, name=company)["id"]
    project = proj.create_project(root, name=f"{company} P", company_id=company_id)
    w = work.create_work(root, project_id=project["id"], name=f"{company} Work")
    ws = work.create_workstream(root, work_id=w["work_id"], name="Frontend")
    cap_id = _get_or_create_cap(root, "Backend Development")
    dom = next((d for d in prof.list_professional_domains(root)
                if d["name"] == "Software Engineering"), None)
    if dom is None:
        dom = prof.create_professional_domain(root, name="Software Engineering")
    pr = prof.resolve_professional_role(root, "Backend Engineer")
    if pr is None:
        pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                           name="Backend Engineer", capability_refs=[cap_id])
    wfk = wf.create_workforce(root, name=f"{company} Team", company_id=company_id,
                              capability_refs=[cap_id])
    wf.set_workforce_status(root, wfk["workforce_id"], "active")
    person = ident.create_identity(root, identity_type="human", company_id=company_id,
                                   display_name=f"{company} Dev")
    wf.add_member(root, wfk["workforce_id"], person["identity_id"])
    t = task.create_task(root, work_id=w["work_id"], name=f"{company} Task",
                         workstream_id=ws["workstream_id"])
    node = tn.create_task_node(root, task_id=t["task_id"], name="Implement",
                               required_capability_refs=[cap_id])
    resolution = res.resolve_task_node(root, node["task_node_id"])
    return {"company": company_id, "project": project["id"], "work": w["work_id"],
            "workstream": ws["workstream_id"], "capability": cap_id,
            "task": t["task_id"], "task_node": node["task_node_id"],
            "resolution": resolution["resolution_id"], "workforce": wfk["workforce_id"],
            "identity": person["identity_id"]}


def _exec(root: str, c: dict, **kw) -> dict:
    return ex.create_execution(root, task_node_id=c["task_node"],
                               resolution_id=c["resolution"],
                               actor_identity_id=c["identity"],
                               workforce_id=c["workforce"], **kw)


# ---------------------------------------------------------------- T1-T8 Execution

def test_t1_t2_t3_t4_execution_binding_and_scope(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = _chain(root, "Company A")
    b = _chain(root, "Company B")
    e = _exec(root, a)
    assert e["task_node_id"] == a["task_node"] and e["resolution_id"] == a["resolution"]  # T1/T2
    # T3/T26: 跨 company 的 Resolution 拒绝
    with pytest.raises(ValueError):
        ex.create_execution(root, task_node_id=a["task_node"], resolution_id=b["resolution"],
                            actor_identity_id=b["identity"], workforce_id=b["workforce"])
    # T4: actor/workforce 必须来自该 Resolution 的 match
    with pytest.raises(ValueError):
        ex.create_execution(root, task_node_id=a["task_node"], resolution_id=a["resolution"],
                            actor_identity_id=b["identity"], workforce_id=a["workforce"])
    with pytest.raises(ValueError):     # 不存在的 TaskNode / Resolution 拒绝
        ex.create_execution(root, task_node_id="TN-nope", resolution_id=a["resolution"])
    with pytest.raises(ValueError):
        ex.create_execution(root, task_node_id=a["task_node"], resolution_id="RS-nope")


def test_t5_t6_t19_t22_t23_t24_retry_preserves_history(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    # T22: failed -> retry -> succeeded (真实 runtime)
    e1 = _exec(root, c)
    r1 = rt.run_execution(root, e1["execution_id"], command="exit 1")
    assert r1["ok"] is False
    e2 = _exec(root, c)
    r2 = rt.run_execution(root, e2["execution_id"], command="echo ok")
    assert r2["ok"] is True
    # T6/T24: 历史 FAILED 不被覆盖
    assert ex.get_execution(root, e1["execution_id"])["status"] == "failed"
    assert ex.get_execution(root, e2["execution_id"])["status"] == "succeeded"
    # T23/T5: 两个 Execution 属于同一 TaskNode 且都保留
    runs = ex.list_executions(root, task_node_id=c["task_node"])
    assert {e["execution_id"] for e in runs} == {e1["execution_id"], e2["execution_id"]}
    assert all(e["task_node_id"] == c["task_node"] for e in runs)
    # T19: TaskNode 与 Execution id 不同
    assert c["task_node"] not in {e1["execution_id"], e2["execution_id"]}


def test_t7_t8_t29_t30_runtime_adapter_required(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    # T29/T30: 仅创建 Execution Record → queued, runtime_ref 为空, 不算真实执行
    assert e["status"] == "queued" and e["runtime_ref"] == ""
    with pytest.raises(ValueError):     # 无 command/executor_fn 拒绝
        rt.run_execution(root, e["execution_id"], command="")
    # T7/T8: 真实执行 → runtime_ref/output_ref + finalize
    r = rt.run_execution(root, e["execution_id"], command="echo hello-runtime")
    done = ex.get_execution(root, e["execution_id"])
    assert done["status"] == "succeeded"
    assert done["runtime_ref"] == "runtime:local-command"          # T7
    assert done["output_refs"] and r["output_ref"] in done["output_refs"]   # T8
    assert (tmp_path / r["output_ref"]).is_file()


# ---------------------------------------------------------------- T9-T13 Verification

def test_t9_t10_t11_t12_t13_verification_binds_execution(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    rt.run_execution(root, e["execution_id"], command="echo ok")
    # T11: succeeded ≠ verification passed (不自动产生验证)
    assert ver.list_verifications(root, execution_id=e["execution_id"]) == []
    # T9: 必须绑定真实 Execution
    with pytest.raises(ValueError):
        ver.create_verification(root, execution_id="EX-nope", status="passed")
    # T10: 不能直接绑定 TaskNode 代替 Execution (签名无 task_node_id)
    with pytest.raises(TypeError):
        ver.create_verification(root, task_node_id=c["task_node"], status="passed")
    # T12/T13
    v_fail = ver.create_verification(root, execution_id=e["execution_id"], status="failed")
    v_pass = ver.create_verification(root, execution_id=e["execution_id"], status="passed")
    assert v_fail["passed"] is False and v_pass["passed"] is True
    assert v_fail["execution_id"] == e["execution_id"]


# ---------------------------------------------------------------- T14-T17 Evidence

def test_t14_t15_t16_t17_evidence_resolvable(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    r = rt.run_execution(root, e["execution_id"], command="echo evidence")
    v = ver.create_verification(root, execution_id=e["execution_id"], status="passed")
    # T14/T17: locator = 真实 output 文件
    evd = ev.create_evidence(root, execution_id=e["execution_id"], type="command_output",
                             source="local-command", locator=f"output:{e['execution_id']}",
                             summary="stdout captured", verification_id=v["verification_id"])
    assert evd["execution_id"] == e["execution_id"]
    resolved = ev.resolve_evidence(root, evd["evidence_id"])
    assert Path(resolved["resolved_path"]).is_file()
    # T15: 不存在的 evidence_ref / locator 必须失败
    with pytest.raises(ValueError):
        ev.create_evidence(root, execution_id=e["execution_id"], type="file",
                           source="x", locator="file:no-such-file.txt")
    with pytest.raises(ValueError):
        ev.resolve_evidence(root, "EV-nope")
    # T16: LLM 文本不能自动成为 Evidence
    with pytest.raises(ValueError):
        ev.create_evidence(root, execution_id=e["execution_id"], type="log",
                           source="llm", locator="the model says done")
    from factory_console.os_core_evidence import resolve_locator
    with pytest.raises(ValueError):
        resolve_locator(root, "llm says done")
    # output locator 真实可解析 (r.output_ref 对应执行输出)
    assert (tmp_path / r["output_ref"]).is_file()


# ---------------------------------------------------------------- T18-T21 Outcome

def test_t18_t19_t20_outcome_contract(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    rt.run_execution(root, e["execution_id"], command="echo ok")
    v_fail = ver.create_verification(root, execution_id=e["execution_id"], status="failed")
    evd = ev.create_evidence(root, execution_id=e["execution_id"], type="command_output",
                             source="local-command", locator=f"output:{e['execution_id']}")
    # T18: 必须绑定真实 Execution
    with pytest.raises(ValueError):
        out.create_outcome(root, execution_id="EX-nope", status="accepted",
                           verification_refs=[v_fail["verification_id"]])
    # T19: 必须引用 Verification 或 Evidence
    with pytest.raises(ValueError):
        out.create_outcome(root, execution_id=e["execution_id"], status="accepted")
    # T20: Execution succeeded + Verification failed → rejected Outcome 合法
    rejected = out.create_outcome(root, execution_id=e["execution_id"], status="rejected",
                                  verification_refs=[v_fail["verification_id"]],
                                  evidence_refs=[evd["evidence_id"]])
    assert rejected["status"] == "rejected"
    assert rejected["execution_id"] == e["execution_id"]


# ---------------------------------------------------------------- T21/T25/T27/T28 E2E + boundaries

def test_t21_t25_e2e_and_reload(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    # 失败执行 → 成功执行
    e1 = _exec(root, c)
    rt.run_execution(root, e1["execution_id"], command="exit 3")
    e2 = _exec(root, c)
    r = rt.run_execution(root, e2["execution_id"], command="echo e2e-ok")
    v = ver.create_verification(root, execution_id=e2["execution_id"], status="passed",
                                checks=[{"name": "exit0", "passed": True}])
    evd = ev.create_evidence(root, execution_id=e2["execution_id"], type="command_output",
                             source="local-command", locator=f"output:{e2['execution_id']}",
                             verification_id=v["verification_id"])
    o = out.create_outcome(root, execution_id=e2["execution_id"], status="accepted",
                           verification_refs=[v["verification_id"]],
                           evidence_refs=[evd["evidence_id"]],
                           result_refs=[r["output_ref"]])
    # reload 稳定
    assert ex.get_execution(root, e2["execution_id"])["runtime_ref"] == "runtime:local-command"
    assert ver.get_verification(root, v["verification_id"])["execution_id"] == e2["execution_id"]
    assert ev.get_evidence(root, evd["evidence_id"])["execution_id"] == e2["execution_id"]
    assert out.get_outcome(root, o["outcome_id"])["execution_id"] == e2["execution_id"]
    assert o["status"] == "accepted"


def test_t27_t28_no_noderun_and_resolution_does_not_execute(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    # T28: Resolution 阶段零副作用 (resolve 已在 fixture 内执行)
    assert ex.list_executions(root, task_node_id=c["task_node"]) == []
    assert not (tmp_path / "nodes").exists()          # T27: TaskNode ≠ NodeRun
    assert not (tmp_path / "ops" / "plugins").exists()
    e = _exec(root, c)
    assert tn.get_task_node(root, c["task_node"])["task_node_id"] == c["task_node"]
    assert e["task_node_id"] == c["task_node"]
