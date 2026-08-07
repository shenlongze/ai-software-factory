"""factory-exec/exec/models.py — 执行领域模型 (Pydantic v2)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §2/§7):
```
ExecutionRequest (执行请求: task + context_refs)   — 只描述意图, 不执行
  → ExecutionResult (status success|failed + artifacts/usage/report)
  → Artifact (patch + test_result + report; 关联 task/employee/agent/event_refs)
  → ApprovalRecord (Human 门禁: pending → approved|rejected; 应用 patch 前必批)
SandboxSession (临时目录项目副本 + git 追踪 + patch 导出)
```

执行权归属 (设计 §2 铁律):
- 拥有执行权: AgentRuntime (执行模块 — 调 Provider/沙箱/产补丁)
- 只负责描述: ExecutionRequest (声明意图, 不执行)
- 只负责检查: Validation/Approval (门禁, 无执行)
- 只负责记录: Experience (沉淀, 无执行)
执行权 != 审核权 (Runtime 执行, Human 批准)。

Pydantic v2 陷阱 (backend-developer 经验):
- 容器字段 None 输入 → 默认值必须 mode="before" validator
- 类级常量带注解 = 字段 → 用 ClassVar
- to_dict() 用 model_dump(mode="json") (datetime → ISO 字符串)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def new_id(prefix: str) -> str:
    """生成带域前缀的唯一 id (EXR-xxx 执行请求 / EXS-xxx 执行结果 / ART-xxx 产物)。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def utcnow() -> datetime:
    """UTC 当前时间 (统一存储格式, 与 events 层同语义)。"""
    return datetime.now(timezone.utc)


def _norm_list(v: Any) -> Any:
    """None → [] 归一 (before validator 用: 类型检查前收到原始输入)。"""
    return v if v is not None else []


def _norm_str(v: Any) -> Any:
    """None → \"\" 归一 (str 字段 None 输入兜底)。"""
    return v if v is not None else ""


class _ExecModel(BaseModel):
    """执行模型基类: 严格字段 (extra=forbid) + JSON 友好导出。"""

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好 dict (datetime → ISO 字符串, 审计/CLI 输出用)。"""
        return self.model_dump(mode="json")


class ExecutionStatus(str, Enum):
    """执行结果终态 (成功/失败)。"""

    SUCCESS = "success"
    FAILED = "failed"


class ArtifactType(str, Enum):
    """Artifact 三产物 (设计 §7): patch / test_result / report。"""

    PATCH = "patch"
    TEST_RESULT = "test_result"
    REPORT = "report"


class ApprovalDecision(str, Enum):
    """审批决定 (Human 门禁状态机): pending → approved|rejected。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentInstance(_ExecModel):
    """Agent 实例 (执行身份; Artifact.agent_id 锚点)。

    MVP: 单 Developer Agent — AgentRuntime 的执行身份载体; 未来多 Agent 扩展
    时替换为 Core Agent 模型引用 (本阶段不 import factory-core agents, 保持
    Extension 边界, duck-typed 兼容任意含 id/name 的对象)。
    """

    id: str
    name: str = "Developer Agent"
    agent_type: str = "developer"


class ExecutionRequest(_ExecModel):
    """执行请求 (只声明意图, 不执行 — 执行权在 AgentRuntime)。

    id/task_id: 请求唯一 id + Core Task 锚点 (task_id 可空: 冒烟/独立执行)。
    objective: 目标描述 (Bug 修复等, Developer Agent prompt 主体)。
    input: 执行上下文 dict (project_dir/provider_id/employee_id/... —
      Core 零修改原则下经 input 携带, 同 Phase 8B-1 模式)。
    output_refs: 期望输出产物引用 (patch/report, 声明意图用)。
    requirement: 验收标准/约束 (Developer Agent prompt 规范部分)。
    """

    id: str
    task_id: str = ""
    objective: str
    input: dict[str, Any] = Field(default_factory=dict)
    output_refs: list[str] = Field(default_factory=list)
    requirement: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("input", mode="before")
    @classmethod
    def _input_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("output_refs", mode="before")
    @classmethod
    def _refs_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("task_id", "requirement", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)


