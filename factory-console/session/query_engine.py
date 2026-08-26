"""factory-console/session/query_engine.py — 会话意图 → 本地真实数据查询 (v1.1.119)。

Founder 设计: 用户输入 → (LLM) 转标准需求/意图 → 本地化查询真实项目情况 → 回答。

v1 实现:
- 意图解析: 确定性关键词优先 (快/省/可断言), 返回 {intent, project?}
- 查询执行: 全部从真实数据构建 (项目列表/单项目状态/质量分/任务/文档/模型);
  查不到 → 如实"待查证", 不编造
- 输出: facts 文本块 → 注入会话 prompt → LLM 只基于查询结果回答

意图集合: list_projects / project_status / project_quality / project_tasks /
project_docs / model / chat (默认对话, 无查询)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: 确定性意图关键词 (顺序即优先级)
_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("tools_list", ("有哪些工具", "工具清单", "工具有什么", "内置工具", "能调用哪些工具")),
    ("task_continue", ("继续做", "接着做", "继续任务", "继续开发", "继续之前", "继续推进", "继续这个", "接着推进")),
    ("deep_analyze", ("详细分析", "深度分析", "分析一下", "全面分析", "分析过程", "深度看", "详细看", "分析下")),
    ("create_project", ("做一个", "创建一个", "开发一个", "帮我做个", "帮我做", "新建一个项目", "做个app", "做个 App", "做个app")),
    ("task_action", ("标记完成", "标为完成", "标记开始", "开始任务", "改优先级", "改成p0", "改成p1", "改成p2", "改成p3", "归档任务", "完成任务", "完成这个任务")),
    ("create_task", ("完善", "优化", "改进", "修复", "修一下", "加个", "增加", "做一下",
                     "细化", "拆解", "拆任务", "拆成", "整理成任务", "转成任务", "落地成任务")),
    ("system_status", ("webui状态", "webui 状态", "系统状态", "运行状态", "服务状态", "服务情况", "现在webui", "系统运行", "前端状态")),
    ("list_projects", ("有哪些项目", "几个项目", "项目列表", "所有项目", "空间内", "重点项目", "项目清单")),
    ("project_quality", ("质量", "评分", "质量分", "分数")),
    ("project_tasks", ("任务", "todo", "待办", "backlog", "排期")),
    ("project_doc", ("文档内容", "讲了什么", "读一下", "内容是什么", ".md", ".json", ".txt", ".docx")),
    ("doc_search", ("检索", "搜索", "搜一下", "查找", "哪些文档提到", "哪份文档", "哪篇文档", "有没有说", "提到")),
    ("project_docs", ("文档", "文档清单", "产物", "产出物", "docs", "dosc", "products", "规格", "product-spec")),
    ("create_idea", ("记录个想法", "记个想法", "记一个想法", "记录一个想法", "新增想法", "建个想法")),
    ("project_artifacts", ("产出物", "版本链", "产物清单", "产物有哪些", "artifact", "artifacts")),
    ("monitor", ("监控", "告警", "告警信息", "运维状态", "健康检查", "服务健康", "有没有告警")),
    ("settings", ("查看设置", "查看配置", "配置清单", "有哪些agent", "有哪些技能", "llm 配置", "模型配置", "agent 列表", "技能列表")),
    ("project_action", ("改名", "重命名", "删除项目", "取消收藏", "收藏这个", "收藏该项目", "设为收藏")),
    ("git_push", ("推送", "推到", "push", "上传到 github", "推到 github", "推送到 github")),
    ("project_scan", ("扫描", "扫一下", "体检", "全面看", "整体情况", "总览", "盘点", "看进度计划", "进度计划")),
    ("project_status", ("状态", "阶段", "进行", "进度", "生命周期", "卡点", "怎么样", "进展",
                       "计划", "规划", "里程碑", "看看项目")),
    ("model", ("模型", "什么模型", "deepseek")),
]

#: 确定性意图解析 (无 LLM 依赖; 未命中 → chat)
def parse_intent(question: str) -> dict[str, Any]:
    q = str(question or "").strip().lower()
    for intent, keys in _INTENT_RULES:
        for k in keys:
            if k in q:
                return {"intent": intent}
    return {"intent": "chat"}


def resolve_project(question: str, projects: list[Any]) -> Any | None:
    """按用户说的项目名匹配 (子串; 失败 → None)。"""
    q = str(question or "").strip()
    if not q:
        return None
    for p in projects:
        name = str(getattr(p, "name", "") or "")
        if name and name in q:
            return p
        pid = str(getattr(p, "id", "") or "")
        if pid and pid in q:
            return p
    return None


def _stage(p: Any) -> str:
    return str(getattr(p, "lifecycle_stage", None) or getattr(p, "status", None) or "未知")


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _project_task_stats(root: Path | None, project_id: str) -> dict[str, int] | None:
    """项目真实任务统计 (management backlog + legacy tasks.json 合并; 失败 → None)。

    Founder 2026-08-26: 会话"扫描项目看进度"之前只报 org progress=0, 太敷衍。
    """
    if root is None:
        return None
    seen: set[str] = set()
    tasks: list[dict[str, Any]] = []
    # mgmt store (workspace/projects/<id>/management/backlog/task.json)
    try:
        tf = (
            Path(root) / "workspace" / "projects" / Path(project_id).name
            / "management" / "backlog" / "task.json"
        )
        data = json.loads(tf.read_text(encoding="utf-8")) or {}
        for t in (data.get("tasks") or {}).values():
            if isinstance(t, dict) and (t.get("id") not in seen):
                seen.add(str(t.get("id")))
                tasks.append(t)
    except Exception:  # noqa: BLE001 — mgmt 读取失败 → 继续 legacy
        pass
    # legacy tasks.json (M2..P0 里程碑树; 按 id 去重合并)
    try:
        lf = Path(root) / "projects" / Path(project_id).name / "tasks.json"
        data = json.loads(lf.read_text(encoding="utf-8")) or {}
        for t in (data.get("tasks") or []):
            if isinstance(t, dict) and (t.get("id") not in seen):
                seen.add(str(t.get("id")))
                tasks.append(t)
    except Exception:  # noqa: BLE001 — legacy 失败 → 忽略
        pass
    if not tasks:
        return None
    statuses = [str(t.get("status") or "todo").lower() for t in tasks if isinstance(t, dict)]
    done = sum(1 for s in statuses if s in ("done", "completed"))
    running = sum(1 for s in statuses if s in ("in_progress", "running", "review"))
    blocked = sum(1 for s in statuses if s in ("blocked", "failed"))
    todo = len(statuses) - done - running - blocked
    total = len(statuses)
    return {
        "total": total,
        "done": done,
        "running": running,
        "blocked": blocked,
        "todo": todo,
        "pct": round(done / total * 100) if total else 0,
    }


def _project_epic_names(root: Path | None, project_id: str) -> dict[str, Any] | None:
    """项目史诗名称预览 (前 5 + 等 N; mgmt + legacy 合并; 失败 → None)。"""
    if root is None:
        return None
    names: list[str] = []
    seen: set[str] = set()
    try:
        ef = (
            Path(root) / "workspace" / "projects" / Path(project_id).name
            / "management" / "backlog" / "epic.json"
        )
        data = json.loads(ef.read_text(encoding="utf-8")) or {}
        for e in (data.get("epics") or {}).values():
            n = str(e.get("name") or "")
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    except Exception:  # noqa: BLE001 — mgmt 失败 → legacy
        pass
    try:
        lf = Path(root) / "projects" / Path(project_id).name / "tasks.json"
        data = json.loads(lf.read_text(encoding="utf-8")) or {}
        for e in (data.get("epics") or []):
            n = str(e or "")
            if n and n not in seen:
                seen.add(n)
                names.append(n)
    except Exception:  # noqa: BLE001 — legacy 失败 → 忽略
        pass
    if not names:
        return None
    return {
        "total": len(names),
        "preview": " · ".join(names[:5]) + (f" 等{len(names) - 5}个" if len(names) > 5 else ""),
    }


def _priority_tasks(root: Path | None, project_id: str, prio: str) -> list[dict[str, Any]] | None:
    """按优先级读任务清单 (mgmt 任务 priority 字段; 失败 → None)。"""
    if root is None:
        return None
    tasks: list[dict[str, Any]] = []
    try:
        tf = (
            Path(root) / "workspace" / "projects" / Path(project_id).name
            / "management" / "backlog" / "task.json"
        )
        data = json.loads(tf.read_text(encoding="utf-8")) or {}
        for t in (data.get("tasks") or {}).values():
            if isinstance(t, dict) and str(t.get("priority") or "").upper() == prio:
                tasks.append(t)
    except Exception:  # noqa: BLE001
        return None
    return tasks if tasks else None


def _extract_priority(question: str) -> str | None:
    """从问句提取优先级 (P0-P3; 无 → None)。"""
    q = str(question or "").lower()
    m = re.search(r"p([0-3])", q)
    return f"P{m.group(1)}" if m else None


def _docs_subpath(question: str) -> str:
    """从问句提取文档子目录 (如 "docs/products" / "dosc/products"; 宽容拼写)。

    规则: 找 docs|dosc 后跟 /xxx 的路径片段; 无 → ""。
    """
    m = re.search(r"(?:docs|dosc)\s*/?\s*([\w\-./]+)", str(question or ""), re.I)
    if not m:
        return ""
    raw = m.group(0).strip().replace("dosc", "docs")
    # 去掉尾随的疑问词/句尾标点 (只留路径字符)
    tail = re.sub(r"[^\w\-./].*$", "", raw)
    return tail.rstrip("/")


def _extract_doc_name(question: str) -> str:
    """从问句提取文档名 (含扩展名 token 优先; 无 → "")。"""
    q = str(question or "")
    m = re.search(r"[\w\u4e00-\u9fff\-./]+\.(?:md|json|txt|docx?)\b", q, re.I)
    if m:
        return m.group(0).strip().rstrip("/")
    return ""


def _read_doc_snippet(
    root: Path | None,
    target: Any,
    doc_name: str,
    *,
    max_chars: int = 2500,
) -> str | None:
    """定位文档 → 读内容前 N 字符 (失败/缺失 → None, 诚实)。

    匹配: name 精确/后缀/包含, 或 label 匹配 (多目录文档按相对名)。
    """
    if root is None or not doc_name:
        return None
    try:
        from ..session.board import list_project_docs, read_project_doc_content

        docs = list_project_docs(root, str(getattr(target, "id", "") or ""))
    except Exception:  # noqa: BLE001
        return None
    needle = doc_name.lower()
    cand = None
    for d in docs:
        if not d.get("exists"):
            continue
        nm = str(d.get("name") or "").lower()
        lb = str(d.get("label") or "").lower()
        if nm == needle or nm.endswith("/" + needle) or lb == needle or needle in nm:
            cand = d
            break
    if cand is None:
        return None
    content = ""
    # 优先按文档 source_dir 直读 (docs_config 可配外部目录, 与 workspace_dir 无关)
    try:
        src_dir = Path(str(cand.get("source_dir") or ""))
        f = (src_dir / str(cand["name"])).resolve()
        if f.is_relative_to(src_dir.resolve()) and f.is_file():
            content = f.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError):  # noqa: BLE001
        content = ""
    if not content:
        # 兜底: 系统核心资产走 read_project_doc_content (路径安全)
        try:
            res = read_project_doc_content(root, str(getattr(target, "id", "") or ""), str(cand["name"]))
            content = str(res.get("content") or "")
        except Exception:  # noqa: BLE001
            content = ""
    if not content:
        return None
    return content[:max_chars] + ("\n…(截断)" if len(content) > max_chars else "")


def _doc_search_hits(root: Path | None, target: Any, question: str) -> list[dict[str, Any]]:
    """文档检索 (K-6 RAG): 幂等建索引 → 确定性词频检索, 返回 top 命中文档片段。"""
    if root is None:
        return []
    try:
        from ..retrieval.knowledge_store import KnowledgeStore, rag_query

        KnowledgeStore(root, str(getattr(target, "id", "") or "")).incremental_ingest()
        hits, _stats = rag_query(root, str(getattr(target, "id", "") or ""), question, top_k=5)
        return [
            {
                "file": str(getattr(h, "file", "") or getattr(h, "source", "") or ""),
                "source": str(getattr(h, "source", "") or ""),
                "fragment": str(getattr(h, "fragment", "") or ""),
                "score": float(getattr(h, "score", 0) or 0),
            }
            for h in hits
        ]
    except Exception:  # noqa: BLE001 — 检索失败 → 诚实空
        return []


def build_facts(
    question: str,
    *,
    scope: str,
    project_id: str | None,
    projects: list[Any],
    root: Path | None,
    model_line: str = "",
    system_line: str = "",
    hint_project: str | None = None,
) -> str:
    """意图 → 真实数据事实块 (查询不到 → 如实待查证; 不编造)。"""
    intent = parse_intent(question)["intent"]
    if intent == "tools_list":
        try:
            from ..tools.registry import list_tools, summary

            s = summary()
            lines = [f"内置工具注册表 (U-1): 共 {s['total']} 个 (已实现 {s['by_status']['implemented']} / 规划 {s['by_status']['planned']})"]
            for stage in ("设计", "开发", "测试", "部署", "运维"):
                rows = list_tools(stage)
                names = "、".join(f"{'✅' if x['status']=='implemented' else '⬜'}{x['name']}" for x in rows)
                lines.append(f"[{stage} · {len(rows)}] {names}")
            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            return "工具注册表不可用（待查证）"
    if intent == "system_status":
        return system_line or "系统状态: 服务信息待查证"
    if intent == "chat":
        # 纯对话: 公司级给项目列表兜底; 项目级给基础事实
        if scope == "project" and project_id:
            p = next((pp for pp in projects if pp.id == project_id), None)
            if p is not None:
                return f"名称: {p.name}\n生命周期: {_stage(p)}\n进度: {p.progress}"
        return f"项目列表: {', '.join(pp.name for pp in projects) if projects else '暂无项目'}"

    # 项目归属: LLM 意图的项目名优先 → 提问匹配 → 项目级会话当前项目
    target = None
    if hint_project:
        target = next((pp for pp in projects if hint_project in str(getattr(pp, "name", "") or "")), None)
    if target is None:
        target = resolve_project(question, projects)
    if target is None and scope == "project" and project_id:
        target = next((pp for pp in projects if pp.id == project_id), None)

    if intent == "list_projects":
        rows = [
            f"{pp.name} (阶段: {_stage(pp)}){' ⭐重点项目' if getattr(pp, 'starred', False) else ''}"
            for pp in projects
            if not getattr(pp, "archived", False)
        ]
        block = f"项目列表 ({len(rows)} 个):\n" + "\n".join(rows) if rows else "项目列表: 暂无项目"
    elif intent == "model":
        block = model_line or "模型信息待查证 (未配置)"
    elif target is not None:
        name = str(getattr(target, "name", "") or "")
        if intent == "project_scan":
            try:
                from ..session.project_scan import format_scan, scan_project

                report = scan_project(
                    root,
                    str(getattr(target, "id", "") or ""),
                    workflow_status=getattr(target, "workflow_status", None) or None,
                    current_stage=getattr(target, "current_stage", None) or None,
                )
                block = format_scan(report, name)
            except Exception:  # noqa: BLE001 — 扫描失败 → 诚实降级
                block = f"项目: {name}\n扫描失败（数据服务不可用）— 请稍后重试。"
        elif intent == "project_status":
            stats = _project_task_stats(root, str(getattr(target, "id", "") or ""))
            lines = [
                f"项目: {name}",
                f"生命周期: {_stage(target)}",
            ]
            if stats:
                lines.append(
                    f"进度: {stats['pct']}% (任务 {stats['total']}: "
                    f"完成 {stats['done']} · 执行中 {stats['running']} · "
                    f"阻塞 {stats['blocked']} · 待办 {stats['todo']})"
                )
            else:
                lines.append(f"进度: {getattr(target, 'progress', None) or 0}")
            lines.append(f"当前阶段: {getattr(target, 'current_stage', None) or '—'}")
            lines.append(f"工作流: {getattr(target, 'workflow_status', None) or '未启动'}")
            epics = _project_epic_names(root, str(getattr(target, "id", "") or ""))
            if epics:
                lines.append(f"史诗 ({epics['total']}): {epics['preview']}")
            block = "\n".join(lines)
        elif intent == "project_quality":
            score = None
            if root is not None:
                qf = Path(root) / "projects" / str(getattr(target, "id", "") or "") / "quality.json"
                d = _read_json_file(qf)
                if d is not None and isinstance(d.get("score"), (int, float)):
                    score = d["score"]
            block = f"项目: {name}\n质量分: {score if score is not None else '未生成'}"
        elif intent == "project_tasks":
            prio = _extract_priority(question)
            if prio is not None:
                # 按优先级任务清单 (Founder 2026-08-26: 查 P0 任务不能只给整体统计)
                ptasks = _priority_tasks(root, str(getattr(target, "id", "") or ""), prio)
                if ptasks:
                    lines = [f"项目: {name}\n{prio} 任务 ({len(ptasks)}):"]
                    for t in ptasks[:12]:
                        st = str(t.get("status") or "todo")
                        mark = "✅" if st in ("done", "completed") else "⬜"
                        lines.append(f"- {mark} [{st}] {str(t.get('title') or '')[:50]}")
                    if len(ptasks) > 12:
                        lines.append(f"  ... 等{len(ptasks) - 12}个")
                    block = "\n".join(lines)
                else:
                    block = f"项目: {name}\n{prio} 任务: 暂无（当前 {name} 未标 {prio} 任务）"
            else:
                stats = _project_task_stats(root, str(getattr(target, "id", "") or ""))
                if stats:
                    block = (
                        f"项目: {name}\n任务统计: 共 {stats['total']} 个 "
                        f"(完成 {stats['done']} · 执行中 {stats['running']} · "
                        f"阻塞 {stats['blocked']} · 待办 {stats['todo']}, 进度 {stats['pct']}%)"
                    )
                else:
                    # 无真实任务文件 → fallback org 字段 (兼容旧数据)
                    tasks = getattr(target, "tasks", None) or {}
                    counts = " · ".join(f"{k}:{v}" for k, v in sorted(tasks.items())) if tasks else "暂无任务"
                    block = f"项目: {name}\n任务统计: {counts}"
        elif intent == "project_doc":
            doc_name = _extract_doc_name(question)
            content = _read_doc_snippet(root, target, doc_name)
            if content is None:
                block = (
                    f"项目: {name}\n文档: 未找到"
                    + (f" '{doc_name}'" if doc_name else "")
                    + "（请说完整文档名, 如 'README.md' / 'API规范.md'; 或先问 '有哪些文档'）"
                )
            else:
                block = f"项目: {name}\n文档: {doc_name}\n--- 内容片段 ---\n{content}"
        elif intent == "doc_search":
            hits = _doc_search_hits(root, target, question)
            if hits:
                lines = [f"项目: {name}\n文档检索: {question.strip()[:60]}"]
                for h in hits[:5]:
                    lines.append(
                        f"- {h.get('file') or h.get('source') or '?'} — {(h.get('fragment') or '')[:120]}"
                    )
                block = "\n".join(lines)
            else:
                block = f"项目: {name}\n文档检索: 未检索到相关内容（可换关键词, 或问 '有哪些文档'）"
        elif intent == "project_docs":
            docs = []
            sub = _docs_subpath(question)
            if root is not None:
                try:
                    from ..session.board import list_docs_with_status

                    docs = list_docs_with_status(
                        root, str(getattr(target, "id", "") or ""), subpath=sub
                    )[:20]
                except Exception:  # noqa: BLE001
                    docs = []
            if docs:
                lines = [f"项目: {name}"]
                if sub:
                    lines.append(f"目录: {sub}")
                for d in docs:
                    label = d.get("label") or d.get("name", "")
                    status = str(d.get("status") or "").strip()
                    lines.append(
                        f"- {label} — {'✅ 状态: ' + status if status else '状态未标注'}"
                    )
                if len(docs) >= 20:
                    lines.append("(仅显示前 20 个)")
                block = "\n".join(lines)
            else:
                block = f"项目: {name}\n文档: {'暂无（未生成）' if not sub else f'目录 {sub} 无文档（或路径不存在）'}"
        else:
            block = f"项目: {name}\n生命周期: {_stage(target)}"
    else:
        # 有查询意图但没匹配到具体项目 → 如实
        block = f"（未定位到具体项目 — 请说项目名，如'旅行记账'）\n项目列表: {', '.join(pp.name for pp in projects) if projects else '暂无项目'}"

    if model_line:
        block = f"{block}\n{model_line}"
    return block



#: 合法意图集合 (校验 LLM 输出)
VALID_INTENTS = {"list_projects", "project_status", "project_scan", "project_quality", "project_tasks",
                 "project_docs", "project_doc", "doc_search",
                 "deep_analyze", "task_action", "create_idea", "project_artifacts", "monitor", "settings", "project_action", "tools_list", "task_continue",
                 "model", "system_status", "create_project", "create_task", "git_push", "chat"}

_INTENT_LLM_PROMPT = """把用户的提问转成标准查询意图 (只输出 JSON, 不要别的):
{{"intent": "list_projects|project_status|project_scan|project_quality|project_tasks|project_docs|project_doc|doc_search|deep_analyze|task_action|create_idea|project_artifacts|monitor|settings|project_action|model|create_project|create_task|git_push|chat",
 "project": "用户提到的项目名 (没提到 → null)",
 "task": "用户要做的开发任务描述 (create_task 时填; 否则 null)}}
规则:
- 问项目列表/有哪些项目/重点项目 → list_projects
- 问某项目状态/阶段/进度/怎么样 → project_status (project=项目名)
- 扫描/全面看/盘点项目整体 (进度+计划+风险+建议) → project_scan
- 详细分析/深度分析 (多工具+可溯源) → deep_analyze
- 查有哪些内置工具 → tools_list
- 继续做/接着做某个任务 → task_continue (task=任务描述)
- 问质量/评分 → project_quality
- 问任务/todo → project_tasks
- 问文档清单/有哪些文档 → project_docs
- 问某份具体文档内容 (如 'README.md 讲了什么' / '看下 API规范.md') → project_doc
- 问在文档里检索/搜索关键词 (如 '文档里检索 错误码' / '哪些文档提到 X') → doc_search
- 问用什么模型 → model
- 完善/优化/修复/加功能/细化/拆解想法 → create_task (task=要做的事, project=目标项目)
- 推送代码到 github/远程 → git_push
- 标记任务完成/开始/改优先级/归档 → task_action (task=任务描述)
- 记录/新增想法 → create_idea (task=想法内容)
- 查产出物/版本链 → project_artifacts
- 查监控/告警/运维健康 → monitor
- 查设置/配置/agent/技能 → settings
- 项目改名/删除/收藏 → project_action
- 问系统/WebUI/服务运行状态 → system_status
- 其余闲聊 → chat
用户: {question}
"""


def parse_intent_llm(question: str, llm_fn: Any) -> dict[str, Any]:
    """意图解析: 确定性强关键词优先, LLM 只补参数 (project/task), 不覆写意图。

    规则 (Founder 2026-08-26 修复):
    - 确定性命中非 chat 意图 (webui状态/有哪些项目/做一个/完善…) → 意图锁定,
      LLM 结果只用于提取 project/task 参数 (防止 LLM 把强信号覆写成 chat)
    - 确定性 chat → 采信 LLM 意图 (若 LLM 返回合法非 chat)
    - LLM 失败 → 确定性 fallback
    """
    import re

    det = parse_intent(question)
    llm_result: dict[str, Any] | None = None
    if llm_fn is not None:
        try:
            raw = str(llm_fn(_INTENT_LLM_PROMPT.format(question=question)) or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                d = json.loads(m.group(0))
                intent = str(d.get("intent") or "").strip()
                if intent in VALID_INTENTS:
                    llm_result = {
                        "intent": intent,
                        "project": str(d.get("project") or "").strip() or None,
                        "task": str(d.get("task") or "").strip() or None,
                    }
        except Exception:  # noqa: BLE001 — LLM 解析失败 → fallback
            llm_result = None

    det_intent = det["intent"]
    if det_intent != "chat":
        # 确定性强信号意图锁定; LLM 只补参数
        if det_intent == "create_project":
            name = re.sub(r"^(做一个|创建一个|开发一个|帮我做个|帮我做|新建一个项目)\s*", "", question.strip())
            name = name.strip() or None
            return {"intent": "create_project", "project": (name[:24] if name else None), "task": None}
        return {
            "intent": det_intent,
            "project": (llm_result or {}).get("project"),
            "task": (llm_result or {}).get("task"),
        }
    # 确定性 chat → 采信 LLM 合法非 chat 意图
    if llm_result is not None and llm_result["intent"] != "chat":
        return llm_result
    return {"intent": "chat", "project": None, "task": None}


#: 系统状态专用输出 (禁止再说"未查询到" — 事实卡就是状态)
SYSTEM_STATUS_OUTPUT_PROMPT = """
【系统状态回答要求】
- 事实卡已给出 Web 工作台/前端/后端运行状态, 直接下结论:
  如 "Web 工作台运行正常 (前端 5180 运行中)" 或 "前端 5180 未运行"。
- 禁止再写 "未查询到 webUI 状态" / "事实卡仅包含基础环境信息" —— 事实卡就是状态。
"""

#: 标准输出格式 (LLM 转标准输出 — 只基于查询结果, 不编造)
STANDARD_OUTPUT_PROMPT = """
【输出要求 — 标准格式】
- 只使用上面"当前空间事实/查询结果"里的真实数据, 不要编造。
- 按以下固定结构回答 (用中文):
  【结论】一句话回答用户问题
  【数据】逐条列出真实数据 (来自查询结果)
  【数据来源】实时查询
  【建议】(可选, 仅基于数据给 1-2 条)
- 查询结果里没有的 → 在【结论】里明确说"当前未查询到", 不猜测。
"""


#: 意图 → 跳转深链 (发起/查看后直达对应功能页)
def intent_target(
    intent: str, *, project_id: str | None = None, project_name: str | None = None
) -> dict[str, str] | None:
    if intent == "chat":
        return None
    pid = project_id or ""
    name = project_name or "项目"
    targets = {
        "list_projects": ("#/workspace/projects", "查看项目列表"),
        "project_status": (f"#/project/{pid}", f"查看{name}概览"),
        "project_quality": (f"#/project/{pid}/quality", f"查看{name}质量"),
        "project_tasks": (f"#/project/{pid}/todo", f"查看{name}任务"),
        "project_docs": (f"#/project/{pid}/docs", f"查看{name}文档"),
        "model": ("#/workspace/settings", "打开设置"),
        "system_status": ("#/workspace", "返回工作台"),
        "create_project": None,
    }
    hit = targets.get(intent)
    if not hit:
        return None
    if hit is None:
        return None
    return {"url": hit[0], "label": hit[1]}

__all__ = ["parse_intent", "parse_intent_llm", "resolve_project", "build_facts", "STANDARD_OUTPUT_PROMPT", "SYSTEM_STATUS_OUTPUT_PROMPT", "VALID_INTENTS", "intent_target"]
