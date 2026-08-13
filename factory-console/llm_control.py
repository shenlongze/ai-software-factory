"""factory-console/llm_control.py — LLM Control Plane v1 (S10-021 Phase 1)。

Provider 配置管理面: providers.json 持久化 (~/.factory/providers.json) +
Credential api_key_ref 引用管理 + 装配决策 (workflow_runner 接线契约)。

设计依据: docs/sprint10/S10-021-phase1-design.md (Rev 2, 已确认)。
- D2: providers.json 存 ~/.factory/providers.json (HOME 可注入隔离 — 测试用 tmp)
- D3: api_key_ref 沿用现有 env:VAR 语义 (同 config.py:_resolve_env_ref)
- D4: 优先级 进程 env > 项目 .env > config.json > providers.json > 内置默认;
  workflow_runner 接线时 providers.json 的 enabled provider 优先, fallback
  现有 get_llm() 兼容不破坏
- D8: key 本体永不入 logger — 只输出 ref / configured=True|False
- ollama 语义: enabled 的 ollama 无 key 也算可用 (本地模型)

数据模型 (pydantic):
- ProviderConfig {id, enabled, models[], base_url?, api_key_ref?, metadata{}}
  — Provider 不绑单模型 (models 列表, Router Decision 兼容)
- ProviderConfigFile {version: 1, providers: {id: ProviderConfig}}
- ProviderSelection {provider_id, model_id?, source, reason, score?}
  — Routing Decision 预留结构 (Phase 4 Router 复用, 字段兼容扩展)

持久化: 原子写 (临时文件 + os.replace — 同 factory-core/providers/store.py
模式); 缺失文件 → 空配置; 损坏 JSON/结构不符/模型校验失败 → 响亮
CorruptProviderFileError (绝不静默返回空)。

铁律: api_key_ref 只存引用 (如 "env:DEEPSEEK_API_KEY"), 不存明文 key。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, Field, ValidationError

from .config import PROVIDER_DEFAULTS

logger = logging.getLogger("factory.llm_control")

#: providers.json 落盘格式版本
CONFIG_FILE_VERSION = 1


class ProviderConfig(BaseModel):
    """单个 Provider 的持久化配置 (providers.json 条目; 不绑单模型)。"""

    id: str  # provider id (deepseek/openai/anthropic/ollama)
    enabled: bool = False
    models: list[str] = Field(default_factory=list)  # 多模型列表 (Router Decision 兼容)
    base_url: str | None = None  # None → 用内置默认
    api_key_ref: str | None = None  # env:VAR 引用或空 (ollama 可空); 只存引用不存明文
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展字段 (费率/display/未来路由元数据)


class ProviderConfigFile(BaseModel):
    """providers.json 落盘格式。"""

    version: int = CONFIG_FILE_VERSION
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)


class ProviderSelection(BaseModel):
    """Routing Decision 预留结构 (Phase 4 Router 复用, 字段兼容扩展)。"""

    provider_id: str
    model_id: str | None = None
    source: str = "control-plane"  # 决策来源 (用户指定/项目规则/系统推荐/默认/control-plane)
    reason: str = ""  # 决策理由
    score: float | None = None  # 未来 Router 打分 (当前 None)


class ProviderFileError(Exception):
    """providers.json 基础异常。"""


class CorruptProviderFileError(ProviderFileError):
    """providers.json 损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


def _default_providers_file() -> Path:
    """默认落盘位置 ~/.factory/providers.json (HOME 重定向即隔离 — 冒烟/测试用)。"""
    return Path.home() / ".factory" / "providers.json"


def _parse_env_file(path: Path) -> dict[str, str]:
    """项目 .env 解析 (同 config.py 语义: KEY=VALUE; # 注释; export 前缀; 引号剥离)。

    独立构造 ControlPlane (无 ConfigProvider 注入) 时用于 .env 兜底层;
    失败安全: 缺失/不可读 → 空层。
    """
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


