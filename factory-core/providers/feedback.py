"""providers/feedback.py — Provider 人工反馈接口预留 (Phase 8B-3)。

设计依据:
- phase8b3-status.md §4: ProviderFeedback (provider_id/execution_id/task_id/
  rating/comment/approved/created_at) + FeedbackStore (.factory/providers/
  feedback.json 独立空间) + Event: provider.feedback.created (经 EventLogger)。
- Provider Intelligence Loop (docs/provider-intelligence-model.md): 执行经验
  (Human Feedback) 是推荐闭环的最后一环 — 本模块只提供数据接口 (模型 + 存储 +
  事件辅助), 暂不实现 UI (设计文档明令"只数据接口")。
- 数据空间: <providers_dir>/feedback.json 独立文件, 与 catalog.json
  (Provider 定义) / usage.json (使用记录) 完全分离 — 删除 feedback 文件不影响
  目录与用量数据。
- 损坏失败安全 (同 UsageStore, 审计增强数据哲学): 文件损坏/单条校验失败 →
  跳过, 读命令永不因 feedback 文件失败; add 在损坏文件上从空重建。
- 文件格式 (KISS, 单节, 同 usage.json):
  ```json
  {"records": [ {ProviderFeedback dict}, ... ]}
  ```

rating 契约: 1-5 整数 (5 = 强烈推荐); approved: 人工批准标记 (True = 采纳
该 Provider 用于后续任务, 推荐层可据此加权 — 本阶段只记录, 不消费)。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from events.models import format_timestamp

from .models import _id_sane


class ProviderFeedback(BaseModel):
    """一条 Provider 人工反馈 (执行经验, 只记录不消费)。

    - id: 记录唯一键 (uuid hex, 存储层回填)。
    - provider_id: 被反馈 Provider; execution_id/task_id: 关联执行与任务 (可选,
      执行经验追溯 — 哪次执行产生这条反馈)。
    - rating: 1-5 整数评分 (5 = 强烈推荐); comment: 评论文本 (可选);
      approved: 人工批准标记 (采纳与否, 本阶段只记录)。
    - created_at: 统一 UTC 时间戳格式 (events TS_FORMAT)。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    provider_id: str
    execution_id: str | None = None
    task_id: str | None = None
    rating: int = 3
    comment: str | None = None
    approved: bool = False
    created_at: str = Field(
        default_factory=lambda: format_timestamp(datetime.now(timezone.utc))
    )

    @field_validator("provider_id")
    @classmethod
    def _feedback_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("rating", mode="before")
    @classmethod
    def _rating_bool_rejected(cls, v: Any) -> Any:
        """bool 是 int 子类 — 在 pydantic 宽松模式把 True 强制转 1 之前显式拒绝。"""
        if isinstance(v, bool):
            raise ValueError(f"rating must be an integer: {v!r}")
        return v

    @field_validator("rating")
    @classmethod
    def _rating_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError(f"rating out of range [1,5]: {v}")
        return v

    @field_validator("comment")
    @classmethod
    def _comment_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        stripped = str(v).strip()
        return stripped or None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class FeedbackStore:
    """Provider 人工反馈 JSON 文件库 (独立文件 feedback.json)。

    - 独立数据空间: <providers_dir>/feedback.json (与 catalog.json / usage.json
      完全分离 — 删除 feedback 文件不影响 Provider 目录与用量数据)。
    - 原子写: 临时文件 + os.replace (同 UsageStore 模式)。
    - 损坏失败安全: 文件损坏/单条校验失败 → 跳过 (list 返回可读部分, 读命令
      永不因 feedback 文件失败); add 在损坏文件上从空重建。
    - 本阶段只提供数据接口 (add/list/list_for_provider/count/clear), 不实现
      UI — 消费方 (未来推荐加权) 直接读 list。
    """

    filename = "feedback.json"

    def __init__(self, providers_dir: str | Path):
        self._dir = Path(providers_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 写

    def add(self, feedback: ProviderFeedback) -> ProviderFeedback:
        """追加一条反馈 (原子写); 返回带存储层回填 id 的反馈。"""
        records = self._read_all()
        records.append(feedback)
        self._write_all(records)
        return feedback

    def clear(self) -> None:
        """清空全部反馈 (重建空库)。"""
        self._write_all([])

    # ------------------------------------------------------------------ 读

    def list(self) -> list[ProviderFeedback]:
        """全部反馈 (按 created_at 升序); 损坏 → 可读部分/空列表。"""
        return sorted(self._read_all(), key=lambda f: f.created_at)

    def list_for_provider(self, provider_id: str) -> list[ProviderFeedback]:
        """按 Provider 过滤反馈 (未反馈 → 空列表)。"""
        return [f for f in self.list() if f.provider_id == provider_id]

    def count(self) -> int:
        return len(self._read_all())

    # ------------------------------------------------------------------ 内部

    def _read_all(self) -> list[ProviderFeedback]:
        """读整库; 文件不存在 → 空; 损坏 (JSON/结构/单条校验) → 失败安全跳过。"""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []  # 损坏失败安全: 解析失败 → 空库
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), list):
            return []
        records: list[ProviderFeedback] = []
        for item in raw["records"]:
            try:
                records.append(ProviderFeedback.model_validate(item))
            except Exception:
                continue  # 单条损坏 → 跳过 (不拖垮整库)
        return records

    def _write_all(self, records: list[ProviderFeedback]) -> None:
        """原子写整库: 临时文件 + os.replace (同 UsageStore 模式)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {
            "records": [f.to_dict() for f in sorted(records, key=lambda f: f.created_at)]
        }
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
