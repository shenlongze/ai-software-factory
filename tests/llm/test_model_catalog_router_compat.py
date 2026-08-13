"""tests/llm/test_model_catalog_router_compat.py — S10-022 Phase 2A: Router 兼容预留。

覆盖 (全 hermetic: models_file/providers_file=tmp 路径注入, 不写真实 ~/.factory):
- F 验收: ModelChoice 字段集 = {model_id, provider_id, score, reasons, source}
  且 source 默认 "model-catalog"; suggest() 返回 ModelChoice 实例
- A 验收: models.json model.provider_id ↔ providers.json provider 两级一致;
  register 时 provider 不存在 → 响亮 UnknownProviderError (不静默)
- 不实现 Router 逻辑: 仅字段兼容 + 候选生成, 无任何决策/路由行为断言

basename 全仓库唯一; sys.path 挂仓库根 (factory-console 包父目录)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录
    sys.path.insert(0, str(_ROOT))

_model_catalog = importlib.import_module("factory-console.model_catalog")
_llm_control = importlib.import_module("factory-console.llm_control")

ModelCatalog = _model_catalog.ModelCatalog
ModelInfo = _model_catalog.ModelInfo
ModelCost = _model_catalog.ModelCost
ModelChoice = _model_catalog.ModelChoice
UnknownProviderError = _model_catalog.UnknownProviderError


def models_file(tmp_path: Path) -> Path:
    return tmp_path / "models.json"


def make_control_plane(
    tmp_path: Path, providers: dict[str, dict] | None = None
) -> Any:
    """构造 ControlPlane (providers.json 预写)。"""
    path = tmp_path / "providers.json"
    data = {"version": 1, "providers": {}}
    for pid, cfg in (providers or {}).items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data), encoding="utf-8")
    return _llm_control.LLMControlPlane(providers_file=path)


# ------------------------------------------------------------------ F: ModelChoice 字段兼容


class TestModelChoiceCompat:
    """F 验收: Router 兼容预留字段集 — 不实现 router 逻辑。"""

    def test_model_choice_exact_field_set(self) -> None:
        """字段集恒等 {model_id, provider_id, score, reasons, source} — 兼容契约。"""
        assert set(ModelChoice.model_fields) == {
            "model_id",
            "provider_id",
            "score",
            "reasons",
            "source",
        }

    def test_model_choice_defaults(self) -> None:
        c = ModelChoice(model_id="m", provider_id="deepseek")
        assert c.score is None
        assert c.reasons == []
        assert c.source == "model-catalog"  # v1 决策来源

    def test_model_choice_all_fields_settable(self) -> None:
        c = ModelChoice(
            model_id="m",
            provider_id="deepseek",
            score=0.8,
            reasons=["capability 'code': matched"],
            source="model-catalog",
        )
        assert c.model_dump() == {
            "model_id": "m",
            "provider_id": "deepseek",
            "score": 0.8,
            "reasons": ["capability 'code': matched"],
            "source": "model-catalog",
        }

    def test_suggest_returns_model_choice_instances(self, tmp_path: Path) -> None:
        cat = ModelCatalog(models_file=models_file(tmp_path))
        choices = cat.suggest(required_capabilities=["code"])
        assert len(choices) > 0
        assert all(isinstance(c, ModelChoice) for c in choices)
        # 每个候选携带完整 Router 兼容字段
        for c in choices:
            assert c.model_id
            assert c.provider_id
            assert c.source == "model-catalog"
            assert isinstance(c.reasons, list) and c.reasons
            assert c.score is not None


# ------------------------------------------------------------------ A: 两级结构校验


class TestTwoLevelStructure:
    """A 验收: Provider→Model 关联 — register 校验 provider 存在。"""

    def test_register_unknown_provider_raises(self, tmp_path: Path) -> None:
        """control_plane 提供 + provider 不存在 → 响亮 UnknownProviderError (不静默)。"""
        cp = make_control_plane(tmp_path, {"deepseek": {"enabled": True}})
        cat = ModelCatalog(models_file=models_file(tmp_path), control_plane=cp)
        with pytest.raises(UnknownProviderError):
            cat.register(
                ModelInfo(model_id="ghost-model", provider_id="no-such-provider")
            )
        assert cat.get_model("ghost-model") is None  # 校验失败 → 未写入

    def test_register_known_provider_ok(self, tmp_path: Path) -> None:
        cp = make_control_plane(tmp_path, {"deepseek": {"enabled": True}})
        cat = ModelCatalog(models_file=models_file(tmp_path), control_plane=cp)
        model = cat.register(
            ModelInfo(
                model_id="deepseek-extra",
                provider_id="deepseek",
                capabilities=["code"],
                cost=ModelCost(input_per_1k=0.0001, output_per_1k=0.0002),
            )
        )
        assert model.provider_id == "deepseek"
        assert cat.get_model("deepseek-extra") is not None

    def test_register_without_control_plane_skips_validation(self, tmp_path: Path) -> None:
        """control_plane 为 None (独立构造) → 跳过 provider 校验 (测试友好)。"""
        cat = ModelCatalog(models_file=models_file(tmp_path))
        cat.register(ModelInfo(model_id="standalone-m", provider_id="any-provider"))
        assert cat.get_model("standalone-m") is not None

    def test_models_json_provider_ids_link_to_providers_json(self, tmp_path: Path) -> None:
        """A 验收核心: models.json 每个 model.provider_id 都指向 providers.json 的 provider。"""
        cp = make_control_plane(
            tmp_path,
            {
                "deepseek": {"enabled": True},
                "openai": {"enabled": True},
                "anthropic": {"enabled": True},
            },
        )
        cat = ModelCatalog(models_file=models_file(tmp_path), control_plane=cp)
        # 种子模型 + 手工注册 → 全量校验两级一致
        for model in cat.list_models(include_disabled=True):
            assert cp.get_provider(model.provider_id) is not None, (
                f"model {model.model_id} → provider {model.provider_id} 悬空"
            )
        # 反向: 每个 provider 的 models.json 条目均可列举 (models_by_provider)
        for pid in ("deepseek", "openai", "anthropic"):
            assert cat.models_by_provider(pid), f"provider {pid} 无模型条目"

    def test_suggest_excludes_provider_not_in_control_plane(self, tmp_path: Path) -> None:
        """两级结构过滤: 模型在目录中但 provider 未纳入 ControlPlane → 不候选。"""
        cp = make_control_plane(tmp_path, {"deepseek": {"enabled": True}})
        cat = ModelCatalog(models_file=models_file(tmp_path), control_plane=cp)
        ids = [c.model_id for c in cat.suggest()]
        assert ids == ["deepseek-chat", "deepseek-reasoner"]
