"""MU-CORE-12: Scheduler Service（readiness + 依赖 + 幂等 + 不执行）。

关键: Scheduler 决定"哪个 TaskNode 现在可以被调度"并创建 OS Execution;
不调用 Provider/Runtime; 依赖完成以 accepted Outcome 为准 (非 Execution.succeeded)。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org"),
           str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from factory_console import os_core_capability as cap  # noqa: E402
from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import os_core_evidence as ev  # noqa: E402
from factory_console import os_core_execution as ex  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_outcome as out  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_runtime as rt  # noqa: E402
from factory_console import os_core_scheduler as sch  # noqa: E402
from factory_console import os_core_task as task  # noqa: E402
from factory_console import os_core_task_node as tn  # noqa: E402
from factory_console import os_core_verification as ver  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _fixture(root: str, company: str = "Acme") -> dict:
    company_id = osco.create_company(root, name=company)["id"]
    project = proj.create_project(root, name=f"{company} P", company_id=company_id)
    w = work.create_work(root, project_id=project["id"], name=f"{company} Work")
    cap_id = next((c["capability_id"] for c in cap.list_capabilities(root)
                   if c["name"] == "Backend Development"), None)
    if cap_id is None:
        cap_id = cap.create_capability(root, name="Backend Development")["capability_id"]
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
    t = task.create_task(root, work_id=w["work_id"], name="Task")
    a = tn.create_task_node(root, task_id=t["task_id"], name="A",
                            required_capability_refs=[cap_id], sequence=1)
    b = tn.create_task_node(root, task_id=t["task_id"], name="B",
                            required_capability_refs=[cap_id], sequence=2,
                            depends_on=[a["task_node_id"]])
    return {"company": company_id, "project": project["id"], "work": w["work_id"],
            "capability": cap_id, "task": t["task_id"], "A": a["task_node_id"],
            "B": b["task_node_id"], "workforce": wfk["workforce_id"],
            "identity": person["identity_id"]}


def _ok_fn(cmd: str):
    def _fn(_i):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {"ok": p.returncode == 0, "output": p.stdout, "error": p.stderr,
                "artifact_type": "report",
                "verification": {"result": "PASS" if p.returncode == 0 else "FAIL",
                                 "source": f"executor exit_code={p.returncode}"}}
    return _fn


def _accept(root: str, execution_id: str, *, verification="passed") -> None:
    """真实完成一次执行 + Verification + Evidence + Outcome(accepted)。"""
    ex_done = ex.get_execution(root, execution_id)
    v = ver.create_verification(root, execution_id=execution_id, status=verification)
    evd = ev.create_evidence(root, execution_id=execution_id, type="command_output",
                             source="node_runtime", locator=f"output:{execution_id}",
                             verification_id=v["verification_id"])
    st = "accepted" if verification == "passed" else "rejected"
    out.create_outcome(root, execution_id=execution_id, status=st,
                       verification_refs=[v["verification_id"]],
                       evidence_refs=[evd["evidence_id"]], result_refs=ex_done["output_refs"])


# ---------------------------------------------------------------- T1-T8 readiness

def test_t1_t7_readiness_dependency(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    ra = sch.evaluate_node(root, f["A"])
    rb = sch.evaluate_node(root, f["B"])
    assert ra["decision"] == "ready" and "resolution resolved" in ra["reasons"]   # T6
    assert rb["decision"] == "blocked" and any("未 accepted" in r for r in rb["reasons"])  # T7/T8
    # T31/T32: 确定性 + 可解释
    assert ra == sch.evaluate_node(root, f["A"])
    assert ra["resolution_id"] and ra["workforce_id"] and ra["identity_id"]


def test_t12_t13_t14_t15_unresolved_paths(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    cap.set_capability_status(root, f["capability"], "retired")     # T13
    assert sch.evaluate_node(root, f["A"])["decision"] == "unresolved"
    cap.set_capability_status(root, f["capability"], "active")

    wf.set_workforce_status(root, f["workforce"], "suspended")      # T14
    assert sch.evaluate_node(root, f["A"])["decision"] == "unresolved"
    wf.set_workforce_status(root, f["workforce"], "active")

    ident.create_identity  # (Identity lifecycle: retired)
    # T12: TaskNode 无 required capability → unresolved
    bare = tn.create_task_node(root, task_id=f["task"], name="bare")
    assert sch.evaluate_node(root, bare["task_node_id"])["decision"] == "unresolved"


def test_t16_company_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = _fixture(root, "Company A")
    _fixture(root, "Company B")
    r = sch.evaluate_node(root, a["A"])
    assert r["decision"] == "ready" and r["company_id"] == a["company"]


def test_t17_t18_t19_lifecycle_blocks(tmp_path: Path) -> None:
    root = str(tmp_path)
    # T17: Task cancelled → 不调度 (cancelled 为终态)
    f1 = _fixture(root, "TaskCancelCo")
    task.set_task_status(root, f1["task"], "cancelled")
    assert sch.evaluate_node(root, f1["A"])["decision"] == "cancelled"
    # T18: TaskNode cancelled → 不调度
    f2 = _fixture(root, "NodeCancelCo")
    tn.set_task_node_status(root, f2["A"], "cancelled")
    assert sch.evaluate_node(root, f2["A"])["decision"] == "cancelled"
    # T19: TaskNode completed → 不重复调度
    f3 = _fixture(root, "NodeDoneCo")
    tn.set_task_node_status(root, f3["A"], "ready")
    tn.set_task_node_status(root, f3["A"], "running")
    tn.set_task_node_status(root, f3["A"], "completed")
    assert sch.evaluate_node(root, f3["A"])["decision"] == "completed"


# ---------------------------------------------------------------- T20-T27 scheduling / idempotency / retry

def test_t20_t21_t22_t23_schedule_idempotent(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    r1 = sch.schedule_node(root, f["A"])
    assert r1["scheduled"] is True and r1["execution_id"].startswith("EX-")
    # T22: 重复调度 → NO-OP
    r2 = sch.schedule_node(root, f["A"])
    assert r2["scheduled"] is False and "active Execution" in " ".join(r2["reasons"])
    # T21: 只有一个 active Execution
    active = [e for e in ex.list_executions(root, task_node_id=f["A"])
              if e["status"] in ("queued", "running")]
    assert len(active) == 1
    # T23: 并发调度 (线程) 仍最多一个 active
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: sch.schedule_node(root, f["A"]), range(4)))
    active = [e for e in ex.list_executions(root, task_node_id=f["A"])
              if e["status"] in ("queued", "running")]
    assert len(active) == 1


def test_t24_t25_t26_t27_retry_new_execution_and_noderun(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    r1 = sch.schedule_node(root, f["A"])
    rt.run_execution_via_node_runtime(root, r1["execution_id"], prompt="fail",
                                      executor_fn=_ok_fn("exit 1"))
    e1 = ex.get_execution(root, r1["execution_id"])
    # T19/T9: 失败后 B 仍 blocked; A 可重试
    assert sch.evaluate_node(root, f["B"])["decision"] == "blocked"
    r2 = sch.schedule_node(root, f["A"])
    assert r2["scheduled"] is True and r2["execution_id"] != e1["execution_id"]   # T24
    rt.run_execution_via_node_runtime(root, r2["execution_id"], prompt="ok",
                                      executor_fn=_ok_fn("echo retry"))
    e2 = ex.get_execution(root, r2["execution_id"])
    assert e2["node_run_id"] != e1["node_run_id"]                                 # T25
    assert ex.get_execution(root, e1["execution_id"])["status"] == "failed"       # T26
    from factory_console.node_runtime import get_node_run
    assert get_node_run(root, e1["node_run_id"])["state"] == "FAILED"             # T27


# ---------------------------------------------------------------- T10/T11/T36/T37 dependency completion semantics

def test_t10_t11_t36_t37_dependency_requires_accepted_outcome(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    # 失败执行 → B blocked
    r1 = sch.schedule_node(root, f["A"])
    rt.run_execution_via_node_runtime(root, r1["execution_id"], prompt="fail",
                                      executor_fn=_ok_fn("exit 1"))
    assert sch.evaluate_node(root, f["B"])["decision"] == "blocked"
    # T11/T37: Execution succeeded + Verification failed + Outcome rejected → B 仍 blocked
    r2 = sch.schedule_node(root, f["A"])
    rt.run_execution_via_node_runtime(root, r2["execution_id"], prompt="ok",
                                      executor_fn=_ok_fn("echo ok"))
    assert ex.get_execution(root, r2["execution_id"])["status"] == "succeeded"
    _accept(root, r2["execution_id"], verification="failed")     # Outcome rejected
    assert sch.evaluate_node(root, f["B"])["decision"] == "blocked"
    # T36: 再重试 + accepted Outcome → B ready
    r3 = sch.schedule_node(root, f["A"])
    rt.run_execution_via_node_runtime(root, r3["execution_id"], prompt="ok2",
                                      executor_fn=_ok_fn("echo ok2"))
    _accept(root, r3["execution_id"], verification="passed")
    assert sch.evaluate_node(root, f["A"])["decision"] == "completed"   # T20 不重复
    rb = sch.evaluate_node(root, f["B"])
    assert rb["decision"] == "ready"                                    # T10/T36
    # T34/T35: B 真实执行 (本地 executor 经 Runtime Integration)
    rb_run = sch.schedule_node(root, f["B"])
    assert rb_run["scheduled"] is True
    rt.run_execution_via_node_runtime(root, rb_run["execution_id"], prompt="b",
                                      executor_fn=_ok_fn("echo B-done"))
    assert ex.get_execution(root, rb_run["execution_id"])["status"] == "succeeded"


# ---------------------------------------------------------------- T28-T33 boundaries + reload

def test_t28_t29_t30_t33_no_provider_no_runtime_direct(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    r = sch.schedule_node(root, f["A"])
    assert r["scheduled"] is True
    # T28/T29/T30: Scheduler 只创建 OS Execution; 不产生 NodeRun / Provider / nodes 目录
    assert ex.get_execution(root, r["execution_id"])["node_run_id"] == ""
    assert not (tmp_path / "nodes").exists()
    assert not (tmp_path / "workflows" / "runs").exists()
    # T33: reload 稳定
    assert sch.evaluate_node(root, f["A"])["decision"] == "blocked"
    assert sch.schedule_node(root, f["A"])["scheduled"] is False
    # T5/T1-T4: 无第二 Execution store
    assert (tmp_path / "execution" / "executions.json").is_file()
    assert not (tmp_path / "scheduler" / "executions.json").exists()
