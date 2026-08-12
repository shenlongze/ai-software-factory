"""factory-exec/exec/agent_executor.py — AgentExecutor (S10-016 Task 002 编排层)。

设计依据 (S10-016-task002 用户约束 + Task 001 RuntimeSession Domain 侦察):
```
Task → Agent Assignment → Agent Executor → LLM Execution → Output
                            ↑                      ↑
                  Runtime Session (Task 001)   AgentRuntime (复用)
```

职责 (编排层 — 不重写 AgentRuntime/Provider 执行逻辑):
- 接收任务 (task_id/agent_id) → 校验 Task/Agent 存在 → 创建 Runtime Session
  (PENDING → RUNNING) → 组装 Task Context → 复用 AgentRuntime.execute()
  (真实 LLM Provider, 零复制) → 写 Runtime Events (agent_started →
  task_received → llm_request_sent → llm_response_received →
  output_generated → execution_finished|failed) → complete SUCCESS|FAILED
  → 返回 {runtime_session_id, status, output}。

执行权归属铁律 (同 agent_runtime 设计):
- 拥有执行权: AgentRuntime (本模块只做 Session 生命周期 + 事件记录 + 错误映射)
- 复用 Provider: 本模块不新建 LLM 调用方式 / 不 Hardcode Provider —
  runtime 由装配方注入 (含 Provider), None → 诚实 FAILED (Provider Adapter
  Interface — 无 Provider 不伪造结果)。

错误处理 (用户约束 — 错误进事件不静默):
- Task 不存在 → TaskNotFoundError (HTTP 400, 不创建 Session)
- Agent 不存在 → AgentNotFoundError (HTTP 400, 不创建 Session)
- runtime.execute 抛异常 / Provider 错误 / 执行失败 → execution_failed 事件
  + complete(FAILED) + 错误信息进事件 data + output 保留失败原因 — 任何
  异常不抛裸异常 (编排层兜底)。

Output 保留 (用户约束 — 不要求完整 Artifact Center):
- execution_output / execution_summary / raw_response 落 RuntimeSession
  字段 (Task 002 最小扩展; 可跨重启查询)。

复用决策 (侦察结论):
- 复用: AgentRuntime.execute() (Task→LLM→Validation→Result 双路径)、
  Provider (ProviderRegistry/ProviderInterface)、RuntimeSession 状态机 +
  RuntimeSessionStore (Task 001)。
- 禁止: 重写 AgentRuntime/Provider/RuntimeSession 主逻辑 (本模块只 import
  复用); 不创建平行执行系统。
"""

from __future__ import annotations

from typing import Any

from .models import ExecutionRequest, new_id
from .runtime_session import (
    RuntimeEventType,
    RuntimeSession,
    new_session_id,
)


class AgentExecutorError(Exception):
    """AgentExecutor 业务错误基类 (Task/Agent 校验失败 → HTTP 400)。"""


class TaskNotFoundError(AgentExecutorError):
    """Invalid Task — task_id 在 TaskStore 不存在 (HTTP 层 400)。"""


class AgentNotFoundError(AgentExecutorError):
    """Agent Not Found — agent_id 在 AgentRegistry 不存在 (HTTP 层 400)。"""


