"""test_session_repo_mode.py — 存量仓库模式 (M1 内核切片)。

覆盖: 理解→计划→patch 应用→测试通过 / 无 patch 只理解计划 / 仓库缺失 /
llm_fn 计划注入。basename 全仓库唯一。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from importlib import import_module

RM = import_module("factory-console.session.repo_mode")


def _make_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "main.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "test_main.py").write_text(
        "from main import add, greet\n\ndef test_add():\n    assert add(1,2) == 3\n\n"
        "def test_greet():\n    assert greet('x') == 'hello x'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def _greet_patch(repo: Path) -> str:
    (repo / "main.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef greet(name):\n    return \"hello \" + name\n",
        encoding="utf-8",
    )
    patch = subprocess.run(
        ["git", "-C", str(repo), "diff"], capture_output=True, text=True, check=True
    ).stdout
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--", "main.py"], check=True)
    return patch


class TestRepoMode:
    def test_apply_patch_and_test_pass(self, tmp_path):
        repo = _make_repo(tmp_path)
        patch = _greet_patch(repo)
        result = RM.RepoModeRunner().run(repo, "加一个 hello 函数", patch_text=patch)
        assert result.error == ""
        assert result.patch_applied is True
        assert "main.py" in result.changed_files
        assert result.test_ok is True
        assert result.understanding.get("stage")  # 理解真实
        assert "已提供 patch" in result.plan_reason

    def test_no_patch_only_understand_plan(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = RM.RepoModeRunner().run(repo, "加导出")
        assert result.patch_applied is False
        assert result.test_ok is None
        assert "未提供 patch" in result.plan_reason

    def test_missing_repo_error(self, tmp_path):
        result = RM.RepoModeRunner().run(tmp_path / "nope", "x")
        assert "仓库不存在" in result.error

    def test_llm_fn_used_for_plan(self, tmp_path):
        repo = _make_repo(tmp_path)
        calls = []

        def fake_llm(prompt, op):
            calls.append(op)
            return "计划: 改 main.py 并验证"

        result = RM.RepoModeRunner(llm_fn=fake_llm).run(repo, "加 hello", patch_text="")
        assert calls == ["repo_plan"]
        assert "改 main.py" in result.plan_reason

    def test_llm_fn_failure_falls_back(self, tmp_path):
        repo = _make_repo(tmp_path)

        def boom(prompt, op):
            raise RuntimeError("llm down")

        result = RM.RepoModeRunner(llm_fn=boom).run(repo, "x", patch_text="")
        assert "LLM 计划失败" in result.plan_reason
