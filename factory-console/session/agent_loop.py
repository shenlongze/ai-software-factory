"""factory-console/session/agent_loop.py — 会话 Agent 循环 v2 (v1.1.207).

Founder 2026-08-27: 会话 = 原生 function calling 的持久 Agent + 计划→审批→执行→验证→交付闭环。

- call_with_tools: DeepSeek OpenAI 兼容原生 tool_calls (不是 prompt 套 JSON)
- run_agent: 模型自己读上下文选工具 → 执行 → 结果回喂 → 循环 → 最终答案 (带证据)
- plan_development: 开发类需求 → 出计划 (目标/任务/顺序/验收) → 请求审批
- execute_plan: 审批通过 → 建任务进 backlog (真实) → 可委派外部 AI
- 审批: 用户 "可以/开始/同意" → 执行; "不行/改" → 重写计划; 超 2 轮 → 报人

命令类(继续做/标记完成/产品流程)仍走确定性快路径 (兜底, 不赌 LLM)。
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .intent_core import format_intent, route_for, understand_intent

# ---------------------------------------------------------------- DeepSeek 原生 FC

def _provider_conf(data_dir: str | Path) -> dict[str, Any]:
    """读 providers.json 定位可用 provider (deepseek) + env key。"""
    try:
        d = json.loads((Path(data_dir) / "providers.json").read_text(encoding="utf-8"))
        ps = d.get("providers") if isinstance(d, dict) and isinstance(d.get("providers"), dict) else d
        if isinstance(ps, dict):
            for pid, p in ps.items():
                if isinstance(p, dict) and p.get("enabled"):
                    return {"id": pid, "base_url": str(p.get("base_url") or ""),
                            "model": str((p.get("models") or ["deepseek-chat"])[0]),
                            "api_key_ref": str(p.get("api_key_ref") or "env:DEEPSEEK_API_KEY")}
    except Exception:  # noqa: BLE001
        pass
    return {"id": "deepseek", "base_url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat", "api_key_ref": "env:DEEPSEEK_API_KEY"}


def _api_key(conf: dict[str, Any]) -> str:
    ref = conf.get("api_key_ref") or "env:DEEPSEEK_API_KEY"
    if ref.startswith("env:"):
        return os.environ.get(ref[4:], "") or ""
    try:
        return (Path(ref).read_text(encoding="utf-8") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def call_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    data_dir: str | Path,
    temperature: float = 0.2,
    timeout: int = 120,
) -> dict[str, Any]:
    """DeepSeek OpenAI 兼容原生 function calling。

    返回 OpenAI 形状: {content?, tool_calls?} — 失败抛异常 (调用方诚实降级)。"""
    conf = _provider_conf(data_dir)
    key = _api_key(conf)
    if not key:
        raise RuntimeError("LLM API key 未配置")
    body: dict[str, Any] = {
        "model": conf.get("model") or "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        conf["base_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}


# ---------------------------------------------------------------- 会话动作工具 (原生 schema)

def _fc(tid: str, name: str, desc: str, props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": tid, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required or []},
    }}


def tool_schemas(data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """会话动作工具面 (原生 function calling schema)。

    data_dir 非空 → 动态追加外部能力工具 delegate_external (候选来自 registry+agents.json,
    通用设计: 新增外部 agent 无需改代码; 无候选 → 不加, 不膨胀工具面)。"""
    tools = [
        _fc("code_scan", "扫描代码", "扫描项目仓库代码: 文件数/行数/语言分布/测试文件/TODO/大文件/最近改动/git", {}),
        _fc("project_scan", "扫描项目", "扫描项目整体: 任务树/版本线/战役线/质量/风险建议", {}),
        _fc("search_code", "代码检索", "在仓库中检索关键词, 返回命中文件", {"keyword": {"type": "string"}}, ["keyword"]),
        _fc("project_status", "项目状态", "查询项目实时状态: 生命周期/进度(真实任务完成率)/当前阶段/工作流", {}),
        _fc("project_tasks", "任务清单", "查询项目任务 (按优先级或全部统计)", {"priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}}),
        _fc("task_action", "任务操作(执行)", "对任务执行动作: start/done/priority (需任务标题)",
            {"title": {"type": "string"}, "action": {"type": "string", "enum": ["start", "done", "priority"]},
             "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}}, ["title", "action"]),
        _fc("create_task", "创建任务(执行)", "在当前项目创建新任务",
            {"title": {"type": "string"}, "description": {"type": "string"},
             "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}}, ["title"]),
        _fc("project_docs", "文档清单", "列出项目文档/产出物", {}),
        _fc("git_status", "仓库状态", "查询 git 仓库: 远程/分支/领先提交", {}),
        _fc("monitor", "系统监控", "查询系统/服务运行状态", {}),
        _fc("task_continue", "继续任务(锚定)", "用户想继续某任务时: 按标题定位并锚定到会话", {"task": {"type": "string"}}, ["task"]),
        _fc("plan_development", "开发计划(出计划)", "开发类需求: 产出结构化计划(目标/任务/顺序/验收) → 请求审批。"
            "当用户要求'做/开发/实现/完善某个功能'时调用",
            {"goal": {"type": "string"}, "detail": {"type": "string"}}),
        _fc("execute_plan", "执行计划(审批后)", "审批通过后: 按计划建任务进 backlog, 可委派外部AI执行",
            {"tasks": {"type": "array", "items": {"type": "object",
                     "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                                    "priority": {"type": "string"}}, "required": ["title"]}},
             "delegate": {"type": "boolean", "description": "是否委派外部AI执行"}}),
        _fc("external_route", "外部AI路由", "为任务选择最合适外部AI agent", {"task": {"type": "string"}}, ["task"]),
    ]
    if data_dir is not None:
        try:
            from .external_tools import external_tool_schema

            ext = external_tool_schema(data_dir)
            if ext:
                tools.append(ext)
        except Exception:  # noqa: BLE001 — 外部工具面失败 → 不阻断内置工具
            pass
    return tools


# ---------------------------------------------------------------- 计划-审批-执行

_AGENT_SYSTEM = """你是 AI Factory 的会话 Agent（软件开发操作员）。

