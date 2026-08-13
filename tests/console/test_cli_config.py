"""tests/console/test_cli_config.py — S10-026 Task D: factory config (运行时配置)。

覆盖 (全 hermetic, tmp_path 注入隔离 — 不读/写真实 ~/.factory):
- 验收 A: config show 显示运行时配置且脱敏 (key 不显示值, 只显示已配置/未配置
  状态; 默认值/配置值/API key 明文绝不出现)
- 验收 B: config set core.port 1234 写入成功 (文件落盘 + 新 ConfigProvider 读取
  回显; 既有键保留)
- 验收 C: config set llm.provider → 拒绝 (红线 ①) — 明确错误 + providers.json /
  models.json 零污染; config.json 不新增 llm 段; 旧版遗留 llm.* 段不被触碰
- 验收 D: config check 输出 OK/WARN (config.json 可读 OK; providers.json 缺失
  WARN; 就绪 OK; 零副作用不创建任何文件)
- 验收 E: config path 显示配置文件路径 (注入的 tmp 路径)
- 验收 F: set 未知键 / 非法端口值 → 拒绝; set 缺 value → 用法提示 rc 2
- 验收 G: 既有命令零影响 (status/stop rc 0); stub (init/project/run) 仍在

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


def subcommand_names(parser) -> set[str]:
    """已注册子命令名集合 (argparse subparsers choices)。"""
    for action in parser._actions:
        if getattr(action, "choices", None):
            return set(action.choices)
    return set()


def make_cli(
    tmp_path: Path, environ: dict[str, str] | None = None
):
    """hermetic FactoryCLI: config.json 指向 tmp (首调用种子, 二次调用复用
    已写入文件 — 模拟新进程读盘), 零真实环境依赖。"""
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
    root.mkdir(exist_ok=True)
    return _cli.FactoryCLI(config, root=root)


def run(cli, *argv: str) -> int:
    """解析 + 执行 (同既有测试模式)。"""
    return cli.run(_cli.build_parser().parse_args(list(argv)))


# ------------------------------------------------------------------ 验收 A: show 脱敏


class TestShow:
    def test_show_lists_keys_with_status_no_values(self, tmp_path, capsys):
        """默认态: 三键齐全 + 未配置; 脱敏 — 默认值明文 (8011/5180) 不出现。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "show")
        out = capsys.readouterr().out
        assert rc == 0
        for key in ("core.data_dir", "core.port", "core.frontend_port"):
            assert key in out, f"show 缺键 {key}"
        assert out.count("未配置") >= 2  # port/frontend_port 默认未配置
        assert "8011" not in out and "5180" not in out  # key 值不显示 (脱敏)
        assert "LLM (只读状态)" in out

    def test_show_masked_after_set(self, tmp_path, capsys):
        """set 后 (新实例模拟新进程读盘): 键显示已配置, 但值 1234 仍不显示。"""
        cli = make_cli(tmp_path)
        assert run(cli, "config", "set", "core.port", "1234") == 0
        capsys.readouterr()
        cli2 = make_cli(tmp_path)  # 复用同一 config.json, 新 ConfigProvider 读盘
        rc = run(cli2, "config", "show")
        out = capsys.readouterr().out
        assert rc == 0
        assert "core.port" in out and "已配置" in out
        assert "1234" not in out  # 配置值不显示 (脱敏)

    def test_show_never_leaks_api_key(self, tmp_path, capsys):
        """API key 明文绝不出现 (铁律); 只显示 已配置/未配置 状态。"""
        cli = make_cli(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-super-secret"})
        rc = run(cli, "config", "show")
        out = capsys.readouterr().out
        assert rc == 0
        assert "sk-super-secret" not in out
        assert "api_key=已配置" in out


# ------------------------------------------------------------------ 验收 B: set 白名单写入


class TestSet:
    def test_set_core_port_written_and_read_back(self, tmp_path, capsys):
        """写入成功: 落盘为整型 + 既有键保留 + 新 ConfigProvider 读取回显。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.port", "1234")
        out = capsys.readouterr().out
        assert rc == 0
        assert "已写入 core.port = 1234" in out
        cfg_file = tmp_path / "config.json"
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert data["core"]["port"] == 1234  # 整型落盘
        assert data["core"]["data_dir"] == str(cli.data_dir)  # 既有键保留
        fresh = _cfg.ConfigProvider(
            user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
        )
        assert fresh.get_port() == 1234  # 读取回显 (分层读取生效)

    def test_set_core_frontend_port(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.frontend_port", "6000")
        assert rc == 0
        capsys.readouterr()
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert data["core"]["frontend_port"] == 6000

    def test_set_core_data_dir(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.data_dir", "/tmp/factory-x")
        assert rc == 0
        capsys.readouterr()
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert data["core"]["data_dir"] == "/tmp/factory-x"

    def test_set_preserves_legacy_llm_section_untouched(self, tmp_path, capsys):
        """旧版 config.json 遗留 llm.* 段: set 只改白名单键, 绝不触碰 llm 段。"""
        data_dir = tmp_path / ".factory"
        data_dir.mkdir(exist_ok=True)
        (tmp_path / "config.json").write_text(
            json.dumps(
                {
                    "core": {"data_dir": str(data_dir)},
                    "llm": {"provider": "deepseek", "model": "deepseek-chat"},
                }
            ),
            encoding="utf-8",
        )
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.port", "8080")
        assert rc == 0
        capsys.readouterr()
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert data["core"]["port"] == 8080
        assert data["llm"] == {"provider": "deepseek", "model": "deepseek-chat"}


# ------------------------------------------------------------------ 验收 C: 红线 (llm.* 拒绝 + 零污染)


class TestRedLine:
    @pytest.mark.parametrize(
        "key", ["llm.provider", "llm.model", "llm.base_url", "llm.api_key_ref"]
    )
    def test_set_llm_key_rejected(self, tmp_path, capsys, key):
        """四个红线键全部拒绝 + 明确错误消息 (引导到 providers.json 等)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", key, "deepseek")
        err = capsys.readouterr().err
        assert rc == 1
        assert "拒绝写入" in err and key in err
        assert "providers.json" in err  # 引导到正确管理面
        assert "models.json" in err

    def test_set_llm_rejected_no_pollution(self, tmp_path, capsys):
        """红线核心: 拒绝后 providers.json/models.json 零污染 (不创建),
        config.json 也不含 llm 段。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "llm.provider", "deepseek")
        assert rc == 1
        capsys.readouterr()
        assert not (cli.data_dir / "providers.json").exists()
        assert not (cli.data_dir / "models.json").exists()
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert "llm" not in data
        assert data["core"]["data_dir"] == str(cli.data_dir)  # 原文件未被破坏


# ------------------------------------------------------------------ 验收 F: 拒绝非法输入


class TestReject:
    def test_set_unknown_key_rejected(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.bogus", "1")
        err = capsys.readouterr().err
        assert rc == 1
        assert "未知配置键" in err and "core.bogus" in err

    def test_set_future_workspace_key_rejected(self, tmp_path, capsys):
        """workspace 为未来扩展位 (设计不实现) — 不在白名单 → 拒绝。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "workspace.dir", "/tmp/x")
        assert rc == 1
        assert "未知配置键" in capsys.readouterr().err

    def test_set_invalid_port_rejected(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.port", "abc")
        assert rc == 1
        assert "非法端口值" in capsys.readouterr().err
        rc = run(cli, "config", "set", "core.port", "70000")  # 超范围
        assert rc == 1
        rc = run(cli, "config", "set", "core.port", "0")
        assert rc == 1

    def test_set_missing_value_usage(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "set", "core.port")
        assert rc == 2
        assert "用法" in capsys.readouterr().err


# ------------------------------------------------------------------ 验收 D: check OK/WARN


class TestCheck:
    def test_check_ok_and_warn(self, tmp_path, capsys):
        """config.json 可读 → OK; providers.json 缺失 → WARN; rc 0。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "check")
        out = capsys.readouterr().out
        assert rc == 0
        assert "配置校验" in out
        assert "OK   config.json 可读" in out
        assert "WARN providers.json 不存在" in out

    def test_check_providers_ready_ok(self, tmp_path, capsys, monkeypatch):
        """providers.json 就绪 (enabled + key 可解析) → OK。"""
        cli = make_cli(tmp_path)
        (cli.data_dir / "providers.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "providers": {
                        "deepseek": {
                            "id": "deepseek",
                            "enabled": True,
                            "models": ["deepseek-chat"],
                            "api_key_ref": "env:DEEPSEEK_API_KEY",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        rc = run(cli, "config", "check")
        out = capsys.readouterr().out
        assert rc == 0
        assert "OK   providers.json 就绪" in out
        assert "deepseek" in out

    def test_check_no_enabled_provider_warn(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        (cli.data_dir / "providers.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "providers": {
                        "deepseek": {"id": "deepseek", "enabled": False}
                    },
                }
            ),
            encoding="utf-8",
        )
        rc = run(cli, "config", "check")
        assert rc == 0
        assert "无 enabled provider" in capsys.readouterr().out

    def test_check_corrupt_providers_warn(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        (cli.data_dir / "providers.json").write_text("{corrupt", encoding="utf-8")
        rc = run(cli, "config", "check")
        assert rc == 0
        assert "WARN providers.json 损坏" in capsys.readouterr().out

    def test_check_readonly_no_side_effect(self, tmp_path, capsys):
        """零副作用: check 绝不创建 providers.json / models.json。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "check")
        assert rc == 0
        capsys.readouterr()
        assert not (cli.data_dir / "providers.json").exists()
        assert not (cli.data_dir / "models.json").exists()


