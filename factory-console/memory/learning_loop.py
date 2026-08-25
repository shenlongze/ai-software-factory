"""factory-console/memory/learning_loop.py — K-3 M4-1 经验闭环 (S10-119, 核心)。

执行完成后自动经验入库 → 下次同类任务路由/执行引用 (带可解释 reason):
- on_execution_complete(record, quality, workspace) -> str
    护栏检查 (总开关/样本质量) → 确定性提取 (task/agent/result/quality_score/
    上下文摘要) → ExperienceStore.add → 画像刷新; 护栏拒绝 → 不写 (诚实返回 "")
- resolve_for_task(objective, workspace) -> Optional[ExperienceHit]
    retrieve_experience (S10-072 统一检索) → 护栏 (样本可信度) → 命中返回
    ExperienceHit{experience_id, summary, reason: "引用经验 X 因为 Y (相似度..)"}
    执行 prompt 引用: 命中 → 注入 "引用经验 X 因为 Y" (reason 可解释)
- refresh_agent_profiles(workspace) -> list[dict]
    M4-5 画像分来源: PatternLearner.learn_agent → agent_profiles.json 落盘
    (capability_router 读取, 失败安全无画像 → 中性)

设计: docs/sprint10/S10-119-k3-learning-loop-plan.md §1.2 (M4-1/B-7/E-1)
边界:
- 纯标准库 (json/dataclasses/pathlib), 零第三方依赖
- 学习核心用确定性规则 (关键词/相似度/护栏), 不调 LLM — 规则分始终存在
- 护栏优先级最高: 任何学习路径可开关 (LearningGuards.enabled)、低质量不写、
  有预算上限 (LearningGuards.budget_ok)
- 失败安全: 任何异常 → 不写/不引用 (返回 ""/None), 不阻断执行链
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from .experience import FAILURE_PATTERN, SUCCESS_PATTERN, ExperienceRecord
from .experience_store import ExperienceStore
from .learning_guards import LearningGuards

#: 经验数据源标记 (on_execution_complete 写入口径)
LEARNING_LOOP_SOURCE = "learning_loop.on_execution_complete"

#: Agent 画像文件名 (M4-5: capability_router 画像分来源)
AGENT_PROFILES_FILE_NAME = "agent_profiles.json"


def agent_profiles_file(workspace: Any = None) -> Path:
    """workspace/memory/agent_profiles.json (缺省 ~/.factory/memory/)。"""
    from .experience_store import memory_dir

    return memory_dir(workspace) / AGENT_PROFILES_FILE_NAME


def load_agent_profiles(workspace: Any = None) -> dict[str, dict[str, Any]]:
    """读 Agent 画像 (M4-5 画像分来源; 失败安全 → {} 无画像中性)。

    返回 {agent_id: profile_dict} (按 agent_id 键控, 供 capability_router)。
    """
    path = agent_profiles_file(workspace)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 缺失/损坏 → 无画像 (中性)
        return {}
    if isinstance(data, list):
        out: dict[str, dict[str, Any]] = {}
        for item in data:
            if isinstance(item, dict) and item.get("agent_id"):
                out[str(item["agent_id"])] = item
        return out
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    return {}


def save_agent_profiles(
    profiles: Any, workspace: Any = None
) -> Path:
    """Agent 画像落盘 (失败安全: 落盘异常不抛; 返回文件路径)。"""
    path = agent_profiles_file(workspace)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [dict(p) for p in (profiles or []) if isinstance(p, dict)],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 — 失败安全
        pass
    return path


def refresh_agent_profiles(
    workspace: Any = None, store: Optional[ExperienceStore] = None
) -> list[dict[str, Any]]:
    """画像刷新 (M4-5): 经验库 → PatternLearner.learn_agent → agent_profiles.json。

    学习护栏: 总开关关闭 → 不刷新 (零变化); 失败安全 → [] 不抛。
    """
    ws = Path(workspace) if workspace is not None else Path.home() / ".factory"
    guards = LearningGuards(workspace=ws)
    if not guards.enabled():
        return []
    try:
        from .learning_engine import PatternLearner

        st = store if store is not None else ExperienceStore.from_workspace(ws)
        profiles = PatternLearner().learn_agent(st.records())
        profile_dicts = [p.to_dict() for p in profiles]
        save_agent_profiles(profile_dicts, ws)
        return profile_dicts
    except Exception:  # noqa: BLE001 — 失败安全: 画像刷新故障不抛
        return []


@dataclass
class ExperienceHit:
    """经验引用命中 (M4-1): 引用对象 + 可解释 reason。

    experience_id: 被引用经验 id; summary: 经验摘要 (problem/result 截断);
    reason: "引用经验 X 因为 Y (相似度 0.xx)" — 可解释, 注入执行 prompt;
    score: 检索相似度 (0-1); dominant: 样本可信度 (n >= MIN_SAMPLES 才主导)。
    """

    experience_id: str
    summary: str
    reason: str
    score: float = 0.0
    dominant: bool = False

    def to_dict(self) -> dict[str, Any]:
        """→ dict (JSON/审计口径)。"""
        return asdict(self)


class LearningLoop:
    """经验闭环 (M4-1/B-7/E-1): 执行完自动入库 + 下次同类任务引用。

    on_execution_complete(record, quality, workspace) -> str:
        护栏 (总开关/样本质量) → 确定性提取 → ExperienceStore.add → 画像刷新;
        返回 experience_id; 护栏拒绝 → "" (诚实不写, 零行为变化)。
    resolve_for_task(objective, workspace) -> Optional[ExperienceHit]:
        统一检索 retrieve_experience → 护栏 (样本可信度) → 命中 ExperienceHit;
        无命中/异常 → None (执行链零变化)。
    """

    def __init__(
        self,
        workspace: Any = None,
        guards: Optional[LearningGuards] = None,
        store: Optional[ExperienceStore] = None,
    ) -> None:
        """workspace 缺省 ~/.factory; guards/store 可注入 (测试隔离)。"""
        self.workspace = Path(workspace) if workspace is not None else Path.home() / ".factory"
        self.guards = guards if guards is not None else LearningGuards(workspace=self.workspace)
        self.store = (
            store
            if store is not None
            else ExperienceStore.from_workspace(self.workspace)
        )

    # ------------------------------------------------------------ 入库

    def on_execution_complete(
        self, record: Any, quality: Any = None, workspace: Any = None
    ) -> str:
        """执行完成后自动经验入库 (护栏内, 确定性提取)。

        record: 执行记录 dict (task/agent/result/error/project/quality...);
        quality: 质量分 dict (score/dimensions — K-2 落盘口径; 缺省从 record 读)。
        返回 experience_id; 护栏拒绝 (关闭/低质量) → "" (诚实不写)。
        """
        if not isinstance(record, dict):
            return ""
        if not self.guards.enabled():
            return ""  # 总开关关闭 → 零行为变化 (向后兼容断言)
        quality = quality if isinstance(quality, dict) else {}
        score = quality.get("score")
        if score is None:
            score = (record.get("quality") or {}).get("score") if isinstance(
                record.get("quality"), dict
            ) else None
        if not self.guards.sample_quality_ok(score):
            return ""  # 低质量/无质量分 → 不写 (诚实, 不污染经验库)
        try:
            extracted = self._extract(record, quality, score)
            item = self.store.add(extracted)
            # M4-5: 画像随经验刷新 (护栏内, 失败安全)
            refresh_agent_profiles(self.workspace, store=self.store)
            return str(item.id)
        except Exception:  # noqa: BLE001 — 失败安全: 入库故障不阻断执行链
            return ""

    def _extract(
        self, record: dict[str, Any], quality: dict[str, Any], score: Any
    ) -> ExperienceRecord:
        """确定性提取: task/agent/result/quality_score/上下文摘要 → ExperienceRecord。

        规则 (不调 LLM): result=success → SUCCESS_PATTERN, 否则 FAILURE_PATTERN;
        problem = error (失败); action = "由 {agent} 执行 {task}"; context = 项目/意图摘要;
        confidence = quality_score (0-1, 兜底 0.5); source = learning_loop。
        """
        task = str(record.get("task") or "")
        agent = str(record.get("agent") or "")
        result = str(record.get("result") or "")
        error = str(record.get("error") or "")
        success = result == "success"
        project = str(record.get("project") or "")
        intent = str(record.get("intent") or "")
        context_parts = [p for p in (project, task, intent) if p]
        context = " | ".join(context_parts) if context_parts else "执行上下文"
        confidence = 0.5
        try:
            value = float(score)
            if value == value and 0.0 <= value <= 1.0:
                confidence = value
        except (TypeError, ValueError):  # noqa: BLE001 — 兜底 0.5
            pass
        return ExperienceRecord(
            type=SUCCESS_PATTERN if success else FAILURE_PATTERN,
            project=project,
            task=task,
            agent=agent,
            role=str(record.get("role") or ""),
            context=context,
            problem=error if error else ("执行失败" if not success else ""),
            action=f"由 {agent} 执行「{task}」" if agent else f"执行「{task}」",
            result=str(
                record.get("result_summary")
                or record.get("result")
                or ("执行成功" if success else "执行失败")
            ),
            success=success,
            confidence=confidence,
            source=LEARNING_LOOP_SOURCE,
        )

    # ------------------------------------------------------------ 引用

    def resolve_for_task(
        self, objective: str, workspace: Any = None
    ) -> Optional[ExperienceHit]:
        """下次同类任务经验引用: 统一检索 → 护栏 (样本可信度) → ExperienceHit。

        无命中/总开关关闭/异常 → None (执行链零变化, 向后兼容)。
        reason 可解释: "引用经验 X 因为 Y (相似度 0.xx; 样本 N 条)" —
        低样本 (n < MIN_SAMPLES) → 追加 "低样本降权参考, 不主导"。
        """
        objective = str(objective or "").strip()
        if not objective:
            return None
        if not self.guards.enabled():
            return None  # 总开关关闭 → 零行为变化
        try:
            from ..retrieval.unified import retrieve_experience

            ws = Path(workspace) if workspace is not None else self.workspace
            store = self.store if workspace is None else ExperienceStore.from_workspace(ws)
            hits, stats = retrieve_experience(
                objective, store=store, top_k=5, max_tokens=2000
            )
            if not hits:
                return None
            best = hits[0]
            score = float(getattr(best, "confidence", 0.0) or 0.0)
            sample_n = self._sample_count(store, objective)
            credible = self.guards.sample_credible(sample_n)
            summary = self._summary_of(best)
            why = self._why_hit(best, objective)
            reason = (
                f"引用经验 {best.id} 因为 {why} (相似度 {score:.2f}; "
                f"同类样本 {sample_n} 条)"
            )
            if not credible:
                reason += " — 低样本降权参考, 不主导"
            return ExperienceHit(
                experience_id=str(best.id),
                summary=summary,
                reason=reason,
                score=round(score, 4),
                dominant=credible,
            )
        except Exception:  # noqa: BLE001 — 失败安全: 引用故障 → None (零变化)
            return None

    @staticmethod
    def _sample_count(store: ExperienceStore, objective: str) -> int:
        """同类样本数: 经验库中 task 与 objective 相同/包含的记录条数 (确定性)。

        口径: r.task == objective (精确同类) 或 r.task 非空且出现在 objective
        中 (任务名包含) — 统计同类任务历史样本量 (护栏 sample_credible 输入)。
        """
        count = 0
        for r in store.records():
            task = str(r.task or "")
            if not task:
                continue
            if task == objective or (objective and task in objective):
                count += 1
        return count

    @staticmethod
    def _summary_of(record: Any) -> str:
        """经验摘要 (problem/result/action 截断 60 字 — prompt 注入口径)。"""
        text = str(
            record.problem
            or record.result
            or record.action
            or record.task
            or ""
        ).strip()
        return text[:60] + ("…" if len(text) > 60 else "")

    @staticmethod
    def _why_hit(record: Any, objective: str) -> str:
        """命中原因 (确定性): 任务/问题/结果与 objective 关键词交集摘要。"""
        text = f"{record.task} {record.problem} {record.result} {record.context}"
        keywords = [
            kw
            for kw in (objective.split() if objective else [])
            if kw and len(kw) >= 2 and kw in text
        ]
        if keywords:
            return "任务匹配关键词 " + ", ".join(keywords[:3])
        if record.task and (record.task in objective or objective in record.task):
            return f"同类任务「{record.task[:24]}」"
        return "历史同类任务经验"


__all__ = [
    "AGENT_PROFILES_FILE_NAME",
    "ExperienceHit",
    "LearningLoop",
    "LEARNING_LOOP_SOURCE",
    "agent_profiles_file",
    "load_agent_profiles",
    "refresh_agent_profiles",
    "save_agent_profiles",
]
