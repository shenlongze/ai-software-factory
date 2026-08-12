"""factory-console/api/agent_executor.py — S10-016 Task 002 Agent Executor API 路由函数。

AI Employee Runtime Foundation (Task 002): Agent 全链路执行入口 — Task/Agent
校验 → Runtime Session → LLM (复用 AgentRuntime/Provider) → 事件链 →
SUCCESS|FAILED → {runtime_session_id, status, output}。Domain
(exec.agent_executor 编排层) 已 GREEN; Service 层 (ConsoleService.
execute_runtime_task) 做注入/自装配 + 输入校验 + AgentExecutorError 归一;
本模块只做路由函数 (无 Web 依赖, FastAPI 薄层做 HTTP 绑定 — 同
api/runtime_session.py 模式)。

路由函数 (HTTP 端点由 fastapi_adapter 绑定):
- execute_runtime_task: POST /api/runtime/execute — Agent 全链路执行

错误语义 (Service 层抛出, HTTP 层映射):
- ValueError → 400 (空 task_id/agent_id; Task/Agent 不存在 — AgentExecutorError
  由 service 归一为 ValueError)
- None → 404 (store/exec 未装配 — 失败安全)
- LLM Provider 失败 → 200 status=failed + output 保留 (不抛裸异常 — 错误进
  事件链, 由编排层兜底)

审计: 端点命中 → console.viewed (view=runtime_execute) — ADR-0002 读审计
同语义; logger=None 静默 (失败安全)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

__all__ = ["execute_runtime_task"]


def execute_runtime_task(
    service: Any,
    task_id: str,
    agent_id: str,
    *,
    context: dict[str, Any] | None = None,
    logger: Any = None,
) -> Any | None:
    """POST /api/runtime/execute — Agent 全链路执行 (编排闭环)。

    {task_id, agent_id, context?} → {runtime_session_id, status, output}:
    - status 终态 success|failed (LLM Provider 失败 → failed + output 保留
      失败原因, 不 5xx — 错误进事件链)
    - 空 task_id/agent_id / Task 不存在 / Agent 不存在 → ValueError (HTTP 400
      — AgentExecutorError 由 service 归一, 不创建 Session)
    - store/exec 未装配 → None (HTTP 404 — 失败安全)
    context: 执行上下文 (project_dir/requirement/instruction — 透传给
    AgentExecutor._build_task_context)。审计: console.viewed
    (view=runtime_execute)。
    """
    record_console_viewed(logger, view="runtime_execute", count=1)
    return service.execute_runtime_task(task_id, agent_id, context=context)
