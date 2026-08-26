"""factory-console/session/project_scan.py — 项目扫描器 (v1.1.161)。

Founder 2026-08-26: "扫描项目看进度计划必须完整、强壮、实事求是"。

多源聚合 + 确定性判断/风险/建议 (不依赖 LLM 生成数字 — 全从真实数据读):
- 任务树: management backlog + legacy tasks.json 合并 (任务数/状态/按史诗/优先级)
- 版本线: CHANGELOG.md 版本标题 (list_project_docs 定位, docs_config 多目录)
- 战役线: 待办清单 K 系列 ✅/⬜ 标记
- 工作流/质量: 调用方注入 workflow 字段 + quality.json
- 判断/风险/建议: 规则生成 (双轨不同步/优先级未分化/执行链空闲/质量缺失…)
失败安全: 任何源缺失 → 诚实标注, 不编造。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: 版本标题正则 (CHANGELOG: "## [v1.1.160] — 2026-08-26"; —/- 均可)
_VERSION_RE = re.compile(r"^##\s*\[(v?[\d.]+)\]", re.MULTILINE)
#: K 系列战役行 (待办清单: "| K-1 | ... |"; 无 ✅ 标记视为待推进)
_CAMPAIGN_RE = re.compile(r"^\|\s*(K-\d+)\s*\|")

#: 需要读取的文档相对名 (经 list_project_docs 定位)
_CHANGELOG_NAME = "CHANGELOG.md"
_TODO_LIST_KEY = "待办清单"


def _read_json_map(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — 失败安全
        return {}


def _find_doc_path(root: Path, project_id: str, name_sub: str) -> Path | None:
    """在项目文档资产中定位文档 (name 包含子串; 失败 → None)。"""
    try:
        from ..session.board import list_project_docs

        docs = list_project_docs(root, project_id)
    except Exception:  # noqa: BLE001 — 文档扫描失败 → None
        return None
    for d in docs:
        if not d.get("exists"):
            continue
        nm = str(d.get("name") or "")
        if name_sub.lower() in nm.lower():
            try:
                return Path(str(d.get("source_dir") or "")) / nm
            except Exception:  # noqa: BLE001
                return None
    return None


def _task_tree_stats(root: Path, project_id: str) -> dict[str, Any] | None:
    """任务树统计 (mgmt + legacy 合并; 状态/按史诗/优先级)。"""
    seen: set[str] = set()
    tasks: list[dict[str, Any]] = []
    try:
        tf = (
            Path(root) / "workspace" / "projects" / Path(project_id).name
            / "management" / "backlog" / "task.json"
        )
        data = _read_json_map(tf)
        for t in (data.get("tasks") or {}).values():
            if isinstance(t, dict) and t.get("id") not in seen:
                seen.add(str(t["id"]))
                tasks.append(t)
    except Exception:  # noqa: BLE001
        pass
    try:
        lf = Path(root) / "projects" / Path(project_id).name / "tasks.json"
        data = _read_json_map(lf)
        for t in (data.get("tasks") or []):
            if isinstance(t, dict) and t.get("id") not in seen:
                seen.add(str(t["id"]))
                tasks.append(t)
    except Exception:  # noqa: BLE001
        pass
    if not tasks:
        return None
    statuses = [str(t.get("status") or "todo").lower() for t in tasks]
    done = sum(1 for s in statuses if s in ("done", "completed"))
    running = sum(1 for s in statuses if s in ("in_progress", "running", "review"))
    blocked = sum(1 for s in statuses if s in ("blocked", "failed"))
    todo = len(statuses) - done - running - blocked
    prio: dict[str, int] = {}
    for t in tasks:
        p = str(t.get("priority") or "").upper()
        if p in ("P0", "P1", "P2", "P3"):
            prio[p] = prio.get(p, 0) + 1
    return {
        "total": len(tasks),
        "done": done,
        "running": running,
        "blocked": blocked,
        "todo": todo,
        "pct": round(done / len(tasks) * 100) if tasks else 0,
        "priority": prio,
    }


def _version_line(root: Path, project_id: str) -> dict[str, Any] | None:
    """版本线: CHANGELOG 版本数 + 最近 5 个 (失败 → None)。"""
    path = _find_doc_path(root, project_id, _CHANGELOG_NAME)
    if path is None or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:  # noqa: BLE001
        return None
    versions = _VERSION_RE.findall(text)
    if not versions:
        return None
    return {
        "count": len(versions),
        "recent": [f"{v}" for v in versions[:5]],
    }


def _campaign_line(root: Path, project_id: str) -> dict[str, Any] | None:
    """战役线: 待办清单 K 系列 ✅/⬜ (失败 → None)。"""
    path = _find_doc_path(root, project_id, _TODO_LIST_KEY)
    if path is None or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:  # noqa: BLE001
        return None
    done: list[str] = []
    pending: list[str] = []
    for line in text.splitlines():
        m = _CAMPAIGN_RE.match(line.strip())
        if not m:
            continue
        key = m.group(1)
        if "✅" in line:
            done.append(key)
        else:
            pending.append(key)
    if not done and not pending:
        return None
    return {"done": done, "pending": pending}


def _quality(root: Path, project_id: str) -> dict[str, Any] | None:
    """质量分 (projects/<id>/quality.json; 缺失 → None 诚实)。"""
    try:
        qf = Path(root) / "projects" / Path(project_id).name / "quality.json"
        data = _read_json_map(qf)
        score = data.get("score")
        if isinstance(score, (int, float)):
            return {"score": score}
    except Exception:  # noqa: BLE001
        pass
    return None


def _judgments(tree: dict[str, Any] | None, versions: dict[str, Any] | None,
               campaigns: dict[str, Any] | None, quality: dict[str, Any] | None,
               workflow_status: str | None) -> tuple[list[str], list[str], list[str]]:
    """确定性判断/风险/建议 (实事求是, 只基于注入数据)。"""
    judgments: list[str] = []
    risks: list[str] = []
    suggestions: list[str] = []

    if tree:
        judgments.append(
            f"任务树 {tree['total']} 个任务, 完成 {tree['done']} ({tree['pct']}%), "
            f"执行中 {tree['running']}, 阻塞 {tree['blocked']}, 待办 {tree['todo']}"
        )
        if tree["total"] > 0 and tree["running"] == 0 and tree["done"] < tree["total"]:
            risks.append("当前无执行中任务 — 执行链空闲, 任务推进停滞")
        prio = tree.get("priority") or {}
        p0 = prio.get("P0", 0)
        p1 = prio.get("P1", 0)
        if p0 == 0 and p1 == 0:
            judgments.append("任务优先级未分化 (无 P0/P1) — '按优先级推进'暂无可排序依据")
            suggestions.append("先给任务定优先级 (P0-P3), 再按优先级分批推进")
        else:
            suggestions.append(f"优先推进 P0×{p0} / P1×{p1} 任务")

    if versions and tree and tree.get("pct", 100) < 60 and versions.get("count", 0) > 5:
        judgments.append(
            f"版本线持续迭代 ({versions['count']} 个版本) 但任务树完成度仅 {tree['pct']}% — "
            "任务树偏'债务台账', 与版本执行不同步"
        )
        suggestions.append("把版本/战役成果回填任务树 (完成勾选), 让两条线对齐")

    if campaigns:
        if campaigns["done"]:
            judgments.append(
                "战役线: " + "、".join(f"{k}✅" for k in campaigns["done"])
            )
        if campaigns["pending"]:
            judgments.append("待推进战役: " + "、".join(campaigns["pending"]))
            suggestions.append("按战役链推进: " + "、".join(campaigns["pending"][:3]))

    if quality is None:
        risks.append("质量分未生成 — 无法评估产出质量")
    else:
        judgments.append(f"质量分 {quality['score']}")

    if workflow_status:
        judgments.append(f"工作流: {workflow_status}")

    return judgments, risks, suggestions


def _git_info(root: Path | None, project_id: str) -> dict[str, Any] | None:
    """仓库信息 (git remote/分支/领先落后; 只读命令, 失败 → None 诚实)。

    定位 repo 目录: project.json workspace_dir → repo_path → docs_config dirs
    (AI Factory 自身 = 源码仓库根)。Founder 2026-08-26: 会话答"没配置远程仓库"
    是错的 — 真实 git remote 存在但事实卡没查。
    """
    import subprocess

    if root is None:
        return None
    candidates: list[str] = []
    try:
        pj = (
            Path(root) / "workspace" / "projects" / Path(project_id).name / "project.json"
        )
        data = _read_json_map(pj)
        for k in ("workspace_dir", "repo_path"):
            v = str(data.get(k) or "").strip()
            if v:
                candidates.append(v)
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..session.board import read_docs_config

        candidates += read_docs_config(root, project_id)["dirs"]
    except Exception:  # noqa: BLE001
        pass
    repo_dir: str | None = None
    for c in candidates:
        try:
            if c and (Path(c) / ".git").is_dir():
                repo_dir = c
                break
        except Exception:  # noqa: BLE001
            continue
    if not repo_dir:
        return None

    def _git(*args: str) -> str:
        try:
            r = subprocess.run(
                ["git", "-C", repo_dir, *args],
                capture_output=True, text=True, timeout=10,
            )
            return (r.stdout or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    remote = _git("remote", "get-url", "origin")
    branch = _git("branch", "--show-current")
    ahead = ""
    if branch and remote:
        ahead = _git("rev-list", "--count", f"origin/{branch}..HEAD")
    if not remote and not branch:
        return None
    return {
        "remote": remote or "（未配置 origin）",
        "branch": branch or "—",
        "ahead": ahead if ahead.isdigit() else None,
        "dir": repo_dir,
    }


def scan_project(
    root: Path | str | None,
    project_id: str,
    *,
    workflow_status: str | None = None,
    current_stage: str | None = None,
) -> dict[str, Any]:
    """多源聚合扫描 → 结构化报告 (确定性; 任何源失败 → 诚实标注)。"""
    root = Path(root) if root is not None else None
    report: dict[str, Any] = {
        "project_id": project_id,
        "task_tree": None,
        "versions": None,
        "campaigns": None,
        "quality": None,
        "repo": None,
        "workflow": {"status": workflow_status or "未启动", "stage": current_stage or "—"},
        "judgments": [],
        "risks": [],
        "suggestions": [],
    }
    if root is None:
        report["risks"].append("数据根缺失 — 无法扫描")
        return report
    report["task_tree"] = _task_tree_stats(root, project_id)
    report["versions"] = _version_line(root, project_id)
    report["campaigns"] = _campaign_line(root, project_id)
    report["quality"] = _quality(root, project_id)
    report["repo"] = _git_info(root, project_id)
    judgments, risks, suggestions = _judgments(
        report["task_tree"], report["versions"], report["campaigns"],
        report["quality"], workflow_status,
    )
    report["judgments"] = judgments
    report["risks"] = risks
    report["suggestions"] = suggestions
    return report


def git_push(root: Path | str | None, project_id: str) -> dict[str, Any]:
    """推送仓库到 origin (Founder 2026-08-26: 会话"帮忙推送一下"真实执行)。

    先查状态 (remote/ahead): 无更新 → 不推 (诚实); 有更新 → git push origin 当前分支。
    失败安全: 返回 ok=False + 明确错误 (网络/凭据/非 git), 不假装成功。
    """
    import subprocess

    info = _git_info(Path(root) if root else None, project_id)
    if info is None or info.get("dir") is None:
        return {"ok": False, "error": "未检测到 git 仓库（无法推送）"}
    repo = info["dir"]
    branch = info.get("branch") or "main"
    ahead = info.get("ahead")
    if ahead is not None and int(ahead) == 0:
        return {
            "ok": True, "pushed": False,
            "remote": info.get("remote", ""), "branch": branch,
            "message": "无更新可推（已与 origin 同步）",
        }
    try:
        r = subprocess.run(
            ["git", "-C", repo, "push", "origin", branch],
            capture_output=True, text=True, timeout=120,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0:
            return {
                "ok": True, "pushed": True,
                "remote": info.get("remote", ""), "branch": branch,
                "message": out or "推送成功",
            }
        return {"ok": False, "error": err or out or f"git push 失败 (rc {r.returncode})"}
    except Exception as exc:  # noqa: BLE001 — 失败安全
        return {"ok": False, "error": f"git push 执行失败: {exc}"}


def format_scan(report: dict[str, Any], project_name: str = "") -> str:
    """扫描报告 → 结构化文本 (喂 LLM 总结; 数据全是确定性读入, 不编造)。"""
    lines = [f"【项目扫描报告 · {project_name or report['project_id']}】"]
    tree = report.get("task_tree")
    if tree:
        lines.append(f"1. 任务树: {tree['total']} 任务 (完成 {tree['done']}/执行中 {tree['running']}/阻塞 {tree['blocked']}/待办 {tree['todo']}, {tree['pct']}%)")
        prio = tree.get("priority") or {}
        if prio:
            counted = sum(prio.values())
            suffix = f" (其余 {tree['total'] - counted} 个未标优先级)" if counted < tree["total"] else ""
            lines.append("   优先级: " + " · ".join(f"{k}×{v}" for k, v in sorted(prio.items())) + suffix)
    else:
        lines.append("1. 任务树: 暂无任务数据")
    versions = report.get("versions")
    if versions:
        lines.append(f"2. 版本线: 共 {versions['count']} 个版本, 最近: {' · '.join(versions['recent'])}")
    else:
        lines.append("2. 版本线: 未找到 CHANGELOG")
    campaigns = report.get("campaigns")
    if campaigns:
        done = "、".join(f"{k}✅" for k in campaigns["done"]) or "无"
        pending = "、".join(campaigns["pending"]) or "无"
        lines.append(f"3. 战役线: 完成 {done} · 待推进 {pending}")
    else:
        lines.append("3. 战役线: 未找到待办清单")
    wf = report.get("workflow") or {}
    lines.append(f"4. 工作流: {wf.get('status')} (阶段 {wf.get('stage')})")
    quality = report.get("quality")
    lines.append(f"5. 质量: {quality['score'] if quality else '未生成'}")
    repo = report.get("repo")
    if repo:
        ahead = f"领先 {repo['ahead']} 提交" if repo.get("ahead") is not None else "状态待查"
        lines.append(f"6. 仓库: {repo['remote']} (分支 {repo['branch']}, {ahead})")
    else:
        lines.append("6. 仓库: 未检测到 git 仓库")
    if report.get("judgments"):
        lines.append("判断:")
        lines.extend(f"- {j}" for j in report["judgments"])
    if report.get("risks"):
        lines.append("风险:")
        lines.extend(f"- {r}" for r in report["risks"])
    if report.get("suggestions"):
        lines.append("建议:")
        lines.extend(f"- {s}" for s in report["suggestions"])
    return "\n".join(lines)
