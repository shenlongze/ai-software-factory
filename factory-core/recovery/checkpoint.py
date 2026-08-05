"""recovery/checkpoint.py — CheckpointStore: JSON 文件持久化 (每任务单文件, 原子写)。

设计依据:
- phase4c3-status.md: `.factory/checkpoints/<task_id>.json`, 原子写 os.replace
  (或单文件 — 按简单可靠)。选每任务单文件: 任务隔离 (删一个任务不影响其他)、
  无并发写冲突 (单进程), 与 tasks/agents 的 {id: dict} 模式一致。
- 目录由首次原子写自动创建 (同 runtime 模式, ADR-0006 决策 5): 不强制 init。
- 损坏文件 (JSON 解析失败 / 模型校验失败) → 抛 CorruptCheckpointError,
  绝不静默返回空 (同 agents/workflows store 模式)。

文件格式: Checkpoint.to_dict() 单对象 (id 即文件名去后缀)。
覆盖语义: 同一任务重复 checkpoint 覆盖旧快照 (最新停靠点为准, 续跑生命线)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import Checkpoint


class CheckpointStoreError(Exception):
    """CheckpointStore 基础异常。"""


class CorruptCheckpointError(CheckpointStoreError):
    """checkpoint 文件损坏 (JSON 解析失败或模型校验失败)。"""


class CheckpointStore:
    """Checkpoint 的 JSON 文件库 (每任务一个文件: <dir>/<task_id>.json)。"""

    def __init__(self, checkpoints_dir: str | Path):
        self._dir = Path(checkpoints_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    def path_for(self, task_id: str) -> Path:
        """任务对应的 checkpoint 文件路径 (id 即文件名, 拒绝路径分隔符/相对路径)。"""
        v = task_id.strip()
        if not v or v in {".", ".."} or "/" in v or "\\" in v:
            raise ValueError(f"invalid task_id: {task_id!r}")
        return self._dir / f"{v}.json"

    # ------------------------------------------------------------------ 读

    def load(self, task_id: str) -> Checkpoint | None:
        """按任务取 checkpoint; 不存在返回 None (损坏抛 CorruptCheckpointError)。"""
        path = self.path_for(task_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptCheckpointError(f"corrupt checkpoint: {path}: {exc}") from exc
        return self._load(raw, path)

    def list(self) -> list[Checkpoint]:
        """全部 checkpoint (按 task_id 排序; 目录不存在/为空返回空列表)。"""
        if not self._dir.exists():
            return []
        checkpoints = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CorruptCheckpointError(f"corrupt checkpoint: {path}: {exc}") from exc
            checkpoints.append(self._load(raw, path))
        return checkpoints

    def _load(self, data: Any, path: Path) -> Checkpoint:
        try:
            return Checkpoint.model_validate(data)
        except ValidationError as exc:
            raise CorruptCheckpointError(f"corrupt checkpoint: {path}: {exc}") from exc

    # ------------------------------------------------------------------ 写

    def save(self, checkpoint: Checkpoint) -> None:
        """upsert checkpoint (同任务覆盖旧快照); 原子写 (临时文件 + os.replace)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{checkpoint.task_id}.json"
        tmp = self._dir / f".{checkpoint.task_id}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def remove(self, task_id: str) -> bool:
        """删除任务 checkpoint; 不存在返回 False。"""
        path = self.path_for(task_id)
        if not path.exists():
            return False
        path.unlink()
        return True
