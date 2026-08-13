"""tests/llm/test_model_catalog_persistence.py — S10-022 Phase 2A: 持久化。

覆盖 (全 hermetic: models_file=tmp 路径注入, 不写真实 ~/.factory):
- E 验收: 首次缺失文件自动写入种子 (4 模型 + version 1 + 真实性字段)
- save → reload/新实例 往返一致 (重启恢复); reload 拾取外部改动
- 损坏 JSON / 非对象 JSON / 结构不符 → 响亮 CorruptModelFileError (不静默)
- register 落盘 / 覆盖 / unregister / set_enabled 持久化
- 原子写: 操作后仅 models.json, 无残留 tmp 文件
- HOME 隔离: 默认路径 = <home>/.factory/models.json

basename 全仓库唯一; sys.path 挂仓库根 (factory-console 包父目录)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录
    sys.path.insert(0, str(_ROOT))

_model_catalog = importlib.import_module("factory-console.model_catalog")

ModelCatalog = _model_catalog.ModelCatalog
ModelInfo = _model_catalog.ModelInfo
ModelCost = _model_catalog.ModelCost
CorruptModelFileError = _model_catalog.CorruptModelFileError
UnknownModelError = _model_catalog.UnknownModelError


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME → 临时目录: ModelCatalog 默认路径 = <home>/.factory/models.json。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def models_file(tmp_path: Path) -> Path:
    return tmp_path / "models.json"


def make_catalog(tmp_path: Path, *, seed: bool = True) -> ModelCatalog:
    """构造 ModelCatalog; seed=False 时预写空 models.json (避免自动种子)。"""
    path = models_file(tmp_path)
    if not seed:
        path.write_text(json.dumps({"version": 1, "models": {}}), encoding="utf-8")
    return ModelCatalog(models_file=path)


def sample_model(model_id: str = "test-model", provider_id: str = "deepseek") -> ModelInfo:
    return ModelInfo(
        model_id=model_id,
        provider_id=provider_id,
        capabilities=["code", "chat"],
        context_window=32000,
        cost=ModelCost(input_per_1k=0.001, output_per_1k=0.002),
        metadata={"note": "test"},
    )


# ------------------------------------------------------------------ E: 种子自举


class TestSeedBootstrapping:
    """E 验收: 首次缺失文件自动写入内置种子。"""

    def test_first_load_writes_seed_file(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        assert cat.path.exists()  # 缺失 → load 即落盘种子
        raw = json.loads(cat.path.read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert set(raw["models"].keys()) == {
            "deepseek-chat",
            "deepseek-reasoner",
            "gpt-4o",
            "claude-sonnet-4",
        }

    def test_seed_fields_authentic(self, tmp_path: Path) -> None:
        """真实性铁律: 种子字段与设计 §7 一致 (费率/上下文/placeholder 注明)。"""
        cat = make_catalog(tmp_path)
        ds = cat.get_model("deepseek-chat")
        assert ds is not None
        assert ds.provider_id == "deepseek"
        assert ds.capabilities == ["code", "chat"]
        assert ds.context_window == 64000
        assert ds.cost.input_per_1k == 0.00028
        assert ds.cost.output_per_1k == 0.00042
        assert ds.metadata.get("placeholder") is False

        claude = cat.get_model("claude-sonnet-4")
        assert claude is not None
        assert claude.context_window == 200000
        assert claude.cost.input_per_1k == 0.003
        assert claude.metadata.get("placeholder") is True
        assert "unverified" in claude.metadata.get("evidence", "")

    def test_default_path_home_isolated(self, isolated_home: Path) -> None:
        """默认路径 = <home>/.factory/models.json (HOME 注入隔离)。"""
        cat = ModelCatalog()  # 无参 → 默认路径
        assert cat.path == isolated_home / ".factory" / "models.json"
        assert cat.path.exists()  # 种子已落盘
        assert len(cat.list_models(include_disabled=True)) == 4


# ------------------------------------------------------------------ E: 往返一致


class TestRoundTrip:
    """E 验收: save → reload/新实例 往返一致 (重启恢复)。"""

    def test_reload_roundtrip(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.register(sample_model())
        cat.reload()  # 模拟重启重读
        restored = cat.get_model("test-model")
        assert restored is not None
        assert restored.model_dump() == sample_model().model_dump()

    def test_new_instance_roundtrip(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.register(sample_model())
        fresh = ModelCatalog(models_file=models_file(tmp_path))  # 新实例 = 重启
        restored = fresh.get_model("test-model")
        assert restored is not None
        assert restored.model_dump() == sample_model().model_dump()

    def test_reload_picks_up_external_change(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        # 外部进程直接改文件
        data = json.loads(cat.path.read_text(encoding="utf-8"))
        data["models"]["external-model"] = sample_model("external-model").model_dump()
        cat.path.write_text(json.dumps(data), encoding="utf-8")
        cat.reload()
        assert cat.get_model("external-model") is not None


# ------------------------------------------------------------------ 损坏响亮错误


class TestCorruptFile:
    """损坏 JSON / 非对象 / 结构不符 → 响亮 CorruptModelFileError (绝不静默)。"""

    def test_corrupt_json_raises(self, tmp_path: Path) -> None:
        path = models_file(tmp_path)
        path.write_text("{broken!!", encoding="utf-8")
        with pytest.raises(CorruptModelFileError):
            ModelCatalog(models_file=path)

    def test_non_object_json_raises(self, tmp_path: Path) -> None:
        path = models_file(tmp_path)
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(CorruptModelFileError):
            ModelCatalog(models_file=path)

    def test_structurally_invalid_raises(self, tmp_path: Path) -> None:
        path = models_file(tmp_path)
        # 缺 provider_id 等必填字段 → pydantic ValidationError → 响亮包装
        path.write_text(
            json.dumps({"version": 1, "models": {"x": {"model_id": "x"}}}),
            encoding="utf-8",
        )
        with pytest.raises(CorruptModelFileError):
            ModelCatalog(models_file=path)


# ------------------------------------------------------------------ 注册/删除/启停 持久化


class TestMutations:
    """register/unregister/set_enabled 均落盘且可恢复。"""

    def test_register_persists_to_disk(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.register(sample_model("disk-model"))
        raw = json.loads(cat.path.read_text(encoding="utf-8"))
        assert raw["models"]["disk-model"]["provider_id"] == "deepseek"
        assert raw["models"]["disk-model"]["cost"]["input_per_1k"] == 0.001

    def test_register_overwrite_replaces(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.register(sample_model("m", provider_id="deepseek"))
        updated = ModelInfo(
            model_id="m",
            provider_id="deepseek",
            capabilities=["vision"],
            context_window=64000,
        )
        cat.register(updated)
        got = cat.get_model("m")
        assert got is not None
        assert got.capabilities == ["vision"]  # 覆盖生效
        assert len(cat.list_models(include_disabled=True)) == 5  # 无重复条目

    def test_unregister_existing_true_and_gone(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        cat.register(sample_model("doomed"))
        assert cat.unregister("doomed") is True
        assert cat.get_model("doomed") is None
        assert "doomed" not in json.loads(cat.path.read_text(encoding="utf-8"))["models"]

    def test_unregister_missing_false(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        assert cat.unregister("never-existed") is False

    def test_set_enabled_toggles_and_persists(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        result = cat.set_enabled("gpt-4o", False)
        assert result.enabled is False
        assert cat.get_model("gpt-4o").enabled is False  # type: ignore[union-attr]
        fresh = ModelCatalog(models_file=models_file(tmp_path))
        assert fresh.get_model("gpt-4o").enabled is False  # type: ignore[union-attr]

    def test_set_enabled_unknown_raises(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        with pytest.raises(UnknownModelError):
            cat.set_enabled("no-such-model", True)

    def test_atomic_write_no_leftover_tmp(self, tmp_path: Path) -> None:
        cat = make_catalog(tmp_path)
        for i in range(5):
            cat.register(sample_model(f"m{i}"))
        cat.unregister("m0")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "models.json"]
        assert leftovers == []  # 原子写: 无残留临时文件
        # 落盘文件本身仍可解析
        assert json.loads(cat.path.read_text(encoding="utf-8"))["version"] == 1
