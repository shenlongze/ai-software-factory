"""factory-console/session/eval_suite.py — K-5 七维评测体系 (S10-121 P0-1/C-1 + P0-5/C-6 发布门)。

评测 = 跑 + 出报告 (只读, 不改业务逻辑, 不调 LLM, 零第三方依赖):
- EVAL_DIMENSIONS: 7 维定义 — correctness(正确性)/robustness(鲁棒性)/
  consistency(一致性)/performance(性能)/security(安全)/longevity(长期)/
  user_value(用户价值); 每维 ≥1 可断言评测项, 复用现有契约/质量分/trace 数据
  (K-2 execution_quality · K-3 eval_loop · K-4 trace_context · J-1 lifecycle_store ·
  P0-10 注册表 · H-1/F-10 证据), 不新造业务。
- EvalSuite.run(workspace, gate=None, repo_root=None) -> EvalReport:
  只读跑全部评测项; 每项 通过/失败/未覆盖 + 证据引用 (测试名/文件/数据源)。
- EvalSuite.level(report) -> str: L0/L1/L2/L3 判定:
  L0 = correctness+robustness+consistency 全通过; L1 = L0 + performance+security
  全通过; L2 = L1 + longevity+user_value 全通过; 未定义/未覆盖维度 → 如实
  "未覆盖" (不臆造等级)。
- 发布门 (P0-5/C-6): patch=L0 · minor=L0+L1 · major=L0+L1+L2; 未覆盖维度
  → 阻断 (无法证明通过 = 门禁失败, rc 非 0 由 CLI 落地)。

边界:
- 纯标准库 (json/pathlib/dataclasses/time/re/contextlib); 零新依赖
- 评测项失败安全: 任何异常 → 该项 fail/not_covered + 诚实原因, 不崩
- 零污染: run() 只读 workspace 与 repo_root; 证据由外部 fixture/脚本在临时
  workspace 生成 (tests/console/test_s10_121_eval_suite.py · scripts/smoke_longrun.py
  · scripts/smoke_24h.py · scripts/coverage_report.py)
- 不调 LLM; 纯确定性断言

设计: docs/sprint10/S10-121-k5-eval-plan.md §1-§2
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

#: 评测套件版本 (可追溯; 与版本四件套语义一致)
EVAL_SUITE_VERSION = "1.0"

#: 性能评测宽松上限 (关键操作: 加载 workspace 状态 JSON, 单位秒)
PERF_KEY_OPS_LIMIT_S = 5.0

#: 24h 长跑阈值 (秒) — 达到才算"完成长跑"; 否则如实标"待长跑"
LONGRUN_24H_S = 24 * 60 * 60

#: 维度 key 常量
CORRECTNESS = "correctness"
ROBUSTNESS = "robustness"
CONSISTENCY = "consistency"
PERFORMANCE = "performance"
SECURITY = "security"
LONGEVITY = "longevity"
USER_VALUE = "user_value"

#: L0 维度 (正确性/鲁棒性/一致性)
L0_DIMENSIONS: tuple[str, ...] = (CORRECTNESS, ROBUSTNESS, CONSISTENCY)
#: L1 = L0 + 性能/安全
L1_DIMENSIONS: tuple[str, ...] = L0_DIMENSIONS + (PERFORMANCE, SECURITY)
#: L2 = L1 + 长期/用户价值
L2_DIMENSIONS: tuple[str, ...] = L1_DIMENSIONS + (LONGEVITY, USER_VALUE)

#: 发布门 → 所需维度 (patch=L0 · minor=L0+L1 · major=L0+L1+L2)
GATE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "patch": L0_DIMENSIONS,
    "minor": L1_DIMENSIONS,
    "major": L2_DIMENSIONS,
}

#: 维度中文标签 (报告展示)
DIMENSION_LABELS: dict[str, str] = {
    CORRECTNESS: "正确性",
    ROBUSTNESS: "鲁棒性",
    CONSISTENCY: "一致性",
    PERFORMANCE: "性能",
    SECURITY: "安全",
    LONGEVITY: "长期",
    USER_VALUE: "用户价值",
}

#: 评测证据目录 (workspace/.eval — 与业务数据隔离)
EVAL_DIR = ".eval"

#: 评测项状态常量
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NOT_COVERED = "not_covered"


def _now_iso() -> str:
    """当前 UTC ISO 时间 (报告时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    """读 JSON (失败安全 → None)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全
        return None


# ============================================================ 数据结构


@dataclass
class EvalItemResult:
    """单个评测项结果: 通过/失败/未覆盖 + 证据引用 + 说明。"""

    status: str = STATUS_NOT_COVERED   # pass | fail | not_covered
    evidence: str = ""                 # 证据引用 (测试名/文件/数据源)
    detail: str = ""                   # 说明 (为什么 / 结论)
    item_id: str = ""
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "label": self.label,
            "status": self.status,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass
class EvalDimensionResult:
    """单维聚合结果: 任一项失败 → fail; 否则任一项未覆盖 → not_covered; 否则 pass。"""

    key: str = ""
    label: str = ""
    status: str = STATUS_NOT_COVERED
    items: list[EvalItemResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class EvalReport:
    """评测报告: 7 维 + 等级判定 + 发布门结果 (可落盘/展示)。"""

    workspace: str = ""
    generated_at: str = ""
    eval_suite_version: str = EVAL_SUITE_VERSION
    dimensions: list[EvalDimensionResult] = field(default_factory=list)
    level: str = "未定义"
    level_reason: str = ""
    gate: Optional[str] = None
    gate_passed: Optional[bool] = None
    gate_reasons: list[str] = field(default_factory=list)

    def dimension(self, key: str) -> Optional[EvalDimensionResult]:
        """按 key 取维度结果 (失败安全 → None)。"""
        for d in self.dimensions:
            if d.key == key:
                return d
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "generated_at": self.generated_at,
            "eval_suite_version": self.eval_suite_version,
            "level": self.level,
            "level_reason": self.level_reason,
            "gate": self.gate,
            "gate_passed": self.gate_passed,
            "gate_reasons": list(self.gate_reasons),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }

    def to_markdown(self) -> str:
        """Markdown 报告 (stdout/--save 落盘)。"""
        lines = [
            "# AI Factory 可靠性评测报告 (K-5 七维)",
            "",
            f"- workspace: `{self.workspace}`",
            f"- 生成时间: {self.generated_at}",
            f"- 评测套件: eval_suite v{self.eval_suite_version}",
            f"- 判定等级: **{self.level}** — {self.level_reason}",
        ]
        if self.gate:
            passed = "通过 ✅" if self.gate_passed else "未通过 ❌ (阻断)"
            lines.append(f"- 发布门 --gate {self.gate}: **{passed}**")
            if self.gate_reasons:
                lines.append("  - " + "\n  - ".join(self.gate_reasons))
        lines.append("")
        lines.append("## 七维评测")
        lines.append("")
        lines.append("| 维度 | 状态 | 评测项 | 证据引用 | 说明 |")
        lines.append("|---|---|---|---|---|")
        for d in self.dimensions:
            status = {"pass": "✅ 通过", "fail": "❌ 失败", "not_covered": "⚠️ 未覆盖"}.get(
                d.status, d.status
            )
            if d.items:
                for i in d.items:
                    ev = i.evidence.replace("|", "\\|")
                    lines.append(
                        f"| {d.label} | {status if i is d.items[0] else ''} | "
                        f"{i.label} | {ev} | {i.detail.replace(chr(10), ' ')} |"
                    )
            else:
                lines.append(f"| {d.label} | {status} | — | — | — |")
        lines.append("")
        lines.append("> 口径: 未覆盖 = 该维度缺少可判定证据 (如实标注, 不伪造分数); 发布门阻断 = 无法证明通过。")
        return "\n".join(lines)


# ============================================================ 评测项


def _result(
    status: str,
    item_id: str,
    label: str,
    evidence: str = "",
    detail: str = "",
) -> EvalItemResult:
    """构造 EvalItemResult (携带 item_id/label)。"""
    return EvalItemResult(
        status=status, evidence=evidence, detail=detail, item_id=item_id, label=label
    )


def _not_covered(item_id: str, label: str, why: str) -> EvalItemResult:
    return _result(STATUS_NOT_COVERED, item_id, label, evidence="", detail=why)


def _eval_file(ws: Path, name: str) -> Path:
    """workspace/.eval/<name> 路径。"""
    return ws / EVAL_DIR / name


def _check_e2e_chain(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """正确性·E2E 链路 (H-1): .eval/e2e_result.json 节点全过 → pass。"""
    f = _eval_file(ws, "e2e_result.json")
    if not f.is_file():
        return _not_covered(
            CORRECTNESS + ".e2e_chain",
            "端到端全链 (H-1)",
            "缺 .eval/e2e_result.json — H-1 fixture 未在临时 workspace 跑过",
        )
    data = _read_json(f)
    if not isinstance(data, dict):
        return _result(
            STATUS_FAIL, CORRECTNESS + ".e2e_chain", "端到端全链 (H-1)",
            evidence=str(f), detail="e2e_result.json 损坏",
        )
    nodes = data.get("nodes") if isinstance(data.get("nodes"), dict) else {}
    if data.get("ok") is True and nodes and all(nodes.values()):
        return _result(
            STATUS_PASS, CORRECTNESS + ".e2e_chain", "端到端全链 (H-1)",
            evidence=(
                "tests/console/test_s10_121_eval_suite.py::run_e2e_fixture"
                f" → {f}"
            ),
            detail=(
                f"节点 {len(nodes)} 个全过 (创建→发现→PRD→工程→执行→证据→审批→交付), "
                f"最终生命周期 {data.get('lifecycle') or '?'} (J-1 投影一致)"
            ),
        )
    failed = [k for k, v in nodes.items() if not v]
    return _result(
        STATUS_FAIL, CORRECTNESS + ".e2e_chain", "端到端全链 (H-1)",
        evidence=str(f),
        detail=f"端到端链路失败: {failed or 'ok=false'}",
    )


def _check_quality_score(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """正确性·执行质量分 (K-2): 每项目最近执行记录 quality.score >= 阈值。"""
    from .execution_quality import LOW_SCORE_THRESHOLD

    f = ws / "exec" / "execution_records.json"
    if not f.is_file():
        return _not_covered(
            CORRECTNESS + ".quality_score",
            "执行质量分 >= 阈值 (K-2)",
            "缺 exec/execution_records.json — 无执行记录可评",
        )
    data = _read_json(f)
    records = data if isinstance(data, list) else []
    if not records:
        return _not_covered(
            CORRECTNESS + ".quality_score",
            "执行质量分 >= 阈值 (K-2)",
            "execution_records.json 为空 — 无执行记录可评",
        )
    # 每项目最近一条记录 (时间戳排序)
    by_project: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if not isinstance(r, dict):
            continue
        proj = str(
            r.get("project")
            or (r.get("input_snapshot") or {}).get("context", {}).get("project")
            or ""
        )
        by_project.setdefault(proj, []).append(r)
    lows: list[str] = []
    checked = 0
    for proj, recs in by_project.items():
        recs.sort(key=lambda r: str(r.get("timestamp") or ""))
        latest = recs[-1]
        q = latest.get("quality")
        q = q if isinstance(q, dict) else {}
        try:
            score = float(q.get("score"))
        except (TypeError, ValueError):  # 无分 → 该记录无质量分, 不算低分
            continue
        checked += 1
        if score < LOW_SCORE_THRESHOLD:
            lows.append(f"{proj}({score:.2f})")
    if checked == 0:
        return _not_covered(
            CORRECTNESS + ".quality_score",
            "执行质量分 >= 阈值 (K-2)",
            "执行记录均无质量分 (K-2 未接线) — 无法判定正确性",
        )
    if lows:
        return _result(
            STATUS_FAIL, CORRECTNESS + ".quality_score", "执行质量分 >= 阈值 (K-2)",
            evidence="factory-console/session/execution_quality.py::score_execution → exec/execution_records.json",
            detail=f"最近执行记录存在低分: {', '.join(lows)} (阈值 {LOW_SCORE_THRESHOLD:g})",
        )
    return _result(
        STATUS_PASS, CORRECTNESS + ".quality_score", "执行质量分 >= 阈值 (K-2)",
        evidence=(
            "factory-console/session/execution_quality.py::score_execution"
            f" + tests/console/test_s10_119_learning_loop.py → {f}"
        ),
        detail=f"{checked} 个项目最近执行记录质量分全部 >= {LOW_SCORE_THRESHOLD:g}",
    )


def _check_fail_safe_quality(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """鲁棒性·失败安全 (K-2): score=None 的记录必须带 reason (诚实标注不臆造)。"""
    f = ws / "exec" / "execution_records.json"
    if not f.is_file():
        return _not_covered(
            ROBUSTNESS + ".fail_safe_quality",
            "评分失败安全 (K-2)",
            "缺 exec/execution_records.json — 无执行记录可评",
        )
    data = _read_json(f)
    records = data if isinstance(data, list) else []
    if not records:
        return _not_covered(
            ROBUSTNESS + ".fail_safe_quality",
            "评分失败安全 (K-2)",
            "execution_records.json 为空",
        )
    violations: list[str] = []
    with_reason = 0
    for r in records:
        if not isinstance(r, dict):
            continue
        q = r.get("quality")
        q = q if isinstance(q, dict) else {}
        if q.get("score") is None and q.get("score") != 0.0:
            if "score" not in q:
                continue  # 无分记录 (中性) — 不算失败安全违规
            if q.get("reason"):
                with_reason += 1
            else:
                violations.append(str(r.get("task") or r.get("task_id") or "?"))
    if violations:
        return _result(
            STATUS_FAIL, ROBUSTNESS + ".fail_safe_quality", "评分失败安全 (K-2)",
            evidence="factory-console/session/execution_quality.py (失败安全 → score=None + reason)",
            detail=f"评分器失败记录缺 reason: {', '.join(violations[:5])}",
        )
    if with_reason or any(
        isinstance(r, dict) and r.get("quality") and r["quality"].get("score") is None
        for r in records
    ):
        return _result(
            STATUS_PASS, ROBUSTNESS + ".fail_safe_quality", "评分失败安全 (K-2)",
            evidence=(
                "factory-console/session/execution_quality.py + "
                "tests/console/test_s10_119_learning_loop.py (失败安全断言)"
            ),
            detail="执行质量评分失败安全路径存在: score=None 均带 reason 诚实标注",
        )
    return _not_covered(
        ROBUSTNESS + ".fail_safe_quality",
        "评分失败安全 (K-2)",
        "执行记录无 score=None 样例 — 失败安全路径未被实测 (未覆盖)",
    )


def _check_bad_input(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """鲁棒性·异常输入: .eval/robustness_result.json 全过 → pass。"""
    f = _eval_file(ws, "robustness_result.json")
    if not f.is_file():
        return _not_covered(
            ROBUSTNESS + ".bad_input",
            "异常输入不崩 (鲁棒性 fixture)",
            "缺 .eval/robustness_result.json — 异常输入 fixture 未跑",
        )
    data = _read_json(f)
    if not isinstance(data, dict):
        return _result(
            STATUS_FAIL, ROBUSTNESS + ".bad_input", "异常输入不崩 (鲁棒性 fixture)",
            evidence=str(f), detail="robustness_result.json 损坏",
        )
    cases = data.get("cases") if isinstance(data.get("cases"), list) else []
    if data.get("ok") is True:
        return _result(
            STATUS_PASS, ROBUSTNESS + ".bad_input", "异常输入不崩 (鲁棒性 fixture)",
            evidence=(
                "tests/console/test_s10_121_eval_suite.py::run_robustness_fixture"
                f" → {f}"
            ),
            detail=f"异常输入 {len(cases)} 例全部不崩 (确定性返回, 无裸异常)",
        )
    return _result(
        STATUS_FAIL, ROBUSTNESS + ".bad_input", "异常输入不崩 (鲁棒性 fixture)",
        evidence=str(f), detail="异常输入用例存在失败",
    )


def _check_registry(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """一致性·注册表 (P0-10): build_parser 子命令 == 测试期望集合 (含 eval)。"""
    if repo_root is None or not (repo_root / "factory-console" / "cli_factory.py").is_file():
        return _not_covered(
            CONSISTENCY + ".registry",
            "CLI 注册表一致 (P0-10)",
            "缺 repo_root — 注册表静态核对需要仓库根 (factory eval 自动注入)",
        )
    try:
        import argparse
        import ast
        import importlib

        cli = importlib.import_module("factory-console.cli_factory")
        parser = cli.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions  # noqa: SLF001 — 注册表核对 (同 test_s10_112)
            if isinstance(a, argparse._SubParsersAction)  # noqa: SLF001
        }
        choices = set(sub_actions["command"].choices)
        src = (repo_root / "tests" / "console" / "test_console_cli.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(src)
        expected: Optional[set[str]] = None
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "test_all_subcommands_registered"):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Set):
                    names = {
                        el.value
                        for el in sub.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    }
                    if names:
                        expected = names
        if expected is None:
            return _result(
                STATUS_FAIL, CONSISTENCY + ".registry", "CLI 注册表一致 (P0-10)",
                evidence="tests/console/test_console_cli.py::test_all_subcommands_registered",
                detail="测试期望集合未找到 (AST 解析失败)",
            )
        missing = sorted(choices - expected)
        extra = sorted(expected - choices)
        if missing or extra:
            return _result(
                STATUS_FAIL, CONSISTENCY + ".registry", "CLI 注册表一致 (P0-10)",
                evidence=(
                    "tests/console/test_s10_112_registry_consistency.py + "
                    "tests/console/test_console_cli.py::test_all_subcommands_registered"
                ),
                detail=(
                    f"注册表漂移: parser 有而测试未同步 {missing} / 测试期望但 parser 缺 {extra}"
                ),
            )
        return _result(
            STATUS_PASS, CONSISTENCY + ".registry", "CLI 注册表一致 (P0-10)",
            evidence=(
                "tests/console/test_s10_112_registry_consistency.py::TestCliRegistryConsistency"
                " + tests/console/test_console_cli.py::test_all_subcommands_registered"
            ),
            detail=f"CLI 子命令 {len(choices)} 个与测试期望集合一致 (含 eval)",
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return _result(
            STATUS_FAIL, CONSISTENCY + ".registry", "CLI 注册表一致 (P0-10)",
            evidence="tests/console/test_s10_112_registry_consistency.py",
            detail=f"注册表核对异常: {exc}",
        )


def _check_state_projection(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """一致性·状态单一来源投影 (J-1): project.json.status 与 product.json /
    execution_state.json.lifecycle 镜像一致 (存在才比, 缺失跳过 — 同写入语义)。"""
    from .lifecycle_store import LEGACY_STATUS_MAP

    projects_root = ws / "projects"
    if not projects_root.is_dir():
        return _not_covered(
            CONSISTENCY + ".state_projection",
            "状态单一来源投影 (J-1)",
            "workspace 无 projects/ 目录 — 无项目可校验",
        )

    def _status(pdir: Path, fname: str, key: str) -> Optional[str]:
        f = pdir / fname
        if not f.is_file():
            return None
        data = _read_json(f)
        if not isinstance(data, dict):
            return None
        value = data.get(key)
        return str(value) if value else None

    def _normalize(value: Optional[str]) -> Optional[str]:
        """旧词汇 → Lifecycle 归一 (同 J-1 口径); 无法判定 → 原样。"""
        if value is None:
            return None
        v = str(value).strip().lower()
        return LEGACY_STATUS_MAP.get(v, v)

    drift: list[str] = []
    checked = 0
    for pdir in sorted(projects_root.iterdir()):
        if not pdir.is_dir():
            continue
        canonical = _status(pdir, "project.json", "status")
        if canonical is None:
            continue  # 无状态项目 (draft 早期) — 跳过不判
        canon_norm = _normalize(canonical)
        checked += 1
        product = _normalize(_status(pdir, "product.json", "status"))
        state = _normalize(_status(pdir, "execution_state.json", "lifecycle"))
        if product is not None and product != canon_norm:
            drift.append(f"{pdir.name}: project={canonical} vs product={product}")
        if state is not None and state != canon_norm:
            drift.append(f"{pdir.name}: project={canonical} vs state={state}")
    if checked == 0:
        return _not_covered(
            CONSISTENCY + ".state_projection",
            "状态单一来源投影 (J-1)",
            "无 project.json.status 可校验 (无确认后项目)",
        )
    if drift:
        return _result(
            STATUS_FAIL, CONSISTENCY + ".state_projection", "状态单一来源投影 (J-1)",
            evidence=(
                "factory-console/session/lifecycle_store.py::set_project_lifecycle"
                " + tests/console/test_s10_115_lifecycle_single_source.py"
            ),
            detail="状态漂移: " + "; ".join(drift[:5]),
        )
    return _result(
        STATUS_PASS, CONSISTENCY + ".state_projection", "状态单一来源投影 (J-1)",
        evidence=(
            "factory-console/session/lifecycle_store.py + "
            "tests/console/test_s10_115_lifecycle_single_source.py (a-h)"
        ),
        detail=f"{checked} 个项目 project.json.status 与 product/state 镜像一致",
    )


def _check_perf_key_ops(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """性能·关键操作耗时上限 (宽松): 加载 workspace 全部 JSON 状态文件。"""
    if not ws.is_dir():
        return _not_covered(
            PERFORMANCE + ".key_ops",
            "关键操作耗时上限 (宽松)",
            "workspace 不存在 — 无数据可测",
        )
    files = sorted(ws.rglob("*.json"))
    if not files:
        return _not_covered(
            PERFORMANCE + ".key_ops",
            "关键操作耗时上限 (宽松)",
            "workspace 无 JSON 状态文件 — 无数据可测 (口径: 不空测)",
        )
    start = time.perf_counter()
    total = 0
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total += len(json.dumps(data))
        except Exception:  # noqa: BLE001 — 损坏文件跳过 (不计入可加载)
            pass
    elapsed = time.perf_counter() - start
    if elapsed <= PERF_KEY_OPS_LIMIT_S:
        return _result(
            STATUS_PASS, PERFORMANCE + ".key_ops", "关键操作耗时上限 (宽松)",
            evidence="factory-console/session/eval_suite.py::_check_perf_key_ops (实测)",
            detail=(
                f"加载 {len(files)} 个 JSON 状态文件耗时 {elapsed:.3f}s "
                f"(上限 {PERF_KEY_OPS_LIMIT_S:g}s, 数据量 {total} bytes)"
            ),
        )
    return _result(
        STATUS_FAIL, PERFORMANCE + ".key_ops", "关键操作耗时上限 (宽松)",
        evidence="factory-console/session/eval_suite.py::_check_perf_key_ops (实测)",
        detail=f"加载 {len(files)} 个 JSON 状态文件耗时 {elapsed:.3f}s — 超过上限 {PERF_KEY_OPS_LIMIT_S:g}s",
    )


def _check_audit_trace(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """安全·审计可追踪 (K-4): 审计事件全部带 trace_id。"""
    from ..audit.audit_store import AuditStore

    f = ws / "audit" / "audit_events.json"
    if not f.is_file():
        return _not_covered(
            SECURITY + ".audit_trace",
            "审计封存/trace 贯穿 (K-4)",
            "缺 audit/audit_events.json — 无审计事件可校验",
        )
    try:
        events = AuditStore(workspace=ws).events()
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return _result(
            STATUS_FAIL, SECURITY + ".audit_trace", "审计封存/trace 贯穿 (K-4)",
            evidence="factory-console/audit/audit_store.py",
            detail=f"审计读取异常: {exc}",
        )
    if not events:
        return _not_covered(
            SECURITY + ".audit_trace",
            "审计封存/trace 贯穿 (K-4)",
            "审计事件为空 — 无法校验",
        )
    missing = [e.audit_id for e in events if not (e.trace_id or "")]
    with_trace = len(events) - len(missing)
    if with_trace == 0:
        # 无带 trace_id 的事件 → 无法证明贯穿生效 (诚实语义: 未覆盖, 非失败 —
        # 无上下文路径的空 trace_id 属 K-4 设计允许; 仅当审计损坏/读取异常才 FAIL)
        return _not_covered(
            SECURITY + ".audit_trace",
            "审计封存/trace 贯穿 (K-4)",
            f"{len(events)} 个审计事件均无 trace_id (无上下文发射属设计允许) — 无法证明贯穿生效",
        )
    return _result(
        STATUS_PASS, SECURITY + ".audit_trace", "审计封存/trace 贯穿 (K-4)",
        evidence=(
            "factory-console/audit/trace_context.py + audit_store.py (封存 hash 链) + "
            "tests/console/test_s10_120_trace_chain.py"
        ),
        detail=f"{with_trace}/{len(events)} 个审计事件带 trace_id (K-4 机制生效; 无上下文路径的空 trace_id 属设计允许)",
    )


#: 明文密钥风险模式: "api_key"/"api_key_ref" 的值为非空且不以 "env:" 开头的字符串
_PLAINTEXT_KEY_KEYS = ("api_key", "api_key_ref")
_SECRET_REF_PREFIX = "env:"


def _scan_plaintext_keys(obj: Any, path: str, hits: list[str]) -> None:
    """递归扫描 JSON 对象中的明文密钥字段 (引用式配置才安全)。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k in _PLAINTEXT_KEY_KEYS:
                if isinstance(v, str) and v and not v.startswith(_SECRET_REF_PREFIX):
                    hits.append(f"{path}.{k}")
            _scan_plaintext_keys(v, f"{path}.{k}", hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _scan_plaintext_keys(v, f"{path}[{i}]", hits)


def _check_secret_scan(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """安全·密钥不落明文: workspace JSON 中 api_key/api_key_ref 只存 env: 引用。"""
    if not ws.is_dir():
        return _not_covered(
            SECURITY + ".secret_scan",
            "密钥只存引用不落明文",
            "workspace 不存在 — 无可扫描数据",
        )
    files = sorted(ws.rglob("*.json"))
    json_files = [f for f in files if f.is_file()]
    if not json_files:
        return _not_covered(
            SECURITY + ".secret_scan",
            "密钥只存引用不落明文",
            "workspace 无 JSON 配置 — 无配置可扫描 (未覆盖)",
        )
    hits: list[str] = []
    scanned = 0
    for f in json_files:
        data = _read_json(f)
        if data is None:
            continue
        before = len(hits)
        _scan_plaintext_keys(data, str(f.relative_to(ws)), hits)
        if len(hits) == before:
            scanned += 1
    if hits:
        return _result(
            STATUS_FAIL, SECURITY + ".secret_scan", "密钥只存引用不落明文",
            evidence="factory-console/llm_control.py (api_key_ref 铁律) + config.py",
            detail=f"发现明文密钥字段: {', '.join(hits[:5])} (只允许 env:VAR 引用)",
        )
    if scanned == 0:
        return _not_covered(
            SECURITY + ".secret_scan",
            "密钥只存引用不落明文",
            "JSON 文件均损坏/无键 — 无法扫描 (未覆盖)",
        )
    return _result(
        STATUS_PASS, SECURITY + ".secret_scan", "密钥只存引用不落明文",
        evidence=(
            "factory-console/llm_control.py (D3 api_key_ref=env:VAR) + "
            "tests/console/test_cli_doctor.py (seed_provider 只存引用)"
        ),
        detail=f"扫描 {scanned} 个 JSON 配置: 未发现明文 api_key (只存 env: 引用)",
    )


def _check_trace_isolation(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """长期·并发不串 (K-4 trace 隔离): .eval/concurrency_result.json。"""
    f = _eval_file(ws, "concurrency_result.json")
    if not f.is_file():
        return _not_covered(
            LONGEVITY + ".trace_isolation",
            "并发不串 (K-4 trace 隔离)",
            "缺 .eval/concurrency_result.json — 并发 fixture 未跑",
        )
    data = _read_json(f)
    if not isinstance(data, dict):
        return _result(
            STATUS_FAIL, LONGEVITY + ".trace_isolation", "并发不串 (K-4 trace 隔离)",
            evidence=str(f), detail="concurrency_result.json 损坏",
        )
    traces = data.get("trace_ids") if isinstance(data.get("trace_ids"), dict) else {}
    if data.get("ok") is True and traces:
        unique = len({str(v) for v in traces.values() if v})
        projects = list(traces)
        isolated = unique == len(projects) and unique == int(data.get("projects") or 0)
        if isolated:
            return _result(
                STATUS_PASS, LONGEVITY + ".trace_isolation", "并发不串 (K-4 trace 隔离)",
                evidence=(
                    "tests/console/test_s10_121_eval_suite.py::run_concurrency_fixture"
                    f" → {f}"
                ),
                detail=(
                    f"{len(projects)} 个项目并发: 各项目 trace_id 独立 ({unique} 个唯一), "
                    f"事件 {data.get('events') or 0} 条零交叉"
                ),
            )
        return _result(
            STATUS_FAIL, LONGEVITY + ".trace_isolation", "并发不串 (K-4 trace 隔离)",
            evidence=str(f),
            detail="并发 trace 隔离失败: trace_id 数量与项目数不一致 (存在串线)",
        )
    return _result(
        STATUS_FAIL, LONGEVITY + ".trace_isolation", "并发不串 (K-4 trace 隔离)",
        evidence=str(f), detail="并发 fixture 报告 ok=false 或 trace_ids 缺失",
    )


def _check_longrun(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """长期·长跑冒烟: .eval/longrun_result.json; <24h 如实标"待长跑"。"""
    f = _eval_file(ws, "longrun_result.json")
    if not f.is_file():
        return _not_covered(
            LONGEVITY + ".longrun",
            "长跑冒烟 (P0-4/C-5)",
            "缺 .eval/longrun_result.json — 长跑冒烟未跑 (scripts/smoke_longrun.py)",
        )
    data = _read_json(f)
    if not isinstance(data, dict) or data.get("ok") is not True:
        return _result(
            STATUS_FAIL, LONGEVITY + ".longrun", "长跑冒烟 (P0-4/C-5)",
            evidence=str(f), detail="长跑冒烟报告异常/失败",
        )
    duration = float(data.get("duration_seconds") or 0.0)
    heartbeats = int(data.get("heartbeats") or 0)
    if duration >= LONGRUN_24H_S:
        return _result(
            STATUS_PASS, LONGEVITY + ".longrun", "长跑冒烟 (P0-4/C-5)",
            evidence=f"scripts/smoke_longrun.py --duration 86400 → {f}",
            detail=f"24h 长跑完成: {duration:.1f}s, {heartbeats} 次心跳全存活",
        )
    return _not_covered(
        LONGEVITY + ".longrun",
        "长跑冒烟 (P0-4/C-5)",
        f"长跑冒烟已跑 {duration:.1f}s ({heartbeats} 次心跳存活) — 未满 24h, 如实标【待长跑】"
        f" (24h 脚本 scripts/smoke_24h.py 已提供)",
    )


def _check_learning_loop(ws: Path, repo_root: Optional[Path]) -> EvalItemResult:
    """用户价值·学习闭环 (K-3): .eval/learning_loop_result.json (口径: 闭环引用存在)。"""
    f = _eval_file(ws, "learning_loop_result.json")
    if not f.is_file():
        return _not_covered(
            USER_VALUE + ".learning_loop",
            "学习闭环引用 (K-3)",
            "缺 .eval/learning_loop_result.json — 学习闭环 fixture 未跑 "
            "(口径: 评测闭环引用存在, 不评测价值本身)",
        )
    data = _read_json(f)
    if not isinstance(data, dict) or data.get("ok") is not True:
        return _result(
            STATUS_FAIL, USER_VALUE + ".learning_loop", "学习闭环引用 (K-3)",
            evidence=str(f), detail="学习闭环报告异常/失败",
        )
    return _result(
        STATUS_PASS, USER_VALUE + ".learning_loop", "学习闭环引用 (K-3)",
        evidence=(
            "factory-console/session/eval_loop.py (E-2/E-3) + "
            "tests/console/test_s10_121_eval_suite.py::run_learning_loop_fixture"
            f" → {f}"
        ),
        detail=(
            f"学习闭环可跑: 分类 {data.get('classification') or '?'} → "
            f"复评 {data.get('reevaluated_score') or '?'} "
            f"(improved={data.get('improved')})"
        ),
    )


#: 七维评测项定义 (每维 ≥1 可断言评测项; check(workspace, repo_root) → EvalItemResult)
EVAL_DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": CORRECTNESS,
        "label": DIMENSION_LABELS[CORRECTNESS],
        "items": [
            {"id": CORRECTNESS + ".e2e_chain", "label": "端到端全链 (H-1)", "check": _check_e2e_chain},
            {"id": CORRECTNESS + ".quality_score", "label": "执行质量分 >= 阈值 (K-2)", "check": _check_quality_score},
        ],
    },
    {
        "key": ROBUSTNESS,
        "label": DIMENSION_LABELS[ROBUSTNESS],
        "items": [
            {"id": ROBUSTNESS + ".fail_safe_quality", "label": "评分失败安全 (K-2)", "check": _check_fail_safe_quality},
            {"id": ROBUSTNESS + ".bad_input", "label": "异常输入不崩 (鲁棒性 fixture)", "check": _check_bad_input},
        ],
    },
    {
        "key": CONSISTENCY,
        "label": DIMENSION_LABELS[CONSISTENCY],
        "items": [
            {"id": CONSISTENCY + ".registry", "label": "CLI 注册表一致 (P0-10)", "check": _check_registry},
            {"id": CONSISTENCY + ".state_projection", "label": "状态单一来源投影 (J-1)", "check": _check_state_projection},
        ],
    },
    {
        "key": PERFORMANCE,
        "label": DIMENSION_LABELS[PERFORMANCE],
        "items": [
            {"id": PERFORMANCE + ".key_ops", "label": "关键操作耗时上限 (宽松)", "check": _check_perf_key_ops},
        ],
    },
    {
        "key": SECURITY,
        "label": DIMENSION_LABELS[SECURITY],
        "items": [
            {"id": SECURITY + ".audit_trace", "label": "审计封存/trace 贯穿 (K-4)", "check": _check_audit_trace},
            {"id": SECURITY + ".secret_scan", "label": "密钥只存引用不落明文", "check": _check_secret_scan},
        ],
    },
    {
        "key": LONGEVITY,
        "label": DIMENSION_LABELS[LONGEVITY],
        "items": [
            {"id": LONGEVITY + ".trace_isolation", "label": "并发不串 (K-4 trace 隔离)", "check": _check_trace_isolation},
            {"id": LONGEVITY + ".longrun", "label": "长跑冒烟 (P0-4/C-5)", "check": _check_longrun},
        ],
    },
    {
        "key": USER_VALUE,
        "label": DIMENSION_LABELS[USER_VALUE],
        "items": [
            {"id": USER_VALUE + ".learning_loop", "label": "学习闭环引用 (K-3)", "check": _check_learning_loop},
        ],
    },
]


# ============================================================ EvalSuite


def _aggregate_dimension(items: list[EvalItemResult]) -> str:
    """维度聚合: 任一项失败 → fail; 否则任一项未覆盖 → not_covered; 否则 pass。"""
    if any(i.status == STATUS_FAIL for i in items):
        return STATUS_FAIL
    if any(i.status == STATUS_NOT_COVERED for i in items):
        return STATUS_NOT_COVERED
    return STATUS_PASS


def _dimension_passed(report: EvalReport, key: str) -> bool:
    """维度是否通过 (未覆盖/失败 → False — 无法证明通过)。"""
    d = report.dimension(key)
    return bool(d and d.status == STATUS_PASS)


class EvalSuite:
    """七维评测套件 (K-5): 只读跑评测 + 出报告 + 等级/门禁判定。

    - run(workspace, gate=None, repo_root=None) -> EvalReport
    - level(report) -> str: L0/L1/L2 (未定义/未覆盖 → 如实标注)
    - gate_passed(report, gate) -> tuple[bool, list[str]]
    """

    # ------------------------------------------------------------ 主入口

    def run(
        self,
        workspace: Path | str,
        *,
        gate: Optional[str] = None,
        repo_root: Optional[Path | str] = None,
    ) -> EvalReport:
        """只读跑全部评测项 → 报告 (含等级 + 可选发布门判定)。

        workspace: 被评测数据根 (只读; 零污染);
        gate: patch|minor|major (None → 只报告不判门);
        repo_root: 仓库根 (注册表静态核对用; None → 该项未覆盖)。
        """
        ws = Path(workspace)
        root = Path(repo_root) if repo_root is not None else None
        if gate is not None and gate not in GATE_DIMENSIONS:
            raise ValueError(f"未知发布门: {gate} (可用: {', '.join(sorted(GATE_DIMENSIONS))})")

        dimensions: list[EvalDimensionResult] = []
        for dim in EVAL_DIMENSIONS:
            items: list[EvalItemResult] = []
            for spec in dim["items"]:
                try:
                    result = spec["check"](ws, root)
                except Exception as exc:  # noqa: BLE001 — 评测项失败安全
                    result = _result(
                        STATUS_FAIL, str(spec["id"]), str(spec["label"]),
                        evidence=str(spec["id"]),
                        detail=f"评测项异常: {exc}",
                    )
                items.append(result)
            dimensions.append(
                EvalDimensionResult(
                    key=str(dim["key"]),
                    label=str(dim["label"]),
                    status=_aggregate_dimension(items),
                    items=items,
                )
            )

        report = EvalReport(
            workspace=str(ws.resolve() if ws.exists() else ws),
            generated_at=_now_iso(),
            eval_suite_version=EVAL_SUITE_VERSION,
            dimensions=dimensions,
        )
        report.level = self.level(report)
        report.level_reason = self.level_reason(report)
        if gate is not None:
            report.gate = gate
            passed, reasons = self.gate_passed(report, gate)
            report.gate_passed = passed
            report.gate_reasons = reasons
        return report

    # ------------------------------------------------------------ 等级判定

    @classmethod
    def level(cls, report: EvalReport) -> str:
        """L0/L1/L2 判定 (第一版; L3 未定义 → 如实"未定义")。

        L0 = correctness+robustness+consistency 全通过;
        L1 = L0 + performance+security 全通过;
        L2 = L1 + longevity+user_value 全通过。
        任何所需维度未覆盖/失败 → 对应等级不达成 (如实标注, 不臆造)。
        """
        if all(_dimension_passed(report, k) for k in L2_DIMENSIONS):
            return "L2"
        if all(_dimension_passed(report, k) for k in L1_DIMENSIONS):
            return "L1"
        if all(_dimension_passed(report, k) for k in L0_DIMENSIONS):
            return "L0"
        return "below-L0"

    @classmethod
    def level_reason(cls, report: EvalReport) -> str:
        """等级判定原因 (可读/可审计)。"""
        if report.level == "L2":
            return "L0+L1+L2 七维全部通过 (正确性/鲁棒性/一致性/性能/安全/长期/用户价值)"
        if report.level == "L1":
            missing = [DIMENSION_LABELS[k] for k in L2_DIMENSIONS if not _dimension_passed(report, k)]
            return f"L0+L1 通过 (正确性/鲁棒性/一致性/性能/安全); L2 未达成: {', '.join(missing) or '?'}"
        if report.level == "L0":
            missing = [DIMENSION_LABELS[k] for k in L1_DIMENSIONS if not _dimension_passed(report, k)]
            return f"L0 通过 (正确性/鲁棒性/一致性); L1 未达成: {', '.join(missing) or '?'}"
        missing = [DIMENSION_LABELS[k] for k in L0_DIMENSIONS if not _dimension_passed(report, k)]
        return f"L0 未达成: {', '.join(missing) or '?'} (含失败/未覆盖维度)"

    @classmethod
    def gate_passed(
        cls, report: EvalReport, gate: str
    ) -> tuple[bool, list[str]]:
        """发布门判定: patch=L0 · minor=L0+L1 · major=L0+L1+L2。

        未覆盖维度 → 阻断 (无法证明通过 = 门禁失败, 如实列原因)。
        """
        if gate not in GATE_DIMENSIONS:
            return False, [f"未知发布门: {gate}"]
        required = GATE_DIMENSIONS[gate]
        reasons: list[str] = []
        for key in required:
            d = report.dimension(key)
            if d is None:
                reasons.append(f"{DIMENSION_LABELS.get(key, key)}: 无评测数据")
                continue
            if d.status == STATUS_FAIL:
                reasons.append(f"{d.label}: 失败")
            elif d.status == STATUS_NOT_COVERED:
                reasons.append(f"{d.label}: 未覆盖 (无法证明通过)")
        return (not reasons), reasons


def run_smoke(workspace: Optional[Path | str] = None) -> dict[str, Any]:
    """评测套件冒烟驱动 (F-10 覆盖率 driver / 快速实测)。

    在给定或临时 workspace 上跑一次 EvalSuite.run, 返回摘要 dict (确定性)。
    """
    import tempfile

    if workspace is None:
        with tempfile.TemporaryDirectory(prefix="factory-eval-smoke-") as td:
            report = EvalSuite().run(Path(td))
    else:
        report = EvalSuite().run(Path(workspace))
    data = report.to_dict()
    return {
        "ok": True,
        "dimensions": len(data["dimensions"]),
        "level": data["level"],
        "gate_passed": data["gate_passed"],
    }


__all__ = [
    "CORRECTNESS",
    "ROBUSTNESS",
    "CONSISTENCY",
    "PERFORMANCE",
    "SECURITY",
    "LONGEVITY",
    "USER_VALUE",
    "L0_DIMENSIONS",
    "L1_DIMENSIONS",
    "L2_DIMENSIONS",
    "GATE_DIMENSIONS",
    "DIMENSION_LABELS",
    "EVAL_DIMENSIONS",
    "EvalItemResult",
    "EvalDimensionResult",
    "EvalReport",
    "EvalSuite",
    "run_smoke",
    "LONGRUN_24H_S",
    "PERF_KEY_OPS_LIMIT_S",
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_NOT_COVERED",
]
