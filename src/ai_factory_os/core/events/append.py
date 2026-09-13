"""events.append — 链式事实的封存与校验。

纯函数，零 IO：持久化由 infrastructure 负责，内核只管链规则。
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Sequence

from ai_factory_os.contracts.events import Event

GENESIS = "0" * 64
_SEP = "\x1f"


def _digest(prev_hash: str, e: Event) -> str:
    """一条事件的内容摘要 —— 绑定前序哈希，故改一条即断全链。"""
    payload = _SEP.join(f"{k}={v}" for k, v in e.payload)
    body = _SEP.join((prev_hash, e.id, e.type, e.at, e.actor_id, e.subject_ref, payload))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def seal(prev: Event | None, draft: Event) -> Event:
    """封存：补上 prev_hash 与 hash。入参不改动。"""
    prev_hash = prev.hash if prev is not None else GENESIS
    return replace(replace(draft, prev_hash=prev_hash), hash=_digest(prev_hash, draft))


def verify_chain(events: Sequence[Event]) -> bool:
    """校验整条链：prev_hash 连续 + 每条自洽。"""
    prev_hash = GENESIS
    for e in events:
        if e.prev_hash != prev_hash or e.hash != _digest(e.prev_hash, e):
            return False
        prev_hash = e.hash
    return True
