"""learning — 经验。零依赖。

经验不是流程步骤，它是**调度的一次输入**（影响排序与匹配偏好）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExperienceStatus(str, Enum):
    CANDIDATE = "candidate"
    PROMOTED = "promoted"
    RETIRED = "retired"


@dataclass(frozen=True)
class Experience:
    """一条经验 —— 从事件里提取的模式与它对调度的影响。"""

    id: str
    scope: str = ""
    pattern: str = ""
    effect: str = ""
    from_event_refs: tuple[str, ...] = ()
    confidence: float = 0.0
    status: ExperienceStatus = ExperienceStatus.CANDIDATE
