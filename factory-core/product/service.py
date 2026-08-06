"""factory-core/product/service.py — ProductService: 产品智能层编排 (Idea/Artifact/Approval/Workflow)。

设计依据:
- phase9-plan.md §2/§4/§5 (数据模型 + Approval Gate 流程 + Extension 边界):
  Idea 创建即落 product_idea Artifact (Artifact 抽象 — 任何 Artifact 可申请
  审批); request_approval → approval.required (workflow → awaiting_approval);
  decide_approval granted → approval.granted + Product Decision Artifact +
  workflow 推进下一 stage; denied → approval.denied + workflow 回 running
  (回退重生成, 记录 comment)。
- phase9a-status.md 5 点约束: Artifact 抽象 / Approval Gate 抽象 / AI Artifact
  Lineage (source_events 记录生成事件链) / Confidence Model / Product Workflow
  解耦 (Product Decision Artifact)。
- 事件边界: 服务层经注入的 EventLogger 发写路径事件 (source="product");
  logger 为 None 时全部静默 (同 understanding/service.py 模式)。读命令审计
  (idea.viewed / approval.viewed / product.workflow.status_viewed) 由 CLI 命令层
  发出 (source="cli", ADR-0002)。
- 无 Database/Web API (phase9a-status 范围): 纯本地 JSON store + 事件审计。
- ID 生成: 前缀 + 3 位序号 (PI-001/ART-001/APR-001/APD-001/PW-001, 同任务/执行风格)。

状态机 (本阶段骨架):
- ApprovalRequest: pending → approved | denied (终态不可逆, 重复 decide 抛错)
- ProductWorkflow: running ↔ awaiting_approval (approval.required 进入 /
  granted|denied 退出); granted 额外推进 current_stage + 记录 product_decision
- ProductWorkflow 不绑定 PRD/UI: stages 为声明式列表, 门按 Artifact type 匹配
"""

from __future__ import annotations

import re
from typing import Any

from .events import (
    record_approval_denied,
    record_approval_granted,
    record_approval_required,
    record_idea_created,
    record_workflow_started,
)
from .models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    Artifact,
    ProductIdea,
    ProductWorkflow,
    WorkflowStatus,
    _now,
)
from .store import ProductStore

#: 产品工作流默认阶段链 (9d 编排前的骨架声明; start_workflow 可覆盖)
DEFAULT_STAGES: list[str] = ["research", "prd", "ui", "architecture", "tasks"]

#: 默认审批门 (id == artifact_type): PRD/UI mandatory (阻塞推进), Architecture
#: recommended (可跳过记录) — phase9-plan §4; 门不绑定这三类: 任意 Artifact
#: 可经 request_approval(artifact_id, gate_id=...) 或自定义门申请。
DEFAULT_GATES: dict[str, tuple[str, str]] = {
    "prd": ("mandatory", "PRD 必须经人工批准后才能进入 UI 设计 (阻塞推进)"),
    "ui": ("mandatory", "UI 设计必须经人工批准后才能进入架构设计 (阻塞推进)"),
    "architecture": ("recommended", "架构设计建议经人工批准 (recommended, 可跳过记录)"),
}


class ProductError(Exception):
    """产品层业务错误 (CLI 映射 → 退出码 1)。"""


class ProductNotFoundError(ProductError):
    """实体不存在 (CLI 映射 → 退出码 7, 同 task not found)。"""


def _next_id(prefix: str, existing: list[Any]) -> str:
    """前缀 + 3 位序号 (PI-001 → PI-002): 取现有最大序号 +1, 空库从 001 起。"""
    max_n = 0
    for record in existing:
        m = re.search(rf"{re.escape(prefix)}-(\d+)$", record.id)  # type: ignore[attr-defined]
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{max_n + 1:03d}"


