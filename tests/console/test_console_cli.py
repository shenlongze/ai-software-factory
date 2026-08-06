"""tests/console/test_console_cli.py — factory console CLI (Phase 11A, ADR-0034)。

覆盖:
- console dashboard: 文本七域汇总输出 / --json 结构 / --limit 截断
- console approvals: 文本清单 / --json / --pending 只列待办
- 退出码: 正常 rc 0; 未知子命令 rc 2; factory-console 缺失响亮 rc 7
  (Removal Isolation — 删除 console 包不影响其余命令)
- 有数据工厂: 各域计数正确投影 (真实 store 种子)
- 只读铁律: 读命令不写任何数据文件 (事件库 factory.db 为唯一允许的写)

basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import json

import pytest

from events.store import EventStore

from intelligence.store import DecisionStore

from product.store import ProductStore

from console_helpers import (
    make_artifact,
    make_decision,
    make_idea,
    make_request,
    make_usage,
)
from providers.usage import UsageStore


def _run(root, *argv) -> int:
    from cli.main import main

    return main(["--root", str(root), *argv])


def _seed_factory(root):
    """种子: 1 idea + 1 artifact + 2 requests (1 pending) + 1 decision + 1 usage。"""
    product = ProductStore(root / "product")
    product.save_idea(make_idea(idea_id="idea-1", project_id="demo"))
    product.save_artifact(make_artifact(artifact_id="art-1", idea_id="idea-1"))
    product.save_request(make_request(request_id="req-1", artifact_id="art-1",
                                      idea_id="idea-1", status="pending"))
    product.save_request(make_request(request_id="req-2", artifact_id="art-1",
                                      idea_id="idea-1", status="approved"))
    decisions = DecisionStore(root / "intelligence")
    decisions.save(make_decision())
    usage = UsageStore(root / "providers")
    usage.record(make_usage(provider_id="hermes", estimated_cost=0.01, success=True))
    return product, decisions, usage


# ------------------------------------------------------------------ dashboard


class TestDashboardText:
    def test_seven_domain_summary_output(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "dashboard")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Human Console — Dashboard 七域汇总 (只读)" in out
        assert "项目" in out
        assert "待审批" in out
        assert "运行中 Agent" in out
        assert "最近决策" in out
        assert "成本" in out
        assert "经验" in out
        assert "最近活动" in out
        assert "console.dashboard.viewed seq=" in out

    def test_counts_reflect_seeded_data(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        _run(tmp_path, "console", "dashboard")
        out = capsys.readouterr().out
        assert "待审批      1  (共 2)" in out
        assert "最近决策    1" in out
        assert "$0.010000  (1 calls)" in out
        assert "最近活动    0 条" in out


class TestDashboardJson:
    def test_json_structure(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "dashboard", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["event"] == "console.dashboard.viewed"
        assert isinstance(data["event_seq"], int)
        d = data["dashboard"]
        # 七域全部出现 (SECTIONS 键序)
        assert list(d.keys()) == [
            "projects", "approvals", "agents", "decisions", "cost",
            "experience", "activity",
        ]
        assert isinstance(d["projects"], list)  # workspace 内置示例项目可能非空
        assert d["cost"]["calls"] == 0
        assert d["experience"]["total"] == 0
        assert d["activity"] == []

    def test_json_counts_with_data(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        _run(tmp_path, "console", "dashboard", "--json")
        d = json.loads(capsys.readouterr().out)["dashboard"]
        assert len(d["approvals"]) == 2
        assert len(d["decisions"]) == 1
        assert d["cost"]["calls"] == 1
        assert d["cost"]["total_cost"] == 0.01

    def test_limit_truncates_decisions(self, tmp_path, capsys):
        decisions = DecisionStore(tmp_path / "intelligence")
        for i in range(5):
            decisions.save(make_decision(
                decision_id=f"dec-{i}",
                created_at=f"2026-01-0{i + 1}T00:00:00.000000Z",
            ))
        _run(tmp_path, "console", "dashboard", "--limit", "2", "--json")
        d = json.loads(capsys.readouterr().out)["dashboard"]
        assert len(d["decisions"]) == 2
        assert d["decisions"][0]["id"] == "dec-4"  # 最近优先


# ------------------------------------------------------------------ approvals


class TestApprovalsText:
    def test_table_and_count_line(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Request" in out
        assert "req-1" in out
        assert "req-2" in out
        assert "2 approvals (pending: 1)" in out
        assert "console.viewed seq=" in out
        assert "view=approvals" in out

    def test_empty_factory_rc0(self, tmp_path, capsys):
        rc = _run(tmp_path, "console", "approvals")
        out = capsys.readouterr().out
        assert rc == 0
        assert "0 approvals (pending: 0)" in out


class TestApprovalsJson:
    def test_json_structure(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["pending"] == 1
        assert data["pending_only"] is False
        assert data["event"] == "console.viewed"
        assert [a["id"] for a in data["approvals"]] == ["req-1", "req-2"]
        a = data["approvals"][0]
        assert a["artifact_id"] == "art-1"
        assert a["gate"] == "prd"
        assert a["status"] == "pending"

    def test_pending_only_filters(self, tmp_path, capsys):
        _seed_factory(tmp_path)
        rc = _run(tmp_path, "console", "approvals", "--pending", "--json")
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["pending_only"] is True
        assert data["count"] == 1
        assert [a["id"] for a in data["approvals"]] == ["req-1"]


# ------------------------------------------------------------------ 退出码 / 缺失包


class TestExitCodes:
    def test_unknown_console_subcommand_rc2(self, tmp_path, capsys):
        """非法子命令 → argparse SystemExit(2) (入口契约, 同 recommend CLI 模式)。"""
        with pytest.raises(SystemExit) as exc:
            _run(tmp_path, "console", "bogus")
        assert exc.value.code == 2

    def test_console_missing_package_rc7(self, tmp_path, capsys, monkeypatch):
        """模拟删除 factory-console/ 包: dashboard 响亮 rc 7 (Removal Isolation)。"""
        orig = importlib.import_module

        def fake_import(name, package=None):
            if name == "factory-console" or name.startswith("factory-console"):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, package)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        rc = _run(tmp_path, "console", "dashboard")
        assert rc == 7
        err = capsys.readouterr().err
        assert "factory-console 未安装" in err

    def test_other_commands_unaffected_without_console(self, tmp_path, capsys, monkeypatch):
        """删除 console 包 → init/task 等其余命令零影响 (rc 0)。"""
        orig = importlib.import_module

        def fake_import(name, package=None):
            if name == "factory-console" or name.startswith("factory-console"):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, package)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        assert _run(tmp_path, "init") == 0
        assert _run(tmp_path, "task", "create", "--title", "t1",
                    "--project", "demo") == 0

    def test_dashboard_rc0_on_empty_factory(self, tmp_path, capsys):
        """空工厂 (无任何数据): dashboard rc 0 + 事件照常写 (审计不因空失败)。"""
        assert _run(tmp_path, "console", "dashboard") == 0
        db = EventStore(tmp_path / "factory.db")
        try:
            assert [e.type.value for e in db.query()] == ["console.dashboard.viewed"]
        finally:
            db.close()


# ------------------------------------------------------------------ 只读铁律 (CLI 层)


class TestCliReadOnly:
    def test_read_commands_write_no_domain_files(self, tmp_path, capsys):
        """console dashboard/approvals 前后, 除 factory.db 外数据空间零变化。"""
        _seed_factory(tmp_path)

        def domain_snapshot(root):
            """排除 *.db (事件库/审计库为唯一允许的写, sqlite 二进制)。"""
            out = {}
            for path in sorted(root.rglob("*")):
                if path.is_file() and path.suffix != ".db":
                    out[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
            return out

        before = domain_snapshot(tmp_path)
        _run(tmp_path, "console", "dashboard")
        _run(tmp_path, "console", "approvals", "--pending")
        after = domain_snapshot(tmp_path)
        assert after == before
