"""tests/console/test_cli_init.py — S10-026 Task E: factory init (首次运行初始化)。

覆盖 (全 hermetic, tmp_path 注入隔离 — 不读/写真实 ~/.factory):
- 验收 A: 无 providers.json → 引导创建 — 交互路径 (monkeypatch _ask/_stdin_is_tty
  模拟) 与非交互路径 (--non-interactive, 参数/默认直写)
- 验收 B: --non-interactive + --provider deepseek → 直接生成 providers.json
  (enabled + models + api_key_ref=env:DEEPSEEK_API_KEY)
- 验收 C: workspace 目录创建 (agents/skills/projects/providers/workspace)
- 验收 D: 红线 — 写入文件只含 api_key_ref 引用, 绝无明文 key (含交互输入
  明文 key 被拒绝回退默认引用场景)
- 验收 E: 已存在 → 幂等 (非交互保持现状, 文件内容不变); --force → 重新引导
- 环境门: venv/node_modules/Node 缺失 → 明确提示先装依赖, rc 1, 零初始化
- 校验: key 可解析 → ✓ 通过; 未配置 → ⚠ WARN (rc 0); 下一步提示 doctor/start
- parser: init 已转正 (不在 STUB_COMMANDS) + 四 flags; 其余 stub (project/run) 不受影响
- 入口级: main() + HOME 隔离端到端 (providers.json + workspace 落盘)

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/console 既有模式)。basename 全仓库唯一。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")

#: workspace 初始目录 (验收 C 断言用)
WORKSPACE_DIRS = ("agents", "skills", "projects", "providers", "workspace")


@pytest.fixture(autouse=True)
def _fake_node(monkeypatch):
    """环境检测 hermetic: 伪造 node 版本 (不依赖真实 node 安装)。"""
    monkeypatch.setattr(_cli, "_node_version", lambda: (26, 7))


def make_cli(tmp_path: Path, environ: dict[str, str] | None = None):
    """hermetic FactoryCLI: config.json 指向 tmp data_dir (首调用种子); 依赖
    目录 (venv/node_modules) 在 tmp 根伪造, 环境检测通过, 零真实环境依赖。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(exist_ok=True)
    cfg_file = tmp_path / "config.json"
    if not cfg_file.exists():
        cfg_file.write_text(
            json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
        )
    config = _cfg.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ=environ or {}
    )
    root = tmp_path / "repo"
    (root / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (root / ".venv" / "bin" / "python").touch()
    (root / "factory-console" / "web" / "frontend" / "node_modules").mkdir(
        parents=True, exist_ok=True
    )
    return _cli.FactoryCLI(config, root=root)


def run(cli, *argv: str) -> int:
    """解析 + 执行 (同既有测试模式)。"""
    return cli.run(_cli.build_parser().parse_args(list(argv)))


def read_providers(cli) -> dict:
    """读取 data_dir/providers.json → dict。"""
    return json.loads((cli.data_dir / "providers.json").read_text(encoding="utf-8"))


def providers_text(cli) -> str:
    """providers.json 原文 (红线断言用)。"""
    return (cli.data_dir / "providers.json").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 验收 B: 非交互直写


class TestNonInteractive:
    def test_provider_deepseek_generates(self, tmp_path, capsys):
        """验收 B: --non-interactive + --provider deepseek → 直接生成 providers.json。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        out = capsys.readouterr().out
        assert rc == 0
        data = read_providers(cli)
        pc = data["providers"]["deepseek"]
        assert pc["enabled"] is True
        assert pc["models"] == [_cfg.PROVIDER_DEFAULTS["deepseek"]["model"]]
        assert pc["api_key_ref"] == "env:DEEPSEEK_API_KEY"
        assert pc["base_url"] == _cfg.PROVIDER_DEFAULTS["deepseek"]["base_url"]
        assert "已写入 providers.json: deepseek" in out

    def test_provider_and_model(self, tmp_path, capsys):
        """--provider + --model → models 列表用显式模型。"""
        cli = make_cli(tmp_path)
        rc = run(
            cli,
            "init",
            "--non-interactive",
            "--provider",
            "openai",
            "--model",
            "gpt-4o-mini",
        )
        assert rc == 0
        capsys.readouterr()
        data = read_providers(cli)
        assert data["providers"]["openai"]["models"] == ["gpt-4o-mini"]
        assert data["providers"]["openai"]["api_key_ref"] == "env:OPENAI_API_KEY"

    def test_default_provider_when_unspecified(self, tmp_path, capsys):
        """非交互无 --provider → 用默认 deepseek 生成 (用参数或默认)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive")
        out = capsys.readouterr().out
        assert rc == 0
        assert "使用默认 provider deepseek" in out
        data = read_providers(cli)
        assert data["providers"]["deepseek"]["enabled"] is True
        assert data["providers"]["deepseek"]["api_key_ref"] == "env:DEEPSEEK_API_KEY"

    def test_ollama_no_key_ref(self, tmp_path, capsys):
        """ollama 本地模型: api_key_ref 为空, 无 env: 引用。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "ollama")
        assert rc == 0
        capsys.readouterr()
        data = read_providers(cli)
        pc = data["providers"]["ollama"]
        assert pc["enabled"] is True
        assert pc["api_key_ref"] is None
        assert "sk-" not in providers_text(cli)

    def test_unknown_provider_rejected(self, tmp_path, capsys):
        """未知 provider → 明确错误, rc 1, 不生成文件。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "bogus")
        err = capsys.readouterr().err
        assert rc == 1
        assert "未知 provider: bogus" in err
        assert not (cli.data_dir / "providers.json").exists()


