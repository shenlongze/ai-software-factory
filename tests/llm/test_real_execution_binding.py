"""tests/llm/test_real_execution_binding.py — S10-023 Phase 3: exec CLI Provider 装配修复。

覆盖 (全 hermetic: HOME 隔离 + 假 key, 不调真实 API):
- A 验收: providers.json 配置 deepseek → _provider_registry() 装配 deepseek
  (OpenAIProvider + OpenAI 兼容端点; provider_id=deepseek, registry.get 命中)
- resolve_runtime_config → Provider 构造参数正确 (model/base_url/api_key/费率)
- anthropic → AnthropicProvider; ollama → OpenAIProvider + 本地占位 key
- B 验收: 无 providers.json / enabled 无 key / 全 disabled → 回退 legacy
  default_registry() (anthropic+openai, 回归保护)
- C 验收: 异常安全 — ControlPlane import 失败 / providers.json 损坏 → 回退不抛
- key 纪律: 全部用假 key (sk-test-*), 不读真实 ~/.hermes/.env; 任何断言不
  触碰 key 明文日志

basename 全仓库唯一; sys.path 挂仓库根 (factory-console 包 — 包名带连字符,
经 importlib 加载) + factory-core + factory-exec (exec 包父目录)。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"  # exec 包父目录 (factory-exec/exec/)
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

_cli = importlib.import_module("exec.cli")

from exec.providers.anthropic import AnthropicProvider  # noqa: E402
from exec.providers.openai import OpenAIProvider  # noqa: E402

#: 可能干扰的进程环境变量 (hermetic 测试前清空)
_ENV_KEYS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """清空相关进程环境变量 (防跨测试泄漏; 快照还原 legacy key)。"""
    snapshot = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key, val in snapshot.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME → 临时目录: LLMControlPlane 默认路径 = <home>/.factory/providers.json。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def seed_providers(home: Path, providers: dict[str, dict[str, Any]]) -> Path:
    """写 <home>/.factory/providers.json (默认路径 — LLMControlPlane 读取点)。"""
    path = home / ".factory" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "providers": {}}
    for pid, cfg in providers.items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _legacy_ids() -> list[str]:
    """legacy default_registry() 的注册 id (回归保护锚点: anthropic+openai)。"""
    return ["anthropic", "openai"]


# ------------------------------------------------------------------ A: ControlPlane 装配


class TestControlPlaneAssembly:
    """A 验收: providers.json 配置 deepseek → _provider_registry() 装配 deepseek。"""

    def test_deepseek_assembled_from_providers_json(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """enabled deepseek + api_key_ref + env key → registry.get("deepseek") 命中。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "base_url": "https://api.deepseek.com/v1/chat/completions",
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")

        registry = _cli._provider_registry()
        provider = registry.get("deepseek")
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_id == "deepseek"  # 实例级覆盖, 注册键命中
        assert registry.ids() == ["deepseek"]  # ControlPlane 优先, 无 legacy 混入

    def test_runtime_config_passed_to_provider_constructor(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_runtime_config 的 model/base_url/api_key/费率正确传入 Provider 构造。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "base_url": "https://llm.example.com/v1/chat/completions",
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                    "metadata": {
                        "input_rate_per_1k": 0.00028,
                        "output_rate_per_1k": 0.00042,
                    },
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-runtime")

        provider = _cli._provider_registry().get("deepseek")
        assert provider is not None
        assert provider._model == "deepseek-v4-pro"
        assert provider._base_url == "https://llm.example.com/v1/chat/completions"
        assert provider._api_key == "sk-test-runtime"
        assert provider._input_rate_per_1k == 0.00028
        assert provider._output_rate_per_1k == 0.00042

    def test_anthropic_assembled_from_providers_json(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """anthropic → AnthropicProvider (provider_id=anthropic, 配置 model 传入)。"""
        seed_providers(
            isolated_home,
            {
                "anthropic": {
                    "enabled": True,
                    "models": ["claude-sonnet-4-20250514"],
                    "api_key_ref": "env:ANTHROPIC_API_KEY",
                }
            },
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        provider = _cli._provider_registry().get("anthropic")
        assert provider is not None
        assert isinstance(provider, AnthropicProvider)
        assert provider.provider_id == "anthropic"
        assert provider._model == "claude-sonnet-4-20250514"
        assert provider._api_key == "sk-ant-test"

    def test_openai_assembled_from_providers_json(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """openai → OpenAIProvider (类属性 provider_id=openai, 实例覆盖同值)。"""
        seed_providers(
            isolated_home,
            {
                "openai": {
                    "enabled": True,
                    "models": ["gpt-4o"],
                    "api_key_ref": "env:OPENAI_API_KEY",
                }
            },
        )
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")

        provider = _cli._provider_registry().get("openai")
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_id == "openai"

    def test_ollama_openai_compat_placeholder_key(
        self, isolated_home: Path
    ) -> None:
        """ollama (本地无 key) → OpenAIProvider + 占位 key "ollama" (同 workflow_runner)。"""
        seed_providers(
            isolated_home, {"ollama": {"enabled": True, "models": ["qwen2.5:14b"]}}
        )

        provider = _cli._provider_registry().get("ollama")
        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_id == "ollama"
        assert provider._api_key == "ollama"


# ------------------------------------------------------------------ B: legacy 回退


class TestLegacyFallback:
    """B 验收: 无 providers.json / 未命中 → 回退 legacy default_registry()。"""

    def test_no_providers_file_falls_back(self, isolated_home: Path) -> None:
        """无 providers.json → default_registry() (anthropic+openai, 回归保护)。"""
        registry = _cli._provider_registry()
        assert registry.ids() == _legacy_ids()
        assert registry.get("deepseek") is None
        assert isinstance(registry.get("anthropic"), AnthropicProvider)
        assert isinstance(registry.get("openai"), OpenAIProvider)

    def test_enabled_without_key_falls_back(self, isolated_home: Path) -> None:
        """enabled 但 key 不可解析 (env 缺失, 假 key 未注入) → selected None → legacy。"""
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )

        registry = _cli._provider_registry()
        assert registry.ids() == _legacy_ids()
        assert registry.get("deepseek") is None

    def test_all_disabled_falls_back(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全 disabled (即使 key 可解析) → selected None → legacy。"""
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": False, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-disabled")

        registry = _cli._provider_registry()
        assert registry.ids() == _legacy_ids()


# ------------------------------------------------------------------ C: 异常安全


class TestFailsafe:
    """C 验收: ControlPlane 不可用 → 回退不抛。"""

    def test_control_plane_import_failure_falls_back(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """factory-console import 失败 (生产 console script 无仓库根 PYTHONPATH) → 回退。"""

        def _boom(name: str, package: str | None = None) -> Any:
            raise ImportError(f"simulated import failure: {name}")

        monkeypatch.setattr(importlib, "import_module", _boom)
        registry = _cli._provider_registry()  # 不抛
        assert registry.ids() == _legacy_ids()

    def test_corrupt_providers_file_falls_back(self, isolated_home: Path) -> None:
        """providers.json 损坏 (CorruptProviderFileError) → 回退不抛。"""
        path = seed_providers(isolated_home, {"deepseek": {"enabled": True}})
        path.write_text("{broken!!", encoding="utf-8")

        registry = _cli._provider_registry()  # 不抛
        assert registry.ids() == _legacy_ids()
