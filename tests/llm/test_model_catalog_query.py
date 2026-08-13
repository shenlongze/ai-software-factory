"""tests/llm/test_model_catalog_query.py — S10-022 Phase 2A: 查询 + suggest。

覆盖 (全 hermetic: models_file=tmp 路径注入, 不写真实 ~/.factory):
- B 验收: ModelInfo 全字段 (model_id/provider_id/capabilities/context_window/
  cost/enabled/metadata) 结构完整
- C 验收: get_model / list_models(include_disabled) / find_by_capability /
  models_by_provider
- D 验收: suggest() 返回 ModelChoice 列表 — 能力过滤 / 成本上限 / 上下文下限 /
  确定性排序 (cost 升序 + model_id 字典序兜底) / placeholder reasons 注明 /
  provider enabled 过滤 (有 control_plane 时) / 无要求 → score None / 定向 provider

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


def models_file(tmp_path: Path) -> Path:
    return tmp_path / "models.json"


def make_catalog(tmp_path: Path) -> ModelCatalog:
    return ModelCatalog(models_file=models_file(tmp_path))  # 首次缺失 → 自动种子


def make_control_plane(
    tmp_path: Path, providers: dict[str, dict] | None = None
) -> Any:
    """构造 ControlPlane (providers.json 预写 — 与 llm_control 测试同装配)。"""
    path = tmp_path / "providers.json"
    data = {"version": 1, "providers": {}}
    for pid, cfg in (providers or {}).items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data), encoding="utf-8")
    return _llm_control.LLMControlPlane(providers_file=path)


def choice_ids(choices: list[ModelChoice]) -> list[str]:
    return [c.model_id for c in choices]


# ------------------------------------------------------------------ B: 结构


class TestModelInfoStructure:
    """B 验收: ModelInfo 全字段结构化。"""

    def test_model_info_all_fields(self) -> None:
        m = ModelInfo(
            model_id="m1",
            provider_id="deepseek",
            capabilities=["code", "chat"],
            context_window=64000,
            cost=ModelCost(input_per_1k=0.1, output_per_1k=0.2),
            enabled=True,
            metadata={"placeholder": False, "evidence": "x"},
        )
        assert m.model_id == "m1"
        assert m.provider_id == "deepseek"
        assert m.capabilities == ["code", "chat"]
        assert m.context_window == 64000
        assert m.cost.input_per_1k == 0.1
        assert m.cost.output_per_1k == 0.2
        assert m.enabled is True
        assert m.metadata == {"placeholder": False, "evidence": "x"}

    def test_model_info_defaults(self) -> None:
        m = ModelInfo(model_id="m2", provider_id="deepseek")
        assert m.capabilities == []
        assert m.context_window is None
        assert m.cost == ModelCost()
        assert m.enabled is True
        assert m.metadata == {}


# ------------------------------------------------------------------ C: 查询


class TestQueries:
    """C 验收: get_model / list_models / find_by_capability / models_by_provider。"""

    def test_get_model_found_and_missing(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        assert cat.get_model("gpt-4o") is not None
        assert cat.get_model("nope") is None

    def test_list_models_default_excludes_disabled(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.set_enabled("gpt-4o", False)
        ids = [m.model_id for m in cat.list_models()]
        assert "gpt-4o" not in ids
        assert len(ids) == 3
        assert ids == sorted(ids)  # 字典序

    def test_list_models_include_disabled(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.set_enabled("gpt-4o", False)
        ids = [m.model_id for m in cat.list_models(include_disabled=True)]
        assert "gpt-4o" in ids
        assert len(ids) == 4

    def test_find_by_capability_hits(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = choice_ids(cat.find_by_capability("vision"))  # type: ignore[arg-type]
        assert ids == ["gpt-4o"]

    def test_find_by_capability_enabled_only_flag(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.set_enabled("gpt-4o", False)
        assert choice_ids(cat.find_by_capability("vision")) == []  # type: ignore[arg-type]
        assert choice_ids(cat.find_by_capability("vision", enabled_only=False)) == [  # type: ignore[arg-type]
            "gpt-4o"
        ]

    def test_models_by_provider_groups(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = [m.model_id for m in cat.models_by_provider("deepseek")]
        assert ids == ["deepseek-chat", "deepseek-reasoner"]
        assert cat.models_by_provider("ollama") == []


# ------------------------------------------------------------------ D: suggest 过滤


class TestSuggestFilters:
    """D 验收: 能力 / 成本 / 上下文 / provider 过滤。"""

    def test_suggest_capability_filter(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = choice_ids(cat.suggest(required_capabilities=["vision"]))
        assert ids == ["gpt-4o"]  # 唯一 vision 模型
        # 多能力全命中: chat + code → reasoner 缺 chat 被滤掉
        ids2 = choice_ids(cat.suggest(required_capabilities=["code", "chat"]))
        assert ids2 == ["deepseek-chat", "gpt-4o", "claude-sonnet-4"]

    def test_suggest_cost_cap(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = choice_ids(cat.suggest(required_capabilities=["code"], max_cost_per_1k=0.001))
        assert ids == ["deepseek-chat", "deepseek-reasoner"]  # gpt-4o/claude 超上限

    def test_suggest_context_floor(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = choice_ids(cat.suggest(min_context_window=100000))
        assert ids == ["gpt-4o", "claude-sonnet-4"]  # deepseek 64000 被滤掉

    def test_suggest_provider_param(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        ids = choice_ids(cat.suggest(provider_id="deepseek"))
        assert ids == ["deepseek-chat", "deepseek-reasoner"]

    def test_suggest_nothing_matches_empty(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        assert cat.suggest(required_capabilities=["speech"]) == []
        assert cat.suggest(min_context_window=10_000_000) == []

    def test_suggest_disabled_model_excluded(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.set_enabled("gpt-4o", False)
        ids = choice_ids(cat.suggest(required_capabilities=["vision"]))
        assert ids == []  # 模型级 enabled 过滤生效

    def test_suggest_provider_enabled_via_control_plane(self, tmp_path: Path) -> None:
        """有 control_plane 时: provider 不在/禁用 → 其模型被滤掉 (D4 第二道闸)。"""
        cp = make_control_plane(
            tmp_path, {"deepseek": {"enabled": True}, "openai": {"enabled": False}}
        )
        cat = ModelCatalog(models_file=models_file(tmp_path), control_plane=cp)
        ids = choice_ids(cat.suggest(required_capabilities=["code"]))
        assert "gpt-4o" not in ids  # openai disabled
        assert "claude-sonnet-4" not in ids  # anthropic 不在 ControlPlane
        assert ids == ["deepseek-chat", "deepseek-reasoner"]


# ------------------------------------------------------------------ D: suggest 排序与理由


class TestSuggestOrdering:
    """D 验收: 确定性排序 (cost 升序 → model_id 字典序兜底) + reasons 可解释。"""

    def test_suggest_deterministic_cost_asc(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        choices = cat.suggest(required_capabilities=["code"])
        # 全命中 → 能力命中数并列 → cost 升序: 0.00028 < 0.00055 < 0.0025 < 0.003
        assert choice_ids(choices) == [
            "deepseek-chat",
            "deepseek-reasoner",
            "gpt-4o",
            "claude-sonnet-4",
        ]
        costs = [
            cat.get_model(c.model_id).cost.input_per_1k  # type: ignore[union-attr]
            for c in choices
        ]
        assert costs == sorted(costs)

    def test_suggest_tiebreak_model_id_lexicographic(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        # 同 cost 同能力 → model_id 字典序兜底 (确定性铁证)
        cat.register(ModelInfo(model_id="zzz-tie", provider_id="deepseek", capabilities=["code"]))
        cat.register(ModelInfo(model_id="aaa-tie", provider_id="deepseek", capabilities=["code"]))
        ids = choice_ids(cat.suggest(required_capabilities=["code"]))
        assert ids.index("aaa-tie") < ids.index("zzz-tie")

    def test_suggest_score_hit_rate(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        choices = cat.suggest(required_capabilities=["code", "chat"])
        for c in choices:
            assert c.score == 1.0  # 严格过滤 → 全命中 → 命中率 1.0
        single = cat.suggest(required_capabilities=["code"])[0]
        assert single.score == 1.0

    def test_suggest_no_requirements_score_none(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        choices = cat.suggest()  # 无要求 → 全部 enabled
        assert len(choices) == 4
        assert all(c.score is None for c in choices)  # 无要求 → score None

    def test_suggest_reasons_explainable(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        choice = cat.suggest(
            required_capabilities=["code"], max_cost_per_1k=0.001, min_context_window=1000
        )[0]
        joined = "\n".join(choice.reasons)
        assert "capability 'code': matched" in joined
        assert "cost input" in joined
        assert "context window" in joined

    def test_suggest_placeholder_reason(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        choices = cat.suggest(required_capabilities=["reasoning"])
        claude = next(c for c in choices if c.model_id == "claude-sonnet-4")
        assert any("placeholder model" in r for r in claude.reasons)  # 真实性注明
        # placeholder 模型仍可返回 (不冒充真实, 但可候选)
        assert "claude-sonnet-4" in choice_ids(choices)

    def test_suggest_repeated_calls_identical(self, tmp_path: Path) -> None:
        """确定性: 同参数重复调用结果逐字段一致。"""
        cat = make_catalog(tmp_path)
        a = cat.suggest(required_capabilities=["code", "chat"], max_cost_per_1k=0.01)
        b = cat.suggest(required_capabilities=["code", "chat"], max_cost_per_1k=0.01)
        assert [c.model_dump() for c in a] == [c.model_dump() for c in b]
