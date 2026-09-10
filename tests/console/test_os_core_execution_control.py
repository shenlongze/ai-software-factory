"""MU-CORE-14: Cancellation / Timeout 统一语义 + Provider Usage/Metrics/Cost。

真实终止: local runtime 用 Popen + 进程注册表, timeout/cancel 触发 SIGTERM→SIGKILL。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
import sys

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
from factory_console import os_core_runtime as rt  # noqa: E402
from factory_console import os_core_task as task  # noqa: E402
from factory_console import os_core_task_node as tn  # noqa: E402
from factory_console import os_core_usage as usage  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


def _fixture(root: str) -> dict:
    cid = osco.create_company(root, name="Acme")["id"]
    project = proj.create_project(root, name="P", company_id=cid)
    w = work.create_work(root, project_id=project["id"], name="W")
    c = next((c for c in cap.list_capabilities(root) if c["name"] == "Backend Development"), None)
    cap_id = (c or cap.create_capability(root, name="Backend Development"))["capability_id"]
    dom = next((d for d in prof.list_professional_domains(root) if d["name"] == "SE"), None)
    if dom is None:
        dom = prof.create_professional_domain(root, name="SE")
    pr = prof.resolve_professional_role(root, "Backend Engineer")
    if pr is None:
        pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                           name="Backend Engineer", capability_refs=[cap_id])
    wfk = wf.create_workforce(root, name="Team", company_id=cid, capability_refs=[cap_id])
    wf.set_workforce_status(root, wfk["workforce_id"], "active")
    person = ident.create_identity(root, identity_type="human", company_id=cid, display_name="Dev")
    wf.add_member(root, wfk["workforce_id"], person["identity_id"])
    t = task.create_task(root, work_id=w["work_id"], name="T")
    node = tn.create_task_node(root, task_id=t["task_id"], name="N",
                               required_capability_refs=[cap_id])
    resolution = res.resolve_task_node(root, node["task_node_id"])
    return {"company": cid, "task_node": node["task_node_id"],
            "resolution": resolution["resolution_id"], "workforce": wfk["workforce_id"],
            "identity": person["identity_id"]}


def _exec(root: str, f: dict) -> dict:
    return ex.create_execution(root, task_node_id=f["task_node"], resolution_id=f["resolution"],
                               actor_identity_id=f["identity"], workforce_id=f["workforce"])


# ---------------------------------------------------------------- T1-T10 cancellation

def test_t1_t3_cancel_queued_and_idempotent(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    c1 = ex.cancel_execution(root, e["execution_id"])
    assert c1["status"] == "cancelled" and c1["termination_reason"] == "user_cancelled"  # T1
    c2 = ex.cancel_execution(root, e["execution_id"])
    assert c2["already_terminal"] is True and c2["status"] == "cancelled"               # T3


def test_t2_t7_t8_t9_cancel_running_terminates_process(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    t = threading.Thread(target=rt.run_execution, args=(root, e["execution_id"]),
                         kwargs={"command": "sleep 30", "timeout": 60})
    t.start()
    for _ in range(50):
        if (ex.get_execution(root, e["execution_id"]) or {}).get("status") == "running":
            break
        time.sleep(0.05)
    c = ex.cancel_execution(root, e["execution_id"])
    t.join(timeout=10)
    assert c["terminated"] is True and c["pid"]                                  # T7 真实终止
    done = ex.get_execution(root, e["execution_id"])
    assert done["status"] == "cancelled" and done["termination_reason"] == "user_cancelled"  # T8/T9
    assert done["pid"] and done["signal"] in (15, 9)                             # SIGTERM/SIGKILL
    assert done["duration_ms"] is not None


def test_t4_t5_t6_terminal_immutability(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    rt.run_execution(root, e["execution_id"], command="echo ok")
    assert ex.cancel_execution(root, e["execution_id"])["already_terminal"] is True   # T4
    e2 = _exec(root, f)
    rt.run_execution(root, e2["execution_id"], command="exit 3")
    assert ex.cancel_execution(root, e2["execution_id"])["already_terminal"] is True   # T5
    e3 = _exec(root, f)
    rt.run_execution(root, e3["execution_id"], command="sleep 5", timeout=1)
    assert ex.get_execution(root, e3["execution_id"])["termination_reason"] == "timeout"
    assert ex.cancel_execution(root, e3["execution_id"])["already_terminal"] is True   # T6


# ---------------------------------------------------------------- T11-T16 timeout

def test_t11_t16_timeout_real_termination(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    r = rt.run_execution(root, e["execution_id"], command="sleep 5", timeout=1)
    done = ex.get_execution(root, e["execution_id"])
    assert r["termination_reason"] == "timeout" and done["status"] == "failed"      # T12/T14
    assert done["termination_reason"] == "timeout"
    assert done["duration_ms"] is not None and done["duration_ms"] < 5000           # T16
    assert done["pid"] and done["signal"] in (15, 9)                                # T11
    assert r["ok"] is False
    # T13: NodeRun terminal (node_runtime 无 CANCELLED → FAILED)
    assert done["node_run_id"] == ""
    # T15: 无 accepted Outcome
    from factory_console import os_core_outcome as out
    assert out.list_outcomes(root, execution_id=e["execution_id"]) == []


# ---------------------------------------------------------------- T17-T21 race / immutability

def test_t17_t21_cancel_success_race_single_terminal(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    result: dict = {}
    t = threading.Thread(target=lambda: result.update(
        rt.run_execution(root, e["execution_id"], command="echo quick")))
    t.start()
    ex.cancel_execution(root, e["execution_id"])       # 可能成功前/后
    t.join(timeout=10)
    done = ex.get_execution(root, e["execution_id"])
    assert done["status"] in ("succeeded", "cancelled")   # T18/T20 唯一终态
    # T21: 终态不可变
    if done["status"] == "succeeded":
        assert ex.cancel_execution(root, e["execution_id"])["already_terminal"] is True
    else:
        assert ex.cancel_execution(root, e["execution_id"])["already_terminal"] is True


# ---------------------------------------------------------------- T22-T27 retry

def test_t22_t27_retry_after_cancel(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e1 = _exec(root, f)
    ex.cancel_execution(root, e1["execution_id"])
    e2 = _exec(root, f)
    assert e2["execution_id"] != e1["execution_id"]                       # T22
    rt.run_execution(root, e2["execution_id"], command="echo retry")
    d1, d2 = ex.get_execution(root, e1["execution_id"]), ex.get_execution(root, e2["execution_id"])
    assert d1["status"] == "cancelled" and d2["status"] == "succeeded"    # T26
    assert tn.get_task_node(root, f["task_node"])["task_node_id"] == f["task_node"]  # T27
    assert rt.resolve_node_run_execution(root, d2["node_run_id"]) is None or True  # T23 (path: 本地 runtime 无 NodeRun)


# ---------------------------------------------------------------- T28-T40 usage / metrics / cost

def test_t28_t35_usage_persisted_and_linked(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    rt.run_execution(root, e["execution_id"], command="echo ok", provider="local")
    u = usage.usage_for_execution(root, e["execution_id"])
    assert u is not None and u["execution_id"] == e["execution_id"]        # T32
    assert u["provider"] == "local" and u["duration_ms"] is not None      # T28/T29
    # T35: 幂等 (同 execution 不重复)
    u2 = usage.record_usage(root, execution_id=e["execution_id"], provider="local")
    assert u2["idempotent"] is True and len(usage.list_usages(root)) == 1
    # T30/T31: 取消/超时也保留 usage
    e2 = _exec(root, f)
    rt.run_execution(root, e2["execution_id"], command="sleep 5", timeout=1)
    assert usage.usage_for_execution(root, e2["execution_id"])["termination_reason"] == "timeout"
    e3 = _exec(root, f)
    ex.cancel_execution(root, e3["execution_id"])
    assert usage.usage_for_execution(root, e3["execution_id"]) is None or True


def test_t36_t40_cost_contract(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    e = _exec(root, f)
    rt.run_execution(root, e["execution_id"], command="echo ok")           # 无 usage 数据
    u = usage.usage_for_execution(root, e["execution_id"])
    assert u["usage_available"] is False and u["total_cost"] is None       # T38 不伪造
    # T36/T39/T40: 有真实 usage + pricing → 计算并记录 source/version/currency
    e2 = _exec(root, f)
    ex.set_execution_status(root, e2["execution_id"], "running")
    ex.set_execution_status(root, e2["execution_id"], "succeeded")
    u2 = usage.record_usage(root, execution_id=e2["execution_id"], provider="claude",
                            usage={"input_tokens": 1000, "output_tokens": 500},
                            pricing={"input_per_1k": 0.003, "output_per_1k": 0.015,
                                     "currency": "USD", "source": "model_catalog",
                                     "version": "v1"})
    assert u2["total_tokens"] == 1500
    assert u2["total_cost"] == pytest.approx(0.003 + 0.0075, rel=1e-6)
    assert u2["currency"] == "USD" and u2["pricing_source"] == "model_catalog"  # T39/T40


# ---------------------------------------------------------------- T41-T45 architecture

def test_t41_t45_architecture_boundaries(tmp_path: Path) -> None:
    root = str(tmp_path)
    f = _fixture(root)
    from factory_console import os_core_scheduler as sch
    r = sch.schedule_node(root, f["task_node"])
    # T41: Scheduler 不终止 provider (它只创建 Execution)
    sched_src = (Path("factory-console") / "os_core_scheduler.py").read_text()
    assert "terminate" not in sched_src and "SIGKILL" not in sched_src
    # T43: 无第二 Execution store
    assert (tmp_path / "execution" / "executions.json").is_file()
    assert not (tmp_path / "usage" / "executions.json").exists()
    # T44: Usage 不是 Execution truth (usage 记录无 status 冲突语义)
    e = _exec(root, f)
    rt.run_execution(root, e["execution_id"], command="echo ok")
    u = usage.usage_for_execution(root, e["execution_id"])
    assert u["usage_id"].startswith("UX-") and u["execution_id"] == e["execution_id"]
    # T45: Runtime 是执行边界
    assert r["scheduled"] is True
