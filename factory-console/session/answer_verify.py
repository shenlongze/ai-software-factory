"""factory-console/session/answer_verify.py — 回答验证闭环 (S-2, v1.1.218).

Founder 2026-08-27: "数据真不真靠自觉" — 回答要能复核:
- verify_numbers: 回答中的关键数字 (百分比/数量+单位) 必须在 reference (查询结果/事实卡) 中能找到,
  找不到 → 标记"可能无据" (提示修正, 不阻断)
- no_evidence_no_conclusion: 查询/分析类若无工具证据 → 拒绝空答 (S-2.2, agent 循环用)
失败安全: 解析失败 → 不误报 (返回 ok)。
"""

from __future__ import annotations

import re
from typing import Any

#: 数字模式: 百分比 / 整数(可带千分位) + 可选单位
_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|％|个|条|项|任务|文件|行|轮|次|天|小时|版本|史诗|战役|分|K|万)?")


def extract_numbers(text: str) -> list[str]:
    """抽取文本中的关键数字 (去重, 保序)。"""
    out: list[str] = []
    for m in _NUM_RE.finditer(str(text or "")):
        num = m.group(1)
        unit = (m.group(2) or "").strip()
        tok = f"{num}{unit}"
        if tok not in out:
            out.append(tok)
    return out


def verify_numbers(answer: str, reference: str) -> dict[str, Any]:
    """回答中的关键数字须能在 reference 中找到 (或回答明说未查到/不确定)。

    返回 {ok, unverified: [数字列表], note} — 只标记不阻断 (模型可修正/澄清)。"""
    ans_nums = extract_numbers(answer)
    if not ans_nums:
        return {"ok": True, "unverified": [], "note": "回答无关键数字"}
    ref = str(reference or "")
    # 回答明说"未查询到/不确定/约" → 不算编造
    if any(k in answer for k in ("未查询到", "未找到", "不确定", "无法确认", "暂无")):
        return {"ok": True, "unverified": [], "note": "回答明确标注未查到/不确定"}
    unverified = [n for n in ans_nums if n not in ref]
    return {"ok": not unverified, "unverified": unverified,
            "note": "回答数字在查询结果中无对应" if unverified else "数字与查询结果一致"}


def no_evidence_prompt() -> str:
    """S-2.2: 无证据不结论 — 查询/分析类未调工具直接答时注入的强制提示。"""
    return (
        "这个查询需要实时数据: 请先调用数据工具 (project_status/project_tasks/project_scan/"
        "code_scan/project_structure/search_code/project_docs/git_status/monitor) 获取真实数据"
        "后再回答, 不要凭空答。"
    )


def self_check_prompt() -> str:
    """S-2.3: 回答后自评 — 硬收敛前注入, 强制检查结论证据。"""
    return (
        "【回答自检】在给出最终答案前, 逐句检查: 每个关键结论是否有工具证据支持?"
        "有 → 保留并引用; 没有 → 删除该结论或明确标注'未查到'; 数字必须是工具结果里的。"
    )
