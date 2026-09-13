"""factory-console/os_core_usage.py — OS Core: Provider Usage / Metrics / Cost (MU-CORE-14).

Usage 是 Execution 的**附属运行事实** (不是 Execution Truth, 不拥有任务状态)。

三分严格分离:
    Metrics: duration_ms / status / exit_code / termination_reason / retry_count
    Usage  : input_tokens / output_tokens / total_tokens (Provider 原生才有; 否则 null)
    Cost   : input_cost / output_cost / total_cost / currency / pricing_source / pricing_version
             (仅当有明确 pricing 契约时计算; 否则 null — 不猜测)

SSOT: <root>/usage/usages.json (UX-*; 每 execution_id 幂等一条)。
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: str | Path) -> Path:
    return Path(root) / "usage" / "usages.json"


def _load(root: str | Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("usages") if isinstance(data, dict) else None
    return items if isinstance(items, dict) else {}


def _save(root: str | Path, data: dict[str, dict[str, Any]]) -> None:
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"usages": data}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def record_usage(root: str | Path, *, execution_id: str, provider: str = "",
                 plugin_id: str = "", node_run_id: str = "", model: str = "",
                 duration_ms: int | None = None, status: str = "",
                 termination_reason: str = "", exit_code: int | None = None,
                 usage: dict[str, Any] | None = None,
                 pricing: dict[str, Any] | None = None) -> dict[str, Any]:
    """记录一次 Provider Usage (按 execution_id **幂等**)。

    usage: {"input_tokens","output_tokens","total_tokens"} 仅当 Provider 原生提供;
    pricing: {"input_per_1k","output_per_1k","currency","source","version"} 提供时才计算 cost。
    """
    from .os_core_execution import get_execution

    if get_execution(root, execution_id) is None:
        raise ValueError(f"Execution 不存在: {execution_id}")
    data = _load(root)
    existing = next((u for u in data.values() if u["execution_id"] == str(execution_id)), None)
    if existing is not None:
        return {**existing, "idempotent": True}

    use = usage or {}
    in_tok = use.get("input_tokens")
    out_tok = use.get("output_tokens")
    total_tok = use.get("total_tokens")
    if total_tok is None and (in_tok is not None or out_tok is not None):
        total_tok = int(in_tok or 0) + int(out_tok or 0)
    usage_available = any(v is not None for v in (in_tok, out_tok, total_tok))

    in_cost = out_cost = tot_cost = None
    currency = pricing_source = pricing_version = ""
    if pricing and usage_available:
        currency = str(pricing.get("currency") or "USD")
        pricing_source = str(pricing.get("source") or "")
        pricing_version = str(pricing.get("version") or "")
        if pricing.get("input_per_1k") is not None and in_tok is not None:
            in_cost = round(float(in_tok) / 1000.0 * float(pricing["input_per_1k"]), 6)
        if pricing.get("output_per_1k") is not None and out_tok is not None:
            out_cost = round(float(out_tok) / 1000.0 * float(pricing["output_per_1k"]), 6)
        if in_cost is not None or out_cost is not None:
            tot_cost = round((in_cost or 0.0) + (out_cost or 0.0), 6)
        else:
            currency = pricing_source = pricing_version = ""   # 无有效定价 → cost 全 null
    rec = {"usage_id": f"UX-{uuid.uuid4().hex[:10]}", "execution_id": str(execution_id),
           "node_run_id": str(node_run_id or ""), "plugin_id": str(plugin_id or ""),
           "provider": str(provider or ""), "model": str(model or ""),
           "duration_ms": duration_ms, "status": str(status or ""),
           "termination_reason": str(termination_reason or ""), "exit_code": exit_code,
           "usage_available": usage_available,
           "input_tokens": in_tok, "output_tokens": out_tok, "total_tokens": total_tok,
           "input_cost": in_cost, "output_cost": out_cost, "total_cost": tot_cost,
           "currency": currency, "pricing_source": pricing_source,
           "pricing_version": pricing_version,
           "created_at": _now_iso()}
    data[rec["usage_id"]] = rec
    _save(root, data)
    return {**rec, "idempotent": False}


def get_usage(root: str | Path, usage_id: str) -> dict[str, Any] | None:
    return _load(root).get(str(usage_id))


def usage_for_execution(root: str | Path, execution_id: str) -> dict[str, Any] | None:
    return next((u for u in _load(root).values() if u["execution_id"] == str(execution_id)), None)


def list_usages(root: str | Path, *, provider: str = "") -> list[dict[str, Any]]:
    recs = list(_load(root).values())
    if provider:
        recs = [u for u in recs if u["provider"] == str(provider)]
    return sorted(recs, key=lambda u: (u.get("created_at", ""), u["usage_id"]))


__all__ = ["get_usage", "list_usages", "record_usage", "usage_for_execution"]
