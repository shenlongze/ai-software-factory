"""factory-console/session/task_proposal.py — TaskProposalEngine (S10-061 批次 A)。

Autonomous Gap Resolution 模型层 (GAP G2/G3/G4, 设计 §3-§5):
- TaskProposal — 自动生成的任务提案数据模型 {task_id, title, description,
  objective, required_role, dependencies, acceptance_criteria,
  validation_command, source_gap, rationale, confidence, priority}
  (+ to_dict/from_dict)
- TaskProposalEngine — GapAnalysis → TaskProposal | None (规则模板驱动,
  deterministic; 无模板的 gap_type → None → REQUEST_REVIEW 路径)
- TaskProposalValidator — 12 项 deterministic 验证门 → {valid, reasons, checks}
- DuplicateDetector — 重复检测 (normalized title / source_gap / objective 重叠)

规则模板 (设计 §3, gap_type → proposal):
  missing_test         → {required_role: qa,       objective: "为 X 增加测试",
                          acceptance_criteria: ["pytest 通过"],
                          validation_command: "pytest", dependencies: [source]}
  missing_implementation→ {required_role: backend, objective: "实现 X 持久化",
                          acceptance_criteria: ["数据可保存", "重启可恢复",
                                                "pytest 通过"],
                          validation_command: "pytest", dependencies: [source]}
  missing_requirement   → {required_role: pm,      objective: "明确 X 需求规格",
                          validation_command: "pytest", dependencies: [source]}
  ui_gap                → {required_role: frontend, objective: "实现 X 界面",
                          validation_command: "flutter test", dependencies: [source]}
  dependency_gap        → {required_role: backend,  objective: "实现 X 缺失依赖",
                          dependencies: [] (前置能力, 先于 source 执行)}
  integration_gap       → {required_role: backend,  objective: "集成 X 模块",
                          dependencies: [source]}
  architecture_gap / unknown / validation_failure → None (REQUEST_REVIEW /
  REPAIR 路径 — 不自动生成任务)

task_id 生成: T0XX 递增 (基于现有任务最大数字后缀 + 1, 空 → T001),
带冲突检查 (永不复用已有 id / source_task_id)。

validator 12 项检查 (设计 §4):
 1. task_id 唯一      2. title 非空       3. description 非空
 4. required_role 合法 5. dependencies 存在 6. 无 DAG cycle
 7. acceptance_criteria 非空  8. validation_command 合法
 9. 不与已有 Task 重复 (DuplicateDetector)  10. source_gap 存在
 11. confidence ≥ 阈值 (0.5)  12. 不超 replanning limit
失败 → valid=False + reasons (每项 REJECT 原因)。

边界 (批次 A 模型层):
- 纯标准库 + 只读引用 session/roles.ROLES (8 角色 — 合法角色面),
  不修改任何现有模块, 不引入新依赖; 失败安全 (非法输入 → None/False)
- 只生成/校验提案, 不改 DAG/不执行 (批次 B 集成)

设计: docs/sprint10/S10-061-autonomous-task-proposal-design.md §3-§5
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .roles import ROLES

#: 合法角色 (S10-056 ROLES 8 角色键 — validator 检查 4 的合法面)
VALID_ROLES: tuple[str, ...] = tuple(ROLES.keys())

#: 合法验证命令 (与 quality.Validator.validate_command 执行面一致)
VALID_VALIDATION_COMMANDS: tuple[str, ...] = (
    "pytest",
    "flutter test",
    "npm test",
)

#: 合法优先级
VALID_PRIORITIES: tuple[str, ...] = ("low", "medium", "high")

#: confidence 阈值 (validator 检查 11 — 设计 §4; 低 confidence → REJECT)
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

#: 重复检测 objective 重叠阈值 (min 归一化 token 重叠 ≥ 阈值 → 重复)
OBJECTIVE_OVERLAP_THRESHOLD = 0.6

#: source_gap 分隔符: "{gap_type}@{source_task_id}" (唯一标识一个缺口)
SOURCE_GAP_SEP = "@"


@dataclass
class TaskProposal:
    """自动任务提案 (设计 §3): 全字段 + to_dict/from_dict。

    task_id:            提案任务 id (T0XX 递增, 不冲突)
    title:              任务标题
    description:        任务描述
    objective:          任务目标 (可执行验收导向)
    required_role:      所需角色 (VALID_ROLES 之一 — AgentMatcher 分配面)
    dependencies:       依赖任务 id 列表 (depends_on, 先于本任务执行)
    acceptance_criteria:验收标准列表
    validation_command: 验证命令 (VALID_VALIDATION_COMMANDS 之一)
    source_gap:         触发缺口标识 "{gap_type}@{source_task_id}"
    rationale:          提案理由 (为什么生成该任务)
    confidence:         0.0-1.0 (继承 GapAnalysis 信号强度)
    priority:           low/medium/high
    """

    task_id: str
    title: str
    description: str
    objective: str
    required_role: str
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    validation_command: str = "pytest"
    source_gap: str = ""
    rationale: str = ""
    confidence: float = 0.0
    priority: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 task_proposals.json / DAG 插入候选 — 批次 B)。"""
        return {
            "task_id": str(self.task_id),
            "title": str(self.title),
            "description": str(self.description),
            "objective": str(self.objective),
            "required_role": str(self.required_role),
            "dependencies": [str(d) for d in (self.dependencies or [])],
            "acceptance_criteria": [
                str(c) for c in (self.acceptance_criteria or [])
            ],
            "validation_command": str(self.validation_command or "pytest"),
            "source_gap": str(self.source_gap or ""),
            "rationale": str(self.rationale or ""),
            "confidence": round(float(self.confidence or 0.0), 2),
            "priority": str(self.priority or "medium"),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "TaskProposal":
        """dict → TaskProposal (缺失字段默认 — 前向兼容/失败安全)。"""
        if not isinstance(data, dict):
            return cls(task_id="", title="", description="", objective="",
                       required_role="")
        return cls(
            task_id=str(data.get("task_id") or ""),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            objective=str(data.get("objective") or ""),
            required_role=str(data.get("required_role") or ""),
            dependencies=[
                str(d) for d in (data.get("dependencies") or [])
                if not isinstance(d, dict)
            ],
            acceptance_criteria=[
                str(c) for c in (data.get("acceptance_criteria") or [])
                if not isinstance(c, dict)
            ],
            validation_command=str(data.get("validation_command") or "pytest"),
            source_gap=str(data.get("source_gap") or ""),
            rationale=str(data.get("rationale") or ""),
            confidence=float(data.get("confidence") or 0.0),
            priority=str(data.get("priority") or "medium"),
        )


class TaskProposalEngine:
    """Gap → 任务提案引擎 (设计 §3): GapAnalysis → TaskProposal | None。

    propose(gap, existing_tasks, dag): 规则模板驱动 — 每个可 INSERT 的
    gap_type 有固定模板 (required_role/objective/acceptance_criteria/
    validation_command/dependencies); 无模板 (architecture_gap/unknown/
    validation_failure) → None (REQUEST_REVIEW / REPAIR 路径, 不自动生成)。
    task_id 由现有任务推导 (T0XX 递增, 冲突检查)。

    输入 gap 支持 GapAnalysis 或 dict (鸭子类型: detected/gap_type/
    source_task_id/description/confidence 属性或键)。
    """

    #: 规则模板: gap_type → 提案模板 (设计 §3 — deterministic)
    #: {source} = source_task_id, {desc} = 缺口描述摘要 (≤60 字符)
    TEMPLATES: dict[str, dict[str, Any]] = {
        "missing_test": {
            "required_role": "qa",
            "title": "为 {source} 增加测试",
            "objective": "为 {source} 增加测试覆盖 ({desc})",
            "description": "由 {source} 的测试缺口生成: {desc}",
            "acceptance_criteria": ["pytest 通过", "测试覆盖新增缺口场景"],
            "validation_command": "pytest",
            "dependencies": ["{source}"],
            "priority": "medium",
        },
        "missing_implementation": {
            "required_role": "backend",
            "title": "实现 {source} 缺失的持久化",
            "objective": "实现 {desc} 持久化",
            "description": "由 {source} 的实现缺口生成: {desc}",
            "acceptance_criteria": ["数据可保存", "重启可恢复", "pytest 通过"],
            "validation_command": "pytest",
            "dependencies": ["{source}"],
            "priority": "high",
        },
        "missing_requirement": {
            "required_role": "pm",
            "title": "补充 {source} 的需求规格",
            "objective": "明确 {desc} 的需求定义与验收标准",
            "description": "由 {source} 的需求缺口生成: {desc}",
            "acceptance_criteria": ["需求文档明确", "验收标准可执行"],
            "validation_command": "pytest",
            "dependencies": ["{source}"],
            "priority": "high",
        },
        "ui_gap": {
            "required_role": "frontend",
            "title": "实现 {source} 的界面",
            "objective": "实现 {desc} 界面/交互",
            "description": "由 {source} 的 UI 缺口生成: {desc}",
            "acceptance_criteria": ["界面可交互", "布局适配", "flutter test 通过"],
            "validation_command": "flutter test",
            "dependencies": ["{source}"],
            "priority": "medium",
        },
        "dependency_gap": {
            "required_role": "backend",
            "title": "实现 {source} 缺失的依赖",
            "objective": "实现 {desc} 依赖能力",
            "description": "由 {source} 的依赖缺口生成: {desc} (前置能力, 先于 "
            "{source} 执行)",
            "acceptance_criteria": ["依赖能力可用", "pytest 通过"],
            "validation_command": "pytest",
            "dependencies": [],
            "priority": "high",
        },
        "integration_gap": {
            "required_role": "backend",
            "title": "集成 {source} 与相关模块",
            "objective": "集成 {desc} 模块并完成联调",
            "description": "由 {source} 的集成缺口生成: {desc}",
            "acceptance_criteria": ["模块联调通过", "pytest 通过"],
            "validation_command": "pytest",
            "dependencies": ["{source}"],
            "priority": "medium",
        },
    }

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------ 提案

    def propose(
        self,
        gap: Any,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
        dag: Any = None,
    ) -> Optional[TaskProposal]:
        """GapAnalysis → TaskProposal | None (规则模板驱动, deterministic)。

        gap:             GapAnalysis (或 dict — 鸭子类型);
        existing_tasks:  已有计划任务列表 (task_id 推导 + 冲突检查);
        dag:             依赖图 (仅预留, 本批不修改 DAG)。

        返回 TaskProposal (可 INSERT 的 gap_type) 或 None (无模板:
        architecture_gap / unknown / validation_failure / detected=False /
        非法输入 → REQUEST_REVIEW / REPAIR 路径)。
        """
        if gap is None:
            return None
        if isinstance(gap, dict):
            detected = bool(gap.get("detected"))
            gtype = str(gap.get("gap_type") or "")
            sid = str(gap.get("source_task_id") or "")
            desc = str(gap.get("description") or "")
            conf = float(gap.get("confidence") or 0.0)
        else:
            detected = bool(getattr(gap, "detected", False))
            gtype = str(getattr(gap, "gap_type", "") or "")
            sid = str(getattr(gap, "source_task_id", "") or "")
            desc = str(getattr(gap, "description", "") or "")
            conf = float(getattr(gap, "confidence", 0.0) or 0.0)

        if not detected or not gtype:
            return None
        if gtype not in self.TEMPLATES:
            # 无模板: architecture_gap/unknown/validation_failure → 不自动生成
            return None

        template = self.TEMPLATES[gtype]
        source = sid or "当前任务"
        summary = self._summarize(desc)
        task_id = self._next_task_id(existing_tasks, sid)

        # 依赖模板 "{source}" 仅在存在真实来源任务时引用 (空 sid → 无依赖,
        # 避免产生指向不存在任务的伪依赖 — validator 检查 5)
        dependencies: list[str] = []
        if sid:
            dependencies = [
                str(d).replace("{source}", source)
                for d in template["dependencies"]
            ]
        return TaskProposal(
            task_id=task_id,
            title=template["title"].format(source=source, desc=summary),
            description=template["description"].format(
                source=source, desc=summary
            ),
            objective=template["objective"].format(source=source, desc=summary),
            required_role=template["required_role"],
            dependencies=dependencies,
            acceptance_criteria=list(template["acceptance_criteria"]),
            validation_command=template["validation_command"],
            source_gap=f"{gtype}{SOURCE_GAP_SEP}{sid}" if sid else gtype,
            rationale=(
                f"由 {source} 的 {gtype} gap 触发 (confidence={conf:.2f}): "
                f"{summary}"
            ),
            confidence=round(conf, 2),
            priority=template["priority"],
        )

    # ------------------------------------------------------------ task_id

    @classmethod
    def _next_task_id(
        cls,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
        source_task_id: str = "",
    ) -> str:
        """T0XX 递增 task_id (基于现有任务最大数字后缀, 冲突检查, deterministic)。

        已有 id 数字后缀最大值为 N → T{N+1:03d}; 无数字 id → 数量 + 1;
        空 → T001; 候选与已有 id / source_task_id 冲突 → 继续递增。
        """
        ids: set[str] = set()
        for t in (existing_tasks or []):
            if isinstance(t, dict):
                tid = t.get("id") or t.get("task_id")
                if tid:
                    ids.add(str(tid))
        if source_task_id:
            ids.add(str(source_task_id))

        max_num = 0
        for i in ids:
            m = re.search(r"(\d+)\s*$", i)
            if m:
                max_num = max(max_num, int(m.group(1)))
        if max_num == 0 and ids:
            max_num = len(ids)
        candidate = max_num + 1
        while True:
            tid = f"T{candidate:03d}"
            if tid not in ids:
                return tid
            candidate += 1

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _summarize(desc: str, limit: int = 60) -> str:
        """描述摘要: 首句/首行, 去空白, 截断 ≤ limit 字符。"""
        text = str(desc or "").strip()
        for sep in ("\n", "。", ";"):
            head = text.split(sep, 1)[0].strip()
            if head:
                text = head
                break
        text = re.sub(r"\s+", " ", text)
        return text if len(text) <= limit else text[: limit - 1] + "…"


class TaskProposalValidator:
    """12 项 deterministic 验证门 (设计 §4): 提案 → {valid, reasons, checks}。

    validate(proposal, existing_tasks, dag, replan_count, max_replan):
    每项检查 PASS/REJECT + reason; 任一 REJECT → valid=False,
    reasons 汇总全部 REJECT 原因 (可解释性)。
    """

    #: 12 项检查名 (设计 §4 顺序)
    CHECK_NAMES: tuple[str, ...] = (
        "task_id 唯一",
        "title 非空",
        "description 非空",
        "required_role 合法",
        "dependencies 存在",
        "无 DAG cycle",
        "acceptance_criteria 非空",
        "validation_command 合法",
        "不与已有 Task 重复",
        "source_gap 存在",
        "confidence ≥ 阈值",
        "不超 replanning limit",
    )

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        duplicate_detector: Optional["DuplicateDetector"] = None,
    ) -> None:
        self._threshold = float(confidence_threshold)
        self._dup = duplicate_detector or DuplicateDetector()

    def validate(
        self,
        proposal: Any,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
        dag: Any = None,
        replan_count: Optional[int] = None,
        max_replan: int = 5,
    ) -> dict[str, Any]:
        """12 项检查 → {valid: bool, reasons: list[str], checks: [...]}。

        proposal:      TaskProposal (或 dict — 鸭子类型);
        existing_tasks: 已有计划任务列表 (id 集合 / 重复检测面);
        dag:            依赖图 (鸭子类型 cycle_detect — 检查 6);
        replan_count:   已重规划次数 (检查 12; None → 视为 0);
        max_replan:     重规划预算 (缺省 5)。
        """
        existing = [t for t in (existing_tasks or []) if isinstance(t, dict)]
        existing_ids = {
            str(t.get("id")) for t in existing if t.get("id")
        }
        if isinstance(proposal, dict):
            p = TaskProposal.from_dict(proposal)
        else:
            p = (
                proposal
                if isinstance(proposal, TaskProposal)
                else TaskProposal.from_dict({})
            )
        cur_replan = int(replan_count) if replan_count is not None else 0

        checks: list[dict[str, Any]] = []
        for i, name in enumerate(self.CHECK_NAMES, start=1):
            status, reason = self._run_check(
                i, name, p, existing, existing_ids, dag, cur_replan,
                int(max_replan),
            )
            checks.append(
                {"check": i, "name": name, "status": status, "reason": reason}
            )
        reasons = [c["reason"] for c in checks if c["status"] == "REJECT"]
        return {
            "valid": not reasons,
            "reasons": reasons,
            "checks": checks,
        }

    # ------------------------------------------------------------ 12 项

    def _run_check(
        self,
        idx: int,
        name: str,
        p: TaskProposal,
        existing: list[dict[str, Any]],
        existing_ids: set[str],
        dag: Any,
        replan_count: int,
        max_replan: int,
    ) -> tuple[str, str]:
        """单检查执行 → (PASS/REJECT, reason)。"""
        if idx == 1:  # task_id 唯一
            if not p.task_id:
                return "REJECT", "检查1 (task_id 唯一): task_id 为空"
            if p.task_id in existing_ids:
                return (
                    "REJECT",
                    f"检查1 (task_id 唯一): task_id {p.task_id} 与已有任务冲突",
                )
            return "PASS", "检查1 (task_id 唯一): PASS"
        if idx == 2:  # title 非空
            if not str(p.title or "").strip():
                return "REJECT", "检查2 (title 非空): title 为空"
            return "PASS", "检查2 (title 非空): PASS"
        if idx == 3:  # description 非空
            if not str(p.description or "").strip():
                return "REJECT", "检查3 (description 非空): description 为空"
            return "PASS", "检查3 (description 非空): PASS"
        if idx == 4:  # required_role 合法
            role = str(p.required_role or "")
            if role not in VALID_ROLES:
                return (
                    "REJECT",
                    f"检查4 (required_role 合法): {role!r} 不在合法角色 "
                    f"{VALID_ROLES}",
                )
            return "PASS", "检查4 (required_role 合法): PASS"
        if idx == 5:  # dependencies 存在
            missing = [
                str(d) for d in (p.dependencies or []) if d not in existing_ids
            ]
            if missing:
                return (
                    "REJECT",
                    f"检查5 (dependencies 存在): 依赖任务不存在: {missing}",
                )
            return "PASS", "检查5 (dependencies 存在): PASS"
        if idx == 6:  # 无 DAG cycle
            if dag is None:
                return (
                    "PASS",
                    "检查6 (无 DAG cycle): 无依赖图, 跳过 (无法验证)",
                )
            cyclic = self._cycle_edges(p, dag)
            if cyclic:
                return (
                    "REJECT",
                    f"检查6 (无 DAG cycle): 形成循环依赖: {cyclic}",
                )
            return "PASS", "检查6 (无 DAG cycle): PASS"
        if idx == 7:  # acceptance_criteria 非空
            crits = [
                str(c).strip() for c in (p.acceptance_criteria or []) if c
            ]
            if not crits or any(not c for c in crits):
                return (
                    "REJECT",
                    "检查7 (acceptance_criteria 非空): 验收标准为空",
                )
            return "PASS", "检查7 (acceptance_criteria 非空): PASS"
        if idx == 8:  # validation_command 合法
            cmd = str(p.validation_command or "")
            if cmd not in VALID_VALIDATION_COMMANDS:
                return (
                    "REJECT",
                    f"检查8 (validation_command 合法): {cmd!r} 不在合法命令 "
                    f"{VALID_VALIDATION_COMMANDS}",
                )
            return "PASS", "检查8 (validation_command 合法): PASS"
        if idx == 9:  # 不与已有 Task 重复
            dup = self._dup.check(p, existing)
            if dup.get("duplicate"):
                return (
                    "REJECT",
                    f"检查9 (不与已有 Task 重复): 与 {dup.get('duplicate_of')} "
                    f"重复 ({dup.get('reason')})",
                )
            return "PASS", "检查9 (不与已有 Task 重复): PASS"
        if idx == 10:  # source_gap 存在
            if not str(p.source_gap or "").strip():
                return "REJECT", "检查10 (source_gap 存在): source_gap 为空"
            return "PASS", "检查10 (source_gap 存在): PASS"
        if idx == 11:  # confidence ≥ 阈值
            if float(p.confidence or 0.0) < self._threshold:
                return (
                    "REJECT",
                    f"检查11 (confidence ≥ 阈值): confidence={p.confidence} "
                    f"< {self._threshold}",
                )
            return "PASS", "检查11 (confidence ≥ 阈值): PASS"
        # idx == 12: 不超 replanning limit
        if replan_count >= max_replan:
            return (
                "REJECT",
                f"检查12 (不超 replanning limit): replan_count={replan_count} "
                f">= max_replan={max_replan}",
            )
        return "PASS", "检查12 (不超 replanning limit): PASS"

    @staticmethod
    def _cycle_edges(p: TaskProposal, dag: Any) -> list[str]:
        """提案依赖边成环边列表 (检查 6; 无 cycle_detect → 空, 失败安全)。"""
        cyclic: list[str] = []
        for dep in p.dependencies or []:
            dep = str(dep)
            if not dep:
                continue
            try:
                if dag.cycle_detect(p.task_id, dep):
                    cyclic.append(f"{p.task_id}→{dep}")
            except Exception:  # noqa: BLE001 — 失败安全: 无 cycle_detect → 跳过
                return []
        return cyclic


