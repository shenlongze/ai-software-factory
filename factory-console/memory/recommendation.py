"""factory-console/memory/recommendation.py — Recommender (S10-067 G7)。

经验影响未来: planning/debug 提醒 — 基于历史经验 (检索 → 提醒), 不执行动作。
- recommend_for_planning(features) → 规划提醒 ("类似项目曾因...失败, 建议...")
- recommend_for_debug(problem)   → 调试提醒 (历史解决方案)

设计: docs/sprint10/S10-067-memory-learning-design.md §5 (→ S10-068 Debug 基础)
边界:
- 纯标准库, 零模块依赖; 失败安全 (无经验 → 兜底提示, 不抛)
- 只读提醒 (Recommendation 不修改任何状态 — 影响未来由上层决定)
"""

from __future__ import annotations

from typing import Any, Optional

from .experience import (
    DEBUG_EXPERIENCE,
    FAILURE_PATTERN,
    PLANNING_EXPERIENCE,
    ExperienceRecord,
)
from .retrieval import ExperienceRetriever

#: 规划提醒看的历史经验类型 (失败/规划缺口)
_PLANNING_TYPES: tuple[str, ...] = (FAILURE_PATTERN, PLANNING_EXPERIENCE)
#: 调试提醒看的历史经验类型 (调试/失败)
_DEBUG_TYPES: tuple[str, ...] = (DEBUG_EXPERIENCE, FAILURE_PATTERN)

#: 兜底提示 (无历史经验时 — 不假装有经验)
_NO_HISTORY = "暂无相关历史经验, 按标准流程执行即可。"


class Recommender:
    """经验推荐器 (G7): 检索历史经验 → 影响未来 (planning/debug 提醒)。

    recommend_for_planning(project_features): 相似项目失败/缺口 → 提醒
      "项目 X 曾因 Y 失败 (n 次) — 建议...";
    recommend_for_debug(problem): 问题关键词 → 历史调试经验 → "历史方案: ..."。
    """

    def __init__(self, retriever: Optional[ExperienceRetriever] = None) -> None:
        self.retriever = retriever if retriever is not None else ExperienceRetriever()

    @classmethod
    def from_workspace(cls, workspace: Any = None) -> "Recommender":
        """workspace 装配 (复用 ExperienceRetriever.from_workspace)。"""
        return cls(ExperienceRetriever.from_workspace(workspace))

    # ------------------------------------------------------------ 规划提醒

    def recommend_for_planning(self, project_features: Any) -> list[str]:
        """规划提醒 (G7): 相似项目历史失败/缺口 → 建议字符串列表。

        project_features: 特征关键词 (str 或 list[str]); 每个匹配项目
        (最多 3 个) 生成 1 条提醒 — "项目 {slug} 曾因 {problem} 失败
        ({n} 次), 建议规划时优先覆盖该风险。"
        """
        similar = self.retriever.similar_projects(project_features)
        if not similar:
            return [_NO_HISTORY]
        reminders: list[str] = []
        for entry in similar[:3]:
            slug = entry["project"]
            records = [
                r
                for r in self.retriever.search("", project=slug)
                if r.type in _PLANNING_TYPES and not r.success
            ]
            if not records:
                continue
            problem = records[0].problem or "未知问题"
            reminders.append(
                f"项目 {slug} 曾因「{problem}」失败 ({len(records)} 次) — "
                "建议规划时优先覆盖该风险。"
            )
        return reminders or [_NO_HISTORY]

    # ------------------------------------------------------------ 调试提醒

    def recommend_for_debug(self, problem: str) -> list[str]:
        """调试提醒 (G7): 问题关键词 → 历史调试/失败经验 (最多 3 条)。

        每条: "历史方案 [{type}]: {problem} → {action/result}"
        (有成功修复经验优先 — 排序由 retriever confidence 决定)。
        """
        # S10-072 P0-B: 统一检索入口 (经 RetrievalOrchestrator)
        try:
            from ..retrieval.unified import retrieve_experience

            store = getattr(self.retriever, "store", None) or getattr(self.retriever, "_store", None)
            recs = getattr(self.retriever, "_records", None)
            hits, _stats = retrieve_experience(str(problem or ""), store=store,
                                               records=recs, top_k=10)
            hits = [r for r in hits if r.type in _DEBUG_TYPES]
        except Exception:  # noqa: BLE001 — 失败安全
            hits = []
        if not hits:
            return [_NO_HISTORY]
        suggestions: list[str] = []
        for r in hits[:3]:
            solution = r.action or r.result or "无记录"
            suggestions.append(
                f"历史方案 [{r.type}]: {r.problem} → {solution}"
            )
        return suggestions
