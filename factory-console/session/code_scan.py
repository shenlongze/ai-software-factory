"""factory-console/session/code_scan.py — 真实代码扫描 (v1.1.207)。

Founder 2026-08-27: "扫描代码" 原来路由到 project_scan (扫项目元数据), 答"未查询到代码扫描结果"
→ 加真代码扫描: 仓库文件树/LOC/语言/测试/TODO/大文件/最近改动/git (确定性读盘, 不编造)。

失败安全: 未定位仓库 / 目录不存在 → 诚实错误, 不假装。
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

#: 忽略目录 (不扫依赖/产物)
_IGNORE_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv",
                "venv", ".next", "coverage", ".factory", "unused", ".pytest_cache",
                # 构建产物/工具目录 (v1.1.214: desktop/src-tauri/target 2.3G 混入)
                "target", ".github", ".ruff_cache", ".idea", ".vscode", ".turbo",
                "Pods", ".dart_tool", ".gradle", ".cache"}

#: 语言分组 (扩展名 → 语言)
_LANG_BY_EXT: dict[str, str] = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TSX/React", ".js": "JavaScript",
    ".jsx": "React", ".css": "CSS", ".md": "Markdown", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".html": "HTML",
    ".sh": "Shell", ".sql": "SQL", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".vue": "Vue", ".swift": "Swift", ".kt": "Kotlin",
}


def _read_json_map(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def locate_repo(root: Path | str | None, project_id: str) -> Path | None:
    """定位仓库目录: project.json workspace_dir/repo_path → docs_config dirs (与 project_scan 同源)。"""
    if root is None:
        return None
    root = Path(root)
    candidates: list[str] = []
    try:
        pj = root / "workspace" / "projects" / Path(project_id).name / "project.json"
        data = _read_json_map(pj)
        for k in ("workspace_dir", "repo_path"):
            v = str(data.get(k) or "").strip()
            if v:
                candidates.append(v)
    except Exception:  # noqa: BLE001
        pass
    try:
        from .board import read_docs_config

        candidates += read_docs_config(root, project_id)["dirs"]
    except Exception:  # noqa: BLE001
        pass
    for c in candidates:
        try:
            p = Path(c).expanduser()
            if p.is_dir():
                return p
        except Exception:  # noqa: BLE001
            continue
    return None


def _git_info(repo: Path) -> dict[str, Any]:
    try:
        r = subprocess.run(["git", "-C", str(repo), "status", "-sb"],
                           capture_output=True, text=True, timeout=10)
        first = (r.stdout or "").splitlines()[0] if r.stdout else ""
        branch = re.sub(r"^## ", "", first).split("...")[0] if first.startswith("##") else "main"
        ahead = 0
        m = re.search(r"ahead (\d+)", first)
        if m:
            ahead = int(m.group(1))
        return {"branch": branch, "ahead": ahead}
    except Exception:  # noqa: BLE001
        return {}


def scan_repo(root: Path | str | None, project_id: str) -> dict[str, Any]:
    """扫描仓库 → 结构化报告 (确定性; 失败 → {"ok": False, "error"} 诚实)。"""
    repo = locate_repo(root, project_id)
    if repo is None:
        return {"ok": False, "error": "未定位到代码仓库目录 (project.json 无 workspace_dir/repo_path)"}
    files: list[Path] = []
    for f in repo.rglob("*"):
        if not f.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in f.parts):
            continue
        files.append(f)
    if not files:
        return {"ok": False, "error": f"仓库目录为空或无文件: {repo}"}
    # 文件数 / LOC / 语言
    ext_count: Counter = Counter()
    loc: Counter = Counter()
    for f in files:
        ext = f.suffix or "(无扩展名)"
        ext_count[ext] += 1
        try:
            loc[ext] += sum(1 for _ in f.open("rb"))
        except OSError:
            pass
    lang_files: Counter = Counter()
    lang_loc: Counter = Counter()
    for ext, n in ext_count.items():
        lang = _LANG_BY_EXT.get(ext, "其他")
        lang_files[lang] += n
        lang_loc[lang] += loc[ext]
    # 测试文件
    test_files = [
        f for f in files
        if "test" in f.name.lower() or "spec" in f.name.lower()
        or f.parent.name in ("tests", "__tests__", "test")
    ]
    # TODO/FIXME
    todo = 0
    for f in files:
        if f.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".md"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        todo += len(re.findall(r"TODO|FIXME", text))
    # 最大文件 / 最近改动
    by_size = sorted(files, key=lambda f: f.stat().st_size, reverse=True)[:5]
    by_mtime = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    git = _git_info(repo)
    total_loc = sum(loc.values())
    return {
        "ok": True,
        "repo": str(repo),
        "files": len(files),
        "total_loc": int(total_loc),
        "by_language": [{"lang": k, "files": lang_files[k], "loc": int(lang_loc[k])}
                        for k in sorted(lang_files, key=lambda x: lang_loc[x], reverse=True)],
        "test_files": len(test_files),
        "test_file_preview": [str(f.relative_to(repo)) for f in test_files[:5]],
        "todo_fixme": todo,
        "largest_files": [str(f.relative_to(repo)) for f in by_size],
        "recent_modified": [str(f.relative_to(repo)) for f in by_mtime],
        "git": git,
    }


def format_code_scan(report: dict[str, Any], project_name: str = "") -> str:
    """代码扫描报告 → 结构化文本 (喂 LLM 总结; 数据全确定性读入)。"""
    if not report.get("ok"):
        return f"【代码扫描】{report.get('error')}"
    lines = [f"【代码扫描报告 · {project_name or report.get('repo')}】"]
    lines.append(f"1. 仓库: {report['repo']}")
    lines.append(f"2. 规模: {report['files']} 文件 · {report['total_loc']} 行")
    langs = report.get("by_language") or []
    if langs:
        lines.append("   语言: " + " · ".join(
            f"{x['lang']} {x['files']}文件/{x['loc']}行" for x in langs[:6]))
    lines.append(f"3. 测试: {report['test_files']} 个测试文件"
                 + (f" (如: {', '.join(report['test_file_preview'])}" if report["test_file_preview"] else "")
                 + (")" if report["test_file_preview"] else ""))
    lines.append(f"4. TODO/FIXME: {report['todo_fixme']} 处")
    if report.get("largest_files"):
        lines.append("5. 最大文件: " + ", ".join(report["largest_files"]))
    if report.get("recent_modified"):
        lines.append("6. 最近改动: " + ", ".join(report["recent_modified"]))
    git = report.get("git") or {}
    if git:
        lines.append(f"7. git: 分支 {git.get('branch')}" + (f" · 领先 {git.get('ahead')} 提交" if git.get("ahead") else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- 项目结构 (v1.1.214)

def scan_structure(
    root: Path | str | None,
    project_id: str,
    *,
    max_children: int = 8,
) -> dict[str, Any]:
    """项目真实结构: 仓库顶层目录树 + 文件/LOC 分布 + 入口文件 (确定性读盘)。

    不编造: 只给目录名/文件数/行数, 描述由上层模型基于数据总结。
    """
    repo = locate_repo(root, project_id)
    if repo is None:
        return {"ok": False, "error": "未定位到代码仓库目录 (project.json 无 workspace_dir/repo_path)"}
    top_dirs = sorted(
        (d for d in repo.iterdir() if d.is_dir() and d.name not in _IGNORE_DIRS),
        key=lambda d: d.name,
    )
    top_files = sorted(
        (f for f in repo.iterdir() if f.is_file() and f.name not in _IGNORE_DIRS),
        key=lambda f: f.name,
    )
    dirs: list[dict[str, Any]] = []
    for d in top_dirs:
        files = [f for f in d.rglob("*") if f.is_file()
                 and not any(part in _IGNORE_DIRS for part in f.parts)]
        loc = 0
        for f in files[:2000]:
            try:
                loc += sum(1 for _ in f.open("rb"))
            except OSError:
                pass
        subdirs = sorted(
            (s.name for s in d.iterdir() if s.is_dir() and s.name not in _IGNORE_DIRS),
        )[:max_children]
        dirs.append({
            "name": d.name, "files": len(files), "loc": int(loc),
            "subdirs": list(subdirs),
        })
    entry = [f.name for f in top_files if f.name.lower() in (
        "readme.md", "pyproject.toml", "package.json", "go.mod", "cargo.toml",
        "requirements.txt", "makefile", "dockerfile", "index.js", "main.py",
    )]
    return {
        "ok": True, "repo": str(repo),
        "root_files": len(top_files), "dirs": dirs,
        "entry_files": entry,
    }


def format_structure(report: dict[str, Any], project_name: str = "") -> str:
    """项目结构 → 结构化文本 (目录树 + 分布; 数据全确定性读入)。"""
    if not report.get("ok"):
        return f"【项目结构】{report.get('error')}"
    lines = [f"【项目结构 · {project_name or report.get('repo')}】"]
    lines.append(f"仓库: {report['repo']}")
    lines.append(f"顶层: {len(report['dirs'])} 个目录 · 根目录 {report['root_files']} 个文件")
    for d in report["dirs"]:
        sub = " / ".join(d["subdirs"]) if d["subdirs"] else "—"
        lines.append(f"- 📁 {d['name']}/ ({d['files']} 文件 · {d['loc']} 行)"
                     + (f" → {sub}" if d["subdirs"] else ""))
    if report.get("entry_files"):
        lines.append("入口/关键文件: " + ", ".join(report["entry_files"]))
    return "\n".join(lines)
