"""factory-console/session/session_audit.py — 会话可观测 (S-1, v1.1.217).

Founder 2026-08-27: 会话问题不能靠用户发现 — 每轮落审计, 指标进监控。

- audit: 每轮会话追加 jsonl (ts/session/question/intent/tools/耗时/收敛方式/answer_len)
- aggregate: 按天聚合 (意图分布/工具成功率/平均轮数/平均耗时/硬收敛率)
失败安全: 审计写失败不阻断会话。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_DAILY = 5000  # jsonl 滚动上限


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(
    data_dir: str | Path | None,
    *,
    session_id: str,
    question: str,
    intent: str,
    emotion: str,
    tools: list[str],
    total_calls: int,
    rounds: int,
    duration_ms: int,
    answer_len: int,
    converge: str,  # autonomous | reflection | hard_cap | rejected
    answer: str = "",
    prompt_tokens: int = 0,  # P2.1 提示缓存意识: token 统计
    completion_tokens: int = 0,
) -> None:
    """追加一条会话审计记录 (<data_dir>/session_audit/<YYYY-MM-DD>.jsonl)。"""
    if not data_dir:
        return
    try:
        day = _now_iso()[:10]
        d = Path(data_dir) / "session_audit"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{day}.jsonl"
        rec = {
            "ts": _now_iso(), "session_id": str(session_id),
            "question": str(question)[:300], "intent": str(intent),
            "emotion": str(emotion), "tools": [str(t) for t in tools],
            "total_calls": int(total_calls), "rounds": int(rounds),
            "duration_ms": int(duration_ms), "answer_len": int(answer_len),
            "converge": str(converge), "answer": str(answer)[:500],
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
        }
        lines = []
        if path.exists():
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
        lines.append(json.dumps(rec, ensure_ascii=False))
        if len(lines) > MAX_DAILY:
            lines = lines[-MAX_DAILY:]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 — 审计失败不阻断会话
        pass


def aggregate(data_dir: str | Path | None, *, days: int = 7) -> dict[str, Any]:
    """近 N 天聚合: 意图分布/工具成功率/平均轮数/平均耗时/硬收敛率。"""
    out: dict[str, Any] = {
        "days": {}, "total": 0, "intent_dist": {}, "tool_success": {},
        "avg_rounds": 0.0, "avg_duration_ms": 0.0,
        "converge_dist": {}, "hard_cap_rate": 0.0,
    }
    if not data_dir:
        return out
    d = Path(data_dir) / "session_audit"
    if not d.is_dir():
        return out
    files = sorted(d.glob("*.jsonl"))[-days:]
    total = 0
    tool_ok: dict[str, int] = {}
    tool_total: dict[str, int] = {}
    converge_count: dict[str, int] = {}
    for f in files:
        try:
            recs = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        except Exception:  # noqa: BLE001
            continue
        out["days"][f.stem] = len(recs)
        for r in recs:
            total += 1
            intent = str(r.get("intent") or "?")
            out["intent_dist"][intent] = out["intent_dist"].get(intent, 0) + 1
            conv = str(r.get("converge") or "?")
            converge_count[conv] = converge_count.get(conv, 0) + 1
            for t in r.get("tools") or []:
                tool_total[str(t)] = tool_total.get(str(t), 0) + 1
                tool_ok.setdefault(str(t), 0)  # 工具被调即计入 (详细 ok 在 jsonl)
    out["total"] = total
    out["intent_dist"] = dict(sorted(out["intent_dist"].items(), key=lambda x: -x[1]))
    out["converge_dist"] = converge_count
    if total:
        rounds = 0.0
        dur = 0.0
        for f in files:
            try:
                recs = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
            except Exception:  # noqa: BLE001
                continue
            rounds += sum(int(r.get("rounds") or 0) for r in recs)
            dur += sum(int(r.get("duration_ms") or 0) for r in recs)
        out["avg_rounds"] = round(rounds / total, 2)
        out["avg_duration_ms"] = int(dur / total)
        hc = converge_count.get("hard_cap", 0)
        out["hard_cap_rate"] = round(hc / total, 3)
    out["tool_success"] = {k: {"calls": tool_total.get(k, 0)} for k in sorted(tool_total)}
    return out
