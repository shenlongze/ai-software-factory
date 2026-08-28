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
import re
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
                conf["context_window"] = mi.context_window
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
        _fc("scan_todos", "扫描TODO", "列出仓库 TODO/FIXME 具体位置 (文件:行:内容), 可按路径过滤",
            {"path": {"type": "string", "description": "可选: 路径子串过滤 (如 factory-console/session)"},
             "max_items": {"type": "integer"}}),
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
        _fc("chain_start", "启动执行链(做人事)", "审批通过后启动执行链: 按计划建任务列表, 逐任务执行; "
            "auto=true 时后台自动执行全部任务 (Promised Work), 完成主动推送交付汇报",
            {"goal": {"type": "string"}, "tasks": {"type": "array", "items": {"type": "object",
                     "properties": {"title": {"type": "string"}, "priority": {"type": "string"}}}},
             "auto": {"type": "boolean", "description": "true=后台自动执行全部任务并主动回报"}}),
        _fc("chain_next", "推进下一个任务", "执行链逐任务推进: 委派执行→验证→回写", {}),
        _fc("chain_status", "执行链进度", "查询当前执行链进度 (完成数/当前任务)", {}),
        _fc("gateway_status", "外部任务进度", "查询外部执行器任务进度 (最近/按项目/统计)", {"project": {"type": "string"}}),
        _fc("knowledge_search", "知识检索", "在项目文档中检索知识点/历史结论, 返回片段+来源 (跨会话记忆/项目知识)",
            {"query": {"type": "string"}}, ["query"]),
        # ---- W4 (v1.1.250): Core Memory — 模型自编辑 human 块 (Letta self-editing) ----
        _fc("memory_update", "更新Core记忆(Human块)", "自编辑长期记忆 (Letta core memory): 记录用户偏好/项目上下文/关键事实/任务状态, "
            "下次会话延续。重要信息值得记 → 调用; append=true 追加到已有记忆。上限 1500 字符",
            {"text": {"type": "string"}, "append": {"type": "boolean"}}, ["text"]),
        # ---- S8 (v1.1.246): 通用执行/搜索工具 — 一劳永逸, 不预置专用工具 ----
        _fc("web_search", "网络搜索", "在互联网搜索 (DuckDuckGo, 无需key)。返回标题+链接+摘要。"
            "【何时用】本地/项目内/常识解决不了, 或需要实时/最新/外部信息, 或用户明确要求'去网上查'时才用; "
            "不要对常识/项目内问题联网搜索",
            {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
        _fc("web_fetch", "网页抓取", "抓取指定 URL 内容 (转纯文本, 去标签)。用于: 打开搜索结果链接、调用公开 JSON/文本 API。"
            "超时 15s, 上限 20k 字符",
            {"url": {"type": "string"}, "max_chars": {"type": "integer"}}, ["url"]),
        _fc("bash_exec", "本地命令执行(沙箱)", "在本地沙箱执行 shell 命令。只读查询类直接执行 "
            "(curl/python3/grep/cat/ls/echo 等); 写操作/敏感命令 (重定向/删改/安装/git push) 需用户批准; 危险命令被拦截。"
            "用于: 本地计算、调 API、跑脚本、处理文件。默认超时 30s",
            {"command": {"type": "string"}, "timeout": {"type": "integer"}}, ["command"]),
    ]
    if data_dir is not None:
        try:
            from .external_tools import external_tool_schema

            ext = external_tool_schema(data_dir)
            if ext:
                tools.append(ext)
        except Exception:  # noqa: BLE001 — 外部工具面失败 → 不阻断内置工具
            pass
        # S10-127 P2.3: MCP 工具进工具面 (mcp__<server>__<tool>; 失败跳过)
        try:
            from .mcp_tools import mcp_tool_schemas

            tools.extend(mcp_tool_schemas(data_dir))
        except Exception:  # noqa: BLE001 — MCP 不可用不阻断
            pass
    return tools


#: S10-127 M2.2 动态工具面 — 首轮核心工具 (通用高频, 覆盖大多数会话场景)
# W3 (v1.1.249): Progressive Disclosure (Pi) — 首轮只 5 个最高频; 其余靠预检索 top-k + tool_search 按需
CORE_TOOL_IDS = [
    "project_status", "project_scan", "code_scan", "bash_exec", "web_search",
]


def _initial_tools(
    question: str,
    all_tools: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """首轮可见工具 = 核心(5) + 按问题预检索 top-k + tool_search 元工具 (W3 精简).

    全量 25 工具不塞给弱模型 — 首轮 ≤9 个, 选择压力骤降; 其他走 tool_search 按需。
    """
    from .tool_search import TOOL_SEARCH_ID, discover_tools, tool_search_schema

    want = {t: None for t in CORE_TOOL_IDS}  # 保序
    for t in all_tools:
        name = str((t.get("function") or {}).get("name") or "")
        if name in want:
            want[name] = t
    for t in discover_tools(all_tools, question, top_k=top_k):
        name = str((t.get("function") or {}).get("name") or "")
        if name not in want:
            want[name] = t
    out = [t for t in want.values() if t is not None]
    out.append(tool_search_schema())
    return out


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

_hooks_instance = None


def _chain_auto_worker(root: Any, project_id: str, session_id: str, service: Any, st: Any) -> None:
    """W1 (v1.1.248): Promised Work (OpenClaw) — 后台自动逐任务执行到完成.

    每步: 委派外部AI → 验证 → 回写 backlog → 同步进度卡;
    全部完成: deliver 交付汇报 → 追加会话消息 (主动回报, 用户不用手动"继续")。
    失败安全: 任何异常吞掉不阻断执行链。
    """
    try:
        from ..external_executor.gateway import gateway_execute

        def _exec_fn(task):
            title = str(task.get("title") or "")
            r = gateway_execute(title, data_dir=root, project_id=project_id, max_retry=1)
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error") or "外部执行失败"}
            return {"ok": True,
                    "output": (f"{r.get('executor')} 完成 (任务 {r.get('task_id')}) · "
                               f"验证 {r.get('verify', {}).get('result') or 'unknown'} · "
                               f"{str(r.get('output') or '')[:300]}"),
                    "verify": dict(r.get("verify") or {}),
                    "exec_ref": str(r.get("task_id") or "")}

        from .progress_card import sync_from_exec

        while st.state.get("status") == "running":
            r = st.next(_exec_fn)
            st.save(root)
            # 回写 backlog (Hermes kanban_complete 思路)
            _idx = st.state.get("current_index", -1)
            _stasks = st.state.get("tasks") or []
            if 0 <= _idx < len(_stasks) and service is not None:
                _cur = _stasks[_idx]
                _bid = str(_cur.get("backlog_id") or "")
                if _bid:
                    try:
                        _v = _cur.get("verify") or {}
                        service.finish_task_exec(
                            project_id, _bid,
                            success=_cur.get("status") == "done",
                            exec_ref=str(_v.get("exec_ref") or "") or _bid,
                            exec_result=(f"{str(_cur.get('result') or '')[:300]}"
                                         + (f" · 验证 {_v.get('result') or 'unknown'}" if _v else "")),
                            actor="session-chain-auto",
                        )
                    except Exception:  # noqa: BLE001 — 回写失败不阻断
                        pass
            try:
                sync_from_exec(root, session_id, st)
            except Exception:  # noqa: BLE001 — 落卡失败不阻断
                pass
            if r.get("finished") or not r.get("ok"):
                break
        # 完成 → 交付汇报主动推送会话 (Promised Work)
        try:
            d = st.deliver()
            if d.get("ok"):
                from ..console_sessions import SessionStore

                store = SessionStore(Path(root) / "console_sessions.json")
                if store.get_session(session_id):
                    store.append_message(session_id, "assistant", d.get("output"),
                                         meta={"kind": "chain_delivery"})
        except Exception:  # noqa: BLE001 — 推送失败不阻断
            pass
    except Exception:  # noqa: BLE001 — 后台异常不阻断
        pass


def _get_hooks():
    """会话级 Hooks 单例 (S10-127 M4) — 延迟构造, 不拖 session 包。"""
    global _hooks_instance
    if _hooks_instance is None:
        from .session_hooks import build_default_hooks

        _hooks_instance = build_default_hooks()
    return _hooks_instance


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
    # S10-127 M4.3 + P1.5: PreToolUse 动作门 (deny 短路; 权限模式 plan/auto)
    try:
        from .session_hooks import load_permission_mode

        _hres = _get_hooks().fire("PreToolUse", {
            "tool_id": tool_id, "args": args, "project_id": project_id,
            "session_id": (ctx or {}).get("session_id") or "",
            "data_dir": str(root) if root else "",
            "permission_mode": load_permission_mode(str(root) if root else None)})
        _denied = _get_hooks().denied(_hres)
        if _denied:
            return {"ok": False, "error": f"已拦截 (S10-127 M4.3): {_denied.get('reason')}"}
    except Exception:  # noqa: BLE001 — hooks 失败不阻断
        pass
    if tool_id in ("plan_development", "execute_plan"):
        ctx = ctx or {}
        if tool_id == "plan_development":
            plan = plan_development(str(args.get("goal") or ""), str(args.get("detail") or ""),
                                    llm_fn=ctx.get("llm_fn") or (lambda p: ""))
            ctx["pending_plan"] = plan
            # P0-B (v1.1.244): 计划落 durable progress_card (OpenClaw 思路)
            try:
                from .progress_card import save_from_plan

                save_from_plan(root, (ctx or {}).get("session_id") or "", plan)
            except Exception:  # noqa: BLE001 — 落卡失败不阻断
                pass
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
        if tool_id == "scan_todos":
            from .code_scan import format_todos, scan_todos

            _pf = str(args.get("path") or "").strip()
            _mi = int(args.get("max_items") or 50)
            _r = scan_todos(root, project_id, path_filter=_pf, max_items=_mi)
            return {"ok": _r.get("ok", False), "output": format_todos(_r),
                    "error": _r.get("error") or ""}
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
            # S10-127 M3.3: 续接信息 — Spine handoff/resume + 执行链 checkpoint
            _resume_lines = [f"已锚定任务「{match.get('title')}」({match.get('id')}), 状态 {match.get('status') or 'todo'}"]
            try:
                from .handoff import ProjectSpine

                _sp = ProjectSpine.load(root, project_id)
                _rp = _sp.data.get("resume_point") or {}
                if _rp.get("task_id") == str(match.get("id")):
                    _resume_lines.append(f"上次进展: {_rp.get('note') or '—'}")
                _hc = _sp.data.get("handoff_card") or {}
                if _hc.get("progress"):
                    _resume_lines.append(f"交接进度: {_hc.get('progress')}")
                    for _ns in (_hc.get("next_steps") or [])[:3]:
                        _resume_lines.append(f"下一步: {_ns}")
            except Exception:  # noqa: BLE001 — Spine 不可用不阻断
                pass
            try:
                from .exec_state import ExecState

                _st = ExecState.load(root, sid or "")
                if _st.state.get("status") == "running":
                    _prog = _st.progress() or {}
                    _resume_lines.append(f"执行链进度: {_prog.get('progress') or _prog}")
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "output": "\n".join(_resume_lines)}
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
        # ---- W4 (v1.1.250): Core Memory 自编辑 ----
        if tool_id == "memory_update":
            from .memory_core import update_human

            return {
                "ok": True,
                "output": "已更新 Core Memory (human 块) · " + json.dumps(
                    update_human(root, str(args.get("text") or ""), append=bool(args.get("append"))),
                    ensure_ascii=False)[:500],
                "need_approval": False,
            }
        # ---- S8 (v1.1.246): 通用搜索/执行 ----
        if tool_id == "bash_exec":
            from .web_tools import bash_exec

            _cmd = str(args.get("command") or "")
            _r = bash_exec(_cmd, timeout=int(args.get("timeout") or 30))
            if _r.get("need_approval"):
                # S8-4: 登记待批准 → 返回 approval_id (前端/会话显示批准卡)
                from .approval_store import request_approval

                _ap = request_approval(root, (ctx or {}).get("session_id") or "", _cmd)
                _r["approval_id"] = _ap.get("id") or ""
                _r["command"] = _cmd[:2000]
                _r["error"] = (
                    f"该命令涉及写操作/敏感操作, 需要批准后执行。"
                    f"审批ID: {_ap.get('id') or 'N/A'} · 命令: {_cmd[:200]}。"
                    "请用户确认批准 (或调用批准 API)。"
                )
            return _r
        if tool_id == "web_search":
            from .web_tools import web_search

            return web_search(
                str(args.get("query") or ""),
                max_results=int(args.get("max_results") or 8),
            )
        if tool_id == "web_fetch":
            from .web_tools import web_fetch

            return web_fetch(
                str(args.get("url") or ""),
                max_chars=int(args.get("max_chars") or 20_000),
            )
        if tool_id == "chain_start":
            from .exec_state import ExecState

            plan = ctx.get("pending_plan") or {}
            tasks = args.get("tasks") or plan.get("tasks") or []
            goal = str(args.get("goal") or plan.get("goal") or "")[:120]
            if not tasks:
                return {"ok": False, "error": "没有任务 (先 plan_development 出计划)"}
            # P0-A (v1.1.244): 执行链 ↔ backlog 打通 — 启动时真实建任务, 映射 backlog_id
            _enriched: list[dict[str, Any]] = []
            _created_n = 0
            for _t in tasks:
                _t2 = dict(_t)
                _bid = ""
                if service is not None:
                    try:
                        _c = service.create_task(
                            project_id, title=str(_t.get("title") or "")[:80],
                            description=str(_t.get("description") or ""),
                            priority=str(_t.get("priority") or "P2"),
                        )
                        if _c:
                            _bid = str(_c.get("id") or "")
                            _created_n += 1
                    except Exception:  # noqa: BLE001 — 建任务失败不阻断执行链
                        _bid = ""
                _t2["backlog_id"] = _bid
                _enriched.append(_t2)
            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            r = st.start({"goal": goal or "执行链", "tasks": _enriched,
                          "acceptance": plan.get("acceptance") or []})
            st.save(root)
            if not r.get("ok"):
                return r
            # P0-B: 执行链启动 → 同步 progress_card
            try:
                from .progress_card import sync_from_exec

                sync_from_exec(root, (ctx or {}).get("session_id") or "", st)
            except Exception:  # noqa: BLE001 — 落卡失败不阻断
                pass
            # W1 (v1.1.248): Promised Work — auto=true → 后台自动执行, 完成主动回报
            _sid = (ctx or {}).get("session_id") or ""
            if args.get("auto"):
                import threading as _th

                _t = _th.Thread(
                    target=_chain_auto_worker,
                    args=(root, project_id, _sid, service, st),
                    daemon=True,
                )
                _t.start()
                return {"ok": True, "output": (
                    f"✅ 执行链已启动并后台自动执行 (Promised Work): {goal or '执行链'} "
                    f"({len(tasks)} 个任务, 已建 backlog {_created_n} 个)。"
                    "后台逐任务委派执行中, 每个完成后结果回写 backlog; "
                    "全部完成会自动推送交付汇报。『进度』可随时查看。")}
            return {"ok": True, "output": (
                f"✅ 执行链已启动: {goal or '执行链'} ({len(tasks)} 个任务, "
                f"已建 backlog 任务 {_created_n} 个)。"
                "说『继续』/『推进』逐任务执行(每个完成后结果回写 backlog); "
                "『进度』查看状态; 敏感任务会先确认。"
                "也可以说『自动执行』(auto) 后台全部跑完。")}
        if tool_id == "chain_next":
            from .exec_state import ExecState

            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            if st.state.get("status") != "running":
                return {"ok": False, "error": "没有运行中的执行链 (先 chain_start)"}

            def _exec_fn(task):
                # 委派外部 AI 执行 (真实): 走执行器网关 (G1-G4: 选执行器/注册/验证/回填/审计)
                from ..external_executor.gateway import gateway_execute

                title = str(task.get("title") or "")
                r = gateway_execute(title, data_dir=root, project_id=project_id, max_retry=1)
                if not r.get("ok"):
                    return {"ok": False, "error": r.get("error") or "外部执行失败"}
                return {"ok": True,
                        "output": (
                            f"{r.get('executor')} 完成 (任务 {r.get('task_id')}) · "
                            f"验证 {r.get('verify', {}).get('result') or 'unknown'} · "
                            f"{str(r.get('output') or '')[:300]}"),
                        "verify": dict(r.get("verify") or {}),
                        "exec_ref": str(r.get("task_id") or "")}

            r = st.next(_exec_fn)
            st.save(root)
            # P0-B: 执行链推进 → 同步 progress_card
            try:
                from .progress_card import sync_from_exec

                sync_from_exec(root, (ctx or {}).get("session_id") or "", st)
            except Exception:  # noqa: BLE001 — 落卡失败不阻断
                pass
            # P0-A (v1.1.244): 执行结果回写 backlog — 完成带 summary+验证 (Hermes kanban_complete 思路)
            _idx = st.state.get("current_index", -1)
            _stasks = st.state.get("tasks") or []
            if 0 <= _idx < len(_stasks) and service is not None:
                _cur = _stasks[_idx]
                _bid = str(_cur.get("backlog_id") or "")
                if _bid:
                    try:
                        _v = _cur.get("verify") or {}
                        _cur_ok = _cur.get("status") == "done"
                        service.finish_task_exec(
                            project_id, _bid,
                            success=_cur_ok,
                            exec_ref=str(_v.get("exec_ref") or "") or _bid,
                            exec_result=(
                                f"{str(_cur.get('result') or '')[:300]}"
                                + (f" · 验证 {_v.get('result') or 'unknown'}" if _v else "")
                            ),
                            actor="session-chain",
                        )
                    except Exception:  # noqa: BLE001 — 回写失败不阻断执行链
                        pass
            if r.get("finished"):
                # 全部完成 → 交付汇报
                d = st.deliver()
                return {"ok": True, "output": d.get("output")}
            return {"ok": r.get("ok"), "output": (
                f"任务『{r.get('task')}』: {'✅ 完成' if r.get('ok') else '❌ 失败'} · "
                f"{r.get('output') or ''} · 进度 {r.get('progress')}。说『继续』推进下一个。")}
        if tool_id == "gateway_status":
            try:
                from ..external_executor.task_registry import ExternalTaskRegistry

                _reg = ExternalTaskRegistry.load(root)
                _proj = str(args.get("project") or "").strip()
                tasks = _reg.list(project_id=_proj) if _proj else _reg.list()[:10]
                stats = _reg.stats()
                lines = [f"外部任务控制面: 共 {stats['total']} · {stats.get('status')} · 总重试 {stats.get('total_retries')}"]
                if not tasks:
                    lines.append("（暂无外部执行任务 — 委派后自动记录）")
                for t in tasks[:10]:
                    lines.append(f"- {t.get('id')} [{t.get('status')}] {t.get('owner')}: "
                                 f"{str(t.get('task') or '')[:50]} · 验证 {t.get('verify', {}).get('result')}")
                return {"ok": True, "output": "\n".join(lines)}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"外部任务进度不可用: {exc}"}
        if tool_id == "chain_status":
            from .exec_state import ExecState
            from .progress_card import load_card, text as _card_text

            _sid = (ctx or {}).get("session_id") or ""
            st = ExecState.load(root, _sid)
            stt = st.status()
            if stt.get("status") == "idle":
                # 有计划卡但未启动 → 展示计划卡
                _card = load_card(root, _sid)
                if _card:
                    return {"ok": True, "output": _card_text(_card) + "\n（计划已就绪, 说『开始执行』启动执行链）"}
                return {"ok": True, "output": "当前没有执行链 (先出计划并审批, 说『开始执行』)"}
            _card = load_card(root, _sid)
            if _card:
                return {"ok": True, "output": _card_text(_card)}
            lines = [f"执行链: {stt.get('status')} · 进度 {stt.get('progress')}"]
            lines.append("目标: " + str(stt.get("goal") or ""))
            for t in stt.get("tasks") or []:
                lines.append(f"- {t.get('status')} [{t.get('priority')}] {t.get('title')}")
            return {"ok": True, "output": "\n".join(lines)}
        if tool_id.startswith("mcp__"):
            from .mcp_tools import dispatch_mcp

            return dispatch_mcp(tool_id, args, str(root) if root else None)
        if tool_id == "tool_search":
            from .tool_search import discover_tools

            all_tools = (ctx or {}).get("all_tools") or []
            q = str(args.get("query") or "")
            max_r = int(args.get("max_results") or 5)
            hits = discover_tools(all_tools, q, top_k=max_r)
            names = [str((t.get("function") or {}).get("name") or "") for t in hits]
            if not names:
                return {"ok": True, "output": (
                    "未找到匹配工具, 试试更具体的关键词 (如 '扫描项目' / '读取代码' / '创建任务' / '查看文档')")}
            return {"ok": True, "matches": names,
                    "output": "匹配工具: " + ", ".join(names) + " (已加入可用列表, 可直接调用)"}
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