# ------------------------------------------------------------------ 验收 E: path


class TestPath:
    def test_path_shows_config_file(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        rc = run(cli, "config", "path")
        out = capsys.readouterr().out
        assert rc == 0
        assert str(tmp_path / "config.json") in out


# ------------------------------------------------------------------ parser / 零影响


class TestParser:
    def test_config_parser_registered(self):
        names = subcommand_names(_cli.build_parser())
        assert "config" in names
        args = _cli.build_parser().parse_args(["config", "show"])
        assert args.command == "config" and args.config_action == "show"
        args = _cli.build_parser().parse_args(["config", "set", "core.port", "1"])
        assert args.key == "core.port" and args.value == "1"
        assert _cli.CONFIG_KEYS == ("core.data_dir", "core.port", "core.frontend_port")
        assert "llm.provider" in _cli.CONFIG_FORBIDDEN_KEYS

    def test_config_requires_action(self):
        with pytest.raises(SystemExit) as exc:
            _cli.build_parser().parse_args(["config"])
        assert exc.value.code == 2

    def test_config_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _cli.build_parser().parse_args(["config", "--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out
        for action in ("show", "set", "check", "path"):
            assert action in out

    def test_stub_commands_still_present(self):
        """config 转正后, 其余 stub (init/project/run) 不受影响。"""
        names = subcommand_names(_cli.build_parser())
        for name in ("init", "project", "run"):
            assert name in names, f"stub 子命令 {name} 丢失"
        assert "config" not in _cli.STUB_COMMANDS


class TestNoRegression:
    def test_existing_commands_unaffected(self, tmp_path, capsys):
        """新增 config 不破坏既有命令 (status/stop 照常 rc 0)。"""
        cli = make_cli(tmp_path)
        for argv in (["status"], ["stop"]):
            rc = run(cli, *argv)
            assert rc == 0, f"command {argv} regressed"


# ------------------------------------------------------------------ 入口级集成 (main + HOME 隔离)

#: 进程环境里可能影响 ConfigProvider 分层取值的变量 (main 级测试需清空隔离)
_CONFIG_ENV_VARS = (
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
)


class TestMainEntrypoint:
    """真实入口 main() + HOME 重定向 — 端到端验收证据 (零真实 ~/.factory 触碰)。"""

    def _isolated_home(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        for var in _CONFIG_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        return home

    def test_main_show_masked_after_set(self, tmp_path, capsys, monkeypatch):
        """验收 A/B 端到端: main(['config','set','core.port','1234']) → 落盘 →
        main(['config','show']) 脱敏 (值不显示, 状态显示)。"""
        home = self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["config", "set", "core.port", "1234"]) == 0
        capsys.readouterr()
        assert _cli.main(["config", "show"]) == 0
        out = capsys.readouterr().out
        assert "core.port" in out and "已配置" in out
        assert "1234" not in out
        assert "8011" not in out
        data = json.loads(
            (home / ".factory" / "config.json").read_text(encoding="utf-8")
        )
        assert data["core"]["port"] == 1234

    def test_main_redline_rejected(self, tmp_path, capsys, monkeypatch):
        """验收 C 端到端: llm.provider 拒绝 + providers.json/models.json 零污染。"""
        home = self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["config", "set", "llm.provider", "deepseek"]) == 1
        err = capsys.readouterr().err
        assert "拒绝写入 llm.provider" in err
        assert not (home / ".factory" / "providers.json").exists()
        assert not (home / ".factory" / "models.json").exists()
        cfg = home / ".factory" / "config.json"
        if cfg.exists():  # 拒绝发生在任何写入之前 — 文件通常不存在
            assert "llm" not in json.loads(cfg.read_text(encoding="utf-8"))

    def test_main_check_ok_and_warn(self, tmp_path, capsys, monkeypatch):
        """验收 D 端到端: config.json 可读 OK + providers.json 缺失 WARN。"""
        self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["config", "set", "core.port", "8080"]) == 0
        capsys.readouterr()
        assert _cli.main(["config", "check"]) == 0
        out = capsys.readouterr().out
        assert "OK   config.json 可读" in out
        assert "WARN providers.json 不存在" in out

    def test_main_path_shows_home_config(self, tmp_path, capsys, monkeypatch):
        """验收 E 端到端: path 指向 HOME 重定向后的 config.json。"""
        home = self._isolated_home(tmp_path, monkeypatch)
        assert _cli.main(["config", "path"]) == 0
        out = capsys.readouterr().out
        assert str(home / ".factory" / "config.json") in out
