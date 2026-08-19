"""S10-083 — Real Execution & Observability Foundation 测试。

覆盖:
P0a Artifact Boundary: 状态文件剥离 / 代码保留
P0b Patch Delivery: apply 回项目 / 0 文件 FAILED / 真实文件出现
P0c Observability: timeline 真实数据 / project status / CLI 展示
约束: 全部真实执行, 无 mock/stub/fake
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from importlib import import_module

PF = import_module("factory-exec.exec.patch_filter")
DELIVERY = import_module("factory-console.session.delivery")
OBS = import_module("factory-console.session.observability")


# ---------------------------------------------------------------- P0a 边界

class TestArtifactBoundary:
    def test_state_file_stripped(self):
        patch = """diff --git a/execution_state.json b/execution_state.json
index 123..456 100644
--- a/execution_state.json
+++ b/execution_state.json
@@ -1 +1 @@
-{"old": true}
+{"new": true}
"""
        clean, blocked = PF.filter_patch(patch)
        assert "execution_state.json" in blocked
        assert "diff --git" not in clean

    def test_code_file_kept(self):
        patch = """diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1 @@
+print("hello")
+
"""
        clean, blocked = PF.filter_patch(patch)
        assert blocked == []
        assert "app.py" in clean

    def test_mixed_patch_only_strips_state(self):
        patch = """diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1 @@
+print("x")
diff --git a/execution_state.json b/execution_state.json
index 1..2 100644
--- a/execution_state.json
+++ b/execution_state.json
@@ -1 +1 @@
-{}
+{"x":1}
+
"""
        clean, blocked = PF.filter_patch(patch)
        assert "execution_state.json" in blocked
        assert "app.py" in clean
        assert "print(\"x\")" in clean


# ---------------------------------------------------------------- P0b Delivery

class TestPatchDelivery:
    def test_apply_patch_to_real_dir(self, tmp_path):
        """patch 应用到真实项目目录 (文件出现)。"""
        proj = tmp_path / "proj"
        proj.mkdir()
        DELIVERY.ensure_git_repo(proj)
        patch = """diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1,2 @@
+def main():
+    print("hi")
+
"""
        ok, msg = DELIVERY.apply_patch(proj, patch)
        assert ok, msg
        assert (proj / "app.py").is_file()
        assert "print" in (proj / "app.py").read_text(encoding="utf-8")

    def test_zero_code_files_fails(self, tmp_path):
        """任务声称代码但 0 代码文件 → 失败 (空目录 PASS 消除)。"""
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "README.md").write_text("# readme", encoding="utf-8")
        ok, msg = DELIVERY.validate_delivery(proj, require_code=True)
        assert not ok
        assert "0 个" in msg

    def test_code_files_pass(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "app.py").write_text("x=1", encoding="utf-8")
        ok, _ = DELIVERY.validate_delivery(proj, require_code=True)
        assert ok

    def test_count_code_files_excludes_git(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "app.py").write_text("x=1", encoding="utf-8")
        (proj / ".git" / "obj").mkdir(parents=True)
        (proj / ".git" / "obj" / "x.py").write_text("x", encoding="utf-8")
        assert DELIVERY.count_code_files(proj) == 1

    def test_deliver_patch_full_flow(self, tmp_path):
        """完整交付: 过滤 → apply → 校验 (代码保留, 状态剥离)。"""
        proj = tmp_path / "proj"
        proj.mkdir()
        patch = """diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1,2 @@
