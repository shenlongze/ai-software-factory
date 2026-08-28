"""factory-console/session/repo_map.py — 代码库符号地图 (W7, v1.1.253).

抄 Aider repo map: 不把整个代码库塞上下文, 而是按 token 预算注入"最相关符号地图" —
提取 Python 文件 def/class 符号, 按用户问题关键词 + 符号密度排名, 输出紧凑地图
(文件: 关键符号列表)。模型据此知道"哪个文件有什么", 再按需 read_code 深入。

- build_repo_map(root, project_id, query, max_chars): 返回 {ok, output} 紧凑地图
- 轻量实现 (正则, 不引 tree-sitter); 扫描 <repo>/*.py 顶层 + 关键子目录
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: 顶层扫描深度 (避免全仓递归爆炸)
MAX_DEPTH = 3
#: 每文件符号上限 (防单文件刷屏)
MAX_SYMBOLS_PER_FILE = 12
#: 默认输出预算
DEFAULT_MAX_CHARS = 1500

_CLASS_RE = re.compile(r"^class\s+(\w+)")
_DEF_RE = re.compile(r"^def\s+(\w+)")
_METHOD_RE = re.compile(r"^    def\s+(\w+)")


def _symbols(path: Path) -> list[str]:
    """提取文件内 def/class 符号 (带行号前缀)。"""
    out: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for i, ln in enumerate(lines, 1):
        m = _CLASS_RE.match(ln)
        if m:
            out.append(f"class {m.group(1)}")
            continue
        m = _DEF_RE.match(ln)
        if m:
            out.append(f"def {m.group(1)}")
            continue
        m = _METHOD_RE.match(ln)
        if m:
            out.append(f"  .{m.group(1)}")
        if len(out) >= MAX_SYMBOLS_PER_FILE:
            break
    return out


def _score(path: Path, rel: str, symbols: list[str], q_tokens: set[str]) -> float:
    """排名分: 关键词命中路径/符号 → 高分; 符号密度次之。"""
    score = 0.0
    if q_tokens:
        hay = (rel + " " + " ".join(symbols)).lower()
        for tok in q_tokens:
            if tok in hay:
                score += 2.0
    score += min(len(symbols), 10) * 0.2  # 符号密度
    if path.name == "__init__.py":
        score += 0.3
    return score


def build_repo_map(root: str | Path | None, project_id: str,
                   query: str = "", max_chars: int = DEFAULT_MAX_CHARS) -> dict[str, Any]:
    """构建代码库符号地图。失败 → 诚实错误。"""
    try:
        from .code_scan import locate_repo
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"repo_map 不可用: {exc}"}
    if not root or not project_id:
        return {"ok": False, "error": "缺少 root/project_id"}
    repo = locate_repo(root, project_id)
    if repo is None:
        return {"ok": False, "error": "未定位到代码仓库目录 (project.json 无 workspace_dir/repo_path)"}
    # 关键词
    q_tokens = {t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", str(query or "").lower())}
    # 扫描 Python 文件 (限制深度 + 跳过隐藏/构建目录)
    entries: list[tuple[float, str, list[str]]] = []
    for f in repo.rglob("*.py"):
        try:
            rel = str(f.relative_to(repo))
        except ValueError:
            continue
        depth = len(Path(rel).parts)
        if depth > MAX_DEPTH:
            continue
        if any(p in rel for p in ("node_modules", ".git", ".venv", "build", "dist", "__pycache__")):
            continue
        syms = _symbols(f)
        if not syms:
            continue
        entries.append((_score(f, rel, syms, q_tokens), rel, syms))
    if not entries:
        return {"ok": False, "error": f"仓库无 Python 符号可映射: {repo}"}
    entries.sort(key=lambda e: -e[0])
    lines = [f"【代码库地图】{repo.name} (符号按相关性排名, {len(entries)} 个 Python 文件有符号):"]
    used = 0
    for _score_v, rel, syms in entries[:40]:
        line = f"- {rel}: {'; '.join(syms[:MAX_SYMBOLS_PER_FILE])}"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    if len(lines) == 1:
        lines.append("(地图为空)")
    return {"ok": True, "output": "\n".join(lines), "repo": str(repo), "files": len(entries)}


__all__ = ["build_repo_map"]
