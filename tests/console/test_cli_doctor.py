"""tests/console/test_cli_doctor.py — S10-026 Task A: Doctor Framework (factory doctor)。

覆盖 (全 hermetic, tmp_path + HOME 隔离 — 不写真实 ~/.factory):
- 5 内置检查器: environment/provider/model/runtime/router 的 PASS/WARN/FAIL 场景
- --json 输出结构 {checks, summary}; 人类可读输出含 PASS/WARN/FAIL + 汇总
- 指定 checker_id 只跑该检查器; 未知检查器 → exit code 2
- 注册表可扩展: 注入假检查器 register 后自动被发现 (未来 rag/governance 模式)
- exit code: 全 PASS → 0; 有 WARN → 0 (带 ⚠ 提示); 有 FAIL → 1
- CLI 集成: build_parser 注册 doctor; FactoryCLI.doctor 薄代理; 既有命令零影响

装配: importlib + sys.path 挂仓库根 (factory-console 包名含连字符, 唯一导入
方式; 同 tests/llm 与 tests/console 模式)。basename 全仓库唯一。

检查器复用资产 (验收 C): LLMControlPlane / ModelCatalog / LLMRouter /
cli_factory._port_in_use / _node_version / MIN_PYTHON / MIN_NODE — 全部真实调用。
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

_doc = importlib.import_module("factory-console.cli_doctor")
_cli = importlib.import_module("factory-console.cli_factory")
_cfg = importlib.import_module("factory-console.config")
_mc = importlib.import_module("factory-console.model_catalog")

BUILTIN_IDS = ["environment", "provider", "model", "runtime", "router"]


def make_ctx(
    tmp_path: Path,
    environ: dict[str, str] | None = None,
    backend_port: int = 8011,
    frontend_port: int = 5180,
):
    """hermetic DoctorContext: data_dir=tmp/.factory, root=tmp/repo (无依赖)。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    return _doc.DoctorContext(
        data_dir=data_dir,
        root=root,
        backend_port=backend_port,
        frontend_port=frontend_port,
        environ=environ or {},
    )


def make_cli(tmp_path: Path):
    """hermetic FactoryCLI: config.json 指向 tmp data_dir, 零环境依赖。"""
    data_dir = tmp_path / ".factory"
    data_dir.mkdir()
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
    )
    config = _cfg.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    root = tmp_path / "repo"
    root.mkdir()
    return _cli.FactoryCLI(config, root=root)


def seed_provider(ctx, *, enabled: bool = True, key: str | None = "sk-test") -> None:
    """providers.json 写入: enabled deepseek + api_key_ref (key 经 environ 注入)。"""
    plane = ctx.control_plane
    plane.set_config(
        "deepseek",
        enabled=enabled,
        models=["deepseek-chat"],
        api_key_ref="env:DEEPSEEK_API_KEY" if key else None,
    )


# ------------------------------------------------------------------ 注册表 (验收 D)


class TestRegistry:
    def test_builtin_checks_registered(self):
        """5 内置检查器注册齐全 (验收 C 检查器清单)。"""
        ids = [c.id for c in _doc.list_checks()]
        assert ids == BUILTIN_IDS

    def test_register_extensible_fake_check_auto_discovered(self, tmp_path, capsys):
        """未来 rag/governance/agent-policy: 实现协议 + register → 自动发现。"""
        ctx = make_ctx(tmp_path)

        class FakeRagCheck:
            id = "rag"
            label = "RAG 诊断 (预留空位)"

            def run(self, c):
                return _doc.CheckResult(self.id, "PASS", "fake rag ok", {"indexed": 0})

        _doc.register(FakeRagCheck())
        try:
            assert "rag" in [c.id for c in _doc.list_checks()]
            rc = _doc.run_doctor(["rag"], ctx=ctx, json_mode=True)
            data = json.loads(capsys.readouterr().out)
            assert rc == 0
            assert data["checks"][0]["id"] == "rag"
            assert data["checks"][0]["status"] == "PASS"
            assert data["checks"][0]["details"] == {"indexed": 0}
        finally:
            del _doc._CHECKS["rag"]  # 清理, 不污染其他用例

    def test_register_duplicate_raises(self):
        with pytest.raises(ValueError):
            _doc.register(_doc.get_check("environment"))

    def test_unknown_checker_rc2(self, tmp_path, capsys):
        rc = _doc.run_doctor(["bogus"], ctx=make_ctx(tmp_path))
        assert rc == 2
        assert "未知检查器: bogus" in capsys.readouterr().err


