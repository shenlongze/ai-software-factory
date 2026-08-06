"""tests/product/product_helpers.py — Product 测试 helper (唯一名, 避免与兄弟目录遮蔽)。"""

from __future__ import annotations

from pathlib import Path

from cli_helpers import open_events  # noqa: F401  (re-export: CLI 事件断言)
from events.store import EventStore

from providers.models import ProviderResponse  # MockAdapter 契约返回

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


def event_sequence(store: EventStore) -> list[str]:
    """全部事件类型序列 (按 seq 升序, 断言链序)。"""
    return [e.type.value for e in store.query()]


# ------------------------------------------------------------------ Phase 9B 生成测试 mock (唯一名)

_UNSET = object()  # 哨兵: 区分"未传参"与"显式 None" (显式 None = 无 selector/无候选)


class MockSelector:
    """CostAwareSelector 测试替身: 固定推荐 / 可注入异常 / 记录调用。

    recommend(requirement, *, explicit=None, **kw) — 记录 (task_type,
    required_capabilities, min_quality, budget, explicit) 供断言。
    recommendation 显式传 None → 返回 None (模拟"无能力匹配候选" — selector
    recommend 返回 None 的语义); 不传 → 默认固定推荐 (provider_id 可配)。
    """

    def __init__(self, provider_id: str = "mock", *, recommendation=_UNSET, exc=None):
        self._provider_id = provider_id
        self._recommendation = recommendation
        self._exc = exc
        self.calls: list[dict] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def recommend(self, requirement, *, explicit=None, **kw):
        self.calls.append({
            "task_type": getattr(requirement, "task_type", None),
            "required_capabilities": list(getattr(requirement, "required_capabilities", [])),
            "min_quality": getattr(requirement, "min_quality", None),
            "budget": getattr(requirement, "budget", None),
            "explicit": explicit,
        })
        if self._exc is not None:
            raise self._exc
        if self._recommendation is not _UNSET:
            return self._recommendation
        from providers.selector import Recommendation
        return Recommendation(
            provider_id=self._provider_id, score=0.9,
            reasons=["mock recommendation"], estimated_cost=0.01,
        )


class MockAdapter:
    """ProviderAdapter 测试替身: 固定 content / error / 可注入异常 (防御兜底分支)。

    契约 (providers/provider.py): generate 不抛异常, 失败返回 error 响应;
    raise_exc 供上层防御兜底测试 (意外异常路径)。
    """

    def __init__(
        self,
        provider_id: str = "mock",
        *,
        content: str = "mock generated content",
        model: str = "mock-model",
        error: str | None = None,
        raise_exc: Exception | None = None,
        usage: dict | None = None,
    ):
        self._provider_id = provider_id
        self._content = content
        self._model = model
        self._error = error
        self._raise_exc = raise_exc
        self._usage = usage or {"prompt_tokens": 10, "completion_tokens": 5}
        self.requests: list = []

    def generate(self, request):
        self.requests.append(request)
        if self._raise_exc is not None:
            raise self._raise_exc
        if self._error is not None:
            return ProviderResponse(
                provider_id=self._provider_id, error=self._error, model=self._model,
            )
        return ProviderResponse(
            provider_id=self._provider_id, content=self._content,
            model=self._model, usage=dict(self._usage),
        )

    def chat(self, request):  # 契约方法 (generation 不使用, 桩实现)
        return self.generate(request)

    def stream(self, request):  # 契约方法 (generation 不使用, 桩实现)
        yield self.generate(request)


class MockUsageStore:
    """ProviderUsageStore 测试替身: 记录 record 调用 (成功/失败安全断言)。"""

    def __init__(self, *, fail: bool = False):
        self._fail = fail
        self.records: list = []

    def record(self, usage):
        if self._fail:
            raise RuntimeError("usage store down")
        self.records.append(usage)
        return usage

    def list(self):
        return list(self.records)


def make_generator(
    product_dir: Path,
    *,
    logger=None,
    selector=_UNSET,
    adapters: dict | None = None,
    usage_store=None,
    experience_store=None,
    agent_id: str | None = None,
    service: ProductService | None = None,
):
    """装配 ProductGenerator (测试替身可注入; 缺省 selector/adapter = mock)。

    selector 显式传 None → 不装配 (无 Provider 智能 — generate 抛
    ProductGenerationNoProviderError); 省略 → 默认 MockSelector。adapters
    显式传 {} → 空映射 (无 Adapter 实现); 省略 → {"mock": MockAdapter()}。
    """
    from product.generation import ProductGenerator

    svc = service if service is not None else make_service(product_dir, logger=logger)
    sel = selector if selector is not _UNSET else MockSelector()
    ads = dict(adapters) if adapters is not None else {"mock": MockAdapter()}
    return ProductGenerator(
        svc, logger=logger,
        selector=sel, adapters=ads, usage_store=usage_store,
        experience_store=experience_store, agent_id=agent_id,
    )
