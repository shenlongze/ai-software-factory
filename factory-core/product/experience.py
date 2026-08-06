"""factory-core/product/experience.py — 生成经验记录接口 (GenerationExperience + ExperienceStore)。

设计依据:
- phase9b-status.md 任务范围 §2: GenerationExperience (artifact_type/provider_id/
  approved/confidence/human_feedback/generated_at) + ExperienceStore (独立空间
  .factory/product/experience.json, 原子写, 损坏失败安全)。
- 定位 = 数据接口 (供未来 Provider 自动优化 — usage/经验回馈 CostAwareSelector
  performance_score 闭环的数据基础), 本阶段只记录不消费 (不实现任何优化逻辑)。
- 损坏失败安全 (同 providers/usage.py UsageStore 语义 — 审计增强数据): 文件损坏/
  单条校验失败 → 跳过, 读命令永不因 experience 文件失败; record 在损坏文件上从
  空重建。区别于 ProductStore 核心目录 (catalog) 的损坏响亮报错语义。
- 参照 providers/usage.py 模式: 原子写 os.replace + 单文件单节
  {"records": [GenerationExperience dict, ...]}。
- 本模块零顶层 imports events (Removal Isolation, 同 product/store.py 解耦铁律);
  事件 (product.experience.recorded/viewed) 由调用方 (ProductGenerator/CLI) 发出。
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


def _now() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    return format_timestamp(datetime.now(timezone.utc))


class GenerationExperience(BaseModel):
    """一次人工对生成产物的经验记录 (只记录不消费 — Provider 自动优化数据接口)。

    - artifact_type: 生成类型 (research/prd/ui, 来自 Artifact.type)。
    - provider_id: 生成来源 Provider (Artifact Lineage; 无生成来源 → None)。
    - approved: 人工是否批准 (None = 未判定; 与 ApprovalRequest 状态解耦 —
      记录时点的人工判定, 由 CLI --approved 显式传入)。
    - confidence: 生成置信度 (0-1, 继承自 Artifact.confidence — Confidence
      Model 的经验学习数据接口)。
    - human_feedback: 人工反馈文本 (评论/修改意见)。
    - rating: 人工评分 1-5 (None = 未评分; 校验范围 1-5)。
    - generated_at: 产物生成时间 (Artifact.created_at); recorded_at: 记录时间。
    - id: 记录唯一键 (uuid hex, ExperienceStore 存储层回填 — 同 UsageStore 模式)。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    artifact_type: str
    provider_id: str | None = None
    approved: bool | None = None
    confidence: float = 0.0
    human_feedback: str = ""
    rating: int | None = None
    generated_at: str = Field(default_factory=_now)
    recorded_at: str = Field(default_factory=_now)

    @field_validator("artifact_type")
    @classmethod
    def _type_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("artifact_type must not be empty")
        return v

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("rating")
    @classmethod
    def _rating_range(cls, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 5:
            raise ValueError(f"rating must be in [1, 5], got {v}")
        return v

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ExperienceStoreError(Exception):
    """ExperienceStore 基础异常。"""


class ExperienceStore:
    """生成经验记录 JSON 文件库 (独立文件 <product_dir>/experience.json)。

    - 独立数据空间: 与 artifacts.json 等 Product 核心文件同目录但独立文件,
      删除 experience.json 不影响 Product 目录 (审计增强数据, 同 UsageStore)。
    - 原子写: 临时文件 + os.replace (同 ProductStore 模式)。
    - 损坏失败安全: 文件损坏/单条校验失败 → 跳过 (list 返回可读部分/空),
      record 在损坏文件上从空重建 — 读命令永不因 experience 文件失败。
    - 文件格式 (KISS, 单节):
      ```json
      {"records": [ {GenerationExperience dict}, ... ]}
      ```
    """

    filename = "experience.json"

    def __init__(self, product_dir: str | Path):
        self._dir = Path(product_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 写

    def record(self, experience: GenerationExperience) -> GenerationExperience:
        """追加一条经验记录 (原子写); 返回带存储层回填 id 的记录。"""
        records = self._read_all()
        records.append(experience)
        self._write_all(records)
        return experience

    def clear(self) -> None:
        """清空全部经验记录 (重建空库)。"""
        self._write_all([])

    # ------------------------------------------------------------------ 读

    def list(self, artifact_type: str | None = None) -> list[GenerationExperience]:
        """全部经验记录 (按 recorded_at 升序; 可按 artifact_type 过滤)。"""
        records = sorted(self._read_all(), key=lambda r: r.recorded_at)
        if artifact_type is None:
            return records
        return [r for r in records if r.artifact_type == artifact_type]

    def count(self, artifact_type: str | None = None) -> int:
        return len(self.list(artifact_type))

    # ------------------------------------------------------------------ 内部

    def _read_all(self) -> list[GenerationExperience]:
        """读整库; 文件不存在 → 空; 损坏 (JSON/结构/单条校验) → 失败安全跳过。"""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []  # 损坏失败安全: 解析失败 → 空库
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), list):
            return []
        records: list[GenerationExperience] = []
        for item in raw["records"]:
            try:
                records.append(GenerationExperience.model_validate(item))
            except Exception:
                continue  # 单条损坏 → 跳过 (不拖垮整库)
        return records

    def _write_all(self, records: list[GenerationExperience]) -> None:
        """原子写整库: 临时文件 + os.replace (同 ProductStore 模式)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {
            "records": [r.to_dict() for r in sorted(records, key=lambda r: r.recorded_at)]
        }
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)
