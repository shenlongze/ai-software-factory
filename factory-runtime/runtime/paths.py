"""runtime/paths.py — 数据目录管理 (平台规范路径 + 权限)。

设计依据: phase15-runtime-design.md §1.4 (数据目录标准) / §5 (安全边界)。

数据根结构 (7 子目录, Phase 16 Registry 预留 providers/agents/skills/mcp):

    <data_root>/
    ├── config/      runtime 状态 + token (Phase 16: config.yaml 用户配置)
    ├── providers/   Provider 配置 (Phase 16)
    ├── agents/      Agent 配置 (Phase 16)
    ├── skills/      Skill 配置 (Phase 16)
    ├── mcp/         MCP 配置 (Phase 16)
    ├── logs/        runtime.log / core.log / console.log (轮转)
    └── data/        工厂数据 (.factory 结构)

权限: POSIX 数据根 700; token/状态文件 600 (设计 §5 默认安全)。
platformdirs 为 pyproject 声明的可选依赖 — 缺失时降级到 stdlib 映射
(同设计 §1.4 表, 保证包在任何环境可加载)。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ai-software-factory"

#: 数据根下必须就位的 7 个子目录
SUBDIRS = ("config", "providers", "agents", "skills", "mcp", "logs", "data")

#: POSIX 权限: 数据根 700, token/状态文件 600
DIR_MODE = 0o700
FILE_MODE = 0o600


def default_data_dir() -> Path:
    """平台规范数据根 (platformdirs user_data_dir 映射)。"""
    mapped = _platformdirs("user_data_dir")
    return Path(mapped) if mapped else _fallback_data_dir()


def default_config_dir() -> Path:
    """平台规范配置根 (Linux 侧与数据根分离: ~/.config)。"""
    mapped = _platformdirs("user_config_dir")
    return Path(mapped) if mapped else _fallback_config_dir()


def ensure_data_root(root: str | Path) -> Path:
    """创建数据根 (700) + 7 子目录, 幂等; 返回规范化 Path。"""
    root = Path(root).expanduser().resolve()
    root.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    chmod(root, DIR_MODE)
    for name in SUBDIRS:
        (root / name).mkdir(exist_ok=True)
    return root


def chmod(path: Path, mode: int) -> None:
    """POSIX 权限设置 (非 POSIX 平台 no-op)。"""
    if os.name == "posix":
        try:
            os.chmod(path, mode)
        except OSError:
            pass


def _platformdirs(func_name: str) -> str | None:
    try:
        from platformdirs import user_config_dir, user_data_dir  # type: ignore[attr-defined]

        fn = user_data_dir if func_name == "user_data_dir" else user_config_dir
        return fn(APP_NAME)
    except ImportError:
        return None


def _fallback_data_dir() -> Path:
    """platformdirs 缺失时的 stdlib 降级映射 (设计 §1.4 表)。"""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home) / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / APP_NAME


def _fallback_config_dir() -> Path:
    """platformdirs 缺失时的配置根降级 (Linux: ~/.config)。"""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home) / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home / ".config"
    return base / APP_NAME
