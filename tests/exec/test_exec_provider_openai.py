"""tests/exec/test_exec_provider_openai.py — OpenAI 真实 Adapter + Provider 配置检查。

覆盖 (零真实网络, httpx.MockTransport):
- OpenAIProvider: mock HTTP 成功 (content/usage/estimated_cost_usd 解析)
- 无 API key → ProviderError "openai api key missing"
- HTTP 429 → "openai http 429" (error.message 解析)
- 网络错误 → "openai request failed"
- 响应结构缺失 → "openai invalid response"
- usage 估算: 有 token → estimated_cost_usd; 无 token → None
- Provider 可替换: default_registry 同时含 anthropic + openai (同接口, 禁 mock 证明)
- ProviderConfigChecker: key 缺失 → 明确提示 + blocked 标注 (诚实不假装)
"""

from __future__ import annotations

import httpx
import pytest

from exec.provider import (
    ProviderConfigChecker,
    ProviderError,
    ProviderRegistry,
    ProviderRequest,
    default_registry,
)
from exec.providers.openai import OpenAIProvider


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_handler(request: httpx.Request) -> httpx.Response:
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "fixed\n<patch>\n--- a/x.py\n+++ b/x.py\n</patch>",
                }
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 80},
    }
    return httpx.Response(200, json=body)


class TestOpenAISuccess:
    def test_generate_mock_transport(self):
        p = OpenAIProvider(api_key="test-key", client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="fix bug"))
        assert "fixed" in resp.content
        assert resp.error is None
        assert resp.usage["prompt_tokens"] == 200
        assert resp.usage["completion_tokens"] == 80

    def test_usage_cost_estimated(self):
        p = OpenAIProvider(api_key="test-key", client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        # 200 input × 0.0025/1K + 80 output × 0.01/1K = 0.0005 + 0.0008 = 0.0013
        assert resp.usage["estimated_cost_usd"] == pytest.approx(0.0013)

    def test_request_body_and_headers(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["model"] = request.read().decode().count("gpt-4o")
            return _ok_handler(request)

        p = OpenAIProvider(api_key="secret", client=_mock_client(handler))
        p.generate(ProviderRequest(task_context="hi", max_tokens=2048))
        assert "api.openai.com" in seen["url"]
        assert seen["auth"] == "Bearer secret"
        assert seen["model"] == 1

    def test_no_tokens_no_estimate(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
            )

        p = OpenAIProvider(api_key="test-key", client=_mock_client(handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        assert "estimated_cost_usd" not in resp.usage

    def test_provider_id(self):
        assert OpenAIProvider(api_key="k").provider_id == "openai"


class TestOpenAIErrors:
    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = OpenAIProvider(api_key=None, client=_mock_client(_ok_handler))
        with pytest.raises(ProviderError, match="openai api key missing"):
            p.generate(ProviderRequest(task_context="x"))

    def test_env_api_key_used(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        p = OpenAIProvider(api_key=None, client=_mock_client(_ok_handler))
        resp = p.generate(ProviderRequest(task_context="x"))
        assert resp.ok is True

    def test_http_429(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": {"message": "rate limited", "type": "rate_limit_error"}}
            )

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match=r"openai http 429: rate limited"):
            p.generate(ProviderRequest(task_context="x"))

    def test_http_error_message_fallback(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "server exploded"})

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match=r"openai http 500: server exploded"):
            p.generate(ProviderRequest(task_context="x"))

    def test_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="openai request failed"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_missing_choices(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"usage": {}})

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="openai invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_message_content_missing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant"}}]}
            )

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="openai invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_invalid_response_non_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>oops</html>")

        p = OpenAIProvider(api_key="k", client=_mock_client(handler))
        with pytest.raises(ProviderError, match="openai invalid response"):
            p.generate(ProviderRequest(task_context="x"))

    def test_error_prefixes_stable(self):
        """错误前缀稳定 (测试/审计断言契约)。"""
        p = OpenAIProvider(api_key=None, client=_mock_client(_ok_handler))
        with pytest.raises(ProviderError) as exc:
            p.generate(ProviderRequest(task_context="x"))
        assert str(exc.value).startswith("openai ")


class TestProviderInterchangeability:
    """Provider 可替换铁律: 同 ProviderInterface, 注册表并存, 禁 mock 当能力证明。"""

    def test_default_registry_has_both(self):
        reg = default_registry()
        assert "anthropic" in reg.ids()
        assert "openai" in reg.ids()
        assert reg.count() == 2

    def test_openai_registered_instance(self):
        reg = default_registry()
        assert isinstance(reg.get("openai"), OpenAIProvider)

    def test_registry_swap_same_interface(self):
        """CLI --provider 切换: 同一 ProviderRegistry, 按 id 取不同 Adapter (零修改)。"""
        reg = ProviderRegistry()
        reg.register(OpenAIProvider(api_key="k"))
        from exec.providers.anthropic import AnthropicProvider

        reg.register(AnthropicProvider(api_key="k"))
        assert reg.get("openai").provider_id == "openai"
        assert reg.get("anthropic").provider_id == "anthropic"


class TestProviderConfigChecker:
    def test_no_keys_all_blocked(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        checker = ProviderConfigChecker()
        summary = checker.summary()
        assert summary["any_configured"] is False
        assert summary["blocked"] == ["anthropic", "openai"]
        assert "BLOCKED" in summary["message"]

    def test_single_key_configured(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        checker = ProviderConfigChecker()
        summary = checker.summary()
        assert summary["any_configured"] is True
        assert summary["configured_ids"] == ["openai"]
        assert summary["blocked"] == ["anthropic"]

    def test_all_configured(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        checker = ProviderConfigChecker()
        assert checker.any_configured() is True
        assert checker.configured_ids() == ["anthropic", "openai"]
        assert checker.summary()["blocked"] == []

    def test_check_single_provider(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        checker = ProviderConfigChecker()
        statuses = checker.check("openai")
        assert len(statuses) == 1
        assert statuses[0].provider_id == "openai"
        assert statuses[0].configured is False
        assert "OPENAI_API_KEY" in statuses[0].message  # 明确提示 key 名

    def test_env_injection(self):
        checker = ProviderConfigChecker(env={"OPENAI_API_KEY": "sk-test"})
        assert checker.configured_ids() == ["openai"]
        assert checker.check("anthropic")[0].configured is False

    def test_status_ok_and_message(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        checker = ProviderConfigChecker()
        status = checker.check("openai")[0]
        assert status.ok is True
        assert "已配置" in status.message

    def test_missing_status_message_has_guide(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        checker = ProviderConfigChecker()
        status = checker.check("openai")[0]
        assert status.ok is False
        assert "export OPENAI_API_KEY" in status.message
