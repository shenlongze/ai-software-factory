"""tests/exec/test_exec_cli.py — exec CLI (run/status/approval + 退出码 + --json + 未知命令)。

入口: standalone `exec.cli.main` (与主 CLI factory-core/cli/main.py 共享同一
cmd_* 实现 — 单一实现零复制; 测试 standalone 即覆盖主 CLI 逻辑)。

覆盖 (Phase A 任务清单):
- exec run: 成功 (mock provider 注入, --json 结构化输出) / Provider 错误 rc 1 /
  项目缺失 rc 1 / 未知 provider rc 1 / 员工未找到 rc 7
- exec status: 空清单 / run 后清单 / --id 详情 / 未找到 rc 7
- exec approval: approve/deny/apply/list 全链 (pending → approved → applied) /
  二次决定 rc 1 / 未批 apply rc 1 / 未找到 rc 7
- 退出码: 0 成功 / 1 业务错误 / 2 用法 (argparse SystemExit) / 7 未找到
- --json: 叶子位置 + 全局位置 (SUPPRESS 修复: 子解析器不覆盖全局 --json)
- 未知命令: argparse 拦截 SystemExit(2) + _dispatch 兜底 dict exit_code 2
- ★ 失败经验 employee_id: run --employee 注入后 Provider 失败 → Experience
  负信号记录的 subject_id == 员工 id (agent_runtime._fail 调用点补参验收)

mock 注入 (装配点模式, 同 Phase 9b): monkeypatch `exec.cli._provider_registry`
返回带 FakeProvider 的注册表 (函数级装配点); `_resolve_employee` 返回
duck-typed 员工 (org 零依赖); `_open_experience_analyzer` 返回 FakeAnalyzer
(经验调用断言)。

事件库路径 (10A-2 陷阱): CLI 测试的 --root R 即数据根 — 事件库 R/factory.db
(不是 R/events.db), 数据空间 R/exec/。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import exec.cli as exec_cli
from events.store import EventStore
from exec.approval import ApprovalGate
from exec.provider import ProviderRegistry
from exec.store import ExecStore
from exec_helpers import FakeProvider, git_diff_text, make_request, write_files

CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


def _bug_project(tmp_path: Path) -> Path:
    """最小 Python 项目 (bug 任务目标; 与 git_diff_text 的 before 逐字一致)。"""
    proj = tmp_path / "cli-bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _patch_content(tmp_path: Path) -> str:
    """真实 git diff (context 逐字匹配, 沙箱 git apply 可应用)。"""
    return git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})


class FakeAnalyzer:
    """ExperienceAnalyzer mock (记录 kwargs; 供经验断言)。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_experience(self, **kwargs):
        self.calls.append(kwargs)
        return {"recorded": True}


class _Employee:
    """duck-typed Employee (org 零依赖; 含 id/capabilities 即可)。"""

    def __init__(self, employee_id: str) -> None:
        self.id = employee_id
        self.capabilities = ["python"]


def _event_types(root: Path) -> list[str]:
    """R/factory.db 事件类型序列 (CLI 每次调用独立 logger_scope, 共用事件库)。"""
    store = EventStore(root / "factory.db")
    try:
        return [e.type.value for e in store.query()]
    finally:
        store.close()


def _json_out(capsys) -> dict:
    """最近一次 CLI 调用的 JSON 输出 (解析)。"""
    out = capsys.readouterr().out
    return json.loads(out)


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """CLI 数据根 (R/exec 数据空间 + R/factory.db 事件库)。"""
    return tmp_path / "cli-root"


@pytest.fixture
def ok_provider(tmp_path: Path) -> FakeProvider:
    """成功 Provider: 合法 patch 回复 (git apply 可应用) + usage。"""
    return FakeProvider(
        content="fixed the sub bug\n<patch>\n" + _patch_content(tmp_path) + "\n</patch>",
        usage={"input_tokens": 12, "estimated_cost_usd": 0.02},
    )


def _install_mock(cli_root: Path, monkeypatch, provider: FakeProvider) -> None:
    """装配点注入: mock provider 注册表 (exec.cli._provider_registry)。"""
    registry = ProviderRegistry()
    registry.register(provider)
    monkeypatch.setattr(exec_cli, "_provider_registry", lambda: registry)


