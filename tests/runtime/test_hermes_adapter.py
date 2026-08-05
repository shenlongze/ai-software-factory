"""test_hermes_adapter.py — HermesRuntimeAdapter: subprocess 调 hermes CLI (Mock subprocess.run)。

覆盖: 身份/契约/配置 (命令+超时, env 覆盖) / prompt 构造 (task/step/instruction/agent_id) /
成功路径 / 失败处理 (命令不存在/timeout/exit≠0/stdout 空/OS 错误 → FAILED 不抛异常) /
与 events/registry/store 解耦。
"""

from __future__ import annotations

import inspect
import subprocess

import pytest

from runtime.adapter import RuntimeAdapter
from runtime.adapters import BUILTIN_ADAPTERS, HermesRuntimeAdapter
from runtime.adapters.hermes import (
    DEFAULT_COMMAND,
    DEFAULT_TIMEOUT,
    ENV_COMMAND,
    ENV_TIMEOUT,
)
from runtime.models import ExecutionResult, ExecutionStatus

from runtime_helpers import make_request


class _FakeCompleted:
    """模拟 subprocess.CompletedProcess (仅断言所需字段)。"""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result: _FakeCompleted | None = None, exc: Exception | None = None,
               seen: list | None = None):
    """替换 runtime.adapters.hermes.subprocess.run; seen 收集 (argv, kwargs)。"""

    def fake_run(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr("runtime.adapters.hermes.subprocess.run", fake_run)


def _hermes_request(request_id: str = "EX-001", **overrides):
    """Hermes 适配器测试请求 (input 默认含 instruction)。"""
    defaults = {"input": {"instruction": "do the thing"}}
    defaults.update(overrides)
    return make_request(request_id, **defaults)


class TestIdentity:
    def test_is_runtime_adapter(self):
        """契约: 实现 RuntimeAdapter 抽象接口 (仅依赖 models, 无 registry/store/events)。"""
        assert issubclass(HermesRuntimeAdapter, RuntimeAdapter)
        assert isinstance(HermesRuntimeAdapter(), RuntimeAdapter)

    def test_runtime_meta(self):
        assert HermesRuntimeAdapter.RUNTIME_ID == "hermes-runtime"
        assert HermesRuntimeAdapter.TYPE == "agent"

    def test_registered_as_builtin(self):
        """内置注册: BUILTIN_ADAPTERS[\"hermes-runtime\"] 为 HermesRuntimeAdapter 实例。"""
        assert "hermes-runtime" in BUILTIN_ADAPTERS
        assert isinstance(BUILTIN_ADAPTERS["hermes-runtime"], HermesRuntimeAdapter)
        assert HermesRuntimeAdapter.RUNTIME_ID in BUILTIN_ADAPTERS

    def test_builtin_map_contains_echo_too(self):
        """既有 echo 内置不被破坏 (824 不回归)。"""
        assert "echo" in BUILTIN_ADAPTERS

    def test_adapter_decoupled_from_events_and_registry(self):
        """解耦铁律 (ADR-0006): 模块零依赖 events/registry/store — 只依赖 models 契约。"""
        mod = inspect.getmodule(HermesRuntimeAdapter)
        assert mod is not None
        src = inspect.getsource(mod)
        assert "EventLogger" not in src
        assert "from events" not in src
        assert "import events" not in src
        assert "from .registry" not in src
        assert "from .store" not in src
        assert "from runtime.models import" in src
        assert "from runtime.adapter import" in src


class TestConfig:
    def test_default_command_and_timeout(self, monkeypatch):
        """默认: 命令 hermes / 超时 300s (无 env 干扰)。"""
        monkeypatch.delenv(ENV_COMMAND, raising=False)
        monkeypatch.delenv(ENV_TIMEOUT, raising=False)
        adapter = HermesRuntimeAdapter()
        assert adapter.command == DEFAULT_COMMAND == "hermes"
        assert adapter.timeout == DEFAULT_TIMEOUT == 300

    def test_constructor_overrides_defaults(self):
        adapter = HermesRuntimeAdapter(command="/fake/hermes", timeout=42)
        assert adapter.command == "/fake/hermes"
        assert adapter.timeout == 42

    def test_env_command_override(self, monkeypatch):
        monkeypatch.setenv(ENV_COMMAND, "/usr/local/bin/hermes")
        assert HermesRuntimeAdapter().command == "/usr/local/bin/hermes"

    def test_env_timeout_override(self, monkeypatch):
        monkeypatch.setenv(ENV_TIMEOUT, "60")
        assert HermesRuntimeAdapter().timeout == 60

    def test_env_timeout_float(self, monkeypatch):
        monkeypatch.setenv(ENV_TIMEOUT, "12.5")
        assert HermesRuntimeAdapter().timeout == 12.5

    def test_constructor_beats_env(self, monkeypatch):
        monkeypatch.setenv(ENV_COMMAND, "/env/hermes")
        monkeypatch.setenv(ENV_TIMEOUT, "60")
        adapter = HermesRuntimeAdapter(command="/ctor/hermes", timeout=7)
        assert adapter.command == "/ctor/hermes"
        assert adapter.timeout == 7

    def test_timeout_zero_allowed(self):
        assert HermesRuntimeAdapter(timeout=0).timeout == 0


class TestPromptBuilding:
    def test_prompt_from_instruction_only(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={"instruction": "hello"}))
        assert prompt == "hello"

    def test_prompt_with_all_fields(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={
            "task": "T-001", "step": "development", "agent_id": "A-001",
            "instruction": "implement it",
        }))
        assert prompt == "task: T-001\nstep: development\nagent_id: A-001\nimplement it"

    def test_prompt_without_instruction(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={
            "task": "T-001", "step": "development",
        }))
        assert prompt == "task: T-001\nstep: development"

    def test_prompt_partial_fields(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={"agent_id": "A-009"}))
        assert prompt == "agent_id: A-009"

    def test_prompt_empty_input_fallback(self):
        """input 全空 → 兜底 prompt (prompt 永不为空, -z 必带参数)。"""
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={}))
        assert prompt == "execute execution EX-001"

    def test_prompt_coerces_non_str_values(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={
            "task": 123, "instruction": 456,
        }))
        assert "task: 123" in prompt and "456" in prompt

    def test_prompt_ignores_unknown_keys(self):
        adapter = HermesRuntimeAdapter()
        prompt = adapter._build_prompt(_hermes_request(input={
            "prompt": "legacy key", "task": "T-1",
        }))
        assert "legacy key" not in prompt
        assert prompt == "task: T-1"


