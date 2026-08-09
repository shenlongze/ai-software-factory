"""tests/s9/test_s9_004_analyzer.py — Repository Analyzer + Baseline + Snapshot
(exec.project_adoption, S9-004)。

覆盖 (exec 侧确定性单元):
- detect_language: 清单强信号 / 扩展名统计 / 空仓库 unknown
- detect_framework: pubspec flutter / pyproject / 未识别 ""
- analyze_project: 载荷 6 字段结构 / 模块 structure / 依赖摘要 / 空仓库回退
- run_baseline: build passed/failed / 命令缺失 unavailable / Python 语法检查
  兜底 (passed + failed 两路径) / test 计数解析 (passed + failed) / 无命令
- build_context_snapshot: 浅层树 / 重要文件排序 / 架构字段

依赖: 本目录 conftest (sys.path 挂 factory-exec)。真实 subprocess 命令
(可执行文件用 sys.executable — 测试环境自洽, 不依赖 PATH 猜测)。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from exec.project_adoption import (
    analyze_project,
    build_context_snapshot,
    detect_framework,
    detect_language,
    detect_test_method,
    run_baseline,
    syntax_check_python,
)

from s9_helpers import make_python_repo


# ------------------------------------------------------------ 语言检测


def test_detect_language_python_by_manifest(tmp_path: Path):
    """requirements.txt 强信号 → python (即使无 .py 文件)。"""
    project = tmp_path / "s9_004_lang_py"
    project.mkdir()
    (project / "requirements.txt").write_text("requests\n", encoding="utf-8")
    assert detect_language(project) == "python"


def test_detect_language_dart_by_pubspec(tmp_path: Path):
    """pubspec.yaml 强信号 → dart。"""
    project = tmp_path / "dart_app"
    project.mkdir()
    (project / "pubspec.yaml").write_text("name: dart_app\n", encoding="utf-8")
    (project / "lib").mkdir()
    (project / "lib" / "main.dart").write_text(
        "void main() {}\n", encoding="utf-8"
    )
    assert detect_language(project) == "dart"


def test_detect_language_by_extension_counts(tmp_path: Path):
    """无清单 → 扩展名计数 (js 文件多 → javascript)。"""
    project = tmp_path / "js_app"
    (project / "src").mkdir(parents=True)
    for i in range(3):
        (project / "src" / f"mod{i}.js").write_text("export {}\n", encoding="utf-8")
    assert detect_language(project) == "javascript"


def test_detect_language_empty_repo(tmp_path: Path):
    """空仓库 → unknown (失败安全, 不崩溃)。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert detect_language(empty) == "unknown"


def test_detect_language_skips_noise_dirs(tmp_path: Path):
    """node_modules/.git 等噪声目录不参与统计 (src.py 唯一 → python)。"""
    project = tmp_path / "mixed"
    (project / "node_modules").mkdir(parents=True)
    (project / "node_modules" / "big.js").write_text("x", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "index.js").write_text("x", encoding="utf-8")
    (project / "src.py").write_text("x = 1\n", encoding="utf-8")
    assert detect_language(project) == "python"


# ------------------------------------------------------------ 框架检测


def test_detect_framework_flutter(tmp_path: Path):
    """pubspec.yaml 含 flutter: → flutter。"""
    project = tmp_path / "flutter_app"
    project.mkdir()
    (project / "pubspec.yaml").write_text(
        "name: f\nflutter:\n  uses-material-design: true\n", encoding="utf-8"
    )
    assert detect_framework(project, "dart") == "flutter"


def test_detect_framework_python_pyproject(tmp_path: Path):
    """pyproject.toml 无已知关键字 → pyproject (确定性兜底)。"""
    project = tmp_path / "py_app"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[build-system]\nrequires = []\n", encoding="utf-8"
    )
    assert detect_framework(project, "python") == "pyproject"


def test_detect_framework_unknown(tmp_path: Path):
    """无清单 → \"\" (诚实不猜)。"""
    project = tmp_path / "bare"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert detect_framework(project, "python") == ""


# ------------------------------------------------------------ 分析载荷