class TestRun:
    def test_run_success_json_and_events(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        """run 成功: rc 0 + --json 结构化输出 + 三产物 + 事件链完整。"""
        _install_mock(cli_root, monkeypatch, ok_provider)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-1",
            "--provider", "mock", "--json",
        ])
        assert rc == 0
        data = _json_out(capsys)
        assert data["ok"] is True
        assert data["status"] == "success"
        assert data["request_id"].startswith("EXR-")
        assert data["result_id"].startswith("EXS-")
        assert data["event_seq"] is not None
        types = [a["type"] for a in data["artifacts"]]
        assert types == ["patch", "test_result", "report"]
        assert data["usage"].get("input_tokens") == 12
        # 事件链: requested → started → completed (终态单一, 无 failed)
        ev = _event_types(cli_root)
        assert ev.count("org.execution.completed") == 1
        assert "org.execution.failed" not in ev
        seqs = {e.type.value: e.seq for e in _events(cli_root)}
        assert seqs["org.execution.requested"] < seqs["org.execution.started"]
        assert seqs["org.execution.started"] < seqs["org.execution.completed"]

    def test_run_json_global_position(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        """--json 在子命令前 (全局位置) 也生效 — SUPPRESS 修复验收。"""
        _install_mock(cli_root, monkeypatch, ok_provider)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "--json", "run",
            "--project", str(project), "--task", "T-cli-2", "--provider", "mock",
        ])
        assert rc == 0
        assert _json_out(capsys)["status"] == "success"

    def test_run_provider_error_rc1(
        self, cli_root: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        """Provider 错误 → 结果 failed + rc 1 (命令本身成功, ok=True)。"""
        _install_mock(cli_root, monkeypatch, FakeProvider(error="anthropic http 429: rate limited"))
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-3", "--provider", "mock",
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "✘ 执行失败" in out
        ev = _event_types(cli_root)
        assert "org.execution.failed" in ev
        assert "org.execution.completed" not in ev

    def test_run_missing_project_rc1(self, cli_root: Path, tmp_path: Path, monkeypatch, capsys):
        _install_mock(cli_root, monkeypatch, FakeProvider())
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(tmp_path / "nope"), "--task", "T-cli-4", "--provider", "mock",
        ])
        assert rc == 1
        err = capsys.readouterr().err
        assert "error:" in err and "project dir not found" in err

    def test_run_unknown_provider_rc1(self, cli_root: Path, tmp_path: Path, monkeypatch, capsys):
        _install_mock(cli_root, monkeypatch, FakeProvider())
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-5", "--provider", "nope",
        ])
        assert rc == 1
        assert "provider not found" in capsys.readouterr().err

    def test_run_employee_not_found_rc7(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        """--employee 未找到 → rc 7 (org 解析错误映射; 装配点 mock 抛错)。"""
        _install_mock(cli_root, monkeypatch, ok_provider)
        project = _bug_project(tmp_path)

        def _resolve_missing(root, employee_ref):
            raise exec_cli.ExecCliError(f"employee not found: {employee_ref}", exit_code=7)

        monkeypatch.setattr(exec_cli, "_resolve_employee", _resolve_missing)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-6",
            "--employee", "E-999", "--provider", "mock",
        ])
        assert rc == 7
        assert "employee not found: E-999" in capsys.readouterr().err

    def test_run_success_records_experience_with_employee(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        """run --employee → 成功经验 subject_id == 员工 id (正信号)。"""
        _install_mock(cli_root, monkeypatch, ok_provider)
        analyzer = FakeAnalyzer()
        monkeypatch.setattr(exec_cli, "_resolve_employee", lambda root, ref: _Employee(ref))
        monkeypatch.setattr(exec_cli, "_open_experience_analyzer", lambda root, logger: analyzer)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-7",
            "--employee", "E-1", "--provider", "mock",
        ])
        assert rc == 0
        assert len(analyzer.calls) == 1
        assert analyzer.calls[0]["subject_id"] == "E-1"
        assert analyzer.calls[0]["result"] == "success"

    def test_run_failure_records_experience_with_employee(
        self, cli_root: Path, tmp_path: Path, monkeypatch, capsys,
    ):
        """★ _fail 补参验收: Provider 失败 → 负信号经验 subject_id == 员工 id。"""
        _install_mock(cli_root, monkeypatch, FakeProvider(error="anthropic http 500: boom"))
        analyzer = FakeAnalyzer()
        monkeypatch.setattr(exec_cli, "_resolve_employee", lambda root, ref: _Employee(ref))
        monkeypatch.setattr(exec_cli, "_open_experience_analyzer", lambda root, logger: analyzer)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-8",
            "--employee", "E-1", "--provider", "mock",
        ])
        assert rc == 1
        assert len(analyzer.calls) == 1
        call = analyzer.calls[0]
        assert call["subject_id"] == "E-1"  # 失败经验 employee_id 正确 (不再为空)
        assert call["result"] == "failure"
        assert call["score"] == 0.2