# ------------------------------------------------------------------ 验收 A: 交互引导


class TestInteractive:
    def _interactive(self, monkeypatch, answers: list[str]):
        """装配交互环境: 假 TTY + _ask 回答队列。"""
        monkeypatch.setattr(_cli, "_stdin_is_tty", lambda: True)
        queue = iter(answers)

        def fake_ask(prompt: str) -> str:
            try:
                return next(queue)
            except StopIteration:
                return ""

        monkeypatch.setattr(_cli, "_ask", fake_ask)

    def test_wizard_creates_provider(self, tmp_path, capsys, monkeypatch):
        """交互引导创建: 选 openai → 自定义 base_url/ref/model → 落盘。"""
        cli = make_cli(tmp_path)
        self._interactive(
            monkeypatch,
            ["2", "https://api.openai.com/v1", "env:OPENAI_API_KEY", "gpt-4o-mini"],
        )
        rc = run(cli, "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "已写入 providers.json: openai" in out
        pc = read_providers(cli)["providers"]["openai"]
        assert pc["enabled"] is True
        assert pc["models"] == ["gpt-4o-mini"]
        assert pc["api_key_ref"] == "env:OPENAI_API_KEY"
        assert pc["base_url"] == "https://api.openai.com/v1"

    def test_wizard_defaults_on_enter(self, tmp_path, capsys, monkeypatch):
        """全部回车 → 默认 deepseek / 默认 base_url / 默认 env: 引用 / 默认模型。"""
        cli = make_cli(tmp_path)
        self._interactive(monkeypatch, ["", "", "", ""])
        rc = run(cli, "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "(使用默认 provider: deepseek)" in out
        pc = read_providers(cli)["providers"]["deepseek"]
        defaults = _cfg.PROVIDER_DEFAULTS["deepseek"]
        assert pc["models"] == [defaults["model"]]
        assert pc["base_url"] == defaults["base_url"]
        assert pc["api_key_ref"] == "env:DEEPSEEK_API_KEY"

    def test_wizard_invalid_choice_falls_back(self, tmp_path, capsys, monkeypatch):
        """无效选择 (9/abc) → 回退默认 provider, 不中断。"""
        cli = make_cli(tmp_path)
        self._interactive(monkeypatch, ["9", "", "", ""])
        rc = run(cli, "init")
        assert rc == 0
        capsys.readouterr()
        assert "deepseek" in read_providers(cli)["providers"]


# ------------------------------------------------------------------ 验收 C: workspace 目录


class TestWorkspace:
    def test_workspace_dirs_created(self, tmp_path, capsys):
        """验收 C: agents/skills/projects/providers/workspace 全部创建。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        assert rc == 0
        out = capsys.readouterr().out
        assert "已创建 workspace 目录" in out
        for name in WORKSPACE_DIRS:
            assert (cli.data_dir / name).is_dir(), f"workspace 目录缺失: {name}"

    def test_workspace_idempotent_second_run(self, tmp_path, capsys):
        """二次运行: 目录已就绪 (不重复创建, 输出已就绪)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        out = capsys.readouterr().out
        assert rc == 0
        assert "workspace 目录已就绪" in out
        for name in WORKSPACE_DIRS:
            assert (cli.data_dir / name).is_dir()


# ------------------------------------------------------------------ 验收 D: 红线 (只写引用, 无明文 key)


class TestRedLine:
    def test_wizard_rejects_plaintext_key(self, tmp_path, capsys, monkeypatch):
        """交互输入明文 key → 拒绝写入 + 明确警告 + 回退默认 env: 引用。"""
        cli = make_cli(tmp_path)
        monkeypatch.setattr(_cli, "_stdin_is_tty", lambda: True)
        queue = iter(["", "", "sk-1234567890abcdef", ""])
        monkeypatch.setattr(_cli, "_ask", lambda prompt: next(queue))
        rc = run(cli, "init")
        err = capsys.readouterr().err
        assert rc == 0
        assert "只接受 env:VAR 引用" in err and "明文 key 不会写入文件" in err
        text = providers_text(cli)
        assert "sk-1234567890abcdef" not in text  # 明文 key 绝不落盘
        pc = read_providers(cli)["providers"]["deepseek"]
        assert pc["api_key_ref"] == "env:DEEPSEEK_API_KEY"  # 回退默认引用
        assert "api_key" not in pc  # 无 api_key 字段, 只有 api_key_ref

    def test_file_contains_only_refs(self, tmp_path, capsys):
        """落盘文件: 唯一 key 相关值 = env: 引用; 无任何明文 key 形态。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        assert rc == 0
        capsys.readouterr()
        text = providers_text(cli)
        assert "env:DEEPSEEK_API_KEY" in text
        assert "sk-" not in text
        assert "api_key_ref" in text
        assert '"api_key"' not in text  # 无明文 api_key 字段

    def test_force_rewrite_keeps_ref_only(self, tmp_path, capsys, monkeypatch):
        """--force 重新引导 (交互输入明文 key) → 仍只写引用。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        monkeypatch.setattr(_cli, "_stdin_is_tty", lambda: True)
        queue = iter(["", "", "sk-plaintext-force-9999", ""])  # provider/base_url/明文key/model
        monkeypatch.setattr(_cli, "_ask", lambda prompt: next(queue))
        rc = run(cli, "init", "--force")
        assert rc == 0
        err = capsys.readouterr().err
        assert "明文 key 不会写入文件" in err
        text = providers_text(cli)
        assert "sk-plaintext-force-9999" not in text
        assert "env:DEEPSEEK_API_KEY" in text


# ------------------------------------------------------------------ 验收 E: 幂等 / --force


class TestIdempotent:
    def test_existing_kept_noninteractive(self, tmp_path, capsys):
        """已存在 + 非交互: 保持现状 (幂等 — 内容逐字节不变)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        before = providers_text(cli)
        rc = run(cli, "init", "--non-interactive", "--provider", "openai")
        out = capsys.readouterr().out
        assert rc == 0
        assert "保持现有 Provider 配置" in out
        assert providers_text(cli) == before  # 幂等: 文件未变
        assert "openai" not in read_providers(cli)["providers"]

    def test_existing_interactive_keep(self, tmp_path, capsys, monkeypatch):
        """已存在 + 交互: 显示当前配置; 回答 n → 保持现状。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        monkeypatch.setattr(_cli, "_stdin_is_tty", lambda: True)
        monkeypatch.setattr(_cli, "_ask", lambda prompt: "n")
        rc = run(cli, "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "当前 Provider 配置" in out
        assert "保持现有 Provider 配置" in out
        assert set(read_providers(cli)["providers"]) == {"deepseek"}

    def test_existing_interactive_reguide(self, tmp_path, capsys, monkeypatch):
        """已存在 + 交互: 回答 y → 重新引导 (新增/覆盖 provider)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        monkeypatch.setattr(_cli, "_stdin_is_tty", lambda: True)
        queue = iter(["y", "3", "", "env:ANTHROPIC_API_KEY", "claude-3-5"])
        monkeypatch.setattr(_cli, "_ask", lambda prompt: next(queue))
        rc = run(cli, "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "开始重新配置" in out
        data = read_providers(cli)["providers"]
        assert data["anthropic"]["enabled"] is True
        assert data["anthropic"]["models"] == ["claude-3-5"]
        assert data["deepseek"]["enabled"] is True  # 既有条目保留 (upsert)

    def test_force_reguides(self, tmp_path, capsys):
        """--force: 无视已存在 → 重新引导 (覆盖 provider 配置)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "init", "--non-interactive", "--provider", "deepseek") == 0
        capsys.readouterr()
        rc = run(
            cli,
            "init",
            "--non-interactive",
            "--force",
            "--provider",
            "openai",
            "--model",
            "gpt-4o",
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "--force: 重新引导" in out
        data = read_providers(cli)["providers"]
        assert data["openai"]["enabled"] is True
        assert data["openai"]["models"] == ["gpt-4o"]
        assert "deepseek" in data  # upsert 不删其他条目

    def test_force_first_run_same_as_init(self, tmp_path, capsys):
        """无 providers.json + --force → 正常引导 (不报错)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--force", "--provider", "deepseek")
        assert rc == 0
        capsys.readouterr()
        assert read_providers(cli)["providers"]["deepseek"]["enabled"] is True


# ------------------------------------------------------------------ 环境门


class TestEnvGate:
    def test_deps_missing_blocks_init(self, tmp_path, capsys):
        """依赖缺失 (无 .venv / node_modules) → 明确提示先安装, rc 1, 零初始化。"""
        data_dir = tmp_path / ".factory"
        data_dir.mkdir()
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(
            json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
        )
        config = _cfg.ConfigProvider(
            user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
        )
        cli = _cli.FactoryCLI(config, root=tmp_path / "empty_repo")  # 无依赖
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        err = capsys.readouterr().err
        assert rc == 1
        assert "未找到虚拟环境" in err
        assert "请先安装依赖" in err
        assert not (data_dir / "agents").exists()  # 环境失败 → 不初始化
        assert not (data_dir / "providers.json").exists()

    def test_node_missing_blocks_init(self, tmp_path, capsys, monkeypatch):
        """Node 缺失 → 环境检查明确提示, rc 1。"""
        monkeypatch.setattr(_cli, "_node_version", lambda: None)
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        err = capsys.readouterr().err
        assert rc == 1
        assert "未找到 Node.js" in err
        assert "环境检查未通过" in err
        assert not (cli.data_dir / "providers.json").exists()


# ------------------------------------------------------------------ 校验 + 下一步


class TestValidate:
    def test_missing_env_key_warns(self, tmp_path, capsys):
        """providers.json 生成但 env key 未配置 → ⚠ WARN (rc 0) + 下一步提示。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        out = capsys.readouterr().out
        assert rc == 0
        assert "缺少 API key" in out
        assert "factory doctor" in out and "factory start" in out

    def test_key_resolvable_passes(self, tmp_path, capsys, monkeypatch):
        """env key 可解析 → ✓ 校验通过。"""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        cli = make_cli(tmp_path)
        rc = run(cli, "init", "--non-interactive", "--provider", "deepseek")
        out = capsys.readouterr().out
        assert rc == 0
        assert "校验通过" in out

    def test_corrupt_providers_warns(self, tmp_path, capsys):
        """providers.json 损坏 → ⚠ WARN, rc 0 (不崩溃)。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "providers.json").write_text("{corrupt", encoding="utf-8")
        rc = run(cli, "init", "--non-interactive")
        out = capsys.readouterr().out
        assert rc == 0
        assert "providers.json 损坏" in out


# ------------------------------------------------------------------ parser


class TestParser:
    def test_init_registered_with_flags(self):
        parser = _cli.build_parser()
        ns = parser.parse_args(
            [
                "init",
                "--force",
                "--non-interactive",
                "--provider",
                "deepseek",
                "--model",
                "deepseek-chat",
            ]
        )
        assert ns.command == "init"
        assert ns.force is True
        assert ns.non_interactive is True
        assert ns.provider == "deepseek"
        assert ns.model == "deepseek-chat"

    def test_init_flags_defaults(self):
        ns = _cli.build_parser().parse_args(["init"])
        assert ns.force is False
        assert ns.non_interactive is False
        assert ns.provider is None
        assert ns.model is None

    def test_init_no_longer_stub(self):
        """init 已转正: 不在 STUB_COMMANDS; project/run 仍为 stub。"""
        assert "init" not in _cli.STUB_COMMANDS
        assert "project" in _cli.STUB_COMMANDS
        assert "run" in _cli.STUB_COMMANDS

    def test_subcommand_still_registered(self):
        """init 子命令仍在 parser (从 stub 转正, 集合不变)。"""
        parser = _cli.build_parser()
        sub_actions = {
            a.dest: a
            for a in parser._actions
            if getattr(a, "choices", None) is not None
        }
        choices = set(sub_actions["command"].choices)
        assert "init" in choices
        for name in ("start", "stop", "status", "doctor", "service", "config"):
            assert name in choices


# ------------------------------------------------------------------ 入口级集成 (main + HOME 隔离)


class TestMainEntrypoint:
    """真实入口 main() + HOME 重定向 — 端到端验收证据 (零真实 ~/.factory 触碰)。"""

    def _isolated_home(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        for var in (
            "PORT",
            "FRONTEND_PORT",
            "DATA_DIR",
            "LLM_PROVIDER",
            "LLM_MODEL",
            "LLM_BASE_URL",
            "LLM_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(var, raising=False)
        return home

    def test_main_noninteractive_init_end_to_end(self, tmp_path, capsys, monkeypatch):
        """端到端: main(['init','--non-interactive','--provider','deepseek']) →
        providers.json + 全部 workspace 目录落盘 (HOME 隔离)。"""
        home = self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["init", "--non-interactive", "--provider", "deepseek"]) == 0
        out = capsys.readouterr().out
        assert "已写入 providers.json: deepseek" in out
        factory = home / ".factory"
        assert (factory / "providers.json").is_file()
        for name in WORKSPACE_DIRS:
            assert (factory / name).is_dir(), f"workspace 目录缺失: {name}"
        data = json.loads((factory / "providers.json").read_text(encoding="utf-8"))
        assert data["providers"]["deepseek"]["api_key_ref"] == "env:DEEPSEEK_API_KEY"
        assert "sk-" not in (factory / "providers.json").read_text(encoding="utf-8")

    def test_main_second_run_idempotent(self, tmp_path, capsys, monkeypatch):
        """端到端幂等: 二次运行保持现有配置, rc 0。"""
        home = self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["init", "--non-interactive", "--provider", "deepseek"]) == 0
        capsys.readouterr()
        assert _cli.main(["init", "--non-interactive"]) == 0
        out = capsys.readouterr().out
        assert "保持现有 Provider 配置" in out
