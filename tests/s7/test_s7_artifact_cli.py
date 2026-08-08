"""tests/s7/test_s7_artifact_cli.py — factory-org artifact CLI (Integration, ADR-0039)。

覆盖 (任务清单: CLI artifact 子命令 create/get/list/update/archive/validate/query):
- create: 人类输出 + --json 形状 + 全字段 + 关联校验失败 rc 7/rc 1
  + 未知类型 argparse SystemExit(2)
- get: 详情 + org.artifact.viewed 审计 + 未找到 rc 7
- list/query: 组合过滤 + viewed 事件 + 软删默认隐藏 / --include-archived
- update: 字段更新 + org.artifact.updated + archived 不可改 rc 1
- archive: 软删 + org.artifact.archived + 从 list 消失
- validate: 失败 → invalid (rc 0, result.ok=False, org.artifact.failed);
  已 generated 产物经 CLI 校验通过 → validated; created 直接校验 → rc 1

依赖: 本目录 conftest (sys.path 挂 factory-core + factory-org + factory-exec)。
"""

from __future__ import annotations

import contextlib
import io
import json as _json
from pathlib import Path

import pytest

from events.store import EventStore


def run_cli(root: Path, *argv: str) -> int:
    from org.cli import main

    return main(["--root", str(root), *argv])


def run_cli_json(root: Path, *argv: str) -> tuple[int, dict]:
    from org.cli import main

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["--root", str(root), "--json", *argv])
    return rc, _json.loads(buf.getvalue())


def cli_event_types(root: Path) -> list[str]:
    store = EventStore(root / "factory.db")
    try:
        return [e.type.value for e in store.query()]
    finally:
        store.close()


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """CLI 工厂根 (root/org 数据空间 + root/factory.db 事件库)。"""
    return tmp_path / "factory"


def _seed_stage_cli(root: Path) -> str:
    """种子: 经 ProjectLifecycle 直接落库 STG-1 (org CLI 无 stage 子命令)。"""
    from org.projects import ProjectLifecycle, ProjectStore

    store = ProjectStore(root / "org")
    ProjectLifecycle(store).create_stage("WF-1", "developer", stage_id="STG-1")
    return "STG-1"


class TestCliCreate:
    def test_create_human_output(self, cli_root, capsys):
        _seed_stage_cli(cli_root)
        rc = run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        out = capsys.readouterr().out
        assert rc == 0
        assert "✔ 产物创建成功" in out
        assert "A-1" in out
        assert "prd" in out
        assert "created" in out

    def test_create_json_shape(self, cli_root):
        _seed_stage_cli(cli_root)
        rc, data = run_cli_json(
            cli_root, "artifact", "create", "--stage", "STG-1",
            "--type", "code", "--id", "A-1", "--version", "2",
            "--metadata", '{"files": ["a.py"], "changes": "x"}',
        )
        assert rc == 0
        assert data["ok"] is True
        assert data["artifact"]["id"] == "A-1"
        assert data["artifact"]["type"] == "code"
        assert data["artifact"]["status"] == "created"
        assert data["artifact"]["version"] == "2"
        assert data["artifact"]["metadata"] == {"files": ["a.py"], "changes": "x"}
        assert data["event_seq"] == 1

    def test_create_full_fields(self, cli_root):
        _seed_stage_cli(cli_root)
        from org.projects import ProjectLifecycle, ProjectStore

        store = ProjectStore(cli_root / "org")
        plife = ProjectLifecycle(store)
        plife.create_project("P", project_id="P-1")
        plife.link_task("P-1", "T-1")
        rc, data = run_cli_json(
            cli_root, "artifact", "create", "--stage", "STG-1", "--type", "release",
            "--project", "P-1", "--task", "T-1", "--producer-role", "tester",
            "--producer-agent", "ag-1", "--ref", "ref://r", "--location", "file:///dist",
            "--version", "1.0.0", "--id", "A-1",
        )
        assert rc == 0
        a = data["artifact"]
        assert a["project_id"] == "P-1"
        assert a["task_id"] == "T-1"
        assert a["producer_role"] == "tester"
        assert a["version"] == "1.0.0"

    def test_create_unknown_stage_rc7(self, cli_root):
        rc, data = run_cli_json(cli_root, "artifact", "create", "--stage", "STG-999", "--type", "prd")
        assert rc == 7
        assert "stage not found" in data["error"]

    def test_create_unknown_role_rc1(self, cli_root):
        _seed_stage_cli(cli_root)
        rc, data = run_cli_json(
            cli_root, "artifact", "create", "--stage", "STG-1",
            "--type", "prd", "--producer-role", "bogus",
        )
        assert rc == 1
        assert "unknown role" in data["error"]

    def test_create_invalid_type_usage_error(self, cli_root):
        """argparse choices 校验失败 → SystemExit(2) (用法错误)。"""
        _seed_stage_cli(cli_root)
        from org.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["--root", str(cli_root), "artifact", "create", "--stage", "STG-1", "--type", "bogus"])
        assert exc.value.code == 2


