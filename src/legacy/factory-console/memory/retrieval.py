"""factory-console/memory/retrieval.py — ExperienceRetriever (S10-067 G5)。

经验检索: 关键词匹配 (project/problem/context/result) + 类型/项目过滤 +
confidence 排序; similar_projects(特征) → 相似项目经验。

设计: docs/sprint10/S10-067-memory-learning-design.md §5
边界:
- 纯标准库, 零模块依赖; 失败安全 (空库/空查询 → 空结果, 不抛)
- 关键词+规则检索 (GAP 五不该: 不引入向量数据库/embedding)
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .experience import ExperienceRecord
from .experience_store import ExperienceStore, experience_store_file


def _tokenize(text: str) -> list[str]:
    """查询分词: 空白/中英文逗号分号分隔 (去空)。"""
    return [
        part.strip()
        for part in re.split(r"[\s,，;；、]+", text or "")
        if part.strip()
    ]


class ExperienceRetriever:
    """经验检索器 (G5): search() + similar_projects()。

    search(query, project=None, type=None): 关键词命中任一记录字段
      (project/problem/context/result) → 候选; 类型/项目过滤; confidence 降序
      (同 confidence → created_at 降序 — 最新优先)。
    similar_projects(features): 项目特征匹配 → [{project, matched_features,
      record_count, failure_count}] (样本量降序)。
    """

    def __init__(
        self,
        store: Optional[ExperienceStore] = None,
        records: Optional[list[ExperienceRecord]] = None,
    ) -> None:
        if records is not None:
            self._records = list(records)
        elif store is not None:
            self._records = store.records()
        else:
            self._records = ExperienceStore(experience_store_file()).records()

    @classmethod
    def from_workspace(cls, workspace: Any = None) -> "ExperienceRetriever":
        """workspace 装配 (workspace/memory/experience_store.json)。"""
        return cls(ExperienceStore.from_workspace(workspace))

    # ------------------------------------------------------------ 检索

    def search(
        self,
        query: str = "",
        project: Optional[str] = None,
        type: Optional[str] = None,
    ) -> list[ExperienceRecord]:
        """关键词检索 (G5): project/problem/context/result 命中 + 过滤 + 排序。

        空查询 → 全量 (仅应用 project/type 过滤); 类型非法 → 空结果 (过滤语义)。
        """
        keywords = _tokenize(query)
        out = self._records
        if project is not None:
            out = [r for r in out if r.project == str(project)]
        if type is not None:
            out = [r for r in out if r.type == str(type)]
        if keywords:
            out = [
                r
                for r in out
                if any(kw in r.project or kw in r.problem or kw in r.context or kw in r.result for kw in keywords)
            ]
        # confidence 降序 + created_at 降序 (稳定确定性 — 最新经验优先)
        out.sort(key=lambda r: (r.confidence, r.created_at), reverse=True)
        return out

    # ------------------------------------------------------------ 相似项目

    def similar_projects(self, features: Any) -> list[dict[str, Any]]:
        """相似项目 (G5): 特征关键词 → 项目匹配度视图。

        features: str (分词) 或 list[str]; 返回 [{project, matched_features,
        record_count, failure_count}] — record_count 降序 (确定性)。
        """
        if isinstance(features, (list, tuple)):
            keywords = [str(f) for f in features if str(f).strip()]
        else:
            keywords = _tokenize(str(features or ""))
        if not keywords:
            return []
        per_project: dict[str, dict[str, Any]] = {}
        for r in self._records:
            if not r.project:
                continue
            text = f"{r.problem} {r.context} {r.result} {r.task}"
            matched = [kw for kw in keywords if kw in text]
            if not matched:
                continue
            entry = per_project.setdefault(
                r.project,
                {
                    "project": r.project,
                    "matched_features": [],
                    "record_count": 0,
                    "failure_count": 0,
                },
            )
            entry["record_count"] += 1
            if not r.success:
                entry["failure_count"] += 1
            for kw in matched:
                if kw not in entry["matched_features"]:
                    entry["matched_features"].append(kw)
        projects = sorted(
            per_project.values(), key=lambda e: (-e["record_count"], e["project"])
        )
        return projects
