"""runtimes/store.py — CatalogStore: Runtime 定义 JSON 持久化 (独立文件, 原子写)。

设计依据:
- phase5a1-status.md: catalog 用独立文件 `.factory/runtimes/catalog.json` —
  ⚠️ 与实例库 runtimes.json (runtime/store.py RuntimeStore: 实例+executions) 完全
  分离, 避免冲突; 原子写 os.replace, 损坏报错 (参照 workflows/runtime store 模式)。
- 文件格式 (单节, KISS):
  ```json
  {"definitions": {"hermes": {RuntimeDefinition dict}, ...}}
  ```
- 默认定义不在此文件自动落盘: 默认值常驻代码层 (definitions.py), 读路径由
  RuntimeCatalog 合并 (ADR-0014 决策 3) — 本 store 只持久化用户注册/覆盖的定义。
- 原子写: 临时文件 + os.replace; 单进程本地使用, 不做文件锁。
- 损坏文件 (JSON 解析失败 / 模型校验失败 / 结构不符) → 抛 CorruptCatalogStoreError,
  绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import RuntimeDefinition


class CatalogStoreError(Exception):
    """CatalogStore 基础异常。"""


class CorruptCatalogStoreError(CatalogStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class CatalogStore:
    """Runtime 定义的 JSON 文件库 (独立文件 catalog.json)。"""

    filename = "catalog.json"

    def __init__(self, runtimes_dir: str | Path):
        self._dir = Path(runtimes_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 读

    def _read_all(self) -> dict:
        """读整库为 {节名: {id: dict}}; 文件不存在返回空库。"""
        if not self.path.exists():
            return {"definitions": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptCatalogStoreError(f"corrupt catalog store: {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptCatalogStoreError(f"corrupt catalog store: {self.path}: expected JSON object")
        if not isinstance(raw.get("definitions"), dict):
            raise CorruptCatalogStoreError(
                f"corrupt catalog store: {self.path}: missing or invalid section 'definitions'"
            )
        return raw

    def _load(self, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise CorruptCatalogStoreError(f"corrupt catalog store: {self.path}: {exc}") from exc

    def get_definition(self, definition_id: str) -> RuntimeDefinition | None:
        """按 id 取定义; 不存在返回 None。"""
        data = self._read_all()["definitions"].get(definition_id)
        if data is None:
            return None
        return self._load(RuntimeDefinition, data)  # type: ignore[return-value]

    def list_definitions(self) -> list[RuntimeDefinition]:
        """全部已持久化定义 (按 id 排序)。"""
        definitions = [
            self._load(RuntimeDefinition, data)
            for data in self._read_all()["definitions"].values()
        ]
        return sorted(definitions, key=lambda d: d.id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ 写

    def save_definition(self, definition: RuntimeDefinition) -> None:
        """upsert 定义 (覆盖同 id 已持久化记录)。"""
        raw = self._read_all()
        raw["definitions"][definition.id] = definition.to_dict()
        self._write_all(raw)

    def remove_definition(self, definition_id: str) -> bool:
        """删除已持久化定义; 不存在返回 False。"""
        raw = self._read_all()
        if definition_id not in raw["definitions"]:
            return False
        del raw["definitions"][definition_id]
        self._write_all(raw)
        return True

    def _write_all(self, data: dict) -> None:
        """原子写整库: 临时文件 + os.replace, 避免半写文件; 按 id 排序 (审计友好)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {"definitions": {k: data["definitions"][k] for k in sorted(data["definitions"])}}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 便捷

    def definition_ids(self) -> list[str]:
        """已持久化定义 id 列表 (排序)。"""
        return sorted(self._read_all()["definitions"])
