"""factory-core/product/models.py — Product Intelligence 领域模型 (Pydantic v2)。

设计依据:
- phase9-plan.md §2 (数据模型) + phase9a-status.md 5 点架构约束:
  1. **Artifact 抽象**: 基础模型 id/type/content/status/created_by/provider_id/
     agent_id/source_events/version/confidence/created_at — 未来多类型
     (Product/Research/PRD/UI/Architecture/Deployment/Operation) 均落在此抽象上,
     本阶段只实现 product_idea + product_decision 两种 (Approval 不绑定 PRD/UI:
     任何 Artifact 可申请)。
  2. **Approval Gate 抽象**: ApprovalGate/ApprovalRequest/ApprovalDecision 三模型,
     任何 Artifact 类型都可走审批 (默认门: prd/ui mandatory, architecture
     recommended — 见 service.DEFAULT_GATES)。
  3. **AI Artifact Lineage**: source_events (生成事件链 event_id 列表) +
     provider_id/agent_id + version (每次重生成 +1) — Input→Agent→Provider→
     Artifact→Approval 全链路可追溯。
  4. **Confidence Model**: confidence 字段 (0-1, 审核优先级/经验学习/Provider
     反馈的数据接口, 本阶段只记录不消费)。
  5. **Product Workflow 解耦**: ProductWorkflow 骨架 + Product Decision Artifact
     (经 Approval 后产生的 product_decision 类型 Artifact, workflow.product_decision
     字段记录其 id) — Idea→Research→PRD→Approval→Product Decision→Architecture→
     Task→Workflow。
- 模型风格参照 tasks/workflows/models.py: to_dict() (model_dump(mode="json"))
  供 store/CLI --json/测试断言共用; 时间戳统一 UTC (events.models.format_timestamp)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from events.models import format_timestamp


def _now() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    return format_timestamp(datetime.now(timezone.utc))


class ApprovalRequired(str, Enum):
    """审批门强度: mandatory 阻塞推进 / recommended 可跳过记录 / optional 不要求。"""

    MANDATORY = "mandatory"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class ApprovalStatus(str, Enum):
    """审批请求状态机 (Phase 9c): pending → approved | rejected | changes_requested | delegated。

    终态可逆: rejected/changes_requested/delegated 后可重新提交 (新请求, 同
    version 允许再申请); approved 后仅当 Artifact version 递增 (v1→v2) 才需
    重新审批 (禁覆盖历史 — 见 service.revise_artifact)。DENIED 为 9a 遗留
    别名 (只读兼容旧数据; 新写入一律 rejected, 输入 denied → rejected 映射)。
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    DELEGATED = "delegated"
    DENIED = "denied"  # 9a 遗留 (读兼容; 不参与新流转)


class WorkflowStatus(str, Enum):
    """产品工作流状态: running / paused (审批门暂停 — 9a awaiting_approval 细化) /
    completed / failed。AWAITING_APPROVAL 为 9a 遗留成员 (只读兼容旧数据)。"""

    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"  # 9a 遗留 (读兼容旧数据)


