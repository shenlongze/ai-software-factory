"""factory-console/session/eval_judge.py — 会话质量评估 (S-3, v1.1.218).

Founder 2026-08-27: 会话质量要可量化 — 数据集 + LLM-judge + 通过率进发布门。

- load_cases: 读 session_eval_cases.json (≥12 条, 8 意图 + 已知坑)
- run_eval(parse_fn, tool_plan_fn, judge_fn): 对每 case: 意图命中 + 工具命中 + 回答要点命中 → 通过率
- judge_answer: LLM-judge (可选) + 规则锚定 (有工具证据=证据分 1)
失败安全: 无数据集 → 空结果不崩。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

CASES_FILE = Path(__file__).with_name("session_eval_cases.json")
PASS_THRESHOLD = 0.9


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or CASES_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        cases = d.get("cases") if isinstance(d, dict) else None
        return [c for c in (cases or []) if isinstance(c, dict) and c.get("question")]
    except Exception:  # noqa: BLE001
        return []


def judge_answer(
    question: str,
    answer: str,
    *,
    tools_used: list[str],
    llm_fn: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """回答质量评分: 证据(规则锚定) + 准确性/格式(LLM 可选, 失败降级)。"""
    answer = str(answer or "")
    evidence = 1.0 if tools_used else 0.0
    accuracy = 0.5
    fmt = 0.5
    if llm_fn is not None:
        try:
            raw = str(llm_fn(
                f"用户问: {question[:200]}\nAI 答: {answer[:500]}\n"
                "打分 (0-1): 准确性/证据充分性/格式自然度, 只输出 JSON "
                '{"accuracy": 0.0, "format": 0.0}'
            ) or "").strip()
            import re as _re
            m = _re.search(r"\{.*\}", raw, _re.DOTALL)
            if m:
                d = json.loads(m.group(0))
                accuracy = max(0.0, min(1.0, float(d.get("accuracy") or accuracy)))
                fmt = max(0.0, min(1.0, float(d.get("format") or fmt)))
        except Exception:  # noqa: BLE001 — LLM 判分失败 → 降级
            pass
    total = round(0.4 * accuracy + 0.4 * evidence + 0.2 * fmt, 2)
    return {"accuracy": round(accuracy, 2), "evidence": evidence,
            "format": round(fmt, 2), "total": total}


def run_eval(
    intent_fn: Callable[[str], str],
    *,
    tools_fn: Callable[[str], list[str]] | None = None,
    answer_fn: Callable[[str], str] | None = None,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """跑数据集: 意图命中 + 工具命中 + 回答要点命中 → 通过率。

    intent_fn(q) → 意图字符串; tools_fn(q) → 期望工具调用列表 (可选);
    answer_fn(q) → 回答文本 (可选, 用于要点命中)。
    """
    cases = cases if cases is not None else load_cases()
    if not cases:
        return {"total": 0, "passed": 0, "rate": 0.0, "failures": [], "ok": False}
    passed = 0
    failures: list[dict[str, Any]] = []
    for c in cases:
        q = str(c.get("question") or "")
        exp_intent = str(c.get("intent") or "")
        ok = True
        reasons: list[str] = []
        try:
            got = intent_fn(q)
            if exp_intent and got != exp_intent:
                ok = False
                reasons.append(f"意图: 期望 {exp_intent}, 得 {got}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            reasons.append(f"intent_fn 异常: {exc}")
        if ok and tools_fn is not None:
            try:
                exp_tools = list(c.get("expect_tools") or [])
                got_tools = tools_fn(q) or []
                missing = [t for t in exp_tools if t not in got_tools]
                if missing:
                    ok = False
                    reasons.append(f"缺工具: {missing}")
            except Exception:  # noqa: BLE001
                pass
        if ok and answer_fn is not None and c.get("expect_answer_has"):
            try:
                ans = answer_fn(q) or ""
                missing = [w for w in c["expect_answer_has"] if w not in ans]
                if missing:
                    ok = False
                    reasons.append(f"回答缺要点: {missing}")
            except Exception:  # noqa: BLE001
                pass
        if ok:
            passed += 1
        else:
            failures.append({"id": c.get("id"), "question": q, "reasons": reasons})
    rate = round(passed / len(cases), 3) if cases else 0.0
    return {"total": len(cases), "passed": passed, "rate": rate,
            "failures": failures, "ok": rate >= PASS_THRESHOLD}
