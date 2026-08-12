"""factory-console/api/runtime_session.py — S10-016 Runtime Session API 路由函数。

AI Employee Runtime Foundation (Task 001b): Agent 执行会话可见性底座 — 谁在跑/
跑哪个任务/跑到哪一步/产出什么事件。Domain (exec.runtime_session) 已 GREEN
(五态状态机 + 7 类型事件链 + 原子写持久化); Service 层 (ConsoleService 8 方法)
做失败安全装配 + 输入校验; 本模块只做路由函数 (无 Web 依赖, FastAPI 薄层
做 HTTP 绑定 — 同 api/runtime.py 模式)。

路由函数 (HTTP 端点由 fastapi_adapter 绑定):
- create_runtime_session:    POST /agents/{agent_id}/sessions — 创建 PENDING 会话
- start_runtime_session:     POST /runtime-sessions/{id}/start — PENDING → RUNNING
- append_runtime_session_event: POST /runtime-sessions/{id}/events — 追加执行事件
- complete_runtime_session:  POST /runtime-sessions/{id}/complete — → SUCCESS|FAILED
- cancel_runtime_session:    POST /runtime-sessions/{id}/cancel — → CANCELLED
- list_runtime_sessions:     GET /runtime-sessions?status=running — 运行中清单
- get_runtime_session:       GET /runtime-sessions/{id} — 详情 (含事件链)
- get_task_runtime_sessions: GET /tasks/{task_id}/runtime — 按 task_id 过滤

错误语义 (Service 层抛出, HTTP 层映射):
- ValueError → 400 (空 task_id / 非法事件类型)
- RuntimeSessionError → 409 (状态机非法流转 — PENDING→complete 等)
- None → 404 (session 不存在 / store 缺失)

审计: 端点命中 → console.viewed (view=runtime_sessions) — ADR-0002 读审计
同语义; logger=None 静默 (失败安全)。
"""

from __future__ import annotations

from typing import Any

from ..events import record_console_viewed

__all__ = [
    "append_runtime_session_event",
    "cancel_runtime_session",
    "complete_runtime_session",
    "create_runtime_session",
    "get_runtime_session",
    "get_task_runtime_sessions",
    "list_runtime_sessions",
    "start_runtime_session",
]


def create_runtime_session(
    service: Any,
    agent_id: str,
    *,
    task_id: str = "",
    workflow_id: str = "",
    logger: Any = None,
) -> Any | None:
    """POST /agents/{agent_id}/sessions — 创建 Runtime Session (PENDING)。

    {task_id, workflow_id?}: task_id 必填 (空 → ValueError → 400 — Session
    必须锚定 Task); workflow_id 可选 (独立执行无工作流)。store 缺失/落库
    失败 → None (404 — 失败安全)。成功 → RuntimeSession dict 形状模型
    (session_id/agent_id/task_id/workflow_id/status/events)。审计:
    console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.create_session(
        agent_id, task_id, workflow_id=workflow_id
    )


def start_runtime_session(
    service: Any,
    session_id: str,
    *,
    logger: Any = None,
) -> Any | None:
    """POST /runtime-sessions/{id}/start — PENDING → RUNNING (started_at)。

    不存在 → None (404); 非 PENDING → RuntimeSessionError (409)。审计:
    console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.start_session(session_id)


def append_runtime_session_event(
    service: Any,
    session_id: str,
    *,
    event_type: str = "",
    message: str = "",
    data: dict[str, Any] | None = None,
    logger: Any = None,
) -> Any | None:
    """POST /runtime-sessions/{id}/events — 追加执行事件 (仅 RUNNING)。

    {type, message?, data?}: 非法事件类型 → ValueError (400); 非 RUNNING →
    RuntimeSessionError (409); 不存在 → None (404)。成功 → RuntimeEvent
    (event_id/type/message/data)。审计: console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.append_event(
        session_id, event_type, message, data=data
    )


def complete_runtime_session(
    service: Any,
    session_id: str,
    *,
    success: bool = True,
    logger: Any = None,
) -> Any | None:
    """POST /runtime-sessions/{id}/complete — RUNNING → SUCCESS|FAILED。

    {success}: true → SUCCESS / false → FAILED (finished_at 记录)。不存在
    → None (404); 非 RUNNING → RuntimeSessionError (409)。审计:
    console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.complete_session(session_id, success=success)


def cancel_runtime_session(
    service: Any,
    session_id: str,
    *,
    logger: Any = None,
) -> Any | None:
    """POST /runtime-sessions/{id}/cancel — RUNNING → CANCELLED。

    不存在 → None (404); 非 RUNNING → RuntimeSessionError (409)。审计:
    console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.cancel_session(session_id)


def list_runtime_sessions(
    service: Any,
    *,
    status: str | None = None,
    logger: Any = None,
) -> list[Any]:
    """GET /runtime-sessions?status=running — 会话清单 (运行中过滤)。

    status=running → 只返回 RUNNING 会话 (含事件链 — 前端 RuntimeActivity
    数据源); status 缺省/其他 → 全部会话 (list_all 按 id 排序)。缺 store →
    [] (失败安全)。审计: console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    if status == "running":
        return service.list_running_sessions()
    return service.list_running_sessions() if status is None else []


def get_runtime_session(
    service: Any,
    session_id: str,
    *,
    logger: Any = None,
) -> Any | None:
    """GET /runtime-sessions/{id} — 会话详情 (含保序事件时间线)。

    不存在 → None (404)。审计: console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.get_session(session_id)


def get_task_runtime_sessions(
    service: Any,
    task_id: str,
    *,
    logger: Any = None,
) -> list[Any]:
    """GET /tasks/{task_id}/runtime — 按 task_id 过滤会话 (多次执行 = 多条)。

    无匹配/缺 store → [] (200 诚实空态 — 与 404 语义区分: task 查询不因
    空结果报错)。审计: console.viewed (view=runtime_sessions)。
    """
    record_console_viewed(logger, view="runtime_sessions", count=1)
    return service.get_sessions_by_task(task_id)