class ProductService:
    """产品智能层服务 (store 持久化 + 可选 logger 事件审计)。

    create_idea → ProductIdea + product_idea Artifact (Idea 即 Artifact);
    request_approval/decide_approval → Approval 状态机 + Product Decision;
    start_workflow/workflow_status → ProductWorkflow 骨架。
    """

    def __init__(self, store: ProductStore, logger: Any = None) -> None:
        self._store = store
        self._logger = logger

    # ------------------------------------------------------------------ Ideas

    def create_idea(
        self,
        title: str,
        description: str = "",
        *,
        goals: list[str] | None = None,
        context: dict[str, Any] | None = None,
        created_by: str = "human",
    ) -> ProductIdea:
        """创建想法: 落库 ProductIdea + product_idea Artifact (Artifact 抽象)。

        Idea 即 Artifact: artifact.content.idea_id 记录关联 — 后续任何阶段产物
        均可沿此锚点关联工作流 (approval 联动)。发 idea.created (source=product)。
        """
        idea = ProductIdea(
            id=_next_id("PI", self._store.list_ideas()),
            title=title,
            description=description or "",
            goals=list(goals or []),
            context=dict(context or {}),
        )
        artifact = Artifact(
            id=_next_id("ART", self._store.list_artifacts()),
            type="product_idea",
            content={"idea_id": idea.id, "title": idea.title, "description": idea.description},
            status="created",
            created_by=created_by,
        )
        self._store.save_idea(idea)
        self._store.save_artifact(artifact)
        record_idea_created(self._logger, idea=idea, artifact=artifact)
        return idea

    def list_ideas(self) -> list[ProductIdea]:
        """全部想法 (按 id 排序)。"""
        return self._store.list_ideas()

    def get_idea(self, idea_id: str) -> ProductIdea:
        """按 id 取想法; 不存在 → ProductNotFoundError。"""
        idea = self._store.get_idea(idea_id)
        if idea is None:
            raise ProductNotFoundError(f"idea not found: {idea_id}")
        return idea

    # ------------------------------------------------------------------ Artifacts

    def create_artifact(
        self,
        artifact_type: str,
        content: dict[str, Any] | None = None,
        *,
        created_by: str = "human",
        provider_id: str | None = None,
        agent_id: str | None = None,
        source_events: list[str] | None = None,
        confidence: float = 0.0,
        status: str = "created",
        idea_id: str | None = None,
    ) -> Artifact:
        """创建任意类型 Artifact (AI Artifact Lineage: provider/agent/source_events)。

        9a 骨架的通用写入口 (CLI 未暴露, 供 9b Provider 生成与测试使用);
        idea_id 非空时写入 content.idea_id (workflow 联动锚点, 同 idea 约定)。
        """
        content = dict(content or {})
        if idea_id is not None:
            content["idea_id"] = idea_id
        artifact = Artifact(
            id=_next_id("ART", self._store.list_artifacts()),
            type=artifact_type,
            content=content,
            status=status,
            created_by=created_by,
            provider_id=provider_id,
            agent_id=agent_id,
            source_events=list(source_events or []),
            confidence=confidence,
        )
        self._store.save_artifact(artifact)
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact:
        """按 id 取 Artifact; 不存在 → ProductNotFoundError。"""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            raise ProductNotFoundError(f"artifact not found: {artifact_id}")
        return artifact

    def list_artifacts(self, artifact_type: str | None = None) -> list[Artifact]:
        """全部 Artifact (可按 type 过滤)。"""
        if artifact_type is None:
            return self._store.list_artifacts()
        return self._store.list_artifacts_by_type(artifact_type)

    def get_artifact_by_idea(self, idea_id: str) -> Artifact | None:
        """取想法的 product_idea Artifact (Idea 即 Artifact 约定); 无 → None。"""
        for artifact in self._store.list_artifacts_by_type("product_idea"):
            if artifact.content.get("idea_id") == idea_id:
                return artifact
        return None

    # ------------------------------------------------------------------ Approval Gate

    def get_or_create_gate(self, artifact_type: str) -> ApprovalGate:
        """取门 (id == artifact_type); 默认门缺失时按 DEFAULT_GATES 落库注册。

        任何 Artifact 类型都可申请: 类型在 DEFAULT_GATES 中 → 自动建门;
        否则须先 save_gate 注册自定义门 (service 层抛 ProductError 提示)。
        """
        gate = self._store.get_gate(artifact_type)
        if gate is not None:
            return gate
        defaults = DEFAULT_GATES.get(artifact_type)
        if defaults is None:
            raise ProductError(
                f"no approval gate for artifact type {artifact_type!r} "
                f"(pass --gate or register a gate first; defaults: {', '.join(DEFAULT_GATES)})"
            )
        gate = ApprovalGate(
            id=artifact_type, artifact_type=artifact_type,
            required=defaults[0], rule=defaults[1],
        )
        self._store.save_gate(gate)
        return gate

    def request_approval(
        self,
        artifact_id: str,
        gate_id: str | None = None,
        *,
        by: str = "human",
        note: str | None = None,
        idea_id: str | None = None,
    ) -> ApprovalRequest:
        """申请审批: 任何 Artifact 可申请 (门按 gate_id 或 artifact.type 解析)。

        流程 (phase9-plan §4): 落 pending 请求 → approval.required → 关联
        workflow (若有) 进入 awaiting_approval (未批准不自动推进)。
        """
        artifact = self.get_artifact(artifact_id)
        gate = self.get_or_create_gate(gate_id or artifact.type)
        idea = idea_id or (
            artifact.content.get("idea_id") if isinstance(artifact.content, dict) else None
        )
        request = ApprovalRequest(
            id=_next_id("APR", self._store.list_requests()),
            artifact_id=artifact.id,
            gate=gate.id,
            idea_id=idea,
            by=by,
            comment=note,
        )
        self._store.save_request(request)
        record_approval_required(self._logger, request=request, gate=gate, artifact=artifact)
        self._pause_workflow_for(idea)
        return request

    def decide_approval(
        self,
        request_id: str,
        decision: str,
        *,
        by: str = "human",
        comment: str = "",
    ) -> tuple[ApprovalRequest, ApprovalDecision, Artifact | None]:
        """审批决定: pending → approved|denied (终态不可逆)。

        approved: approval.granted + Product Decision Artifact (source_events 锚定
        granted 事件, Lineage 闭环) + workflow 推进下一 stage + product_decision
        回填; denied: approval.denied + workflow 回 running (回退重生成)。
        """
        request = self._store.get_request(request_id)
        if request is None:
            raise ProductNotFoundError(f"approval request not found: {request_id}")
        if request.status != "pending":
            raise ProductError(f"approval request {request_id} already {request.status}")
        decision_value = decision.lower()
        if decision_value not in ("approved", "denied"):
            raise ProductError(f"invalid approval decision: {decision!r} (expected approved|denied)")

        decided_at = _now()
        request2 = request.model_copy(
            update={
                "status": decision_value,
                "decided_by": by,
                "decided_at": decided_at,
                "comment": comment,
            }
        )
        self._store.save_request(request2)
        decision_record = ApprovalDecision(
            id=_next_id("APD", self._store.list_decisions()),
            request_id=request.id,
            decision=decision_value,
            decided_by=by,
            comment=comment or "",
            decided_at=decided_at,
        )
        self._store.save_decision(decision_record)
        artifact = self._store.get_artifact(request.artifact_id)

        if decision_value == "approved":
            ev = record_approval_granted(
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
            decision_artifact = self._make_product_decision(request2, decision_record, artifact, ev)
            self._store.save_artifact(decision_artifact)  # Product Decision 落库 (Artifact 抽象)
            self._advance_workflow_for(request.idea_id, decision_artifact.id)
            return request2, decision_record, decision_artifact
        record_approval_denied(
            self._logger, request=request2, decision=decision_record, artifact=artifact
        )
        self._resume_workflow_for(request.idea_id)
        return request2, decision_record, None

    def list_approvals(self, pending_only: bool = False) -> list[ApprovalRequest]:
        """审批请求清单 (pending_only=True 只列待办)。"""
        if pending_only:
            return self._store.list_pending_requests()
        return self._store.list_requests()

    def get_approval_request(self, request_id: str) -> ApprovalRequest:
        """按 id 取审批请求; 不存在 → ProductNotFoundError。"""
        request = self._store.get_request(request_id)
        if request is None:
            raise ProductNotFoundError(f"approval request not found: {request_id}")
        return request

    # ------------------------------------------------------------------ Workflow

    def start_workflow(
        self, idea_id: str, stages: list[str] | None = None,
    ) -> ProductWorkflow:
        """启动产品工作流 (一个 idea 至多一个 run): 发 product.workflow.started。

        骨架: stages 默认 DEFAULT_STAGES, current_stage = 首阶段, status running。
        """
        self.get_idea(idea_id)  # 想法须存在
        if self._store.get_workflow_by_idea(idea_id) is not None:
            raise ProductError(f"workflow already started for idea {idea_id}")
        stages = list(stages or DEFAULT_STAGES)
        workflow = ProductWorkflow(
            id=_next_id("PW", self._store.list_workflows()),
            idea_id=idea_id,
            stages=stages,
            current_stage=stages[0] if stages else "",
            status=WorkflowStatus.RUNNING.value,
        )
        self._store.save_workflow(workflow)
        record_workflow_started(self._logger, workflow=workflow)
        return workflow

    def workflow_status(self, idea_id: str) -> ProductWorkflow:
        """工作流当前状态; 无工作流 → ProductNotFoundError (CLI 退出码 7)。"""
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is None:
            raise ProductNotFoundError(f"no product workflow for idea {idea_id}")
        return workflow

    # ------------------------------------------------------------------ 内部 (workflow 联动)

    def _pause_workflow_for(self, idea_id: str | None) -> None:
        """approval.required → 关联 workflow 进入 awaiting_approval (暂停不推进)。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is not None and workflow.status == WorkflowStatus.RUNNING.value:
            updated = workflow.model_copy(update={"status": WorkflowStatus.AWAITING_APPROVAL.value})
            self._store.save_workflow(updated)

    def _advance_workflow_for(self, idea_id: str | None, decision_artifact_id: str) -> None:
        """granted → workflow 回 running + 推进 current_stage + 记录 product_decision。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is None or workflow.status != WorkflowStatus.AWAITING_APPROVAL.value:
            return
        idx = workflow.stages.index(workflow.current_stage) if workflow.current_stage in workflow.stages else -1
        next_stage = workflow.stages[idx + 1] if 0 <= idx < len(workflow.stages) - 1 else workflow.current_stage
        updated = workflow.model_copy(
            update={
                "status": WorkflowStatus.RUNNING.value,
                "current_stage": next_stage,
                "product_decision": decision_artifact_id,
            }
        )
        self._store.save_workflow(updated)

    def _resume_workflow_for(self, idea_id: str | None) -> None:
        """denied → workflow 回 running (回退重生成, 停留在当前 stage)。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is not None and workflow.status == WorkflowStatus.AWAITING_APPROVAL.value:
            updated = workflow.model_copy(update={"status": WorkflowStatus.RUNNING.value})
            self._store.save_workflow(updated)

    def _make_product_decision(
        self,
        request: ApprovalRequest,
        decision: ApprovalDecision,
        artifact: Artifact | None,
        event: Any,
    ) -> Artifact:
        """Product Decision Artifact (约束 5): 经 Approval 后产生的决策产物。

        Lineage 闭环: provider_id/confidence 继承自被审批 Artifact;
        source_events 锚定 approval.granted 事件 event_id。
        """
        return Artifact(
            id=_next_id("ART", self._store.list_artifacts()),
            type="product_decision",
            content={
                "request_id": request.id,
                "artifact_id": request.artifact_id,
                "gate": request.gate,
                "decision": decision.decision,
                "comment": decision.comment,
                "idea_id": request.idea_id,
            },
            status="approved",
            created_by=decision.decided_by,
            provider_id=artifact.provider_id if artifact is not None else None,
            agent_id=artifact.agent_id if artifact is not None else None,
            source_events=[event.event_id] if event is not None else [],
            confidence=artifact.confidence if artifact is not None else 0.0,
        )
