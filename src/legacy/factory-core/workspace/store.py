"""workspace/store.py — WorkspaceStore: workspace.yaml 原子持久化 (Phase 6A, ADR-0016)。

设计依据:
- phase6a-status.md: store.py — 持久化 (workspace.yaml, 原子写)
- 同 tasks/store.py 模式: 临时文件 + os.replace 原子写, 避免半写文件;
  单进程本地使用不做文件锁 (KISS)。
- 解析/校验错误抛 WorkspaceConfigError (config.py), 缺失抛 WorkspaceNotFoundError;
  绝不静默返回空 (同 JSON store 铁律)。
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import WorkspaceConfig, load_config


class WorkspaceStore:
    """workspace.yaml 读写 (位置 = <root>/workspace.yaml)。"""

    def __init__(self, root: str | Path):
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def path(self) -> Path:
        return self._root / "workspace.yaml"

    # ------------------------------------------------------------------ 写入

    def save(self, config: WorkspaceConfig) -> None:
        """原子写 workspace.yaml (临时文件 + os.replace, 同 TaskStore)。"""
        from .config import dump_config

        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._root / f".workspace.yaml.{os.getpid()}.tmp"
        tmp.write_text(dump_config(config), encoding="utf-8")
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 读取

    def load(self) -> WorkspaceConfig:
        """读取 workspace.yaml; 缺失 → WorkspaceNotFoundError, 损坏 → WorkspaceConfigError。"""
        return load_config(self.path)

    def exists(self) -> bool:
        return self.path.is_file()
