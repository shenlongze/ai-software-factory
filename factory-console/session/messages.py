"""factory-console/session/messages.py — AgentMessageStore + HandoffStore (S10-056/S10-057)。

Agent 基础消息模型 (设计 §2.6): architect → backend 指令模型 —
{from, to, type, content, timestamp}, 落盘 agent_messages.json (~/.factory/teams/)。
只实现基础 append/query (不做聊天系统 — 边界 §7)。

S10-057 (Team Production Validation, 设计 §P2): Agent Handoff —
handoff(from_agent, to_agent, requirement, decision, constraints) → AgentMessage
type="handoff" {from, to, requirement, decision, constraints, task_id,
timestamp}, 落盘 handoff_messages.json (projects/<slug>/, 调用方指定文件)。

组件:
- AgentMessage — 消息 dataclass (from_/to/type/content/timestamp + to_dict/from_dict)
- AgentMessageStore — send(from_, to, type, content) / messages_for(agent)
  (收件箱: to == agent) / list() / save() / load() (失败安全: 缺失/损坏 → 空)
- HandoffMessage — 交接消息 dataclass (from_/to/requirement/decision/constraints/
  task_id/type/timestamp + to_dict/from_dict)
- HandoffStore — send(from_, to, requirement, decision, constraints?, task_id?)
  / messages_for(agent) / list() / save() / load() (失败安全)
- handoff(from_agent, to_agent, requirement, decision, constraints?, file?) —
  模块级便捷函数: 落盘 handoff_messages.json → 消息 dict

设计: docs/sprint10/S10-056-team-design.md §2.6 / §4;
docs/sprint10/S10-057-team-production-design.md §P2 / §2 数据资产
边界:
- 纯标准库 (json/pathlib/dataclasses), 零模块依赖; 失败安全, 永不抛
- JSON 字段名 "from" (Python 关键字 → dataclass 字段 from_)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 默认消息文件 (~/.factory/teams/agent_messages.json — 设计 §4 资产口径)
DEFAULT_MESSAGES_FILE = Path.home() / ".factory" / "teams" / "agent_messages.json"

#: 默认交接文件 (~/.factory/teams/handoff_messages.json — 设计 §4 资产口径;
#: 项目级交接记录 → projects/<slug>/handoff_messages.json, 由调用方显式指定)
DEFAULT_HANDOFFS_FILE = Path.home() / ".factory" / "teams" / "handoff_messages.json"

#: 交接消息类型 (设计 §P2: AgentMessage type="handoff")
HANDOFF_TYPE = "handoff"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (消息时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentMessage:
    """Agent 消息 (设计 §2.6): from → to 指令/通知, 含时间戳。"""

    from_: str
    to: str
    type: str
    content: str
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """落盘格式: {from, to, type, content, timestamp} (设计 §2.6)。"""
        return {
            "from": self.from_,
            "to": self.to,
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AgentMessage":
        """读回格式 → AgentMessage; 缺字段失败安全缺省。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            from_=str(data.get("from") or ""),
            to=str(data.get("to") or ""),
            type=str(data.get("type") or "message"),
            content=str(data.get("content") or ""),
            timestamp=str(data.get("timestamp") or _now_iso()),
        )


