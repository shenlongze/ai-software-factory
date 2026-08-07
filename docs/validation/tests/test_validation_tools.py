"""docs/validation/tests/test_validation_tools.py — Phase A+ 验证工具的 pytest 证据。

覆盖两个变更文件:
- verify_search_fix.py: 正例 (修复后副本 → rc=0) + 反例 (原始缺陷 → rc=1)
- phase_a_validation.py: 模块可导入 + 夹具漂移守卫 (OLD_METHOD 仍匹配源) +
  gen_patch 产出可 apply 的真实 git diff

前置: run-data/projects/markpad-editor 复本已就位 (phase_a_validation.py 建立);
verifier 经 subprocess 在沙箱语义 (cwd=目标目录) 下执行。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

VAL_ROOT = Path(__file__).resolve().parents[1]
TOOLS = VAL_ROOT / "tools"
REPLICA = VAL_ROOT / "run-data" / "projects" / "markpad-editor"
VERIFIER = TOOLS / "verify_search_fix.py"
REL_FILE = "services/search_service.dart"


@pytest.fixture(scope="module")
def driver_module():
    """导入 phase_a_validation 模块 (只读; main 不执行)。"""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import phase_a_validation as mod

    return mod


def _run_verifier(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER)], cwd=str(cwd), capture_output=True, text=True
    )


def test_verifier_passes_on_fixed_replica():
    """修复已应用 (全链路 apply 后) → verifier PASS (rc=0)。"""
    proc = _run_verifier(REPLICA)
    assert proc.returncode == 0, f"verifier rc={proc.returncode}\n{proc.stdout}"
    assert "RESULT: PASS" in proc.stdout


def test_verifier_rejects_buggy_original(tmp_path: Path):
    """原始缺陷版本 (git HEAD, 未修复) → verifier FAIL (rc=1) — 证明检测有效。"""
    src = subprocess.run(
        ["git", "-C", str(REPLICA), "show", f"HEAD:{REL_FILE}"],
        check=True, capture_output=True, text=True,
    ).stdout
    target = tmp_path / REL_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src, encoding="utf-8")
    proc = _run_verifier(tmp_path)
    assert proc.returncode == 1, f"expected rc=1 on buggy original\n{proc.stdout}"
    assert "RESULT: FAIL" in proc.stdout


def test_fixture_drift_guard(driver_module):
    """夹具漂移守卫: OLD_METHOD 必须仍匹配复本**基线**源 (git HEAD — 工作区已
    应用修复, 不能作为比对对象; markpad 源改动会显式暴露)。"""
    baseline = subprocess.run(
        ["git", "-C", str(REPLICA), "show", f"HEAD:{REL_FILE}"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert driver_module.OLD_METHOD in baseline, "夹具漂移: OLD_METHOD 不再匹配基线源"


def test_gen_patch_produces_applyable_diff(driver_module):
    """gen_patch: before→after 真实 git diff, 含修复语义行。"""
    diff = driver_module.gen_patch(
        driver_module.OLD_METHOD, driver_module.NEW_METHOD, rel=REL_FILE
    )
    assert f"a/{REL_FILE}" in diff and f"b/{REL_FILE}" in diff
    assert "+" in diff and "fullContent" in diff


def test_manifest_unchanged_for_untouched_copy(driver_module, tmp_path: Path):
    """manifest: 相同内容 → 相同清单 (零修改比对口径)。"""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for d in (a, b):
        d.mkdir(parents=True, exist_ok=True)
        (d / "f.txt").write_text("same bytes", encoding="utf-8")
    assert driver_module.manifest(a) == driver_module.manifest(b)
