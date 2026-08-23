"""factory-console/session/decomposition_evaluator.py — 拆解质量评估 + 四档行动 (M3d, S10-095)。

把 DecomposeEngine 产出的叶子（或 LLM 深度拆解的结构化 {tasks[]}）做**质量门控**:
六维确定性评分（完整性/粒度/依赖/可行性/可测性/风险）+ 四档行动
（adopt/adjust/reject/ask_user）——"拆完还要验质量"，不合格就诚实降级，不伪造。

- 六维权重（§3.4）: 完整性 25% / 粒度 20% / 依赖 20% / 可行性 15% /
  可测性 10% / 风险 10%; score = Σ(维分 × 权重)
- 确定性规则（每维可手算）:
  ① 完整性 = 叶子覆盖 core_features 比例（缺失 feature → 失分）
  ② 粒度 = 原子四条件通过率（单Agent/单文件/可验证/≤10min, 每条件 0.25）
  ③ 依赖 = cycle_detect（环=0）+ 关键路径合理性（无死节点/悬空依赖）
  ④ 可行性 = agent_type ∈ capabilities（不可用 agent → 失分）
  ⑤ 可测性 = verify_cmd 覆盖率（有 verify 的叶子比例）
  ⑥ 风险 = risks 标注存在（全部无标注 → 0）
- 四档行动:
  adopt  (≥0.9)   → 采用拆解
  adjust (0.7-0.9) → adjust() 自动修正（补 feature / 补 verify / 修剪环）→
                     修正后采用（标注 adjusted）; 仍 <0.7 → reject
  reject (<0.7)   → 回退确定性技术层模板（诚实降级, 不伪造 LLM 质量）
  ask_user(<0.5)  → 返回 questions（REPL 层处理后重评）
- 落盘: evaluation {score, dims, decision, reasons} 进 decomposition.json /
  evidence（evidence.py 字段扩展）+ 审计 EVAL_COMPLETED / EVAL_REJECTED_FALLBACK

设计: docs/sprint10/S10-095-m3d-evaluator-plan.md
边界:
- 纯标准库 + 复用 dependencies.TaskDependencyGraph（只读 API: add_dependency
  返回 False = 成环拒绝）
- 只做计划层质量评估; 不做 M3-4 动态分配 / 并行线程化 / 模板库扩展
- 向后兼容: 评估器可选注入（decomposer 默认开, 显式禁用/替换不破坏 M3a）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .dependencies import TaskDependencyGraph

#: 六维权重（§3.4 — 完整性/粒度/依赖/可行性/可测性/风险）
WEIGHTS: dict[str, float] = {
    "完整性": 0.25,
    "粒度": 0.20,
    "依赖": 0.20,
    "可行性": 0.15,
    "可测性": 0.10,
    "风险": 0.10,
}

#: 四档行动阈值
THRESHOLD_ADOPT = 0.9
THRESHOLD_ADJUST = 0.7
THRESHOLD_ASK_USER = 0.5

#: 原子四条件（粒度维每条件 0.25 — 对齐 M3a is_atomic 语义）
GRANULARITY_CONDITIONS = ("single_agent", "single_file", "verifiable", "est_ok")

#: 高风险/复合启发式（风险维: 这些叶子必须标注 risks）
COMPLEX_KEYWORDS = (
    "重构", "大规模", "复杂", "整套", "全部", "全面", "架构",
    "迁移", "重写", "性能优化", "分布式", "微服务", "模块化",
)

#: 语言 → 默认验证命令（adjust 补 verify 用 — 与 decomposer.LANG_VERIFY_CMD 对齐）
LANG_VERIFY_CMD: dict[str, str] = {
    "py": "pytest {file}",
    "js": "npm test -- {file}",
    "ts": "npm test -- {file}",
    "tsx": "npm test -- {file}",
    "jsx": "npm test -- {file}",
    "go": "go test {file}",
    "rs": "cargo test {file}",
    "dart": "flutter test {file}",
    "java": "mvn test -Dtest={file}",
    "kt": "gradle test --tests {file}",
    "rb": "ruby -c {file}",
    "sh": "bash -n {file}",
    "sql": "sqlfluff lint {file}",
    "md": "markdownlint {file}",
    "json": "python -m json.tool {file}",
    "yaml": "python -c \"import yaml,sys;yaml.safe_load(open('{file}'))\"",
    "yml": "python -c \"import yaml,sys;yaml.safe_load(open('{file}'))\"",
    "toml": "python -c \"import tomllib;tomllib.load(open('{file}','rb'))\"",
    "html": "html5validator {file}",
    "css": "stylelint {file}",
    "vue": "npm test -- {file}",
}


def _now_iso() -> str:  # pragma: no cover — 仅调试/落盘时间戳
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvalResult:
    """评估结果（to_dict 供落盘/审计/CLI）。"""

    score: float = 0.0
    dims: dict[str, float] = field(default_factory=dict)
    decision: str = "reject"           # adopt | adjust | reject | ask_user
    reasons: list[str] = field(default_factory=list)
    adjusted: bool = False             # adjust 已自动修正
    adjustments: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)  # ask_user 问询
    task_count: int = 0
    feature_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "dims": {k: round(float(v), 4) for k, v in self.dims.items()},
            "decision": self.decision,
            "reasons": list(self.reasons),
            "adjusted": bool(self.adjusted),
            "adjustments": list(self.adjustments),
            "questions": list(self.questions),
            "task_count": int(self.task_count),
            "feature_count": int(self.feature_count),
        }


class DecompositionEvaluator:
    """拆解质量评估器（六维确定性评分 + 四档行动）。

    evaluate(decomposition, task, context) → EvalResult（纯评分, 不改输入）;
    adjust(decomposition, task, context) → (adjusted, EvalResult)（自动修正）。
    """

    def __init__(self, audit: Optional[Any] = None, workspace: Any = None,
                 project_id: str = "") -> None:
        self._audit = audit
        self.workspace = Path(workspace) if workspace is not None else None
        self.project_id = str(project_id or "")

    # ------------------------------------------------------------ 入口

    def evaluate(
        self,
        decomposition: Any,
        task: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> EvalResult:
        """六维评分 + 四档行动判定（确定性, 不改输入）。

        decomposition: {"tasks": [...]} / {"leaves": [...]} / list[dict];
        task: 原复合任务 {id,name,requirement,core_features?};
        context: {capabilities, product}（M3-4 前 capabilities 可缺省）。
        """
        tasks = self._normalize_tasks(decomposition)
        context = dict(context or {})
        caps = context.get("capabilities")
        product = dict(context.get("product") or {})

        dims = {
            "完整性": self._score_completeness(tasks, task, product),
            "粒度": self._score_granularity(tasks, caps),
            "依赖": self._score_deps(tasks),
            "可行性": self._score_feasibility(tasks, caps),
            "可测性": self._score_testability(tasks),
            "风险": self._score_risk(tasks),
        }
        reasons = self._collect_reasons(tasks, task, product, caps, dims)
        score = round(sum(dims[k] * WEIGHTS[k] for k in WEIGHTS), 4)
        decision = self._decide(score)
        questions = self._build_questions(tasks, task, product, caps, dims) if decision == "ask_user" else []
        return EvalResult(
            score=score,
            dims=dims,
            decision=decision,
            reasons=reasons,
            questions=questions,
            task_count=len(tasks),
            feature_count=len(self._features(task, product)),
        )

    def adjust(
        self,
        decomposition: Any,
        task: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], EvalResult]:
        """自动修正（0.7-0.9 档）: 补缺失 feature / 补默认 verify / 修剪依赖环。

        返回 (修正后 decomposition dict {tasks:[...], adjusted:True}, 重评结果)。
        重评后 score ≥0.7 → decision=adopt（标注 adjusted）; 仍 <0.7 → reject
        （诚实: 修正不足则降级, 不伪造）。
        """
        tasks = [dict(t) for t in self._normalize_tasks(decomposition)]
        context = dict(context or {})
        product = dict(context.get("product") or {})
        adjustments: list[str] = []

        # ① 缺失 core_features 补齐（诚实占位: 目标文件/verify 可推导 → 可执行）
        features = self._features(task, product)
        covered = self._covered_features(tasks, features)
        missing = [f for f in features if f not in covered]
        if missing:
            for f in missing:
                tasks.append(self._default_task(f, task))
            adjustments.append(f"补缺失 feature 任务: {', '.join(missing)}")

        # ② verify_cmd 补默认（按 target_file 语言映射）
        patched = []
        for t in tasks:
            if not str(t.get("verify_cmd") or "").strip():
                vc = self._default_verify_cmd(t)
                if vc:
                    t["verify_cmd"] = vc
                    patched.append(str(t.get("id") or t.get("name") or "?"))
        if patched:
            adjustments.append(f"补默认 verify_cmd: {', '.join(patched[:5])}"
                               + (" 等" if len(patched) > 5 else ""))

        # ③ 依赖环修剪（逐条 add_dependency, 成环边丢弃 → DAG 保持）
        pruned = self._prune_cycles(tasks)
        if pruned:
            adjustments.append(f"修剪依赖环: 丢弃 {len(pruned)} 条成环边")

        result = self.evaluate({"tasks": tasks}, task, context)
        result.adjustments = adjustments
        if result.score >= THRESHOLD_ADJUST:
            result.decision = "adopt"   # 修正后采用（标注 adjusted）
        else:
            result.decision = "reject"  # 修正仍不足 → 诚实降级
        result.adjusted = True
        result.reasons = [f"[adjusted] {a}" for a in adjustments] + result.reasons
        adjusted_decomp: dict[str, Any] = {
            "tasks": tasks,
            "adjusted": True,
            "adjustments": adjustments,
        }
        return adjusted_decomp, result

    # ------------------------------------------------------------ 归一化

    @staticmethod
    def _normalize_tasks(decomposition: Any) -> list[dict[str, Any]]:
        """任意拆解输入 → 叶子任务列表（dict 带 tasks/leaves 或裸 list）。"""
        if isinstance(decomposition, dict):
            src = decomposition.get("tasks") or decomposition.get("leaves")
        else:
            src = decomposition
        if not isinstance(src, list):
            return []
        tasks: list[dict[str, Any]] = []
        for item in src:
            if isinstance(item, dict):
                tasks.append(dict(item))
        return tasks

    @staticmethod
    def _features(task: dict[str, Any], product: dict[str, Any]) -> list[str]:
        """core_features 提取（task 优先, product 兜底; dict/list 归一）。"""
        raw = task.get("core_features")
        if raw is None:
            raw = product.get("core_features")
        if raw is None:
            raw = product.get("features")
        features: list[str] = []
        for f in (raw or []):
            name = str(f.get("name") if isinstance(f, dict) else f or "").strip()
            if name and name not in features:
                features.append(name)
        return features

    @staticmethod
    def _text(t: dict[str, Any]) -> str:
        return " ".join(
            str(t.get(k) or "") for k in ("name", "goal", "requirement", "target_file")
        )

    @staticmethod
    def _covered_features(
        tasks: list[dict[str, Any]], features: list[str]
    ) -> set[str]:
        """被叶子覆盖的 feature 集合（叶子文本含 feature 名 → 覆盖）。"""
        covered: set[str] = set()
        for t in tasks:
            text = DecompositionEvaluator._text(t)
            for f in features:
                if f in text:
                    covered.add(f)
        return covered

    @staticmethod
    def _default_verify_cmd(t: dict[str, Any]) -> str:
        """按 target_file 扩展名 → 默认验证命令（无文件/未知语言 → ""）。"""
        f = str(t.get("target_file") or "").strip()
        if not f:
            return ""
        ext = Path(f).suffix.lstrip(".").lower()
        tmpl = LANG_VERIFY_CMD.get(ext)
        return tmpl.format(file=f) if tmpl else ""

    def _default_task(self, feature: str, task: dict[str, Any]) -> dict[str, Any]:
        """缺失 feature 的补齐任务（可执行: 目标文件 + verify + est ≤10min）。"""
        slug = str(feature).strip().lower()
        fname = f"backend/{slug}_api.py"
        return {
            "id": f"{str(task.get('id') or 'root')}-missing-{slug}",
            "name": f"实现功能: {feature}",
            "goal": f"实现功能: {feature}",
            "requirement": f"实现功能: {feature}（补齐缺失 core_feature）",
            "agent_type": "backend",
            "target_file": fname,
            "verify_cmd": LANG_VERIFY_CMD.get("py", "").format(file=fname),
            "est_minutes": 10,
            "depends_on": [],
            "risks": [f"{feature} 功能范围需用户确认（自动补齐占位）"],
            "parent": str(task.get("id") or "root"),
            "verified": True,     # 补齐任务满足原子四条件（单Agent/单文件/可验证/≤10min）
            "unverified": False,
            "source": "evaluator_adjust",
        }

    @staticmethod
    def _prune_cycles(tasks: list[dict[str, Any]]) -> list[tuple[str, str]]:
        """逐条 add_dependency 建图; 成环边丢弃 → 返回被修剪的边列表。"""
        ids = {str(t.get("id") or "") for t in tasks}
        graph = TaskDependencyGraph()
        pruned: list[tuple[str, str]] = []
        for t in tasks:
            tid = str(t.get("id") or "")
            deps = t.get("depends_on") or []
            if isinstance(deps, str):
                deps = [deps]
            kept: list[str] = []
            for d in deps:
                d = str(d)
                if d not in ids:      # 悬空引用 → 丢弃（死引用）
                    pruned.append((tid, d))
                    continue
                if not graph.add_dependency(tid, d):
                    pruned.append((tid, d))  # 成环 → 丢弃
                    continue
                kept.append(d)
            if deps is not None and not isinstance(deps, str):
                t["depends_on"] = kept
        return pruned

    # ------------------------------------------------------------ 六维评分

    def _score_completeness(
        self, tasks: list[dict[str, Any]], task: dict[str, Any], product: dict[str, Any]
    ) -> float:
        """完整性: 叶子覆盖 core_features 比例（无 feature 定义 → 1.0 空真）。"""
        features = self._features(task, product)
        if not features:
            return 1.0
        covered = self._covered_features(tasks, features)
        return round(len(covered) / len(features), 4)

    @staticmethod
    def _leaf_condition_flags(t: dict[str, Any], caps: Optional[Any]) -> dict[str, bool]:
        """叶子原子四条件（每条件 0.25; 与 M3a is_atomic 对齐, 确定性）。"""
        agent_type = str(t.get("agent_type") or "").strip()
        single_agent = bool(agent_type)
        if single_agent and caps is not None and agent_type in caps:
            cands = caps[agent_type]
            if isinstance(cands, (list, set, tuple)):
                single_agent = len(cands) == 1
            else:
                single_agent = int(cands or 0) == 1
        # 单文件: 显式 target_file/files 恰好 1 个（缺失 → 0）
        files: list[str] = []
        explicit = t.get("target_file") or t.get("files")
        if isinstance(explicit, str) and explicit.strip():
            files.append(explicit.strip())
        elif isinstance(explicit, (list, tuple)):
            files.extend(str(f) for f in explicit if str(f).strip())
        single_file = len(files) == 1
        verify = str(t.get("verify_cmd") or "").strip()
        verifiable = bool(verify)
        est_raw = t.get("est_minutes")
        if est_raw is None:
            est_raw = t.get("est")
        est_ok = True
        try:
            est_ok = int(est_raw or 0) <= 10
        except (TypeError, ValueError):
            est_ok = False
        return {
            "single_agent": single_agent,
            "single_file": single_file,
            "verifiable": verifiable,
            "est_ok": est_ok,
        }

    def _score_granularity(self, tasks: list[dict[str, Any]], caps: Optional[Any]) -> float:
        """粒度: 原子四条件通过率（每条件 0.25; 无叶子 → 0）。"""
        if not tasks:
            return 0.0
        total = 0.0
        for t in tasks:
            flags = self._leaf_condition_flags(t, caps)
            total += sum(1 for v in flags.values() if v) * 0.25
        return round(total / len(tasks), 4)

    def _score_deps(self, tasks: list[dict[str, Any]]) -> float:
        """依赖: cycle_detect 通过=1 / 环=0 + 无死节点/悬空依赖。

        无显式依赖边 → 1.0（顺序执行语义, 无环可判）; 有边但含死节点/
        悬空引用 → 0.5（半失分, 关键路径合理性受损）。
        """
        edges: list[tuple[str, str]] = []
        ids = {str(t.get("id") or "") for t in tasks}
        for t in tasks:
            deps = t.get("depends_on") or []
            if isinstance(deps, str):
                deps = [deps]
            tid = str(t.get("id") or "")
            for d in deps:
                if str(d) and (str(d), tid) not in edges:
                    edges.append((str(d), tid))
        if not edges:
            return 1.0
        graph = TaskDependencyGraph()
        for dep, task_id in edges:
            if not graph.add_dependency(task_id, dep):
                return 0.0  # 成环 → 依赖维 0
        # 死节点/悬空: 悬空引用 or 有边声明但节点孤立（无依赖也无被依赖）
        dangling = any(d not in ids for d, _ in edges)
        connected: set[str] = set()
        for dep, task_id in edges:
            connected.add(dep)
            connected.add(task_id)
        isolated = [tid for tid in ids if tid and tid not in connected]
        if dangling or isolated:
            return 0.5
        return 1.0

    def _score_feasibility(self, tasks: list[dict[str, Any]], caps: Optional[Any]) -> float:
        """可行性: agent_type ∈ capabilities 比例（capabilities 缺省 → 1.0 空真）。"""
        if not tasks:
            return 0.0
        if caps is None:
            return 1.0
        caps = dict(caps) if isinstance(caps, dict) else {}
        if not caps:
            return 1.0
        ok = 0
        for t in tasks:
            agent = str(t.get("agent_type") or "").strip()
            if agent and agent in caps:
                ok += 1
        return round(ok / len(tasks), 4)

    def _score_testability(self, tasks: list[dict[str, Any]]) -> float:
        """可测性: verify_cmd 覆盖率（有 verify 的叶子比例; 无叶子 → 0）。"""
        if not tasks:
            return 0.0
        ok = sum(1 for t in tasks if str(t.get("verify_cmd") or "").strip())
        return round(ok / len(tasks), 4)

    def _score_risk(self, tasks: list[dict[str, Any]]) -> float:
        """风险: risks 标注覆盖率（全部无标注 → 0; 每个复合/高风险叶子
        必须有 risks, 缺失计入失分）。"""
        if not tasks:
            return 0.0
        with_risks = 0
        for t in tasks:
            risks = t.get("risks")
            if isinstance(risks, list) and risks:
                with_risks += 1
            elif isinstance(risks, str) and risks.strip():
                with_risks += 1
        return round(with_risks / len(tasks), 4)

    # ------------------------------------------------------------ 四档行动

    @staticmethod
    def _decide(score: float) -> str:
        """四档行动: ≥0.9 adopt / 0.7-0.9 adjust / <0.7 reject / <0.5 ask_user。"""
        if score >= THRESHOLD_ADOPT:
            return "adopt"
        if score >= THRESHOLD_ADJUST:
            return "adjust"
        if score >= THRESHOLD_ASK_USER:
            return "reject"
        return "ask_user"

    # ------------------------------------------------------------ 原因/问询

    def _collect_reasons(
        self,
        tasks: list[dict[str, Any]],
        task: dict[str, Any],
        product: dict[str, Any],
        caps: Optional[Any],
        dims: dict[str, float],
    ) -> list[str]:
        reasons: list[str] = []
        features = self._features(task, product)
        covered = self._covered_features(tasks, features)
        missing = [f for f in features if f not in covered]
        if missing:
            reasons.append(
                f"完整性: 缺失 core_features 覆盖 {len(missing)}/{len(features)}"
                f"（{'/'.join(missing)}）"
            )
        if dims["粒度"] < 1.0 and tasks:
            for t in tasks:
                flags = self._leaf_condition_flags(t, caps)
                if not all(flags.values()):
                    broken = [k for k, v in flags.items() if not v]
                    reasons.append(
                        f"粒度: {t.get('id') or t.get('name') or '?'} 未过原子四条件"
                        f"（{', '.join(broken)}）"
                    )
        if dims["依赖"] < 1.0:
            if dims["依赖"] == 0.0:
                reasons.append("依赖: 检测到依赖环（cycle_detect 失败）")
            else:
                reasons.append("依赖: 存在死节点/悬空依赖引用（关键路径合理性受损）")
        if dims["可行性"] < 1.0 and caps:
            unknown = sorted({
                str(t.get("agent_type") or "") for t in tasks
                if not str(t.get("agent_type") or "").strip()
                or str(t.get("agent_type") or "") not in caps
            })
            if unknown:
                reasons.append(
                    f"可行性: agent_type {'/'.join(unknown)} 不在可用 capabilities 中"
                )
        if dims["可测性"] < 1.0:
            n = sum(1 for t in tasks if not str(t.get("verify_cmd") or "").strip())
            reasons.append(f"可测性: {n} 个叶子缺 verify_cmd")
        if dims["风险"] < 1.0:
            n = sum(
                1 for t in tasks
                if not (isinstance(t.get("risks"), list) and t.get("risks"))
                and not (isinstance(t.get("risks"), str) and str(t.get("risks")).strip())
            )
            reasons.append(f"风险: {n} 个叶子未标注 risks")
        return reasons

    def _build_questions(
        self,
        tasks: list[dict[str, Any]],
        task: dict[str, Any],
        product: dict[str, Any],
        caps: Optional[Any],
        dims: dict[str, float],
    ) -> list[str]:
        """ask_user 问询（低分维度 → 缺失信息问题, REPL 层处理后重评）。"""
        questions: list[str] = []
        features = self._features(task, product)
        missing = [f for f in features if f not in self._covered_features(tasks, features)]
        if missing:
            questions.append(f"请确认 core_features 范围: 缺少 {'/'.join(missing)} 的实现任务")
        if dims["粒度"] < 1.0:
            questions.append(
                "请补充叶子任务的目标文件 / agent_type / 验证命令 / 工作量估计"
                "（当前粒度不足, 未到可执行原子）"
            )
        if dims["可行性"] < 1.0 and caps:
            unknown = sorted({
                str(t.get("agent_type") or "") for t in tasks
                if str(t.get("agent_type") or "") not in caps
            })
            if unknown:
                questions.append(f"请确认可用 Agent 能力: {'/'.join(unknown)} 不在 capabilities 中")
        if dims["可测性"] < 1.0:
            questions.append("请提供缺失叶子任务的验证命令（verify_cmd）")
        if dims["风险"] < 1.0:
            questions.append("请确认复合/高风险叶子的风险标注（risks）")
        return questions[:3]

    # ------------------------------------------------------------ 落盘/审计

    def to_evidence(self, result: EvalResult) -> dict[str, Any]:
        """评估结果 → evidence 字段（score/dims/decision/reasons/adjusted）。"""
        return result.to_dict()

    def emit(self, event_type: str, result: EvalResult, **fields: Any) -> Optional[Any]:
        """审计事件（失败安全: 审计故障不中断评估）。"""
        try:
            if self._audit is not None:
                return self._audit.emit(
                    event_type,
                    project_id=self.project_id,
                    result=result.to_dict(),
                    decision=result.decision,
                    decision_reason="; ".join(result.reasons),
                    **fields,
                )
            if self.workspace is not None:
                from ..audit.audit_emitter import AuditEmitter

                return AuditEmitter(workspace=self.workspace).emit(
                    event_type,
                    project_id=self.project_id,
                    result=result.to_dict(),
                    decision=result.decision,
                    decision_reason="; ".join(result.reasons),
                    **fields,
                )
        except Exception:  # noqa: BLE001 — 失败安全铁律
            return None
        return None


__all__ = [
    "WEIGHTS",
    "THRESHOLD_ADOPT",
    "THRESHOLD_ADJUST",
    "THRESHOLD_ASK_USER",
    "EvalResult",
    "DecompositionEvaluator",
]
