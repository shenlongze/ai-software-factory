"""factory-console/tools/adapters.py — 工具执行适配器 (U-2)。

统一签名: fn(root, project_id, params) -> result
把注册表工具接到真实能力 (失败安全, 诚实错误)。
第一批: 查询/备份类 (安全可执行); 执行类 (code_exec/prd 等) 下一阶段接 exec 引擎。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _root(ctx_root: Any) -> Path | None:
    return Path(ctx_root) if ctx_root else None


def code_search(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..session.analysis_tools import search_code

    kw = str(params.get("keyword") or "").strip()
    if not kw:
        return {"ok": False, "error": "缺少 keyword"}
    hits = search_code(_root(root), project_id, kw)
    return {"hits": hits}


def scan(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..session.analysis_tools import run_analysis

    ev = run_analysis(_root(root), project_id, str(params.get("question") or "扫描项目"))
    return {"evidence": ev}


def list_tasks(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..session.analysis_tools import list_tasks as _lt

    prio = str(params.get("priority") or "").upper()
    tasks = _lt(_root(root), project_id, priority=prio if prio in ("P0", "P1", "P2", "P3") else "")
    return {"count": len(tasks), "tasks": tasks}


def read_doc(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..session.analysis_tools import read_doc as _rd

    name = str(params.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "缺少 name (文档名)"}
    return {"content": _rd(_root(root), project_id, name)}


def backup(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..backup import create_backup

    return create_backup(root or Path.home() / ".factory")


def git_status(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..session.project_scan import _git_info

    return _git_info(_root(root), project_id) or {"ok": False, "error": "未检测到 git 仓库"}


def monitor(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    from ..monitor import collect_system, check_alerts

    try:
        from factory_console.web.backend.fastapi_adapter import _factory_version, DEFAULT_ROOT
    except Exception:  # noqa: BLE001
        _factory_version, DEFAULT_ROOT = "unknown", str(Path.home() / ".factory")
    sys_mon = collect_system(_root(root) or Path(DEFAULT_ROOT), _factory_version, model_line="")
    alerts = check_alerts(sys_mon, [])
    return {"system": sys_mon, "alerts": alerts}


def quality_score(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    import json

    qf = (_root(root) or Path.home() / ".factory") / "projects" / Path(project_id).name / "quality.json"
    try:
        d = json.loads(qf.read_text(encoding="utf-8"))
        return {"score": d.get("score"), "dimensions": d.get("dimensions") or {}}
    except Exception:  # noqa: BLE001
        return {"score": None, "note": "未生成"}
