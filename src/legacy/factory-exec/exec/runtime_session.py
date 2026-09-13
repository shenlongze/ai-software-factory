"""factory-exec/exec/runtime_session.py — S10-016 Runtime Session Domain (最小 Agent Runtime)。

设计依据 (S10-016-task001 用户约束 + 现有 Domain 侦察):
```
Task → Agent Assignment → Agent Runtime → Execution → Runtime Event → Artifact → Quality Gate
                                  ↑
                        Runtime Session (本模块 — 执行会话可见性底座)
```
目标: 从「用户看到 AI 在工作」→「AI Employee 开始执行工作」的基础 — 每次
Agent 执行 = 一个 Runtime Session (谁在跑/跑哪个任务/跑到哪一步/产出什么事件),
事件链可查询 (Runtime State 查询 API 的数据源)。

复用决策 (侦察结论):
- 已有 ExecStore (factory-exec/exec/store.py) 是 requests/results/artifacts/
  approvals 四子库的持久化基座; AgentRuntime (agent_runtime.py) 有执行能力但
  无显式 Session 模型; EmployeeExecutor 是 任务→能力→运行时 连接层。
- S10-004 RuntimeInstance (factory-console/runtime_store.py, root/runtimes) 是
  browser|terminal 沙箱实例 — 与「Agent 执行会话」概念不同, **不扩展不冲突**。
- 故新建最小 Runtime Session Domain (本模块): 模型 + 状态机 + 独立持久化
  (<root>/runtime-sessions/sessions.json — 独立数据空间, 原子写, 与 org/runtimes
  并存互不影响)。

状态机 (任务约束, 非法转换响亮报错):
```
PENDING ──start──▶ RUNNING ──complete(success=True)──▶ SUCCESS
                      │      ──complete(success=False)─▶ FAILED
                      │      ──cancel──────────────────▶ CANCELLED
                      └── append_event (仅 RUNNING 允许追加事件; 终态冻结)
```

与既有模型的关系 (禁止平行系统/重写):
- 不重写 AgentRuntime/EmployeeExecutor/Workflow/Task — 本模块只提供 Session
  记录 (谁/何时/何状态/事件链), 执行权仍在 AgentRuntime。
- 事件模型 (RuntimeEvent 7 类型) 与 org.* 事件 (factory-org/org/events.py) 并存:
  前者是执行会话内时间线 (内嵌于 session), 后者是全局审计流 — 不互相替代。

持久化语义 (同 ExecStore/runtime_store 模式): 原子写 (临时文件 + os.replace);
损坏 → 响亮 CorruptRuntimeSessionStoreError (绝不静默返回空); 本模块只做持久化
+ 状态机, 无业务逻辑; 只依赖 stdlib + pydantic + 本层 models (Removal Isolation)。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import utcnow


def new_session_id() -> str:
    """新会话 id (rs-<uuid4 前 8 hex>; 唯一 basename, 无时钟碰撞语义)。"""
    return f"rs-{uuid.uuid4().hex[:8]}"


def new_event_id() -> str:
    """新事件 id (ev-<uuid4 前 8 hex>)。"""
    return f"ev-{uuid.uuid4().hex[:8]}"


def new_step_id() -> str:
    """新步骤 id (st-<uuid4 前 8 hex> — AgentStep 执行步骤)。"""
    return f"st-{uuid.uuid4().hex[:8]}"


class RuntimeSessionStatus(str, Enum):
    """Runtime Session 五状态 (API 契约: pending/running/success/failed/cancelled)。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeEventType(str, Enum):
    """Runtime Event 类型 (任务约束 — Agent 执行时间线事件)。

    S10-016 Task 002 最小扩展 (向后兼容): 新增 LLM_REQUEST_SENT /
    LLM_RESPONSE_RECEIVED — Agent Executor 编排层标记 LLM 调用边界
    (Request Sent: 调 Provider 前; Response Received: Provider 返回后)。

    S10-017 Task 001 扩展 (9→14, 向后兼容): 新增 THINKING_STARTED /
    DECISION_CREATED / ACTION_REQUESTED / OBSERVATION_RECEIVED /
    EXECUTION_COMPLETED — Agent Execution Loop 完整记录
    Task→Step→Decision→Result (思考/决策/动作边界/观察/循环完成)。
    """

    AGENT_STARTED = "agent_started"
    TASK_RECEIVED = "task_received"
    EXECUTION_STARTED = "execution_started"
    TOOL_CALLED = "tool_called"
    LLM_REQUEST_SENT = "llm_request_sent"
    LLM_RESPONSE_RECEIVED = "llm_response_received"
    OUTPUT_GENERATED = "output_generated"
    EXECUTION_FINISHED = "execution_finished"
    EXECUTION_FAILED = "execution_failed"
    # S10-017 Task 001: Execution Loop 事件 (Reason→Act→Observe→Complete)
    THINKING_STARTED = "thinking_started"
    DECISION_CREATED = "decision_created"
    ACTION_REQUESTED = "action_requested"
    OBSERVATION_RECEIVED = "observation_received"
    EXECUTION_COMPLETED = "execution_completed"
    # S10-018 Task 001: Tool Runtime 事件 (Decision→Tool→Result→Observation;
    # 完整链路 ...→tool_requested→tool_started→tool_completed→observation_received→...;
    # 失败 → tool_failed → execution_failed)
    TOOL_REQUESTED = "tool_requested"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    # S10-019 Task 001: Skill System 事件 (职业能力上下文; **条件触发** — 仅当
    # Agent 装配了 SkillContext (有已注册 Skill) 时发出, 不污染无技能 Agent 的
    # 既有精确事件链):
    # - skill_loaded:   Agent 启动后 (agent_started/task_received 之后), Skill
    #   上下文就绪时 — 记录 Agent 拥有的职业能力快照 (skill/available_tools)。
    # - skill_selected: 决策前 (planner.plan 之前), 当前轮选中的 Skill 边界 —
    #   记录 Planner 决策时可见的职业能力约束 (round/skill/available_tools)。
    SKILL_LOADED = "skill_loaded"
    SKILL_SELECTED = "skill_selected"
    # S10-020 Task 001: MCP Adapter Foundation 事件 (20→23, 向后兼容):
    # - mcp_connected:      MCP Client 建立连接时 (Mock 连接/MCP tool 首次
    #   调用 — adapter 延迟连接) — 记录外部 MCP Server 连接边界。
    # - mcp_tool_discovered: 连接后 list_tools 发现 Tool 时 — 记录发现结果
    #   (tools 名列表, 注册前置)。
    # - mcp_tool_registered: MCP Tool 经 MCPToolAdapter 注册进内部 ToolRegistry
    #   时 — 记录注册边界 (tool/server; 之后该 Tool 与内部 Tool 无差别)。
    MCP_CONNECTED = "mcp_connected"
    MCP_TOOL_DISCOVERED = "mcp_tool_discovered"
    MCP_TOOL_REGISTERED = "mcp_tool_registered"


