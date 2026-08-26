"""factory-console/external_executor/metrics.py — M4 外部执行器监控指标聚合。

设计依据: 设计文档 §8 (监控指标模型)。
从 exec/execution_records.json 的 EXS 记录聚合 (executor_id 字段) —
效率/效果/完成率/回修/验证; 告警: 连续失败≥3 / 验证 fail(回修>0) /
probe 不可用 / 无记录(unknown 诚实)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FAIL_THRESHOLD = 3


def _load_records(data_dir: str | Path) -> list[dict[str, Any]]:
    try:
        d = json.loads((Path(data_dir) / "exec" / "execution_records.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 空
        return []


def aggregate_executor_metrics(data_dir: str | Path) -> list[dict[str, Any]]:
    """按 executor_id 聚合 → 每执行器一行指标 (按总次数倒序)。"""
    records = [r for r in _load_records(data_dir) if r.get("executor_id")]
    by: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by.setdefault(str(r["executor_id"]), []).append(r)
    out: list[dict[str, Any]] = []
    for eid, rs in by.items():
        total = len(rs)
        success = sum(1 for r in rs if str(r.get("result") or "") == "success")
        first_pass = sum(1 for r in rs if r.get("first_pass") is not False)
        verified = [r for r in rs if (r.get("verify") or {}).get("result") in ("pass", "fail")]
        verify_pass = sum(1 for r in verified if (r.get("verify") or {}).get("result") == "pass")
        rework = sum(int((r.get("rework") or {}).get("count", 0)) for r in rs)
        durations = [int(r.get("duration_ms") or 0) for r in rs if r.get("duration_ms")]
        last = max(rs, key=lambda r: str(r.get("timestamp") or ""))
        out.append({
            "executor_id": eid,
            "total": total,
            "success": success,
            "failed": total - success,
            "success_rate": round(success / total, 3) if total else 0.0,
            "first_pass_rate": round(first_pass / total, 3) if total else 0.0,
            "verify_pass_rate": round(verify_pass / len(verified), 3) if verified else None,
            "verified": len(verified),
            "avg_duration_ms": int(sum(durations) / len(durations)) if durations else None,
            "rework_total": rework,
            "last_run_at": last.get("timestamp"),
            "last_result": last.get("result"),
            "last_mode": last.get("mode"),
            "last_host_agent": last.get("host_agent"),
            "last_result_id": last.get("result_id"),
        })
    out.sort(key=lambda m: m["total"], reverse=True)
    return out


def build_alerts(data_dir: str | Path, adapters: list[Any]) -> list[dict[str, Any]]:
    """告警: 连续失败≥3 / 验证 fail (回修>0) / probe 不可用 / 无记录 (unknown)。"""
    alerts: list[dict[str, Any]] = []
    records = [r for r in _load_records(data_dir) if r.get("executor_id")]
    from . import executor as _ee_exec

    # 按执行器分组检查连续失败
    by: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by.setdefault(str(r["executor_id"]), []).append(r)
    for eid, rs in by.items():
        # 从新到旧连续失败
        consec = 0
        for r in sorted(rs, key=lambda x: str(x.get("timestamp") or ""), reverse=True):
            if str(r.get("result") or "") == "failed":
                consec += 1
            else:
                break
        if consec >= FAIL_THRESHOLD:
            alerts.append({"severity": "high", "executor_id": eid,
                           "type": "consecutive_failures", "detail": f"连续失败 {consec} 次"})
        rework = sum(int((r.get("rework") or {}).get("count", 0)) for r in rs)
        if rework > 0:
            alerts.append({"severity": "medium", "executor_id": eid,
                           "type": "verify_rework", "detail": f"回修 {rework} 次 (验证未过)"})
    # probe 不可用
    for a in adapters:
        path = _ee_exec.discover_binary(a)
        if path is None:
            alerts.append({"severity": "medium", "executor_id": a.id,
                           "type": "not_found", "detail": "未发现二进制 (可注册不可委派)"})
            continue
        pr = _ee_exec.probe(a, path)
        if not pr["ok"]:
            alerts.append({"severity": "medium", "executor_id": a.id,
                           "type": "probe_failed", "detail": f"probe 失败: {pr.get('error')}"})
    # 已导入但有执行器从未跑过 → unknown 诚实
    for a in adapters:
        if a.id not in by and _ee_exec.discover_binary(a) is not None:
            alerts.append({"severity": "info", "executor_id": a.id,
                           "type": "no_records", "detail": "已发现但暂无委派记录"})
    return alerts


def build_monitor(data_dir: str | Path, adapters: list[Any]) -> dict[str, Any]:
    """监控聚合: {executors: [指标], alerts: [...]}。"""
    return {
        "executors": aggregate_executor_metrics(data_dir),
        "alerts": build_alerts(data_dir, adapters),
    }
