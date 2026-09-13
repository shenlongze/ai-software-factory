"""factory-console/session/plan_critic.py — PlanCritic (S10-062 批次 A)。

LLM Planning 基础设施 (GAP G5, 设计 §6): 执行前检查计划缺口 — 输入
plan + product + engineering + capabilities → 输出 GapAnalysis 列表
(与 S10-061 GapAnalysis 同结构, 走 GapAnalyzer → TaskProposal → Validator
→ ReplanningEngine 流程, 不直接修改 DAG)。

deterministic 检查 (设计 §6):
1. 持久化缺口 (missing_implementation): PRD/engineering 含持久化要求
   (persistence/持久化/存储 信号) 但 plan 无持久化任务 → gap
   severity=high, confidence 0.80 (双来源命中 +0.05, 封顶 0.95), INSERT_TASK
2. 测试缺口 (missing_test): plan 非空但无 QA/测试任务 (required_role ∈
   {qa, tester} 或任务文本命中 test/测试/pytest) → gap
   severity=medium, confidence 0.80 (plan ≥4 任务 +0.05), INSERT_TASK
3. UI 缺口 (ui_gap): product.platform ∈ {mobile, web} 或 product/engineering
   含 UI 信号 (界面/前端/frontend/\\bui\\b) 但 plan 无 frontend 任务 → gap
   severity=low, confidence 0.70 (显式平台 +0.05), INSERT_TASK
4. 角色缺口 (dependency_gap): plan 任务缺 required_role 或角色不合法
   (∉ ROLES 键; capabilities 非空时还须 ∈ capabilities) → gap (每任务一条)
   severity=medium, confidence 0.85, MODIFY_TASK

无缺口 → 返回 []。severity/confidence 确定性推导 (信号强度, 封顶 0.95)。

边界 (批次 A 基础设施):
- 纯标准库 (json/re/datetime) + 只读引用 session/gap_analyzer.GapAnalysis
  (输出模型) + session/roles.ROLES (合法角色面); 零新依赖, 不修改任何
  现有模块
- review() 纯函数: 只读输入, 不修改 plan/DAG, 不落盘, 不调 LLM

设计: docs/sprint10/S10-062-llm-planning-design.md §6
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from .gap_analyzer import GapAnalysis
from .roles import ROLES

#: 合法角色 (ROLES 8 角色键 — 角色缺口判定的合法面)
VALID_ROLES: tuple[str, ...] = tuple(ROLES.keys())

#: 持久化信号 (PRD/engineering 要求侧 + plan 任务侧共用)
PERSISTENCE_MARKERS: tuple[str, ...] = ("persistence", "持久化", "存储")

#: 测试信号 (任务侧: qa/tester 角色或文本命中)
TEST_ROLES: tuple[str, ...] = ("qa", "tester")
TEST_MARKERS: tuple[str, ...] = ("re:\\btest\\b", "测试", "pytest")

#: UI 平台 (platform ∈ 该集合 → 需要前端任务)
UI_PLATFORMS: tuple[str, ...] = ("mobile", "web")

#: UI 信号 (product/engineering 文本侧)
UI_MARKERS: tuple[str, ...] = ("re:\\bui\\b", "界面", "前端", "frontend")

#: gap_type → (基础 severity, 基础 confidence, recommended_action)
#: (计划级缺口推导基准 — 与 GapAnalyzer.TYPE_PROFILE 对齐, 设计 §6)
TYPE_PROFILE: dict[str, tuple[str, float, str]] = {
    "missing_implementation": ("high", 0.80, "INSERT_TASK"),
    "missing_test": ("medium", 0.80, "INSERT_TASK"),
    "ui_gap": ("low", 0.70, "INSERT_TASK"),
    "dependency_gap": ("medium", 0.85, "MODIFY_TASK"),
}

#: confidence 封顶 (与 GapAnalyzer 一致 — 保留人工评审空间)
CONFIDENCE_CAP = 0.95


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (评审时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


class PlanCritic:
    """执行前计划缺口检查器 (设计 §6): review → list[GapAnalysis]。

    review(plan, product, engineering, capabilities): 4 类 deterministic
    检查 (持久化/测试/UI/角色) → GapAnalysis 列表 (无缺口 → []),
    只输出分析, 不直接修改 DAG/plan (纯函数, 输入不改, 不落盘)。
    severity/confidence 确定性推导 (TYPE_PROFILE + 信号强度, 封顶 0.95)。
    """

    def review(
        self,
        plan: Any = None,
        product: Any = None,
        engineering: Any = None,
        capabilities: Any = None,
    ) -> list[GapAnalysis]:
        """执行前计划缺口检查 (设计 §6) → list[GapAnalysis]。

        plan: 计划任务列表 (list[dict]) 或 {tasks: [...]}; 非 dict 任务跳过;
        product: {platform, name, requirements, ...} (PRD 侧要求);
        engineering: {architecture, modules, technical_tasks, ...};
        capabilities: 可选可用角色列表 (非空时 required_role 还须 ∈ 它)。

        永不修改 plan/product/engineering/capabilities (只读); 永不抛。
        """
        tasks = self._tasks(plan)
        gaps: list[GapAnalysis] = []

        # ---- 1. 持久化缺口 (PRD/engineering 要求但 plan 无实现任务)
        req_text = self._collect_text(product, engineering)
        if self._marker_hit(req_text, PERSISTENCE_MARKERS):
            plan_has = any(
                self._marker_hit(self._collect_text(t), PERSISTENCE_MARKERS)
                for t in tasks
            )
            if not plan_has:
                sources = 1 + (
                    1 if self._marker_hit(
                        self._collect_text(product), PERSISTENCE_MARKERS
                    ) and self._marker_hit(
                        self._collect_text(engineering), PERSISTENCE_MARKERS
                    ) else 0
                )
                gaps.append(self._build(
                    gap_type="missing_implementation",
                    evidence=[
                        "product/engineering 含持久化要求 "
                        f"(命中 {self._marker_hit(req_text, PERSISTENCE_MARKERS)!r})",
                        "plan 无持久化实现任务 (INSERT_TASK 候选)",
                    ],
                    extra_sources=max(0, sources - 1),
                    description=(
                        "实现缺口: 计划缺少持久化实现任务 "
                        "(PRD/engineering 要求持久化)"
                    ),
                    reason=(
                        "PRD/engineering 含持久化要求但 plan 无 persistence 任务 "
                        "— 插入实现任务 (INSERT_TASK)"
                    ),
                ))

        # ---- 2. 测试缺口 (plan 非空但无 QA/测试任务)
        if tasks:
            plan_has_test = any(
                self._is_test_task(t) for t in tasks
            )
            if not plan_has_test:
                gaps.append(self._build(
                    gap_type="missing_test",
                    evidence=[
                        "plan 无 required_role∈{qa, tester} 任务",
                        "plan 无任务含测试信号 (test/测试/pytest)",
                    ],
                    extra_sources=1 if len(tasks) >= 4 else 0,
                    description="测试缺口: 计划缺少 QA/测试任务",
                    reason=(
                        "plan 无 QA/测试任务 — 插入测试任务 (INSERT_TASK)"
                    ),
                ))

        # ---- 3. UI 缺口 (平台/PRD 要求界面但 plan 无前端任务)
        ui_required, explicit_platform = self._ui_required(
            product, engineering
        )
        if ui_required:
            plan_has_ui = any(
                str(t.get("required_role") or t.get("agent_type") or "").lower()
                == "frontend"
                for t in tasks
            )
            if not plan_has_ui:
                gaps.append(self._build(
                    gap_type="ui_gap",
                    evidence=[
                        "product.platform="
                        f"{str((product or {}).get('platform') or '')!r}"
                        if isinstance(product, dict) else "platform 未知",
                        "product/engineering 含 UI 信号 (界面/前端/ui)",
                        "plan 无 required_role=frontend 任务",
                    ],
                    extra_sources=1 if explicit_platform else 0,
                    description="UI 缺口: 平台要求界面但计划无前端任务",
                    reason=(
                        "平台/PRD 要求 UI 但 plan 无前端任务 — 插入前端任务 "
                        "(INSERT_TASK)"
                    ),
                ))

        # ---- 4. 角色缺口 (任务缺 required_role 或角色不合法)
        caps = self._capability_roles(capabilities)
        for t in tasks:
            role = str(
                t.get("required_role") or t.get("agent_type") or ""
            ).strip().lower()
            tid = str(t.get("id") or t.get("task_id") or t.get("name") or "")
            if not role:
                gaps.append(self._build(
                    gap_type="dependency_gap",
                    evidence=[
                        f"任务 {tid or '(无名)'} 缺少 required_role",
                        "任务无法分配 Agent (AgentMatcher 无角色面)",
                    ],
                    extra_sources=0,
                    description=(
                        f"依赖缺口: 任务 {tid or '(无名)'} 缺少 required_role"
                    ),
                    reason=(
                        "plan 任务无 required_role — 需补充合法角色 "
                        f"(MODIFY_TASK); 合法角色: {', '.join(VALID_ROLES)}"
                    ),
                    source_task_id=tid,
                ))
            elif role not in VALID_ROLES or (caps and role not in caps):
                gaps.append(self._build(
                    gap_type="dependency_gap",
                    evidence=[
                        f"任务 {tid or '(无名)'} required_role={role!r} "
                        f"不合法 (∉ {', '.join(VALID_ROLES)})"
                        if role not in VALID_ROLES else
                        f"任务 {tid or '(无名)'} required_role={role!r} "
                        f"不可用 (∉ capabilities)",
                    ],
                    extra_sources=0,
                    description=(
                        f"依赖缺口: 任务 {tid or '(无名)'} 角色不合法/不可用"
                    ),
                    reason=(
                        f"required_role={role!r} 不合法或不可用 — 需修正 "
                        f"(MODIFY_TASK)"
                    ),
                    source_task_id=tid,
                ))
        return gaps

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _tasks(plan: Any) -> list[dict[str, Any]]:
        """plan → 任务 dict 列表 ({tasks: [...]} / list; 非 dict 任务跳过)。"""
        if isinstance(plan, dict) and "tasks" in plan:
            plan = plan["tasks"]
        if isinstance(plan, dict):
            return [dict(t) for t in plan.values() if isinstance(t, dict)]
        if isinstance(plan, list):
            return [dict(t) for t in plan if isinstance(t, dict)]
        return []

    @staticmethod
    def _collect_text(*objs: Any) -> str:
        """dict/str 对象 → 拼接文本 (marker 匹配面; 非预期类型忽略)。"""
        parts: list[str] = []
        for obj in objs:
            if isinstance(obj, dict):
                try:
                    parts.append(json.dumps(obj, ensure_ascii=False, default=str))
                except Exception:  # noqa: BLE001 — 失败安全
                    continue
            elif isinstance(obj, str):
                parts.append(obj)
        return "\n".join(parts)

    @classmethod
    def _marker_hit(cls, text: str, markers: tuple[str, ...]) -> str:
        """文本命中首个信号词 (re: 前缀 = 正则; 其余子串; 失败安全)。"""
        low = str(text or "").lower()
        for m in markers:
            if m.startswith("re:"):
                try:
                    if re.search(m[3:], low):
                        return m[3:]
                except re.error:  # noqa: BLE001 — 失败安全: 坏正则跳过
                    continue
            elif m in low:
                return m
        return ""

    @classmethod
    def _is_test_task(cls, task: dict[str, Any]) -> bool:
        """任务是否为测试任务 (role ∈ {qa, tester} 或文本命中测试信号)。"""
        role = str(
            task.get("required_role") or task.get("agent_type") or ""
        ).lower()
        if role in TEST_ROLES:
            return True
        return bool(cls._marker_hit(cls._collect_text(task), TEST_MARKERS))

    @classmethod
    def _ui_required(
        cls, product: Any, engineering: Any
    ) -> tuple[bool, bool]:
        """是否要求 UI (平台 ∈ {mobile, web} 或 product/engineering 含 UI 信号)。

        返回 (ui_required, explicit_platform)。"""
        platform = ""
        if isinstance(product, dict):
            platform = str(product.get("platform") or "").lower()
        explicit = platform in UI_PLATFORMS
        if explicit:
            return True, True
        text = cls._collect_text(product, engineering)
        return bool(cls._marker_hit(text, UI_MARKERS)), False

    @staticmethod
    def _capability_roles(capabilities: Any) -> set[str]:
        """capabilities → 可用角色集合 (list/dict 兼容; 非预期 → 空集)。"""
        if isinstance(capabilities, list):
            return {str(c).lower() for c in capabilities if c}
        if isinstance(capabilities, dict):
            raw = capabilities.get("roles") or capabilities.get("capabilities")
            if isinstance(raw, list):
                return {str(c).lower() for c in raw if c}
        return set()

    @classmethod
    def _build(
        cls,
        *,
        gap_type: str,
        evidence: list[str],
        extra_sources: int,
        description: str,
        reason: str,
        source_task_id: str = "",
    ) -> GapAnalysis:
        """按 gap_type 组装 GapAnalysis (severity/confidence 推导, 封顶 0.95)。"""
        severity, base_conf, action = TYPE_PROFILE.get(
            gap_type, ("medium", 0.5, "REQUEST_REVIEW")
        )
        conf = round(min(base_conf + 0.05 * max(0, extra_sources), CONFIDENCE_CAP), 2)
        return GapAnalysis(
            detected=True,
            gap_type=gap_type,
            description=description,
            evidence=list(evidence),
            severity=severity,
            source_task_id=source_task_id,
            confidence=conf,
            duplicate_of=None,
            recommended_action=action,
            reason=reason,
            timestamp=_now_iso(),
        )
