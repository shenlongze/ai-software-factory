"""factory-exec/exec/tester.py — Tester Agent 执行 (Sprint 7 S7-004)。

设计依据 (sprint7-architecture.md §2 Tester Agent / §4 Tester 优先级):
```
输入: Developer Artifact (patch + 项目) + 测试
执行: test (沙箱内运行测试: unittest/pytest, 确定性验证循环, 不靠 LLM 猜)
      → failure analysis (LLM 分析失败输出, v4-pro)
      → bug report (结构化: 位置/复现/期望/实际/根因/严重级)
      → repair task (回传 Developer, 附上下文)
输出: test_result + bug_report artifact (注册进 ArtifactRegistry)
```

实现 (KISS, 复用优先):
- 测试执行: 复用 Validation 验证循环 (factory-exec/exec/validation.py —
  subprocess 确定性执行 + 输出捕获), 零 LLM 猜测试结果。
- 失败分析: 仅当测试失败才调 Provider (生产 DeepSeek v4-pro; 测试注入 mock);
  LLM 输出结构化 JSON → BugReport 列表 (宽容解析, 缺核心字段响亮拒绝 —
  不伪造缺陷报告)。
- repair task: bug report → 结构化修复任务 (回传 Developer 的输入)。
- Workflow 接入: build_tester_executor / make_workflow_executor 产出 S7-003
  WorkflowRunner executor 注入点契约 (stage, context) → dict 多产物
  (test + bug_report 自动注册)。

约束 (S7-004):
- 只扩展, 不重写: 不 import factory-org (Removal Isolation, 同 exec 既有
  模块); 不实现 PM/Architect/Release/Analytics Agent; 零明文密钥。
- 诚实: 测试通过 → bugs=[] 零 LLM 调用; 分析失败 → TesterError 响亮
  (不假装分析成功, 不伪造缺陷)。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .provider import ProviderRequest
from .validation import Validation

#: 缺省测试命令 (确定性执行; 调用方可显式注入, 如 sys.executable 前缀)
DEFAULT_TEST_COMMAND = "python -m pytest -q"

#: bug_report 契约字段 (与 org CONTRACTS bug_report required_fields 同源)
BUG_REPORT_FIELDS: tuple[str, ...] = (
    "location",
    "repro",
    "expected",
    "actual",
    "root_cause",
    "severity",
)


class TesterError(Exception):
    """Tester Agent 业务错误 (缺 project_dir / 分析失败 / 未映射执行器等)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)


# ------------------------------------------------------------------ 模型


@dataclass(frozen=True)
class BugReport:
    """结构化缺陷报告 (bug_report artifact 载荷; 契约字段 = BUG_REPORT_FIELDS)。

    severity 缺省 "medium" (安全默认); test_name 可选 (缺陷归属用例)。
    """

    location: str
    repro: str
    expected: str
    actual: str
    root_cause: str
    severity: str = "medium"
    test_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """契约载荷 (全部 6 字段; test_name 非空时附带)。"""
        data = {f: getattr(self, f) for f in BUG_REPORT_FIELDS}
        if self.test_name:
            data["test_name"] = self.test_name
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BugReport":
        """宽容解析 (LLM 输出): 缺核心字段 → TesterError 响亮 (不伪造缺陷);
        severity 缺省 medium; 未知字段忽略。"""
        missing = [
            f for f in ("location", "repro", "expected", "actual", "root_cause")
            if not str(raw.get(f) or "").strip()
        ]
        if missing:
            raise TesterError(
                f"bug report missing required fields: {', '.join(missing)}"
            )
        return cls(
            location=str(raw["location"]).strip(),
            repro=str(raw["repro"]).strip(),
            expected=str(raw["expected"]).strip(),
            actual=str(raw["actual"]).strip(),
            root_cause=str(raw["root_cause"]).strip(),
            severity=str(raw.get("severity") or "medium").strip() or "medium",
            test_name=str(raw.get("test_name") or "").strip(),
        )


@dataclass(frozen=True)
class TestRunResult:
    """确定性测试执行结果 (test artifact results 载荷; passed 必含)。"""

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    passed: bool
    total: int = 0
    failed: int = 0
    output: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": self.total,
            "failed": self.failed,
            "command": self.command,
        }


# ------------------------------------------------------------------ 分析


#: 失败分析 prompt (结构化 bug report 输出; 生产 provider = DeepSeek v4-pro)
_FAILURE_ANALYSIS_PROMPT = (
    "你是一名 Tester (测试工程师)。测试执行失败, 请分析失败输出, 定位缺陷并生成"
    "结构化缺陷报告 (bug report)。\n\n"
    "项目文件清单:\n{project_files}\n\n"
    "测试命令: {command}\n\n"
    "测试输出:\n{output}\n\n"
    "输出 JSON 数组, 每项包含字段:\n"
    "- location: 缺陷位置 (文件:行号/函数名)\n"
    "- repro: 复现步骤\n"
    "- expected: 期望行为\n"
    "- actual: 实际行为\n"
    "- root_cause: 根因分析\n"
    "- severity: 严重级 (critical/high/medium/low)\n"
    "仅输出 JSON, 不要任何多余文字。"
)


