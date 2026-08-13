"""tests/llm/test_llm_control_runtime_binding.py — S10-021 Phase 1: workflow_runner 接线。

覆盖 (全 hermetic: HOME 隔离 + get_config 注入, 不写真实 ~/.factory):
- has_llm_key 四场景 (B 验收): 空配置 False / enabled+key_ref+env True /
  enabled 无 key False / ollama True; OPENAI_API_KEY 向后兼容优先
- load_llm_key 从 providers.json 注入 OPENAI_API_KEY (deepseek → OpenAI 兼容
  注入目标); ollama 不注入
- _build_provider (C 验收): 返回 OpenAIProvider 实例且 model/base_url 来自
  providers.json; 无 providers.json → get_llm() 旧路径 (回归保护);
  ollama 占位 key; anthropic → AnthropicProvider
- 冒烟 (C 验收): service.ConsoleService._self_assemble_runtime() 非 None —
  providers.json → ControlPlane → workflow_runner → Provider → AgentRuntime
  真实装配链

basename 全仓库唯一; sys.path 挂仓库根 + factory-core + factory-exec
(exec 包父目录 — _build_provider 内 exec.providers.* 延迟导入需要)。
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

_config = importlib.import_module("factory-console.config")
_runner = importlib.import_module("factory-console.workflow_runner")

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
    """清空相关进程环境变量 + 快照/还原 load_llm_key 注入目标 (防跨测试泄漏)。"""
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


def make_config(tmp_path: Path, environ: dict[str, str] | None = None) -> Any:
    """hermetic ConfigProvider (旧路径 get_llm() 数据源; 空 .env / 空用户配置)。"""
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    return _config.ConfigProvider(
        env_file=env_path,
        user_config_file=tmp_path / "config.json",
        environ=environ or {},
    )


def patch_runner_config(monkeypatch: pytest.MonkeyPatch, config: Any) -> None:
    """workflow_runner 的 get_config 单例 → hermetic 注入 (同 tests/console 模式)。"""
    monkeypatch.setattr(_runner, "get_config", lambda: config)


def seed_providers(home: Path, providers: dict[str, dict[str, Any]]) -> Path:
    """写 <home>/.factory/providers.json (默认路径 — has_llm_key/_build_provider 读取点)。"""
    path = home / ".factory" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "providers": {}}
    for pid, cfg in providers.items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ------------------------------------------------------------------ has_llm_key


class TestHasLlmKey:
    """B 验收: has_llm_key() 正确判断配置状态。"""

    def test_empty_config_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """空配置 (无 providers.json / 无 env key) → False。"""
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is False

    def test_enabled_with_key_env_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """enabled + api_key_ref + env 注入 → True。"""
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-1")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is True

    def test_enabled_without_key_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """enabled 但 key 不可解析 → False (诚实缺失)。"""
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is False

    def test_enabled_ollama_true(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """enabled 的 ollama 无 key → True (本地模型无需 key)。"""
        seed_providers(isolated_home, {"ollama": {"enabled": True}})
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is True

    def test_legacy_openai_env_still_priority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """向后兼容: 进程环境 OPENAI_API_KEY 仍优先 (无 providers.json 也 True)。"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is True

    def test_corrupt_providers_file_fails_safe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """损坏 providers.json → 管理面异常 → False (失败安全, 不阻断旧路径)。"""
        path = seed_providers(isolated_home, {"deepseek": {"enabled": True}})
        path.write_text("{broken!!", encoding="utf-8")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.has_llm_key() is False


# ------------------------------------------------------------------ load_llm_key


class TestLoadLlmKey:
    """load_llm_key: providers.json 管理面兜底注入 (D4)。"""

    def test_injects_openai_api_key_from_providers_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-inject-1")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.load_llm_key() == "sk-inject-1"
        # deepseek → OpenAI 兼容端点 → 注入 OPENAI_API_KEY
        assert os.environ["OPENAI_API_KEY"] == "sk-inject-1"

    def test_ollama_no_injection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        seed_providers(isolated_home, {"ollama": {"enabled": True}})
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.load_llm_key() == ""
        assert "OPENAI_API_KEY" not in os.environ

    def test_no_providers_file_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        patch_runner_config(monkeypatch, make_config(tmp_path))
        assert _runner.load_llm_key() == ""


# ------------------------------------------------------------------ _build_provider


class TestBuildProvider:
    """C 验收: _build_provider 真实装配 — providers.json 优先, get_llm() 兼容。"""

    def test_openai_provider_from_providers_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """model/base_url 来自 providers.json (非内置默认) → 管理面装配生效。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "base_url": "https://llm.example.com/v1/chat/completions",
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-provider-1")
        patch_runner_config(monkeypatch, make_config(tmp_path))

        from exec.providers.openai import OpenAIProvider

        wrapper = _runner._build_provider(None)
        inner = wrapper._inner
        assert isinstance(inner, OpenAIProvider)
        assert inner._model == "deepseek-v4-pro"
        assert inner._base_url == "https://llm.example.com/v1/chat/completions"

    def test_fallback_to_get_llm_without_providers_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无 providers.json → 走 get_llm() 旧路径 (回归保护, 行为与 S10-007 一致)。"""
        patch_runner_config(monkeypatch, make_config(tmp_path))

        from exec.providers.openai import OpenAIProvider

        wrapper = _runner._build_provider(None)
        inner = wrapper._inner
        assert isinstance(inner, OpenAIProvider)
        assert inner._model == "deepseek-v4-pro"  # PROVIDER_DEFAULTS 默认
        assert inner._base_url == "https://api.deepseek.com/v1/chat/completions"

    def test_ollama_placeholder_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """ollama 本地模型 → OpenAIProvider + 占位 key (不校验 Authorization)。"""
        seed_providers(
            isolated_home,
            {"ollama": {"enabled": True, "models": ["qwen2.5:14b"]}},
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))

        from exec.providers.openai import OpenAIProvider

        wrapper = _runner._build_provider(None)
        assert isinstance(wrapper._inner, OpenAIProvider)
        assert wrapper._inner._api_key == "ollama"

    def test_anthropic_provider_from_providers_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
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
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-1")
        patch_runner_config(monkeypatch, make_config(tmp_path))

        from exec.providers.anthropic import AnthropicProvider

        wrapper = _runner._build_provider(None)
        assert isinstance(wrapper._inner, AnthropicProvider)


# ------------------------------------------------------------------ 自装配冒烟


class TestSelfAssembleSmoke:
    """C 验收冒烟: service._self_assemble_runtime() 非 None (真实装配链)。"""

    def test_self_assemble_runtime_non_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """providers.json → ControlPlane → workflow_runner → Provider → AgentRuntime。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-smoke-1")
        patch_runner_config(monkeypatch, make_config(tmp_path))

        service = importlib.import_module("factory-console.service")
        runtime = service.ConsoleService()._self_assemble_runtime()
        assert runtime is not None  # 装配成功 — 不再恒 None (reality-check 缺口 3 关闭)
        assert runtime._developer is not None

    def test_self_assemble_none_without_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无已配置 key → None (诚实 FAILED 依据 — 不伪造 LLM 结果)。"""
        patch_runner_config(monkeypatch, make_config(tmp_path))
        service = importlib.import_module("factory-console.service")
        assert service.ConsoleService()._self_assemble_runtime() is None
