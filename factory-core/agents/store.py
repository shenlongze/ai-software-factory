"""agents/store.py — Agent / Skill JSON 文件持久化 (单文件整体原子写, 标准库零依赖)。

设计依据:
- phase3b-status.md: JSON 持久化 — .factory/agents/agents.json + .factory/skills/skills.json
- tasks/store.py 同款模式: 原子写 (临时文件 + os.replace), 单进程本地使用, 不做文件锁。

文件格式: `{id: 模型 dict}`, 按 id 排序写入 (人工审计与 git 差异友好)。
损坏文件 (JSON 解析失败 / 模型校验失败) → 抛 CorruptStoreError, 绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, ValidationError

from .models import Agent, Skill

T = TypeVar("T", bound=BaseModel)


class RegistryStoreError(Exception):
    """Registry 存储基础异常。"""


class CorruptStoreError(RegistryStoreError):
    """存储文件损坏 (JSON 解析失败或模型校验失败)。"""


def _atomic_write_json(path: Path, data: dict) -> None:
    """原子写: 临时文件 + os.replace, 避免半写文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class _JsonStore(Generic[T]):
    """通用单文件 JSON 存储 (子类声明模型类型与文件名)。"""

    model: type[T]
    filename: str

    def __init__(self, store_dir: str | Path):
        self._dir = Path(store_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 读

    def _read_all(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptStoreError(f"corrupt store file: {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptStoreError(f"corrupt store file: {self.path}: expected JSON object")
        return raw

    def load(self, item_id: str) -> T | None:
        """按 id 取单条; 不存在返回 None。"""
        data = self._read_all().get(item_id)
        if data is None:
            return None
        try:
            return cast(T, self.model.model_validate(data))
        except ValidationError as exc:
            raise CorruptStoreError(f"corrupt store file: {self.path}: {exc}") from exc

    def load_all(self) -> dict[str, T]:
        """全部记录 {id: 模型}。"""
        raw = self._read_all()
        items: dict[str, T] = {}
        for key, data in raw.items():
            try:
                items[key] = cast(T, self.model.model_validate(data))
            except ValidationError as exc:
                raise CorruptStoreError(f"corrupt store file: {self.path}: {exc}") from exc
        return items

    # ------------------------------------------------------------------ 写

    def save(self, item: T) -> None:
        """upsert 单条 (id 为键)。"""
        data = cast(Any, item)  # 具体模型均实现 id 字段 + to_dict
        raw = self._read_all()
        raw[data.id] = data.to_dict()
        self._write_all(raw)

    def remove(self, item_id: str) -> bool:
        """删除单条; 不存在返回 False。"""
        raw = self._read_all()
        if item_id not in raw:
            return False
        del raw[item_id]
        self._write_all(raw)
        return True

    def _write_all(self, items: dict[str, dict]) -> None:
        _atomic_write_json(self.path, {k: items[k] for k in sorted(items)})


class AgentStore(_JsonStore[Agent]):
    """Agent 存储: `<agents_dir>/agents.json`。"""

    model = Agent
    filename = "agents.json"


class SkillStore(_JsonStore[Skill]):
    """Skill 存储: `<skills_dir>/skills.json`。"""

    model = Skill
    filename = "skills.json"
