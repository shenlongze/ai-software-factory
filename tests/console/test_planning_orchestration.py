"""tests/console/test_planning_orchestration.py — P1-FIX: 执行链依赖感知。

验证 ExecState.next:
- Ready = todo + 全部依赖 done
- 链式 A→B→C 顺序执行, 未满足依赖不执行
- 失败传播: 依赖 failed → 下游 blocked
- 无依赖任务行为不变 (第一个 todo)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory_console.session.exec_state import ExecState


def _mk_state(tasks: list[dict]) -> ExecState:
    st = ExecState("s1")
    st.state["plan"] = {"goal": "g"}
    st.state["status"] = "running"
    st.state["tasks"] = tasks
    return st


def _t(title: str, bid: str, deps: list[str] | None = None, status: str = "todo") -> dict:
    return {"title": title, "backlog_id": bid, "dependency": deps or [], "status": status,
            "priority": "P2"}


def _ok_fn(task: dict) -> dict:
    return {"ok": True, "output": f"done {task['title']}"}


def _fail_fn(task: dict) -> dict:
    return {"ok": False, "error": f"fail {task['title']}"}


def test_chain_dependency_gate() -> None:
    """A→B→C: B 依赖 A, C 依赖 B — 未满足依赖不执行。"""
    st = _mk_state([_t("A", "TA", []), _t("B", "TB", ["TA"]), _t("C", "TC", ["TB"])])
    # 第一轮: 只有 A ready
    r1 = st.next(_ok_fn)
    assert r1["task"] == "A" and r1["status"] == "done"
    # 第二轮: B ready (A done)
    r2 = st.next(_ok_fn)
    assert r2["task"] == "B"
    # 第三轮: C ready (B done)
    r3 = st.next(_ok_fn)
    assert r3["task"] == "C"
    assert st.state["status"] == "done"


def test_dependency_not_done_blocks() -> None:
    """B 依赖 A, A 未完成 → B 不能执行 (waiting)。"""
    st = _mk_state([_t("B", "TB", ["TA"]), _t("A", "TA", [])])
    # 列表顺序 B 在前, 但 B 依赖 A 未 done → 跳过 B 选 A
    r1 = st.next(_ok_fn)
    assert r1["task"] == "A", "必须跳过依赖未满足的 B, 执行 A"
    r2 = st.next(_ok_fn)
    assert r2["task"] == "B"
    assert r2["status"] == "done"


def test_failure_propagates_blocked() -> None:
    """A failed → 依赖 A 的 B 不得执行 → blocked。"""
    st = _mk_state([_t("A", "TA", []), _t("B", "TB", ["TA"])])
    r1 = st.next(_fail_fn)
    assert r1["status"] == "failed"
    r2 = st.next(_ok_fn)
    assert r2["ok"] is False
    assert r2.get("blocked") == ["B"], f"B 应被阻塞: {r2}"
    assert st.state["tasks"][1]["status"] == "blocked"


def test_fanout_ready() -> None:
    """A→B, A→C: A done 后 B/C 都 ready (依赖感知选择第一个)。"""
    st = _mk_state([_t("A", "TA", []), _t("B", "TB", ["TA"]), _t("C", "TC", ["TA"])])
    r1 = st.next(_ok_fn)
    assert r1["task"] == "A"
    # A done 后: B 或 C ready
    r2 = st.next(_ok_fn)
    assert r2["task"] in ("B", "C")
    r3 = st.next(_ok_fn)
    assert r3["task"] in ("B", "C")


def test_merge_wait() -> None:
    """B→D, C→D: D 必须等 B+C 都 done。"""
    st = _mk_state([_t("B", "TB", []), _t("C", "TC", []), _t("D", "TD", ["TB", "TC"])])
    st.next(_ok_fn)  # B done
    st.next(_ok_fn)  # C done
    r3 = st.next(_ok_fn)
    assert r3["task"] == "D", "D 在 B+C 完成后才 ready"
