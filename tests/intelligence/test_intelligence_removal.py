"""tests/intelligence/test_intelligence_removal.py — Removal Isolation (Phase 10A-1)。

覆盖 (工程规则: 删除 intelligence/ 系统仍运行; Core 零感知):
1. 源码级: Core 各模块零 imports intelligence (Core 不感知 Extension)。
2. 源码级: store.py 零顶层 imports events/product/providers/runtime (纯 stdlib
   + 公共接口); models.py 零 imports product/providers/runtime。
3. 运行期: 模拟删除 intelligence 包 (monkeypatch builtins.__import__ 抛
   ImportError) → Core 模块正常导入/工作。
4. 数据空间隔离: 删除 <root>/intelligence/ 数据空间不影响 Core store 数据。
5. intelligence 包独立可导入 (不依赖 CLI/dashboard 装配)。
"""

from __future__ import annotations

import builtins
import inspect
import re
from pathlib import Path

from events.models import Event, EventType
from events.store import EventStore

from intelligence import Decision, DecisionStore, Recommendation, RecommendationStore
from intelligence.store import ExperienceStore

from intelligence_helpers import make_decision, make_experience, make_recommendation


# ------------------------------------------------------------------ 源码级隔离


def _core_py_files() -> list[Path]:
    """factory-core 下除 intelligence/ 外的全部 .py 文件。"""
    root = Path(__file__).resolve().parents[2] / "factory-core"
    return [
        p
        for p in root.rglob("*.py")
        if "intelligence" not in p.parts and "__pycache__" not in p.parts
    ]


class TestCoreDoesNotImportIntelligence:
    def test_no_core_module_imports_intelligence(self):
        """Core 零感知: 任何 Core 模块源码无 import intelligence (含注释外注释,
        只查 import 语句 — 文档里 "Intelligence" 单词不算)。"""
        pattern = re.compile(r"(?m)^\s*(?:import intelligence\b|from intelligence\b)")
        offenders = []
        for p in _core_py_files():
            if pattern.search(p.read_text(encoding="utf-8")):
                offenders.append(str(p))
        assert offenders == []

    def test_intelligence_dir_not_imported_by_cli(self):
        """CLI 装配零引用 (10A-1 无 CLI 命令, 10A-5 接入时才需延迟导入)。"""
        root = Path(__file__).resolve().parents[2] / "factory-core" / "cli"
        pattern = re.compile(r"(?m)^\s*(?:import intelligence\b|from intelligence\b)")
        for p in root.rglob("*.py"):
            assert not pattern.search(p.read_text(encoding="utf-8")), p


class TestStoreZeroTopLevelDependencies:
    def test_store_no_top_level_events_import(self):
        """store.py 零顶层 imports events (Removal Isolation, 同 provider/product 模式)。"""
        import intelligence.store as store_module

        src = inspect.getsource(store_module)
        assert not re.search(r"(?m)^(?:import events\b|from events\b)", src)

    def test_store_no_product_providers_runtime_imports(self):
        import intelligence.store as store_module

        src = inspect.getsource(store_module)
        for mod in ("product", "providers", "runtime", "runtimes", "tasks", "workflows"):
            assert not re.search(
                rf"(?m)^(?:import {mod}\b|from {mod}\b)", src
            ), f"store.py must not import {mod}"

    def test_models_no_product_providers_runtime_imports(self):
        import intelligence.models as models_module

        src = inspect.getsource(models_module)
        for mod in ("product", "providers", "runtime", "runtimes", "tasks", "workflows"):
            assert not re.search(
                rf"(?m)^(?:import {mod}\b|from {mod}\b)", src
            ), f"models.py must not import {mod}"
        # models.py 允许 import events.models (Core 公共接口, 时间戳格式复用)

    def test_events_helper_imports_only_events(self):
        import intelligence.events as events_module

        src = inspect.getsource(events_module)
        imports = re.findall(r"(?m)^(?:import (\w+)|from (\w+) import)", src)
        top_modules = {a or b for a, b in imports}
        assert top_modules <= {"events", "typing", "__future__"}


