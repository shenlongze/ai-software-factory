"""S47-E4 — Truth Retrieval + Refinement 测试 (LLM mock 真实形状)。"""
import pytest
from factory_console.session.agent_loop import _governance_guide
from factory_console import product_truth as pt


class TestRefinementSemantics:
    def test_refinement_guide_reads_and_deepens(self):
        g = _governance_guide("refinement", "product_lifecycle", True,
                              {"topic": "需求分析"}, "太模糊了")
        assert "产出深化" in g and "get_product_record" in g and "save_product_record" in g
        assert "不要解释现状" in g

    def test_complaint_still_recovery(self):
        g = _governance_guide("complaint", "conversation", False, {}, "你怎么又跑题了")
        assert "对话恢复" in g and "不要调用项目诊断工具" in g


class TestTruthReadWrite:
    def test_update_requirement_same_id(self, tmp_path):
        rec = pt.create_requirement(str(tmp_path), title="t", description="v1")
        rid = rec["id"]
        pt.update_requirement(str(tmp_path), rid, description="v2 深化内容")
        got = pt.get_requirement(str(tmp_path), rid)
        assert got["id"] == rid and got["description"].startswith("v2")

    def test_update_rejects_validated(self, tmp_path):
        rec = pt.create_requirement(str(tmp_path), title="t", description="v1")
        rid = rec["id"]
        pt.transition_requirement(str(tmp_path), rid, "validated")
        with pytest.raises(ValueError):
            pt.update_requirement(str(tmp_path), rid, description="不可改")

    def test_update_missing_raises(self, tmp_path):
        with pytest.raises(KeyError):
            pt.update_requirement(str(tmp_path), "REQ-nope", description="x")

    def test_getters_present(self):
        for fn in (pt.get_requirement, pt.get_discovery, pt.get_prd, pt.get_plan,
                   pt.list_requirements):
            assert callable(fn)
