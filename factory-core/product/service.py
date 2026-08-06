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

状态机 (9a 骨架 + 9c 完整状态机, ADR-0028):
- ApprovalRequest: pending → approved | rejected | changes_requested | delegated
  (终态可逆: rejected/changes_requested/delegated 后可重新提交新请求; approved
  仅当 Artifact version 递增才需重新审批 — 禁覆盖历史)。输入 "denied" 为 9a
  遗留别名 → rejected (兼容 9a CLI deny 动词与旧调用)。
- ProductWorkflow: running ↔ paused (9a awaiting_approval 细化); approval 申请 →
  paused; 终态决定 → running (approved 额外推进 current_stage + 记录
  product_decision + approval.resumed; rejected/changes_requested 停留当前 stage
  进入修改流程); 手动 workflow_resume 同款恢复 (approval.resumed, reason=manual)。
- ProductWorkflow 不绑定 PRD/UI: stages 为声明式列表, 门按 Artifact type 匹配

Phase 9c 新增 (Human Decision Intelligence, ADR-0028):
- Artifact Version: revise_artifact (v1 → v2 新 Artifact, supersedes 指向前版,
  禁覆盖历史) + artifact_version_history; ApprovalRequest.artifact_version 绑定
  申请时点版本 — 新 version 需重新审批。
- Approval Queue: approval_queue (request + artifact type/version/confidence +
  required_action) + list_approvals(status=...) 过滤。
- Approval History: approval_history (request + decision 联表)。
- 事件 (经 EventLogger): approval.created/pending 申请时, approved/rejected/
  changes_requested/delegated 终态时, approval.resumed 工作流恢复时; 9a 既有
  approval.required/granted/denied 保留 (兼容语义映射, ADR-0028 决策 1)。