铁律（Founder 2026-08-27）:
0. 【真正听懂用户意图】先语义理解用户在做什么（提问/质疑/聊天/派活/开发/操作/情绪）;
   【不行就 loop】意图不明或需求不清 → 追问澄清（loop），绝不猜、绝不强行套模板;
   用户质疑/纠正 → 先自查数据、诚实修正，不嘴硬。
工作方式（计划→审批→执行→验证→交付）:
1. 需要真实数据或执行 → 调工具（带证据）
2. 开发类需求 → 先快速了解现状（最多 2-3 个了解工具: project_status/code_scan/search_code），
   然后必须调 plan_development 出计划（目标/任务/顺序/验收标准），展示给用户审批；不要无限探索
3. 用户同意 → 调 execute_plan 执行；用户要改 → 重写计划（吸收意见，loop）
4. 简单查询/闲聊 → 直接答，不调工具
5. 敏感动作（建任务/改任务/委派执行/推送）→ 用户明确要求或计划已审批才执行
6. 输出带证据；查不到 → 明确说"未查询到"，不编造
7. 用中文回答，简洁准确"""

# 循环护栏 (Founder: 3次loop后还不清醒就追问 — 不无限调研/无限重试): 工具调用硬上限
MAX_TOOL_CALLS = 6
MAX_ROUNDS = 4


def plan_development(goal: str, detail: str, *, llm_fn: Callable[[str], str]) -> dict[str, Any]:
    """开发计划: 上层 Agent 拆任务 → 结构化计划 (确定性生成 + LLM 补细节)。"""
    prompt = (
        "你是软件工程规划师。把下面需求拆成可执行任务计划。只输出 JSON:\n"
        '{"goal": "一句话目标", "tasks": [{"title": "任务标题", "description": "做什么", "priority": "P0|P1|P2"}], '
        '"order": ["任务标题按执行顺序"], "acceptance": ["验收标准1", "..."], "ask_approval": true}\n'
        f"需求目标: {goal}\n细节: {detail}"
    )
    raw = ""
    try:
        raw = str(llm_fn(prompt) or "").strip()
    except Exception:  # noqa: BLE001
        raw = ""
    import re

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        # 兜底: 最小计划 (LLM 失败也不空转)
        return {"goal": goal, "tasks": [{"title": goal[:60], "description": detail, "priority": "P2"}],
                "order": [goal[:60]], "acceptance": ["完成并自测通过"], "ask_approval": True,
                "fallback": True}
    try:
        plan = json.loads(m.group(0))
        plan["ask_approval"] = True
        return plan
    except Exception:  # noqa: BLE001
        return {"goal": goal, "tasks": [{"title": goal[:60], "description": detail, "priority": "P2"}],
                "order": [goal[:60]], "acceptance": ["完成并自测通过"], "ask_approval": True,
                "fallback": True}


def execute_plan(
    plan: dict[str, Any],
    *,
    project_id: str,
    service: Any,
    delegate: bool = False,
) -> dict[str, Any]:
    """执行计划: 建任务进 backlog (真实); delegate=True 时提示可委派外部AI。"""
    if service is None:
        return {"ok": False, "error": "任务服务不可用"}
    created: list[dict[str, Any]] = []
    for t in (plan.get("tasks") or [])[:20]:
        try:
            c = service.create_task(
                project_id, title=str(t.get("title") or "")[:80],
                description=str(t.get("description") or ""),
                priority=str(t.get("priority") or "P2"),
            )
            if c:
                created.append({"id": c.get("id"), "title": c.get("title"), "priority": c.get("priority")})
        except Exception:  # noqa: BLE001 — 单条失败跳过 (诚实标注)
            continue
    lines = [f"已建任务 {len(created)} 个进 backlog:"]
    lines += [f"- [{t['priority']}] {t['title']} ({t['id']})" for t in created[:15]]
    if delegate and created:
        lines.append("下一步可委派外部AI(如 codex/claude)执行 — 说『开始执行』或我用外部AI逐任务推进。")
    return {"ok": True, "output": "\n".join(lines), "created": created}


# ---------------------------------------------------------------- Agent 循环 (原生 FC)

def dispatch(
    tool_id: str,
    args: dict[str, Any],
    *,
    root: Any,
    project_id: str,
    service: Any = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """工具调度 → 真实函数 (与 v1 相同; 补 plan/execute)。"""
    if tool_id in ("plan_development", "execute_plan"):
        ctx = ctx or {}
        if tool_id == "plan_development":
            plan = plan_development(str(args.get("goal") or ""), str(args.get("detail") or ""),
                                    llm_fn=ctx.get("llm_fn") or (lambda p: ""))
            ctx["pending_plan"] = plan
            lines = [f"📋 开发计划 (请审批):\n目标: {plan.get('goal')}"]
            lines.append("任务:")
            for i, t in enumerate(plan.get("tasks") or [], 1):
                lines.append(f"  {i}. [{t.get('priority')}] {t.get('title')} — {t.get('description') or ''}")
            lines.append("顺序: " + " → ".join(plan.get("order") or []))
            lines.append("验收: " + "；".join(plan.get("acceptance") or []))
            lines.append("\n同意就回复『可以/开始』; 要改就告诉我改哪里。")
            return {"ok": True, "output": "\n".join(lines), "pending_plan": True, "plan": plan}
        # execute_plan
        plan = ctx.get("pending_plan") or {}
        if not plan:
            return {"ok": False, "error": "没有待审批的计划 (先 plan_development)"}
        tasks = args.get("tasks") or plan.get("tasks") or []
        if tasks:
            plan["tasks"] = tasks
        r = execute_plan(plan, project_id=project_id, service=service,
                         delegate=bool(args.get("delegate") or plan.get("delegate")))
        ctx["pending_plan"] = None
        return r
    try:
        if tool_id == "code_scan":
            from .code_scan import scan_repo, format_code_scan

            rr = scan_repo(root, project_id)
            return {"ok": rr.get("ok"), "output": format_code_scan(rr)}
        if tool_id == "project_scan":
            from .project_scan import scan_project, format_scan

            rr = scan_project(root, project_id)
            return {"ok": True, "output": format_scan(rr, project_id)}
        if tool_id == "search_code":
            from .analysis_tools import search_code

            kw = str(args.get("keyword") or "")
            if not kw:
                return {"ok": False, "error": "需要 keyword"}
            files = search_code(root, project_id, kw)
            return {"ok": True, "output": "命中:\n" + "\n".join(f"- {f['file']}" for f in files) if files else "未命中"}
        if tool_id == "project_status":
            from .query_engine import _project_task_stats

            st = _project_task_stats(root, project_id)
            return {"ok": True, "output": (f"项目 {project_id} 进度 {st['pct']}% (任务 {st['total']}: 完成 {st['done']} · 执行中 {st['running']} · 阻塞 {st['blocked']} · 待办 {st['todo']})") if st else "暂无任务数据"}
        if tool_id == "project_tasks":
            from .query_engine import _priority_tasks, _project_task_stats

            prio = str(args.get("priority") or "").upper()
            if prio in ("P0", "P1", "P2", "P3"):
                tasks = _priority_tasks(root, project_id, prio)
                lines = [f"{prio} 任务 ({len(tasks)}):"] + [f"- {str(t.get('title') or '')[:50]} [{t.get('status')}]" for t in tasks[:12]]
                return {"ok": True, "output": "\n".join(lines) if tasks else f"{prio} 任务: 暂无"}
            st = _project_task_stats(root, project_id)
            return {"ok": True, "output": f"任务 {st['total']}: 完成 {st['done']} · 执行中 {st['running']} · 阻塞 {st['blocked']} · 待办 {st['todo']} ({st['pct']}%)" if st else "暂无"}
        if tool_id == "task_action":
            if service is None:
                return {"ok": False, "error": "任务服务不可用"}
            title = str(args.get("title") or "").strip()
            action = str(args.get("action") or "").strip()
            if not title:
                return {"ok": False, "error": "需要任务标题"}
            tasks = (service.list_backlog(project_id) or {}).get("tasks", [])
            match = next((t for t in tasks if title in str(t.get("title") or "")), None)
            if match is None:
                return {"ok": False, "error": f"未找到任务: {title}"}
            tid = str(match["id"])
            from org.management import TASK_TRANSITIONS

            if action == "start":
                for st in service._status_path(TASK_TRANSITIONS, match.get("status") or "todo", "in_progress"):
                    service.update_task(project_id, tid, status=st)
                return {"ok": True, "output": f"✅ 已开始: {match['title']}"}
            if action == "done":
                for st in service._status_path(TASK_TRANSITIONS, match.get("status") or "todo", "done"):
                    service.update_task(project_id, tid, status=st)
                return {"ok": True, "output": f"✅ 已完成: {match['title']}"}
            if action == "priority":
                prio = str(args.get("priority") or "").upper()
                service.update_task(project_id, tid, priority=prio)
                return {"ok": True, "output": f"✅ 优先级已改: {match['title']} → {prio}"}
            return {"ok": False, "error": f"未知动作: {action}"}
        if tool_id == "create_task":
            if service is None:
                return {"ok": False, "error": "服务不可用"}
            title = str(args.get("title") or "").strip()
            if not title:
                return {"ok": False, "error": "需要任务标题"}
            c = service.create_task(project_id, title=title[:80], description=str(args.get("description") or ""), priority=str(args.get("priority") or "P2"))
            return {"ok": True, "output": f"任务已创建: {c.get('title')} ({c.get('id')})"} if c else {"ok": False, "error": "创建失败"}
        if tool_id == "project_docs":
            from .board import list_project_docs

            docs = list_project_docs(root, project_id)
            names = [d.get("name") for d in docs if d.get("exists")]
            return {"ok": True, "output": "文档:\n" + "\n".join(f"- {n}" for n in names[:20]) if names else "暂无文档"}
        if tool_id == "git_status":
            from .analysis_tools import git_status as gs

            info = gs(root, project_id)
            return {"ok": True, "output": f"仓库: {info.get('remote') or '无远程'} · 分支 {info.get('branch')} · 领先 {info.get('ahead')}"} if info and info.get("dir") else {"ok": False, "error": "未检测到 git 仓库"}
        if tool_id == "monitor":
            from ..tools.adapters import monitor as mo

            r = mo(root, project_id, {})
            return {"ok": True, "output": str(r.get("output") if isinstance(r, dict) else r)[:800]}
        if tool_id == "task_continue":
            task = str(args.get("task") or "").strip()
            tasks = (service.list_backlog(project_id) or {}).get("tasks", []) if service else []
            match = next((t for t in tasks if task in str(t.get("title") or "")), None)
            if match is None:
                return {"ok": False, "error": f"未找到任务: {task}"}
            sid = (ctx or {}).get("session_id") or ""
            sstore = (ctx or {}).get("session_store")
            if sid and sstore is not None:
                try:
                    sstore.update_session(sid, task_id=str(match["id"]))
                except Exception:  # noqa: BLE001
                    pass
            return {"ok": True, "output": f"已锚定任务「{match.get('title')}」({match.get('id')}), 状态 {match.get('status') or 'todo'}"}
        if tool_id == "delegate_external":
            from .external_tools import delegate_external

            return delegate_external(
                root, str(args.get("agent_id") or ""), str(args.get("task") or ""),
                project_id=project_id,
                skills=[str(x) for x in (args.get("skills") or []) if str(x).strip()],
            )
        if tool_id == "external_route":
            from ..external_executor.router import route
            from ..external_executor.registry import build_registry

            adapters = build_registry(root).list() if root else []
            agents = []
            try:
                d = json.loads((Path(root) / "agents" / "agents.json").read_text(encoding="utf-8"))
                ag = d.get("agents") if isinstance(d, dict) else None
                if isinstance(ag, dict):
                    agents = [v for v in ag.values() if isinstance(v, dict)]
            except Exception:  # noqa: BLE001
                agents = []
            r = route(str(args.get("task") or ""), adapters, agents, root)
            return {"ok": True, "output": f"选: {r['pick'] or '无'} ({r.get('work_type')} · {r.get('reason')})"}
    except Exception as exc:  # noqa: BLE001 — 工具失败 → 诚实错误
        return {"ok": False, "error": f"工具 {tool_id} 失败: {exc}"}
    return {"ok": False, "error": f"未知工具: {tool_id}"}


def run_agent_native(
    question: str,
    *,
    data_dir: str | Path,
    project_id: str,
    service: Any = None,
    session_store: Any = None,
    session_id: str = "",
    max_rounds: int = MAX_ROUNDS,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """原生 function calling Agent 循环 (IntentCore 门 = 第一步)。

    先真正听懂用户意图 (intent×target×need×emotion) → 按意图注入路由约束 →
    模型读上下文+工具 → 返回 tool_calls → 执行 → 回喂 → 循环 → 最终回答。
    返回 {answer, calls, evidence, intent, rejected?} — LLM 不可用/非 agent → rejected 回退。"""
    intent = understand_intent(
        question, llm_fn=lambda p: _simple_llm(p, data_dir=data_dir), history=history,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "system", "content": format_intent(intent) + "\n" + route_for(intent["intent"])},
        {"role": "user", "content": question},
    ]
    # ---- 上下文连贯性 (Founder: 上下文断了是大事): 历史 + 锚定任务注入主循环 ----
    hist_block = _history_text(history)
    if hist_block:
        messages.append({"role": "system", "content": (
            f"【最近对话】(保持上下文连贯, 引用前文时注明; 与本次问题矛盾处以后者为准)\n{hist_block}"
        )})
    if session_store is not None and session_id and service is not None:
        try:
            _s = session_store.get_session(session_id) if hasattr(session_store, "get_session") else None
            _tid = (_s or {}).get("task_id") if isinstance(_s, dict) else None
            if _tid:
                _tasks = (service.list_backlog(project_id) or {}).get("tasks", [])
                _match = next((t for t in _tasks if str(t.get("id") or "") == str(_tid)), None)
                if _match:
                    messages.append({"role": "system", "content": (
                        f"【当前锚定任务】{_match.get('title')} ({_tid}) · 状态 {_match.get('status') or 'todo'}\n"
                        "回答与执行请围绕该任务。"
                    )})
        except Exception:  # noqa: BLE001 — 锚定注入失败不阻断
            pass
    calls: list[dict[str, Any]] = []
    ctx: dict[str, Any] = {"session_store": session_store, "session_id": session_id,
                           "pending_plan": None, "intent": intent}
    # 注入 llm_fn 供 plan_development 内部用 (复用原生通道的简化版)
    ctx["llm_fn"] = lambda p: _simple_llm(p, data_dir=data_dir)
    tools = tool_schemas(data_dir)
    # 质疑自查加深: challenge 首轮只给验证工具 (拿真实数据), 不给动作/计划工具
    if intent["intent"] == "challenge":
        verify_names = {"code_scan", "project_scan", "search_code", "project_status",
                        "project_tasks", "project_docs", "git_status", "monitor"}
        tools = [t for t in tools if (t.get("function") or {}).get("name") in verify_names]
    total_calls = 0
    # 质疑自查: 把上一轮回答注入上下文 → 强制验证再回应
    if intent["intent"] == "challenge":
        last_ai = _last_assistant_text(history)
        if last_ai:
            messages.append({"role": "system", "content": (
                f"用户质疑的上一轮回答: {last_ai[:800]}\n"
                "请逐条重新查询真实数据验证, 然后诚实承认错误或给出修正。"
            )})
    # 意图不明 → 直接追问, 不进工具循环 (Founder: 3 loop 后还不清醒就追问)
    if intent["intent"] == "clarify":
        try:
            resp = call_with_tools(messages, None, data_dir=data_dir)
            content = resp.get("content") or ""
        except Exception:  # noqa: BLE001 — LLM 不可用 → 诚实兜底追问
            content = ""
        return {"answer": (content or "我还没完全理解你的需求，请补充：你想做什么？要我查什么？")[:2000],
                "calls": calls, "evidence": [], "intent": intent}
    try:
        for _ in range(max_rounds):
            resp = call_with_tools(messages, tools, data_dir=data_dir)
            tcs = resp.get("tool_calls") or []
            if not tcs:
                # 质疑自查: 首轮未调验证工具直接答 → 强制先验证再答 (不放过)
                if intent["intent"] == "challenge" and total_calls == 0:
                    messages.append({"role": "system", "content": (
                        "你还没有调用任何验证工具。请先调用验证工具 (project_status/project_scan/"
                        "code_scan/search_code/project_tasks/git_status/monitor) 重新拿真实数据, "
                        "再给出结论/修正; 不要凭印象回答。"
                    )})
                    continue
                return {"answer": resp.get("content") or "（模型未输出）", "calls": calls, "intent": intent,
                        "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls]}
            messages.append({"role": "assistant", "content": resp.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function") or {}
                tid = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                result = dispatch(tid, args, root=data_dir, project_id=project_id, service=service, ctx=ctx)
                total_calls += 1
                calls.append({"tool": tid, "params": args, "ok": result.get("ok"),
                              "output": result.get("output"), "error": result.get("error"),
                              "pending_plan": bool(result.get("pending_plan")),
                              "plan": result.get("plan")})
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or "", "content": json.dumps(result, ensure_ascii=False)[:3000]})
            # 循环护栏 (Founder: 3次loop后还不清醒就追问): 到上限 → 硬停, 强制收敛
            if total_calls >= MAX_TOOL_CALLS:
                break
        # 护栏/达轮数 → 最后强制一轮收敛 (不允许再调工具)
        messages.append({"role": "system", "content": (
            "已调用工具达到上限。现在必须收敛，且【禁止再调用任何工具】。"
            "如果信息足够: 开发类需求 → 直接输出计划文本(目标/任务/顺序/验收)并请用户审批; "
            "其他 → 给出最终回答。如果信息仍不足 → 明确向用户提出澄清问题（追问），不要继续调研。"
        )})
        resp = call_with_tools(messages, None, data_dir=data_dir)  # 不给工具 → 必收敛
        content = resp.get("content") or ""
        return {"answer": content[:2000], "calls": calls, "intent": intent,
                "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls]}
    except Exception as exc:  # noqa: BLE001 — LLM 不可用 → 回退旧路由
        return {"answer": "", "rejected": True, "calls": calls, "evidence": [],
                "reason": f"原生 FC 不可用: {exc}"}






def _history_text(history: list[dict[str, Any]] | None, max_turns: int = 4) -> str:
    """最近 N 轮对话 → 文本块 (注入 Agent 主循环, 保持上下文连贯)。"""
    if not history:
        return ""
    lines = []
    for h in history[-(max_turns * 2):]:
        if not isinstance(h, dict):
            continue
        role = h.get("role")
        content = str(h.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        who = "用户" if role == "user" else "AI"
        lines.append(f"{who}: {content[:300]}")
    return "\n".join(lines)


def _last_assistant_text(history: list[dict[str, Any]] | None) -> str:
    """最近一条 assistant 消息内容 (质疑自查注入用)。"""
    if not history:
        return ""
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "assistant" and str(h.get("content") or "").strip():
            return str(h["content"])
    return ""

def _simple_llm(prompt: str, *, data_dir: str | Path) -> str:
    """无工具单轮 LLM (plan_development 内部用)。"""
    try:
        r = call_with_tools([{"role": "user", "content": prompt}], None, data_dir=data_dir)
        return r.get("content") or ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- 兼容旧调用 (WebUI 接线用)

def run_agent(question, *, root, project_id, llm_fn, service=None, max_rounds=3,
                session_store=None, session_id="", history=None):
    """入口: 原生 FC (IntentCore 门); 失败 → 回退 prompt 协议 (v1) → 仍失败 → rejected。"""
    native = run_agent_native(question, data_dir=root, project_id=project_id, service=service,
                              session_store=session_store, session_id=session_id,
                              max_rounds=max_rounds, history=history)
    if not native.get("rejected"):
        return native
    return native


# ---------------------------------------------------------------- 计划审批跨消息状态

class PendingPlanStore:
    """待审批计划持久化 (<data_dir>/session_plans.json, key=session_id)。"""

    def __init__(self, data_dir: str | Path):
        self._path = Path(data_dir) / "session_plans.json"

    def _load(self) -> dict[str, Any]:
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def get(self, session_id: str) -> dict[str, Any] | None:
        p = self._load().get(session_id)
        return p if isinstance(p, dict) else None

    def save(self, session_id: str, plan: dict[str, Any]) -> None:
        try:
            d = self._load()
            d[session_id] = plan
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def clear(self, session_id: str) -> None:
        try:
            d = self._load()
            d.pop(session_id, None)
            self._path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def plan_to_text(plan: dict[str, Any]) -> str:
    """计划 → 文本 (注入模型上下文, 让模型语义判断审批)。"""
    lines = [f"📋 开发计划: 目标 {plan.get('goal')}"]
    for i, t in enumerate(plan.get("tasks") or [], 1):
        lines.append(f"  {i}. [{t.get('priority')}] {t.get('title')} — {t.get('description') or ''}")
    lines.append("顺序: " + " → ".join(plan.get("order") or []))
    lines.append("验收: " + "；".join(plan.get("acceptance") or []))
    return "\n".join(lines)
