"""tests/understanding/test_understanding_cli.py — factory understand CLI (Phase 7, ADR-0021)。

覆盖: 文本报告 (阶段/基本信息/产物表/缺失/建议) / --json 结构化输出 /
--stage 仅阶段识别 / 退出码 (0 成功, 1 路径无效, 2 用法错误) / 审计事件
(understanding.started/completed source=understanding + understanding.viewed
source=cli — ADR-0002 读命令审计) / 只读 (分析不写任何文件)。
"""

from __future__ import annotations

import json

import pytest

from cli_helpers import event_types, open_events, run_cli
from events.models import EventType

from understanding_helpers import (
    code_project,
    complete_project,
    empty_project,
    make_project,
    ops_project,
    prd_project,
    readme_project,
    snapshot_tree,
)


class TestCliTextOutput:
    def test_full_report_text(self, capsys, tmp_path, cli_root):
        root = code_project(tmp_path / "proj")
        rc, out, err = run_cli(capsys, cli_root, "understand", str(root))
        assert rc == 0
        assert "✔ 项目理解报告" in out
        assert "DEVELOPMENT" in out
        assert "python" in out
        assert "Artifact" in out and "SOURCE_CODE" in out
        assert "补充 PRD 文档" in out  # 建议区

    def test_empty_project_text(self, capsys, tmp_path, cli_root):
        root = empty_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", str(root))
        assert rc == 0
        assert "IDEA" in out
        assert "confidence: 0.90" in out

    def test_full_operational_project(self, capsys, tmp_path, cli_root):
        root = complete_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", str(root))
        assert rc == 0
        assert "OPERATION" in out
        assert "已存在" in out and "(无)" in out  # 缺失为空

    def test_stage_only_text(self, capsys, tmp_path, cli_root):
        root = prd_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", "--stage", str(root))
        assert rc == 0
        assert "✔ 阶段识别: PRD" in out
        assert "artifact:PRD" in out
        assert "项目理解报告" not in out  # 无完整报告段

    def test_readme_project(self, capsys, tmp_path, cli_root):
        root = readme_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", str(root))
        assert rc == 0
        assert "PRD" in out and "planning" in out


class TestCliJson:
    def test_json_full_report(self, capsys, tmp_path, cli_root):
        root = code_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", "--json", str(root))
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["stage_only"] is False
        assert data["path"] == str(root)
        report = data["report"]
        assert report["stage"]["stage"] == "DEVELOPMENT"
        assert report["stage"]["confidence"] == 0.6
        assert report["missing"]["present"] == ["SOURCE_CODE"]
        assert len(report["artifacts"]) == 7
        assert "event_seq" in data

    def test_json_stage_only(self, capsys, tmp_path, cli_root):
        root = prd_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", "--json", "--stage", str(root))
        assert rc == 0
        data = json.loads(out)
        assert data["stage_only"] is True
        assert data["stage"]["stage"] == "PRD"
        assert "report" not in data

    def test_json_empty_project(self, capsys, tmp_path, cli_root):
        root = empty_project(tmp_path / "proj")
        rc, out, _ = run_cli(capsys, cli_root, "understand", "--json", str(root))
        assert rc == 0
        data = json.loads(out)
        assert data["report"]["stage"]["stage"] == "IDEA"
        assert len(data["report"]["next_actions"]) == 7


class TestCliExitCodes:
    def test_missing_path_rc1(self, capsys, tmp_path, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "understand", str(tmp_path / "nope"))
        assert rc == 1
        assert "path not found" in err or "path not found" in out

    def test_file_path_rc1(self, capsys, tmp_path, cli_root):
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        rc, out, err = run_cli(capsys, cli_root, "understand", str(f))
        assert rc == 1

    def test_missing_argument_usage_error(self, capsys, cli_root):
        # argparse 缺必选参数 → SystemExit(2) (main 直调, 非返回码)
        with pytest.raises(SystemExit) as exc:
            run_cli(capsys, cli_root, "understand")
        assert exc.value.code == 2


class TestCliEvents:
    def test_audit_event_sequence(self, capsys, tmp_path, cli_root):
        root = code_project(tmp_path / "proj")
        rc, _, _ = run_cli(capsys, cli_root, "understand", str(root))
        assert rc == 0
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert types[0] == "understanding.started"   # 服务层 (source=understanding)
        assert types[1] == "understanding.completed"
        assert types[-1] == "understanding.viewed"   # CLI 读命令审计 (source=cli)

    def test_viewed_payload_contract(self, capsys, tmp_path, cli_root):
        root = code_project(tmp_path / "proj")
        run_cli(capsys, cli_root, "understand", str(root))
        store = open_events(cli_root)
        evs = [e for e in store.query() if e.type == EventType.UNDERSTANDING_VIEWED]
        store.close()
        assert len(evs) == 1
        assert evs[0].source == "cli"
        payload = evs[0].payload
        assert payload["path"] == str(root)
        assert payload["stage"] == "DEVELOPMENT"
        assert payload["confidence"] == 0.6
        assert payload["artifacts_present"] == 1
        assert payload["artifacts_missing"] == 6

    def test_completed_event_from_cli(self, capsys, tmp_path, cli_root):
        root = prd_project(tmp_path / "proj")
        run_cli(capsys, cli_root, "understand", str(root))
        store = open_events(cli_root)
        evs = [e for e in store.query() if e.type == EventType.UNDERSTANDING_COMPLETED]
        store.close()
        assert evs[0].source == "understanding"
        assert evs[0].payload["stage"] == "PRD"

    def test_stage_only_also_audits(self, capsys, tmp_path, cli_root):
        root = prd_project(tmp_path / "proj")
        run_cli(capsys, cli_root, "understand", "--stage", str(root))
        store = open_events(cli_root)
        types = event_types(store)
        store.close()
        assert "understanding.started" in types
        assert "understanding.completed" in types
        assert "understanding.viewed" in types


class TestCliReadOnly:
    def test_cli_does_not_modify_project(self, capsys, tmp_path, cli_root):
        root = ops_project(tmp_path / "proj")
        before = snapshot_tree(root)
        run_cli(capsys, cli_root, "understand", str(root))
        run_cli(capsys, cli_root, "understand", "--json", str(root))
        assert snapshot_tree(root) == before

    def test_cli_creates_no_factory_state_for_project(self, capsys, tmp_path, cli_root):
        # 只读铁律: 分析项目目录, 工厂根只落事件库 (审计), 项目目录零写入
        root = make_project(tmp_path / "proj", {"docs/prd.md": "x"})
        run_cli(capsys, cli_root, "understand", str(root))
        assert (cli_root / "factory.db").exists()  # 审计事件落库
        assert snapshot_tree(root) == {"docs/prd.md": b"x"}