"""

from __future__ import annotations

import re
from typing import Any

from .events import (
    record_approval_approved,
    record_approval_changes_requested,
    record_approval_created,
    record_approval_delegated,
    record_approval_denied,
    record_approval_granted,
    record_approval_pending,
    record_approval_rejected,
    record_approval_required,
    record_approval_resumed,
    record_idea_created,
    record_workflow_started,
)
from .models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
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

#: Phase 9c 状态机: 合法终态决策值 (decide_approval 输入, 大小写不敏感)。
#: "denied" 为 9a 遗留输入别名 → rejected (兼容 9a CLI deny 动词与旧调用)。
VALID_DECISIONS: tuple[str, ...] = (
    "approved", "rejected", "changes_requested", "delegated",
)
DECISION_ALIASES: dict[str, str] = {"denied": "rejected"}


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


def _required_action(status: str) -> str:
    """Approval Queue 的 required action (通用决策系统 — 人工下一步动作提示)。

    pending → decide (待人工决定); approved → none (已通过);
    rejected/changes_requested (含 9a 遗留 denied) → revise & re-request
    (修改后重新审批, 终态可逆); delegated → await delegate (待被转派人决定)。
    """
    if status == ApprovalStatus.PENDING.value:
        return "decide"
    if status == ApprovalStatus.APPROVED.value:
        return "none"
    if status == ApprovalStatus.DELEGATED.value:
        return "await delegate"
    return "revise & re-request"  # rejected / changes_requested / denied (遗留)


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
        version: int | None = None,
    ) -> Artifact:
        """创建任意类型 Artifact (AI Artifact Lineage: provider/agent/source_events)。

        9a 骨架的通用写入口 (CLI 未暴露, 供 9b Provider 生成与测试使用);
        idea_id 非空时写入 content.idea_id (workflow 联动锚点, 同 idea 约定)。
        version (Phase 9b, ADR-0027): 重生成版本覆盖 (None → 1, 既有调用零
        影响 — 同 idea 同类型产物的版本递增由 ProductGenerator._next_version
        负责, Lineage \"每次重生成 +1\" 语义)。
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
            version=version if version is not None else 1,
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

        流程 (phase9-plan §4 + 9c 状态机): 落 pending 请求 (artifact_version
        快照绑定) → approval.created → approval.pending → approval.required (9a
        兼容) → 关联 workflow (若有) 进入 paused (未批准不自动推进)。

        Phase 9c 队列守卫 (通用决策系统 — 禁重复申请/禁覆盖历史):
        - 同 Artifact 已有 pending 请求 → ProductError (重复申请)。
        - 同 Artifact 同 version 已 approved → ProductError (需 v2 重新审批)。
        - rejected/changes_requested/delegated 终态 → 允许重新提交 (终态可逆)。
        """
        artifact = self.get_artifact(artifact_id)
        gate = self.get_or_create_gate(gate_id or artifact.type)
        self._guard_request_duplicate(artifact)
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
            artifact_version=artifact.version,
        )
        self._store.save_request(request)
        record_approval_created(self._logger, request=request, gate=gate, artifact=artifact)
        record_approval_pending(self._logger, request=request, gate=gate, artifact=artifact)
        record_approval_required(self._logger, request=request, gate=gate, artifact=artifact)  # 9a 兼容
        self._pause_workflow_for(idea)
        return request

    def _guard_request_duplicate(self, artifact: Artifact) -> None:
        """审批队列唯一性守卫: 同 artifact pending 或同 version approved 拒重复申请。

        终态可逆: rejected/changes_requested/delegated (含 9a 遗留 denied) 后可
        重新提交 (同 version 允许再申请); approved 仅 version 递增后可再申请。
        """
        for existing in self._store.list_requests():
            if existing.artifact_id != artifact.id:
                continue
            if existing.status == ApprovalStatus.PENDING.value:
                raise ProductError(
                    f"approval already pending for artifact {artifact.id} "
                    f"(request {existing.id})"
                )
            if (
                existing.status == ApprovalStatus.APPROVED.value
                and existing.artifact_version == artifact.version
            ):
                raise ProductError(
                    f"artifact {artifact.id} version {artifact.version} already approved "
                    f"(request {existing.id}); revise to a new version and re-approve"
                )

    def decide_approval(
        self,
        request_id: str,
        decision: str,
        *,
        by: str = "human",
        comment: str = "",
    ) -> tuple[ApprovalRequest, ApprovalDecision, Artifact | None]:
        """审批决定 (9c 状态机): pending → approved | rejected | changes_requested | delegated。

        - approved: approval.approved + approval.granted (9a 兼容) + Product
          Decision Artifact (source_events 锚定 granted 事件, Lineage 闭环) +
          workflow 恢复并推进下一 stage (approval.resumed, reason=approved)。
        - rejected: approval.rejected + approval.denied (9a 兼容) + workflow 恢复
          停留当前 stage (进入修改流程, approval.resumed, reason=rejected)。
        - changes_requested: approval.changes_requested + workflow 恢复 (修改后
          重新审批); delegated: approval.delegated + workflow 恢复 (待被转派人决定)。
        - 输入 "denied" (9a 遗留) → rejected (状态机终态值映射, ADR-0028)。
        终态不可重复 decide (重复决定抛错); 终态可逆 = 重新提交新请求。
        """
        request = self._store.get_request(request_id)
        if request is None:
            raise ProductNotFoundError(f"approval request not found: {request_id}")
        if request.status != ApprovalStatus.PENDING.value:
            raise ProductError(f"approval request {request_id} already {request.status}")
        decision_value = decision.lower()
        if decision_value in DECISION_ALIASES:
            decision_value = DECISION_ALIASES[decision_value]  # denied → rejected (9a 兼容)
        if decision_value not in VALID_DECISIONS:
            raise ProductError(
                f"invalid approval decision: {decision!r} "
                f"(expected approved|rejected|changes_requested|delegated)"
            )

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
            record_approval_approved(
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
            ev = record_approval_granted(  # 9a 兼容 (Product Decision 锚点)
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
            decision_artifact = self._make_product_decision(request2, decision_record, artifact, ev)
            self._store.save_artifact(decision_artifact)  # Product Decision 落库 (Artifact 抽象)
            self._advance_workflow_for(request.idea_id, decision_artifact.id)
            return request2, decision_record, decision_artifact
        if decision_value == "rejected":
            record_approval_rejected(
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
            record_approval_denied(  # 9a 兼容 (语义映射 denied → rejected)
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
        elif decision_value == "changes_requested":
            record_approval_changes_requested(
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
        else:  # delegated
            record_approval_delegated(
                self._logger, request=request2, decision=decision_record, artifact=artifact
            )
        self._resume_workflow_for(request.idea_id, reason=decision_value)
        return request2, decision_record, None

    def list_approvals(
        self,
        pending_only: bool = False,
        status: str | None = None,
    ) -> list[ApprovalRequest]:
        """审批请求清单 (pending_only=True 只列待办; status 按终态值过滤)。

        Phase 9c: --status 过滤 (Approval Queue); "denied" (9a 遗留) → rejected
        归一 (状态机语义映射)。
        """
        requests = self._store.list_requests()
        if status is not None:
            status_value = DECISION_ALIASES.get(status.lower(), status.lower())
            requests = [r for r in requests if r.status == status_value]
        if pending_only:
            requests = [r for r in requests if r.status == ApprovalStatus.PENDING.value]
        return requests

    def get_approval_request(self, request_id: str) -> ApprovalRequest:
        """按 id 取审批请求; 不存在 → ProductNotFoundError。"""
        request = self._store.get_request(request_id)
        if request is None:
            raise ProductNotFoundError(f"approval request not found: {request_id}")
        return request

    # ------------------------------------------------------------------ Approval Queue / History (Phase 9c)

    def approval_queue(self, status: str | None = None) -> list[dict[str, Any]]:
        """待审核队列 (通用决策系统): request + artifact 上下文 + required_action。

        每行 = ApprovalRequest dict 扩展 artifact_type/artifact_version/confidence
        (来自 Artifact 只读联表; artifact 缺失 → None/0.0 失败安全) +
        required_action (pending → decide; approved → none; rejected/
        changes_requested → revise & re-request; delegated → await delegate)。
        """
        rows: list[dict[str, Any]] = []
        for request in self.list_approvals(status=status):
            artifact = self._store.get_artifact(request.artifact_id)
            rows.append({
                **request.to_dict(),
                "artifact_type": artifact.type if artifact is not None else None,
                "artifact_version": (
                    artifact.version if artifact is not None else request.artifact_version
                ),
                "confidence": artifact.confidence if artifact is not None else 0.0,
                "required_action": _required_action(request.status),
            })
        return rows

    def approval_history(self, artifact_id: str) -> list[dict[str, Any]]:
        """Artifact 审批历史: 全部请求 (按 requested_at 升序) + 决定记录联表。

        artifact 不存在 → ProductNotFoundError; 无请求 → 空列表。
        """
        self.get_artifact(artifact_id)
        decisions = {d.request_id: d for d in self._store.list_decisions()}
        rows: list[dict[str, Any]] = []
        for request in self._store.list_requests():
            if request.artifact_id != artifact_id:
                continue
            row = request.to_dict()
            decision = decisions.get(request.id)
            row["decision"] = decision.to_dict() if decision is not None else None
            rows.append(row)
        return rows

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

    def workflow_resume(self, idea_id: str) -> ProductWorkflow:
        """手动恢复暂停的工作流 (Phase 9c): paused → running, 停留当前 stage。

        发 approval.resumed (reason=manual); 未暂停 (running/completed/failed) →
        ProductError; 无工作流 → ProductNotFoundError。通用决策系统的恢复入口:
        审批终态 (rejected/changes_requested) 后用户决定不重审直接推进时使用。
        """
        workflow = self.workflow_status(idea_id)  # 无工作流 → ProductNotFoundError
        if workflow.status not in (
            WorkflowStatus.PAUSED.value,
            WorkflowStatus.AWAITING_APPROVAL.value,  # 9a 遗留
        ):
            raise ProductError(
                f"workflow for idea {idea_id} is not paused (status: {workflow.status})"
            )
        updated = workflow.model_copy(update={"status": WorkflowStatus.RUNNING.value})
        self._store.save_workflow(updated)
        record_approval_resumed(self._logger, workflow=updated, reason="manual")
        return updated

    # ------------------------------------------------------------------ Artifact Version (Phase 9c)

    def revise_artifact(
        self,
        artifact_id: str,
        content: dict[str, Any] | None = None,
        *,
        by: str = "human",
        provider_id: str | None = None,
        agent_id: str | None = None,
        source_events: list[str] | None = None,
        confidence: float | None = None,
        status: str = "revised",
        note: str | None = None,
    ) -> Artifact:
        """修改 Artifact → 新版本 (禁覆盖历史): v1 → v2 新 Artifact (supersedes=v1)。

        Artifact 不可变 (id 即版本身份): revise 产出**新 id** 的 Artifact
        (version = 前版 +1, Lineage 继承 provider/agent/source_events/confidence,
        supersedes 指向前版), 旧版本原样保留 (versioned store — 历史可追溯)。
        content 为增量更新 (旧 content 之上覆盖, idea_id 锚点自然保留)。
        v2 需重新审批: request_approval 的 artifact_version 守卫拒绝\"同版本
        重复批准\", 新版本申请走全新 pending 流程。
        """
        old = self.get_artifact(artifact_id)
        new_content = dict(old.content)
        new_content.update(dict(content or {}))
        if note is not None:
            new_content["revision_note"] = note
        artifact = Artifact(
            id=_next_id("ART", self._store.list_artifacts()),
            type=old.type,
            content=new_content,
            status=status,
            created_by=by,
            provider_id=provider_id if provider_id is not None else old.provider_id,
            agent_id=agent_id if agent_id is not None else old.agent_id,
            source_events=list(source_events or old.source_events),
            version=old.version + 1,
            confidence=confidence if confidence is not None else old.confidence,
            supersedes=old.id,
        )
        self._store.save_artifact(artifact)
        return artifact

    def artifact_version_history(self, artifact_id: str) -> list[Artifact]:
        """Artifact 版本链历史 (禁覆盖历史): 同 idea 同类型全部版本, 按 version 升序。

        无 idea 锚点 (content.idea_id 缺失) → 仅自身 (KISS: 无法归族)。返回的
        首条即 v1, 末条为当前版本 — 与 approval 绑定 (artifact_version) 对照
        即可还原\"哪个版本经哪次审批\"。
        """
        artifact = self.get_artifact(artifact_id)
        idea_id = (
            artifact.content.get("idea_id") if isinstance(artifact.content, dict) else None
        )
        if idea_id is None:
            return [artifact]
        chain = [
            a for a in self._store.list_artifacts()
            if a.type == artifact.type
            and isinstance(a.content, dict)
            and a.content.get("idea_id") == idea_id
        ]
        return sorted(chain, key=lambda a: a.version)

    # ------------------------------------------------------------------ 内部 (workflow 联动)

    def _pause_workflow_for(self, idea_id: str | None) -> None:
        """approval.required → 关联 workflow 进入 paused (暂停不推进; 9a
        awaiting_approval 细化 — 仅 running 可暂停, 非 running 不动)。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is not None and workflow.status == WorkflowStatus.RUNNING.value:
            updated = workflow.model_copy(update={"status": WorkflowStatus.PAUSED.value})
            self._store.save_workflow(updated)

    def _advance_workflow_for(self, idea_id: str | None, decision_artifact_id: str) -> None:
        """approved → workflow 回 running + 推进 current_stage + 记录 product_decision
        + approval.resumed (reason=approved)。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is None or workflow.status not in (
            WorkflowStatus.PAUSED.value,
            WorkflowStatus.AWAITING_APPROVAL.value,  # 9a 遗留
        ):
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
        record_approval_resumed(self._logger, workflow=updated, reason="approved")

    def _resume_workflow_for(self, idea_id: str | None, *, reason: str = "rejected") -> None:
        """终态非批准 (rejected/changes_requested/delegated) → workflow 回 running
        (进入修改流程, 停留当前 stage) + approval.resumed。"""
        if idea_id is None:
            return
        workflow = self._store.get_workflow_by_idea(idea_id)
        if workflow is not None and workflow.status in (
            WorkflowStatus.PAUSED.value,
            WorkflowStatus.AWAITING_APPROVAL.value,  # 9a 遗留
        ):
            updated = workflow.model_copy(update={"status": WorkflowStatus.RUNNING.value})
            self._store.save_workflow(updated)
            record_approval_resumed(self._logger, workflow=updated, reason=reason)

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
