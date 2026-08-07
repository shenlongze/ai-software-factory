"""tests/exec/test_exec_sandbox.py — 沙箱副本 + patch 隔离 (原项目零接触)。

覆盖: create (副本 + git init + 基线) / 原项目逐字节不变 (副本修改后) /
apply_patch (真实 git apply) / diff/export_patch 双路径 / change_summary /
忽略项 (.git/.venv/__pycache__) / 失败路径 (目录缺失/重复创建/git 缺失)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.sandbox import Sandbox, SandboxError
from exec_helpers import git_diff_text


class TestCreate:
    def test_create_copies_project(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        session = sbx.create(request_id="EXR-1")
        copy = Path(session.workspace_copy_path)
        assert copy.is_dir()
        assert (copy / "calc.py").read_text() == (project_dir / "calc.py").read_text()
        assert session.id.startswith("SBX-")
        assert session.request_id == "EXR-1"
        assert session.baseline_commit is not None

    def test_create_ignores_venv_and_git(self, project_dir: Path, tmp_path: Path):
        (project_dir / ".venv").mkdir()
        (project_dir / ".venv" / "lib.py").write_text("import os\n")
        (project_dir / "__pycache__").mkdir()
        (project_dir / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        (project_dir / "node_modules").mkdir()
        (project_dir / "node_modules" / "dep.js").write_text("let x = 1;\n")
        sbx = Sandbox(project_dir, work_root=tmp_path)
        session = sbx.create()
        copy = Path(session.workspace_copy_path)
        assert not (copy / ".venv").exists()
        assert not (copy / "__pycache__").exists()
        assert not (copy / "node_modules").exists()
        assert (copy / "calc.py").exists()

    def test_create_project_missing(self, tmp_path: Path):
        sbx = Sandbox(tmp_path / "nope", work_root=tmp_path)
        with pytest.raises(SandboxError, match="project dir not found"):
            sbx.create()

    def test_create_twice_raises(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        with pytest.raises(SandboxError, match="already created"):
            sbx.create()

    def test_copy_dir_property_before_create(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        with pytest.raises(SandboxError, match="not created"):
            sbx.copy_dir

    def test_empty_project_no_baseline(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        sbx = Sandbox(empty, work_root=tmp_path)
        session = sbx.create()
        assert session.baseline_commit is None  # nothing to commit → 合法无基线


class TestApplyPatch:
    def test_apply_patch_changes_copy_only(self, project_dir: Path, tmp_path: Path):
        """副本修改不影响原项目 (沙箱铁律): 应用后原文件逐字节不变。"""
        before = {"calc.py": (project_dir / "calc.py").read_text()}
        after = {
            "calc.py": (
                "def add(a, b):\n"
                "    return a + b\n"
                "\n"
                "def sub(a, b):\n"
                "    return abs(a - b)\n"
            )
        }
        diff = git_diff_text(tmp_path, before, after)
        sbx = Sandbox(project_dir, work_root=tmp_path)
        session = sbx.create()
        sbx.apply_patch(diff)
        copy = Path(session.workspace_copy_path)
        assert "abs(a - b)" in (copy / "calc.py").read_text()
        # 原项目零接触
        assert (project_dir / "calc.py").read_text() == before["calc.py"]
        assert "abs" not in (project_dir / "calc.py").read_text()

    def test_apply_patch_empty_noop(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        session = sbx.create()
        sbx.apply_patch("")  # 空 patch 静默 (NO_CHANGE 合法)
        assert sbx.diff() == ""
        assert Path(session.workspace_copy_path).is_dir()

    def test_apply_patch_before_create_raises(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        with pytest.raises(SandboxError, match="not created"):
            sbx.apply_patch("--- a/x\n+++ b/x\n")

    def test_apply_invalid_patch_raises(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        with pytest.raises(SandboxError, match="git apply"):
            sbx.apply_patch("this is not a valid unified diff at all\n")


class TestDiffExport:
    def test_diff_empty_after_create(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        assert sbx.diff() == ""

    def test_diff_reflects_change(self, project_dir: Path, tmp_path: Path):
        before = {"calc.py": (project_dir / "calc.py").read_text()}
        after = {"calc.py": before["calc.py"].replace("a - b", "abs(a - b)")}
        diff = git_diff_text(tmp_path, before, after)
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        sbx.apply_patch(diff)
        out = sbx.diff()
        assert "calc.py" in out
        assert "+    return abs(a - b)" in out

    def test_export_patch_writes_file(self, project_dir: Path, tmp_path: Path):
        before = {"calc.py": (project_dir / "calc.py").read_text()}
        after = {"calc.py": before["calc.py"].replace("a - b", "abs(a - b)")}
        diff = git_diff_text(tmp_path, before, after)
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        sbx.apply_patch(diff)
        target = tmp_path / "out" / "patch.patch"
        text = sbx.export_patch(target)
        assert target.exists()
        assert target.read_text() == text
        assert "calc.py" in text

    def test_export_patch_empty_diff_writes_empty_file(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        target = tmp_path / "empty.patch"
        text = sbx.export_patch(target)
        assert text == ""
        assert target.exists()

    def test_change_summary(self, project_dir: Path, tmp_path: Path):
        before = {"calc.py": (project_dir / "calc.py").read_text()}
        after = {"calc.py": before["calc.py"].replace("a - b", "abs(a - b)")}
        diff = git_diff_text(tmp_path, before, after)
        sbx = Sandbox(project_dir, work_root=tmp_path)
        sbx.create()
        sbx.apply_patch(diff)
        summary = sbx.change_summary()
        assert "calc.py" in summary
        assert " M " in summary or "M " in summary  # porcelain 修改标记

    def test_git_bin_missing_raises(self, project_dir: Path, tmp_path: Path):
        sbx = Sandbox(project_dir, work_root=tmp_path, git_bin="definitely-not-git")
        with pytest.raises(SandboxError, match="git command not found"):
            sbx.create()


class TestSelectiveCopy:
    """选择性复制 (project_files): 只拷指定相对路径; 原项目零影响; None 兼容全量。

    场景: markpad 2.2G (build/.dart_tool/dist 大体积) — 全量拷贝数小时;
    选择性复制 ["lib", "pubspec.yaml"] 秒级完成, 沙箱只含源码。
    """

    @staticmethod
    def _make_project(root: Path) -> Path:
        """模拟 Flutter 项目: lib/ 源码 + pubspec.yaml + 大体积构建产物。"""
        proj = root / "proj"
        (proj / "lib" / "editor").mkdir(parents=True)
        (proj / "lib" / "editor" / "search_service.dart").write_text(
            "class SearchService {}\n", encoding="utf-8"
        )
        (proj / "lib" / "core").mkdir(parents=True)
        (proj / "lib" / "core" / "document.dart").write_text(
            "class Document {}\n", encoding="utf-8"
        )
        (proj / "pubspec.yaml").write_text("name: markpad\n", encoding="utf-8")
        (proj / "README.md").write_text("# markpad\n", encoding="utf-8")
        # 构建产物 (选择性复制必须跳过)
        (proj / "build" / "app").mkdir(parents=True)
        (proj / "build" / "app" / "huge.bin").write_bytes(b"\x00" * 1024)
        (proj / ".dart_tool").mkdir(parents=True)
        (proj / ".dart_tool" / "package_config.json").write_text("{}\n", encoding="utf-8")
        (proj / "dist" / "out").mkdir(parents=True)
        (proj / "dist" / "out" / "bundle.js").write_text("console.log(1)\n", encoding="utf-8")
        return proj

    def test_selective_copy_only_specified_paths(self, tmp_path: Path):
        """project_files=["lib", "pubspec.yaml"] → 副本只含这两个路径, 无其他。"""
        proj = self._make_project(tmp_path)
        sbx = Sandbox(proj, work_root=tmp_path)
        session = sbx.create(project_files=["lib", "pubspec.yaml"])
        copy = Path(session.workspace_copy_path)
        assert (copy / "lib" / "editor" / "search_service.dart").is_file()
        assert (copy / "lib" / "core" / "document.dart").is_file()
        assert (copy / "pubspec.yaml").is_file()
        assert not (copy / "README.md").exists(), "未指定的文件不得复制"
        assert not (copy / "build").exists(), "构建产物不得进入沙箱"
        assert not (copy / ".dart_tool").exists()
        assert not (copy / "dist").exists()

    def test_selective_copy_file_only(self, tmp_path: Path):
        """project_files=[单文件路径] → 仅该文件 (嵌套父目录自动创建)。"""
        proj = self._make_project(tmp_path)
        sbx = Sandbox(proj, work_root=tmp_path)
        session = sbx.create(project_files=["lib/editor/search_service.dart"])
        copy = Path(session.workspace_copy_path)
        assert (copy / "lib" / "editor" / "search_service.dart").is_file()
        assert not (copy / "lib" / "core").exists(), "同 lib 下未指定子目录不得复制"
        assert not (copy / "pubspec.yaml").exists()

    def test_selective_copy_missing_path_raises(self, tmp_path: Path):
        """project_files 含不存在路径 → SandboxError (响亮, 不静默空副本)。"""
        proj = self._make_project(tmp_path)
        sbx = Sandbox(proj, work_root=tmp_path)
        with pytest.raises(SandboxError, match="project file not found"):
            sbx.create(project_files=["lib", "no_such_file.dart"])

    def test_selective_copy_original_untouched(self, tmp_path: Path):
        """选择性副本上应用 patch → 原项目逐字节不变 (沙箱铁律)。"""
        proj = self._make_project(tmp_path)
        before = (proj / "lib" / "editor" / "search_service.dart").read_text()
        after = before.replace("class SearchService {}", "class SearchService {}\n// fixed")
        diff = git_diff_text(
            tmp_path, {"lib/editor/search_service.dart": before},
            {"lib/editor/search_service.dart": after},
        )
        sbx = Sandbox(proj, work_root=tmp_path)
        session = sbx.create(project_files=["lib", "pubspec.yaml"])
        sbx.apply_patch(diff)
        copy = Path(session.workspace_copy_path)
        assert "// fixed" in (copy / "lib" / "editor" / "search_service.dart").read_text()
        assert (proj / "lib" / "editor" / "search_service.dart").read_text() == before
        assert (proj / "build" / "app" / "huge.bin").read_bytes() == b"\x00" * 1024

    def test_selective_copy_none_means_full_copy(self, tmp_path: Path):
        """project_files=None (缺省) → 全量拷贝 (兼容现有语义, 含忽略项过滤)。"""
        proj = self._make_project(tmp_path)
        sbx = Sandbox(proj, work_root=tmp_path)
        session = sbx.create()  # 不传 project_files
        copy = Path(session.workspace_copy_path)
        assert (copy / "lib" / "editor" / "search_service.dart").is_file()
        assert (copy / "README.md").is_file(), "None → 全量拷贝"
        assert (copy / "pubspec.yaml").is_file()
        # 即使全量, 构建产物也默认忽略
        assert not (copy / "build").exists()
        assert not (copy / ".dart_tool").exists()
        assert not (copy / "dist").exists()

    def test_selective_copy_empty_list_empty_copy(self, tmp_path: Path):
        """project_files=[] → 空副本 (显式声明; 基线可空, diff 走空树)。"""
        proj = self._make_project(tmp_path)
        sbx = Sandbox(proj, work_root=tmp_path)
        session = sbx.create(project_files=[])
        copy = Path(session.workspace_copy_path)
        assert copy.is_dir()
        assert not (copy / "lib").exists()
        assert not (copy / "pubspec.yaml").exists()
        assert sbx.diff() == ""  # 空副本零变更