def _finish_session_hooks(
    data_dir: str | Path, project_id: str, session_id: str,
    question: str, messages: list[dict[str, Any]], answer: str,
) -> None:
    """S10-127 M4.2: 会话收尾 — PreCompact 写交接 + SessionEnd 提取记忆。"""
    # W4 (v1.1.250): 会话收尾提取 → 更新 core human 块 (轻量, 不调 LLM)
    try:
        from .memory_core import extract_and_update

        _sess = None
        try:
            from ..console_sessions import SessionStore

            _store = SessionStore(Path(data_dir) / "console_sessions.json")
            _sess = _store.get_session(session_id) if _store is not None else None
        except Exception:  # noqa: BLE001 — 会话读取失败 → 空
            pass
        extract_and_update(data_dir, _sess, question, answer)
    except Exception:  # noqa: BLE001 — 提取失败不阻断
        pass
    try:
        _h = _get_hooks()
        _h.fire("PreCompact", {
            "data_dir": data_dir, "project_id": project_id, "session_id": session_id,
            "question": question, "last_answer": str(answer or "")[:200]})
        _h.fire("SessionEnd", {
            "data_dir": data_dir, "project_id": project_id, "session_id": session_id,
            "messages": messages})
    except Exception:  # noqa: BLE001 — hooks 失败不阻断
        pass


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
    on_event: Callable[[dict[str, Any]], None] | None = None,
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

    # S10-127 P1.1: 分模型 prompt 模板 (强模型完整指令+自主; 弱模型精简+严收敛)
    from .model_prompt import pick_prompt

    _mconf = _resolve_model_conf(data_dir, need_fc=True)
    _mp = pick_prompt(_mconf.get("capabilities"), _mconf.get("context_window"))
    _max_calls = _mp["max_tool_calls"]
    _agent_system = _mp["system"]
    _reflection = _mp["reflection"]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _agent_system},
        # W4 (v1.1.250): Core Memory 注入 (persona + human 自编辑块, Letta)
        {"role": "system", "content": _core_render(data_dir)},
        {"role": "system", "content": format_intent(intent) + "\n" + route_for(intent["intent"])},
        {"role": "system", "content": style_instruction(question, intent.get("intent"), intent.get("emotion"))},
        {"role": "user", "content": question},
    ]
    # ---- S3 (v1.1.243): 纠正信号由 LLM 语义判定 (intent.correction), 不再用关键词 ----
    if intent.get("correction"):
        messages.append({"role": "system", "content": (
            "用户正在纠正方向(『" + question[:120] + "』, 意图理解: " + str(intent.get("summary") or "")[:80] + ")。"
            "请先重新理解用户真正要什么: 重述用户问题, 如果之前的理解/工具方向错了, 立刻纠正; "
            "回答必须围绕用户纠正后的真实意图, 不要继续原方向。"
        )})
    # ---- S3 (v1.1.243): 产出模式由 LLM 语义判定 (intent.mode), 不再用关键词 ----
    _mode = intent.get("mode") or "general"
    if _mode == "code":
        messages.append({"role": "system", "content": (
            "【重要】用户要的是【真实代码】: 请用 read_code / code_scan / search_code / project_structure "
            "读代码文件(.py/.ts 等) 分析代码逻辑、关键函数、调用链; "
            "不要读 docs/ 下的文档, 除非用户明确说'看文档/方案/说明书'。"
        )})
    elif _mode == "doc":
        messages.append({"role": "system", "content": (
            "【用户要文档类产出】: 优先 project_docs / 文档检索; 如需要可配合 code_scan 佐证, "
            "但不要用大量代码文件内容替代文档说明。"
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
    # ---- S4 (v1.1.243): live plan — 多步任务先规划再执行, 边做边更新 (Pi update_plan + Cline Plan) ----
    _needs_plan = (
        intent.get("intent") in ("analyze", "deep_analyze", "develop", "operate", "plan")
        or intent.get("mode") == "plan"
    )
    if _needs_plan:
        messages.append({"role": "system", "content": (
            "【多步任务规划】这是多步任务。开始执行前, 先在心里列一份简短计划: 目标 → 步骤(按序) → 验证方式。"
            "然后按计划执行: 每一步用对应工具拿到真实结果; 每完成一步, 在后续回复中标注『✓ 已完成: <这步做了什么>』; "
            "不要跳步, 不要漏步骤; 步骤全部完成后对照计划检查是否回答了用户的完整需求, 再给最终回答。"
        )})
    # S10-127 P1.3: L0/L1/L2 分层上下文注入 (按模型能力选深度; 复用 M3 权威分层)
    try:
        from .context_layers import build_context, pick_depth

        _depth = pick_depth(_mp.get("tier"), _mconf.get("context_window"))
        _ctx_block = build_context(data_dir, project_id, depth=_depth)
        if _ctx_block:
            messages.append({"role": "system", "content": _ctx_block})
    except Exception:  # noqa: BLE001 — 上下文不可用不阻断
        pass
    # S10-127 M4.1: SessionStart hooks → 注入续接内容
    try:
        _hook_inj = _get_hooks().injected(_get_hooks().fire("SessionStart", {
            "data_dir": data_dir, "project_id": project_id, "session_id": session_id,
            "question": question}))
        if _hook_inj:
            messages.append({"role": "system", "content": _hook_inj})
    except Exception:  # noqa: BLE001 — hooks 不阻断
        pass
    calls: list[dict[str, Any]] = []
    all_tools = tool_schemas(data_dir)
    ctx: dict[str, Any] = {"session_store": session_store, "session_id": session_id,
                           "pending_plan": None, "intent": intent, "all_tools": all_tools}
    ctx["llm_fn"] = lambda p: _simple_llm(p, data_dir=data_dir)
    # S10-127 M2.2: 动态工具面 — 首轮核心+预检索+tool_search, 命中累积加入
    tools = _initial_tools(question, all_tools)
    try:
        from .tool_search import catalog_summary

        _catalog = catalog_summary(all_tools)
        messages.append({"role": "system", "content": (
            f"【工具面】首轮已加载常用工具: {[str((t.get('function') or {}).get('name')) for t in tools]}.\n"
            f"完整工具目录 (含未加载的执行类工具, 用户问'能调用哪些工具/有什么能力'时据此回答):\n{_catalog}"
        )})
    except Exception:  # noqa: BLE001 — 目录不可用 → 简单提示
        messages.append({"role": "system", "content": (
            "【工具面】当前已加载部分常用工具; 需要其他能力时调用 tool_search 搜索并加载。"
        )})
    total_calls = 0
    _usage_prompt = 0
    _usage_completion = 0
    import time as _time
    _start_ms = _time.monotonic() * 1000
    _converge = "reflection"
    # ---- S2 (v1.1.243): 循环护栏 — 无进展检测 / 同工具连续失败 / 整轮超时 ----
    _guard: dict[str, Any] = {
        "tool_fail_streak": {},     # 工具名 → 连续失败次数
        "all_fail_rounds": 0,       # 连续"整轮全失败"轮数
        "warned_fail": set(),       # 已注入换策略提示的工具
        "warned_no_progress": False,
        "force_converge": False,    # 超时 → 强制收敛
        "max_turn_ms": 240_000,     # 整轮超时上限 240s (OpenClaw 硬超时思路)
    }

    def _guard_inject() -> None:
        """循环护栏: 检测到异常模式 → 注入约束提示 (治原地打转/假装成功)。"""
        if _time.monotonic() * 1000 - _start_ms > _guard["max_turn_ms"] and not _guard["force_converge"]:
            _guard["force_converge"] = True
            messages.append({"role": "system", "content": (
                "【超时护栏】本轮执行已超过时限。请立即收敛: 基于已有结果直接回答用户问题; "
                "信息不足则明确追问; 【禁止再调用工具】。"
            )})
            return
        for tid, streak in list(_guard["tool_fail_streak"].items()):
            if streak >= 2 and tid not in _guard["warned_fail"]:
                _guard["warned_fail"].add(tid)
                messages.append({"role": "system", "content": (
                    f"【护栏】工具 {tid} 已连续失败 {streak} 次。不要重复调用它; "
                    "换一种方式: 换工具 / 换参数 / 换查询词 / 拆小步骤, 或直接基于已有信息回答并说明缺失。"
                )})
        if _guard["all_fail_rounds"] >= 2 and not _guard["warned_no_progress"]:
            _guard["warned_no_progress"] = True
            messages.append({"role": "system", "content": (
                "【护栏】最近两轮工具调用全部失败/无实质进展。停止原地打转: "
                "要么换一个完全不同的方法重试一次, 要么直接基于已有信息回答用户并如实说明哪些没查到。"
            )})

    try:
        for _ in range(max_rounds):
            # U1: 思考过程事件 (前端显示"思考中…"; 模型有 reasoning → 带思考内容)
            if on_event is not None:
                try:
                    on_event({"type": "thinking", "round": total_calls + 1,
                              "status": "start", "label": f"正在思考… (第 {total_calls + 1} 轮)"})
                except Exception:  # noqa: BLE001
                    pass
            _guard_inject()
            resp = call_with_tools(messages, tools, data_dir=data_dir)
            _r = resp.get("reasoning") or ""
            if _r and on_event is not None:
                try:
                    on_event({"type": "thinking", "round": total_calls + 1,
                              "status": "detail", "detail": str(_r)[:500]})
                except Exception:  # noqa: BLE001
                    pass
            _u = resp.get("usage") or {}
            if _u:
                _usage_prompt += int(_u.get("prompt_tokens") or 0)
                _usage_completion += int(_u.get("completion_tokens") or 0)
            tcs = resp.get("tool_calls") or []
            if not tcs:
                # S1.1 (v1.1.244): 文本模拟工具调用检测 — 回答里写 <tool_calls> 但没走真实通道 (deepseek 常见)
                _content = resp.get("content") or ""
                if re.search(r"<tool_calls>|```tool_calls|</tool_calls>|<invoke name=", _content):
                    messages.append({"role": "system", "content": (
                        "检测到你在回答文本里写了 <tool_calls> 但没有真实发起工具调用 — 这只是描述, 不是执行。"
                        "如果你确实需要调用工具 (如 plan_development/project_docs 等), 请通过真正的函数调用通道发起; "
                        "不需要的话, 直接基于已有结果给出回答。"
                    )})
                    continue
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
                            total_calls, max_rounds, _start_ms, _converge, _answer,
                            _usage_prompt, _usage_completion)
                try:
                    _finish_session_hooks(data_dir, project_id, session_id, question, messages, _answer)
                except Exception:  # noqa: BLE001
                    pass
                return {"answer": _answer, "calls": calls, "intent": intent,
                        "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls]}
            if _guard["force_converge"]:
                break
            messages.append({"role": "assistant", "content": resp.get("content") or "", "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function") or {}
                tid = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                _tool_t0 = __import__("time").monotonic()
                result = dispatch(tid, args, root=data_dir, project_id=project_id, service=service, ctx=ctx)
                _tool_dur = int((__import__("time").monotonic() - _tool_t0) * 1000)
                # tool_search 命中 → 累积加入可见工具 (Eino 模式)
                if tid == "tool_search" and result.get("matches"):
                    from .tool_search import expand_matches

                    tools = expand_matches(all_tools, tools, result.get("matches") or [])
                # S2: 同工具连续失败统计
                if result.get("ok"):
                    _guard["tool_fail_streak"][tid] = 0
                else:
                    _guard["tool_fail_streak"][tid] = _guard["tool_fail_streak"].get(tid, 0) + 1
                # S10-127 M4.1: PostToolUse 审计
                try:
                    _get_hooks().fire("PostToolUse", {
                        "tool_id": tid, "args": args, "project_id": project_id,
                        "session_id": session_id, "result_ok": bool(result.get("ok"))})
                except Exception:  # noqa: BLE001
                    pass
                # S10-127 P1.4 + U2: 流式事件 (工具执行中实时推送 + 耗时)
                if on_event is not None:
                    try:
                        on_event({"type": "tool", "tool": tid,
                                  "ok": bool(result.get("ok")),
                                  "error": str(result.get("error") or "")[:200],
                                  "duration_ms": _tool_dur,
                                  # S8-4: bash 写操作批准 — 透传审批字段给前端
                                  "need_approval": bool(result.get("need_approval")),
                                  "approval_id": str(result.get("approval_id") or ""),
                                  "command": str(result.get("command") or "")[:2000]})
                    except Exception:  # noqa: BLE001 — 事件推送失败不阻断
                        pass
                total_calls += 1
                calls.append({"tool": tid, "params": args, "ok": result.get("ok"),
                              "output": result.get("output"), "error": result.get("error"),
                              "pending_plan": bool(result.get("pending_plan")),
                              "plan": result.get("plan")})
                # P0-C (v1.1.244): 工具结果分级截断 — 长报告/扫描/读取给大预算, 否则小预算 (Hermes 100k 思路)
                _tool_budget = {
                    "project_scan": 20000, "code_scan": 20000, "project_structure": 20000,
                    "read_code": 16000, "project_tasks": 12000, "project_docs": 12000,
                    "search_code": 12000, "scan_todos": 12000, "chain_status": 8000,
                    "gateway_status": 8000, "knowledge_search": 8000, "git_status": 6000,
                }
                _res_json = json.dumps(result, ensure_ascii=False)
                _budget = _tool_budget.get(tid, 6000)
                _trunc = _res_json[:_budget]
                if len(_res_json) > _budget:
                    _trunc += f"\n...(结果过长, 截断至 {_budget} 字符; 如需要更详细请针对性查询)"
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or "", "content": _trunc})
            # S2: 本轮工具调用全失败 → 累计无进展轮数; 有成功 → 清零
            _round_results = [c.get("ok") for c in calls[-len(tcs):]]
            if _round_results and not any(_round_results):
                _guard["all_fail_rounds"] += 1
            else:
                _guard["all_fail_rounds"] = 0
            # 硬上限 → 停 (最后强制收敛)
            if total_calls >= _max_calls:
                break
            # S4: 计划进度回注 (多步任务: 已完成动作清单 + 对照提醒)
            if _needs_plan and calls:
                _done = " → ".join(
                    f"{c['tool']}{'✅' if c.get('ok') else '❌'}" for c in calls[-6:]
                ) or "（无）"
                messages.append({"role": "system", "content": (
                    f"【计划进度】已执行: {_done}\n"
                    "请对照你列的计划: 还有哪些步骤没做? 是否需要换工具拿更准的数据? "
                    "步骤完成 → 标注『✓』并继续; 全部完成或受阻 → 给最终回答。"
                )})
            # Reflection 自评: 主动收敛 (不等 3-loop 兜底)
            messages.append({"role": "system", "content": _reflection})
        # 硬收敛轮 (不允许再调工具): 信息不足 → 明确追问 (Founder: 3 loop 后还不清醒就追问)
        from .answer_verify import self_check_prompt
        try:
            _finish_session_hooks(data_dir, project_id, session_id, question, messages, content)
        except Exception:  # noqa: BLE001
            pass

        # S5 (v1.1.243): 防过度声称 — 失败的工具调用不得声称成功 (Hermes file-mutation verifier 思路)
        _failed_calls = [c for c in calls if not c.get("ok")]
        if _failed_calls:
            _fail_desc = "; ".join(
                f"{c['tool']}→{str(c.get('error') or '失败')[:80]}" for c in _failed_calls[-5:]
            )
            messages.append({"role": "system", "content": (
                "【验证提醒】以下工具调用失败了: " + _fail_desc + "。"
                "回答时不得声称这些操作已成功; 如实说明失败原因, 或基于其他成功结果回答; "
                "如果这些失败影响结论, 明确标注'该项未完成/未验证'。"
            )})
        messages.append({"role": "system", "content": (
            "已调用工具达到上限。现在必须收敛，且【禁止再调用任何工具】。"
            "回答前【强制对齐】: 用户的问题是『" + question + "』, 你的回答必须直接回答它; "
            "如果工具结果答非所问, 明确说明并回到用户的问题; 如果信息仍不足 → 明确追问, 不硬答。"
            "如果用户纠正过方向(如说'不是XX/我说的是XX'), 以用户最新纠正为准。"
        )})
        messages.append({"role": "system", "content": self_check_prompt()})
        resp = call_with_tools(messages, None, data_dir=data_dir)  # 不给工具 → 必收敛
        content = resp.get("content") or ""
        _converge = "hard_cap" if total_calls >= _max_calls else "reflection"
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, _converge, content,
                    _usage_prompt, _usage_completion)
        return {"answer": content[:2000], "calls": calls, "intent": intent,
                "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls]}
    except Exception as exc:  # noqa: BLE001 — LLM 不可用 → 回退旧路由
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, "rejected", "",
                    _usage_prompt, _usage_completion)
        return {"answer": "", "rejected": True, "calls": calls, "evidence": [],
                "reason": f"原生 FC 不可用: {exc}"}


def _core_render(data_dir: str | Path | None) -> str:
    """W4: Core Memory 渲染注入 (persona + human)。失败安全 → 空。"""
    try:
        from .memory_core import render

        return render(data_dir)
    except Exception:  # noqa: BLE001
        return ""


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
                start_ms, converge, answer, prompt_tokens=0, completion_tokens=0) -> None:
    """会话审计落盘 (S-1; 失败静默; P2.1 含 token 统计)。"""
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
            prompt_tokens=int(prompt_tokens or 0), completion_tokens=int(completion_tokens or 0),
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
                session_store=None, session_id="", history=None, context_view=None,
                on_event=None):
    """入口: 原生 FC (IntentCore 门); 失败 → 回退 prompt 协议 (v1) → 仍失败 → rejected。

    S10-127 P1.4: on_event 流式回调 — 工具事件由 native 发, done 在此发。"""
    native = run_agent_native(question, data_dir=root, project_id=project_id, service=service,
                              session_store=session_store, session_id=session_id,
                              max_rounds=max_rounds, history=history, context_view=context_view,
                              on_event=on_event)
    if on_event is not None:
        try:
            on_event({"type": "done", "answer": native.get("answer") or "",
                      "rejected": bool(native.get("rejected")),
                      "calls": [c.get("tool") for c in native.get("calls") or []]})
        except Exception:  # noqa: BLE001
            pass
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
