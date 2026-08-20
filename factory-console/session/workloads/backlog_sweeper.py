"""factory-console/session/workloads/backlog_sweeper.py — 积压清道夫 (M1b · E3)。

Claude 战略 E3: 第一个可售卖工作负载 — 「AI 干完一件看得见的活」(本地 repo 模式)。

输入: 项目目录 (repo_mode) + issue 清单 (本地文件 `issues.json`:
      [{id, title, type}] — type: bug / feature / dependency)。

流程 (真实链路, 零 stub):
  1. 分诊 (triage): bug/feature/dependency → 修复策略
     - dependency → 确定性依赖修复器 (DependencyPatchGenerator: 真实分析
       requirements.txt / pyproject.toml, 生成可应用 unified diff)
     - bug/feature → LLM 生成 patch (llm_fn; 无 LLM → 明确 skipped, 不伪造)
  2. 执行 (execute): 复用现有 Execution Kernel — RepoModeRunner
     (理解→计划→patch 应用(Sandbox 副本, 原仓库零影响)→pytest 验证→修复)
  3. 证据包 (evidence): 复用 evidence.py — 每个修复自动组装 EvidenceBundle
     (diff+测试+日志+决策+变更文件) 落盘 projects/<slug>/evidence/ + 审计
  4. 审批 (approval): 每个成功修复自动请求审批 (复用 exec.approval.ApprovalGate
     → pending 记录入 exec store) — Human 经 `factory approval list/decide`
     决策; patch 默认不直接应用 (应用权在 Human, 设计铁律)。
  5. 报告 (report): 运行报告落盘 projects/<slug>/sweeps/sweep-<ts>.json +
     summary 文本 (`factory workload status` 只读查询)。

边界: 纯标准库; 只读消费方输入; 失败安全 (单 issue 失败/跳过不中断 sweep;
无 LLM/无测试 → 明确说明, 不静默假成功)。
"""

from __future__ import annotations

import difflib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

#: issue 清单缺省文件名 (项目目录内)
DEFAULT_ISSUES_FILE = "issues.json"
#: 运行报告目录名 (workspace/projects/<slug>/)
SWEEP_ROOT = "sweeps"
#: 需求文件优先级 (依赖修复目标)
_REQ_FILES = ("requirements.txt", "pyproject.toml")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BacklogSweepError(Exception):
    """积压清道夫失败 (项目缺失 / issue 清单缺失或损坏 / 依赖修复无法定位)。"""


# ------------------------------------------------------------------ 领域模型


@dataclass
class BacklogIssue:
    """积压 issue (输入: issues.json 条目 {id, title, type})。"""

    id: str
    title: str
    type: str = "bug"          # bug | feature | dependency

    @classmethod
    def from_dict(cls, data: Any) -> "BacklogIssue":
        data = data if isinstance(data, dict) else {}
        return cls(
            id=str(data.get("id") or "").strip() or f"ISS-{uuid.uuid4().hex[:6]}",
            title=str(data.get("title") or "").strip(),
            type=str(data.get("type") or "bug").strip().lower(),
        )


@dataclass
class TriageDecision:
    """分诊结论: issue 类型 → 修复策略 (可解释, 进报告/日志)。"""

    issue_id: str
    issue_type: str
    strategy: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "strategy": self.strategy,
            "summary": self.summary,
        }


@dataclass
class IssueOutcome:
    """单 issue 执行结果 (fixed / skipped / failed)。"""

    issue_id: str
    title: str
    issue_type: str
    status: str                  # fixed | skipped | failed
    strategy: str = ""
    reason: str = ""             # skipped/failed 原因 (可解释, 不黑盒)
    changed_files: list[str] = field(default_factory=list)
    test_ok: Optional[bool] = None
    test_output: str = ""
    bundle_id: str = ""
    approval_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "title": self.title,
            "issue_type": self.issue_type,
            "status": self.status,
            "strategy": self.strategy,
            "reason": self.reason,
            "changed_files": list(self.changed_files),
            "test_ok": self.test_ok,
            "test_output": self.test_output[-2000:],
            "bundle_id": self.bundle_id,
            "approval_id": self.approval_id,
        }


