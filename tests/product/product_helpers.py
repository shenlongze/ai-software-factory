"""tests/product/product_helpers.py — Product 测试 helper (唯一名, 避免与兄弟目录遮蔽)。"""

from __future__ import annotations

from pathlib import Path

from cli_helpers import open_events  # noqa: F401  (re-export: CLI 事件断言)
from events.store import EventStore

from product.models import ApprovalGate, Artifact, ProductIdea, ProductWorkflow
from product.service import ProductService
from product.store import ProductStore


def make_store(product_dir: Path) -> ProductStore:
    """独立 ProductStore (测试内直接构造, 不依赖 fixture)。"""
    return ProductStore(product_dir)


def make_service(product_dir: Path, logger=None) -> ProductService:
    """ProductService (可选 logger)。"""
    return ProductService(make_store(product_dir), logger=logger)


def seed_idea(service: ProductService, title: str = "AI 助手", **kw) -> ProductIdea:
    """创建想法 (默认标题), 返回 ProductIdea。"""
    return service.create_idea(title, **kw)


def seed_artifact(
    service: ProductService,
    artifact_type: str = "prd",
    idea_id: str | None = None,
    **kw,
) -> Artifact:
    """创建任意类型 Artifact (CLI 未暴露, 测试/服务层直用)。"""
    return service.create_artifact(artifact_type, idea_id=idea_id, **kw)


def seed_gate(
    service: ProductService,
    gate_id: str = "prd",
    required: str = "mandatory",
    rule: str = "test rule",
) -> ApprovalGate:
    """注册自定义门。"""
    gate = ApprovalGate(id=gate_id, artifact_type=gate_id, required=required, rule=rule)
    service._store.save_gate(gate)
    return gate


def seed_workflow(service: ProductService, idea_id: str) -> ProductWorkflow:
    """启动工作流 (默认阶段链)。"""
    return service.start_workflow(idea_id)


def event_types_of(store: EventStore) -> list[str]:
    """事件类型列表 (断言审计链)。"""
    return [e.type.value for e in store.query()]


def payload_of(store: EventStore, event_type: str) -> dict:
    """最后一条指定类型事件的 payload。"""
    events = [e for e in store.query() if e.type.value == event_type]
    assert events, f"no event of type {event_type!r}"
    return events[-1].payload
