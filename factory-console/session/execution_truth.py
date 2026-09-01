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
        # P0-FIX: 数量型/组合型任务声称 (覆盖 "拆解成 6 个任务并创建到任务列表")
        r"(已|已经)?(拆解|拆分|分解)(成|为)?[^。；\n]{0,24}(任务|任务列表)",
        r"(已|已经)?(创建|生成)(了)?[^。；\n]{0,24}(任务|任务列表)",
        r"(已|已经)?(添加|加入)(了)?[^。；\n]{0,24}(任务|任务列表)",
        r"(已|已经)?(落到|写入|进入)(了)?[^。；\n]{0,16}(任务|任务列表)",
        r"(已|已经)?(标记为|进入)(了)?(待办|待办树)",
        r"(已|已经)?(创建|生成|添加|加入)(了)?\s*\d+\s*个任务",
        r"\d+\s*个任务[^。；\n]{0,10}?(已|已经)?(添加|创建|生成|加入)(了)?(成功|完成)?",
        r"(已|已经)?创建(了)?[^。；\n]{0,16}到任务列表",
        r"创建了?\s*\d+\s*个(任务|功能|模块)",
    ],
}

#: 条件/假设前缀 — 永远 INTENT (无论完成态): "如果你刚才执行成功" 不是声称
_CONDITION_PREFIX = ("如果", "若", "假如", "假设", "要是", "只要", "除非", "万一",
                     "即便", "即使", "虽然", "尽管")

#: 意图/未来前缀 — 仅无完成态时豁免 (我计划/准备/打算/将 → INTENT)
_INTENT_PREFIX = ("计划", "准备", "打算", "将", "建议", "请", "要", "想", "希望",
                  "试着", "应该", "最好", "可以", "可能", "需要", "例如", "比如",
                  "下一步", "未来", "试着", "尝试")

#: 完成态标记 — 匹配文本内出现任一 → 完成态执行声称, 跳过意图前缀豁免
#: (Rule 1: 完成态优先; "开发计划已创建完成" 的 "计划" 是业务名词, 非意图)
_COMPLETION_MARKERS = ("已", "已经", "了", "完成", "成功", "好了", "完毕")

#: 数量型声称提取 (创建/拆解 N 个任务/功能/模块 — 允许 "N 个具体任务" 类修饰)
_COUNT_RE = re.compile(r"(\d+)\s*个[^。；\n]{0,8}?(任务|功能|模块|子任务)")

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    t: [re.compile(p) for p in pats] for t, pats in CLAIM_PATTERNS.items()
}

#: 确定性完成/成功语义 (用于 calls 全失败时的阻断判定)
_SUCCESS_MARKERS = ("成功", "完成", "已创建", "已执行", "已写入", "已删除",
                    "已部署", "已上线", "通过", "已生成")


#: 完成态标记 — 匹配文本内出现任一 → 完成态执行声称, 不做前缀 INTENT 豁免
#: (Rule 1: 完成态优先; "开发计划已创建完成" 的 "计划" 是业务名词, 非意图)
_COMPLETION_MARKERS = ("已", "已经", "了", "完成", "成功", "好了", "完毕")


def extract_execution_claims(text: str) -> list[dict[str, str]]:
    """提取文本中的执行事实声称 → [{type, text}] (结构化, 去重)。

    Claim/Intent 优先级 (P1-FIX):
    - 匹配文本含完成态标记 (已/已经/了/完成/成功/好了) → EXECUTION CLAIM
      (前缀即使含 "计划/准备/将" 等业务名词/引导词也不豁免 — "开发计划已创建完成")
    - 无完成态标记 + 前缀含意图引导 (我计划/准备/打算/将/建议) → INTENT, 跳过
      ("我计划创建 7 个任务" 不拦截)
    """
    claims: list[dict[str, str]] = []
    if not text:
        return claims
    for ctype, pats in _COMPILED.items():
        for pat in pats:
            for m in pat.finditer(text):
                mtext = m.group(0)
                start = max(0, m.start() - 6)
                prefix = text[start:m.start()]
                # 条件/假设前缀 → 永远 INTENT ("如果你刚才执行成功" 不是声称)
                if any(p in prefix for p in _CONDITION_PREFIX):
                    continue
                completed = any(k in mtext for k in _COMPLETION_MARKERS)
                if completed:
                    # Rule 1: 完成态执行声称优先 — 业务名词 (开发计划) 不豁免
                    claims.append({"type": ctype, "text": mtext.strip()})
                    continue
                # 无完成态: 前导意图语境 → INTENT (我计划/准备/建议/将)
                if any(p in prefix for p in _INTENT_PREFIX):
                    continue
                claims.append({"type": ctype, "text": mtext.strip()})
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


def extract_claimed_count(text: str) -> int | None:
    """提取数量型声称中的数字 (创建/拆解 N 个任务)。多数字 → 取最大 (保守)。"""
    m = _COUNT_RE.search(text or "")
    if not m:
        return None
    return max(int(x) for x, _ in _COUNT_RE.findall(text))


def _evidence_task_count(evidence_text: str | None) -> int:
    """从事实文本提取任务 id 数 (意图路由 facts 驱动回复的证据计数)。"""
    if not evidence_text:
        return 0
    return len(set(re.findall(r"\bTASK-[\w-]+", evidence_text)))


