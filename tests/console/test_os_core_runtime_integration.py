"""MU-CORE-11: Runtime Integration (OS Execution ↔ node_runtime.NodeRun ↔ external_executor)。

真实执行: 测试用真实 subprocess (python3/echo) 与真实 external_executor.run (本地 adapter),
不 mock provider; real provider (codex/claude) 见 Runtime Evidence。
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


def _chain(root: str, company: str = "Acme") -> dict:
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
    t = task.create_task(root, work_id=w["work_id"], name=f"{company} Task")
    node = tn.create_task_node(root, task_id=t["task_id"], name="Node",
                               required_capability_refs=[cap_id])
    resolution = res.resolve_task_node(root, node["task_node_id"])
    return {"company": company_id, "project": project["id"], "work": w["work_id"],
            "capability": cap_id, "task": t["task_id"], "task_node": node["task_node_id"],
            "resolution": resolution["resolution_id"], "workforce": wfk["workforce_id"],
            "identity": person["identity_id"]}


def _exec(root: str, c: dict) -> dict:
    return ex.create_execution(root, task_node_id=c["task_node"],
                               resolution_id=c["resolution"],
                               actor_identity_id=c["identity"],
                               workforce_id=c["workforce"])


def _ok_fn(command: str):
    """真实 subprocess executor_fn: node_runtime 契约 {ok, output, error}。"""
    def _fn(_input):
        p = subprocess.run(command, shell=True, capture_output=True, text=True)
        return {"ok": p.returncode == 0, "output": p.stdout, "error": p.stderr,
                "artifact_type": "report",
                "verification": {"result": "PASS" if p.returncode == 0 else "FAIL",
                                 "source": f"executor exit_code={p.returncode}"}}
    return _fn


# ---------------------------------------------------------------- T1-T8 integration

def test_t1_t8_execution_to_noderun_mapping(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    r = rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="real task",
                                          executor_fn=_ok_fn("echo integration-ok"))
    done = ex.get_execution(root, e["execution_id"])
    # T1/T2: Execution -> NodeRun 映射 (双向)
    assert done["node_run_id"].startswith("run-")
    assert rt.resolve_node_run_execution(root, done["node_run_id"])["execution_id"] == e["execution_id"]
    # T3: runtime_ref 可定位 NodeRun
    assert done["runtime_ref"] == f"node_run:{done['node_run_id']}:custom"
    from factory_console.node_runtime import get_node_run
    assert get_node_run(root, done["node_run_id"]) is not None
    # T4/T5: NodeRun != TaskNode; NodeRun 生命周期真实
    assert done["node_run_id"] != c["task_node"]
    assert get_node_run(root, done["node_run_id"])["state"] == "COMPLETED"
    # T6/T19: 真实执行输出可追溯
    assert done["output_refs"] and (tmp_path / done["output_refs"][0]).is_file()
    assert "run-" in (tmp_path / done["output_refs"][0]).read_text()
    assert r["ok"] is True


def test_t7_t29_external_executor_real_call(tmp_path: Path) -> None:
    """external_executor.run 真实 subprocess (本地 adapter: python3)。"""
    from factory_console.external_executor.executor import run as ext_run
    from factory_console.external_executor.schema import ExternalExecutorAdapter

    adapter = ExternalExecutorAdapter(id="localecho", name="local echo",
                                      binary="echo",
                                      invocation={"non_interactive": ["{prompt}"],
                                                  "project_dir": "cwd", "timeout": 30})
    res = ext_run(adapter, "ext-ok", str(tmp_path))
    assert res["exit_code"] == 0 and "ext-ok" in res["output"]     # 真 subprocess


def test_t8_provider_adapter_selection() -> None:
    from factory_console.os_core_runtime import _provider_adapter

    assert _provider_adapter("codex").binary == "codex"
    assert _provider_adapter("claude").binary == "claude"
    with pytest.raises(ValueError):
        _provider_adapter("no-such-provider")


def test_t9_t10_t14_retry_creates_new_noderuns(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e1 = _exec(root, c)
    rt.run_execution_via_node_runtime(root, e1["execution_id"], prompt="fail",
                                      executor_fn=_ok_fn("exit 1"))
    e2 = _exec(root, c)
    rt.run_execution_via_node_runtime(root, e2["execution_id"], prompt="ok",
                                      executor_fn=_ok_fn("echo retry-ok"))
    d1, d2 = ex.get_execution(root, e1["execution_id"]), ex.get_execution(root, e2["execution_id"])
    # T9/T10/T11/T12/T13: 各自 NodeRun; 失败保留; 成功重试
    assert d1["status"] == "failed" and d2["status"] == "succeeded"
    assert d1["node_run_id"] != d2["node_run_id"]
    assert d1["task_node_id"] == d2["task_node_id"] == c["task_node"]
    from factory_console.node_runtime import get_node_run
    assert get_node_run(root, d1["node_run_id"])["state"] == "FAILED"    # T13
    assert get_node_run(root, d2["node_run_id"])["state"] == "COMPLETED"


# ---------------------------------------------------------------- T15-T18 boundaries

def test_t15_t16_t17_causal_and_company(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = _chain(root, "Company A")
    b = _chain(root, "Company B")
    with pytest.raises(ValueError):   # T15/T16 跨 company Resolution 拒绝
        ex.create_execution(root, task_node_id=a["task_node"], resolution_id=b["resolution"],
                            actor_identity_id=b["identity"], workforce_id=b["workforce"])
    with pytest.raises(ValueError):   # T17 actor/workforce 必须来自该 Resolution
        ex.create_execution(root, task_node_id=a["task_node"], resolution_id=a["resolution"],
                            actor_identity_id=b["identity"], workforce_id=a["workforce"])


def test_t18_reload_stable_mapping(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="reload",
                                      executor_fn=_ok_fn("echo reload"))
    d = ex.get_execution(root, e["execution_id"])
    # 重新读取 (SSOT 文件) 后映射稳定
    assert ex.get_execution(root, e["execution_id"])["node_run_id"] == d["node_run_id"]
    assert rt.resolve_node_run_execution(root, d["node_run_id"])["execution_id"] == e["execution_id"]


def test_t23_t24_t25_no_fake_execution(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    # T25/T23: 仅创建 Execution Record -> queued, 无 NodeRun, 不算真实执行
    assert e["status"] == "queued" and e["node_run_id"] == "" and e["runtime_ref"] == ""
    # T24: 失败 provider 路径不得产出 succeeded
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="fail",
                                      executor_fn=_ok_fn("exit 7"))
    assert ex.get_execution(root, e["execution_id"])["status"] == "failed"


def test_t26_t27_t28_boundaries(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    assert ex.list_executions(root, task_node_id=c["task_node"]) == []   # T26 Resolution 不执行
    e = _exec(root, c)
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="x",
                                      executor_fn=_ok_fn("echo x"))
    node = tn.get_task_node(root, c["task_node"])
    # T27: TaskNode 身份与状态独立于 Execution
    assert node["task_node_id"] == c["task_node"] and node["status"] == "pending"
    # T28: production_run (Factory) 未被本路径写入
    assert not (tmp_path / "workflows" / "runs").exists()


# ---------------------------------------------------------------- T20-T22, T30 E2E

def test_t20_t21_t22_t30_e2e_with_verification_evidence_outcome(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = _chain(root)
    e = _exec(root, c)
    rt.run_execution_via_node_runtime(root, e["execution_id"], prompt="e2e",
                                      executor_fn=_ok_fn("echo e2e-node-runtime"))
    done = ex.get_execution(root, e["execution_id"])
    assert done["status"] == "succeeded" and done["node_run_id"]
    v = ver.create_verification(root, execution_id=e["execution_id"], status="passed",
                                checks=[{"name": "node_run_completed", "passed": True}])
    evd = ev.create_evidence(root, execution_id=e["execution_id"], type="command_output",
                             source="node_runtime", locator=f"output:{e['execution_id']}",
                             verification_id=v["verification_id"])
    o = out.create_outcome(root, execution_id=e["execution_id"], status="accepted",
                           verification_refs=[v["verification_id"]],
                           evidence_refs=[evd["evidence_id"]],
                           result_refs=done["output_refs"])
    assert v["execution_id"] == e["execution_id"]
    assert evd["execution_id"] == e["execution_id"]
    assert o["execution_id"] == e["execution_id"] and o["status"] == "accepted"
    resolved = ev.resolve_evidence(root, evd["evidence_id"])
    assert Path(resolved["resolved_path"]).is_file()
