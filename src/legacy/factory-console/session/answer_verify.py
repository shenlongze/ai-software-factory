"""factory-console/session/answer_verify.py — 回答验证闭环 (S-2, v1.1.218).

Founder 2026-08-27: "数据真不真靠自觉" — 回答要能复核:
- verify_numbers: 回答中的关键数字 (百分比/数量+单位) 必须在 reference (查询结果/事实卡) 中能找到,
  找不到 → 标记"可能无据" (提示修正, 不阻断)
- verify_details (W8 强化, v1.1.261): 数字 + 色值(#xxx)/版本/类名/文件路径 细节须能在 reference 中找到,
  找不到 → 强制修正或标注"未查到具体值" (治"方向对、细节编")
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


#: 细节模式 (W8 强化 — 治"结论方向对、具体值编造")
_DETAIL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"#[0-9a-fA-F]{3,8}\b"), "色值"),                       # #f5f7fa
    (re.compile(r"\bv?\d+\.\d+\.\d+\b"), "版本"),                 # v1.1.260
    (re.compile(r"\.(?:af|app|shell|workspace|console)-[\w-]+"), "类名"),  # .af-card-name
    (re.compile(r"[\w./-]*/(?:[\w-]+\.)+[a-z]{1,6}\b"), "路径"),      # factory-console/web/.../af.css
    (re.compile(r"\b[\w-]+\.(?:py|tsx?|jsx?|css|json|md|dart)\b"), "文件"),  # af.css / actions.py
]


def extract_details(text: str) -> list[tuple[str, str]]:
    """提取回答里的可验证细节 (色值/版本/类名/路径/文件) → [(token, 类型)] 去重。"""
    out: list[tuple[str, str]] = []
    for pat, kind in _DETAIL_PATTERNS:
        for m in pat.finditer(str(text or "")):
            tok = m.group(0)
            if (tok, kind) not in out:
                out.append((tok, kind))
    return out


def verify_details(answer: str, reference: str) -> dict[str, Any]:
    """W8 强化: 数字 + 细节(色值/版本/类名/路径/文件) 须能在 reference 中找到。

    返回 {ok, unverified: [token(类型)], note}。回答明说"未查到/不确定" → 放行。
    只标记不阻断 (注入修正轮); reference 空 → 只做数字校验。"""
    chk_num = verify_numbers(answer, reference)
    ref = str(reference or "")
    unverified = list(chk_num.get("unverified") or [])
    if ref and not any(k in answer for k in ("未查询到", "未找到", "不确定", "无法确认", "暂无")):
        for tok, kind in extract_details(answer):
            if tok not in ref:
                unverified.append(f"{tok}({kind})")
    return {"ok": not unverified, "unverified": unverified,
            "note": "回答细节在查询结果中无对应" if unverified else "细节与查询结果一致"}


def no_evidence_prompt() -> str:
    """S-2.2: 无证据不结论 — 查询/分析类未调工具直接答时注入的强制提示。"""
    return (
        "这个查询需要实时数据: 请先调用数据工具 (project_status/project_tasks/project_scan/"
        "code_scan/project_structure/search_code/project_docs/git_status/monitor) 获取真实数据"
        "后再回答, 不要凭空答。"
    )


def production_claim_prompt() -> str:
    """S34/S35-P0-1/6: 生产对象声明必须基于工具结果 — LLM 是解释器, 不是事实来源。"""
    return (
        "【生产声明约束】你在回答中声称的任何生产对象必须来自真实工具结果, 禁止自行推断:\n"
        "- 说『项目已创建』→ 必须有 create_project 工具返回的 project_id\n"
        "- 说『计划已生成/已重新生成』→ 必须有 plan_development 工具返回的 plan_id\n"
        "  (没有 plan_id 只能说『计划已生成』的意图, 或调用 plan_development 生成)\n"
        "- 说『任务已创建』→ 必须有 execute_plan/chain_start 返回的 task_ids\n"
        "- 说『已开始执行』→ 必须有 chain_start/execute_plan 返回的 run_id 或明确执行状态\n"
        "  (若工具返回失败/未返回 ID, 必须如实说明, 不得声称成功)\n"
        "- 查询计划/任务/进度 → 必须先调用 project_plan/project_tasks/project_status 且传 project_id\n"
        "未满足以上条件时, 如实说『尚未创建/尚未执行/需要先执行XX』。"
    )


def self_check_prompt() -> str:
    """S-2.3: 回答后自评 — 硬收敛前注入, 强制检查结论证据。"""
    return (
        "【回答自检】在给出最终答案前, 逐句检查: 每个关键结论是否有工具证据支持?"
        "有 → 保留并引用; 没有 → 删除该结论或明确标注'未查到'; 数字必须是工具结果里的。"
    )
