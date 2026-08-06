"""factory-console/service.py — ConsoleService: Human Console 只读聚合服务。

设计依据:
- phase11a-status.md: Console 只读聚合各域 — workspace projects → lifecycle
  (product) → approvals (product 9c) → decisions/recommendations/experience
  (intelligence) → providers (providers)。**零写操作** (Human Layer 铁律:
  只查看/理解/审批/控制流程状态; 禁自动批准/禁修改 Decision/权重)。
- 边界 (phase10a-plan.md §Q1): Console 只读 Core/Extension 数据
  (Event/Artifact/Decision/Recommendation/Experience/Approval/Provider),
  不写任何状态 — 本服务全部方法只调用各 store 读接口
  (list/get/query/count), 无 save/update/record。
- 失败安全 (同 dashboard/metrics 哲学): 所有 store 依赖可选 (None → 空),
  缺 store/损坏文件不拖垮 Console (读命令永不因数据缺失失败)。
- 项目 → 生命周期关联 (复用 9d 既有约定, lifecycle.py:602): idea.context
  ["project"] 即项目 id (task 阶段生成 Core Task 时同款推导) — 本服务按
  该约定把 workspace 项目与 product lifecycle 关联, 不复制/不修改引擎逻辑。
- 延迟导入 Core 包 (Removal Isolation): 本模块函数内 import product/
  intelligence/providers 等 — 删除任一 Core 包不影响 Console 加载。
- 无 Database/Web API 依赖: 纯本地 JSON/SQLite 读接口 + 事件审计 (未来
  11B 经 api/ 路由函数挂 FastAPI 薄层)。
"""

from __future__ import annotations

from typing import Any

from .models import (
    AgentSummary,
    ApprovalSummary,
    ConsoleDashboard,
    CostSummary,
    DecisionSummary,
    EventSummary,
    ExperienceSummary,
    ExperienceSummaryModel,
    LifecycleSummary,
    ProjectSummary,
    ProviderSummary,
    RecommendationSummary,
)

#: 默认最近决策/活动条数 (KISS: Dashboard 不无限增长, CLI --limit 可覆盖)
DEFAULT_RECENT_LIMIT = 10


