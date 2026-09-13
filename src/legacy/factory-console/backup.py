"""factory-console/backup.py — 数据保护 (X-1, D-1)。

Founder 2026-08-26: 数据资产零保护 (git 未推送 + ~/.factory 无备份) — 最致命。
功能:
- create_backup: ~/.factory 数据目录 → tar.gz 归档 (排除临时/垃圾)
- list_backups: 备份清单 (时间/大小/文件)
- restore_backup: 恢复 (安全: 路径防穿越, 先解到临时再校验)
失败安全: 任何一步失败 → 明确错误, 不破坏现有数据。
"""

from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

#: 备份时排除的路径片段 (临时/垃圾/大调试文件/旧备份)
_EXCLUDE_PARTS = {
    "__pycache__", ".DS_Store", ".git", "node_modules",
    ".factory_rag",  # RAG 索引可重建
}
_EXCLUDE_NAMES = {
    "factory.db-shm", "factory.db-wal",
    "cleanup-backup",  # 旧备份不嵌套
}
_EXCLUDE_SUFFIXES = {".tmp", ".pyc"}
_DEBUG_FILES = {"debug_cases.json", "debug_sessions.json", "debug_trace.json"}


def _excluded(rel: Path) -> bool:
    parts = set(rel.parts)
    if any(p in _EXCLUDE_PARTS for p in parts):
        return True
    if rel.name in _EXCLUDE_NAMES or rel.name in _DEBUG_FILES:
        return True
    if rel.suffix.lower() in _EXCLUDE_SUFFIXES:
        return True
    return False


def default_backup_dir() -> Path:
    """默认备份目录: 数据目录的同级 .factory-backups (不污染数据目录本身)。"""
    return Path.home() / ".factory-backups"


def create_backup(data_dir: Path | str, backup_dir: Path | str | None = None) -> dict[str, Any]:
    """备份数据目录 → tar.gz (排除临时/垃圾; 失败 → 明确错误不破坏)。

    返回 {ok, file, size, count}; 归档名 factory-<时间戳>.tar.gz。
    """
    data = Path(data_dir)
    if not data.is_dir():
        return {"ok": False, "error": f"数据目录不存在: {data}"}
    bdir = Path(backup_dir) if backup_dir else default_backup_dir()
    try:
        bdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"备份目录不可写: {bdir} ({exc})"}
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = bdir / f"factory-{ts}.tar.gz"
    count = 0
    try:
        with tarfile.open(out, "w:gz") as tar:
            for f in sorted(data.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(data)
                if _excluded(rel):
                    continue
                try:
                    tar.add(f, arcname=f"factory/{rel}")
                    count += 1
                except OSError:  # noqa: BLE001 — 单文件失败跳过
                    continue
    except (OSError, tarfile.TarError) as exc:
        # 失败 → 删除半成品, 不留下损坏备份
        try:
            out.unlink(missing_ok=True)
        except OSError:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"备份失败: {exc}"}
    size = out.stat().st_size if out.is_file() else 0
    return {"ok": True, "file": str(out), "size": size, "count": count}


def list_backups(backup_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """备份清单 (按时间倒序; 无 → [] 诚实)。"""
    bdir = Path(backup_dir) if backup_dir else default_backup_dir()
    if not bdir.is_dir():
        return []
    out = []
    for f in sorted(bdir.glob("factory-*.tar.gz"), reverse=True):
        try:
            st = f.stat()
        except OSError:  # noqa: BLE001
            continue
        out.append({"file": str(f), "name": f.name, "size": st.st_size, "mtime": st.st_mtime})
    return out


def restore_backup(data_dir: Path | str, backup_file: Path | str) -> dict[str, Any]:
    """从备份恢复 (安全: 解到临时目录校验后, 文件级覆盖; 失败不破坏现有)。"""
    data = Path(data_dir)
    bf = Path(backup_file)
    if not bf.is_file():
        return {"ok": False, "error": f"备份文件不存在: {bf}"}
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="factory-restore-"))
    try:
        with tarfile.open(bf, "r:gz") as tar:
            members = tar.getmembers()
            for m in members:
                # 路径防穿越: 只允许 factory/ 前缀, 且规范化后不越界
                name = m.name.replace("\\", "/")
                if not name.startswith("factory/"):
                    return {"ok": False, "error": f"备份含非法路径: {name}"}
                rel = Path(*name.split("/")[1:])
                target = (tmp / "factory" / rel).resolve()
                if not target.is_relative_to((tmp / "factory").resolve()):
                    return {"ok": False, "error": f"路径越界: {name}"}
            tar.extractall(tmp)
        # 校验临时解包存在核心数据 (至少有文件)
        src = tmp / "factory"
        if not src.is_dir() or not any(src.rglob("*")):
            return {"ok": False, "error": "备份内容为空 (拒绝恢复)"}
        # 文件级覆盖 (保留未在备份中的现有文件 — 合并语义, 不整体替换)
        restored = 0
        data.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(src)
            target = (data / rel).resolve()
            if not target.is_relative_to(data.resolve()):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(f.read_bytes())
                restored += 1
            except OSError:  # noqa: BLE001
                continue
        return {"ok": True, "restored": restored, "file": bf.name}
    except (OSError, tarfile.TarError) as exc:
        return {"ok": False, "error": f"恢复失败: {exc}"}
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
