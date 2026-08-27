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
from . import llm_gateway as _lg  # S10-127 M1: 模型无关网关 (模块级, 测试可 patch)

# ---------------------------------------------------------------- DeepSeek 原生 FC

def _provider_conf(data_dir: str | Path) -> dict[str, Any]:
    """读 providers.json 定位可用 provider (deepseek) + env key (最后兜底)。"""
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


#: 模型装配缓存 (按 data_dir) — 避免每轮重建 plane/catalog/router
_model_conf_cache: dict[str, dict[str, Any]] = {}


def _resolve_model_conf(
    data_dir: str | Path,
    *,
    explicit_provider: str | None = None,
    explicit_model: str | None = None,
    need_fc: bool = False,
) -> dict[str, Any]:
    """S10-127 M1.2: 会话 LLM 装配 — LLMRouter(L1-L5) + ModelCatalog + ControlPlane。

    返回 {provider, model, base_url, api_key, capabilities?}; 任何异常 →
    旧 _provider_conf 兜底 (失败安全, 不阻断会话)。"""
    key = f"{data_dir}|{explicit_provider}|{explicit_model}|{need_fc}"
    if key in _model_conf_cache:
        return dict(_model_conf_cache[key])
    try:
        from ..llm_control import LLMControlPlane
        from ..model_catalog import ModelCatalog
        from ..llm_router import LLMRouter

        plane = LLMControlPlane(providers_file=Path(data_dir) / "providers.json")
        catalog = None
        if (Path(data_dir) / "models.json").is_file():
            catalog = ModelCatalog(models_file=Path(data_dir) / "models.json")
        router = LLMRouter(control_plane=plane, model_catalog=catalog)

        choice = None
        try:
            choice = router.route(
                explicit_provider=explicit_provider,
                explicit_model=explicit_model,
                required_capabilities=["fc"] if need_fc else None,
            )
        except Exception:  # noqa: BLE001 — 路由异常 → 走 fallback (不阻断)
            choice = None

        provider_id = None
        model_id = None
        if choice is not None:
            provider_id = choice.provider_id
            model_id = choice.model_id
        if provider_id is None:
            provider_id = plane.selected_provider_id()
        if provider_id is None:
            raise RuntimeError("no enabled provider with resolvable key")

        conf = plane.resolve_runtime_config(provider_id)
        if conf is None:
            raise RuntimeError(f"provider {provider_id} runtime config unavailable")
        # 模型选择: route choice > provider default_model > models[0] > old conf
        if model_id:
            conf["model"] = model_id
        else:
            pc = plane.get_provider(provider_id)
            if pc is not None:
                meta = dict(pc.metadata or {})
                conf["model"] = meta.get("default_model") or (pc.models[0] if pc.models else conf["model"])
        if catalog is not None:
            mi = catalog.get_model(conf["model"])
            if mi is not None:
                conf["capabilities"] = list(mi.capabilities or [])
        conf["provider"] = provider_id
        _model_conf_cache[key] = conf
        return dict(conf)
    except Exception:  # noqa: BLE001 — 装配失败 → 旧路径 (诚实降级)
        conf = _provider_conf(data_dir)
        return {"provider": conf["id"], "model": conf["model"], "base_url": conf["base_url"],
                "api_key": _api_key(conf)}