class ConsoleService:
    """Human Console 只读聚合服务 (依赖注入各 store, 全部可选)。

    构造: 传 None 的依赖在对应查询时按空数据处理 (冷启动/缺装 Console
    照常工作, 失败安全)。典型装配见 cli.commands._open_console_service。
    """

    def __init__(
        self,
        *,
        workspace_manager: Any = None,
        task_store: Any = None,
        agent_registry: Any = None,
        product_store: Any = None,
        decision_store: Any = None,
        recommendation_store: Any = None,
        experience_store: Any = None,
        usage_store: Any = None,
        provider_registry: Any = None,
        event_store: Any = None,
    ) -> None:
        self._workspace = workspace_manager
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._product = product_store
        self._decisions = decision_store
        self._recommendations = recommendation_store
        self._experiences = experience_store
        self._usage = usage_store
        self._providers = provider_registry
        self._events = event_store

    # ------------------------------------------------------------------ 七域 Dashboard

    def dashboard(self, *, recent_limit: int = DEFAULT_RECENT_LIMIT) -> ConsoleDashboard:
        """七域汇总快照 (只读聚合, 失败安全)。

        projects/approvals/agents/decisions/cost/experience/activity 七域
        一次装配; 空工厂 → 全空域, Console 永不因数据缺失失败。
        """
        return ConsoleDashboard(
            projects=self.list_projects(),
            approvals=self.list_approvals(),
            agents=self._agent_summaries(),
            decisions=self.list_recent_decisions(recent_limit),
            cost=self._cost_summary(),
            experience=self._experience_summary(),
            activity=self._recent_events(recent_limit),
        )

    # ------------------------------------------------------------------ GET /projects

    def list_projects(self) -> list[ProjectSummary]:
        """全部项目只读投影 (workspace 项目定义 + 生命周期阶段/任务计数)。"""
        definitions = self._project_definitions()
        tasks = self._tasks_by_project()
        summaries: list[ProjectSummary] = []
        for definition in definitions:
            project_id = definition.id
            lifecycle = self._lifecycle_for_project(project_id)
            summaries.append(
                ProjectSummary(
                    id=project_id,
                    name=definition.name or project_id,
                    description=definition.description,
                    language=definition.language,
                    repository=definition.repository,
                    tech_stack=list(definition.tech_stack or []),
                    status=definition.status,
                    lifecycle_stage=(
                        lifecycle["current_stage"]["name"]
                        if lifecycle and lifecycle.get("current_stage")
                        else None
                    ),
                    lifecycle_status=(
                        (lifecycle.get("lifecycle") or {}).get("status")
                        if lifecycle
                        else None
                    ),
                    pending_approvals=self._pending_approvals_for_project(project_id),
                    tasks=tasks.get(project_id, {}),
                    last_activity=self._project_last_activity(project_id),
                )
            )
        return summaries

    def project_lifecycle(self, project_id: str) -> LifecycleSummary | None:
        """单项目生命周期只读快照; 无生命周期/无项目 → None (404 语义由调用方定)。

        经 idea.context["project"] == project_id 关联 (9d 既有约定); 阶段
        完成清单按 stages 链过滤; next_actions 投影引擎建议 (只读, 不执行)。
        """
        lifecycle = self._lifecycle_for_project(project_id)
        if lifecycle is None:
            return None
        raw = lifecycle["lifecycle"]
        stages = raw.get("stages") or []
        completed = [s["name"] for s in stages if s.get("status") == "completed"]
        return LifecycleSummary(
            project_id=project_id,
            lifecycle_id=raw.get("id"),
            idea_id=raw.get("idea_id"),
            template_name=raw.get("template_name", ""),
            status=raw.get("status", ""),
            current_stage=lifecycle.get("current_stage"),
            completed_stages=completed,
            pending_approval=lifecycle.get("pending_approval"),
            next_actions=lifecycle.get("next_actions") or [],
        )

    # ------------------------------------------------------------------ GET /approvals

    def list_approvals(self) -> list[ApprovalSummary]:
        """全部审批请求只读投影 (9c 状态机, Console 只读不决定)。

        evidence 投影: 审批绑定 Artifact 的决策链证据 (evidence 字段引用
        lineage 字符串, 无 → 空列表); risk 投影: Artifact confidence < 0.5
        时标 medium (低置信度需人工确认信号, 同 9c 审核优先级语义)。
        """
        store = self._product
        if store is None:
            return []
        try:
            requests = store.list_requests()
        except Exception:
            return []  # 损坏 store → 空 (失败安全, 同其余域)
        summaries: list[ApprovalSummary] = []
        for request in requests:
            artifact = store.get_artifact(request.artifact_id) if request.artifact_id else None
            summaries.append(
                ApprovalSummary(
                    id=request.id,
                    artifact_id=request.artifact_id,
                    artifact_type=artifact.type if artifact else "",
                    gate=request.gate,
                    status=request.status,
                    confidence=artifact.confidence if artifact else 0.0,
                    risk="medium" if artifact is not None and artifact.confidence < 0.5 else None,
                    evidence=self._artifact_evidence(artifact),
                    idea_id=request.idea_id,
                    by=request.by,
                    comment=request.comment,
                    requested_at=request.requested_at,
                    artifact_version=request.artifact_version,
                )
            )
        return summaries

    # ------------------------------------------------------------------ GET /decisions/{id}

    def get_decision(self, decision_id: str) -> DecisionSummary | None:
        """单决策只读投影 (AI 推荐产物全链可追溯); 不存在 → None。

        options 投影为引擎产物快照 (id/name/score/factors/reasoning);
        recommendation 评分取推荐选项的 score (无推荐 → 0.0); evidence 投影
        lineage_ref (source_type:source_id, 可审计锚点)。
        """
        store = self._decisions
        if store is None:
            return None
        try:
            decision = store.get(decision_id)
        except Exception:
            return None  # 损坏 store → None (失败安全)
        if decision is None:
            return None
        options = [dict(o) for o in decision.options]
        recommended = next(
            (o for o in decision.options if o["id"] == decision.recommendation), None
        )
        return DecisionSummary(
            id=decision.id,
            decision_type=decision.decision_type,
            subject_id=decision.subject_id,
            description=decision.description,
            status=decision.status.value
            if hasattr(decision.status, "value")
            else str(decision.status),
            options=options,
            recommendation=decision.recommendation,
            score=float(recommended.get("score", 0.0)) if recommended else 0.0,
            confidence=decision.confidence,
            reasoning=self._decision_reasoning(options, decision.recommendation),
            evidence=[e.lineage_ref() for e in decision.evidence],
            risk=decision.risk,
            risk_level=decision.risk_level,
            requires_approval=decision.requires_approval,
            approval_request_id=decision.approval_request_id,
            created_at=decision.created_at,
        )

    def list_recent_decisions(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[DecisionSummary]:
        """最近决策投影 (按 created_at 倒序截断; 无 store → 空)。"""
        store = self._decisions
        if store is None:
            return []
        try:
            decisions = sorted(store.list_all(), key=lambda d: d.created_at, reverse=True)
        except Exception:
            return []  # 损坏 store → 空 (失败安全)
        return [self._decision_summary(d) for d in decisions[: max(limit, 0)]]

    # ------------------------------------------------------------------ GET /recommendations

    def list_recommendations(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[RecommendationSummary]:
        """推荐产物只读投影 (只推荐不执行; 按 created_at 倒序截断)。"""
        store = self._recommendations
        if store is None:
            return []
        recommendations = sorted(store.list_all(), key=lambda r: r.created_at, reverse=True)
        out: list[RecommendationSummary] = []
        for rec in recommendations[: max(limit, 0)]:
            candidate = (
                f"{rec.target_type}:{rec.target_id}"
                if rec.target_type and rec.target_id
                else rec.target_id
            )
            out.append(
                RecommendationSummary(
                    id=rec.id,
                    target_type=rec.target_type,
                    candidate=candidate,
                    score=rec.score,
                    factors=self._recommendation_factors(rec),
                    explanation=list(rec.reasoning),
                    evidence=[e.lineage_ref() for e in rec.evidence],
                    confidence=rec.confidence,
                    risk=rec.risk,
                    created_at=rec.created_at,
                )
            )
        return out

    # ------------------------------------------------------------------ GET /experience

    def list_experience(self, limit: int = DEFAULT_RECENT_LIMIT) -> list[ExperienceSummary]:
        """经验记录只读投影 (六域; 按 created_at 倒序截断)。

        subject = f"{subject_type}:{subject_id}" (统一经验模型定位键);
        freshness = 当前新鲜度 (0-1, 历史经验不永久有效)。
        """
        store = self._experiences
        if store is None:
            return []
        records = sorted(store.list_all(), key=lambda r: r.created_at, reverse=True)
        out: list[ExperienceSummary] = []
        for record in records[: max(limit, 0)]:
            subject_type = record.subject_type or record.domain.value
            out.append(
                ExperienceSummary(
                    id=record.id,
                    domain=record.domain.value,
                    subject=f"{subject_type}:{record.subject_id}",
                    result=record.result.value,
                    score=record.score,
                    confidence=record.confidence,
                    freshness=record.freshness,
                    task_type=record.task_type,
                    capability=list(record.capability),
                    created_at=record.created_at,
                )
            )
        return out

    # ------------------------------------------------------------------ GET /providers

    def list_providers(self) -> list[ProviderSummary]:
        """Provider 目录只读投影 (能力/成本/性能/经验聚合)。

        cost/performance/experience: 从 usage 统计 + experience 记录聚合
        (无数据 → None, 冷启动不臆造 — 与推荐引擎中性分语义一致)。
        """
        registry = self._providers
        if registry is None:
            return []
        usage_by_provider = self._usage_by_provider()
        experience_by_subject = self._experience_by_subject()
        out: list[ProviderSummary] = []
        for definition in registry.list():
            usage = usage_by_provider.get(definition.id)
            records = experience_by_subject.get(definition.id, [])
            out.append(
                ProviderSummary(
                    id=definition.id,
                    name=definition.name,
                    type=definition.type,
                    status=definition.status.value
                    if hasattr(definition.status, "value")
                    else str(definition.status),
                    capabilities=list(definition.capabilities),
                    models=list(definition.models),
                    version=definition.version,
                    cost=self._provider_cost_score(usage, records),
                    performance=self._provider_performance_score(usage),
                    experience=self._provider_experience_score(records),
                    usage_calls=usage.get("calls", 0) if usage else 0,
                )
            )
        return out

    # ------------------------------------------------------------------ 内部: 项目域

    def _project_definitions(self) -> list[Any]:
        """workspace 项目定义 (无 workspace → 空, 失败安全)。"""
        manager = self._workspace
        if manager is None:
            return []
        try:
            return manager.list_projects()
        except Exception:
            return []  # workspace 缺失/损坏 → 空 (Console 永不失败)

    def _lifecycle_for_project(self, project_id: str) -> dict[str, Any] | None:
        """项目关联生命周期快照 (idea.context["project"] == project_id)。

        复用 9d engine.status 形状 (lifecycle/current_stage/pending_approval/
        artifacts/decisions/next_actions); 无 idea/无生命周期 → None。
        """
        store = self._product
        if store is None:
            return None
        try:
            idea_ids = [
                idea.id
                for idea in store.list_ideas()
                if isinstance(idea.context, dict) and idea.context.get("project") == project_id
            ]
        except Exception:
            return None
        if not idea_ids:
            return None
        try:
            from product.lifecycle import ProductLifecycleEngine
            from product.service import ProductService

            engine = ProductLifecycleEngine(store, ProductService(store))
            for idea_id in idea_ids:
                if store.get_lifecycle_by_idea(idea_id) is None:
                    continue
                return engine.status(idea_id)
        except Exception:
            return None
        return None

    def _pending_approvals_for_project(self, project_id: str) -> int:
        """项目维度待审批数 (pending 请求 ∩ 项目 idea 关联)。"""
        store = self._product
        if store is None:
            return 0
        try:
            project_idea_ids = {
                idea.id
                for idea in store.list_ideas()
                if isinstance(idea.context, dict) and idea.context.get("project") == project_id
            }
            return sum(
                1
                for request in store.list_pending_requests()
                if request.idea_id in project_idea_ids
            )
        except Exception:
            return 0

    def _tasks_by_project(self) -> dict[str, dict[str, int]]:
        """任务状态计数 (project → {BACKLOG: n, ...}); 无 task_store → {}。"""
        store = self._task_store
        if store is None:
            return {}
        try:
            out: dict[str, dict[str, int]] = {}
            for task in store.list():
                bucket = out.setdefault(task.project, {})
                status = task.status.value if hasattr(task.status, "value") else str(task.status)
                bucket[status] = bucket.get(status, 0) + 1
            return out
        except Exception:
            return {}

    def _project_last_activity(self, project_id: str) -> str | None:
        """项目维度最近事件时间 (无事件 → None)。"""
        store = self._events
        if store is None:
            return None
        try:
            events = store.query(project_id=project_id, limit=1)
            if not events:
                return None
            from events.models import format_timestamp

            return format_timestamp(events[-1].timestamp)
        except Exception:
            return None

    # ------------------------------------------------------------------ 内部: 审批/证据域

    def _artifact_evidence(self, artifact: Any) -> list[str]:
        """Artifact 证据引用投影 (content.evidence 或 source_events 摘要)。"""
        if artifact is None:
            return []
        evidence: list[str] = []
        content = artifact.content or {}
        if isinstance(content, dict) and isinstance(content.get("evidence"), list):
            evidence.extend(str(e) for e in content["evidence"])
        for event_id in getattr(artifact, "source_events", None) or []:
            evidence.append(f"event:{event_id}")
        return evidence

    # ------------------------------------------------------------------ 内部: 决策域

    def _decision_summary(self, decision: Any) -> DecisionSummary:
        """单决策 → 投影 (get_decision 与 list_recent_decisions 共用)。"""
        options = [dict(o) for o in decision.options]
        recommended = next(
            (o for o in decision.options if o["id"] == decision.recommendation), None
        )
        return DecisionSummary(
            id=decision.id,
            decision_type=decision.decision_type,
            subject_id=decision.subject_id,
            description=decision.description,
            status=decision.status.value
            if hasattr(decision.status, "value")
            else str(decision.status),
            options=options,
            recommendation=decision.recommendation,
            score=float(recommended.get("score", 0.0)) if recommended else 0.0,
            confidence=decision.confidence,
            reasoning=self._decision_reasoning(options, decision.recommendation),
            evidence=[e.lineage_ref() for e in decision.evidence],
            risk=decision.risk,
            risk_level=decision.risk_level,
            requires_approval=decision.requires_approval,
            approval_request_id=decision.approval_request_id,
            created_at=decision.created_at,
        )

    @staticmethod
    def _decision_reasoning(options: list[dict[str, Any]], recommendation: str | None) -> list[str]:
        """推荐解释投影: 推荐选项的 reasoning 逐条复制 (无推荐 → 空)。"""
        for option in options:
            if option.get("id") == recommendation:
                reasoning = option.get("reasoning")
                if isinstance(reasoning, list):
                    return [str(r) for r in reasoning]
                return []
        return []

    def _recommendation_factors(self, rec: Any) -> dict[str, float]:
        """推荐分项投影 (factors dict 宽容解析)。

        factors 数据源宽容读取 rec.factors / rec.basis (模型变体自适应;
        当前 Recommendation 模型无分项字段 → 空 dict, 不臆造)。
        """
        raw = getattr(rec, "factors", None) or getattr(rec, "basis", None) or {}
        if isinstance(raw, dict):
            return {
                str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))
            }
        return {}

    # ------------------------------------------------------------------ 内部: 成本/经验/Provider 域

    def _cost_summary(self) -> CostSummary:
        """成本汇总 (usage 估算计量; 无 usage_store → 空汇总)。"""
        store = self._usage
        if store is None:
            return CostSummary()
        try:
            records = store.list()
        except Exception:
            return CostSummary()
        total_cost = sum(r.estimated_cost for r in records)
        calls = len(records)
        success = sum(1 for r in records if r.success)
        by_provider: dict[str, dict[str, Any]] = {}
        for record in records:
            bucket = by_provider.setdefault(
                record.provider_id,
                {"calls": 0, "total_cost": 0.0, "success_rate": 0.0, "success": 0},
            )
            bucket["calls"] += 1
            bucket["total_cost"] = round(bucket["total_cost"] + record.estimated_cost, 6)
            if record.success:
                bucket["success"] += 1
        for bucket in by_provider.values():
            bucket["success_rate"] = (
                round(bucket["success"] / bucket["calls"], 4) if bucket["calls"] else 0.0
            )
            bucket.pop("success", None)
        return CostSummary(
            total_cost=round(total_cost, 6),
            calls=calls,
            success_rate=round(success / calls, 4) if calls else 0.0,
            avg_cost=round(total_cost / calls, 6) if calls else 0.0,
            total_tokens=sum(r.total_tokens for r in records),
            by_provider=by_provider,
        )

    def _experience_summary(self) -> ExperienceSummaryModel:
        """经验汇总 (六域统计; 无 experience_store → 空汇总)。"""
        store = self._experiences
        if store is None:
            return ExperienceSummaryModel()
        try:
            records = store.list_all()
        except Exception:
            return ExperienceSummaryModel()
        by_domain: dict[str, int] = {}
        success = 0
        score_total = 0.0
        conf_total = 0.0
        for record in records:
            domain = record.domain.value if hasattr(record.domain, "value") else str(record.domain)
            by_domain[domain] = by_domain.get(domain, 0) + 1
            if record.result.value == "success":
                success += 1
            score_total += record.score
            conf_total += record.confidence
        total = len(records)
        return ExperienceSummaryModel(
            total=total,
            by_domain=by_domain,
            success_rate=round(success / total, 4) if total else 0.0,
            avg_score=round(score_total / total, 4) if total else 0.0,
            avg_confidence=round(conf_total / total, 4) if total else 0.0,
        )

    def _agent_summaries(self) -> list[AgentSummary]:
        """Agent 运行投影 (全量, 状态过滤在 Dashboard 派生属性)。"""
        registry = self._agent_registry
        if registry is None:
            return []
        try:
            agents = registry.list()
        except Exception:
            return []
        out: list[AgentSummary] = []
        for agent in agents:
            out.append(
                AgentSummary(
                    id=agent.id,
                    name=agent.name,
                    role=agent.role,
                    status=agent.status.value,
                    skills=list(agent.skills),
                    current_task=agent.current_task,
                )
            )
        return out

    def _recent_events(self, limit: int) -> list[EventSummary]:
        """最近事件活动投影 (事件审计流; 无 event_store → 空)。"""
        store = self._events
        if store is None:
            return []
        try:
            events = store.query(limit=max(limit, 0))
        except Exception:
            return []
        out: list[EventSummary] = []
        for event in events:
            from events.models import format_timestamp

            out.append(
                EventSummary(
                    seq=event.seq,
                    type=event.type.value,
                    timestamp=format_timestamp(event.timestamp),
                    source=event.source,
                    project_id=event.project_id,
                    task_id=event.task_id,
                    action=event.action,
                    result=event.result,
                )
            )
        return out

    def _usage_by_provider(self) -> dict[str, dict[str, Any]]:
        """usage 按 Provider 聚合 (calls/total_cost/success_rate; 失败安全)。"""
        store = self._usage
        if store is None:
            return {}
        try:
            records = store.list()
        except Exception:
            return {}
        out: dict[str, dict[str, Any]] = {}
        for record in records:
            bucket = out.setdefault(
                record.provider_id, {"calls": 0, "total_cost": 0.0, "success": 0}
            )
            bucket["calls"] += 1
            bucket["total_cost"] = round(bucket["total_cost"] + record.estimated_cost, 6)
            if record.success:
                bucket["success"] += 1
        for bucket in out.values():
            bucket["success_rate"] = (
                round(bucket["success"] / bucket["calls"], 4) if bucket["calls"] else 0.0
            )
            bucket.pop("success", None)
        return out

    def _experience_by_subject(self) -> dict[str, list[Any]]:
        """经验记录按 subject_id 分组 (Provider 经验聚合输入; 失败安全)。"""
        store = self._experiences
        if store is None:
            return {}
        try:
            records = store.list_all()
        except Exception:
            return {}
        out: dict[str, list[Any]] = {}
        for record in records:
            out.setdefault(record.subject_id, []).append(record)
        return out

    @staticmethod
    def _provider_cost_score(usage: dict[str, Any] | None, records: list[Any]) -> float | None:
        """成本效益分 (0-1, 高 = 单位产出成本低)。

        avg_cost 越低越好 → 1/(1+avg_cost) 归一 (0 成本 → 1.0; 无 usage →
        None 不臆造); 经验记录的 cost 分 (0-1) 补充均值。
        """
        if not usage and not records:
            return None
        cost_parts: list[float] = []
        if usage and usage.get("calls"):
            avg = float(usage["total_cost"]) / float(usage["calls"])
            cost_parts.append(1.0 / (1.0 + avg))
        for record in records:
            if record.cost is not None:
                cost_parts.append(float(record.cost))
        if not cost_parts:
            return None
        return round(sum(cost_parts) / len(cost_parts), 4)

    @staticmethod
    def _provider_performance_score(usage: dict[str, Any] | None) -> float | None:
        """性能分 (0-1): success_rate 为主 (usage 调用成功率); 无 usage → None。"""
        if not usage or not usage.get("calls"):
            return None
        return round(float(usage["success_rate"]), 4)

    @staticmethod
    def _provider_experience_score(records: list[Any]) -> float | None:
        """经验分 (0-1): 记录 score×confidence×freshness 均值 (正负经验语义,
        同 ExperienceAnalyzer 聚合; 无记录 → None 冷启动不臆造)。"""
        if not records:
            return None
        from intelligence.experience import aggregate_experience_factor

        try:
            return round(aggregate_experience_factor(records), 4)
        except Exception:
            return None


__all__ = ["ConsoleService", "DEFAULT_RECENT_LIMIT"]
