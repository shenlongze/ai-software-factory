"""factory-exec/exec/providers/anthropic.py — Anthropic 真实 Provider Adapter (httpx)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §3):
- 真实 HTTP 调用 (Anthropic Messages API), 不是 mock; 无 API key → 清晰
  ProviderError (配置缺口响亮暴露, 不静默降级、不假装成功)。
- Agent 只调 ProviderInterface.generate(), 不知模型/API 细节。

实现:
- ANTHROPIC_API_KEY 环境变量 (构造参数可覆盖, 测试注入)。
- POST https://api.anthropic.com/v1/messages
  headers: x-api-key / anthropic-version: 2023-06-01 / content-type
  body: {model, max_tokens, messages: [{role: "user", content: task_context}]}
- 解析: content[0].text → response.content; usage.input_tokens/output_tokens
  → response.usage (附 estimated_cost 美元估算, 供 Experience 成本记录)。
- 失败路径 (全部转 ProviderError, 稳定前缀供测试/审计断言):
  - 无 key: "anthropic api key missing: ANTHROPIC_API_KEY 未设置 ..."
  - HTTP 错误: "anthropic http <status>: <detail>"
  - 网络错误: "anthropic request failed: <exc>"
  - 响应解析失败: "anthropic invalid response: <exc>"

可测性: client 参数可注入 httpx.Client (测试用 httpx.MockTransport 拦真实
HTTP, 零真实网络); api_key 缺省读环境变量 (调用时读取, monkeypatch.delenv
可测无 key 路径)。
"""

from __future__ import annotations

import os
from typing import Any, cast

import httpx

from ..provider import ProviderError, ProviderInterface, ProviderRequest, ProviderResponse

#: Anthropic Messages API 端点 (官方, 2026-08 稳定)
DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages"
#: API 版本头 (Anthropic 要求)
ANTHROPIC_VERSION = "2023-06-01"
#: 缺省模型 (构造参数可覆盖 — 接口不绑模型, 未来模型名变化只改这里/参数)
DEFAULT_MODEL = "claude-sonnet-4-5"
#: 成本估算 (美元/1K token, 缺省 claude-sonnet 定价; 仅估算, 非计费)
DEFAULT_INPUT_RATE_PER_1K = 3.0
DEFAULT_OUTPUT_RATE_PER_1K = 15.0


class AnthropicProvider:
    """Anthropic Messages API Adapter (ProviderInterface 实现)。

    构造:
    - api_key: 显式 key (None → 每次 generate 时读 ANTHROPIC_API_KEY env —
      测试可 monkeypatch.delenv 触发无 key 路径)。
    - model: 模型名 (缺省 DEFAULT_MODEL; 不绑死 — 未来换模型只改参数)。
    - base_url/timeout: 端点/超时 (测试 MockTransport 时 base_url 随意)。
    - client: 可选注入 httpx.Client (测试 httpx.MockTransport; 缺省自建,
      每次 generate 新建短生命周期 client — 无连接泄漏, KISS)。
    """

    provider_id = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._client = client

    # ------------------------------------------------------------------ 内部

    def _resolve_api_key(self) -> str:
        """API key 解析: 构造参数优先, 否则读环境变量; 缺失 → 清晰 ProviderError。"""
        key = self._api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ProviderError(
                "anthropic api key missing: ANTHROPIC_API_KEY 未设置 "
                "(export ANTHROPIC_API_KEY=... 或构造 AnthropicProvider(api_key=...))"
            )
        return key

    def _estimate_cost(self, usage: dict[str, Any]) -> float | None:
        """token → 美元估算 (仅成本记录用; 无 token 数据 → None, 不臆造)。"""
        try:
            inp = int(usage.get("input_tokens") or 0)
            out = int(usage.get("output_tokens") or 0)
        except (TypeError, ValueError):
            return None
        if inp <= 0 and out <= 0:
            return None
        return round(
            inp / 1000.0 * DEFAULT_INPUT_RATE_PER_1K
            + out / 1000.0 * DEFAULT_OUTPUT_RATE_PER_1K,
            6,
        )

    @staticmethod
    def _parse_content(data: dict[str, Any]) -> str:
        """响应解析: content[0].text; 结构不符 → ProviderError (响亮, 不静默空)。"""
        content = data.get("content")
        if not isinstance(content, list) or not content:
            raise ProviderError(
                f"anthropic invalid response: missing content block: {data!r}"
            )
        first = content[0]
        if not isinstance(first, dict):
            raise ProviderError(
                f"anthropic invalid response: content block not object: {first!r}"
            )
        text = first.get("text")
        if text is None:
            raise ProviderError(
                f"anthropic invalid response: content[0].text missing: {first!r}"
            )
        return str(text)

    # ------------------------------------------------------------ 接口实现

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """真实 HTTP 调用 Messages API (失败 → ProviderError, 不返回假成功)。"""
        key = self._resolve_api_key()
        body = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.task_context}],
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            if self._client is not None:
                resp = self._client.post(
                    self._base_url, json=body, headers=headers, timeout=self._timeout
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.post(
                        self._base_url, json=body, headers=headers, timeout=self._timeout
                    )
        except httpx.HTTPError as exc:
            raise ProviderError(f"anthropic request failed: {exc}") from exc

        if resp.status_code != 200:
            detail = self._error_detail(resp)
            raise ProviderError(
                f"anthropic http {resp.status_code}: {detail}"
            )
        try:
            data = cast(Any, resp.json())
        except ValueError as exc:
            raise ProviderError(f"anthropic invalid response: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError(
                f"anthropic invalid response: body not object: {data!r}"
            )
        try:
            text = self._parse_content(data)
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover — 防御兜底
            raise ProviderError(f"anthropic invalid response: {exc}") from exc

        usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        usage: dict[str, Any] = dict(usage_raw)
        estimated = self._estimate_cost(usage)
        if estimated is not None:
            usage["estimated_cost_usd"] = estimated
        return ProviderResponse(content=text, usage=usage)

    @staticmethod
    def _error_detail(resp: httpx.Response) -> str:
        """HTTP 错误体解析 (Anthropic error.message; 无 JSON 用 status 兜底)。"""
        try:
            data = cast(Any, resp.json())
        except ValueError:
            return resp.text[:200] or f"status {resp.status_code}"
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:200]
            if data.get("message"):
                return str(data["message"])[:200]
            return str(data)[:200]
        return str(data)[:200]
