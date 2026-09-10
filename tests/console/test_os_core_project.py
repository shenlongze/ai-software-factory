"""MU-CORE-05: Project SSOT（OS Core Work Anchor）。

验收 (MU-CORE-05 §二十):
1 Project SSOT · 2 stable ID · 3 Company isolation · 4 persistence/reload · 5 lifecycle
6 Conversation↔Project reference · 7 conv_id ≠ project_id · 8 无第二 store
9 Company 校验 · 10 project_agile 投影 · 11 Web smoke
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
from factory_console import os_core_project as proj  # noqa: E402
from factory_console import product_understanding as pu  # noqa: E402


def _company(root: str, name: str = "Acme") -> str:
    return osco.create_company(root, name=name)["id"]


# ---------------------------------------------------------------- 1-5 SSOT / ID / isolation / lifecycle

def test_project_ssot_create_get_persist(tmp_path: Path) -> None:
    root = str(tmp_path)
    cid = _company(root)
    p = proj.create_project(root, name="Plane Game", company_id=cid, goal="ship it")
    assert p["id"].startswith("P-")                       # stable OS project id
    assert p["company_id"] == cid
    assert (tmp_path / "org" / "projects.json").is_file()  # SSOT = org store
    assert proj.get_project(root, p["id"])["name"] == "Plane Game"
    assert proj.OS_PROJECT_SSOT == "factory-org/org/projects.py"


def test_project_id_stable_and_unique(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = proj.create_project(root, name="A")
    b = proj.create_project(root, name="B")
    assert a["id"] != b["id"]
    assert proj.get_project(root, a["id"])["id"] == a["id"]   # reload 后 id 稳定


def test_company_isolation(tmp_path: Path) -> None:
    root = str(tmp_path)
    ca = _company(root, "Company A")
    cb = _company(root, "Company B")
    pa = proj.create_project(root, name="P-A", company_id=ca)
    proj.create_project(root, name="P-B", company_id=cb)
    listed = proj.list_projects(root, company_id=ca)
    assert [x["id"] for x in listed] == [pa["id"]]            # 不返回 P-B
    assert len(proj.list_projects(root)) == 2


def test_project_lifecycle(tmp_path: Path) -> None:
    root = str(tmp_path)
    p = proj.create_project(root, name="Lifecycle")
    assert p["lifecycle"] == "idea"
    moved = proj.set_project_lifecycle(root, p["id"], "confirmed")
    assert moved["lifecycle"] == "confirmed"
    with pytest.raises(Exception):        # 单向无环: confirmed -> idea 非法
        proj.set_project_lifecycle(root, p["id"], "idea")


def test_company_validation(tmp_path: Path) -> None:
    root = str(tmp_path)
    with pytest.raises(ValueError):
        proj.create_project(root, name="X", company_id="C-nope")
    p = proj.create_project(root, name="X")
    with pytest.raises(ValueError):
        proj.set_project_company(root, p["id"], "C-nope")


# ---------------------------------------------------------------- 6-8 Conversation reference

def test_conversation_reference_not_identity(tmp_path: Path) -> None:
    root = str(tmp_path)
    p = proj.create_project(root, name="Plane Game")
    c1 = pu.create_conversation(root, title="C1")["id"]
    c2 = pu.create_conversation(root, title="C2")["id"]
    proj.link_conversation(root, p["id"], c1)
    proj.link_conversation(root, p["id"], c2)

    d1 = pu._load_conv(root, c1)
    d2 = pu._load_conv(root, c2)
    assert d1["project_id"] == p["id"] and d2["project_id"] == p["id"]
    # P0: conv_id 脱钩 (两个 conversation 引用同一 project, 且 conv_id != project_id)
    assert c1 != p["id"] and c2 != p["id"] and c1 != c2
    assert proj.resolve_project_for_conversation(root, c1)["id"] == p["id"]
    convs = proj.conversations_for_project(root, p["id"])
    assert {c["conversation_id"] for c in convs} == {c1, c2}


def test_link_unknown_project_or_conversation(tmp_path: Path) -> None:
    root = str(tmp_path)
    c1 = pu.create_conversation(root, title="C1")["id"]
    with pytest.raises(ValueError):
        proj.link_conversation(root, "P-nope", c1)
    p = proj.create_project(root, name="P")
    with pytest.raises(ValueError):
        proj.link_conversation(root, p["id"], "conv-nope")


def test_no_second_project_store(tmp_path: Path) -> None:
    root = str(tmp_path)
    proj.create_project(root, name="P")
    assert not (tmp_path / "project" / "projects.json").exists()  # 不新建第二 store


# ---------------------------------------------------------------- 10 project_agile 投影 (兼容)

def test_project_agile_projection_path(tmp_path: Path) -> None:
    from factory_console import project_agile as pa

    root = str(tmp_path)
    p = proj.create_project(root, name="Agile P")
    cid = pu.create_conversation(root, title="C")["id"]
    pa.attach_project(root, cid, p["id"])            # 既有 agile attach (写 conv.project_id)
    assert pa.conversation_project_id(root, cid) == p["id"]
    # OS boundary 能解析 agile 建立的引用 (project_agile = 视图, 不是真相)
    assert proj.resolve_project_for_conversation(root, cid)["id"] == p["id"]


# ---------------------------------------------------------------- 11 CLI smoke (真实 CLI -> org SSOT)

def test_cli_project_path_uses_org_ssot(tmp_path: Path, monkeypatch) -> None:
    from factory_console.cli_factory import main as cli_main

    root = str(tmp_path)
    cid = _company(root)
    monkeypatch.setenv("DATA_DIR", root)          # FactoryCLI 经 ConfigProvider 取数据根
    rc = cli_main(["create", "project", "--name", "CLI Project", "--company", cid,
                   "--json"])
    assert rc == 0
    listed = proj.list_projects(root, company_id=cid)
    assert any(p["name"] == "CLI Project" for p in listed)   # CLI -> org SSOT
    assert not (tmp_path / "project" / "projects.json").exists()  # 无第二 store
