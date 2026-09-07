"""S49 / Phase 5 — Product Understanding SSOT E2E 测试 (Test A–F + 单元)。

验收映射 (S49 §15/§16):
- Test A: 连续产品理解 — 自然语言逐句 → facts 完整 (idea/mobile/no-login/future/decision)
- Test B: Session Restart — Session1 写入+close → Session2 加载完整恢复
- Test C: 自然语言无 keyword — 输入全是普通中文句子, 无 GENERATE_PRD/SET_REQUIREMENT
- Test D: 修改不是新增重复 — supersession (同 constraint 复述不产生冲突事实)
- Test E: Context Continuity — Session2 追问基于持久化 Understanding 回答
- Test F: PRD 从 Understanding 派生 — source_product_understanding_version 可追踪

P0/P1 补充:
- Intent 不控制 Product 状态机 (本域无 intent→state 路径, 断言无 INTENT 依赖)
- Context 从持久化 Understanding 构建 (build_context)
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import application_formalization as fmt  # noqa: E402
from factory_console import conversation_app as ca  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402

#: 用户完整自然语言序列 (Test A / Test C — 无任何 keyword/内部命令)
NL_SEQUENCE = [
    "我想做一个飞机大战小游戏。",   # → IDEA
    "手机端。",                    # → REQUIREMENT platform
    "不要登录，打开就能玩。",      # → CONSTRAINT
    "以后可以加排行榜。",          # → FUTURE_IDEA
    "操作就用虚拟摇杆吧。",        # → DECISION
]


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv_svc(root: str) -> ca.ConversationApplicationService:
    return ca.ConversationApplicationService(root)


@pytest.fixture()
def pu_svc(root: str) -> ca.ProductUnderstandingService:
    return ca.ProductUnderstandingService(root)


def _run_nl(pus: ca.ProductUnderstandingService, conv_id: str,
            lines: list[str]) -> list[dict]:
    """逐句自然语言输入 (Test C: 用户输入必须是普通中文自然语言)。"""
    out = []
    for line in lines:
        out.append(pus.process_user_message(conv_id, line))
    return out


# ---------------------------------------------------------------- Test A / C

class TestContinuousUnderstanding:
    def test_nl_sequence_accumulates_all_fact_types(self, root: str,
                                                    conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        snap = pu_svc.snapshot(c["id"])
        types = {f["type"] for f in snap["facts"]}
        assert {"IDEA", "REQUIREMENT", "CONSTRAINT", "FUTURE_IDEA", "DECISION"} <= types
        contents = " ".join(str(f["content"]) for f in snap["facts"])
        assert "飞机大战" in contents
        assert "手机" in contents
        assert "登录" in contents
        assert "排行榜" in contents
        assert "摇杆" in contents

    def test_no_keyword_used(self) -> None:
        """Test C 强化: NL_SEQUENCE 不含任何内部命令/keyword。"""
        banned = ["GENERATE_PRD", "SET_REQUIREMENT", "/idea", "/requirement",
                  "UPDATE_REQUIREMENT", "INTENT_"]
        for line in NL_SEQUENCE:
            for b in banned:
                assert b.lower() not in line.lower()

    def test_no_intent_state_machine_dependency(self, root: str) -> None:
        """P0: Product Understanding 域不依赖 Intent → Workflow State Machine。"""
        import inspect
        src = inspect.getsource(pu) + inspect.getsource(ca)
        assert "INTENT_" not in src
        assert "state_machine" not in src.lower()


# ---------------------------------------------------------------- Test B / E

class TestSessionRestart:
    def test_session1_close_session2_restore(self, root: str,
                                             conv_svc, pu_svc) -> None:
        # Session 1
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE[:4])
        assert pu_svc.snapshot(c["id"])["version"] >= 4
        conv_svc.close(c["id"])  # session 结束

        # Session 2: 全新 service 实例, 同一 root
        svc2 = ca.ConversationApplicationService(root)
        c2 = svc2.get(c["id"])
        assert c2 is not None and c2["status"] == "ARCHIVED"
        pus2 = ca.ProductUnderstandingService(root)
        snap = pus2.snapshot(c["id"])
        assert snap["version"] >= 4
        types = {f["type"] for f in snap["facts"]}
        assert {"IDEA", "REQUIREMENT", "CONSTRAINT", "FUTURE_IDEA"} <= types

    def test_session2_continuation_knows_product(self, root: str,
                                                 conv_svc, pu_svc) -> None:
        """Test E: Session 2 追问, AI 基于持久化 Understanding 回答 (不重问产品)。"""
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        conv_svc.close(c["id"])
        # Session 2
        pus2 = ca.ProductUnderstandingService(root)
        snap = pus2.snapshot(c["id"])
        idea = next(f for f in snap["facts"] if f["type"] == "IDEA")
        assert "飞机大战" in idea["content"]
        # 追问 "操作方式?" → 应引用已记录 DECISION
        pus2.process_user_message(c["id"], "那操作方式具体怎么设计？")
        snap2 = pus2.snapshot(c["id"])
        dec = [f for f in snap2["facts"] if f["type"] == "DECISION"]
        assert dec and "摇杆" in dec[0]["content"]

    def test_restart_does_not_require_redescribe(self, root: str,
                                                 conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        conv_svc.close(c["id"])
        pus2 = ca.ProductUnderstandingService(root)
        # 直接问问题 (不重新描述) — 不应出现 "请描述你的产品"
        out = pus2.process_user_message(c["id"], "用什么操作方式比较好？")
        reply = out["reply"]
        assert "不知道你说的是什么项目" not in reply
        assert "请描述你的产品" not in reply


# ---------------------------------------------------------------- Test D

class TestSupersessionNotDuplicate:
    def test_restate_constraint_updates_not_duplicates(self, root: str,
                                                       conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        v0 = pu_svc.snapshot(c["id"])["version"]
        _run_nl(pus=pu_svc, conv_id=c["id"],
                lines=["不要登录，打开就能玩。", "还是不要登录，直接打开就能玩。"])
        eff = pu_svc.facts(c["id"], fact_type="CONSTRAINT")
        assert len(eff) == 1  # 不产生两个冲突 constraint
        assert eff[0]["status"] in ("PROPOSED", "CONFIRMED")
        # 同内容重申 = 原地更新 (understanding version 递增, 不新增重复 fact)
        assert pu_svc.snapshot(c["id"])["version"] > v0
        assert len(pu_svc.facts(c["id"], fact_type="CONSTRAINT",
                                include_inactive=True)) == 1

    def test_confirm_then_modify_supersedes(self, root: str,
                                            conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="记账App")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["手机端。"])
        f0 = pu_svc.facts(c["id"], fact_type="REQUIREMENT")[0]
        pu.transition_fact(root, c["id"], f0["id"], to="CONFIRMED")
        # 用户改主意 → 网页端 (同 identity key → SUPERSEDED, 不新增重复)
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["还是做成网页端吧。"])
        eff = pu_svc.facts(c["id"], fact_type="REQUIREMENT")
        assert len(eff) == 1
        assert "网页" in eff[0]["content"]
        allc = pu_svc.facts(c["id"], fact_type="REQUIREMENT", include_inactive=True)
        assert any(f["status"] == "SUPERSEDED" for f in allc)

    def test_fact_identity_key(self) -> None:
        assert pu.identity_key({"type": "CONSTRAINT", "content": "不要登录"}) == \
            ("CONSTRAINT", "不要登录")
        assert pu.normalize_content("不要登录， 打开就能玩") == "不要登录, 打开就能玩"


# ---------------------------------------------------------------- Context (P0)

class TestContextFromUnderstanding:
    def test_context_built_from_persisted_understanding(self, root: str,
                                                        conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        conv_svc.close(c["id"])
        ctx = pu_svc.context(c["id"])
        assert ctx["conversation_id"] == c["id"]
        assert ctx["understanding_version"] >= 1
        assert any("飞机大战" in str(f["content"]) for f in ctx["facts"])
        assert ctx["by_type"]["DECISION"]
        # Context 包含最近消息 (不靠重新猜)
        assert any("摇杆" in str(m["content"]) for m in ctx["recent_messages"])


# ---------------------------------------------------------------- Test F / PRD

class TestPRDFromUnderstanding:
    def test_prd_derived_with_provenance(self, root: str,
                                         conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        version_before = pu_svc.snapshot(c["id"])["version"]
        prd = fmt.create_prd(root, c["id"], actor="test")
        assert prd["conversation_id"] == c["id"]
        assert prd["version"] == 1
        assert prd["status"] == "draft"
        assert prd["source_product_understanding_version"] == version_before
        # structured content 可追踪
        prov = prd["content"]["provenance"]
        assert prov["source_understanding_version"] == version_before
        assert prov["facts"]

    def test_prd_versioned_after_modification(self, root: str,
                                              conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        prd1 = fmt.create_prd(root, c["id"], actor="test")
        # 修改 Understanding (用户补充约束) → update → v2 + 新 provenance
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["不要内购。"])
        prd2 = fmt.update_prd(root, c["id"], prd1["id"], actor="test")
        assert prd2["version"] == 2
        assert prd2["source_product_understanding_version"] > \
            prd1["source_product_understanding_version"]
        assert len(prd2["history"]) == 2

    def test_prd_markdown_projection(self, root: str,
                                     conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        prd = fmt.create_prd(root, c["id"], actor="test")
        md = fmt.render_prd_markdown(prd)
        assert "PRD" in md and "source understanding v" in md
        assert "摇杆" in md or "排行榜" in md or "飞机大战" in md

    def test_prd_not_allowed_without_understanding(self, root: str,
                                                   conv_svc) -> None:
        c = conv_svc.create(title="空会话")
        with pytest.raises(ValueError):
            fmt.create_prd(root, c["id"], actor="test")

    def test_approved_prd_immutable_inline(self, root: str,
                                           conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=NL_SEQUENCE)
        prd = fmt.create_prd(root, c["id"], actor="test")
        fmt.approve_prd(root, c["id"], prd["id"], actor="test")
        with pytest.raises(ValueError):
            fmt.update_prd(root, c["id"], prd["id"], actor="test")


# ---------------------------------------------------------------- Adaptive (P1)

class TestAdaptiveClarification:
    def test_gap_detection_adaptive_not_fixed_rounds(self, root: str,
                                                     conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        # 只有 idea → 缺 platform/decision, 但不应机械问 problem/user/core_features
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["我想做一个飞机大战小游戏。"])
        gaps = pu_svc.sufficiency_gaps(c["id"])
        assert gaps  # 仍有缺失
        combined = " ".join(gaps)
        assert "问题" not in combined or "核心功能" not in combined  # 非固定问卷

    def test_question_answered_once_not_repeated(self, root: str,
                                                 conv_svc, pu_svc) -> None:
        c = conv_svc.create(title="飞机大战")
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["我想做一个飞机大战小游戏。"])
        q1 = pu_svc.adaptive_question(c["id"])
        assert q1
        # 用户回答平台 → 该问题不再重复
        _run_nl(pus=pu_svc, conv_id=c["id"], lines=["手机端。"])
        q2 = pu_svc.adaptive_question(c["id"], asked=[q1])
        assert q2 != q1 or not q2  # 不再问同一问题
