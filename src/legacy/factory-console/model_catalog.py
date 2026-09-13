"""factory-console/model_catalog.py — Model Catalog v1 (S10-022 Phase 2A)。

模型级元数据管理面: models.json 持久化 (~/.factory/models.json) + Provider→Model
两级结构 + 能力过滤 + suggest() 确定性候选生成器 (Router 兼容预留)。

设计依据: docs/sprint10/S10-022-phase2a-design.md (已确认)。
- D2: models.json 存 ~/.factory/models.json (HOME 可注入隔离 — 测试用 tmp)
- D3: register 时 model.provider_id 必须存在于 ControlPlane (不存在 → 响亮
  UnknownProviderError, 不静默); control_plane 为 None (独立构造) → 跳过校验
- D4: ModelInfo.enabled 与 ProviderConfig.enabled 独立 (模型级开关)
- D5: suggest() 返回 ModelChoice 列表 (确定性过滤+排序+理由), 非智能推荐;
  Router 逻辑 (动态权重/历史学习/自动优化) 不在 v1 范围
- 真实性铁律 (设计 §7): 种子数据真实 API 名称; 未验证模型
  metadata.placeholder=true + metadata.evidence 注明, 绝不冒充真实模型

数据模型 (pydantic):
- ModelCost {input_per_1k?, output_per_1k?}  — USD / 1K tokens
- ModelInfo {model_id, provider_id, capabilities[], context_window?, cost,
  enabled, metadata{}}  — models.json 条目 (唯一键 = model_id)
- ModelCatalogFile {version: 1, models: {model_id: ModelInfo}}
- ModelChoice {model_id, provider_id, score?, reasons[], source}
  — Router 兼容预留 (Phase 4 Router 复用, 字段兼容扩展); v1 只做候选生成,
    不做 Router 决策

持久化: 原子写 (临时文件 + os.replace — 同 llm_control.py 模式); 缺失文件
→ 写入内置种子 (首次启动自举); 损坏 JSON/结构不符 → 响亮 CorruptModelFileError
(绝不静默返回空)。

铁律: 任何 logger 不输出 key/敏感值 (本模块不接触凭据, 日志仅路径/计数)。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .llm_control import LLMControlPlane

logger = logging.getLogger("factory.model_catalog")

#: models.json 落盘格式版本
CATALOG_FILE_VERSION = 1


class ModelCost(BaseModel):
    """模型费率 (USD / 1K tokens); 未知 → None。"""

    input_per_1k: float | None = None
    output_per_1k: float | None = None


class ModelInfo(BaseModel):
    """单个模型的元数据 (models.json 条目; 唯一键 = model_id)。"""

    model_id: str  # 唯一键 (如 "deepseek-chat")
    provider_id: str  # 归属 provider (必须存在于 ControlPlane — D3)
    capabilities: list[str] = Field(default_factory=list)  # code/reasoning/chat/vision/tool-use
    context_window: int | None = None  # tokens
    cost: ModelCost = Field(default_factory=ModelCost)
    enabled: bool = True  # 模型级开关 (与 Provider 开关独立 — D4)
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展 (placeholder/evidence/…)


class ModelCatalogFile(BaseModel):
    """models.json 落盘格式。"""

    version: int = CATALOG_FILE_VERSION
    models: dict[str, ModelInfo] = Field(default_factory=dict)


class ModelChoice(BaseModel):
    """Router 兼容预留 (Phase 4 Router 复用, 字段兼容扩展)。

    v1: suggest() 的确定性候选; 未来 Router 在此扩展加权 score/来源。
    """

    model_id: str
    provider_id: str
    score: float | None = None  # 当前 = 能力命中率 (0-1); 无要求 → None
    reasons: list[str] = Field(default_factory=list)  # 为什么候选 (能力命中/成本/上下文)
    source: str = "model-catalog"  # 决策来源 (v1: model-catalog; 未来: router)


class ModelCatalogError(Exception):
    """models.json 基础异常。"""


class CorruptModelFileError(ModelCatalogError):
    """models.json 损坏 (JSON 解析失败 / 结构不符)。"""


class UnknownProviderError(ModelCatalogError):
    """register 时 provider 不存在于 ControlPlane (两级结构校验失败)。"""


class UnknownModelError(ModelCatalogError):
    """set_enabled 目标模型不存在。"""


def _default_models_file() -> Path:
    """默认落盘位置 ~/.factory/models.json (HOME 重定向即隔离 — 冒烟/测试用)。"""
    return Path.home() / ".factory" / "models.json"


#: 内置默认模型目录 (设计 §7 真实性铁律 — 首次 load 缺失文件时写入)
_SEED_MODELS: dict[str, ModelInfo] = {
    "deepseek-chat": ModelInfo(
        model_id="deepseek-chat",
        provider_id="deepseek",
        capabilities=["code", "chat"],
        context_window=64000,
        cost=ModelCost(input_per_1k=0.00028, output_per_1k=0.00042),
        metadata={"placeholder": False, "evidence": "DeepSeek API docs, verified 2026-08"},
    ),
    "deepseek-reasoner": ModelInfo(
        model_id="deepseek-reasoner",
        provider_id="deepseek",
        capabilities=["reasoning", "code"],
        context_window=64000,
        cost=ModelCost(input_per_1k=0.00055, output_per_1k=0.00219),
        metadata={"placeholder": False, "evidence": "DeepSeek API docs, verified 2026-08"},
    ),
    "gpt-4o": ModelInfo(
        model_id="gpt-4o",
        provider_id="openai",
        capabilities=["code", "chat", "vision"],
        context_window=128000,
        cost=ModelCost(input_per_1k=0.0025, output_per_1k=0.01),
        metadata={"placeholder": False, "evidence": "OpenAI API docs, verified 2026-08"},
    ),
    "claude-sonnet-4": ModelInfo(
        model_id="claude-sonnet-4",
        provider_id="anthropic",
        capabilities=["code", "reasoning", "chat"],
        context_window=200000,
        cost=ModelCost(input_per_1k=0.003, output_per_1k=0.015),
        metadata={
            "placeholder": True,
            "evidence": "vendor docs, exact version unverified",
        },
    ),
}


def _seed_catalog() -> ModelCatalogFile:
    """内置种子 (深拷贝 — 调用方修改不污染模块级常量)。"""
    return ModelCatalogFile(
        models={mid: info.model_copy(deep=True) for mid, info in _SEED_MODELS.items()}
    )


class ModelCatalog:
    """模型目录管理面: 持久化 models.json + Provider→Model 两级结构 + suggest 候选。"""

    def __init__(
        self,
        models_file: str | Path | None = None,
        control_plane: LLMControlPlane | None = None,
    ) -> None:
        # models_file 缺省 ~/.factory/models.json; control_plane 可选 (D3 校验 + provider enabled 过滤)
        self._models_file = (
            Path(models_file) if models_file is not None else _default_models_file()
        )
        self._control_plane = control_plane
        self._data = self.load()

    # ------------------------------------------------------------------ 持久化

    @property
    def path(self) -> Path:
        """models.json 落盘路径。"""
        return self._models_file

    def load(self) -> ModelCatalogFile:
        """原子读 models.json; 缺失 → 写入内置种子并返回; 损坏 → 响亮错误 (不静默)。"""
        path = self._models_file
        if not path.exists():
            logger.debug("model_catalog: seeding default models file: %s", path)
            data = _seed_catalog()
            self.save(data)
            return data
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptModelFileError(
                f"corrupt model file: {path}: {exc}"
            ) from exc
        except OSError as exc:
            raise ModelCatalogError(f"model file unreadable: {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptModelFileError(
                f"corrupt model file: {path}: expected JSON object"
            )
        try:
            data = ModelCatalogFile.model_validate(raw)
        except ValidationError as exc:
            raise CorruptModelFileError(
                f"corrupt model file: {path}: {exc}"
            ) from exc
        self._data = data
        return self._data

    def save(self, data: ModelCatalogFile) -> None:
        """原子写 (临时文件 + os.replace — 同 llm_control.py 模式)。"""
        path = self._models_file
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        self._data = data

    def reload(self) -> ModelCatalogFile:
        """重读磁盘 (重启恢复验证入口: save → 新实例构造/reload 往返一致)。"""
        return self.load()

    # ------------------------------------------------------------------ 注册/变更

    def register(self, model: ModelInfo) -> ModelInfo:
        """注册或覆盖模型 (唯一键 model_id); 落盘后返回。

        D3 两级结构校验: control_plane 提供时 provider_id 必须存在,
        否则响亮 UnknownProviderError (不静默); control_plane 为 None →
        跳过校验 (独立构造, 测试友好)。
        """
        cp = self._control_plane
        if cp is not None and cp.get_provider(model.provider_id) is None:
            raise UnknownProviderError(
                f"model_catalog: cannot register model {model.model_id!r}: "
                f"provider {model.provider_id!r} not found in control plane"
            )
        self._data.models[model.model_id] = model
        self.save(self._data)
        logger.debug(
            "model_catalog: registered model=%s provider=%s", model.model_id, model.provider_id
        )
        return model

    def unregister(self, model_id: str) -> bool:
        """删除模型; 存在 → True (并落盘), 不存在 → False。"""
        if model_id not in self._data.models:
            return False
        del self._data.models[model_id]
        self.save(self._data)
        return True

    def set_enabled(self, model_id: str, enabled: bool) -> ModelInfo:
        """模型级开关 (D4: 与 Provider 开关独立); 不存在 → 响亮 UnknownModelError。"""
        model = self._data.models.get(model_id)
        if model is None:
            raise UnknownModelError(f"model_catalog: unknown model {model_id!r}")
        updated = model.model_copy(update={"enabled": enabled})
        self._data.models[model_id] = updated
        self.save(self._data)
        return updated

    # ------------------------------------------------------------------ 查询

    def list_models(self, *, include_disabled: bool = False) -> list[ModelInfo]:
        """全部模型 (默认仅 enabled); 按 model_id 字典序 (确定性)。"""
        models = list(self._data.models.values())
        if not include_disabled:
            models = [m for m in models if m.enabled]
        return sorted(models, key=lambda m: m.model_id)

    def get_model(self, model_id: str) -> ModelInfo | None:
        """按 id 取模型 (不存在 → None)。"""
        return self._data.models.get(model_id)

    def find_by_capability(
        self, capability: str, *, enabled_only: bool = True
    ) -> list[ModelInfo]:
        """按能力过滤 (capability ∈ capabilities); 默认仅 enabled; 字典序。"""
        models = [
            m
            for m in self._data.models.values()
            if capability in m.capabilities and (not enabled_only or m.enabled)
        ]
        return sorted(models, key=lambda m: m.model_id)

    def models_by_provider(self, provider_id: str) -> list[ModelInfo]:
        """某 provider 下全部模型 (含 disabled — 两级结构查询); 字典序。"""
        models = [m for m in self._data.models.values() if m.provider_id == provider_id]
        return sorted(models, key=lambda m: m.model_id)

    # ------------------------------------------------------------------ Agent 侧查询

    def suggest(
        self,
        *,
        required_capabilities: list[str] | None = None,
        min_quality: float = 0.0,
        max_cost_per_1k: float | None = None,
        min_context_window: int | None = None,
        provider_id: str | None = None,
    ) -> list[ModelChoice]:
        """Agent 侧查询: "哪个模型适合该任务" — v1 确定性候选生成器 (D5, 非智能推荐)。

        过滤: enabled=True + (control_plane 提供时 provider 在 ControlPlane
        enabled) + required_capabilities 全命中 + max_cost_per_1k 成本上限 +
        min_context_window 上下文下限 + provider_id 定向。
        排序: 能力命中数降序 → cost (input_per_1k, 缺失视为 +inf) 升序 →
        model_id 字典序 (完全确定性)。
        score = 能力命中率 (命中数/要求数; 无要求 → None)。
        reasons 每条可解释 (能力命中/成本/上下文/placeholder 注明)。
        min_quality 为 TaskRequirement 兼容预留参数, v1 无模型级质量分,
        不参与过滤 (Router 阶段接入)。
        """
        required = list(required_capabilities or [])
        models = [
            m
            for m in self._data.models.values()
            if m.enabled and self._provider_enabled(m.provider_id)
        ]
        if provider_id is not None:
            models = [m for m in models if m.provider_id == provider_id]
        if required:
            models = [m for m in models if all(c in m.capabilities for c in required)]
        if max_cost_per_1k is not None:
            models = [
                m
                for m in models
                if m.cost.input_per_1k is None or m.cost.input_per_1k <= max_cost_per_1k
            ]
        if min_context_window is not None:
            models = [m for m in models if (m.context_window or 0) >= min_context_window]

        scored: list[tuple[int, ModelChoice]] = []
        for m in models:
            hits = sum(1 for c in required if c in m.capabilities)
            reasons = [f"capability '{c}': matched" for c in required]
            if max_cost_per_1k is not None:
                if m.cost.input_per_1k is None:
                    reasons.append(
                        f"cost: unspecified, assumed within max {max_cost_per_1k}/1k"
                    )
                else:
                    reasons.append(
                        f"cost input {m.cost.input_per_1k}/1k <= max {max_cost_per_1k}/1k"
                    )
            if min_context_window is not None:
                reasons.append(
                    f"context window {m.context_window or 0} >= min {min_context_window}"
                )
            if m.metadata.get("placeholder") is True:
                reasons.append("placeholder model (unverified)")
            scored.append(
                (
                    hits,
                    ModelChoice(
                        model_id=m.model_id,
                        provider_id=m.provider_id,
                        score=(hits / len(required)) if required else None,
                        reasons=reasons,
                        source="model-catalog",
                    ),
                )
            )
        scored.sort(
            key=lambda item: (
                -item[0],  # 能力命中数降序 (严格过滤下恒等, Router 扩展预留)
                self._cost_key(item[1].model_id),  # cost 升序
                item[1].model_id,  # 字典序 (确定性兜底)
            )
        )
        return [choice for _, choice in scored]

    # ------------------------------------------------------------------ 内部

    def _provider_enabled(self, provider_id: str) -> bool:
        """control_plane 提供时 provider 必须 enabled (D4 独立开关之外的第二道闸)。

        control_plane 为 None (独立构造) → 不按 provider 过滤。
        """
        cp = self._control_plane
        if cp is None:
            return True
        return cp.is_enabled(provider_id)

    def _cost_key(self, model_id: str) -> float:
        """suggest 排序用成本键: input_per_1k; 缺失 → +inf (排最后, 确定性)。"""
        m = self._data.models.get(model_id)
        if m is None or m.cost.input_per_1k is None:
            return float("inf")
        return m.cost.input_per_1k
