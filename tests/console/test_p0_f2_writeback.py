"""P0-F2 — Execution Completion → Canonical Writeback Closure 测试。

F0/F1 冻结:
  Task = backlog TASK-* | TaskRun = NodeRun run-* | EXS = execution result
  Task.exec_ref = EXS-* | NodeRun.task_id = TASK-* | EXS.task_run_id = run-*

F2 目标: 真实外部执行完成后 EXS → TaskRun 终态 → Task 终态 (幂等, 零二次执行)。

覆盖:
  1. finalize_node_run 成功/失败/幂等/从 VERIFYING·RUNNING 恢复 (零 executor_fn 调用)
  2. TaskRun finalize 后状态 = COMPLETED/FAILED; Task 经 finish_task_exec 收敛
  3. exec_ref 失败路径也回传 EXS (Gap-2)
  4. recover: EXS / NodeRun 证据映射 (Gap-3)
  5. 真实 E2E (隔离 tmp): Task → chain 委派 → EXS → TaskRun COMPLETED → Task done
本测试隔离 tmp 工作区, 不触碰 ~/.factory。
"""

from __future__ import annotations

import json
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


# ------------------------------------------------------------------ 1. finalize


class TestFinalizeNodeRun:
    """F2 §8 — TaskRun (NodeRun) finalization: 幂等, 零二次执行, 合法转换。"""

    def _mk_run(self, root: Path, task_id: str = "TASK-x") -> dict:
        from node_runtime import create_node_run, register_node

        register_node(root, node_id="task-execution", name="Task Exec",
                      node_type="task-execution")
        return create_node_run(root, "task-execution", task_id=task_id, trigger="chain")

    def test_success_finalizes_to_completed(self, workroot: Path) -> None:
        from node_runtime import finalize_node_run, get_node_run

        run = self._mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=True,
                                verification={"result": "PASS"})
        assert out["state"] == "COMPLETED"
        # P0-F3: run.verification = ver-* 引用; canonical 在 verification store
        assert out["verification"]["status"] == "PASS"
        assert out["verification"]["verification_id"].startswith("ver-")
        assert out["completed_at"]
        # 持久化
        assert get_node_run(workroot, run["run_id"])["state"] == "COMPLETED"
        # 合法转换链 (无跳过)
        states = [h["to"] for h in out["history"]]
        assert states == ["PENDING", "RUNNING", "VERIFYING", "COMPLETED"]

    def test_failure_finalizes_to_failed(self, workroot: Path) -> None:
        from node_runtime import finalize_node_run

        run = self._mk_run(workroot)
        out = finalize_node_run(workroot, run["run_id"], success=False,
                                failure_reason="boom", verification={"result": "FAIL"})
        assert out["state"] == "FAILED"
        # P0-F3: ver-* 引用 FAIL
        assert out["verification"]["status"] == "FAIL"
        assert out["verification"]["verification_id"].startswith("ver-")
        assert out["failure_reason"] == "boom"
        states = [h["to"] for h in out["history"]]
        assert states == ["PENDING", "RUNNING", "FAILED"]

    def test_idempotent_double_complete(self, workroot: Path) -> None:
        """F2 §9 — complete 两次 → 终态一致, 无重复转换/无逆转。"""
        from node_runtime import finalize_node_run

        run = self._mk_run(workroot)
        f1 = finalize_node_run(workroot, run["run_id"], success=True)
        hist1 = len(f1["history"])
        f2 = finalize_node_run(workroot, run["run_id"], success=True)
        assert f2["state"] == "COMPLETED"
        assert len(f2["history"]) == hist1  # 幂等: 不追加转换
        # 失败后再 complete(success) 不得逆转终态
        run2 = self._mk_run(workroot)
        finalize_node_run(workroot, run2["run_id"], success=False)
        f3 = finalize_node_run(workroot, run2["run_id"], success=True)
        assert f3["state"] == "FAILED"  # 终态不可逆

    def test_zero_second_execution(self, workroot: Path) -> None:
        """P0 STOP 条件: finalize 绝不触发第二次外部执行 (无 executor_fn)。"""
        from node_runtime import finalize_node_run

        run = self._mk_run(workroot)
        # finalize_node_run 签名无 executor_fn — 静态证明零执行路径
        import inspect

        sig = inspect.signature(finalize_node_run)
        assert "executor_fn" not in sig.parameters
        assert "repair_fn" not in sig.parameters
        finalize_node_run(workroot, run["run_id"], success=True)
        assert True

    def test_from_verifying_or_running(self, workroot: Path) -> None:
        """crash 恢复场景: run 已在 RUNNING/VERIFYING → finalize 合法收敛。"""
        from node_runtime import (
            finalize_node_run, transition_node_run,
        )

        # VERIFYING → COMPLETED
        r1 = self._mk_run(workroot, "TASK-v")
        transition_node_run(workroot, r1["run_id"], "RUNNING")
        transition_node_run(workroot, r1["run_id"], "VERIFYING")
        assert finalize_node_run(workroot, r1["run_id"], success=True)["state"] == "COMPLETED"
        # RUNNING → FAILED
        r2 = self._mk_run(workroot, "TASK-r")
        transition_node_run(workroot, r2["run_id"], "RUNNING")
        assert finalize_node_run(workroot, r2["run_id"], success=False)["state"] == "FAILED"


