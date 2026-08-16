"""factory-console/memory/extraction.py — ExperienceExtractor (S10-067 G3)。

自动提取: 现有数据资产 (execution_records/repair_task/replanning_decisions/
gap_analysis/validation_result) → ExperienceRecord。核心学习循环第一环:
Execution → Observation → Learning (数据 → 经验)。

设计: docs/sprint10/S10-067-memory-learning-design.md §3
数据源 → 经验类型:
- execution_records (失败)  → FAILURE_PATTERN (失败原因/error)
- execution_records (成功)  → SUCCESS_PATTERN (成功方案)
- repair_task              → DEBUG_EXPERIENCE (修复经验)
- replanning_decisions     → PLANNING_EXPERIENCE (规划缺口模式)
- gap_analysis             → PLANNING_EXPERIENCE (缺口模式)
- validation_result (失败) → DEBUG_EXPERIENCE (验证失败模式)

边界:
- 纯标准库 (json/pathlib), 零模块依赖; 失败安全 (缺失/损坏 → [])
- 幂等: 同源同内容 → 同 id (内容哈希) — 重跑不产生重复经验
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .experience import (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    PLANNING_EXPERIENCE,
    SUCCESS_PATTERN,
    ExperienceRecord,
    make_record_id,
)

#: 数据资产文件名 (与既有资产口径一致 — 不造新数据源)
EXECUTION_RECORDS_FILE = "execution_records.json"      # workspace/exec/
REPAIR_TASK_FILE = "repair_task.json"                   # projects/<slug>/
REPLANNING_DECISIONS_FILE = "replanning_decisions.json"  # projects/<slug>/
GAP_ANALYSIS_FILE = "gap_analysis.json"                 # projects/<slug>/ + teams/
VALIDATION_RESULT_FILE = "validation_result.json"       # projects/<slug>/

#: 成功结果别名 (result 字段取值 — 同 agents.AgentMetrics 口径)
_SUCCESS_RESULTS: frozenset[str] = frozenset(
    {"success", "ok", "passed", "completed", "done", "succeeded"}
)

#: 修复完成状态 (repair_task.status)
_REPAIR_DONE: frozenset[str] = frozenset({"completed", "success", "done"})

#: 重规划决策类型 (PLANNING_EXPERIENCE 语义)
_PLANNING_DECISIONS: frozenset[str] = frozenset(
    {"INSERT_TASK", "MODIFY_TASK", "DELETE_TASK", "REORDER", "REPLAN"}
)


def _load_json(path: Path) -> Any:
    """读 JSON (缺失/损坏 → None 失败安全)。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 失败安全
        return None


def _as_list(data: Any) -> list[dict[str, Any]]:
    """任意结构 → dict 记录列表 (list 过滤 dict; 单 dict → [dict]; 其他 → [])。"""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        return [data]
    return []


