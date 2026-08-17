"""S10-071 — WorkspaceRepairExecutor + PytestValidator 测试 (P0-1/P0-2 反虚标)。

覆盖: 真实文件修改 (snapshot/diff/rollback) + 真实 pytest 验证 + 生产默认替代桩。
装配: tmp_path 真实项目 (bug + test); 禁外部网络 (本地 pytest 真实执行)。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

WE = import_module("factory-console.session.debug.workspace_executor")
DP = import_module("factory-console.session.debug.debug_pipeline")


def _buggy_project(tmp_path: Path) -> Path:
    """真实 Bug 项目: 实现硬编码错值 + 测试期望正确值。"""
    ws = tmp_path / "proj"
    ws.mkdir(exist_ok=True)
    (ws / "scoring.py").write_text(
        "def score(shots):\n    return 4  # BUG: 硬编码错误值\n", encoding="utf-8")
    (ws / "test_scoring.py").write_text(
        "from scoring import score\n\ndef test_score():\n    assert score(3) == 6\n",
        encoding="utf-8")
    return ws


def _session(ws: Path, error: str = "FAILED test_scoring.py::test_score - assert 4 == 6: expected 6 got 4"):
    from importlib import import_module as _im
    DS = _im("factory-console.session.debug.debug_session")
    s = DS.DebugSessionStore().create(DS.DebugSession(
        debug_id="", project_id="demo", task_id="T1", agent_id="backend-1",
        error_summary=error, status=DS.SESSION_ANALYZING,
        timestamps={"created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"},
    ))
    s.selected_strategy = "FIX_CODE"
    s.error_type = "ASSERTION"
    return s


# ================================================================== 1. build_repair_actions


class TestBuildActions:
    def test_fix_code_expected_got(self, tmp_path):
        ws = _buggy_project(tmp_path)
        actions = WE.build_repair_actions(_session(ws), ws)
        assert actions, "应生成修复动作"
        assert actions[0].action == "apply_patch"
        assert actions[0].old_text == "4"
        assert actions[0].new_text == "6"

    def test_no_action_unknown_strategy(self, tmp_path):
        ws = _buggy_project(tmp_path)
        s = _session(ws)
        s.selected_strategy = "REQUEST_REVIEW"
        assert WE.build_repair_actions(s, ws) == []


# ================================================================== 2. WorkspaceRepairExecutor


class TestExecutor:
    def test_execute_real_modification(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        result = ex.execute(_session(ws))
        assert result.success
        assert result.changed_files == ["scoring.py"]
        content = (ws / "scoring.py").read_text()
        assert "return 6" in content  # 真实修改

    def test_diff_recorded(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        result = ex.execute(_session(ws))
        assert result.diffs.get("scoring.py")
        assert "-    return 4" in result.diffs["scoring.py"]
        assert "+    return 6" in result.diffs["scoring.py"]

    def test_snapshot_taken(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        result = ex.execute(_session(ws))
        assert "scoring.py" in result.snapshots
        assert "return 4" in result.snapshots["scoring.py"]

    def test_rollback_restores(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        ex.execute(_session(ws))
        assert "return 6" in (ws / "scoring.py").read_text()
        restored = ex.rollback()
        assert "scoring.py" in restored
        assert "return 4" in (ws / "scoring.py").read_text()

    def test_write_file_action(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        ok = ex.apply_action(WE.RepairAction(
            file="new_module.py", action="write_file", content="# new\n"))
        assert ok
        assert (ws / "new_module.py").is_file()


# ================================================================== 3. PytestValidator (真实 pytest)


class TestPytestValidator:
    def test_initial_fail(self, tmp_path):
        ws = _buggy_project(tmp_path)
        v = WE.PytestValidator().validate(ws)
        assert v.success is False  # bug 未修 → FAIL
        assert v.exit_code != 0

    def test_after_repair_pass(self, tmp_path):
        ws = _buggy_project(tmp_path)
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        ex.execute(_session(ws))
        v = WE.PytestValidator().validate(ws)
        assert v.success is True  # 修复后 → PASS
        assert "passed=1" in v.summary

    def test_summary_fields(self, tmp_path):
        ws = _buggy_project(tmp_path)
        v = WE.PytestValidator().validate(ws)
        assert v.duration >= 0
        assert v.command == "pytest"


# ================================================================== 4. 生产默认替代桩


class TestProductionDefault:
    def test_default_execute_real(self, tmp_path):
        """DebugPipeline 默认 (无注入) → 真实修改。"""
        ws = _buggy_project(tmp_path)
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", agent_id="backend-1",
                    error_message="FAILED test_scoring.py::test_score - assert 4 == 6: expected 6 got 4")
        s = p.analyze(s)
        s = p.repair(s)  # 无 execute_fn → 生产默认
        assert "return 6" in (ws / "scoring.py").read_text()

    def test_default_validator_real_pytest(self, tmp_path):
        """DebugPipeline 默认验证 → 真实 pytest (非注入)。"""
        ws = _buggy_project(tmp_path)
        # 先修复
        ex = WE.WorkspaceRepairExecutor(workspace=ws)
        ex.execute(_session(ws))
        p = DP.DebugPipeline(workspace=ws)
        s = p.start(project_id="demo", task_id="T1", error_message="timeout")
        s = p.analyze(s)
        s = p.repair(s)
        s = p.validate(s, result=None)  # 无注入 → 真实 pytest
        assert s.status == "SUCCESS"

    def test_old_stub_still_seam(self, tmp_path):
        """旧桩保留为显式测试 seam (注入时使用)。"""
        fn = DP._default_execute_fn()
        outcome = fn(None, Path("/tmp"))
        assert outcome["success"] is True
        assert "deterministic" in outcome["note"]