class AgentExecutor:
    """Agent 执行编排层: Task → Session → AgentRuntime → Events → Result。

    构造 (依赖注入, 全部显式):
    - task_store: duck-typed get(task_id) → Task | None (Core TaskStore)。
    - agent_registry: duck-typed get(agent_id) → Agent | None (Core
      AgentRegistry)。
    - session_store: exec.runtime_session.RuntimeSessionStore (Task 001 持久化)。
    - runtime: AgentRuntime | None (执行引擎, 含 Provider; None = 无
      Provider → 诚实 FAILED — 不伪造 LLM 结果)。

    方法:
    - execute_task(task_id, agent_id, *, context=None) → dict
      {runtime_session_id, status, output} 完整闭环 (编排; 不抛未处理异常,
      校验失败除外)。
    """

    def __init__(
        self,
        *,
        task_store: Any,
        agent_registry: Any,
        session_store: Any,
        runtime: Any = None,
    ) -> None:
        self._task_store = task_store
        self._agent_registry = agent_registry
        self._session_store = session_store
        self._runtime = runtime

    # ------------------------------------------------------------------ 校验

    def _require_task(self, task_id: str) -> Any:
        """Task 存在性校验 (不存在 → TaskNotFoundError — HTTP 400)。"""
        task = self._task_store.get(task_id) if self._task_store is not None else None
        if task is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        return task

    def _require_agent(self, agent_id: str) -> Any:
        """Agent 存在性校验 (不存在 → AgentNotFoundError — HTTP 400)。"""
        agent = (
            self._agent_registry.get(agent_id)
            if self._agent_registry is not None
            else None
        )
        if agent is None:
            raise AgentNotFoundError(f"agent not found: {agent_id}")
        return agent

    # ------------------------------------------------------------------ 上下文

    @staticmethod
    def _build_task_context(task: Any, agent_id: str, context: dict[str, Any] | None) -> str:
        """组装 Task Context (用户约束: task description + project context +
        workflow stage + requirements)。

        task 为 Core Task (title/project/type/workflow); requirements 来自
        context.requirement (调用方验收标准); 补充指令 context.instruction。
        """
        ctx = context or {}
        parts = [
            f"任务: {task.title} (id: {task.id})",
            f"项目: {task.project}",
            f"类型: {task.type}",
            f"工作流阶段: {task.workflow or '(无工作流)'}",
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
        self, task: Any, agent_id: str, context: dict[str, Any] | None
    ) -> ExecutionRequest:
        """构造 ExecutionRequest (只声明意图 — 执行权在 AgentRuntime)。"""
        task_context = self._build_task_context(task, agent_id, context)
        ctx = context or {}
        project_dir = str(ctx.get("project_dir") or "").strip()
        return ExecutionRequest(
            id=new_id("EXR"),
            task_id=task.id,
            objective=task.title,
            requirement=task_context,
            input={
                "project_dir": project_dir,
                "agent_id": agent_id,
                "task_context": task_context,
                "workflow_stage": task.workflow or "",
            },
        )

    # ------------------------------------------------------------------ 事件辅助

    def _append(self, session: RuntimeSession, event_type, message: str, data=None) -> RuntimeSession:
        """追加事件 + 落库 (RUNNING 状态保证 — 编排层全程 RUNNING)。"""
        updated, _event = session.append_event(event_type, message, data=data)
        self._session_store.save(updated)
        return updated

    def _finish(
        self,
        session: RuntimeSession,
        *,
        success: bool,
        output: dict[str, str],
    ) -> dict[str, Any]:
        """complete SUCCESS|FAILED + Output 保留 (execution_output/summary/
        raw_response) + 落库; 返回 API 形状 {runtime_session_id, status, output}。"""
        finished = session.complete(success=success)
        finished = finished.model_copy(
            update={
                "execution_output": output.get("execution_output", ""),
                "execution_summary": output.get("execution_summary", ""),
                "raw_response": output.get("raw_response", ""),
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
        }

    def _fail(self, session: RuntimeSession, error: str) -> dict[str, Any]:
        """失败路径 (错误进事件不静默): execution_failed 事件 (data 带 error)
        → complete(FAILED) → Output 保留失败原因。"""
        session = self._append(
            session,
            RuntimeEventType.EXECUTION_FAILED,
            "执行失败",
            data={"error": error[:1000]},
        )
        return self._finish(
            session,
            success=False,
            output={
                "execution_output": error,
                "execution_summary": f"failed · {error[:200]}",
                "raw_response": error,
            },
        )

    # ------------------------------------------------------------------ 主流程

    def execute_task(
        self,
        task_id: str,
        agent_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """完整闭环: 校验 → Session (PENDING→RUNNING) → Task Context →
        AgentRuntime.execute() (复用 Provider) → 事件链 → SUCCESS|FAILED。

        返回 {runtime_session_id, status, output} — status 终态 success|
        failed; output 保留 execution_output/execution_summary/raw_response。
        校验失败 (Task/Agent 不存在) → 抛 TaskNotFoundError/AgentNotFoundError
        (HTTP 400, 不创建 Session); 执行期任何异常 → FAILED session + 事件
        (不抛裸异常)。
        """
        task = self._require_task(task_id)
        agent = self._require_agent(agent_id)

        # 1) 创建 Runtime Session (PENDING → RUNNING)
        session = RuntimeSession(
            session_id=new_session_id(),
            agent_id=agent_id,
            task_id=task_id,
            workflow_id=str(getattr(task, "workflow", "") or ""),
        )
        self._session_store.save(session)
        session = session.start()
        self._session_store.save(session)

        # 2) Agent Started / Task Received 事件 (时间线锚点)
        session = self._append(
            session,
            RuntimeEventType.AGENT_STARTED,
            "Agent 已唤醒",
            data={"agent_id": agent_id, "task_id": task_id},
        )
        session = self._append(
            session,
            RuntimeEventType.TASK_RECEIVED,
            f"接收任务 {task.title}",
            data={"task_id": task_id, "title": str(getattr(task, "title", ""))},
        )

        # 3) 无 Provider → 诚实 FAILED (Provider Adapter Interface, 不伪造结果)
        if self._runtime is None:
            return self._fail(session, "no LLM provider configured (provider key missing)")

        # 4) 组装 ExecutionRequest (Task Context: description/project/stage/requirements)
        request = self._build_request(task, agent_id, context)

        # 5) LLM Request Sent 事件 → 复用 AgentRuntime.execute() → Response Received
        provider_id = getattr(
            getattr(self._runtime, "developer", None), "provider", None
        )
        provider_id = getattr(provider_id, "provider_id", "") or ""
        session = self._append(
            session,
            RuntimeEventType.LLM_REQUEST_SENT,
            "LLM 请求已发送",
            data={"provider_id": provider_id, "task_id": task_id},
        )
        try:
            result = self._runtime.execute(request, employee=agent, agent_instance=agent)
        except Exception as exc:  # noqa: BLE001 — 编排层兜底: 意外异常 → FAILED
            return self._fail(session, f"execution error: {exc}")

        _status = getattr(result, "status", None)
        status_value = getattr(_status, "value", "") if _status is not None else ""
        session = self._append(
            session,
            RuntimeEventType.LLM_RESPONSE_RECEIVED,
            "LLM 响应已接收",
            data={
                "provider_id": provider_id,
                "status": status_value,
            },
        )

        # 6) 结果处理: 成功 → output_generated + execution_finished;
        #    失败 → execution_failed (错误进事件不静默)
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
            session = self._append(
                session,
                RuntimeEventType.EXECUTION_FINISHED,
                "执行完成",
                data={"status": "success"},
            )
            return self._finish(
                session,
                success=True,
                output={
                    "execution_output": report,
                    "execution_summary": summary,
                    "raw_response": report,
                },
            )

        # 失败 (ExecutionResult failed — Provider 错误/沙箱错误等)
        error = str(getattr(result, "error", "") or "")
        return self._fail(session, error or "execution failed (no error detail)")


__all__ = [
    "AgentExecutor",
    "AgentExecutorError",
    "AgentNotFoundError",
    "TaskNotFoundError",
]
