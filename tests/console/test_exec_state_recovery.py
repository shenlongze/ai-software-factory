"""tests/console/test_exec_state_recovery.py — P2-②: Running Crash/Restart Recovery。

Contract (orchestration-recovery-contract.md):
- Run done → 同步 done (不重跑) / Run failed → 同步 failed (不重跑)
- Run running/missing/exec_ref 缺失 → UNKNOWN → todo 重排队 (不伪造)
- 幂等: 连续 recover 无变化; CANCELLED/FAILED/DONE/BLOCKED/todo 不动
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory_console.session.exec_state import ExecState


def _mk(tasks: list[dict]) -> ExecState:
    st = ExecState("s1")
    st.state["plan"] = {"goal": "g"}
    st.state["status"] = "running"
    st.state["tasks"] = tasks
    return st


def _t(title: str, status: str = "running", bid: str = "T-1",
       deps: list[str] | None = None, ref: str = "") -> dict:
    return {"title": title, "backlog_id": bid, "dependency": deps or [],
            "status": status, "priority": "P2", "exec_ref": ref,
            "result": "", "verify": {}}


def _ok_fn(task: dict) -> dict:
    return {"ok": True, "output": f"done {task['title']}", "exec_ref": "RUN-1"}


# R1: running + Run done → 同步 done, 不重跑
def test_r1_run_done_syncs_done() -> None:
    st = _mk([_t("A", ref="RUN-1")])
    r = st.recover(lambda ref: "done")
    assert r["count"] == 1
    assert st.state["tasks"][0]["status"] == "done"
    assert st.state["tasks"][0]["verify"]["result"] == "done"


# R2: running + Run failed → 同步 failed
def test_r2_run_failed_syncs_failed() -> None:
    st = _mk([_t("A", ref="RUN-1")])
    st.recover(lambda ref: "failed")
    assert st.state["tasks"][0]["status"] == "failed"


# R3: running + Run running → UNKNOWN → todo
def test_r3_run_running_unknown_requeue() -> None:
    st = _mk([_t("A", ref="RUN-1")])
    st.recover(lambda ref: "running")
    t = st.state["tasks"][0]
    assert t["status"] == "todo", "UNKNOWN → todo 重排队"
    assert t["verify"]["result"] == "unknown"


# R4: running + Run missing → UNKNOWN → todo
def test_r4_run_missing_unknown_requeue() -> None:
    st = _mk([_t("A", ref="RUN-1")])
    st.recover(lambda ref: None)
    assert st.state["tasks"][0]["status"] == "todo"
    assert st.state["tasks"][0]["verify"]["result"] == "unknown"


# R5: running + exec_ref missing → UNKNOWN → todo, 不 crash
def test_r5_exec_ref_missing_unknown_requeue() -> None:
    st = _mk([_t("A", ref="")])
    st.recover(lambda ref: "done")  # 无 ref → 不查询 → UNKNOWN
    t = st.state["tasks"][0]
    assert t["status"] == "todo"
    assert t["verify"]["result"] == "unknown"


# R6: 连续 recover 幂等
def test_r6_recover_idempotent() -> None:
    st = _mk([_t("A", ref="RUN-1"), _t("B", status="done", bid="T-2")])
    st.recover(lambda ref: "done")
    first = json.dumps(st.state, sort_keys=True)
    r2 = st.recover(lambda ref: "done")
    assert r2["count"] == 0, "第二次无变化"
    assert json.dumps(st.state, sort_keys=True) == first


# R7: done/failed/cancelled/blocked/todo 不动
def test_r7_non_running_untouched() -> None:
    st = _mk([
        _t("D", status="done", bid="T-1"),
        _t("F", status="failed", bid="T-2"),
        _t("C", status="cancelled", bid="T-3"),
        _t("B", status="blocked", bid="T-4"),
        _t("T", status="todo", bid="T-5"),
    ])
    r = st.recover(lambda ref: "done")
    assert r["count"] == 0
    sts = [t["status"] for t in st.state["tasks"]]
    assert sts == ["done", "failed", "cancelled", "blocked", "todo"]


# R8: 恢复后依赖 gate 正常 (blocked/waiting 不错误执行)
def test_r8_dependency_gate_after_recovery() -> None:
    st = _mk([
        _t("A", ref="RUN-1", bid="TA"),
        _t("B", status="todo", bid="TB", deps=["TA"]),
    ])
    st.recover(lambda ref: "running")  # A → UNKNOWN → todo
    # next: A 无依赖 → ready; B 依赖 A (todo) → waiting
    r = st.next(_ok_fn)
    assert r["task"] == "A", "A 重排队后可执行"
    st.state["tasks"][0]["status"] = "done"
    st.state["tasks"][0]["exec_ref"] = "RUN-2"
    r2 = st.next(_ok_fn)
    assert r2["task"] == "B", "A done 后 B ready"


# R9: restart 模拟 — running → persist → reload → recover → next 继续
def test_r9_restart_recover_continue(tmp_path: Path) -> None:
    st = _mk([_t("A", ref="RUN-1", bid="TA"), _t("B", status="todo", bid="TB", deps=["TA"])])
    st.save(tmp_path)
    st2 = ExecState.load(tmp_path, "s1")  # 模拟重启
    st2.recover(lambda ref: "done")  # A Run done → 同步 done
    st2.save(tmp_path)
    st3 = ExecState.load(tmp_path, "s1")
    r = st3.next(_ok_fn)
    assert r["task"] == "B", "A 同步 done 后 B ready (不卡死)"
    assert st3.state["tasks"][0]["status"] == "done", "A 保持 done 不重跑"


# R10: Run done + backlog 未回写 → recovery 补齐 + 不创建第二个 Run
def test_r10_run_done_backlog_not_written(tmp_path: Path) -> None:
    from factory_console.external_executor.task_registry import ExternalTaskRegistry

    reg = ExternalTaskRegistry.load(tmp_path)
    reg.create(task="A", owner="exe")  # RUN running (无 tid 引用)
    # 直接用已知 tid 模拟 Run done
    tid = next(iter(reg.tasks))
    reg.update(tid, status="done")
    st = _mk([_t("A", ref=tid)])
    st.recover(lambda ref: reg.get(ref)["status"] if reg.get(ref) else None)
    assert st.state["tasks"][0]["status"] == "done"
    # 不创建第二个 Run
    assert len(reg.tasks) == 1
