"""MU-CORE-09: Task / TaskNode / Execution OS Core（T1-T28 适用项）。

关键不变式: Task ≠ TaskNode ≠ Execution；TaskNode 可在无 Execution 时存在；
一个 TaskNode 可有多次 Execution；Execution 记录因果引用 (resolution→workforce→identity)。
"""
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
from factory_console import os_core_execution as ex  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_resolution as res  # noqa: E402
from factory_console import os_core_task as task  # noqa: E402
from factory_console import os_core_task_node as tn  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _chain(root: str, company: str = "Acme") -> dict:
    company_id = osco.create_company(root, name=company)["id"]
    project = proj.create_project(root, name=f"{company} P", company_id=company_id)
    w = work.create_work(root, project_id=project["id"], name="Work A")
    ws = work.create_workstream(root, work_id=w["work_id"], name="Frontend")
    existing = next((c for c in cap.list_capabilities(root) if c["name"] == "Backend Development"), None)
    cap_id = (existing or cap.create_capability(root, name="Backend Development"))["capability_id"]
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
                                   display_name="Alice")
    wf.add_member(root, wfk["workforce_id"], person["identity_id"])
    return {"company": company_id, "project": project["id"], "work": w["work_id"],
            "workstream": ws["workstream_id"], "capability": cap_id,
            "professional_role": pr["professional_role_id"],
            "workforce": wfk["workforce_id"], "identity": person["identity_id"]}


# ---------------------------------------------------------------- T1-T4 Task / TaskNode CRUD

def test_t1_t3_task_crud_and_workstream_validation(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="API Task",
                         workstream_id=c["workstream"], priority="P1")
    assert t["task_id"].startswith("T-") and t["status"] == "todo"
    assert (tmp_path / "task" / "tasks.json").is_file()
    assert task.get_task(root, t["task_id"])["work_id"] == c["work"]          # T2
    assert task.get_task(root, t["task_id"])["workstream_id"] == c["workstream"]
    # 不属于该 Work 的 workstream 必须拒绝 (T3)
    other_work = work.create_work(root, project_id=c["project"], name="Other Work")
    other_ws = work.create_workstream(root, work_id=other_work["work_id"], name="Backend")
    with pytest.raises(ValueError):
        task.create_task(root, work_id=c["work"], name="Bad", workstream_id=other_ws["workstream_id"])
    with pytest.raises(ValueError):
        task.create_task(root, work_id="W-nope", name="Bad")


