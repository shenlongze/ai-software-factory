"""identity — 主体契约：人 / Agent / 服务。零依赖。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SubjectKind(str, Enum):
    """主体种类。这是「agent」在平台里唯一出现的位置。"""

    HUMAN = "human"
    AGENT = "agent"
    SERVICE = "service"


SUBJECT_STATES: tuple[str, ...] = ("active", "suspended", "retired")


@dataclass(frozen=True)
class Identity:
    """一个主体（人 / Agent / 服务）。

    Identity 只描述「是谁」，不描述「能做什么」（那是 Role/Capability）。
    """

    id: str
    kind: SubjectKind
    name: str
    external_ref: str = ""
    status: str = "active"