def call_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    data_dir: str | Path,
    temperature: float = 0.2,
    timeout: int = 120,
    explicit_provider: str | None = None,
    explicit_model: str | None = None,
) -> dict[str, Any]:
    """模型无关原生 function calling (S10-127 M1): LLMRouter 装配 + llm_gateway 适配。

    返回 OpenAI 形状: {content?, tool_calls?, no_fc?} — 失败抛异常 (调用方诚实降级)。
    no_fc=True 表示模型无 tool-use 能力 (M1.3: 调用方走纯文本收敛)。"""
    conf = _resolve_model_conf(
        data_dir, explicit_provider=explicit_provider, explicit_model=explicit_model,
        need_fc=bool(tools),
    )
    key = conf.get("api_key") or ""
    provider = conf.get("provider") or "deepseek"
    if not key and provider != "ollama":
        raise RuntimeError("LLM API key 未配置")
    caps = conf.get("capabilities")
    fc_ok = True
    if caps is not None:
        fc_ok = _lg.supports_tool_use(caps)
    if tools and not fc_ok:
        # M1.3 能力协商: 模型无 tool-use → 降级纯文本 (不传工具, 必收敛)
        tools = None
    resp = _lg.complete(
        messages, tools,
        provider_id=provider,
        model=conf.get("model") or "deepseek-chat",
        base_url=conf.get("base_url") or "",
        api_key=key,
        temperature=temperature,
        timeout=timeout,
    )
    if tools is None and not fc_ok:
        resp["no_fc"] = True
    return resp


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
        _fc("project_structure", "项目结构", "查看项目真实结构: 仓库顶层目录树/模块划分/文件分布/入口文件 (用户说'了解项目结构/有哪些模块/目录'时用)", {}),
        _fc("read_code", "读取代码", "读取指定文件的代码内容(带行号, 支持分页), 用于理解代码逻辑/实现/调用链。"
            "规则: 1) 通常从 offset=0 从头读起; 除非之前已读过该文件或用 offset 翻页; "
            "2) 读完必须基于内容向用户解释代码逻辑/关键函数/调用链, 不要只贴代码不给解释; "
            "3) 文件很大时分多次读取完整后再解释。参数 path 为仓库内相对路径, 或 keyword 定位文件",
            {"path": {"type": "string"}, "keyword": {"type": "string"}, "offset": {"type": "integer"}}),
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
        _fc("chain_start", "启动执行链(做人事)", "审批通过后启动执行链: 按计划建任务列表, 逐任务执行",
            {"goal": {"type": "string"}, "tasks": {"type": "array", "items": {"type": "object",
                     "properties": {"title": {"type": "string"}, "priority": {"type": "string"}}}}}),
        _fc("chain_next", "推进下一个任务", "执行链逐任务推进: 委派执行→验证→回写", {}),
        _fc("chain_status", "执行链进度", "查询当前执行链进度 (完成数/当前任务)", {}),
        _fc("knowledge_search", "知识检索", "在项目文档中检索知识点/历史结论, 返回片段+来源 (跨会话记忆/项目知识)",
            {"query": {"type": "string"}}, ["query"]),
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

_AGENT_SYSTEM = """你是 AI Factory 的会话 Agent（自主执行者）。

铁律 (v1.1.216 agentic 重写):
0. 【真正听懂用户】先语义理解用户意图 (提问/质疑/聊天/派活/开发/操作/情绪);
   意图不明或需求不清 → 追问澄清, 绝不猜、绝不强行套模板
1. 需要真实数据/执行 → 调工具 (带证据); 查不到 → 明确说"未查询到", 不编造
2. 用户质疑/纠正 → 先重新查证, 诚实承认错误或给出修正, 不嘴硬不糊弄
3. 开发类需求 → 先快速了解现状, 然后出计划 (目标/任务/顺序/验收) 请求用户审批, 不无限探索
4. 敏感动作 (建任务/改任务/委派执行/推送) → 用户明确要求或计划已审批才执行
5. 【主动收敛】每次工具调用后自评: 信息够 → 直接给最终答案 (带证据); 不够 → 继续查; 需澄清 → 提问
6. 简单查询/闲聊 → 直接答 (需要实时数据才调工具)
7. 【像人说话】自然段落回答, 不要用【结论】【数据】【数据来源】等模板标签;
   关键数字和来源保留, 但组织得像人报告; 简短场景≤3句, 复杂才展开
8. 用中文回答, 简洁准确"""


#: Reflection 自评提示 (v1.1.216: 每轮工具后注入, 主动收敛, 不等用户追问)
REFLECTION_PROMPT = """【自评收敛】基于以上工具结果, 回答前先检查两点:
① 信息足够吗? 不足 → 继续调用必要工具 (不重复已执行的; 最多再查几次); 需用户补充 → 提问
② 【答非所问检查】我即将给出的回答, 是否直接回答了用户当前的问题?
   - 先把用户的问题在心里重述一遍; 回答必须围绕它, 不能跑偏到别的方向
   - 如果工具结果与用户问题无关/不完整 → 不要硬答, 继续查或说明缺口
对齐后再给最终答案 (引用工具证据; 不编造)。给出最终答案时不要再调用工具。"""