class LLMControlPlane:
    """Provider 配置管理面: 持久化 providers.json + 解析 + 装配决策。

    构造参数均可注入 (测试/冒烟用):
    - providers_file: 落盘路径 (缺省 ~/.factory/providers.json)
    - environ: 进程环境映射 (缺省 os.environ 实时读取 — monkeypatch.setenv 可见)
    - config: ConfigProvider (可选; 提供时 .env 层复用其已解析值 — 与
      config.py 同源, D4 优先级一致; 独立构造时自解析项目 .env)
    """

    def __init__(
        self,
        providers_file: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        config: Any | None = None,
    ) -> None:
        self._providers_file = (
            Path(providers_file)
            if providers_file is not None
            else _default_providers_file()
        )
        self._environ = os.environ if environ is None else environ
        self._config = config
        self._data = self.load()

    # ------------------------------------------------------------------ 持久化

    @property
    def path(self) -> Path:
        """providers.json 落盘路径。"""
        return self._providers_file

    def load(self) -> ProviderConfigFile:
        """原子读 providers.json; 缺失 → 空配置; 损坏 → 响亮错误 (不静默)。"""
        path = self._providers_file
        if not path.exists():
            self._data = ProviderConfigFile()
            return self._data
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptProviderFileError(
                f"corrupt provider file: {path}: {exc}"
            ) from exc
        except OSError as exc:
            raise ProviderFileError(f"provider file unreadable: {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptProviderFileError(
                f"corrupt provider file: {path}: expected JSON object"
            )
        try:
            data = ProviderConfigFile.model_validate(raw)
        except ValidationError as exc:
            raise CorruptProviderFileError(
                f"corrupt provider file: {path}: {exc}"
            ) from exc
        self._data = data
        return self._data

    def save(self, data: ProviderConfigFile) -> None:
        """原子写 (临时文件 + os.replace — 同 factory-core/providers/store.py 模式)。"""
        path = self._providers_file
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        self._data = data

    def reload(self) -> ProviderConfigFile:
        """重读磁盘 (重启恢复验证入口: save → 新实例构造/reload 往返一致)。"""
        return self.load()

    # ------------------------------------------------------------------ 查询

    def list_providers(self) -> list[ProviderConfig]:
        """全部 Provider 配置 (含 disabled)。"""
        return list(self._data.providers.values())

    def get_provider(self, provider_id: str) -> ProviderConfig | None:
        """按 id 取 Provider 配置 (不存在 → None)。"""
        return self._data.providers.get(provider_id)

    def enabled_providers(self) -> list[ProviderConfig]:
        """enabled 的 Provider 配置列表。"""
        return [p for p in self._data.providers.values() if p.enabled]

    def is_enabled(self, provider_id: str) -> bool:
        """Provider 是否启用 (不存在 → False)。"""
        p = self.get_provider(provider_id)
        return bool(p is not None and p.enabled)

    # ------------------------------------------------------------------ 变更

    def enable(self, provider_id: str, **overrides: Any) -> ProviderConfig:
        """启用 provider (不存在则创建); 返回保存后状态。"""
        return self._upsert(provider_id, enabled=True, overrides=overrides)

    def disable(self, provider_id: str) -> ProviderConfig:
        """禁用 provider (不存在则创建 disabled 条目); 返回保存后状态。"""
        return self._upsert(provider_id, enabled=False, overrides={})

    def set_config(self, provider_id: str, **overrides: Any) -> ProviderConfig:
        """更新 provider 配置 (enabled/models/base_url/api_key_ref/metadata);
        返回保存后状态。不改变既有 enabled 状态 (除非显式传入 enabled=)。"""
        return self._upsert(provider_id, enabled=None, overrides=overrides)

    def _upsert(
        self,
        provider_id: str,
        *,
        enabled: bool | None,
        overrides: dict[str, Any],
    ) -> ProviderConfig:
        existing = self.get_provider(provider_id)
        data = existing.model_dump() if existing is not None else {"id": provider_id}
        for key, value in overrides.items():
            if key not in {"enabled", "models", "base_url", "api_key_ref", "metadata"}:
                raise ValueError(f"llm_control: unknown provider field {key!r}")
            data[key] = value
        if enabled is not None:
            data["enabled"] = enabled
        data["id"] = provider_id  # id 恒等于字典键 (overrides 不允许覆盖 id)
        pc = ProviderConfig.model_validate(data)
        self._data.providers[provider_id] = pc
        self.save(self._data)
        return pc

    # ------------------------------------------------------------------ key 解析 (禁明文日志)

    def resolve_api_key(self, provider_id: str) -> str:
        """api_key_ref 解析: "env:VAR" → 进程 env → 项目 .env → 空串。

        ollama / 未配置 ref → 空串 (本地模型无需 key)。任何 logger 只输出
        ref 或 configured=True/False, 绝不输出 key 本体 (D8)。
        """
        pc = self.get_provider(provider_id)
        if pc is None or not pc.api_key_ref:
            return ""
        ref = pc.api_key_ref
        key = self._resolve_env_ref(ref)
        logger.debug(
            "llm_control: resolve_api_key provider=%s ref=%s configured=%s",
            provider_id,
            ref,
            bool(key),
        )
        return key

    def _resolve_env_ref(self, raw: str) -> str:
        """env:VAR 引用解析: 进程环境 → .env 层 → 空串 (同 config.py 语义, D3)。

        非 env: 前缀原样返回 (兼容 config.py 语义; 正常配置只存 env: 引用 —
        明文 key 不入 providers.json)。
        """
        if not raw.startswith("env:"):
            return raw
        name = raw[4:].strip()
        if not name:
            return ""
        val = self._environ.get(name, "")
        if val:
            return val
        return self._env_layer().get(name, "")

    def _env_layer(self) -> dict[str, str]:
        """.env 层: 优先复用 ConfigProvider 已解析值 (同源); 独立构造时自解析项目 .env。"""
        cfg = self._config
        if cfg is not None:
            values = getattr(cfg, "_env_values", None)
            if isinstance(values, dict):
                return values
        return _parse_env_file(Path(__file__).resolve().parent / ".env")

    # ------------------------------------------------------------------ 装配决策

    def any_enabled_with_key(self) -> bool:
        """至少一个 enabled provider 且 key 可解析 (ollama 本地无需 key → True)。"""
        for pc in self.enabled_providers():
            if pc.id == "ollama":
                return True
            if self.resolve_api_key(pc.id):
                return True
        return False

    def selected_provider_id(self) -> str | None:
        """第一个 enabled 且 key 可解析的 provider id (ollama 含; 无 → None)。"""
        for pc in self.enabled_providers():
            if pc.id == "ollama" or self.resolve_api_key(pc.id):
                return pc.id
        return None

    def select(
        self,
        task_type: str | None = None,
        required_capabilities: list[str] | None = None,
    ) -> ProviderSelection | None:
        """装配决策 (v1): 第一个 enabled + key 可解析的 ProviderSelection。

        source="control-plane"; task_type/required_capabilities 为 Router
        预留参数 (Phase 4 在此扩展 source/reason/score, 签名兼容)。
        """
        pid = self.selected_provider_id()
        if pid is None:
            return None
        pc = self.get_provider(pid)
        assert pc is not None
        return ProviderSelection(
            provider_id=pid,
            model_id=pc.models[0] if pc.models else None,
            source="control-plane",
            reason="first enabled provider with resolvable key (v1, no router)",
        )

    def resolve_runtime_config(self, provider_id: str) -> dict[str, Any] | None:
        """ControlPlane → workflow_runner 装配契约。

        返回 {provider, model, base_url, api_key, key_env, 费率}; model 取
        models[0] (默认, 不绑死 — workflow_runner 可显式覆盖); 无此 provider
        → None。费率: providers.json metadata 优先, 内置默认兜底 (D4)。
        """
        pc = self.get_provider(provider_id)
        if pc is None:
            return None
        defaults = PROVIDER_DEFAULTS.get(provider_id, {})
        model = pc.models[0] if pc.models else defaults.get("model")
        base_url = pc.base_url or defaults.get("base_url")
        meta = pc.metadata or {}
        input_rate = meta.get("input_rate_per_1k")
        if input_rate is None:
            input_rate = defaults.get("input_rate_per_1k")
        output_rate = meta.get("output_rate_per_1k")
        if output_rate is None:
            output_rate = defaults.get("output_rate_per_1k")
        return {
            "provider": provider_id,
            "model": model,
            "base_url": base_url,
            "api_key": self.resolve_api_key(provider_id),
            "key_env": defaults.get("key_env"),
            "input_rate_per_1k": input_rate,
            "output_rate_per_1k": output_rate,
        }
