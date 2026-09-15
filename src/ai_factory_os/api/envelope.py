"""api/envelope.py — 响应/错误包络的唯一实现（对齐 docs/API规范.md v1 ✓）。

规范（Founder 批准 2026-08-26 ✓ 照做 ✗ 不重新发明）:
  集合   → {"items": [...], "count": N}          HTTP 200
  单对象 → 直接返回对象                          HTTP 200
  创建   → 直接返回对象                          HTTP 201
  删除   → {"deleted": true, "id": "..."}        HTTP 200
  错误   → {"error": {code, message, detail?, suggestion?}}；code 缺省 = E7{status}
  禁止裸 {"detail": "..."} ✗（历史格式已收敛 ✓）
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

#: 错误码域: E7xxx = HTTP API（E4xxx CLI / E5xxx 脚本 / E6xxx session ✓）
API_ERROR_PREFIX = "E7"

#: 状态码 → 缺省中文消息（规范 §6 错误码表 ✓）
DEFAULT_MESSAGES: dict[int, str] = {
    400: "参数错误",
    404: "资源不存在",
    409: "冲突/状态非法",
    422: "请求体校验失败",
    500: "服务器内部错误",
}


def ok_list(items: Any) -> dict[str, Any]:
    """集合响应（★ 集合必须是 {items, count} ✓ 禁裸数组 ✗）。"""
    seq = list(items)
    return {"items": seq, "count": len(seq)}


def ok_deleted(resource_id: str) -> dict[str, Any]:
    """删除响应（规范 §1 ✓）。"""
    return {"deleted": True, "id": resource_id}


def error_body(status: int, message: str = "", *, code: str = "",
               detail: str = "", suggestion: str = "") -> dict[str, Any]:
    """错误包络（规范 §2 ✓）；code 缺省 = E7{status} ✓。"""
    err: dict[str, Any] = {
        "code": code or f"{API_ERROR_PREFIX}{status}",
        "message": message or DEFAULT_MESSAGES.get(status, "请求失败"),
    }
    if detail:
        err["detail"] = detail
    if suggestion:
        err["suggestion"] = suggestion
    return {"error": err}


def install(app: FastAPI) -> None:
    """挂全部异常处理器 —— 一处覆盖所有端点 ✓（规范 §2 最后一条 ✓）。"""

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_req: Request, exc: StarletteHTTPException) -> JSONResponse:
        # message 走规范 §6 的中文表 ✓；原始 detail（如 "Not Found"）进 detail 字段 ✓
        return JSONResponse(status_code=exc.status_code,
                            content=error_body(exc.status_code, "", detail=str(exc.detail or "")))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content=error_body(422, "", detail=str(exc.errors())[:500]))

    @app.exception_handler(Exception)
    async def _internal_error(_req: Request, exc: Exception) -> JSONResponse:
        # 失败安全: 不泄露堆栈 ✓（规范 §4 500 ✓）
        return JSONResponse(status_code=500,
                            content=error_body(500, "", detail=type(exc).__name__))
