"""infrastructure.plugins — 插件机制（注册表 / resolver / 生命周期）。

层级判据（code-placement §一）: plugins/ 放【具体实现】（换一份实现即换此层文件）;
而本模块是【插件机制本身】—— 与业务无关的技术能力（换掉它业务逻辑不变）⇒ infrastructure ✓
（2026-09-15 从 _pending_migration 归位）
"""
from .kernel import (  # noqa: F401
    get_plugin, list_plugins, register_plugin, bootstrap, plugin_status,
)

__all__ = ["get_plugin", "list_plugins", "register_plugin", "bootstrap", "plugin_status"]
