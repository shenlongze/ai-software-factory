"""test_store.py — WorkspaceStore 原子持久化 (Phase 6A, ADR-0016)。

覆盖: 写读往返 / 原子写 (无 .tmp 残留) / 覆盖 / 缺失与损坏报错 /
位置约定 (<root>/workspace.yaml)。
"""

from __future__ import annotations

import pytest

from workspace.config import WorkspaceConfig, WorkspaceNotFoundError
from workspace.store import WorkspaceStore


@pytest.fixture
def store(tmp_path) -> WorkspaceStore:
    return WorkspaceStore(tmp_path)


class TestWorkspaceStore:
    def test_path_convention(self, tmp_path, store):
        assert store.path == tmp_path / "workspace.yaml"

    def test_save_creates_file(self, store):
        store.save(WorkspaceConfig(name="w", projects=["markpad"]))
        assert store.path.is_file()
        assert "name: w" in store.path.read_text(encoding="utf-8")

    def test_save_atomic_no_tmp_left(self, store):
        store.save(WorkspaceConfig(name="w"))
        leftovers = [p.name for p in store.root.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_save_creates_parent_dirs(self, tmp_path, store):
        nested = WorkspaceStore(tmp_path / "a" / "b")
        nested.save(WorkspaceConfig(name="w"))
        assert (tmp_path / "a" / "b" / "workspace.yaml").is_file()

    def test_load_roundtrip(self, store):
        store.save(WorkspaceConfig(name="w", projects=["markpad", "timeon"]))
        c = store.load()
        assert c.name == "w"
        assert c.projects == ["markpad", "timeon"]

    def test_load_missing_raises_not_found(self, store):
        with pytest.raises(WorkspaceNotFoundError):
            store.load()

    def test_load_corrupt_raises_config_error(self, store):
        store.path.write_text("name: [broken\n", encoding="utf-8")
        with pytest.raises(Exception) as exc:
            store.load()
        from workspace.config import WorkspaceConfigError
        assert isinstance(exc.value, WorkspaceConfigError)

    def test_exists_false_initial(self, store):
        assert store.exists() is False

    def test_exists_true_after_save(self, store):
        store.save(WorkspaceConfig(name="w"))
        assert store.exists() is True

    def test_save_overwrites_existing(self, store):
        store.save(WorkspaceConfig(name="w1", projects=["markpad"]))
        store.save(WorkspaceConfig(name="w2", projects=["timeon"]))
        c = store.load()
        assert c.name == "w2"
        assert c.projects == ["timeon"]
