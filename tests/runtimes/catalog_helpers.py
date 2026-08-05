"""tests/runtimes/catalog_helpers.py — Runtime Catalog 测试数据构造 (唯一名防遮蔽)。

注意: 与其他测试目录的 helpers.py 不同名, 避免多非包目录共存时的模块遮蔽
(backend-developer skill 陷阱记录); 目录 CRUD/搜索测试用非默认 id,
默认定义 (hermes/echo/mock) 断言单独走 definitions.py。
"""

from __future__ import annotations

from runtimes.models import CatalogStatus, RuntimeDefinition


def make_definition(definition_id: str = "custom-rt", **overrides) -> RuntimeDefinition:
    """默认自定义定义 (id 避开内建 hermes/echo/mock); overrides 覆盖任意字段。"""
    defaults = {
        "id": definition_id,
        "name": f"runtime {definition_id}",
        "type": "agent",
        "description": "默认测试定义",
        "capabilities": ["code-generation", "testing"],
        "supported_tasks": ["feature-implementation"],
        "version": "1.0.0",
        "status": CatalogStatus.ACTIVE,
    }
    defaults.update(overrides)
    return RuntimeDefinition(**defaults)
