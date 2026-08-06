"""test_provider_failures.py — HermesProviderAdapter 失败处理 (统一转 error 响应, 不抛异常)。

覆盖 (同 ADR-0009 决策 2 / runtime hermes adapter 哲学): 命令不存在
(FileNotFoundError) / 超时 (TimeoutExpired) / exit code != 0 (error 附 stderr,
stderr 空时回落 stdout) / stdout 空 (含纯空白; error 附 stderr) / OS 级错误
(PermissionError 等) — 全部返回 ProviderResponse(error=...) 稳定响应; 意外异常
由上层防御 (cmd_provider_test try/except 兜底); 错误消息前缀稳定 (供测试/审计
断言); 失败响应 model 回填 (请求未指定 → DEFAULT_MODEL)。
"""

from __future__ import annotations

import subprocess

import pytest

from providers.adapters.hermes import (
    DEFAULT_MODEL,
    HermesProviderAdapter,
)
from providers.models import ProviderRequest, ProviderResponse

from test_provider_hermes import _FakeCompleted, _patch_run, _request


class TestCommandNotFound:
    def test_returns_error_response(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert isinstance(response, ProviderResponse)
        assert response.ok is False

    def test_error_message_includes_command(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        response = HermesProviderAdapter(command="ghost-hermes").generate(_request(prompt="go"))
        assert "hermes command not found" in response.error
        assert "ghost-hermes" in response.error

    def test_never_raises(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        response = HermesProviderAdapter().generate(_request(prompt="go"))  # 不抛
        assert response.error


class TestTimeout:
    def test_timeout_returns_error(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False

    def test_timeout_message_includes_seconds(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        response = HermesProviderAdapter(timeout=123).generate(_request(prompt="go"))
        assert "timed out" in response.error
        assert "123" in response.error


class TestExitNonZero:
    def test_exit_nonzero_error(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False

    def test_exit_error_includes_stderr(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=2, stderr="boom"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert "exited with code 2" in response.error
        assert "boom" in response.error

    def test_exit_error_falls_back_to_stdout(self, monkeypatch):
        """stderr 空 → error 附 stdout (不丢信息)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stdout="oops"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert "oops" in response.error


class TestEmptyOutput:
    def test_stdout_empty_error(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False
        assert "no output" in response.error

    def test_stdout_whitespace_only_error(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="  \n\t"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False

    def test_empty_error_includes_stderr(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="", stderr="warn: nothing"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert "warn: nothing" in response.error


class TestOsError:
    def test_os_error_returns_error(self, monkeypatch):
        _patch_run(monkeypatch, exc=PermissionError("denied"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False

    def test_os_error_message_includes_type(self, monkeypatch):
        _patch_run(monkeypatch, exc=PermissionError("denied"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert "PermissionError" in response.error


class TestFailureStability:
    @pytest.mark.parametrize("failure", [
        "not_found", "timeout", "exit_nonzero", "stdout_empty", "os_error",
    ])
    def test_failure_kinds_never_raise(self, monkeypatch, failure):
        """五类失败全部返回 error 响应, 一律不抛异常 (稳定响应哲学)。"""
        if failure == "not_found":
            _patch_run(monkeypatch, exc=FileNotFoundError())
        elif failure == "timeout":
            _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=1))
        elif failure == "exit_nonzero":
            _patch_run(monkeypatch, result=_FakeCompleted(returncode=3, stderr="err"))
        elif failure == "stdout_empty":
            _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        else:  # os_error
            _patch_run(monkeypatch, exc=OSError("io error"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.ok is False
        assert response.error

    def test_failure_response_model_default(self, monkeypatch):
        """失败响应 model 回填 (请求未指定 → DEFAULT_MODEL, 稳定契约)。"""
        _patch_run(monkeypatch, exc=FileNotFoundError())
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.model == DEFAULT_MODEL

    def test_failure_response_binds_provider_id(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.provider_id == "hermes"

    def test_failure_has_no_content(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        response = HermesProviderAdapter().generate(_request(prompt="go"))
        assert response.content == ""
