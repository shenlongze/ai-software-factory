"""factory-console/session/eval_loop.py — K-3 E-2/E-3 评估驱动修复/优化闭环 (S10-119)。

低分任务 → 失败分类 → 修复建议 → 应用 (repair_task 机制) → 复评 → 分数提升断言:
- analyze(record, quality)     低分执行记录 → {classification, suggestion,
                               original_score, evidence} (确定性规则, 不调 LLM)
- apply_repair(project_dir, task, suggestion)  应用修复 (RepairManager.create_repair)
- reevaluate(new_quality, original_score)      复评对比 → {improved, 分数变化}
- run(workspace, project, task_id, execute_fn) 完整闭环 (低分 → 建议 → 应用 →
                              修复执行 → 复评; 失败安全)

复用 (不重写): execution_quality.LOW_SCORE_THRESHOLD (K-2 低分阈值) +
RepairManager (S10-053 repair_task 机制) + Validator。

设计: docs/sprint10/S10-119-k3-learning-loop-plan.md §1.7 (E-2/E-3)
边界:
- 纯标准库 (json/pathlib/dataclasses), 零第三方依赖
- 确定性规则 (失败分类/建议), 不调 LLM; 修复执行由调用方注入 (测试/真实链)
- 失败安全: 任何环节故障 → 明确结果字段 (status), 不抛、不假装闭环
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional

#: 低分阈值 (复用 K-2 execution_quality — 低分任务才进修复闭环)
try:
    from .execution_quality import LOW_SCORE_THRESHOLD
except Exception:  # noqa: BLE001 — 失败安全: 阈值缺失 → 0.5 同源缺省
    LOW_SCORE_THRESHOLD = 0.5

#: 失败分类 (确定性规则表): (分类, (错误/维度关键词...), 建议)
#: 顺序即优先级 — 先命中先分类。
FAILURE_CLASSIFIERS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "provider_error",
        ("provider", "api key", "http 429", "http 401", "http 403", "http 5", "timeout", "网络", "鉴权"),
        "更换/检查 LLM Provider 配置 (API Key/网络/限流) 后重试执行",
    ),
    (
        "empty_content",
        ("empty content", "empty response", "空输出", "max_tokens"),
        "增大 max_tokens / 简化任务描述后重试 (推理耗尽 → 空输出)",
    ),
    (
        "patch_apply_failed",
        ("patch apply failed", "hunk", "补丁", "diff 不匹配"),
        "重新生成补丁: 确保源文件上下文与行号匹配后重试",
    ),
    (
        "validation_failed",
        ("validation", "测试失败", "test failed", "assertion", "验证失败"),
        "修复代码缺陷并通过验证 (补充/修正测试后重试)",
    ),
    (
        "scope_creep",
        ("范围", "scope", "过大", "重构"),
        "收窄修改范围: 只改任务要求文件, 拆分过大的改动",
    ),
)

#: 兜底分类 (无信号命中)
DEFAULT_CLASSIFICATION = "other"
DEFAULT_SUGGESTION = "复查失败原因, 补充上下文后重试 (失败分类: other)"


@dataclass
class FixAnalysis:
    """低分任务分析 (E-2): 分类 + 建议 + 证据 (确定性可解释)。"""

    task_id: str = ""
    classification: str = DEFAULT_CLASSIFICATION
    suggestion: str = DEFAULT_SUGGESTION
    original_score: Optional[float] = None
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (闭环结果/审计口径)。"""
        return asdict(self)


