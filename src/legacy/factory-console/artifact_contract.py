"""factory-console/artifact_contract.py — 产出物契约（平台级, C-1）。

AI Factory OS 对**全部项目**的统一产出物标准: Manifest 权威清单 + 版本历史 + 追溯。
- MANIFEST_FILE: projects/<id>/artifacts.manifest.json — 权威清单
  {schema_version, version(项目级), updated_at, artifacts{type: entry}}
  entry: {type,label,kind,file(当前),version,producer,trace_id,created_at,updated_at,versions[]}
- set_artifact: 统一写入口 — 归档旧版到 history/ → 写当前 → 更新 manifest → bump 版本
- get_artifact_version: 按版本读内容 (历史可追溯查看)
- scan_project / validate_project / validate_all: manifest 视图 + 对照校验

诚实原则: 读不到 → 如实标缺失, 不伪造; 历史不丢 (每次更新前归档旧版)。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 契约 schema 版本
CONTRACT_SCHEMA_VERSION = 1

#: 产出物类型默认约定 (type → 默认文件名 + 人话标签 + 种类; manifest 是权威, 此仅默认)
ARTIFACT_SCHEMA: dict[str, dict[str, str]] = {
    "product": {"file": "product.json", "label": "产品定义", "kind": "json"},
    "prd": {"file": "PRD.md", "label": "需求文档", "kind": "md"},
    "engineering": {"file": "engineering.json", "label": "工程计划", "kind": "json"},
    "plan": {"file": "plan.json", "label": "依赖计划", "kind": "json"},
    "tasks": {"file": "tasks.json", "label": "任务拆分", "kind": "json"},
    "execution_plan": {"file": "execution_plan.json", "label": "执行计划", "kind": "json"},
    "execution_state": {"file": "execution_state.json", "label": "执行状态", "kind": "json"},
    "validation": {"file": "validation_result.json", "label": "验证结果", "kind": "json"},
    "repair": {"file": "repair_task.json", "label": "修复任务", "kind": "json"},
    "quality": {"file": "quality.json", "label": "质量分", "kind": "json"},
}

MANIFEST_FILE = "artifacts.manifest.json"
HISTORY_DIR = "history"

#: 合法辅助文件 (非展示产出物, 不报漂移)
ALLOWED_AUX_FILES = {
    MANIFEST_FILE,
    "project.json",
    "README.md",
    "docs_config.json",
    "decomposition.json",
    "dependencies.json",
}
ALLOWED_AUX_PREFIXES = (".status_snapshot_",)

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _project_dir(root: Path | str, project_id: str) -> Path:
    return Path(root) / "projects" / Path(str(project_id)).name


def _empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "version": 0,
        "updated_at": None,
        "artifacts": {},
    }


def read_manifest(root: Path | str, project_id: str) -> dict[str, Any]:
    """读取权威清单 (缺失/损坏 → 空清单, 失败安全)。"""
    p = _project_dir(root, project_id) / MANIFEST_FILE
    try:
        d = json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict) or not isinstance(d.get("artifacts"), dict):
        return _empty_manifest()
    d.setdefault("schema_version", CONTRACT_SCHEMA_VERSION)
    d.setdefault("version", 0)
    d.setdefault("updated_at", None)
    return d


def _write_manifest(root: Path | str, project_id: str, manifest: dict[str, Any]) -> None:
    pdir = _project_dir(root, project_id)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / MANIFEST_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def set_artifact(
    root: Path | str,
    project_id: str,
    artifact_type: str,
    data: Any,
    *,
    raw_text: str | None = None,
    producer: str = "unknown",
    trace_id: str | None = None,
    file: str | None = None,
) -> dict[str, Any]:
    """统一写入口: 归档旧版 → 写当前 → 更新 manifest → bump 项目版本。

    - type 不在注册表且未显式 file → ValueError (HTTP 400)
    - 旧版先归档到 history/<名>.v<N>.<ext> (历史不丢, git 可 diff)
    - entry 带 producer / trace_id / created_at / updated_at (追溯)
    """
    spec = ARTIFACT_SCHEMA.get(artifact_type)
    if spec is None and file is None:
        raise ValueError(
            f"未知产出物类型: {artifact_type} (注册表: {', '.join(sorted(ARTIFACT_SCHEMA))})"
        )
    with _lock:
        pdir = _project_dir(root, project_id)
        pdir.mkdir(parents=True, exist_ok=True)
        manifest = read_manifest(root, project_id)
        entry = manifest["artifacts"].get(artifact_type)
        now = _now_iso()
        target = file or (spec or {}).get("file", f"{artifact_type}.json")

        # 1) 归档旧版 (当前文件存在且未归档过该版本)
        if entry is not None and entry.get("file"):
            old_path = pdir / entry["file"]
            if old_path.is_file():
                old_ver = int(entry.get("version", 0) or 0)
                hist_rel = f"{HISTORY_DIR}/{Path(entry['file']).stem}.v{old_ver}{Path(entry['file']).suffix}"
                hist_path = pdir / hist_rel
                hist_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    hist_path.write_bytes(old_path.read_bytes())
                    old_versions = [v for v in entry.get("versions", []) if v.get("file") != hist_rel]
                    entry["versions"] = old_versions + [
                        {
                            "version": old_ver,
                            "file": hist_rel,
                            "created_at": entry.get("created_at"),
                            "producer": entry.get("producer"),
                            "trace_id": entry.get("trace_id"),
                        }
                    ]
                except OSError:
                    pass  # 归档失败 → 仍写当前 (历史尽力而为)

        # 2) 写当前
        kind = (spec or {}).get("kind", "json")
        if kind == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            content = raw_text if raw_text is not None else str(data)
        (pdir / target).write_text(content, encoding="utf-8")

        # 3) 更新 manifest entry
        new_version = (int(entry.get("version", 0) or 0) + 1) if entry else 1
        versions = list(entry.get("versions", [])) if entry else []
        versions = [v for v in versions if v.get("file") != target]
        versions.append(
            {
                "version": new_version,
                "file": target,
                "created_at": now,
                "producer": producer,
                "trace_id": trace_id,
            }
        )
        manifest["artifacts"][artifact_type] = {
            "type": artifact_type,
            "label": (spec or {}).get("label", artifact_type),
            "kind": kind,
            "file": target,
            "version": new_version,
            "producer": producer,
            "trace_id": trace_id,
            "created_at": entry.get("created_at") if entry else now,
            "updated_at": now,
            "versions": versions,
        }
        manifest["version"] = int(manifest.get("version", 0) or 0) + 1
        manifest["updated_at"] = now
        _write_manifest(root, project_id, manifest)
        return manifest["artifacts"][artifact_type]


def get_artifact_version(
    root: Path | str, project_id: str, artifact_type: str, version: int
) -> dict[str, Any] | None:
    """按版本读内容 (历史可追溯查看; 不存在 → None)。"""
    manifest = read_manifest(root, project_id)
    entry = manifest["artifacts"].get(artifact_type)
    if entry is None:
        return None
    hit = next((v for v in entry.get("versions", []) if int(v.get("version", 0)) == version), None)
    if hit is None:
        return None
    p = _project_dir(root, project_id) / hit["file"]
    try:
        content = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {**hit, "content": None, "note": "读取失败"}
    return {**hit, "content": content}


def scan_project(root: Path | str, project_id: str) -> dict[str, Any]:
    """项目产出物统一状态 (manifest 视图; 存在/缺失/格式/版本链) — 只读实事求是。"""
    pdir = _project_dir(root, project_id)
    manifest = read_manifest(root, project_id)
    items: list[dict[str, Any]] = []
    for artifact_type, entry in manifest["artifacts"].items():
        f = pdir / entry["file"]
        exists = f.is_file()
        schema_ok = True
        if exists and entry.get("kind") == "json":
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                schema_ok = False
        items.append(
            {
                "type": artifact_type,
                "label": entry.get("label", artifact_type),
                "kind": entry.get("kind", ""),
                "file": entry.get("file", ""),
                "exists": exists,
                "legacy": False,
                "schema_ok": schema_ok,
                "version": entry.get("version"),
                "producer": entry.get("producer"),
                "trace_id": entry.get("trace_id"),
                "created_at": entry.get("created_at"),
                "updated_at": entry.get("updated_at"),
                "versions": entry.get("versions", []),
            }
        )
    # 默认约定类型未纳入 manifest → 存量文件标 legacy (存在但未纳入契约), 否则缺失
    produced = set(manifest["artifacts"].keys())
    for artifact_type, spec in ARTIFACT_SCHEMA.items():
        if artifact_type in produced:
            continue
        f = pdir / spec["file"]
        legacy = f.is_file()
        schema_ok = True
        if legacy and spec["kind"] == "json":
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                schema_ok = False
        items.append(
            {
                "type": artifact_type,
                "label": spec["label"],
                "kind": spec["kind"],
                "file": spec["file"],
                "exists": legacy,
                "legacy": legacy,
                "schema_ok": schema_ok,
                "version": None,
                "producer": None,
                "trace_id": None,
                "created_at": None,
                "updated_at": None,
                "versions": [],
            }
        )
    items.sort(key=lambda i: (0 if i["exists"] else 1, i["type"]))
    drift: list[str] = []
    if pdir.is_dir():
        referenced = {v.get("file") for e in manifest["artifacts"].values() for v in e.get("versions", [])}
        referenced |= {e.get("file") for e in manifest["artifacts"].values()}
        standard = {s["file"] for s in ARTIFACT_SCHEMA.values()}
        try:
            for f in sorted(pdir.iterdir()):
                if not f.is_file() or f.name in standard or f.name in ALLOWED_AUX_FILES:
                    continue
                if f.name.startswith(ALLOWED_AUX_PREFIXES):
                    continue
                if f.suffix.lower() in {".md", ".json"} and str(f.name) not in referenced:
                    drift.append(f.name)
        except OSError:  # noqa: BLE001
            pass
    return {
        "project_id": project_id,
        "items": items,
        "meta": {
            "version": int(manifest.get("version", 0) or 0),
            "updated_at": manifest.get("updated_at"),
            "schema_version": manifest.get("schema_version", CONTRACT_SCHEMA_VERSION),
        },
        "drift": drift,
    }


def validate_project(root: Path | str, project_id: str) -> dict[str, Any]:
    """单项目校验: 缺失 / 格式 / 历史缺失 / 无版本 → 问题清单。"""
    scan = scan_project(root, project_id)
    manifest = read_manifest(root, project_id)
    problems: list[dict[str, str]] = []
    for item in scan["items"]:
        if not item["exists"]:
            problems.append({"type": item["type"], "issue": "missing", "detail": item["file"]})
        elif item.get("legacy"):
            problems.append({"type": item["type"], "issue": "legacy", "detail": f"{item['file']} 存量未纳入契约 (需 set_artifact 迁移)"})
        elif not item["schema_ok"]:
            problems.append({"type": item["type"], "issue": "format", "detail": f"{item['file']} 格式不兼容"})
        # 历史链校验: 非当前版本的 history 文件是否存在
        for v in item.get("versions", []):
            vp = _project_dir(root, project_id) / v["file"]
            if not vp.is_file():
                problems.append({"type": item["type"], "issue": "history-missing", "detail": v["file"]})
    if scan["meta"]["version"] <= 0:
        problems.append({"type": "meta", "issue": "no-version", "detail": f"{MANIFEST_FILE} 未生成（无版本信号）"})
    for name in scan["drift"]:
        problems.append({"type": "drift", "issue": "drift", "detail": f"非标准文件: {name}"})
    return {"project_id": project_id, "ok": len(problems) == 0, "problems": problems, **scan}


def validate_all(root: Path | str) -> dict[str, Any]:
    """遍历全部项目 validate (任何异常 → 该项目标 error, 不 5xx)。"""
    root_path = Path(root)
    projects_dir = root_path / "projects"
    results: list[dict[str, Any]] = []
    if projects_dir.is_dir():
        for pdir in sorted(projects_dir.iterdir()):
            if not pdir.is_dir():
                continue
            try:
                results.append(validate_project(root_path, pdir.name))
            except Exception as exc:  # noqa: BLE001
                results.append({"project_id": pdir.name, "ok": False, "problems": [{"type": "error", "issue": "error", "detail": str(exc)}]})
    return {"contract_version": CONTRACT_SCHEMA_VERSION, "projects": results}


__all__ = [
    "ARTIFACT_SCHEMA",
    "CONTRACT_SCHEMA_VERSION",
    "MANIFEST_FILE",
    "read_manifest",
    "set_artifact",
    "get_artifact_version",
    "scan_project",
    "validate_project",
    "validate_all",
]
