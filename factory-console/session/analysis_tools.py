"""factory-console/session/analysis_tools.py — 会话分析工具集 (v1.1.166)。

Founder 2026-08-26: 会话"详细分析"不能靠 LLM 脑补 — 必须调用专业工具,
结论可溯源 (每个判断对应工具输出 + 来源)。

工具 (全部真实执行, 失败安全):
- list_tasks: 按优先级/状态查任务明细 (backlog)
- scan: 多源扫描 (任务树/版本线/战役/仓库/质量 + 判断风险建议)
- git_status: 仓库状态 (remote/分支/领先提交)
- search_code: 代码检索 (repo 内 grep, 返回文件+行)
- read_doc: 读文档内容 (前 N 字符)

run_analysis: 分析意图 → 按需执行工具集 → 证据块 (带来源), 供 LLM 引用。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .project_scan import _git_info, scan_project


def list_tasks(root: Path | str | None, project_id: str, *, priority: str = "") -> list[dict[str, Any]]:
    """按优先级查任务明细 (mgmt backlog; 失败 → [] 诚实)。"""
    if root is None:
        return []
    try:
        import json

        tf = (
            Path(root) / "workspace" / "projects" / Path(project_id).name
            / "management" / "backlog" / "task.json"
        )
        data = json.loads(tf.read_text(encoding="utf-8")) or {}
        out = []
        for t in (data.get("tasks") or {}).values():
            if not isinstance(t, dict):
                continue
            if priority and str(t.get("priority") or "").upper() != priority.upper():
                continue
            out.append({
                "id": t.get("id", ""),
                "title": t.get("title", ""),
                "status": t.get("status", "todo"),
                "priority": t.get("priority", ""),
                "description": str(t.get("description") or "")[:80],
            })
        return out
    except Exception:  # noqa: BLE001 — 失败安全
        return []


def git_status(root: Path | str | None, project_id: str) -> dict[str, Any] | None:
    """仓库状态 (remote/分支/领先; 失败 → None)。"""
    return _git_info(Path(root) if root else None, project_id)


def search_code(root: Path | str | None, project_id: str, keyword: str, *, limit: int = 8) -> list[dict[str, str]]:
    """代码检索: repo 内 grep 关键词 (返回 文件+行; 失败 → [] 诚实)。"""
    info = git_status(root, project_id)
    if info is None or not info.get("dir"):
        return []
    repo = info["dir"]
    try:
        r = subprocess.run(
            ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.tsx",
             "-l", keyword, repo],
            capture_output=True, text=True, timeout=20,
        )
        files = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        return [{"file": f} for f in files[:limit]]
    except Exception:  # noqa: BLE001 — 失败安全
        return []


def read_doc(root: Path | str | None, project_id: str, name: str, *, max_chars: int = 800) -> str:
    """读文档内容前 N 字符 (失败 → 诚实文案)。"""
    try:
        from .query_engine import _read_doc_snippet

        class _T:
            id = project_id

        snippet = _read_doc_snippet(Path(root) if root else None, _T(), name, max_chars=max_chars)
        return snippet if snippet else f"（未找到文档 {name}）"
    except Exception:  # noqa: BLE001
        return f"（读取文档 {name} 失败）"


def run_analysis(
    root: Path | str | None,
    project_id: str,
    question: str,
    *,
    priority: str = "",
    workflow_status: str | None = None,
    current_stage: str | None = None,
) -> str:
    """分析意图 → 按需执行工具集 → 证据块 (带来源, 供 LLM 引用; 不编造)。

    规则: 从问句提取优先级 (P0-P3); 总是带 任务明细 + 扫描 + 仓库;
    含代码/实现/改动 → 加代码检索; 含文档/方案 → 加文档。
    """
    import re

    root_p = Path(root) if root else None
    evidence: list[str] = []

    # 工具 1: 扫描 (进度/版本/战役/仓库/质量 + 判断风险建议)
    try:
        report = scan_project(
            root_p, project_id,
            workflow_status=workflow_status, current_stage=current_stage,
        )
        from .project_scan import format_scan

        evidence.append(f"【工具 · scan_project】\n{format_scan(report, project_id)}")
    except Exception as exc:  # noqa: BLE001
        evidence.append(f"【工具 · scan_project】执行失败: {exc}")

    # 工具 2: 任务明细 (指定优先级 or 全部)
    prio = priority or ""
    if not prio:
        m = re.search(r"p([0-3])", str(question or ""), re.I)
        if m:
            prio = f"P{m.group(1)}"
    tasks = list_tasks(root_p, project_id, priority=prio)
    if tasks:
        lines = [f"【工具 · list_tasks{'(P' + prio[1] + ')' if prio else ''}】{len(tasks)} 条:"]
        for t in tasks[:15]:
            lines.append(f"- [{t['status']}] {t['title'][:60]}")
        evidence.append("\n".join(lines))
    else:
        evidence.append(f"【工具 · list_tasks】未查询到{'P' + prio[1] if prio else ''}任务")

    # 工具 3: 仓库状态
    g = git_status(root_p, project_id)
    if g:
        ahead = f"领先 {g['ahead']} 提交" if g.get("ahead") is not None else "状态待查"
        evidence.append(f"【工具 · git_status】{g['remote']} (分支 {g['branch']}, {ahead})")

    # 工具 4: 代码检索 (含 代码/实现/改动/文件/模块 时)
    if re.search(r"代码|实现|改动|文件|模块|在哪|怎么改", str(question or "")):
        kw = re.sub(r"[^\w\u4e00-\u9fff]+", " ", str(question or ""))[:12].strip()
        if kw:
            hits = search_code(root_p, project_id, kw.split()[0] if kw.split() else kw)
            if hits:
                evidence.append(
                    "【工具 · search_code】命中文件: " + "、".join(h["file"] for h in hits[:8])
                )

    return "\n\n".join(evidence)
