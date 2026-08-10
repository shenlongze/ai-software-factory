"""factory-console/config.py — AI Factory 配置 Provider (S10-007 阶段一, 配置独立化)。

用户要求 (S10-007): 禁止 Runtime 直接读 Hermes 路径; Config Provider 抽象;
未来支持 DeepSeek/OpenAI/Anthropic/本地模型 — 不写死 DeepSeek。

加载优先级 (高 → 低, 逐 key 合并):
    1. 进程环境变量 (os.environ)   — LLM_PROVIDER/LLM_MODEL/LLM_BASE_URL/
                                      LLM_API_KEY/DATA_DIR/PORT/FRONTEND_PORT
    2. 项目 .env (本目录 .env)     — 同 key 名 (KEY=VALUE; # 注释; export 前缀;
                                      引号剥离; 非法行响亮忽略)
    3. 用户级 ~/.factory/config.json — {"llm": {"provider", "model", "base_url",
                                      "api_key"}, "data_dir", "port", "frontend_port"}
    4. 默认值 (PROVIDER_DEFAULTS 映射表 + 本文件常量)

LLM 多 Provider 映射 (provider → 默认 model/base_url/费率/key 注入目标):
    deepseek | openai | anthropic | ollama (本地)。LLM_MODEL/LLM_BASE_URL/
    LLM_API_KEY 可显式覆盖 provider 默认 (env > .env > config.json > 默认)。
    未知 provider → 响亮警告 + 降级 deepseek 默认映射 (失败安全)。

API key 语义 (get_llm()["api_key"]):
    - LLM_API_KEY 支持 env:VAR 引用 (如 env:DEEPSEEK_API_KEY) — 先查进程环境,
      再查项目 .env; 缺 VAR → 空 (诚实缺失, 不臆造)。
    - 兜底链 (向后兼容): provider 专属环境变量 (deepseek → DEEPSEEK_API_KEY,
      anthropic → ANTHROPIC_API_KEY) → OPENAI_API_KEY (历史 Hermes 注入目标,
      开发环境有 ~/.hermes/.env 时经 env 注入继续可用 — 本模块自身不读它)。
    - 注入目标 key_env: deepseek/openai → OPENAI_API_KEY (OpenAI 兼容端点,
      exec.providers.openai.OpenAIProvider 读 OPENAI_API_KEY); anthropic →
      ANTHROPIC_API_KEY; ollama → None (本地无 key)。

失败安全: .env 解析失败 / config.json 损坏 / 非法端口值 → logging.warning 响亮
日志 + 降级到默认值, 绝不抛异常拖垮启动。

铁律: 本模块不读取任何 ~/.hermes 路径 (Hermes 耦合解除 — S10-007 P0)。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger("factory.config")

#: 默认数据目录 (用户级; 与 fastapi_adapter.DEFAULT_ROOT / cli.context 同口径)
DEFAULT_DATA_DIR = "~/.factory"
#: 默认后端端口 (uvicorn; 与 fastapi_adapter.DEFAULT_PORT 同口径)
DEFAULT_PORT = 8011
#: 默认前端端口 (vite dev)
DEFAULT_FRONTEND_PORT = 5180
#: 默认 provider (DeepSeek — S8-005 已验证; 仅默认值, 不写死使用方)
DEFAULT_PROVIDER = "deepseek"

#: provider → 默认 model/base_url/费率/API key 环境变量/注入目标 (多 Provider 映射表)。
#: api_key_env: 未配 LLM_API_KEY 时从进程环境兜底的变量; key_env: key 进程内
#: 注入目标 (OpenAI 兼容端点统一走 OPENAI_API_KEY; anthropic 走 ANTHROPIC_API_KEY;
#: ollama 本地无 key)。费率仅成本估算 (per 1K tokens, 非计费 — 同 S8-005)。
PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "key_env": "OPENAI_API_KEY",
        "input_rate_per_1k": 0.00028,
        "output_rate_per_1k": 0.00042,
    },
    "openai": {
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
        "key_env": "OPENAI_API_KEY",
        "input_rate_per_1k": 0.0025,
        "output_rate_per_1k": 0.01,
    },
    "anthropic": {
        "model": "claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com/v1/messages",
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_env": "ANTHROPIC_API_KEY",
        "input_rate_per_1k": 0.003,
        "output_rate_per_1k": 0.015,
    },
    "ollama": {
        "model": "qwen2.5:14b",
        "base_url": "http://127.0.0.1:11434/v1/chat/completions",
        "api_key_env": None,
        "key_env": None,
        "input_rate_per_1k": None,
        "output_rate_per_1k": None,
    },
}

#: section → 环境变量前缀 (llm.* → LLM_*; core.* → 无前缀: DATA_DIR/PORT/...)
_ENV_PREFIX: dict[str, str] = {"llm": "LLM_", "core": ""}


def _default_env_file() -> Path:
    """项目 .env = 本文件所在目录 (factory-console/) 的 .env。"""
    return Path(__file__).resolve().parent / ".env"


def _default_user_config_file() -> Path:
    """用户级配置 ~/.factory/config.json (HOME 重定向即隔离 — 冒烟/测试用)。"""
    return Path.home() / ".factory" / "config.json"


def _to_int(raw: Any, default: int) -> int:
    """端口等整型解析 (非法值 → 响亮日志 + 默认, 失败安全)。"""
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("config: 非法整型值 %r, 使用默认 %d", raw, default)
        return default


class ConfigProvider:
    """分层配置读取 (env > 项目 .env > ~/.factory/config.json > 默认值)。

    构造参数均可注入 (测试/冒烟用): env_file / user_config_file / environ。
    environ 缺省 os.environ (调用时实时读 — monkeypatch.setenv 测试可见);
    传入 dict 则完全隔离 (hermetic 测试不依赖真实进程环境)。
    """

    def __init__(
        self,
        *,
        env_file: str | Path | None = None,
        user_config_file: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._env_file = Path(env_file) if env_file is not None else _default_env_file()
        self._user_config_file = (
            Path(user_config_file) if user_config_file is not None else _default_user_config_file()
        )
        self._environ = os.environ if environ is None else environ
        self._env_values: dict[str, str] = {}
        self._user_values: dict[str, Any] = {}
        self._load_env_file()
        self._load_user_config()

    # ------------------------------------------------------------------ 加载

    def _load_env_file(self) -> None:
        """项目 .env 解析 (失败安全: 缺失/损坏 → 空 + 响亮日志, 不抛)。"""
        try:
            text = self._env_file.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — 失败安全铁律
            if isinstance(exc, OSError) and not self._env_file.exists():
                return  # 无 .env 文件 → 正常空层
            logger.warning("config: .env %s 读取失败, 忽略: %s", self._env_file, exc)
            return
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                logger.warning("config: 忽略非法 .env 行: %r", raw[:80])
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            # 引号剥离 (双/单引号包裹的带空格值)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            self._env_values[key] = value

    def _load_user_config(self) -> None:
        """~/.factory/config.json 解析 (失败安全: 损坏 → 空 + 响亮日志, 不抛)。"""
        try:
            text = self._user_config_file.read_text(encoding="utf-8")
        except OSError:
            return  # 无用户配置 → 正常空层
        except Exception as exc:  # noqa: BLE001
            logger.warning("config: 用户配置 %s 读取失败, 忽略: %s", self._user_config_file, exc)
            return
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("顶层必须是 JSON 对象")
            self._user_values = data
        except Exception as exc:  # noqa: BLE001 — 损坏兜底
            logger.warning(
                "config: 用户配置 %s 损坏, 忽略 (使用默认值): %s",
                self._user_config_file,
                exc,
            )
            self._user_values = {}

    # ------------------------------------------------------------------ 读取

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """分层取值: 进程 env > 项目 .env > 用户 config.json > default。

        section: "llm" (env 前缀 LLM_) 或 "core" (无前缀: DATA_DIR/PORT/...)。
        空串视为未配置 (逐层下落, 不阻断链)。
        """
        prefix = _ENV_PREFIX.get(section, "")
        env_key = f"{prefix}{key.upper()}"
        env_val = self._environ.get(env_key)
        if env_val is not None and env_val != "":
            return env_val
        env_file_val = self._env_values.get(env_key)
        if env_file_val is not None and env_file_val != "":
            return env_file_val
        user_val = self._user_value(section, key)
        if user_val is not None:
            return user_val
        return default

    def _user_value(self, section: str, key: str) -> Any:
        """用户 config.json 的 section.key (非 dict section / None → 未配置)。"""
        sec = self._user_values.get(section)
        if isinstance(sec, dict):
            val = sec.get(key)
            if val is not None:
                return val
        return None

    def _resolve_env_ref(self, raw: str) -> str:
        """env:VAR 引用解析: 进程环境 → 项目 .env → 空串 (缺 VAR 诚实缺失)。"""
        if not raw.startswith("env:"):
            return raw
        name = raw[4:].strip()
        if not name:
            return ""
        val = self._environ.get(name, "")
        if val:
            return val
        return self._env_values.get(name, "")

    def _resolve_api_key(self, provider_defaults: dict[str, Any]) -> str:
        """API key 解析链 (S10-007 语义):
        1. LLM_API_KEY (env > .env > config.json; 支持 env:VAR 引用)
        2. provider 专属环境变量 (deepseek → DEEPSEEK_API_KEY, 兜底)
        3. OPENAI_API_KEY (历史 Hermes 进程环境注入目标, 开发兼容)
        """
        raw = self.get("llm", "api_key", None)
        if raw:
            key = self._resolve_env_ref(str(raw))
            if key:
                return key
        api_key_env = provider_defaults.get("api_key_env")
        if api_key_env:
            key = self._environ.get(api_key_env, "")
            if key:
                return key
        return self._environ.get("OPENAI_API_KEY", "") or ""

    # ------------------------------------------------------------------ LLM

    def get_llm(self) -> dict[str, Any]:
        """LLM 配置解析 → {provider, model, base_url, api_key, key_env, 费率}。

        provider 默认映射: deepseek/openai/anthropic 各配默认 model/base_url;
        本地 ollama 可配 (LLM_MODEL/LLM_BASE_URL 显式覆盖)。未知 provider →
        响亮警告 + 降级 deepseek 默认映射 (失败安全, 不写死使用方)。
        """
        provider = str(self.get("llm", "provider", DEFAULT_PROVIDER)).strip().lower()
        defaults = PROVIDER_DEFAULTS.get(provider)
        if defaults is None:
            logger.warning(
                "config: 未知 LLM provider %r, 使用 deepseek 默认映射 (支持: %s)",
                provider,
                ", ".join(PROVIDER_DEFAULTS),
            )
            provider = DEFAULT_PROVIDER
            defaults = PROVIDER_DEFAULTS[provider]
        model = str(self.get("llm", "model", defaults["model"])).strip() or defaults["model"]
        base_url = (
            str(self.get("llm", "base_url", defaults["base_url"])).strip()
            or defaults["base_url"]
        )
        return {
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "api_key": self._resolve_api_key(defaults),
            "key_env": defaults["key_env"],
            "input_rate_per_1k": defaults.get("input_rate_per_1k"),
            "output_rate_per_1k": defaults.get("output_rate_per_1k"),
        }

    # ------------------------------------------------------------------ 其他

    def get_data_dir(self) -> Path:
        """数据目录 (默认 ~/.factory; ~ 展开)。"""
        raw = str(self.get("core", "data_dir", DEFAULT_DATA_DIR)).strip() or DEFAULT_DATA_DIR
        return Path(os.path.expanduser(raw))

    def get_port(self) -> int:
        """后端端口 (默认 8011; 非法值 → 默认)。"""
        return _to_int(self.get("core", "port", DEFAULT_PORT), DEFAULT_PORT)

    def get_frontend_port(self) -> int:
        """前端端口 (默认 5180; 非法值 → 默认)。"""
        return _to_int(
            self.get("core", "frontend_port", DEFAULT_FRONTEND_PORT),
            DEFAULT_FRONTEND_PORT,
        )


# ------------------------------------------------------------------ 进程级单例

_CONFIG: ConfigProvider | None = None


def get_config() -> ConfigProvider:
    """进程级单例 (workflow_runner 等消费方共用; 测试/冒烟可 monkeypatch)。"""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = ConfigProvider()
    return _CONFIG


__all__ = [
    "DEFAULT_DATA_DIR",
    "DEFAULT_FRONTEND_PORT",
    "DEFAULT_PORT",
    "DEFAULT_PROVIDER",
    "PROVIDER_DEFAULTS",
    "ConfigProvider",
    "get_config",
]
