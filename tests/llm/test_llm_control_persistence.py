"""tests/llm/test_llm_control_persistence.py — S10-021 Phase 1: providers.json 持久化。

覆盖 (全 hermetic, tmp_path 隔离 — 不写真实 ~/.factory):
- save → load 往返一致 (同实例)
- 新实例 (重启模拟) 构造/reload 从磁盘读回配置
- 缺失文件 → 空配置不抛
- 损坏 JSON → 响亮 CorruptProviderFileError (绝不静默返回空)
- 结构不符 (顶层非对象 / providers 缺 id / 模型校验失败) → 响亮错误
- enable/disable/set_config 变更后 save 持久化 (新实例可见)
- 原子写: 落盘 JSON 合法, 无 .tmp 残留
- HOME 隔离: 默认路径 = <HOME>/.factory/providers.json (重启恢复验证)

basename 全仓库唯一 (test_llm_control_* 前缀); sys.path 挂仓库根
(factory-console 包父目录 — 含连字符包名, importlib 导入, 同 tests/console 模式)。
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

_llm = importlib.import_module("factory-console.llm_control")


def make_plane(tmp_path: Path, environ: dict[str, str] | None = None) -> Any:
    """hermetic LLMControlPlane: providers.json 在 tmp_path 下, 环境完全隔离。"""
    return _llm.LLMControlPlane(
        providers_file=tmp_path / "providers.json", environ=environ or {}
    )


def _providers_path(tmp_path: Path) -> Path:
    return tmp_path / "providers.json"


# ------------------------------------------------------------------ 持久化往返


class TestSaveLoadRoundtrip:
    """save → load / 重启恢复 (A 验收: 重启后 Provider 配置仍存在)。"""

    def test_save_then_load_identical(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        plane.set_config(
            "deepseek",
            enabled=True,
            models=["deepseek-v4-pro"],
            base_url="https://llm.example.com/v1/chat/completions",
            api_key_ref="env:DEEPSEEK_API_KEY",
        )
        loaded = plane.load()
        assert loaded.version == 1
        assert "deepseek" in loaded.providers
        pc = loaded.providers["deepseek"]
        assert pc.enabled is True
        assert pc.models == ["deepseek-v4-pro"]
        assert pc.base_url == "https://llm.example.com/v1/chat/completions"
        assert pc.api_key_ref == "env:DEEPSEEK_API_KEY"

    def test_new_instance_restart_reads_disk(self, tmp_path: Path) -> None:
        """重启模拟: 全新实例 (同路径) 构造即从磁盘读回 — save→reload 往返一致。"""
        plane1 = make_plane(tmp_path)
        plane1.set_config(
            "openai", enabled=True, models=["gpt-4o"], api_key_ref="env:OPENAI_API_KEY"
        )
        plane2 = make_plane(tmp_path)  # 模拟重启 — 全新实例, 零内存共享
        pc = plane2.get_provider("openai")
        assert pc is not None
        assert pc.enabled is True
        assert pc.models == ["gpt-4o"]
        assert pc.api_key_ref == "env:OPENAI_API_KEY"
        # reload 也是同一磁盘来源
        assert plane2.reload().providers["openai"].enabled is True

    def test_reload_sees_external_change(self, tmp_path: Path) -> None:
        """另一实例修改落盘后, reload 读到新状态 (内存缓存与磁盘同步)。"""
        plane = make_plane(tmp_path)
        plane.enable("deepseek", api_key_ref="env:DEEPSEEK_API_KEY")
        other = make_plane(tmp_path)
        other.disable("deepseek")
        assert plane.get_provider("deepseek").enabled is True  # 内存仍旧
        assert plane.reload().providers["deepseek"].enabled is False

    def test_on_disk_json_valid_and_versioned(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        plane.enable(
            "anthropic",
            models=["claude-sonnet-4-20250514"],
            api_key_ref="env:ANTHROPIC_API_KEY",
        )
        raw = json.loads(_providers_path(tmp_path).read_text(encoding="utf-8"))
        assert raw["version"] == 1
        assert raw["providers"]["anthropic"]["enabled"] is True
        assert raw["providers"]["anthropic"]["api_key_ref"] == "env:ANTHROPIC_API_KEY"

    def test_atomic_write_no_tmp_leftovers(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        for i in range(3):
            plane.set_config("deepseek", enabled=True, models=[f"m{i}"])
        assert _providers_path(tmp_path).exists()
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


# ------------------------------------------------------------------ 缺失/损坏容错


class TestMissingAndCorrupt:
    """缺失 → 空配置不抛; 损坏 → 响亮错误不静默 (store.py 同语义)。"""

    def test_missing_file_is_empty_config(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        data = plane.load()
        assert data.version == 1
        assert data.providers == {}
        assert plane.list_providers() == []
        assert plane.enabled_providers() == []
        assert plane.any_enabled_with_key() is False

    def test_corrupt_json_raises_loud(self, tmp_path: Path) -> None:
        _providers_path(tmp_path).write_text("{not valid json!!", encoding="utf-8")
        with pytest.raises(_llm.CorruptProviderFileError):
            make_plane(tmp_path).load()

    def test_top_level_non_object_raises(self, tmp_path: Path) -> None:
        _providers_path(tmp_path).write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(_llm.CorruptProviderFileError):
            make_plane(tmp_path).load()

    def test_invalid_field_type_raises(self, tmp_path: Path) -> None:
        """模型校验失败 (enabled 非法类型) → 响亮错误。"""
        data = {
            "version": 1,
            "providers": {"deepseek": {"id": "deepseek", "enabled": "not-a-bool"}},
        }
        _providers_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(_llm.CorruptProviderFileError):
            make_plane(tmp_path).load()

    def test_provider_entry_missing_id_raises(self, tmp_path: Path) -> None:
        data = {"version": 1, "providers": {"deepseek": {"enabled": True}}}
        _providers_path(tmp_path).write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(_llm.CorruptProviderFileError):
            make_plane(tmp_path).load()


# ------------------------------------------------------------------ enable/disable/set_config


class TestEnableDisableSetConfig:
    """变更接口: get-or-create + 保存后状态 + 持久化可见。"""

    def test_enable_creates_and_persists(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        pc = plane.enable(
            "deepseek", models=["deepseek-v4-pro"], api_key_ref="env:DEEPSEEK_API_KEY"
        )
        assert pc.enabled is True
        assert plane.is_enabled("deepseek") is True
        assert make_plane(tmp_path).is_enabled("deepseek") is True  # 持久化

    def test_disable_persists(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        plane.enable("openai", api_key_ref="env:OPENAI_API_KEY")
        pc = plane.disable("openai")
        assert pc.enabled is False
        assert plane.is_enabled("openai") is False
        assert make_plane(tmp_path).is_enabled("openai") is False

    def test_set_config_keeps_enabled_state(self, tmp_path: Path) -> None:
        """set_config 不改变既有 enabled 状态 (除非显式传 enabled=)。"""
        plane = make_plane(tmp_path)
        plane.enable("deepseek", api_key_ref="env:DEEPSEEK_API_KEY")
        plane.set_config(
            "deepseek",
            models=["deepseek-v4-pro", "deepseek-reasoner"],
            base_url="https://new.example.com/v1/chat/completions",
        )
        pc = plane.get_provider("deepseek")
        assert pc is not None
        assert pc.enabled is True
        assert pc.models == ["deepseek-v4-pro", "deepseek-reasoner"]
        assert pc.base_url == "https://new.example.com/v1/chat/completions"

    def test_set_config_can_flip_enabled(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        plane.set_config("deepseek", enabled=True, api_key_ref="env:DEEPSEEK_API_KEY")
        assert plane.is_enabled("deepseek") is True

    def test_unknown_field_rejected(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        with pytest.raises(ValueError):
            plane.set_config("deepseek", bogus_field=1)

    def test_enabled_providers_filters(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path)
        plane.set_config("deepseek", enabled=True, api_key_ref="env:DEEPSEEK_API_KEY")
        plane.set_config("openai", enabled=False, api_key_ref="env:OPENAI_API_KEY")
        plane.set_config("ollama", enabled=True)
        assert [p.id for p in plane.enabled_providers()] == ["deepseek", "ollama"]
        assert sorted(p.id for p in plane.list_providers()) == [
            "deepseek",
            "ollama",
            "openai",
        ]
        assert plane.is_enabled("openai") is False
        assert plane.is_enabled("nope") is False


# ------------------------------------------------------------------ HOME 隔离 (默认路径)


class TestDefaultPathHomeIsolation:
    """默认落盘位置 ~/.factory/providers.json — HOME 重定向即隔离。"""

    def test_default_path_under_home_and_restart(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        plane = _llm.LLMControlPlane(environ={})
        assert plane.path == tmp_path / ".factory" / "providers.json"
        plane.enable("deepseek", enabled=True, api_key_ref="env:DEEPSEEK_API_KEY")
        assert (tmp_path / ".factory" / "providers.json").exists()
        # 重启恢复: 新实例 (同样 HOME) 读回
        plane2 = _llm.LLMControlPlane(environ={})
        assert plane2.is_enabled("deepseek") is True

    def test_real_home_untouched(self, tmp_path: Path, monkeypatch) -> None:
        """显式 providers_file 时绝不触碰真实 ~/.factory。"""
        plane = make_plane(tmp_path)
        plane.enable("deepseek", enabled=True)
        real = Path.home() / ".factory" / "providers.json"
        assert not real.exists() or real.read_text(encoding="utf-8") != plane.path.read_text(
            encoding="utf-8"
        )
