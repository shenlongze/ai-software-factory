"""MU-CORE-06: Work / Workstream OS Core SSOT。

验收: SSOT(create/reload/get/list/update/lifecycle) · ID 契约 · Project 引用 · Company 隔离
      Workstream 属于 Work · 语义边界(不产生 Task 层) · Identity owner 引用
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-org"),
           str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from factory_console import os_core_company_organization as osco  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import os_core_work as work  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402


def _chain(root: str, company_name: str = "Acme") -> dict:
    company = osco.create_company(root, name=company_name)
    project = proj.create_project(root, name=f"{company_name} Project",
                                  company_id=company["id"])
    return {"company": company, "project": project}


# ---------------------------------------------------------------- SSOT

def test_work_crud_lifecycle_persist(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _chain(root)
    w = work.create_work(root, project_id=ctx["project"]["id"], name="产品设计",
                         work_type="design")
    assert w["work_id"].startswith("W-") and w["status"] == "draft"
    assert (tmp_path / "work" / "work.json").is_file()          # persistence
    assert work.get_work(root, w["work_id"])["name"] == "产品设计"
    assert [x["work_id"] for x in work.list_works(root, project_id=ctx["project"]["id"])] == [w["work_id"]]

    work.set_work_status(root, w["work_id"], "active")
    assert work.get_work(root, w["work_id"])["status"] == "active"
    work.set_work_status(root, w["work_id"], "completed")
    work.set_work_status(root, w["work_id"], "archived")
    assert work.get_work(root, w["work_id"])["status"] == "archived"
    work.update_work(root, w["work_id"], description="done")
    assert work.get_work(root, w["work_id"])["description"] == "done"


def test_work_id_contract(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _chain(root)
    a = work.create_work(root, project_id=ctx["project"]["id"], name="A")
    b = work.create_work(root, project_id=ctx["project"]["id"], name="B")
    assert a["work_id"] != b["work_id"]                          # unique
    assert work.get_work(root, a["work_id"])["work_id"] == a["work_id"]   # stable reload
    # 语义边界: work_id 不得是 project/conversation id, 也不得由它们派生
    conv = pu.create_conversation(root, title="C")["id"]
    assert a["work_id"] != ctx["project"]["id"]
    assert a["work_id"] != conv
    assert not a["work_id"].startswith("P-") and not a["work_id"].startswith("conv-")


def test_work_requires_real_project(tmp_path: Path) -> None:
    root = str(tmp_path)
    with pytest.raises(ValueError):
        work.create_work(root, project_id="P-nope", name="X")
    ctx = _chain(root)
    w = work.create_work(root, project_id=ctx["project"]["id"], name="X")
    assert w["project_id"] == ctx["project"]["id"]


def test_company_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    ca = osco.create_company(root, name="Company A")
    cb = osco.create_company(root, name="Company B")
    pa = proj.create_project(root, name="P-A", company_id=ca["id"])
    pb = proj.create_project(root, name="P-B", company_id=cb["id"])
    wa = work.create_work(root, project_id=pa["id"], name="W-A")
    work.create_work(root, project_id=pb["id"], name="W-B")
    assert [w["work_id"] for w in work.list_works(root, project_id=pa["id"])] == [wa["work_id"]]
    assert all(w["work_id"] != wa["work_id"] for w in work.list_works(root, project_id=pb["id"]))
    # resolve 链: Work -> Project -> Company
    resolved = work.resolve_work(root, wa["work_id"])
    assert resolved["project"]["id"] == pa["id"]
    assert resolved["project"]["company_id"] == ca["id"]


# ---------------------------------------------------------------- Workstream

def test_workstream_belongs_to_work(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _chain(root)
    w = work.create_work(root, project_id=ctx["project"]["id"], name="游戏核心开发")
    s1 = work.create_workstream(root, work_id=w["work_id"], name="前端")
    s2 = work.create_workstream(root, work_id=w["work_id"], name="后端")
    assert s1["workstream_id"].startswith("WS-")
    assert s1["workstream_id"] != s2["workstream_id"]
    assert s1["work_id"] == w["work_id"]
    assert [x["workstream_id"] for x in work.list_workstreams(root, work_id=w["work_id"])] == [
        s1["workstream_id"], s2["workstream_id"]]
    r = work.resolve_workstream(root, s1["workstream_id"])
    assert r["work"]["work_id"] == w["work_id"]
    assert r["project"]["id"] == ctx["project"]["id"]
    work.set_workstream_status(root, s1["workstream_id"], "active")
    assert work.get_workstream(root, s1["workstream_id"])["status"] == "active"


def test_workstream_requires_work_and_no_renaming(tmp_path: Path) -> None:
    root = str(tmp_path)
    with pytest.raises(ValueError):
        work.create_workstream(root, work_id="W-nope", name="X")
    ctx = _chain(root)
    w = work.create_work(root, project_id=ctx["project"]["id"], name="W")
    s = work.create_workstream(root, work_id=w["work_id"], name="WS")
    # 语义边界: workstream 不得变成 Project / Task / Sprint
    assert s["workstream_id"] != ctx["project"]["id"]
    assert not s["workstream_id"].startswith("P-")
    assert not s["workstream_id"].startswith("TASK")
    assert not s["workstream_id"].startswith("sprint")


# ---------------------------------------------------------------- Identity owner + 边界

def test_owner_identity_reference(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _chain(root)
    human = ident.create_identity(root, identity_type="human",
                                  company_id=ctx["company"]["id"], display_name="Alice")
    w = work.create_work(root, project_id=ctx["project"]["id"], name="W",
                         owner_identity_id=human["identity_id"])
    assert w["owner_identity_id"] == human["identity_id"]
    with pytest.raises(ValueError):
        work.create_work(root, project_id=ctx["project"]["id"], name="Bad",
                         owner_identity_id="I-nope")


def test_no_task_layer_created(tmp_path: Path) -> None:
    root = str(tmp_path)
    ctx = _chain(root)
    w = work.create_work(root, project_id=ctx["project"]["id"], name="W")
    work.create_workstream(root, work_id=w["work_id"], name="WS")
    # 本 MU 不实现 Task/TaskNode/Execution: 不得产生对应 store
    assert not (tmp_path / "task").exists()
    assert not (tmp_path / "tasks").exists()
    assert not (tmp_path / "nodes").exists()
