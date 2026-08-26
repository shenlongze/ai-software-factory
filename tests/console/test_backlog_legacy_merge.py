"""tests/console/test_backlog_legacy_merge.py — legacy tasks.json 并入 backlog 树 (v1.1.188)。

Founder: 任务页空 — legacy 有完整 epics/tasks 树, 并入 backlog。
验证 service.list_backlog: 史诗→模块→故事→任务 四层树 (legacy + management 合并, 去重)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")


def _build_service(root: Path):
    return _adapter.build_console_service(root, event_logger=None)


def _seed_legacy(root: Path, project: str):
    pdir = root / "projects" / project
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "tasks.json").write_text(
        json.dumps(
            {
                "epics": ["M2", "M3"],
                "tasks": [
                    {"id": "M2-1", "name": "任务A", "epic": "M2", "feature": "M2", "status": "done"},
                    {"id": "M2-2", "name": "任务B", "epic": "M2", "feature": "M2", "status": "todo"},
                    {"id": "M3-1", "name": "任务C", "epic": "M3", "feature": "M3", "status": "todo"},
                ],
            }
        ),
        encoding="utf-8",
    )


class TestLegacyMerge:
    def test_list_backlog_merges_legacy_tree(self, tmp_path):
        _seed_legacy(tmp_path, "P-1")
        svc = _build_service(tmp_path)
        backlog = svc.list_backlog("P-1")
        assert backlog is not None
        epics = {e["id"] for e in backlog["epics"]}
        assert {"M2", "M3"} <= epics
        # 四层: epic → feature → story → task
        assert backlog["features"], "缺 features"
        assert backlog["stories"], "缺 stories (任务挂载层)"
        tasks = {t["id"] for t in backlog["tasks"]}
        assert {"M2-1", "M2-2", "M3-1"} <= tasks
        # story 挂任务 (M2 story 有 2 个任务)
        m2_story = next(s for s in backlog["stories"] if "M2" in s["id"])
        assert len(m2_story["children"]) == 2

    def test_legacy_parent_child_hierarchy_preserved(self, tmp_path):
        """Founder 2026-08-27: 主任务有未完成子任务 → 不拍平进 story, 层级保留。
        子任务挂主任务 children; story 只挂根任务 (主任务不归档, 树内聚合)。"""
        pdir = tmp_path / "projects" / "P-2"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "tasks.json").write_text(
            json.dumps(
                {
                    "epics": ["M2"],
                    "tasks": [
                        {"id": "M2-1", "name": "主任务", "epic": "M2", "feature": "M2", "status": "done"},
                        {"id": "M2-1-1", "name": "子任务A", "epic": "M2", "feature": "M2", "parent": "M2-1", "status": "todo"},
                        {"id": "M2-1-2", "name": "子任务B", "epic": "M2", "feature": "M2", "parent": "M2-1", "status": "todo"},
                        {"id": "M2-2", "name": "独立任务", "epic": "M2", "feature": "M2", "status": "done"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        svc = _build_service(tmp_path)
        backlog = svc.list_backlog("P-2")
        tasks = {t["id"]: t for t in backlog["tasks"]}
        # story 只挂根 (主任务 M2-1 + 独立 M2-2), 子任务不拍平进 story
        m2_story = next(s for s in backlog["stories"] if "M2" in s["id"])
        assert set(m2_story["children"]) == {"M2-1", "M2-2"}
        # 主任务带 children; 子任务不带 children
        assert set(tasks["M2-1"].get("children") or []) == {"M2-1-1", "M2-1-2"}
        assert "children" not in tasks["M2-1-1"]
        assert "children" not in tasks["M2-2"]

    def test_legacy_tree_no_duplicates(self, tmp_path):
        _seed_legacy(tmp_path, "P-1")
        svc = _build_service(tmp_path)
        backlog = svc.list_backlog("P-1")
        ids = [t["id"] for t in backlog["tasks"]]
        assert len(ids) == len(set(ids)), "合并后任务 id 重复"

    def test_merge_by_id_dedup(self):
        base = [{"id": "a"}, {"id": "b"}]
        extra = [{"id": "b"}, {"id": "c"}]
        merged = _adapter.build_console_service  # noqa: B018 (占位避免未用)
        svc = object.__new__(importlib.import_module("factory-console.service").ConsoleService)
        out = svc._merge_by_id(base, extra)
        assert [x["id"] for x in out] == ["a", "b", "c"]
