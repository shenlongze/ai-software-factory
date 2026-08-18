"""factory-console/session/naming.py — 产品命名智能 (S10-081 P0)。

流程: Discovery 字段齐全 → 生成产品名候选 → 用户确认/修改。

- LLM 可用 → AI 生成候选 (简洁中文产品名)
- LLM 不可用 → deterministic 规则提取 (从 idea/problem, 不产生"未命名产品")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("factory.session.naming")

#: 规则提取时剔除的噪音词 (从 idea/problem 提取产品核心词)
_NOISE_WORDS = (
    "我想做", "我想开发", "我想做一个", "我想开发一个", "做一个", "开发一个",
    "做一款", "类似", "一个", "一款", "的app", "的App", "APP", "App", "app",
    "软件", "系统", "工具", "应用", "应用软件",
)

#: LLM 名称建议 prompt
_NAME_PROMPT = (
    "你是产品命名助手。根据下面的产品描述, 给出 1 个简洁的中文产品名"
    "(2-6 字, 不要带'App/系统/工具'等后缀, 不要引号)。\n"
    "产品描述: {desc}\n"
    "产品名:"
)


def _extract_core(text: str, max_len: int = 12) -> str:
    """deterministic 提取: 去噪音词 + 去标点, 取核心片段。"""
    t = str(text or "").strip()
    for w in _NOISE_WORDS:
        t = t.replace(w, " ")
    t = re.sub(r"[，。、,.;；:：!?？!~～\s]+", "", t)
    # 若剩太短或空 → 尝试保留原文首 4 字 (去除尾词)
    if len(t) < 2:
        raw = re.sub(r"[，。、,.;；:：!?？!~～\s]+", "", str(text or "").strip())
        t = raw[:4]
    return t[:max_len]


def suggest_names(desc: str, *, llm_fn: Optional[object] = None, limit: int = 3) -> list[str]:
    """生成产品名候选列表 (S10-082: 多候选供用户选择)。

    LLM 可用 → AI 生成多个; 否则 deterministic 变体。永不产生
    "未命名产品-{ts}"。返回去重、非空、限长候选。
    """
    desc = str(desc or "").strip()
    if not desc:
        return []
    candidates: list[str] = []
    if llm_fn is not None:
        try:
            text = str(llm_fn(_NAMES_PROMPT.format(desc=desc), "naming") or "").strip()
            for line in text.replace("\n", "|").split("|"):
                name = line.strip().strip("-*•·1234567890. ").strip("\"'“”「」")
                if name and len(name) <= 16 and name not in candidates:
                    candidates.append(name)
                    if len(candidates) >= limit:
                        break
        except Exception as exc:  # noqa: BLE001 — LLM 失败 → deterministic
            logger.debug("naming llm failed: %s", exc)
    if not candidates:
        core = _extract_core(desc)
        if core and core not in candidates:
            candidates.append(core)
        # deterministic 变体: 核心词 + 业务后缀
        for suffix in ("助手", "管家", "空间"):
            variant = f"{core}{suffix}" if core else ""
            if variant and variant not in candidates:
                candidates.append(variant)
                if len(candidates) >= limit:
                    break
    return candidates[:limit]


#: LLM 多候选 prompt
_NAMES_PROMPT = (
    "你是产品命名专家。根据下面的产品描述, 给出 3 个简洁的中文产品名候选"
    "(每个 2-6 字, 不要带'App/系统/工具'等后缀, 不要引号), 每行一个。\n"
    "产品描述: {desc}\n"
    "候选名:"
)


def suggest_name(desc: str, *, llm_fn: Optional[object] = None) -> str:
    """生成产品名候选。

    llm_fn 可用 → AI 建议; 否则 deterministic 提取。永不在无候选时
    返回 "未命名产品" (调用方保证 fallback 到临时名仅作极兜底)。
    """
    desc = str(desc or "").strip()
    if not desc:
        return ""
    if llm_fn is not None:
        try:
            text = str(llm_fn(_NAME_PROMPT.format(desc=desc), "naming") or "").strip()
            text = text.strip("\"'“”「」")
            if text and len(text) <= 16:
                return text
        except Exception as exc:  # noqa: BLE001 — LLM 失败 → deterministic
            logger.debug("naming llm failed: %s", exc)
    core = _extract_core(desc)
    if core:
        return core
    return desc[:6]


def suggest_product_name(product_intent: object) -> str:
    """从 ProductIntent 生成名称候选: idea/problem 优先。"""
    raw = getattr(product_intent, "raw", "") or ""
    problem = getattr(product_intent, "problem", "") or ""
    desc = raw or problem or ""
    return suggest_name(desc)


def is_temp_name(name: str) -> bool:
    """判断是否为临时名 (未命名产品-*)。"""
    return str(name or "").startswith("未命名产品")
