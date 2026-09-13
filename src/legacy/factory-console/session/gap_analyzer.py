"""factory-console/session/gap_analyzer.py — GapAnalyzer (S10-061 批次 A)。

Autonomous Gap Resolution 模型层: 观察执行上下文 → 结构化 Gap 分析
(GAP G1/G9, 设计 §2)。GapAnalyzer 消费 项目上下文 / 工作区 / 当前任务 /
执行结果 / 验证结果 / artifacts / Agent 输出 / 失败列表 / 已有任务 /
依赖图 / 历史重规划决策 → 输出 GapAnalysis {detected, gap_type, description,
evidence, severity, source_task_id, confidence, duplicate_of,
recommended_action, reason, timestamp}, 落盘 gap_analysis.json (append,
可解释性资产 — GAP G9)。

gap_type (9 种, 设计 §2):
- missing_requirement  需求缺口 (requirement/需求变更 信号)
- missing_implementation  实现缺口 (persistence/持久化/存储 信号)
- missing_test          测试缺口 (missing_test/test/测试缺失 信号)
- validation_failure    验证失败 (validation.success=False, 最高优先级)
- dependency_gap        依赖缺口 (dependency/依赖缺失 信号)
- integration_gap       集成缺口 (integration/集成/联调 信号)
- architecture_gap      架构缺口 (architecture/架构 信号 → 高安全风险)
- ui_gap                UI 缺口 (ui/界面/前端 信号)
- unknown               任务失败但无明确信号 (→ 人工评审)

recommended_action (6 种): NO_ACTION/REPAIR/MODIFY_TASK/INSERT_TASK/
BLOCK/REQUEST_REVIEW。

信号规则 (deterministic, 优先级从高到低):
1. validation.success is False        → validation_failure → REPAIR
2. agent_output 命中 missing_test 信号 → missing_test      → INSERT_TASK
3. agent_output 命中 persistence 信号  → missing_implementation → INSERT_TASK
4. agent_output 命中 requirement 信号  → missing_requirement → INSERT_TASK
5. agent_output 命中 dependency 信号   → dependency_gap     → INSERT_TASK
6. agent_output 命中 integration 信号  → integration_gap    → INSERT_TASK
7. agent_output 命中 ui 信号           → ui_gap             → INSERT_TASK
8. agent_output 命中 architecture 信号 → architecture_gap   → REQUEST_REVIEW
9. 有失败但无信号                      → unknown             → REQUEST_REVIEW
10. 无失败且无信号                      → detected=False      → NO_ACTION

severity/confidence 推导 (信号强度): 每种 gap_type 有基础 severity/confidence,
命中信号词越多 / 证据来源越多 → confidence 递增 (封顶 0.95);
duplicate_of: 相同 (source_task_id, gap_type) 已在本文件分析过, 或
prev_decisions 已对该 source 任务 INSERT_TASK → 重复 (GAP G6 防重)。

边界 (批次 A 模型层):
- 纯标准库 (json/re/dataclasses/datetime/pathlib), 零模块依赖, 失败安全
  (record/previous_analyses 读写异常 → 不抛)
- 只做分析 + 资产化, 不生成任务 (TaskProposalEngine 在 task_proposal.py),
  不修改 DAG/计划 (批次 B 集成)

设计: docs/sprint10/S10-061-gap-analysis.md (G1/G9) +
docs/sprint10/S10-061-autonomous-task-proposal-design.md §2
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 缺省 gap 分析资产文件 (~/.factory/teams/gap_analysis.json — 设计 §7 资产口径;
#: 项目级记录 → projects/<slug>/gap_analysis.json, 由调用方显式指定)
DEFAULT_GAP_FILE = Path.home() / ".factory" / "teams" / "gap_analysis.json"

#: 项目级 gap 分析文件名 (projects/<slug>/gap_analysis.json — S10-061 资产)
GAP_ANALYSIS_FILE_NAME = "gap_analysis.json"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (分析时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GapAnalysis:
    """结构化 Gap 分析 (设计 §2 输出): 全字段 + to_dict/from_dict。

    detected:           是否检测到缺口 (False → NO_ACTION, 无缺口)
    gap_type:           9 种缺口类型之一 (missing_requirement/.../unknown)
    description:        人类可读缺口描述
    evidence:           证据列表 (验证结果/信号词/失败上下文/来源)
    severity:           low/medium/high/critical (信号强度推导)
    source_task_id:     触发缺口的来源任务 id (当前任务或失败任务)
    confidence:         0.0-1.0 (信号强度推导, 封顶 0.95)
    duplicate_of:       重复来源 (相同 source_task_id+gap_type 已分析 /
                        prev_decisions 已 INSERT_TASK); None = 非重复
    recommended_action: 6 种建议动作之一 (NO_ACTION/REPAIR/MODIFY_TASK/
                        INSERT_TASK/BLOCK/REQUEST_REVIEW)
    reason:             可解释原因 (为什么判定该缺口)
    timestamp:          分析时间 (UTC ISO — 资产落盘用)
    """

    detected: bool = False
    gap_type: str = ""
    description: str = ""
    evidence: list[str] = field(default_factory=list)
    severity: str = "low"
    source_task_id: str = ""
    confidence: float = 0.0
    duplicate_of: Optional[str] = None
    recommended_action: str = "NO_ACTION"
    reason: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 gap_analysis.json / 审计视图)。"""
        return {
            "detected": bool(self.detected),
            "gap_type": str(self.gap_type or ""),
            "description": str(self.description or ""),
            "evidence": [str(e) for e in (self.evidence or []) if e is not None],
            "severity": str(self.severity or "low"),
            "source_task_id": str(self.source_task_id or ""),
            "confidence": round(float(self.confidence or 0.0), 2),
            "duplicate_of": (
                str(self.duplicate_of) if self.duplicate_of is not None else None
            ),
            "recommended_action": str(self.recommended_action or "NO_ACTION"),
            "reason": str(self.reason or ""),
            "timestamp": str(self.timestamp or _now_iso()),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "GapAnalysis":
        """dict → GapAnalysis (缺失字段默认 — 前向兼容/失败安全)。"""
        if not isinstance(data, dict):
            return cls()
        gtype = str(data.get("gap_type") or "")
        if gtype and gtype not in GapAnalyzer.GAP_TYPES:
            gtype = "unknown"
        action = str(data.get("recommended_action") or "NO_ACTION")
        if action not in GapAnalyzer.ACTIONS:
            action = "NO_ACTION"
        sev = str(data.get("severity") or "low")
        if sev not in GapAnalyzer.SEVERITIES:
            sev = "low"
        return cls(
            detected=bool(data.get("detected")),
            gap_type=gtype,
            description=str(data.get("description") or ""),
            evidence=[
                str(e) for e in (data.get("evidence") or []) if e is not None
            ],
            severity=sev,
            source_task_id=str(data.get("source_task_id") or ""),
            confidence=float(data.get("confidence") or 0.0),
            duplicate_of=(
                str(data["duplicate_of"])
                if data.get("duplicate_of") is not None
                else None
            ),
            recommended_action=action,
            reason=str(data.get("reason") or ""),
            timestamp=str(data.get("timestamp") or ""),
        )


class GapAnalyzer:
    """结构化 Gap 分析器 (S10-061 批次 A): 执行上下文 → GapAnalysis。

    analyze(): 按优先级规则 (验证失败 → 测试 → 实现 → 需求 → 依赖 →
    集成 → UI → 架构 → unknown) 检测缺口, 推导 severity/confidence/
    recommended_action, 检测重复 (duplicate_of); 每次分析可 record 落盘
    gap_analysis.json (append — 缺口历史资产, GAP G9)。
    record()/previous_analyses() 失败安全 (缺失/损坏 → 空, 永不抛)。
    """

    #: 9 种缺口类型 (设计 §2)
    GAP_TYPES: tuple[str, ...] = (
        "missing_requirement",
        "missing_implementation",
        "missing_test",
        "validation_failure",
        "dependency_gap",
        "integration_gap",
        "architecture_gap",
        "ui_gap",
        "unknown",
    )

    #: 6 种建议动作 (设计 §2)
    ACTIONS: tuple[str, ...] = (
        "NO_ACTION",
        "REPAIR",
        "MODIFY_TASK",
        "INSERT_TASK",
        "BLOCK",
        "REQUEST_REVIEW",
    )

    #: 4 级严重度
    SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")

    #: 项目级缺口分析文件名 (projects/<slug>/gap_analysis.json — S10-061 资产)
    FILE_NAME = GAP_ANALYSIS_FILE_NAME

    # ------------------------------------------------------------ 信号表
    #: 测试缺口信号 (re: 前缀 = 正则, 其余 = 子串; 短英文词用词边界防误报:
    #: "latest/contest" 含 "test" 但不命中 \btest)
    MISSING_TEST_MARKERS: tuple[str, ...] = (
        "missing_test",
        "missing test",
        "needs test",
        "need tests",
        "测试缺失",
        "缺测试",
        "没有测试",
        "无测试",
        "re:\\btest",
    )

    #: 实现缺口信号 (persistence/持久化/存储)
    MISSING_IMPLEMENTATION_MARKERS: tuple[str, ...] = (
        "missing implementation",
        "persistence",
        "持久化",
        "存储",
        "未实现",
        "没有实现",
        "not implemented",
    )

    #: 需求缺口信号 (requirement/需求变更)
    MISSING_REQUIREMENT_MARKERS: tuple[str, ...] = (
        "missing requirement",
        "requirement",
        "requirements",
        "需求变更",
        "需求缺失",
        "缺需求",
        "没有需求",
    )

    #: 依赖缺口信号 (dependency/依赖缺失)
    DEPENDENCY_MARKERS: tuple[str, ...] = (
        "missing dependency",
        "dependency",
        "dependencies",
        "依赖缺失",
        "缺依赖",
        "缺少依赖",
        "没有依赖",
    )

    #: 集成缺口信号 (integration/集成/联调)
    INTEGRATION_MARKERS: tuple[str, ...] = (
        "integration",
        "集成",
        "联调",
        "对接",
    )

    #: UI 缺口信号 (ui/界面/前端; "ui" 词边界防误报: "build/guide" 含 ui 不命中)
    UI_MARKERS: tuple[str, ...] = (
        "re:\\bui\\b",
        "界面",
        "前端",
        "frontend",
        "ui 缺失",
    )

    #: 架构缺口信号 (architecture/架构 — 高风险 → REQUEST_REVIEW)
    ARCHITECTURE_MARKERS: tuple[str, ...] = (
        "architecture",
        "架构",
        "架构缺陷",
        "设计缺陷",
    )

    #: gap_type → (基础 severity, 基础 confidence, recommended_action)
    #: (severity/confidence 信号强度推导基准, 设计 §2)
    TYPE_PROFILE: dict[str, tuple[str, float, str]] = {
        "missing_requirement": ("medium", 0.75, "INSERT_TASK"),
        "missing_implementation": ("high", 0.80, "INSERT_TASK"),
        "missing_test": ("medium", 0.80, "INSERT_TASK"),
        "validation_failure": ("high", 0.90, "REPAIR"),
        "dependency_gap": ("high", 0.85, "INSERT_TASK"),
        "integration_gap": ("medium", 0.70, "INSERT_TASK"),
        "architecture_gap": ("critical", 0.65, "REQUEST_REVIEW"),
        "ui_gap": ("low", 0.70, "INSERT_TASK"),
        "unknown": ("medium", 0.40, "REQUEST_REVIEW"),
    }

    #: confidence 封顶 (信号再强也不满额 — 保留人工评审空间)
    CONFIDENCE_CAP = 0.95

    #: gap_type → 信号表 (信号强度推导用)
    MARKERS: dict[str, tuple[str, ...]] = {
        "missing_test": MISSING_TEST_MARKERS,
        "missing_implementation": MISSING_IMPLEMENTATION_MARKERS,
        "missing_requirement": MISSING_REQUIREMENT_MARKERS,
        "dependency_gap": DEPENDENCY_MARKERS,
        "integration_gap": INTEGRATION_MARKERS,
        "ui_gap": UI_MARKERS,
        "architecture_gap": ARCHITECTURE_MARKERS,
    }

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_GAP_FILE

    # ------------------------------------------------------------ 分析

    def analyze(
        self,
        project: Any = None,
        workspace: Optional[dict[str, Any]] = None,
        task: Optional[dict[str, Any]] = None,
        result: Optional[dict[str, Any]] = None,
        validation: Optional[dict[str, Any]] = None,
        artifacts: Any = None,
        agent_output: Optional[str] = None,
        failures: Optional[list[dict[str, Any]]] = None,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
        dag: Any = None,
        prev_decisions: Optional[list[dict[str, Any]]] = None,
    ) -> GapAnalysis:
        """对执行上下文产出结构化 Gap 分析 (设计 §2 规则, 优先级从高到低)。

        project:        项目上下文 dict (仅 reason/evidence 引用);
        workspace:      工作区上下文 dict (WorkspaceContext 数据, 仅引用);
        task:           当前任务记录 dict ({id, name, ...});
        result:         执行结果 dict ({success?, agent_output?, output?, error?});
        validation:     验证结果 dict ({success?, errors?});
        artifacts:      artifacts (dict/list, 仅引用);
        agent_output:   Agent 输出文本 (缺口信号来源);
        failures:       失败任务上下文 [{task_id, name, error}];
        existing_tasks: 已有计划任务列表 (仅 duplicate 参考);
        dag:            依赖图 (鸭子类型, 仅引用);
        prev_decisions: 历史重规划决策列表 (INSERT_TASK 已处理 → duplicate_of)。

        返回 GapAnalysis (全字段 + timestamp)。
        """
        task = task if isinstance(task, dict) else {}
        result = result if isinstance(result, dict) else {}
        validation = validation if isinstance(validation, dict) else {}
        failures = [f for f in (failures or []) if isinstance(f, dict)]
        workspace = workspace if isinstance(workspace, dict) else {}
        prev_decisions = [d for d in (prev_decisions or []) if isinstance(d, dict)]
        output = self._collect_output(agent_output, result)

        # 来源任务: 当前任务 id → 首个失败任务 task_id → 空
        sid = str(task.get("id") or "")
        if not sid and failures:
            sid = str(failures[0].get("task_id") or "")
        sname = str(task.get("name") or "")
        if not sname and failures:
            sname = str(failures[0].get("name") or "")

        # ---- 规则 1: 验证失败 (validation.success is False) → validation_failure
        if validation.get("success") is False:
            return self._build(
                gtype="validation_failure",
                sid=sid,
                sname=sname,
                output=output,
                validation=validation,
                failures=failures,
                prev_decisions=prev_decisions,
            )

        # ---- 规则 2-8: Agent 输出信号 (优先级: 测试 → 实现 → 需求 → 依赖 →
        # ----           集成 → UI → 架构)
        for gtype, markers in self.MARKERS.items():
            hit = self._marker_hit(output, markers)
            if hit:
                return self._build(
                    gtype=gtype,
                    sid=sid,
                    sname=sname,
                    output=output,
                    validation=validation,
                    failures=failures,
                    hit=hit,
                    prev_decisions=prev_decisions,
                )

        # ---- 规则 9: 有失败但无信号 → unknown (REQUEST_REVIEW — 安全兜底)
        if failures:
            return self._build(
                gtype="unknown",
                sid=sid,
                sname=sname,
                output=output,
                validation=validation,
                failures=failures,
                prev_decisions=prev_decisions,
            )

        # ---- 规则 10: 无失败且无信号 → 无缺口 (NO_ACTION)
        return GapAnalysis(
            detected=False,
            gap_type="",
            description="未检测到缺口: 无验证失败、无失败任务、Agent 输出无缺口信号",
            evidence=[f"agent_output={output[:120]!r}" if output else "agent_output 为空"],
            severity="low",
            source_task_id=sid,
            confidence=0.0,
            duplicate_of=None,
            recommended_action="NO_ACTION",
            reason="无失败/验证通过/无信号 — 计划无需调整 (NO_ACTION)",
            timestamp=_now_iso(),
        )

    # ------------------------------------------------------------ 记录/读回

    def record(self, analysis: Any) -> dict[str, Any]:
        """append 落盘 gap_analysis.json (失败安全: 读写异常 → 不抛)。"""
        obj = self._normalize(analysis)
        records = self.previous_analyses()
        records.append(obj)
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全: 落盘失败不中断分析流
            pass
        return obj

    def previous_analyses(self) -> list[dict[str, Any]]:
        """读回全部 gap 分析记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [self._normalize(d) for d in data if isinstance(d, dict)]
        except Exception:  # noqa: BLE001 — 失败安全: 缺失/损坏 → 空记录
            pass
        return []

    def analyses_for(self, task_id: str) -> list[dict[str, Any]]:
        """某任务相关的全部历史 gap 分析 (source_task_id == task_id)。"""
        key = str(task_id)
        return [
            a for a in self.previous_analyses() if a.get("source_task_id") == key
        ]

    def analyses_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    # ------------------------------------------------------------ 内部

    @classmethod
    def _normalize(cls, analysis: Any) -> dict[str, Any]:
        """GapAnalysis/dict → 归一化 dict (缺失字段失败安全缺省)。"""
        if isinstance(analysis, GapAnalysis):
            analysis = analysis.to_dict()
        if not isinstance(analysis, dict):
            return cls._no_gap().to_dict()
        return GapAnalysis.from_dict(analysis).to_dict()

    @classmethod
    def _no_gap(cls) -> GapAnalysis:
        """缺省无缺口分析 (归一化兜底)。"""
        return GapAnalysis(
            detected=False,
            reason="缺省分析 (空)",
            timestamp=_now_iso(),
        )

    def _build(
        self,
        *,
        gtype: str,
        sid: str,
        sname: str,
        output: str,
        validation: dict[str, Any],
        failures: list[dict[str, Any]],
        hit: str = "",
        prev_decisions: Optional[list[dict[str, Any]]] = None,
    ) -> GapAnalysis:
        """按 gap_type 组装 GapAnalysis (severity/confidence/evidence/重复检测)。"""
        severity, base_conf, action = self.TYPE_PROFILE.get(
            gtype, ("medium", 0.5, "REQUEST_REVIEW")
        )
        evidence: list[str] = []
        if validation.get("success") is False:
            evidence.append("validation.success=false")
            errors = validation.get("errors") or []
            if isinstance(errors, list) and errors:
                evidence.append(
                    "validation.errors: " + " | ".join(str(e) for e in errors[:3])
                )
        if hit:
            evidence.append(f"agent_output 命中信号词: {hit!r}")
        if output:
            evidence.append(f"agent_output 摘要: {output[:200]}")
        if failures:
            for f in failures[:3]:
                evidence.append(
                    f"failures: {f.get('task_id')} ({f.get('name')}) — "
                    f"{str(f.get('error') or '')[:120]}"
                )
        if not evidence:
            evidence.append(f"无额外证据 (gap_type={gtype})")

        # 信号强度 → confidence: 命中信号词越多/证据来源越多 → 递增 (封顶 0.95)
        conf = base_conf
        if hit and gtype in self.MARKERS:
            hits = self._hits(output, self.MARKERS[gtype])
            conf += 0.05 * max(0, len(hits) - 1)  # 每多命中一个信号词 +0.05
        if validation.get("success") is False:
            conf += 0.05
        if failures:
            conf += 0.05
        conf = round(min(conf, self.CONFIDENCE_CAP), 2)

        dup = self._find_duplicate(gtype, sid, prev_decisions)
        desc, reason = self._describe(
            gtype=gtype,
            sid=sid,
            sname=sname,
            output=output,
            validation=validation,
            failures=failures,
            hit=hit,
            duplicate=dup,
        )
        return GapAnalysis(
            detected=True,
            gap_type=gtype,
            description=desc,
            evidence=evidence,
            severity=severity,
            source_task_id=sid,
            confidence=conf,
            duplicate_of=dup,
            recommended_action=action,
            reason=reason,
            timestamp=_now_iso(),
        )

    def _find_duplicate(
        self,
        gtype: str,
        sid: str,
        prev_decisions: Optional[list[dict[str, Any]]] = None,
    ) -> Optional[str]:
        """重复检测 (GAP G6): 相同 (source_task_id, gap_type) 已分析过,
        或历史决策已对该 source 任务 INSERT_TASK → 重复。

        返回先前记录的 source_task_id (缺口归属任务), 无 → None。
        """
        for p in self.previous_analyses():
            if (
                p.get("source_task_id") == sid
                and p.get("gap_type") == gtype
                and p.get("detected")
            ):
                return str(p.get("source_task_id") or sid)
        for d in (prev_decisions or []):
            if (
                d.get("decision") == "INSERT_TASK"
                and sid
                and sid in (d.get("affected_tasks") or [])
            ):
                return sid
        return None

    def _describe(
        self,
        *,
        gtype: str,
        sid: str,
        sname: str,
        output: str,
        validation: dict[str, Any],
        failures: list[dict[str, Any]],
        hit: str,
        duplicate: Optional[str],
    ) -> tuple[str, str]:
        """按 gap_type 生成描述 + 原因 (可解释性)。"""
        who = sid or sname or "当前任务"
        if gtype == "validation_failure":
            errors = validation.get("errors") or []
            err = " | ".join(str(e) for e in errors[:2]) if isinstance(errors, list) else ""
            desc = f"验证失败: 任务 {who} 未通过验证" + (f" ({err})" if err else "")
            reason = f"validation.success=false — 任务 {who} 需任务级修复 (REPAIR)"
        elif gtype == "missing_test":
            desc = f"测试缺口: {who} 缺少测试覆盖 (命中 {hit!r})"
            reason = f"Agent 报告测试缺失 ({hit!r}) — 插入测试任务 (INSERT_TASK)"
        elif gtype == "missing_implementation":
            desc = f"实现缺口: {who} 缺少持久化/存储实现 (命中 {hit!r})"
            reason = f"Agent 报告实现缺口 ({hit!r}) — 插入实现任务 (INSERT_TASK)"
        elif gtype == "missing_requirement":
            desc = f"需求缺口: {who} 需求不明确/变更 (命中 {hit!r})"
            reason = f"Agent 报告需求变更/缺失 ({hit!r}) — 插入需求任务 (INSERT_TASK)"
        elif gtype == "dependency_gap":
            desc = f"依赖缺口: {who} 依赖缺失 (命中 {hit!r})"
            reason = f"Agent 报告依赖缺失 ({hit!r}) — 插入依赖实现任务 (INSERT_TASK)"
        elif gtype == "integration_gap":
            desc = f"集成缺口: {who} 需要集成/联调 (命中 {hit!r})"
            reason = f"Agent 报告集成需要 ({hit!r}) — 插入集成任务 (INSERT_TASK)"
        elif gtype == "ui_gap":
            desc = f"UI 缺口: {who} 缺少界面/前端实现 (命中 {hit!r})"
            reason = f"Agent 报告 UI 缺口 ({hit!r}) — 插入前端任务 (INSERT_TASK)"
        elif gtype == "architecture_gap":
            desc = f"架构缺口: {who} 存在架构/设计风险 (命中 {hit!r})"
            reason = (
                f"Agent 报告架构问题 ({hit!r}) — 高风险, 需人工评审 "
                f"(REQUEST_REVIEW)"
            )
        else:  # unknown
            err = (
                str(failures[0].get("error") or "")[:120]
                if failures
                else ""
            )
            desc = f"未知缺口: 任务 {who} 失败但无明确缺口信号" + (
                f" ({err})" if err else ""
            )
            reason = (
                f"失败 {len(failures)} 个任务且无信号 — 安全兜底, 需人工评审 "
                f"(REQUEST_REVIEW)"
            )
        if duplicate:
            reason += f"; 该缺口已由 {duplicate} 处理过 (duplicate_of={duplicate})"
        return desc, reason

    @staticmethod
    def _collect_output(agent_output: Optional[str], result: dict[str, Any]) -> str:
        """Agent 输出: 显式参数 or 执行结果字段 (orchestrator 口径)。"""
        if agent_output is not None and str(agent_output).strip():
            return str(agent_output)
        for key in ("agent_output", "output", "error"):
            val = result.get(key)
            if val is not None and str(val).strip():
                return str(val)
        return ""

    @classmethod
    def _marker_hit(cls, output: str, markers: tuple[str, ...]) -> str:
        """输出中命中的首个信号词 (re: 前缀 = 正则; 否则子串)。"""
        low = str(output or "").lower()
        for m in markers:
            if m.startswith("re:"):
                try:
                    if re.search(m[3:], low):
                        return m[3:]
                except re.error:  # 失败安全: 坏正则 → 跳过
                    continue
            elif m in low:
                return m
        return ""

    @classmethod
    def _hits(cls, output: str, markers: tuple[str, ...]) -> list[str]:
        """输出中命中的全部信号词 (去重, 信号强度推导)。"""
        low = str(output or "").lower()
        found: list[str] = []
        for m in markers:
            if m.startswith("re:"):
                try:
                    if re.search(m[3:], low) and m[3:] not in found:
                        found.append(m[3:])
                except re.error:  # noqa: BLE001 — 失败安全
                    continue
            elif m in low and m not in found:
                found.append(m)
        return found
