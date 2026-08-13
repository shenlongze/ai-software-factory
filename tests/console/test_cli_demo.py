"""tests/console/test_cli_demo.py — S10-026 Task F: factory demo (隔离 Demo Workspace)。

覆盖 (全 hermetic: HOME 重定向 tmp, 零真实 ~/.factory / ~/.factory-demo 触碰):
- 验收 A: demo init 创建隔离 workspace (~/.factory-demo) — 目录 + providers/models
  就位 (复用 LLMControlPlane / ModelCatalog 种子)
- 验收 B: 示例项目 seed (org ProjectStore/ProjectAdoption — org/projects.json)
- 验收 C: demo status 显示状态 (root / providers / models / 示例项目; 未初始化提示)
- 验收 D: demo reset 清空重建; 绝不碰 ~/.factory (两个隔离 HOME 对比 + 预置用户
  数据 marker 断言)
- 验收 E: 红线 — providers.json 只含 api_key_ref 引用, 无明文 key
- 验收 F: demo init 幂等 (二次运行 rc 0, 不重复创建示例项目)
- 验收 G: demo start — 未初始化 → rc 1 明确提示; 已初始化 → 复用 start
  (data_dir 指向 demo root, 不碰用户数据目录)
- parser: demo 注册 + 四动作 choices + start flags
- 入口级: main(['demo', 'init']) + HOME 隔离端到端 (~/.factory-demo 落盘,
  ~/.factory 零创建)

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/console 既有模式; conftest 已挂 factory-core — org seed 依赖)。
basename 全仓库唯一。
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

#: workspace 初始目录 (验收 A 断言用)
WORKSPACE_DIRS = ("agents", "skills", "projects", "providers", "workspace")
#: demo 数据根目录名
DEMO_ROOT_NAME = ".factory-demo"
#: 示例项目固定 id
DEMO_PROJECT_ID = "demo-project"

#: 入口级测试需要清空的 env (防真实环境变量串入 — 同 test_cli_init)
_ENV_PURGE = (
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


@pytest.fixture(autouse=True)
def _fake_node(monkeypatch):
    """环境检测 hermetic: 伪造 node 版本 (demo start 复用 start 的环境门)。"""
    monkeypatch.setattr(_cli, "_node_version", lambda: (26, 7))


def make_cli(tmp_path: Path, environ: dict[str, str] | None = None):
    """hermetic FactoryCLI: config.json 指向 tmp data_dir; 依赖目录伪造。"""
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


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """HOME 重定向到 tmp (<home>/.factory-demo = demo root; 用户 <home>/.factory 零预置)。"""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in _ENV_PURGE:
        monkeypatch.delenv(var, raising=False)
    return home


def demo_root(home: Path) -> Path:
    return home / DEMO_ROOT_NAME


# ------------------------------------------------------------------ 验收 A: demo init 创建隔离 workspace


class TestDemoInit:
    def test_init_creates_isolated_workspace(self, tmp_path, isolated_home, capsys):
        """验收 A: demo init → ~/.factory-demo 目录 + providers/models 就位。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Demo Workspace 初始化" in out
        root = demo_root(isolated_home)
        assert root.is_dir()
        for name in WORKSPACE_DIRS:
            assert (root / name).is_dir(), f"demo workspace 目录缺失: {name}"
        # 验收 B: providers.json + models.json 就位 (种子写入)
        assert (root / "providers.json").is_file()
        assert (root / "models.json").is_file()
        assert "providers.json 就位" in out
        assert "models.json 就位" in out

    def test_providers_seed_via_control_plane(self, tmp_path, isolated_home, capsys):
        """providers.json 经 LLMControlPlane 写入: enabled + env: 引用。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        data = json.loads(
            (demo_root(isolated_home) / "providers.json").read_text(encoding="utf-8")
        )
        pc = data["providers"][_cli.DEMO_PROVIDER]
        assert pc["enabled"] is True
        assert pc["api_key_ref"] == "env:DEEPSEEK_API_KEY"  # 只写引用
        assert pc["models"]  # 非空模型列表

    def test_models_seed_via_model_catalog(self, tmp_path, isolated_home, capsys):
        """models.json 经 ModelCatalog 构造自动 seed (真实种子模型元数据)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        data = json.loads(
            (demo_root(isolated_home) / "models.json").read_text(encoding="utf-8")
        )
        assert data["version"] == 1
        assert "deepseek-chat" in data["models"]
        assert "deepseek-reasoner" in data["models"]

    def test_seed_project_via_org(self, tmp_path, isolated_home, capsys):
        """示例项目经 org ProjectStore/ProjectAdoption 落盘 (org/projects.json)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "示例项目已 seed" in out
        data = json.loads(
            (demo_root(isolated_home) / "org" / "projects.json").read_text(
                encoding="utf-8"
            )
        )
        project = data["projects"][DEMO_PROJECT_ID]
        assert project["name"] == _cli.DEMO_PROJECT_NAME
        assert project["user_id"] == "demo"
        assert project["goal"]

    def test_init_idempotent(self, tmp_path, isolated_home, capsys):
        """验收 F: 二次 init → rc 0, 目录已就绪, 示例项目不重复 (仍 1 个)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        rc = run(cli, "demo", "init")
        out = capsys.readouterr().out
        assert rc == 0
        assert "workspace 目录已就绪" in out  # 幂等: 不重复创建
        root = demo_root(isolated_home)
        data = json.loads(
            (root / "org" / "projects.json").read_text(encoding="utf-8")
        )
        assert set(data["projects"]) == {DEMO_PROJECT_ID}  # 仍 1 个示例项目