def test_analyze_project_payload_structure(tmp_path: Path):
    """载荷 6 字段齐全 + 类型正确 (CONTRACTS project_analysis 同源)。"""
    project = make_python_repo(tmp_path, name="s9_004_analyze")
    payload = analyze_project(project)
    assert set(payload) == {
        "language", "framework", "structure", "dependencies",
        "build_method", "test_method",
    }
    assert payload["language"] == "python"
    assert isinstance(payload["structure"], list) and payload["structure"]
    assert payload["dependencies"]["edge_count"] >= 1
    assert payload["build_method"]
    assert payload["test_method"] == "pytest"  # tests/test_hello.py 含 import pytest


def test_analyze_project_structure_modules(tmp_path: Path):
    """structure 含根模块与测试模块 (repo_intelligence L2 复用)。"""
    project = make_python_repo(tmp_path, name="s9_004_modules")
    payload = analyze_project(project)
    paths = {m["path"] for m in payload["structure"]}
    assert "(root)" in paths or "tests" in paths
    root_mod = next(m for m in payload["structure"] if m["path"] == "(root)")
    assert root_mod["file_count"] >= 2  # hello.py + main.py


def test_analyze_project_dependencies_summary(tmp_path: Path):
    """依赖摘要: main.py → hello.py 一条依赖边 (L3 复用)。"""
    project = make_python_repo(tmp_path, name="s9_004_deps")
    payload = analyze_project(project)
    deps = payload["dependencies"]
    assert deps["file_count"] >= 3
    top = {t["file"] for t in deps["top_dependents"]}
    assert "hello.py" in top  # 被 main.py 依赖 → 影响面核心


def test_analyze_project_empty_repo_fallback(tmp_path: Path):
    """空仓库 → structure 单条 (root) 占位 (契约 min_items 1 失败安全)。"""
    empty = tmp_path / "s9_004_empty"
    empty.mkdir()
    payload = analyze_project(empty)
    assert payload["language"] == "unknown"
    assert len(payload["structure"]) == 1
    assert payload["structure"][0]["path"] == "(root)"
    assert payload["dependencies"]["edge_count"] == 0


def test_detect_test_method_no_tests(tmp_path: Path):
    """无测试文件 → unknown (诚实不猜)。"""
    project = tmp_path / "no_tests"
    project.mkdir()
    (project / "x.py").write_text("x = 1\n", encoding="utf-8")
    assert detect_test_method(project, "python") == "unknown"


# ------------------------------------------------------------ 基线 (失败安全)


def test_run_baseline_build_passed(tmp_path: Path):
    """build_command 成功 (exit 0) → build.status passed。"""
    project = make_python_repo(tmp_path, name="s9_004_bl_pass")
    result = run_baseline(project, build_command=f"{sys.executable} -c 'print(1)'")
    assert result["build"]["status"] == "passed"
    assert result["build"]["returncode"] == 0


def test_run_baseline_build_failed(tmp_path: Path):
    """build_command 失败 (exit 1) → build.status failed (不抛异常)。"""
    project = make_python_repo(tmp_path, name="s9_004_bl_fail")
    result = run_baseline(
        project, build_command=f"{sys.executable} -c 'import sys; sys.exit(1)'"
    )
    assert result["build"]["status"] == "failed"
    assert result["build"]["returncode"] == 1


def test_run_baseline_missing_command_unavailable(tmp_path: Path):
    """命令缺失 + 非 python → unavailable (记录原因, 不崩溃)。"""
    project = tmp_path / "s9_004_bl_unavail"
    project.mkdir()
    (project / "x.go").write_text("package main\n", encoding="utf-8")
    result = run_baseline(project, language="go")
    assert result["build"]["status"] == "unavailable"
    assert "no build command" in result["build"]["output_head"]
    assert result["test"]["status"] == "unavailable"


def test_run_baseline_python_syntax_check_passed(tmp_path: Path):
    """python + 无 build_command → ast.parse 语法检查 passed (零副作用)。"""
    project = make_python_repo(tmp_path, name="s9_004_syn_ok")
    result = run_baseline(project, language="python")
    assert result["build"]["status"] == "passed"
    assert result["build"]["command"] == "syntax_check(python)"
    assert not (project / "__pycache__").exists()  # 零副作用铁律