+def main():
+    return 1
+
diff --git a/execution_state.json b/execution_state.json
index 1..2 100644
--- a/execution_state.json
+++ b/execution_state.json
@@ -1 +1 @@
-{}
+{"x":1}
+
"""
        result = DELIVERY.deliver_patch(proj, patch)
        assert result["applied"] is True
        assert result["ok"] is True
        assert result["code_files"] >= 1
        assert "execution_state.json" in result["blocked_files"]
        assert (proj / "app.py").is_file()
        assert not (proj / "execution_state.json").exists()


# ---------------------------------------------------------------- P0c Observability

class TestObservability:
    def _make_exec_dir(self, tmp_path) -> Path:
        exec_dir = tmp_path / "exec"
        exec_dir.mkdir(parents=True)
        (exec_dir / "execution_records.json").write_text(json.dumps([
            {
                "intent": "execute_task", "action": "agent.execute_task",
                "agent": "backend-1", "task": "保存历史",
                "result": "success", "result_id": "EXS-test1",
                "timestamp": "2026-08-19T10:30:00+00:00", "error": None,
            },
            {
                "intent": "execute_task", "action": "agent.execute_task",
                "agent": "pm-agent", "task": "PRD",
                "result": "failed", "result_id": "EXS-test2",
                "timestamp": "2026-08-19T10:31:00+00:00", "error": "timeout",
            },
        ]), encoding="utf-8")
        (exec_dir / "EXS-test1.report.md").write_text(
            "## Usage\n{'total_tokens': 1500, 'estimated_cost_usd': 0.001}\n",
            encoding="utf-8")
        return exec_dir

    def test_timeline_real_records(self, tmp_path):
        exec_dir = self._make_exec_dir(tmp_path)
        events = OBS.execution_timeline(tmp_path)
        assert len(events) == 2
        assert events[0]["agent"] == "pm-agent"  # 最新在前
        assert events[1]["tokens"] == 1500
        assert events[1]["cost_usd"] == 0.001

    def test_timeline_no_fake_usage(self, tmp_path):
        """无 report → usage 空 (不伪造)。"""
        exec_dir = self._make_exec_dir(tmp_path)
        events = OBS.execution_timeline(tmp_path)
        assert events[0]["tokens"] is None

    def test_project_status_real_data(self, tmp_path):
        exec_dir = self._make_exec_dir(tmp_path)
        proj = tmp_path / "projects" / "P-test"
        proj.mkdir(parents=True)
        (proj / "project.json").write_text(json.dumps({"status": "execution_ready"}), encoding="utf-8")
        (proj / "execution_state.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "name": "保存历史", "agent": "backend-1", "status": "completed",
                 "applied": True, "code_files": 2},
                {"id": "t2", "name": "统计", "agent": "backend-1", "status": "failed",
                 "applied": False, "code_files": 0},
            ]
        }), encoding="utf-8")
        (proj / "app.py").write_text("x=1", encoding="utf-8")
        status = OBS.project_status(tmp_path, proj)
        assert status["lifecycle"] == "execution_ready"
        assert status["tasks_total"] == 2
        assert status["tasks_completed"] == 1
        assert status["tasks_failed"] == 1
        assert status["code_files"] == 1
        assert status["tasks"][0]["applied"] is True

    def test_format_timeline_human_readable(self, tmp_path):
        exec_dir = self._make_exec_dir(tmp_path)
        events = OBS.execution_timeline(tmp_path)
        text = OBS.format_timeline(events)
        assert "执行历史" in text
        assert "backend-1" in text
        assert "✅" in text
        assert "❌" in text

    def test_format_status_phase_and_tasks(self, tmp_path):
        exec_dir = self._make_exec_dir(tmp_path)
        proj = tmp_path / "projects" / "P-test"
        proj.mkdir(parents=True)
        (proj / "project.json").write_text(json.dumps({"status": "execution_ready"}), encoding="utf-8")
        (proj / "execution_state.json").write_text(json.dumps({"tasks": []}), encoding="utf-8")
        text = OBS.format_status(OBS.project_status(tmp_path, proj))
        assert "项目:" in text
        assert "阶段:" in text


class TestObservabilityFixes:
    """2026-08-19 修复: 时间线去重 + 任务失败原因可见。"""

    def _exec_dir_with_retry(self, tmp_path) -> Path:
        exec_dir = tmp_path / "exec"
        exec_dir.mkdir(parents=True)
        (exec_dir / "execution_records.json").write_text(json.dumps([
            {
                "intent": "execute_task", "action": "agent.execute_task",
                "agent": "backend-1", "task": "保存历史", "result": "failed",
                "result_id": "EXS-a", "timestamp": "2026-08-19T10:30:00+00:00",
            },
            {
                "intent": "execute_task", "action": "agent.execute_task",
                "agent": "backend-1", "task": "保存历史", "result": "failed",
                "result_id": "EXS-b", "timestamp": "2026-08-19T10:30:01+00:00",
            },
            {
                "intent": "execute_task", "action": "agent.execute_task",
                "agent": "pm-agent", "task": "PRD", "result": "success",
                "result_id": "EXS-c", "timestamp": "2026-08-19T10:31:00+00:00",
            },
        ]), encoding="utf-8")
        return exec_dir

    def test_timeline_dedupes_retry_records(self, tmp_path):
        """同一任务初次+重试 → 时间线只保留最新一次 (不再重复刷屏)。"""
        self._exec_dir_with_retry(tmp_path)
        events = OBS.execution_timeline(tmp_path)
        tasks = [e["task"] for e in events]
        assert tasks.count("保存历史") == 1
        kept = next(e for e in events if e["task"] == "保存历史")
        assert kept["result_id"] == "EXS-b"  # 保留最新一次

    def test_status_shows_task_error(self, tmp_path):
        """任务失败原因进入状态视图 (原只有 'failed', 无原因)。"""
        proj = tmp_path / "projects" / "P-test"
        proj.mkdir(parents=True)
        (proj / "project.json").write_text(json.dumps({"status": "development"}), encoding="utf-8")
        (proj / "execution_state.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "name": "保存历史", "agent": "backend-1", "status": "failed",
                 "applied": False, "code_files": 0,
                 "error": "provider error: openai request failed: network down"},
            ]
        }), encoding="utf-8")
        status = OBS.project_status(tmp_path, proj)
        assert status["tasks"][0]["error"] == "provider error: openai request failed: network down"
        text = OBS.format_status(status)
        assert "network down" in text
