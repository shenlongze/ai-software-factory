"""factory-exec/exec/providers/openai.py — OpenAI 真实 Provider Adapter (httpx)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §3 + Provider 可替换铁律):
- 与 AnthropicProvider 同 ProviderInterface (provider_id + generate(request)),
  仅 API 形态不同 (OpenAI Chat Completions API)。Provider 可替换: CLI --provider
  切换, Core/Runtime 零修改 (禁 mock 当能力证明 — 真实 HTTP 调用)。
- 真实 HTTP 调用, 不是 mock; 无 API key → 清晰 ProviderError (配置缺口响亮
  暴露, 不静默降级、不假装成功) — 与 Anthropic 同语义。
- Agent 只调 ProviderInterface.generate(), 不知模型/API 细节。

实现:
- OPENAI_API_KEY 环境变量 (构造参数可覆盖, 测试注入)。
- POST https://api.openai.com/v1/chat/completions
  headers: Authorization: Bearer <key> / content-type
  body: {model, max_tokens, messages: [{role: "user", content: task_context}]}
- 解析: choices[0].message.content → response.content;
  usage.prompt_tokens/completion_tokens → response.usage (附 estimated_cost
  美元估算, 供 Experience 成本记录)。
- 失败路径 (全部转 ProviderError, 稳定前缀供测试/审计断言):
  - 无 key: "openai api key missing: OPENAI_API_KEY 未设置 ..."
  - HTTP 错误: "openai http <status>: <detail>"
  - 网络错误: "openai request failed: <exc>"
  - 响应解析失败: "openai invalid response: <exc>"

可测性: client 参数可注入 httpx.Client (测试用 httpx.MockTransport 拦真实
HTTP, 零真实网络); api_key 缺省读环境变量 (调用时读取, monkeypatch.delenv
可测无 key 路径)。
"""

from __future__ import annotations

import os
import ssl
from typing import Any, cast

import httpx

from ..provider import ProviderError, ProviderInterface, ProviderRequest, ProviderResponse

#: OpenAI Chat Completions API 端点 (官方, 2026-08 稳定)
DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
#: 缺省模型 (构造参数可覆盖 — 接口不绑模型, 未来模型名变化只改这里/参数)
DEFAULT_MODEL = "gpt-4o"
#: 成本估算 (美元/1K token, 缺省 gpt-4o 定价; 仅估算, 非计费)
DEFAULT_INPUT_RATE_PER_1K = 0.0025
DEFAULT_OUTPUT_RATE_PER_1K = 0.01


def _default_ssl_context() -> ssl.SSLContext:
    """默认 TLS 上下文: 强制最低 TLSv1_2 (代理 TLS 1.3 不兼容 → SSL UNEXPECTED_EOF)。

    本机/部分网络代理 (如 127.0.0.1:6518) 只支持 TLS 1.2, 而 httpx 默认协商
    TLS 1.3 → 握手被代理截断 (SSL UNEXPECTED_EOF_BEFORE_FIRST_BYTE)。
    强制 minimum_version=TLSv1_2 后握手成功 (与 curl --tlsv1.2 行为一致)。
    TLSv1_2 仍是当前安全基线 (AES-GCM/ECDHE, PCI-DSS 合规), 不降级安全性。
    """
    ctx = ssl.create_default_context()
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    except AttributeError:  # pragma: no cover — 极老 Python 兜底
        pass
    return ctx


