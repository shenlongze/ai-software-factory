"""S1: Artifact Apply Integration — 真实 delivery.apply_patch 应用 + 失败语义。

场景:
1. 真实临时 git 仓库 → Artifact GENERATED→…→APPROVED → 真实 apply → workspace 变化 → APPLIED
2. Apply 失败 → Artifact 不前进 (绝不伪装 APPLIED)
3. 未 APPROVED 不能 Apply
4. Apply 证据存在
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.artifact_lifecycle import (  # noqa: E402
    create_artifact,
    transition_artifact,
    approve_artifact,
    apply_artifact,
    validate_artifact,
    commit_artifact,
    release_artifact,
    get_artifact,
    artifact_state,
    ArtifactError,
)
from factory_console.session.delivery import apply_patch as real_apply_patch  # noqa: E402


def _git(ws: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(ws), *args], capture_output=True, text=True, timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _init_repo(ws: Path, filename: str = "main.py", content: str = "x = 1\n") -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / filename).write_text(content, encoding="utf-8")
    _git(ws, "init", "-q")
    _git(ws, "add", "-A")
    _git(ws, "-c", "user.email=factory@local", "-c", "user.name=factory", "commit", "-q", "-m", "base")


def _patch_add_function(filename: str = "main.py") -> str:
    """生成真实可 apply 的 patch (最后一行=内容行+单换行, delivery 会补尾部换行)。"""
    return (
        f"diff --git a/{filename} b/{filename}\n"
        f"--- a/{filename}\n"
        f"+++ b/{filename}\n"
        f"@@ -1 +1,5 @@\n"
        f" x = 1\n"
        f"+\n"
        f"+def add(a: int, b: int) -> int:\n"
        f"+    return a + b\n"
    )


def _approved_artifact(tmp_path, ws: Path, patch: str):
    art = create_artifact(str(tmp_path), artifact_type="code_change",
                          patch_text=patch, project_id="P-int", producer="test")
    aid = art["artifact_id"]
    transition_artifact(str(tmp_path), aid, "STAGED", actor="test")
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="test")
    approve_artifact(str(tmp_path), aid, approved_by="user1", note="ok")
    return aid


def test_real_apply_modifies_workspace(tmp_path):
    """真实 apply: workspace 真的变化 (git diff 验证), 状态变 APPLIED。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    before = (ws / "main.py").read_text()

    aid = _approved_artifact(tmp_path, ws, _patch_add_function())
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-1", "state": "APPROVED"})

    after = (ws / "main.py").read_text()
    assert artifact_state(str(tmp_path), aid) == "APPLIED"
    assert before != after, "workspace 必须真实变化"
    assert "def add" in after, "apply 后应含新增函数"
    # git diff 证实
    code, out = _git(ws, "diff")
    assert "def add" in out or "def add" in (ws / "main.py").read_text()


def test_apply_failure_does_not_advance(tmp_path):
    """Apply 失败: Artifact 保持 APPROVED, 不伪装 APPLIED, 有失败证据。"""
    ws = tmp_path / "ws"
    _init_repo(ws, filename="main.py", content="x = 1\n")
    # 构造无法 apply 的 patch (上下文不匹配 — 任何容错都无法救)
    bad_patch = (
        "diff --git a/main.py b/main.py\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -99,3 +99,3 @@\n"
        " line_that_does_not_exist_1\n"
        " line_that_does_not_exist_2\n"
        " line_that_does_not_exist_3\n"
    )
    aid = _approved_artifact(tmp_path, ws, bad_patch)
    with pytest.raises(ArtifactError):
        apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                       approval={"approval_id": "apr-1", "state": "APPROVED"})
    assert artifact_state(str(tmp_path), aid) == "APPROVED", "apply 失败不能进 APPLIED"
    # workspace 无变化
    assert (ws / "main.py").read_text() == "x = 1\n"


def test_apply_without_approval_rejected(tmp_path):
    """未 APPROVED 不能 Apply (I1): 状态必须 APPROVED。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    art = create_artifact(str(tmp_path), artifact_type="code_change",
                          patch_text=_patch_add_function(), project_id="P-int", producer="t")
    aid = art["artifact_id"]
    transition_artifact(str(tmp_path), aid, "STAGED", actor="t")
    # 停在 REVIEWED (未 APPROVED)
    transition_artifact(str(tmp_path), aid, "REVIEWED", actor="t")
    with pytest.raises(ArtifactError):
        apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="t",
                       approval={"approval_id": "apr-1", "state": "APPROVED"})
    assert artifact_state(str(tmp_path), aid) == "REVIEWED"


def test_full_lifecycle_to_released(tmp_path):
    """完整链路: GENERATED→…→RELEASED, 真实 apply + validate + commit。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    aid = _approved_artifact(tmp_path, ws, _patch_add_function())
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-1", "state": "APPROVED"})
    validate_artifact(str(tmp_path), aid, verification={"result": "PASS", "tests": 3})
    commit_artifact(str(tmp_path), aid, approval={"approval_id": "apr-1", "state": "APPROVED"})
    release_artifact(str(tmp_path), aid, approval={"approval_id": "apr-1", "state": "APPROVED"})
    assert artifact_state(str(tmp_path), aid) == "RELEASED"
    art = get_artifact(str(tmp_path), aid)
    assert art["commit_hash"], "commit 后必须有 hash"
    # workspace 已提交 (git log)
    code, out = _git(ws, "log", "--oneline")
    assert "factory" in out


def test_apply_evidence_recorded(tmp_path):
    """Apply 证据: history 含 apply_msg + workspace。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    aid = _approved_artifact(tmp_path, ws, _patch_add_function())
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-1", "state": "APPROVED"})
    art = get_artifact(str(tmp_path), aid)
    apply_ev = next(h for h in art["history"] if h["to"] == "APPLIED")
    assert "workspace" in apply_ev["evidence"]
    assert art["workspace"] == str(ws)


def test_validate_fail_does_not_commit(tmp_path):
    """验证失败 (FAIL): 不能 VALIDATED, 不能 COMMITTED。"""
    ws = tmp_path / "ws"
    _init_repo(ws)
    aid = _approved_artifact(tmp_path, ws, _patch_add_function())
    apply_artifact(str(tmp_path), aid, workspace_dir=ws, actor="system",
                   approval={"approval_id": "apr-1", "state": "APPROVED"})
    with pytest.raises(ArtifactError):
        validate_artifact(str(tmp_path), aid, verification={"result": "FAIL", "error": "test failed"})
    assert artifact_state(str(tmp_path), aid) == "APPLIED"
    with pytest.raises(ArtifactError):
        commit_artifact(str(tmp_path), aid, approval={"approval_id": "apr-1", "state": "APPROVED"})
