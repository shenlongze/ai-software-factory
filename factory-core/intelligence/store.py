"""factory-core/intelligence/store.py — Intelligence 独立数据空间 JSON 持久化 (原子写)。

设计依据:
- phase10a1-status.md 冻结约束 (Extension 独立): `.factory/intelligence/` 独立
  数据空间, 与 tasks/agents/workflows/providers/product 等完全分离; 删除
  intelligence/ 不影响 Factory (Core 零感知)。
- 参照 product/store.py + providers/store.py 模式: 原子写 (临时文件 + os.replace);
  损坏文件 (JSON 解析失败 / 结构不符 / 模型校验失败) → CorruptIntelligenceStoreError,
  绝不静默返回空 (核心目录数据响亮失败, 同 ProductStore 语义)。
- 文件布局 (每文件单节, KISS — 与 product 多节模式同构的简化版):
  ```
  .factory/intelligence/
  ├── decisions.json        {"decisions": {id: Decision dict}}
  ├── recommendations.json  {"recommendations": {id: Recommendation dict}}
  └── experiences.json      {"experiences": {id: ExperienceRecord dict}}
  ```
- 三 Store 独立文件 (decisions/recommendations/experiences), 共享同一目录,
  互不依赖: 一个文件损坏不影响另外两个。
- 本模块只做持久化 (读/写整库), 无业务逻辑; **零顶层 imports events**
  (Removal Isolation, 同 provider/product store 模式); 只依赖 stdlib +
  pydantic + 本层 models (纯 stdlib + 公共接口铁律)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .models import Decision, ExperienceDomain, ExperienceRecord, Recommendation

T = TypeVar("T", bound=BaseModel)


class IntelligenceStoreError(Exception):
    """IntelligenceStore 基础异常。"""


class CorruptIntelligenceStoreError(IntelligenceStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class _JsonRecordStore(Generic[T]):
    """三 Store 共用的 JSON 记录库基类 (原子写/损坏失败安全)。

    子类声明 _filename/_section/_model 三个类属性即可获得完整持久化能力
    (save/get/list_all/count + 按 id 排序)。DRY: DecisionStore /
    RecommendationStore / ExperienceStore 只补各自查询方法。
    """

    _filename: str
    _section: str
    _model: type[T]

    def __init__(self, intelligence_dir: str | Path):
        self._dir = Path(intelligence_dir)

    @property
    def dir(self) -> Path:
        """数据空间目录 (<root>/intelligence)。"""
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
            raise CorruptIntelligenceStoreError(
                f"corrupt intelligence store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptIntelligenceStoreError(
                f"corrupt intelligence store: {path}: missing or invalid "
                f"section {self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> T:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptIntelligenceStoreError(
                f"corrupt intelligence store: {self._path()}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ 写

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        """原子写单文件: 临时文件 + os.replace (同 product/providers store 模式)。

        目录在首次写时创建; 临时文件与目标同目录 (os.replace 同文件系统原子性);
        正常路径不残留 .tmp 文件。
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 通用 API

    def save(self, record: T) -> None:
        """upsert 记录 (覆盖同 id; 状态流转经 model_copy 新实例后落库)。"""
        records = self._read_all()
        records[record.id] = record.to_dict()  # type: ignore[attr-defined]
        self._write(records)

    def get(self, record_id: str) -> T | None:
        """按 id 取记录; 不存在返回 None。"""
        data = self._read_all().get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[T]:
        """全部记录 (按 id 排序, 审计友好)。"""
        return sorted(
            (self._load(data) for data in self._read_all().values()),
            key=lambda r: r.id,  # type: ignore[attr-defined, return-value]
        )

    def count(self) -> int:
        """记录总数。"""
        return len(self._read_all())


class DecisionStore(_JsonRecordStore[Decision]):
    """Decision 持久化 (decisions.json, 独立数据空间)。"""

    _filename = "decisions.json"
    _section = "decisions"
    _model = Decision

    def list_by_subject(self, subject_id: str) -> list[Decision]:
        """按决策对象 (task/project/idea/artifact id) 过滤。"""
        return [d for d in self.list_all() if d.subject_id == subject_id]


class RecommendationStore(_JsonRecordStore[Recommendation]):
    """Recommendation 持久化 (recommendations.json, 独立数据空间)。"""

    _filename = "recommendations.json"
    _section = "recommendations"
    _model = Recommendation

    def list_by_target(self, target_type: str, target_id: str) -> list[Recommendation]:
        """按推荐目标 (target_type + target_id) 过滤。"""
        return [
            r
            for r in self.list_all()
            if r.target_type == target_type and r.target_id == target_id
        ]


class ExperienceStore(_JsonRecordStore[ExperienceRecord]):
    """ExperienceRecord 持久化 (experiences.json, 独立数据空间)。"""

    _filename = "experiences.json"
    _section = "experiences"
    _model = ExperienceRecord

    def list_by_domain(self, domain: str | ExperienceDomain) -> list[ExperienceRecord]:
        """按经验域 (provider/agent/workflow/project/decision) 过滤。"""
        key = ExperienceDomain(domain) if isinstance(domain, str) else domain
        return [e for e in self.list_all() if e.domain == key]

    def find(self, subject_id: str, domain: str | ExperienceDomain | None = None) -> list[ExperienceRecord]:
        """按经验对象定位 (subject_id, 可选 domain 过滤)。"""
        records = [e for e in self.list_all() if e.subject_id == subject_id]
        if domain is not None:
            key = ExperienceDomain(domain) if isinstance(domain, str) else domain
            records = [e for e in records if e.domain == key]
        return records
