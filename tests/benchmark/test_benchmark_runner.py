"""tests/benchmark/test_benchmark_runner.py — Benchmark 执行框架测试 (不调 LLM)。

覆盖:
- BLOCKED 语义: 无 key → 全部样本 status=BLOCKED + blocked_reason (诚实标注,
  零 Provider 调用 — 不 mock 当能力证明)。
- 真实执行链: FakeProvider 注入确定性回复 → 沙箱 → patch 应用 → verifier
  判定 → 7 指标 (success/token/cost/latency/patch_quality/human_intervention)
  + 五维评分。
- 失败路径: 无 patch 产出 / patch 不可用 → FAILED + error (响亮, 不假成功)。
- 报告聚合: counts/success_rate/total_cost/avg_latency/avg_score。
- patch_quality / estimate_cost / patch_stats / provisional_score 单元。
"""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from exec.benchmark import verifiers
from exec.benchmark.models import (
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkSample,
    FiveDimScore,
    SampleKind,
    SampleStatus,
)
from exec.benchmark.runner import (
    BenchmarkRunner,
    estimate_cost_usd,
    patch_quality_score,
    patch_stats,
    provisional_score,
)
from exec.benchmark.greenfield import GREENFIELD_SAMPLES
from exec.provider import ProviderResponse

# ================================================================ fakes

class FakeProvider:
    """确定性 Provider (注入回复文本; usage 可配; 无网络)。"""

    provider_id = "openai"
    model = "fake-model"

    def __init__(self, content: str, usage: dict | None = None) -> None:
        self._content = content
        self._usage = usage or {}
        self.calls = 0
        self.requests: list = []

    def generate(self, request) -> ProviderResponse:
        self.calls += 1
        self.requests.append(request)
        return ProviderResponse(content=self._content, usage=dict(self._usage))


class RaisingProvider(FakeProvider):
    """不应被调用 (BLOCKED 模式验证: 无 key 时零 Provider 调用)。"""

    def generate(self, request) -> ProviderResponse:  # pragma: no cover
        raise AssertionError("BLOCKED 模式禁止 Provider 调用")


class SequenceProvider:
    """按调用序号依次返回回复 (重试场景: 先空 patch, 后有效 patch)。"""

    provider_id = "openai"
    model = "fake-model"

    def __init__(self, contents: list[str], usage: dict | None = None) -> None:
        self._contents = list(contents)
        self._usage = usage or {}
        self.calls = 0

    def generate(self, request) -> ProviderResponse:
        idx = min(self.calls, len(self._contents) - 1)
        self.calls += 1
        return ProviderResponse(content=self._contents[idx], usage=dict(self._usage))


def make_patch(old: str, new: str, rel: str) -> str:
    """old/new 文件内容 → 统一 diff (difflib; git apply 可应用)。"""
    diff = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="",
    )
    return "<patch>\n" + "\n".join(diff) + "\n</patch>"


def make_new_file_patch(content: str, rel: str) -> str:
    """新建文件 → 统一 diff (--- /dev/null)。"""
    diff = difflib.unified_diff(
        [], content.splitlines(),
        fromfile="/dev/null", tofile=f"b/{rel}", lineterm="",
    )
    return "<patch>\n" + "\n".join(diff) + "\n</patch>"


def write(sandbox: Path, rel: str, content: str) -> None:
    target = sandbox / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


#: 样本 (test 内独立构造, 不依赖 markpad 真实目录)
def sample(sample_id: str, kind: SampleKind, verifier_id: str,
           rels: list[str]) -> BenchmarkSample:
    return BenchmarkSample(id=sample_id, kind=kind, objective="任务描述",
                           requirement="验收标准", project_files=rels,
                           verifier_id=verifier_id)


BUGGY_SEARCH = """\
class SearchService {
  String _replaceQuery = '';

  void replaceCurrent(void Function(String) onContentChanged) {
    onContentChanged(_replaceQuery);
  }
}
"""

FIXED_SEARCH = """\
class SearchService {
  String _replaceQuery = '';

  void replaceCurrent(void Function(String) onContentChanged, String fullContent) {
    final match = RegExp(_replaceQuery).firstMatch(fullContent);
    if (match != null) {
      final display = fullContent.replaceRange(match.start, match.end, _replaceQuery);
      onContentChanged(display);
    }
  }
}
"""


def fake_markpad(root: Path) -> None:
    """最小假项目 (镜像样本 project_files 布局; 沙箱源, 只读)。"""
    write(root, "lib/editor/services/search_service.dart", BUGGY_SEARCH)


