"""tests/exec/test_exec_tester.py — Tester Agent 执行 (Unit, S7-004)。

覆盖 (任务清单: Tester prompt/execution_kind/bug_report 契约/failure analysis
结构化 — exec 侧执行链):
- BugReport 模型: to_dict 契约字段 / from_dict 宽容解析 (severity 缺省,
  未知字段忽略) / 缺核心字段响亮拒绝
- run_tests: 确定性测试执行 (真实 pytest, 不靠 LLM 猜) — 通过/失败/计数解析
  / 缺 project_dir 响亮 / 目录缺失不崩溃
- analyze_failures: mock provider 结构化 bug report / markdown 围栏容错 /
  provider 错误 / 垃圾输出 / 空列表 / 无 provider — 全响亮拒绝
- test_and_report: 通过 → bugs=[] 零 LLM 调用; 失败 → 结构化 bugs + repair
  task; repair task 形状
- Workflow 接入: make_workflow_executor 路由 (未映射角色响亮) /
  build_tester_executor 多产物契约 (test + bug_report) + project_dir 解析

依赖: 本目录 conftest (sys.path 挂 factory-exec); exec_helpers (write_files/
FakeProvider)。不调真实 LLM (mock provider); 测试执行确定性 (真实 pytest)。

"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from exec.provider import ProviderRequest, ProviderResponse
from exec.tester import (
    BUG_REPORT_FIELDS,
    BugReport,
    DEFAULT_TEST_COMMAND,
    TestRunResult,
    TesterAgent,
    TesterError,
    _parse_test_counts,
    build_tester_executor,
    make_workflow_executor,
)

from exec_helpers import FakeProvider, write_files

PYTEST_CMD = f"{sys.executable} -m pytest -q"

#: 缺陷项目: sub 误用加法 (test_sub 失败) — 确定性失败
BUGGY_FILES = {
    "calc.py": (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def sub(a, b):\n"
        "    return a + b\n"  # bug: 应为 a - b
    ),
    "test_calc.py": (
        "from calc import add, sub\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
        "\n"
        "def test_sub():\n"
        "    assert sub(5, 3) == 2\n"
    ),
}

FIXED_FILES = {
    "calc.py": (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def sub(a, b):\n"
        "    return a - b\n"
    ),
    "test_calc.py": BUGGY_FILES["test_calc.py"],
}

BUG_JSON = json.dumps(
    [
        {
            "location": "calc.py:6 (sub)",
            "repro": "运行 test_sub: sub(5, 3)",
            "expected": "sub(5, 3) == 2",
            "actual": "sub(5, 3) == 8",
            "root_cause": "sub 误用加法运算符",
            "severity": "high",
        }
    ]
)


@pytest.fixture
def buggy_project(tmp_path: Path) -> Path:
    proj = tmp_path / "buggy"
    write_files(proj, BUGGY_FILES)
    return proj


@pytest.fixture
def fixed_project(tmp_path: Path) -> Path:
    proj = tmp_path / "fixed"
    write_files(proj, FIXED_FILES)
    return proj


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider(content=BUG_JSON)


def make_tester(provider=None, **kw) -> TesterAgent:
    kw.setdefault("test_command", PYTEST_CMD)
    return TesterAgent(provider, **kw)


class TestBugReportModel:
    def test_to_dict_contract_fields(self):
        bug = BugReport(
            location="calc.py:6", repro="r", expected="e", actual="a",
            root_cause="rc", severity="high",
        )
        data = bug.to_dict()
        assert set(data) == set(BUG_REPORT_FIELDS)
        assert data["location"] == "calc.py:6"
        assert data["severity"] == "high"

    def test_to_dict_includes_test_name_when_set(self):
        bug = BugReport(
            location="l", repro="r", expected="e", actual="a",
            root_cause="rc", severity="low", test_name="test_sub",
        )
        assert bug.to_dict()["test_name"] == "test_sub"

    def test_from_dict_lenient_defaults(self):
        """宽容解析: severity 缺省 medium; 未知字段忽略; 空白 strip。"""
        bug = BugReport.from_dict(
            {"location": " l ", "repro": "r", "expected": "e",
             "actual": "a", "root_cause": "rc", "extra": "ignored"}
        )
        assert bug.location == "l"
        assert bug.severity == "medium"

    def test_from_dict_missing_core_field_raises(self):
        with pytest.raises(TesterError, match="missing required fields"):
            BugReport.from_dict({"location": "l", "repro": "r"})

    def test_from_dict_blank_core_field_raises(self):
        with pytest.raises(TesterError, match="missing required fields"):
            BugReport.from_dict(
                {"location": "l", "repro": "  ", "expected": "e",
                 "actual": "a", "root_cause": "rc"}
            )


class TestRunTests:
    def test_passing_project_deterministic(self, fixed_project):
        """确定性测试执行: 真实 pytest 通过 → passed=True + 计数。"""
        run = make_tester().run_tests(fixed_project)
        assert run.passed
        assert run.total == 2
        assert run.failed == 0
        assert run.command == PYTEST_CMD
        assert "passed" in run.output

    def test_failing_project_deterministic(self, buggy_project):
        run = make_tester().run_tests(buggy_project)
        assert not run.passed
        assert run.failed == 1
        assert run.total == 2

    def test_missing_project_dir_raises(self):
        with pytest.raises(TesterError, match="project_dir required"):
            make_tester().run_tests()

    def test_nonexistent_dir_returns_failed(self, tmp_path):
        """目录缺失 → 诚实 failed (不崩溃, 不假装通过)。"""
        run = make_tester().run_tests(tmp_path / "no-such-dir")
        assert not run.passed

    def test_result_to_dict_shape(self, fixed_project):
        d = make_tester().run_tests(fixed_project).to_dict()
        assert d["passed"] is True
        assert set(d) == {"passed", "total", "failed", "command"}


class TestFailureAnalysis:
    def test_structured_bug_reports(self, buggy_project, provider):
        """mock provider (v4-pro 契约) → 结构化 bug report 列表。"""
        bugs = make_tester(provider).analyze_failures(
            test_output="1 failed", project_dir=buggy_project
        )
        assert len(bugs) == 1
        bug = bugs[0]
        assert bug.location == "calc.py:6 (sub)"
        assert bug.severity == "high"
        assert bug.root_cause == "sub 误用加法运算符"

    def test_prompt_contains_failure_context(self, buggy_project, provider):
        """prompt 携带项目清单/命令/失败输出 (分析上下文完整)。"""
        tester = make_tester(provider)
        tester.analyze_failures(test_output="FAILED calc.py", project_dir=buggy_project)
        request: ProviderRequest = provider.calls[0]
        assert "calc.py" in request.task_context
        assert PYTEST_CMD in request.task_context
        assert "FAILED calc.py" in request.task_context
        assert request.sandbox_path == str(buggy_project)

    def test_markdown_fenced_json_tolerated(self, buggy_project):
        provider = FakeProvider(content=f"```json\n{BUG_JSON}\n```")
        bugs = make_tester(provider).analyze_failures(
            test_output="x", project_dir=buggy_project
        )
        assert len(bugs) == 1

    def test_provider_error_raises(self, buggy_project):
        provider = FakeProvider(error="llm timeout")
        with pytest.raises(TesterError, match="llm timeout"):
            make_tester(provider).analyze_failures(
                test_output="x", project_dir=buggy_project
            )

    def test_garbage_output_raises(self, buggy_project):
        provider = FakeProvider(content="sorry, no json here")
        with pytest.raises(TesterError, match="not valid JSON"):
            make_tester(provider).analyze_failures(
                test_output="x", project_dir=buggy_project
            )

    def test_empty_bug_list_raises(self, buggy_project):
        """分析产出空列表 → 响亮拒绝 (不假装分析成功/不误判通过)。"""
        provider = FakeProvider(content="[]")
        with pytest.raises(TesterError, match="no bug reports"):
            make_tester(provider).analyze_failures(
                test_output="x", project_dir=buggy_project
            )

    def test_missing_provider_raises(self, buggy_project):
        with pytest.raises(TesterError, match="requires a provider"):
            make_tester(None).analyze_failures(
                test_output="x", project_dir=buggy_project
            )


class TestRepairTask:
    def test_repair_task_shape(self):
        bugs = [BugReport(location="l", repro="r", expected="e",
                          actual="a", root_cause="rc", severity="high")]
        task = make_tester().build_repair_task(bugs, test_output="1 failed")
        assert task["objective"] == "修复 1 个测试失败缺陷 (依据 bug report)"
        assert task["bug_count"] == 1
        assert task["bugs"][0]["location"] == "l"
        assert task["context"] == "1 failed"


class TestTestAndReport:
    def test_pass_path_zero_llm_calls(self, fixed_project, provider):
        """通过 → bugs=[] 且零 LLM 调用 (测试结果确定性, 不靠 LLM 猜)。"""
        report = make_tester(provider).test_and_report(fixed_project)
        assert report["passed"] is True
        assert report["bugs"] == []
        assert report["repair_tasks"] == []
        assert provider.calls == []

    def test_fail_path_structured_output(self, buggy_project, provider):
        report = make_tester(provider).test_and_report(buggy_project)
        assert report["passed"] is False
        assert len(report["bugs"]) == 1
        assert set(report["bugs"][0]) == set(BUG_REPORT_FIELDS)
        assert report["repair_tasks"][0]["bug_count"] == 1
        assert provider.calls, "失败路径应调用 LLM 分析"


class TestWorkflowAdapters:
    def test_make_workflow_executor_routes_by_role(self):
        seen: list[str] = []

        def dev(stage, context):
            seen.append("dev")
            return {"artifact_type": "code", "metadata": {"files": ["a"], "changes": "x"}}

        def tester(stage, context):
            seen.append("tester")
            return {"artifact_type": "test",
                    "metadata": {"results": {"passed": True}, "bugs": []}}

        executor = make_workflow_executor({"developer": dev, "tester": tester})
        class _S:  # 最小 stage 桩 (duck-typed)
            role_id = "developer"
            id = "STG-1"

        class _T:
            role_id = "tester"
            id = "STG-2"

        assert executor(_S(), {})["artifact_type"] == "code"
        assert executor(_T(), {})["artifact_type"] == "test"
        assert seen == ["dev", "tester"]

    def test_make_workflow_executor_unmapped_role_raises(self):
        executor = make_workflow_executor({"developer": lambda s, c: {}})

        class _S:
            role_id = "release-manager"
            id = "STG-9"

        with pytest.raises(TesterError, match="no executor mapped for role 'release-manager'"):
            executor(_S(), {})

    def test_build_tester_executor_multi_artifact(self, buggy_project, provider):
        """executor 契约: (stage, context) → 多产物 (test + bug_report)。"""
        tester = make_tester(provider)
        executor = build_tester_executor(tester)
        result = executor(
            object(),
            {"inputs": [{"type": "code", "metadata": {"project_dir": str(buggy_project)}}]},
        )
        types = [a["type"] for a in result["artifacts"]]
        assert types == ["test", "bug_report"]
        assert result["artifacts"][0]["metadata"]["results"]["passed"] is False
        assert len(result["artifacts"][0]["metadata"]["bugs"]) == 1
        assert result["repair_tasks"][0]["bug_count"] == 1

    def test_build_tester_executor_pass_no_bug_report(self, fixed_project, provider):
        """通过 → 仅 test 产物 (无 bug_report), 零 LLM 调用。"""
        tester = make_tester(provider)
        result = build_tester_executor(tester)(
            object(),
            {"inputs": [{"type": "code", "metadata": {"project_dir": str(fixed_project)}}]},
        )
        assert [a["type"] for a in result["artifacts"]] == ["test"]
        assert result["artifacts"][0]["metadata"]["bugs"] == []
        assert provider.calls == []

    def test_build_tester_executor_missing_project_dir_raises(self, provider):
        tester = make_tester(provider)
        with pytest.raises(TesterError, match="project_dir"):
            build_tester_executor(tester)(object(), {"inputs": []})

    def test_tester_configured_project_dir_fallback(self, buggy_project, provider):
        """project_dir 解析: tester 配置优先于 context 输入。"""
        tester = make_tester(provider, project_dir=buggy_project)
        result = build_tester_executor(tester)(object(), {"inputs": []})
        assert result["artifacts"][0]["type"] == "test"


class TestParseHelpers:
    def test_pytest_counts(self):
        assert _parse_test_counts("1 failed, 2 passed in 0.5s") == (3, 1)
        assert _parse_test_counts("3 passed in 0.1s") == (3, 0)

    def test_unittest_counts(self):
        assert _parse_test_counts("Ran 4 tests\nFAILED (failures=1)") == (4, 1)
        assert _parse_test_counts("Ran 2 tests ... OK") == (2, 0)

    def test_unknown_output_zero(self):
        assert _parse_test_counts("nothing here") == (0, 0)

    def test_default_command(self):
        assert DEFAULT_TEST_COMMAND == "python -m pytest -q"

    def test_test_run_result_dataclass(self):
        r = TestRunResult(passed=False, total=2, failed=1, output="o", command="c")
        assert r.to_dict() == {"passed": False, "total": 2, "failed": 1, "command": "c"}
