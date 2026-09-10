"""MU-CORE-07: Capability SSOT + ProfessionalRole/Workforce 引用解析。

验收: CRUD/persistence/stable ID · PR→CAP resolve · Workforce→CAP resolve · invalid ref 拒绝
      Industry 分离 · Agent≠Capability · 无第二 store
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

from factory_console import os_core_capability as cap  # noqa: E402
from factory_console import os_core_identity as ident  # noqa: E402
from factory_console import os_core_professional as prof  # noqa: E402
from factory_console import os_core_workforce as wf  # noqa: E402


# ---------------------------------------------------------------- CRUD / persistence

def test_capability_crud_persist(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = cap.create_capability(root, name="Backend Development", category="engineering")
    assert c["capability_id"].startswith("CAP-") and c["status"] == "active"
    assert (tmp_path / "capability" / "capabilities.json").is_file()   # persistence
    assert cap.get_capability(root, c["capability_id"])["name"] == "Backend Development"
    assert [x["capability_id"] for x in cap.list_capabilities(root, category="engineering")] == [c["capability_id"]]
    cap.update_capability(root, c["capability_id"], description="API + DB")
    assert cap.get_capability(root, c["capability_id"])["description"] == "API + DB"


def test_capability_id_stable_unique(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = cap.create_capability(root, name="A")
    b = cap.create_capability(root, name="B")
    assert a["capability_id"] != b["capability_id"]
    assert cap.get_capability(root, a["capability_id"])["capability_id"] == a["capability_id"]  # reload 稳定
    with pytest.raises(ValueError):     # 重名拒绝
        cap.create_capability(root, name="A")


def test_capability_resolve_by_id_and_name(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = cap.create_capability(root, name="Testing")
    assert cap.resolve_capability(root, c["capability_id"])["name"] == "Testing"
    assert cap.resolve_capability(root, "Testing")["capability_id"] == c["capability_id"]
    assert cap.validate_capability_ref(root, "Testing") == c["capability_id"]
    with pytest.raises(ValueError):
        cap.resolve_capability(root, "CAP-nope")
    cap.set_capability_status(root, c["capability_id"], "retired")
    with pytest.raises(ValueError):     # retired 不可再被引用
        cap.validate_capability_ref(root, c["capability_id"])


# ---------------------------------------------------------------- ProfessionalRole -> Capability

def test_professional_role_capability_resolution(tmp_path: Path) -> None:
    root = str(tmp_path)
    c1 = cap.create_capability(root, name="Requirement Analysis")
    c2 = cap.create_capability(root, name="Product Planning")
    dom = prof.create_professional_domain(root, name="Software Engineering")
    pr = prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                       name="Product Manager",
                                       capability_refs=[c1["capability_id"], "Product Planning"])
    # name 解析为 canonical id
    assert pr["capability_refs"] == [c1["capability_id"], c2["capability_id"]]
    resolved = prof.resolve_professional_role_capabilities(root, pr["professional_role_id"])
    names = {x["name"] for x in resolved["capabilities"]}
    assert names == {"Requirement Analysis", "Product Planning"}   # PR → CAP 真实 resolve


def test_professional_role_invalid_capability_rejected(tmp_path: Path) -> None:
    root = str(tmp_path)
    dom = prof.create_professional_domain(root, name="Data")
    with pytest.raises(ValueError):
        prof.create_professional_role(root, professional_domain_id=dom["domain_id"],
                                      name="Data Engineer", capability_refs=["CAP-nope"])


# ---------------------------------------------------------------- Workforce -> Capability

def test_workforce_capability_resolution(tmp_path: Path) -> None:
    root = str(tmp_path)
    c = cap.create_capability(root, name="ETL")
    w = wf.create_workforce(root, name="Data WF", capability_refs=["ETL"])
    assert w["capability_refs"] == [c["capability_id"]]        # name -> canonical id
    resolved = wf.resolve_workforce_capabilities(root, w["workforce_id"])
    assert resolved["capabilities"][0]["capability_id"] == c["capability_id"]
    with pytest.raises(ValueError):
        wf.create_workforce(root, name="Bad WF", capability_refs=["CAP-nope"])


# ---------------------------------------------------------------- 边界: Industry / Agent / 无第二 store

def test_industry_is_not_capability(tmp_path: Path) -> None:
    root = str(tmp_path)
    # Capability SSOT 无 industry 字段; 创建 capability 不触碰 org capability 池
    c = cap.create_capability(root, name="Supply Chain Planning")
    assert "industry" not in c and "industry_id" not in c
    assert not (tmp_path / "org" / "capabilities.json").exists()
    # org.capabilities.Industry 是提供者目录实体, 不进 Capability SSOT
    assert cap.get_capability(root, c["capability_id"])["name"] == "Supply Chain Planning"
    assert all(x["capability_id"] != "Industry" for x in cap.list_capabilities(root))


def test_agent_is_not_capability(tmp_path: Path) -> None:
    root = str(tmp_path)
    a = ident.create_identity(root, identity_type="agent", display_name="Agent X")
    assert a["identity_type"] == "agent"
    # 创建 Agent Identity 不产生 Capability
    assert cap.list_capabilities(root) == []


def test_no_second_capability_store(tmp_path: Path) -> None:
    root = str(tmp_path)
    cap.create_capability(root, name="Research")
    assert (tmp_path / "capability" / "capabilities.json").is_file()
    assert not (tmp_path / "capabilities.json").exists()
    assert not (tmp_path / "ops" / "capabilities").exists()
