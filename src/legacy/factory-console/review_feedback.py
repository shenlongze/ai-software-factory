"""factory-console/review_feedback.py — S10-006 审核反馈记录持久化 (原子写)。

设计依据 (docs/sprint10/api-data-model.md §1 ReviewComment + workspace-architecture.md
§3 Panel Review): Reject 决定的驳回意见除落 gate.comment (S9-001 org 审计) 外,
另存结构化反馈记录 (reviewer/artifact_id/comment/round), 作为下一轮 Agent
重生成输入的数据源 (Feedback Loop)。

数据空间 (与 org/runtimes 并存, 独立互不影响):
```
<root>/review_feedback.json    {"feedback": {id: ReviewFeedback dict}}
```

与 runtime_store 同构 (每实体单文件单节; 原子写 = 临时文件 + os.replace;
损坏 → 响亮 CorruptReviewFeedbackError — 绝不静默丢数据)。

本模块只做持久化 (读/写整库), 无业务逻辑; round 递增/路由校验在
service.py + api/review_feedback.py 层; 零 Core 修改。
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import ReviewFeedback


class ReviewFeedbackError(Exception):
    """ReviewFeedback 基础异常。"""


class CorruptReviewFeedbackError(ReviewFeedbackError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class ReviewFeedbackStore:
    """审核反馈记录库 (<root>/review_feedback.json; 原子写/损坏响亮)。

    仿 runtime_store._JsonStore 模式 — Console 侧独立数据空间实现
    (不跨包 import org.store, 保持 Removal Isolation)。
    """

    _filename = "review_feedback.json"
    _section = "feedback"
    _model = ReviewFeedback

    def __init__(self, dir_path: str | Path):
        self._dir = Path(dir_path)

    @property
    def dir(self) -> Path:
        """数据空间目录。"""
        return self._dir

    # ------------------------------------------------------------------ 读

    def _path(self) -> Path:
        return self._dir / self._filename

    def _read_all(self) -> dict[str, dict[str, Any]]:
        """读整库 {id: dict}; 文件不存在返回空库 (首次写前合法状态)。"""
        path = self._path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptReviewFeedbackError(
                f"corrupt review feedback store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptReviewFeedbackError(
                f"corrupt review feedback store: {path}: missing or invalid "
                f"section {self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> ReviewFeedback:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptReviewFeedbackError(
                f"corrupt review feedback store: {self._path()}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ 写

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        """原子写单文件: 临时文件 + os.replace (同目录, 同文件系统原子性)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 业务 API

    def save(self, record: ReviewFeedback) -> None:
        """保存一条反馈记录 (同 id 覆盖 = 幂等重放)。"""
        records = self._read_all()
        records[record.id] = record.to_dict()
        self._write(records)

    def get(self, record_id: str) -> ReviewFeedback | None:
        """按 id 取记录; 不存在返回 None。"""
        data = self._read_all().get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[ReviewFeedback]:
        """全部记录 (按 round 升序, 审计友好)。"""
        return sorted(
            (self._load(data) for data in self._read_all().values()),
            key=lambda r: (r.artifact_id, r.round, r.id),
        )

    def list_by_artifact(self, artifact_id: str) -> list[ReviewFeedback]:
        """某产物全部反馈 (按 round 升序 — 下轮输入按序消费)。"""
        return [r for r in self.list_all() if r.artifact_id == artifact_id]

    def next_round(self, artifact_id: str) -> int:
        """某产物下一轮序号 (现有最大 round + 1; 无 → 1)。"""
        rounds = [r.round for r in self.list_by_artifact(artifact_id)]
        return (max(rounds) + 1) if rounds else 1

    def count(self) -> int:
        """记录总数。"""
        return len(self._read_all())


def new_feedback_id() -> str:
    """反馈记录 id (fb-<hex>; 唯一 basename, 与 org/runtime id 风格一致)。"""
    return f"fb-{uuid.uuid4().hex[:12]}"