@dataclass
class SweepReport:
    """积压清道夫运行报告 (分诊/执行/证据包/审批汇总)。"""

    project: str
    issues_file: str
    total: int = 0
    triaged: int = 0
    fixed: int = 0
    skipped: int = 0
    failed: int = 0
    outcomes: list[IssueOutcome] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "issues_file": self.issues_file,
            "total": self.total,
            "triaged": self.triaged,
            "fixed": self.fixed,
            "skipped": self.skipped,
            "failed": self.failed,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "SweepReport":
        data = data if isinstance(data, dict) else {}
        outcomes = [
            IssueOutcome(
                issue_id=str(o.get("issue_id") or ""),
                title=str(o.get("title") or ""),
                issue_type=str(o.get("issue_type") or ""),
                status=str(o.get("status") or "failed"),
                strategy=str(o.get("strategy") or ""),
                reason=str(o.get("reason") or ""),
                changed_files=list(o.get("changed_files") or []),
                test_ok=o.get("test_ok"),
                test_output=str(o.get("test_output") or ""),
                bundle_id=str(o.get("bundle_id") or ""),
                approval_id=str(o.get("approval_id") or ""),
            )
            for o in (data.get("outcomes") or []) if isinstance(o, dict)
        ]
        return cls(
            project=str(data.get("project") or ""),
            issues_file=str(data.get("issues_file") or ""),
            total=int(data.get("total") or 0),
            triaged=int(data.get("triaged") or 0),
            fixed=int(data.get("fixed") or 0),
            skipped=int(data.get("skipped") or 0),
            failed=int(data.get("failed") or 0),
            outcomes=outcomes,
            created_at=str(data.get("created_at") or ""),
        )

    def summary_text(self) -> str:
        """人类可读运行报告 (CLI 输出)。"""
        lines = [
            f"积压清道夫完成: {self.project}",
            f"  issue 总数 {self.total} | 分诊 {self.triaged} | "
            f"修复 {self.fixed} | 跳过 {self.skipped} | 失败 {self.failed}",
        ]
        for o in self.outcomes:
            mark = "✅" if o.status == "fixed" else ("⏭" if o.status == "skipped" else "❌")
            line = f"  {mark} {o.issue_id} [{o.issue_type}] {o.title} — {o.status}"
            if o.changed_files:
                line += f" (变更 {len(o.changed_files)}: {', '.join(o.changed_files)})"
            if o.test_ok is True:
                line += " 测试✅"
            elif o.test_ok is False:
                line += " 测试❌"
            if o.bundle_id:
                line += f" 证据包 {o.bundle_id}"
            if o.approval_id:
                line += f" 审批 {o.approval_id}(pending)"
            lines.append(line)
            if o.reason:
                lines.append(f"      {o.reason}")
        return "\n".join(lines)


# ------------------------------------------------------------------ 分诊


def triage_issue(issue: BacklogIssue) -> TriageDecision:
    """分诊: issue 类型 → 修复策略 (确定性规则, 可解释)。

    bug       → 最小修复 (Execution Kernel + LLM patch)
    feature   → 新增能力 (Execution Kernel + LLM patch)
    dependency→ 依赖修复 (确定性依赖修复器, 无 LLM 也可真实修复)
    未知类型   → skipped (明确原因, 不猜测执行)
    """
    t = (issue.type or "").lower()
    if t == "bug":
        return TriageDecision(
            issue.id, t, "patch: 最小修复 (Execution Kernel → LLM patch)",
            "按 bug 描述生成最小修复 patch 并验证",
        )
    if t == "feature":
        return TriageDecision(
            issue.id, t, "patch: 新增能力 (Execution Kernel → LLM patch)",
            "按功能描述生成新增能力 patch 并验证",
        )
    if t == "dependency":
        return TriageDecision(
            issue.id, t, "patch: 依赖修复 (DependencyPatchGenerator 确定性)",
            "分析 requirements.txt/pyproject.toml, 确定性生成依赖修复 patch",
        )
    return TriageDecision(
        issue.id, t or "unknown", "skip: 未知 issue 类型",
        f"未知类型 {t!r} — 支持 bug/feature/dependency",
    )