class OpenAIProvider:
    """OpenAI Chat Completions API Adapter (ProviderInterface 实现)。

    构造:
    - api_key: 显式 key (None → 每次 generate 时读 OPENAI_API_KEY env —
      测试可 monkeypatch.delenv 触发无 key 路径)。
    - model: 模型名 (缺省 DEFAULT_MODEL; 不绑死 — 未来换模型只改参数)。
    - base_url/timeout: 端点/超时 (测试 MockTransport 时 base_url 随意)。
    - client: 可选注入 httpx.Client (测试 httpx.MockTransport; 缺省自建,
      每次 generate 新建短生命周期 client — 无连接泄漏, KISS)。
    """

    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
        input_rate_per_1k: float | None = None,
        output_rate_per_1k: float | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._client = client
        # 成本估算费率可覆盖 (OpenAI 兼容端点如 DeepSeek 定价不同;
        # 缺省 gpt-4o 费率 — 仅估算, 非计费)
        self._input_rate_per_1k = (
            input_rate_per_1k if input_rate_per_1k is not None else DEFAULT_INPUT_RATE_PER_1K
        )
        self._output_rate_per_1k = (
            output_rate_per_1k if output_rate_per_1k is not None else DEFAULT_OUTPUT_RATE_PER_1K
        )

    # ------------------------------------------------------------------ 内部

    def _resolve_api_key(self) -> str:
        """API key 解析: 构造参数优先, 否则读环境变量; 缺失 → 清晰 ProviderError。"""
        key = self._api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ProviderError(
                "openai api key missing: OPENAI_API_KEY 未设置 "
                "(export OPENAI_API_KEY=... 或构造 OpenAIProvider(api_key=...))"
            )
        return key

    def _estimate_cost(self, usage: dict[str, Any]) -> float | None:
        """token → 美元估算 (仅成本记录用; 无 token 数据 → None, 不臆造)。"""
        try:
            inp = int(usage.get("prompt_tokens") or 0)
            out = int(usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            return None
        if inp <= 0 and out <= 0:
            return None
        return round(
            inp / 1000.0 * self._input_rate_per_1k
            + out / 1000.0 * self._output_rate_per_1k,
            6,
        )

    @staticmethod
    def _parse_content(data: dict[str, Any]) -> str:
        """响应解析: choices[0].message.content; 结构不符/空内容 → ProviderError。

        Phase A++++++-1 可靠性: **空内容检测** — reasoning 模型 max_tokens
        耗尽时 content 为空串 (历史空内容 ×4 根因); 空内容 → 明确
        ProviderError (finish_reason=length 时提示 max_tokens 耗尽), 供
        DeveloperAgent 判定为可重试信号 (不静默当成功)。

        content 兼容两种形态 (OpenAI 兼容端点差异):
        - str: 纯文本 (主流形态);
        - list: 多段内容 (部分兼容端点返回 [{type: text, text: ...}, ...]) —
          拼接各段 text; 段内无 text → 该段忽略。
        """
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                f"openai invalid response: missing choices: {data!r}"
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise ProviderError(
                f"openai invalid response: choice not object: {first!r}"
            )
        message = first.get("message")
        if not isinstance(message, dict):
            raise ProviderError(
                f"openai invalid response: choice.message missing: {first!r}"
            )
        text = message.get("content")
        if text is None:
            raise ProviderError(
                f"openai invalid response: message.content missing: {message!r}"
            )
        if isinstance(text, list):
            parts: list[str] = []
            for seg in text:
                if isinstance(seg, dict) and isinstance(seg.get("text"), str):
                    parts.append(seg["text"])
            text = "".join(parts)
        else:
            text = str(text)
        if not text.strip():
            # 空内容: 显式错误 + 重试信号 (finish_reason=length → max_tokens 耗尽)
            finish = first.get("finish_reason")
            if finish == "length":
                raise ProviderError(
                    "openai empty response: finish_reason=length "
                    "(max_tokens exhausted by reasoning — retry with "
                    "higher max_tokens or shorter task)"
                )
            raise ProviderError(
                "openai empty response: message.content is empty "
                "(reasoning model produced no output — retryable)"
            )
        return text

    # ------------------------------------------------------------ 接口实现

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """真实 HTTP 调用 Chat Completions API (失败 → ProviderError, 不返回假成功)。"""
        key = self._resolve_api_key()
        body = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.task_context}],
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        }
        try:
            if self._client is not None:
                resp = self._client.post(
                    self._base_url, json=body, headers=headers, timeout=self._timeout
                )
            else:
                with httpx.Client(
                    timeout=self._timeout, verify=_default_ssl_context()
                ) as client:
                    resp = client.post(
                        self._base_url, json=body, headers=headers, timeout=self._timeout
                    )
        except httpx.HTTPError as exc:
            raise ProviderError(f"openai request failed: {exc}") from exc

        if resp.status_code != 200:
            detail = self._error_detail(resp)
            raise ProviderError(
                f"openai http {resp.status_code}: {detail}"
            )
        try:
            data = cast(Any, resp.json())
        except ValueError as exc:
            raise ProviderError(f"openai invalid response: {exc}") from exc
        if not isinstance(data, dict):
            raise ProviderError(
                f"openai invalid response: body not object: {data!r}"
            )
        try:
            text = self._parse_content(data)
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover — 防御兜底
            raise ProviderError(f"openai invalid response: {exc}") from exc

        usage_raw = data.get("usage")
        usage: dict[str, Any] = (
            {str(k): v for k, v in usage_raw.items()}
            if isinstance(usage_raw, dict)
            else {}
        )
        estimated = self._estimate_cost(usage)
        if estimated is not None:
            usage["estimated_cost_usd"] = estimated
        return ProviderResponse(content=text, usage=usage)

    @staticmethod
    def _error_detail(resp: httpx.Response) -> str:
        """HTTP 错误体解析 (OpenAI error.message; 无 JSON 用 status 兜底)。"""
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
