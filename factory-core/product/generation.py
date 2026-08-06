"""factory-core/product/generation.py — 生成编排框架 (GeneratedArtifactContext + ProductGenerator)。

设计依据:
- phase9b-status.md 任务范围 §1 + phase9-plan.md §8 (Provider/Agent 调度):
  TaskRequirement (task_type=research/prd/ui) → CostAwareSelector.recommend
  (Provider Intelligence: 能力+成本+表现) → ProviderAdapter.generate → Artifact
  (+ GeneratedArtifactContext + Lineage) → 自动 request_approval (PRD/UI
  mandatory, 生成后等待人工批准)。第一阶段只实现生成框架 (编排 + 上下文记录),
  不实现复杂 Prompt — Provider 返回内容直接作为 artifact content。
- 禁硬编码 Provider / 禁直接调 LLM: Provider 选择完全经注入的 CostAwareSelector
  (复用 Phase 8, 只读调用零修改); 本模块不构造任何具体 Provider id, 不 import
  任何 Adapter 实现 (adapters 由装配点注入 — CLI 装配 BUILTIN_PROVIDER_ADAPTERS)。
  "生成类型 → TaskRequirement" 映射 (GENERATION_TYPES) 是领域知识 (什么任务需要
  什么能力), 不是 Provider 硬编码。
- 事件链 (经 EventLogger, source="product"): product.generation.started →
  provider.selected (source=recommendation, 复用 8B-2 审计语义) →
  provider.execution.started → completed|failed → product.generation.completed |
  failed; usage_store 注入时追加 provider.usage.recorded (经验积累闭环, 失败安全)。
- 失败不静默: 无 Provider 可用 / 无 Adapter 实现 / 生成失败 → 发
  product.generation.failed + 抛明确异常 (CLI rc 1); adapter 失败额外产出
  status="failed" 的 Artifact (可追溯 + Dashboard generation 状态列数据源)。
- GeneratedArtifactContext 落于 artifact.content["generation_context"] (Artifact
  模型零修改); Lineage 字段 (provider_id/agent_id/source_events/version/confidence)
  用 Artifact 原生字段 — AI Artifact Lineage 闭环 (phase9a-status 约束 3/4)。
- 无 Database/Web API: 纯本地 JSON store + 事件审计 (同 service.py 边界)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, field_validator

from events.models import parse_timestamp

from providers.models import ProviderRequest, ProviderResponse, TaskRequirement  # noqa: F401  (复用 Phase 8 I/O 契约)
from providers.usage import ProviderUsage  # noqa: F401  (经验积累计量, 失败安全)

from .events import (
    record_experience_recorded,
    record_generation_completed,
    record_generation_failed,
    record_generation_started,
)
from .experience import ExperienceStore, GenerationExperience
from .models import ApprovalRequest, Artifact, ProductIdea, _now
from .service import ProductError, ProductNotFoundError, ProductService

if TYPE_CHECKING:  # 类型标注专用 (运行时惰性 — 删除 providers 不影响模块加载)
    from providers.selector import CostAwareSelector  # pragma: no cover

#: 生成类型 → 生成需求模板 (领域映射, 非 Provider 硬编码):
#: task_type = TaskRequirement.task_type (与 runtime_preferences.<task_type> 键同构);
#: capabilities = 该阶段产物所需能力标签 (CostAwareSelector 能力过滤输入);
#: gate = 生成后自动申请审批的门 id (None = 无默认门不自动申请; PRD/UI mandatory 保持)。
GENERATION_TYPES: dict[str, dict[str, Any]] = {
    "research": {
        "task_type": "research",
        "capabilities": ["analysis"],
        "gate": None,
        "description": "研究产物: 市场/竞品/机会分析",
    },
    "prd": {
        "task_type": "prd",
        "capabilities": ["generation", "reasoning"],
        "gate": "prd",
        "description": "PRD 产物: 问题/目标/用户/功能/指标 (生成后等待人工批准)",
    },
    "ui": {
        "task_type": "ui",
        "capabilities": ["generation"],
        "gate": "ui",
        "description": "UI 设计产物: 方向/流程/原型 (生成后等待人工批准)",
    },
}


class ProductGenerationError(ProductError):
    """生成业务错误 (无 Provider/无 Adapter/无效类型/生成失败; CLI 映射 → 退出码 1)。"""


class ProductGenerationNoProviderError(ProductGenerationError):
    """无 Provider 可用 (CostAwareSelector 推荐为空 — 配置缺口, 明确错误不静默)。"""


def _is_utc_timestamp(value: str) -> bool:
    """统一 UTC 时间戳校验: 内部规范格式 (%Y-%m-%dT%H:%M:%S.%fZ) 或 ISO 8601
    UTC 表示 (Z 后缀 / +00:00 偏移, 微秒可选)。naive 时间戳 (无时区) 一律拒绝。
    """
    try:
        parse_timestamp(value)
        return True
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = dt.utcoffset()
    return offset is not None and offset == timedelta(0)


class GeneratedArtifactContext(BaseModel):
    """一次 AI 生成的上下文记录 (AI Artifact Lineage 的生成侧描述)。

    - source_artifact_id: 生成来源 Artifact (research ← product_idea; prd/ui ←
      product_idea 锚点) — Input→Agent→Provider→Artifact 链路可追溯。
    - agent_id: 执行 Agent (本阶段无 Agent 参与产品阶段 — phase9-plan §8
      \"产品阶段无人 Agent\", 预留 None)。
    - provider_id: 生成来源 Provider (CostAwareSelector 推荐结果)。
    - generation_time: 生成完成时间 (统一 UTC 时间戳)。
    - task_requirement: 本次生成使用的 TaskRequirement dict (审计: 什么需求
      经什么选择逻辑选了哪个 Provider)。
    - confidence: 生成置信度 0-1 (审核优先级/经验学习数据接口, 只记录不消费)。
    - source_events: 生成事件链 event_id 列表 (generation.started +
      provider.execution.completed, 唯一事实源引用)。
    """

    source_artifact_id: str
    agent_id: str | None = None
    provider_id: str | None = None
    generation_time: str = Field(default_factory=_now)
    task_requirement: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    source_events: list[str] = Field(default_factory=list)

    @field_validator("source_artifact_id")
    @classmethod
    def _source_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("source_artifact_id must not be empty")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("generation_time")
    @classmethod
    def _time_format(cls, v: str) -> str:
        if not _is_utc_timestamp(v):
            raise ValueError(f"generation_time must be a UTC timestamp: {v!r}")
        return v

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@dataclass(frozen=True)
class GenerationResult:
    """一次成功生成的完整结果 (CLI --json 出口与测试断言共用)。

    - artifact: 生成的 Artifact (status=completed, Lineage 已回填)。
    - context: GeneratedArtifactContext (同 artifact.content["generation_context"])。
    - approval_request: 自动申请的审批请求 (PRD/UI mandatory; research → None)。
    - provider_id: 实际使用的 Provider; recommendation: 推荐结果 dict (审计展示)。
    """

    artifact: Artifact
    context: GeneratedArtifactContext
    approval_request: ApprovalRequest | None = None
    provider_id: str = ""
    recommendation: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "context": self.context.to_dict(),
            "approval_request": (
                self.approval_request.to_dict() if self.approval_request is not None else None
            ),
            "provider_id": self.provider_id,
            "recommendation": self.recommendation,
        }


class ProductGenerator:
    """产品生成编排器: TaskRequirement → CostAwareSelector → ProviderAdapter → Artifact。

    组装 (CLI 装配点, 延迟导入 providers — Removal Isolation):
        generator = ProductGenerator(service, logger=logger, selector=selector,
                                     adapters=BUILTIN_PROVIDER_ADAPTERS,
                                     usage_store=usage_store,
                                     experience_store=experience_store)
    - selector: CostAwareSelector (Phase 8 复用, 只读调用) — 未装配 (None) →
      视为无 Provider 智能 → generate 抛 ProductGenerationNoProviderError (明确)。
    - adapters: {provider_id: ProviderAdapter} 实现映射 (由装配点注入, 本模块
      不 import 任何 Adapter 实现 — 禁硬编码)。
    - usage_store: ProviderUsageStore (可选) — 生成成功后记录 usage
      (provider.usage.recorded, 经验积累闭环); 失败安全 (落库失败跳过 BOTH
      落库与事件, 不破坏生成链路, 同 8B-3 语义)。
    - experience_store: ExperienceStore (可选) — record_experience/list_experiences。
    - logger: EventLogger (可选) — None 时全部事件静默 (同 ProductService 模式)。

    事件链 (成功): product.generation.started → provider.selected (recommendation)
    → provider.execution.started → provider.execution.completed →
    [provider.usage.recorded] → product.generation.completed → approval.required
    (PRD/UI mandatory)。
    """

    def __init__(
        self,
        service: ProductService,
        logger: Any = None,
        *,
        selector: Any = None,
        adapters: dict[str, Any] | None = None,
        usage_store: Any = None,
        experience_store: ExperienceStore | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._service = service
        self._logger = logger
        self._selector = selector
        self._adapters = dict(adapters or {})
        self._usage_store = usage_store
        self._experience_store = experience_store
        self._agent_id = agent_id

    @property
    def service(self) -> ProductService:
        return self._service

    @property
    def selector(self) -> Any:
        """注入的 CostAwareSelector (None = 未装配 — 无 Provider 智能)。"""
        return self._selector

    @property
    def adapters(self) -> dict[str, Any]:
        return dict(self._adapters)

    # ------------------------------------------------------------------ 生成编排

    def generate(
        self,
        idea_id: str,
        artifact_type: str,
        *,
        provider_id: str | None = None,
        min_quality: float = 0.0,
        budget: float | None = None,
        confidence: float = 0.0,
        created_by: str = "generator",
    ) -> GenerationResult:
        """生成一个产品 Artifact (research/prd/ui) — 完整编排链。

        流程: 校验类型 → idea 存在性 → TaskRequirement 构造 → CostAwareSelector.
        recommend (显式 --provider 覆盖经 explicit 层) → ProviderAdapter.generate
        → Artifact 产出 (GeneratedArtifactContext + Lineage) → 自动 request_approval
        (PRD/UI mandatory) → GenerationResult。

        Raises:
            ProductNotFoundError: idea 不存在 (CLI 退出码 7)。
            ProductGenerationNoProviderError: 无 Provider 智能 / 无能力匹配候选
                (CLI 退出码 1, 明确错误不静默)。
            ProductGenerationError: 无 Adapter 实现 / 生成失败 (CLI 退出码 1)。
        """
        template = GENERATION_TYPES.get(artifact_type)
        if template is None:
            raise ProductGenerationError(
                f"unsupported artifact type: {artifact_type!r} "
                f"(expected one of: {', '.join(GENERATION_TYPES)})"
            )
        idea = self._service.get_idea(idea_id)  # ProductNotFoundError → CLI rc 7
        source_artifact = self._service.get_artifact_by_idea(idea_id)
        source_id = source_artifact.id if source_artifact is not None else idea.id

        requirement = TaskRequirement(
            task_type=template["task_type"],
            required_capabilities=list(template["capabilities"]),
            min_quality=min_quality,
            budget=budget,
        )
        selected_id, recommendation = self._select(idea, artifact_type, source_id, requirement, provider_id)

        ev_started = record_generation_started(
            self._logger,
            artifact_type=artifact_type,
            source_artifact_id=source_id,
            idea_id=idea.id,
            provider_id=selected_id,
            task_requirement=requirement.to_dict(),
        )
        self._record_provider_selected(selected_id, recommendation)
        self._record_provider_execution_started(selected_id)

        request = ProviderRequest(
            prompt=self._build_prompt(artifact_type, idea),
            metadata={
                "artifact_type": artifact_type,
                "idea_id": idea.id,
                "source_artifact_id": source_id,
                "generation": "product-generator",
            },
        )
        started = time.monotonic()
        try:
            response = adapter_call(self._adapters, selected_id, request)
        except Exception as exc:  # Adapter 违反不抛契约 (意外异常) — 防御兜底
            latency = _ms_since(started)
            self._record_usage(
                selected_id, None, success=False, error=f"{type(exc).__name__}: {exc}",
                estimated_cost=None, latency_ms=latency,
            )
            self._record_failed_artifact(
                artifact_type, idea=idea, source_id=source_id,
                provider_id=selected_id, requirement=requirement,
                confidence=confidence, error=f"{type(exc).__name__}: {exc}",
                source_events=_event_id_list(ev_started),
            )
            self._fail(
                artifact_type, source_id, idea_id=idea.id, provider_id=selected_id,
                error=f"provider generation raised: {exc}",
            )
            raise ProductGenerationError(
                f"provider {selected_id!r} generation raised: {exc}"
            ) from exc
        latency_ms = _ms_since(started)

        if not response.ok:
            self._record_usage(
                selected_id, response, success=False, error=response.error,
                estimated_cost=None, latency_ms=latency_ms,
            )
            self._record_provider_execution_failed(selected_id, response.error or "provider error")
            self._record_failed_artifact(
                artifact_type, idea=idea, source_id=source_id,
                provider_id=selected_id, requirement=requirement,
                confidence=confidence, error=response.error or "provider generation failed",
                source_events=_event_id_list(ev_started),
            )
            self._fail(
                artifact_type, source_id, idea_id=idea.id, provider_id=selected_id,
                error=response.error or "provider generation failed",
            )
            raise ProductGenerationError(
                f"provider {selected_id!r} generation failed: {response.error}"
            )

        self._record_provider_execution_completed(selected_id, response)
        self._record_usage(
            selected_id, response, success=True, error=None,
            estimated_cost=recommendation.estimated_cost
            if recommendation is not None else None,
            latency_ms=latency_ms,
        )

        # Artifact 产出 (GeneratedArtifactContext + Lineage 闭环)
        version = self._next_version(idea.id, artifact_type)
        context = GeneratedArtifactContext(
            source_artifact_id=source_id,
            agent_id=self._agent_id,
            provider_id=selected_id,
            task_requirement=requirement.to_dict(),
            confidence=confidence,
            source_events=self._source_event_ids(ev_started),
        )
        artifact = self._service.create_artifact(
            artifact_type,
            content={
                "content": response.content,  # 第一阶段: Provider 内容直接作 artifact content
                "provider_id": selected_id,
                "model": response.model,
                "idea_id": idea.id,
                "generation_context": context.to_dict(),
            },
            created_by=created_by,
            provider_id=selected_id,
            agent_id=self._agent_id,
            source_events=list(context.source_events),
            confidence=confidence,
            status="completed",
            idea_id=idea.id,
            version=version,
        )
        # 自动审批 (PRD/UI mandatory, 生成后等待人工批准; research → None)
        approval = None
        gate = template["gate"]
        if gate is not None:
            approval = self._service.request_approval(
                artifact.id,
                gate_id=gate,
                by=created_by,
                note=f"auto-requested after {artifact_type} generation (mandatory gate)",
            )
        # 事件链约定: product.generation.completed 在审批请求**之后**统一发出
        # (approval_request 信息一并入 payload, 单一 completed 事件 — 避免
        # PRD/UI 路径双 completed 与 research 单 completed 不一致; 链序:
        # started → provider.* → [usage.recorded] → completed → approval.required)。
        record_generation_completed(
            self._logger, artifact=artifact, context=context,
            provider_id=selected_id, approval_request=approval,
        )

        return GenerationResult(
            artifact=artifact,
            context=context,
            approval_request=approval,
            provider_id=selected_id,
            recommendation=recommendation.to_dict() if recommendation is not None else None,
        )

    # ------------------------------------------------------------------ Experience 记录接口

    def record_experience(
        self,
        artifact_id: str,
        *,
        rating: int | None = None,
        comment: str = "",
        approved: bool | None = None,
        by: str = "cli",
    ) -> GenerationExperience:
        """记录一次人工对生成产物的经验 (数据接口, 不实现优化逻辑)。

        从 Artifact Lineage 推导 provider_id/confidence/generated_at; 落
        ExperienceStore + 发 product.experience.recorded (source=product)。
        artifact 不存在 → ProductNotFoundError (CLI 退出码 7)。
        """
        artifact = self._service.get_artifact(artifact_id)
        if self._experience_store is None:
            raise ProductGenerationError("experience store not configured")
        experience = GenerationExperience(
            artifact_type=artifact.type,
            provider_id=artifact.provider_id,
            approved=approved,
            confidence=artifact.confidence,
            human_feedback=comment or "",
            rating=rating,
            generated_at=artifact.created_at,
        )
        self._experience_store.record(experience)
        record_experience_recorded(self._logger, experience=experience, by=by)
        return experience

    def list_experiences(self, artifact_type: str | None = None) -> list[GenerationExperience]:
        """经验清单 (可按 artifact_type 过滤); 未装配 ExperienceStore → []。"""
        if self._experience_store is None:
            return []
        return self._experience_store.list(artifact_type)

    # ------------------------------------------------------------------ 内部

    def _select(
        self,
        idea: ProductIdea,
        artifact_type: str,
        source_id: str,
        requirement: TaskRequirement,
        explicit: str | None,
    ) -> tuple[str, Any]:
        """Provider 选择 (禁硬编码): 经注入 CostAwareSelector.recommend。

        未装配 selector → 无 Provider 智能 (配置缺口, 明确错误); 推荐为空 →
        无能力匹配候选 (同样明确错误); 显式 --provider 未注册/禁用由 selector
        explicit 层抛 ProviderNotFoundError → 包装为 ProductGenerationError。
        """
        if self._selector is None:
            self._fail(
                artifact_type, source_id, idea_id=idea.id, provider_id=explicit,
                error="provider intelligence not configured (CostAwareSelector unavailable)",
            )
            raise ProductGenerationNoProviderError(
                "no provider available: provider intelligence not configured "
                "(CostAwareSelector unavailable)"
            )
        try:
            recommendation = self._selector.recommend(requirement, explicit=explicit)
        except Exception as exc:  # ProviderNotFoundError (显式未注册/禁用) 等 — 明确暴露
            self._fail(
                artifact_type, source_id, idea_id=idea.id, provider_id=explicit,
                error=f"provider selection failed: {exc}",
            )
            raise ProductGenerationError(f"provider selection failed: {exc}") from exc
        if recommendation is None:
            self._fail(
                artifact_type, source_id, idea_id=idea.id, provider_id=explicit,
                error=f"no provider available for artifact type {artifact_type!r} "
                      "(no capability match; check provider capability profiles)",
            )
            raise ProductGenerationNoProviderError(
                f"no provider available for artifact type {artifact_type!r} "
                "(no capability match; check provider capability profiles)"
            )
        return recommendation.provider_id, recommendation

    def _record_provider_selected(self, provider_id: str, recommendation: Any) -> None:
        if self._logger is None:
            return
        from providers.events import record_provider_selected

        record_provider_selected(
            self._logger,
            provider_id=provider_id,
            source="product",
            stage="recommended",
            action="select provider for product generation",
            selection_source=getattr(recommendation, "source", "recommendation"),
        )

    def _record_provider_execution_started(self, provider_id: str) -> None:
        if self._logger is None:
            return
        from providers.events import record_provider_execution_started

        record_provider_execution_started(
            self._logger, provider_id=provider_id, source="product",
        )

    def _record_provider_execution_completed(self, provider_id: str, response: ProviderResponse) -> None:
        if self._logger is None:
            return
        from providers.events import record_provider_execution_completed

        record_provider_execution_completed(
            self._logger, provider_id=provider_id, model=response.model,
            usage=response.usage or None, source="product",
        )

    def _record_provider_execution_failed(self, provider_id: str, error: str) -> None:
        if self._logger is None:
            return
        from providers.events import record_provider_execution_failed

        record_provider_execution_failed(
            self._logger, provider_id=provider_id, error=error, source="product",
        )

    def _record_usage(
        self,
        provider_id: str,
        response: ProviderResponse | None,
        *,
        success: bool,
        error: str | None,
        estimated_cost: float | None,
        latency_ms: int,
    ) -> None:
        """usage 自动记录 (经验积累闭环; 失败安全 — 落库异常跳过 BOTH 落库与事件)。

        8B-3 语义: usage 是审计增强数据, 记录失败绝不破坏生成链路 (事件是唯一
        事实源, 落库失败即事实未发生, 不发\"声称已落库\"的假事件)。
        """
        if self._usage_store is None:
            return
        usage = response.usage if response is not None else {}
        try:
            record = ProviderUsage(
                provider_id=provider_id,
                model=response.model if response is not None else None,
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                estimated_cost=float(estimated_cost or 0.0),
                latency_ms=int(latency_ms),
                success=success,
                error=error,
            )
            self._usage_store.record(record)
        except Exception:
            return  # 落库失败 → 事件也不发 (不破坏生成链路)
        if self._logger is None:
            return
        from providers.events import record_provider_usage

        try:
            record_provider_usage(self._logger, usage=record, source="product")
        except Exception:
            return  # 事件失败也不级联 (审计增强数据)

    def _source_event_ids(self, started_event: Any) -> list[str]:
        """生成事件链 event_id 列表 (Lineage source_events, 唯一事实源引用)。"""
        ids: list[str] = []
        if started_event is not None and getattr(started_event, "event_id", None):
            ids.append(started_event.event_id)
        if self._logger is not None:
            try:
                events = self._logger.store.query(event_type="provider.execution.completed")
                if events:
                    ids.append(events[-1].event_id)
            except Exception:
                pass  # 事件库不可用 → 只保留 started (失败安全)
        return ids

    def _next_version(self, idea_id: str, artifact_type: str) -> int:
        """同 idea 同类型产物的重生成版本 (Lineage: 每次重生成 +1, 首版 1)。"""
        versions = [
            a.version
            for a in self._service.list_artifacts(artifact_type)
            if isinstance(a.content, dict) and a.content.get("idea_id") == idea_id
        ]
        return max(versions) + 1 if versions else 1

    def _build_prompt(self, artifact_type: str, idea: ProductIdea) -> str:
        """框架级生成上下文 (第一阶段不实现复杂 Prompt — 结构化注入产物类型与
        idea 摘要, 具体生成质量由 Provider 决定)。"""
        template = GENERATION_TYPES[artifact_type]
        return (
            f"Generate a {artifact_type} artifact for product idea {idea.id} ({template['description']}).\n"
            f"Title: {idea.title}\n"
            f"Description: {idea.description or '(none)'}\n"
            f"Goals: {', '.join(idea.goals) or '(none)'}"
        )

    def _fail(
        self,
        artifact_type: str,
        source_artifact_id: str,
        *,
        error: str,
        provider_id: str | None,
        idea_id: str | None = None,
    ) -> None:
        """生成失败审计 (product.generation.failed, result=ERROR — 明确错误不静默)。"""
        record_generation_failed(
            self._logger,
            artifact_type=artifact_type,
            source_artifact_id=source_artifact_id,
            idea_id=idea_id,
            provider_id=provider_id,
            error=error,
        )

    def _record_failed_artifact(
        self,
        artifact_type: str,
        *,
        idea: ProductIdea,
        source_id: str,
        provider_id: str,
        requirement: TaskRequirement,
        confidence: float,
        error: str,
        source_events: list[str] | None = None,
    ) -> Artifact:
        """adapter 实际调用失败 → 落 status='failed' Artifact (失败产物可追溯,
        Lineage 保留 provider_id/version; Dashboard generation 状态列数据源 —
        9a '幻影产物'教训的失败侧: 失败也落库, 不静默消失)。"""
        version = self._next_version(idea.id, artifact_type)
        context = GeneratedArtifactContext(
            source_artifact_id=source_id,
            agent_id=self._agent_id,
            provider_id=provider_id,
            task_requirement=requirement.to_dict(),
            confidence=confidence,
            source_events=list(source_events or []),
        )
        return self._service.create_artifact(
            artifact_type,
            content={
                "content": "",
                "provider_id": provider_id,
                "idea_id": idea.id,
                "error": error,
                "generation_context": context.to_dict(),
            },
            created_by="generator",
            provider_id=provider_id,
            agent_id=self._agent_id,
            source_events=list(context.source_events),
            confidence=confidence,
            status="failed",
            idea_id=idea.id,
            version=version,
        )


def adapter_call(adapters: dict[str, Any], provider_id: str, request: ProviderRequest) -> ProviderResponse:
    """经 ProviderAdapter.generate 调用 (统一 I/O; 无实现 → 明确配置缺口错误)。

    本模块不 import 任何 Adapter 实现 (禁硬编码) — 实现映射由装配点注入;
    Adapter 契约: 失败返回 ProviderResponse(error=...), 不抛异常 (防御兜底
    在 generate() 的调用点)。
    """
    adapter = adapters.get(provider_id)
    if adapter is None:
        raise ProductGenerationError(
            f"no adapter implementation for provider {provider_id!r} "
            "(registered but not implemented)"
        )
    return adapter.generate(request)


def _event_id_list(event: Any) -> list[str]:
    """从事件对象取 event_id 列表 (失败链路 Lineage 锚点: generation.started)。"""
    if event is not None and getattr(event, "event_id", None):
        return [event.event_id]
    return []


def _ms_since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
