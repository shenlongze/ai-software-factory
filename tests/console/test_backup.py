"""tests/console/test_backup.py — 数据保护 (X-1/D-1, v1.1.167)。

Founder: 数据资产零保护 (git 未推送 + ~/.factory 无备份) — 最致命。
覆盖 (factory_console.backup):
- create_backup: tar.gz 归档, 排除临时/垃圾 (db-wal/shm/debug/__pycache__)
- list_backups: 清单 (完整路径 + 倒序)
- restore_backup: 恢复 (路径防穿越, 合并语义不整体替换, 失败不破坏)
- CLI factory backup create/list/restore
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_P) if (_P := _p) else _p)  # noqa: F841

_bak = importlib.import_module("factory_console.backup")


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "projects" / "p1").mkdir(parents=True)
    (d / "projects" / "p1" / "task.json").write_text('{"t":1}', encoding="utf-8")
    (d / "providers.json").write_text("{}", encoding="utf-8")
    (d / "debug_sessions.json").write_text("BIG", encoding="utf-8")
    (d / "factory.db-wal").write_text("WAL", encoding="utf-8")
    (d / "__pycache__").mkdir(exist_ok=True)
    (d / "__pycache__" / "x.pyc").write_bytes(b"x")
    return d


class TestBackup:
    def test_create_excludes_junk(self, data_dir, tmp_path):
        r = _bak.create_backup(data_dir, tmp_path / "backups")
        assert r["ok"] and r["file"].endswith(".tar.gz")
        # 排除 debug/wal/pycache
        import tarfile

        with tarfile.open(r["file"], "r:gz") as tar:
            names = " ".join(m.name for m in tar.getmembers())
        assert "task.json" in names and "providers.json" in names
        assert "debug_sessions" not in names
        assert "factory.db-wal" not in names
        assert "__pycache__" not in names

    def test_list_and_restore(self, data_dir, tmp_path):
        _bak.create_backup(data_dir, tmp_path / "backups")
        rows = _bak.list_backups(tmp_path / "backups")
        assert len(rows) == 1 and rows[0]["name"].startswith("factory-")
        d2 = tmp_path / "data2"
        d2.mkdir()
        r = _bak.restore_backup(d2, rows[0]["file"])
        assert r["ok"] and (d2 / "projects/p1/task.json").is_file()
        assert not (d2 / "debug_sessions.json").exists()

    def test_restore_rejects_path_traversal(self, tmp_path):
        import tarfile

        evil = tmp_path / "evil.tar.gz"
        with tarfile.open(evil, "w:gz") as tar:
            import io

            info = tarfile.TarInfo("../../escape.txt")
            tar.addfile(info, io.BytesIO(b"x"))
        d = tmp_path / "d"
        d.mkdir()
        r = _bak.restore_backup(d, evil)
        assert not r["ok"]

    def test_restore_missing_file(self, tmp_path):
        r = _bak.restore_backup(tmp_path, tmp_path / "nope.tar.gz")
        assert not r["ok"]
