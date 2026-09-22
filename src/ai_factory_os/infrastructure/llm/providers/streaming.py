"""真·流式：直连 OpenAI 兼容端点，**分块收**（首字几百毫秒就出来）。

为什么单独一个模块（Founder: "A′ 真流式" + 分刀纪律）:
  · 现有 `adapters/hermes.py` 的 `stream()` 是**假流式** —— 它先 `subprocess.run(capture_output=True)`
    把**整段**拿回来, 再按行切块 yield ✗（零加速; 要像打字机只能加人为延迟 = 装样子 ✗）
  · 真流式只有一条路: 换成 **HTTP 直连 + `stream: true`**, 逐块收 SSE ✓
  · ★ 本模块**只新增**, 不改 `generate()` / `chat()` 一个字节 ⇒ 其它环（架构/需求/执行）零影响 ✓

配置来源（单源铁律 ✓）: `<root>/providers.json` 的 `providers.<id>`:
  · `base_url`     —— 完整 chat/completions 地址 ✓
  · `models`       —— 可用模型（取第一个, 或调用方指定 ✓）
  · `api_key_ref`  —— 形如 `env:DEEPSEEK_API_KEY` ⇒ 从 `<root>/.env` 或环境变量取（**密钥只存 env** ✓）
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

_ERR_NO_PROVIDER = "providers.json 里没有可直连的 provider（缺 base_url ✗）"


def load_env(root: Path | str) -> dict[str, str]:
    """读 `<root>/.env`（factory 自己的凭据文件 ✓）—— 只读不写, 不落盘 ✗。"""
    env: dict[str, str] = {}
    for p in (Path(root) / ".env", Path(root) / "llm" / ".env"):
        if not p.is_file():
            continue
        try:
            for ln in p.read_text(encoding="utf-8").splitlines():
                s = ln.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            continue
    return env


def resolve_direct_provider(root: Path | str, provider_id: str = "") -> dict[str, Any]:
    """挑一个**可直连**的 provider（有 base_url + 能解析出 key ✓）; 没有就返回 {}（调用方回退 ✓）。"""
    cfg = Path(root) / "providers.json"
    if not cfg.is_file():
        return {}
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    provs = data.get("providers") or {}
    if not isinstance(provs, dict):
        return {}
    env_file = load_env(root)
    order = [provider_id] if provider_id else [k for k, v in provs.items() if (v or {}).get("enabled")]
    for pid in order:
        p = provs.get(pid) or {}
        base = str(p.get("base_url") or "").strip()
        ref = str(p.get("api_key_ref") or "").strip()
        if not base or not ref.startswith("env:"):
            continue
        key = env_file.get(ref[4:]) or os.environ.get(ref[4:], "")
        if not key:
            continue
        models = p.get("models") or []
        return {"id": pid, "base_url": base, "model": (models[0] if models else ""), "api_key": key}
    return {}


def stream_chat(
    root: Path | str,
    messages: list[dict[str, str]],
    *,
    provider_id: str = "",
    model: str = "",
    on_delta: Callable[[str], None] | None = None,
    timeout: int = 90,
    max_tokens: int = 1200,
) -> dict[str, Any]:
    """直连流式对话: 逐块回调 `on_delta(片段)`; 返回 `{ok, content, usage, model, error}`。

    网络/解析失败**不抛**给人（返回 ok=False + error ✓）, 调用方回退到非流式路径 ✓。
    """
    prov = resolve_direct_provider(root, provider_id)
    if not prov:
        return {"ok": False, "error": _ERR_NO_PROVIDER, "content": ""}
    body = {
        "model": model or prov["model"],
        "messages": messages,
        "stream": True,                     # ★ 关键: 分块收 ✓
        "max_tokens": int(max_tokens),
    }
    req = _urllib_request(prov["base_url"], json.dumps(body).encode("utf-8"),
                          {"Content-Type": "application/json",
                           "Authorization": f"Bearer {prov['api_key']}"})
    full: list[str] = []
    usage: dict[str, Any] = {}
    try:
        import urllib.request as _u

        with _u.urlopen(req, timeout=timeout) as resp:      # noqa: S310 — 地址来自 providers.json（自有配置 ✓）
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except ValueError:
                    continue
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for ch in (chunk.get("choices") or []):
                    piece = ((ch.get("delta") or {}).get("content")) or ""
                    if piece:
                        full.append(piece)
                        if on_delta is not None:
                            on_delta(piece)
    except Exception as exc:  # noqa: BLE001 — 失败交给调用方回退 ✓
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}",
                "content": "".join(full), "usage": usage, "model": body["model"]}
    return {"ok": True, "content": "".join(full), "usage": usage, "model": body["model"],
            "provider_id": prov["id"]}


def iter_lines(text: str) -> Iterator[str]:
    """把一段文本按行给出去（会话层用它做"逐行呈现" —— 与真流式配合时, 边收边出 ✓）。"""
    for ln in (text or "").splitlines():
        yield ln


def _urllib_request(url: str, data: bytes, headers: dict[str, str]) -> Any:
    import urllib.request as _u

    return _u.Request(url, data=data, headers=headers, method="POST")  # noqa: S310 — 自有配置地址 ✓
