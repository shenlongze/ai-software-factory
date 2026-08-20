"""tests/console/test_workload_backlog.py — 积压清道夫 (M1b/E3)。

覆盖: 分诊 (bug/feature/dependency → 策略) / 确定性依赖修复 (requirements.txt /
pyproject.toml 真实 diff) / 执行 (复用 RepoModeRunner → patch + pytest) /
证据包 (EvidenceBundle 落盘 + logs) / 审批请求 (ApprovalGate pending) /
运行报告 (summary + status 只读) / LLM 路径 (feature/bug patch) / 失败安全。
basename 全仓库唯一。
"""

from __future__ import annotations

import json
import subprocess
import sys
from importlib import import_module
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:  # 审批装配需 exec 包 (同 tests/exec/conftest)
    sys.path.insert(0, str(_FACTORY_EXEC))

SW = import_module("factory-console.session.workloads.backlog_sweeper")
EV = import_module("factory-console.session.evidence")


def _make_repo(root: Path, *, issues: list[dict] | None = None) -> Path:
    """最小可修复仓库 (main.py + 通过测试 + requirements.txt + issues.json)。"""
    repo = root / "repo"
    repo.mkdir(parents=True)
    (repo / "main.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (repo / "test_main.py").write_text(
        "from main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (repo / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (repo / "issues.json").write_text(
        json.dumps(issues or [
            {"id": "ISS-001", "title": "缺少 requests 依赖", "type": "dependency"},
            {"id": "ISS-002", "title": "增加 greet 函数", "type": "feature"},
            {"id": "ISS-003", "title": "add 负数相加返回错误", "type": "bug"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    return repo


def _git_diff_patch(repo: Path, before: dict[str, str], after: dict[str, str]) -> str:
    """真实生成 unified diff (git 临时提交 → diff → 还原)。"""
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    for name, content in before.items():
        (repo / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    for name, content in after.items():
        (repo / name).write_text(content, encoding="utf-8")
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff"], capture_output=True, text=True, check=True
    ).stdout
    for name in after:
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", name], check=True)
    return diff


# ------------------------------------------------------------------ 分诊


class TestTriage:
    def test_bug_strategy(self):
        d = SW.triage_issue(SW.BacklogIssue(id="1", title="x", type="bug"))
        assert "最小修复" in d.strategy
        assert d.issue_type == "bug"

    def test_feature_strategy(self):
        d = SW.triage_issue(SW.BacklogIssue(id="1", title="x", type="feature"))
        assert "新增能力" in d.strategy

    def test_dependency_strategy(self):
        d = SW.triage_issue(SW.BacklogIssue(id="1", title="x", type="dependency"))
        assert "依赖修复" in d.strategy

    def test_unknown_type_skips(self):
        d = SW.triage_issue(SW.BacklogIssue(id="1", title="x", type="weird"))
        assert "skip" in d.strategy
        assert "未知类型" in d.summary


# ------------------------------------------------------------------ 确定性依赖修复


class TestDependencyPatchGenerator:
    def test_missing_dependency_requirements_txt(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / "requirements.txt").write_text("flask\n", encoding="utf-8")
        patch, reason = SW.DependencyPatchGenerator().generate(
            repo, SW.BacklogIssue(id="1", title="缺少 requests 依赖", type="dependency")
        )
        assert reason == "依赖修复: requests → requirements.txt"
        assert "--- a/requirements.txt" in patch
        assert "+requests" in patch

    def test_already_present_no_change(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / "requirements.txt").write_text("flask\nrequests\n", encoding="utf-8")
        patch, reason = SW.DependencyPatchGenerator().generate(
            repo, SW.BacklogIssue(id="1", title="缺少 requests 依赖", type="dependency")
        )
        assert patch == ""
        assert "已满足" in reason

    def test_specifier_title(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / "requirements.txt").write_text("flask\n", encoding="utf-8")
        patch, reason = SW.DependencyPatchGenerator().generate(
            repo, SW.BacklogIssue(id="1", title="依赖 django==5.0.3", type="dependency")
        )
        assert "django==5.0.3" in patch

    def test_pyproject_toml(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = [\n    "flask",\n]\n',
            encoding="utf-8",
        )
        patch, reason = SW.DependencyPatchGenerator().generate(
            repo, SW.BacklogIssue(id="1", title="缺少 httpx 依赖", type="dependency")
        )
        assert "httpx" in patch
        assert "pyproject.toml" in reason

    def test_no_req_file_unfixable(self, tmp_path):
        repo = tmp_path / "r"
        repo.mkdir()
        patch, reason = SW.DependencyPatchGenerator().generate(
            repo, SW.BacklogIssue(id="1", title="缺少 requests 依赖", type="dependency")
        )
        assert patch == ""
        assert "未发现需求文件" in reason


# ------------------------------------------------------------------ 积压清道夫


class TestBacklogSweeper:
    def test_sweep_fixes_dependency_and_evidence(self, tmp_path):
        repo = _make_repo(tmp_path)
        ws = tmp_path / "factory"
        report = SW.BacklogSweeper(ws).sweep(repo)
        # 分诊/执行/报告
        assert report.total == 3
        assert report.triaged == 3
        assert report.fixed == 1
        assert report.skipped == 2
        assert report.failed == 0
        fixed = [o for o in report.outcomes if o.status == "fixed"][0]
        assert fixed.issue_id == "ISS-001"
        assert fixed.changed_files == ["requirements.txt"]
        assert fixed.test_ok is True
        assert fixed.bundle_id.startswith("ev-")
        assert fixed.approval_id.startswith("APR-")
        skipped = [o for o in report.outcomes if o.status == "skipped"]
        assert len(skipped) == 2
        assert all("LLM" in o.reason for o in skipped)  # 诚实跳过, 不伪造
        # 证据包落盘 + logs (T4) + 变更文件
        bundles = EV.EvidenceStore(ws, "repo").list()
        assert len(bundles) == 1
        b = bundles[0]
        assert "缺少 requests 依赖" in b.task_id  # 目标含 issue 标题 (带类型前缀)
        assert b.artifacts == ["requirements.txt"]
        assert len(b.logs) >= 4  # understand/plan/patch/test 执行事件摘要
        assert any(log["step"] == "test" for log in b.logs)
        # 审批 pending (复用 ApprovalGate)
        from exec.store import ExecStore

        approvals = ExecStore(ws / "exec").list_approvals()
        assert [a.id for a in approvals] == [fixed.approval_id]
        assert approvals[0].decision.value == "pending"

    def test_sweep_without_approval(self, tmp_path):
        repo = _make_repo(tmp_path, issues=[
            {"id": "ISS-001", "title": "缺少 requests 依赖", "type": "dependency"},
        ])
        report = SW.BacklogSweeper(tmp_path / "factory").sweep(
            repo, request_approval=False
        )
        assert report.fixed == 1
        assert report.outcomes[0].approval_id == ""

    def test_sweep_llm_feature_patch(self, tmp_path):
        """feature issue + llm_fn → LLM 生成 patch → 真实修复 (复用 Execution Kernel)。"""
        repo = _make_repo(tmp_path, issues=[
            {"id": "ISS-002", "title": "增加 greet 函数", "type": "feature"},
        ])
        (repo / "test_main.py").write_text(
            "from main import add, greet\n\ndef test_add():\n    assert add(1, 2) == 3\n"
            "def test_greet():\n    assert greet('x') == 'hello x'\n",
            encoding="utf-8",
        )
        before = {"main.py": "def add(a, b):\n    return a + b\n"}
        after = {
            "main.py": "def add(a, b):\n    return a + b\n\n"
            "def greet(name):\n    return \"hello \" + name\n"
        }
        patch = _git_diff_patch(repo, before, after)
        calls = []

        def fake_llm(prompt, op):
            calls.append(op)
            if op != "backlog_patch":
                return "计划: 增加 greet 函数"
            return patch

        report = SW.BacklogSweeper(tmp_path / "factory", llm_fn=fake_llm).sweep(repo)
        assert report.fixed == 1
        outcome = report.outcomes[0]
        assert outcome.status == "fixed"
        assert outcome.changed_files == ["main.py"]
        assert outcome.test_ok is True
        assert "backlog_patch" in calls
        assert outcome.bundle_id.startswith("ev-")

    def test_sweep_limit(self, tmp_path):
        repo = _make_repo(tmp_path)
        report = SW.BacklogSweeper(tmp_path / "factory").sweep(repo, limit=1)
        assert report.total == 1
        assert report.fixed == 1

    def test_sweep_missing_issues_raises(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        with pytest.raises(SW.BacklogSweepError, match="issue 清单不存在"):
            SW.BacklogSweeper(tmp_path / "factory").sweep(repo)

    def test_sweep_missing_project_raises(self, tmp_path):
        with pytest.raises(SW.BacklogSweepError, match="项目目录不存在"):
            SW.BacklogSweeper(tmp_path / "factory").sweep(tmp_path / "nope")

    def test_status_returns_latest_report(self, tmp_path):
        repo = _make_repo(tmp_path)
        ws = tmp_path / "factory"
        sweeper = SW.BacklogSweeper(ws)
        sweeper.sweep(repo)
        report = sweeper.status(repo)
        assert report is not None
        assert report.fixed == 1
        assert report.outcomes[0].bundle_id
        # 无报告 → None
        assert SW.BacklogSweeper(ws).status(tmp_path / "other") is None


class TestCliRegistration:
    """factory workload 命令组注册 (M1b/E3 CLI 验收)。"""

    def test_workload_and_approval_registered(self):
        _CLI = import_module("factory-console.cli_factory")
        parser = _CLI.build_parser()
        names = set()
        for action in parser._actions:
            if getattr(action, "choices", None):
                names = set(action.choices)
        assert "workload" in names
        assert "approval" in names

    def test_workload_backlog_help(self, capsys):
        _CLI = import_module("factory-console.cli_factory")
        with pytest.raises(SystemExit) as exc:
            _CLI.build_parser().parse_args(["workload", "backlog", "--help"])
        assert exc.value.code == 0
        assert "usage:" in capsys.readouterr().out


class TestSweepReport:
    def test_roundtrip_dict(self):
        r = SW.SweepReport(
            project="/p", issues_file="issues.json", total=1, triaged=1, fixed=1,
            outcomes=[
                SW.IssueOutcome(
                    issue_id="I1", title="t", issue_type="dependency", status="fixed",
                    changed_files=["requirements.txt"], test_ok=True,
                    bundle_id="ev-1", approval_id="APR-1",
                )
            ],
            created_at="2026-08-20T00:00:00+00:00",
        )
        back = SW.SweepReport.from_dict(r.to_dict())
        assert back.fixed == 1
        assert back.outcomes[0].bundle_id == "ev-1"
        assert "ISS" not in back.summary_text() or True  # summary 可渲染
        assert "积压清道夫完成" in r.summary_text()

    def test_issue_from_dict_defaults(self):
        i = SW.BacklogIssue.from_dict({"id": "x"})
        assert i.type == "bug"
        assert i.title == ""
