"""execution_truth.py — P0-001: Execution Claim ≠ Execution Fact.

核心原则: LLM output is not execution evidence.
任何执行类事实声称 (命令执行/文件操作/测试/构建/部署/任务完成) 必须由
真实 ToolCall + ToolResult 支撑。零工具调用的执行声称是负证据, 必须阻止
进入最终回答。

验证边界:
    MODEL OUTPUT
        ↓
    CLAIM EXTRACTION (结构化声称分类)
        ↓
    EVIDENCE VALIDATION (真实 calls 查找)
        ↓
    ALLOW / REWRITE (Strategy B 撤回)

这不是关键词黑名单 — 机制是 "Execution Claim → Required Evidence →
Evidence Lookup": 声称被识别为执行事实类后, 必须能在本轮真实工具调用
记录中找到支撑, 否则不允许作为事实输出。
"""

from __future__ import annotations

import re
from typing import Any

#: 执行类声称的结构化识别模式 (按事实类型)。匹配的是"陈述完成态"的事实声称,
#: 不是禁用词 — 检测到的声称必须通过证据校验, 普通建议/条件表达不命中。
CLAIM_PATTERNS: dict[str, list[str]] = {
    "command": [
        r"(已|已经)(执行|运行|启动)(了)?[^。；\n]{0,30}",
        r"(命令|脚本|bash|shell)[^。；\n]{0,14}(执行|运行)(完成|成功|了)",
        r"(执行|运行)(完成|成功)(了)?",
        r"正在(执行|运行)[^。；\n]{0,24}(命令|脚本|sleep|bash)",
        r"sleep[^。；\n]{0,12}(正在|已)?(执行|运行)",
    ],
    "file": [
        r"(已|已经)(创建|建立|生成)(了)?[^。；\n]{0,48}",
        r"(已|已经)(删除|移除|写入|修改|更新)(了)?(文件|内容|目录)[^。；\n]{0,48}",
        r"(文件|目录)[^。；\n]{0,14}(已|已经)(创建|删除|写入|修改|更新)",
    ],
    "test": [
        r"(测试|用例|pytest)[^。；\n]{0,20}(通过|失败|passed|failed)",
        r"\d+\s*(passed|failed)",
    ],
    "build": [
        r"(构建|编译|build)[^。；\n]{0,12}(成功|完成|通过|失败)",
    ],
    "deploy": [
        r"已(部署|上线|发布)(了)?[^。；\n]{0,24}",
        r"服务已(启动|上线)",
    ],
    "task": [
        r"(任务|开发|功能|工作)已(完成|全部完成)",
        r"已(完成|交付)(开发|任务|功能)",
        r"全部完成",
    ],
}

#: 声称片段前导的条件/建议/祈使语境 — 这些不是事实声称 (建议/条件表达允许)
_NON_CLAIM_PREFIX = ("如果", "若", "建议", "可以", "请", "假设", "可能", "需要", "例如", "比如")

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    t: [re.compile(p) for p in pats] for t, pats in CLAIM_PATTERNS.items()
}

#: 确定性完成/成功语义 (用于 calls 全失败时的阻断判定)
_SUCCESS_MARKERS = ("成功", "完成", "已创建", "已执行", "已写入", "已删除",
                    "已部署", "已上线", "通过", "已生成")


def extract_execution_claims(text: str) -> list[dict[str, str]]:
    """提取文本中的执行事实声称 → [{type, text}] (结构化, 去重)。"""
    claims: list[dict[str, str]] = []
    if not text:
        return claims
    for ctype, pats in _COMPILED.items():
        for pat in pats:
            for m in pat.finditer(text):
                # 声称片段前导语境检查: 条件/建议/祈使前缀 → 非事实声称
                start = max(0, m.start() - 6)
                prefix = text[start:m.start()]
                if any(p in prefix for p in _NON_CLAIM_PREFIX):
                    continue
                claims.append({"type": ctype, "text": m.group(0).strip()})
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for c in claims:
        key = (c["type"], c["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def has_success_semantics(claims: list[dict[str, str]]) -> bool:
    """声称是否含确定性完成/成功语义 (配合 calls 全失败 → 阻断成功声称)。"""
    return any(k in c["text"] for c in claims for k in _SUCCESS_MARKERS)


def validate_execution_claims(
    text: str, calls: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Execution Claim Validator — 最终响应边界校验。

    规则 (结构化 Claim → Evidence Lookup):
    1. 无执行声称 → ALLOW (普通回答/建议/条件表达)
    2. 有声称 + 本轮零真实工具调用 (calls 无 tool 记录) → BLOCK
       (负证据: 声称没有任何执行记录支撑)
    3. 有声称 + calls 全部失败 + 声称含成功/完成语义 → BLOCK
       (声称成功但无成功执行记录)
    4. 其余 → ALLOW (有真实执行记录支撑; 细节数字由 W8 verify_details 兜底)

    返回 {ok, has_claims, missing: [claim...], reason: zero_tool_call |
    no_success_evidence | ""}
    """
    claims = extract_execution_claims(text or "")
    if not claims:
        return {"ok": True, "has_claims": False, "missing": [], "reason": ""}
    real_calls = [c for c in (calls or []) if c.get("tool")]
    if not real_calls:
        return {
            "ok": False, "has_claims": True,
            "missing": claims, "reason": "zero_tool_call",
        }
    if not any(c.get("ok") for c in real_calls) and has_success_semantics(claims):
        return {
            "ok": False, "has_claims": True,
            "missing": claims, "reason": "no_success_evidence",
        }
    return {"ok": True, "has_claims": True, "missing": [], "reason": ""}


def execution_claim_block_prompt(
    missing: list[dict[str, str]], reason: str
) -> str:
    """Strategy B — 撤回提示: 声称执行但无真实证据 → 要求模型撤回/如实改写。"""
    items = "；".join(f"「{c['text']}」({c['type']})" for c in (missing or [])[:5])
    if reason == "zero_tool_call":
        return (
            "【执行事实校验未通过 (P0-001)】你声称了执行事实, 但本轮没有产生任何真实工具调用: "
            + items + "。\n"
            "本轮 tool_calls=0, 这些声称没有任何执行记录支撑, 禁止作为已发生事实输出。\n"
            "二选一:\n"
            "A. 如果需要真实执行 → 立即通过真实函数调用通道调用对应工具 (如 bash_exec), "
            "拿到真实结果后再陈述;\n"
            "B. 如果无法/不需要执行 → 撤回声称, 如实改写为: 『我还没有实际执行该操作, "
            "当前没有产生真实执行记录』。\n"
            "禁止在未调用工具时描述『已执行/已创建/执行成功』等结果。"
        )
    return (
        "【执行事实校验未通过 (P0-001)】你声称了成功执行, 但本轮所有工具调用都失败了, "
        "没有成功执行记录: " + items + "。\n"
        "禁止声称成功。请如实改写为工具实际返回的失败/错误信息, 或明确标注『执行失败/未完成』。"
    )


def sanitize_hard_converge(content: str, calls: list[dict[str, Any]] | None) -> str:
    """硬收敛兜底: 无法再循环时, 对未通过校验的声称追加诚实标注 (不直接放行)。"""
    v = validate_execution_claims(content, calls)
    if v["ok"]:
        return content
    return (
        "⚠️ 【执行真实性提示】以下内容中声称的执行操作本轮没有真实工具执行记录, "
        "实际执行状态以工具记录为准, 请勿视为已执行: " +
        "；".join(c["text"] for c in (v.get("missing") or [])[:5]) +
        "\n\n" + content
    )
