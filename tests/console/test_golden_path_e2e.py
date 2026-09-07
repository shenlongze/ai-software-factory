"""Cognitive Golden Path — Phase 7: 完整 E2E (Golden Path §22/§28)。

真实全链 (非固定台词; 覆盖语义等价表达):
```
1 创建/进入 Conversation
2 输入模糊 Idea (自然语言)
3 自然讨论 (平台/约束/操作/未来)
4 Product Understanding 增长
5 AI 展示当前理解 (understanding_statement)
6 用户自然修改 (还是做成网页吧 → REPLACE)
7 用户否定 (不要登录 → CONSTRAINT/REJECT)
8 用户延后已有需求 (排行榜先不做 → DEFER)
9 用户替换已有决定 (虚拟按键 → 虚拟摇杆 → REPLACE)
10 用户问"你觉得还有什么问题" → 主动缺口分析
11 结束 Session
12 新 Session 恢复 (同一 Product Understanding)
13 继续修改
14 生成 PRD
15 自然修改 PRD (简单一点 → v2 范围收窄)
16 生成新 PRD version
17 用户确认 PRD (approve)
18 生成 Development Plan
19 用户确认 Plan (approve)
20 进入 Production Runtime (execution gate 全过)
21 NodeRun / Artifact / Verification / Delivery
```
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


def _delivering_capability(input_data: dict) -> dict:
    """Production capability: 返回真实交付物 (模拟 Agent 执行)。"""
    task = (input_data or {}).get("task", {})
    return {"ok": True, "output": f"delivered:{task.get('id', '?')}",
            "deliverable": f"真实交付物 {task.get('title', '')}"}


class TestGoldenPathE2E:
    def test_full_golden_path(self, root: str) -> None:
        """从模糊想法一路走到真实交付 — 唯一验收主线 (Golden Path §28)。"""
        # 1. 创建/进入 Conversation (Session A)
        app_a = ca.ConversationApplicationService(root)
        cid = app_a.create(title="飞机大战小游戏")["id"]
        svc_a = ca.ProductUnderstandingService(root, interpreter=_nlp_semantic_interp)

        # 2. 模糊 Idea → 3. 自然讨论 → 4. Understanding 增长
        svc_a.process_user_message(cid, "我想做一个飞机大战小游戏。")
        svc_a.process_user_message(cid, "手机端。")
        svc_a.process_user_message(cid, "不要登录, 打开就能玩。")
        svc_a.process_user_message(cid, "以后可以加排行榜。")
        snap = svc_a.snapshot(cid)
        assert snap["version"] >= 4
        types = {f["type"] for f in snap["facts"]}
        assert "IDEA" in types and "REQUIREMENT" in types and "FUTURE_IDEA" in types

        # 5. AI 展示当前理解 (用户可见)
        stmt = svc_a.understanding_statement(cid)
        assert "我目前理解的是" in stmt and "飞机大战" in stmt

        # 6. 自然修改 (手机端 → 网页端 REPLACE)
        svc_a.process_user_message(cid, "还是做成网页吧。")
        reqs = svc_a.facts(cid, fact_type="REQUIREMENT")
        assert len(reqs) == 1 and "网页端" in reqs[0]["content"]

        # 7. 否定 (不要登录 → 已记录 CONSTRAINT)
        #    (fake interpreter 把"不要登录"变 CONSTRAINT — 已在上文; 此处验证存在)
        cons = svc_a.facts(cid, fact_type="CONSTRAINT")
        assert any("登录" in f["content"] for f in cons)

        # 8. 延后已有需求 (排行榜先不做 → DEFER)
        svc_a.process_user_message(cid, "排行榜先不做。")
        snap8 = svc_a.snapshot(cid)
        assert any("排行榜" in f["content"] for f in snap8["deferred"]), snap8

        # 9. 用户替换决定 (先决定按键 → 替换成摇杆)
        svc_a.process_user_message(cid, "操作就用虚拟按键吧。")
        svc_a.process_user_message(cid, "别用按键了, 用虚拟摇杆。")
        decs = svc_a.facts(cid, fact_type="DECISION")
        assert len(decs) == 1 and "摇杆" in decs[0]["content"]

        # 10. 主动缺口分析 ("你觉得还有什么问题")
        gaps = svc_a.analysis_gaps(cid)
        assert gaps  # 有真正缺口

        # 11. 结束 Session A
        app_a.close(cid)

        # 12. 新 Session 恢复同一 Product Understanding
        app_b = ca.ConversationApplicationService(root)
        svc_b = ca.ProductUnderstandingService(root, interpreter=_nlp_semantic_interp)
        conv_b = app_b.get(cid)
        assert conv_b is not None
        snap_b = svc_b.snapshot(cid)
        assert any(f["type"] == "IDEA" and "飞机大战" in f["content"]
                   for f in snap_b["facts"])

        # 13. 继续修改 (Session B)
        svc_b.process_user_message(cid, "还需要支持暂停。")
        assert any("暂停" in f["content"] for f in svc_b.facts(cid))

        # 14. 生成 PRD
        prd_v1 = gp.generate_prd(root, cid)
        assert prd_v1["version"] == 1 and prd_v1["status"] == "draft"

        # 15-16. 自然修改 PRD (简单一点 → 范围收窄 → v2)
        svc_b.process_user_message(cid, "简单一点, 第一版做最小版本。")
        prd_v2 = gp.generate_prd(root, cid)
        assert prd_v2["version"] == 2
        assert prd_v2["source_product_understanding_version"] > \
            prd_v1["source_product_understanding_version"]
        # PRD v2 provenance 保留 (知道来自哪个理解版本)
        assert prd_v2["id"] == prd_v1["id"]  # 同一 PRD 记录升版 (非新对象)
        # v2 内容含范围收窄约束
        v2_content = str(prd_v2["content"])
        assert "MVP" in v2_content or "收窄" in v2_content, v2_content

        # 17. 用户确认 PRD ("就按这个做")
        approved_prd = gp.approve_prd(root, cid, prd_v2["id"])
        assert approved_prd["status"] == "approved"

        # 18. 生成 Development Plan (provenance: prd_id + prd_version)
        plan = gp.generate_plan(root, cid)
        assert plan["status"] == "pending"
        assert plan["prd_id"] == prd_v2["id"]
        assert plan["prd_version"] == prd_v2["version"]

        # 19. 用户确认 Plan
        gp.approve_plan(root, plan["id"])

        # 20-21. 进入 Production Runtime → NodeRun/Artifact/Verification/Delivery
        out = gp.execute_approved(root, cid, capability_fn=_delivering_capability)
        assert out["plan_id"] == plan["id"]
        assert out["prd_id"] == prd_v2["id"]
        assert len(out["executed"]) == len(plan["tasks"])
        for e in out["executed"]:
            r = e["result"]
            assert r.get("state") == "COMPLETED"
            assert r.get("verification") == "PASS"
            assert r.get("artifact_id")  # Artifact 真实生成
        # 交付物
        assert all("delivered" in str(e["result"].get("output") or "")
                   for e in out["executed"])
        # Production 事实落盘 (NodeRun 可查)
        from factory_console import node_runtime as nr
        runs = nr.list_node_runs(root)
        assert len(runs) >= len(plan["tasks"])

    def test_gate_blocks_premature_execution(self, root: str) -> None:
        """未确认(PRD/Plan) → 任何时点不能提前进生产 (Golden Path §20/§24)。"""
        cid = ca.ConversationApplicationService(root).create(title="t")["id"]
        svc = ca.ProductUnderstandingService(root, interpreter=_nlp_semantic_interp)
        svc.process_user_message(cid, "我想做一个飞机大战小游戏。")
        # 无 PRD → 拒绝
        with pytest.raises(gp.GoldenPathError):
            gp.execute_approved(root, cid)
        # PRD 生成但未确认 → 拒绝
        prd = gp.generate_prd(root, cid)
        with pytest.raises(gp.GoldenPathError):
            gp.execute_approved(root, cid)
        # PRD 已确认但 Plan 未确认 → 拒绝
        gp.approve_prd(root, cid, prd["id"])
        with pytest.raises(gp.GoldenPathError):
            gp.execute_approved(root, cid)

    def test_intent_is_not_lifecycle_truth(self, root: str) -> None:
        """Intent 不存在于 Golden Path 主链 (Product lifecycle 由理解+确认驱动)。"""
        import inspect
        from factory_console import golden_path
        src = inspect.getsource(golden_path)
        # 注释/docstring 允许提到 Intent (解释为什么不使用);
        # 核心: 不得有 intent 变量/常量/状态机引用
        assert "intent_type" not in src and "intent ==" not in src
        assert "def detect_intent" not in src and "INTENT_" not in src
        # 生产入口 = execute_approved (approved-gated), 非 intent dispatch
        assert "def execute_approved" in src
