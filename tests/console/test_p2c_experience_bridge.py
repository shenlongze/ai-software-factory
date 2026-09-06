"""P2-C — Experience Bridge 测试。

契约 (docs/audits/2026-09-06-p2c-experience-bridge-contract/):
- exp-* canonical (memory/experience_store.json); ExperienceBridge 唯一 writer
- (source, source_id) 幂等 (1→1); anchors task_run_id/exs_id/release_id
- 单向派生 (不反向写生产); 失败不伪装成功
- release → exp (RELEASED→SUCCESS / REJECTED→FAILURE)
- legacy 隔离: 旧 exp 无 FK 兼容; intelligence/experiences 不被读
- E2E 语义: 真实 run/EXS/ver/art/EVD → RELEASE → exp + reverse trace
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


def _exp_store(root: Path):
    from factory_console.memory.experience_store import ExperienceStore

    return ExperienceStore.from_workspace(root)


def _make_ok_run(root: Path, task_id: str = "TASK-e2"):
    """真实 P0 run: EXS + art + ver PASS + EVD。"""
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


class TestBridgeCore:
    def test_record_and_anchor(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        e = eb.record(workroot, source="execution", source_id="run-1:EXS-1",
                      type_="SUCCESS_PATTERN", success=True,
                      task_run_id="run-1", exs_id="EXS-1")
        assert e["id"].startswith("exp-")
        assert e["task_run_id"] == "run-1" and e["exs_id"] == "EXS-1"
        # 真实落盘 canonical store
        recs = _exp_store(workroot).records()
        assert any(r.id == e["id"] for r in recs)

    def test_idempotent_source_id(self, workroot: Path) -> None:
        """同 (source, source_id) → 1 exp (1→1)。"""
        from factory_console import experience_bridge as eb

        a = eb.record(workroot, source="execution", source_id="run-1:EXS-1",
                      type_="SUCCESS_PATTERN", success=True)
        b = eb.record(workroot, source="execution", source_id="run-1:EXS-1",
                      type_="SUCCESS_PATTERN", success=True)
        assert a["id"] == b["id"]
        assert len(_exp_store(workroot).records()) == 1

    def test_requires_source_and_source_id(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        with pytest.raises(ValueError):
            eb.record(workroot, source="", source_id="x", type_="SUCCESS_PATTERN",
                      success=True)
        with pytest.raises(ValueError):
            eb.record(workroot, source="x", source_id="", type_="SUCCESS_PATTERN",
                      success=True)


class TestExecutionBridge:
    def test_success_execution(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        e = eb.record_execution(workroot, task_run_id="run-x", exs_id="EXS-x",
                                success=True, ver_status="PASS")
        assert e["type"] == "SUCCESS_PATTERN" and e["success"] is True
        assert e["source"] == "execution" and e["source_id"] == "run-x:EXS-x"

    def test_ver_fail_not_fake_success(self, workroot: Path) -> None:
        """EXS SUCCESS + ver FAIL → FAILURE_PATTERN (不伪装成功)。"""
        from factory_console import experience_bridge as eb

        e = eb.record_execution(workroot, task_run_id="run-y", exs_id="EXS-y",
                                success=True, ver_status="FAIL")
        assert e["type"] == "FAILURE_PATTERN" and e["success"] is False

    def test_no_anchor_no_record(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        assert eb.record_execution(workroot, task_run_id="", exs_id="",
                                   success=True) == {}

    def test_retry_idempotent(self, workroot: Path) -> None:
        """重复 finalize (同 run+exs) → 1 exp。"""
        from factory_console import experience_bridge as eb

        e1 = eb.record_execution(workroot, task_run_id="run-r", exs_id="EXS-r",
                                 success=True, ver_status="PASS")
        e2 = eb.record_execution(workroot, task_run_id="run-r", exs_id="EXS-r",
                                 success=True, ver_status="PASS")
        assert e1["id"] == e2["id"]
        assert len(_exp_store(workroot).records()) == 1

    def test_recovery_new_run_new_exp(self, workroot: Path) -> None:
        """recovery = 新 run → 新 exp; 旧 FAIL 保留。"""
        from factory_console import experience_bridge as eb

        eb.record_execution(workroot, task_run_id="run-1", exs_id="EXS-1",
                            success=False, ver_status="FAIL")
        e2 = eb.record_execution(workroot, task_run_id="run-2", exs_id="EXS-2",
                                 success=True, ver_status="PASS")
        assert e2["success"] is True and e2["task_run_id"] == "run-2"
        recs = _exp_store(workroot).records()
        assert len(recs) == 2  # 旧 FAIL 不覆盖


class TestReleaseBridge:
    def test_released_success(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        e = eb.record_release(workroot, "RELEASE-1", outcome="RELEASED")
        assert e["type"] == "SUCCESS_PATTERN" and e["success"] is True
        assert e["release_id"] == "RELEASE-1" and e["source"] == "release"
        assert e["source_id"] == "RELEASE-1"

    def test_rejected_failure(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        e = eb.record_release(workroot, "RELEASE-2", outcome="REJECTED",
                              gate_missing=["verification"])
        assert e["type"] == "FAILURE_PATTERN" and e["success"] is False
        assert "verification" in e["problem"]

    def test_release_idempotent(self, workroot: Path) -> None:
        from factory_console import experience_bridge as eb

        e1 = eb.record_release(workroot, "RELEASE-3", outcome="RELEASED")
        e2 = eb.record_release(workroot, "RELEASE-3", outcome="RELEASED")
        assert e1["id"] == e2["id"]


class TestFullChain:
    def test_release_to_experience_full_chain(self, workroot: Path) -> None:
        """真实: run → EXS → art → ver → EVD → RELEASE → exp (bridge)。"""
        from factory_console import experience_bridge as eb
        from factory_console import release_truth as rt

        run, rec, out = _make_ok_run(workroot)
        rel = rt.create_release(workroot, task_run_id=run["run_id"],
                                exs_id=rec["result_id"])
        rt.gate_release(workroot, rel["release_id"])
        # governance approval
        from factory_console.governance_service import request_approval, decide_approval

        ar = request_approval(workroot, production_run_id="",
                              artifact_ids=rel["artifact_ids"], requested_by="user",
                              policy_id="release", subject_type="release",
                              subject_id=rel["release_id"])
        decide_approval(workroot, ar["approval_id"], decision="APPROVED",
                        decided_by="admin")
        ex = rt.execute_release(workroot, rel["release_id"])
        assert ex["status"] == "RELEASED"
        # bridge: RELEASE → exp (真实 canonical)
        e = eb.record_release(workroot, ex["release_id"], outcome=ex["status"])
        assert e["release_id"] == ex["release_id"]
        # execution exp
        e2 = eb.record_execution(workroot, task_run_id=run["run_id"],
                                 exs_id=rec["result_id"], success=True,
                                 ver_status="PASS")
        assert e2["exs_id"] == rec["result_id"]

    def test_reverse_trace(self, workroot: Path) -> None:
        """exp → release → run → task (FK-based)。"""
        from factory_console import experience_bridge as eb

        run, rec, _ = _make_ok_run(workroot, task_id="TASK-rev")
        e = eb.record_execution(workroot, task_run_id=run["run_id"],
                                exs_id=rec["result_id"], success=True,
                                ver_status="PASS")
        tr = eb.trace_experience(workroot, e["id"])
        assert tr["experience"]["id"] == e["id"]
        assert tr["run"] is not None and tr["run"]["run_id"] == run["run_id"]
        # run→task FK 存在 (task_id 在 run 记录); backlog 反查在全链 E2E 验证
        assert tr["run"].get("task_id") == "TASK-rev"
        assert any(k[0] == "task_run" for k in tr["chain"])


class TestLegacyIsolation:
    def test_legacy_no_fk_records_load(self, workroot: Path) -> None:
        """旧 84 条 (无 FK) from_dict 兼容 (缺省空 anchor 不崩)。"""
        from factory_console.memory.experience import ExperienceRecord
        from factory_console.memory.experience_store import ExperienceStore

        store = ExperienceStore.from_workspace(workroot)
        legacy = {"id": "exp-abc", "type": "SUCCESS_PATTERN", "source": "execution_records",
                  "success": True, "task": "登录功能"}
        store.add(ExperienceRecord.from_dict(legacy))
        recs = store.records()
        assert recs[0].task_run_id == "" and recs[0].exs_id == ""  # 不伪造 FK

    def test_intelligence_not_read(self, workroot: Path) -> None:
        """bridge 不读 intelligence/experiences.json (LEGACY 隔离)。"""
        from factory_console import experience_bridge as eb

        # 造 intelligence/experiences.json (LEGACY)
        import json

        d = workroot / "intelligence"
        d.mkdir(parents=True)
        (d / "experiences.json").write_text(
            json.dumps({"experiences": {"uuid1": {"domain": "agent"}}}))
        # bridge record 只写 memory store; 不受 intelligence 影响
        e = eb.record(workroot, source="execution", source_id="s1",
                      type_="SUCCESS_PATTERN", success=True)
        assert e["id"].startswith("exp-")
        assert len(_exp_store(workroot).records()) == 1
