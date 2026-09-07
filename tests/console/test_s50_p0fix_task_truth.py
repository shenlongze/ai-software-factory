"""S50-P0-FIX — Task Truth Store Consistency 测试。

核心: create == visible (同一 canonical store, slug 解析一致)。
fixture 直写 org/projects.json (避开 build/lib 双副本 import 混乱)。
"""
import json
import uuid

from factory_console.session.agent_loop import _format_project_entry
from factory_console.web.backend.fastapi_adapter import build_console_service


def _mk(tmp_path, name):
    root = str(tmp_path)
    os_ = __import__("os")
    os_.makedirs(root + "/org", exist_ok=True)
    pid = "P-" + uuid.uuid4().hex[:8]
    f = root + "/org/projects.json"
    d = {"projects": {}}
    if os_.path.isfile(f):
        d = json.load(open(f))
    d["projects"][pid] = {"id": pid, "name": name, "user_id": "u1"}
    json.dump(d, open(f, "w"), ensure_ascii=False)
    return pid


class TestCreateReadConsistency:
    def test_create_visible_in_list_and_status(self, tmp_path):
        root = str(tmp_path)
        svc = build_console_service(root)
        pid = _mk(tmp_path, "番茄钟 FIX")
        c1 = svc.create_task(pid, title="t1", priority="P0", description="d")
        c2 = svc.create_task(pid, title="t2", priority="P1", description="d")
        assert c1 and c2
        bl = svc.list_backlog(pid) or {}
        tasks = bl.get("tasks") or []
        assert len(tasks) == 2, f"create 2 但 list {len(tasks)} — create/read 分叉"
        ids = {str(t.get("id")) for t in tasks}
        assert str(c1.get("id")) in ids and str(c2.get("id")) in ids
        out = _format_project_entry(root, pid, {"name": "番茄钟 FIX"}, service=svc)
        assert "任务: 2 个" in out and "P0: 1" in out

    def test_cross_project_isolation(self, tmp_path):
        root = str(tmp_path)
        svc = build_console_service(root)
        pa = _mk(tmp_path, "项目 A")
        pb = _mk(tmp_path, "项目 B")
        svc.create_task(pa, title="a-task", priority="P0", description="")
        svc.create_task(pb, title="b-task", priority="P1", description="")
        bl_a = (svc.list_backlog(pa) or {}).get("tasks") or []
        assert [t.get("title") for t in bl_a] == ["a-task"]
