"""test_demo_installation.py — Phase 13A: 安装冒烟 (scripts/setup.sh --check / console
script / examples 文件存在性 / scripts/demo.sh 一键演示)。

覆盖安装面: setup.sh --check 轻量验证 (只读) / .venv console script (`factory`
入口) / examples/markpad-demo 输入文件 / demo.sh 人类可读 + --json 摘要。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run_script(repo_root: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    """以 bash 运行仓库脚本 (scripts/*.sh), 返回 CompletedProcess。"""
    return subprocess.run(
        ["bash", str(repo_root / "scripts" / script), *args],
        cwd=repo_root, capture_output=True, text=True, timeout=180,
    )


def test_demo_examples_files_exist(repo_root: Path) -> None:
    """examples/markpad-demo 三件套存在: idea.json/requirements.json/expected-flow.md。"""
    demo_dir = repo_root / "examples" / "markpad-demo"
    for name in ("idea.json", "requirements.json", "expected-flow.md"):
        f = demo_dir / name
        assert f.is_file(), f"missing example file {f}"
    idea = json.loads((demo_dir / "idea.json").read_text(encoding="utf-8"))
    assert idea["title"] == "MarkPad 表格编辑器增强"
    assert (demo_dir / "requirements.json").stat().st_size > 0


def test_setup_script_check_smoke(repo_root: Path) -> None:
    """bash scripts/setup.sh --check: 只读轻量验证, 退出码 0 (venv/console/examples 就绪)。"""
    proc = _run_script(repo_root, "setup.sh", "--check")
    assert proc.returncode == 0, f"setup --check failed:\n{proc.stdout}\n{proc.stderr}"
    assert "就绪" in proc.stdout


def test_setup_script_executable(repo_root: Path) -> None:
    """scripts/setup.sh + demo.sh 可执行 (chmod +x, 安装后可直接 ./scripts/demo.sh)。"""
    for name in ("setup.sh", "demo.sh"):
        f = repo_root / "scripts" / name
        assert f.is_file(), f"missing script {f}"
        assert f.stat().st_mode & 0o111, f"script not executable: {f}"


def test_console_script_smoke(repo_root: Path) -> None:
    """console script: .venv/bin/factory 存在且可执行; factory --help 退出码 0。"""
    factory = repo_root / ".venv" / "bin" / "factory"
    assert factory.is_file(), f"console script missing: {factory} (先运行 scripts/setup.sh)"
    proc = subprocess.run(
        [str(factory), "--help"], cwd=repo_root,
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "demo" in proc.stdout  # Phase 13A: demo 命令已注册


def test_demo_script_json_smoke(repo_root: Path) -> None:
    """bash scripts/demo.sh --json: 一键演示, JSON 摘要含 completed 生命周期。"""
    proc = _run_script(repo_root, "demo.sh", "--json")
    assert proc.returncode == 0, f"demo.sh --json failed:\n{proc.stdout}\n{proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["demo"] == "markpad"
    assert data["lifecycle"]["status"] == "completed"
    assert len(data["stages"]) == 8


def test_demo_script_human_smoke(repo_root: Path) -> None:
    """bash scripts/demo.sh (人类可读): 退出码 0 且含生命周期关键输出。"""
    proc = _run_script(repo_root, "demo.sh")
    assert proc.returncode == 0, f"demo.sh failed:\n{proc.stdout}\n{proc.stderr}"
    assert "MarkPad Demo 完整生命周期完成" in proc.stdout
    assert "summary" in proc.stdout.lower() or "汇总" in proc.stdout