class TestCliGetListQuery:
    def test_get_and_viewed_event(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        rc, data = run_cli_json(cli_root, "artifact", "get", "A-1")
        assert rc == 0
        assert data["artifact"]["id"] == "A-1"
        assert "org.artifact.viewed" in cli_event_types(cli_root)

    def test_get_not_found_rc7(self, cli_root):
        rc, data = run_cli_json(cli_root, "artifact", "get", "A-999")
        assert rc == 7
        assert "artifact not found" in data["error"]

    def test_list_filters_and_viewed(self, cli_root):
        _seed_stage_cli(cli_root)
        from org.projects import ProjectLifecycle, ProjectStore

        store = ProjectStore(cli_root / "org")
        ProjectLifecycle(store).create_project("P", project_id="P-1")
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--project", "P-1", "--id", "A-1")
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "design", "--id", "A-2")
        rc, data = run_cli_json(cli_root, "artifact", "list", "--project", "P-1")
        assert rc == 0
        assert data["count"] == 1
        assert data["artifacts"][0]["id"] == "A-1"
        assert "org.artifact.viewed" in cli_event_types(cli_root)

    def test_query_by_type_and_status(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "design", "--id", "A-2")
        rc, data = run_cli_json(cli_root, "artifact", "query", "--type", "design")
        assert rc == 0
        assert [a["id"] for a in data["artifacts"]] == ["A-2"]

    def test_list_hides_archived_and_include_flag(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "design", "--id", "A-2")
        # CREATED 不能直接 ARCHIVED — 经 API 走受控链 (→validated) 后 CLI archive
        from org.artifact import ArtifactRegistry
        from org.projects import ProjectStore

        reg = ArtifactRegistry(ProjectStore(cli_root / "org"))
        reg.mark_generated("A-2")
        reg.validate("A-2", payload={"architecture": "a", "api": "b", "database": "c"})
        rc, _ = run_cli_json(cli_root, "artifact", "archive", "A-2")
        assert rc == 0
        _, data = run_cli_json(cli_root, "artifact", "list")
        assert [a["id"] for a in data["artifacts"]] == ["A-1"]
        _, data2 = run_cli_json(cli_root, "artifact", "list", "--include-archived")
        assert [a["id"] for a in data2["artifacts"]] == ["A-1", "A-2"]
        _, data3 = run_cli_json(cli_root, "artifact", "query", "--status", "archived")
        assert [a["id"] for a in data3["artifacts"]] == ["A-2"]


