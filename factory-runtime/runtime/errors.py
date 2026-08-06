"""runtime/errors.py — factory-runtime 域错误。

独立异常层级 (不依赖 Core): 生命周期/健康检查/watchdog/CLI 统一抛
RuntimeError, CLI 捕获后转退出码 1。
"""

from __future__ import annotations


class RuntimeError(Exception):
    """factory-runtime 域错误 (注意: 非内置 RuntimeError, 独立层级)。"""