class AgentStepType(str, Enum):
    """Agent 执行步骤类型 (S10-017 Task 001 — 执行循环步骤模型)。

    RECEIVE_TASK (接收任务) → ANALYZE (分析/思考) → DECISION (决策) →
    ACTION (动作边界 — 本 Sprint 仅 Mock noop, 为 Tool/MCP 预留) →
    OBSERVATION (观察结果) → FINAL (最终产出/循环完成)。
    """

    RECEIVE_TASK = "RECEIVE_TASK"
    ANALYZE = "ANALYZE"
    DECISION = "DECISION"
    ACTION = "ACTION"
    OBSERVATION = "OBSERVATION"
    FINAL = "FINAL"


class AgentStepStatus(str, Enum):
    """Agent 步骤状态 (pending/running/succeeded/failed — 与执行结果同构)。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RuntimeSessionError(Exception):
    """Runtime Session 业务错误 (非法状态转换等 — HTTP 层 409)。"""


class _SessionModel(BaseModel):
    """Session 模型基类: 严格字段 (extra=forbid) + JSON 友好导出 (同 exec.models)。"""

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好 dict (datetime → ISO 字符串, 审计/API 响应用)。"""
        return self.model_dump(mode="json")


class RuntimeEvent(_SessionModel):
    """执行会话事件 (时间线条目; 内嵌于 RuntimeSession.events)。"""

    event_id: str
    session_id: str
    type: RuntimeEventType
    message: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    data: dict[str, Any] | None = None

    @property
    def id(self) -> str:
        """通用 id 别名 (Store 通用 save 语义兼容)。"""
        return self.event_id


