"""runtimes/models.py — Runtime 能力定义模型 (Pydantic v2): Catalog 层数据载体。

设计依据:
- phase5a1-status.md: RuntimeDefinition (id/name/type/description/capabilities/
  supported_tasks/version/status/metadata) — Catalog=能力描述层, 与 Registry 实例
  (runtime/models.py RuntimeInfo) 和 Runtime 执行器 (adapters) 三者分离。
- 参照 runtime/tasks/agents models 风格: 枚举宽容 parse + id 即存储键校验 + to_dict
  (JSON 友好); 时间戳统一 UTC 带时区。

边界 (ADR-0014): RuntimeDefinition 只描述能力, 不含执行/可用状态 — 执行器选择
是 Registry (实例可用状态) + Adapter (实现) 的职责, Catalog 永不参与派发。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CatalogStatus(str, Enum):
    """定义生命周期状态 (Catalog 层, 与 Registry 的 RuntimeStatus 分离)。"""

    ACTIVE = "ACTIVE"          # 现行定义 (可用/推荐)
    DEPRECATED = "DEPRECATED"  # 已弃用 (仅保留描述, 不建议新建实例)

    @classmethod
    def parse(cls, value: str) -> "CatalogStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, CatalogStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"invalid catalog status: {value!r} (expected one of: {valid})"
            ) from None


def _id_sane(value: str) -> str:
    """id 即存储键: 拒绝空值、路径分隔符与相对路径。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


def _normalize_list(values: list[str] | None) -> list[str]:
    """字符串列表规范化: 去空白、去空串、保序去重 (capabilities/supported_tasks 共用)。"""
    seen: list[str] = []
    for item in values or []:
        v = str(item).strip()
        if v and v not in seen:
            seen.append(v)
    return seen


class RuntimeDefinition(BaseModel):
    """一个 Runtime 的能力定义 (Catalog 数据, 只描述不执行)。

    - capabilities: 能力标签 (如 code-generation/tool-use/reasoning), 供
      find_by_capability 检索。
    - supported_tasks: 适合承担的任务类型 (如 feature-implementation)。
    - status: ACTIVE/DEPRECATED (定义生命周期, 与实例 AVAILABLE/DISABLED 无关)。
    - metadata: 厂商/执行方式等扩展信息 (JSON 友好)。
    - 默认定义 (hermes/echo/mock) 见 definitions.py; 本模型只负责承载数据。
    """

    id: str
    name: str
    type: str = "agent"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    supported_tasks: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    status: CatalogStatus = CatalogStatus.ACTIVE
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("id")
    @classmethod
    def _definition_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v

    @field_validator("type")
    @classmethod
    def _type_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("type must not be empty")
        return v

    @field_validator("version")
    @classmethod
    def _version_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("version must not be empty")
        return v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> CatalogStatus:
        if isinstance(v, CatalogStatus):
            return v
        return CatalogStatus.parse(str(v))

    @field_validator("capabilities", mode="before")
    @classmethod
    def _capabilities_normalized(cls, v: list[str] | None) -> list[str]:
        # mode="before": None → [] 由 _normalize_list 归一化 (None 时 Pydantic 的
        # list[str] 类型检查会先于普通 after-validator 拒绝输入)
        return _normalize_list(v)

    @field_validator("supported_tasks", mode="before")
    @classmethod
    def _tasks_normalized(cls, v: list[str] | None) -> list[str]:
        return _normalize_list(v)

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")