@dataclass
class EvalFixResult:
    """评估驱动修复闭环结果 (E-3): 低分 → 建议 → 应用 → 复评。"""

    status: str = "none"          # low_score_applied | no_low_score | none | failed
    task_id: str = ""
    classification: str = ""
    suggestion: str = ""
    repair_id: Optional[str] = None
    repair_status: Optional[str] = None
    original_score: Optional[float] = None
    reevaluated_score: Optional[float] = None
    improved: Optional[bool] = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (API/CLI/测试断言口径)。"""
        return asdict(self)


class EvalFixLoop:
    """评估驱动修复闭环 (E-2/E-3): 确定性规则 + repair_task 机制复用。

    analyze: 低分记录 → 失败分类 + 修复建议 (纯规则);
    apply_repair: 建议 → RepairManager.create_repair (repair_task.json pending);
    run: 完整闭环 — 找低分任务 → analyze → apply → RepairManager.repair →
         复评 → improved 断言 (至少一条可断言闭环)。
    """

    # ------------------------------------------------------------ 分析

    @staticmethod
    def analyze(record: Any, quality: Any = None) -> FixAnalysis:
        """低分执行记录 → 失败分类 + 修复建议 (确定性规则, 不调 LLM)。

        record: 执行记录 dict (task/error/result/quality...);
        quality: 质量分 dict (缺省从 record 读); 分类输入 = error + 质量分维度。
        """
        record = record if isinstance(record, dict) else {}
        quality = quality if isinstance(quality, dict) else {}
        if not quality:
            q = record.get("quality")
            quality = q if isinstance(q, dict) else {}
        score_raw = quality.get("score")
        original_score: Optional[float] = None
        if score_raw is not None:
            try:
                original_score = float(score_raw)
            except (TypeError, ValueError):  # noqa: BLE001 — 无分 → None
                original_score = None
        task_id = str(record.get("task_id") or record.get("task") or "")
        error = str(record.get("error") or "")
        dims = quality.get("dimensions") or {}
        if not isinstance(dims, dict):
            dims = {}
        text = " ".join(
            [
                error,
                str(record.get("result") or ""),
                " ".join(f"{k}={v}" for k, v in dims.items()),
            ]
        ).lower()
        for classification, keywords, suggestion in FAILURE_CLASSIFIERS:
            if any(keyword in text for keyword in keywords):
                return FixAnalysis(
                    task_id=task_id,
                    classification=classification,
                    suggestion=suggestion,
                    original_score=original_score,
                    evidence=error[:120] or f"低分 {original_score} (质量分维度)",
                )
        return FixAnalysis(
            task_id=task_id,
            classification=DEFAULT_CLASSIFICATION,
            suggestion=DEFAULT_SUGGESTION,
            original_score=original_score,
            evidence=error[:120] or f"低分 {original_score} (无失败分类信号)",
        )

    # ------------------------------------------------------------ 应用

    @staticmethod
    def apply_repair(
        project_dir: Any, task: dict[str, Any], suggestion: str
    ) -> dict[str, Any]:
        """应用修复建议 (E-2): RepairManager.create_repair (repair_task 机制)。

        复用 quality.RepairManager — 创建 pending 修复记录; 返回 repair dict。
        失败安全: 异常 → {"repair_id": None, "status": "failed", ...} 不抛。
        """
        try:
            from .quality import RepairManager

            repair = RepairManager.create_repair(
                Path(project_dir),
                task if isinstance(task, dict) else {},
                str(suggestion or "评估驱动修复建议"),
            )
            return dict(repair)
        except Exception as exc:  # noqa: BLE001 — 失败安全
            return {
                "repair_id": None,
                "status": "failed",
                "failure_reason": f"应用修复失败: {exc}",
            }

    # ------------------------------------------------------------ 复评

    @staticmethod
    def reevaluate(
        new_quality: Any, original_score: Optional[float]
    ) -> dict[str, Any]:
        """复评对比 (E-3): 修复后质量分 vs 原始分 → improved 断言。

        new_quality: 修复后质量分 dict (score 必须存在, 否则无法断言提升 —
        诚实标注 score=None 不可断言)。
        """
        new_quality = new_quality if isinstance(new_quality, dict) else {}
        score_raw = new_quality.get("score")
        new_score: Optional[float] = None
        if score_raw is not None:
            try:
                new_score = float(score_raw)
            except (TypeError, ValueError):  # noqa: BLE001 — 无分 → None
                new_score = None
        improved: Optional[bool] = None
        if original_score is not None and new_score is not None:
            improved = new_score > original_score
        return {
            "original_score": original_score,
            "reevaluated_score": new_score,
            "improved": improved,
            "delta": (
                round(new_score - original_score, 4)
                if original_score is not None and new_score is not None
                else None
            ),
        }

    # ------------------------------------------------------------ 完整闭环

    def run(
        self,
        workspace: Any,
        project: str,
        task_id: str = "",
        *,
        execute_fn: Optional[Callable[..., dict[str, Any]]] = None,
    ) -> EvalFixResult:
        """评估驱动修复完整闭环 (E-3): 低分 → 建议 → 应用 → 修复 → 复评。

        workspace: 工厂工作区; project: 项目 slug; task_id: 目标任务 (空 → 最近低分);
        execute_fn: 修复执行函数 (缺省 RepairManager._default_execute_fn 薄调
        execute_task); 返回 EvalFixResult (至少一条可断言闭环: improved)。

        失败安全: 无低分任务 → status=no_low_score; 修复执行失败 → status=failed
        (诚实标注, 不假装闭环)。
        """
        ws = Path(workspace) if workspace is not None else Path.home() / ".factory"
        slug = str(project or "")
        try:
            record = self._latest_low_score_record(ws, slug, task_id)
            if record is None:
                return EvalFixResult(
                    status="no_low_score",
                    task_id=task_id,
                    message=f"项目 {slug or '(全部)'} 无低分执行任务 (score < {LOW_SCORE_THRESHOLD})",
                )
            analysis = self.analyze(record)
            task = self._task_for(ws, slug, analysis.task_id) or {
                "id": analysis.task_id or task_id,
                "name": str(record.get("task") or analysis.task_id or ""),
            }
            project_dir = ws / "projects" / slug if slug else ws
            project_dir.mkdir(parents=True, exist_ok=True)
            repair = self.apply_repair(project_dir, task, analysis.suggestion)
            repair_id = repair.get("repair_id")
            repair_status: Optional[str] = None
            if repair_id:
                from .quality import RepairManager

                outcome = RepairManager().repair(project_dir, execute_fn=execute_fn)
                repair_status = str(outcome.get("status") or "none")
            new_score: Optional[float] = None
            improved: Optional[bool] = None
            if repair_status == "completed":
                new_record = self._latest_record(ws, slug, analysis.task_id)
                new_quality = (
                    new_record.get("quality")
                    if isinstance(new_record, dict)
                    else None
                )
                re = self.reevaluate(new_quality, analysis.original_score)
                new_score = re["reevaluated_score"]
                improved = re["improved"]
            return EvalFixResult(
                status="low_score_applied" if repair_id else "failed",
                task_id=analysis.task_id or task_id,
                classification=analysis.classification,
                suggestion=analysis.suggestion,
                repair_id=repair_id,
                repair_status=repair_status,
                original_score=analysis.original_score,
                reevaluated_score=new_score,
                improved=improved,
                message=self._message(analysis, repair_status, new_score, improved),
            )
        except Exception as exc:  # noqa: BLE001 — 失败安全: 闭环故障不抛
            return EvalFixResult(
                status="failed",
                task_id=task_id,
                message=f"评估驱动修复闭环失败: {exc}",
            )

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _exec_records(ws: Path, slug: str) -> list[dict[str, Any]]:
        """执行记录列表 (workspace/exec/execution_records.json; 失败安全 → [])。"""
        path = ws / "exec" / "execution_records.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001 — 失败安全
            return []

    @classmethod
    def _latest_low_score_record(
        cls, ws: Path, slug: str, task_id: str = ""
    ) -> Optional[dict[str, Any]]:
        """最近一次低分执行记录 (score < 阈值; task_id 过滤可选; 无 → None)。"""
        records = cls._exec_records(ws, slug)
        if slug:
            records = [
                r
                for r in records
                if str(r.get("project") or "").lower() == slug.lower()
                or str(r.get("input_snapshot") or {}).get("context", {}).get("project", "").lower()
                == slug.lower()
            ]
        if task_id:
            records = [
                r
                for r in records
                if task_id in str(r.get("task") or "") or task_id in str(r.get("task_id") or "")
            ]
        low: list[dict[str, Any]] = []
        for r in records:
            q = r.get("quality")
            q = q if isinstance(q, dict) else {}
            try:
                score = float(q.get("score"))
            except (TypeError, ValueError):  # noqa: BLE001 — 无分 → 不算低分
                continue
            if score < LOW_SCORE_THRESHOLD:
                low.append(r)
        if not low:
            return None
        low.sort(key=lambda r: str(r.get("timestamp") or ""))
        return low[-1]

    @classmethod
    def _latest_record(
        cls, ws: Path, slug: str, task_id: str = ""
    ) -> Optional[dict[str, Any]]:
        """最近一次执行记录 (task_id 过滤可选; 无 → None)。"""
        records = cls._exec_records(ws, slug)
        if slug:
            records = [
                r
                for r in records
                if str(r.get("project") or "").lower() == slug.lower()
                or str(r.get("input_snapshot") or {}).get("context", {}).get("project", "").lower()
                == slug.lower()
            ]
        if task_id:
            records = [
                r
                for r in records
                if task_id in str(r.get("task") or "") or task_id in str(r.get("task_id") or "")
            ]
        if not records:
            return None
        records.sort(key=lambda r: str(r.get("timestamp") or ""))
        return records[-1]

    @staticmethod
    def _task_for(ws: Path, slug: str, task_id: str) -> Optional[dict[str, Any]]:
        """execution_state.json 中任务 (id 匹配; 无 → None)。"""
        if not slug:
            return None
        state_file = ws / "projects" / slug / "execution_state.json"
        if not state_file.is_file():
            return None
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全
            return None
        for t in state.get("tasks") or []:
            if isinstance(t, dict) and str(t.get("id") or "") == str(task_id):
                return t
        return None

    @staticmethod
    def _message(
        analysis: FixAnalysis,
        repair_status: Optional[str],
        new_score: Optional[float],
        improved: Optional[bool],
    ) -> str:
        """闭环消息 (可读/可断言)。"""
        if repair_status == "completed" and new_score is not None:
            arrow = "提升" if improved else ("未提升" if improved is False else "无法断言")
            return (
                f"评估驱动修复闭环: 低分 {analysis.original_score} → 分类 "
                f"{analysis.classification} → 建议「{analysis.suggestion}」→ 修复 "
                f"{repair_status} → 复评 {new_score} ({arrow})"
            )
        return (
            f"评估驱动修复闭环: 分类 {analysis.classification} → 建议「{analysis.suggestion}」"
            f" → 修复 {repair_status or '未执行'}"
        )


__all__ = [
    "DEFAULT_CLASSIFICATION",
    "DEFAULT_SUGGESTION",
    "EvalFixLoop",
    "EvalFixResult",
    "FAILURE_CLASSIFIERS",
    "FixAnalysis",
    "LOW_SCORE_THRESHOLD",
]