def _project_files(project_dir: Path) -> str:
    """项目文件清单 (相对路径, 隐藏目录跳过; prompt 上下文)。"""
    files: list[str] = []
    if project_dir.is_dir():
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(project_dir)
            if any(part.startswith(".") for part in rel.parts):
                continue
            files.append(str(rel))
    if not files:
        return "(empty project)"
    shown = files[:60]
    lines = "\n".join(f"- {f}" for f in shown)
    if len(files) > 60:
        lines += f"\n... ({len(files) - 60} more files)"
    return lines


def _parse_test_counts(output: str) -> tuple[int, int]:
    """从测试输出解析 (total, failed) — pytest/unittest 轻量计数 (确定性)。

    解析失败 → (0, 0) (计数是审计增强, 不破坏执行链); 不靠 LLM 猜。
    """
    failed = 0
    passed = 0
    m = re.search(r"(\d+)\s+failed", output)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+)\s+passed", output)
    if m:
        passed = int(m.group(1))
    if passed or failed:
        return passed + failed, failed
    m = re.search(r"Ran\s+(\d+)\s+tests", output)
    if m:
        total = int(m.group(1))
        mf = re.search(r"failures=(\d+)", output)
        return total, int(mf.group(1)) if mf else 0
    return 0, 0


def _extract_json(content: str) -> Any:
    """宽容 JSON 提取: 剥 markdown 围栏 → 整体解析 → 子串回退 ([]/{})。"""
    text = content.strip()
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                continue
    raise TesterError("failure analysis output is not valid JSON")


def _parse_bug_reports(content: str) -> list[BugReport]:
    """LLM 输出 → BugReport 列表 (宽容解析; 空/垃圾 → TesterError 响亮)。"""
    data = _extract_json(content)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise TesterError("failure analysis produced no bug reports (不假装分析成功)")
    reports: list[BugReport] = []
    for item in data:
        if not isinstance(item, dict):
            raise TesterError(f"failure analysis item is not a dict: {item!r}")
        reports.append(BugReport.from_dict(item))
    return reports


# ------------------------------------------------------------------ Tester Agent


class TesterAgent:
    """Tester Agent: test → failure analysis → bug report → repair task。

    构造:
    - provider: ProviderInterface (失败分析 LLM; 生产 DeepSeek v4-pro,
      测试注入 mock; None 且测试失败 → TesterError 响亮)。
    - test_command: 沙箱内测试命令 (缺省 pytest -q; 确定性执行, 复用
      Validation 验证循环 — 不靠 LLM 猜测试结果)。
    - project_dir: 可选固定项目目录 (Workflow executor 场景可经 code 产物
      metadata 解析, 见 build_tester_executor)。
    - command_timeout: 测试命令超时 (秒, 透传 Validation)。

    方法:
    - run_tests(project_dir) → TestRunResult: 确定性测试执行。
    - analyze_failures(*, test_output, project_dir) → list[BugReport]:
      LLM 失败分析 (结构化输出)。
    - build_repair_task(bugs, *, test_output) → dict: 修复任务 (回传 Developer)。
    - test_and_report(project_dir) → dict: 全链
      {passed, results, bugs, repair_tasks} (通过 → bugs=[] 零 LLM 调用)。
    """

    __test__ = False  # pytest 收集豁免 (Test* 前缀类名误匹配)

    def __init__(
        self,
        provider: Any = None,
        *,
        test_command: str = DEFAULT_TEST_COMMAND,
        project_dir: str | Path | None = None,
        command_timeout: float = 60.0,
    ) -> None:
        self._provider = provider
        self._test_command = test_command
        self._project_dir = Path(project_dir) if project_dir else None
        self._command_timeout = command_timeout

    @property
    def provider(self) -> Any:
        return self._provider

    @property
    def test_command(self) -> str:
        return self._test_command

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    # ------------------------------------------------------------ 执行链

    def run_tests(self, project_dir: str | Path | None = None) -> TestRunResult:
        """确定性测试执行 (复用 Validation 验证循环; 沙箱内 subprocess)。"""
        pdir = self._resolve_project_dir(project_dir)
        validation = Validation(pdir, command_timeout=self._command_timeout)
        result = validation.validate(self._test_command)
        total, failed = _parse_test_counts(result.output)
        return TestRunResult(
            passed=result.passed,
            total=total,
            failed=failed,
            output=result.output,
            command=self._test_command,
        )

    def analyze_failures(
        self, *, test_output: str, project_dir: str | Path | None = None
    ) -> list[BugReport]:
        """失败分析: LLM (v4-pro) 分析失败输出 → 结构化 bug report 列表。

        provider 缺失 / 调用失败 / 输出不可解析 → TesterError 响亮
        (不假装分析成功; 空 bug 列表同样响亮拒绝 — 防误判通过)。
        """
        if self._provider is None:
            raise TesterError(
                "failure analysis requires a provider (仅 DeepSeek v4-pro; 测试注入 mock)"
            )
        pdir = self._resolve_project_dir(project_dir)
        prompt = _FAILURE_ANALYSIS_PROMPT.format(
            project_files=_project_files(pdir),
            command=self._test_command,
            output=(test_output or "")[:8000],
        )
        response = self._provider.generate(
            ProviderRequest(task_context=prompt, sandbox_path=str(pdir))
        )
        if not response.ok or not (response.content or "").strip():
            raise TesterError(
                f"failure analysis failed: {response.error or 'empty provider response'}"
            )
        return _parse_bug_reports(response.content)

    def build_repair_task(
        self, bugs: list[BugReport], *, test_output: str = ""
    ) -> dict[str, Any]:
        """修复任务 (回传 Developer): 目标 + 缺陷清单 + 失败输出上下文。"""
        return {
            "objective": f"修复 {len(bugs)} 个测试失败缺陷 (依据 bug report)",
            "bug_count": len(bugs),
            "bugs": [b.to_dict() if isinstance(b, BugReport) else b for b in bugs],
            "context": (test_output or "")[:2000],
        }

    def test_and_report(self, project_dir: str | Path | None = None) -> dict[str, Any]:
        """Tester 执行链全链: test → (失败) → LLM 分析 → bug_report + repair task。

        返回: {"passed", "results", "bugs", "repair_tasks"} — 通过时 bugs=[]
        (零 LLM 调用 — 测试结果确定性, 不靠 LLM 猜); 失败且分析成功 → 结构化
        bug report + repair task; 分析失败 → TesterError (向上, Workflow
        Runner 转 stage FAILED — 诚实)。
        """
        run = self.run_tests(project_dir)
        if run.passed:
            return {
                "passed": True,
                "results": run.to_dict(),
                "bugs": [],
                "repair_tasks": [],
            }
        bugs = self.analyze_failures(test_output=run.output, project_dir=project_dir)
        repair = self.build_repair_task(bugs, test_output=run.output)
        return {
            "passed": False,
            "results": run.to_dict(),
            "bugs": [b.to_dict() for b in bugs],
            "repair_tasks": [repair],
        }

    # ------------------------------------------------------------ 内部辅助

    def _resolve_project_dir(self, project_dir: str | Path | None) -> Path:
        pdir = project_dir or self._project_dir
        if pdir is None:
            raise TesterError("project_dir required (测试执行须有确定性项目目录)")
        return Path(pdir)


