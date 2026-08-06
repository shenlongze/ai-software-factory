"""test_provider_hermes.py — HermesProviderAdapter: subprocess 调 hermes CLI (Mock subprocess.run)。

覆盖: 身份/契约 (ProviderAdapter 实现) / 配置 (命令+超时, 构造参数优先于 env,
env 优先于默认值) / prompt 构造 (generate: prompt → messages 末条 → system →
兜底; chat: system 前缀行 + messages 逐条) / 成功路径 (argv 形态 hermes -z /
usage 计量 / metadata 回填 / 模型回填 DEFAULT_MODEL) / stream 按非空行切块
(末块附 usage) / 与 events/registry/store 解耦。

设计依据: providers/adapters/hermes.py (Phase 8A, ADR-0022), 参照
tests/runtime/test_hermes_adapter.py 模式。
"""

from __future__ import annotations

import inspect
import subprocess

import pytest

from providers.adapters import BUILTIN_PROVIDER_ADAPTERS, HermesProviderAdapter
from providers.adapters.hermes import (
    DEFAULT_COMMAND,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    ENV_COMMAND,
    ENV_TIMEOUT,
)
from providers.models import ProviderRequest, ProviderResponse
from providers.provider import ProviderAdapter

from providers_helpers import make_definition


class _FakeCompleted:
    """模拟 subprocess.CompletedProcess (仅断言所需字段)。"""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result: _FakeCompleted | None = None, exc: Exception | None = None,
               seen: list | None = None):
    """替换 providers.adapters.hermes.subprocess.run; seen 收集 (argv, kwargs)。"""

    def fake_run(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr("providers.adapters.hermes.subprocess.run", fake_run)


def _request(**overrides) -> ProviderRequest:
    defaults = {"provider_id": "hermes"}
    defaults.update(overrides)
    return ProviderRequest(**defaults)


class TestIdentity:
    def test_is_provider_adapter(self):
        assert issubclass(HermesProviderAdapter, ProviderAdapter)
        assert isinstance(HermesProviderAdapter(), ProviderAdapter)

    def test_provider_meta(self):
        assert HermesProviderAdapter.PROVIDER_ID == "hermes"
        assert HermesProviderAdapter.PROVIDER_TYPE == "agent"

    def test_registered_as_builtin(self):
        assert isinstance(BUILTIN_PROVIDER_ADAPTERS["hermes"], HermesProviderAdapter)

    def test_adapter_decoupled_from_events_and_registry(self):
        """解耦铁律 (ADR-0006): 模块零依赖 events/registry/store。"""
        mod = inspect.getmodule(HermesProviderAdapter)
        assert mod is not None
        src = inspect.getsource(mod)
        assert "EventLogger" not in src
        assert "from events" not in src
        assert "import events" not in src
        assert "from .registry" not in src
        assert "from .store" not in src
        assert "from providers.models" in src
        assert "from providers.provider" in src


class TestConfig:
    def test_default_command_and_timeout(self, monkeypatch):
        monkeypatch.delenv(ENV_COMMAND, raising=False)
        monkeypatch.delenv(ENV_TIMEOUT, raising=False)
        adapter = HermesProviderAdapter()
        assert adapter.command == DEFAULT_COMMAND == "hermes"
        assert adapter.timeout == DEFAULT_TIMEOUT == 300

    def test_constructor_overrides_defaults(self):
        adapter = HermesProviderAdapter(command="/fake/hermes", timeout=42)
        assert adapter.command == "/fake/hermes"
        assert adapter.timeout == 42

    def test_env_command_override(self, monkeypatch):
        monkeypatch.setenv(ENV_COMMAND, "/usr/local/bin/hermes")
        assert HermesProviderAdapter().command == "/usr/local/bin/hermes"

    def test_env_timeout_override(self, monkeypatch):
        monkeypatch.setenv(ENV_TIMEOUT, "60")
        assert HermesProviderAdapter().timeout == 60

    def test_env_timeout_float(self, monkeypatch):
        monkeypatch.setenv(ENV_TIMEOUT, "12.5")
        assert HermesProviderAdapter().timeout == 12.5

    def test_constructor_beats_env(self, monkeypatch):
        monkeypatch.setenv(ENV_COMMAND, "/env/hermes")
        monkeypatch.setenv(ENV_TIMEOUT, "60")
        adapter = HermesProviderAdapter(command="/ctor/hermes", timeout=7)
        assert adapter.command == "/ctor/hermes"
        assert adapter.timeout == 7


class TestPromptBuilding:
    def test_generate_uses_prompt(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_prompt(_request(prompt="hello"))
        assert prompt == "hello"

    def test_generate_falls_back_to_last_message(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_prompt(_request(messages=[
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]))
        assert prompt == "second"

    def test_generate_falls_back_to_system(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_prompt(_request(system="sys"))
        assert prompt == "sys"

    def test_generate_empty_fallback(self):
        """prompt 全空 → 兜底 (prompt 永不为空, -z 必带参数)。"""
        adapter = HermesProviderAdapter()
        prompt = adapter._build_prompt(_request())
        assert prompt == "execute provider request hermes"

    def test_chat_builds_system_prefix_lines(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_chat_prompt(_request(
            system="be nice",
            messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
        ))
        assert prompt == "system: be nice\nuser: hi\nassistant: yo"

    def test_chat_ignores_empty_content(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_chat_prompt(_request(messages=[
            {"role": "user", "content": ""},
            {"role": "user", "content": "real"},
        ]))
        assert prompt == "user: real"  # 空 content 行不生成

    def test_chat_falls_back_to_prompt(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_chat_prompt(_request(prompt="plain"))
        assert prompt == "plain"

    def test_chat_empty_fallback(self):
        adapter = HermesProviderAdapter()
        prompt = adapter._build_chat_prompt(_request(provider_id="p9"))
        assert prompt == "execute provider request p9"


class TestSuccessPath:
    def test_success_returns_response(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert isinstance(response, ProviderResponse)
        assert response.ok is True

    def test_success_content_stdout(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="Hello world\n"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.content == "Hello world\n"

    def test_invokes_hermes_one_shot(self, monkeypatch):
        """argv 形态契约: [command, '-z', prompt] (ADR-0009 决策 1 同款)。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        HermesProviderAdapter().generate(_request(prompt="go"))
        argv, _ = seen[0]
        assert argv == ["hermes", "-z", "go"]

    def test_subprocess_kwargs(self, monkeypatch):
        """调用参数: capture_output + text + timeout (契约稳定)。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        adapter = HermesProviderAdapter(timeout=99)
        adapter.generate(_request(prompt="go"))
        _, kwargs = seen[0]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 99

    def test_success_model_default(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.model == DEFAULT_MODEL == "hermes-default"

    def test_success_model_request_override(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        response = HermesProviderAdapter().generate(_request(prompt="go", model="m-9"))
        assert response.model == "m-9"

    def test_success_usage_metrics(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="ab\ncd\n"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.usage["output_chars"] == 6  # len(stdout) 原始字符数 (含换行)
        assert response.usage["output_lines"] == 2

    def test_success_metadata_command(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        response = HermesProviderAdapter(command="/usr/bin/hermes").generate(_request(prompt="go"))
        assert response.metadata["command"] == "/usr/bin/hermes"
        assert response.metadata["exit_code"] == 0

    def test_chat_success(self, monkeypatch):
        """chat 与 generate 走同一 subprocess 调用 (prompt 不同)。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        adapter = HermesProviderAdapter()
        response = adapter.chat(_request(
            system="sys", messages=[{"role": "user", "content": "hi"}],
        ))
        assert response.ok is True
        assert seen[0][0] == ["hermes", "-z", "system: sys\nuser: hi"]


class TestStream:
    def test_stream_yields_lines_as_chunks(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="line1\n\nline2\n"))
        adapter = HermesProviderAdapter()
        chunks = list(adapter.stream(_request(prompt="go")))
        assert [c.content for c in chunks] == ["line1\n", "line2\n"]  # 空行不切块

    def test_stream_last_chunk_has_usage(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="a\nb\n"))
        chunks = list(HermesProviderAdapter().stream(_request(prompt="go")))
        assert chunks[0].usage == {}
        assert chunks[1].usage["output_lines"] == 2

    def test_stream_no_lines_errors(self, monkeypatch):
        """stdout 全空行 → 单 error 块 (稳定响应)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="  \n"))
        chunks = list(HermesProviderAdapter().stream(_request(prompt="go")))
        assert len(chunks) == 1
        assert chunks[0].ok is False
        assert "no output" in chunks[0].error

    def test_stream_failure_yields_error_block(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        chunks = list(HermesProviderAdapter().stream(_request(prompt="go")))
        assert len(chunks) == 1
        assert chunks[0].ok is False
