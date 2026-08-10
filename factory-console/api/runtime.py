"""factory-console/api/runtime.py — S10-002 Runtime API 路由函数 (Sprint 10)。

设计依据 (docs/sprint10/api-data-model.md §3-4 + workspace-architecture.md §6):
CLI 与 UI 共用同一 Runtime API; Adapter 层只消费 org.* 查询 + events 流
(不修改 Core Workflow/Artifact/Approval — 冻结铁律)。

路由函数 (无 Web 依赖, FastAPI 薄层做 HTTP 绑定):
- get_project_workflow: GET /projects/{id}/workflow — 项目工作流详情
  (mock fallback: 项目存在但无运行数据 → is_mock=True 演示数据, 诚实标注)
- get_workflow_stages: GET /workflows/{id}/stages — 阶段运行明细
  (状态/agent/artifacts/duration/cost; duration 从事件流推导)
- get_project_timeline: GET /projects/{id}/timeline — Timeline 事件聚合
  (user/stage/artifact/review/error 五类, 与 SSE 同源同映射)
- iter_sse_events: SSE /events/stream — 事件流生成器 (纯函数, 可单测)

SSE 事件映射 (api-data-model §4 契约 → S10-002 事件名; 业务事件 7 类
+ error 失败/降级通道):
  org.workflow.stage_started   → stage.started      {stage_id, agent_id, name}
  org.workflow.stage_completed → stage.completed    {stage_id, artifact_id,
                                                     duration_s, cost_usd}
  org.artifact.created         → artifact.created   {artifact_id, type}
  org.approval.created         → approval.required  {stage_id, gate_id}
  org.approval.approved        → approval.completed {stage_id, gate_id}
  org.runtime.created          → runtime.created    {instance_id, type, status,
                                                     artifact_id, project_id}
  org.runtime.status_changed   → runtime.status.changed {instance_id, status,
                                                     previous_status}
  org.workflow.failed / org.artifact.failed → error {stage_id, reason}
其余 org.* 事件 (stage_ready/approved 等) 不进 SSE 流 (KISS, 前端订阅
业务 7 类 + error 通道)。runtime.* 事件为契约先行 (S10-004 Runtime 服务
发射点), 实现前无真实事件, 映射/形状已由测试锁定。

审计: 端点命中 → console.viewed (view=project_workflow|workflow_stages|
project_timeline|events_stream) — ADR-0002 读审计同语义; logger=None 静默。
"""

from __future__ import annotations

import time
from typing import Any, Iterator

from ..events import (
    record_console_viewed,
    record_runtime_created,
    record_runtime_status_changed,
)
from ..models import (
    RuntimeInstance,
    RuntimeScreenshot,
    StageRunSummary,
    TimelineEventSummary,
    WorkflowDetail,
)
from ..service import RuntimeStateError

#: SSE 事件映射 (org 事件类型 → SSE 事件名; 只推送七类)。
SSE_EVENT_MAP: dict[str, str] = {
    "org.workflow.stage_started": "stage.started",
    "org.workflow.stage_completed": "stage.completed",
    "org.artifact.created": "artifact.created",
    "org.approval.created": "approval.required",
    "org.approval.approved": "approval.completed",
    "org.workflow.failed": "error",
    "org.artifact.failed": "error",
    # S10-002: Runtime Instance 生命周期 (S10-004 Runtime 服务发射点 —
    # 契约先行: 该服务按 org.runtime.* 事件名落库, SSE 同映射; 发射点
    # 实现前无真实事件, 映射/形状已定并测试锁定)。
    "org.runtime.created": "runtime.created",
    "org.runtime.status_changed": "runtime.status.changed",
}

__all__ = [
    "SSE_EVENT_MAP",
    "get_project_timeline",
    "get_project_workflow",
    "get_workflow_stages",
    "iter_sse_events",
]


