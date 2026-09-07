"""Cognitive Golden Path — Phase 4/5: PRD→Approval→Development Plan→Production Gate。

验证 Golden Path §16-§20:
- Understanding → PRD (structured, versioned, provenance)
- PRD generated ≠ PRD approved (approval gate)
- Approved PRD → Development Plan (provenance: prd_id/prd_version)
- Plan approval gate
- Production Gate: 无 approved PRD/Plan → 拒绝执行 (RED-2 修复)
- Approved Plan → production_runtime (复用现有, 不建第二套)
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
from factory_console import product_truth as pt  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402
from factory_console.testing_semantic_interp import nlp_semantic_interp  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return ca.ConversationApplicationService(root).create(title="飞机大战")


@pytest.fixture()
def svc(root: str):
    return ca.ProductUnderstandingService(root, interpreter=nlp_semantic_interp)


def _build_understanding(root: str, conv_id: str,
                         svc: ca.ProductUnderstandingService) -> None:
    """填充产品理解 (自然语言, 与 Golden Path E2E 相同入口)。"""
    svc.process_user_message(conv_id, "我想做一个飞机大战小游戏。")
    svc.process_user_message(conv_id, "手机端。")
    svc.process_user_message(conv_id, "不要登录, 打开就能玩。")
    svc.process_user_message(conv_id, "操作就用虚拟摇杆吧。")


class TestPrdGeneration:
    def test_prd_derived_from_understanding(self, root: str, conv: dict,
                                            svc) -> None:
        _build_understanding(root, conv["id"], svc)
        v0 = pu.understanding_version(root, conv["id"])
        prd = gp.generate_prd(root, conv["id"])
        assert prd["status"] == "draft"
        assert prd["version"] == 1
        assert prd["source_product_understanding_version"] == v0  # provenance
        content = prd["content"]
        assert "飞机大战" in str(content["overview"])
        assert any("手机端" in str(x) for x in content["functional_requirements"]
                   + content["constraints"] + [content["overview"].get("platform", "")])

    def test_prd_empty_understanding_rejected(self, root: str,
                                              conv: dict) -> None:
        with pytest.raises(ValueError):
            gp.generate_prd(root, conv["id"])

    def test_prd_regeneration_bumps_version(self, root: str, conv: dict,
                                            svc) -> None:
        """修改理解后重生成 → PRD v2 (从最新 Understanding 派生, 非重来)。"""
        _build_understanding(root, conv["id"], svc)
        gp.generate_prd(root, conv["id"])
        # 用户加一个需求 → understanding version 前进
        svc.process_user_message(conv["id"], "需要支持暂停功能。")
        prd2 = gp.generate_prd(root, conv["id"])
        assert prd2["version"] == 2
        assert prd2["source_product_understanding_version"] > 1


class TestPrdApprovalGate:
    def test_approve_draft_prd(self, root: str, conv: dict, svc) -> None:
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        approved = gp.approve_prd(root, conv["id"], prd["id"])
        assert approved["status"] == "approved"

    def test_approve_missing_prd_rejected(self, root: str, conv: dict) -> None:
        with pytest.raises(gp.GoldenPathError):
            gp.approve_prd(root, conv["id"], "PRD-nope")

    def test_generated_not_approved_is_distinct(self, root: str, conv: dict,
                                                svc) -> None:
        """PRD generated ≠ PRD approved (Golden Path §18)。"""
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        assert prd["status"] == "draft"  # 生成 ≠ 批准
        st = gp.path_status(root, conv["id"])
        assert st["approved_prd"] is None  # 未确认不产生 approved


class TestPlanGeneration:
    def test_plan_requires_approved_prd(self, root: str, conv: dict,
                                        svc) -> None:
        """PRD 未确认 → 不能生成 Plan (Golden Path §19)。"""
        _build_understanding(root, conv["id"], svc)
        gp.generate_prd(root, conv["id"])
        with pytest.raises(gp.GoldenPathError):
            gp.generate_plan(root, conv["id"])

    def test_plan_from_approved_prd_has_provenance(self, root: str,
                                                   conv: dict,
                                                   svc) -> None:
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        plan = gp.generate_plan(root, conv["id"])
        assert plan["status"] == "pending"
        assert plan["prd_id"] == prd["id"]
        assert plan["prd_version"] == prd["version"]
        assert plan["goal"]
        assert plan["tasks"]  # 从 PRD content 派生
        # Plan 在 product_truth 正式域 (非第二套)
        assert pt.get_plan(root, plan["id"])["id"] == plan["id"]


class TestPlanApproval:
    def test_approve_plan(self, root: str, conv: dict, svc) -> None:
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        plan = gp.generate_plan(root, conv["id"])
        ap = gp.approve_plan(root, plan["id"])
        assert ap["status"] == "approved"

    def test_approve_non_pending_plan_rejected(self, root: str, conv: dict,
                                               svc) -> None:
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        plan = gp.generate_plan(root, conv["id"])
        gp.approve_plan(root, plan["id"])
        with pytest.raises(gp.GoldenPathError):
            gp.approve_plan(root, plan["id"])  # 已 approved → 拒绝


class TestProductionGate:
    def test_no_approved_prd_blocks_production(self, root: str, conv: dict,
                                               svc) -> None:
        """RED-2 修复: 未确认 PRD → 拒绝进生产。"""
        _build_understanding(root, conv["id"], svc)
        with pytest.raises(gp.GoldenPathError) as exc:
            gp.execute_approved(root, conv["id"])
        assert "Production Gate" in str(exc.value)

    def test_approved_prd_but_no_plan_blocks(self, root: str, conv: dict,
                                             svc) -> None:
        """PRD 确认但 Plan 未确认 → 拒绝进生产。"""
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        with pytest.raises(gp.GoldenPathError) as exc:
            gp.execute_approved(root, conv["id"])
        assert "Development Plan" in str(exc.value)

    def test_approved_plan_then_execute(self, root: str, conv: dict,
                                        svc) -> None:
        """全门通过 → 进 production_runtime (复用现有执行核)。"""
        calls: list[dict] = []

        def _cap(input_data: dict) -> dict:
            calls.append(input_data)
            return {"ok": True, "output": "delivered"}

        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        plan = gp.generate_plan(root, conv["id"])
        gp.approve_plan(root, plan["id"])
        out = gp.execute_approved(root, conv["id"], capability_fn=_cap)
        assert out["prd_id"] == prd["id"]
        assert out["plan_id"] == plan["id"]
        assert out["executed"]
        # 每个 task 都经 production_runtime (capability_fn 被调)
        assert len(calls) == len(plan["tasks"])

    def test_path_status_visibility(self, root: str, conv: dict,
                                    svc) -> None:
        """path_status: 各阶段可见 (UI/CLI Truth 断言)。"""
        st0 = gp.path_status(root, conv["id"])
        assert st0["understanding_version"] == 0 and st0["prd_count"] == 0
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        gp.generate_plan(root, conv["id"])
        st = gp.path_status(root, conv["id"])
        assert st["approved_prd"]["id"] == prd["id"]
        assert st["understanding_version"] > 0


class TestNoSecondTruth:
    def test_plan_lives_in_product_truth_not_conversation(self, root: str,
                                                          conv: dict,
                                                          svc) -> None:
        """Plan 只存 product_truth/plans.json (正式域), conversation 无第二份。"""
        _build_understanding(root, conv["id"], svc)
        prd = gp.generate_prd(root, conv["id"])
        gp.approve_prd(root, conv["id"], prd["id"])
        plan = gp.generate_plan(root, conv["id"])
        # conversation 文档里不应有 plans 字段 (PRD 在 conversation 内嵌, Plan 在 truth 域)
        doc = pu._load_conv(root, conv["id"])  # noqa: SLF001 — 测试读
        assert "plans" not in doc or not doc.get("plans")
        # product_truth 有且仅一份
        assert pt.get_plan(root, plan["id"])["id"] == plan["id"]
