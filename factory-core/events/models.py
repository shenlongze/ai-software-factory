"""events/models.py — Event 领域模型 (Pydantic v2, 不可变)。

设计依据:
- phase1-plan.md §3: EventType 六类最小事件 + Event 模型
- event-model.md §2: 四个语义列 (stage/action/result/evidence) + project_id + payload

不可变 (frozen=True): append-only 语义的模型层保证, seq 回填经 model_copy(update=...) 返回新实例。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 统一 UTC 存储格式: 固定 26 字符, 字符串排序 == 时间排序 (SQLite 过滤/排序无歧义)
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def format_timestamp(dt: datetime) -> str:
    """datetime → 统一存储格式 (UTC, 固定小数秒)。"""
    return dt.astimezone(timezone.utc).strftime(TS_FORMAT)


def parse_timestamp(s: str) -> datetime:
    """统一存储格式 → 带 UTC 时区的 datetime。"""
    return datetime.strptime(s, TS_FORMAT).replace(tzinfo=timezone.utc)


class EventType(str, Enum):
    """六类最小事件 (phase1-plan §3.1)。

    扩展策略: 后续按 event-model.md 六类字典 (task.*/agent.*/validation.*/workflow.*/system.*/human.*)
    扩类时"加枚举成员即可", 不改表结构 (type 列存字符串)。
    """

    TASK_START = "task.start"      # 任务开始: 任务定义、目标、开始时间
    TASK_END = "task.end"          # 任务结束: 结果 (done/failed)、耗时、产物指针
    TASK_FAIL = "task.fail"        # 任务失败: 失败阶段、错误摘要、证据指针
    TOOL_CALL = "tool.call"        # 工具调用: 工具名、参数摘要、结果摘要、耗时
    CHECKPOINT = "checkpoint"      # 停靠点落盘: 停靠点描述、落盘产物清单 (续跑生命线)
    SESSION_CLOSE = "session.close"  # 会话结束: 事件数、任务数、成败统计

    # --- Phase 2: Factory Control CLI 事件 (增量扩展, ADR-0002) ---
    # 依 ADR-0001 决策 1 的扩展路径: 加枚举成员即可, type 列存字符串, 不改表结构。
    # 命名遵循 event-model.md §3 六类字典 (task.* / system.* / validation.*)。
    SYSTEM_INIT = "system.init"                # 工厂初始化
    SYSTEM_LOGS_VIEWED = "system.logs_viewed"  # 事件日志被查询
    SYSTEM_STATUS_VIEWED = "system.status_viewed"  # 工厂状态总览被查看
    TASK_CREATED = "task.created"              # 任务定义
    TASK_VIEWED = "task.viewed"                # 任务被查看 (列表/详情)
    TASK_UPDATED = "task.updated"              # 任务状态更新
    VALIDATION_STARTED = "validation.started"  # 独立验证开始
    VALIDATION_COMPLETED = "validation.completed"  # 独立验证结束 (result=PASS/FAIL)


class Event(BaseModel):
    """一条事件。append-only: 写入后永不修改、永不删除。"""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: uuid4().hex)  # 全局唯一
    seq: int = 0                      # 单调递增序号, 由存储层分配 (回放锚点)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType                   # 事件类型 (六类)
    source: str                       # 发布模块, 如 "cli" / "orchestrator" / "agent"
    project_id: str | None = None     # 可选: 项目维度
    task_id: str | None = None        # 可选: 任务维度
    agent_id: str | None = None       # 可选: Agent 维度
    stage: str | None = None          # 事件发生时对象的状态/阶段 (event-model §2.2)
    action: str | None = None         # 动作简述 (自然语言, 检索友好)
    result: str | None = None         # 判定结果, 可机读 (OK/PASS/FAIL/ERROR/done/failed/...)
    evidence: str | None = None       # 证据引用 (ref:// 或文件路径)
    payload: dict[str, Any] = Field(default_factory=dict)  # 类型相关扩展载荷 (JSON 友好)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> EventType:
        return EventType(v) if isinstance(v, str) else v

    @field_validator("payload")
    @classmethod
    def _payload_json_safe(cls, v: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(v)  # 序列化失败则抛错, 拒绝入库
        except TypeError as exc:  # Pydantic v2 只把 ValueError/AssertionError 转 ValidationError
            raise ValueError(f"payload must be JSON-serializable: {exc}") from exc
        return v

    @classmethod
    def create(
        cls,
        type_: EventType | str,
        *,
        source: str,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        stage: str | None = None,
        action: str | None = None,
        result: str | None = None,
        evidence: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        """工厂方法: 生成 uuid event_id + UTC 时间戳。

        type_ 传字符串时由模型 _coerce_type validator 处理 (非法值 → ValidationError)。
        """
        return cls(
            event_id=uuid4().hex,
            timestamp=datetime.now(timezone.utc),
            type=cast(EventType, type_),
            source=source,
            project_id=project_id,
            task_id=task_id,
            agent_id=agent_id,
            stage=stage,
            action=action,
            result=result,
            evidence=evidence,
            payload=payload if payload is not None else {},
        )

    def to_row(self) -> tuple:
        """转 SQLite 行 (含语义列, payload 为 JSON 字符串)。"""
        return (
            self.event_id,
            format_timestamp(self.timestamp),
            self.type.value,
            self.source,
            self.project_id,
            self.task_id,
            self.agent_id,
            self.stage,
            self.action,
            self.result,
            self.evidence,
            json.dumps(self.payload, ensure_ascii=False),
        )

    @classmethod
    def from_row(cls, row: Any) -> Event:
        """从 SQLite 行重建 Event (seq 由存储层回填)。"""
        return cls(
            event_id=row["event_id"],
            seq=row["seq"],
            timestamp=parse_timestamp(row["timestamp"]),
            type=row["type"],
            source=row["source"],
            project_id=row["project_id"],
            task_id=row["task_id"],
            agent_id=row["agent_id"],
            stage=row["stage"],
            action=row["action"],
            result=row["result"],
            evidence=row["evidence"],
            payload=json.loads(row["payload"]),
        )