# ------------------------------------------------------------------ 验收 E: 红线 (无明文 key)


class TestRedLine:
    def test_no_plaintext_key_in_providers(self, tmp_path, isolated_home, capsys):
        """验收 E: providers.json 只含 env: 引用; 无明文 key 形态。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        text = (demo_root(isolated_home) / "providers.json").read_text(
            encoding="utf-8"
        )
        assert "env:DEEPSEEK_API_KEY" in text
        assert "sk-" not in text
        assert '"api_key"' not in text  # 无明文 api_key 字段, 只有 api_key_ref

    def test_no_plaintext_key_anywhere_in_demo_root(self, tmp_path, isolated_home, capsys):
        """红线扩展: demo root 内全部文件无明文 key 形态。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        for path in demo_root(isolated_home).rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            assert "sk-" not in text, f"明文 key 形态出现在 {path}"


# ------------------------------------------------------------------ 验收 C: demo status


class TestDemoStatus:
    def test_status_before_init(self, tmp_path, isolated_home, capsys):
        """未初始化 → 明确提示, rc 0 (失败安全)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "status")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Demo Workspace 状态" in out
        assert "不存在 (请先运行 factory demo init)" in out

    def test_status_after_init(self, tmp_path, isolated_home, capsys):
        """初始化后 → 显示 root / providers / models / 示例项目状态。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        rc = run(cli, "demo", "status")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Demo 根目录" in out and "(存在)" in out
        assert "workspace 目录" in out
        assert "providers.json: 就位" in out
        assert "models.json: 就位" in out
        assert "示例项目: 1 个" in out

    def test_status_fail_safe_on_corrupt(self, tmp_path, isolated_home, capsys):
        """providers.json 损坏 → 明确提示, rc 0 (永不抛)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        (demo_root(isolated_home) / "providers.json").write_text(
            "{corrupt", encoding="utf-8"
        )
        rc = run(cli, "demo", "status")
        out = capsys.readouterr().out
        assert rc == 0
        assert "providers.json: 损坏" in out


# ------------------------------------------------------------------ 验收 D: demo reset (绝不碰 ~/.factory)


class TestDemoReset:
    def test_reset_rebuilds(self, tmp_path, isolated_home, capsys):
        """reset → 清空重建: 内容仍完整 (目录/providers/models/示例项目)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        # 改动 demo 数据 (模拟脏状态)
        (demo_root(isolated_home) / "dirty.txt").write_text("dirty", encoding="utf-8")
        rc = run(cli, "demo", "reset")
        out = capsys.readouterr().out
        assert rc == 0
        assert "已清空" in out
        root = demo_root(isolated_home)
        assert not (root / "dirty.txt").exists()  # 已重建
        assert (root / "providers.json").is_file()
        assert (root / "models.json").is_file()
        assert (root / "org" / "projects.json").is_file()

    def test_reset_never_touches_user_factory(self, tmp_path, monkeypatch, capsys):
        """验收 D (两个隔离 HOME 对比): demo 操作绝不碰 ~/.factory。

        HOME A: 预置用户 ~/.factory 数据 (marker + providers) → init/status/
        reset 后逐字节不变; HOME B: 全新 → demo init 只建 .factory-demo,
        ~/.factory 零创建。
        """
        cli = make_cli(tmp_path)
        # HOME A — 用户已有真实数据
        home_a = tmp_path / "home_a"
        home_a.mkdir()
        user_factory = home_a / ".factory"
        user_factory.mkdir()
        (user_factory / "marker.txt").write_text("user data", encoding="utf-8")
        (user_factory / "providers.json").write_text(
            json.dumps({"user": True, "note": "real user config"}), encoding="utf-8"
        )
        monkeypatch.setenv("HOME", str(home_a))
        for var in _ENV_PURGE:
            monkeypatch.delenv(var, raising=False)
        assert run(cli, "demo", "init") == 0
        assert run(cli, "demo", "status") == 0
        assert run(cli, "demo", "reset") == 0
        capsys.readouterr()
        # 用户数据零触碰 (逐字节不变)
        assert (user_factory / "marker.txt").read_text(encoding="utf-8") == "user data"
        assert json.loads(
            (user_factory / "providers.json").read_text(encoding="utf-8")
        ) == {"user": True, "note": "real user config"}
        assert not (user_factory / "models.json").exists()  # 未新增任何文件
        # demo 数据独立完整
        assert (home_a / DEMO_ROOT_NAME / "providers.json").is_file()
        assert (home_a / DEMO_ROOT_NAME / "models.json").is_file()
        # HOME B — 全新用户: demo init 只建 .factory-demo, 绝不创建 .factory
        home_b = tmp_path / "home_b"
        home_b.mkdir()
        monkeypatch.setenv("HOME", str(home_b))
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        assert (home_b / DEMO_ROOT_NAME).is_dir()
        assert (home_b / DEMO_ROOT_NAME / "providers.json").is_file()
        assert not (home_b / ".factory").exists()

    def test_reset_when_missing(self, tmp_path, isolated_home, capsys):
        """demo 根不存在时 reset → 直接重建, rc 0。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "reset")
        out = capsys.readouterr().out
        assert rc == 0
        assert "直接重建" in out
        assert (demo_root(isolated_home) / "providers.json").is_file()

    def test_rmtree_guard_rejects_non_demo_path(self, tmp_path, isolated_home):
        """安全护栏: _demo_rmtree 拒绝删除非 ~/.factory-demo 路径。"""
        evil = isolated_home / ".factory"  # 用户数据路径 — 必须被拒
        evil.mkdir()
        with pytest.raises(ValueError, match="拒绝删除非 demo 路径"):
            _cli._demo_rmtree(evil)
        assert evil.is_dir()  # 未被删除


# ------------------------------------------------------------------ 验收 G: demo start


class TestDemoStart:
    def test_start_uninitialized_errors(self, tmp_path, isolated_home, capsys):
        """未初始化 → 明确提示, rc 1 (不启动任何服务)。"""
        cli = make_cli(tmp_path)
        rc = run(cli, "demo", "start")
        err = capsys.readouterr().err
        assert rc == 1
        assert "Demo Workspace 未初始化" in err

    def test_start_delegates_to_start_with_demo_root(
        self, tmp_path, isolated_home, capsys, monkeypatch
    ):
        """已初始化 → 复用 start, data_dir 指向 demo root (不碰用户数据目录)。"""
        cli = make_cli(tmp_path)
        assert run(cli, "demo", "init") == 0
        capsys.readouterr()
        captured: dict = {}

        def fake_start(
            self,
            *,
            no_browser=False,
            port=None,
            frontend_port=None,
            services=None,
            dev=False,
        ):
            captured["data_dir"] = self.data_dir
            captured["run_dir"] = self.run_dir
            captured["kwargs"] = dict(
                no_browser=no_browser,
                port=port,
                frontend_port=frontend_port,
                services=services,
                dev=dev,
            )
            return 0

        monkeypatch.setattr(_cli.FactoryCLI, "start", fake_start)
        rc = run(cli, "demo", "start", "--no-browser", "--port", "9000")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Demo Workspace 启动" in out
        assert captured["data_dir"] == demo_root(isolated_home)
        assert captured["run_dir"] == demo_root(isolated_home) / "run"
        assert captured["kwargs"]["no_browser"] is True
        assert captured["kwargs"]["port"] == 9000
        assert captured["kwargs"]["services"] is None


# ------------------------------------------------------------------ parser


class TestParser:
    def test_demo_registered_with_actions(self):
        parser = _cli.build_parser()
        for action in ("init", "status", "reset", "start"):
            ns = parser.parse_args(["demo", action])
            assert ns.command == "demo", f"demo {action} 未注册"
            assert ns.demo_action == action

    def test_demo_start_flags(self):
        ns = _cli.build_parser().parse_args(
            ["demo", "start", "--no-browser", "--dev", "--port", "9000", "--frontend-port", "9100"]
        )
        assert ns.no_browser is True
        assert ns.dev is True
        assert ns.port == 9000
        assert ns.frontend_port == 9100

    def test_demo_help_exits_zero(self, capsys):
        parser = _cli.build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["demo", "--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "usage:" in out and "demo" in out


# ------------------------------------------------------------------ 入口级集成 (main + HOME 隔离)


class TestMainEntrypoint:
    """真实入口 main() + HOME 重定向 — 端到端验收证据 (零真实 ~/.factory 触碰)。"""

    def test_main_demo_init_end_to_end(self, tmp_path, isolated_home, capsys):
        """端到端: main(['demo','init']) → ~/.factory-demo 完整落盘, ~/.factory 零创建。"""
        assert _cli.main(["demo", "init"]) == 0
        out = capsys.readouterr().out
        assert "示例项目已 seed" in out
        root = demo_root(isolated_home)
        assert (root / "providers.json").is_file()
        assert (root / "models.json").is_file()
        assert (root / "org" / "projects.json").is_file()
        for name in WORKSPACE_DIRS:
            assert (root / name).is_dir()
        assert not (isolated_home / ".factory").exists()  # 零污染

    def test_main_demo_status_and_reset_end_to_end(self, tmp_path, isolated_home, capsys):
        """端到端: init → status → reset 全链路 rc 0, 用户数据零触碰。"""
        assert _cli.main(["demo", "init"]) == 0
        capsys.readouterr()
        assert _cli.main(["demo", "status"]) == 0
        capsys.readouterr()
        assert _cli.main(["demo", "reset"]) == 0
        out = capsys.readouterr().out
        assert "已清空" in out
        root = demo_root(isolated_home)
        assert (root / "providers.json").is_file()  # 重建后仍完整
        assert not (isolated_home / ".factory").exists()
