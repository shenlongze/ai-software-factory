"""llm.credential_pool — Provider 凭据池（多把 key 轮换 + 耗尽自愈）。

来源: 借鉴 Hermes 的 agent/credential_pool.py（MIT）取其【池语义】，
      丢弃其 provider 私有同步逻辑（claude_code / nous auth.json 等），
      并按本仓库的安全规则改造:

        ★ 池里存的是【环境变量名】，不是 key 本身 —— key 永不落盘。
          （Hermes 存 token；我们只存 "env:VAR" 引用，与实际 key 隔离）

语义（与 Hermes 一致的部分）:
  · 条目状态: ok / exhausted(冷却中) / dead(永久失效)
  · 选择策略: fill_first(默认) / round_robin / least_used
  · 耗尽自愈: exhausted 带 TTL，到期自动恢复为 ok（冷却结束再试）
  · 失败标记: 每次调用失败可 mark_exhausted；连续失败 → dead
  · 持久化: 可选落盘（只落 env 引用与统计，不落 key）

本模块只做"选哪把 key"；怎么用 key 发请求属调用方（infrastructure/llm/providers）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATUS_OK = "ok"
STATUS_EXHAUSTED = "exhausted"
STATUS_DEAD = "dead"
STATUSES: tuple[str, ...] = (STATUS_OK, STATUS_EXHAUSTED, STATUS_DEAD)

STRATEGY_FILL_FIRST = "fill_first"
STRATEGY_ROUND_ROBIN = "round_robin"
STRATEGY_LEAST_USED = "least_used"
STRATEGIES: tuple[str, ...] = (STRATEGY_FILL_FIRST, STRATEGY_ROUND_ROBIN, STRATEGY_LEAST_USED)

#: exhausted 默认冷却时长（秒）—— 到期自动恢复可用（自愈，无需人工 reset）。
EXHAUSTED_TTL_DEFAULT_SECONDS = 60 * 60
#: 连续失败达到该次数 → dead（需人工重置，不再自动重试）。
DEAD_AFTER_FAILURES = 3


@dataclass
class PooledCredential:
    """池中一条凭据 —— 只存 env 引用与统计，不存 key 本身。"""

    env_var: str                       # ★ 环境变量名（如 DEEPSEEK_API_KEY_2）
    label: str = ""                    # 人类可读标签（备注用）
    priority: int = 0                  # 越小越优先（fill_first 用）
    status: str = STATUS_OK
    use_count: int = 0
    failure_count: int = 0
    last_used_at: float = 0.0
    exhausted_until: float = 0.0       # 冷却截止时间戳（0 = 无冷却）

    def is_available(self, now: float | None = None) -> bool:
        """是否可立即使用（含冷却到期自愈判定）。"""
        now = time.time() if now is None else now
        if self.status == STATUS_DEAD:
            return False
        if self.status == STATUS_EXHAUSTED and now < self.exhausted_until:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "env_var": self.env_var, "label": self.label, "priority": self.priority,
            "status": self.status, "use_count": self.use_count,
            "failure_count": self.failure_count, "last_used_at": self.last_used_at,
            "exhausted_until": self.exhausted_until,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PooledCredential":
        return cls(
            env_var=str(payload.get("env_var", "")),
            label=str(payload.get("label", "")),
            priority=int(payload.get("priority", 0) or 0),
            status=str(payload.get("status", STATUS_OK)),
            use_count=int(payload.get("use_count", 0) or 0),
            failure_count=int(payload.get("failure_count", 0) or 0),
            last_used_at=float(payload.get("last_used_at", 0.0) or 0.0),
            exhausted_until=float(payload.get("exhausted_until", 0.0) or 0.0),
        )


class CredentialPool:
    """单 provider 的凭据池。选池不选钥匙 —— key 由调用方从 env_var 解析。"""

    def __init__(self, provider_id: str, *,
                 strategy: str = STRATEGY_FILL_FIRST,
                 entries: list[PooledCredential] | None = None,
                 store_path: Path | None = None) -> None:
        self.provider_id = provider_id
        self.strategy = strategy if strategy in STRATEGIES else STRATEGY_FILL_FIRST
        self._entries: list[PooledCredential] = list(entries or [])
        self._store_path = store_path
        self._rr_cursor = 0

    # ---------------------------------------------------------------- 读写

    @property
    def entries(self) -> tuple[PooledCredential, ...]:
        return tuple(self._entries)

    def has_credentials(self) -> bool:
        return bool(self._entries)

    def has_available(self) -> bool:
        return any(e.is_available() for e in self._entries)

    def add(self, entry: PooledCredential) -> PooledCredential:
        """加入池中（同 env_var 已存在 → 更新，保证幂等）。"""
        for i, e in enumerate(self._entries):
            if e.env_var == entry.env_var:
                self._entries[i] = entry
                self._save()
                return entry
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.priority)
        self._save()
        return entry

    def remove(self, env_var: str) -> PooledCredential | None:
        for i, e in enumerate(self._entries):
            if e.env_var == env_var:
                gone = self._entries.pop(i)
                self._save()
                return gone
        return None

    # ---------------------------------------------------------------- 选择

    def select(self, *, environ: dict[str, str] | None = None) -> PooledCredential | None:
        """按策略选一条可用凭据。

        environ 提供时，只选【该环境里真有值】的条目（缺值不算可用）。
        """
        now = time.time()
        self._recover_cooled(now)
        pool = [e for e in self._entries if e.is_available(now)]
        if environ is not None:
            pool = [e for e in pool if (environ.get(e.env_var) or "").strip()]
        if not pool:
            return None

        chosen: PooledCredential | None
        if self.strategy == STRATEGY_LEAST_USED:
            chosen = min(pool, key=lambda e: (e.use_count, e.priority))
        elif self.strategy == STRATEGY_ROUND_ROBIN:
            chosen = pool[self._rr_cursor % len(pool)]
            self._rr_cursor = (self._rr_cursor + 1) % len(pool)
        else:  # fill_first
            chosen = min(pool, key=lambda e: e.priority)
        chosen.use_count += 1
        chosen.last_used_at = now
        self._save()
        return chosen

    def peek(self) -> PooledCredential | None:
        """看一眼会被选中谁（不改统计、不落盘）。"""
        self._recover_cooled(time.time())
        avail = [e for e in self._entries if e.is_available()]
        if not avail:
            return None
        if self.strategy == STRATEGY_LEAST_USED:
            return min(avail, key=lambda e: (e.use_count, e.priority))
        return min(avail, key=lambda e: e.priority)

    # ---------------------------------------------------------------- 状态

    def mark_exhausted(self, env_var: str, *,
                       ttl_seconds: int = EXHAUSTED_TTL_DEFAULT_SECONDS) -> PooledCredential | None:
        """标记某条耗尽（限流/配额）→ 冷却 ttl 秒后自动恢复（自愈）。"""
        entry = self._find(env_var)
        if entry is None:
            return None
        entry.status = STATUS_EXHAUSTED
        entry.failure_count += 1
        entry.exhausted_until = time.time() + max(0, int(ttl_seconds))
        if entry.failure_count >= DEAD_AFTER_FAILURES:
            entry.status = STATUS_DEAD      # 连续失败 → 永久失效，需人工重置
        self._save()
        return entry

    def reset_statuses(self) -> int:
        """把所有 exhausted/dead 重置为 ok（人工干预；返回重置条数）。"""
        n = 0
        for e in self._entries:
            if e.status != STATUS_OK:
                e.status = STATUS_OK
                e.exhausted_until = 0.0
                e.failure_count = 0
                n += 1
        if n:
            self._save()
        return n

    def status_report(self) -> list[dict[str, Any]]:
        """状态汇总（CLI/Web 展示用 —— key 值不出现，只有 env 名与状态）。"""
        now = time.time()
        out = []
        for e in self._entries:
            remaining = max(0, int(e.exhausted_until - now)) if e.status == STATUS_EXHAUSTED else 0
            out.append({
                "env_var": e.env_var, "label": e.label, "status": e.status,
                "priority": e.priority, "use_count": e.use_count,
                "failure_count": e.failure_count, "cooldown_remaining": remaining,
            })
        return out

    # ---------------------------------------------------------------- 内部

    def _find(self, env_var: str) -> PooledCredential | None:
        return next((e for e in self._entries if e.env_var == env_var), None)

    def _recover_cooled(self, now: float) -> None:
        """冷却到期的 exhausted 自动恢复为 ok（自愈）。"""
        changed = False
        for e in self._entries:
            if e.status == STATUS_EXHAUSTED and now >= e.exhausted_until > 0:
                e.status = STATUS_OK
                e.exhausted_until = 0.0
                e.failure_count = 0
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        if self._store_path is None:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "provider": self.provider_id,
                       "strategy": self.strategy,
                       "entries": [e.to_dict() for e in self._entries]}
            self._store_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 — 持久化失败不影响内存态（失败安全）
            pass

    @classmethod
    def load(cls, provider_id: str, store_path: Path | None = None,
             *, strategy: str = STRATEGY_FILL_FIRST) -> "CredentialPool":
        """从磁盘装载；不存在/损坏 → 空池（失败安全，不抛）。"""
        entries: list[PooledCredential] = []
        eff_strategy = strategy
        if store_path is not None and store_path.exists():
            try:
                data = json.loads(store_path.read_text(encoding="utf-8"))
                entries = [PooledCredential.from_dict(x) for x in data.get("entries", [])]
                eff_strategy = str(data.get("strategy", strategy) or strategy)
            except Exception:  # noqa: BLE001
                entries = []
        return cls(provider_id, strategy=eff_strategy, entries=entries, store_path=store_path)
