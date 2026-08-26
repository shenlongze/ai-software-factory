"""factory-console/external_executor/monitor_detail.py — M4.2 监控中心详细聚合。

Founder 2026-08-27: 监控太简单, 维度不全 → 补:
- 趋势 (近 N 天执行次数/成功率)
- 多维聚合: 按执行器 / host_agent / 项目 / 回修原因 / 验证方式
- 执行记录流 (最近 N 条, 含 verify/rework/耗时/命令摘要, 可钻取)
- 自身能力 (内部执行记录, 无 executor_id) 与外部能力并轨

数据源: exec/execution_records.json (EXS; 内部旧格式无 executor_id 也兼容)。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .metrics import build_alerts

FAIL_THRESHOLD = 3


def _load_records(data_dir: str | Path) -> list[dict[str, Any]]:
    try:
        d = json.loads((Path(data_dir) / "exec" / "execution_records.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _day(ts: Any) -> str:
    try:
        return str(ts or "")[:10]
    except Exception:
        return ""


def _duration(r: dict) -> int:
    try:
        return int(r.get("duration_ms") or 0)
    except (TypeError, ValueError):
        return 0


def _summary(records: list[dict]) -> dict[str, Any]:
    total = len(records)
    success = sum(1 for r in records if str(r.get("result") or "") == "success")
    # 首次通过只统计"有该字段"的记录 (内部旧记录无 first_pass → 不虚高)
    first_pass_known = [r for r in records if r.get("first_pass") is not None]
    first_pass = sum(1 for r in first_pass_known if r.get("first_pass") is True)
    verified = [r for r in records if (r.get("verify") or {}).get("result") in ("pass", "fail")]
    verify_pass = sum(1 for r in verified if (r.get("verify") or {}).get("result") == "pass")
    durations = sorted(_duration(r) for r in records if r.get("duration_ms"))
    rework = sum(int((r.get("rework") or {}).get("count", 0)) for r in records)
    return {
        "total": total, "success": success, "failed": total - success,
        "success_rate": _rate(success, total),
        "first_pass_rate": _rate(first_pass, len(first_pass_known)),
        "verified": len(verified),
        "verify_pass_rate": _rate(verify_pass, len(verified)),
        "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
        "p90_duration_ms": durations[int(len(durations) * 0.9) - 1] if durations else None,
        "total_rework": rework,
    }


def build_trend(records: list[dict], *, days: int = 14) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date()
    buckets = {str(today - timedelta(days=i)): {"date": str(today - timedelta(days=i)), "count": 0, "success": 0, "failed": 0}
               for i in range(days - 1, -1, -1)}
    for r in records:
        d = _day(r.get("timestamp"))
        if d in buckets:
            buckets[d]["count"] += 1
            if str(r.get("result") or "") == "success":
                buckets[d]["success"] += 1
            else:
                buckets[d]["failed"] += 1
    return [buckets[d] for d in sorted(buckets)]


def _group_stats(groups: dict[str, list[dict]]) -> list[dict[str, Any]]:
    out = []
    for key, rs in groups.items():
        s = _summary(rs)
        out.append({"key": key, **s})
    out.sort(key=lambda x: x["total"], reverse=True)
    return out


def build_monitor_detail(
    data_dir: str | Path,
    adapters: list[Any],
    *,
    days: int = 14,
    recent_limit: int = 30,
) -> dict[str, Any]:
    records = _load_records(data_dir)
    ext = [r for r in records if r.get("executor_id")]
    internal = [r for r in records if not r.get("executor_id")]

    # 按 host_agent (外部) / agent (内部)
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in ext:
        key = f"{r.get('executor_id')}.{r.get('host_agent')}" if r.get("host_agent") else str(r.get("executor_id"))
        by_agent[key].append(r)
    for r in internal:
        by_agent[str(r.get("agent") or "unknown")].append(r)

    # 按项目 (外部 project_dir; 内部无 → 不归入)
    by_project: dict[str, list[dict]] = defaultdict(list)
    for r in ext:
        by_project[str(r.get("project_dir") or "（未指定目录）")].append(r)

    # 回修原因 / 验证方式
    rework_reasons: Counter = Counter()
    verify_methods: Counter = Counter()
    for r in ext:
        for reason in (r.get("rework") or {}).get("reasons", []):
            rework_reasons[str(reason)] += 1
        v = r.get("verify") or {}
        if v.get("result") in ("pass", "fail", "unknown"):
            verify_methods[f"{v.get('method') or 'manual'}·{v.get('result')}"] += 1

    recent = sorted(records, key=lambda r: str(r.get("timestamp") or ""), reverse=True)[:recent_limit]
    recent_out = []
    for r in recent:
        recent_out.append({
            "result_id": r.get("result_id"), "timestamp": r.get("timestamp"),
            "executor_id": r.get("executor_id"), "mode": r.get("mode"),
            "host_agent": r.get("host_agent"), "agent": r.get("agent"),
            "task": str(r.get("task") or "")[:120], "result": r.get("result"),
            "duration_ms": _duration(r), "exit_code": r.get("exit_code"),
            "first_pass": r.get("first_pass"), "verify": r.get("verify"),
            "rework": r.get("rework"), "command": str(r.get("command") or "")[:200],
            "error": str(r.get("error") or "")[:200],
        })

    return {
        "summary": {
            "external": _summary(ext),
            "internal": _summary(internal),
            "combined": _summary(records),
        },
        "trend": build_trend(records, days=days),
        "by_executor": _group_stats({str(r.get("executor_id")): [x for x in ext if x.get("executor_id") == r.get("executor_id")] for r in ext}),
        "by_agent": _group_stats(dict(by_agent)),
        "by_project": _group_stats(dict(by_project)),
        "rework_reasons": [{"reason": k, "count": v} for k, v in rework_reasons.most_common(10)],
        "verify_methods": [{"method": k, "count": v} for k, v in verify_methods.most_common(10)],
        "recent": recent_out,
        "alerts": build_alerts(data_dir, adapters),
    }