class Artifact(BaseModel):
    """Artifact 抽象基础模型 (约束 1: 任何产品阶段产物落在此抽象上)。

    Lineage 字段 (约束 3): provider_id (生成来源 Provider) / agent_id (执行
    Agent) / source_events (生成事件链 event_id 列表, 唯一事实源引用) /
    version (重生成递增)。confidence (约束 4): 0-1 审核优先级/经验学习数据接口。
    """

    id: str
    type: str                       # product_idea/product_decision/research/prd/ui/...
    content: dict[str, Any] = Field(default_factory=dict)
    status: str = "created"         # created/pending/completed/failed/approved/denied/...
    created_by: str = "human"       # 创建者 (human / agent id / provider id)
    provider_id: str | None = None  # AI Artifact Lineage: 生成来源 Provider
    agent_id: str | None = None     # AI Artifact Lineage: 执行 Agent
    source_events: list[str] = Field(default_factory=list)  # Lineage: 生成事件链 (event_id)
    version: int = 1                # Lineage: 重生成递增
    confidence: float = 0.0         # Confidence Model: 0-1
    created_at: str = Field(default_factory=_now)
    supersedes: str | None = None   # Phase 9c: 版本链前驱 Artifact id (revise 递增, 禁覆盖历史)

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("version")
    @classmethod
    def _version_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"version must be >= 1, got {v}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ProductIdea(BaseModel):
    """产品想法 (阶段链源头; 同时以 product_idea Artifact 落库 — 任何 Artifact 可申请审批)。"""

    id: str
    title: str
    description: str = ""
    goals: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "created"         # created/refined/approved/archived
    created_at: str = Field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalGate(BaseModel):
    """审批门定义 (约束 2): 按 artifact_type 归类, required 决定是否阻塞推进。

    门 id 默认 = artifact_type (KISS, 如 --gate prd → gate id "prd"); rule 为
    人工可读的门规则描述。默认门 (service.DEFAULT_GATES): prd/ui mandatory,
    architecture recommended — 但门不绑定 PRD/UI: 任何 Artifact 类型都可
    request_approval (自定义门经 save_gate 注册)。
    """

    id: str
    artifact_type: str
    required: str = ApprovalRequired.MANDATORY.value  # mandatory/recommended/optional
    rule: str = ""                                    # 门规则描述 (人工可读)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalRequest(BaseModel):
    """审批请求: 任何 Artifact 可申请 (artifact_id → gate 门)。pending → 终态。

    idea_id (扩展字段): 审批涉及的产品想法 — 用于 workflow 联动 (approval.required
    时 workflow → paused; 终态时推进/resume)。CLI 未显式传时由 service 从
    artifact.content["idea_id"] 推导 (Idea 即 Artifact 约定)。
    artifact_version (Phase 9c): 申请时点 Artifact.version 快照 — Approval 绑定
    版本 (禁覆盖历史: v1 已批准后修改 → v2 需重新审批; 队列/历史按版本追溯)。
    decided_by/decided_at/comment: 决策回填 (决定后由 decide_approval 更新)。
    """

    id: str
    artifact_id: str
    gate: str                       # gate id (= artifact_type 于默认门)
    status: str = ApprovalStatus.PENDING.value
    requested_at: str = Field(default_factory=_now)
    idea_id: str | None = None      # 扩展: workflow 联动锚点
    by: str = "human"               # 申请人
    comment: str | None = None      # 申请备注 (deny 理由在 decision.comment)
    decided_by: str | None = None   # 决策人 (decide 回填)
    decided_at: str | None = None   # 决策时间 (decide 回填)
    artifact_version: int | None = None  # Phase 9c: Artifact version 快照 (绑定版本)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ApprovalDecision(BaseModel):
    """审批决定 (不可变记录): request_id → decision (approved|rejected|
    changes_requested|delegated) + 决策人/理由。created_at (Phase 9c): 记录创建
    时间 (与 decided_at 同值, 模型契约字段); decided_at 保留 9a 兼容。"""

    id: str
    request_id: str
    decision: str = ApprovalStatus.APPROVED.value  # approved/rejected/changes_requested/delegated
    decided_by: str = "human"
    comment: str = ""
    decided_at: str = Field(default_factory=_now)
    created_at: str = Field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProductWorkflow(BaseModel):
    """产品工作流骨架 (约束 5): stages 链 + current_stage + 状态机。

    状态流转 (9a 骨架 + 9c Pause/Resume, phase9-plan §4): start → running; 关联
    Artifact 申请审批 (approval.required) → paused (9a awaiting_approval 细化);
    approved → running + 推进 current_stage + 产生 Product Decision Artifact
    (product_decision 字段记录其 id) + approval.resumed; rejected/changes_requested
    → running (回退重生成/修改, 停留当前 stage); 手动 workflow resume 同款恢复。
    completed/failed 为 9d 编排预留终态。
    """

    id: str
    idea_id: str
    stages: list[str] = Field(default_factory=list)  # [research, prd, ui, architecture, tasks]
    current_stage: str = ""
    status: str = WorkflowStatus.RUNNING.value
    product_decision: str | None = None  # Product Decision Artifact id (granted 后回填)
    created_at: str = Field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
