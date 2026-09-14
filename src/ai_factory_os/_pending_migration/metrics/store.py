"""metrics/store.py — 可选快照持久化 (FactoryMetrics → JSON, 原子写)。

设计依据:
- phase5b-status.md: store.py (如需要快照持久化 — 可选; 或纯计算不持久化)
- ADR-0015 决策 2: 指标默认纯计算不持久化 (event-model §6 按需聚合 — 指标一律
  按需从 store/事件聚合, 不维护统计表); 本类为可选快照出口 — 供调试对比/外部
  消费/CI 归档, CLI 与 Dashboard 均不依赖 (KISS)。

与 tasks/workflows/runtime store 同模式: 原子写 (临时文件 + os.replace);
损坏文件 (JSON 解析失败 / 模型校验失败) → MetricsStoreError, 绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import FactoryMetrics


class MetricsStoreError(Exception):
    """MetricsStore 基础异常。"""


class CorruptMetricsStoreError(MetricsStoreError):
    """快照文件损坏 (JSON 解析失败 / 模型校验失败)。"""


class MetricsStore:
    """FactoryMetrics 快照 JSON 文件库 (可选持久化)。"""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------ 写

    def save(self, metrics: FactoryMetrics) -> None:
        """原子写快照 (临时文件 + os.replace, 避免半写文件)。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.parent / f".{self._path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(metrics.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------ 读

    def load(self) -> FactoryMetrics | None:
        """读快照; 文件不存在返回 None; 损坏抛 CorruptMetricsStoreError。"""
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptMetricsStoreError(f"corrupt metrics snapshot: {self._path}: {exc}") from exc
        try:
            return FactoryMetrics.model_validate(raw)
        except ValidationError as exc:
            raise CorruptMetricsStoreError(f"corrupt metrics snapshot: {self._path}: {exc}") from exc
