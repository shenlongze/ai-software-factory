"""test_demo_markpad_lifecycle.py — Phase 13A: demo.markpad 生命周期 API 直测。

直接调 run_markpad_demo (与 CLI --json 同一出口): 生命周期 completed / 8 阶段
日志 / Artifact/Decision/Task/审批/经验 / 临时根清理 (禁 /tmp 固定路径, tempfile)
/ 输入缺失错误。全部真实业务逻辑 (Mock 只生成内容)。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from demo.markpad import DEMO_NAME, DemoError, default_demo_dir, run_markpad_demo


def test_demo_lifecycle_completed() -> None:
    """完整生命周期: 8 阶段跑通 → lifecycle completed (template=software_project)。"""
    result = run_markpad_demo()
    assert result["demo"] == DEMO_NAME
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["idea"]["title"] == "MarkPad 表格编辑器增强"
    lifecycle = result["lifecycle"]
    assert lifecycle["template"] == "software_project"
    assert lifecycle["status"] == "completed"
    assert lifecycle["completed_at"] is not None
    assert [s["stage"] for s in result["stages"]] == [
        "idea", "research", "prd", "approval(prd)",
        "ui", "approval(ui)", "architecture", "task",
    ]


def test_demo_artifacts_decisions_tasks() -> None:
    """关键产物齐备: Artifact ≥8 (含决策链) / Decision 3 种 / Task ≥1 / 审批 2 条已批准。"""
    result = run_markpad_demo()
    types = [a["type"] for a in result["artifacts"]]
    for expected in ("product_idea", "research", "prd", "ui", "architecture"):
        assert expected in types, f"missing artifact {expected}"
    assert "product_decision" in types and "task_plan" in types
    decision_types = {d["type"] for d in result["decisions"]}
    assert decision_types == {"product", "architecture", "task_plan"}
    assert len(result["tasks"]) >= 1
    assert result["tasks"][0]["id"].startswith("T-")
    approvals = result["approvals"]
    assert len(approvals) == 2
    assert all(a["status"] == "approved" for a in approvals)
    assert result["events_count"] >= 40
    assert "product.lifecycle.completed" in result["event_types"]


def test_demo_stage_log_shape() -> None:
    """阶段日志三要素: 每步 stage/action/events; 生成步带 Artifact; 审批步带 Decision。"""
    stages = run_markpad_demo()["stages"]
    by_stage = {s["stage"]: s for s in stages}
    for stage in ("idea", "research", "prd", "ui", "architecture", "task"):
        step = by_stage[stage]
        assert step["action"]
        assert isinstance(step["events"], list) and step["events"]
    # 生成步产物: research/prd/ui 带 Artifact; approval 步带 approval (Decision)
    assert by_stage["research"]["artifact"] is not None
    assert by_stage["prd"]["artifact"] is not None
    assert by_stage["ui"]["artifact"] is not None
    assert by_stage["approval(prd)"]["approval"]["status"] == "approved"
    assert by_stage["approval(ui)"]["approval"]["status"] == "approved"
    assert by_stage["idea"]["artifact"] is not None  # product_idea 随 idea 创建


def test_demo_experiences_recorded() -> None:
    """经验闭环: 正向 (rating 5) + 负向 (rating 2) + 审批经验各 1 条。"""
    result = run_markpad_demo()
    assert result["experience_positive"]["rating"] == 5
    assert result["experience_positive"]["approved"] is True
    assert result["experience_negative"]["rating"] == 2
    assert result["experience_negative"]["approved"] is False
    assert len(result["experiences"]) >= 2
    assert len(result["approval_experiences"]) >= 1
    assert "product.experience.recorded" in result["event_types"]
    assert "product.approval_experience.recorded" in result["event_types"]


def test_demo_temp_root_cleanup() -> None:
    """默认退出清理: 临时工厂根 (tempfile) 运行后不存在 (无 /tmp 固定路径残留)。"""
    result = run_markpad_demo()
    root = Path(result["root"])
    assert result["kept"] is False
    assert not root.exists(), f"temp root leaked: {root}"


def test_demo_keep_root_preserves() -> None:
    """--keep-root 语义: kept=true 且临时根保留 (人工检视), 测试后手动清理。"""
    result = run_markpad_demo(keep_root=True)
    root = Path(result["root"])
    try:
        assert result["kept"] is True
        assert root.is_dir()
        assert (root / "factory.db").exists()
        assert (root / "product").is_dir() and (root / "tasks").is_dir()
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def test_demo_default_demo_dir_points_to_examples() -> None:
    """默认 demo 目录 = examples/markpad-demo (与仓库布局对齐, 含 expected-flow.md)。"""
    d = default_demo_dir()
    assert d.name == "markpad-demo"
    assert (d / "idea.json").is_file()
    assert (d / "requirements.json").is_file()
    assert (d / "expected-flow.md").is_file()


def test_demo_missing_input_error(tmp_path: Path) -> None:
    """输入缺失 → DemoError (CLI 映射 rc=1), 不产生半成品工厂根。"""
    empty = tmp_path / "empty-demo"
    empty.mkdir()
    with pytest.raises(DemoError, match="demo input missing"):
        run_markpad_demo(demo_dir=empty)


def test_demo_custom_demo_dir_and_approver(tmp_path: Path) -> None:
    """自定义 demo 目录 (拷贝真实输入) + 自定义审批人: 结果携带两者。"""
    src = default_demo_dir()
    demo_dir = tmp_path / "custom-demo"
    demo_dir.mkdir()
    for name in ("idea.json", "requirements.json"):
        (demo_dir / name).write_text(
            (src / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    result = run_markpad_demo(demo_dir=demo_dir, approver="bob")
    assert result["approver"] == "bob"
    assert result["lifecycle"]["status"] == "completed"


def test_demo_no_fixed_tmp_path_dependency() -> None:
    """临时根由 tempfile 创建 (不在固定 /tmp 下硬编码路径)。"""
    result = run_markpad_demo()
    root = str(result["root"])
    assert "factory-demo-markpad-" in root
    assert tempfile.gettempdir() in root  # tempfile 语义, 非硬编码 /tmp/xxx
