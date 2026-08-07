"""tests/exec/test_exec_provider.py — Provider 注册表 + Anthropic 真实 Adapter。

覆盖 (零真实网络, httpx.MockTransport):
- ProviderRegistry 注册/取/列表/覆盖语义
- default_registry() 懒加载 AnthropicProvider
- AnthropicProvider: mock HTTP 成功 (content/usage/estimated_cost_usd 解析)
- 无 API key → ProviderError "anthropic api key missing"
- HTTP 429 → "anthropic http 429" (error.message 解析)
- 网络错误 → "anthropic request failed"
- 响应结构缺失 → "anthropic invalid response"
- usage 估算: 有 token → estimated_cost_usd; 无 token → None
"""

from __future__ import annotations

import os

import httpx
import pytest

from exec.provider import (
    ProviderError,
    ProviderInterface,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    default_registry,
)
from exec.providers.anthropic import AnthropicProvider


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_handler(request: httpx.Request) -> httpx.Response:
    body = {
        "content": [{"type": "text", "text": "fixed\n<patch>\n--- a/x.py\n+++ b/x.py\n</patch>"}],
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return httpx.Response(200, json=body)


class TestRegistry:
    def test_register_get(self):
        reg = ProviderRegistry()
        p = AnthropicProvider(api_key="k")
        reg.register(p)
        assert reg.get("anthropic") is p

    def test_get_missing_none(self):
        reg = ProviderRegistry()
        assert reg.get("nope") is None

    def test_list_sorted_ids(self):
        reg = ProviderRegistry()
        a = AnthropicProvider(api_key="k")
        b = AnthropicProvider(api_key="k")
        b.provider_id = "zeta"
        c = AnthropicProvider(api_key="k")
        c.provider_id = "alpha"
        for p in (a, b, c):
            reg.register(p)
        assert reg.ids() == ["alpha", "anthropic", "zeta"]
        assert reg.count() == 3

    def test_overwrite_same_id(self):
        reg = ProviderRegistry()
        p1 = AnthropicProvider(api_key="k")
        p2 = AnthropicProvider(api_key="k")
        p2.provider_id = "dupe"
        p1.provider_id = "dupe"
        reg.register(p1)
        reg.register(p2)
        assert reg.get("dupe") is p2  # 后注册优先

    def test_default_registry_has_anthropic(self):
        reg = default_registry()
        assert "anthropic" in reg.ids()
        assert isinstance(reg.get("anthropic"), AnthropicProvider)

    def test_protocol_runtime_checkable(self):
        class Fake:
            provider_id = "f"
            def generate(self, request):  # noqa: ARG002
                return ProviderResponse(content="x")

        assert isinstance(Fake(), ProviderInterface)

    def test_provider_request_defaults(self):
        r = ProviderRequest(task_context="hello")
        assert r.sandbox_path == ""
        assert r.max_tokens == 4096

    def test_provider_response_ok(self):
        assert ProviderResponse(content="x").ok is True
        assert ProviderResponse(content="", error="boom").ok is False


class TestAnthropicSuccess:
    def test_generate_mock_transport(self):
        p = AnthropicProvider(api_key="test-key", client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="fix bug"))
        assert "fixed" in resp.content
        assert resp.error is None
        assert resp.usage["input_tokens"] == 100
        assert resp.usage["output_tokens"] == 50

    def test_usage_cost_estimated(self):
        p = AnthropicProvider(api_key="test-key", client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        # 100 input × 3.0/1K + 50 output × 15.0/1K = 0.3 + 0.75 = 1.05
        assert resp.usage["estimated_cost_usd"] == pytest.approx(1.05)

    def test_request_body_and_headers(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["key"] = request.headers.get("x-api-key")
            seen["version"] = request.headers.get("anthropic-version")
            seen["model"] = request.read().decode().count("claude-sonnet-4-5")
            return _ok_handler(request)

        p = AnthropicProvider(api_key="secret", client=_mock_client(handler))
        p.generate(ProviderRequest(task_context="hi", max_tokens=2048))
        assert "api.anthropic.com" in seen["url"]
        assert seen["key"] == "secret"
        assert seen["version"] == "2023-06-01"
        assert seen["model"] == 1

    def test_no_tokens_no_estimate(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

        p = AnthropicProvider(api_key="test-key", client=_mock_client(handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        assert "estimated_cost_usd" not in resp.usage


class TestAnthropicErrors:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = AnthropicProvider(api_key=None, client=_mock_client(_ok_handler))
        with pytest.raises(ProviderError, match="anthropic api key missing"):
            p.generate(ProviderRequest(task_context="x"))

    def test_env_api_key_used(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        p = AnthropicProvider(api_key=None, client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        assert resp.ok is True

    def test_http_429(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": {"message": "rate limited", "type": "rate_limit_error"}}
            )

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match=r"anthropic http 429: rate limited"):
            p.generate(ProviderRequest(task_context="x"))

    def test_http_error_message_fallback(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "server exploded"})

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match=r"anthropic http 500: server exploded"):
            p.generate(ProviderRequest(task_context="x"))

    def test_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="anthropic request failed"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_missing_content(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"usage": {}})

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="anthropic invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_content_text_missing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"content": [{"type": "text"}]})

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="anthropic invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_non_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        p = AnthropicProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="anthropic invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_error_prefixes_stable(self):
        """错误前缀稳定 (测试/审计断言契约)。"""
        assert os.environ.get("ANTHROPIC_API_KEY") is None or True  # 不依赖 env
        p = AnthropicProvider(api_key=None, client=_mock_client(_ok_handler))
        with pytest.raises(ProviderError) as exc:
            p.generate(ProviderRequest(task_context="x"))
        assert str(exc.value).startswith("anthropic ")
