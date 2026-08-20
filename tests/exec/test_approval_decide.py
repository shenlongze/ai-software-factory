"""tests/exec/test_approval_decide.py — 审批 decide CLI (M1b/T2)。

覆盖: factory approval list (待审批列表 / --project 过滤 / --status) /
factory approval decide <id> approve|reject (复用 ApprovalGate → 终态落库 +
org.execution.approved 审计) / 二次决定响亮 / 未找到响亮 / 参数缺失 rc 2。
basename 全仓库唯一。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 父目录 (importlib 加载)
    sys.path.insert(0, str(_ROOT))

from exec.approval import ApprovalGate  # noqa: E402
from exec.models import (  # noqa: E402
    Artifact,
    ArtifactType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    new_id,
)
from exec.store import ExecStore  # noqa: E402
from exec_helpers import git_diff_text  # noqa: E402

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

BEFORE = {"calc.py": "def add(a, b):\n    return a + b\n\n"}
AFTER = {"calc.py": "def add(a, b):\n    return a * b\n\n"}


def make_cli(tmp_path: Path) -> tuple[object, Path]:
    """hermetic FactoryCLI: config.json 指向 tmp data_dir (零真实 ~/.factory)。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir()
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
    )
    config = _cfg.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    root = tmp_path / "repo"
    root.mkdir()
    return _cli.FactoryCLI(config, root=root), data_dir


def _seed_approval(
    data_dir: Path, tmp_path: Path, *, project: str = "proj-x", request_id: str = "EXR-decide-1"
) -> str:
    """真实 ApprovalGate.request 种子: ExecutionResult + patch artifact → pending。"""
    store = ExecStore(data_dir / "exec")
    patch_path = tmp_path / "changes.patch"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(git_diff_text(tmp_path, BEFORE, AFTER), encoding="utf-8")
    request = ExecutionRequest(
        id=request_id, task_id="T-decide", objective="fix calc",
        input={"project_dir": str(tmp_path / project)},
    )
    result = ExecutionResult(
        id=new_id("EXS"), request_id=request.id, status=ExecutionStatus.SUCCESS,
        artifacts=[
            Artifact(id=new_id("ART"), type=ArtifactType.PATCH, task_id="T-decide",
                     path=str(patch_path)),
        ],
    )
    store.save_request(request)
    store.save_result(result)
    record = ApprovalGate(store).request(result)
    return record.id


class TestApprovalListCLI:
    def test_list_pending_and_project_filter(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        aid = _seed_approval(data_dir, tmp_path, project="proj-x")
        parser = _cli.build_parser()
        # 全量 pending
        rc = cli.run(parser.parse_args(["approval", "list"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert aid in out
        assert "pending" in out
        # --project 过滤 (匹配)
        rc = cli.run(parser.parse_args(["approval", "list", "--project", str(tmp_path / "proj-x")]))
        assert rc == 0
        out = capsys.readouterr().out
        assert aid in out
        # --project 过滤 (不匹配 → 空)
        rc = cli.run(parser.parse_args(["approval", "list", "--project", str(tmp_path / "other")]))
        assert rc == 0
        out = capsys.readouterr().out
        assert aid not in out
        assert "0 条" in out

    def test_list_status_filter(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        aid = _seed_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "list", "--status", "approved"]))
        assert rc == 0
        assert aid not in capsys.readouterr().out


class TestApprovalCliRegistration:
    def test_approval_list_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _cli.build_parser().parse_args(["approval", "list", "--help"])
        assert exc.value.code == 0
        assert "usage:" in capsys.readouterr().out


class TestApprovalDecideCLI:
    def test_decide_approve_reuses_gate(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        aid = _seed_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(
            parser.parse_args(
                ["approval", "decide", aid, "approve", "--by", "CEO", "--comment", "ok"]
            )
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "approved" in out
        assert aid in out
        assert "CEO" in out
        # 终态落库 (ApprovalGate 状态机)
        record = ExecStore(data_dir / "exec").get_approval(aid)
        assert record.decision.value == "approved"
        assert record.decided_by == "CEO"
        assert record.comment == "ok"
        # 审计: org.execution.approved
        from events.store import EventStore

        store = EventStore(data_dir / "factory.db")
        try:
            types = [e.type.value for e in store.query()]
            assert "org.execution.approved" in types
        finally:
            store.close()

    def test_decide_reject(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        aid = _seed_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(
            parser.parse_args(
                ["approval", "decide", aid, "reject", "--by", "QA", "--comment", "fix tests"]
            )
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "rejected" in out
        record = ExecStore(data_dir / "exec").get_approval(aid)
        assert record.decision.value == "rejected"
        assert record.comment == "fix tests"

    def test_double_decide_fails(self, tmp_path):
        cli, data_dir = make_cli(tmp_path)
        aid = _seed_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        assert cli.run(parser.parse_args(["approval", "decide", aid, "approve", "--by", "CEO"])) == 0
        rc = cli.run(parser.parse_args(["approval", "decide", aid, "approve", "--by", "CEO"]))
        assert rc != 0

    def test_decide_not_found(self, tmp_path):
        cli, data_dir = make_cli(tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "decide", "APR-nope", "approve"]))
        assert rc == 7

    def test_decide_missing_args_rc2(self, tmp_path):
        cli, data_dir = make_cli(tmp_path)
        parser = _cli.build_parser()
        # argparse nargs="?" 可解析缺参 → CLI 层明确 rc 2 (不裸抛)
        rc = cli.run(parser.parse_args(["approval", "decide"]))
        assert rc == 2
