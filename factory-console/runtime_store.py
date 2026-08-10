"""factory-console/runtime_store.py — S10-004 Runtime Instance 持久化 (原子写)。

设计依据 (docs/sprint10/workspace-architecture.md §4 + api-data-model.md §1;
仿 org store 模式 — 独立数据空间, 原子写, 损坏失败安全):

```
<root>/runtimes/
├── runtimes.json      {"runtimes": {id: RuntimeInstance dict}}
└── screenshots.json   {"screenshots": {id: RuntimeScreenshot dict}}
```

与 org store 同构 (每实体单文件单节); 与既有六库/org 数据空间并存,
互不影响 (Runtime 层独立数据空间 — S10-002 Runtime API 的落库点)。

损坏语义 (同 ProductStore/IntelligenceStore/org store): 核心数据损坏 →
响亮 CorruptRuntimeStoreError (绝不静默返回空 — 静默丢数据比报错危险);
原子写 = 临时文件 + os.replace (同目录同文件系统原子性)。

本模块只做持久化 (读/写整库), 无业务逻辑; 状态机/生命周期在
ConsoleService (service.py) + api/runtime.py 路由层; 零 Core 修改
(事件经 events.logger.EventLogger.record 字符串类型落库, 见 events.py)。
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .models import RuntimeInstance, RuntimeScreenshot

T = TypeVar("T", bound=BaseModel)


class RuntimeStoreError(Exception):
    """RuntimeStore 基础异常。"""


class CorruptRuntimeStoreError(RuntimeStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class _JsonStore(Generic[T]):
    """单实体 JSON 记录库基类 (原子写/损坏响亮; 子类声明类属性即可)。

    仿 org/store.py _SectionStore — S10-004 Runtime 数据空间独立实现
    (不跨包 import org.store, 保持 Console 侧 Removal Isolation)。
    """

    _filename: str
    _section: str
    _model: type[T]

    def __init__(self, dir_path: str | Path):
        self._dir = Path(dir_path)

    @property
    def dir(self) -> Path:
        """数据空间目录 (<root>/runtimes)。"""
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
            raise CorruptRuntimeStoreError(
                f"corrupt runtime store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptRuntimeStoreError(
                f"corrupt runtime store: {path}: missing or invalid section "
                f"{self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> T:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptRuntimeStoreError(
                f"corrupt runtime store: {self._path()}: {exc}"
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

    # ------------------------------------------------------------------ 通用 API

    def save(self, record: T) -> None:
        """upsert 记录 (同 id 覆盖 = 状态流转经 model_copy 新实例后落库)。"""
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


class RuntimeInstanceStore(_JsonStore[RuntimeInstance]):
    """RuntimeInstance 记录库 (<root>/runtimes/runtimes.json)。"""

    _filename = "runtimes.json"
    _section = "runtimes"
    _model = RuntimeInstance

    def list_by_project(self, project_id: str) -> list[RuntimeInstance]:
        """项目全部实例 (按 id 排序, 审计友好)。"""
        return [r for r in self.list_all() if r.project_id == project_id]


class RuntimeScreenshotStore(_JsonStore[RuntimeScreenshot]):
    """RuntimeScreenshot 记录库 (<root>/runtimes/screenshots.json)。

    S10-004 截图反馈预留: 保存截图记录 (artifact_id 为预留产物引用 —
    完整 Feedback Loop 由 S10-005+/后续实现, 本 Sprint 只落记录)。
    """

    _filename = "screenshots.json"
    _section = "screenshots"
    _model = RuntimeScreenshot


def new_runtime_id() -> str:
    """新实例 id (rt-<uuid4 前 8 hex>; 唯一 basename, 无时钟碰撞语义)。"""
    return f"rt-{uuid.uuid4().hex[:8]}"


def new_screenshot_id() -> str:
    """新截图记录 id (shot-<uuid4 前 8 hex>)。"""
    return f"shot-{uuid.uuid4().hex[:8]}"


__all__ = [
    "CorruptRuntimeStoreError",
    "RuntimeInstanceStore",
    "RuntimeScreenshotStore",
    "RuntimeStoreError",
    "new_runtime_id",
    "new_screenshot_id",
]