# ------------------------------------------------------------------ 运行期隔离 (模拟删包)


class TestSimulatedDeletion:
    def test_core_imports_work_without_intelligence(self, monkeypatch):
        """模拟删除 intelligence 包: Core 模块导入与工作零影响。"""
        orig = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "intelligence" or name.startswith("intelligence."):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        import events.logger
        import events.models
        import events.store
        import product.models
        import providers.models
        import tasks.store
        import workflows.models

        assert events.models.EventType.TASK_START.value == "task.start"
        assert events.models.EventType.INTELLIGENCE_VIEWED.value == "intelligence.viewed"

    def test_import_intelligence_fails_cleanly_when_removed(self, monkeypatch):
        """删包后 import intelligence 抛 ImportError (而非挂起/半初始化)。"""
        orig = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "intelligence" or name.startswith("intelligence."):
                raise ImportError(f"No module named {name!r} (simulated removal)")
            return orig(name, globals, locals, fromlist, level)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        import pytest

        with pytest.raises(ImportError):
            import intelligence  # noqa: F401


# ------------------------------------------------------------------ 数据空间隔离


class TestDataSpaceIsolation:
    def test_deleting_intelligence_dir_does_not_affect_event_store(self, tmp_path: Path):
        """删除 <root>/intelligence/ 数据空间: Core 事件库 (events.db) 零影响。"""
        root = tmp_path / "factory"
        idir = root / "intelligence"
        DecisionStore(idir).save(make_decision())
        RecommendationStore(idir).save(make_recommendation())
        ExperienceStore(idir).save(make_experience())

        db = root / "events.db"
        store = EventStore(db)
        store.append(Event.create("task.start", source="test"))
        assert store.count() == 1
        store.close()

        # 删除 intelligence 数据空间
        import shutil

        shutil.rmtree(idir)
        assert not idir.exists()

        # Core 事件库照常读
        reopened = EventStore(db)
        assert reopened.count() == 1
        assert reopened.query()[0].type == EventType.TASK_START
        reopened.close()
        # 工厂根只残留 Core 数据 (无 intelligence 残留)
        assert sorted(p.name for p in root.iterdir()) == ["events.db"]

    def test_intelligence_dir_is_self_contained(self, tmp_path: Path):
        """数据空间自包含: <root>/intelligence/ 下只有本层三个 JSON 文件。"""
        root = tmp_path / "factory"
        idir = root / "intelligence"
        DecisionStore(idir).save(make_decision())
        assert sorted(p.name for p in idir.iterdir()) == ["decisions.json"]
        RecommendationStore(idir).save(make_recommendation())
        ExperienceStore(idir).save(make_experience())
        assert sorted(p.name for p in idir.iterdir()) == [
            "decisions.json",
            "experiences.json",
            "recommendations.json",
        ]
        assert root.exists()  # 目录树只在本层创建


# ------------------------------------------------------------------ 独立可导入


class TestStandalonePackage:
    def test_intelligence_importable_without_cli_dashboard(self):
        """intelligence 包独立可导入 (零装配依赖)。"""
        import intelligence
        import intelligence.events
        import intelligence.store

        assert intelligence.Decision is Decision
        assert intelligence.DecisionStore is DecisionStore
        assert intelligence.RecommendationStore is RecommendationStore

    def test_init_exports(self):
        import intelligence

        assert intelligence.__all__
        for name in intelligence.__all__:
            assert hasattr(intelligence, name), name

    def test_store_usable_without_event_logger(self, tmp_path: Path):
        """纯存储场景不依赖事件系统 (logger 可缺省 — 事件是附加审计)。"""
        store = DecisionStore(tmp_path / "factory" / "intelligence")
        d = make_decision()
        store.save(d)
        assert store.get(d.id).subject_id == "task-1"
        # 不触碰事件库: 数据空间内只有 decisions.json
        assert sorted(p.name for p in (tmp_path / "factory" / "intelligence").iterdir()) == [
            "decisions.json"
        ]
