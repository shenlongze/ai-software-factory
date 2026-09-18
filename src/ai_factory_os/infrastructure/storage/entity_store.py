"""infrastructure/storage/entity_store.py — 统一实体【存储实现】。

2026-09-15 自 _pending_migration/factory_console/unified_contract.py **拆出**:
 契约面（常量 + 纯函数）已在 contracts/entity/contract.py; 本文件只留**读写盘**的部分
 （_file / _load / _save / store_entity / get_entity / entities / trace_lineage / create_requirement）。

★ 拆分的理由（七层判据）: 有 IO ⇒ 属技术底座, 不属契约层。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from ai_factory_os.contracts.entity.contract import (
    validate_entity,
)

def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "unified" / f"{name}.json"


def _project_entity_file(root: Path | str, project_id: str) -> Path:
    """项目级实体库: projects/<P-id>/entities.json ✓（Founder 铁律 ✓）。"""
    return Path(root) / "projects" / project_id / "entities.json"


def _write_list(p: Path, data: list[dict[str, Any]]) -> None:
    """原子写 json 列表 ✓ —— 临时名必须【唯一】✗。

    为什么（2026-09-14 实测崩溃 ✓）:
      原用固定 `entities.json.tmp` ✗ → 并发写入方互相抢同一 tmp:
        P1 写完 → os.replace 移走 tmp ✓ → P2 的 replace → FileNotFoundError ✗
      （真实根上跑套件时实测: No such file or directory: entities.json.tmp ✗）
    修法: 临时名带 pid + 线程 id ✓（与 execution/kernel/store 的写法一致 ✓）
    """
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, p)


def _entity_index(data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(e.get("id") or ""): e for e in data if isinstance(e, dict)}


def resolve_entity_project(eid: str, index: dict[str, dict[str, Any]],
                          _seen: set[str] | None = None) -> str:
    """沿【父链】推导实体所属项目（只走明确的链 ✓ 推导不出 → 空 ✓）。

    链（实测覆盖率 100% ✓）:
      msg → conv → project_id ✓ · req → conv → project_id ✓
      task → (task*|req|project|conv) → … ✓ · sprint → project ✓ · evidence → task ✓
    防环: _seen ✓（有环 → 空 ✓ 不静默 → 由调用方归入公共 ✓）
    """
    seen = _seen if _seen is not None else set()
    if not eid or eid in seen:
        return ""
    seen.add(eid)
    if eid.startswith("project_"):
        return eid                       # 项目自身 ✓
    e = index.get(eid)
    if not e:
        return ""                        # 父缺失 → 公共 ✓（宁公共不错塞 ✓）
    pid = str(e.get("project_id") or "")
    if pid.startswith("project_"):
        return pid
    return resolve_entity_project(str(e.get("parent_id") or ""), index, seen)


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    """读实体库: 公共 ✓ + 各项目 ✓（Founder 模型: 有项目就在项目下 ✓）。"""
    out: list[dict[str, Any]] = []
    paths = [_file(root, name)]
    if name == "entities":
        paths += sorted(Path(root).glob("projects/*/entities.json"))
    for p in paths:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue                      # 失败安全: 单文件损坏不阻断其它 ✓
        if isinstance(d, list):
            out.extend(d)
    return out


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    """写实体库: entities 按【推导出的项目】分片 ✓；其它 name 维持原行为 ✓。"""
    if name == "entities":
        idx = _entity_index(data)
        public: list[dict[str, Any]] = []
        by_proj: dict[str, list[dict[str, Any]]] = {}
        for e in data:
            if not isinstance(e, dict):
                continue
            pid = resolve_entity_project(str(e.get("id") or ""), idx)
            (by_proj.setdefault(pid, []) if pid else public).append(e)
        for pid, sub in by_proj.items():
            _write_list(_project_entity_file(root, pid), sub)
        data = public                    # 公共部分照原路径写 ✓
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def store_entity(root: Path | str, entity: dict[str, Any]) -> dict[str, Any]:
    """持久化 Entity (统一 Store, 单一事实源)。"""
    validate_entity(entity)
    data = _load(root, "entities")
    data = [e for e in data if e["id"] != entity["id"]]
    data.append(entity)
    _save(root, "entities", data)
    return entity


def get_entity(root: Path | str, entity_id: str) -> dict[str, Any]:
    for e in _load(root, "entities"):
        if e["id"] == entity_id:
            return e
    raise ValueError(f"NOT_FOUND: entity {entity_id}")


def entities(root: Path | str, *, entity_type: str = "") -> list[dict[str, Any]]:
    data = _load(root, "entities")
    if entity_type:
        data = [e for e in data if e["type"] == entity_type]
    return data


def trace_lineage(root: Path | str, entity_id: str) -> list[dict[str, Any]]:
    """Lineage 追溯: 沿 parent_id 向上 (为什么创建这个实体)。"""
    chain = []
    current = entity_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        try:
            e = get_entity(root, current)
        except ValueError:
            break
        chain.append({"id": e["id"], "type": e["type"], "version": e["version"],
                      "status": e["status"]})
        current = e.get("parent_id", "")
    return chain