def get_project_workflow(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> WorkflowDetail | None:
    """GET /projects/{id}/workflow — 项目工作流详情 (mock fallback 标注)。

    真实 workflow → WorkflowDetail (is_mock=False); 项目存在但无运行数据
    → mock 工作流 (is_mock=True — 前端可展示不崩溃, 明确标注不冒充真实);
    项目不存在 → None (HTTP 层 404)。审计: console.viewed
    (view=project_workflow / project_workflow_mock)。
    """
    detail = service.get_project_workflow(project_id)
    if detail is not None:
        record_console_viewed(
            logger, view="project_workflow", count=1, project_id=project_id
        )
        return detail
    if not service.project_exists(project_id):
        return None  # 项目不存在 → 404 (mock 只兜底数据缺失, 不兜底不存在)
    record_console_viewed(
        logger, view="project_workflow_mock", count=1, project_id=project_id
    )
    return service.build_mock_workflow(project_id)


def get_workflow_stages(
    service: Any,
    workflow_id: str,
    *,
    logger: Any = None,
) -> list[StageRunSummary] | None:
    """GET /workflows/{id}/stages — 阶段运行明细 (状态/agent/artifacts/
    duration/cost); 无 org/不存在 → None (HTTP 层 404)。审计: console.viewed
    (view=workflow_stages)。
    """
    runs = service.get_workflow_stage_runs(workflow_id, event_logger=logger)
    if runs is None:
        return None
    record_console_viewed(logger, view="workflow_stages", count=len(runs))
    return runs


def get_project_timeline(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
    limit: int = 200,
) -> list[TimelineEventSummary] | None:
    """GET /projects/{id}/timeline — Timeline 事件聚合 (五类节点)。

    项目不存在 → None (404); 无事件 → [] (诚实空态); 数据源 = events.db
    org.* 事件 (与 SSE 同源同映射 — Timeline 历史快照, SSE 增量推送)。
    审计: console.viewed (view=project_timeline)。
    """
    events = service.get_project_timeline(
        project_id, event_logger=logger, limit=limit
    )
    if events is None:
        return None
    record_console_viewed(
        logger, view="project_timeline", count=len(events), project_id=project_id
    )
    return events


def iter_sse_events(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
    since_seq: int = 0,
    poll_interval: float = 1.0,
    max_polls: int | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """SSE 事件生成器 (纯函数, 无 Web 依赖 — HTTP 层 StreamingResponse 包)。

    yield (event_name, data): stage.started / stage.completed /
    artifact.created / approval.required / error; 从 events 库按 project_id
    轮询 (since_seq 断点续推, max_polls=None → 持续到客户端断开)。

    mock fallback: 无事件库 (logger=None) → 立即 yield 一条 error 事件
    (mock=True 标注 — 前端据此显示演示/降级提示) 后结束; 轮询查询异常同
    语义 (失败安全, 不拖垮流)。审计: 连接时 console.viewed
    (view=events_stream) 一次 (逐轮询审计会刷屏, KISS)。
    """
    store = getattr(logger, "store", None) if logger is not None else None
    record_console_viewed(logger, view="events_stream", count=0, project_id=project_id)
    if store is None:
        yield "error", {
            "stage_id": None,
            "reason": "event store unavailable",
            "mock": True,
        }
        return
    polls = 0
    while max_polls is None or polls < max_polls:
        polls += 1
        try:
            events = store.query(project_id=project_id, since_seq=since_seq)
        except Exception:
            yield "error", {
                "stage_id": None,
                "reason": "event store unavailable",
                "mock": True,
            }
            return
        for event in events:
            mapped = _sse_event(event, store)
            if mapped is not None:
                yield mapped[0], mapped[1]
            if event.seq > since_seq:
                since_seq = event.seq
        if max_polls is not None and polls >= max_polls:
            return
        time.sleep(poll_interval)


# ------------------------------------------------------------------ 映射


def _sse_event(event: Any, store: Any) -> tuple[str, dict[str, Any]] | None:
    """org 事件 → (SSE 事件名, data) (SSE_EVENT_MAP; 未知类型 → None 跳过)。"""
    event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
    name = SSE_EVENT_MAP.get(event_type)
    if name is None:
        return None
    payload = dict(event.payload or {})
    stage_id = payload.get("stage_id")
    agent_id = payload.get("role_id") or event.agent_id
    if name == "stage.started":
        return name, {
            "stage_id": stage_id,
            "agent_id": agent_id,
            "name": payload.get("name") or "",
        }
    if name == "stage.completed":
        artifact_ids = payload.get("output_artifact_ids") or []
        artifact_id = artifact_ids[0] if artifact_ids else None
        return name, {
            "stage_id": stage_id,
            "agent_id": agent_id,
            "name": payload.get("name") or "",
            "artifact_id": artifact_id,
            "duration_s": _stage_duration_s(store, event, stage_id),
            "cost_usd": None,  # org 未跟踪成本 — 诚实 null
        }
    if name == "artifact.created":
        return name, {
            "artifact_id": payload.get("artifact_id"),
            "type": payload.get("type"),
        }
    if name == "approval.required":
        return name, {
            "stage_id": stage_id,
            "gate_id": payload.get("gate_id"),
        }
    # approval.completed: 审批放行 (org.approval.approved → 前端收尾通知)
    if name == "approval.completed":
        return name, {
            "stage_id": stage_id,
            "gate_id": payload.get("gate_id"),
            "workflow_id": payload.get("workflow_id"),
        }
    # runtime.created: Runtime 实例创建 (S10-004 发射; instance_id 取
    # payload.instance_id, 兼容 fallback 到 artifact_id 绑定维度)
    if name == "runtime.created":
        return name, {
            "instance_id": payload.get("instance_id"),
            "type": payload.get("type"),
            "status": payload.get("status"),
            "artifact_id": payload.get("artifact_id"),
            "project_id": payload.get("project_id") or event.project_id,
        }
    # runtime.status.changed: 实例状态流转 (starting|running|stopped|error)
    if name == "runtime.status.changed":
        return name, {
            "instance_id": payload.get("instance_id"),
            "status": payload.get("status"),
            "previous_status": payload.get("previous_status"),
        }
    # error: org.workflow.failed (reason) / org.artifact.failed (artifact_id)
    return name, {
        "stage_id": stage_id,
        "artifact_id": payload.get("artifact_id"),
        "reason": payload.get("reason") or "",
        "workflow_id": payload.get("workflow_id"),
    }


def _stage_duration_s(store: Any, completed_event: Any, stage_id: Any) -> float | None:
    """stage.completed 事件 → duration_s (最近一次 stage_started 时间戳差)。

    无 started 事件/查询失败 → None (诚实不臆造); 重试场景取最近一次
    started (倒序遍历, 与 completed 对齐)。
    """
    if not stage_id or completed_event.project_id is None:
        return None
    try:
        from events.models import EventType

        started = store.query(
            project_id=completed_event.project_id,
            event_type=EventType.ORG_WORKFLOW_STAGE_STARTED,
        )
    except Exception:
        return None
    for event in reversed(started):  # 最近一次 started 优先
        if (event.payload or {}).get("stage_id") == stage_id:
            return round(
                (completed_event.timestamp - event.timestamp).total_seconds(), 3
            )
    return None


# ------------------------------------------------ S10-004: Runtime Workspace API
# Instance 模式 (workspace-architecture.md §4 调整版): "+" 创建 browser|terminal
# 实例 + start/stop 生命周期 + screenshot 预留。路由函数无 Web 依赖 (FastAPI
# 薄层做 HTTP 绑定); 事件发射: 创建 → org.runtime.created, 状态流转 →
# org.runtime.status_changed (字符串事件类型落库, SSE_EVENT_MAP 同映射 —
# S10-002 契约先行已锁定, 前端 SSE 零改动); 审计: console.viewed
# (view=runtime_create|runtimes|runtime_detail|runtime_start|runtime_stop|
# runtime_screenshot)。
#
# None 语义 (HTTP 层映射): 项目不存在 / 实例不存在 / store 缺失 → 404;
# RuntimeStateError (状态机非法流转) → 409; ValueError (非法 type) → 400。


def create_runtime(
    service: Any,
    project_id: str,
    runtime_type: str,
    artifact_id: str | None = None,
    *,
    logger: Any = None,
) -> RuntimeInstance | None:
    """POST /projects/{id}/runtimes — 创建 Runtime Instance (starting)。

    项目不存在 → None (404); 非法 type (非 browser|terminal) → ValueError
    (HTTP 层 400); 成功 → 落库 + org.runtime.created 事件 + 审计。
    """
    instance = service.create_runtime(project_id, runtime_type, artifact_id=artifact_id)
    if instance is None:
        return None
    record_runtime_created(logger, instance=instance)
    record_console_viewed(logger, view="runtime_create", count=1, project_id=project_id)
    return instance


def list_runtimes(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> list[RuntimeInstance] | None:
    """GET /projects/{id}/runtimes — 项目实例列表 (id 排序; 无 → [])。

    项目不存在 → None (404); store 缺失 → [] (失败安全); 审计: console.viewed
    (view=runtimes)。
    """
    instances = service.list_runtimes(project_id)
    if instances is None:
        return None
    record_console_viewed(logger, view="runtimes", count=len(instances), project_id=project_id)
    return instances


def get_runtime(
    service: Any,
    runtime_id: str,
    *,
    logger: Any = None,
) -> RuntimeInstance | None:
    """GET /runtimes/{id} — 实例详情; 不存在 → None (404)。审计: console.viewed
    (view=runtime_detail)。"""
    instance = service.get_runtime(runtime_id)
    if instance is None:
        return None
    record_console_viewed(
        logger, view="runtime_detail", count=1, project_id=instance.project_id
    )
    return instance


def start_runtime(
    service: Any,
    runtime_id: str,
    *,
    logger: Any = None,
) -> RuntimeInstance | None:
    """POST /runtimes/{id}/start — starting|stopped → running (重启允许)。

    不存在 → None (404); 状态机非法流转 → RuntimeStateError (HTTP 层 409);
    成功 → org.runtime.status_changed 事件 (previous_status) + 审计。
    """
    previous = service.get_runtime(runtime_id)
    instance = service.start_runtime(runtime_id)
    if instance is None:
        return None
    if previous is not None:
        record_runtime_status_changed(logger, instance=instance, previous_status=previous.status)
    record_console_viewed(
        logger, view="runtime_start", count=1, project_id=instance.project_id
    )
    return instance


def stop_runtime(
    service: Any,
    runtime_id: str,
    *,
    logger: Any = None,
) -> RuntimeInstance | None:
    """POST /runtimes/{id}/stop — starting|running → stopped。

    不存在 → None (404); 已 stopped/error → RuntimeStateError (409);
    成功 → org.runtime.status_changed 事件 + 审计。
    """
    previous = service.get_runtime(runtime_id)
    instance = service.stop_runtime(runtime_id)
    if instance is None:
        return None
    if previous is not None:
        record_runtime_status_changed(logger, instance=instance, previous_status=previous.status)
    record_console_viewed(
        logger, view="runtime_stop", count=1, project_id=instance.project_id
    )
    return instance


def capture_runtime_screenshot(
    service: Any,
    runtime_id: str,
    *,
    logger: Any = None,
) -> RuntimeScreenshot | None:
    """POST /runtimes/{id}/screenshot — 截图预留 (只落记录 + artifact 引用)。

    不存在 → None (404); 非 running → RuntimeStateError (409 — 截图只在
    运行态有意义); 成功 → 截图记录落库 + 审计。完整 Feedback Loop (截图 →
    意见 → Agent 修改) 由后续 Sprint 实现 (S10-004 只预留动作 + artifact)。
    """
    screenshot = service.capture_runtime_screenshot(runtime_id)
    if screenshot is None:
        return None
    record_console_viewed(
        logger, view="runtime_screenshot", count=1, project_id=screenshot.project_id
    )
    return screenshot
