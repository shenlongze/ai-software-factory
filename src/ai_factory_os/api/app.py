"""api/app.py — 新地基 API 的唯一装配点。

形状: create_app() → 读 registry.DOMAINS → include_router → 挂包络异常处理。

纪律:
  · 本文件【不写任何端点】✗（端点只写在 api/domains/<域>/router.py ✓）
  · 装配只读 registry ✓ 不手写 include_router 列表 ✗（新增域 = 加一行 ✓ 忘接线会被守卫抓到 ✓）
"""
from __future__ import annotations

from fastapi import FastAPI

from . import envelope, registry


def create_app(*, title: str = "AI Factory OS API") -> FastAPI:
    """构建 API 应用（无副作用: 不读数据、不起服务 ✓）。"""
    app = FastAPI(title=title, version="1.0")
    for _name, _label, router in registry.iter_routers():
        app.include_router(router)
    envelope.install(app)
    return app


def route_count() -> int:
    """全部已挂路由数（守卫用: 端点数必须 == registry 里各 router 之和 ✓）。"""
    return len(create_app().routes)
