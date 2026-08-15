"""factory-console/session/progress.py — ProductProgressTracker (S10-055 Task 003)。

功能级进度: product_progress.json — 回答 "做到哪里" (功能粒度, 非任务粒度)。
G2 缺口: product_progress.json 不存在 → 无法回答 "做到哪里"。

组件:
- ProductProgressTracker — init (ProductIntent + 任务 → 全 pending 文档) /
  update_from_execution (execution_state → 功能完成度) /
  save / load (product_progress.json 落盘/读取)

数据模型 (product_progress.json 内容):
  {
    "product": <产品名>,
    "status": pending | in_progress | completed,     # 整体功能完成度
    "tasks_total": N,
    "tasks_completed": M,
    "features": [
      {"name": <功能名>, "status": pending|in_progress|completed,
       "total_tasks": n, "completed_tasks": m}, ...
    ]
  }

状态推导 (每 feature, 验收 D):
  total_tasks <= 0            → pending
  completed_tasks == total    → completed
  completed_tasks > 0         → in_progress
  其余                        → pending
整体 status: 无 feature → pending; 全 completed → completed; 有 in_progress
(或部分完成) → in_progress; 否则 pending。

边界:
- 纯标准库零依赖; 不 import .orchestrator/.actions (供 orchestrator/actions
  引用, 无循环依赖 — 本模块只依赖 .product.ProductIntent)
- 只建模/计算/落盘, 不执行业务; 失败安全 (损坏 product_progress.json → None)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .product import ProductIntent

#: 功能状态常量 (落盘小写, 同 Lifecycle 口径)
FEATURE_PENDING = "pending"
FEATURE_IN_PROGRESS = "in_progress"
FEATURE_COMPLETED = "completed"

#: 任务缺省落组名 (旧式 execution_state 无 feature 字段 — 向后兼容分组)
_UNGROUPED = "未分组"


class ProductProgressTracker:
    """功能级进度跟踪器 (S10-055 Task 003, 验收 C/D)。

    init: ProductIntent + 任务 → 初始进度文档 (全 pending, features 按
    task.feature 去重保序 — 回答 "有哪些功能/各多少任务")。
    update_from_execution: execution_state (ExecutionState/dict) → 功能完成度
    文档 (回答 "做到哪里" — 每功能 total/completed/status)。
    save/load: product_progress.json 落盘/读取 (失败安全: 损坏 → None)。
    """

    FEATURE_PENDING = FEATURE_PENDING
    FEATURE_IN_PROGRESS = FEATURE_IN_PROGRESS
    FEATURE_COMPLETED = FEATURE_COMPLETED

    # ------------------------------------------------------------ 构建

    @classmethod
    def init(cls, product: ProductIntent, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """ProductIntent + 任务列表 → 初始进度文档 (全 pending)。

        features 按任务 feature 归属去重保序; 无任务/无归属 → 空 features。
        """
        features: dict[str, dict[str, Any]] = {}
        for task in tasks or []:
            if not isinstance(task, dict):
                continue
            fname = str(task.get("feature") or _UNGROUPED)
            feat = features.setdefault(
                fname,
                {
                    "name": fname,
                    "status": cls.FEATURE_PENDING,
                    "total_tasks": 0,
                    "completed_tasks": 0,
                },
            )
            feat["total_tasks"] += 1
        return cls._compose(
            str(product.name) if product is not None else "", list(features.values())
        )

    @classmethod
    def update_from_execution(
        cls, state: Any, product_name: Optional[str] = None
    ) -> dict[str, Any]:
        """execution_state (ExecutionState/dict) → 功能完成度文档 (验收 D)。

        state 兼容两种形态: ExecutionState 对象 (hasattr tasks) 或
        execution_state.json 的 dict (get("tasks")) — 前向兼容。
        每功能: total_tasks = 归属任务数, completed_tasks = status=="completed" 数。
        """
        if hasattr(state, "tasks"):
            tasks = state.tasks
            name = product_name or str(getattr(state, "project", "") or "")
        elif isinstance(state, dict):
            tasks = state.get("tasks") or []
            name = product_name or str(state.get("project") or "")
        else:
            tasks = []
            name = product_name or ""
        counts: dict[str, list[int]] = {}
        for task in tasks or []:
            if not isinstance(task, dict):
                continue
            fname = str(task.get("feature") or _UNGROUPED)
            bucket = counts.setdefault(fname, [0, 0])
            bucket[0] += 1
            if task.get("status") == "completed":
                bucket[1] += 1
        features = [
            {
                "name": fname,
                "status": cls._feature_status(total, done),
                "total_tasks": total,
                "completed_tasks": done,
            }
            for fname, (total, done) in counts.items()
        ]
        return cls._compose(name, features)

    @classmethod
    def _feature_status(cls, total: int, completed: int) -> str:
        """功能状态推导 (验收 D): 全完成 → completed; 部分 → in_progress; 其余 → pending。"""
        if total <= 0:
            return cls.FEATURE_PENDING
        if completed >= total:
            return cls.FEATURE_COMPLETED
        if completed > 0:
            return cls.FEATURE_IN_PROGRESS
        return cls.FEATURE_PENDING

    @classmethod
    def _compose(
        cls, product_name: str, features: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """features → 完整进度文档 (整体 status 推导 + 汇总计数)。"""
        total = sum(int(f.get("total_tasks") or 0) for f in features)
        done = sum(int(f.get("completed_tasks") or 0) for f in features)
        if features and all(
            f.get("status") == cls.FEATURE_COMPLETED for f in features
        ):
            overall = cls.FEATURE_COMPLETED
        elif done > 0:
            overall = cls.FEATURE_IN_PROGRESS
        else:
            overall = cls.FEATURE_PENDING
        return {
            "product": product_name or "",
            "status": overall,
            "tasks_total": total,
            "tasks_completed": done,
            "features": features,
        }

    # ------------------------------------------------------------ 落盘/读取

    @classmethod
    def save(cls, project_dir: Path, progress: dict[str, Any]) -> Path:
        """进度文档 → product_progress.json (验收 C; 中文可读, 父目录自动创建)。"""
        path = Path(project_dir) / "product_progress.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, project_dir: Path) -> Optional[dict[str, Any]]:
        """product_progress.json 读取 (验收 C); 缺失 → None; 损坏 → None (失败安全)。"""
        path = Path(project_dir) / "product_progress.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 损坏 → None, 不裸抛
            return None
        return data if isinstance(data, dict) else None
