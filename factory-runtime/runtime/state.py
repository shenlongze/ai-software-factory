"""runtime/state.py — Runtime 状态持久化 (pid/port/status/version/timestamps)。

架构调整 (用户确认): 不做 config.py — 本模块只管理 runtime 状态;
配置加载属 Phase 16 (config.yaml 三层合并), 目录结构已在 paths.py 就位。

状态文件: <data_root>/config/runtime_state.json (原子写: tmp + fsync + os.replace)。

状态机: idle → starting → ready → stopping → stopped; 任意态可 → failed。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import FILE_MODE, chmod

#: 状态文件相对数据根
STATE_RELPATH = Path("config") / "runtime_state.json"

#: 合法状态值
STATUSES = ("idle", "starting", "ready", "stopping", "stopped", "failed")

#: 运行中状态集合 (status()/watchdog 判定)
RUNNING_STATUSES = ("starting", "ready")


@dataclass
class RuntimeState:
    """Runtime 运行态快照 (非配置 — 配置属 Phase 16)。"""

    pid: int | None = None  # RuntimeManager 自身 pid (运行中)
    port: int | None = None  # Console 实际监听端口 (0 → 启动时动态分配)
    status: str = "idle"  # idle|starting|ready|stopping|stopped|failed
    version: str = ""  # factory-runtime 包版本
    started_at: str | None = None  # ISO8601
    stopped_at: str | None = None  # ISO8601

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RuntimeState":
        status = data.get("status", "idle")
        if not isinstance(status, str) or status not in STATUSES:
            status = "idle"
        version = data.get("version", "")
        return cls(
            pid=data.get("pid"),
            port=data.get("port"),
            status=status,
            version=version if isinstance(version, str) else "",
            started_at=data.get("started_at"),
            stopped_at=data.get("stopped_at"),
        )


def state_path(data_root: str | Path) -> Path:
    """状态文件绝对路径。"""
    return Path(data_root) / STATE_RELPATH


def save_state(state: RuntimeState, data_root: str | Path) -> Path:
    """原子写状态文件 (tmp + fsync + os.replace), POSIX 600。"""
    path = state_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        chmod(Path(tmp_name), FILE_MODE)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    chmod(path, FILE_MODE)
    return path


def load_state(data_root: str | Path) -> RuntimeState:
    """读状态文件; 缺失/损坏 → 默认 RuntimeState (失败安全)。"""
    path = state_path(data_root)
    if not path.exists():
        return RuntimeState()
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return RuntimeState()
        return RuntimeState.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return RuntimeState()
