"""providers/store.py — ProviderStore: Provider 定义 JSON 持久化 (独立文件, 原子写)。

设计依据:
- phase8-plan.md §Q7 持久化边界: Provider Catalog (定义) → `.factory/providers/
  catalog.json` — 独立数据空间, 与 runtime catalog (runtimes/catalog.json) /
  runtime 实例库 (runtimes/runtimes.json) 完全分离, 禁止混合 (phase8a-status.md
  冻结约束: 删除 providers 不影响 Factory)。
- 参照 runtimes/store.py (CatalogStore) 模式: 原子写 os.replace, 损坏报错
  (JSON 解析失败 / 结构不符 / 模型校验失败 → CorruptProviderStoreError, 绝不
  静默返回空)。
- 文件格式 (双节, KISS):
  ```json
  {
    "definitions": {"hermes": {ProviderDefinition dict}, ...},
    "default": "hermes"
  }
  ```
  default 为默认 Provider id (ProviderRegistry.set_default 持久化; 运行时选择
  优先级第 4 位, phase8-plan §Q5 — 定义见 registry.py)。
- 默认定义不在此文件自动落盘: 默认值常驻代码层 (definitions.py), 读路径由
  ProviderRegistry 合并 (同 ADR-0014 决策 3 模式)。
- 原子写: 临时文件 + os.replace; 单进程本地使用, 不做文件锁。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import ProviderDefinition


class ProviderStoreError(Exception):
    """ProviderStore 基础异常。"""


class CorruptProviderStoreError(ProviderStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class ProviderStore:
    """Provider 定义的 JSON 文件库 (独立文件 catalog.json, 独立目录 providers/)。"""

    filename = "catalog.json"

    def __init__(self, providers_dir: str | Path):
        self._dir = Path(providers_dir)

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
            return {"definitions": {}, "default": None}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptProviderStoreError(
                f"corrupt provider store: {self.path}: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise CorruptProviderStoreError(
                f"corrupt provider store: {self.path}: expected JSON object"
            )
        if not isinstance(raw.get("definitions"), dict):
            raise CorruptProviderStoreError(
                f"corrupt provider store: {self.path}: missing or invalid section 'definitions'"
            )
        default = raw.get("default")
        if default is not None and not isinstance(default, str):
            raise CorruptProviderStoreError(
                f"corrupt provider store: {self.path}: 'default' must be a string or null"
            )
        return raw

    def _load(self, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise CorruptProviderStoreError(
                f"corrupt provider store: {self.path}: {exc}"
            ) from exc

    def get_definition(self, definition_id: str) -> ProviderDefinition | None:
        """按 id 取定义; 不存在返回 None。"""
        data = self._read_all()["definitions"].get(definition_id)
        if data is None:
            return None
        return self._load(ProviderDefinition, data)  # type: ignore[return-value]

    def list_definitions(self) -> list[ProviderDefinition]:
        """全部已持久化定义 (按 id 排序)。"""
        definitions = [
            self._load(ProviderDefinition, data)
            for data in self._read_all()["definitions"].values()
        ]
        return sorted(definitions, key=lambda d: d.id)  # type: ignore[return-value]

    def get_default(self) -> str | None:
        """默认 Provider id; 未设置返回 None。"""
        return self._read_all().get("default")

    # ------------------------------------------------------------------ 写

    def save_definition(self, definition: ProviderDefinition) -> None:
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

    def save_default(self, provider_id: str) -> None:
        """持久化默认 Provider id (覆盖原值)。"""
        raw = self._read_all()
        raw["default"] = provider_id
        self._write_all(raw)

    def _write_all(self, data: dict) -> None:
        """原子写整库: 临时文件 + os.replace, 避免半写文件; 按 id 排序 (审计友好)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {
            "definitions": {k: data["definitions"][k] for k in sorted(data["definitions"])},
            "default": data.get("default"),
        }
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 便捷

    def definition_ids(self) -> list[str]:
        """已持久化定义 id 列表 (排序)。"""
        return sorted(self._read_all()["definitions"])
