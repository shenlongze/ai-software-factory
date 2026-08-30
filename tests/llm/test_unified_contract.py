"""S43: Unified Entity/Data Contract (Master Plan S42)。

覆盖:
- ID Contract (统一前缀, 未知类型拒绝, 类型匹配)
- Universal Entity Contract (基础字段完整, 禁重复定义)
- Version Contract (乐观并发 VERSION_CONFLICT, 非静默覆盖)
- Lifecycle Engine (Created→Validated→Active→…; 非法迁移拒绝)
- Command/Response Contract
- Event Contract (correlation/causation)
- Error Contract (统一 code)
- Pagination Contract
- Realtime Event Contract
- 13 实体统一关系 + Lineage 追溯
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.unified_contract import (  # noqa: E402
    new_id, validate_entity_id, create_entity, validate_entity, check_version,
    bump_version, ConcurrencyError, lifecycle_transition, make_command,
    make_response, make_event, make_error, make_page, make_realtime_event,
    relation_children, relation_parents, store_entity, get_entity, entities,
    trace_lineage, ID_PREFIXES, ENTITY_RELATIONS, LIFECYCLE_STATES, ERROR_CODES,
)


# --- ID Contract ---

def test_id_contract(tmp_path):
    cid = new_id("conv")
    assert cid.startswith("conv_")
    tid = new_id("task")
    assert tid.startswith("task_")
    assert validate_entity_id(cid, "conv")
    assert not validate_entity_id("foo_abc", "task")
    with pytest.raises(ValueError, match="未知 entity_type"):
        new_id("unknown_type")
    # 类型不匹配
    assert not validate_entity_id(cid, "task")


# --- Universal Entity Contract ---

def test_entity_contract(tmp_path):
    e = create_entity("conv", created_by="human", metadata={"title": "讨论"})
    assert e["type"] == "conv"
    assert e["version"] == 1
    assert e["status"] == "CREATED"
    assert validate_entity(e)["valid"]
    # 缺基础字段 → 拒绝
    bad = dict(e)
    del bad["lineage"]
    with pytest.raises(ValueError, match="缺基础字段"):
        validate_entity(bad)
    # 非法 id → 拒绝
    bad2 = dict(e)
    bad2["id"] = "foo_123"
    with pytest.raises(ValueError, match="非法 entity_id"):
        validate_entity(bad2)


# --- Version Contract (乐观并发) ---

def test_version_optimistic_concurrency(tmp_path):
    e = create_entity("task")
    bump_version(e, actor="agent", note="v2")
    assert e["version"] == 2
    assert len(e["lineage"]) == 1
    # 基于旧版本修改 → VERSION_CONFLICT
    with pytest.raises(ConcurrencyError, match="VERSION_CONFLICT"):
        check_version(e, expected_version=1)
    # 基于当前版本 → OK
    check_version(e, expected_version=2)


# --- Lifecycle Engine ---

def test_lifecycle_engine(tmp_path):
    e = create_entity("task")
    lifecycle_transition(e, target="VALIDATED")
    lifecycle_transition(e, target="ACTIVE")
    lifecycle_transition(e, target="COMPLETED")
    assert e["status"] == "COMPLETED"
    assert len(e["lifecycle_history"]) == 3
    # 非法迁移拒绝
    e2 = create_entity("task")
    with pytest.raises(ValueError, match="INVALID_STATE"):
        lifecycle_transition(e2, target="ACTIVE")  # CREATED→ACTIVE 非法
    # 终态不可变
    with pytest.raises(ValueError, match="INVALID_STATE"):
        lifecycle_transition(e, target="ACTIVE")  # COMPLETED→ACTIVE 非法


# --- Command/Response ---

def test_command_response(tmp_path):
    cmd = make_command(command="task.update", entity_id="task_1", actor="human",
                       expected_version=2)
    assert cmd["request_id"].startswith("cmd_")
    assert cmd["command"] == "task.update"
    assert cmd["version"] == 2
    resp = make_response(success=True, data={"id": "task_1"}, entity_version=3,
                         event_ids=["evt_1"])
    assert resp["success"] is True
    assert resp["entity_version"] == 3


# --- Event Contract (correlation/causation) ---

def test_event_contract(tmp_path):
    e = create_entity("task")
    ev = make_event(event_type="TASK_UPDATED", entity=e, action="update",
                    actor="agent", correlation_id="corr_x", causation_id="evt_prev")
    assert ev["event_id"].startswith("evt_")
    assert ev["entity_id"] == e["id"]
    assert ev["correlation_id"] == "corr_x"
    assert ev["causation_id"] == "evt_prev"
    # 自动生成 correlation
    ev2 = make_event(event_type="X", entity=e, action="y")
    assert ev2["correlation_id"].startswith("corr_")


# --- Error Contract ---

def test_error_contract(tmp_path):
    err = make_error(code="VERSION_CONFLICT", entity_id="task_1")
    assert err["code"] == "VERSION_CONFLICT"
    assert err["message"]  # 默认消息
    # 未知 code → UNKNOWN_ERROR
    err2 = make_error(code="WEIRD", message="custom")
    assert err2["code"] == "UNKNOWN_ERROR"
    assert err2["message"] == "custom"


# --- Pagination ---

def test_pagination(tmp_path):
    pg = make_page(items=[1, 2, 3], page=1, page_size=2, total=3)
    assert pg["total"] == 3
    assert pg["pages"] == 2
    assert len(pg["items"]) == 3


# --- Realtime Event ---

def test_realtime_event(tmp_path):
    rt = make_realtime_event(event_type="TASK_RUNNING", entity_type="task",
                             entity_id="task_1", version=3)
    assert rt["type"] == "TASK_RUNNING"
    assert rt["entity"] == "task"
    assert rt["version"] == 3


# --- 13 实体关系 + Lineage ---

def test_relations_and_lineage(tmp_path):
    # 统一关系
    assert "req" in relation_children("conv")
    assert "decision" in relation_children("analysis")
    assert "node" in relation_children("task")
    assert "project" in relation_parents("sprint")
    # 关系树 + lineage 追溯
    conv = create_entity("conv", created_by="human")
    req = create_entity("req", parent_id=conv["id"])
    an = create_entity("analysis", parent_id=req["id"])
    dec = create_entity("decision", parent_id=an["id"])
    proj = create_entity("project", parent_id=dec["id"])
    task = create_entity("task", parent_id=proj["id"])
    node = create_entity("node", parent_id=task["id"])
    for e in [conv, req, an, dec, proj, task, node]:
        store_entity(str(tmp_path), e)
    lg = trace_lineage(str(tmp_path), node["id"])
    types = [x["type"] for x in lg]
    assert types == ["node", "task", "project", "decision", "analysis", "req", "conv"]
    # 持久化
    assert len(entities(str(tmp_path))) == 7
    assert get_entity(str(tmp_path), conv["id"])["type"] == "conv"


# --- CLI ---

def test_cli_entity(tmp_path):
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["entity", "create", "--type", "task", "--by", "human",
                      "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["entity", "list", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["entity", "contracts", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_entity(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/entities", json={"type": "task", "created_by": "human"})
    assert resp.status_code == 200
    e = resp.json()
    assert e["id"].startswith("task_")
    assert e["version"] == 1
    resp = client.post("/api/entities", json={"type": "bogus"})
    assert resp.status_code == 400  # 未知类型
    resp = client.get(f"/api/entities/{e['id']}")
    assert resp.status_code == 200
    resp = client.get("/api/entities")
    assert resp.status_code == 200
    assert "items" in resp.json()
    resp = client.get(f"/api/entities/{e['id']}/lineage")
    assert resp.status_code == 200
    resp = client.get("/api/contracts")
    assert resp.status_code == 200
    assert "id_prefixes" in resp.json()