class TestStatus:
    def test_status_empty(self, cli_root: Path, capsys):
        rc = exec_cli.main(["--root", str(cli_root), "status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "执行结果 0 条" in out
        ev = _event_types(cli_root)
        assert "org.execution.viewed" in ev  # ADR-0002: 读命令审计

    def test_status_json_empty(self, cli_root: Path, capsys):
        rc = exec_cli.main(["--root", str(cli_root), "status", "--json"])
        assert rc == 0
        data = _json_out(capsys)
        assert data["count"] == 0
        assert data["results"] == []

    def test_status_after_run_lists_result(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        _install_mock(cli_root, monkeypatch, ok_provider)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-9", "--provider", "mock", "--json",
        ])
        assert rc == 0
        result_id = _json_out(capsys)["result_id"]
        rc = exec_cli.main(["--root", str(cli_root), "status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert f"执行结果 1 条" in out
        assert result_id in out
        # --id 详情
        rc = exec_cli.main(["--root", str(cli_root), "status", "--id", result_id])
        assert rc == 0
        out = capsys.readouterr().out
        assert result_id in out

    def test_status_not_found_rc7(self, cli_root: Path, capsys):
        rc = exec_cli.main(["--root", str(cli_root), "status", "--id", "EXS-nope"])
        assert rc == 7
        assert "result not found: EXS-nope" in capsys.readouterr().err


class TestApproval:
    def _seed_pending(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ) -> tuple[str, str]:
        """run 成功 + 审批 pending; 返回 (approval_id, request_id)。"""
        _install_mock(cli_root, monkeypatch, ok_provider)
        project = _bug_project(tmp_path)
        rc = exec_cli.main([
            "--root", str(cli_root), "run",
            "--project", str(project), "--task", "T-cli-ap", "--provider", "mock", "--json",
        ])
        assert rc == 0
        data = _json_out(capsys)
        result = ExecStore(cli_root / "exec").get_result(data["result_id"])
        assert result is not None
        # CLI 无 request 子命令 (审批申请走 ApprovalGate); 直接 store 层造 pending
        gate = ApprovalGate(ExecStore(cli_root / "exec"))
        approval = gate.request(result)
        return approval.id, data["request_id"]

    def test_approval_list_empty(self, cli_root: Path, capsys):
        rc = exec_cli.main(["--root", str(cli_root), "approval", "list"])
        assert rc == 0
        assert "审批记录 0 条" in capsys.readouterr().out

    def test_approval_chain_approve_apply(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys, git_target: Path,
    ):
        """pending → list → approve → apply 全链 (真实 git 目标) + 事件链。"""
        approval_id, request_id = self._seed_pending(
            cli_root, tmp_path, ok_provider, monkeypatch, capsys
        )
        # list: 1 条 pending
        rc = exec_cli.main(["--root", str(cli_root), "approval", "list", "--json"])
        assert rc == 0
        data = _json_out(capsys)
        assert data["count"] == 1
        assert data["approvals"][0]["id"] == approval_id
        assert data["approvals"][0]["decision"] == "pending"
        # approve
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "approve",
            "--id", approval_id, "--by", "CEO", "--comment", "looks good", "--json",
        ])
        assert rc == 0
        data = _json_out(capsys)
        assert data["approval"]["decision"] == "approved"
        assert data["approval"]["decided_by"] == "CEO"
        # apply 到真实 git 仓库
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "apply",
            "--id", approval_id, "--project", str(git_target), "--json",
        ])
        assert rc == 0
        data = _json_out(capsys)
        assert data["approval"]["applied"] is True
        assert data["patch_lines"] > 0
        assert "abs(a + b)" in (git_target / "calc.py").read_text()
        # 事件链: requested → started → completed → approved → applied
        seqs = {e.type.value: e.seq for e in _events(cli_root)}
        for name in (
            "org.execution.requested", "org.execution.started",
            "org.execution.completed", "org.execution.approved",
            "org.execution.applied",
        ):
            assert name in seqs, name
        assert seqs["org.execution.completed"] < seqs["org.execution.approved"]
        assert seqs["org.execution.approved"] < seqs["org.execution.applied"]

    def test_approval_deny_then_apply_rejected_rc1(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys, git_target: Path,
    ):
        """deny → rejected; 已拒绝记录 apply → rc 1 (硬拒绝)。"""
        approval_id, _ = self._seed_pending(
            cli_root, tmp_path, ok_provider, monkeypatch, capsys
        )
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "deny",
            "--id", approval_id, "--by", "PM", "--comment", "needs more work",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "rejected" in out
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "apply",
            "--id", approval_id, "--project", str(git_target),
        ])
        assert rc == 1
        assert "requires approved approval" in capsys.readouterr().err

    def test_approval_apply_unapproved_rc1(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys, git_target: Path,
    ):
        """未批 apply → rc 1 (应用 patch 前必批)。"""
        approval_id, _ = self._seed_pending(
            cli_root, tmp_path, ok_provider, monkeypatch, capsys
        )
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "apply",
            "--id", approval_id, "--project", str(git_target),
        ])
        assert rc == 1
        assert "requires approved approval" in capsys.readouterr().err

    def test_approval_decide_twice_rc1(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        """二次决定 → rc 1 (防覆盖审计)。"""
        approval_id, _ = self._seed_pending(
            cli_root, tmp_path, ok_provider, monkeypatch, capsys
        )
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "approve",
            "--id", approval_id, "--by", "CEO",
        ])
        assert rc == 0
        capsys.readouterr()
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "deny",
            "--id", approval_id, "--by", "CEO",
        ])
        assert rc == 1
        assert "already decided" in capsys.readouterr().err

    def test_approval_not_found_rc7(self, cli_root: Path, capsys):
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "approve",
            "--id", "APR-nope", "--by", "CEO",
        ])
        assert rc == 7
        assert "approval not found: APR-nope" in capsys.readouterr().err

    def test_approval_list_status_filter(
        self, cli_root: Path, tmp_path: Path, ok_provider: FakeProvider,
        monkeypatch, capsys,
    ):
        approval_id, _ = self._seed_pending(
            cli_root, tmp_path, ok_provider, monkeypatch, capsys
        )
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "list", "--status", "pending", "--json",
        ])
        assert rc == 0
        assert _json_out(capsys)["count"] == 1
        rc = exec_cli.main([
            "--root", str(cli_root), "approval", "list", "--status", "approved", "--json",
        ])
        assert rc == 0
        assert _json_out(capsys)["count"] == 0


