"""factory-exec/exec/execution_loop.py — S10-017 Task 001 Agent Execution Loop。

设计依据 (S10-017-task001 用户约束 + Task 001/002 RuntimeSession Domain 侦察):
```
Task → AgentExecutionLoop (Reason → Act → Observe → Complete)
          │
          ├─ Planner (LLMPlanner — 复用 ProviderInterface, 决策边界)
          ├─ Action Executor (MockActionExecutor — 动作边界, 为 Tool/MCP 预留)
          └─ Runtime Session (exec.runtime_session — 每阶段落 session, 不静默)
```

职责 (编排层 — 不重写 AgentRuntime/Provider 执行逻辑):
- run(): 完整生命周期 CREATED→RUNNING→(WAITING_DECISION|WAITING_ACTION)→
  COMPLETED|FAILED — 每轮: ANALYZE (thinking_started) → DECISION
  (decision_created) → FINAL (复用 runtime.execute, 旧流程 Task→LLM→Result)
  或 ACTION_REQUIRED (action_requested → MockActionExecutor → observation_received
  → 下一轮)。单轮 FINAL = 旧流程 (Task→LLM→Result) 兼容。
- transition(): 状态机合法/非法转换 (非法 → ExecutionLoopError 响亮);
  终态 (COMPLETED/FAILED) 冻结。
- 状态变化必须写 RuntimeSession: 每阶段步骤 (AgentStep) + 事件 (RuntimeEvent)
  立即落库 (session_store.save), 不静默。

执行权归属铁律 (同 agent_runtime 设计):
- 拥有执行权: AgentRuntime (FINAL 路径复用 runtime.execute — 本模块只编排)
- 复用 Provider: LLMPlanner 直接复用 ProviderInterface.generate (Provider
  Adapter Interface — 无 Provider → 诚实 FINAL 单轮回退, 不伪造决策)
- 无 runtime (无 Provider) → 诚实 FAILED (不伪造 LLM 结果)

循环收敛铁律: ACTION_REQUIRED 轮次超上限 (MAX_ROUNDS) → 诚实 FAILED
(禁无限循环; 错误信息含 round 供审计)。

依赖 (Removal Isolation): 只 import 同层 exec 模块 (models/provider/
runtime_session) + stdlib + pydantic; 不触碰 agent_runtime.py / provider.py
主逻辑 (只复用其公开接口)。
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .models import ExecutionRequest, new_id
from .provider import ProviderInterface, ProviderRequest
from .runtime_session import (
    AgentStepType,
    RuntimeEventType,
    RuntimeSession,
    RuntimeSessionStatus,
)
from .skill import resolve_agent_skills, skill_context_for

#: ACTION_REQUIRED 轮次上限 (超限 → 诚实 FAILED — 禁无限循环)。
MAX_ROUNDS = 4


class ExecutionLoopError(Exception):
    """Execution Loop 业务错误 (非法状态转换 / 重复 run — 响亮, 不静默)。"""


class ExecutionState(str, Enum):
    """Execution Loop 六状态 (CREATED→RUNNING→WAITING_DECISION|\n
    WAITING_ACTION→COMPLETED|FAILED)。"""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING_DECISION = "WAITING_DECISION"
    WAITING_ACTION = "WAITING_ACTION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


#: 合法转换表 (终态 COMPLETED/FAILED 冻结 — 无出口)。
_ALLOWED_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.CREATED: {ExecutionState.RUNNING},
    ExecutionState.RUNNING: {
        ExecutionState.WAITING_DECISION,
        ExecutionState.COMPLETED,
        ExecutionState.FAILED,
    },
    ExecutionState.WAITING_DECISION: {
        ExecutionState.RUNNING,
        ExecutionState.WAITING_ACTION,
        ExecutionState.FAILED,
    },
    ExecutionState.WAITING_ACTION: {
        ExecutionState.RUNNING,
        ExecutionState.FAILED,
    },
    ExecutionState.COMPLETED: set(),
    ExecutionState.FAILED: set(),
}


class DecisionType(str, Enum):
    """Planner 决策类型: FINAL (直接执行) / ACTION_REQUIRED (需要动作)。"""

    FINAL = "FINAL"
    ACTION_REQUIRED = "ACTION_REQUIRED"


#: 模块级常量 (测试/调用方便利 — Decision(type=FINAL) 同义 DecisionType.FINAL)
FINAL = DecisionType.FINAL
ACTION_REQUIRED = DecisionType.ACTION_REQUIRED


class Decision(BaseModel):
    """Planner 决策 (type/reason/payload — 可审计, 落 decision_created 事件)。"""

    type: DecisionType
    reason: str = ""
    payload: dict[str, Any] | None = None


class ActionResultStatus(str, Enum):
    """动作执行结果状态 (succeeded/failed — 与执行结果同构)。"""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActionResult(BaseModel):
    """动作执行结果 (status/output/error — 观察边界载荷)。"""

    status: ActionResultStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class Planner(Protocol):
    """Planner Protocol — 决策边界 (task + context → Decision)。

    LLMPlanner 是默认实现 (复用 ProviderInterface); 测试注入假 Planner
    (固定决策序列) 验证循环行为 — 循环不关心决策来源, 只消费 Decision。
    """

    def plan(self, task: Any, context: dict[str, Any] | None) -> Decision: ...


def _build_plan_context(task: Any, context: dict[str, Any] | None) -> str:
    """组装 Planner Task Context (任务/项目/类型/工作流阶段/验收要求)。"""
    ctx = context or {}
    parts = [
        f"任务: {getattr(task, 'title', '')} (id: {getattr(task, 'id', '')})",
        f"项目: {getattr(task, 'project', '')}",
        f"类型: {getattr(task, 'type', '')}",
        f"工作流阶段: {getattr(task, 'workflow', '') or '(无工作流)'}",
        "请决策下一步: 输出 'DECISION: FINAL' (直接执行任务) 或 "
        "'DECISION: ACTION_REQUIRED' (需要执行动作), 可附理由; "
        "或输出 JSON {\"decision\": \"FINAL|ACTION_REQUIRED\", \"reason\": ..., "
        "\"payload\": {...}}。",
    ]
    requirement = str(ctx.get("requirement") or "").strip()
    if requirement:
        parts.append(f"验收要求: {requirement}")
    extra = str(ctx.get("instruction") or "").strip()
    if extra:
        parts.append(f"补充上下文: {extra}")
    return "\n".join(parts)


class LLMPlanner:
    """LLM Planner — 复用 ProviderInterface.generate (决策边界, 不绑 OpenAI)。

    - 无 Provider → 诚实 FINAL 单轮回退 (reason 说明 provider 缺失, 不伪造)
    - Provider 返回 error / 抛异常 → 诚实 FINAL 单轮回退 (错误原因进 reason)
    - 解析: 先 JSON {\"decision\", ...} → 再 'DECISION: FINAL|ACTION_REQUIRED'
      标记 → 无法识别 → 诚实 FINAL 单轮回退 (reason 说明)
    """

    def __init__(self, provider: ProviderInterface | None = None) -> None:
        self._provider = provider

    def plan(self, task: Any, context: dict[str, Any] | None) -> Decision:
        """task + context → Decision (Provider 复用; 无 Provider → 诚实 FINAL)。"""
        if self._provider is None:
            return Decision(
                type=FINAL,
                reason="no LLM provider configured (provider key missing)",
            )
        try:
            response = self._provider.generate(
                ProviderRequest(task_context=_build_plan_context(task, context))
            )
        except Exception as exc:  # noqa: BLE001 — Provider 抛异常 → 诚实回退
            return Decision(type=FINAL, reason=f"provider error: {exc}")
        if response.error:
            return Decision(
                type=FINAL, reason=f"provider error: {response.error}"
            )
        return self._parse(response.content)

    @staticmethod
    def _parse(content: str) -> Decision:
        """LLM 响应 → Decision (JSON 优先 → 标记 → 诚实 FINAL 回退)。"""
        text = (content or "").strip()
        if not text:
            return Decision(
                type=FINAL, reason="empty planner response (honest FINAL fallback)"
            )
        # 1) JSON 决策 {decision, reason?, payload?}
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("decision"):
                return Decision(
                    type=DecisionType(str(data["decision"]).strip().upper()),
                    reason=str(data.get("reason") or ""),
                    payload=data.get("payload"),
                )
        except (ValueError, TypeError):
            pass
        # 2) 'DECISION: FINAL|ACTION_REQUIRED' 标记
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("DECISION:"):
                marker = stripped.split(":", 1)[1].strip().upper()
                if "ACTION_REQUIRED" in marker:
                    return Decision(type=ACTION_REQUIRED, reason="")
                if "FINAL" in marker:
                    return Decision(type=FINAL, reason="")
        # 3) 无法识别 → 诚实 FINAL 单轮回退 (不伪造决策)
        return Decision(
            type=FINAL,
            reason="unrecognized planner output (honest FINAL fallback)",
        )


class MockActionExecutor:
    """Mock 动作执行器 (动作边界 — 为 Tool/MCP/Skill 预留)。

    本 Sprint 仅支持 {type: \"noop\"} (无操作 — 合法空动作); 未知 action /
    缺 type → ActionResult FAILED (响亮, 不假装成功)。
    """

    def execute(self, action: dict[str, Any] | None) -> ActionResult:
        """执行动作 → ActionResult (unknown/missing type → FAILED 响亮)。"""
        if not isinstance(action, dict) or not str(action.get("type") or "").strip():
            return ActionResult(
                status=ActionResultStatus.FAILED,
                error="action missing required 'type' field",
            )
        action_type = str(action["type"])
        if action_type == "noop":
            return ActionResult(
                status=ActionResultStatus.SUCCEEDED,
                output={
                    "type": "noop",
                    "message": "noop action executed (no-op, 为 Tool/MCP 预留)",
                },
            )
        return ActionResult(
            status=ActionResultStatus.FAILED,
            error=f"unknown action type: {action_type!r} (only 'noop' supported)",
        )


class AgentExecutionLoop:
    """Agent 执行循环: Task → Reason → Act → Observe → Complete (全记录)。

    构造 (依赖注入, 全部显式):
    - session: RuntimeSession (必须已 RUNNING — 由装配方 start)。
    - session_store: RuntimeSessionStore (状态变化立即落库 — 不静默)。
    - planner: Planner | None (缺省 LLMPlanner — 复用 runtime 的 Provider)。
    - action_executor: MockActionExecutor | None (缺省 MockActionExecutor)。
    - tool_executor: ToolExecutor | None (S10-018 — Tool Action 分发; None →
      诚实 tool_failed 'tool executor not configured', 不伪造)。
    - skill_registry: SkillRegistry | None (S10-019 — Skill 职业能力上下文;
      None → 不触发 skill_* 事件 + 不校验权限链 (既有精确事件链零污染);
      装配 → 解析 Agent 技能 → SkillContext 传 Planner + check_tool_access
      权限链接入 Tool 分支; 条件触发: 仅当 Agent 有已注册 Skill)。
    - runtime: AgentRuntime | None (FINAL 路径执行引擎; None = 无 Provider
      → 诚实 FAILED, 不伪造 LLM 结果)。

    方法:
    - run(task, agent, *, context=None) → dict {runtime_session_id, status,
      output, execution_steps} 完整闭环 (编排; 不抛未处理异常)。
    - transition(target): 状态机转换 (非法 → ExecutionLoopError 响亮)。
    - state: 当前 ExecutionState (审计/测试断言)。
    """

    def __init__(
        self,
        *,
        session: RuntimeSession,
        session_store: Any,
        planner: Any = None,
        action_executor: Any = None,
        runtime: Any = None,
        tool_executor: Any = None,
        skill_registry: Any = None,
    ) -> None:
        self._session = session
        self._session_store = session_store
        self._runtime = runtime
        self._planner = (
            planner if planner is not None else LLMPlanner(provider=self._provider())
        )
        self._action_executor = (
            action_executor
            if action_executor is not None
            else MockActionExecutor()
        )
        # S10-018 Task 001: Tool Runtime — ToolExecutor (exec.tool) 可选装配;
        # None → Tool Action 诚实 tool_failed ('tool executor not configured')。
        self._tool_executor = tool_executor
        # S10-019 Task 001: Skill Registry (exec.skill) 可选装配; None → 不触发
        # skill_* 事件 + 不校验权限链 (既有精确事件链零污染)。装配 → run() 启动
        # 阶段解析 Agent 技能: 有已注册 Skill → skill_loaded 事件 + SkillContext
        # (skill_selected 决策前事件 + 并入 planner context + check_tool_access
        # 权限链接入 Tool 分支); 无技能 Agent → 零 skill_* 事件 (条件触发铁律)。
        self._skill_registry = skill_registry
        #: Agent 已解析技能列表 (resolve_agent_skills — 权限链数据源; run 填充)。
        self._agent_skills: list[str] = []
        #: SkillContext (职业能力快照 — 有技能 Agent 非 None; 驱动条件触发)。
        self._skill_context: Any = None
        self._state = ExecutionState.CREATED

    # ------------------------------------------------------------------ 状态机

    @property
    def state(self) -> ExecutionState:
        """当前执行状态 (CREATED→…→COMPLETED|FAILED)。"""
        return self._state

    def transition(self, target: ExecutionState) -> None:
        """状态转换 (非法 → ExecutionLoopError; 终态冻结 — 响亮不静默)。"""
        allowed = _ALLOWED_TRANSITIONS.get(self._state, set())
        if target not in allowed:
            raise ExecutionLoopError(
                f"illegal execution loop transition: "
                f"{self._state.value} -> {target.value}"
            )
        self._state = target

    # ------------------------------------------------------------------ 装配辅助

    def _provider(self) -> ProviderInterface | None:
        """runtime 的 Provider (复用 AgentRuntime.developer.provider;
        runtime None → None — LLMPlanner 诚实回退)。"""
        if self._runtime is None:
            return None
        return getattr(getattr(self._runtime, "developer", None), "provider", None)

    def _provider_id(self) -> str:
        """Provider id (事件 data 审计; 未装配 → 空串)。"""
        provider = self._provider()
        return getattr(provider, "provider_id", "") or ""

    # ------------------------------------------------------------------ Session 写入 (状态变化落库 — 不静默)

    def _save(self, session: RuntimeSession) -> RuntimeSession:
        """落库 + 更新本地引用 (每次状态变化立即持久化)。"""
        self._session_store.save(session)
        self._session = session
        return session

    def _add_step(
        self,
        session: RuntimeSession,
        step_type: AgentStepType,
        *,
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
    ) -> RuntimeSession:
        """追加 AgentStep (step_number 递增) + 落库。"""
        updated, _step = session.add_step(step_type, input=input, output=output)
        return self._save(updated)

    def _append(
        self,
        session: RuntimeSession,
        event_type: RuntimeEventType,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> RuntimeSession:
        """追加 RuntimeEvent + 落库 (事件链保序)。"""
        updated, _event = session.append_event(event_type, message, data=data)
        return self._save(updated)

    # ------------------------------------------------------------------ 上下文/请求 (复用 AgentExecutor 语义)

    @staticmethod
    def _build_task_context(
        task: Any, agent_id: str, context: dict[str, Any] | None
    ) -> str:
        """组装 Task Context (任务/项目/类型/工作流阶段/验收要求/补充指令)。"""
        ctx = context or {}
        parts = [
            f"任务: {getattr(task, 'title', '')} (id: {getattr(task, 'id', '')})",
            f"项目: {getattr(task, 'project', '')}",
            f"类型: {getattr(task, 'type', '')}",
            f"工作流阶段: {getattr(task, 'workflow', '') or '(无工作流)'}",
            f"执行 Agent: {agent_id}",
        ]
        requirement = str(ctx.get("requirement") or "").strip()
        if requirement:
            parts.append(f"验收要求: {requirement}")
        extra = str(ctx.get("instruction") or "").strip()
        if extra:
            parts.append(f"补充上下文: {extra}")
        return "\n".join(parts)

    def _build_request(
        self, task: Any, agent: Any, context: dict[str, Any] | None
    ) -> ExecutionRequest:
        """构造 ExecutionRequest (FINAL 路径 — 执行权在 AgentRuntime)。"""
        task_context = self._build_task_context(task, agent.id, context)
        ctx = context or {}
        project_dir = str(ctx.get("project_dir") or "").strip()
        return ExecutionRequest(
            id=new_id("EXR"),
            task_id=task.id,
            objective=getattr(task, "title", ""),
            requirement=task_context,
            input={
                "project_dir": project_dir,
                "agent_id": agent.id,
                "task_context": task_context,
                "workflow_stage": getattr(task, "workflow", "") or "",
            },
        )

    # ------------------------------------------------------------------ 结果辅助

    @staticmethod
    def _step_dict(step: Any) -> dict[str, Any]:
        """AgentStep → API 形状 (execution_steps 元素: type/status/output)。"""
        return {
            "id": step.id,
            "step_number": step.step_number,
            "type": step.step_type.value,
            "status": step.status.value,
            "input": step.input,
            "output": step.output,
        }

    def _finish(
        self, session: RuntimeSession, *, summary: str = "", report: str = ""
    ) -> dict[str, Any]:
        """SUCCESS 终态: complete(SUCCESS) + Output 保留 + execution_steps。"""
        finished = session.complete(success=True)
        finished = finished.model_copy(
            update={
                "execution_output": report,
                "execution_summary": summary,
                "raw_response": report,
            }
        )
        self._session_store.save(finished)
        return {
            "runtime_session_id": finished.session_id,
            "status": finished.status.value,
            "output": {
                "execution_output": finished.execution_output,
                "execution_summary": finished.execution_summary,
                "raw_response": finished.raw_response,
            },
            "execution_steps": [self._step_dict(s) for s in finished.steps],
        }

    def _fail(self, session: RuntimeSession, error: str) -> dict[str, Any]:
        """FAILED 终态: execution_failed 事件 (错误进事件) + complete(FAILED)
        + Output 保留失败原因 + execution_steps。"""
        session = self._append(
            session,
            RuntimeEventType.EXECUTION_FAILED,
            "执行失败",
            data={"error": error[:1000]},
        )
        self.transition(ExecutionState.FAILED)
        finished = session.complete(success=False)
        finished = finished.model_copy(
            update={
                "execution_output": error,
                "execution_summary": f"failed · {error[:200]}",
                "raw_response": error,
            }
        )
        self._session_store.save(finished)
        return {
            "runtime_session_id": finished.session_id,
            "status": finished.status.value,
            "output": {
                "execution_output": finished.execution_output,
                "execution_summary": finished.execution_summary,
                "raw_response": finished.raw_response,
            },
            "execution_steps": [self._step_dict(s) for s in finished.steps],
        }

    # ------------------------------------------------------------------ Tool 分支 (S10-018 Task 001)

    def _run_tool_action(
        self,
        session: RuntimeSession,
        action: dict[str, Any],
        agent: Any,
        context: dict[str, Any] | None,
    ) -> tuple[RuntimeSession, dict[str, Any] | None]:
        """Tool Action 分支: Decision→Tool→Result→Observation (事件全记录)。

        action = {type: "tool", tool_id, input} — 事件链:
        - 成功: tool_requested → tool_started → tool_completed →
          observation_received (Observation 边界: status=succeeded + 工具输出),
          返回 (session, None) — 调用方继续下一轮 (Continue 语义)。
        - 失败: tool_requested → tool_started → tool_failed →
          execution_failed (错误进 tool_failed.data.error), 返回
          (session, FAILED 终态 dict) — 诚实终止, 不假装成功。
        - 未装配 tool_executor → 诚实 tool_failed ('tool executor not
          configured') → execution_failed (约束: 无执行器不伪造 Tool 结果)。
        - 执行器抛异常 → 捕获转 tool_failed (编排层兜底, 不抛裸异常)。
        """
        tool_id = str(action.get("tool_id") or "").strip()
        tool_input = dict(action.get("input") or {})
        session = self._append(
            session,
            RuntimeEventType.TOOL_REQUESTED,
            "请求执行工具",
            data={"tool_id": tool_id, "input": tool_input},
        )
        # S10-019: 权限链接入 Tool 分支 (条件触发 — 仅装配 SkillContext 的 Agent):
        # Agent has Skill → Skill includes Tool → Tool Permission allows; 任一环
        # 失败 → tool_failed (error 含 'skill permission denied' + tool_id) →
        # execution_failed (诚实拒绝 — 不执行, 不假装成功)。无技能 Agent / 未装配
        # skill_registry → 跳过 (既有 Tool 分支行为原样, 零污染)。
        if self._skill_context is not None and self._skill_registry is not None:
            denied = self._skill_registry.check_tool_access(
                agent.id, self._agent_skills, tool_id
            )
            if denied:
                session = self._append(
                    session,
                    RuntimeEventType.TOOL_FAILED,
                    "工具执行失败",
                    data={"tool_id": tool_id, "error": denied},
                )
                return session, self._fail(session, denied)
        if self._tool_executor is None:
            error = "tool executor not configured"
            session = self._append(
                session,
                RuntimeEventType.TOOL_FAILED,
                "工具执行失败",
                data={"tool_id": tool_id, "error": error},
            )
            return session, self._fail(session, error)
        session = self._append(
            session,
            RuntimeEventType.TOOL_STARTED,
            "工具开始执行",
            data={"tool_id": tool_id},
        )
        try:
            tool_result = self._tool_executor.execute(
                tool_id, tool_input, agent.id, context=context
            )
        except Exception as exc:  # noqa: BLE001 — 执行器兜底 → 明确失败
            error = f"tool executor error: {exc}"
            session = self._append(
                session,
                RuntimeEventType.TOOL_FAILED,
                "工具执行失败",
                data={"tool_id": tool_id, "error": error},
            )
            return session, self._fail(session, error)
        if not getattr(tool_result, "success", False):
            error = (
                str(getattr(tool_result, "error", "") or "") or f"tool failed: {tool_id}"
            )
            session = self._append(
                session,
                RuntimeEventType.TOOL_FAILED,
                "工具执行失败",
                data={"tool_id": tool_id, "error": error},
            )
            return session, self._fail(session, error)
        output = getattr(tool_result, "output", None)
        session = self._append(
            session,
            RuntimeEventType.TOOL_COMPLETED,
            "工具执行完成",
            data={"tool_id": tool_id, "output": output},
        )
        observation = {"status": "succeeded", "output": output or {}}
        session = self._add_step(
            session,
            AgentStepType.OBSERVATION,
            input={"action": action},
            output=observation,
        )
        session = self._append(
            session,
            RuntimeEventType.OBSERVATION_RECEIVED,
            "观察已接收",
            data=observation,
        )
        return session, None

    # ------------------------------------------------------------------ 主流程

    def run(
        self,
        task: Any,
        agent: Any,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """完整闭环: RECEIVE_TASK → (ANALYZE → DECISION → FINAL | ACTION → …)
        → COMPLETED|FAILED (每阶段写 Session, 不静默; 不抛未处理异常)。

        返回 {runtime_session_id, status, output, execution_steps} — status
        终态 success|failed; execution_steps = Loop 步骤链 (RECEIVE_TASK→…→
        FINAL, 保序)。单轮 FINAL = 旧流程 (Task→LLM→Result) 兼容。
        """
        if self._state != ExecutionState.CREATED:
            raise ExecutionLoopError(
                f"loop cannot run from state {self._state.value!r} (only CREATED)"
            )
        self.transition(ExecutionState.RUNNING)
        session = self._session
        try:
            # 1) 接收任务 (步骤 + 时间线锚点事件)
            session = self._add_step(
                session,
                AgentStepType.RECEIVE_TASK,
                input={"task_id": task.id, "agent_id": agent.id},
            )
            session = self._append(
                session,
                RuntimeEventType.AGENT_STARTED,
                "Agent 已唤醒",
                data={"agent_id": agent.id, "task_id": task.id},
            )
            session = self._append(
                session,
                RuntimeEventType.TASK_RECEIVED,
                f"接收任务 {getattr(task, 'title', '')}",
                data={"task_id": task.id, "title": str(getattr(task, "title", ""))},
            )

            # --- S10-019: 启动阶段 Skill 装配 (条件触发 — 仅 Agent 有已注册 Skill)
            # resolve_agent_skills: agent.skills 已注册 id 优先 → 系统映射兜底
            # (backend-1→backend.development …); 无技能 Agent → [] → 零 skill_*
            # 事件 + 不校验权限链 (既有精确事件链零污染)。skill_loaded 在
            # agent_started/task_received 之后 (启动阶段收尾), 循环开始前。
            if self._skill_registry is not None:
                agent_skills = resolve_agent_skills(agent, self._skill_registry)
                self._agent_skills = agent_skills
                if agent_skills:
                    skill_ctx = skill_context_for(
                        agent.id, agent_skills, self._skill_registry
                    )
                    self._skill_context = skill_ctx
                    session = self._append(
                        session,
                        RuntimeEventType.SKILL_LOADED,
                        "技能已加载",
                        data={
                            "agent_id": agent.id,
                            "skill": skill_ctx.active_skill,
                            "available_tools": list(skill_ctx.available_tools),
                        },
                    )

            # 2) Reason → Act → Observe 循环 (收敛 → FINAL; 超限 → 诚实 FAILED)
            round_no = 1
            while True:
                if round_no > MAX_ROUNDS:
                    return self._fail(
                        session,
                        "execution loop did not converge "
                        f"after {MAX_ROUNDS} rounds (action required repeatedly)",
                    )
                self.transition(ExecutionState.WAITING_DECISION)

                # --- ANALYZE (思考) ---
                task_context = self._build_task_context(task, agent.id, context)
                session = self._add_step(
                    session,
                    AgentStepType.ANALYZE,
                    input={"task_context": task_context, "round": round_no},
                )
                session = self._append(
                    session,
                    RuntimeEventType.THINKING_STARTED,
                    "开始分析",
                    data={"round": round_no},
                )

                # --- DECISION (决策) ---
                # S10-019: 决策前 skill_selected 事件 (thinking_started 之后、
                # decision_created 之前 — Planner 决策可见职业能力边界) + 把
                # SkillContext 并入 planner context (context.skill_context:
                # active_skill/instructions/available_tools/constraints — 职业
                # 能力快照, 不覆盖调用方原始 context, 仅条件触发时有技能 Agent)。
                planner_context = context
                if self._skill_context is not None:
                    session = self._append(
                        session,
                        RuntimeEventType.SKILL_SELECTED,
                        "技能已选择",
                        data={
                            "round": round_no,
                            "skill": self._skill_context.active_skill,
                        },
                    )
                    planner_context = dict(context or {})
                    planner_context["skill_context"] = self._skill_context.model_dump()
                try:
                    decision = self._planner.plan(task, planner_context)
                except Exception as exc:  # noqa: BLE001 — planner 兜底 → FAILED
                    return self._fail(session, f"planner error: {exc}")
                session = self._add_step(
                    session,
                    AgentStepType.DECISION,
                    output={
                        "type": decision.type.value,
                        "reason": decision.reason or "",
                    },
                )
                session = self._append(
                    session,
                    RuntimeEventType.DECISION_CREATED,
                    "决策已生成",
                    data={
                        "type": decision.type.value,
                        "reason": decision.reason or "",
                    },
                )

                # --- ACTION_REQUIRED: 动作边界 ---
                # S10-018 Task 001: action.type == "tool" → ToolExecutor 分支
                # (tool_requested→tool_started→tool_completed→observation_received;
                # 失败 → tool_failed→execution_failed); 其余 (noop) → Mock
                # ActionExecutor 旧流程 (S10-017 兼容)。
                if decision.type == DecisionType.ACTION_REQUIRED:
                    self.transition(ExecutionState.WAITING_ACTION)
                    action = dict((decision.payload or {}).get("action") or {})
                    session = self._add_step(
                        session,
                        AgentStepType.ACTION,
                        input={"action": action},
                    )
                    if str(action.get("type") or "").strip() == "tool":
                        session, tool_result = self._run_tool_action(
                            session, action, agent, context
                        )
                        if tool_result is not None:
                            return tool_result
                        self.transition(ExecutionState.RUNNING)
                        round_no += 1
                        continue
                    session = self._append(
                        session,
                        RuntimeEventType.ACTION_REQUESTED,
                        "请求执行动作",
                        data={"action": action},
                    )
                    try:
                        action_result = self._action_executor.execute(action)
                    except Exception as exc:  # noqa: BLE001 — 动作器兜底
                        action_result = ActionResult(
                            status=ActionResultStatus.FAILED,
                            error=f"action executor error: {exc}",
                        )
                    observation = {
                        "status": action_result.status.value,
                        "output": action_result.output or {},
                    }
                    if action_result.error:
                        observation["error"] = action_result.error
                    session = self._add_step(
                        session,
                        AgentStepType.OBSERVATION,
                        input={"action": action},
                        output=observation,
                    )
                    session = self._append(
                        session,
                        RuntimeEventType.OBSERVATION_RECEIVED,
                        "观察已接收",
                        data=observation,
                    )
                    self.transition(ExecutionState.RUNNING)
                    round_no += 1
                    continue

                # --- FINAL: 复用 runtime.execute (旧流程 Task→LLM→Result) ---
                # 执行前置校验 (诚实 FAILED 不伪造): 无 runtime (无 Provider)
                # 或 context 缺 project_dir (无法构造执行请求) → 在 LLM 事件
                # 之前响亮失败 (Provider Adapter Interface 语义)。
                self.transition(ExecutionState.RUNNING)
                project_dir = str((context or {}).get("project_dir") or "").strip()
                if self._runtime is None or not project_dir:
                    return self._fail(
                        session,
                        "no LLM provider configured (provider key missing)",
                    )
                request = self._build_request(task, agent, context)
                provider_id = self._provider_id()
                session = self._append(
                    session,
                    RuntimeEventType.LLM_REQUEST_SENT,
                    "LLM 请求已发送",
                    data={"provider_id": provider_id, "task_id": task.id},
                )
                try:
                    result = self._runtime.execute(
                        request, employee=agent, agent_instance=agent
                    )
                except Exception as exc:  # noqa: BLE001 — 编排层兜底
                    return self._fail(session, f"execution error: {exc}")

                _status = getattr(result, "status", None)
                status_value = (
                    getattr(_status, "value", "") if _status is not None else ""
                )
                session = self._append(
                    session,
                    RuntimeEventType.LLM_RESPONSE_RECEIVED,
                    "LLM 响应已接收",
                    data={"provider_id": provider_id, "status": status_value},
                )

                if result.is_success:
                    report = str(getattr(result, "report", "") or "")
                    usage = dict(getattr(result, "usage", None) or {})
                    artifacts = list(getattr(result, "artifacts", None) or [])
                    summary = (
                        f"success · {getattr(result, 'duration', 0.0):.1f}s · "
                        f"{len(artifacts)} 产物 · usage={usage}"
                    )
                    session = self._append(
                        session,
                        RuntimeEventType.OUTPUT_GENERATED,
                        "执行输出已生成",
                        data={"summary": summary},
                    )
                    session = self._add_step(
                        session,
                        AgentStepType.FINAL,
                        output={"summary": summary, "execution_output": report},
                    )
                    session = self._append(
                        session,
                        RuntimeEventType.EXECUTION_COMPLETED,
                        "执行完成",
                        data={"status": "success"},
                    )
                    self.transition(ExecutionState.COMPLETED)
                    return self._finish(session, summary=summary, report=report)

                # 失败 (ExecutionResult failed — Provider 错误/沙箱错误等)
                error = str(getattr(result, "error", "") or "")
                return self._fail(session, error or "execution failed (no error detail)")
        except ExecutionLoopError:
            raise
        except Exception as exc:  # noqa: BLE001 — 编排层兜底: 意外异常 → FAILED
            return self._fail(session, f"execution loop error: {exc}")


__all__ = [
    "ACTION_REQUIRED",
    "FINAL",
    "ActionResult",
    "ActionResultStatus",
    "AgentExecutionLoop",
    "Decision",
    "DecisionType",
    "ExecutionLoopError",
    "ExecutionState",
    "LLMPlanner",
    "MAX_ROUNDS",
    "MockActionExecutor",
    "Planner",
]