def validate_execution_claims(
    text: str,
    calls: list[dict[str, Any]] | None,
    *,
    actual_count: int | None = None,
    evidence_text: str | None = None,
) -> dict[str, Any]:
    """Execution Claim Validator — 最终响应边界校验 (P0-FIX: 数量型事实比对)。

    规则 (结构化 Claim → Evidence Lookup → Outcome):
    1. 无执行声称 → ALLOW (普通回答/建议/条件/计划表达), outcome=informational
    2. 有声称 + 本轮零真实工具调用 + 无 facts 证据 → BLOCK, outcome=not_executed
    3. 有声称 + calls 全部失败 + 声称含成功/完成语义 → BLOCK, outcome=failed
    4. 数量型声称 + actual_count 提供 (calls 或 evidence_text 推导):
       - actual >= claimed → ALLOW (success)
       - 0 < actual < claimed → BLOCK 成功语义, outcome=partial (事实降级)
       - actual == 0 → BLOCK, outcome=not_executed
    5. evidence_text (意图路由 facts 驱动回复): 声称需能在 facts 找到依据 —
       数量型用 facts 中任务 id 数; 非数量型若 facts 无任何任务 id → not_executed

    返回 {ok, has_claims, missing, reason, outcome, claimed_count, actual_count}
    outcome ∈ informational | success | partial | not_executed | failed
    """
    claims = extract_execution_claims(text or "")
    if not claims:
        return {"ok": True, "has_claims": False, "missing": [], "reason": "",
                "outcome": "informational", "claimed_count": None,
                "actual_count": actual_count}
    claimed = extract_claimed_count(text or "")
    real_calls = [c for c in (calls or []) if c.get("tool")]
    # 事实数量: 显式 actual_count > calls 成功数 > evidence 任务 id 数
    ev_count = _evidence_task_count(evidence_text)
    if actual_count is None and real_calls:
        actual_count = len([
            c for c in real_calls
            if c.get("tool") in ("create_task", "task_action", "execute_plan")
            and c.get("ok")
        ])
    if actual_count is None and evidence_text:
        actual_count = ev_count
    if not real_calls and not evidence_text:
        return {
            "ok": False, "has_claims": True,
            "missing": claims, "reason": "zero_tool_call",
            "outcome": "not_executed", "claimed_count": claimed,
            "actual_count": actual_count,
        }
    if not any(c.get("ok") for c in real_calls) and has_success_semantics(claims) \
            and not evidence_text:
        return {
            "ok": False, "has_claims": True,
            "missing": claims, "reason": "no_success_evidence",
            "outcome": "failed", "claimed_count": claimed,
            "actual_count": actual_count,
        }
    # 数量型声称事实比对
    if claimed is not None and actual_count is not None:
        if actual_count == 0:
            return {
                "ok": False, "has_claims": True, "missing": claims,
                "reason": "count_zero", "outcome": "not_executed",
                "claimed_count": claimed, "actual_count": actual_count,
            }
        if actual_count < claimed:
            return {
                "ok": False, "has_claims": True, "missing": claims,
                "reason": "count_mismatch", "outcome": "partial",
                "claimed_count": claimed, "actual_count": actual_count,
            }
    return {"ok": True, "has_claims": True, "missing": [], "reason": "",
            "outcome": "success", "claimed_count": claimed,
            "actual_count": actual_count}


def execution_claim_block_prompt(
    missing: list[dict[str, str]], reason: str,
    *, outcome: str = "", claimed_count: int | None = None,
    actual_count: int | None = None,
) -> str:
    """Strategy B — 撤回提示: 声称执行但无真实证据 → 要求模型撤回/如实改写。"""
    items = "；".join(f"「{c['text']}」({c['type']})" for c in (missing or [])[:5])
    if outcome == "partial":
        return (
            f"【执行事实校验未通过 (P0-001)】你声称创建 {claimed_count} 个任务, "
            f"但实际成功创建 {actual_count} 个 — 数量不一致。\n"
            "禁止输出『已创建 N 个任务』等成功语义。请如实改写为: "
            f"『已创建 {actual_count} 个任务, 其余尚未创建』, 以实际执行为准。"
        )
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


def sanitize_hard_converge(
    content: str, calls: list[dict[str, Any]] | None,
    *, actual_count: int | None = None,
) -> str:
    """硬收敛兜底: 无法再循环时, 对未通过校验的声称追加诚实标注 (不直接放行)。"""
    v = validate_execution_claims(content, calls, actual_count=actual_count)
    if v["ok"]:
        return content
    if v.get("outcome") == "partial" and v.get("claimed_count") and v.get("actual_count") is not None:
        return (
            f"⚠️ 【执行真实性提示】声称创建 {v['claimed_count']} 个任务, 实际成功 "
            f"{v['actual_count']} 个 — 以实际执行为准, 未创建部分不得视为成功: "
            + "；".join(c["text"] for c in (v.get("missing") or [])[:3])
            + "\n\n" + content
        )
    return (
        "⚠️ 【执行真实性提示】以下内容中声称的执行操作本轮没有真实工具执行记录, "
        "实际执行状态以工具记录为准, 请勿视为已执行: "
        + "；".join(c["text"] for c in (v.get("missing") or [])[:5])
        + "\n\n" + content
    )
