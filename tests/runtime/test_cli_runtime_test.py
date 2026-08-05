"""test_cli_runtime_test.py — CLI: factory runtime test <runtime_id> (smoke, Mock subprocess)。

覆盖: 未注册 rc 7 / SUCCESS rc 0 / FAILED rc 1 (exit≠0/命令不存在/timeout) / --json /
--instruction / runtime.viewed 事件 / 配置缺口 rc 1 / 不落库 / argparse 用法错误。
"""

from __future__ import annotations

import json
import subprocess

import pytest

from cli.main import main
from cli_helpers import event_types, open_events, run_cli
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.models import ExecutionRequest, ExecutionResult, ExecutionStatus
from runtime.store import RuntimeStore

# 冒烟指令常量来自 cli/commands.py (运行时可见)
from cli.commands import SMOKE_INSTRUCTION


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result: _FakeCompleted | None = None, exc: Exception | None = None,
               seen: list | None = None):
    """替换 runtime.adapters.hermes.subprocess.run (CLI 经 BUILTIN_ADAPTERS 实例调用)。"""

    def fake_run(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr("runtime.adapters.hermes.subprocess.run", fake_run)


def _register_runtime(capsys, cli_root, runtime_id: str = "hermes-runtime"):
    """CLI 注册 runtime 身份 (ADR-0007 决策 3: 显式注册)。"""
    rc, out, err = run_cli(capsys, cli_root, "runtime", "add", "--id", runtime_id)
    assert rc == 0
    return runtime_id


class TestSmokePreconditions:
    def test_requires_registration_rc7(self, capsys, cli_root):
        """身份未注册 → rc 7 (registry 是派发解析的唯一事实源)。"""
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 7
        assert "runtime not found" in err

    def test_registered_without_adapter_rc1(self, capsys, cli_root):
        """身份已注册但无内置实现 → 配置缺口 rc 1 (同 execution run 契约)。"""
        _register_runtime(capsys, cli_root, runtime_id="R-001")
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "R-001")
        assert rc == 1
        assert "no adapter implementation" in err


class TestSmokeSuccess:
    def test_smoke_success_rc0(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 0
        assert "hermes-runtime" in out and "SUCCESS" in out

    def test_smoke_success_json(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "test", "hermes-runtime")
        data = json.loads(out)
        assert rc == 0
        assert data["ok"] is True
        assert data["runtime"] == "hermes-runtime"
        assert data["status"] == "SUCCESS"
        assert data["result"]["status"] == "SUCCESS"
        assert data["result"]["output"]["stdout"] == "OK"
        assert data["execution_id"] == "EX-SMOKE-hermes-runtime"
        assert data["event_seq"] > 0

    def test_smoke_default_instruction(self, capsys, cli_root, monkeypatch):
        """默认冒烟指令: 最小 Hermes 调用 (Reply with exactly: OK)。"""
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        argv, _ = seen[0]
        assert argv[1] == "-z"
        assert argv[2] == SMOKE_INSTRUCTION

    def test_smoke_custom_instruction(self, capsys, cli_root, monkeypatch):
        seen = []
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"), seen=seen)
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime",
                "--instruction", "ping")
        assert seen[0][0][2] == "ping"

    def test_smoke_executes_minimal_request(self, capsys, cli_root, monkeypatch):
        """构造最小 execution: task_id=SMOKE, runtime_id 绑定, input 含 instruction。"""
        captured = {}

        def fake_execute(request: ExecutionRequest) -> ExecutionResult:
            captured["request"] = request
            return ExecutionResult(id="EXR-X", request_id=request.id,
                                   output={"stdout": "OK"})

        monkeypatch.setattr(BUILTIN_ADAPTERS["hermes-runtime"], "execute", fake_execute)
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        request = captured["request"]
        assert isinstance(request, ExecutionRequest)
        assert request.task_id == "SMOKE"
        assert request.runtime_id == "hermes-runtime"
        assert request.input["instruction"] == SMOKE_INSTRUCTION

    def test_smoke_no_store_side_effects(self, capsys, cli_root, monkeypatch):
        """smoke 为临时执行: 不落库 (runtimes.json 无 executions/results 残留)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        store = RuntimeStore(cli_root / "runtimes")
        assert store.execution_ids() == []
        assert store.list_results() == []

    def test_smoke_emits_runtime_viewed(self, capsys, cli_root, monkeypatch):
        """审计: 仅 runtime.viewed (ADR-0002 铁律; Adapter 自身不写 execution 事件)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        store = open_events(cli_root)
        try:
            assert event_types(store) == ["runtime.registered", "runtime.viewed"]
        finally:
            store.close()

    def test_smoke_viewed_payload(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout="OK"))
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        store = open_events(cli_root)
        try:
            ev = store.query()[-1]
            assert ev.type.value == "runtime.viewed"
            assert ev.payload["runtime_id"] == "hermes-runtime"
            assert ev.payload["smoke_status"] == "SUCCESS"
            assert ev.payload["execution_id"] == "EX-SMOKE-hermes-runtime"
        finally:
            store.close()


class TestSmokeFailure:
    def test_smoke_exit_nonzero_rc1(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 1
        assert "FAILED" in out
        assert "boom" in out

    def test_smoke_exit_nonzero_json(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "runtime", "test", "hermes-runtime")
        data = json.loads(out)
        assert rc == 1
        assert data["ok"] is False
        assert data["status"] == "FAILED"
        assert data["exit_code"] == 1
        assert "exited with code 1" in data["result"]["error"]

    def test_smoke_command_not_found_rc1(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, exc=FileNotFoundError())
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 1
        assert "FAILED" in out
        assert "command not found" in out

    def test_smoke_timeout_rc1(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, exc=subprocess.TimeoutExpired(cmd="hermes", timeout=300))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 1
        assert "FAILED" in out
        assert "timed out" in out

    def test_smoke_stdout_empty_rc1(self, capsys, cli_root, monkeypatch):
        _patch_run(monkeypatch, result=_FakeCompleted(stdout=""))
        _register_runtime(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        assert rc == 1
        assert "FAILED" in out
        assert "no output" in out

    def test_smoke_failed_viewed_payload(self, capsys, cli_root, monkeypatch):
        """FAILED smoke 同样留审计事件 (payload 带 smoke_status/error)。"""
        _patch_run(monkeypatch, result=_FakeCompleted(returncode=1, stderr="boom"))
        _register_runtime(capsys, cli_root)
        run_cli(capsys, cli_root, "runtime", "test", "hermes-runtime")
        store = open_events(cli_root)
        try:
            ev = store.query()[-1]
            assert ev.payload["smoke_status"] == "FAILED"
            assert ev.payload["error"]
        finally:
            store.close()


class TestUsageErrors:
    def test_unknown_runtime_command_systemexit2(self, cli_root):
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "bogus"])
        assert exc.value.code == 2

    def test_missing_runtime_id_usage_error(self, cli_root):
        """runtime test 缺 runtime_id → argparse SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "test"])
        assert exc.value.code == 2

    def test_runtime_test_listed_in_help(self, cli_root, capsys):
        """runtime --help 列 test 子命令 (argparse 打印后 SystemExit(0))。"""
        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "runtime", "--help"])
        assert exc.value.code == 0
        out, _ = capsys.readouterr()
        assert "test" in out
        assert "smoke test" in out
