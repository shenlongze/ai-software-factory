"""factory-exec/exec/agent_executor.py — AgentExecutor (S10-016 Task 002 编排层
+ S10-017 Task 001 Execution Loop 重构)。

设计依据 (S10-016-task002 用户约束 + S10-017-task001 Execution Loop):
```
Task → Agent Assignment → Agent Executor → Execution Loop → Output
                            ↑                    ↑
                  Runtime Session (Task 001)   AgentExecutionLoop (S10-017)
```

职责 (编排层 — 不重写 AgentRuntime/Provider 执行逻辑):
- 接收任务 (task_id/agent_id) → 校验 Task/Agent 存在 → 创建 Runtime Session
  (PENDING → RUNNING) → 交给 AgentExecutionLoop 编排 (RECEIVE_TASK → ANALYZE
  → DECISION → FINAL|WAITING_ACTION → COMPLETED|FAILED) → 返回
  {runtime_session_id, status, output, execution_steps}。
- Loop 内部复用 AgentRuntime.execute() (真实 LLM Provider, 零复制) + 写
  Runtime Events (agent_started → task_received → thinking_started →
  decision_created → llm_request_sent → llm_response_received →
  output_generated → execution_completed|failed) → complete SUCCESS|FAILED。
- 外部 API 不变 (execute_task 签名/错误语义), 返回新增 execution_steps
  (Loop 步骤链 RECEIVE_TASK→…→FINAL, 保序)。

执行权归属铁律 (同 agent_runtime 设计):
- 拥有执行权: AgentRuntime (本模块只做 Session 生命周期 + 校验 + 编排委托)
- 复用 Provider: 本模块不新建 LLM 调用方式 / 不 Hardcode Provider —
  runtime 由装配方注入 (含 Provider), None → 诚实 FAILED (Provider Adapter
  Interface — 无 Provider 不伪造结果)。

错误处理 (用户约束 — 错误进事件不静默):
- Task 不存在 → TaskNotFoundError (HTTP 400, 不创建 Session)
- Agent 不存在 → AgentNotFoundError (HTTP 400, 不创建 Session)
- Loop 编排层兜底: runtime.execute 抛异常 / Provider 错误 / 执行失败 →
  execution_failed 事件 + complete(FAILED) + 错误信息进事件 data + output
  保留失败原因 — 任何异常不抛裸异常。

复用决策 (侦察结论):
- 复用: AgentExecutionLoop (S10-017 — Reason→Act→Observe→Complete 编排)、
  AgentRuntime.execute() (Task→LLM→Validation→Result 双路径)、
  Provider (ProviderRegistry/ProviderInterface)、RuntimeSession 状态机 +
  RuntimeSessionStore (Task 001)。
- 禁止: 重写 AgentRuntime/Provider/RuntimeSession 主逻辑 (本模块只 import
  复用); 不创建平行执行系统。
"""

from __future__ import annotations

from typing import Any

from .execution_loop import AgentExecutionLoop
from .runtime_session import (
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
    """Agent 执行编排层: Task → Session → Execution Loop → Result。

    构造 (依赖注入, 全部显式):
    - task_store: duck-typed get(task_id) → Task | None (Core TaskStore)。
    - agent_registry: duck-typed get(agent_id) → Agent | None (Core
      AgentRegistry)。
    - session_store: exec.runtime_session.RuntimeSessionStore (Task 001 持久化)。
    - runtime: AgentRuntime | None (执行引擎, 含 Provider; None = 无
      Provider → 诚实 FAILED — 不伪造 LLM 结果)。

    方法:
    - execute_task(task_id, agent_id, *, context=None) → dict
      {runtime_session_id, status, output, execution_steps} 完整闭环
      (编排; 不抛未处理异常, 校验失败除外)。S10-017 Task 001: 内部由
      AgentExecutionLoop 编排 (RECEIVE_TASK→ANALYZE→DECISION→FINAL|
      WAITING_ACTION→COMPLETED); 返回新增 execution_steps (Loop 步骤链)。
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

    # ------------------------------------------------------------------ 主流程

    def execute_task(
        self,
        task_id: str,
        agent_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """完整闭环: 校验 → Session (PENDING→RUNNING) → AgentExecutionLoop
        (RECEIVE_TASK→ANALYZE→DECISION→FINAL|WAITING_ACTION→COMPLETED) →
        {runtime_session_id, status, output, execution_steps}。

        status 终态 success|failed; output 保留 execution_output/
        execution_summary/raw_response; execution_steps = Loop 步骤链
        (RECEIVE_TASK→…→FINAL, 保序)。校验失败 (Task/Agent 不存在) → 抛
        TaskNotFoundError/AgentNotFoundError (HTTP 400, 不创建 Session);
        执行期任何异常 → FAILED session + 事件 (Loop 编排层兜底, 不抛裸异常)。
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

        # 2) Execution Loop 编排 (S10-017 — 状态变化写 Session, 不静默)
        #    Loop 默认装配: LLMPlanner (复用 runtime 的 Provider) +
        #    MockActionExecutor; FINAL 路径复用 runtime.execute (旧流程
        #    Task→LLM→Result); runtime None → 诚实 FAILED。
        loop = AgentExecutionLoop(
            session=session,
            session_store=self._session_store,
            runtime=self._runtime,
        )
        return loop.run(task, agent, context=context)


__all__ = [
    "AgentExecutor",
    "AgentExecutorError",
    "AgentNotFoundError",
    "TaskNotFoundError",
]
