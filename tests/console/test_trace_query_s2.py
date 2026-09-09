"""S1 第 5 刀 M2a/M2b — 认知审计事件 + factory trace 测试。

M2a: 真实 canonical 链 (理解→PRD→确认→Plan→确认) 后 audit_events.json
     含 PRODUCT_INTELLIGENCE/PRD_CREATED/PRD_APPROVED/PLAN_CREATED/
     APPROVAL_DECIDED, trace_id=conversation_id 可关联。
M2b: build_trace 覆盖每一环且与磁盘一致; 缺环 MISSING。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import conversation_app as ca  # noqa: E402
from factory_console import golden_path as gp  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402
from factory_console.trace_query import build_trace  # noqa: E402


def _seed_full(root: str) -> tuple[str, dict]:
    """理解→PRD→approve→Plan→approve→execute(带 1 失败叶), 返回 (cid, plan)。"""
    cid = ca.ConversationApplicationService(root).create(title="t")["id"]
    svc = ca.ProductUnderstandingService(root, semantic=False)
    svc.process_user_message(cid, "我想做一个飞机大战小游戏。")
    svc.process_user_message(cid, "手机端。")
    pu.upsert_fact(root, cid, fact_type="REQUIREMENT",
                   content="实现功能: 移动", source_message_id="",
                   confidence=1.0, provenance="test", status="CONFIRMED")
    prd = gp.generate_prd(root, cid)
    gp.approve_prd(root, cid, prd["id"])
    plan = gp.generate_plan(root, cid, decompose=True, decomposer=None)
    gp.approve_plan(root, plan["id"])

    def cap(inp: dict) -> dict:
        t = (inp.get("task") or {}).get("title", "")
        if "移动" in str(t):
            return {"ok": False, "error": "真实失败",
                    "output": {}, "artifact_type": "code_change"}
        return {"ok": True, "output": {"msg": "ok"},
                "artifact_type": "code_change"}

    gp.execute_approved(root, cid, capability_fn=cap)
    return cid, plan


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


class TestM2aCognitiveAudit:
    def test_cognitive_events_emitted(self, root: str) -> None:
        """M2a: 认知段 5 类事件各就位, trace_id 关联会话。"""
        cid, _ = _seed_full(root)
        evs = json.loads(Path(root, "audit", "audit_events.json").read_text(
            encoding="utf-8"))
        mine = [e for e in evs if (e.get("trace_id")) == cid]
        types = [e.get("event_type") or e.get("type") for e in mine]
        # 理解变更 (deterministic 首条产 ops → ≥1)
        assert "PRODUCT_INTELLIGENCE" in types, types
        # PRD 生命周期
        assert types.count("PRD_CREATED") == 1, types
        assert types.count("PRD_APPROVED") == 1, types
        assert types.count("PLAN_CREATED") == 1, types
        assert types.count("APPROVAL_DECIDED") == 1, types
        # PRD_CREATED 详情含版本与来源 (metadata)
        prd_ev = next(e for e in mine
                      if (e.get("event_type") or e.get("type"))
                      == "PRD_CREATED")
        ev = prd_ev.get("metadata") or {}
        assert ev.get("prd_id") and ev.get("version") == 1
        assert "source_understanding_version" in ev
        # evidence list 语义: 单元素且 id 为完整 prd_id (防按字符迭代 bug)
        ev_list = prd_ev.get("evidence") or []
        assert len(ev_list) == 1, ev_list
        assert ev_list[0]["id"] == ev.get("prd_id"), ev_list

    def test_audit_failure_does_not_break(self, root: str, monkeypatch) -> None:
        """M2a 失败安全: 审计不可写不中断 generate_prd。"""
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        ca.ProductUnderstandingService(root).process_user_message(
            cid, "我想做一个倒计时器。")
        # AuditStore.append 抛异常 → _emit_cognitive 内部 except → 不中断业务
        from factory_console.audit import audit_store as asm

        def boom(*a, **kw):
            raise RuntimeError("audit store down")

        monkeypatch.setattr(asm.AuditStore, "append", boom)
        prd = gp.generate_prd(root, cid)  # 不应抛 (审计故障安全)
        assert prd.get("id")


class TestM2bTraceQuery:
    def test_trace_covers_full_chain(self, root: str) -> None:
        """M2b: trace 覆盖理解/PRD/Plan/树/执行, 与磁盘一致。"""
        cid, plan = _seed_full(root)
        t = build_trace(root, cid)
        assert t["conversation"] != "MISSING"
        conv = t["conversation"]
        assert conv["understanding_version"] >= 1
        assert conv["fact_count"] >= 1
        # PRD
        assert t["prds"] != "MISSING"
        assert any(p["status"] == "approved" for p in t["prds"])
        # Plan + 树
        assert t["plans"] != "MISSING"
        assert any(p["id"] == plan["id"] and p["leaf_count"] >= 1
                   for p in t["plans"])
        # 执行: 有 FAILED (移动叶) 记录
        assert isinstance(t["node_runs"], list)
        assert any(nr["state"] == "FAILED" for nr in t["node_runs"])
        # audit: trace_id 关联认知事件
        assert isinstance(t["audit"], list)
        assert any(e["event_type"] == "PRD_CREATED" for e in t["audit"])

    def test_trace_missing_conversation(self, root: str) -> None:
        """M2b: 不存在会话 → conversation MISSING。"""
        t = build_trace(root, "conv-does-not-exist")
        assert t["conversation"] == "MISSING"
