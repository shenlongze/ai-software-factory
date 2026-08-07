"""tests/benchmark/test_benchmark_samples.py — 样本集完整性校验 (不调 LLM)。

覆盖:
- 配比: 5 Bug + 3 Feature + 1 Greenfield = 9 样本, 唯一 id。
- verifier 注册: 每个样本 verifier_id 已在 verifiers 注册表。
- 禁人工答案: prompt_text() 不含 fix_hint; fix_hint 不进任务上下文。
- greenfield: 空 project_files + 无 fix_hint (从零构建)。
- 项目文件存在性: 样本 project_files 在 markpad 项目目录存在
  (skipif 守卫 — 项目目录缺失时跳过, 不假装)。
- runner.validate_samples(): 完整样本集 → 无问题; 坏样本 → 响亮问题列表。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.benchmark import verifiers
from exec.benchmark.models import SampleKind
from exec.benchmark.runner import DEFAULT_PROJECT_DIR, BenchmarkRunner
from exec.benchmark.samples import ALL_SAMPLES, KIND_COUNTS, SAMPLES_BY_ID

#: markpad 项目目录 (样本 project_files 存在性检查; 缺失 → 跳过)
MARKPAD_DIR = Path(DEFAULT_PROJECT_DIR)


def test_sample_set_ratio_and_unique_ids() -> None:
    """样本配比 5/3/1, id 全局唯一, SAMPLES_BY_ID 索引完整。"""
    ids = [s.id for s in ALL_SAMPLES]
    assert len(ids) == 9
    assert len(set(ids)) == 9, "样本 id 必须唯一"

    from collections import Counter

    kinds = Counter(s.kind for s in ALL_SAMPLES)
    assert kinds[SampleKind.BUG] == 5
    assert kinds[SampleKind.FEATURE] == 3
    assert kinds[SampleKind.GREENFIELD] == 1
    assert KIND_COUNTS == {"bug": 5, "feature": 3, "greenfield": 1}
    assert set(SAMPLES_BY_ID) == set(ids)


def test_all_samples_verifiers_registered() -> None:
    """每个样本的 verifier_id 必须已注册 (样本不可执行 = 定义错误)。"""
    missing = [s.id for s in ALL_SAMPLES if verifiers.get(s.verifier_id) is None]
    assert missing == [], f"verifier 未注册: {missing}"


def test_objective_never_leaks_fix_hint() -> None:
    """禁人工答案: 任务描述/验收标准/提示词不含 fix_hint 内容。"""
    for s in ALL_SAMPLES:
        if not s.fix_hint:
            continue
        # fix_hint 关键词绝不出现于 objective/requirement (提示词素材)
        leak_tokens = [w for w in s.fix_hint.split() if len(w) > 3]
        assert not any(t in s.objective for t in leak_tokens), \
            f"{s.id}: objective 泄露 fix_hint"
        assert not any(t in s.requirement for t in leak_tokens), \
            f"{s.id}: requirement 泄露 fix_hint"
        # prompt_text (Agent 实际看到的) 不含 fix_hint 原文
        assert s.fix_hint not in s.prompt_text(), f"{s.id}: prompt 泄露 fix_hint"


def test_greenfield_is_clean_slate() -> None:
    """Greenfield 样本: 空 project_files + 无 fix_hint (从零构建, 无隐藏答案)。"""
    g = SAMPLES_BY_ID["GREENFIELD-001"]
    assert g.kind is SampleKind.GREENFIELD
    assert g.project_files == []
    assert g.fix_hint == ""
    assert "todo.py" in g.objective


def test_prompt_text_shape() -> None:
    """prompt_text(): objective + 验收标准, 不含 fix_hint / project_files。"""
    s = SAMPLES_BY_ID["BUG-MKP-001"]
    text = s.prompt_text()
    assert "replaceCurrent" in text  # 现象描述
    assert "验收标准" in text
    assert s.fix_hint not in text
    assert "fix_hint" not in text


@pytest.mark.skipif(
    not MARKPAD_DIR.is_dir(),
    reason=f"markpad 项目目录缺失: {MARKPAD_DIR} (样本存在性检查跳过)",
)
def test_project_files_exist_in_markpad() -> None:
    """样本 project_files 必须在 markpad 项目目录存在 (真实 Bug/Feature 来源)。"""
    missing = []
    for s in ALL_SAMPLES:
        if s.kind is SampleKind.GREENFIELD:
            continue
        for rel in s.project_files:
            if not (MARKPAD_DIR / rel).is_file():
                missing.append(f"{s.id}: {rel}")
    assert missing == [], f"项目文件缺失: {missing}"


@pytest.mark.skipif(
    not MARKPAD_DIR.is_dir(),
    reason=f"markpad 项目目录缺失: {MARKPAD_DIR} (缺陷存在性检查跳过)",
)
def test_bug_defects_exist_in_markpad() -> None:
    """反模式断言: 5 个 Bug 的缺陷代码必须仍存在于 markpad 生产目录 (只读核验)。

    反向保障: verifier 反例有效 + 生产目录确实带病 → 样本可执行、修复有对象。
    """
    checks = {
        "BUG-MKP-001": "lib/editor/services/search_service.dart",
        "BUG-MKP-002": "lib/editor/controllers/file_controller.dart",
        "BUG-MKP-003": "lib/editor/services/encoding_service.dart",
        "BUG-MKP-004": "lib/editor/undo/document_snapshot.dart",
        "BUG-MKP-005": "lib/core/document/serializer.dart",
    }
    for sid, rel in checks.items():
        src = (MARKPAD_DIR / rel).read_text(encoding="utf-8", errors="replace")
        if sid == "BUG-MKP-001":
            assert "onContentChanged(_replaceQuery)" in src
        elif sid == "BUG-MKP-002":
            assert "switchToTab" in src and "_readOnly = false;" in src
        elif sid == "BUG-MKP-003":
            assert "bytes.length < 4" in src
            assert "0xFF && bytes[1] == 0xFE" in src
        elif sid == "BUG-MKP-004":
            assert "TableBlock" in src and "aligns" not in src
        elif sid == "BUG-MKP-005":
            assert "${i + 1}. " in src


def test_validate_samples_ok_with_real_project(tmp_path: Path) -> None:
    """完整样本集校验: 项目目录就位 → 无问题; 目录缺失 → 响亮问题 (不静默)。"""
    class _FakeProvider:
        provider_id = "openai"

    # 项目目录缺失 → 文件存在性问题响亮暴露
    problems = BenchmarkRunner(_FakeProvider(), project_dir=tmp_path / "missing").validate_samples()
    assert problems, "项目目录缺失时 validate_samples 必须报文件缺失"
    assert any("项目文件缺失" in p for p in problems)

    if MARKPAD_DIR.is_dir():
        ok = BenchmarkRunner(_FakeProvider(), project_dir=MARKPAD_DIR).validate_samples()
        assert ok == [], f"完整样本集不应有问题: {ok}"


def test_validate_samples_catches_bad_sample(tmp_path: Path) -> None:
    """坏样本 (verifier 未注册 / 重复 id / 空 objective) → validate_samples 响亮。"""
    from exec.benchmark.models import BenchmarkSample

    class _FakeProvider:
        provider_id = "openai"

    bad = [
        BenchmarkSample(id="X-1", kind=SampleKind.BUG, objective="ok",
                        verifier_id="not_registered_verifier"),
        BenchmarkSample(id="X-1", kind=SampleKind.BUG, objective="ok",
                        verifier_id="verify_bug_001_replace_current"),
        BenchmarkSample(id="X-3", kind=SampleKind.BUG, objective="   ",
                        verifier_id="verify_bug_001_replace_current"),
    ]
    problems = BenchmarkRunner(_FakeProvider(), samples=bad,
                               project_dir=tmp_path).validate_samples()
    joined = "; ".join(problems)
    assert "duplicate sample id" in joined
    assert "verifier 未注册" in joined
    assert "objective 为空" in joined
