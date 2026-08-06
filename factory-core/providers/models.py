"""providers/models.py — Provider 领域模型 (Pydantic v2): 定义/请求/响应/状态。

设计依据:
- phase8-plan.md §3 数据模型 + phase8a-status.md: ProviderDefinition + ProviderRequest/
  ProviderResponse (统一 I/O, 不绑 OpenAI 格式 — 结构化输入输出, 各 Provider 自行映射)。
- 参照 runtimes/models.py (RuntimeDefinition) 风格: 枚举宽容 parse + id 即存储键校验 +
  _normalize_list 列表规范化 + to_dict (model_dump(mode="json")) 供 CLI --json 与
  文件持久化共用; 时间戳统一 UTC 带时区。

分层语义 (phase8-plan §Q2/Q7):
- ProviderDefinition = Catalog 能力描述 (持久化到 .factory/providers/catalog.json),
  与 runtime Catalog (runtimes/catalog.json) 数据空间完全分离 — Provider 是智能来源,
  Runtime 是执行机制。
- ProviderRequest/ProviderResponse = 统一 I/O 契约 (ProviderAdapter 输入输出),
  不携带任何 OpenAI/Claude 专有结构; usage 为 tokens 等可移植计量 (dict, JSON 友好)。
- ProviderResponse.error 承载失败 (不抛异常 → 稳定响应, 同 HermesRuntimeAdapter 失败
  处理哲学); ok 属性 = error is None。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ProviderStatus(str, Enum):
    """Provider 生命周期状态 (Catalog 层, 与 Runtime 的 CatalogStatus 语义平行)。"""

    ACTIVE = "ACTIVE"      # 可用 (参与选择/执行)
    DISABLED = "DISABLED"  # 禁用 (不参与选择/执行)

    @classmethod
    def parse(cls, value: str) -> "ProviderStatus":
        """宽容解析: 大小写不敏感; 枚举对象直接返回; 非法值抛 ValueError。"""
        if isinstance(value, ProviderStatus):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"invalid provider status: {value!r} (expected one of: {valid})") from None


def _id_sane(value: str) -> str:
    """id 即存储键: 拒绝空值、路径分隔符与相对路径。"""
    v = value.strip()
    if not v or v in {".", ".."} or "/" in v or "\\" in v:
        raise ValueError(f"invalid id: {value!r}")
    return v


def _normalize_list(values: list[str] | None) -> list[str]:
    """字符串列表规范化: 去空白、去空串、保序去重 (capabilities/models 共用)。"""
    seen: list[str] = []
    for item in values or []:
        v = str(item).strip()
        if v and v not in seen:
            seen.append(v)
    return seen


class ProviderDefinition(BaseModel):
    """一个 Provider 的能力定义 (Catalog 数据, 只描述不执行)。

    - type: 部署形态 (cloud/local/agent) — phase8-plan §3。
    - capabilities: 能力标签 (chat/generation/code/vision/reasoning/tool-use...),
      供 find_by_capability 检索 (大小写不敏感精确匹配)。
    - models: 可用模型名列表 (如 gpt-4o/claude-sonnet-4/llama3-8b)。
    - config_schema: 配置项描述 (api_key 引用/env/endpoint/command — 适配器可配置化),
      只描述不包含密钥明文。
    - status: ACTIVE/DISABLED (ProviderStatus)。
    - metadata: 厂商/执行方式等扩展信息 (JSON 友好)。
    - 默认定义 (hermes) 见 definitions.py; 本模型只负责承载数据。
    """

    id: str
    name: str
    type: str = "cloud"
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    status: ProviderStatus = ProviderStatus.ACTIVE
    config_schema: dict[str, Any] = Field(default_factory=dict)
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
    def _coerce_status(cls, v: Any) -> ProviderStatus:
        if isinstance(v, ProviderStatus):
            return v
        return ProviderStatus.parse(str(v))

    @field_validator("capabilities", mode="before")
    @classmethod
    def _capabilities_normalized(cls, v: list[str] | None) -> list[str]:
        # mode="before": None → [] 由 _normalize_list 归一化 (同 runtimes/models.py)
        return _normalize_list(v)

    @field_validator("models", mode="before")
    @classmethod
    def _models_normalized(cls, v: list[str] | None) -> list[str]:
        return _normalize_list(v)

    def to_dict(self) -> dict:
        """JSON 友好序列化 (CLI --json 输出 / 文件持久化共用)。"""
        return self.model_dump(mode="json")


class ProviderRequest(BaseModel):
    """一次 Provider 调用请求 (统一 I/O 输入契约, 不绑 OpenAI 格式)。

    - prompt: 单轮生成 (generate) 正文; messages: 多轮对话 (chat) 消息列表
      (每项 {role, content, ...} — 语义由各适配器映射, 本模型不校验结构)。
    - system: 系统提示 (chat 首条注入; generate 可并入 prompt 前)。
    - model: 目标模型 (None = Provider 默认); temperature: 采样温度 (None = 默认)。
    - metadata: 调用方透传扩展信息 (JSON 友好, 如 task_id/execution_id 追踪)。
    """

    provider_id: str | None = None  # 可选: 适配器已知自身 id (registry 解析后可回填)
    prompt: str | None = None
    messages: list[dict[str, Any]] | None = None
    system: str | None = None
    model: str | None = None
    temperature: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProviderResponse(BaseModel):
    """一次 Provider 调用的结果 (统一 I/O 输出契约)。

    - content: 生成文本 (成功时非空); error: 失败描述 (失败时非空) — 成功与失败
      都返回本结构 (不抛异常, 稳定响应), 消费方以 ok/error 判定。
    - model: 实际使用的模型 (请求未指定时回填 Provider 默认); usage: 计量
      (tokens 等, dict JSON 友好, 不绑 OpenAI usage 结构); metadata: 扩展信息。
    """

    provider_id: str
    content: str = ""
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        """成功判定: 无 error 即成功 (与 error 语义互斥)。"""
        return self.error is None

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
