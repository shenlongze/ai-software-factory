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
    """全部已挂【端点】数（守卫用: 端点数必须 == registry 里各 router 之和 ✓）。

    ★ 不能用 `len(create_app().routes)`: 本版 FastAPI 的 `include_router` 存的是
      `_IncludedRouter` 延迟对象、子路由不展开 ⇒ 那算出来是"挂载次数 + 4 个自带路由"
      而不是端点数（2026-09-15 实测: 返回 18, 真实端点数另有其值 —— 这种"看着对、
      其实算错"的读数最危险, 会让"端点数不变"的验收失去意义）。
      故直接从 registry 各 router 的 routes 求和 ✓。
    """
    return sum(len(router.routes) for _name, _label, router in registry.iter_routers())