class AgentStep(_SessionModel):
    """Agent 执行步骤 (S10-017 Task 001 — 执行循环步骤记录; 内嵌于
    RuntimeSession.steps)。

    id (st-)/session_id/step_number (从 1 递增)/step_type (RECEIVE_TASK|
    ANALYZE|DECISION|ACTION|OBSERVATION|FINAL)/input/output/status/
    created_at — 完整记录 Task→Step→Decision→Result 的每一步。
    """

    id: str
    session_id: str
    step_number: int
    step_type: AgentStepType
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    status: AgentStepStatus = AgentStepStatus.SUCCEEDED
    created_at: datetime = Field(default_factory=utcnow)


class RuntimeSession(_SessionModel):
    """Runtime Session — 一次 Agent 执行会话的记录 (谁/何时/何任务/何状态/事件链)。

    session_id/agent_id/task_id/workflow_id: 任务约束字段 (workflow_id 可选 —
    独立执行无工作流); status: 五状态机; created_at/started_at/finished_at:
    生命周期时间戳; events: 内嵌事件链 (append 保序, 终态冻结)。
    """

    session_id: str
    agent_id: str
    task_id: str = ""
    workflow_id: str = ""
    status: RuntimeSessionStatus = RuntimeSessionStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    events: list[RuntimeEvent] = Field(default_factory=list)
    # S10-017 Task 001: Agent Execution Loop 步骤链 (RECEIVE_TASK→…→FINAL;
    # 状态变化不静默 — 每步都落 session; 缺省空列表, 旧数据无损)
    steps: list[AgentStep] = Field(default_factory=list)
    # S10-016 Task 002: Agent Executor 输出保留 (执行产出 — execution_output/
    # execution_summary/raw_response; 缺省空串, 向后兼容旧数据无字段)
    execution_output: str = ""
    execution_summary: str = ""
    raw_response: str = ""

    @property
    def id(self) -> str:
        """通用 id 别名 (Store 通用 save 语义兼容)。"""
        return self.session_id

    # ------------------------------------------------------------------ 状态机

    def start(self) -> "RuntimeSession":
        """PENDING → RUNNING (started_at 记录)。非法 → RuntimeSessionError。"""
        if self.status != RuntimeSessionStatus.PENDING:
            raise RuntimeSessionError(
                f"session {self.session_id} cannot start from status "
                f"{self.status.value!r} (only PENDING)"
            )
        return self.model_copy(
            update={
                "status": RuntimeSessionStatus.RUNNING,
                "started_at": utcnow(),
            }
        )

    def complete(self, success: bool) -> "RuntimeSession":
        """RUNNING → SUCCESS|FAILED (finished_at 记录)。非法 → RuntimeSessionError。"""
        if self.status != RuntimeSessionStatus.RUNNING:
            raise RuntimeSessionError(
                f"session {self.session_id} cannot complete from status "
                f"{self.status.value!r} (only RUNNING)"
            )
        return self.model_copy(
            update={
                "status": (
                    RuntimeSessionStatus.SUCCESS
                    if success
                    else RuntimeSessionStatus.FAILED
                ),
                "finished_at": utcnow(),
            }
        )

    def cancel(self) -> "RuntimeSession":
        """RUNNING → CANCELLED (finished_at 记录)。非法 → RuntimeSessionError。"""
        if self.status != RuntimeSessionStatus.RUNNING:
            raise RuntimeSessionError(
                f"session {self.session_id} cannot cancel from status "
                f"{self.status.value!r} (only RUNNING)"
            )
        return self.model_copy(
            update={
                "status": RuntimeSessionStatus.CANCELLED,
                "finished_at": utcnow(),
            }
        )

    def append_event(
        self,
        event_type: RuntimeEventType | str,
        message: str = "",
        *,
        data: dict[str, Any] | None = None,
    ) -> tuple["RuntimeSession", RuntimeEvent]:
        """追加事件 (仅 RUNNING 允许; 终态/未开始 → RuntimeSessionError)。

        返回 (新 session, 新事件) — 调用方经 store.save(新 session) 落库。
        事件内嵌于 session.events (独立事件库不必要 — KISS, 无平行系统)。
        """
        if self.status != RuntimeSessionStatus.RUNNING:
            raise RuntimeSessionError(
                f"session {self.session_id} cannot append event from status "
                f"{self.status.value!r} (only RUNNING)"
            )
        event = RuntimeEvent(
            event_id=new_event_id(),
            session_id=self.session_id,
            type=RuntimeEventType(event_type),  # 未知值 → ValueError (响亮)
            message=message,
            data=data,
        )
        return (
            self.model_copy(update={"events": [*self.events, event]}),
            event,
        )

    # ------------------------------------------------------------------ 步骤链 (S10-017)

    def add_step(
        self,
        step_type: AgentStepType | str,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        *,
        status: AgentStepStatus = AgentStepStatus.SUCCEEDED,
    ) -> tuple["RuntimeSession", AgentStep]:
        """追加执行步骤 (仅 RUNNING 允许; 终态/未开始 → RuntimeSessionError)。

        step_number 从 1 递增 (len(steps)+1); input/output 缺省空 dict (无
        None 陷阱); 未知 step_type → ValueError (响亮)。返回 (新 session,
        新 AgentStep) — 调用方经 store.save(新 session) 落库; 步骤内嵌于
        session.steps (保序, 同事件链)。
        """
        if self.status != RuntimeSessionStatus.RUNNING:
            raise RuntimeSessionError(
                f"session {self.session_id} cannot add step from status "
                f"{self.status.value!r} (only RUNNING)"
            )
        step = AgentStep(
            id=new_step_id(),
            session_id=self.session_id,
            step_number=len(self.steps) + 1,
            step_type=AgentStepType(step_type),  # 未知值 → ValueError (响亮)
            input=input or {},
            output=output or {},
            status=status,
        )
        return (
            self.model_copy(update={"steps": [*self.steps, step]}),
            step,
        )