# 循环护栏 (Founder: 3次loop后还不清醒就追问 — 不无限调研/无限重试)
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
        if tool_id == "project_structure":
            from .code_scan import scan_structure, format_structure

            rr = scan_structure(root, project_id)
            return {"ok": rr.get("ok"), "output": format_structure(rr, project_id)}
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
        if tool_id == "read_code":
            from .code_scan import locate_repo
            from pathlib import Path as _P

            repo = locate_repo(root, project_id)
            if repo is None:
                return {"ok": False, "error": "未定位到代码仓库目录"}
            repo = _P(repo).resolve()
            path = str(args.get("path") or "").strip()
            keyword = str(args.get("keyword") or "").strip()
            offset = int(args.get("offset") or 0)
            if path:
                target = (repo / path).resolve()
                if str(target) != str(repo) and not str(target).startswith(str(repo) + "/"):
                    return {"ok": False, "error": "路径越界: 只能读仓库内文件"}
                rel = path
            elif keyword:
                # 关键词定位: 文件名匹配优先, 再内容扫描 (纯 Python, 不依赖 subprocess/git_status)
                _code_exts = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
                              ".vue", ".swift", ".kt", ".c", ".cpp", ".h", ".md")
                hits: list[str] = []
                try:
                    for f in repo.rglob("*"):
                        if not f.is_file() or f.suffix not in _code_exts:
                            continue
                        if keyword in f.name:
                            hits.append(str(f))
                            if len(hits) >= 20:
                                break
                except Exception:  # noqa: BLE001
                    hits = []
                if not hits:
                    _scanned = 0
                    try:
                        for f in repo.rglob("*"):
                            if not f.is_file() or f.suffix not in _code_exts:
                                continue
                            _scanned += 1
                            if _scanned > 1200:
                                break
                            try:
                                if keyword in f.read_text(encoding="utf-8", errors="ignore")[:200000]:
                                    hits.append(str(f))
                                    if len(hits) >= 20:
                                        break
                            except OSError:
                                continue
                    except Exception:  # noqa: BLE001
                        pass
                if not hits:
                    return {"ok": False, "error": f"未找到含『{keyword}』的文件"}
                target = _P(hits[0]).resolve()
                try:
                    rel = str(target.relative_to(repo))
                except ValueError:
                    return {"ok": False, "error": "命中文件不在仓库内"}
            else:
                return {"ok": False, "error": "需要 path 或 keyword"}
            # 目录 → 返回文件/子目录列表 (模型据此决定读哪个文件)
            if target.is_dir():
                items = sorted(target.iterdir())
                lines = [f"目录 {rel}/ (共 {len(items)} 项):"]
                for f in items[:60]:
                    if f.is_dir():
                        lines.append(f"  📁 {f.name}/")
                    else:
                        try:
                            sz = f.stat().st_size
                        except OSError:
                            sz = 0
                        lines.append(f"  📄 {f.name} ({sz}B)")
                if len(items) > 60:
                    lines.append(f"  … 等 {len(items)} 项")
                return {"ok": True, "output": "\n".join(lines)}
            if not target.is_file():
                return {"ok": False, "error": f"路径不存在: {rel}"}
            if target.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
                                     ".vue", ".swift", ".kt", ".md", ".json", ".yaml", ".yml",
                                     ".sh", ".toml", ".sql", ".html", ".css", ".c", ".cpp", ".h"):
                return {"ok": False, "error": f"非代码/文本文件: {rel}"}
            try:
                lines = target.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError as exc:
                return {"ok": False, "error": f"读取失败: {exc}"}
            total = len(lines)
            start = max(0, min(offset, total))
            shown = lines[start:start + 120]
            header = f"文件 {rel} (共 {total} 行)"
            if start > 0:
                header += f" · 从第 {start + 1} 行"
            if start + len(shown) < total:
                header += f" · 已显示 {start + 1}-{start + len(shown)} 行, 需要继续可调 offset={start + len(shown)}"
            body = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(shown, start=start))
            return {"ok": True, "output": header + "\n" + body[:6000]}
        if tool_id == "knowledge_search":
            try:
                from ..retrieval.knowledge_store import rag_query

                query = str(args.get("query") or "").strip()
                if not query:
                    return {"ok": False, "error": "需要 query"}
                hits, _stats = rag_query(root, project_id, query, top_k=5)
                if not hits:
                    return {"ok": True, "output": "知识检索未命中 (项目文档中无相关内容)"}
                lines = [f"知识检索命中 {len(hits)} 条:"]
                for h in hits[:5]:
                    src = str(getattr(h, "source", "") or getattr(h, "doc", "") or "")
                    frag = str(getattr(h, "fragment", "") or getattr(h, "text", "") or "")[:200]
                    lines.append(f"- [{src}] {frag}")
                return {"ok": True, "output": "\n".join(lines)}
            except Exception as exc:  # noqa: BLE001 — 检索失败 → 诚实
                return {"ok": False, "error": f"知识检索失败: {exc}"}
        if tool_id == "chain_start":
            from .exec_state import ExecState

            plan = ctx.get("pending_plan") or {}
            tasks = args.get("tasks") or plan.get("tasks") or []
            goal = str(args.get("goal") or plan.get("goal") or "")[:120]
            if not tasks:
                return {"ok": False, "error": "没有任务 (先 plan_development 出计划)"}
            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            r = st.start({"goal": goal or "执行链", "tasks": tasks,
                          "acceptance": plan.get("acceptance") or []})
            st.save(root)
            if not r.get("ok"):
                return r
            return {"ok": True, "output": (
                f"✅ 执行链已启动: {goal or '执行链'} ({len(tasks)} 个任务)。"
                "说『继续』/『推进』逐任务执行; 『进度』查看状态; 敏感任务会先确认。")}
        if tool_id == "chain_next":
            from .exec_state import ExecState

            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            if st.state.get("status") != "running":
                return {"ok": False, "error": "没有运行中的执行链 (先 chain_start)"}

            def _exec_fn(task):
                # 委派外部 AI 执行 (真实): 路由选 agent → delegate_external
                from ..external_executor.router import route
                from ..external_executor.registry import build_registry

                adapters = build_registry(root).list() if root else []
                agents = []
                try:
                    import json as _j
                    d = _j.loads((Path(root) / "agents" / "agents.json").read_text(encoding="utf-8"))
                    ag = d.get("agents") if isinstance(d, dict) else None
                    if isinstance(ag, dict):
                        agents = [v for v in ag.values() if isinstance(v, dict)]
                except Exception:  # noqa: BLE001
                    agents = []
                rr = route(str(task.get("title") or ""), adapters, agents, root)
                pick = rr.get("pick")
                if not pick:
                    return {"ok": False, "error": "无可用外部执行器 (设置→外部AI 配置)"}
                from .external_tools import delegate_external

                return delegate_external(root, pick, str(task.get("title") or ""), project_id=project_id)

            r = st.next(_exec_fn)
            st.save(root)
            if r.get("finished"):
                # 全部完成 → 交付汇报
                d = st.deliver()
                return {"ok": True, "output": d.get("output")}
            return {"ok": r.get("ok"), "output": (
                f"任务『{r.get('task')}』: {'✅ 完成' if r.get('ok') else '❌ 失败'} · "
                f"{r.get('output') or ''} · 进度 {r.get('progress')}。说『继续』推进下一个。")}
        if tool_id == "chain_status":
            from .exec_state import ExecState

            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            stt = st.status()
            if stt.get("status") == "idle":
                return {"ok": True, "output": "当前没有执行链 (先出计划并审批, 说『开始执行』)"}
            lines = [f"执行链: {stt.get('status')} · 进度 {stt.get('progress')}"]
            lines.append("目标: " + str(stt.get("goal") or ""))
            for t in stt.get("tasks") or []:
                lines.append(f"- {t.get('status')} [{t.get('priority')}] {t.get('title')}")
            return {"ok": True, "output": "\n".join(lines)}
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
    context_view: str | None = None,
) -> dict[str, Any]:
    """AgentLoop v3 (agentic + reflection, v1.1.216).

    推翻 v2 的"意图门硬路由": 意图降级为软参考 (不拦截/不锁工具),
    模型在循环里自主决策 (调工具/直接答/追问), 每轮工具后 Reflection 自评主动收敛,
    硬收敛 (上限 + 强制收敛轮 + 3-loop 追问) 保留为最后兜底。
    返回 {answer, calls, evidence, intent, rejected?} — LLM 不可用 → rejected 回退。"""
    intent = understand_intent(
        question, llm_fn=lambda p: _simple_llm(p, data_dir=data_dir), history=history,
    )
    from .dialog_style import style_instruction

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "system", "content": format_intent(intent) + "\n" + route_for(intent["intent"])},
        {"role": "system", "content": style_instruction(question, intent.get("intent"), intent.get("emotion"))},
        {"role": "user", "content": question},
    ]
    # ---- 用户纠正信号: 检测"不是/我说的是/我要的是/理解错" → 强制重对齐 (治所答非所问) ----
    _correct_sigs = ("不是", "我说的是", "我要的是", "理解错", "答非所问", "没回答", "跑偏",
                     "不是这个", "不对", "你听错了", "我指的是", "你答的")
    if any(sig in question for sig in _correct_sigs):
        messages.append({"role": "system", "content": (
            "用户正在纠正方向(『" + question[:120] + "』)。"
            "请先重新理解用户真正要什么: 重述用户问题, 如果之前的理解/工具方向错了, 立刻纠正; "
            "回答必须围绕用户纠正后的真实意图, 不要继续原方向。"
        )})
    # ---- 代码 vs 文档偏好 (Founder: 要"架构/逻辑/实现"= 真实代码, 不是 docs 文档) ----
    _code_sigs = ("代码逻辑", "代码怎么", "怎么实现", "实现原理", "怎么做的", "代码结构",
                  "源码", "工作原理", "代码分析", "怎么写的", "逻辑", "架构", "实现细节")
    _doc_sigs = ("文档", "设计文档", "说明书", "readme", "文档目录", "方案书", "规格书")
    if any(sig in question for sig in _code_sigs) and not any(sig in question for sig in _doc_sigs):
        messages.append({"role": "system", "content": (
            "【重要】用户要的是【真实代码】: 请用 read_code / code_scan / search_code / project_structure "
            "读代码文件(.py/.ts 等) 分析代码逻辑、关键函数、调用链; "
            "不要读 docs/ 下的文档, 除非用户明确说'看文档/方案/说明书'。"
        )})
    # ---- 上下文连贯性: 话题账本视图优先, fallback 最近4轮 ----
    hist_block = context_view if (context_view or "").strip() else _history_text(history)
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
    # 质疑自查: 注入上一轮回答 → 上下文引导验证 (不锁工具, 模型自主)
    if intent["intent"] == "challenge":
        last_ai = _last_assistant_text(history)
        if last_ai:
            messages.append({"role": "system", "content": (
                f"用户质疑的上一轮回答: {last_ai[:800]}\n"
                "请重新查询真实数据验证, 然后诚实承认错误或给出修正。"
            )})
    # 跨会话记忆注入 (S-4): 项目级记忆 → 上下文 ("继续上次"可接上)
    try:
        from .project_memory import MemoryStore

        _mem_block = MemoryStore.load(data_dir, project_id).inject_block()
        if _mem_block:
            messages.append({"role": "system", "content": _mem_block})
    except Exception:  # noqa: BLE001 — 记忆不可用不阻断
        pass
    calls: list[dict[str, Any]] = []
    ctx: dict[str, Any] = {"session_store": session_store, "session_id": session_id,
                           "pending_plan": None, "intent": intent}
    ctx["llm_fn"] = lambda p: _simple_llm(p, data_dir=data_dir)
    tools = tool_schemas(data_dir)
    total_calls = 0
    import time as _time
    _start_ms = _time.monotonic() * 1000
    _converge = "reflection"
    try:
        for _ in range(max_rounds):
            resp = call_with_tools(messages, tools, data_dir=data_dir)
            tcs = resp.get("tool_calls") or []
            if not tcs:
                # S-2.2 无证据不结论: 查询/分析类完全没调工具直接答 → 强制先查再说
                if total_calls == 0 and intent["intent"] in ("question", "deep_analyze", "analyze"):
                    from .answer_verify import no_evidence_prompt

                    messages.append({"role": "system", "content": no_evidence_prompt()})
                    continue
                # 模型自主收敛 (直接回答/追问) — agentic: 不强制拦截
                if total_calls == 0:
                    _converge = "autonomous"
                _answer = resp.get("content") or "（模型未输出）"
                _audit_sess(data_dir, session_id, question, intent, calls,
                            total_calls, max_rounds, _start_ms, _converge, _answer)
                return {"answer": _answer, "calls": calls, "intent": intent,
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
            # 硬上限 → 停 (最后强制收敛)
            if total_calls >= MAX_TOOL_CALLS:
                break
            # Reflection 自评: 主动收敛 (不等 3-loop 兜底)
            messages.append({"role": "system", "content": REFLECTION_PROMPT})
        # 硬收敛轮 (不允许再调工具): 信息不足 → 明确追问 (Founder: 3 loop 后还不清醒就追问)
        from .answer_verify import self_check_prompt

        messages.append({"role": "system", "content": (
            "已调用工具达到上限。现在必须收敛，且【禁止再调用任何工具】。"
            "回答前【强制对齐】: 用户的问题是『" + question + "』, 你的回答必须直接回答它; "
            "如果工具结果答非所问, 明确说明并回到用户的问题; 如果信息仍不足 → 明确追问, 不硬答。"
            "如果用户纠正过方向(如说'不是XX/我说的是XX'), 以用户最新纠正为准。"
        )})
        messages.append({"role": "system", "content": self_check_prompt()})
        resp = call_with_tools(messages, None, data_dir=data_dir)  # 不给工具 → 必收敛
        content = resp.get("content") or ""
        _converge = "hard_cap" if total_calls >= MAX_TOOL_CALLS else "reflection"
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, _converge, content)
        return {"answer": content[:2000], "calls": calls, "intent": intent,
                "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls]}
    except Exception as exc:  # noqa: BLE001 — LLM 不可用 → 回退旧路由
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, "rejected", "")
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



