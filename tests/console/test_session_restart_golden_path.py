"""Cognitive Golden Path — Phase 6: Session Restart Continuity。

验证 Golden Path §15/§23/§28:
- Session A 自然语言建立 Product Understanding → close
- Session B (新 service 实例) → 继续同一产品认知 (持久化理解 + 相关历史重组,
  非把整个聊天塞回 context)
- 继续修改/否定/延后 → 正确作用于持久化理解
- Understanding/PRD 跨 session 保留 provenance

测试模型: "Session" = ConversationApplicationService + ProductUnderstandingService
实例生命周期 (新实例 = 新 session); conversation (conv-*) 持久化于 root —
Session restart = 同 root 新建 service 实例加载同 conversation。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import conversation_app as ca  # noqa: E402
from factory_console import golden_path as gp  # noqa: E402
from tests.console.test_understanding_confirmation import (  # noqa: E402
    _nlp_semantic_interp,
)


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


def _session(root: str) -> ca.ProductUnderstandingService:
    """新 Session = 新 service 实例 (同 root 持久化)。"""
    return ca.ProductUnderstandingService(root, interpreter=_nlp_semantic_interp)


def _open_conversation(root: str, title: str = "飞机大战") -> str:
    return ca.ConversationApplicationService(root).create(title=title)["id"]


class TestSessionRestartContinuity:
    def test_understanding_survives_restart(self, root: str) -> None:
        """Session A 写入 → Session B (新实例) 恢复同一认知。"""
        cid = _open_conversation(root)
        # --- Session A ---
        svc_a = _session(root)
        svc_a.process_user_message(cid, "我想做一个飞机大战小游戏。")
        svc_a.process_user_message(cid, "手机端。")
        svc_a.process_user_message(cid, "不要登录, 打开就能玩。")
        snap_a = svc_a.snapshot(cid)
        # 结束 Session A (归档)
        ca.ConversationApplicationService(root).close(cid)
        # --- Session B (同 root, 新实例) ---
        svc_b = _session(root)
        conv_b = ca.ConversationApplicationService(root).get(cid)
        assert conv_b is not None  # conversation 仍在 (ARCHIVED 仍可读)
        snap_b = svc_b.snapshot(cid)
        assert snap_b["version"] >= snap_a["version"]
        assert {f["content"] for f in snap_b["facts"]} >= \
            {f["content"] for f in snap_a["facts"]}
        # IDEA 保留 (没被问"请描述产品")
        assert any(f["type"] == "IDEA" and "飞机大战" in f["content"]
                   for f in snap_b["facts"])

    def test_continue_modifying_after_restart(self, root: str) -> None:
        """Session B 继续修改 → 正确 supersede (非重新开始)。"""
        cid = _open_conversation(root)
        svc_a = _session(root)
        svc_a.process_user_message(cid, "我想做一个飞机大战小游戏。")
        svc_a.process_user_message(cid, "手机端。")
        ca.ConversationApplicationService(root).close(cid)
        # --- Session B: 用户改主意 手机端 → 网页端 ---
        svc_b = _session(root)
        svc_b.process_user_message(cid, "还是做成网页吧。")
        reqs = svc_b.facts(cid, fact_type="REQUIREMENT")
        assert len(reqs) == 1
        assert "网页端" in reqs[0]["content"]
        old = [f for f in svc_b.facts(cid, fact_type="REQUIREMENT",
                                      include_inactive=True)
               if f["status"] == "SUPERSEDED"]
        assert len(old) == 1 and "手机端" in old[0]["content"]
        # IDEA 未被破坏
        assert any(f["type"] == "IDEA" for f in svc_b.facts(cid))

    def test_continue_prd_chain_after_restart(self, root: str) -> None:
        """Session A 建 Understanding → Session B 生成并批准 PRD → Plan。"""
        cid = _open_conversation(root)
        svc_a = _session(root)
        svc_a.process_user_message(cid, "我想做一个飞机大战小游戏。")
        svc_a.process_user_message(cid, "手机端。")
        svc_a.process_user_message(cid, "操作就用虚拟摇杆吧。")
        ca.ConversationApplicationService(root).close(cid)
        # --- Session B: 继续到 Plan (全链跨 session) ---
        prd = gp.generate_prd(root, cid)
        assert prd["version"] == 1
        gp.approve_prd(root, cid, prd["id"])
        plan = gp.generate_plan(root, cid)
        assert plan["prd_id"] == prd["id"]
        gp.approve_plan(root, plan["id"])

    def test_understanding_version_anchor_stable(self, root: str) -> None:
        """PRD provenance 跨 session 仍指向正确的 understanding version。"""
        cid = _open_conversation(root)
        svc_a = _session(root)
        svc_a.process_user_message(cid, "我想做一个飞机大战小游戏。")
        svc_a.process_user_message(cid, "手机端。")
        v_before = svc_a.snapshot(cid)["version"]
        ca.ConversationApplicationService(root).close(cid)
        # --- Session B 生成 PRD → source version 与 Session A 结束时一致 ---
        svc_b = _session(root)
        assert svc_b.snapshot(cid)["version"] == v_before
        prd = gp.generate_prd(root, cid)
        assert prd["source_product_understanding_version"] == v_before