class TestCliUpdateArchiveValidate:
    def test_update(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        rc, data = run_cli_json(cli_root, "artifact", "update", "A-1", "--version", "3", "--location", "file:///x")
        assert rc == 0
        assert data["artifact"]["version"] == "3"
        assert "org.artifact.updated" in cli_event_types(cli_root)

    def test_update_archived_rc1(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        from org.projects import ArtifactStatus
        from org.artifact import ArtifactRegistry
        from org.projects import ProjectStore

        registry = ArtifactRegistry(ProjectStore(cli_root / "org"))
        registry.mark_generated("A-1")
        registry.validate("A-1", payload={"problem": "p", "user": "u", "features": ["f"]})
        registry.archive("A-1")
        assert registry.get("A-1").status == ArtifactStatus.ARCHIVED
        rc, data = run_cli_json(cli_root, "artifact", "update", "A-1", "--version", "2")
        assert rc == 1
        assert "immutable" in data["error"]

    def test_archive_soft_delete(self, cli_root):
        _seed_stage_cli(cli_root)
        from org.artifact import ArtifactRegistry
        from org.projects import ProjectStore

        # created 产物先经 API 走受控链 (→validated) — CLI archive 测软删语义
        reg = ArtifactRegistry(ProjectStore(cli_root / "org"))
        reg.create("STG-1", "prd", artifact_id="A-1")
        reg.mark_generated("A-1")
        reg.validate("A-1", payload={"problem": "p", "user": "u", "features": ["f"]})
        rc, data = run_cli_json(cli_root, "artifact", "archive", "A-1")
        assert rc == 0
        assert data["artifact"]["status"] == "archived"
        assert "org.artifact.archived" in cli_event_types(cli_root)

    def test_validate_failure_to_invalid(self, cli_root):
        _seed_stage_cli(cli_root)
        run_cli(
            cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd",
            "--id", "A-1", "--metadata", '{"problem": "p"}',
        )
        rc, data = run_cli_json(cli_root, "artifact", "validate", "A-1")
        assert rc == 0  # 操作本身合法 (校验失败 → invalid 是受控结果)
        assert data["result"]["ok"] is False
        assert data["artifact"]["status"] == "invalid"
        assert data["result"]["missing"] == ["user", "features"]
        assert "org.artifact.failed" in cli_event_types(cli_root)

    def test_validate_success_after_generated(self, cli_root):
        """种子经 API 置 generated 后, CLI validate 通过 → validated。"""
        _seed_stage_cli(cli_root)
        from org.artifact import ArtifactRegistry
        from org.projects import ProjectStore

        store = ProjectStore(cli_root / "org")
        ArtifactRegistry(store).create(
            "STG-1", "prd", artifact_id="A-1",
            metadata={"problem": "p", "user": "u", "features": ["f1"]},
        )
        ArtifactRegistry(store).mark_generated("A-1")
        rc, data = run_cli_json(cli_root, "artifact", "validate", "A-1")
        assert rc == 0
        assert data["result"]["ok"] is True
        assert data["artifact"]["status"] == "validated"
        assert "org.artifact.validated" in cli_event_types(cli_root)

    def test_validate_created_without_generate_rc1(self, cli_root):
        """CREATED 直接校验 (合法载荷) → 非法跳转 rc 1 (受控转换表)。"""
        _seed_stage_cli(cli_root)
        run_cli(
            cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd",
            "--id", "A-1", "--metadata", '{"problem": "p", "user": "u", "features": ["f1"]}',
        )
        rc, data = run_cli_json(cli_root, "artifact", "validate", "A-1")
        assert rc == 1
        assert "invalid artifact transition" in data["error"]

    def test_validate_explicit_payload_flag(self, cli_root):
        """--payload 显式载荷 (缺省用 metadata 之外的另一入口)。"""
        _seed_stage_cli(cli_root)
        run_cli(cli_root, "artifact", "create", "--stage", "STG-1", "--type", "prd", "--id", "A-1")
        rc, data = run_cli_json(
            cli_root, "artifact", "validate", "A-1",
            "--payload", '{"problem": "p", "user": "u", "features": []}',
        )
        assert rc == 0
        assert data["result"]["ok"] is False
        assert data["artifact"]["status"] == "invalid"
        assert any("features" in e for e in data["result"]["errors"])
