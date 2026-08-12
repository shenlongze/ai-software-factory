"""factory-exec/exec/tool.py — S10-018 Task 001 Tool Runtime Foundation。

设计依据 (S10-018-task001 用户约束 + S10-017 Execution Loop 侦察):
```
Decision → Action {type: "tool", tool_id, input} → ToolExecutor → ToolResult → Observation
                              ↑                          ↑
                     ToolRegistry (注册表)        filesystem.read (系统 Tool)
```
目标: AI Employee 从 Decision 升级到 Decision → Tool → Result → Observation
(内部 Tool Runtime 基础设施)。**不实现** MCP Server/Client / External Tool
Marketplace / Skill System / Multi Agent / Memory / Learning Loop — 只建立内部
Tool 基础设施, 未来兼容 Internal/MCP/Skill/API Tool。

职责 (纯内部域模型 — 不绑 OpenAI function calling / MCP / 第三方协议):
- Tool: id/name/description/input_schema (JSON Schema)/output_schema/handler
  (callable)/permission_policy/enabled/created_at — 协议无关, 未来任意 Tool
  类型 (Internal/MCP/Skill/API) 都以本模型注册。
- ToolResult: {success, output, error, metadata} — 失败必须带明确 error
  (禁止异常吞掉 / 禁止空 error 失败)。
- ToolPermissionPolicy: 最小权限表 (allowed_agent_ids 白名单 / allow_all
  显式开放); 默认全部禁止 — 权限失败 → ToolResult.failed("permission denied")。
- ToolRegistry: register (id 冲突 → ToolConflictError 响亮) / unregister
  (不存在 → ToolNotFoundError) / get / list (id 排序) / validate (schema +
  handler 校验); with_system_tools() 启动加载系统 Tool (filesystem.read)。
- ToolExecutor: execute(tool_id, input, agent_id, context) → ToolResult —
  流程 Lookup → Enabled → Permission → Input Validation (JSON Schema) →
  Execute; 每步失败都返回明确 ToolResult.failed (tool not found / tool
  disabled / permission denied / invalid input / handler error), 不抛不吞。

依赖 (Removal Isolation): 只 import stdlib + pydantic + 本层 models
(utcnow); 不触碰 agent_runtime.py / provider.py 主逻辑。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import utcnow

#: Tool handler 签名: (input: dict, context: dict) -> Any (输出任意可 JSON 序列化值)。
ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Any]


class ToolError(Exception):
    """Tool 业务错误基类 (注册/校验/查找 — 响亮, 不静默)。"""


class ToolConflictError(ToolError):
    """Tool id 冲突 (register 同 id 二次 — 响亮, 不静默覆盖)。"""


class ToolNotFoundError(ToolError):
    """Tool 不存在 (unregister/API 404 语义)。"""


class ToolValidationError(ToolError):
    """Tool 校验失败 (schema/handler 非法 — 注册前拒绝)。"""


class ToolPermissionPolicy(BaseModel):
    """Tool 权限策略 (最小权限表 — 默认全部禁止)。

    allowed_agent_ids: 允许使用本 Tool 的 agent id 白名单 (backend-1 → 允许
    filesystem.read; 其他 Agent 默认禁止 — 约束 9)。
    allow_all: 显式开放开关 (未来内部/系统 Tool 用; 默认 False = 最小权限)。
    """

    model_config = ConfigDict(extra="forbid")

    allowed_agent_ids: list[str] = Field(default_factory=list)
    allow_all: bool = False

    def allows(self, agent_id: str) -> bool:
        """agent 是否允许使用本 Tool (allow_all → 放行; 否则白名单命中)。"""
        if self.allow_all:
            return True
        return agent_id in self.allowed_agent_ids


class Tool(BaseModel):
    """Tool Domain Model (协议无关 — 不绑 OpenAI/MCP/第三方协议)。

    id: 唯一标识 ("filesystem.read" — 点分命名, 类型前缀); name/description:
    人话元信息; input_schema/output_schema: JSON Schema (执行前校验输入);
    handler: (input, context) -> output 可调用; permission_policy: 最小权限;
    enabled: 开关 (false → 执行前拒绝); created_at: 注册时间 (审计)。
    未来兼容: Internal/MCP/Skill/API Tool 都以本模型注册 (type 字段后续扩展,
    本 Task 不实现)。
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    handler: ToolHandler
    permission_policy: ToolPermissionPolicy = Field(default_factory=ToolPermissionPolicy)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class ToolResult(BaseModel):
    """Tool 执行结果 {success, output, error, metadata}。

    success: true|false; output: 成功输出 (任意可 JSON 序列化值); error: 失败
    明确错误 (失败必须非空 — 禁止空 error 静默失败); metadata: 附加审计信息。
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    output: Any = None
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _failure_requires_error(self) -> "ToolResult":
        """失败必须有明确 error (禁止异常吞掉 / 空 error 假失败)。"""
        if not self.success and not str(self.error or "").strip():
            raise ValueError("ToolResult failed requires a non-empty error")
        return self

    @classmethod
    def ok(cls, output: Any = None, *, metadata: dict[str, Any] | None = None) -> "ToolResult":
        """成功结果工厂 (output + 可选 metadata)。"""
        return cls(success=True, output=output, metadata=metadata or {})

    @classmethod
    def failed(cls, error: str, *, metadata: dict[str, Any] | None = None) -> "ToolResult":
        """失败结果工厂 (明确 error + 可选 metadata — 失败不吞)。"""
        return cls(success=False, error=error, metadata=metadata or {})


# ------------------------------------------------------------------ JSON Schema 最小校验
# 无新依赖 (KISS): 支持 {"type": "object", "properties": {...}, "required": [...]}
# + properties 标量类型 (string/integer/number/boolean/array/object/null)。
# 未知关键字宽容 (不拒绝 — 未来可换 jsonschema 库, 接口不变)。

_SCALAR_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _type_name(value: Any) -> str:
    """值 → JSON Schema 类型名 (None → "null"; list → "array"; dict → "object")。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def validate_against_schema(schema: dict[str, Any], value: Any) -> str:
    """最小 JSON Schema 校验: 合法 → ""; 非法 → 明确错误信息 (校验失败响亮)。"""
    if not isinstance(schema, dict):
        return "schema must be a dict"
    if not schema:
        return ""  # 空 schema = 不校验 (宽容)
    if schema.get("type") != "object":
        return f"unsupported schema type: {schema.get('type')!r} (only object supported)"
    if not isinstance(value, dict):
        return f"input must be an object, got {_type_name(value)}"
    # required 字段存在性
    required = schema.get("required") or []
    if not isinstance(required, list):
        return "schema 'required' must be a list"
    for field in required:
        if field not in value:
            return f"missing required field: {field!r}"
    # properties 类型校验
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return "schema 'properties' must be a dict"
    for field, field_schema in properties.items():
        if field not in value:
            continue
        if not isinstance(field_schema, dict) or "type" not in field_schema:
            continue  # 无类型约束 → 宽容
        expected = field_schema["type"]
        actual = _type_name(value[field])
        if expected in _SCALAR_TYPES and not isinstance(value[field], _SCALAR_TYPES[expected]):
            return (
                f"field {field!r} must be {expected}, got {actual}"
            )
    return ""


