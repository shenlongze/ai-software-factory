"""P2-A — Release Truth 测试 (RELEASE-* canonical)。

契约 (docs/audits/2026-09-06-release-truth-p2-contract/):
- RELEASE-* entity / store / 唯一 writer / lifecycle / gate 消费 ver-*/EVD-*
- negative paths: ver FAIL → ≠RELEASED; missing EVD → ≠RELEASED
- idempotency / traceability / legacy rel-* 隔离 / P0/P1 consume-only
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402


@pytest.fixture()
def workroot(tmp_path: Path) -> Path:
    return tmp_path / "factory"


def _make_ok_run(root: Path, task_id: str = "TASK-rel"):
    """真实 P0 run: EXS + art + ver PASS + EVD (真实 pytest)。"""
    from factory_console.node_runtime import (
        finalize_node_run, register_node, create_node_run,
    )
    from factory_console.external_executor.executor import record_invocation
    from factory_console.verification import verify_pytest

    register_node(root, node_id="task-execution", name="t", node_type="task-execution")
    ok = root / "proj-ok"
    ok.mkdir()
    (ok / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    run = create_node_run(root, "task-execution", task_id=task_id, trigger="chain")
    rec = record_invocation(root, executor_id="hermes", mode="blackbox",
                            host_agent="", prompt=task_id, project_dir=str(ok),
                            exit_code=0, output="ok", error="", command="hermes",
                            duration_ms=10, task_id=task_id, task_run_id=run["run_id"])
    v = verify_pytest(ok)
    out = finalize_node_run(root, run["run_id"], success=True, exs_id=rec["result_id"],
                            output=str(v.get("stdout", "")), actor="test",
                            verification={"method": "pytest -q",
                                          "result": "pass" if v.get("status") == "PASS" else "fail",
                                          "stdout": str(v.get("stdout", ""))[-300:]})
    return run, rec, out


def _make_fail_run(root: Path, task_id: str = "TASK-rel-fail"):
    """真实 P0 run: EXS SUCCESS + ver FAIL (pytest 失败)。"""
    from factory_console.node_runtime import (
        finalize_node_run, register_node, create_node_run,
    )
    from factory_console.external_executor.executor import record_invocation
    from factory_console.verification import verify_pytest

    register_node(root, node_id="task-execution", name="t", node_type="task-execution")
    bad = root / "proj-fail"
    bad.mkdir()
    (bad / "test_fail.py").write_text("def test_fail():\n    assert False\n", encoding="utf-8")
    run = create_node_run(root, "task-execution", task_id=task_id, trigger="chain")
    rec = record_invocation(root, executor_id="hermes", mode="blackbox",
                            host_agent="", prompt=task_id, project_dir=str(bad),
                            exit_code=0, output="o", error="", command="hermes",
                            duration_ms=10, task_id=task_id, task_run_id=run["run_id"])
    v = verify_pytest(bad)
    out = finalize_node_run(root, run["run_id"], success=True, exs_id=rec["result_id"],
                            output=str(v.get("stdout", "")), actor="test",
                            verification={"method": "pytest -q",
                                          "result": "pass" if v.get("status") == "PASS" else "fail"})
    return run, rec, out


def _rt(workroot: Path):
    from factory_console import release_truth as rt

    return rt


class TestReleaseEntity:
    def test_identity_and_store(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        assert rel["release_id"].startswith("RELEASE-")
        assert rel["status"] == "CANDIDATE"
        assert run["run_id"] in (rel.get("task_run_id"),)
        # store 独立 (M3 rel-* 的 releases.json 不混入)
        assert (workroot / "releases" / "release_truth.json").is_file()

    def test_auto_collects_p0_facts(self, workroot: Path) -> None:
        """create 自动收集 canonical art/ver/EVD (consume P0, 不自产)。"""
        rt = _rt(workroot)
        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        assert rel["artifact_ids"] == [out["artifact_id"]]
        assert rel["verification_ids"] == [out["verification"]["verification_id"]]
        assert len(rel["evidence_ids"]) == 1  # pytest 输出 EVD

    def test_single_writer_store_no_external(self, workroot: Path) -> None:
        """release_truth store 仅模块内写 (无外部直写)。"""
        run, rec, _ = _make_ok_run(workroot)
        _rt(workroot).create_release(workroot, task_run_id=run["run_id"],
                                     exs_id=rec["result_id"])
        # 无 create_task/自跑 pytest 逻辑在此域
        import inspect
        import factory_console.release_truth as m

        src = inspect.getsource(m)
        assert "verify_pytest" not in src or "def " not in src.split("verify_pytest")[0]


class TestReleaseGate:
    def test_gate_pass(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        g = rt.gate_release(workroot, rel["release_id"])
        assert g["status"] == "GATED"
        assert g["gate"]["allowed"] is True

    def test_gate_fail_verification_not_pass(self, workroot: Path) -> None:
        """ver-* FAIL → gate REJECTED (≠RELEASED)。"""
        rt = _rt(workroot)
        run, rec, out = _make_fail_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        assert rel["verification_ids"], "fail run 也有 ver (FAIL)"
        g = rt.gate_release(workroot, rel["release_id"])
        assert g["status"] == "REJECTED"
        assert any("verification" in x for x in (g["gate"]["missing"] or []))
        # 无法 RELEASED
        from factory_console.governance_service import request_approval, decide_approval

        ar = request_approval(workroot, production_run_id="", artifact_ids=[],
                              requested_by="user", policy_id="release",
                              subject_type="release", subject_id=rel["release_id"])
        decide_approval(workroot, ar["approval_id"], decision="APPROVED", decided_by="admin")
        with pytest.raises(ValueError):
            rt.execute_release(workroot, rel["release_id"])
        assert rt.get_release(workroot, rel["release_id"])["status"] != "RELEASED"

    def test_gate_fail_missing_evidence(self, workroot: Path) -> None:
        """ver PASS 但 EVD 缺失 → REJECTED (evidence completeness)。"""
        rt = _rt(workroot)
        from factory_console.node_runtime import (
            finalize_node_run, register_node, create_node_run,
        )
        from factory_console.external_executor.executor import record_invocation

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        ok = workroot / "proj2"
        ok.mkdir()
        (ok / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
        run = create_node_run(workroot, "task-execution", task_id="TASK-noev", trigger="chain")
        rec = record_invocation(workroot, executor_id="hermes", mode="blackbox",
                                host_agent="", prompt="x", project_dir=str(ok),
                                exit_code=0, output="ok", error="", command="hermes",
                                duration_ms=10, task_id="TASK-noev",
                                task_run_id=run["run_id"])
        # verification 无 method/stdout → 无 EVD (F4 不伪造)
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                exs_id=rec["result_id"], output="",
                                actor="test",
                                verification={"result": "PASS"})  # 无内容 → 0 EVD
        # create_release 收集 ver 但 EVD 空
        rel = rt.create_release(workroot, task_run_id=run["run_id"],
                                exs_id=rec["result_id"])
        assert rel["verification_ids"], "有 ver"
        assert rel["evidence_ids"] == [], "EVD 空 (无真实内容)"
        g = rt.gate_release(workroot, rel["release_id"])
        assert g["status"] == "REJECTED"
        assert any("evidence" in x for x in (g["gate"]["missing"] or []))


class TestReleaseExecute:
    def test_execute_requires_approval(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, _ = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        rt.gate_release(workroot, rel["release_id"])
        with pytest.raises(ValueError):
            rt.execute_release(workroot, rel["release_id"])  # 无 approval → BLOCK

    def test_execute_released_with_approval(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        rt.gate_release(workroot, rel["release_id"])
        from factory_console.governance_service import request_approval, decide_approval

        ar = request_approval(workroot, production_run_id="",
                              artifact_ids=rel["artifact_ids"], requested_by="user",
                              policy_id="release", subject_type="release",
                              subject_id=rel["release_id"])
        decide_approval(workroot, ar["approval_id"], decision="APPROVED", decided_by="admin")
        ex = rt.execute_release(workroot, rel["release_id"])
        assert ex["status"] == "RELEASED"

    def test_supersede_revoke(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, _ = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        rt.supersede_release(workroot, rel["release_id"], by_release_id="RELEASE-2")
        assert rt.get_release(workroot, rel["release_id"])["status"] == "SUPERSEDED"
        rel2 = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"],
                                 idempotency_key="k2")
        rt.revoke_release(workroot, rel2["release_id"], reason="召回")
        assert rt.get_release(workroot, rel2["release_id"])["status"] == "REVOKED"


class TestIdempotencyTrace:
    def test_create_idempotent_same_run(self, workroot: Path) -> None:
        """同 (task_run, exs) 非 terminal → 返回现有 (不重复)。"""
        rt = _rt(workroot)
        run, rec, _ = _make_ok_run(workroot)
        a = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        b = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        assert a["release_id"] == b["release_id"]
        assert len(rt.list_releases(workroot)) == 1

    def test_idempotency_key(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, _ = _make_ok_run(workroot)
        a = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"],
                              idempotency_key="k1")
        b = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"],
                              idempotency_key="k1")
        assert a["release_id"] == b["release_id"]

    def test_trace_release_chain(self, workroot: Path) -> None:
        rt = _rt(workroot)
        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id=rec["result_id"])
        tr = rt.trace_release(workroot, rel["release_id"])
        kinds = [c[0] for c in tr["chain"]]
        assert "release" in kinds and "exs" in kinds and "task_run" in kinds
        assert "artifact" in kinds and "verification" in kinds and "evidence" in kinds
        assert tr["release"]["release_id"] == rel["release_id"]

    def test_no_ver_no_art_gate_reject(self, workroot: Path) -> None:
        """无 ver/art (空 run) → REJECTED。"""
        rt = _rt(workroot)
        from factory_console.node_runtime import register_node, create_node_run

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-empty",
                              trigger="chain")
        rel = rt.create_release(workroot, task_run_id=run["run_id"], exs_id="")
        g = rt.gate_release(workroot, rel["release_id"])
        assert g["status"] == "REJECTED"
        missing = " ".join(g["gate"]["missing"] or [])
        assert "artifact" in missing and "verification" in missing


class TestLegacyIsolation:
    def test_rel_star_untouched(self, workroot: Path) -> None:
        """M3 release_service 的 rel-* 与新 RELEASE-* 隔离 (独立文件)。"""
        run, rec, _ = _make_ok_run(workroot)
        _rt(workroot).create_release(workroot, task_run_id=run["run_id"],
                                     exs_id=rec["result_id"])
        # M3 store 无 RELEASE-* 混入
        import json

        m3 = workroot / "releases" / "releases.json"
        # release_truth 写独立文件; M3 文件不存在或空
        if m3.exists():
            data = json.loads(m3.read_text())
            assert all(not str(d.get("release_id", "")).startswith("RELEASE-")
                       for d in data)
        # 本域不产 rel-*
        from factory_console import release_truth as rt

        assert all(r["release_id"].startswith("RELEASE-")
                   for r in rt.list_releases(workroot))