class TestExitCodes:
    def test_unknown_command_systemexit2(self, cli_root: Path):
        """未知顶层命令 → argparse 用法错误 SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            exec_cli.main(["--root", str(cli_root), "bogus"])
        assert exc.value.code == 2

    def test_unknown_approval_subcommand_systemexit2(self, cli_root: Path):
        with pytest.raises(SystemExit) as exc:
            exec_cli.main(["--root", str(cli_root), "approval", "bogus"])
        assert exc.value.code == 2

    def test_missing_required_arg_systemexit2(self, cli_root: Path):
        """run 缺 --project (required) → argparse SystemExit(2)。"""
        with pytest.raises(SystemExit) as exc:
            exec_cli.main(["--root", str(cli_root), "run", "--task", "T-x"])
        assert exc.value.code == 2

    def test_dispatch_unknown_returns_exit_code_2(self, cli_root: Path):
        """_dispatch 兜底: 未知命令 dict exit_code 2 (argparse 拦截后的防御)。"""
        class _Args:
            command = "bogus"
        result = exec_cli._dispatch(cli_root, _Args())
        assert result["ok"] is False
        assert result["exit_code"] == 2


def _events(root: Path):
    """R/factory.db 事件序列 (seq 升序)。"""
    store = EventStore(root / "factory.db")
    try:
        return store.query()
    finally:
        store.close()