# ------------------------------------------------------------------ ToolRegistry


class ToolRegistry:
    """Tool 注册表: register/unregister/get/list/validate + 启动加载系统 Tool。

    - register: id 冲突 → ToolConflictError (响亮, 不静默覆盖); 校验失败 →
      ToolValidationError (注册前拒绝非法 Tool)。
    - unregister: 不存在 id → ToolNotFoundError (响亮)。
    - list: 全部 Tool (含 disabled), 按 id 排序 (审计友好)。
    - validate: schema (dict) + handler (callable) + id/name 非空。
    - with_system_tools: 启动时加载系统 Tool (filesystem.read — S10-018 第一个
      真实 Tool; 沙箱根由 ToolExecutor 经 context 注入, 注册表协议无关)。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------------ 校验

    @staticmethod
    def validate(tool: Tool) -> None:
        """Tool 合法性校验 (id/name 非空 + schema dict + handler 可调用)。"""
        if not tool.id or not str(tool.id).strip():
            raise ToolValidationError("tool id must not be empty")
        if not tool.name or not str(tool.name).strip():
            raise ToolValidationError(f"tool {tool.id!r}: name must not be empty")
        if not callable(tool.handler):
            raise ToolValidationError(f"tool {tool.id!r}: handler must be callable")
        if not isinstance(tool.input_schema, dict):
            raise ToolValidationError(f"tool {tool.id!r}: input_schema must be a dict")
        if not isinstance(tool.output_schema, dict):
            raise ToolValidationError(f"tool {tool.id!r}: output_schema must be a dict")

    # ------------------------------------------------------------------ CRUD

    def register(self, tool: Tool) -> Tool:
        """注册 Tool (id 冲突 → ToolConflictError 响亮; 校验失败 → 拒绝)。"""
        self.validate(tool)
        if tool.id in self._tools:
            raise ToolConflictError(f"tool already registered: {tool.id}")
        self._tools[tool.id] = tool
        return tool

    def unregister(self, tool_id: str) -> None:
        """注销 Tool (不存在 → ToolNotFoundError 响亮)。"""
        if tool_id not in self._tools:
            raise ToolNotFoundError(f"tool not found: {tool_id}")
        del self._tools[tool_id]

    def get(self, tool_id: str) -> Tool | None:
        """按 id 取 Tool (不存在 → None — 查询语义)。"""
        return self._tools.get(tool_id)

    def list(self) -> list[Tool]:
        """全部 Tool (含 disabled), 按 id 排序。"""
        return [self._tools[tool_id] for tool_id in sorted(self._tools)]

    # ------------------------------------------------------------------ 系统 Tool

    @classmethod
    def with_system_tools(cls) -> "ToolRegistry":
        """启动加载系统 Tool (本 Task: filesystem.read — workspace 沙箱读)。"""
        registry = cls()
        from .tools.filesystem import build_filesystem_read_tool

        registry.register(build_filesystem_read_tool())
        return registry


# ------------------------------------------------------------------ ToolExecutor


class ToolExecutor:
    """Tool 执行器: Lookup → Permission → Schema Validation → Execute → ToolResult。

    构造:
    - registry: ToolRegistry (必填 — Tool 查找边界)。
    - workspace_root: workspace 沙箱根 (filesystem.read 等沙箱 Tool 的边界;
      None → context 无 workspace_root, 沙箱 Tool 执行失败并明确报错)。
    - event_callback: (event_type: str, data: dict) 可选回调 — 供 Execution
      Loop 集成 (事件写 RuntimeSession); 无 → 静默 (API 直调路径无 session)。

    execute(tool_id, tool_input, agent_id, *, context=None) → ToolResult:
    每步失败返回明确 ToolResult.failed (tool not found / tool disabled /
    permission denied / invalid input / handler error), **不抛不吞** —
    handler 异常捕获转 failed (error 含异常信息), 编排层不崩溃。
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        workspace_root: str | Path | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._workspace_root = Path(workspace_root) if workspace_root is not None else None
        self._event_callback = event_callback

    @property
    def registry(self) -> ToolRegistry:
        """Tool 注册表 (API 层查询当前可用 Tool 的数据源)。"""
        return self._registry

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """事件回调 (可选; 无 → 静默 — API 直调路径无 session 上下文)。"""
        if self._event_callback is not None:
            try:
                self._event_callback(event_type, data)
            except Exception:  # noqa: BLE001 — 事件回调失败不阻断执行
                pass

    def execute(
        self,
        tool_id: str,
        tool_input: dict[str, Any],
        agent_id: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> ToolResult:
        """执行 Tool (Lookup → Enabled → Permission → Schema → Execute)。

        失败路径全部返回 ToolResult.failed + 明确 error (tool not found /
        tool disabled / permission denied / invalid input / handler error),
        禁止异常吞掉 (handler 异常捕获转 failed, 错误信息进 error)。
        """
        # 1) Lookup
        tool = self._registry.get(tool_id)
        if tool is None:
            return ToolResult.failed(f"tool not found: {tool_id}")
        if not tool.enabled:
            return ToolResult.failed(f"tool disabled: {tool_id}")
        # 2) Permission Check (最小权限 — 默认禁止)
        agent = str(agent_id or "").strip()
        if not tool.permission_policy.allows(agent):
            return ToolResult.failed(
                f"permission denied: agent {agent or '(unknown)'} is not allowed "
                f"to use tool {tool_id}"
            )
        # 3) Input Validation (JSON Schema)
        schema_error = validate_against_schema(tool.input_schema, tool_input)
        if schema_error:
            return ToolResult.failed(f"invalid input for tool {tool_id}: {schema_error}")
        # 4) Execute (handler 异常 → 明确 failed, 不吞不抛)
        ctx: dict[str, Any] = dict(context or {})
        ctx.setdefault("agent_id", agent)
        if self._workspace_root is not None:
            ctx.setdefault("workspace_root", str(self._workspace_root))
        try:
            output = tool.handler(tool_input, ctx)
        except Exception as exc:  # noqa: BLE001 — handler 异常 → 明确失败
            return ToolResult.failed(
                f"handler error for tool {tool_id}: {exc}",
                metadata={"tool_id": tool_id},
            )
        return ToolResult.ok(output, metadata={"tool_id": tool_id})


__all__ = [
    "Tool",
    "ToolConflictError",
    "ToolError",
    "ToolHandler",
    "ToolNotFoundError",
    "ToolPermissionPolicy",
    "ToolRegistry",
    "ToolResult",
    "ToolValidationError",
    "ToolExecutor",
    "validate_against_schema",
]
