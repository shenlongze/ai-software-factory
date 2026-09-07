"""S47-E5 — Canonical Product Chain Continuity 测试 (全域契约)。"""
import pytest
from factory_console import product_truth as pt


class TestFullChain:
    def test_idea_to_plan_chain(self, tmp_path):
        r = str(tmp_path)
        idea = pt.create_idea(r, project_id="P-1", title="飞机大战", description="v0")
        iid = idea["id"]
        pt.update_idea(r, iid, description="v1 深化")           # Refine idea
        assert pt.get_idea(r, iid)["description"].startswith("v1")
        pt.transition_idea(r, iid, "validated")                  # Continue idea
        disc = pt.create_discovery(r, idea_id=iid, title="需求理解")
        did = disc["id"]
        pt.update_discovery(r, did, input_ref="JS+HTML+CSS+Three.js")
        assert "Three.js" in pt.get_discovery(r, did)["input_ref"]
        pt.transition_discovery(r, did, "completed")
        req = pt.create_requirement(r, discovery_id=did, title="需求清单", description="d")
        rid = req["id"]
        pt.update_requirement(r, rid, description="d2")
        pt.transition_requirement(r, rid, "validated")
        prd = pt.create_prd(r, project_id="P-1", title="PRD", requirement_ids=[rid])
        pid = prd["id"]
        pt.update_prd_content(r, pid, "方案 v1 body")
        pt.update_prd_content(r, pid, "方案 v2 深化 body")        # PRD 版本化 Refine
        prd2 = pt.get_prd(r, pid)
        assert prd2["current_version"] == 3  # v1 初始 + v2 body + v3 深化
        assert "深化" in prd2["versions"][-1]["content"]["body"]
        pt.transition_prd(r, pid, "approved")
        plan = pt.create_plan(r, project_id="P-1", prd_id=pid,
                              goal="开发飞机大战", tasks=[{"title": "t1"}],
                              ask_approval=False)
        pt.transition_plan(r, plan["id"], "approved")
        pl = pt.get_plan(r, plan["id"])
        assert pl["status"] == "approved" and pl["project_id"] == "P-1"
        # 项目归属
        assert pt.get_idea(r, iid)["project_id"] == "P-1"
        assert pt.get_prd(r, pid)["project_id"] == "P-1"

    def test_update_rejects_approved(self, tmp_path):
        r = str(tmp_path)
        req = pt.create_requirement(r, title="t", description="d")
        pt.transition_requirement(r, req["id"], "validated")
        with pytest.raises(ValueError):
            pt.update_requirement(r, req["id"], description="不可改")
        prd = pt.create_prd(r, project_id="P-1", title="p")
        pt.transition_prd(r, prd["id"], "approved")
        with pytest.raises(ValueError):
            pt.update_prd_content(r, prd["id"], "不可改")

    def test_new_writers_exposed(self):
        for fn in (pt.update_idea, pt.update_discovery, pt.transition_discovery,
                   pt.transition_prd, pt.transition_plan, pt.update_prd_content):
            assert callable(fn)

    def test_tool_schema_covers_all_kinds(self):
        from factory_console.session.agent_loop import tool_schemas
        schemas = tool_schemas(None)
        spr = next(s for s in schemas
                   if s.get("function", {}).get("name") == "save_product_record")
        enum = spr["function"]["parameters"]["properties"]["kind"]["enum"]
        assert {"idea", "discovery", "requirement", "prd"}.issubset(set(enum))
        gpr = next(s for s in schemas
                   if s.get("function", {}).get("name") == "get_product_record")
        enum2 = gpr["function"]["parameters"]["properties"]["kind"]["enum"]
        assert {"idea", "discovery", "requirement", "prd", "plan"}.issubset(set(enum2))
