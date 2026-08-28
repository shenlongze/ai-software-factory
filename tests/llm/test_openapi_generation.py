"""T17: openapi.json 可生成 — 修 StreamingResponse ForwardRef 500 (T17)。

覆盖: build_app().openapi() 不抛异常, 且路径数 > 100。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def test_openapi_generates_without_500(tmp_path):
    """T17: openapi schema 可生成 (曾因 SSE 路由 ForwardRef 500)。"""
    import os

    from factory_console.web.backend.fastapi_adapter import build_app

    old = os.environ.get("FACTORY_ROOT")
    os.environ["FACTORY_ROOT"] = str(tmp_path)
    try:
        app = build_app(str(tmp_path), event_logger=None)
        schema = app.openapi()
        assert "paths" in schema
        assert len(schema["paths"]) > 100
        # SSE 路由仍在
        assert "/api/events/stream" in schema["paths"]
    finally:
        if old is None:
            os.environ.pop("FACTORY_ROOT", None)
        else:
            os.environ["FACTORY_ROOT"] = old
