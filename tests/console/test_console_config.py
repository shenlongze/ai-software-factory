"""tests/console/test_console_config.py — S10-007 阶段一 配置层 (ConfigProvider) 测试。

覆盖 (factory-console/config.py + workflow_runner.py 解耦):
- 优先级: 进程 env > 项目 .env > 用户级 ~/.factory/config.json > 默认值
- API key: 从 .env 读 (无 ~/.hermes 依赖 — HOME 隔离验证); env:VAR 引用解析
  (进程环境 / .env 内变量); provider 专属环境变量兜底; OPENAI_API_KEY 兼容兜底
- provider 映射: deepseek/openai/anthropic/ollama 默认 model/base_url/key_env
  + LLM_MODEL/LLM_BASE_URL 显式覆盖 + 未知 provider 失败安全降级
- 失败安全: config.json 损坏 / .env 非法行 / 非法端口 → 默认值 + 响亮日志
- workflow_runner: has_llm_key 在纯配置环境 (无 ~/.hermes) 为 true;
  load_llm_key 按 provider 注入 (deepseek→OPENAI_API_KEY / anthropic→
  ANTHROPIC_API_KEY / ollama 无 key); 无 key → false; 进程环境 OPENAI_API_KEY
  向后兼容优先

basename 全仓库唯一 (test_console_* 前缀 — tests/console 惯例); 全部 hermetic
(显式注入 env_file/user_config_file/environ, 不依赖真实进程环境/用户配置)。
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
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_config = importlib.import_module("factory-console.config")
_runner = importlib.import_module("factory-console.workflow_runner")

#: 可能干扰的进程环境变量 (hermetic 测试前清空)
_ENV_KEYS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "DATA_DIR",
    "PORT",
    "FRONTEND_PORT",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """清空相关进程环境变量 (hermetic — 不依赖开发者机器 env)。

    同时快照/还原 load_llm_key 注入的 OPENAI_API_KEY/ANTHROPIC_API_KEY
    (测试体内直接写 os.environ, monkeypatch 无法 undo — 防跨测试模块泄漏)。
    """
    snapshot = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY")}
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    for key, val in snapshot.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def make_provider(
    tmp_path: Path,
    *,
    env_file: str = "",
    user_config: dict | None = None,
    environ: dict[str, str] | None = None,
) -> Any:
    """hermetic ConfigProvider: .env / 用户 config.json / 环境变量全注入。"""
    env_path = tmp_path / ".env"
    env_path.write_text(env_file, encoding="utf-8")
    user_path = tmp_path / "config.json"
    if user_config is not None:
        user_path.write_text(json.dumps(user_config), encoding="utf-8")
    return _config.ConfigProvider(
        env_file=env_path,
        user_config_file=user_path,
        environ=environ or {},
    )


# ------------------------------------------------------------------ 优先级


class TestPriority:
    """env > 项目 .env > 用户 config.json > 默认值 (逐 key 合并)。"""

    def test_env_overrides_env_file(self, tmp_path: Path) -> None:
        """进程环境 > 项目 .env (同 key)。"""
        cfg = make_provider(
            tmp_path, env_file="LLM_MODEL=file-model\n", environ={"LLM_MODEL": "env-model"}
        )
        assert cfg.get("llm", "model") == "env-model"

    def test_env_file_overrides_user_config(self, tmp_path: Path) -> None:
        """项目 .env > 用户 config.json (同 key)。"""
        cfg = make_provider(
            tmp_path,
            env_file="LLM_MODEL=file-model\n",
            user_config={"llm": {"model": "user-model"}},
        )
        assert cfg.get("llm", "model") == "file-model"

    def test_user_config_overrides_defaults(self, tmp_path: Path) -> None:
        """用户 config.json > 默认值。"""
        cfg = make_provider(tmp_path, user_config={"llm": {"model": "user-model"}})
        assert cfg.get("llm", "model") == "user-model"
        assert cfg.get_llm()["model"] == "user-model"

    def test_defaults_fully_unconfigured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全空配置 → 默认值 (provider=deepseek / data_dir=~/.factory / 端口)。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = make_provider(tmp_path)
        llm = cfg.get_llm()
        assert llm["provider"] == "deepseek"
        assert llm["model"] == "deepseek-v4-pro"
        assert llm["base_url"] == "https://api.deepseek.com/v1/chat/completions"
        assert llm["api_key"] == ""
        assert cfg.get_data_dir() == tmp_path / ".factory"
        assert cfg.get_port() == 8011
        assert cfg.get_frontend_port() == 5180

    def test_data_dir_and_ports_overridable(self, tmp_path: Path) -> None:
        """DATA_DIR/PORT/FRONTEND_PORT 分层可配 (env 层)。"""
        cfg = make_provider(
            tmp_path,
            environ={"DATA_DIR": "~/my-factory", "PORT": "9000", "FRONTEND_PORT": "6000"},
        )
        assert cfg.get_data_dir() == Path("~/my-factory").expanduser()
        assert cfg.get_port() == 9000
        assert cfg.get_frontend_port() == 6000


# ------------------------------------------------------------------ API key


class TestApiKey:
    """key 解析: .env 直读 / env:VAR 引用 / provider 环境变量兜底 (无 ~/.hermes)。"""

    def test_api_key_from_env_file_no_hermes_dependency(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """key 从项目 .env 读 — HOME 指向全新临时目录 (不可能存在 ~/.hermes)。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = make_provider(tmp_path, env_file="LLM_API_KEY=sk-test-123\n")
        llm = cfg.get_llm()
        assert llm["api_key"] == "sk-test-123"
        assert llm["provider"] == "deepseek"
        assert not (tmp_path / ".hermes").exists()  # 干净环境无 Hermes 路径

    def test_api_key_env_var_reference_from_process_env(self, tmp_path: Path) -> None:
        """LLM_API_KEY=env:DEEPSEEK_API_KEY → 从进程环境解析。"""
        cfg = make_provider(
            tmp_path,
            environ={"LLM_API_KEY": "env:DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY": "sk-dd"},
        )
        assert cfg.get_llm()["api_key"] == "sk-dd"

    def test_api_key_env_var_reference_from_env_file(self, tmp_path: Path) -> None:
        """env:VAR 引用 → .env 文件内的变量也可被引用。"""
        cfg = make_provider(
            tmp_path,
            env_file="DEEPSEEK_API_KEY=sk-file\nLLM_API_KEY=env:DEEPSEEK_API_KEY\n",
        )
        assert cfg.get_llm()["api_key"] == "sk-file"

    def test_api_key_env_var_reference_missing_var_is_empty(self, tmp_path: Path) -> None:
        """env:VAR 引用的变量缺失 → 诚实空 key (不臆造)。"""
        cfg = make_provider(tmp_path, environ={"LLM_API_KEY": "env:NOPE_API_KEY"})
        assert cfg.get_llm()["api_key"] == ""

    def test_api_key_provider_env_fallback(self, tmp_path: Path) -> None:
        """未配 LLM_API_KEY → provider 专属环境变量兜底 (deepseek→DEEPSEEK_API_KEY)。"""
        cfg = make_provider(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-dd"})
        assert cfg.get_llm()["api_key"] == "sk-dd"

    def test_api_key_openai_env_backward_compat(self, tmp_path: Path) -> None:
        """未配任何 LLM key → OPENAI_API_KEY 兜底 (历史 Hermes 注入目标, 开发兼容)。"""
        cfg = make_provider(tmp_path, environ={"OPENAI_API_KEY": "sk-legacy"})
        assert cfg.get_llm()["api_key"] == "sk-legacy"


# ------------------------------------------------------------------ provider 映射


class TestProviderMapping:
    """多 Provider 默认映射表 (deepseek/openai/anthropic/ollama) — 不写死 DeepSeek。"""

    def test_deepseek_defaults(self, tmp_path: Path) -> None:
        llm = make_provider(tmp_path).get_llm()
        assert llm["provider"] == "deepseek"
        assert llm["model"] == "deepseek-v4-pro"
        assert llm["base_url"] == "https://api.deepseek.com/v1/chat/completions"
        assert llm["key_env"] == "OPENAI_API_KEY"  # OpenAI 兼容端点注入

    def test_openai_defaults(self, tmp_path: Path) -> None:
        llm = make_provider(tmp_path, environ={"LLM_PROVIDER": "openai"}).get_llm()
        assert llm["provider"] == "openai"
        assert llm["model"] == "gpt-4o"
        assert llm["base_url"] == "https://api.openai.com/v1/chat/completions"
        assert llm["key_env"] == "OPENAI_API_KEY"

    def test_anthropic_defaults(self, tmp_path: Path) -> None:
        llm = make_provider(tmp_path, environ={"LLM_PROVIDER": "anthropic"}).get_llm()
        assert llm["provider"] == "anthropic"
        assert llm["model"] == "claude-sonnet-4-20250514"
        assert llm["base_url"] == "https://api.anthropic.com/v1/messages"
        assert llm["key_env"] == "ANTHROPIC_API_KEY"

    def test_ollama_defaults(self, tmp_path: Path) -> None:
        llm = make_provider(tmp_path, environ={"LLM_PROVIDER": "ollama"}).get_llm()
        assert llm["provider"] == "ollama"
        assert llm["model"] == "qwen2.5:14b"
        assert llm["base_url"] == "http://127.0.0.1:11434/v1/chat/completions"
        assert llm["key_env"] is None  # 本地无 key
        assert llm["api_key"] == ""

    def test_model_and_base_url_overrides(self, tmp_path: Path) -> None:
        """LLM_MODEL/LLM_BASE_URL 显式覆盖 provider 默认 (本地 Ollama 可配)。"""
        llm = make_provider(
            tmp_path,
            environ={
                "LLM_PROVIDER": "ollama",
                "LLM_MODEL": "llama3.1:8b",
                "LLM_BASE_URL": "http://127.0.0.1:11435/v1/chat/completions",
            },
        ).get_llm()
        assert llm["provider"] == "ollama"
        assert llm["model"] == "llama3.1:8b"
        assert llm["base_url"] == "http://127.0.0.1:11435/v1/chat/completions"

    def test_unknown_provider_falls_back_to_deepseek(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """未知 provider → 响亮警告 + 降级 deepseek 默认映射 (失败安全)。"""
        with caplog.at_level("WARNING", logger="factory.config"):
            llm = make_provider(tmp_path, environ={"LLM_PROVIDER": "not-a-provider"}).get_llm()
        assert llm["provider"] == "deepseek"
        assert llm["model"] == "deepseek-v4-pro"
        assert any("未知 LLM provider" in r.message for r in caplog.records)


# ------------------------------------------------------------------ 失败安全


class TestFailureSafe:
    """配置损坏 → 默认值 + 响亮日志 (绝不抛异常拖垮启动)。"""

    def test_corrupted_user_config_ignored(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """config.json 非法 JSON → 忽略 + 警告 + 默认值。"""
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")
        user_path = tmp_path / "config.json"
        user_path.write_text("{not valid json!!", encoding="utf-8")
        with caplog.at_level("WARNING", logger="factory.config"):
            cfg = _config.ConfigProvider(env_file=env_path, user_config_file=user_path, environ={})
        assert cfg.get_llm()["provider"] == "deepseek"
        assert cfg.get_port() == 8011
        assert any("损坏" in r.message for r in caplog.records)

    def test_user_config_non_dict_ignored(self, tmp_path: Path) -> None:
        """config.json 顶层非对象 → 忽略 + 默认值。"""
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")
        user_path = tmp_path / "config.json"
        user_path.write_text("[1, 2, 3]", encoding="utf-8")
        cfg = _config.ConfigProvider(env_file=env_path, user_config_file=user_path, environ={})
        assert cfg.get_llm()["provider"] == "deepseek"

    def test_invalid_env_file_line_ignored(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """.env 非法行 → 响亮忽略, 合法行仍生效。"""
        with caplog.at_level("WARNING", logger="factory.config"):
            cfg = make_provider(
                tmp_path,
                env_file="garbage line without equals sign\nLLM_MODEL=ok-model\n# 注释\n",
            )
        assert cfg.get("llm", "model") == "ok-model"
        assert any("非法 .env 行" in r.message for r in caplog.records)

    def test_invalid_port_falls_back_to_default(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """非法端口值 → 默认 8011 + 警告 (失败安全)。"""
        with caplog.at_level("WARNING", logger="factory.config"):
            cfg = make_provider(tmp_path, environ={"PORT": "not-a-port"})
        assert cfg.get_port() == 8011
        assert any("非法整型值" in r.message for r in caplog.records)


# ------------------------------------------------------------------ workflow_runner 解耦


class TestWorkflowRunnerDecoupled:
    """has_llm_key/load_llm_key 走 ConfigProvider — 无 ~/.hermes 依赖 (S10-007 P0)。"""

    @pytest.fixture
    def isolated_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """HOME → 全新临时目录 (干净环境: 不可能存在 ~/.hermes/.env)。"""
        home = tmp_path / "isolated-home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        return home

    def _patch_runner_config(self, monkeypatch: pytest.MonkeyPatch, provider) -> None:
        """workflow_runner 的 get_config 单例 → hermetic 注入。"""
        monkeypatch.setattr(_runner, "get_config", lambda: provider)

    def test_has_llm_key_true_with_config_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """干净环境 (HOME 隔离, 无 ~/.hermes) + 项目 .env 配 key → has_llm_key True。"""
        provider = make_provider(tmp_path, env_file="LLM_API_KEY=sk-clean-env\n")
        self._patch_runner_config(monkeypatch, provider)
        assert not (isolated_home / ".hermes").exists()
        assert _runner.has_llm_key() is True

    def test_has_llm_key_false_without_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """无任何 key 配置 → has_llm_key False (诚实 503 依据)。"""
        provider = make_provider(tmp_path)
        self._patch_runner_config(monkeypatch, provider)
        assert _runner.has_llm_key() is False

    def test_load_llm_key_injects_openai_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """deepseek provider → key 注入 OPENAI_API_KEY (OpenAI 兼容端点转换)。"""
        provider = make_provider(tmp_path, env_file="LLM_API_KEY=sk-deepseek-test\n")
        self._patch_runner_config(monkeypatch, provider)
        assert _runner.load_llm_key() == "sk-deepseek-test"
        assert _runner.os.environ["OPENAI_API_KEY"] == "sk-deepseek-test"

    def test_load_llm_key_anthropic_injects_anthropic_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """anthropic provider → key 注入 ANTHROPIC_API_KEY (不注入 OPENAI_API_KEY)。"""
        provider = make_provider(
            tmp_path,
            env_file="LLM_PROVIDER=anthropic\nLLM_API_KEY=sk-ant-test\n",
        )
        self._patch_runner_config(monkeypatch, provider)
        assert _runner.load_llm_key() == "sk-ant-test"
        assert _runner.os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"
        assert "OPENAI_API_KEY" not in _runner.os.environ

    def test_has_llm_key_true_for_ollama_without_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """ollama 本地模型无需 key → has_llm_key True (配置 provider 即可启动)。"""
        provider = make_provider(tmp_path, environ={"LLM_PROVIDER": "ollama"})
        self._patch_runner_config(monkeypatch, provider)
        assert provider.get_llm()["api_key"] == ""
        assert _runner.has_llm_key() is True

    def test_has_llm_key_process_env_openai_priority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_home: Path
    ) -> None:
        """向后兼容: 进程环境 OPENAI_API_KEY 仍优先 (Hermes 曾注入的部署形态)。"""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-process-env")
        provider = make_provider(tmp_path)  # 无任何配置 key
        self._patch_runner_config(monkeypatch, provider)
        assert provider.get_llm()["api_key"] == ""
        assert _runner.has_llm_key() is True

    def test_runner_source_has_no_hermes_env_read(
        self, isolated_home: Path
    ) -> None:
        """静态守卫: 源码不再含旧 ~/.hermes/.env 的读取代码形态 (Path.home() 直拼)。

        docstring 提及历史路径做兼容说明不算 — 守卫只查读取代码形态。
        """
        for mod in (_runner, _config):
            assert mod.__file__ is not None
            src = Path(mod.__file__).read_text(encoding="utf-8")
            assert 'Path.home() / ".hermes"' not in src, f"{mod.__name__} 仍直读 Hermes 路径"
            assert '"/.hermes"' not in src, f"{mod.__name__} 仍直读 Hermes 路径"