def _audit_sess(data_dir, session_id, question, intent, calls, total_calls, rounds,
                start_ms, converge, answer) -> None:
    """会话审计落盘 (S-1; 失败静默)。"""
    try:
        from .session_audit import audit

        audit(
            data_dir, session_id=session_id, question=question,
            intent=str((intent or {}).get("intent") or ""),
            emotion=str((intent or {}).get("emotion") or ""),
            tools=[str(c.get("tool") or "") for c in calls],
            total_calls=total_calls, rounds=rounds,
            duration_ms=int((__import__("time").monotonic() * 1000) - start_ms),
            answer_len=len(str(answer or "")), converge=converge, answer=answer,
        )
    except Exception:  # noqa: BLE001 — 审计失败不阻断会话
        pass

def _simple_llm(prompt: str, *, data_dir: str | Path) -> str:
    """无工具单轮 LLM (plan_development 内部用)。"""
    try:
        r = call_with_tools([{"role": "user", "content": prompt}], None, data_dir=data_dir)
        return r.get("content") or ""
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- 兼容旧调用 (WebUI 接线用)

def run_agent(question, *, root, project_id, llm_fn, service=None, max_rounds=3,
                session_store=None, session_id="", history=None, context_view=None):
    """入口: 原生 FC (IntentCore 门); 失败 → 回退 prompt 协议 (v1) → 仍失败 → rejected。"""
    native = run_agent_native(question, data_dir=root, project_id=project_id, service=service,
                              session_store=session_store, session_id=session_id,
                              max_rounds=max_rounds, history=history, context_view=context_view)
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
