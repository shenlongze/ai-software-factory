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
from pathlib import Path
from typing import Any

#: 确定性意图关键词 (顺序即优先级)
_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("create_project", ("做一个", "创建一个", "开发一个", "帮我做个", "帮我做", "新建一个项目", "做个app", "做个 App", "做个app")),
    ("create_task", ("完善", "优化", "改进", "修复", "修一下", "加个", "增加", "做一下")),
    ("list_projects", ("有哪些项目", "几个项目", "项目列表", "所有项目", "空间内", "重点项目", "项目清单")),
    ("project_quality", ("质量", "评分", "质量分", "分数")),
    ("project_tasks", ("任务", "todo", "待办", "backlog", "排期")),
    ("project_docs", ("文档", "文档清单", "产物", "产出物")),
    ("project_status", ("状态", "阶段", "进行", "进度", "生命周期", "卡点", "怎么样", "进展")),
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


def build_facts(
    question: str,
    *,
    scope: str,
    project_id: str | None,
    projects: list[Any],
    root: Path | None,
    model_line: str = "",
    hint_project: str | None = None,
) -> str:
    """意图 → 真实数据事实块 (查询不到 → 如实待查证; 不编造)。"""
    intent = parse_intent(question)["intent"]
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
        if intent == "project_status":
            block = (
                f"项目: {name}\n生命周期: {_stage(target)}\n"
                f"进度: {getattr(target, 'progress', None) or 0}\n"
                f"当前阶段: {getattr(target, 'current_stage', None) or '—'}\n"
                f"工作流: {getattr(target, 'workflow_status', None) or '未启动'}"
            )
        elif intent == "project_quality":
            score = None
            if root is not None:
                qf = Path(root) / "projects" / str(getattr(target, "id", "") or "") / "quality.json"
                d = _read_json_file(qf)
                if d is not None and isinstance(d.get("score"), (int, float)):
                    score = d["score"]
            block = f"项目: {name}\n质量分: {score if score is not None else '未生成'}"
        elif intent == "project_tasks":
            tasks = getattr(target, "tasks", None) or {}
            counts = " · ".join(f"{k}:{v}" for k, v in sorted(tasks.items())) if tasks else "暂无任务"
            block = f"项目: {name}\n任务统计: {counts}"
        elif intent == "project_docs":
            docs = []
            if root is not None:
                try:
                    from ..session.board import list_project_docs

                    docs = [
                        d.get("label") or d.get("name", "")
                        for d in list_project_docs(root, str(getattr(target, "id", "") or ""))
                        if d.get("exists")
                    ][:20]
                except Exception:  # noqa: BLE001
                    docs = []
            block = f"项目: {name}\n文档: {', '.join(docs) if docs else '暂无（未生成）'}"
        else:
            block = f"项目: {name}\n生命周期: {_stage(target)}"
    else:
        # 有查询意图但没匹配到具体项目 → 如实
        block = f"（未定位到具体项目 — 请说项目名，如'旅行记账'）\n项目列表: {', '.join(pp.name for pp in projects) if projects else '暂无项目'}"

    if model_line:
        block = f"{block}\n{model_line}"
    return block



#: 合法意图集合 (校验 LLM 输出)
VALID_INTENTS = {"list_projects", "project_status", "project_quality", "project_tasks",
                 "project_docs", "model", "create_project", "create_task", "chat"}

_INTENT_LLM_PROMPT = """把用户的提问转成标准查询意图 (只输出 JSON, 不要别的):
{{"intent": "list_projects|project_status|project_quality|project_tasks|project_docs|model|create_project|create_task|chat",
 "project": "用户提到的项目名 (没提到 → null)",
 "task": "用户要做的开发任务描述 (create_task 时填; 否则 null)}}
规则:
- 问项目列表/有哪些项目/重点项目 → list_projects
- 问某项目状态/阶段/进度/怎么样 → project_status (project=项目名)
- 问质量/评分 → project_quality
- 问任务/todo → project_tasks
- 问文档/产物 → project_docs
- 问用什么模型 → model
- 完善/优化/修复/加功能 → create_task (task=要做的事, project=目标项目)
- 其余闲聊 → chat
用户: {question}
"""


def parse_intent_llm(question: str, llm_fn: Any) -> dict[str, Any]:
    """意图解析: 确定性高置信动作优先, 否则 LLM JSON; 失败 → 确定性 fallback。

    创建类动作 (create_project) 是强关键词信号 — 不交给 LLM 覆写成 chat,
    并从问句确定性提取项目名。
    """
    import re

    det = parse_intent(question)
    if det["intent"] == "create_project":
        name = re.sub(r"^(做一个|创建一个|开发一个|帮我做个|帮我做|新建一个项目)\s*", "", question.strip())
        name = name.strip() or None
        return {"intent": "create_project", "project": (name[:24] if name else None)}
    if llm_fn is not None:
        try:
            raw = str(llm_fn(_INTENT_LLM_PROMPT.format(question=question)) or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                d = json.loads(m.group(0))
                intent = str(d.get("intent") or "").strip()
                if intent in VALID_INTENTS:
                    project = str(d.get("project") or "").strip() or None
                    task = str(d.get("task") or "").strip() or None
                    return {"intent": intent, "project": project, "task": task}
        except Exception:  # noqa: BLE001 — LLM 解析失败 → fallback
            pass
    det_intent = det["intent"]
    if det_intent == "create_task":
        desc = re.sub(r"^(请|帮我|给|为|对)?\s*", "", question.strip())
        return {"intent": "create_task", "project": None, "task": desc[:80]}
    return {"intent": det_intent, "project": None, "task": None}


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
        "create_project": None,
    }
    hit = targets.get(intent)
    if not hit:
        return None
    if hit is None:
        return None
    return {"url": hit[0], "label": hit[1]}

__all__ = ["parse_intent", "parse_intent_llm", "resolve_project", "build_facts", "STANDARD_OUTPUT_PROMPT", "VALID_INTENTS", "intent_target"]
