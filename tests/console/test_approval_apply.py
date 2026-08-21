"""tests/console/test_approval_apply.py — factory approval apply CLI (M1 闭环 T1)。

覆盖: apply 成功 (已批准 + git 目标 → patch 真实落地, 不 stub) / 未批准硬拒绝
(pending/rejected 不绕过 ApprovalGate) / 重复应用拒绝 (幂等) / 非 git 目标硬
拒绝 (可审计铁律) / 未找到响亮 (rc 7) / 参数缺失 rc 2 / decide approve 后打印
下一步提示 (演示不再死路)。
basename 全仓库唯一; 本目录自洽 (git helper 局部实现, 不跨目录依赖)。
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 父目录 (importlib 加载)
    sys.path.insert(0, str(_ROOT))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:  # exec 包父目录
    sys.path.insert(0, str(_FACTORY_EXEC))

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

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

BEFORE = {"calc.py": "def add(a, b):\n    return a + b\n\n"}
AFTER = {"calc.py": "def add(a, b):\n    return a * b\n\n"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _git_repo(repo: Path, files: dict[str, str]) -> None:
    """真实 git 仓库 (本地身份 + 基线提交; 不依赖全局 user.name/email)。"""
    repo.mkdir(parents=True, exist_ok=True)
    init = _git(repo, "init", "-q", "-b", "main")
    if init.returncode != 0:  # 老 git 退化 init + checkout
        _git(repo, "init", "-q")
        _git(repo, "checkout", "-q", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@local")
    for name, content in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "baseline")


def _git_diff_text(workdir: Path, before: dict[str, str], after: dict[str, str]) -> str:
    """before→after 的真实 git diff (git-applyable 补丁, 不手写 diff 格式)。"""
    src = workdir / "diff-src"
    _git_repo(src, before)
    for name, content in after.items():
        (src / name).write_text(content, encoding="utf-8")
    return _git(src, "diff").stdout


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


def _seed_approved_approval(
    data_dir: Path,
    tmp_path: Path,
    *,
    project: str = "proj-x",
    request_id: str = "EXR-apply-1",
) -> tuple[str, Path]:
    """真实 ApprovalGate 链路: request → approve → git 目标 (apply 就绪)。"""
    store = ExecStore(data_dir / "exec")
    patch_path = tmp_path / "changes.patch"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(_git_diff_text(tmp_path, BEFORE, AFTER), encoding="utf-8")
    target = tmp_path / project
    _git_repo(target, BEFORE)
    request = ExecutionRequest(
        id=request_id, task_id="T-apply", objective="fix calc",
        input={"project_dir": str(target)},
    )
    result = ExecutionResult(
        id=new_id("EXS"), request_id=request.id, status=ExecutionStatus.SUCCESS,
        artifacts=[
            Artifact(id=new_id("ART"), type=ArtifactType.PATCH, task_id="T-apply",
                     path=str(patch_path)),
        ],
    )
    store.save_request(request)
    store.save_result(result)
    record = ApprovalGate(store).request(result)
    ApprovalGate(store).decide(record.id, "approved", decided_by="CEO")
    return record.id, target


class TestApprovalApplyCLI:
    def test_apply_success_applies_patch(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        aid, target = _seed_approved_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", aid, "--project", str(target)]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "patch 已应用" in out
        assert aid in out
        # 真实落地: 目标文件内容已变 (不 stub)
        assert (target / "calc.py").read_text(encoding="utf-8") == AFTER["calc.py"]
        # 状态机: applied 置位
        record = ExecStore(data_dir / "exec").get_approval(aid)
        assert record.applied is True
        assert record.applied_at

    def test_apply_without_project_uses_request_dir(self, tmp_path, capsys):
        """--project 缺省 → 取请求 input.project_dir (薄代理同 exec CLI)。"""
        cli, data_dir = make_cli(tmp_path)
        aid, _target = _seed_approved_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", aid]))
        assert rc == 0
        assert "patch 已应用" in capsys.readouterr().out

    def test_apply_pending_hard_rejected(self, tmp_path, capsys):
        """未批准 (pending) → 硬拒绝, 不绕过 ApprovalGate。"""
        cli, data_dir = make_cli(tmp_path)
        store = ExecStore(data_dir / "exec")
        patch_path = tmp_path / "p.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(_git_diff_text(tmp_path, BEFORE, AFTER), encoding="utf-8")
        request = ExecutionRequest(
            id="EXR-pending", task_id="T", objective="x",
            input={"project_dir": str(tmp_path / "proj-x")},
        )
        result = ExecutionResult(
            id="EXS-pending", request_id=request.id, status=ExecutionStatus.SUCCESS,
            artifacts=[Artifact(id="ART-p", type=ArtifactType.PATCH, task_id="T",
                                path=str(patch_path))],
        )
        store.save_request(request)
        store.save_result(result)
        aid = ApprovalGate(store).request(result).id
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", aid]))
        assert rc != 0
        assert "patch apply requires approved" in capsys.readouterr().err
        assert store.get_approval(aid).applied is False  # 未落地

    def test_apply_rejected_hard_rejected(self, tmp_path, capsys):
        """已拒绝 → 硬拒绝 (终态不可逆)。"""
        cli, data_dir = make_cli(tmp_path)
        aid, _target = _seed_approved_approval(data_dir, tmp_path)
        store = ExecStore(data_dir / "exec")
        record = store.get_approval(aid)
        # 构造 rejected 终态 (直接落库, 复用门禁状态机)
        from exec.models import ApprovalDecision

        store.save_approval(record.model_copy(update={"decision": ApprovalDecision.REJECTED}))
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", aid]))
        assert rc != 0
        assert "patch apply requires approved" in capsys.readouterr().err

    def test_duplicate_apply_rejected(self, tmp_path, capsys):
        """重复应用 → 拒绝 (幂等保护)。"""
        cli, data_dir = make_cli(tmp_path)
        aid, target = _seed_approved_approval(data_dir, tmp_path)
        parser = _cli.build_parser()
        assert cli.run(parser.parse_args(["approval", "apply", aid, "--project", str(target)])) == 0
        rc = cli.run(parser.parse_args(["approval", "apply", aid, "--project", str(target)]))
        assert rc != 0
        assert "already applied" in capsys.readouterr().err

    def test_apply_non_git_target_hard_rejected(self, tmp_path, capsys):
        """非 git 目标 → 硬拒绝 (应用前须可审计, 不静默降级)。"""
        cli, data_dir = make_cli(tmp_path)
        aid, _target = _seed_approved_approval(data_dir, tmp_path)
        plain = tmp_path / "plain-target"
        plain.mkdir()
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", aid, "--project", str(plain)]))
        assert rc != 0
        assert "not a git repository" in capsys.readouterr().err

    def test_apply_not_found(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply", "APR-nope"]))
        assert rc == 7
        assert "approval not found" in capsys.readouterr().err

    def test_apply_missing_id_rc2(self, tmp_path, capsys):
        cli, data_dir = make_cli(tmp_path)
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "apply"]))
        assert rc == 2
        assert "用法: factory approval apply" in capsys.readouterr().err

    def test_apply_registered_in_parser(self):
        parser = _cli.build_parser()
        ns = parser.parse_args(["approval", "apply", "APR-1", "--project", "/tmp/x"])
        assert ns.approval_command == "apply"
        assert ns.approval_id == "APR-1"
        assert ns.project == "/tmp/x"


class TestDecideNextStepHint:
    def test_decide_approve_prints_next_step(self, tmp_path, capsys):
        """approve 成功后打印下一步 (M1 闭环: 演示不再死路)。"""
        cli, data_dir = make_cli(tmp_path)
        store = ExecStore(data_dir / "exec")
        patch_path = tmp_path / "p.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(_git_diff_text(tmp_path, BEFORE, AFTER), encoding="utf-8")
        request = ExecutionRequest(
            id="EXR-hint", task_id="T", objective="x",
            input={"project_dir": str(tmp_path / "proj-x")},
        )
        result = ExecutionResult(
            id="EXS-hint", request_id=request.id, status=ExecutionStatus.SUCCESS,
            artifacts=[Artifact(id="ART-h", type=ArtifactType.PATCH, task_id="T",
                                path=str(patch_path))],
        )
        store.save_request(request)
        store.save_result(result)
        aid = ApprovalGate(store).request(result).id
        parser = _cli.build_parser()
        rc = cli.run(parser.parse_args(["approval", "decide", aid, "approve", "--by", "CEO"]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "已批准" in out
        assert f"factory approval apply {aid} --project <repo> 可应用" in out