# ------------------------------------------------------------------ 确定性依赖修复


#: 需求条目解析: `包名==版本` / `包名>=版本` 等 (specifier 提取)
_REQ_SPEC_RE = re.compile(
    r"([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*(==|>=|<=|~=|!=)\s*([0-9][0-9A-Za-z.\-]*)"
)
#: S10-089: 中文依赖句式 ("升级 requests 到 2.32.0" / "把 X 升级到 V" / "升级 X")
_CN_UPGRADE_RE = re.compile(
    r"(?i)(?:升级|更新|升到|升为)\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*(?:到|为|至|至到|到)\s*([0-9][0-9A-Za-z.\-]*)"
)
_CN_UPGRADE_NO_VERSION_RE = re.compile(
    r"(?i)(?:升级|更新)\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)"
)
#: 缺包短语解析: 缺少 X 依赖 / missing X / add X (包名 = 短语内首个合法包 token)
_MISSING_RE = re.compile(
    r"(?i)(缺少|缺失|缺|missing|add|依赖)\s*[:：]?\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)"
)
#: 未 pin 短语: pin/固定/锁定 某包
_PIN_RE = re.compile(r"(?i)(pin|固定|锁定|未固定)\s*[:：]?\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)")


class DependencyPatchGenerator:
    """确定性依赖修复器 (真实分析+生成可应用 diff; 非 stub)。

    能力:
    1. 缺少依赖: issue 标题含包名 (如「缺少 requests 依赖」) 且需求文件缺失
       → 追加该包 (requirements.txt 按字典序插入 / pyproject.toml 数组追加)。
    2. 未 pin: issue 标题含「pin/固定 X」且 X 已存在未 pin → 补 specifier
       (== 当前已装版本无法得知 → 用 >=0.1 语义? 不 — 确定性用 `>=0.1.0`
       最小语义版本锚点, 并在 summary 说明)。
    无法确定 (无需求文件 / 包已满足 / 标题不可解析) → 返回空 patch + 原因。
    """

    def __init__(self, default_pin: str = ">=0.1.0") -> None:
        self._default_pin = str(default_pin or ">=0.1.0")

    def generate(self, project_dir: str | Path, issue: BacklogIssue) -> tuple[str, str]:
        """生成依赖修复 patch。返回 (patch_text, 说明); 空 patch → 无法确定性修复。

        patch 为标准 unified diff (git apply 可应用; RepoModeRunner/Sandbox 复用)。
        """
        project_dir = Path(project_dir)
        req_file = self._locate_req_file(project_dir)
        if req_file is None:
            return "", "未发现需求文件 (requirements.txt/pyproject.toml) — 无法确定性修复"
        title = issue.title or ""
        spec = _REQ_SPEC_RE.search(title)
        if spec is not None:
            name, op, version = spec.group(1), spec.group(2), spec.group(3)
            return self._add_or_update(req_file, f"{name}{op}{version}", issue)
        # S10-089: 中文句式 ("升级 requests 到 2.32.0" → requests>=2.32.0)
        cn = _CN_UPGRADE_RE.search(title)
        if cn is not None:
            name, version = cn.group(1), cn.group(2)
            return self._add_or_update(req_file, f"{name}>={version}", issue)
        cn2 = _CN_UPGRADE_NO_VERSION_RE.search(title)
        if cn2 is not None:
            name = cn2.group(1)
            return self._pin(req_file, name, issue)
        missing = _MISSING_RE.search(title)
        if missing is not None:
            name = missing.group(2)
            return self._add_or_update(req_file, name, issue)
        pin = _PIN_RE.search(title)
        if pin is not None:
            name = pin.group(2)
            return self._pin(req_file, name, issue)
        return "", f"issue 标题无法解析依赖意图: {title!r}"

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _locate_req_file(project_dir: Path) -> Optional[Path]:
        """定位需求文件 (requirements.txt 优先, pyproject.toml 兜底)。"""
        for name in _REQ_FILES:
            cand = project_dir / name
            if cand.is_file():
                return cand
        return None

    def _add_or_update(self, req_file: Path, entry: str, issue: BacklogIssue) -> tuple[str, str]:
        """追加/更新需求条目 (已存在且满足 → 空 patch + 说明; 幂等)。"""
        name = entry.split("=")[0].split("<")[0].split(">")[0].split("~")[0].split("!")[0]
        if req_file.name == "requirements.txt":
            old_lines, new_lines, changed = self._requirements_apply(
                req_file, name, entry
            )
        else:
            old_lines, new_lines, changed = self._pyproject_apply(req_file, name, entry)
        if not changed:
            return "", f"依赖已满足: {entry} (无变更, 幂等)"
        patch = self._unified_diff(req_file.name, old_lines, new_lines)
        return patch, f"依赖修复: {entry} → {req_file.name}"

    def _pin(self, req_file: Path, name: str, issue: BacklogIssue) -> tuple[str, str]:
        """给已有未 pin 包补 specifier (确定性: == 无法得知 → >= 语义锚点)。"""
        if req_file.name == "requirements.txt":
            old_lines = [ln.rstrip("\n") for ln in req_file.read_text(encoding="utf-8").splitlines()]
            new_lines = []
            for ln in old_lines:
                stripped = ln.strip()
                if stripped and not stripped.startswith("#") and stripped.split("=")[0].split("<")[0].split(">")[0].split("~")[0].split("!")[0].strip() == name and "=" not in ln and ">" not in ln and "<" not in ln and "~" not in ln:
                    new_lines.append(f"{ln}{self._default_pin}")
                else:
                    new_lines.append(ln)
            if new_lines == old_lines:
                return "", f"未发现可 pin 的 {name} 或已 pin — 无变更"
            patch = self._unified_diff(req_file.name, old_lines, new_lines)
            return patch, f"依赖 pin: {name}{self._default_pin} → {req_file.name}"
        return "", "pyproject.toml 未 pin 检测暂不支持 — 请用 requirements.txt"

    @staticmethod
    def _requirements_apply(req_file: Path, name: str, entry: str) -> tuple[list[str], list[str], bool]:
        """requirements.txt 应用: 已含同名条目 → 无变更; 否则字典序插入。"""
        raw = req_file.read_text(encoding="utf-8")
        old_lines = raw.splitlines() if raw.strip() else []
        existing = {
            _entry_name(ln) for ln in old_lines
            if ln.strip() and not ln.lstrip().startswith("#")
        }
        if name in existing:
            # S10-089: 同名条目 — 已满足目标 → 幂等; 否则版本升级 (替换)
            target_norm = entry.strip()
            # 裸包名 (无 specifier) → 已存在即满足
            if "=" not in target_norm and ">" not in target_norm and "<" not in target_norm and "~" not in target_norm and "!" not in target_norm:
                return old_lines, list(old_lines), False
            cur_line = None
            for ln in old_lines:
                if not ln.lstrip().startswith("#") and _entry_name(ln) == name:
                    cur_line = ln.strip()
                    break
            if cur_line is not None and _version_satisfies(cur_line, target_norm):
                return old_lines, list(old_lines), False
            new_lines = [
                target_norm if (not ln.lstrip().startswith("#") and _entry_name(ln) == name) else ln
                for ln in old_lines
            ]
            return old_lines, new_lines, True
        new_lines = list(old_lines)
        insert_at = len(new_lines)
        for i, ln in enumerate(new_lines):
            if ln.strip() and not ln.lstrip().startswith("#") and _entry_name(ln) > name:
                insert_at = i
                break
        new_lines.insert(insert_at, entry)
        return old_lines, new_lines, True

    @staticmethod
    def _pyproject_apply(req_file: Path, name: str, entry: str) -> tuple[list[str], list[str], bool]:
        """pyproject.toml 应用: [project] dependencies 数组追加 (tomllib 只读解析)。

        失败安全: 解析失败/无 dependencies → 无变更 (返回 False, 调用方说明)。
        """
        old_lines = req_file.read_text(encoding="utf-8").splitlines()
        try:
            import tomllib

            data = tomllib.loads("\n".join(old_lines))
        except Exception:  # noqa: BLE001 — 解析失败 → 无法确定性修改
            return old_lines, list(old_lines), False
        deps = data.get("project", {}).get("dependencies")
        if not isinstance(deps, list):
            return old_lines, list(old_lines), False
        if any(_entry_name(str(d)) == name for d in deps if isinstance(d, str)):
            return old_lines, list(old_lines), False
        # 找 dependencies 数组最后一行, 在其后插入 (字符串条目; 缩进跟随)
        new_lines = list(old_lines)
        insert_idx = -1
        indent = "    "
        in_deps = False
        for i, ln in enumerate(old_lines):
            stripped = ln.strip()
            if stripped.startswith("dependencies") and "=" in stripped and "[" in stripped:
                in_deps = True
                continue
            if in_deps and (stripped == "]" or stripped.startswith("]")):
                insert_idx = i
                break
            if in_deps and stripped:
                indent = ln[: len(ln) - len(ln.lstrip())]
        if insert_idx < 0:
            return old_lines, list(old_lines), False
        new_lines.insert(insert_idx, f"{indent}\"{entry}\",")
        return old_lines, new_lines, True

    @staticmethod
    def _unified_diff(filename: str, old_lines: list[str], new_lines: list[str]) -> str:
        """标准 unified diff (git apply 可应用; a/ b/ 前缀可选)。"""
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"a/{filename}", tofile=f"b/{filename}",
            lineterm=""
        )
        text = "\n".join(diff)
        return text + ("\n" if text else "")


