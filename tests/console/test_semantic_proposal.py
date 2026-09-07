"""Cognitive Golden Path — Phase 1: Semantic Proposal + Domain Validation 测试。

验证 Golden Path §7/§8 管道:
  User Message → Context Assembly → LLM/Interpreter → Semantic Proposal
  → Domain Validation → Conflict/Supersession Resolution → Product Understanding
  → Persistence

核心断言:
1. validate_proposal 拒绝非法操作 (LLM 幻觉不得直接污染 Truth)
2. validate_proposal 拒绝非法 fact_type/缺 content/越界 confidence
3. apply_operations 是唯一写入口 — 各语义操作 (ADD/UPDATE/NEGATE/DEFER/
   REPLACE/CONFIRM/REJECT/SUGGEST/QUESTION) 产生正确的 Truth mutation
4. CONFIRM 无对象可确认 → 拒绝 (防幻觉确认)
5. NEGATE/DEFER 找不到对象 → 落 REJECTED/DEFERRED 历史 (否定/延后仍被记录)
6. supersession: UPDATE 手机端→网页端 → 旧 SUPERSEDED; DEFERRED 恢复不新增重复
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import product_understanding as pu  # noqa: E402
from factory_console.semantic_proposal import (  # noqa: E402
    ProposalValidationError,
    apply_operations, build_proposal, validate_proposal,
)


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return pu.create_conversation(root, title="飞机大战")


def _run(root: str, conv_id: str, ops: list[dict], *, text: str = "msg") -> list[dict]:
    msg = pu.append_message(root, conv_id, role="human", content=text)
    return apply_operations(root, conv_id, ops, source_message_id=msg["id"])


def _effective_facts(root: str, conv_id: str) -> list[dict]:
    return pu.list_facts(root, conv_id)


def _all_facts(root: str, conv_id: str) -> list[dict]:
    return pu.list_facts(root, conv_id, include_inactive=True)


class TestProposalValidation:
    def test_rejects_unknown_op(self) -> None:
        with pytest.raises(ProposalValidationError):
            build_proposal(operations=[{"op": "DELETE_ALL", "fact_type": "IDEA",
                                         "content": "x"}])

    def test_rejects_unknown_fact_type(self) -> None:
        with pytest.raises(ProposalValidationError):
            build_proposal(operations=[{"op": "ADD", "fact_type": "MAGIC",
                                         "content": "x"}])

    def test_rejects_missing_content(self) -> None:
        with pytest.raises(ProposalValidationError):
            build_proposal(operations=[{"op": "ADD", "fact_type": "IDEA",
                                         "content": "  "}])

    def test_rejects_out_of_range_confidence(self) -> None:
        with pytest.raises(ProposalValidationError):
            build_proposal(operations=[{"op": "ADD", "fact_type": "IDEA",
                                         "content": "x", "confidence": 2.5}])

    def test_accepts_valid_proposal(self) -> None:
        p = build_proposal(
            operations=[{"op": "ADD", "fact_type": "IDEA", "content": "飞机大战"}],
            reply="明白", summary="记录核心想法")
        assert p["operations"][0]["op"] == "ADD"
        assert p["reply"] == "明白"

    def test_clarify_needs_content(self) -> None:
        with pytest.raises(ProposalValidationError):
            build_proposal(operations=[{"op": "CLARIFY"}])


class TestApplyAdd:
    def test_add_idea(self, root: str, conv: dict) -> None:
        r = _run(root, conv["id"], [{"op": "ADD", "fact_type": "IDEA",
                                     "content": "飞机大战小游戏"}])
        assert r[0]["op"] == "ADD"
        facts = _effective_facts(root, conv["id"])
        assert len(facts) == 1
        assert facts[0]["type"] == "IDEA"
        assert facts[0]["provenance"] == "semantic:add"

    def test_add_same_content_no_duplicate(self, root: str, conv: dict) -> None:
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                 "content": "手机端"}])
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                 "content": "手机端"}])
        assert len(_effective_facts(root, conv["id"])) == 1
        assert len(_all_facts(root, conv["id"])) == 1


class TestApplyUpdateReplace:
    def test_update_supersedes_dimension(self, root: str, conv: dict) -> None:
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                 "content": "运行平台: 手机端"}])
        _run(root, conv["id"], [{"op": "UPDATE", "fact_type": "REQUIREMENT",
                                 "content": "运行平台: 网页端"}])
        facts = _effective_facts(root, conv["id"])
        assert len(facts) == 1
        assert "网页端" in facts[0]["content"]
        old = [f for f in _all_facts(root, conv["id"])
               if f["status"] == "SUPERSEDED"]
        assert len(old) == 1 and "手机端" in old[0]["content"]

    def test_replace_input_mechanism(self, root: str, conv: dict) -> None:
        """别用虚拟按键,改成虚拟摇杆 → input mechanism supersession。"""
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "DECISION",
                                 "content": "操作方式: 虚拟按键"}])
        _run(root, conv["id"], [{"op": "REPLACE", "fact_type": "DECISION",
                                 "content": "操作方式: 虚拟摇杆"}])
        facts = _effective_facts(root, conv["id"])
        assert len(facts) == 1 and "摇杆" in facts[0]["content"]


class TestApplyNegateReject:
    def test_reject_no_login(self, root: str, conv: dict) -> None:
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                 "content": "需要登录"}])
        _run(root, conv["id"], [{"op": "NEGATE", "fact_type": "REQUIREMENT",
                                 "content": "需要登录"}])
        assert _effective_facts(root, conv["id"]) == []
        rej = [f for f in _all_facts(root, conv["id"])
               if f["status"] == "REJECTED"]
        assert len(rej) == 1 and "登录" in rej[0]["content"]

    def test_reject_unrecorded_records_history(self, root: str,
                                               conv: dict) -> None:
        """否定未记录的东西 → 落 REJECTED 历史 (不静默忽略)。"""
        _run(root, conv["id"], [{"op": "REJECT", "fact_type": "FUTURE_IDEA",
                                 "content": "排行榜"}])
        rej = [f for f in _all_facts(root, conv["id"])
               if f["status"] == "REJECTED"]
        assert len(rej) == 1 and "排行榜" in rej[0]["content"]
        assert rej[0]["type"] == "FUTURE_IDEA"


class TestApplyDefer:
    def test_defer_existing_requirement(self, root: str, conv: dict) -> None:
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                 "content": "排行榜"}])
        _run(root, conv["id"], [{"op": "DEFER", "fact_type": "REQUIREMENT",
                                 "content": "排行榜"}])
        assert _effective_facts(root, conv["id"]) == []
        snap = pu.understanding_snapshot(root, conv["id"])
        assert len(snap["deferred"]) == 1 and "排行榜" in snap["deferred"][0]["content"]

    def test_defer_unrecorded_becomes_deferred_future(self, root: str,
                                                      conv: dict) -> None:
        _run(root, conv["id"], [{"op": "DEFER", "fact_type": "REQUIREMENT",
                                 "content": "多人在线"}])
        snap = pu.understanding_snapshot(root, conv["id"])
        assert len(snap["deferred"]) == 1
        assert snap["deferred"][0]["type"] == "FUTURE_IDEA"

    def test_deferred_reactivated_no_duplicate(self, root: str,
                                               conv: dict) -> None:
        """排行榜先别做 → DEFERRED; 排行榜还是做 → 恢复, 不新增冲突重复。"""
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "FUTURE_IDEA",
                                 "content": "排行榜"}])
        _run(root, conv["id"], [{"op": "DEFER", "fact_type": "FUTURE_IDEA",
                                 "content": "排行榜"}])
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "FUTURE_IDEA",
                                 "content": "排行榜"}])
        facts = _effective_facts(root, conv["id"])
        assert len(facts) == 1 and "排行榜" in facts[0]["content"]
        # 历史: 一条 DEFERRED (被新 fact supersede), 一条 effective — 无重复冲突
        assert len(_all_facts(root, conv["id"])) == 2


class TestApplyConfirm:
    def test_confirm_existing(self, root: str, conv: dict) -> None:
        f = _run(root, conv["id"], [{"op": "ADD", "fact_type": "REQUIREMENT",
                                     "content": "手机端"}])[0]["fact"]
        r = _run(root, conv["id"], [{"op": "CONFIRM", "fact_type": "REQUIREMENT",
                                     "content": "手机端"}])
        got = pu.get_fact(root, conv["id"], r[0]["fact"]["id"])
        assert got["status"] == "CONFIRMED"

    def test_confirm_without_target_rejected(self, root: str,
                                             conv: dict) -> None:
        """CONFIRM 无对象可确认 → 拒绝幻觉确认 (LLM 不得凭空确认)。"""
        with pytest.raises(ProposalValidationError):
            _run(root, conv["id"], [{"op": "CONFIRM", "fact_type": "DECISION",
                                     "content": "虚拟摇杆"}])


class TestApplyQuestion:
    def test_question_records_fact(self, root: str, conv: dict) -> None:
        r = _run(root, conv["id"], [{"op": "QUESTION", "fact_type": "QUESTION",
                                     "content": "横屏还是竖屏?"}])
        assert r[0]["op"] == "QUESTION"
        facts = [f for f in _effective_facts(root, conv["id"])
                 if f["type"] == "QUESTION"]
        assert len(facts) == 1


class TestEmptyOperations:
    def test_empty_ops_returns_empty(self, root: str, conv: dict) -> None:
        assert _run(root, conv["id"], []) == []
        assert _effective_facts(root, conv["id"]) == []


class TestVersionBumps:
    def test_mutation_bumps_understanding_version(self, root: str,
                                                  conv: dict) -> None:
        v0 = pu.understanding_version(root, conv["id"])
        _run(root, conv["id"], [{"op": "ADD", "fact_type": "IDEA",
                                 "content": "记账App"}])
        _run(root, conv["id"], [{"op": "DEFER", "fact_type": "REQUIREMENT",
                                 "content": "多人在线"}])
        assert pu.understanding_version(root, conv["id"]) > v0 + 1
