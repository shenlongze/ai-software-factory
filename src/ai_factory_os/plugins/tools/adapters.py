"""plugins.tools.adapters — 工具执行适配器（统一签名 `fn(root, project_id, params) -> dict`）。

★ 2026-09-19 重写（修断链）—— 原实现（老区 `factory-console/tools/adapters.py` 搬来的）有
  **7 处 import 指向已删模块**:
    ..session.analysis_tools（search_code/run_analysis/list_tasks/read_doc）×4
    ..session.project_scan（_git_info）×1 · ..backup（create_backup）×1 · ..monitor ×1
  而 `plugins/session/`、`plugins/backup.py`、`plugins/monitor.py` **都不存在**
  ⇒ 7 个工具里 6 个一调用就 ModuleNotFoundError ⇒ **agent 的手是坏的**。

  ★ 修法: **不迁老区代码**（它会带来老依赖）, 用新区已有能力 + stdlib 重写:
    backup     → services/operations/backup.create_backup（新区已有）
    git_status → infrastructure/git/code_scan._git_info（新区已有）
    其余（搜索/结构扫描/读文档/任务列表/系统信息）→ 用 pathlib / os / shutil 现写

  统一约定（照原注释）: **失败安全 + 诚实错误** —— 拿不到就返回
  {"ok": False, "error": "..."} 或 {"note": "..."}, **绝不假装成功**。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

#: 搜索/扫描时跳过的目录（避免把依赖与缓存当成项目代码）
_SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next"}


def _root(ctx_root: Any) -> Path | None:
    return Path(ctx_root) if ctx_root else None


def _proj(root: Any, project_id: str) -> Path:
    """定位项目目录: <root>/projects/<project_id>；取不到就用 root 本身（只读工具的合理回落）。"""
    base = _root(root) or (Path.home() / ".factory")
    if project_id:
        cand = base / "projects" / Path(project_id).name
        if cand.is_dir():
            return cand
    return base


def _iter_files(base: Path, *, exts: tuple[str, ...] = (), limit: int = 4000):
    """遍历文件（跳过 _SKIP 目录; 可选按扩展名过滤）。"""
    n = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP and not d.startswith(".")]
        for fn in filenames:
            if exts and not fn.endswith(exts):
                continue
            yield Path(dirpath) / fn
            n += 1
            if n >= limit:
                return


# ------------------------------------------------------------------ ① 代码搜索

def code_search(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """按关键字搜文件内容（只读, 返回命中行 + 位置）。"""
    kw = str(params.get("keyword") or "").strip()
    if not kw:
        return {"ok": False, "error": "缺少 keyword"}
    base = _proj(root, project_id)
    limit = int(params.get("limit") or 30)
    hits: list[dict[str, Any]] = []
    try:
        for f in _iter_files(base, exts=(".py", ".md", ".json", ".yaml", ".yml", ".toml",
                                         ".txt", ".js", ".ts", ".html", ".css", ".sh")):
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if kw in line:
                        hits.append({"file": str(f.relative_to(base)), "line": i,
                                     "text": line.strip()[:200]})
                        if len(hits) >= limit:
                            return {"hits": hits, "truncated": True}
            except OSError:
                continue
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"hits": hits, "count": len(hits)}


# ------------------------------------------------------------------ ② 结构扫描

def scan(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """项目结构快照（文件数/按扩展名分布/顶层目录）—— 只读, 不调 LLM。"""
    base = _proj(root, project_id)
    if not base.is_dir():
        return {"ok": False, "error": f"目录不存在: {base}"}
    exts: dict[str, int] = {}
    total = 0
    lines = 0
    try:
        for f in _iter_files(base):
            total += 1
            exts[f.suffix or "(无后缀)"] = exts.get(f.suffix or "(无后缀)", 0) + 1
            if f.suffix in (".py", ".js", ".ts", ".sh", ".md"):
                try:
                    lines += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
                except OSError:
                    pass
        tops = sorted(d.name for d in base.iterdir() if d.is_dir() and d.name not in _SKIP)[:20]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    top_ext = sorted(exts.items(), key=lambda kv: -kv[1])[:10]
    return {"base": str(base), "files": total, "code_lines": lines,
            "by_ext": dict(top_ext), "top_dirs": tops,
            "evidence": f"{base.name}: {total} 文件 · 代码约 {lines} 行 · 主要类型 {top_ext[:3]}"}


# ------------------------------------------------------------------ ③ 任务列表

def list_tasks(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """列任务树里的叶（读新区 services/work/decomposition 的真实任务树）。"""
    prio = str(params.get("priority") or "").upper()
    base = _root(root) or (Path.home() / ".factory")
    try:
        from ai_factory_os.services.work import decomposition as D

        out: list[dict[str, Any]] = []
        for t in D.list_trees(base):
            pid = str(t.get("plan_id") or "")
            tree = D.load_tree(base, pid, project_id)
            if not tree:
                continue
            for n in D.tree_leaves(tree):
                if prio and str(n.get("priority") or "").upper() != prio:
                    continue
                out.append({"plan_id": pid, "id": str(n.get("id") or ""),
                            "title": str(n.get("title") or ""),
                            "status": str(n.get("status") or "pending"),
                            "role": str(n.get("role_hint") or "")})
        return {"count": len(out), "tasks": out}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "count": 0, "tasks": []}


# ------------------------------------------------------------------ ④ 读文档

def read_doc(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """读项目里的一篇文档（按文件名模糊匹配, 限长返回）。"""
    name = str(params.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "缺少 name (文档名)"}
    base = _proj(root, project_id)
    max_chars = int(params.get("max_chars") or 8000)
    try:
        exact = base / name
        if exact.is_file():
            return {"content": exact.read_text(encoding="utf-8", errors="ignore")[:max_chars],
                    "path": str(exact)}
        for f in _iter_files(base, exts=(".md", ".txt", ".rst")):
            if name.lower() in f.name.lower():
                return {"content": f.read_text(encoding="utf-8", errors="ignore")[:max_chars],
                        "path": str(f)}
        return {"ok": False, "error": f"未找到文档: {name}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ ⑤ 备份

def backup(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """备份（接新区 services/operations/backup）。"""
    try:
        from ai_factory_os.services.operations.backup import create_backup

        base = _root(root) or (Path.home() / ".factory")
        return create_backup(base)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ ⑥ Git 状态

def git_status(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Git 状态（接新区 infrastructure/git/code_scan）。"""
    base = _proj(root, project_id)
    try:
        from ai_factory_os.infrastructure.git.code_scan import _git_info

        got = _git_info(base)
        return got or {"ok": False, "error": "未检测到 git 仓库", "base": str(base)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ ⑦ 系统信息

def monitor(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """系统信息（磁盘/负载/内存粗看）—— stdlib 实现, 不依赖第三方。"""
    try:
        base = _root(root) or (Path.home() / ".factory")
        du = shutil.disk_usage(str(base if base.exists() else Path.home()))
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        mem: dict[str, Any] = {}
        try:
            total = int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
            mem = {"total_gb": round(total / 1e9, 1)}
        except (ValueError, OSError, AttributeError):
            mem = {}
        return {
            "system": {
                "disk_total_gb": round(du.total / 1e9, 1),
                "disk_free_gb": round(du.free / 1e9, 1),
                "disk_used_pct": round((du.used / du.total) * 100, 1) if du.total else 0,
                "load_1m": load[0],
                "mem": mem,
            },
            "alerts": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------ ⑧ 质量分（原本就好）

def quality_score(root: Any, project_id: str, params: dict[str, Any]) -> dict[str, Any]:
    qf = (_root(root) or Path.home() / ".factory") / "projects" / Path(project_id).name / "quality.json"
    try:
        d = json.loads(qf.read_text(encoding="utf-8"))
        return {"score": d.get("score"), "dimensions": d.get("dimensions") or {}}
    except Exception:  # noqa: BLE001
        return {"score": None, "note": "未生成"}