# ------------------------------------------------------------------ Store

T = TypeVar("T", bound=BaseModel)


class CorruptRuntimeSessionStoreError(Exception):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class _SessionSectionStore(Generic[T]):
    """单实体 JSON 记录库 (原子写/损坏响亮; 仿 exec/store.py _SectionStore 模式)。

    独立实现 (不 import exec.store 私有基类 — 本模块 Removal Isolation,
    只依赖 stdlib + pydantic + 本层 models)。
    """

    _filename: str
    _section: str
    _model: type[T]

    def __init__(self, dir_path: str | Path):
        self._dir = Path(dir_path)

    @property
    def dir(self) -> Path:
        """数据空间目录 (<root>/runtime-sessions)。"""
        return self._dir

    # ------------------------------------------------------------------ 读

    def _path(self) -> Path:
        return self._dir / self._filename

    def _read_all(self) -> dict[str, dict[str, Any]]:
        """读整库 {id: dict}; 文件不存在返回空库 (首次写前合法状态)。"""
        path = self._path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptRuntimeSessionStoreError(
                f"corrupt runtime session store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptRuntimeSessionStoreError(
                f"corrupt runtime session store: {path}: missing or invalid section "
                f"{self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> T:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptRuntimeSessionStoreError(
                f"corrupt runtime session store: {self._path()}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ 写

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        """原子写单文件: 临时文件 + os.replace (同目录, 同文件系统原子性)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 通用 API

    def save(self, record: T) -> None:
        """upsert 记录 (同 id 覆盖 = 状态流转经 model_copy 新实例后落库)。"""
        records = self._read_all()
        records[record.id] = record.to_dict()  # type: ignore[attr-defined]
        self._write(records)

    def get(self, record_id: str) -> T | None:
        """按 id 取记录; 不存在返回 None。"""
        data = self._read_all().get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[T]:
        """全部记录 (按 id 排序, 审计友好)。"""
        return sorted(
            (self._load(data) for data in self._read_all().values()),
            key=lambda r: r.id,  # type: ignore[attr-defined, return-value]
        )

    def count(self) -> int:
        """记录总数。"""
        return len(self._read_all())


class RuntimeSessionStore(_SessionSectionStore[RuntimeSession]):
    """RuntimeSession 持久化 (<dir>/sessions.json — 独立数据空间, 原子写)。

    与 S10-004 RuntimeInstanceStore (root/runtimes) 完全分离: 那是 browser/
    terminal 沙箱实例; 本库是 Agent 执行会话。重启 (重建 store) 后数据可查
    (持久化铁律)。
    """

    _filename = "sessions.json"
    _section = "sessions"
    _model = RuntimeSession


__all__ = [
    "CorruptRuntimeSessionStoreError",
    "RuntimeEvent",
    "RuntimeEventType",
    "RuntimeSession",
    "RuntimeSessionError",
    "RuntimeSessionStatus",
    "RuntimeSessionStore",
    "new_event_id",
    "new_session_id",
]
