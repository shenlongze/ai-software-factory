"""api/errors.py — 错误码表的机器可读形态（docs/API规范.md §6 ✓）。

为什么单列（2026-09-15 ✓ Founder: "接口说明文档必须跟上"）:
  · 规范文档里是**表格**（人读 ✓），本文件是**代码**（可断言 ✓ 可生成文档 ✓）
  · 守卫（刀5）会核对: 代码里出现的 code 必须在本表登记 ✓ 否则报红 ✗
"""
from __future__ import annotations

#: 错误码域: E7xxx = HTTP API ✓
HTTP_API_CODE = "E7"

#: status → (code, 中文消息, 建议下一步) —— 与 docs/API规范.md §6 逐行一致 ✓
HTTP_API_CODES: tuple[tuple[int, str, str, str], ...] = (
    (400, "E7400", "参数错误", "见 detail"),
    (404, "E7404", "资源不存在", "检查 id/路径"),
    (409, "E7409", "冲突/状态非法", "见 detail"),
    (422, "E7422", "请求体校验失败", "见 detail"),
    (500, "E7500", "服务器内部错误", "查看日志"),
)

_BY_STATUS: dict[int, tuple[str, str, str]] = {
    status: (code, message, suggestion) for status, code, message, suggestion in HTTP_API_CODES
}


def code_for(status: int) -> str:
    """状态码 → 错误码（未登记的 status 回落到 E7{status} ✓ 与包络缺省一致）。"""
    return _BY_STATUS.get(status, (f"{HTTP_API_CODE}{status}", "", ""))[0]


def message_for(status: int) -> str:
    return _BY_STATUS.get(status, (f"{HTTP_API_CODE}{status}", "", ""))[1]