class Artifact(_ExecModel):
    """执行产物 (patch / test_result / report; 事件链锚点 event_refs)。

    关联 (设计 §7): task_id → Task; employee_id → Employee (组织身份);
    agent_id → Agent Instance (执行身份); event_refs → org.execution.* 事件
    seq 列表 (执行事件链锚点, 审计可追溯)。
    path: 产物文件落盘路径 (patch 文件 / 测试输出文本 / 报告 md)。
    """

    id: str
    type: ArtifactType
    task_id: str = ""
    employee_id: str = ""
    agent_id: str = ""
    event_refs: list[str] = Field(default_factory=list)
    path: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> ArtifactType:
        return ArtifactType(v) if isinstance(v, str) else v

    @field_validator("event_refs", mode="before")
    @classmethod
    def _refs_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("task_id", "employee_id", "agent_id", "path", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)


class ExecutionResult(_ExecModel):
    """执行结果 (AgentRuntime 产物; status success|failed)。

    artifacts: 本执行产出的 Artifact 列表 (patch/test_result/report 内嵌,
    同时逐条落 ArtifactStore 供跨查询)。
    usage: Provider usage dict (input_tokens/output_tokens/estimated_cost...)。
    report: 执行报告文本 (做了什么/为什么/结果 — Developer Agent 生成)。
    error: 失败原因 (failed 终态必填, 结构化短语供 Experience failure_reason)。
    duration: 执行耗时 (秒, Experience 记录)。
    """

    id: str
    request_id: str
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    artifacts: list[Artifact] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    report: str = ""
    error: str = ""
    duration: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        return ExecutionStatus(v) if isinstance(v, str) else v

    @field_validator("artifacts", mode="before")
    @classmethod
    def _artifacts_none(cls, v: Any) -> Any:
        if v is None:
            return []
        return [a if isinstance(a, Artifact) else Artifact.model_validate(a) for a in v]

    @field_validator("usage", mode="before")
    @classmethod
    def _usage_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("report", "error", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)

    @property
    def is_success(self) -> bool:
        """成功判定 (Experience 记录/审批门禁用)。"""
        return self.status is ExecutionStatus.SUCCESS


class SandboxSession(_ExecModel):
    """沙箱会话 (临时目录项目副本 + git 追踪 + patch 导出)。

    沙箱铁律 (设计 §5): Agent 不直接改用户环境 — 副本 + patch;
    修改前后 diff 全记录; 不应用 = 无影响。
    workspace_copy_path: 项目副本目录 (Agent 唯一可写空间)。
    baseline_commit: 基线提交 (副本 git init 后快照; 空项目 None)。
    change_summary: 变更摘要 (git status --porcelain 行数/文件数)。
    patch_path: 导出的 patch 文件路径 (git diff → .patch)。
    """

    id: str
    request_id: str = ""
    workspace_copy_path: str
    baseline_commit: str | None = None
    change_summary: str = ""
    patch_path: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("change_summary", mode="before")
    @classmethod
    def _summary_none(cls, v: Any) -> Any:
        return _norm_str(v)


class ApprovalRecord(_ExecModel):
    """审批记录 (Human 门禁; 应用 patch 前必批 — 执行权 != 审核权)。

    request_id: 关联 ExecutionRequest (经 request_id → ExecutionResult →
      patch Artifact 定位待应用补丁)。
    decision: pending → approved|rejected (approve/deny 后落终态; CLI 动词
      approve|deny 在命令层映射, 服务层只接受语义值)。
    decided_by: 审批人 (Human 身份, 如 CEO/员工 id 或姓名)。
    comment: 审批意见 (reject 反馈 → Agent 修复循环记录)。
    applied/applied_at: patch 已应用标记 (防重复应用; 审批通过后 apply 置位)。
    """

    id: str
    request_id: str
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_by: str = ""
    comment: str = ""
    applied: bool = False
    applied_at: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None

    @field_validator("decision", mode="before")
    @classmethod
    def _coerce_decision(cls, v: Any) -> ApprovalDecision:
        return ApprovalDecision(v) if isinstance(v, str) else v

    @field_validator("decided_by", "comment", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)

    @property
    def is_approved(self) -> bool:
        """审批通过判定 (apply 前置条件)。"""
        return self.decision is ApprovalDecision.APPROVED