class TestSuccessPath:
    def test_success_returns_result(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert isinstance(result, ExecutionResult)
        assert result.status is ExecutionStatus.SUCCESS

    def test_success_binds_request(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        result = HermesRuntimeAdapter().execute(_hermes_request("EX-007"))
        assert result.request_id == "EX-007"
        assert result.id == "EXR-EX-007"

    def test_success_output_stdout(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK\n"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.output["stdout"] == "OK\n"

    def test_success_output_meta(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.output["runtime_id"] == "hermes-runtime"
        assert result.output["exit_code"] == 0
        assert result.output["instruction"] == "do the thing"

    def test_success_no_error(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.error is None

    def test_invokes_hermes_one_shot(self, monkeypatch):
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        HermesRuntimeAdapter().execute(_hermes_request(input={"instruction": "go"}))
        argv, _ = seen[0]
        assert argv == ["hermes", "-z", "go"]

    def test_subprocess_kwargs(self, monkeypatch):
        """调用参数: capture_output + text + timeout (契约稳定)。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        adapter = HermesRuntimeAdapter(timeout=99)
        adapter.execute(_hermes_request())
        _, kwargs = seen[0]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 99

    def test_multiline_stdout_preserved(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="line1\nline2\n"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.output["stdout"] == "line1\nline2\n"

    def test_empty_input_dict_still_succeeds(self, monkeypatch):
        """input={} 合法: 兜底 prompt 执行, stdout 非空 → SUCCESS。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        result = HermesRuntimeAdapter().execute(_hermes_request(input={}))
        assert result.status is ExecutionStatus.SUCCESS
        assert seen[0][0][2] == "execute execution EX-001"


class TestFailureHandling:
    """失败处理 (ADR-0009 决策 2): 全部转 FAILED 结果, 不抛未处理异常。"""

    def test_command_not_found_failed(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_command_not_found_error_message(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        result = HermesRuntimeAdapter(command="ghost-hermes").execute(_hermes_request())
        assert "hermes command not found" in result.error
        assert "ghost-hermes" in result.error

    def test_command_not_found_binds_request(self, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        result = HermesRuntimeAdapter().execute(_hermes_request("EX-011"))
        assert result.request_id == "EX-011"
        assert result.id == "EXR-EX-011"

    def test_timeout_failed(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_timeout_error_message(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        result = HermesRuntimeAdapter(timeout=123).execute(_hermes_request())
        assert "timed out" in result.error
        assert "123" in result.error

    def test_timeout_binds_request(self, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        result = HermesRuntimeAdapter().execute(_hermes_request("EX-012"))
        assert result.request_id == "EX-012"

    def test_exit_nonzero_failed(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_exit_nonzero_error_includes_stderr(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=2, stderr="boom"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert "exited with code 2" in result.error
        assert "boom" in result.error

    def test_exit_nonzero_falls_back_to_stdout(self, monkeypatch):
        """stderr 空 → error 附 stdout (不丢信息)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stdout="oops"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert "oops" in result.error

    def test_exit_nonzero_binds_request(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="x"))
        result = HermesRuntimeAdapter().execute(_hermes_request("EX-013"))
        assert result.request_id == "EX-013"

    def test_stdout_empty_failed(self, monkeypatch):
        """exit 0 但 stdout 空 → FAILED (无输出视为未完成)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_stdout_whitespace_only_failed(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="  \n\t"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_stdout_empty_error_message(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert "no output" in result.error

    def test_stdout_empty_includes_stderr(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="", stderr="warn: nothing"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert "warn: nothing" in result.error

    def test_os_error_failed(self, monkeypatch):
        """防御兜底: 其他 OS 级错误 (PermissionError 等) → FAILED 不抛。"""
        _patch_run(monkeypatch, exc=PermissionError("denied"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.status is ExecutionStatus.FAILED

    def test_os_error_message(self, monkeypatch):
        _patch_run(monkeypatch, exc=PermissionError("denied"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert "PermissionError" in result.error

    @pytest.mark.parametrize("failure", [
        "not_found", "timeout", "exit_nonzero", "stdout_empty", "os_error",
    ])
    def test_failure_kinds_never_raise(self, monkeypatch, failure):
        """五类失败全部返回 FAILED 结果, 一律不抛异常。"""
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
        result = HermesRuntimeAdapter().execute(_hermes_request("EX-014"))
        assert result.status is ExecutionStatus.FAILED
        assert result.error

    def test_failed_result_has_no_output(self, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        result = HermesRuntimeAdapter().execute(_hermes_request())
        assert result.output == {}