class AgentMessageStore:
    """Agent 消息存储: append (send) + query (messages_for/list) + 落盘。

    基础模型, 不做聊天系统; 失败安全 (缺失/损坏 → 空消息列表, 不抛)。
    """

    DEFAULT_FILE = DEFAULT_MESSAGES_FILE

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else self.DEFAULT_FILE
        self._messages: list[AgentMessage] = []
        self._load()

    # ------------------------------------------------------------ 写入

    def send(
        self, from_: str, to: str, type: str = "message", content: str = ""
    ) -> dict[str, Any]:
        """发送消息: 追加 → 落盘 → 返回消息 dict (设计 §2.6)。"""
        msg = AgentMessage(
            from_=str(from_), to=str(to), type=str(type), content=str(content)
        )
        self._messages.append(msg)
        self._save()
        return msg.to_dict()

    # ------------------------------------------------------------ 查询

    def messages_for(self, agent: str) -> list[dict[str, Any]]:
        """收件箱: 发给该 agent 的全部消息 (to == agent, 发送顺序)。"""
        target = str(agent)
        return [m.to_dict() for m in self._messages if m.to == target]

    def list(self) -> list[dict[str, Any]]:
        """全部消息 (发送顺序)。"""
        return [m.to_dict() for m in self._messages]

    # ------------------------------------------------------------ 落盘

    def _load(self) -> None:
        data: Any = None
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空消息列表
            data = None
        if isinstance(data, list):
            self._messages = [
                AgentMessage.from_dict(m) for m in data if isinstance(m, dict)
            ]
        else:
            self._messages = []

    def load(self, file: Optional[Path] = None) -> "AgentMessageStore":
        """(重)加载消息 (缺省当前文件); 返回 self 支持链式。"""
        if file is not None:
            self._file = Path(file)
        self._load()
        return self

    def _save(self) -> Path:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                [m.to_dict() for m in self._messages], ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        return self._file

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 agent_messages.json (可指定文件); 返回文件路径。"""
        if file is not None:
            self._file = Path(file)
        return self._save()


@dataclass
class HandoffMessage:
    """Agent 交接消息 (设计 §P2): 前序 Agent → 后继 Agent。

    requirement/decision/constraints 为交接内容 (需求/决策/约束);
    task_id 关联后继任务 (可选); type 恒为 "handoff"。
    """

    from_: str
    to: str
    requirement: str
    decision: str
    constraints: str = ""
    task_id: str = ""
    type: str = HANDOFF_TYPE
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """落盘格式: {from, to, requirement, decision, constraints, task_id, type, timestamp}。"""
        return {
            "from": self.from_,
            "to": self.to,
            "requirement": self.requirement,
            "decision": self.decision,
            "constraints": self.constraints,
            "task_id": self.task_id,
            "type": self.type,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "HandoffMessage":
        """读回格式 → HandoffMessage; 缺字段失败安全缺省。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            from_=str(data.get("from") or ""),
            to=str(data.get("to") or ""),
            requirement=str(data.get("requirement") or ""),
            decision=str(data.get("decision") or ""),
            constraints=str(data.get("constraints") or ""),
            task_id=str(data.get("task_id") or ""),
            type=str(data.get("type") or HANDOFF_TYPE),
            timestamp=str(data.get("timestamp") or _now_iso()),
        )


class HandoffStore:
    """Agent 交接存储 (设计 §P2): 前序完成 → 后继交接, 落盘 handoff_messages.json。

    与 AgentMessageStore 同构 (append/query/落盘), 失败安全 (缺失/损坏 → 空)。
    项目级文件: projects/<slug>/handoff_messages.json (调用方显式指定)。
    """

    DEFAULT_FILE = DEFAULT_HANDOFFS_FILE

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else self.DEFAULT_FILE
        self._handoffs: list[HandoffMessage] = []
        self._load()

    # ------------------------------------------------------------ 写入

    def send(
        self,
        from_: str,
        to: str,
        requirement: str,
        decision: str,
        constraints: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        """发送交接: 追加 → 落盘 → 返回消息 dict (设计 §P2)。"""
        msg = HandoffMessage(
            from_=str(from_),
            to=str(to),
            requirement=str(requirement),
            decision=str(decision),
            constraints=str(constraints),
            task_id=str(task_id),
        )
        self._handoffs.append(msg)
        self._save()
        return msg.to_dict()

    # ------------------------------------------------------------ 查询

    def messages_for(self, agent: str) -> list[dict[str, Any]]:
        """收件箱: 发给该 agent 的交接 (to == agent, 发送顺序)。"""
        target = str(agent)
        return [m.to_dict() for m in self._handoffs if m.to == target]

    def list(self) -> list[dict[str, Any]]:
        """全部交接 (发送顺序)。"""
        return [m.to_dict() for m in self._handoffs]

    # ------------------------------------------------------------ 落盘

    def _load(self) -> None:
        data: Any = None
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空交接
            data = None
        if isinstance(data, list):
            self._handoffs = [
                HandoffMessage.from_dict(m) for m in data if isinstance(m, dict)
            ]
        else:
            self._handoffs = []

    def load(self, file: Optional[Path] = None) -> "HandoffStore":
        """(重)加载 handoff_messages.json (缺省当前文件); 返回 self 链式。"""
        if file is not None:
            self._file = Path(file)
        self._load()
        return self

    def _save(self) -> Path:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(
                [m.to_dict() for m in self._handoffs], ensure_ascii=False, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        return self._file

    def save(self, file: Optional[Path] = None) -> Path:
        """落盘 handoff_messages.json (可指定文件); 返回文件路径。"""
        if file is not None:
            self._file = Path(file)
        return self._save()


def handoff(
    from_agent: str,
    to_agent: str,
    requirement: str,
    decision: str,
    constraints: str = "",
    file: Optional[Path] = None,
    task_id: str = "",
) -> dict[str, Any]:
    """Agent 交接便捷函数 (设计 §P2): 落盘 handoff_messages.json → 消息 dict。

    等价 HandoffStore(file).send(...) — 缺省文件 ~/.factory/teams/
    handoff_messages.json; 项目级 → file=projects/<slug>/handoff_messages.json。
    """
    store = HandoffStore(file=file)
    return store.send(from_agent, to_agent, requirement, decision, constraints, task_id=task_id)
