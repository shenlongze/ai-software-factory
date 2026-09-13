"""factory-console/web/backend/ — Phase 11B Web 后端 (FastAPI Adapter, ADR-0035)。

只包含最薄 HTTP 绑定 (fastapi_adapter.py); 不写 UI 逻辑, 不修改
factory-console/service.py 或 api/* (只读适配)。依赖 fastapi + uvicorn
仅装 console 侧 venv (不污染 factory-core pyproject)。
"""
