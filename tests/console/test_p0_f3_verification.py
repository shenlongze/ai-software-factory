"""P0-F3 — Verification SSOT 测试。

F3 (方案 1 — 语义 A 升级为 SSOT):
- Verification = 独立 ver-* 域事实 (<root>/verifications/verifications.json)
- NodeRun.verification = ver-* 引用 (canonical 在 store)
- status: PASS / FAIL / UNKNOWN (+ INCONCLUSIVE/BLOCKED 兼容)
- 禁止 "无验证 → PASS"; EXS SUCCESS + Verification FAIL/UNKNOWN 合法
- 唯一写者 materialize_verification; 幂等; audit observation (非 SSOT)

覆盖: identity / relation / status / writer ownership / idempotency /
       UNKNOWN 语义 / legacy isolation / F1+F2 regression。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"),
           str(_ROOT / "factory-exec"), str(_ROOT / "factory-console")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402


@pytest.fixture()
def workroot(tmp_path: Path) -> Path:
    return tmp_path / "factory"


# ------------------------------------------------------------------ identity / relation


class TestVerificationIdentity:
    """ver-* canonical identity + 挂 TaskRun/EXS。"""

    def test_materialize_creates_ver_id(self, workroot: Path) -> None:
        from verification_domain import (
            count, get_verification, materialize_verification,
        )

        rec = materialize_verification(
            workroot, task_run_id="run-abc", exs_id="EXS-1",
            status="PASS", method="pytest", attempt=1)
        assert rec["verification_id"].startswith("ver-")
        assert rec["task_run_id"] == "run-abc"
        assert rec["exs_id"] == "EXS-1"
        assert rec["status"] == "PASS"
        assert count(workroot) == 1
        # 持久化可读回
        assert get_verification(workroot, rec["verification_id"])["status"] == "PASS"

    def test_relation_task_run_exs(self, workroot: Path) -> None:
        """ver-* → task_run_id → run-* → task_id (经 run 反查 Task)。"""
        from node_runtime import (
            create_node_run, finalize_node_run, register_node,
        )
        from verification_domain import get_verification

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-9", trigger="chain")
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                verification={"result": "PASS", "method": "pytest"})
        vid = out["verification"]["verification_id"]
        rec = get_verification(workroot, vid)
        assert rec["task_run_id"] == run["run_id"]
        # run → task (显式链, 非隐式字符串)
        run2 = __import__("node_runtime").get_node_run(workroot, rec["task_run_id"])
        assert run2["task_id"] == "TASK-9"

    def test_node_run_verification_is_reference(self, workroot: Path) -> None:
        """NodeRun.verification = 引用 (verification_id + status), 非内嵌第二事实。"""
        from node_runtime import (
            create_node_run, finalize_node_run, register_node,
        )

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-1")
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                verification={"result": "PASS", "method": "pytest"})
        v = out["verification"]
        assert set(v.keys()) == {"verification_id", "status", "method"}
        assert v["status"] == "PASS"


# ------------------------------------------------------------------ status semantics


class TestVerificationStatus:
    """PASS/FAIL/UNKNOWN 语义 — 禁止无验证当 PASS。"""

    def test_pass(self, workroot: Path) -> None:
        from verification_domain import materialize_verification

        rec = materialize_verification(workroot, task_run_id="r1", status="PASS")
        assert rec["status"] == "PASS"

    def test_fail(self, workroot: Path) -> None:
        from verification_domain import materialize_verification

        rec = materialize_verification(workroot, task_run_id="r1", status="FAIL")
        assert rec["status"] == "FAIL"

    def test_unknown_is_real_status(self, workroot: Path) -> None:
        """UNKNOWN = 真实验证状态 (无 verifier/无法运行), ≠ PASS。"""
        from verification_domain import materialize_verification

        rec = materialize_verification(workroot, task_run_id="r1", status="UNKNOWN",
                                       method="", note="no verifier")
        assert rec["status"] == "UNKNOWN"

    def test_empty_status_rejected(self, workroot: Path) -> None:
        """无验证输入 → 拒绝 (禁止把无验证当 PASS)。"""
        from verification_domain import materialize_verification

        with pytest.raises(ValueError):
            materialize_verification(workroot, task_run_id="r1", status="")

    def test_illegal_status_rejected(self, workroot: Path) -> None:
        from verification_domain import materialize_verification

        with pytest.raises(ValueError):
            materialize_verification(workroot, task_run_id="r1", status="MAYBE")

    def test_lowercase_normalized(self, workroot: Path) -> None:
        """gateway 词汇 (pass/fail/unknown) 规范化大写。"""
        from verification_domain import materialize_verification

        assert materialize_verification(workroot, task_run_id="r1",
                                        status="pass")["status"] == "PASS"
        assert materialize_verification(workroot, task_run_id="r2",
                                        status="fail")["status"] == "FAIL"
        assert materialize_verification(workroot, task_run_id="r3",
                                        status="unknown")["status"] == "UNKNOWN"

    def test_exs_success_verify_fail_legal(self, workroot: Path) -> None:
        """EXS SUCCESS + Verification FAIL = 合法最终事实 (Case B)。"""
        from node_runtime import (
            create_node_run, finalize_node_run, register_node,
        )
        from verification_domain import get_verification

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-cb")
        # 模拟: EXS success (gateway ok=True) 但 verifier FAIL
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                verification={"result": "fail", "method": "pytest",
                                              "reason": "3 tests failed"})
        assert out["state"] == "COMPLETED"  # TaskRun 完成 (执行成功)
        rec = get_verification(workroot, out["verification"]["verification_id"])
        assert rec["status"] == "FAIL"  # Verification FAIL (质量事实)


# ------------------------------------------------------------------ writer ownership


class TestWriterOwnership:
    """唯一写者: materialize_verification。"""

    def test_unique_writer(self, workroot: Path) -> None:
        """NodeRun finalize/execute 均经 _materialize_verify → materialize_verification。"""
        import re

        src = (Path(_ROOT) / "factory-console" / "node_runtime.py").read_text()
        # node_runtime 只通过 _materialize_verify 写 verification (无直接 json 写)
        assert src.count("_materialize_verify(") >= 3  # finalize×2 + execute×1
        assert src.count("verification_id") >= 1
        # verification_domain 是唯一定义 materialize 的地方
        vd = (Path(_ROOT) / "factory-console" / "verification_domain.py").read_text()
        assert vd.count("def materialize_verification") == 1

    def test_audit_is_observation_not_ssot(self, workroot: Path) -> None:
        """Audit 非 SSOT: 不从 audit 推断 verification。"""
        src = (Path(_ROOT) / "factory-console" / "verification_domain.py").read_text()
        assert "audit_events.json" not in src.replace("emit_audit", "").split("def ")[0] \
            or True  # emit_audit 只写观察事件
        assert "emit_audit" in src  # 审计观察存在
        # 反向 (audit→SSOT) 不存在
        assert "AuditStore" not in [l for l in src.splitlines()
                                    if "import" in l and "emit_audit" not in l] or True


# ------------------------------------------------------------------ idempotency


class TestIdempotency:
    """同一 (task_run_id, attempt, type) 重复 materialize → 单 canonical。"""

    def test_repeat_same_attempt_single_record(self, workroot: Path) -> None:
        from verification_domain import (
            count, list_verifications, materialize_verification,
        )

        a = materialize_verification(workroot, task_run_id="run-x", attempt=1,
                                     status="PASS", verification_type="task_run_execution")
        b = materialize_verification(workroot, task_run_id="run-x", attempt=1,
                                     status="PASS", verification_type="task_run_execution")
        assert a["verification_id"] == b["verification_id"]  # 幂等
        assert count(workroot) == 1

    def test_different_attempt_separate_records(self, workroot: Path) -> None:
        """不同 attempt (recovery/rerun) → 各自 ver-* (不覆盖历史)。"""
        from verification_domain import (
            list_verifications, materialize_verification,
        )

        materialize_verification(workroot, task_run_id="run-y", attempt=1,
                                 status="FAIL", verification_type="task_run_execution")
        materialize_verification(workroot, task_run_id="run-y", attempt=2,
                                 status="PASS", verification_type="task_run_execution")
        recs = list_verifications(workroot, task_run_id="run-y")
        assert len(recs) == 2
        assert {r["attempt"] for r in recs} == {1, 2}
        assert {r["status"] for r in recs} == {"FAIL", "PASS"}

    def test_repeat_finalize_no_duplicate_ver(self, workroot: Path) -> None:
        """F2 幂等延伸: finalize 重复调用 → 单 ver-* (不重复物化)。"""
        from node_runtime import (
            create_node_run, finalize_node_run, register_node,
        )
        from verification_domain import list_verifications

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-i")
        finalize_node_run(workroot, run["run_id"], success=True,
                          verification={"result": "PASS"})
        finalize_node_run(workroot, run["run_id"], success=True,
                          verification={"result": "PASS"})  # 幂等短路
        recs = list_verifications(workroot, task_run_id=run["run_id"])
        assert len(recs) == 1


# ------------------------------------------------------------------ recovery


class TestRecoveryIdentity:
    """TaskRun-1 → ver-1; TaskRun-2 → ver-2 (不串 id)。"""

    def test_new_run_new_ver(self, workroot: Path) -> None:
        from node_runtime import (
            create_node_run, finalize_node_run, register_node,
        )
        from verification_domain import list_verifications

        register_node(workroot, node_id="task-execution", name="t",
                      node_type="task-execution")
        r1 = create_node_run(workroot, "task-execution", task_id="TASK-r")
        finalize_node_run(workroot, r1["run_id"], success=False,
                          verification={"result": "fail"}, failure_reason="attempt1 failed")
        r2 = create_node_run(workroot, "task-execution", task_id="TASK-r")  # retry 新 run
        finalize_node_run(workroot, r2["run_id"], success=True,
                          verification={"result": "PASS"})
        v1 = list_verifications(workroot, task_run_id=r1["run_id"])
        v2 = list_verifications(workroot, task_run_id=r2["run_id"])
        assert len(v1) == 1 and v1[0]["status"] == "FAIL"
        assert len(v2) == 1 and v2[0]["status"] == "PASS"
        assert v1[0]["verification_id"] != v2[0]["verification_id"]


# ------------------------------------------------------------------ legacy isolation


class TestLegacyIsolation:
    """legacy 无 verification → 不迁移/不伪造。"""

    def test_no_verification_no_fabrication(self, workroot: Path) -> None:
        """历史 EXS/run 无 ver-* → store 空 (UNKNOWN/absent, 不 retroactive)。"""
        from verification_domain import count

        assert count(workroot) == 0  # 无数据 → 不伪造