# ------------------------------------------------------------------ 输出格式 (验收 A/B)


class TestOutput:
    def test_json_structure(self, tmp_path, capsys):
        rc = _doc.run_doctor(["provider"], ctx=make_ctx(tmp_path), json_mode=True)
        data = json.loads(capsys.readouterr().out)
        assert rc == 1  # providers.json 缺失 → FAIL
        assert set(data.keys()) == {"checks", "summary"}
        assert data["summary"] == {"pass": 0, "warn": 0, "fail": 1}
        assert len(data["checks"]) == 1
        c = data["checks"][0]
        assert set(c.keys()) == {"id", "status", "message", "details"}
        assert c["id"] == "provider"
        assert c["status"] == "FAIL"

    def test_human_output_pass(self, tmp_path, capsys):
        ctx = make_ctx(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-test"})
        seed_provider(ctx)
        rc = _doc.run_doctor(["provider"], ctx=ctx)
        out = capsys.readouterr().out
        assert rc == 0
        assert "[PASS] provider" in out
        assert "汇总: 1 PASS / 0 WARN / 0 FAIL" in out

    def test_human_output_warn_with_mark(self, tmp_path, capsys):
        rc = _doc.run_doctor(["model"], ctx=make_ctx(tmp_path))
        out = capsys.readouterr().out
        assert rc == 0
        assert "⚠ [WARN] model" in out
        assert "⚠ 存在 WARN 项" in out

    def test_human_output_fail_to_stderr_hint(self, tmp_path, capsys):
        rc = _doc.run_doctor(["provider"], ctx=make_ctx(tmp_path))
        assert rc == 1
        err = capsys.readouterr().err
        assert "存在 FAIL 项" in err

    def test_run_doctor_all_builtin_default(self, tmp_path, capsys):
        rc = _doc.run_doctor(ctx=make_ctx(tmp_path), json_mode=True)
        data = json.loads(capsys.readouterr().out)
        assert rc == 1  # provider FAIL (空环境)
        assert [c["id"] for c in data["checks"]] == BUILTIN_IDS
        assert set(data["summary"].keys()) == {"pass", "warn", "fail"}

    def test_verbose_shows_details(self, tmp_path, capsys, monkeypatch):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_port_in_use", lambda port: False)
        _doc.run_doctor(["runtime"], ctx=ctx, verbose=True)
        out = capsys.readouterr().out
        assert "backend_running: False" in out


# ------------------------------------------------------------------ environment


class TestEnvironment:
    def test_pass_full_setup(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_node_version", lambda: (26, 4))
        venv_py = ctx.root / ".venv" / "bin" / "python"
        venv_py.parent.mkdir(parents=True)
        venv_py.write_text("", encoding="utf-8")
        (ctx.root / "factory-console" / "web" / "frontend" / "node_modules").mkdir(
            parents=True
        )
        for name in _doc.WORKSPACE_DIRS:
            (ctx.data_dir / name).mkdir()
        result = _doc.EnvironmentCheck().run(ctx)
        assert result.status == "PASS"
        assert result.details["missing_workspace_dirs"] == []

    def test_warn_node_missing(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_node_version", lambda: None)
        result = _doc.EnvironmentCheck().run(ctx)
        assert result.status == "WARN"
        assert "未找到 Node.js" in result.message

    def test_fail_python_too_old(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "MIN_PYTHON", (99, 99))  # 当前 3.x 必然过低
        result = _doc.EnvironmentCheck().run(ctx)
        assert result.status == "FAIL"
        assert "Python 版本过低" in result.message

    def test_warn_missing_workspace_dirs(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_node_version", lambda: (26, 4))
        result = _doc.EnvironmentCheck().run(ctx)
        assert result.status == "WARN"
        assert result.details["missing_workspace_dirs"] == list(_doc.WORKSPACE_DIRS)
        assert "factory init" in result.message


# ------------------------------------------------------------------ provider


class TestProvider:
    def test_fail_missing_providers_json(self, tmp_path):
        result = _doc.ProviderCheck().run(make_ctx(tmp_path))
        assert result.status == "FAIL"
        assert "providers.json 不存在" in result.message
        assert "factory init" in result.message

    def test_warn_no_enabled_provider(self, tmp_path):
        ctx = make_ctx(tmp_path)
        seed_provider(ctx, enabled=False)
        result = _doc.ProviderCheck().run(ctx)
        assert result.status == "WARN"
        assert "无 enabled provider" in result.message
        assert result.details["providers"] == 1

    def test_warn_enabled_but_key_missing(self, tmp_path):
        ctx = make_ctx(tmp_path, environ={})  # 无 DEEPSEEK_API_KEY
        seed_provider(ctx, key=None)
        ctx.control_plane.set_config("deepseek", enabled=True)
        result = _doc.ProviderCheck().run(ctx)
        assert result.status == "WARN"
        assert "缺少 API key" in result.message
        assert result.details["missing_api_key"] == ["deepseek"]

    def test_pass_enabled_with_key(self, tmp_path):
        ctx = make_ctx(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-test"})
        seed_provider(ctx)
        result = _doc.ProviderCheck().run(ctx)
        assert result.status == "PASS"
        assert result.details["enabled"] == 1
        assert result.details["missing_api_key"] == []

    def test_fail_corrupt_file(self, tmp_path):
        ctx = make_ctx(tmp_path)
        (ctx.data_dir / "providers.json").write_text("{corrupt", encoding="utf-8")
        result = _doc.ProviderCheck().run(ctx)
        assert result.status == "FAIL"
        assert "损坏" in result.message


# ------------------------------------------------------------------ model


class TestModel:
    def test_warn_missing_models_json_no_side_effect(self, tmp_path):
        """缺失 → WARN + 不触发种子写入 (零副作用铁律)。"""
        ctx = make_ctx(tmp_path)
        result = _doc.ModelCheck().run(ctx)
        assert result.status == "WARN"
        assert "models.json 不存在" in result.message
        assert not (ctx.data_dir / "models.json").exists()

    def test_pass_seeded(self, tmp_path):
        ctx = make_ctx(tmp_path)
        _mc.ModelCatalog(models_file=ctx.data_dir / "models.json")  # 构造即 seed
        result = _doc.ModelCheck().run(ctx)
        assert result.status == "PASS"
        assert result.details["enabled"] >= 1
        assert "seeded" not in result.details  # 文件存在分支无该字段

    def test_warn_all_disabled(self, tmp_path):
        ctx = make_ctx(tmp_path)
        catalog = _mc.ModelCatalog(models_file=ctx.data_dir / "models.json")
        for m in catalog.list_models(include_disabled=True):
            catalog.set_enabled(m.model_id, False)
        result = _doc.ModelCheck().run(ctx)
        assert result.status == "WARN"
        assert "无 enabled 模型" in result.message
        assert result.details["enabled"] == 0

    def test_fail_corrupt_file(self, tmp_path):
        ctx = make_ctx(tmp_path)
        (ctx.data_dir / "models.json").write_text("{corrupt", encoding="utf-8")
        result = _doc.ModelCheck().run(ctx)
        assert result.status == "FAIL"
        assert "损坏" in result.message


# ------------------------------------------------------------------ runtime


class TestRuntime:
    def test_pass_both_ports_up(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_port_in_use", lambda port: True)
        result = _doc.RuntimeCheck().run(ctx)
        assert result.status == "PASS"
        assert result.details["backend_running"] is True
        assert result.details["frontend_running"] is True

    def test_warn_both_down(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(_doc, "_port_in_use", lambda port: False)
        result = _doc.RuntimeCheck().run(ctx)
        assert result.status == "WARN"
        assert "未运行" in result.message
        assert result.details["backend_running"] is False

    def test_warn_backend_only(self, monkeypatch, tmp_path):
        ctx = make_ctx(tmp_path)
        monkeypatch.setattr(
            _doc, "_port_in_use", lambda port: port == ctx.backend_port
        )
        result = _doc.RuntimeCheck().run(ctx)
        assert result.status == "WARN"
        assert "前端" in result.message

    def test_real_port_detection(self, tmp_path):
        """真实端口探测: 本机空闲端口起监听 → _port_in_use True (复用 cli_factory)。"""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.listen(1)
            assert _doc._port_in_use(port) is True


# ------------------------------------------------------------------ router


class TestRouter:
    def test_warn_no_usable_provider(self, tmp_path):
        ctx = make_ctx(tmp_path)  # 无 providers.json → 无可命中
        result = _doc.RouterCheck().run(ctx)
        assert result.status == "WARN"
        assert result.details == {"hit": False}

    def test_pass_route_hits_system_recommendation(self, tmp_path):
        ctx = make_ctx(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-test"})
        seed_provider(ctx)
        _mc.ModelCatalog(models_file=ctx.data_dir / "models.json")  # seed → L4 候选
        result = _doc.RouterCheck().run(ctx)
        assert result.status == "PASS"
        assert result.details["hit"] is True
        assert result.details["provider_id"] == "deepseek"
        assert result.details["source"] in ("system-recommendation", "fallback")

    def test_fail_corrupt_providers_file(self, tmp_path):
        ctx = make_ctx(tmp_path)
        (ctx.data_dir / "providers.json").write_text("{corrupt", encoding="utf-8")
        result = _doc.RouterCheck().run(ctx)
        assert result.status == "FAIL"
        assert "Router 决策异常" in result.message


# ------------------------------------------------------------------ exit code


class TestExitCode:
    def test_all_pass_rc0(self, tmp_path, capsys, monkeypatch):
        ctx = make_ctx(tmp_path, environ={"DEEPSEEK_API_KEY": "sk-test"})
        monkeypatch.setattr(_doc, "_port_in_use", lambda port: True)
        seed_provider(ctx)
        _mc.ModelCatalog(models_file=ctx.data_dir / "models.json")
        for name in _doc.WORKSPACE_DIRS:
            (ctx.data_dir / name).mkdir()
        rc = _doc.run_doctor(["provider", "model", "runtime"], ctx=ctx)
        assert rc == 0

    def test_warn_rc0_with_mark(self, tmp_path, capsys):
        rc = _doc.run_doctor(["model"], ctx=make_ctx(tmp_path))
        assert rc == 0  # WARN 不改变退出码
        assert "⚠ 存在 WARN 项" in capsys.readouterr().out

    def test_fail_rc1(self, tmp_path, capsys):
        rc = _doc.run_doctor(["provider"], ctx=make_ctx(tmp_path))
        assert rc == 1


# ------------------------------------------------------------------ CLI 集成 (cli_factory 注册)


class TestCliIntegration:
    def test_parser_registers_doctor(self):
        parser = _cli.build_parser()
        args = parser.parse_args(["doctor"])
        assert args.command == "doctor"
        assert args.checker == []
        assert args.json is False
        assert args.verbose is False

    def test_cli_doctor_human_full(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        args = _cli.build_parser().parse_args(["doctor"])
        rc = cli.run(args)
        out = capsys.readouterr().out
        assert rc == 1  # 空环境 → provider FAIL
        assert "[FAIL] provider" in out
        assert "汇总:" in out

    def test_cli_doctor_json_structure(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        args = _cli.build_parser().parse_args(["doctor", "--json"])
        rc = cli.run(args)
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert set(data.keys()) == {"checks", "summary"}
        assert [c["id"] for c in data["checks"]] == BUILTIN_IDS

    def test_cli_doctor_single_checker(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        args = _cli.build_parser().parse_args(["doctor", "provider", "--json"])
        rc = cli.run(args)
        data = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert [c["id"] for c in data["checks"]] == ["provider"]

    def test_cli_doctor_unknown_checker_rc2(self, tmp_path, capsys):
        cli = make_cli(tmp_path)
        args = _cli.build_parser().parse_args(["doctor", "bogus"])
        rc = cli.run(args)
        assert rc == 2
        assert "未知检查器: bogus" in capsys.readouterr().err

    def test_cli_existing_commands_unaffected(self, tmp_path, capsys):
        """既有命令零改动: status 照常 rc 0 (doctor 注册不破坏其他命令)。"""
        cli = make_cli(tmp_path)
        for argv in (["status"], ["stop"]):
            args = _cli.build_parser().parse_args(argv)
            rc = cli.run(args)
            assert rc == 0, f"command {argv} regressed"


class TestOutputInfo:
    """2026-08-19: doctor 信息量增强 (版本/关于/数据目录/下一步)。"""

    def test_human_output_has_version_about_and_next(self, tmp_path, capsys):
        rc = _doc.run_doctor(["provider"], ctx=make_ctx(tmp_path))
        out = capsys.readouterr().out
        assert rc == 1
        assert "版本: v" in out
        assert "关于: AI Software Factory" in out
        assert "数据目录:" in out
        assert "下一步:" in out
        assert "factory init" in out
        assert "factory start" in out
        assert "factory status" in out

    def test_doctor_version_reads_single_source(self):
        v = _doc._doctor_version()
        assert v and v != "未知"
        assert v.count(".") >= 1

    def test_double_dash_doctor_alias(self, monkeypatch, tmp_path, capsys):
        """factory --doctor (用户把子命令当 flag) → 等价 doctor。"""
        monkeypatch.setenv("HOME", str(tmp_path))
        rc = _cli.main(["--doctor"])
        out = capsys.readouterr().out
        assert "AI Factory Doctor" in out
        assert rc in (0, 1)  # 空环境 provider FAIL → 1; 有配置 → 0