def _entry_name(line: str) -> str:
    """需求条目 → 包名 (去 specifier/空白/注释)。"""
    text = line.strip()
    if text.startswith("#"):
        return ""
    for op in ("==", ">=", "<=", "~=", "!=", ">", "<", "=", "~"):
        if op in text:
            text = text.split(op)[0]
    return text.strip()


def _ver_tuple(v: str) -> tuple:
    """版本 → 比较元组 (数字段优先, 字母段兜底)。"""
    parts: list = []
    for seg in str(v).strip().lstrip("=<>~!^ ").split("."):
        parts.append(int(seg) if seg.isdigit() else seg)
    return tuple(parts)


def _version_satisfies(cur_line: str, target: str) -> bool:
    """启发式满足判断: 当前条目是否满足目标 specifier (==/>=/<=)。

    无法解析 → False (保守: 走更新)。
    """
    m = re.match(
        r"\s*([A-Za-z0-9_][A-Za-z0-9_.\-]*)\s*(==|>=|<=|~=|!=)\s*([0-9][0-9A-Za-z.\-]*)",
        target,
    )
    if m is None:
        return False
    op, spec_v = m.group(2), m.group(3)
    cur_m = re.match(
        r"\s*[A-Za-z0-9_][A-Za-z0-9_.\-]*\s*(==|>=|<=|~=)?\s*([0-9][0-9A-Za-z.\-]*)",
        cur_line,
    )
    if cur_m is None:
        return False
    cur_v = cur_m.group(2)
    try:
        c, s = _ver_tuple(cur_v), _ver_tuple(spec_v)
    except Exception:  # noqa: BLE001
        return False
    if op == "==":
        return c == s
    if op == ">=":
        return c >= s
    if op == "<=":
        return c <= s
    return False


