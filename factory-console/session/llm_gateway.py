"""factory-console/session/llm_gateway.py — 模型无关网关 (S10-127 M1.1/M1.3).

统一内部形状 (OpenAI 为标准):
- messages: [{"role": "system"|"user"|"assistant"|"tool", "content": str, ...}]
- tools:    [{"type": "function", "function": {"name", "description", "parameters"}}]
- 响应:     {"content": str, "tool_calls": [{"id", "type": "function",
              "function": {"name", "arguments"}}]}  (OpenAI 形状)

Provider 适配器注册表 (新增 provider = 加一个适配器, 不改主循环):
- openai_compat: deepseek/openai/moonshot/kimi/ollama/自建 — OpenAI 兼容 /chat/completions
- anthropic:     Messages API (tool_use blocks ↔ OpenAI tool_calls)
- gemini:        generateContent (functionCall ↔ OpenAI tool_calls)

能力协商 (M1.3): 读 ModelCatalog capabilities → 无 tool-use 降级 (不传 tools,
调用方走 prompt 套 JSON 兜底); context_window 由调用方用于注入截断。

不引入第三方 HTTP 依赖 (urllib, 同 agent_loop.call_with_tools)。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger("factory.llm_gateway")

#: Anthropic 默认端点 (providers.json 未配 base_url 时)
_ANTHROPIC_DEFAULT = "https://api.anthropic.com/v1/messages"
#: Gemini 默认端点前缀 (providers.json 未配 base_url 时)
_GEMINI_DEFAULT = "https://generativelanguage.googleapis.com/v1beta"

#: 能力名常量 (ModelCatalog.capabilities 语义)
CAP_TOOL_USE = "tool-use"
CAP_TOOL_USE_ALT = "fc"  # 兼容缩写


# ---------------------------------------------------------------------------
# Provider 类型判定 (provider_id / base_url → 适配器名)
# ---------------------------------------------------------------------------

def provider_kind(provider_id: str, base_url: str = "") -> str:
    """provider_id 归一化 → 适配器名 (openai_compat / anthropic / gemini)。"""
    pid = (provider_id or "").strip().lower()
    if pid in {"anthropic", "claude"} or "anthropic" in pid:
        return "anthropic"
    if pid in {"gemini", "google"} or "gemini" in pid:
        return "gemini"
    return "openai_compat"


# ---------------------------------------------------------------------------
# 形状转换: Anthropic
# ---------------------------------------------------------------------------

def _to_anthropic(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]] | None]:
    """OpenAI 形状 → Anthropic Messages API 形状。

    返回 (system, messages, tools)。tool 结果 → user 消息内 tool_result 块。
    """
    system_parts: list[str] = []
    anth: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        if role == "user":
            anth.append({"role": "user", "content": [{"type": "text", "text": str(content)}]})
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            blocks: list[dict[str, Any]] = []
            if content:
                blocks.append({"type": "text", "text": str(content)})
            for tc in tcs:
                fn = tc.get("function") or {}
                try:
                    inp = json.loads(fn.get("arguments") or "{}")
                except Exception:  # noqa: BLE001 — 坏 JSON → 空对象, 不阻断
                    inp = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id") or "",
                    "name": fn.get("name") or "",
                    "input": inp,
                })
            anth.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            anth.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id") or "",
                    "content": str(content),
                }],
            })
    system = "\n\n".join(p for p in system_parts if p) if system_parts else None
    anth_tools = None
    if tools:
        anth_tools = []
        for t in tools:
            fn = t.get("function") or {}
            anth_tools.append({
                "name": fn.get("name") or "",
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
    return system, anth, anth_tools


def _from_anthropic(data: dict[str, Any]) -> dict[str, Any]:
    """Anthropic 响应 → OpenAI 形状 {content, tool_calls}。"""
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in data.get("content") or []:
        btype = block.get("type")
        if btype == "text":
            if block.get("text"):
                content_parts.append(str(block["text"]))
        elif btype == "tool_use":
            tool_calls.append({
                "id": block.get("id") or "",
                "type": "function",
                "function": {
                    "name": block.get("name") or "",
                    "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                },
            })
    return {"content": "\n".join(p for p in content_parts if p), "tool_calls": tool_calls}


def _anthropic_complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout: int,
) -> dict[str, Any]:
    system, anth_messages, anth_tools = _to_anthropic(messages, tools)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": anth_messages,
        "temperature": temperature,
    }
    if system:
        # P2.1 提示缓存意识: system 块加 cache_control (Anthropic 前缀缓存)
        body["system"] = [{"type": "text", "text": system,
                           "cache_control": {"type": "ephemeral"}}]
    if anth_tools:
        body["tools"] = anth_tools
    req = urllib.request.Request(
        base_url or _ANTHROPIC_DEFAULT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = _from_anthropic(data)
    _u = data.get("usage") or {}
    out["usage"] = {"prompt_tokens": _u.get("input_tokens") or 0,
                    "completion_tokens": _u.get("output_tokens") or 0}
    return out


# ---------------------------------------------------------------------------
# 形状转换: Gemini
# ---------------------------------------------------------------------------

def _to_gemini(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]] | None]:
    """OpenAI 形状 → Gemini generateContent 形状。

    返回 (system_instruction, contents, tools)。tool 结果 → user 内 functionResponse。
    """
    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        if role == "system":
            if content:
                system_parts.append(str(content))
            continue
        g_role = "model" if role == "assistant" else "user"
        if role == "tool":
            contents.append({
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": (m.get("name") or ""),
                        "response": {"result": str(content)},
                    }
                }],
            })
        else:
            parts: list[dict[str, Any]] = []
            if content:
                parts.append({"text": str(content)})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                parts.append({"functionCall": {"name": fn.get("name") or "", "args": args}})
            contents.append({"role": g_role, "parts": parts})
    system = "\n\n".join(p for p in system_parts if p) if system_parts else None
    gemini_tools = None
    if tools:
        decls = []
        for t in tools:
            fn = t.get("function") or {}
            decls.append({
                "name": fn.get("name") or "",
                "description": fn.get("description") or "",
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        gemini_tools = [{"functionDeclarations": decls}]
    return system, contents, gemini_tools


def _from_gemini(data: dict[str, Any]) -> dict[str, Any]:
    """Gemini 响应 → OpenAI 形状 {content, tool_calls}。"""
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    try:
        cands = data.get("candidates") or []
        parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
    except Exception:  # noqa: BLE001
        parts = []
    for part in parts:
        if "text" in part and part.get("text"):
            content_parts.append(str(part["text"]))
        if "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append({
                "id": "",
                "type": "function",
                "function": {
                    "name": fc.get("name") or "",
                    "arguments": json.dumps(fc.get("args") or {}, ensure_ascii=False),
                },
            })
    return {"content": "\n".join(p for p in content_parts if p), "tool_calls": tool_calls}


def _gemini_complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout: int,
) -> dict[str, Any]:
    system, contents, gemini_tools = _to_gemini(messages, tools)
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if gemini_tools:
        body["tools"] = gemini_tools
    url = f"{base_url or _GEMINI_DEFAULT}/models/{model}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out = _from_gemini(data)
    _um = data.get("usageMetadata") or {}
    if _um:
        out["usage"] = {"prompt_tokens": _um.get("promptTokenCount") or 0,
                        "completion_tokens": _um.get("candidatesTokenCount") or 0}
    return out


# ---------------------------------------------------------------------------
# OpenAI 兼容 (默认)
# ---------------------------------------------------------------------------

def _openai_compat_complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    model: str,
    base_url: str,
    api_key: str,
    temperature: float,
    timeout: int,
) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        base_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    out = {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}
    _u = data.get("usage") or {}
    if _u:
        out["usage"] = {"prompt_tokens": _u.get("prompt_tokens") or 0,
                        "completion_tokens": _u.get("completion_tokens") or 0}
    return out


# ---------------------------------------------------------------------------
# 网关入口 (M1.2: 接入 LLMRouter/ModelCatalog 后由 call_with_tools 调用)
# ---------------------------------------------------------------------------

def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    provider_id: str,
    model: str,
    base_url: str = "",
    api_key: str = "",
    temperature: float = 0.2,
    timeout: int = 120,
) -> dict[str, Any]:
    """按 provider 类型分派到对应适配器, 返回 OpenAI 形状 {content, tool_calls}。

    失败抛异常 (调用方诚实降级 — 与旧 call_with_tools 语义一致)。
    """
    kind = provider_kind(provider_id, base_url)
    if kind == "anthropic":
        return _anthropic_complete(
            messages, tools, model=model, base_url=base_url,
            api_key=api_key, temperature=temperature, timeout=timeout,
        )
    if kind == "gemini":
        return _gemini_complete(
            messages, tools, model=model, base_url=base_url,
            api_key=api_key, temperature=temperature, timeout=timeout,
        )
    return _openai_compat_complete(
        messages, tools, model=model, base_url=base_url,
        api_key=api_key, temperature=temperature, timeout=timeout,
    )


def supports_tool_use(capabilities: list[str] | None) -> bool:
    """模型 capabilities 是否支持原生 function calling (M1.3 能力协商)。"""
    caps = [str(c).lower() for c in (capabilities or [])]
    return CAP_TOOL_USE in caps or CAP_TOOL_USE_ALT in caps
