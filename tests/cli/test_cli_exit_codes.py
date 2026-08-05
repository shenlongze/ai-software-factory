"""test_exit_codes.py — 退出码约定 (cli-design §5: 0/1/2/3/7)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.main import build_parser, main
from cli_helpers import run_cli


class TestUsageExit2:
    """用法错误: argparse 默认 SystemExit(2)。"""

    @pytest.mark.parametrize(
        "argv",
        [
            [],                          # 无命令
            ["bogus"],                   # 未知命令
            ["task"],                    # task 缺子命令
            ["task", "status"],          # 缺 task_id
            ["task", "update", "T-1"],   # 缺 --status
            ["task", "create"],          # 缺 --title
            ["event"],                   # event 缺子命令
            ["validate"],                # validate 缺 task_id
        ],
    )
    def test_usage_errors(self, cli_root: Path, argv: list[str]):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), *argv])
        assert exc.value.code == 2

    def test_help_exits_0(self):
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--help"])
        assert exc.value.code == 0

    def test_bad_root_option(self, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "--bogus-flag", "init"])
        assert exc.value.code == 2


class TestExitCodes:
    def test_success_0(self, capsys, cli_root: Path):
        assert run_cli(capsys, cli_root, "init")[0] == 0

    def test_not_found_7(self, capsys, cli_root: Path):
        rc, _, _ = run_cli(capsys, cli_root, "task", "status", "T-999")
        assert rc == 7
        rc2, _, _ = run_cli(capsys, cli_root, "validate", "T-999")
        assert rc2 == 7

    def test_validation_failed_3(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, _, _ = run_cli(capsys, cli_root, "validate", "T-001", "--expect-status", "DONE")
        assert rc == 3

    def test_usage_2_via_cli_error_path(self, capsys, cli_root: Path):
        rc, _, _ = run_cli(capsys, cli_root, "task", "list", "--status", "bogus")
        assert rc == 2

    def test_general_error_1(self, capsys, cli_root: Path):
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "a")
        rc, _, _ = run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "dup")
        assert rc == 1
