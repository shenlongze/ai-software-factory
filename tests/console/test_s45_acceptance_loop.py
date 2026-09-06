"""S45 — User Acceptance Loop 测试 (ACC-* canonical domain)。

覆盖 (S45 §23): creation/approve/request-change/invalid transition/
idempotent approve/idempotent change/artifact version binding/old approval
not transfer/release blocked before acceptance/release allowed after/
change creates real production/new artifact returns to acceptance/failure
does not produce acceptance.
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
def root(tmp_path: Path) -> Path:
    return tmp_path / "factory"


def _mk_ok_run(root: Path, task_id: str):
    """真实 P0 run: EXS + art + ver PASS + EVD。"""
    from factory_console.node_runtime import (
        register_node, create_node_run, finalize_node_run,
    )
    from factory_console.external_executor.executor import record_invocation
    from factory_console.verification import verify_pytest

    register_node(root, node_id="task-execution", name="t", node_type="task-execution")
    d = root / "proj"
    d.mkdir(exist_ok=True)
    (d / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    run = create_node_run(root, "task-execution", task_id=task_id, trigger="workflow")
    rec = record_invocation(root, executor_id="hermes", mode="blackbox",
                            host_agent="", prompt=task_id, project_dir=str(d),
                            exit_code=0, output="ok", error="", command="hermes",
                            duration_ms=5, task_id=task_id,
                            task_run_id=run["run_id"])
    v = verify_pytest(d)
    out = finalize_node_run(root, run["run_id"], success=True,
                            exs_id=rec["result_id"],
                            output=str(v.get("stdout", "")), actor="agent",
                            verification={"method": "pytest -q",
                                          "result": "pass" if v.get("status") == "PASS" else "fail",
                                          "stdout": str(v.get("stdout", ""))[-300:]})
    return run, rec, out


def _acc(root: Path, out: dict, run_id: str):
    from factory_console import acceptance_truth as at

    return at.begin_acceptance(root, artifact_id=out["artifact_id"], version=1,
                               verification_id=out["verification"]["verification_id"],
                               source_run_id=run_id)


class TestAcceptanceCore:
    def test_create_pending(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        assert acc["acceptance_id"].startswith("ACC-")
        assert acc["status"] == "PENDING"
        assert acc["artifact_id"] == out["artifact_id"]

    def test_approve(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        a = at.approve(root, acc["acceptance_id"], reviewer="user")
        assert a["status"] == "APPROVED"
        assert a["reviewer"] == "user"

    def test_approve_requires_ver_pass(self, root: Path) -> None:
        """ver FAIL → approve 拒绝 (不能批准未验证产品)。"""
        from factory_console import acceptance_truth as at
        from factory_console.node_runtime import (
            register_node, create_node_run, finalize_node_run,
        )
        from factory_console.external_executor.executor import record_invocation
        from factory_console.verification import verify_pytest

        register_node(root, node_id="task-execution", name="t",
                      node_type="task-execution")
        d = root / "bad"
        d.mkdir()
        (d / "test_f.py").write_text("def test_f():\n    assert False\n", encoding="utf-8")
        run = create_node_run(root, "task-execution", task_id="TASK-f", trigger="w")
        rec = record_invocation(root, executor_id="hermes", mode="blackbox",
                                host_agent="", prompt="x", project_dir=str(d),
                                exit_code=0, output="o", error="", command="hermes",
                                duration_ms=5, task_id="TASK-f",
                                task_run_id=run["run_id"])
        v = verify_pytest(d)
        out = finalize_node_run(root, run["run_id"], success=True,
                                exs_id=rec["result_id"], output="",
                                actor="agent",
                                verification={"method": "pytest -q", "result": "fail"})
        acc = at.begin_acceptance(root, artifact_id=out["artifact_id"], version=1,
                                  verification_id=out["verification"]["verification_id"],
                                  source_run_id=run["run_id"])
        with pytest.raises(ValueError):
            at.approve(root, acc["acceptance_id"], reviewer="user")

    def test_request_change(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        c = at.request_change(root, acc["acceptance_id"], comment="改成深色")
        assert c["status"] == "CHANGE_REQUESTED"
        assert c["decision"]["comment"] == "改成深色"

    def test_change_requires_comment(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        with pytest.raises(ValueError):
            at.request_change(root, acc["acceptance_id"], comment="")

    def test_invalid_transition_superseded_to_approved(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        at.supersede_older(root, out["artifact_id"], keep_version=99)
        st = at.get_acceptance(root, acc["acceptance_id"])
        assert st["status"] == "SUPERSEDED"
        with pytest.raises(ValueError):
            at.approve(root, acc["acceptance_id"], reviewer="user")


class TestIdempotency:
    def test_approve_twice_one_fact(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        at.approve(root, acc["acceptance_id"], reviewer="user")
        again = at.approve(root, acc["acceptance_id"], reviewer="user")
        assert again["acceptance_id"] == acc["acceptance_id"]
        assert again["status"] == "APPROVED"
        assert len([x for x in at.list_acceptances(root)]) == 1

    def test_change_twice_same_comment(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        at.request_change(root, acc["acceptance_id"], comment="改 A")
        c2 = at.request_change(root, acc["acceptance_id"], comment="改 A")
        assert c2["acceptance_id"] == acc["acceptance_id"]
        assert len([x for x in at.list_acceptances(root)]) == 1

    def test_begin_acceptance_idempotent(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        run, _, out = _mk_ok_run(root, "TASK-1")
        a1 = _acc(root, out, run["run_id"])
        a2 = _acc(root, out, run["run_id"])
        assert a1["acceptance_id"] == a2["acceptance_id"]


class TestVersionBinding:
    def test_old_approval_not_transfer(self, root: Path) -> None:
        """V1 APPROVED → V2 (新 artifact) 必须重新 PENDING (不继承)。"""
        from factory_console import acceptance_truth as at

        r1, _, o1 = _mk_ok_run(root, "TASK-v1")
        acc1 = _acc(root, o1, r1["run_id"])
        at.approve(root, acc1["acceptance_id"], reviewer="user")
        # V2 = 新 run 新 artifact (S44 absorb 每次新 art)
        r2, _, o2 = _mk_ok_run(root, "TASK-v2")
        acc2 = _acc(root, o2, r2["run_id"])
        assert acc2["acceptance_id"] != acc1["acceptance_id"]
        assert acc2["status"] == "PENDING", "新版本不能继承 APPROVED"
        # V1 历史仍 APPROVED (不覆盖)
        assert at.get_acceptance(root, acc1["acceptance_id"])["status"] == "APPROVED"

    def test_verification_binding(self, root: Path) -> None:
        from factory_console import acceptance_truth as at

        r1, _, o1 = _mk_ok_run(root, "TASK-v1")
        acc = _acc(root, o1, r1["run_id"])
        assert acc["verification_id"] == o1["verification"]["verification_id"]
        assert acc["source_run_id"] == r1["run_id"]


class TestReleaseGate:
    def test_release_blocked_before_acceptance(self, root: Path) -> None:
        from factory_console import acceptance_truth as at  # noqa: F401
        from factory_console import release_truth as rt

        run, rec, out = _mk_ok_run(root, "TASK-1")
        # ver PASS 但无 acceptance → require_acceptance gate REJECTED
        rel = rt.create_release(root, task_run_id=run["run_id"],
                                exs_id=rec["result_id"])
        g = rt.gate_release(root, rel["release_id"], require_acceptance=True)
        assert g["status"] == "REJECTED"
        assert any("acceptance" in m for m in g["gate"]["missing"])

    def test_release_allowed_after_acceptance(self, root: Path) -> None:
        from factory_console import acceptance_truth as at
        from factory_console import release_truth as rt

        run, rec, out = _mk_ok_run(root, "TASK-1")
        acc = _acc(root, out, run["run_id"])
        at.approve(root, acc["acceptance_id"], reviewer="user")
        rel = rt.create_release(root, task_run_id=run["run_id"],
                                exs_id=rec["result_id"])
        g = rt.gate_release(root, rel["release_id"], require_acceptance=True)
        assert g["status"] == "GATED", g["gate"]

    def test_backward_compat_no_acceptance_required(self, root: Path) -> None:
        """require_acceptance=False (旧调用) 行为不变。"""
        from factory_console import release_truth as rt

        run, rec, _ = _mk_ok_run(root, "TASK-1")
        rel = rt.create_release(root, task_run_id=run["run_id"],
                                exs_id=rec["result_id"])
        g = rt.gate_release(root, rel["release_id"])  # 默认 False
        assert g["status"] == "GATED"


class TestChangeCreatesProduction:
    def test_change_request_supersedes_then_new_cycle(self, root: Path) -> None:
        """CHANGE_REQUESTED → 新 run 新 art → 新 PENDING → approve。"""
        from factory_console import acceptance_truth as at

        r1, _, o1 = _mk_ok_run(root, "TASK-v1")
        acc1 = _acc(root, o1, r1["run_id"])
        at.request_change(root, acc1["acceptance_id"], comment="改功能")
        assert at.get_acceptance(root, acc1["acceptance_id"])["status"] == \
            "CHANGE_REQUESTED"
        # repair: 真实新 run (V2)
        r2, _, o2 = _mk_ok_run(root, "TASK-repair")
        acc2 = _acc(root, o2, r2["run_id"])
        assert acc2["status"] == "PENDING"
        at.approve(root, acc2["acceptance_id"], reviewer="user")
        assert at.get_acceptance(root, acc2["acceptance_id"])["status"] == "APPROVED"

    def test_failure_does_not_produce_acceptance(self, root: Path) -> None:
        """repair 执行失败 → 无 ACC (不允许 ACC 覆盖失败)。"""
        from factory_console import acceptance_truth as at
        from factory_console.node_runtime import (
            register_node, create_node_run, finalize_node_run,
        )
        from factory_console.external_executor.executor import record_invocation
        from factory_console.verification import verify_pytest

        register_node(root, node_id="task-execution", name="t",
                      node_type="task-execution")
        d = root / "bad"
        d.mkdir()
        (d / "test_f.py").write_text("def test_f():\n    assert False\n", encoding="utf-8")
        run = create_node_run(root, "task-execution", task_id="TASK-fail", trigger="w")
        rec = record_invocation(root, executor_id="hermes", mode="blackbox",
                                host_agent="", prompt="x", project_dir=str(d),
                                exit_code=0, output="o", error="", command="hermes",
                                duration_ms=5, task_id="TASK-fail",
                                task_run_id=run["run_id"])
        v = verify_pytest(d)
        out = finalize_node_run(root, run["run_id"], success=True,
                                exs_id=rec["result_id"], output="",
                                actor="agent",
                                verification={"method": "pytest -q", "result": "fail"})
        # ver FAIL → begin 仍可 (记录事实) 但 approve 禁; 模拟失败 run 无 PENDING
        acc = at.begin_acceptance(root, artifact_id=out["artifact_id"], version=1,
                                  verification_id=out["verification"]["verification_id"],
                                  source_run_id=run["run_id"])
        with pytest.raises(ValueError):
            at.approve(root, acc["acceptance_id"], reviewer="user")