def test_t4_t5_tasknode_crud_and_tree(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    a = tn.create_task_node(root, task_id=t["task_id"], name="A", sequence=1)
    b = tn.create_task_node(root, task_id=t["task_id"], name="B", sequence=2)
    b1 = tn.create_task_node(root, task_id=t["task_id"], parent_node_id=b["task_node_id"],
                             name="B1", sequence=1)
    assert a["task_node_id"].startswith("TN-")
    assert (tmp_path / "task" / "task_nodes.json").is_file()
    tree = tn.task_node_tree(root, t["task_id"])
    assert [n["task_node_id"] for n in tree] == [a["task_node_id"], b["task_node_id"]]
    assert tree[1]["children"][0]["task_node_id"] == b1["task_node_id"]
    # 父节点必须属于同一 Task
    t2 = task.create_task(root, work_id=c["work"], name="T2")
    with pytest.raises(ValueError):
        tn.create_task_node(root, task_id=t2["task_id"],
                            parent_node_id=b["task_node_id"], name="X")


# ---------------------------------------------------------------- T6-T12 TaskNode != Execution; Resolution 接入

def test_t6_t8_t19_tasknode_multiple_executions(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    node = tn.create_task_node(root, task_id=t["task_id"], name="Implement API",
                               required_capability_refs=[c["capability"]])
    # T6: TaskNode 可以没有 Execution
    assert ex.list_executions(root, task_node_id=node["task_node_id"]) == []
    # T10/T11: TaskNode -> Resolution -> Workforce/Identity
    r = res.resolve_task_node(root, node["task_node_id"])
    assert r["status"] == "resolved"
    assert r["matches"][0]["workforce_id"] == c["workforce"]
    assert r["matches"][0]["identity_id"] == c["identity"]
    # T8/T19: 多次 Execution (failed 后允许再次执行)
    e1 = ex.create_execution(root, task_node_id=node["task_node_id"],
                             resolution_id=r["resolution_id"],
                             actor_identity_id=c["identity"], workforce_id=c["workforce"])
    ex.set_execution_status(root, e1["execution_id"], "running")
    ex.set_execution_status(root, e1["execution_id"], "failed", error="boom")
    e2 = ex.create_execution(root, task_node_id=node["task_node_id"],
                             resolution_id=r["resolution_id"],
                             actor_identity_id=c["identity"], workforce_id=c["workforce"])
    ex.set_execution_status(root, e2["execution_id"], "running")
    ex.set_execution_status(root, e2["execution_id"], "succeeded")
    # T7/T9/T20: TaskNode 仍存在且 id 与 Execution 不同
    assert tn.get_task_node(root, node["task_node_id"]) is not None
    assert e1["execution_id"] != e2["execution_id"]
    assert node["task_node_id"] != e1["execution_id"]
    assert ex.get_execution(root, e1["execution_id"])["task_node_id"] == node["task_node_id"]


def test_t12_tasknode_capability_validation(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    n = tn.create_task_node(root, task_id=t["task_id"], name="N",
                            required_capability_refs=[c["capability"]])
    assert n["required_capability_refs"] == [c["capability"]]
    with pytest.raises(ValueError):
        tn.create_task_node(root, task_id=t["task_id"], name="Bad",
                            required_capability_refs=["CAP-nope"])


# ---------------------------------------------------------------- T13-T18 边界 / 生命周期

def test_t13_t14_t15_scope_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    ca = _chain(root, "Company A")
    cb = _chain(root, "Company B")
    ta = task.create_task(root, work_id=ca["work"], name="A Task")
    node = tn.create_task_node(root, task_id=ta["task_id"], name="N",
                               required_capability_refs=[ca["capability"]])
    r = res.resolve_task_node(root, node["task_node_id"])
    assert r["matches"][0]["workforce_id"] == ca["workforce"]        # T13 跨 company 不串
    # T14: Task -> Work -> Project -> Company 链
    chain = task.resolve_task(root, ta["task_id"])
    assert chain["work"]["work_id"] == ca["work"] and chain["project"]["company_id"] == ca["company"]
    # T15: Workstream 归属
    with pytest.raises(ValueError):
        task.create_task(root, work_id=ca["work"], name="Bad", workstream_id="WS-nope")
    assert cb["work"] != ca["work"]


def test_t16_t17_t18_execution_and_tasknode_lifecycle(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    node = tn.create_task_node(root, task_id=t["task_id"], name="N")
    # T16: actor Identity
    e = ex.create_execution(root, task_node_id=node["task_node_id"],
                            actor_identity_id=c["identity"])
    assert ex.get_execution(root, e["execution_id"])["actor_identity_id"] == c["identity"]
    # T17: Execution 生命周期 (queued→running→succeeded; 非法转换拒绝)
    ex.set_execution_status(root, e["execution_id"], "running")
    ex.set_execution_status(root, e["execution_id"], "succeeded")
    assert ex.get_execution(root, e["execution_id"])["completed_at"]
    with pytest.raises(ValueError):
        ex.set_execution_status(root, e["execution_id"], "running")
    # T18: TaskNode 生命周期
    tn.set_task_node_status(root, node["task_node_id"], "ready")
    tn.set_task_node_status(root, node["task_node_id"], "running")
    tn.set_task_node_status(root, node["task_node_id"], "completed")
    with pytest.raises(ValueError):
        tn.set_task_node_status(root, node["task_node_id"], "ready")
    # Task 生命周期
    task.set_task_status(root, t["task_id"], "ready")
    assert task.get_task(root, t["task_id"])["status"] == "ready"


# ---------------------------------------------------------------- T21-T28 边界

def test_t21_reload_stable(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    n = tn.create_task_node(root, task_id=t["task_id"], name="N")
    e = ex.create_execution(root, task_node_id=n["task_node_id"])
    assert task.get_task(root, t["task_id"])["task_id"] == t["task_id"]
    assert tn.get_task_node(root, n["task_node_id"])["task_node_id"] == n["task_node_id"]
    assert ex.get_execution(root, e["execution_id"])["execution_id"] == e["execution_id"]


def test_t22_t24_single_stores(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    n = tn.create_task_node(root, task_id=t["task_id"], name="N")
    ex.create_execution(root, task_node_id=n["task_node_id"])
    assert (tmp_path / "task" / "tasks.json").is_file()
    assert (tmp_path / "task" / "task_nodes.json").is_file()
    assert (tmp_path / "execution" / "executions.json").is_file()
    assert not (tmp_path / "task" / "task_tree.json").exists()       # 无第二 Task/TaskNode store
    assert not (tmp_path / "execution" / "executions_legacy.json").exists()


def test_t25_t28_not_noderun_not_sprint(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    n = tn.create_task_node(root, task_id=t["task_id"], name="N")
    # T25: TaskNode ≠ NodeRun (不产生 nodes/ 执行目录)
    assert not (tmp_path / "nodes").exists()
    assert n["task_node_id"].startswith("TN-")
    # T28: Sprint 不是 Task SSOT
    assert "sprint" not in t and not (tmp_path / "project_agile").exists()
    from factory_console import project_agile as pa
    sp = pa.create_sprint(root, c["project"], title="S1")
    assert sp["sprint_id"] != t["task_id"]          # Sprint 与 Task 身份互不相干


def test_t26_t27_resolution_does_not_execute(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    t = task.create_task(root, work_id=c["work"], name="T")
    n = tn.create_task_node(root, task_id=t["task_id"], name="N",
                            required_capability_refs=[c["capability"]])
    res.resolve_task_node(root, n["task_node_id"])
    # 只解析: 不创建 Execution / NodeRun / Plugin / Agent run
    assert ex.list_executions(root, task_node_id=n["task_node_id"]) == []
    assert not (tmp_path / "nodes").exists()
    assert not (tmp_path / "ops" / "plugins").exists()