class DuplicateDetector:
    """重复任务检测 (设计 §5, GAP G4): deterministic 三信号。

    check(proposal, existing_tasks) → {duplicate, duplicate_of, reason}:
    1. normalized title 精确匹配 (去空白/标点/大小写)
    2. source_gap 精确匹配 (同一缺口标识 "{type}@{source}" → 同一缺口)
    3. objective 重叠 (归一化后相等 / 互相包含 / token 重叠 ≥ 0.6)
    任一命中 → duplicate=True + duplicate_of (被重复任务的 id)。
    """

    def check(
        self,
        proposal: Any,
        existing_tasks: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """proposal vs 已有任务 → 重复检测结果。"""
        p = (
            proposal
            if isinstance(proposal, TaskProposal)
            else TaskProposal.from_dict(
                proposal if isinstance(proposal, dict) else {}
            )
        )
        existing = [t for t in (existing_tasks or []) if isinstance(t, dict)]
        p_title = self._normalize(p.title)
        p_obj = self._normalize(p.objective)
        p_gap = str(p.source_gap or "")

        for t in existing:
            tid = str(t.get("id") or t.get("task_id") or "")
            if not tid or tid == p.task_id:
                continue
            t_title = self._normalize(
                str(t.get("title") or t.get("name") or "")
            )
            t_obj = self._normalize(str(t.get("objective") or ""))
            t_gap = str(t.get("source_gap") or "")
            reason = ""
            if p_title and t_title and p_title == t_title:
                reason = "normalized title 匹配"
            elif p_gap and t_gap and p_gap == t_gap:
                reason = "source_gap 匹配"
            elif self._objective_overlap(p_obj, t_obj):
                reason = "objective 重叠"
            if reason:
                return {
                    "duplicate": True,
                    "duplicate_of": tid,
                    "reason": reason,
                }
        return {
            "duplicate": False,
            "duplicate_of": None,
            "reason": "未发现重复",
        }

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _normalize(text: Any) -> str:
        """标题归一化: 小写 + 去空白/标点/非词字符。"""
        return re.sub(r"[\s\W_]+", "", str(text or "")).lower()

    @classmethod
    def _objective_overlap(cls, a: str, b: str) -> bool:
        """objective 重叠: 相等 / 互相包含 / token 重叠 ≥ 0.6 (min 归一化)。"""
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        ta = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", a))
        tb = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", b))
        if not ta or not tb:
            return False
        inter = len(ta & tb)
        return inter / min(len(ta), len(tb)) >= OBJECTIVE_OVERLAP_THRESHOLD
