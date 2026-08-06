"""test_demo_markpad_cli.py — Phase 13A: `factory demo markpad` CLI 冒烟 (人类可读 + --json)。

链路: CLI parser → cmd_demo_markpad (延迟 import demo.markpad) → 临时工厂根
(tempfile) → Mock Provider 生命周期 → _print_demo 人类可读渲染。
覆盖: 退出码 / 生命周期关键输出 (阶段/Artifact/Event/Decision/汇总) / --approver /
--json 结构。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_helpers import run_cli

EXPECTED_STAGES = [
    "idea", "research", "prd", "approval(prd)",
    "ui", "approval(ui)", "architecture", "task",
]


def test_demo_cli_run_ok(capsys, cli_root: Path) -> None:
    """`factory demo markpad` 退出码 0 且输出生命周期完成标记 (人类可读路径无 NameError)。"""
    rc, out, err = run_cli(capsys, cli_root, "demo", "markpad")
    assert rc == 0, err
    assert "MarkPad Demo 完整生命周期完成" in out
    assert "completed" in out
    assert "lifecycle" in out


def test_demo_cli_lifecycle_output(capsys, cli_root: Path) -> None:
    """人类可读输出含 8 阶段日志三要素 (Artifact/Event/Decision) 与汇总 (推荐/经验)。"""
    rc, out, err = run_cli(capsys, cli_root, "demo", "markpad")
    assert rc == 0, err
    for i, stage in enumerate(EXPECTED_STAGES, start=1):
        assert f"[{i}] {stage}" in out, f"missing stage [{i}] {stage}"
    assert "Artifact" in out
    assert "Event" in out
    assert "Decision" in out
    assert "汇总" in out
    assert "推荐" in out
    assert "经验" in out
    assert "Events" in out


def test_demo_cli_approver_option(capsys, cli_root: Path) -> None:
    """--approver 自定义审批人出现在输出 (demo 自动批准, 审批人可配置)。"""
    rc, out, err = run_cli(capsys, cli_root, "demo", "markpad", "--approver", "alice")
    assert rc == 0, err
    assert "alice" in out


def test_demo_cli_json_structure(capsys, cli_root: Path) -> None:
    """--json 走全局 JSON 前置: 解析成功且含生命周期/阶段/产物/事件关键键。"""
    rc, out, err = run_cli(capsys, cli_root, "demo", "markpad", "--json")
    assert rc == 0, err
    data = json.loads(out)
    assert data["demo"] == "markpad"
    assert data["ok"] is True
    assert data["exit_code"] == 0
    assert data["lifecycle"]["status"] == "completed"
    assert data["lifecycle"]["template"] == "software_project"
    assert [s["stage"] for s in data["stages"]] == EXPECTED_STAGES
    for key in ("idea", "artifacts", "decisions", "tasks", "approvals",
                "experiences", "events_count", "root", "approver", "kept"):
        assert key in data, f"missing json key {key}"


def test_demo_cli_keep_root_option(capsys, cli_root: Path, tmp_path: Path) -> None:
    """--keep-root: 输出显示 kept=true 且临时根目录被保留 (人工检视用)。"""
    rc, out, err = run_cli(capsys, cli_root, "demo", "markpad", "--keep-root")
    assert rc == 0, err
    assert "kept: true" in out
    root_dir = Path(out.split("root")[-1].split("(")[0].strip())
    assert root_dir.is_dir(), f"kept root missing: {root_dir}"
    # 清理保留的临时根 (避免测试泄漏)
    import shutil
    shutil.rmtree(root_dir, ignore_errors=True)