def sample_bug() -> BenchmarkSample:
    return sample("BUG-TEST-001", SampleKind.BUG, "verify_bug_001_replace_current",
                  ["lib/editor/services/search_service.dart"])


# ================================================================ BLOCKED

def test_blocked_without_key_records_all_blocked(tmp_path: Path) -> None:
    """无 key → 全部 BLOCKED + blocked_reason (诚实, 零 Provider 调用)。"""
    provider = RaisingProvider("should not be called")
    runner = BenchmarkRunner(
        provider, samples=[sample_bug(), GREENFIELD_SAMPLES[0]],
        project_dir=fake_markpad(tmp_path / "proj"), work_root=tmp_path,
        env={},  # 无任何 key
    )
    report = runner.run_all()
    assert report.blocked is True
    assert "OPENAI_API_KEY" in report.blocked_reason
    assert report.success_rate is None
    assert report.total_cost_usd is None
    assert len(report.results) == 2
    for r in report.results:
        assert r.status is SampleStatus.BLOCKED
        assert r.blocked_reason == report.blocked_reason
        assert r.verifier_passed is None
        assert r.score is None
        assert r.patch_quality is None
    assert provider.calls == 0, "BLOCKED 模式不得调 Provider"


def test_precheck_ok_with_key(tmp_path: Path) -> None:
    """key 就绪 → precheck True; validate_samples 无问题 (假项目就位)。"""
    fake_markpad(tmp_path / "proj")
    runner = BenchmarkRunner(
        FakeProvider("x"), samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    ok, reason = runner.precheck()
    assert ok is True
    assert reason == ""
    assert runner.validate_samples() == []


# ================================================================ 真实执行链

#: 最小可用 todo.py (Greenfield 正例产物; 与 verifier 行为契约一致)
TODO_PY = '''\
#!/usr/bin/env python3
"""todo.py — 命令行待办管理 (Python 3 标准库, 零第三方依赖)."""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "todo.json"


def load():
    if not DATA.exists():
        return []
    return json.loads(DATA.read_text(encoding="utf-8"))


def save(tasks):
    DATA.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id(tasks):
    return max([t["id"] for t in tasks], default=0) + 1


def main(argv):
    cmd = argv[0] if argv else "list"
    tasks = load()
    if cmd == "add":
        task = {"id": next_id(tasks), "text": " ".join(argv[1:]), "done": False}
        tasks.append(task)
        save(tasks)
        print(f"added {task['id']}: {task['text']}")
    elif cmd == "list":
        show = tasks if "--all" in argv else [t for t in tasks if not t["done"]]
        for t in show:
            mark = "[x]" if t["done"] else "[ ]"
            print(f"{t['id']}. {mark} {t['text']}")
    elif cmd == "done":
        tid = int(argv[1])
        for t in tasks:
            if t["id"] == tid:
                t["done"] = True
        save(tasks)
    elif cmd == "remove":
        tid = int(argv[1])
        tasks = [t for t in tasks if t["id"] != tid]
        save(tasks)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
'''


def test_greenfield_success_records_metrics(tmp_path: Path) -> None:
    """Greenfield 全链路: patch → verifier 行为验证通过 → 7 指标 + 五维评分。"""
    provider = FakeProvider(
        make_new_file_patch(TODO_PY, "todo.py"),
        usage={"prompt_tokens": 1200, "completion_tokens": 300,
               "estimated_cost_usd": 0.0004},
    )
    runner = BenchmarkRunner(
        provider, samples=GREENFIELD_SAMPLES,
        project_dir=tmp_path / "unused", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.SUCCESS
    assert result.verifier_passed is True
    assert result.verifier_id == "verify_greenfield_todo_cli"
    # 7 指标
    assert result.usage["prompt_tokens"] == 1200
    assert result.cost_usd == pytest.approx(0.0004)
    assert result.latency_s is not None and result.latency_s >= 0
    assert result.patch_quality == 100  # 可应用 40 + verifier 40 + ≤3 文件 10 + 有产物 10
    assert result.human_intervention == 0
    # 五维评分 (verifier 通过 → Level 2 基线)
    assert result.score is not None
    assert result.score.average == 2.0
    assert provider.calls == 1


def test_bug_fix_success_via_sandbox(tmp_path: Path) -> None:
    """Bug 样本全链路: 假项目副本 → 修复 patch → verifier 通过。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider(
        make_patch(BUGGY_SEARCH, FIXED_SEARCH, "lib/editor/services/search_service.dart"),
        usage={"prompt_tokens": 900, "completion_tokens": 150},
    )
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.SUCCESS
    assert result.verifier_passed is True
    assert result.sample_id == "BUG-TEST-001"
    # usage 无 estimated_cost_usd → cost 诚实 None (不臆造费率)
    assert result.cost_usd is None
    assert result.patch_quality == 100


def test_no_patch_fails_loudly(tmp_path: Path) -> None:
    """Provider 回复无 patch → DeveloperError → FAILED + error (不假成功)。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider("I don't know how to fix this.", usage={})
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.FAILED
    assert "no parseable patch" in result.error
    assert result.verifier_passed is None
    assert result.score is not None and result.score.average == 1.0
    assert result.patch_quality == 0


def test_unappliable_patch_fails(tmp_path: Path) -> None:
    """patch 不可应用 → FAILED (error=patch apply failed) + verifier False。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider(make_patch(BUGGY_SEARCH, FIXED_SEARCH,
                                       "lib/editor/services/search_service.dart")
                            .replace("class SearchService", "class Renamed"))
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.FAILED
    assert "patch apply failed" in result.error
    assert result.verifier_passed is False
    assert result.patch_quality == 10  # 只有 has_patch 10 分


def test_runs_repeat_and_unique_result_ids(tmp_path: Path) -> None:
    """runs=2 → 每样本 2 条结果 (唯一 result id)。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider(
        make_patch(BUGGY_SEARCH, FIXED_SEARCH, "lib/editor/services/search_service.dart"))
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()], runs=2,
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    report = runner.run_all()
    assert len(report.results) == 2
    ids = [r.id for r in report.results]
    assert len(set(ids)) == 2
    assert report.success_rate == 1.0


# ================================================================ 重试语义

def test_empty_patch_retries_once_then_succeeds(tmp_path: Path) -> None:
    """空 patch (模型随机性) → 重试 1 次 → 有效 patch → SUCCESS (调用 2 次)。"""
    fake_markpad(tmp_path / "proj")
    provider = SequenceProvider([
        "need to think\n<patch>\n</patch>",  # 空 patch 标签
        make_patch(BUGGY_SEARCH, FIXED_SEARCH, "lib/editor/services/search_service.dart"),
    ], usage={"prompt_tokens": 10, "completion_tokens": 5,
              "estimated_cost_usd": 0.0001})
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.SUCCESS
    assert result.verifier_passed is True
    assert provider.calls == 2, "空 patch 应重试 1 次"
    # 成本累计两次调用 (诚实总花费)
    assert result.cost_usd == pytest.approx(0.0002)


def test_empty_patch_both_attempts_fail(tmp_path: Path) -> None:
    """两次都空 patch → FAILED + error 标注 (after 1 retry)。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider("still thinking\n<patch>\n</patch>")
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.FAILED
    assert "empty patch" in result.error
    assert "after 1 retry" in result.error
    assert result.verifier_passed is None
    assert provider.calls == 2


def test_empty_content_retries_then_fails(tmp_path: Path) -> None:
    """空内容 (reasoning 模型空 content) → 重试 → 仍空 → FAILED 诚实标注。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider("")
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.FAILED
    assert "empty content" in result.error
    assert "after 1 retry" in result.error
    assert provider.calls == 2


def test_unappliable_patch_does_not_retry(tmp_path: Path) -> None:
    """patch 可解析但不可应用 → 不重试 (真实能力判定, 重试是放水)。"""
    fake_markpad(tmp_path / "proj")
    provider = FakeProvider(make_patch(BUGGY_SEARCH, FIXED_SEARCH,
                                       "lib/editor/services/search_service.dart")
                            .replace("class SearchService", "class Renamed"))
    runner = BenchmarkRunner(
        provider, samples=[sample_bug()],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.FAILED
    assert "patch apply failed" in result.error
    assert "after 1 retry" not in result.error
    assert provider.calls == 1, "不可应用 patch 不重试"


def test_source_files_embedded_in_prompt(tmp_path: Path) -> None:
    """样本 source_files → 沙箱内文件内容内联进 Provider 提示词 (模型唯一代码来源)。"""
    fake_markpad(tmp_path / "proj")
    sb = sample("BUG-TEST-002", SampleKind.BUG, "verify_bug_001_replace_current",
                ["lib/editor/services/search_service.dart"])
    sb.source_files = ["lib/editor/services/search_service.dart"]
    provider = FakeProvider(
        make_patch(BUGGY_SEARCH, FIXED_SEARCH, "lib/editor/services/search_service.dart"))
    runner = BenchmarkRunner(
        provider, samples=[sb],
        project_dir=tmp_path / "proj", work_root=tmp_path,
        env={"OPENAI_API_KEY": "sk-test"},
    )
    result = runner.run_all().results[0]
    assert result.status is SampleStatus.SUCCESS
    prompt = provider.requests[0].task_context
    assert "## Relevant source files" in prompt
    assert "class SearchService" in prompt  # 缺陷现场代码已内联
    assert "verify_bug_001_replace_current" not in prompt  # verifier id 不进 prompt


# ================================================================ 报告聚合

def test_report_aggregation(tmp_path: Path) -> None:
    """混合结果报告: counts / success_rate / cost / latency / avg_score。"""
    ok_result = BenchmarkResult(
        sample_id="A", kind=SampleKind.BUG, status=SampleStatus.SUCCESS,
        verifier_passed=True, cost_usd=0.001, latency_s=2.5,
        patch_quality=90, score=FiveDimScore(understanding=2, analysis=2,
                                             implementation=2, validation=2,
                                             communication=2),
        human_intervention=0,
    )
    bad_result = BenchmarkResult(
        sample_id="B", kind=SampleKind.FEATURE, status=SampleStatus.FAILED,
        verifier_passed=False, cost_usd=0.002, latency_s=4.0,
        patch_quality=30, score=FiveDimScore(understanding=1, analysis=1,
                                             implementation=1, validation=1,
                                             communication=1),
        human_intervention=1,
    )
    report = BenchmarkReport(results=[ok_result, bad_result])
    assert report.counts == {"success": 1, "failed": 1}
    assert report.success_rate == 0.5
    assert report.total_cost_usd == 0.003
    assert report.avg_latency_s == 3.25
    assert report.avg_score == 1.5
    assert len(report.by_kind(SampleKind.BUG)) == 1
    d = report.to_dict()
    assert d["counts"] == {"success": 1, "failed": 1}
    assert d["success_rate"] == 0.5
    assert d["results"][0]["kind"] == "bug"


# ================================================================ 单元

def test_estimate_cost_usd() -> None:
    assert estimate_cost_usd({}) is None
    assert estimate_cost_usd({"estimated_cost_usd": 0.00012}) == pytest.approx(0.00012)
    assert estimate_cost_usd({"estimated_cost_usd": "bad"}) is None
    assert estimate_cost_usd(None) is None


def test_patch_quality_score() -> None:
    assert patch_quality_score(applied=True, verifier_passed=True,
                               files_touched=1, has_patch=True) == 100
    assert patch_quality_score(applied=True, verifier_passed=True,
                               files_touched=5, has_patch=True) == 95
    assert patch_quality_score(applied=True, verifier_passed=True,
                               files_touched=8, has_patch=True) == 90
    assert patch_quality_score(applied=True, verifier_passed=False,
                               files_touched=1, has_patch=True) == 60
    assert patch_quality_score(applied=False, verifier_passed=False,
                               files_touched=0, has_patch=False) == 0
    assert patch_quality_score(applied=True, verifier_passed=True,
                               files_touched=1, has_patch=False) == 90


def test_patch_stats() -> None:
    diff = (
        "diff --git a/lib/a.dart b/lib/a.dart\n"
        "--- a/lib/a.dart\n+++ b/lib/a.dart\n"
        "@@ -1,2 +1,3 @@\n"
        " old line\n+added line\n-removed line\n"
        "diff --git a/lib/b.dart b/lib/b.dart\n"
        "--- a/lib/b.dart\n+++ b/lib/b.dart\n"
        "@@ -1 +1 @@\n+new\n"
    )
    stats = patch_stats(diff)
    assert stats["files"] == 2
    assert stats["insertions"] == 2
    assert stats["deletions"] == 1


def test_provisional_score() -> None:
    passed = provisional_score(True)
    assert passed.average == 2.0
    assert passed.understanding == 2
    failed = provisional_score(False)
    assert failed.average == 1.0
    # 越界 clamp (Level 1-3)
    assert FiveDimScore(implementation=9).implementation == 3


def test_runner_cli_check_exits_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    """CLI --check (无 key): 预检输出 BLOCKED, 退出码 0 (诚实标注不假装)。"""
    from exec.benchmark.runner import main

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = main(["--check", "--provider", "openai"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "BLOCKED" in out
    assert "OPENAI_API_KEY" in out
