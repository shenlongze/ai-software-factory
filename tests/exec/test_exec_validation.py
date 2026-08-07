"""tests/exec/test_exec_validation.py — 沙箱验证器 (语法/测试命令)。

覆盖: ast.parse 语法检查通过/失败 / 测试命令成功/失败/超时 / validate 总入口
(有/无命令) / ValidationResult 模型默认值。
"""

from __future__ import annotations

from pathlib import Path

from exec.validation import Validation, ValidationCheck, ValidationResult
from exec_helpers import write_files


class TestSyntaxCheck:
    def test_pass(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"a.py": "x = 1\n", "b.py": "def f():\n    return 2\n"})
        check = Validation(tmp_path / "proj").syntax_check()
        assert check.passed is True
        assert check.name == "syntax"

    def test_fail_reports_file_and_line(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"bad.py": "def f(:\n    pass\n"})
        check = Validation(tmp_path / "proj").syntax_check()
        assert check.passed is False
        assert "bad.py" in check.output

    def test_missing_dir_pass(self, tmp_path: Path):
        check = Validation(tmp_path / "nope").syntax_check()
        assert check.passed is True

    def test_skips_hidden_dirs(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"ok.py": "x=1\n"})
        hidden = tmp_path / "proj" / ".hidden"
        hidden.mkdir()
        (hidden / "bad.py").write_text("def f(:\n", encoding="utf-8")
        check = Validation(tmp_path / "proj").syntax_check()
        assert check.passed is True


class TestRunCommand:
    def test_success(self, tmp_path: Path):
        check = Validation(tmp_path).run_command("python3 -c 'print(1)'")
        assert check.passed is True

    def test_failure(self, tmp_path: Path):
        check = Validation(tmp_path).run_command("python3 -c 'raise SystemExit(3)'")
        assert check.passed is False

    def test_timeout(self, tmp_path: Path):
        check = Validation(tmp_path, command_timeout=0.2).run_command("python3 -c 'import time; time.sleep(5)'")
        assert check.passed is False
        assert "timed out" in check.output

    def test_command_not_found(self, tmp_path: Path):
        check = Validation(tmp_path).run_command("definitely-not-a-command-xyz")
        assert check.passed is False
        assert check.output  # 启动失败也返回输出, 不抛


class TestValidate:
    def test_syntax_only(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"a.py": "x = 1\n"})
        result = Validation(tmp_path / "proj").validate()
        assert result.passed is True
        assert [c.name for c in result.checks] == ["syntax"]

    def test_with_command(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"a.py": "x = 1\n"})
        result = Validation(tmp_path / "proj").validate("python3 -c 'print(1)'")
        assert result.passed is True
        assert len(result.checks) == 2

    def test_command_failure_marks_fail(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"a.py": "x = 1\n"})
        result = Validation(tmp_path / "proj").validate("python3 -c 'raise SystemExit(1)'")
        assert result.passed is False
        assert "FAIL" in result.output

    def test_syntax_failure_marks_fail(self, tmp_path: Path):
        write_files(tmp_path / "proj", {"bad.py": "def f(:\n"})
        result = Validation(tmp_path / "proj").validate()
        assert result.passed is False


class TestModels:
    def test_validation_check_defaults(self):
        c = ValidationCheck(name="x", passed=True)
        assert c.output == ""

    def test_validation_result_defaults(self):
        r = ValidationResult(passed=True)
        assert r.checks == []
        assert r.output == ""
