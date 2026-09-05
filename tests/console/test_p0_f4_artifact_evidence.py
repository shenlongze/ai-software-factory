"""P0-F4 — Artifact / Evidence / I8 Production Closure 测试。

D1-D4 冻结:
- Artifact canonical = S2 art-* (唯一 lifecycle; exs_id 新增; I8 收纳幂等)
- Evidence canonical = EVD-* (新域; 与 ev-* M3 legacy 隔离; 共享)
- D3: TaskRun→Artifact[], TaskRun→Verification[], Verification↔Artifact[],
       Verification→Evidence[]; Evidence 可共享
- I8: 生产执行产物必须经 create_artifact (finalize 内收纳, 非事后补)

覆盖: artifact identity/lifecycle/relation/idempotency/I8 / verification-artifact /
      EVD identity/relation/shared/idempotency / legacy isolation / F1-F3 兼容
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
# 依赖 tests/console/conftest.py 的 sys.path (仓库根 + factory-core), 不自插 factory-console
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402


@pytest.fixture()
def workroot(tmp_path: Path) -> Path:
    return tmp_path / "factory"


def _mk_run(root: Path, task_id: str = "TASK-f4") -> dict:
    from factory_console.node_runtime import create_node_run, register_node

    register_node(root, node_id="task-execution", name="Task Exec",
                  node_type="task-execution")
    return create_node_run(root, "task-execution", task_id=task_id, trigger="chain")


# ---------------------------------------------------------------- Artifact


class TestArtifactI8:
    """D4/I8: finalize 收纳 EXS 产物为 canonical art-* (幂等)。"""

    def test_success_absorbs_artifact(self, workroot: Path) -> None:
        from factory_console.node_runtime import finalize_node_run
        from factory_console.artifact_lifecycle import get_artifact, list_artifacts

        run = _mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                exs_id="EXS-f4a1",
                                output="task done output", actor="chain")
        assert out["state"] == "COMPLETED"
        assert out["artifact_id"].startswith("art-")
        art = get_artifact(workroot, out["artifact_id"])
        assert art is not None
        assert art["type"] == "report"
        assert art["exs_id"] == "EXS-f4a1"          # D3: art ↔ EXS
        assert art["node_run_id"] == run["run_id"]   # D3: art ↔ TaskRun
        assert art["state"] == "GENERATED"
        assert "output_tail" in (art.get("payload") or {})

    def test_artifact_idempotent_per_exs(self, workroot: Path) -> None:
        """同 EXS 重复 finalize (retry/callback) → 同 art-* (不双写)。"""
        from factory_console.node_runtime import finalize_node_run
        from factory_console.artifact_lifecycle import list_artifacts

        run = _mk_run(workroot)
        finalize_node_run(workroot, run["run_id"], success=True,
                          exs_id="EXS-idem", output="out")
        finalize_node_run(workroot, run["run_id"], success=True,
                          exs_id="EXS-idem", output="out")  # 幂等短路 (终态)
        arts = [a for a in list_artifacts(workroot) if a.get("exs_id") == "EXS-idem"]
        assert len(arts) == 1

    def test_no_exs_no_artifact(self, workroot: Path) -> None:
        """无 EXS (非 chain 场景) → 不收纳 (不伪造)。"""
        from factory_console.node_runtime import finalize_node_run
        from factory_console.artifact_lifecycle import list_artifacts

        run = _mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                verification={"result": "PASS"})  # 无 exs_id
        assert out["state"] == "COMPLETED"
        assert list_artifacts(workroot) == []  # workflow 域不在此收纳 (execute 路径)

    def test_failure_no_artifact(self, workroot: Path) -> None:
        """执行失败 → 不产 artifact。"""
        from factory_console.node_runtime import finalize_node_run
        from factory_console.artifact_lifecycle import list_artifacts

        run = _mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=False,
                                exs_id="EXS-fail", failure_reason="boom")
        assert out["state"] == "FAILED"
        assert list_artifacts(workroot) == []

    def test_i8_verification_linked_artifact(self, workroot: Path) -> None:
        """ver-* 关联 canonical art-* (D3: Verification ↔ Artifact)。"""
        from factory_console.node_runtime import finalize_node_run
        from factory_console.verification_domain import get_verification

        run = _mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                exs_id="EXS-f4b", output="x",
                                verification={"result": "PASS", "method": "pytest"})
        vid = out["verification"]["verification_id"]
        rec = get_verification(workroot, vid)
        assert out["artifact_id"] in (rec.get("artifact_ids") or [])  # ver ↔ art


class TestArtifactExecutePath:
    """workflow 域 execute_node_run: art-* + ver-* + EVD-*。"""

    def test_execute_produces_artifact_and_ver(self, workroot: Path) -> None:
        from factory_console.node_runtime import create_node_run, execute_node_run, register_node
        from factory_console.artifact_lifecycle import get_artifact
        from factory_console.verification_domain import get_verification

        register_node(workroot, node_id="gen", name="g", node_type="engineering")

        def good(inp):
            return {"ok": True, "output": {"code": "x"}, "patch_text": "diff",
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS", "tests": 1}}

        run2 = create_node_run(workroot, "gen", task_id="TASK-x")
        done = execute_node_run(workroot, run2["run_id"], executor_fn=good,
                                executor_name="exec", artifact_root=str(workroot))
        assert done["state"] == "COMPLETED"
        art = get_artifact(workroot, done["artifact_id"])
        assert art["node_run_id"] == run2["run_id"]
        ver = get_verification(workroot, done["verification"]["verification_id"])
        assert done["artifact_id"] in (ver.get("artifact_ids") or [])
        # EVD: verification dict 无真实输出内容 (method/stdout/stderr) → 不伪造 (F4 §15)
        from factory_console.evidence_domain import list_evidence

        evs = list_evidence(workroot, verification_id=done["verification"]["verification_id"])
        assert evs == []  # tests=1 无内容 → 无 EVD (禁止 fake evidence)

    def test_execute_attaches_real_evidence(self, workroot: Path) -> None:
        """verification 含真实 verifier 输出 → EVD 物化 (支撑结论)。"""
        from factory_console.node_runtime import (
            create_node_run, execute_node_run, register_node,
        )
        from factory_console.evidence_domain import list_evidence

        register_node(workroot, node_id="gen", name="g", node_type="engineering")

        def good_verbose(inp):
            return {"ok": True, "output": {"code": "x"}, "patch_text": "diff",
                    "artifact_type": "code_change",
                    "verification": {"result": "PASS", "method": "pytest -q",
                                     "stdout": "2 passed, 0 failed", "tests": 1}}

        run = create_node_run(workroot, "gen", task_id="TASK-y")
        done = execute_node_run(workroot, run["run_id"], executor_fn=good_verbose,
                                executor_name="exec", artifact_root=str(workroot))
        assert done["state"] == "COMPLETED"
        evs = list_evidence(workroot, verification_id=done["verification"]["verification_id"])
        assert len(evs) == 1 and evs[0]["evidence_type"] == "verifier_output"
        assert evs[0]["content"] == "2 passed, 0 failed"  # 真实 verifier 输出


# ---------------------------------------------------------------- Evidence


class TestEvidenceDomain:
    """EVD-*: identity/relation/shared/idempotency。"""

    def test_evd_identity_and_relation(self, workroot: Path) -> None:
        from factory_console.evidence_domain import (
            attach_evidence, get_evidence, list_evidence, materialize_evidence,
        )

        e = materialize_evidence(workroot, verification_id="ver-1",
                                 evidence_type="pytest_output", source_ref="pytest -q",
                                 content="2 passed, 0 failed")
        assert e["evidence_id"].startswith("EVD-")
        assert e["verification_refs"] == ["ver-1"]
        assert get_evidence(workroot, e["evidence_id"])["content"].startswith("2 passed")

    def test_evd_idempotent(self, workroot: Path) -> None:
        from factory_console.evidence_domain import count, materialize_evidence

        e1 = materialize_evidence(workroot, verification_id="ver-1",
                                  evidence_type="pytest_output", source_ref="pytest -q")
        e2 = materialize_evidence(workroot, verification_id="ver-1",
                                  evidence_type="pytest_output", source_ref="pytest -q")
        assert e1["evidence_id"] == e2["evidence_id"]
        assert count(workroot) == 1

    def test_evd_shared_across_verifications(self, workroot: Path) -> None:
        """一个 EVD 被多 Verification 引用 (D3: Evidence 可共享)。"""
        from factory_console.evidence_domain import (
            attach_evidence, get_evidence, materialize_evidence,
        )

        e = materialize_evidence(workroot, verification_id="ver-A",
                                 evidence_type="pytest_output", source_ref="pytest -q")
        assert attach_evidence(workroot, e["evidence_id"], "ver-B")
        refs = get_evidence(workroot, e["evidence_id"])["verification_refs"]
        assert refs == ["ver-A", "ver-B"]
        # 幂等 attach 不重复
        attach_evidence(workroot, e["evidence_id"], "ver-B")
        assert get_evidence(workroot, e["evidence_id"])["verification_refs"] == \
            ["ver-A", "ver-B"]

    def test_evd_requires_verification_and_type(self, workroot: Path) -> None:
        from factory_console.evidence_domain import materialize_evidence

        with pytest.raises(ValueError):
            materialize_evidence(workroot, verification_id="", evidence_type="x")
        with pytest.raises(ValueError):
            materialize_evidence(workroot, verification_id="ver-1", evidence_type="")

    def test_no_content_no_fake_evidence(self, workroot: Path) -> None:
        """finalize 无真实 verifier 输出 → 不伪造 EVD。"""
        from factory_console.node_runtime import finalize_node_run
        from factory_console.evidence_domain import count

        run = _mk_run(workroot)
        finalize_node_run(workroot, run["run_id"], success=True,
                          exs_id="EXS-ev0", output="out",
                          verification={"result": "PASS"})  # 无 method/content
        assert count(workroot) == 0  # 无证据材料 → 无 EVD


class TestLegacyIsolation:
    """旧 ev-* (M3) / exec ART-* 与 EVD-*/art-* 隔离。"""

    def test_legacy_evd_prefix_disjoint(self, workroot: Path) -> None:
        """EVD-* 不与 ev-* 冲突; legacy store 不进入新域。"""
        from factory_console.evidence_domain import count

        assert count(workroot) == 0
        # legacy ev-* 文件 (M3 EvidenceStore 路径) 不被 evidence_domain 读取
        legacy = workroot / "projects" / "p1" / "evidence"
        legacy.mkdir(parents=True)
        (legacy / "ev-abc123.json").write_text('{"bundle_id": "ev-abc123"}')
        assert count(workroot) == 0  # legacy ev-* 在 projects/ 下, EVD 在 <root>/evidence/

    def test_verify_evidence_ref_kept_f3(self, workroot: Path) -> None:
        """F3 ver.evidence_ref 保留 (EVD 由 evidence_domain 管理, 不冲突)。"""
        from factory_console.verification_domain import materialize_verification

        rec = materialize_verification(workroot, task_run_id="run-1", status="PASS",
                                       evidence_ref=["EVD-x"])
        assert rec["evidence_ref"] == ["EVD-x"]
