"""test_cli_validate_report.py — factory validate: Validation Report 输出 / 退出码 / 事件集成。

覆盖: 报告格式 (通过/失败/未找到) / 退出码 (0/3/7/2) / validation.* 事件产生 / --json 结构。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.main import main
from events.models import EventType
from events.store import EventStore

from validation_helpers import write_raw_task


def run_cli(capsys, root: Path, *argv: str) -> tuple[int, str, str]:
    """执行 CLI (root 固定注入), 返回 (退出码, stdout, stderr)。"""
    rc = main(["--root", str(root), *argv])
    out, err = capsys.readouterr()
    return rc, out, err


def seed_task(capsys, root: Path, task_id: str = "T-001", status: str = "BACKLOG") -> None:
    """CLI 建任务 (发 task.created / task.updated 事件)。"""
    run_cli(capsys, root, "task", "create", "--id", task_id, "--title", "实现撤销/重做")
    if status != "BACKLOG":
        run_cli(capsys, root, "task", "update", task_id, "--status", status)


def event_types(root: Path) -> list[str]:
    with EventStore(root / "factory.db") as store:
        return [e.type.value for e in store.query()]


class TestReportOutput:
    def test_report_format_pass(self, capsys, cli_root: Path):
        """通过报告逐行匹配父任务样例。"""
        seed_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001")
        assert rc == 0
        assert out.splitlines()[:6] == [
            "Validation Report",
            "Task: T-001",
            "L1 Factory    PASS",
            "L2 Workflow   PASS",
            "L3 Artifact   SKIP",
            "Result: PASS",
        ]
        assert "验证通过" in out

    def test_report_format_missing_task(self, capsys, cli_root: Path):
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-999")
        assert rc == 7
        assert "Validation Report" in out
        assert "L1 Factory    FAIL" in out
        assert "Result: FAIL" in out
        assert "验证失败" in out

    def test_report_format_l2_fail(self, capsys, cli_root: Path):
        """事件历史与状态不一致 → L2 FAIL → 退出码 3。"""
        seed_task(capsys, cli_root)
        write_raw_task(cli_root / "tasks", "T-001",
                       json.dumps({"id": "T-001", "title": "实现撤销/重做", "project": "default",
                                   "status": "DEVELOPMENT"}))
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001")
        assert rc == 3
        assert "L2 Workflow   FAIL" in out
        assert "Result: FAIL" in out
        assert "验证失败" in out

    def test_report_format_expect_status_fail(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "DONE")
        assert rc == 3
        assert "Result: FAIL" in out
        assert "status_mismatch" in out


class TestExitCodes:
    def test_pass_exit_0(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        assert run_cli(capsys, cli_root, "validate", "T-001")[0] == 0

    def test_fail_exit_3(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        assert run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "DONE")[0] == 3

    def test_missing_task_exit_7(self, capsys, cli_root: Path):
        """未找到 (cli-design §5) 优先于验证失败 (ADR-0003)。"""
        assert run_cli(capsys, cli_root, "validate", "T-999")[0] == 7

    def test_bad_expect_status_exit_2(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        assert run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "nope")[0] == 2

    def test_level_option_accepted(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        assert run_cli(capsys, cli_root, "validate", "T-001", "--level", "L1")[0] == 0


class TestEvents:
    def test_pass_emits_rule_flow(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        run_cli(capsys, cli_root, "validate", "T-001")
        types = event_types(cli_root)
        assert "validation.started" in types
        assert "validation.rule.started" in types
        assert "validation.rule.completed" in types
        assert types[-1] == "validation.completed"
        assert "validation.failed" not in types

    def test_fail_emits_failed_event(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "DONE")
        with EventStore(cli_root / "factory.db") as store:
            failed = store.query(event_type=EventType.VALIDATION_FAILED)
            assert len(failed) == 1
            assert failed[0].result == "FAIL"
            assert failed[0].payload["reason"] == "status_mismatch"
            completed = store.query(event_type=EventType.VALIDATION_COMPLETED)[0]
            assert completed.result == "FAIL"
            assert completed.payload["reason"] == "status_mismatch"

    def test_missing_task_emits_failed_event(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "validate", "T-999")
        with EventStore(cli_root / "factory.db") as store:
            failed = store.query(event_type=EventType.VALIDATION_FAILED)
            assert len(failed) == 1
            assert failed[0].payload["reason"] == "task_not_found"
            assert failed[0].result == "FAIL"


class TestJson:
    def test_json_structure(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001", "--json")
        assert rc == 0
        d = json.loads(out)
        assert d["ok"] is True
        assert d["exit_code"] == 0
        assert d["result"] == "PASS"
        assert d["reason"] is None
        assert d["report"]["task_id"] == "T-001"
        assert len(d["report"]["results"]) == 6
        assert d["report"]["results"][0]["id"] == "L1.task_exists"
        assert d["report_text"].startswith("Validation Report\nTask: T-001")

    def test_json_structure_fail(self, capsys, cli_root: Path):
        seed_task(capsys, cli_root)
        rc, out, _ = run_cli(capsys, cli_root, "validate", "T-001",
                             "--expect-status", "DONE", "--json")
        assert rc == 3
        d = json.loads(out)
        assert d["ok"] is False
        assert d["result"] == "FAIL"
        assert d["reason"] == "status_mismatch"
        assert d["exit_code"] == 3
        assert len(d["checks"]) == 7  # 6 基础规则 + expect_status
