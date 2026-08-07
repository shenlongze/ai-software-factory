"""tests/exec/test_exec_operations.py — File Operation API (确定性 diff 生成)。

覆盖 (Phase A++++++-1): 4 操作类型 (create_file/delete_file/modify_file/
replace_block) / 锚点解析 (symbol + line_range) / 越界错误 / diff 可应用
(真实 git apply) / 语法校验 (ast.parse) / 防御 (绝对路径拒绝)。

设计依据: docs/architecture/developer-agent-reliability-model.md §2 —
LLM → Intent → Structured Code Operation → Validation → Patch (确定性,
非模型手写 hunk; 修复真实 Benchmark diff 不可应用 ×2 根因)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from exec.operations import (
    FileChange,
    LocationSpec,
    OperationEngine,
    OperationError,
    OperationPlan,
    OperationType,
    OperationValidation,
    StructuredCodeOperation,
)
from exec_helpers import git_repo, write_files

PY_SRC = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"
)


def op(
    operation: str,
    target: str,
    *,
    change: str = "",
    location: dict | LocationSpec | None = None,
) -> StructuredCodeOperation:
    """StructuredCodeOperation 便捷构造 (测试夹具)。"""
    return StructuredCodeOperation(
        operation=operation, target=target, change=change, location=location
    )


@pytest.fixture
def engine(tmp_path: Path) -> OperationEngine:
    """指向最小项目副本的引擎 (py 源 + dart 源)。"""
    write_files(
        tmp_path,
        {
            "calc.py": PY_SRC,
            "lib/a.dart": "class A {\n  int x = 1;\n}\n",
        },
    )
    return OperationEngine(tmp_path)


class TestCreateFile:
    def test_plan_new_file_old_text_empty(self, engine: OperationEngine):
        plan = engine.plan([op("create_file", "new.py", change="x = 1\n")])
        assert len(plan.changes) == 1
        ch = plan.changes[0]
        assert ch.path == "new.py"
        assert ch.old_text == ""
        assert ch.new_text == "x = 1\n"

    def test_create_file_diff_fromfile_dev_null(self, engine: OperationEngine):
        diff = engine.plan([op("create_file", "new.py", change="x = 1\n")]).to_diff()
        assert "--- /dev/null" in diff
        assert "+++ b/new.py" in diff
        assert diff.endswith("\n")

    def test_create_file_apply_writes_file(self, engine: OperationEngine):
        plan = engine.plan([op("create_file", "new.py", change="x = 1\n")])
        written = engine.apply(plan)
        assert written == ["new.py"]
        assert (engine.root_dir / "new.py").read_text() == "x = 1\n"

    def test_create_file_existing_raises(self, engine: OperationEngine):
        with pytest.raises(OperationError, match="已存在"):
            engine.plan([op("create_file", "calc.py", change="x = 1\n")])

    def test_create_file_missing_change_validation_error(self):
        with pytest.raises(ValidationError, match="change"):
            op("create_file", "new.py", change="")


class TestModifyFile:
    def test_plan_replace_whole_content(self, engine: OperationEngine):
        plan = engine.plan([op("modify_file", "calc.py", change="def add(a, b):\n    return a + b\n")])
        ch = plan.changes[0]
        assert ch.old_text == PY_SRC
        assert ch.new_text.startswith("def add(a, b):")

    def test_modify_file_missing_target_raises(self, engine: OperationEngine):
        with pytest.raises(OperationError, match="不存在"):
            engine.plan([op("modify_file", "not_there.py", change="x")])

    def test_modify_file_apply_overwrites(self, engine: OperationEngine):
        plan = engine.plan([op("modify_file", "calc.py", change="x = 2\n")])
        engine.apply(plan)
        assert (engine.root_dir / "calc.py").read_text() == "x = 2\n"


class TestDeleteFile:
    def test_plan_delete_new_text_empty(self, engine: OperationEngine):
        plan = engine.plan([op("delete_file", "calc.py")])
        ch = plan.changes[0]
        assert ch.old_text == PY_SRC
        assert ch.new_text == ""

    def test_delete_file_diff_tofile_dev_null(self, engine: OperationEngine):
        diff = engine.plan([op("delete_file", "calc.py")]).to_diff()
        assert "--- a/calc.py" in diff
        assert "+++ /dev/null" in diff

    def test_delete_file_apply_removes(self, engine: OperationEngine):
        plan = engine.plan([op("delete_file", "calc.py")])
        engine.apply(plan)
        assert not (engine.root_dir / "calc.py").exists()

    def test_delete_file_missing_raises(self, engine: OperationEngine):
        with pytest.raises(OperationError, match="不存在"):
            engine.plan([op("delete_file", "not_there.py")])


class TestReplaceBlockSymbol:
    def test_symbol_replaces_function_body(self, engine: OperationEngine):
        plan = engine.plan(
            [op("replace_block", "calc.py", location={"symbol": "sub"},
                change="def sub(a, b):\n    return abs(a - b)\n")]
        )
        ch = plan.changes[0]
        assert "return abs(a - b)" in ch.new_text
        # add 函数不受影响
        assert "return a + b" in ch.new_text
        assert ch.block_desc.startswith("symbol 'sub'")

    def test_symbol_class_block(self, engine: OperationEngine):
        plan = engine.plan(
            [op("replace_block", "lib/a.dart", location={"symbol": "A"},
                change="class A {\n  int x = 2;\n}\n")]
        )
        assert "int x = 2;" in plan.changes[0].new_text

    def test_symbol_not_found_raises(self, engine: OperationEngine):
        with pytest.raises(OperationError, match="symbol 定位失败"):
            engine.plan(
                [op("replace_block", "calc.py", location={"symbol": "nope"},
                    change="def nope(): pass\n")]
            )

    def test_block_end_stops_at_next_def(self):
        lines = ["def foo():", "    return 1", "", "def bar():", "    return 2"]
        start = OperationEngine.find_def_line(lines, "foo")
        assert start == 0
        end = OperationEngine.block_end(lines, start)
        assert end == 2  # 空行跳过, 到 bar 定义前一行

    def test_resolve_block_returns_1based_inclusive(self, engine: OperationEngine):
        lines = PY_SRC.splitlines()
        start, end = OperationEngine.resolve_block(lines, LocationSpec(symbol="add"))
        # 块 = def add 行 + return 行 + 尾部空行 (到下一同缩进定义前一行)
        assert (start, end) == (1, 3)


class TestReplaceBlockLineRange:
    def test_line_range_replaces_exact_lines(self, engine: OperationEngine):
        plan = engine.plan(
            [op("replace_block", "calc.py", location={"line_range": [4, 5]},
                change="def sub(a, b):\n    return a * b\n")]
        )
        ch = plan.changes[0]
        assert "return a * b" in ch.new_text
        assert "return a - b" not in ch.new_text

    def test_line_range_start_zero_rejected_at_model(self):
        """start < 1 在 LocationSpec 模型层拦截 (1-based 契约), 引擎层兜底同语义。"""
        with pytest.raises(ValidationError, match="line_range 非法"):
            LocationSpec(line_range=[0, 2])

    def test_line_range_end_beyond_file_raises(self, engine: OperationEngine):
        """end > 文件行数 通过模型校验, 在引擎 resolve 层报越界。"""
        with pytest.raises(OperationError, match="越界"):
            engine.plan(
                [op("replace_block", "calc.py", location={"line_range": [1, 999]},
                    change="x")]
            )

    def test_line_range_end_before_start_rejected_at_model(self):
        """end < start 在 LocationSpec 模型层拦截 (start <= end 契约)。"""
        with pytest.raises(ValidationError, match="line_range 非法"):
            LocationSpec(line_range=[5, 2])

    def test_location_requires_anchor_validation_error(self):
        with pytest.raises(ValidationError, match="symbol 或 line_range"):
            LocationSpec(symbol="", line_range=None)


class TestDiffApplicable:
    def test_operations_diff_applies_in_real_git(self, tmp_path: Path, engine: OperationEngine):
        """确定性 diff 必须能真实 git apply (--check rc 0) — 修复方向的核心验收。"""
        repo = tmp_path / "gitapply"
        git_repo(repo, {"calc.py": PY_SRC})
        plan = engine.plan(
            [op("replace_block", "calc.py", location={"symbol": "sub"},
                change="def sub(a, b):\n    return abs(a - b)\n")]
        )
        diff = plan.to_diff()
        patch = repo / "ops.patch"
        patch.write_text(diff, encoding="utf-8")
        check = subprocess.run(
            ["git", "-C", str(repo), "apply", "--check", str(patch)],
            capture_output=True, text=True, timeout=60,
        )
        assert check.returncode == 0, check.stderr

    def test_multi_operation_diff_applies(self, tmp_path: Path):
        """多操作合并 diff (create + modify) 同样 git apply --check 通过。"""
        repo = tmp_path / "multi"
        git_repo(repo, {"calc.py": PY_SRC})
        engine = OperationEngine(repo)
        plan = engine.plan(
            [
                op("replace_block", "calc.py", location={"symbol": "sub"},
                    change="def sub(a, b):\n    return abs(a - b)\n"),
                op("create_file", "new_mod.py", change="def double(x):\n    return x * 2\n"),
            ]
        )
        patch = repo / "multi.patch"
        patch.write_text(plan.to_diff(), encoding="utf-8")
        check = subprocess.run(
            ["git", "-C", str(repo), "apply", "--check", str(patch)],
            capture_output=True, text=True, timeout=60,
        )
        assert check.returncode == 0, check.stderr

    def test_to_diff_skips_unchanged(self, engine: OperationEngine):
        """old == new 的变更不出现在 diff 里 (最小性)。"""
        plan = OperationPlan(changes=[FileChange(path="a.py", old_text="x", new_text="x")])
        assert plan.to_diff() == ""


class TestValidate:
    def test_validate_python_syntax_ok(self, engine: OperationEngine):
        v = engine.validate([op("modify_file", "calc.py", change="def add(a, b):\n    return a + b\n")])
        assert isinstance(v, OperationValidation)
        assert v.passed
        assert v.errors == []

    def test_validate_python_syntax_error(self, engine: OperationEngine):
        v = engine.validate([op("modify_file", "calc.py", change="def broken(:\n")])
        assert not v.passed
        assert any("语法错误" in e for e in v.errors)

    def test_validate_anchor_failure_reports_error(self, engine: OperationEngine):
        v = engine.validate(
            [op("replace_block", "calc.py", location={"symbol": "ghost"},
                change="def ghost(): pass\n")]
        )
        assert not v.passed
        assert any("symbol 定位失败" in e for e in v.errors)

    def test_validate_non_python_skips_syntax(self, engine: OperationEngine):
        v = engine.validate([op("modify_file", "lib/a.dart", change="class A {" )])
        assert v.passed  # dart 不做 ast.parse (仅 .py)


class TestDefense:
    def test_absolute_target_rejected(self, engine: OperationEngine):
        with pytest.raises(OperationError, match="相对路径"):
            engine.plan([op("create_file", "/etc/passwd2", change="x")])

    def test_operation_type_invalid_validation_error(self):
        with pytest.raises(ValidationError, match="operation 非法"):
            op("teleport", "a.py", change="x")

    def test_replace_block_requires_location(self):
        with pytest.raises(ValidationError, match="location"):
            op("replace_block", "calc.py", change="x")
