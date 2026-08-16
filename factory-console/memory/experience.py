"""factory-console/memory/experience.py — ExperienceRecord 模型 (S10-067 G1)。

统一经验模型: id/type/project/task/agent/role/context/problem/action/result/
success/confidence/source/created_at + 6 类型 (SUCCESS_PATTERN/FAILURE_PATTERN/
DEBUG_EXPERIENCE/PLANNING_EXPERIENCE/AGENT_EXPERIENCE/USER_FEEDBACK)。

设计: docs/sprint10/S10-067-memory-learning-design.md §2
边界:
- 纯标准库 (dataclasses/uuid/datetime/pathlib), 零模块依赖
- to_dict/from_dict 双向 roundtrip; from_dict 失败安全 (非法输入 → ValueError,
  字段缺省兜底) — 经验 = 结构化记忆单元, 不是日志行
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

#: 经验类型注册表 (S10-067 G1 — 6 类型)
SUCCESS_PATTERN = "SUCCESS_PATTERN"        # 成功方案 (execution_records 成功)
FAILURE_PATTERN = "FAILURE_PATTERN"        # 失败模式 (execution_records 失败)
DEBUG_EXPERIENCE = "DEBUG_EXPERIENCE"      # 修复/调试经验 (repair_task)
PLANNING_EXPERIENCE = "PLANNING_EXPERIENCE"  # 规划经验 (replanning/gap)
AGENT_EXPERIENCE = "AGENT_EXPERIENCE"      # Agent 能力画像 (agent metrics)
USER_FEEDBACK = "USER_FEEDBACK"            # 用户反馈 (预留)

#: 全部合法类型 (校验/过滤口径)
TYPES: tuple[str, ...] = (
    SUCCESS_PATTERN,
    FAILURE_PATTERN,
    DEBUG_EXPERIENCE,
    PLANNING_EXPERIENCE,
    AGENT_EXPERIENCE,
    USER_FEEDBACK,
)


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (记录创建时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: Any, default: float = 0.5) -> float:
    """数字 → float (失败安全: 非法 → default; 夹取 0-1)。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN
        return default
    return max(0.0, min(1.0, num))


@dataclass
class ExperienceRecord:
    """结构化经验单元 (S10-067 G1 — Memory ≠ 日志 的最小单位)。

    id:          全局唯一 (缺省 uuid; 提取器用内容哈希 → 幂等去重)
    type:        6 类型之一 (TYPES)
    project:     项目 slug ("" = 全局经验)
    task:        任务名/任务 id
    agent:       Agent id ("" = 不绑定 Agent)
    role:        Agent 角色 (学习画像用)
    context:     上下文 (任务/intent/环境描述 — 检索关键词面)
    problem:     问题描述 (失败原因/缺口/痛点)
    action:      采取的行动 (方案/修复动作/推荐动作)
    result:      结果 (成功/失败/状态/输出摘要)
    success:     是否成功 (模式统计口径)
    confidence:  置信度 0-1 (来源可信度/信号强度)
    source:      数据源 (execution_records/repair_task/replanning_decisions/
                 gap_analysis/...)
    created_at:  创建时间 ISO (UTC)
    """

    id: str = field(default_factory=lambda: f"exp-{uuid.uuid4().hex[:12]}")
    type: str = SUCCESS_PATTERN
    project: str = ""
    task: str = ""
    agent: str = ""
    role: str = ""
    context: str = ""
    problem: str = ""
    action: str = ""
    result: str = ""
    success: bool = True
    confidence: float = 0.5
    source: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """序列化 (JSON 落盘/API 响应口径)。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperienceRecord":
        """反序列化 (失败安全: 非 dict → ValueError; 字段缺省兜底)。

        type 不在 TYPES → ValueError (校验铁律 — 经验类型必须合法);
        confidence/success 类型非法 → 兜底 (0.5 / True), 不抛。
        """
        if not isinstance(data, dict):
            raise ValueError(
                f"ExperienceRecord.from_dict 需要 dict, 收到 {type(data).__name__}"
            )
        record_type = str(data.get("type") or SUCCESS_PATTERN)
        if record_type not in TYPES:
            raise ValueError(f"未知经验类型: {record_type!r} (合法: {', '.join(TYPES)})")
        success_raw = data.get("success", True)
        return cls(
            id=str(data.get("id") or f"exp-{uuid.uuid4().hex[:12]}"),
            type=record_type,
            project=str(data.get("project") or ""),
            task=str(data.get("task") or ""),
            agent=str(data.get("agent") or ""),
            role=str(data.get("role") or ""),
            context=str(data.get("context") or ""),
            problem=str(data.get("problem") or ""),
            action=str(data.get("action") or ""),
            result=str(data.get("result") or ""),
            success=bool(success_raw),
            confidence=_coerce_float(data.get("confidence"), 0.5),
            source=str(data.get("source") or ""),
            created_at=str(data.get("created_at") or _now_iso()),
        )


def make_record_id(source: str, project: str, task: str, problem: str,
                   action: str, result: str) -> str:
    """内容哈希经验 id (提取器用 — 幂等: 同源同内容 → 同 id → 去重)。"""
    payload = "|".join([source, project, task, problem, action, result])
    return f"exp-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:12]}"


def ensure_type(record_type: Any) -> str:
    """类型校验 (非法 → ValueError)。API/Store 写入门。"""
    value = str(record_type or "")
    if value not in TYPES:
        raise ValueError(f"未知经验类型: {value!r} (合法: {', '.join(TYPES)})")
    return value