def test_run_baseline_python_syntax_check_failed(tmp_path: Path):
    """语法损坏 → syntax_check failed + 错误位置 (不崩溃)。"""
    project = make_python_repo(
        tmp_path, name="s9_004_syn_bad", broken_syntax=True
    )
    result = run_baseline(project, language="python")
    assert result["build"]["status"] == "failed"
    assert "hello.py" in result["build"]["output_head"]
    assert result["build"]["error_count"] >= 1


def test_syntax_check_python_skips_noise(tmp_path: Path):
    """syntax_check 跳过噪声目录 (node_modules 内坏文件不影响)。"""
    project = tmp_path / "s9_004_syn_noise"
    (project / "node_modules").mkdir(parents=True)
    (project / "node_modules" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (project / "ok.py").write_text("x = 1\n", encoding="utf-8")
    result = syntax_check_python(project)
    assert result["status"] == "passed"


def test_run_baseline_test_passed_counts(tmp_path: Path):
    """test_command 输出 '2 passed' → test.passed=2 / failed=0。"""
    project = make_python_repo(tmp_path, name="s9_004_tp")
    result = run_baseline(
        project, test_command=f"{sys.executable} -c 'print(\"2 passed, 0 failed\")'"
    )
    assert result["test"]["status"] == "passed"
    assert result["test"]["passed"] == 2
    assert result["test"]["failed"] == 0


def test_run_baseline_test_failed_counts(tmp_path: Path):
    """test_command 输出 '1 failed, 3 passed' + exit 1 → failed 计数正确。"""
    project = make_python_repo(tmp_path, name="s9_004_tf")
    result = run_baseline(
        project,
        test_command=(
            f"{sys.executable} -c 'import sys; "
            "print(\"3 passed, 1 failed\"); sys.exit(1)'"
        ),
    )
    assert result["test"]["status"] == "failed"
    assert result["test"]["passed"] == 3
    assert result["test"]["failed"] == 1


def test_run_baseline_test_missing_unavailable(tmp_path: Path):
    """test_command 缺失 → test.status unavailable (失败安全)。"""
    project = make_python_repo(tmp_path, name="s9_004_tu")
    result = run_baseline(project, language="python")
    assert result["test"]["status"] == "unavailable"
    assert result["test"]["passed"] == 0
    assert result["test"]["failed"] == 0


def test_run_baseline_analysis_ref_placeholder(tmp_path: Path):
    """analysis_ref 由 org 侧回填 — exec 侧返回空占位。"""
    project = make_python_repo(tmp_path, name="s9_004_ref")
    result = run_baseline(project, language="python")
    assert result["analysis_ref"] == ""


# ------------------------------------------------------------ 上下文快照


def test_build_context_snapshot_tree_and_important(tmp_path: Path):
    """快照: 浅层树含文件/目录 + important_files 按重要性排序。"""
    project = make_python_repo(tmp_path, name="s9_004_snap")
    snapshot = build_context_snapshot(project)
    assert snapshot["tree_entries"] >= 4
    assert any(line.endswith("main.py") for line in snapshot["tree"])
    assert any(line.endswith("tests/") for line in snapshot["tree"])
    important = snapshot["important_files"]
    assert important and important[0]["path"] == "main.py"  # high 入口优先
    assert important[0]["importance"] == "high"
    assert "line_count" in important[0]


def test_build_context_snapshot_architecture_fields(tmp_path: Path):
    """快照: architecture 含 entry_points/tech_stack/risk_areas/summary。"""
    project = make_python_repo(tmp_path, name="s9_004_arch")
    snapshot = build_context_snapshot(project)
    arch = snapshot["architecture"]
    assert set(arch) == {
        "entry_points", "core_modules", "tech_stack", "risk_areas", "summary_text",
    }
    assert any("main.py" in ep for ep in arch["entry_points"])
    assert snapshot["summary_text"]
