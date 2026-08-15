"""factory-console/session/messages.py — AgentMessageStore (S10-056 批次 A)。

Agent 基础消息模型 (设计 §2.6): architect → backend 指令模型 —
{from, to, type, content, timestamp}, 落盘 agent_messages.json (~/.factory/teams/)。
只实现基础 append/query (不做聊天系统 — 边界 §7)。

组件:
- AgentMessage — 消息 dataclass (from_/to/type/content/timestamp + to_dict/from_dict)
- AgentMessageStore — send(from_, to, type, content) / messages_for(agent)
  (收件箱: to == agent) / list() / save() / load() (失败安全: 缺失/损坏 → 空)

设计: docs/sprint10/S10-056-team-design.md §2.6 / §4
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
