"""infrastructure/llm/complete_text.py — 「调一次 LLM 拿文本」的统一口。

★ 2026-09-15 新增（功能驱动: 让环①「会话 → 需求理解」能通）。

【为什么需要它】
 `services/conversation/interpreter.py`（语义解释器）与任务拆解等**结构化调用**需要一个
 最简的口: 给一段 prompt, 拿回原始文本; 不可用/失败 → None（调用方诚实降级）。

【为什么不是搬老区的 llm_raw】
 老区 `session/llm_raw.py` 依赖 `session/reasoning.ReasoningProvider`（604 行, 未迁）;
 而新地基**已经具备全部素材**:
   · `infrastructure/llm/gateway.complete()` —— 三家适配器（openai_compat / anthropic / gemini）+ 成本估算
   · `infrastructure/llm/providers/control_plane.LLMControlPlane` —— 配置 + 密钥解析（providers.json）
   · `infrastructure/llm/trace.record_llm_call` —— 留痕（gateway 内已在唯一汇聚点调用）
 ⇒ 所以按功能需要【组装】, 而不是照搬老区那两套。

【行为约定（照老区 llm_raw: 诚实 + 失败安全）】
 · 真实 LLM 输出（不经 JSON 解析、不做结构化约束 —— 那是调用方的事）
 · 不可用 / 无 key / 网络失败 / 空输出 → **None**（绝不假装有内容）
"""

from __future__ import annotations

from typing import Any

__all__ = ["complete_text", "llm_identity"]


def _control_plane() -> Any:
    """LLMControlPlane（providers.json 的配置面）—— 延迟导入, 失败 → None。"""
    try:
        from ai_factory_os.infrastructure.llm.providers.control_plane import LLMControlPlane
        return LLMControlPlane()
    except Exception:  # noqa: BLE001 — 缺配置/包 → 调用方降级
        return None


def llm_identity() -> tuple[str, str]:
    """当前 LLM 身份 (model, provider) —— 供留痕/展示; 取不到 → ("", "")。"""
    plane = _control_plane()
    if plane is None:
        return "", ""
    try:
        pid = plane.selected_provider_id()
        if pid is None:
            return "", ""
        cfg = plane.resolve_runtime_config(pid) or {}
        return str(cfg.get("model") or ""), str(pid)
    except Exception:  # noqa: BLE001
        return "", ""


def complete_text(prompt: str, *, system: str = "", timeout: int = 120) -> str | None:
    """调一次 LLM 拿原始文本; 不可用/失败 → None（调用方自行诚实降级）。

    留痕由 `gateway.complete` 内的唯一汇聚点完成（kind=llm_complete, 带 tokens/cost）,
    本函数不重复记录。
    """
    plane = _control_plane()
    if plane is None:
        return None
    try:
        pid = plane.selected_provider_id()
        if pid is None:
            return None
        cfg = plane.resolve_runtime_config(pid) or {}
        from ai_factory_os.infrastructure.llm.gateway import complete

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": str(prompt)})
        out = complete(
            messages, None,
            provider_id=str(pid),
            model=str(cfg.get("model") or ""),
            base_url=str(cfg.get("base_url") or ""),
            api_key=str(cfg.get("api_key") or ""),
            timeout=int(timeout),
        )
        text = str(out.get("content") or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 — LLM 挂 → None（同老区 llm_raw 语义）
        return None
