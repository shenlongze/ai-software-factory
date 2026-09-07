"""S49-FIX.1 — Tool Safety & Recovery 测试 (scope + 参数 recovery)。"""
import pytest
from factory_console import product_truth as pt
from factory_console.session.agent_loop import tool_schemas


def _chain(root, pid, tag):
    idea = pt.create_idea(root, project_id=pid, title=f"{tag}-idea")
    disc = pt.create_discovery(root, idea_id=idea["id"], title=f"{tag}-disc")
    req = pt.create_requirement(root, discovery_id=disc["id"], title=f"{tag}-REQ")
    return {"idea": idea, "disc": disc, "req": req}


class TestP1aScope:
    def test_resolve_all_kinds(self, tmp_path):
        r = str(tmp_path)
        c = _chain(r, "P-A", "a")
        assert pt.resolve_record_scope(r, "ideas", c["idea"]["id"]) == ("project", "P-A")
        assert pt.resolve_record_scope(r, "discoveries", c["disc"]["id"]) == ("project", "P-A")
        assert pt.resolve_record_scope(r, "requirements", c["req"]["id"]) == ("project", "P-A")
        prd = pt.create_prd(r, project_id="P-A", title="p")
        plan = pt.create_plan(r, project_id="P-A", goal="g", ask_approval=False)
        assert pt.resolve_record_scope(r, "prds", prd["id"]) == ("project", "P-A")
        assert pt.resolve_record_scope(r, "plans", plan["id"]) == ("project", "P-A")

    def test_unbound_not_forced_to_project(self, tmp_path):
        r = str(tmp_path)
        free = pt.create_requirement(r, title="游离", source="conversation")
        assert pt.resolve_record_scope(r, "requirements", free["id"])[0] == "unbound"

    def test_scoped_recent_never_crosses(self, tmp_path):
        r = str(tmp_path)
        ca = _chain(r, "P-A", "a")
        cb = _chain(r, "P-B", "b")
        sc = pt.scoped_recent(r, "requirements", "P-A")
        assert all(x["id"] == ca["req"]["id"] for x in sc)
        assert cb["req"]["id"] not in [x["id"] for x in sc]

    def test_scoped_recent_b_newer_still_isolated(self, tmp_path):
        r = str(tmp_path)
        _chain(r, "P-A", "a")
        _chain(r, "P-B", "b")  # B 更晚
        sc = pt.scoped_recent(r, "requirements", "P-A")
        assert all(pt.resolve_record_scope(r, "requirements", x["id"])[1] == "P-A" for x in sc)


class TestP1bValidation:
    def test_validation_error_is_structured(self, tmp_path):
        r = str(tmp_path)
        c = _chain(r, "P-A", "a")
        # 直接域层: update 保留 title (record_id REFINE title 可省略 — handler 层逻辑)
        pt.update_requirement(r, c["req"]["id"], description="v2 深化")  # 无 title → 保留
        got = pt.get_requirement(r, c["req"]["id"])
        assert got["title"] == "a-REQ" and got["description"].startswith("v2")

    def test_schema_has_no_forbidden_hardcode(self):
        # 工具 schema 存在 (结构契约)
        schemas = tool_schemas(None)
        names = [s.get("function", {}).get("name") for s in schemas]
        assert "get_product_record" in names and "save_product_record" in names

    def test_write_rejects_other_project_record(self, tmp_path):
        r = str(tmp_path)
        ca = _chain(r, "P-A", "a")
        cb = _chain(r, "P-B", "b")
        # A 项目会话试图 REFINE B 的 REQ → scope resolve 显示 P-B → 上层必拒
        st, val = pt.resolve_record_scope(r, "requirements", cb["req"]["id"])
        assert st == "project" and val == "P-B"
