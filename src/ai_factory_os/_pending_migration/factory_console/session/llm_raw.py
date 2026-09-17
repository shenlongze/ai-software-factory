"""LLM 原始调用 —— 从 console_sessions 摘出（该模块整体停用待删，但本能力不能跟着死）。

为什么单列:
    `console_sessions`（Web 会话栏存储）最后活动 2026-09-07、已被判退，
    但它的 `llm_raw` 被**活跃功能**依赖:
      · `task_decomposition`（任务拆解 —— LLM 分解器工厂注入）
      · `llm_semantic_interpreter`（语义解释器）
    两者要的都是"调 LLM 拿原始文本 + 留痕"，与"会话存储"无关
    ⇒ 摘到 `session/`（老区共用库），让 console_sessions 能被干净删除。

行为与摘出前**完全一致**（照搬，未改逻辑）:
    · 走 `session.reasoning.ReasoningProvider` 装配链（真实 LLM）
    · 留痕 `llm_trace.record_llm_call`（失败安全，绝不影响主链）
    · 不可用 / 失败 → `None`（调用方自行 fallback）
"""
from __future__ import annotations

import time

__all__ = ["llm_raw"]


def _trace(prompt: str, response: str | None, *,
           duration_s: float | None = None, error: str = "",
           model: str = "", provider: str = "") -> None:
    """LLM 调用留痕（延迟导入 ✓ 失败安全 ✓ —— 绝不影响主链 ✓）。"""
    try:
        from ..llm_trace import record_llm_call
        record_llm_call(prompt, response, duration_s=duration_s,
                        model=model, provider=provider, error=error)
    except Exception:  # noqa: BLE001
        pass


def _llm_identity() -> tuple[str, str]:
    """当前 LLM 身份 (model, provider) —— 供留痕 ✓（失败安全 ✓ 空串 ✓）。"""
    try:
        from ai_factory_os.infrastructure.config.provider import get_config
        _l = get_config().get_llm()
        return str(_l.get("model") or ""), str(_l.get("provider") or "")
    except Exception:  # noqa: BLE001 — 留痕绝不因取身份失败而中断 ✓
        return "", ""


def llm_raw(prompt: str) -> str | None:
    """真实 LLM 原始输出 (供意图解析等结构化调用); 不可用/失败 → None。"""
    _t0 = time.time()
    try:
        from .reasoning import ReasoningProvider

        provider = ReasoningProvider()
        llm_fn = provider._default_llm_fn()  # noqa: SLF001 — 同包复用装配链
        text = llm_fn(prompt, "chat")
        text = str(text or "").strip()
        # ★ 思考留痕: 记录原始 prompt/输出（截断 ✓ 失败安全 ✓ 不影响主链 ✓）
        _m1, _p1 = _llm_identity()
        _trace(prompt, text or None, duration_s=time.time() - _t0,
               model=_m1, provider=_p1)
        return text or None
    except Exception as exc:  # noqa: BLE001 — LLM 挂 → None (调用方 fallback)
        _m2, _p2 = _llm_identity()
        _trace(prompt, None, duration_s=time.time() - _t0,
               model=_m2, provider=_p2,
               error=f"{type(exc).__name__}: {exc}")
        return None
