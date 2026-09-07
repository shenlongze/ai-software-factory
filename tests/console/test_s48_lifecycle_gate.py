"""S48-FIX — Lifecycle Gate + enforcement 测试。"""
import pytest
from factory_console import product_truth as pt


class TestLifecycleGate:
    def test_req_first_create_allowed(self, tmp_path):
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "requirement")
        assert g["allowed"] is True and g["action"] == "CREATE"

    def test_req_free_dup_denied_refine(self, tmp_path):
        pt.create_requirement(str(tmp_path), title="r1", source="conversation")
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "requirement")
        assert g["allowed"] is False and g["action"] == "REFINE"
        assert g["target_kind"] == "requirement" and g["target_id"]

    def test_prd_dup_denied(self, tmp_path):
        pt.create_prd(str(tmp_path), project_id="P-1", title="p")
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "prd")
        assert g["allowed"] is False and g["action"] == "REFINE"

    def test_prd_first_allowed(self, tmp_path):
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "prd")
        assert g["allowed"] is True

    def test_disc_requires_idea(self, tmp_path):
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "discovery")
        assert g["allowed"] is False and g["action"] == "ADVANCE"

    def test_disc_dup_running_denied(self, tmp_path):
        idea = pt.create_idea(str(tmp_path), project_id="P-1", title="i")
        pt.create_discovery(str(tmp_path), idea_id=idea["id"], title="d")
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "discovery", idea_id=idea["id"])
        assert g["allowed"] is False and g["action"] == "REFINE"

    def test_idea_allowed(self, tmp_path):
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "idea")
        assert g["allowed"] is True

    def test_refine_after_gate_denied_updates_same_id(self, tmp_path):
        """DENIED 后走 record_id REFINE → 同一记录更新, 不产生第二条。"""
        r1 = pt.create_requirement(str(tmp_path), title="r1", description="v1",
                                   source="conversation")
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "requirement")
        assert g["target_id"] == r1["id"]
        pt.update_requirement(str(tmp_path), r1["id"], description="v2")
        recs = pt.list_requirements(str(tmp_path))
        assert len(recs) == 1 and recs[0]["description"].startswith("v2")


class TestGateSinceWindow:
    def test_historical_free_req_not_blocking(self, tmp_path):
        from factory_console import product_truth as pt
        pt.create_requirement(str(tmp_path), title="历史游离", source="conversation")
        # 会话起始时间晚于历史记录 (未来窗口) → 放行 (历史不误伤新项目)
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "requirement",
                              since="2099-01-01T00:00:00")
        assert g["allowed"] is True

    def test_session_window_req_blocking(self, tmp_path):
        import datetime
        from factory_console import product_truth as pt
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rec = pt.create_requirement(str(tmp_path), title="会话内", source="conversation")
        g = pt.lifecycle_gate(str(tmp_path), "P-1", "requirement", since=start)
        assert g["allowed"] is False and g["action"] == "REFINE"
        assert g["target_id"] == rec["id"]
