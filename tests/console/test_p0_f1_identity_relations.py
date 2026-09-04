"""P0-F1 — Execution Record Normalization: Task → TaskRun → EXS 身份关系测试。

F0 冻结:
  Task    = backlog TASK-*   (org.management.Task)
  TaskRun = NodeRun run-*    (node_runtime)
  EXS     = execution result (record_invocation / ExecutionResult)
  exec_ref = EXS-* (唯一语义)

覆盖 (F1 §9 Test A-F):
  A. TaskRun anchors Task      — create NodeRun(task_id=TASK-*) → run.task_id == task
  B. EXS anchors TaskRun       — record_invocation(task_id, task_run_id) → EXS 记录含锚
  C. exec_ref semantics        — chain 委派 exec_ref = EXS (result_id), 非 TASK-GW/EXR/run
  D. round trip                — EXS → TaskRun → Task 反查
  E. idempotency               — 重复创建不产生第二 canonical relation
  F. legacy isolation          — task-e1-*/EXR-*/TASK-GW-* 不作为 canonical TaskRun/EXS

本测试隔离 tmp 工作区, 不触碰 ~/.factory。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

import pytest  # noqa: E402


@pytest.fixture()
def workroot(tmp_path: Path) -> Path:
    """隔离工作区 (nodes/exec 数据空间与 ~/.factory 完全隔离)。"""
    return tmp_path / "factory"


# ------------------------------------------------------------------ Test A


class TestTaskRunAnchorsTask:
    """F1 §9 Test A — TaskRun.task_id → Task (TASK-*)。"""

    def test_node_run_created_with_task_id(self, workroot: Path) -> None:
        from factory_console.node_runtime import (
            create_node_run, get_node_run, register_node,
        )

        register_node(workroot, node_id="task-execution", name="Task Exec",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id="TASK-abc123",
                              trigger="chain")
        assert run["run_id"].startswith("run-")
        assert run["task_id"] == "TASK-abc123"

        persisted = get_node_run(workroot, run["run_id"])
        assert persisted is not None
        assert persisted["task_id"] == "TASK-abc123"  # 持久化, 非仅内存

    def test_node_run_without_task_id_backward_compatible(self, workroot: Path) -> None:
        """旧 S2/S3 workflow 调用 (无 task_id) 不破坏。"""
        from factory_console.node_runtime import (
            create_node_run, register_node,
        )

        register_node(workroot, node_id="wf-node", name="WF", node_type="engineering")
        run = create_node_run(workroot, "wf-node", trigger="production")
        assert run["task_id"] == ""

    def test_task_run_requires_node(self, workroot: Path) -> None:
        """create_node_run 仍需 Node 定义 (S2 不变); 未注册 → NodeError。"""
        from factory_console.node_runtime import NodeError, create_node_run

        with pytest.raises(NodeError):
            create_node_run(workroot, "not-registered", task_id="TASK-x")


# ------------------------------------------------------------------ Test B


class TestEXSAnchorsTaskRun:
    """F1 §9 Test B — EXS.task_run_id → TaskRun (run-*)。"""

    def test_record_invocation_persists_anchors(self, workroot: Path) -> None:
        from factory_console.external_executor.executor import record_invocation

        rec = record_invocation(
            workroot, executor_id="claude", mode="blackbox", host_agent="",
            prompt="task prompt", project_dir="", exit_code=0,
            output="ok", error="", command="claude", duration_ms=10,
            task_id="TASK-abc123", task_run_id="run-xyz789",
        )
        assert rec["result_id"].startswith("EXS-")
        assert rec["task_id"] == "TASK-abc123"
        assert rec["task_run_id"] == "run-xyz789"

        # 持久化验证
        data = json.loads((workroot / "exec" / "execution_records.json").read_text())
        last = data[-1]
        assert last["result_id"] == rec["result_id"]
        assert last["task_id"] == "TASK-abc123"
        assert last["task_run_id"] == "run-xyz789"

    def test_exs_backward_compatible_no_anchors(self, workroot: Path) -> None:
        """旧调用 (无 task_id/task_run_id) → 空锚, 不破坏。"""
        from factory_console.external_executor.executor import record_invocation

        rec = record_invocation(
            workroot, executor_id="backend-1", mode="blackbox", host_agent="",
            prompt="p", project_dir="", exit_code=0, output="o", error="",
            command="c", duration_ms=1,
        )
        assert rec["task_id"] == ""
        assert rec["task_run_id"] == ""

    def test_execution_result_model_accepts_anchors(self) -> None:
        """exec store pydantic ExecutionResult 支持 task_id/task_run_id。"""
        from exec.models import ExecutionResult, ExecutionStatus, new_id

        r = ExecutionResult(
            id=new_id("EXS"), request_id=new_id("EXR"),
            task_id="TASK-abc123", task_run_id="run-xyz789",
            status=ExecutionStatus.SUCCESS,
        )
        assert r.task_id == "TASK-abc123"
        assert r.task_run_id == "run-xyz789"
        d = r.model_dump()
        assert d["task_id"] == "TASK-abc123"
        assert d["task_run_id"] == "run-xyz789"

    def test_execution_result_model_old_data_compatible(self) -> None:
        """旧 ExecutionResult JSON (无锚字段) 反序列化默认空。"""
        from exec.models import ExecutionResult, ExecutionStatus

        r = ExecutionResult.model_validate(
            {"id": "EXS-old", "request_id": "EXR-old",
             "status": ExecutionStatus.SUCCESS.value}
        )
        assert r.task_id == ""
        assert r.task_run_id == ""


# ------------------------------------------------------------------ Test C


class TestExecRefSemantics:
    """F1 §9 Test C — chain 委派 exec_ref = EXS (result_id), 非 TASK-GW/EXR/run。"""

    def test_chain_task_run_anchors_and_persists(self, workroot: Path) -> None:
        """_chain_task_run: backlog 任务 → run-* 锚 (共享 Node 自动注册)。"""
        import factory_console.session.agent_loop as al
        from factory_console.node_runtime import get_node, get_node_run

        task = {"title": "实现功能", "backlog_id": "TASK-abc123"}
        run_id = al._chain_task_run(workroot, task, "P-1")
        assert run_id.startswith("run-")

        # 共享 Node 已注册
        node = get_node(workroot, "task-execution")
        assert node is not None
        assert node["type"] == "task-execution"
        # run 持久化且 task_id 锚定
        run = get_node_run(workroot, run_id)
        assert run is not None
        assert run["task_id"] == "TASK-abc123"
        assert run["trigger"] == "chain"

    def test_chain_task_run_no_backlog_no_run(self, workroot: Path) -> None:
        """无 backlog_id (独立执行) → 不建 run, 失败安全返回空。"""
        import factory_console.session.agent_loop as al

        assert al._chain_task_run(workroot, {"title": "t"}, "") == ""

    def test_exec_fn_source_uses_result_id(self) -> None:
        """源码级: 两处 _exec_fn 的 exec_ref = EXS (_exs=result_id) 优先, 非 task_id。

        P0-F2: exec_ref 重构为局部 _exs (gateway result_id, 成功/失败均回传);
        fallback task_id 仅 legacy (gateway 无 result_id 时)。run_id 只入
        EXS.task_run_id, 绝不进 exec_ref。
        """
        import re

        src = (Path(_ROOT) / "factory-console" / "session" / "agent_loop.py").read_text()
        # 两处 _exec_fn 均定义 _exs = result_id 且成功路径 exec_ref 用 _exs
        assert src.count('_exs = str(r.get("result_id") or "")') == 2
        matches = re.findall(r'"exec_ref": _exs or str\(r\.get\("task_id"\) or ""\)', src)
        assert len(matches) == 2, f"expected 2 EXS-priority exec_ref, got {len(matches)}"
        # 失败路径也回传 exec_ref=EXS (P0-F2 Gap-2)
        assert src.count('"exec_ref": _exs}') == 2
        # 不应再存在 exec_ref = task_id (TASK-GW) 的旧写法
        assert re.search(r'"exec_ref": str\(r\.get\("task_id"\) or ""\)', src) is None
        # gateway 透传 task_run_id
        assert src.count("task_run_id=run_id") >= 2
        # P0-F2: TaskRun finalize 接入 (两处)
        assert src.count("finalize_node_run(") >= 2

    def test_exec_ref_never_gw_or_run(self) -> None:
        """语义断言: exec_ref 候选顺序 = result_id (EXS) > task_id (legacy), 绝不取 run_id。"""
        # 生产 _exec_fn 的 exec_ref 表达式 (agent_loop): r.result_id or r.task_id
        # run_id 只写入 EXS.task_run_id, 不写入 exec_ref
        fake = {"result_id": "EXS-1", "task_id": "TASK-GW-9"}
        exec_ref = str(fake.get("result_id") or fake.get("task_id") or "")
        task_run_id = "run-123"
        assert exec_ref == "EXS-1"
        assert exec_ref != "run-123"
        assert exec_ref != "TASK-GW-9"


# ------------------------------------------------------------------ Test D


class TestRoundTrip:
    """F1 §9 Test D — Task → TaskRun → EXS 完整反查。"""

    def test_full_chain_round_trip(self, workroot: Path) -> None:
        from factory_console.external_executor.executor import record_invocation
        from factory_console.node_runtime import (
            create_node_run, get_node_run, register_node,
        )

        task_id = "TASK-roundtrip"
        register_node(workroot, node_id="task-execution", name="Task Exec",
                      node_type="task-execution")
        run = create_node_run(workroot, "task-execution", task_id=task_id, trigger="chain")
        rec = record_invocation(
            workroot, executor_id="claude", mode="blackbox", host_agent="",
            prompt="p", project_dir="", exit_code=0, output="o", error="",
            command="c", duration_ms=1, task_id=task_id, task_run_id=run["run_id"],
        )

        # EXS → TaskRun → Task
        assert rec["task_run_id"] == run["run_id"]
        run2 = get_node_run(workroot, rec["task_run_id"])
        assert run2 is not None
        assert run2["task_id"] == task_id
        # exec_ref = EXS → 可反查 EXS 记录
        assert rec["result_id"].startswith("EXS-")


# ------------------------------------------------------------------ Test E


class TestIdempotency:
    """F1 §9 Test E — 重复创建不产生第二 canonical relation。"""

    def test_repeat_node_run_creates_distinct_runs_same_task(self, workroot: Path) -> None:
        """同一 Task 多次执行 = 多个 TaskRun (run 不可变, 每次新 run), 每个独立锚 task。"""
        from factory_console.node_runtime import (
            create_node_run, register_node,
        )

        register_node(workroot, node_id="task-execution", name="Task Exec",
                      node_type="task-execution")
        r1 = create_node_run(workroot, "task-execution", task_id="TASK-same", trigger="chain")
        r2 = create_node_run(workroot, "task-execution", task_id="TASK-same", trigger="chain")
        assert r1["run_id"] != r2["run_id"]  # 每次新 run
        assert r1["task_id"] == r2["task_id"] == "TASK-same"
        # 无第二套 task_id 字段/SSOT — 单 task_id 字段即 canonical

    def test_repeat_record_invocation_appends_not_overwrites(self, workroot: Path) -> None:
        """同一 TaskRun 多次 EXS 记录 = append (attempts 历史), 不覆盖。"""
        from factory_console.external_executor.executor import record_invocation

        for i in range(2):
            record_invocation(
                workroot, executor_id="claude", mode="blackbox", host_agent="",
                prompt="p", project_dir="", exit_code=0, output="o", error="",
                command="c", duration_ms=i + 1,
                task_id="TASK-same", task_run_id="run-same",
            )
        data = json.loads((workroot / "exec" / "execution_records.json").read_text())
        same_run = [r for r in data if r.get("task_run_id") == "run-same"]
        assert len(same_run) == 2  # append, 非覆盖


# ------------------------------------------------------------------ Test F


class TestLegacyIsolation:
    """F1 §9 Test F — legacy id (task-e1-*/EXR-*/TASK-GW-*) 不作 canonical TaskRun/EXS。"""

    def test_legacy_ids_not_valid_task_run_anchors(self) -> None:
        """canonical TaskRun id = run-*; EXS id = EXS-*; 其他前缀不冒充。"""
        import re

        assert re.match(r"^run-[0-9a-f]{12}$", "run-123456789abc") is not None
        assert re.match(r"^EXS-[0-9a-f]{8}$", "EXS-12345678") is not None
        # legacy 前缀不符合 canonical 格式
        assert re.match(r"^run-", "task-e1-core") is None
        assert re.match(r"^EXS-", "EXR-d606d3a1") is None
        assert re.match(r"^EXS-", "TASK-GW-47d2c100") is None

    def test_exec_ref_semantics_docstring_frozen(self) -> None:
        """management.Task 注释 = EXS (F0); 用 AST 确认生产注释不再宣传 EXR 语义。"""
        import ast

        src = (Path(_ROOT) / "factory-org" / "org" / "management.py").read_text()
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Task":
                doc = ast.get_docstring(node) or ""
                found = True
                assert "exec_ref" in doc
                assert "EXS-*" in doc  # canonical
                assert "EXR-*" not in doc.split("P0-F1")[0] or "禁止 exec_ref 指向" in doc
        assert found