# ------------------------------------------------------------------ 积压清道夫


class BacklogSweeper:
    """积压清道夫编排: 分诊 → 执行 (Execution Kernel) → 证据包 → 审批 → 报告。

    构造:
    - workspace: 工厂数据根 (证据包/报告/审批落盘; None → 纯内存, 不持久化)
    - llm_fn: (prompt, operation) -> str — bug/feature patch 生成的 LLM 来源
      (无 → dependency 仍可确定性修复, bug/feature 明确 skipped)
    - execute_fn: 可插拔执行内核 (缺省 RepoModeRunner — 复用现有 Execution
      Kernel; 测试可注入桩内核, 生产零 stub)
    - approval_gate/exec_store: 审批门 (缺省按 workspace 装配 exec
      ApprovalGate + ExecStore; None → 不请求审批)
    """

    def __init__(
        self,
        workspace: Any = None,
        *,
        llm_fn: Optional[Callable[[str, str], str]] = None,
        execute_fn: Optional[Callable[..., Any]] = None,
        approval_gate: Any = None,
        exec_store: Any = None,
        dep_fixer: Optional[DependencyPatchGenerator] = None,
    ) -> None:
        self.workspace = Path(workspace) if workspace is not None else None
        self.llm_fn = llm_fn if callable(llm_fn) else None
        self.execute_fn = execute_fn if callable(execute_fn) else None
        self._approval_gate = approval_gate
        self._exec_store = exec_store
        self.dep_fixer = dep_fixer if dep_fixer is not None else DependencyPatchGenerator()

    # ------------------------------------------------------------------ 主入口

    def sweep(
        self,
        project_dir: str | Path,
        *,
        issues_file: str | Path = DEFAULT_ISSUES_FILE,
        limit: Optional[int] = None,
        request_approval: bool = True,
    ) -> SweepReport:
        """执行一轮积压清道夫 (完整链路, 失败安全)。

        - 项目/issue 清单缺失或损坏 → BacklogSweepError (响亮, 不静默空跑)
        - 单 issue 失败/跳过 → 记入 outcomes, 不中断整体 sweep
        """
        project_dir = Path(project_dir)
        if not project_dir.is_dir():
            raise BacklogSweepError(f"项目目录不存在: {project_dir}")
        issues_path = Path(issues_file)
        if not issues_path.is_absolute():
            issues_path = project_dir / issues_path
        issues = self._load_issues(issues_path)
        if limit is not None:
            issues = issues[: max(0, int(limit))]
        report = SweepReport(
            project=str(project_dir.resolve()),
            issues_file=str(issues_path),
            created_at=_now_iso(),
        )
        for issue in issues:
            report.total += 1
            decision = triage_issue(issue)
            report.triaged += 1
            try:
                outcome = self._process_issue(
                    project_dir, issue, decision, request_approval=request_approval
                )
            except Exception as exc:  # noqa: BLE001 — 单 issue 失败安全
                outcome = IssueOutcome(
                    issue_id=issue.id, title=issue.title, issue_type=issue.type,
                    status="failed", strategy=decision.strategy,
                    reason=f"执行异常: {exc}",
                )
            report.outcomes.append(outcome)
            if outcome.status == "fixed":
                report.fixed += 1
            elif outcome.status == "skipped":
                report.skipped += 1
            else:
                report.failed += 1
        self._save_report(project_dir, report)
        return report

    def status(self, project_dir: str | Path) -> Optional[SweepReport]:
        """最近一次运行报告 (只读; 无报告 → None)。"""
        if self.workspace is None:
            return None
        slug = Path(project_dir).resolve().name or "repo"
        root = self.workspace / "projects" / str(slug) / SWEEP_ROOT
        if not root.is_dir():
            return None
        files = sorted(root.glob("sweep-*.json"))
        if not files:
            return None
        try:
            return SweepReport.from_dict(
                json.loads(files[-1].read_text(encoding="utf-8"))
            )
        except Exception:  # noqa: BLE001 — 损坏 → None (失败安全)
            return None

    # ------------------------------------------------------------------ 内部

    @staticmethod
    def _load_issues(path: Path) -> list[BacklogIssue]:
        """读取 issues.json (缺失/损坏 → 响亮 BacklogSweepError)。"""
        if not path.is_file():
            raise BacklogSweepError(f"issue 清单不存在: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — 损坏 → 响亮
            raise BacklogSweepError(f"issue 清单损坏: {path}: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("issues") or []
        if not isinstance(data, list):
            raise BacklogSweepError(f"issue 清单结构非法 (需 list 或 {{issues: [...]}}): {path}")
        return [BacklogIssue.from_dict(item) for item in data if isinstance(item, dict)]

    def _process_issue(
        self,
        project_dir: Path,
        issue: BacklogIssue,
        decision: TriageDecision,
        *,
        request_approval: bool,
    ) -> IssueOutcome:
        """单 issue: 生成 patch → Execution Kernel 执行 → 证据包 → 审批请求。"""
        outcome = IssueOutcome(
            issue_id=issue.id, title=issue.title, issue_type=issue.type,
            status="skipped", strategy=decision.strategy,
        )
        patch_text, reason = self._generate_patch(project_dir, issue, decision)
        if not patch_text or not patch_text.strip():
            outcome.reason = reason or "未生成 patch"
            return outcome
        # 执行内核 (缺省 RepoModeRunner): 理解→计划→patch 应用→测试→证据包
        result = self._execute(project_dir, issue, decision, patch_text)
        if result.error:
            outcome.status = "failed"
            outcome.reason = result.error
            outcome.test_output = getattr(result, "test_output", "") or ""
            return outcome
        outcome.status = "fixed"
        outcome.changed_files = list(getattr(result, "changed_files", []) or [])
        outcome.test_ok = getattr(result, "test_ok", None)
        outcome.test_output = str(getattr(result, "test_output", "") or "")
        outcome.bundle_id = self._latest_bundle_id(project_dir, result)
        # 审批请求 (复用 ApprovalGate; Human 决定, 不自动应用)
        if request_approval:
            outcome.approval_id = self._request_approval(project_dir, issue, patch_text)
        return outcome

    def _generate_patch(
        self, project_dir: Path, issue: BacklogIssue, decision: TriageDecision
    ) -> tuple[str, str]:
        """按分诊策略生成 patch:
        dependency → 确定性依赖修复器 (无 LLM 也能真实修复);
        bug/feature → llm_fn (无 LLM → 明确 skipped)。"""
        if issue.type == "dependency":
            patch, reason = self.dep_fixer.generate(project_dir, issue)
            return patch, reason
        if self.llm_fn is None:
            return "", (
                f"{decision.summary} — 无可用 LLM Provider (未配置或装配失败); "
                "配置 LLM 后可自动修复 (dependency issue 无需 LLM)"
            )
        try:
            prompt = (
                f"项目: {project_dir}\n"
                f"issue: [{issue.type}] {issue.title}\n"
                "请输出最小 unified diff (git apply 可应用, 只改必要文件, "
                "保持现有风格, 不引入新依赖)。只输出 diff, 不要解释。"
            )
            text = str(self.llm_fn(prompt, "backlog_patch") or "").strip()
            if not text:
                return "", "LLM 未返回 patch (空输出) — 请重试或配置更好的模型"
            # git apply 要求 patch 文件以换行结尾 — strip() 已去尾, 补回
            return text + "\n", f"LLM 生成 patch ({issue.type})"
        except Exception as exc:  # noqa: BLE001 — LLM 失败 → 明确跳过, 不伪造
            return "", f"LLM patch 生成失败: {exc}"

    def _execute(
        self, project_dir: Path, issue: BacklogIssue, decision: TriageDecision, patch_text: str
    ) -> Any:
        """执行内核: 缺省 RepoModeRunner (复用 M1 repo_mode Execution Kernel)。"""
        if self.execute_fn is not None:
            return self.execute_fn(project_dir, issue, decision, patch_text)
        from ..repo_mode import RepoModeRunner

        runner = RepoModeRunner(llm_fn=self.llm_fn)
        slug = project_dir.resolve().name or "repo"
        kwargs: dict[str, Any] = {}
        if self.workspace is not None:
            kwargs = {"evidence_workspace": self.workspace, "evidence_slug": slug}
        return runner.run(
            project_dir, f"[{issue.type}] {issue.title}",
            patch_text=patch_text, **kwargs,
        )

    def _latest_bundle_id(self, project_dir: Path, result: Any) -> str:
        """本轮执行产出的证据包 id (evidence store 最新一条; 失败安全 → "")。"""
        try:
            if self.workspace is None:
                return ""
            slug = project_dir.resolve().name or "repo"
            from ..evidence import EvidenceStore

            bundles = EvidenceStore(self.workspace, slug).list()
            return bundles[-1].bundle_id if bundles else ""
        except Exception:  # noqa: BLE001 — 证据定位失败安全
            return ""

    def _request_approval(self, project_dir: Path, issue: BacklogIssue, patch_text: str) -> str:
        """复用 ApprovalGate: 执行结果 → pending 审批记录 (不自动应用)。"""
        if self._approval_gate is None:
            gate, store = self._build_approval()
            if gate is None:
                return ""
            self._approval_gate, self._exec_store = gate, store
        return self._request_approval_impl(project_dir, issue, patch_text)

    # ------------------------------------------------------------------ 审批 (复用 exec ApprovalGate)

    def _build_approval(self) -> tuple[Any, Any]:
        """装配 exec ApprovalGate + ExecStore (失败 → (None, None), 不抛)。

        factory-exec 目录须已在 sys.path (CLI 经 cli_factory._proxy_exec_cli
        挂载; 测试自行挂载)。exec 不可用 → 不请求审批, 不中断 sweep。
        """
        if self.workspace is None:
            return None, None
        try:
            from exec.store import ExecStore
            from exec.approval import ApprovalGate

            store = ExecStore(self.workspace / "exec")
            return ApprovalGate(store), store
        except Exception:  # noqa: BLE001 — exec 不可用 → 不请求审批 (不中断 sweep)
            return None, None

    def _request_approval_impl(self, project_dir: Path, issue: BacklogIssue, patch_text: str) -> str:
        """构造 ExecutionRequest/Result + patch artifact → ApprovalGate.request。

        返回 approval_id; 失败安全 → "" (不中断 sweep, 证据包仍可见)。
        """
        try:
            from exec.store import ExecStore
            from exec.approval import ApprovalGate
            from exec.models import (
                Artifact, ArtifactType, ExecutionRequest, ExecutionResult,
                ExecutionStatus, new_id,
            )
            store = (
                self._exec_store
                if self._exec_store is not None
                else ExecStore(self.workspace / "exec")
            )
            gate = (
                self._approval_gate
                if self._approval_gate is not None
                else ApprovalGate(store)
            )
            request = ExecutionRequest(
                id=new_id("EXR"),
                task_id=issue.id,
                objective=f"[{issue.type}] {issue.title}",
                input={
                    "project_dir": str(project_dir.resolve()),
                    "source": "backlog_sweeper",
                },
            )
            patch_path = self.workspace / "exec" / "patches" / f"{request.id}.patch"
            patch_path.parent.mkdir(parents=True, exist_ok=True)
            patch_path.write_text(patch_text, encoding="utf-8")
            result = ExecutionResult(
                id=new_id("EXS"),
                request_id=request.id,
                status=ExecutionStatus.SUCCESS,
                artifacts=[
                    Artifact(
                        id=new_id("ART"), type=ArtifactType.PATCH,
                        task_id=issue.id, path=str(patch_path),
                    )
                ],
                report=f"backlog sweep: {issue.id}",
            )
            store.save_request(request)
            store.save_result(result)
            record = gate.request(result)
            return record.id
        except Exception:  # noqa: BLE001 — 审批请求失败安全 (不伪造成功)
            return ""

    # ------------------------------------------------------------------ 报告落盘

    def _save_report(self, project_dir: Path, report: SweepReport) -> None:
        """运行报告落盘 projects/<slug>/sweeps/sweep-<ts>.json (失败安全)。"""
        if self.workspace is None:
            return
        try:
            slug = project_dir.resolve().name or "repo"
            root = self.workspace / "projects" / str(slug) / SWEEP_ROOT
            root.mkdir(parents=True, exist_ok=True)
            ts = report.created_at.replace(":", "-").replace("+00:00", "Z")
            (root / f"sweep-{ts}.json").write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 报告落盘失败安全
            pass