class ExperienceExtractor:
    """自动提取器 (G3): 4+ 数据源 → ExperienceRecord 列表。

    extract_from_records(execution_records)  — 失败 → FAILURE_PATTERN / 成功 → SUCCESS_PATTERN
    extract_from_repairs(repair_tasks)       — DEBUG_EXPERIENCE
    extract_from_replanning(replanning)      — PLANNING_EXPERIENCE
    extract_from_gaps(gap_analyses)          — PLANNING_EXPERIENCE
    extract_from_validation(validation)      — DEBUG_EXPERIENCE (验证失败)
    extract_all(workspace)                   — 聚合全部数据源 (失败安全)
    """

    # ------------------------------------------------------------ 提取器

    @staticmethod
    def extract_from_records(
        records: list[dict[str, Any]],
    ) -> list[ExperienceRecord]:
        """执行记录 → 经验 (G3): 失败 → FAILURE_PATTERN, 成功 → SUCCESS_PATTERN。

        problem = error (失败) / task (成功); context = task + intent;
        confidence: 失败带 error → 0.8, 其余 0.6。
        """
        out: list[ExperienceRecord] = []
        for record in _as_list(records):
            result = str(record.get("result") or "").lower()
            success = result in _SUCCESS_RESULTS
            task = str(record.get("task") or "")
            error = str(record.get("error") or "")
            intent = str(record.get("intent") or "")
            action = str(record.get("action") or "")
            agent = str(record.get("agent") or "")
            problem = error or task or "未知任务"
            record_type = SUCCESS_PATTERN if success else FAILURE_PATTERN
            out.append(
                ExperienceRecord(
                    id=make_record_id(
                        "execution_records",
                        str(record.get("project") or ""),
                        task,
                        problem,
                        action,
                        result,
                    ),
                    type=record_type,
                    project=str(record.get("project") or ""),
                    task=task,
                    agent=agent,
                    context=f"{intent} {task}".strip(),
                    problem=problem,
                    action=action,
                    result=result,
                    success=success,
                    confidence=0.8 if (not success and error) else 0.6,
                    source="execution_records",
                    created_at=str(record.get("timestamp") or ""),
                )
            )
        return out

    @staticmethod
    def extract_from_repairs(
        repair_tasks: list[dict[str, Any]],
    ) -> list[ExperienceRecord]:
        """修复记录 → DEBUG_EXPERIENCE (G3): 失败原因 + 修复动作 + 结果。"""
        out: list[ExperienceRecord] = []
        for repair in _as_list(repair_tasks):
            status = str(repair.get("status") or "").lower()
            problem = str(repair.get("failure_reason") or "未知失败原因")
            task = str(repair.get("original_task_name") or "")
            out.append(
                ExperienceRecord(
                    id=make_record_id(
                        "repair_task",
                        str(repair.get("project") or ""),
                        str(repair.get("original_task_id") or task),
                        problem,
                        "repair",
                        status,
                    ),
                    type=DEBUG_EXPERIENCE,
                    project=str(repair.get("project") or ""),
                    task=task,
                    problem=problem,
                    action="repair",
                    result=status,
                    success=status in _REPAIR_DONE,
                    confidence=0.7,
                    source="repair_task",
                    created_at=str(repair.get("created_at") or ""),
                )
            )
        return out

    @staticmethod
    def extract_from_replanning(
        replanning_decisions: list[dict[str, Any]],
    ) -> list[ExperienceRecord]:
        """重规划决策 → PLANNING_EXPERIENCE (G3): 缺口原因 + 规划动作。"""
        out: list[ExperienceRecord] = []
        for decision in _as_list(replanning_decisions):
            decision_type = str(decision.get("decision") or "")
            reason = str(decision.get("reason") or "")
            new_tasks = decision.get("new_tasks") or []
            modified = decision.get("modified_tasks") or []
            plan_version = str(decision.get("plan_version") or "")
            action_parts: list[str] = []
            if isinstance(new_tasks, list):
                action_parts.extend(
                    f"新增 {t.get('id')} {t.get('name')}"
                    for t in new_tasks
                    if isinstance(t, dict) and (t.get("id") or t.get("name"))
                )
            if isinstance(modified, list):
                action_parts.extend(
                    f"修改 {t.get('id') or t.get('name')}"
                    for t in modified
                    if isinstance(t, dict)
                )
            action = "; ".join(action_parts) or decision_type or "重规划"
            out.append(
                ExperienceRecord(
                    id=make_record_id(
                        "replanning_decisions",
                        str(decision.get("project") or ""),
                        decision_type,
                        reason,
                        action,
                        f"plan_version {plan_version}".strip(),
                    ),
                    type=PLANNING_EXPERIENCE,
                    project=str(decision.get("project") or ""),
                    task=decision_type,
                    problem=reason or f"计划缺口 ({decision_type})",
                    action=action,
                    result=f"plan_version {plan_version}".strip() or decision_type,
                    success=True,
                    confidence=0.6,
                    source="replanning_decisions",
                    created_at=str(decision.get("timestamp") or ""),
                )
            )
        return out

    @staticmethod
    def extract_from_gaps(
        gap_analyses: list[dict[str, Any]],
    ) -> list[ExperienceRecord]:
        """缺口分析 → PLANNING_EXPERIENCE (G3): 缺口类型 + 推荐动作。"""
        out: list[ExperienceRecord] = []
        for gap in _as_list(gap_analyses):
            detected = bool(gap.get("detected", True))
            gap_type = str(gap.get("gap_type") or "unknown")
            description = str(gap.get("description") or "")
            recommended = str(gap.get("recommended_action") or "")
            reason = str(gap.get("reason") or "")
            try:
                confidence = float(gap.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            problem = description or f"{gap_type} 缺口"
            action = recommended or "NO_ACTION"
            if reason:
                action = f"{action} ({reason})"
            out.append(
                ExperienceRecord(
                    id=make_record_id(
                        "gap_analysis",
                        str(gap.get("project") or ""),
                        str(gap.get("source_task_id") or ""),
                        problem,
                        action,
                        gap_type,
                    ),
                    type=PLANNING_EXPERIENCE,
                    project=str(gap.get("project") or ""),
                    task=str(gap.get("source_task_id") or ""),
                    problem=problem,
                    action=action,
                    result=gap_type,
                    success=not detected,
                    confidence=max(0.4, min(0.95, confidence)) if confidence else 0.6,
                    source="gap_analysis",
                    created_at=str(gap.get("timestamp") or ""),
                )
            )
        return out

    @staticmethod
    def extract_from_validation(
        validation_results: list[dict[str, Any]],
    ) -> list[ExperienceRecord]:
        """验证结果 (失败) → DEBUG_EXPERIENCE (G3): 验证失败模式。"""
        out: list[ExperienceRecord] = []
        for validation in _as_list(validation_results):
            success = bool(validation.get("success", True))
            if success:
                continue  # 只有验证失败才是经验 (成功验证无学习价值)
            errors = validation.get("errors") or []
            problem = "验证失败"
            if isinstance(errors, list) and errors:
                problem = f"验证失败: {errors[0]}"
            project = str(
                validation.get("project")
                or validation.get("project_id")
                or ""
            )
            out.append(
                ExperienceRecord(
                    id=make_record_id(
                        "validation_result",
                        project,
                        str(validation.get("task") or ""),
                        problem,
                        "验证重跑",
                        "failed",
                    ),
                    type=DEBUG_EXPERIENCE,
                    project=project,
                    task=str(validation.get("task") or ""),
                    problem=problem,
                    action="验证重跑",
                    result="failed",
                    success=False,
                    confidence=0.7,
                    source="validation_result",
                    created_at=str(validation.get("timestamp") or ""),
                )
            )
        return out

    # ------------------------------------------------------------ 聚合

    @classmethod
    def extract_all(cls, workspace: Any = None) -> list[ExperienceRecord]:
        """聚合全部数据源 (G3/验收 B): workspace 下 exec + projects + teams。

        数据源 (缺失/损坏 → 跳过, 失败安全):
          workspace/exec/execution_records.json
          workspace/projects/<slug>/{repair_task, replanning_decisions,
            gap_analysis, validation_result}.json
          workspace/teams/gap_analysis.json (全局缺口 — S10-061 缺省资产)
        """
        root = Path(workspace) if workspace is not None else Path.home() / ".factory"
        out: list[ExperienceRecord] = []

        # 1) 全局执行记录 (exec/execution_records.json)
        records_data = _load_json(root / "exec" / EXECUTION_RECORDS_FILE)
        out.extend(cls.extract_from_records(_as_list(records_data)))

        # 2) 项目级资产 (projects/<slug>/*)
        projects_dir = root / "projects"
        if projects_dir.is_dir():
            for slug_dir in sorted(
                p for p in projects_dir.iterdir() if p.is_dir()
            ):
                slug = slug_dir.name
                out.extend(
                    cls._annotate_project(
                        cls.extract_from_repairs(
                            _as_list(_load_json(slug_dir / REPAIR_TASK_FILE))
                        ),
                        slug,
                    )
                )
                out.extend(
                    cls._annotate_project(
                        cls.extract_from_replanning(
                            _as_list(
                                _load_json(slug_dir / REPLANNING_DECISIONS_FILE)
                            )
                        ),
                        slug,
                    )
                )
                out.extend(
                    cls._annotate_project(
                        cls.extract_from_gaps(
                            _as_list(_load_json(slug_dir / GAP_ANALYSIS_FILE))
                        ),
                        slug,
                    )
                )
                out.extend(
                    cls._annotate_project(
                        cls.extract_from_validation(
                            _as_list(_load_json(slug_dir / VALIDATION_RESULT_FILE))
                        ),
                        slug,
                    )
                )

        # 3) 全局缺口资产 (teams/gap_analysis.json — S10-061 缺省文件)
        teams_gaps = _as_list(_load_json(root / "teams" / GAP_ANALYSIS_FILE))
        out.extend(cls.extract_from_gaps(teams_gaps))

        return out

    @staticmethod
    def _annotate_project(
        records: list[ExperienceRecord], slug: str
    ) -> list[ExperienceRecord]:
        """项目 slug 注入 (提取器内部 — 数据源文件无 project 字段时兜底)。"""
        for r in records:
            if not r.project:
                r.project = slug
        return records
