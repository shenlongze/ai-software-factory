"""tests/llm/test_llm_router_binding.py — S10-024 Router v1.1: workflow_runner 接线。

覆盖 (全 hermetic: HOME 隔离 + get_config 注入 + _ROUTER_CONTEXT 清理):
- E 验收: _resolve_llm_config() 返回 Router 决策结果 (L2 agent 策略 / L1 explicit)
- F 验收: 无任何配置时行为与 S10-021 一致 (ControlPlane 第一个 enabled);
  无 providers.json → get_llm() 旧路径 (回归保护)
- set_router_context() 注入上下文; None 值忽略; _router_context() 快照过滤
- Router 异常/未命中 → get_llm() 兜底 (失败安全, 行为兼容)

basename 全仓库唯一; sys.path 挂仓库根 + factory-exec (exec.providers.* 延迟导入)。
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
_FACTORY_EXEC = _ROOT / "factory-exec"  # exec 包父目录 (factory-exec/exec/)
if str(_FACTORY_EXEC) not in sys.path:
    sys.path.insert(0, str(_FACTORY_EXEC))

_config = importlib.import_module("factory-console.config")
_runner = importlib.import_module("factory-console.workflow_runner")

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
def _clean_env_and_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """清空 LLM 环境变量 + Router 接线上下文 (防跨测试泄漏)。"""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(_runner, "_ROUTER_CONTEXT", {})
    yield


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME → 临时目录: ControlPlane/AgentPolicyStore 默认路径全隔离。"""
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
    """写 <home>/.factory/providers.json (ControlPlane 默认路径)。"""
    path = home / ".factory" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "providers": {}}
    for pid, cfg in providers.items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_agent_yaml(home: Path, agent_id: str, text: str) -> Path:
    """写 <home>/.factory/agents/<agent_id>/agent.yaml (AgentPolicyStore 默认路径)。"""
    path = home / ".factory" / "agents" / agent_id / "agent.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_project_yaml(project_dir: Path, text: str) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "project.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ E: 接线生效


class TestBindingRouterDecision:
    """E 验收: _resolve_llm_config() 返回 Router 决策结果。"""

    def test_agent_policy_decision_flows_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """L2 agent 策略命中 → _resolve_llm_config 返回其 model (非 providers 默认)。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        write_agent_yaml(
            isolated_home,
            "backend-1",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-reasoner\n      provider: deepseek\n",
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(agent_id="backend-1")

        cfg = _runner._resolve_llm_config()

        assert cfg["provider"] == "deepseek"
        assert cfg["model"] == "deepseek-reasoner"  # Router L2 决策覆盖 providers 默认
        assert cfg["api_key"] == "sk-test"

    def test_explicit_decision_flows_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """L1 explicit 决策 → _resolve_llm_config 返回其 model。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(explicit_provider="deepseek", explicit_model="deepseek-reasoner")

        cfg = _runner._resolve_llm_config()

        assert cfg["model"] == "deepseek-reasoner"
        assert cfg["provider"] == "deepseek"

    def test_project_rule_decision_flows_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """L3 project 规则命中 → _resolve_llm_config 返回其 model。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        project_dir = tmp_path / "project"
        write_project_yaml(
            project_dir,
            "llm:\n  routing:\n    default:\n      provider: deepseek\n      model: deepseek-reasoner\n",
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(project_dir=str(project_dir))

        cfg = _runner._resolve_llm_config()

        assert cfg["model"] == "deepseek-reasoner"
        assert cfg["provider"] == "deepseek"

    def test_router_context_none_values_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """set_router_context(None) 不覆盖上下文; 快照只传 route() 认识的关键字。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        write_agent_yaml(
            isolated_home,
            "backend-1",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-reasoner\n      provider: deepseek\n",
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(agent_id="backend-1")
        _runner.set_router_context(agent_id=None, unknown_key="junk")  # None 忽略 + 未知键

        ctx = _runner._router_context()

        assert ctx == {"agent_id": "backend-1"}  # 未知键/None 均不入快照

        cfg = _runner._resolve_llm_config()
        assert cfg["model"] == "deepseek-reasoner"


# ------------------------------------------------------------------ F: fallback 兼容 (S10-021 一致)


class TestBindingFallbackCompat:
    """F 验收: 无配置/无上下文时行为与 S10-021 完全一致。"""

    def test_no_context_fallback_first_enabled_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无 Router 上下文 → L5 fallback = ControlPlane 第一个 enabled+key。"""
        seed_providers(
            isolated_home,
            {
                "ollama": {"enabled": True, "models": ["qwen2.5:14b"]},
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                },
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        patch_runner_config(monkeypatch, make_config(tmp_path))

        cfg = _runner._resolve_llm_config()

        assert cfg["provider"] == "ollama"  # 第一个 enabled (无 key 也算可用)
        assert cfg["model"] == "qwen2.5:14b"

    def test_fallback_same_as_s10_021_selected_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """与 S10-021 等价: 返回 selected_provider_id → resolve_runtime_config。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "base_url": "https://llm.example.com/v1/chat/completions",
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        patch_runner_config(monkeypatch, make_config(tmp_path))

        plane = _runner._control_plane()
        expected = plane.resolve_runtime_config(plane.selected_provider_id())

        cfg = _runner._resolve_llm_config()

        assert cfg == expected  # 无上下文时 Router L5 == S10-021 直连结果

    def test_no_providers_fallback_to_get_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无 providers.json → get_llm() 旧路径 (回归保护, 与 S10-007 一致)。"""
        patch_runner_config(monkeypatch, make_config(tmp_path))

        cfg = _runner._resolve_llm_config()

        assert cfg["provider"] == "deepseek"  # PROVIDER_DEFAULTS 默认
        assert cfg["model"] == "deepseek-v4-pro"

    def test_router_raise_falls_back_to_get_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """Router 异常 (L1 响亮错误) → 接线层兜底 get_llm() (失败安全)。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(explicit_provider="ghost-provider")  # L1 会响亮报错

        cfg = _runner._resolve_llm_config()  # 不抛异常

        assert cfg["provider"] == "deepseek"  # get_llm() 兜底 (PROVIDER_DEFAULTS)
        assert cfg["model"] == "deepseek-v4-pro"  # 默认模型 — 未走 providers.json

    def test_control_plane_missing_falls_back_to_get_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无任何 enabled provider → Router None → get_llm() 兜底。"""
        seed_providers(
            isolated_home,
            {"deepseek": {"enabled": False, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))

        cfg = _runner._resolve_llm_config()

        assert cfg["provider"] == "deepseek"  # get_llm() 默认
        assert cfg["model"] == "deepseek-v4-pro"


# ------------------------------------------------------------------ 冒烟: _build_provider 全链


class TestBindingBuildProviderSmoke:
    """接线冒烟: Router 决策 → _build_provider 装配真实 Provider。"""

    def test_build_provider_uses_router_agent_decision(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """agent 策略指定 deepseek-reasoner → OpenAIProvider 用该 model。"""
        seed_providers(
            isolated_home,
            {
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-chat"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        write_agent_yaml(
            isolated_home,
            "backend-1",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-reasoner\n      provider: deepseek\n",
        )
        patch_runner_config(monkeypatch, make_config(tmp_path))
        _runner.set_router_context(agent_id="backend-1")

        from exec.providers.openai import OpenAIProvider

        wrapper = _runner._build_provider(None)
        inner = wrapper._inner

        assert isinstance(inner, OpenAIProvider)
        assert inner._model == "deepseek-reasoner"  # Router L2 决策 → Provider
