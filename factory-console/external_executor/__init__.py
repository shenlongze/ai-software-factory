"""factory-console/external_executor — 外部执行器通用适配层 (M1, 设计文档 §3-§5)。

声明式适配器 + 通用引擎: 新增外部 AI CLI = 写一个 yaml, 不改代码。
- schema.py: 适配器 Schema (Pydantic, 严谨校验)
- registry.py: 注册表 (内置 codex/claude/hermes + <data_dir>/external-ais/*.yaml)
- executor.py: 通用执行器 (discover/probe/invoke)
- host_assets.py: 宿主资产发现 (M2)
- router.py / metrics.py: 路由与指标 (M3/M4/M5)
"""

from .registry import ExternalExecutorRegistry, build_registry
from .schema import ExternalExecutorAdapter

__all__ = ["ExternalExecutorRegistry", "ExternalExecutorAdapter", "build_registry"]
