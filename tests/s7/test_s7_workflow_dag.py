"""tests/s7/test_s7_workflow_dag.py — Stage 依赖 DAG 校验 (Unit, S7-003)。

覆盖:
- validate_dag: 线性链拓扑序 / 菱形并行 (两分支顺序合法) / 空 workflow []
  / 无依赖全就绪
- 循环拒绝 (Kahn): 三阶段环 / 自依赖 — validate_dag 为第二道防线, 环依赖
  数据直接落库 (绕过 lifecycle 增量检查) 后经 validate_dag 响亮拒绝
- 增量 DFS 环检测 (set_stage_dependencies): 对既有 stage 加依赖成环 →
  设置时即拒绝 (原子性: 拒绝后依赖保持原样)
- 未定义依赖拒绝: 不存在 stage / 跨 workflow → WorkflowDependencyError
  (create_stage/set_stage_dependencies 设置时拒绝 + validate_dag 兜底)

依赖: 本目录 conftest (project_store + logger)。
"""

from __future__ import annotations

import pytest

from org.projects import Stage
from org.workflow import (
    WorkflowCycleError,
    WorkflowDependencyError,
    WorkflowLifecycle,
)


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def wfid(wlife) -> str:
    from org.projects import ProjectLifecycle

    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return wlife.create_workflow("P-1", "Ship v1", workflow_id="WF-1").id


def _save_direct(wlife, workflow_id: str, *specs: tuple[str, list[str]]) -> None:
    """绕过 lifecycle 校验直接落库 (构造 validate_dag 兜底防线测试数据)。"""
    for stage_id, depends_on in specs:
        wlife.store.save_stage(
            Stage(id=stage_id, workflow_id=workflow_id, role_id="developer",
                  depends_on=depends_on)
        )


class TestTopologicalOrder:
    def test_linear_chain(self, wlife, wfid):
        """A → B → C: 依赖先于被依赖。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-A"], stage_id="STG-B")
        wlife.create_stage("WF-1", "devops", depends_on=["STG-B"], stage_id="STG-C")
        order = wlife.validate_dag("WF-1")
        assert order.index("STG-A") < order.index("STG-B") < order.index("STG-C")

    def test_diamond_parallel_branches(self, wlife, wfid):
        """A → (B, C) → D: 两并行分支顺序合法 (B/C 相对顺序不限定)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "architect", depends_on=["STG-A"], stage_id="STG-B")
        wlife.create_stage("WF-1", "ui-designer", depends_on=["STG-A"], stage_id="STG-C")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-B", "STG-C"], stage_id="STG-D")
        order = wlife.validate_dag("WF-1")
        assert set(order) == {"STG-A", "STG-B", "STG-C", "STG-D"}
        assert order.index("STG-A") < order.index("STG-B")
        assert order.index("STG-A") < order.index("STG-C")
        assert order.index("STG-B") < order.index("STG-D")
        assert order.index("STG-C") < order.index("STG-D")

    def test_empty_workflow(self, wlife, wfid):
        assert wlife.validate_dag("WF-1") == []

    def test_no_dependencies_all_ready(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "tester", stage_id="STG-B")
        assert set(wlife.validate_dag("WF-1")) == {"STG-A", "STG-B"}


class TestCycleRejectionKahn:
    def test_three_stage_cycle(self, wlife, wfid):
        """A 依赖 B, B 依赖 C, C 依赖 A → Kahn 检出环 (响亮拒绝)。"""
        _save_direct(wlife, "WF-1",
                     ("STG-A", ["STG-C"]), ("STG-B", ["STG-A"]), ("STG-C", ["STG-B"]))
        with pytest.raises(WorkflowCycleError, match="cycle"):
            wlife.validate_dag("WF-1")

    def test_self_dependency(self, wlife, wfid):
        _save_direct(wlife, "WF-1", ("STG-A", ["STG-A"]))
        with pytest.raises(WorkflowCycleError, match="cycle"):
            wlife.validate_dag("WF-1")

    def test_cycle_error_lists_stages(self, wlife, wfid):
        _save_direct(wlife, "WF-1", ("STG-A", ["STG-B"]), ("STG-B", ["STG-A"]))
        with pytest.raises(WorkflowCycleError) as exc:
            wlife.validate_dag("WF-1")
        assert "STG-A" in str(exc.value)
        assert "STG-B" in str(exc.value)


class TestCycleRejectionIncremental:
    def test_set_dependencies_incremental_dfs(self, wlife, wfid):
        """增量环检测: B 依赖 A 后, 再给 A 加依赖 B → 设置时 DFS 检出环。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-A"], stage_id="STG-B")
        with pytest.raises(WorkflowCycleError, match="dependency cycle"):
            wlife.set_stage_dependencies("STG-A", ["STG-B"])

    def test_set_dependencies_self_cycle(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        with pytest.raises(WorkflowCycleError, match="dependency cycle"):
            wlife.set_stage_dependencies("STG-A", ["STG-A"])

    def test_set_dependencies_three_stage_cycle(self, wlife, wfid):
        """A→B→C 已建, 给 A 加依赖 C → 成环, 设置时拒绝。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-A"], stage_id="STG-B")
        wlife.create_stage("WF-1", "devops", depends_on=["STG-B"], stage_id="STG-C")
        with pytest.raises(WorkflowCycleError, match="dependency cycle"):
            wlife.set_stage_dependencies("STG-A", ["STG-C"])

    def test_cycle_not_broken_state_unchanged(self, wlife, wfid):
        """拒绝后 stage 依赖保持原样 (原子性)。"""
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        wlife.create_stage("WF-1", "tester", depends_on=["STG-A"], stage_id="STG-B")
        with pytest.raises(WorkflowCycleError):
            wlife.set_stage_dependencies("STG-A", ["STG-B"])
        assert wlife.get_stage("STG-A").depends_on == []


class TestUndefinedDependency:
    def test_create_stage_rejects_undefined(self, wlife, wfid):
        """create_stage 设置时即拒绝 (依赖须为本 workflow 已存在 stage)。"""
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.create_stage("WF-1", "developer",
                               depends_on=["STG-999"], stage_id="STG-A")

    def test_set_stage_rejects_undefined(self, wlife, wfid):
        wlife.create_stage("WF-1", "developer", stage_id="STG-A")
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.set_stage_dependencies("STG-A", ["STG-999"])

    def test_cross_workflow_dependency_rejected(self, wlife, wfid):
        """跨 workflow 依赖拒绝 (dep 属另一 workflow 的 stage 视为未定义)。"""
        wlife.create_workflow("P-1", "W2", workflow_id="WF-2")
        wlife.create_stage("WF-2", "developer", stage_id="STG-9")
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.create_stage("WF-1", "developer",
                               depends_on=["STG-9"], stage_id="STG-A")

    def test_validate_dag_backstop_undefined(self, wlife, wfid):
        """validate_dag 兜底: 直接落库的坏数据 (如手工编辑 JSON) 被拒绝。"""
        _save_direct(wlife, "WF-1", ("STG-A", ["STG-999"]))
        with pytest.raises(WorkflowDependencyError, match="undefined stage"):
            wlife.validate_dag("WF-1")

    def test_error_message_carries_workflow(self, wlife, wfid):
        _save_direct(wlife, "WF-1", ("STG-A", ["STG-X"]))
        with pytest.raises(WorkflowDependencyError) as exc:
            wlife.validate_dag("WF-1")
        assert "STG-X" in str(exc.value)
        assert "WF-1" in str(exc.value)
