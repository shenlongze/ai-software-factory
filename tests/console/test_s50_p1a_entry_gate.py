"""S50-P1A — Production Entry Gate 测试。"""
import json
import uuid

from factory_console import product_truth as pt
from factory_console.session.agent_loop import _production_entry_gate
from factory_console.web.backend.fastapi_adapter import build_console_service


def _mkproj(tmp_path, name="番茄钟"):
    root = str(tmp_path)
    import os
    os.makedirs(root + "/org", exist_ok=True)
    pid = "P-" + uuid.uuid4().hex[:8]
    f = root + "/org/projects.json"
    d = {"projects": {}}
    if os.path.isfile(f):
        d = json.load(open(f))
    d["projects"][pid] = {"id": pid, "name": name, "user_id": "u1"}
    json.dump(d, open(f, "w"), ensure_ascii=False)
    return pid


class TestProductionEntryGate:
    def test_blocked_without_plan(self, tmp_path):
        root = str(tmp_path)
        pid = _mkproj(tmp_path)
        g = _production_entry_gate(root, pid, {})
        assert g["allowed"] is False and g["required_next"] == "PLAN"

    def test_blocked_with_only_req(self, tmp_path):
        root = str(tmp_path)
        pid = _mkproj(tmp_path)
        idea = pt.create_idea(root, project_id=pid, title="i")
        disc = pt.create_discovery(root, idea_id=idea["id"], title="d")
        pt.create_requirement(root, discovery_id=disc["id"], title="req")
        g = _production_entry_gate(root, pid, {})
        assert g["allowed"] is False  # REQ 已建但无 PLAN → 仍禁止 TASK

    def test_allowed_with_approved_plan(self, tmp_path):
        root = str(tmp_path)
        pid = _mkproj(tmp_path)
        plan = pt.create_plan(root, project_id=pid, goal="g", ask_approval=False)
        pt.transition_plan(root, plan["id"], "approved")
        g = _production_entry_gate(root, pid, {})
        assert g["allowed"] is True and g.get("plan_id") == plan["id"]

    def test_create_task_denied_until_plan(self, tmp_path):
        """Case C: IDEA 阶段直接 create_task → DENIED 且任务数不变。"""
        root = str(tmp_path)
        svc = build_console_service(root)
        pid = _mkproj(tmp_path)
        from factory_console.session.agent_loop import dispatch
        r = dispatch("create_task", {"title": "偷跑任务"},
                     root=root, project_id=pid, service=svc, ctx={"session_id": "s1"})
        assert r.get("ok") is False and (r.get("blocked") or r.get("governance"))
        bl = (svc.list_backlog(pid) or {}).get("tasks") or []
        assert len(bl) == 0  # 无副作用

    def test_create_task_allowed_after_plan(self, tmp_path):
        root = str(tmp_path)
        svc = build_console_service(root)
        pid = _mkproj(tmp_path)
        plan = pt.create_plan(root, project_id=pid, goal="g", tasks=[{"title": "t1"}],
                              ask_approval=False)
        pt.transition_plan(root, plan["id"], "approved")
        from factory_console.session.agent_loop import dispatch
        r = dispatch("create_task", {"title": "合法任务"},
                     root=root, project_id=pid, service=svc, ctx={"session_id": "s2"})
        assert r.get("ok") is True
