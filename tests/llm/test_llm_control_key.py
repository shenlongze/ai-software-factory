"""tests/llm/test_llm_control_key.py — S10-021 Phase 1: api_key_ref 解析与脱敏。

覆盖 (全 hermetic, tmp_path 隔离):
- env:VAR 从注入 environ 解析 (进程 env 优先)
- .env 兜底 (ConfigProvider 注入 env_file; 进程 env > .env)
- 无 ref → 空串; VAR 缺失 → 空串; 未知 provider → 空串
- ollama 无 key: resolve_api_key "" 但 any_enabled_with_key True (本地可用)
- any_enabled_with_key 四场景 (空配置 False / enabled+key True / enabled 无 key
  False / ollama True) + disabled 不计数
- selected_provider_id / select 装配决策 (source=control-plane, Router 预留参数)
- resolve_runtime_config 契约 (provider/model/base_url/api_key/key_env/费率;
  metadata 费率优先, 内置默认兜底)
- logger 永不输出 key 本体 (caplog 断言 — D8 脱敏铁律)

basename 全仓库唯一; sys.path 挂仓库根 (含连字符包名, importlib 导入)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录
    sys.path.insert(0, str(_ROOT))

_llm = importlib.import_module("factory-console.llm_control")
_config = importlib.import_module("factory-console.config")


def make_plane(
    tmp_path: Path,
    *,
    environ: dict[str, str] | None = None,
    config: Any | None = None,
    providers: dict[str, dict[str, Any]] | None = None,
) -> Any:
    """hermetic LLMControlPlane + 可选 providers 种子 (经 set_config 走真实写入路径)。"""
    plane = _llm.LLMControlPlane(
        providers_file=tmp_path / "providers.json",
        environ=environ or {},
        config=config,
    )
    if providers is not None:
        for pid, cfg in providers.items():
            plane.set_config(pid, **cfg)
    return plane


def make_config(tmp_path: Path, env_text: str) -> Any:
    """hermetic ConfigProvider: .env 指向 tmp (.env 兜底层数据源)。"""
    env_path = tmp_path / ".env"
    env_path.write_text(env_text, encoding="utf-8")
    return _config.ConfigProvider(
        env_file=env_path, user_config_file=tmp_path / "config.json", environ={}
    )


# ------------------------------------------------------------------ resolve_api_key


class TestResolveApiKey:
    """api_key_ref "env:VAR" → 进程 env → .env → 空串 (D3/D4 语义)。"""

    def test_env_var_from_injected_environ(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-dd-123"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.resolve_api_key("deepseek") == "sk-dd-123"

    def test_env_file_fallback(self, tmp_path: Path) -> None:
        """进程 env 缺失 → .env 兜底 (经 ConfigProvider 注入 env_file)。"""
        cfg = make_config(tmp_path, "DEEPSEEK_API_KEY=sk-from-file\n")
        plane = make_plane(
            tmp_path,
            config=cfg,
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.resolve_api_key("deepseek") == "sk-from-file"

    def test_process_env_precedence_over_env_file(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, "DEEPSEEK_API_KEY=sk-from-file\n")
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-proc"},
            config=cfg,
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.resolve_api_key("deepseek") == "sk-proc"

    def test_no_ref_returns_empty(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path, providers={"deepseek": {"enabled": True}})
        assert plane.resolve_api_key("deepseek") == ""

    def test_missing_var_returns_empty(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:NOPE_API_KEY"}},
        )
        assert plane.resolve_api_key("deepseek") == ""

    def test_unknown_provider_returns_empty(self, tmp_path: Path) -> None:
        assert make_plane(tmp_path).resolve_api_key("nope") == ""

    def test_ollama_no_key(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path, providers={"ollama": {"enabled": True}})
        assert plane.resolve_api_key("ollama") == ""


# ------------------------------------------------------------------ any_enabled_with_key


class TestAnyEnabledWithKey:
    """B 验收核心: 空→False / enabled+key→True / enabled 无 key→False / ollama→True。"""

    def test_empty_config_false(self, tmp_path: Path) -> None:
        assert make_plane(tmp_path).any_enabled_with_key() is False

    def test_enabled_with_key_true(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-x"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.any_enabled_with_key() is True

    def test_enabled_without_key_false(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.any_enabled_with_key() is False

    def test_enabled_ollama_true(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path, providers={"ollama": {"enabled": True}})
        assert plane.any_enabled_with_key() is True

    def test_disabled_provider_not_counted(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-x"},
            providers={"deepseek": {"enabled": False, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        assert plane.any_enabled_with_key() is False


# ------------------------------------------------------------------ 装配决策


class TestSelection:
    """selected_provider_id / select: 第一个 enabled + key 可解析 (ollama 含)。"""

    def test_selected_none_when_empty(self, tmp_path: Path) -> None:
        assert make_plane(tmp_path).selected_provider_id() is None

    def test_selected_first_enabled_with_key(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"OPENAI_API_KEY": "sk-o", "DEEPSEEK_API_KEY": "sk-d"},
            providers={
                "openai": {"enabled": True, "api_key_ref": "env:OPENAI_API_KEY"},
                "deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"},
            },
        )
        assert plane.selected_provider_id() == "openai"  # 第一个 enabled

    def test_selected_skips_enabled_without_key(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-d"},
            providers={
                "openai": {"enabled": True, "api_key_ref": "env:OPENAI_API_KEY"},
                "deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"},
            },
        )
        assert plane.selected_provider_id() == "deepseek"  # openai 无 key → 跳过

    def test_select_returns_provider_selection(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-d"},
            providers={
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro", "deepseek-reasoner"],
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                }
            },
        )
        sel = plane.select()
        assert sel is not None
        assert sel.provider_id == "deepseek"
        assert sel.model_id == "deepseek-v4-pro"  # models[0] 默认
        assert sel.source == "control-plane"
        assert sel.score is None

    def test_select_none_when_nothing_usable(self, tmp_path: Path) -> None:
        assert make_plane(tmp_path).select() is None

    def test_select_accepts_router_reserved_args(self, tmp_path: Path) -> None:
        """task_type/required_capabilities 为 Router 预留参数 (签名兼容)。"""
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-d"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        sel = plane.select(task_type="coding", required_capabilities=["code"])
        assert sel is not None
        assert sel.provider_id == "deepseek"

    def test_select_ollama(self, tmp_path: Path) -> None:
        plane = make_plane(tmp_path, providers={"ollama": {"enabled": True}})
        sel = plane.select()
        assert sel is not None
        assert sel.provider_id == "ollama"


# ------------------------------------------------------------------ resolve_runtime_config


class TestResolveRuntimeConfig:
    """ControlPlane → workflow_runner 装配契约 (C 验收数据源)。"""

    def test_contract_shape_from_providers_json(self, tmp_path: Path) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-x"},
            providers={
                "deepseek": {
                    "enabled": True,
                    "models": ["deepseek-v4-pro"],
                    "base_url": "https://custom.example.com/v1/chat/completions",
                    "api_key_ref": "env:DEEPSEEK_API_KEY",
                    "metadata": {"input_rate_per_1k": 0.001, "output_rate_per_1k": 0.002},
                }
            },
        )
        cfg = plane.resolve_runtime_config("deepseek")
        assert cfg is not None
        assert cfg["provider"] == "deepseek"
        assert cfg["model"] == "deepseek-v4-pro"
        assert cfg["base_url"] == "https://custom.example.com/v1/chat/completions"
        assert cfg["api_key"] == "sk-x"
        assert cfg["key_env"] == "OPENAI_API_KEY"  # deepseek 默认注入目标
        assert cfg["input_rate_per_1k"] == 0.001  # metadata 费率优先
        assert cfg["output_rate_per_1k"] == 0.002

    def test_builtin_defaults_fallback(self, tmp_path: Path) -> None:
        """base_url/models 未配 → PROVIDER_DEFAULTS 内置默认 (D4 最底层)。"""
        plane = make_plane(tmp_path, providers={"deepseek": {"enabled": True}})
        cfg = plane.resolve_runtime_config("deepseek")
        assert cfg is not None
        assert cfg["model"] == "deepseek-v4-pro"
        assert cfg["base_url"] == "https://api.deepseek.com/v1/chat/completions"
        assert cfg["api_key"] == ""
        assert cfg["input_rate_per_1k"] == 0.00028
        assert cfg["output_rate_per_1k"] == 0.00042

    def test_unknown_provider_none(self, tmp_path: Path) -> None:
        assert make_plane(tmp_path).resolve_runtime_config("nope") is None


# ------------------------------------------------------------------ 脱敏铁律


class TestKeyNeverInLogs:
    """D8: key 本体永不入 logger — 只输出 ref / configured=True|False。"""

    def test_resolve_logs_ref_not_key(self, tmp_path: Path, caplog) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-super-secret-abc"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        with caplog.at_level("DEBUG", logger="factory.llm_control"):
            key = plane.resolve_api_key("deepseek")
        assert key == "sk-super-secret-abc"
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "sk-super-secret-abc" not in text  # key 本体零输出
        assert "env:DEEPSEEK_API_KEY" in text  # ref 可输出

    def test_any_enabled_logs_no_key(self, tmp_path: Path, caplog) -> None:
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-hidden-xyz"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        with caplog.at_level("DEBUG", logger="factory.llm_control"):
            assert plane.any_enabled_with_key() is True
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "sk-hidden-xyz" not in text
        assert "configured=True" in text

    def test_runtime_config_contains_key_but_logs_do_not(self, tmp_path: Path, caplog) -> None:
        """装配契约 dict 内必须有 key (供注入), 但日志/落盘文件均无明文。"""
        plane = make_plane(
            tmp_path,
            environ={"DEEPSEEK_API_KEY": "sk-confidential-777"},
            providers={"deepseek": {"enabled": True, "api_key_ref": "env:DEEPSEEK_API_KEY"}},
        )
        with caplog.at_level("DEBUG", logger="factory.llm_control"):
            cfg = plane.resolve_runtime_config("deepseek")
        assert cfg is not None
        assert cfg["api_key"] == "sk-confidential-777"  # 内存契约可解析
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "sk-confidential-777" not in text
        # 落盘文件只存引用
        disk = (tmp_path / "providers.json").read_text(encoding="utf-8")
        assert "sk-confidential-777" not in disk
        assert "env:DEEPSEEK_API_KEY" in disk
