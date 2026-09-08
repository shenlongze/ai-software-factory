"""tests/console/test_canonical_golden_path.py — Canonical Application Orchestrator 测试。

R0 P0 (2026-09-08): CanonicalGoldenPath 是 Application Orchestrator (非新业务域):
- 复用 conversation_app / golden_path / product_truth / production_runtime
- Lifecycle Gate 由 golden_path 强制 — 测试证明无绕过、无自动批准/执行
- 自然语言理解用 deterministic interpreter (semantic=False, CI 无 LLM 依赖)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console.canonical_golden_path import (  # noqa: E402
    CanonicalGoldenPath,
    detect_lifecycle,
)


def _fake_capability(input_data: dict[str, Any]) -> dict[str, Any]:
    """注入式执行能力 (生产 execute_task 同代码路径; 仅能力实现被替换)。"""
    task = (input_data or {}).get("task") or {}
    return {
        "ok": True,
        "output": {"task_id": task.get("id"), "title": task.get("title"),
                   "result": "ok"},
        "summary": f"fake capability executed: {task.get('title')}",
        "metadata": {"source": "test_canonical_golden_path"},
    }


@pytest.fixture()
def orch(tmp_path: Path) -> CanonicalGoldenPath:
    return CanonicalGoldenPath(str(tmp_path), semantic=False)


@pytest.fixture()
def conv(orch: CanonicalGoldenPath) -> str:
    return orch.create_conversation(title="测试会话")["id"]


# ---------------------------------------------------------------- NL 映射 (保守)
def test_detect_lifecycle_phrase_mapping() -> None:
    assert detect_lifecycle("整理成 PRD") == "generate_prd"
    assert detect_lifecycle("帮我生成开发计划") == "generate_plan"
    assert detect_lifecycle("就按这个做") == "approve_prd"
    assert detect_lifecycle("确认计划") == "approve_plan"
    assert detect_lifecycle("开始做") == "execute"
    assert detect_lifecycle("状态") == "status"
    # 普通自然语言 / 模糊确认 → 不触发生命周期
    assert detect_lifecycle("我觉得可以加个排行榜") is None
    assert detect_lifecycle("可以") is None
    assert detect_lifecycle("好的") is None


# ---------------------------------------------------------------- 理解管道
def test_nl_idea_updates_understanding(orch: CanonicalGoldenPath,
                                       conv: str) -> None:
    res = orch.handle(conv, "我想做一个飞机大战小游戏，可以在浏览器运行")
    assert res["kind"] == "chat"
    assert res["reply"]
    snap = orch.understanding.snapshot(conv)
    assert snap["version"] >= 1
    types = {f.get("type") for f in snap.get("facts", [])}
    assert "IDEA" in types


def test_empty_conversation_cannot_generate_prd(orch: CanonicalGoldenPath,
                                                conv: str) -> None:
    # 无 Product Understanding → Domain 拒绝派生 PRD (诚实, 不猜)
    res = orch.handle(conv, "整理成 PRD")
    assert res["kind"] == "gate"
    assert "Product Understanding" in res["reply"] or "无法派生" in res["reply"] \
        or "尚无" in res["reply"]


# ---------------------------------------------------------------- Gate 完整性
def test_execute_blocked_until_prd_and_plan_approved(
        orch: CanonicalGoldenPath, conv: str) -> None:
    orch.handle(conv, "我想做一个飞机大战小游戏，可以在浏览器运行")

    # 无 PRD → Gate 拒绝
    res = orch.handle(conv, "开始做")
    assert res["kind"] == "gate"

    # PRD 草稿 → 仍 Gate 拒绝 (PRD 未确认)
    assert orch.handle(conv, "整理成 PRD")["kind"] == "lifecycle"
    res = orch.handle(conv, "开始做")
    assert res["kind"] == "gate"

    # PRD 已确认但无 Plan → Gate 拒绝
    assert orch.handle(conv, "就按这个做")["kind"] == "lifecycle"
    assert orch.handle(conv, "生成计划")["kind"] == "lifecycle"
    res = orch.handle(conv, "开始做")
    assert res["kind"] == "gate"  # Plan 未确认

    # Plan 已确认 → 可执行 (注入 capability)
    assert orch.handle(conv, "确认计划")["kind"] == "lifecycle"
    res = orch.handle(conv, "开始做", capability_fn=_fake_capability)
    assert res["kind"] == "lifecycle"
    assert res["action"] == "execute"


def test_generic_confirm_does_not_bypass_prd_gate(
        orch: CanonicalGoldenPath, conv: str) -> None:
    orch.handle(conv, "我想做一个飞机大战小游戏，可以在浏览器运行")
    assert orch.handle(conv, "整理成 PRD")["kind"] == "lifecycle"

    # "可以" 是普通对话 (可能确认理解), 不是自动批准 PRD
    res = orch.handle(conv, "可以")
    assert res["kind"] == "chat"
    st = orch.status(conv)["path"]
    assert any(p.get("status") == "draft" for p in st.get("prds", []))


# ---------------------------------------------------------------- 全链 (含执行)
def test_full_golden_path_flow_with_capability(
        orch: CanonicalGoldenPath, conv: str) -> None:
    res = orch.handle(conv, "我想做一个飞机大战小游戏，可以在浏览器运行，"
                            "需要飞机移动、发射子弹、敌机出现和基本得分")
    assert res["kind"] == "chat"

    assert orch.handle(conv, "整理成 PRD")["kind"] == "lifecycle"
    assert orch.handle(conv, "就按这个做")["kind"] == "lifecycle"
    assert orch.handle(conv, "生成计划")["kind"] == "lifecycle"
    assert orch.handle(conv, "确认计划")["kind"] == "lifecycle"

    res = orch.handle(conv, "开始做", capability_fn=_fake_capability)
    assert res["kind"] == "lifecycle"
    executed = res["detail"]["executed"]
    assert executed, "Golden Path 执行后应产生 executed tasks"
    assert all((e.get("result") or {}).get("state") == "COMPLETED"
               for e in executed)
    # NodeRun / Artifact / Verification / Evidence 事实存在 (production_runtime 产物)
    run_ids = [(e.get("result") or {}).get("run_id") for e in executed]
    assert all(run_ids)

    # 无第二套 Truth: 单一 conversation + 单一 PRD + 单一 Plan
    st = orch.status(conv)["path"]
    assert st["prd_count"] == 1
    assert len(st["plans"]) >= 1


def test_session_continuity_new_orchestrator_same_root(
        tmp_path: Path, conv: str) -> None:
    """同一 root 下, 新 Orchestrator 实例能恢复同一 conversation (Session 断连语义)。"""
    orch2 = CanonicalGoldenPath(str(tmp_path), semantic=False)
    res = orch2.handle(conv, "我想做一个飞机大战小游戏")
    assert res["kind"] == "chat"
    assert orch2.understanding.snapshot(conv)["version"] >= 1