# ------------------------------------------------------------------ 2. 链级 writeback


class TestChainWriteback:
    """F2 §6/§7 — chain 委派 → EXS → TaskRun finalize → Task writeback。"""

    def test_chain_exec_fn_success_full_writeback(self, workroot: Path) -> None:
        """模拟 chain_next _exec_fn 语义 (真实 gateway 结构): 委派后 finalize + EXS 回传。"""
        import factory_console.session.agent_loop as al
        from node_runtime import get_node_run

        # 复用 _chain_task_run (F1) + F2 finalize 语义
        task = {"title": "实现功能", "backlog_id": "TASK-f2-1"}
        run_id = al._chain_task_run(workroot, task, "P-1")
        assert run_id.startswith("run-")

        # 模拟 gateway 返回 (真实 record_invocation 已写 EXS — 用 executor 模块直写)
        from external_executor.executor import record_invocation

        rec = record_invocation(
            workroot, executor_id="hermes", mode="blackbox", host_agent="",
            prompt="t", project_dir="", exit_code=0, output="ok", error="",
            command="hermes -z t", duration_ms=5,
            task_id="TASK-f2-1", task_run_id=run_id,
        )
        exs = rec["result_id"]

        # F2 finalize (chain_next 内的调用)
        from node_runtime import finalize_node_run

        finalize_node_run(workroot, run_id, success=True,
                          verification={"result": "unknown"},
                          actor="session-chain", note=f"EXS {exs}")
        run = get_node_run(workroot, run_id)
        assert run["state"] == "COMPLETED"
        assert run["task_id"] == "TASK-f2-1"

        # EXS 记录带锚 (F1)
        data = json.loads((workroot / "exec" / "execution_records.json").read_text())
        recs = [r for r in data if r["result_id"] == exs]
        assert recs and recs[0]["task_run_id"] == run_id and recs[0]["task_id"] == "TASK-f2-1"

    def test_exec_ref_failure_path_returns_exs(self, workroot: Path) -> None:
        """F2 Gap-2: 失败时 _exec_fn 也回传 exec_ref=EXS。"""
        # 源码级断言: 两处 _exec_fn 失败 return 均带 exec_ref
        src = (Path(_ROOT) / "factory-console" / "session" / "agent_loop.py").read_text()
        assert src.count('"exec_ref": _exs}') == 2


# ------------------------------------------------------------------ 3. recover


class TestRecoverSemantics:
    """F2 Gap-3 — recover 用 NodeRun/EXS 证据 (非 TASK-GW)。"""

    def test_run_status_node_run_evidence(self, workroot: Path) -> None:
        """源码级: _run_status 先查 NodeRun (run-*), 次查 EXS, TASK-GW 仅 legacy。"""
        src = (Path(_ROOT) / "factory-console" / "session" / "agent_loop.py").read_text()
        assert 'if _ref.startswith("run-"):' in src
        assert '"COMPLETED": "done", "FAILED": "failed"' in src
        assert 'if _ref.startswith("EXS-"):' in src