# ------------------------------------------------------------------ Workflow 接入


def make_workflow_executor(
    executors: dict[str, Callable[[Any, dict[str, Any]], dict[str, Any]]],
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Workflow Runner executor 路由适配器 (S7-003 注入点契约)。

    executor(stage, context) → dict: 按 stage.role_id 查表路由到对应角色执行器
    (developer/tester/...); 未映射角色 → TesterError 响亮 (不假装执行, 同
    编排壳诚实边界)。Dev↔Tester Loop 场景: {"developer": dev_fn,
    "tester": build_tester_executor(tester)}。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        fn = executors.get(stage.role_id)
        if fn is None:
            raise TesterError(
                f"no executor mapped for role {stage.role_id!r} (stage {stage.id})"
            )
        return fn(stage, context)

    return executor


def build_tester_executor(tester: TesterAgent) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """TesterAgent → Workflow executor 适配器 (多产物契约)。

    返回 dict 契约 (S7-003 _register_outputs 消费):
    - artifacts[]: test 产物 (results/bugs 契约载荷) + 每缺陷一条 bug_report
      产物 (结构化; 全部自动注册 → generated → validated)
    - repair_tasks (可选): 修复任务清单 (回传 Developer 上下文)
    project_dir 解析: tester 配置 > code 产物 metadata.project_dir。
    """

    def executor(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        project_dir = tester.project_dir or _code_project_dir(context)
        if project_dir is None:
            raise TesterError(
                "tester executor needs project_dir "
                "(TesterAgent 配置或 code 产物 metadata.project_dir)"
            )
        report = tester.test_and_report(project_dir)
        artifacts: list[dict[str, Any]] = [
            {
                "type": "test",
                "ref": "file:///test_result.json",
                "metadata": {"results": report["results"], "bugs": report["bugs"]},
            }
        ]
        for bug in report["bugs"]:
            artifacts.append(
                {"type": "bug_report", "ref": "file:///bug_report.json", "metadata": bug}
            )
        result: dict[str, Any] = {"artifacts": artifacts}
        if report["repair_tasks"]:
            result["repair_tasks"] = report["repair_tasks"]
        return result

    return executor


def _code_project_dir(context: dict[str, Any]) -> str | None:
    """从 executor context 的 code 产物 metadata 解析项目目录 (开发产物契约)。"""
    for inp in context.get("inputs", []):
        if not isinstance(inp, dict):
            continue
        meta = inp.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        pdir = meta.get("project_dir")
        if pdir:
            return str(pdir)
    return None
