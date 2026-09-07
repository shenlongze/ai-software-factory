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
                    _cw = 0
                    try:
                        _m0 = (p.get("models") or ["deepseek-chat"])[0]
                        _md = (p.get("model_catalog") or {}).get(_m0) or {}
                        _cw = int(_md.get("context_window") or 0)
                    except Exception:  # noqa: BLE001
                        _cw = 0
                    return {"id": pid, "base_url": str(p.get("base_url") or ""),
                            "model": str((p.get("models") or ["deepseek-chat"])[0]),
                            "context_window": _cw,
                            "api_key_ref": str(p.get("api_key_ref") or "env:DEEPSEEK_API_KEY")}
    except Exception:  # noqa: BLE001
        pass
    return {"id": "deepseek", "base_url": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat", "context_window": 0,
            "api_key_ref": "env:DEEPSEEK_API_KEY"}


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
                "context_window": int(conf.get("context_window") or 0),
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
        _fc("project_list", "项目列表", "列出所有项目, 用 markdown 无序列表呈现; 每个项目字段齐全: 项目ID/名称/本地地址/Git地址/阶段/语言/任务分类统计(P0-P3)/完成度/文档; 用户问'项目列表/有哪些项目/项目清单'时用", {}),
        _fc("create_project", "创建项目", "创建新项目 (用户明确要'新建/创建/做一个XXX项目'且当前无匹配项目时用; 先确认名称与需求再调用; 参数: name 项目名, goal 项目目标描述)", {"name": {"type": "string", "description": "项目名称"}, "goal": {"type": "string", "description": "项目目标/描述"}}),
        _fc("project_structure", "项目结构", "查看项目真实结构: 仓库顶层目录树/模块划分/文件分布/入口文件 (用户说'了解项目结构/有哪些模块/目录'时用)", {}),
        _fc("read_code", "读取代码", "读取指定文件的代码内容(带行号, 支持分页), 用于理解代码逻辑/实现/调用链。"
            "规则: 1) 通常从 offset=0 从头读起; 除非之前已读过该文件或用 offset 翻页; "
            "2) 读完必须基于内容向用户解释代码逻辑/关键函数/调用链, 不要只贴代码不给解释; "
            "3) 文件很大时分多次读取完整后再解释。参数 path 为仓库内相对路径, 或 keyword 定位文件",
            {"path": {"type": "string"}, "keyword": {"type": "string"}, "offset": {"type": "integer"}}),
        _fc("search_code", "代码检索", "在仓库中检索关键词, 返回命中文件", {"keyword": {"type": "string"}}, ["keyword"]),
        _fc("project_status", "项目状态", "查询项目实时状态: 生命周期/进度(真实任务完成率)/当前阶段/工作流", {}),
        _fc("project_lifecycle", "产品生命周期状态",
            "查询项目 产品链 各阶段真实状态 (需求/PRD/产品方案/计划/任务拆解 是否建立与状态)。"
            "用户问 需求分析/需求整理/理解程度、PRD/方案/原型 是否完成、任务拆解/计划到哪一步 → 用本工具,"
            " 不用 project_tasks (任务统计不能回答产品链完成度)。返回各阶段存在/状态/ID/缺失, 如实回答未建立。",
            {}),
        _fc("project_tasks", "任务清单", "查询项目任务: 默认返回统计; 用户要求'查看任务列表/具体任务'时传 detail=true 返回任务明细表格 (任务/模块/优先级/类型/状态)", {"priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}, "detail": {"type": "string", "enum": ["true", "false"]}}),
        _fc("requirement_analysis_round", "需求分析回合(Node)", "产品链需求分析节点: 创建/恢复当前项目 requirement-analysis NodeRun 并推进一个分析回合。有决策点→返回 pending_questions 需向用户提问; 全维度覆盖+决策齐→COMPLETED。用户说'分析需求/继续分析/分析更多/找需求漏洞'时用它。", {"request": {"type": "string", "description": "首轮用户原始需求 (可省, 已从会话取)"}}, []),
        _fc("requirement_analysis_answer", "需求分析决策回答(Node)", "用户对需求分析 pending 决策的答复: decision_id + chosen (用户明确选择)。记录为 human decision 事实后自动续推进。用户回答选项/拍板时用。", {"decision_id": {"type": "string", "description": "待决策 ID"}, "chosen": {"type": "string", "description": "用户选择/回答内容"}}, ["decision_id", "chosen"]),
        _fc("task_action", "任务操作(执行)", "对任务执行动作: start/done/priority (需任务标题)",
            {"title": {"type": "string"}, "action": {"type": "string", "enum": ["start", "done", "priority"]},
             "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}}, ["title", "action"]),
        _fc("create_task", "创建任务(执行)", "在当前项目创建新任务",
            {"title": {"type": "string"}, "description": {"type": "string"}, "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]}}, ["title"]),
        _fc("save_product_record", "保存/更新产品链记录 (canonical)",
            "把产品链真实产出写入 canonical Product Truth。kind: "
            "idea(想法) / discovery(需求理解) / requirement(需求) / prd(产品方案)。"
            "用户要求 继续/整理/分析/接受建议/更具体/深化 → 即授权产出。"
            "迭代规则: 若该工作已有记录且仍是 draft (record_id 已知或先用 "
            "get_product_record 查到) → 传 record_id 更新其内容 (深化, 不重复"
            "新建); 无记录 → 新建。不要在回答里只输出文本而不落盘。",
            {"kind": {"type": "string", "enum": ["idea", "discovery", "requirement", "prd", "plan"]},
             "title": {"type": "string"}, "content": {"type": "string"},
             "record_id": {"type": "string", "description": "可选: 更新已有 draft 记录 (深化) — 省略则新建"},
             "idea_id": {"type": "string", "description": "kind=discovery 且新建时必填 (IDEA-*)"}},
            ["kind", "title", "content"]),
        _fc("get_product_record", "读取产品链记录 (canonical)",
            "读取 canonical Product Truth 记录的完整内容。record_id 已知 (如 "
            "REQ-xxx) 传之; 未知则传 kind (requirement/discovery/prd/plan) 返回"
            "该类型最近一条含完整内容。用于继续深化/查看已确定的产出/回答"
            "'目前确定了什么'。",
            {"kind": {"type": "string", "enum": ["idea", "discovery", "requirement", "prd", "plan"]},
             "record_id": {"type": "string"}}, ["kind"]),
        _fc("project_docs", "文档清单", "列出项目文档/产出物", {}),
        _fc("git_status", "仓库状态", "查询 git 仓库: 远程/分支/领先提交", {}),
        _fc("monitor", "系统监控", "查询系统/服务运行状态", {}),
        _fc("task_continue", "继续任务(锚定)", "用户想继续某任务时: 按标题定位并锚定到会话", {"task": {"type": "string"}}, ["task"]),
        _fc("plan_development", "开发计划(出计划)", "开发类需求: 产出结构化计划(目标/任务/顺序/验收) → 请求审批。"
            "当用户要求'做/开发/实现/完善某个功能'时调用; company 会话先 project_list 查项目, 用 project_id 参数显式指定目标项目",
            {"goal": {"type": "string"}, "detail": {"type": "string"},
             "project_id": {"type": "string", "description": "目标项目 ID (company 会话必须传)"}}),
        _fc("execute_plan", "执行计划(审批后)", "审批通过后: 按计划建任务进 backlog, 可委派外部AI执行",
            {"tasks": {"type": "array", "items": {"type": "object",
                     "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                                    "priority": {"type": "string"}}, "required": ["title"]}},
             "delegate": {"type": "boolean", "description": "是否委派外部AI执行"}}),
        _fc("external_route", "外部AI路由", "为任务选择最合适外部AI agent", {"task": {"type": "string"}}, ["task"]),
        _fc("chain_start", "启动执行链(做人事)", "审批通过后启动执行链: 按计划建任务列表, 逐任务执行; "
            "auto=true 时后台自动执行全部任务 (Promised Work), 完成主动推送交付汇报; "
            "company 会话必须传 project_id (目标项目 ID)",
            {"goal": {"type": "string"}, "tasks": {"type": "array", "items": {"type": "object",
                     "properties": {"title": {"type": "string"}, "priority": {"type": "string"}}}},
             "auto": {"type": "boolean", "description": "true=后台自动执行全部任务并主动回报"},
             "project_id": {"type": "string", "description": "目标项目 ID (company 会话必须传)"}}),
        _fc("chain_next", "推进下一个任务", "执行链逐任务推进: 委派执行→验证→回写", {}),
        _fc("chain_status", "执行链进度", "查询当前执行链进度 (完成数/当前任务)", {}),
        _fc("gateway_status", "外部任务进度", "查询外部执行器任务进度 (最近/按项目/统计)", {"project": {"type": "string"}}),
        _fc("knowledge_search", "知识检索", "在项目文档中检索知识点/历史结论, 返回片段+来源 (跨会话记忆/项目知识)",
            {"query": {"type": "string"}}, ["query"]),
        # ---- W4 (v1.1.250): Core Memory — 模型自编辑 human 块 (Letta self-editing) ----
        _fc("memory_update", "更新Core记忆(Human块)", "自编辑长期记忆 (Letta core memory): 记录用户偏好/项目上下文/关键事实/任务状态, "
            "下次会话延续。重要信息值得记 → 调用; append=true 追加到已有记忆。上限 1500 字符",
            {"text": {"type": "string"}, "append": {"type": "boolean"}}, ["text"]),
        # ---- T1 (v1.1.305): 手动上下文压缩 — 长会话聚焦 (压缩 → 交接 → 精简上下文) ----
        _fc("compact_context", "压缩上下文", "长会话聚焦: 当前话题摘要 + PreCompact 交接写入 Spine + 记忆沉淀, "
            "返回压缩后上下文块。会话变慢/跑偏/要重新聚焦时调用; 不影响历史消息",
            {"focus": {"type": "string"}}, ["focus"]),
        # ---- W5 (v1.1.251): skills 按需检索 (OpenClaw <available_skills>) ----
        _fc("skill_search", "技能检索", "检索可用技能库 (147+ 技能: 产品/开发/质量/运维等)。"
            "需要专业技能/专业方法时调用, 返回技能名字+分类+路径, 再按路径读取 SKILL.md 加载指引",
            {"query": {"type": "string"}, "max_results": {"type": "integer"}}, ["query"]),
        # ---- W7 (v1.1.253): 代码库符号地图 (Aider repo map 思路) ----
        _fc("repo_map", "代码库地图", "生成代码库符号地图 (文件+关键 def/class, 按问题相关性排名, token 预算内)。"
            "理解项目代码结构/找实现位置/分析架构时先调用, 再按需 read_code 深入; 不用全量读文件",
            {"query": {"type": "string"}, "max_chars": {"type": "integer"}}, ["query"]),
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
3. 开发/操作类需求 → Plan/Act 双模式: 先 Plan (快速了解现状 + plan_development 出计划 + 请求审批),
   批准前不执行任何写操作 (Plan 阶段只读); 批准后 Act (execute_plan/chain_start 执行)
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


def _try_promote_lifecycle(service: Any, project_id: str, target: str) -> None:
    """任务拆解完成 → 项目 lifecycle 自动推进 (S35-P0 数据同步)。

    建任务成功后调用: idea→confirmed (任务拆解=需求明确)。
    安全: org store 缺失/非法流转/异常 → 静默跳过, 不阻断执行 (幂等: 同状态无事件)。
    """
    if service is None or not project_id:
        return
    try:
        store = getattr(service, "_project_store", None)
        if store is None:
            return
        from org.projects import ProjectLifecycle

        ProjectLifecycle(store).transition_lifecycle(project_id, target)
    except Exception:  # noqa: BLE001 — 流转失败不阻断任务执行
        pass


def _plan_dependency_map(plan: dict[str, Any]) -> dict[str, list[str]]:
    """P1-R1: 从 Plan 提取任务依赖 {title: [dep_titles]}。

    优先: task.dependency / task.depends_on (显式);
    兜底: plan.order 顺序链 (LLM 表达的执行顺序 → 相邻成链: 后者依赖前者)。
    仅当显式依赖缺失时用 order — 不覆盖 LLM 明确声明的依赖。
    """
    dep: dict[str, list[str]] = {}
    for t in (plan.get("tasks") or []):
        if not isinstance(t, dict):
            continue
        title = str(t.get("title") or "").strip()
        if not title:
            continue
        d = t.get("dependency") or t.get("depends_on") or []
        if d:
            dep[title] = [str(x).strip() for x in d if str(x).strip()]
    order = plan.get("order") or []
    if order and not any(dep.values()):
        for i in range(1, len(order)):
            prev, cur = str(order[i - 1]).strip(), str(order[i]).strip()
            if prev and cur:
                dep.setdefault(cur, []).append(prev)
    return dep


def execute_plan(
    plan: dict[str, Any],
    *,
    project_id: str,
    service: Any,
    delegate: bool = False,
) -> dict[str, Any]:
    """执行计划: 建任务进 backlog (真实); delegate=True 时提示可委派外部AI。

    S34-P0-E: 任务关联 plan_id (Plan→Task 链真实)。
    """
    if service is None:
        return {"ok": False, "error": "任务服务不可用"}
    _plan_id = str(plan.get("plan_id") or "")
    created: list[dict[str, Any]] = []
    # S34/S35-P0-3: 幂等 — plan_id 已执行过则返回已有任务, 不重复创建
    if _plan_id and service is not None:
        try:
            _existing = (service.list_backlog(project_id) or {}).get("tasks") or []
            _same_plan = [t for t in _existing if str(t.get("plan_id") or "") == _plan_id]
            if _same_plan:
                _try_promote_lifecycle(service, project_id, "confirmed")
                return {
                    "ok": True, "idempotent": True,
                    "output": f"计划 {_plan_id} 已执行过 (任务已存在 {len(_same_plan)} 个, 不重复创建)。",
                    "created": [{"id": t.get("id"), "title": t.get("title"),
                                 "priority": t.get("priority"), "plan_id": _plan_id}
                                for t in _same_plan],
                    "plan_id": _plan_id,
                }
        except Exception:  # noqa: BLE001 — 幂等检查失败 → 继续 (保守)
            pass
    # P1-R1: 依赖提取 (显式 dependency/depends_on; 兜底 plan.order 链)
    _dep_map = _plan_dependency_map(plan)
    created: list[dict[str, Any]] = []
    _id_by_title: dict[str, str] = {}
    for t in (plan.get("tasks") or [])[:20]:
        try:
            c = service.create_task(
                project_id, title=str(t.get("title") or "")[:80],
                description=str(t.get("description") or ""),
                priority=str(t.get("priority") or "P2"),
                plan_id=_plan_id,  # S34/S35-P0-4: 任务关联计划
            )
            if c:
                created.append({"id": c.get("id"), "title": c.get("title"),
                                "priority": c.get("priority"), "plan_id": _plan_id})
                _tid = str(c.get("id") or "")
                _ttl = str(c.get("title") or "").strip()
                if _tid and _ttl:
                    _id_by_title[_ttl] = _tid
        except Exception as exc:  # noqa: BLE001 — 单条失败跳过 (诚实标注)
            try:
                created.append({"id": "", "title": str(t.get("title") or "")[:40],
                                "priority": str(t.get("priority") or "P2"),
                                "error": f"{type(exc).__name__}: {exc}"})
            except Exception:  # noqa: BLE001
                pass
    # P1-R1: dependency resolve (plan task title → created Task ID) + 校验更新
    # (自引用/环/未知依赖由 service.update_task → validate_dependency 真实检查;
    #  解析失败的任务依赖保持 [] — 失败安全, 不阻断任务创建)
    if _dep_map and _id_by_title:
        for _title, _deps in _dep_map.items():
            _cid = _id_by_title.get(_title)
            if not _cid:
                continue
            _resolved: list[str] = []
            for _d in _deps:
                _did = _id_by_title.get(_d)
                if not _did:
                    _did = next(
                        (v for k, v in _id_by_title.items()
                         if _d and (_d in k or k in _d)),
                        "",
                    )
                if _did and _did != _cid:
                    _resolved.append(_did)
            if not _resolved:
                continue
            try:
                service.update_task(project_id, _cid, dependency=_resolved)
            except Exception:  # noqa: BLE001 — 依赖更新失败保持原状 (诚实)
                pass
    lines = [f"已建任务 {len(created)} 个进 backlog:"]
    lines += [f"- [{t['priority']}] {t['title']} ({t['id']})" for t in created[:15] if t.get("id")]
    _failed = [t for t in created if not t.get("id")]
    if _failed:
        lines.append(f"⚠ {len(_failed)} 个任务创建失败: " + "; ".join(
            f"{t.get('title')} ({t.get('error')})" for t in _failed[:3]
        ))
    if delegate and created:
        lines.append("下一步可委派外部AI(如 codex/claude)执行 — 说『开始执行』或我用外部AI逐任务推进。")
    # S35-P0: 任务拆解完成 → 项目 lifecycle 自动推进 (idea→confirmed, 数据同步)
    if created:
        _try_promote_lifecycle(service, project_id, "confirmed")
    return {"ok": True, "output": "\n".join(lines), "created": created, "plan_id": _plan_id}


# ---------------------------------------------------------------- Agent 循环 (原生 FC)

_hooks_instance = None


#: v1.1.267 深度调研方法 (抄 Hermes 调研风格: 先查本地→并行收集→深挖源码→结构化可执行输出)
RESEARCH_METHOD_PROMPT = """【深度调研方法 (Research)】这是调研/研究/对比类任务。按以下方法做, 要细致、准确、可执行:

1. 先查本地已有 (避免重复劳动): knowledge_search 查项目知识/记忆; 查 docs/ 下是否已有同类调研文档
2. 并行收集: web_search 搜 GitHub/官方文档/权威来源; 识别本地是否有可深挖的一手资料 (本地安装的源码、AGENTS.md、README)
3. 深挖一手资料: 用 read_code/read 读本地源码/文档原文, 引用真实内容 (函数名/设计原则/许可证); GitHub API 搜准确仓库名, 核对 star/许可证
4. 结构化输出 (markdown 分节):
   一、核心对象怎么做的 (机制/设计, 引用真实代码或文档)
   二、生态/同类对比 (表格: 项目 | 定位 | 许可证 | 可借鉴点)
   三、直接结论: 能抄什么分档 (✅可直接抄代码 MIT/Apache / ⚠️只能抄架构 AGPL/商用条款 / 🔧设计启示)
   四、落地优先级: P0/P1 带大致工作量

数据必须真实 (仓库名/star数/许可证/文件路径来自工具输出); 查不到 → 说"未查到", 不许编造。"""


#: A (v1.1.269): 兑现文本模拟时允许的工具白名单 (查询/读取类; 写操作仍走批准门)
_SESSION_TOOL_WHITELIST = {
    "project_status", "project_tasks", "project_scan", "code_scan", "project_structure",
    "read_code", "search_code", "scan_todos", "project_docs", "git_status", "monitor",
    "repo_map", "skill_search", "knowledge_search", "gateway_status", "chain_status",
    "web_search", "web_fetch", "bash_exec",
}


#: v1.1.262 深度审计方法 (抄 Hermes project-audit/codebase-inspection 技能效果)
AUDIT_METHOD_PROMPT = """【深度审计方法 (Project Audit)】这是结构性审计任务。按以下方法多轮深入, 不要一次扫描就下结论:

1. 摸底: 顶层目录 + 各模块规模(文件数/行数) + 语言分布 (code_scan/repo_map/bash_exec find)
2. 核心机制: 核心目录(session/tools等)组织; 找出超大文件(>2000行)与"上帝模块"
3. 关键维度逐项核对 (每项都要真实数据, 不许猜):
   a. 版本一致性: pyproject.toml vs git HEAD (commit message) vs 已装包 dist-info vs .venv 安装版 — 是否一致? (常见: 5个版本号互不相同)
   b. 测试对称性: tests/ 与源码模块是否对应; 测试用例数
   c. 真实链路: WebUI 是否 mock 支撑? UI→API→Backend 是否闭环?
   d. 物理残留: 未跟踪/废弃/临时文件 ($SMOKE_ROOT/, unused/, 过期 pycache)
   e. CLI/前端一致性: CLI 命令与 WebUI 功能是否对应
4. 每步用工具拿真实数据 (bash_exec/code_scan/repo_map/read_code); 命令失败/路径错 → 修正重跑, 不要放弃
5. 最终报告格式 (markdown):
   一、总体规模: 表格 (模块 | 文件数 | 行数)
   二、合理的部分: 有证据
   三、问题: 按 P0/P1/P2 严重度排序, 每条带具体证据 (路径/行数/版本号)
   四、结论: 合理性分数 /100 + 一句话判断
   五、建议修复顺序: 带大致工作量

数据必须来自工具输出; 版本号/行数/路径/色值不许编造, 查不到就说"未查到"。"""


def _chain_task_run(root: Any, task: dict[str, Any], project_id: str) -> str:
    """P0-F1: 为 backlog 任务创建 TaskRun (NodeRun) 锚 — 返回 run-* id。

    - 共享 Node "task-execution" (首次自动注册; Node=模板, 多 TaskRun 同 Node 合法)
    - run.task_id = backlog TASK-* (F0: TaskRun.task_id → Task)
    - 失败安全: 无 backlog_id/异常 → "" (不锚, 不阻断委派 — F1 不改变既有行为)
    """
    bid = str(task.get("backlog_id") or "").strip()
    if not bid or not root:
        return ""
    try:
        from ..node_runtime import create_node_run, get_node, register_node

        node_id = "task-execution"
        if get_node(root, node_id) is None:
            register_node(root, node_id=node_id, name="Backlog Task Execution",
                          node_type="task-execution")
        nr = create_node_run(
            root, node_id, task_id=bid,
            input_data={"project_id": str(project_id or ""),
                        "title": str(task.get("title") or "")[:200]},
            trigger="chain",
        )
        return str(nr.get("run_id") or "")
    except Exception:  # noqa: BLE001 — TaskRun 锚失败不阻断委派
        return ""


def _chain_auto_worker(root: Any, project_id: str, session_id: str, service: Any, st: Any) -> None:
    """W1 (v1.1.248): Promised Work (OpenClaw) — 后台自动逐任务执行到完成.

    每步: 委派外部AI → 验证 → 回写 backlog → 同步进度卡;
    全部完成: deliver 交付汇报 → 追加会话消息 (主动回报, 用户不用手动"继续")。
    失败安全: 任何异常吞掉不阻断执行链。
    P0-F1: 每任务先建 TaskRun 锚 (run-*), gateway 透传 task_id/task_run_id → EXS 锚;
           exec_ref = EXS-* (F0 语义)。
    """
    try:
        from ..external_executor.gateway import gateway_execute

        def _exec_fn(task):
            title = str(task.get("title") or "")
            run_id = _chain_task_run(root, task, project_id)  # P0-F1: run-* 锚
            r = gateway_execute(
                title, data_dir=root, project_id=project_id, max_retry=1,
                task_id=str(task.get("backlog_id") or ""),  # P0-F1
                task_run_id=run_id,  # P0-F1
            )
            _exs = str(r.get("result_id") or "")  # P0-F2: EXS (成功/失败均已写入)
            # P0-F2: TaskRun finalize — 吸收外部执行结果 (零二次执行, 幂等)
            if run_id:
                try:
                    from ..node_runtime import finalize_node_run

                    finalize_node_run(
                        root, run_id,
                        success=bool(r.get("ok")),
                        verification=dict(r.get("verify") or {}),
                        failure_reason=str(r.get("error") or ""),
                        actor="session-chain-auto",
                        note=f"gateway result absorbed (EXS {_exs})",
                        exs_id=_exs,                      # P0-F4 (I8)
                        output=str(r.get("output") or ""),
                        artifact_root=root,
                    )
                except Exception:  # noqa: BLE001 — finalize 失败不阻断委派链
                    pass
            # P2-C (Experience Bridge): finalize 终态 → canonical exp-*
            # (单向派生; (source, source_id) 幂等; 失败安全 — 不阻断委派链)
            try:
                if run_id and _exs:
                    from ..experience_bridge import record_execution

                    record_execution(
                        root, task_run_id=run_id, exs_id=_exs,
                        success=bool(r.get("ok")),
                        ver_status=str((r.get("verify") or {}).get("result") or ""),
                        project=project_id,
                        task=str(task.get("title") or "")[:80],
                        actor="session-chain-auto",
                    )
            except Exception:  # noqa: BLE001 — bridge 失败不阻断
                pass
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error") or "外部执行失败",
                        # P0-F2: 失败也回传 EXS (Task.exec_ref=EXS 在失败路径成立)
                        "exec_ref": _exs}
            return {"ok": True,
                    "output": (f"{r.get('executor')} 完成 (任务 {r.get('task_id')}) · "
                               f"验证 {r.get('verify', {}).get('result') or 'unknown'} · "
                               f"{str(r.get('output') or '')[:300]}"),
                    "verify": dict(r.get("verify") or {}),
                    # P0-F1: exec_ref = EXS-* (result_id), 非 TASK-GW (task_id)
                    "exec_ref": _exs or str(r.get("task_id") or "")}

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
                            # P0-F1: exec_ref = Task 副本持久化的 EXS-* (st.next 已写入); 兜底 _bid
                            exec_ref=str(_cur.get("exec_ref") or "") or _bid,
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


# S35: 项目信息 markdown 无序列表格式化 — project_list / project_status 共用。
# 字段: ID/名称/本地地址(真实检测优先)/Git地址/阶段/语言/任务分类统计/完成度/文档。
_PROJECT_LIST_ANSWER_TEMPLATE = (
    "【回答模板 — 必须严格按此格式输出, 不要输出本说明】\n"
    "请直接基于以上真实数据, 用无序列表向用户呈现项目, 每个项目字段齐全 "
    "(项目ID/名称/本地地址/Git地址/阶段/语言/任务分类统计/完成度/文档); "
    "禁止改写为散文或表格, 禁止添加数据中没有的字段。"
)


def _project_lifecycle(root: Any, project_id: str) -> dict[str, Any]:
    """S47-E1: 产品链各阶段真实状态 (通用查询, 零硬编码)。

    数据源 (SSOT): canonical product_truth (IDEA/DISC/REQ/PRD/PLAN) +
    org 需求资产 (requirements/requirements.json) + 会话计划
    (session_plans.json, 按 project_id)。各阶段独立报告存在/状态/ID;
    缺失如实说"未建立", 绝不凭任务数量推断产品链完成度。
    """
    from pathlib import Path as _P
    import json as _json

    root_p = _P(str(root)) if root is not None else None
    rows: list[tuple[str, str, str, str]] = []  # (阶段, 状态, id, 摘要)

    def _canon(loader_name: str, key: str, label: str) -> None:
        try:
            from factory_console import product_truth as pt
            fn = getattr(pt, loader_name, None)
            recs = fn(root) if fn is not None else []
            hit = [r for r in recs
                   if r and r.get("project_id") == project_id]
            if hit:
                h = hit[-1]
                rows.append((label, str(h.get("status") or "存在"),
                             str(h.get("id") or h.get(key) or ""),
                             str(h.get("title") or "")[:60]))
            else:
                # canonical 记录无 project_id (经 idea/discovery 链归属) —
                # project filter 空不代表不存在: 诚实显示全局最近记录待归属
                unbound = [r for r in recs if r and not r.get("project_id")
                           and (r.get("id") or r.get(key))]
                if unbound:
                    h = unbound[-1]
                    rows.append((label, "存在·未绑定项目",
                                 str(h.get("id") or h.get(key) or ""),
                                 str(h.get("title") or "")[:60]))
                else:
                    rows.append((label, "未建立(canonical)", "", ""))
        except Exception:  # noqa: BLE001 — 域缺失/异常 → 诚实标注
            rows.append((label, "未建立(canonical)", "", ""))

    _canon("list_ideas", "idea_id", "Idea 想法")
    _canon("list_discoveries", "discovery_id", "Discovery 需求理解")
    _canon("list_requirements", "req_id", "Requirement 需求")
    _canon("list_prds", "prd_id", "PRD 产品方案")
    _canon("list_plans", "plan_id", "Plan 计划")

    # org 需求资产 (requirements.json — M3 会话需求)
    org_req = None
    if root_p is not None:
        try:
            _f = root_p / "requirements" / "requirements.json"
            if _f.is_file():
                _d = _json.loads(_f.read_text(encoding="utf-8"))
                _items = _d if isinstance(_d, list) else _d.get("requirements", [])
                for _r in _items:
                    if isinstance(_r, dict) and _r.get("project_id") == project_id:
                        org_req = _r
                        break
        except Exception:  # noqa: BLE001
            pass
    if org_req is not None:
        rows.append(("org 需求", str(org_req.get("status") or "存在"),
                     str(org_req.get("id") or ""), str(org_req.get("title") or "")[:60]))

    # 会话计划 (session_plans.json, project 绑定)
    plan_hit = None
    if root_p is not None:
        try:
            _f = root_p / "session_plans.json"
            if _f.is_file():
                _d = _json.loads(_f.read_text(encoding="utf-8"))
                _items = _d if isinstance(_d, list) else list(_d.values())
                for _pl in _items:
                    if isinstance(_pl, dict) and (_pl.get("project_id") == project_id
                                                  or str(_pl.get("project") or "") == project_id):
                        plan_hit = _pl
                        break
        except Exception:  # noqa: BLE001
            pass
    if plan_hit is not None:
        rows.append(("会话计划", str(plan_hit.get("status") or "存在"),
                     str(plan_hit.get("plan_id") or plan_hit.get("id") or ""),
                     str(plan_hit.get("goal") or plan_hit.get("title") or "")[:60]))

    lines = [f"项目 {project_id} 产品链各阶段状态:"]
    for label, status, rid, title in rows:
        _extra = f" · {title}" if title else ""
        _rid = f" [{rid}]" if rid else ""
        lines.append(f"- {label}: {status}{_rid}{_extra}")
    if not rows:
        lines.append("- 未发现任何产品链记录 (canonical 与 org 均为空)")
    lines.append("说明: 各阶段独立存在/缺失如实列出; 不能仅凭任务数量推断需求/PRD 是否完成。")
    return {"ok": True, "output": "\n".join(lines)}


def _node_run_context(data_dir: Any, project_id: str) -> str:
    """Phase 3: 当前项目 active 产品链 NodeRun → 事实文本 (注入 LLM)。

    仅当存在未终态 requirement-analysis NodeRun 时返回 (执行事实 SSOT —
    Conversation 据此定位当前 Work, resume SAME run; 不猜不另起)。
    无 active run → "" (Conversation 正常处理新意图)。
    """
    if not data_dir or not project_id:
        return ""
    try:
        from factory_console import node_runtime as nr
        run = nr.get_active_run(str(data_dir), "requirement-analysis",
                                project_id=project_id)
        if run is None:
            return ""
        cp = run.get("checkpoint") or {}
        lines = [f"- NodeRun: {run.get('run_id')} · state={run.get('state')}",
                 f"- 已覆盖维度: {'、'.join(cp.get('completed_dimensions') or []) or '(无)'}",
                 f"- 迭代: {cp.get('iteration') or 0}"]
        pend = [d for d in (run.get("decisions") or []) if d.get("status") == "PENDING"]
        if pend:
            lines.append("- 待你决策:")
            for d in pend:
                opt = " / ".join(d.get("options") or []) or "(自由回答)"
                lines.append(f"  · [{d.get('decision_id')}] {d.get('question')} — 选项: {opt}")
        if cp.get("open_questions"):
            lines.append("- 未决问题: " + "；".join(cp["open_questions"][:4]))
        lines.append("- 下一步: 继续分析 → 调 requirement_analysis_round; 回答决策 → "
                     "调 requirement_analysis_answer (decision_id + 你的选择)")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — 注入失败不阻断
        return ""


def _production_entry_gate(root: Any, project_id: str,
                           ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """S50-P1A: Production Entry Gate — create_task 前置。

    允许条件: 项目已有合法 canonical PLAN (approved/executing) 或
    本会话计划已批准 (PendingPlanStore status ∈ approved/executing)。
    否则 blocked: 必须先走 IDEA→DISC→REQ→PRD→PLAN 产品链。
    结构化返回, 供 Conversation 继续推进; 不产生副作用。
    """
    reason_default = "生产 TASK 需先有合法 PLAN — 当前产品链尚未形成计划; " \
                     "请先推进 需求→PRD→开发计划(plan_development)并审批"
    try:
        if root is not None and project_id:
            from factory_console import product_truth as pt
            plans = pt.list_plans(root) or []
            for p in plans:
                if (p.get("project_id") == project_id
                        and str(p.get("status") or "") in ("approved", "executing")):
                    return {"allowed": True, "plan_id": p.get("id")}
        # 会话级 pending plan 已批准/执行中
        try:
            if root is not None:
                from pathlib import Path as _P
                import json as _json
                _spf = _P(str(root)) / "session_plans.json"
                _sid = str((ctx or {}).get("session_id") or "")
                if _spf.is_file() and _sid:
                    _d = _json.loads(_spf.read_text(encoding="utf-8")) or {}
                    _cand = _d.get(_sid) or {}
                    if str(_cand.get("status") or "") in ("approved", "executing"):
                        return {"allowed": True, "plan_id": _cand.get("plan_id")}
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    return {"allowed": False, "reason": reason_default, "required_next": "PLAN"}


def _format_project_entry(root: Any, project_id: str, proj: dict[str, Any],
                          service: Any = None) -> str:
    """单个项目 → 无序列表块 (project_list 多项目 / project_status 单项目复用)。"""
    from .query_engine import _project_docs, _project_task_stats

    pid = str(project_id or "")
    name = str(proj.get("name") or pid or "—")
    life = str(proj.get("lifecycle") or proj.get("status") or "")
    lang = " + ".join(x for x in (
        str(proj.get("language") or ""), str(proj.get("framework") or "")) if x) or "—"
    # 本地地址: 真实检测优先 (root/projects/<id> 目录存在 → 绝对路径);
    # 否则 repo_path 非空用它; 再否则 —
    local = "—"
    if root is not None:
        real_dir = Path(root) / "projects" / Path(pid).name
        if real_dir.is_dir():
            try:
                local = str(real_dir.resolve())
            except Exception:  # noqa: BLE001
                local = str(real_dir)
    if local == "—":
        repo_path = str(proj.get("repo_path") or "")
        local = repo_path or "—"
    git = str(proj.get("git_repo_url") or proj.get("git_url") or "") or "—"
    # S50-P0-FIX: 任务统计经 service (slug 正确解析) — 勿拼 project_id 目录
    stats: dict[str, Any] = {}
    if service is not None:
        try:
            bl = service.list_backlog(pid) or {}
            _tl = [t for t in (bl.get("tasks") or []) if t]
            stats = {
                "total": len(_tl),
                "p0": sum(1 for t in _tl if str(t.get("priority") or "") == "P0"),
                "p1": sum(1 for t in _tl if str(t.get("priority") or "") == "P1"),
                "p2": sum(1 for t in _tl if str(t.get("priority") or "") == "P2"),
                "p3": sum(1 for t in _tl if str(t.get("priority") or "") == "P3"),
                "todo": sum(1 for t in _tl if str(t.get("status") or "") == "todo"),
                "running": sum(1 for t in _tl if str(t.get("status") or "") in ("running", "in_progress", "verifying")),
                "done": sum(1 for t in _tl if str(t.get("status") or "") in ("done", "completed")),
                "blocked": sum(1 for t in _tl if str(t.get("status") or "") == "blocked"),
                "pct": round(100 * sum(1 for t in _tl if str(t.get("status") or "") in ("done", "completed")) / len(_tl)) if _tl else 0,
            }
        except Exception:  # noqa: BLE001 — service 失败 → fallback query_engine
            stats = _project_task_stats(root, pid) or {}
    else:
        stats = _project_task_stats(root, pid) or {}
    total = stats.get("total", 0)
    p0, p1, p2, p3 = stats.get("p0", 0), stats.get("p1", 0), stats.get("p2", 0), stats.get("p3", 0)
    pct = stats.get("pct", 0)
    todo, running, done, blocked = (
        stats.get("todo", 0), stats.get("running", 0),
        stats.get("done", 0), stats.get("blocked", 0),
    )
    docs = _project_docs(root, pid)
    docs_str = ", ".join(docs) if docs else "—"
    return "\n".join([
        f"- 项目ID: {pid}",
        f"  名称: {name}",
        f"  本地地址: {local}",
        f"  Git地址: {git}",
        f"  阶段: {life or '—'} | 语言: {lang}",
        f"  任务: {total} 个 (P0: {p0} · P1: {p1} · P2: {p2} · P3: {p3})",
        f"  完成度: {pct}% (待办 {todo} · 执行中 {running} · 完成 {done} · 阻塞 {blocked})",
        f"  文档: {docs_str}",
    ])


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
    # W6 (v1.1.252): Plan/Act 双模式 (Cline) — 计划待审批时禁止"非计划消费"写工具.
    # execute_plan/chain_start 是消费 pending_plan 的批准执行入口 → 放行;
    # 其他写操作 (绕过计划直接建/改/委派) → Plan 阶段拒绝.
    _WRITE_TOOLS = {"create_task", "task_action", "delegate_external", "external_route"}
    if (ctx or {}).get("pending_plan") and tool_id in _WRITE_TOOLS:
        return {"ok": False, "error": (
            "当前处于 Plan 阶段 (计划待审批): 不能执行写操作。"
            "请先让用户批准计划 (回复『可以/开始』) 再执行; "
            "现在可以继续了解现状、调整计划或回答用户问题。")}
    if tool_id in ("plan_development", "execute_plan"):
        ctx = ctx or {}
        if tool_id == "plan_development":
            # S34-P0: project_id 优先取工具参数 (company 会话 AI 识别项目后显式传入)
            _plan_project_id = str(args.get("project_id") or project_id or "").strip()
            plan = plan_development(str(args.get("goal") or ""), str(args.get("detail") or ""),
                                    llm_fn=ctx.get("llm_fn") or (lambda p: ""))
            # S34-P0-B: Plan 必须是关联 Artifact — 唯一 plan_id + project/requirement 关联
            try:
                import uuid as _uuid
                import json as _json
                from datetime import datetime, timezone as _tz

                _plan_id = f"plan_{_uuid.uuid4().hex[:12]}"
                _now_iso = datetime.now(_tz.utc).isoformat()
            except Exception:  # noqa: BLE001
                import time as _tm

                _plan_id = f"plan_{int(_tm.time() * 1000)}"
                _now_iso = _tm.strftime("%Y-%m-%dT%H:%M:%S+00:00", _tm.gmtime())
            plan["plan_id"] = _plan_id
            plan["project_id"] = _plan_project_id
            plan["requirement_id"] = ""
            plan["approval_id"] = ""
            plan["status"] = "planning"
            plan["created_at"] = _now_iso
            # S34-P0-3: 完整 Plan Artifact 字段 (缺省补全, LLM 有则保留)
            plan.setdefault("version", 1)
            plan.setdefault("assumptions", [])
            plan.setdefault("architecture", "")
            plan.setdefault("milestones", [])
            plan.setdefault("dependencies", [])
            plan.setdefault("risks", [])
            plan.setdefault("task_ids", [])
            plan.setdefault("updated_at", _now_iso)
            ctx["pending_plan"] = plan
            ctx["plan_id"] = _plan_id
            # P0-B (v1.1.244): 计划落 durable progress_card (OpenClaw 思路)
            try:
                from .progress_card import save_from_plan

                save_from_plan(root, (ctx or {}).get("session_id") or "", plan)
            except Exception:  # noqa: BLE001 — 落卡失败不阻断
                pass
            # S34-CORE-C5: Requirement 真实落盘 (idea → Requirement Record)
            # 注: extract_requirement 依赖 conv 实体 (conv_ 体系); Web 会话是
            # console_sessions (sess- 体系) → 独立落盘 requirements.json (不依赖 conv)
            try:
                import json as _json
                import uuid as _uuid
                from datetime import datetime, timezone as _tz

                _req_dir = Path(root) / "requirements"
                _req_dir.mkdir(parents=True, exist_ok=True)
                _req_file = _req_dir / "requirements.json"
                _reqs = []
                if _req_file.is_file():
                    _reqs = _json.loads(_req_file.read_text(encoding="utf-8"))
                if not isinstance(_reqs, list):
                    _reqs = []
                _rid = f"req_{_uuid.uuid4().hex[:12]}"
                _reqs.append({
                    "id": _rid,
                    "session_id": (ctx or {}).get("session_id") or "",
                    "project_id": _plan_project_id,
                    "title": str(plan.get("goal") or "")[:80],
                    "description": str(args.get("detail") or "")[:500],
                    "status": "VALIDATED",
                    "created_at": datetime.now(_tz.utc).isoformat(),
                })
                _req_file.write_text(_json.dumps(_reqs, ensure_ascii=False, indent=2), encoding="utf-8")
                ctx["requirement_id"] = _rid
                plan["requirement_id"] = _rid
            except Exception:  # noqa: BLE001 — 需求落盘失败不阻断
                pass
            # P1 (D2/D13): 同步产生 canonical REQ-* (Product Truth domain;
            # 旧 req_* = legacy 兼容保留; REQ-* 进 product_truth store 供 trace)
            try:
                from factory_console.product_truth import create_requirement

                _c_req = create_requirement(
                    root, title=str(plan.get("goal") or "")[:80],
                    description=str(args.get("detail") or "")[:500],
                    priority="P0",
                    source=f"session:{str((ctx or {}).get('session_id') or '')}",
                    idempotency_key=f"session:{str((ctx or {}).get('session_id') or '')}:plan",
                    actor="session-chain",
                )
                if _c_req:
                    plan["req_canonical_id"] = _c_req.get("id")  # REQ-* (provenance)
            except Exception:  # noqa: BLE001 — REQ-* 写失败不阻断 (失败安全)
                pass
            # S34-CORE-C3: 真实 Approval Request (持久化 PENDING → 可批准/拒绝)
            _approval_id = ""
            try:
                from factory_console.governance_service import request_approval

                _ar = request_approval(
                    root, production_run_id="", artifact_ids=[],
                    requested_by="agent", subject_type="conversation",
                    subject_id=(ctx or {}).get("session_id") or "",
                    subject_ref=_plan_id,  # S34-P0-4: 审批引用 plan_id
                )
                _approval_id = str(_ar.get("approval_id") or _ar.get("id") or "")
                ctx["pending_approval_id"] = _approval_id
                plan["approval_id"] = _approval_id
            except Exception:  # noqa: BLE001 — 审批创建失败不阻断 (诚实标注)
                pass
            # P0-B: Plan 持久化到 session_plans.json (关联 Artifact, 可查询)
            try:
                import json as _json
                from datetime import datetime, timezone as _tz

                _spf = Path(root) / "session_plans.json"
                _sp = {}
                if _spf.is_file():
                    _sp = _json.loads(_spf.read_text(encoding="utf-8"))
                if not isinstance(_sp, dict):
                    _sp = {}
                _sp[str((ctx or {}).get("session_id") or "")] = plan
                _spf.write_text(_json.dumps(_sp, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:  # noqa: BLE001 — 计划持久化失败不阻断
                pass
            lines = [f"📋 开发计划 (请审批):\n目标: {plan.get('goal')}"]
            lines.append(f"计划 ID: {_plan_id}")
            lines.append("任务:")
            for i, t in enumerate(plan.get("tasks") or [], 1):
                lines.append(f"  {i}. [{t.get('priority')}] {t.get('title')} — {t.get('description') or ''}")
            lines.append("顺序: " + " → ".join(plan.get("order") or []))
            lines.append("验收: " + "；".join(plan.get("acceptance") or []))
            if _approval_id:
                lines.append(f"\n审批请求: {_approval_id} (PENDING — 说『同意/批准』进入执行)")
            else:
                lines.append("\n(审批系统不可用 — 计划已落卡, 说『同意/开始』继续)")
            lines.append("\n同意就回复『可以/开始』; 要改就告诉我改哪里。")
            return {"ok": True, "output": "\n".join(lines), "pending_plan": True,
                    "plan": plan, "plan_id": _plan_id, "approval_id": _approval_id}
        # execute_plan
        plan = ctx.get("pending_plan") or {}
        if not plan:
            # S34-P0-FIX: pending_plan 不跨轮 → 从持久化 session_plans 恢复 (真实)
            try:
                import json as _json

                _spf = Path(root) / "session_plans.json"
                if _spf.is_file():
                    _sp = _json.loads(_spf.read_text(encoding="utf-8"))
                    _sid = (ctx or {}).get("session_id") or ""
                    _cand = _sp.get(_sid) or {}
                    if isinstance(_cand, dict) and _cand.get("plan_id"):
                        plan = _cand
                        ctx["pending_plan"] = plan
            except Exception:  # noqa: BLE001
                plan = {}
        if not plan:
            return {"ok": False, "error": "没有待审批的计划 (先 plan_development)"}
        # P2-①: 幂等消费 — 已消费计划 (executing/completed/failed) 不得重复创建任务
        _plan_st = str(plan.get("status") or "pending")
        if _plan_st in ("executing", "completed", "failed"):
            return {
                "ok": False,
                "error": f"计划已消费 (status={_plan_st}), 不重复执行",
                "plan_id": plan.get("plan_id"),
                "plan_status": _plan_st,
            }
        tasks = args.get("tasks") or plan.get("tasks") or []
        if tasks:
            plan["tasks"] = tasks
        # S34-P0: 执行目标项目 = plan 的 project_id (优先) 或会话 project_id
        _exec_project_id = str(plan.get("project_id") or project_id or "").strip()
        r = execute_plan(plan, project_id=_exec_project_id, service=service,
                         delegate=bool(args.get("delegate") or plan.get("delegate")))
        # S34-P0-FIX: 执行前批准真实审批 (approve API — 计划批准 → 任务创建)
        if r.get("ok") and plan.get("approval_id"):
            try:
                from factory_console.governance_service import approve

                approve(root, str(plan["approval_id"]), decided_by="human")
                r["approval"] = "approved"
            except Exception as exc:  # noqa: BLE001 — 批准失败诚实标注
                r["approval_error"] = str(exc)
        # P2-①: Plan 生命周期 — 消费后持久化状态 (防重复批准重复创建任务)
        try:
            PendingPlanStore(root).update_status(
                str((ctx or {}).get("session_id") or ""),
                "executing" if r.get("ok") else "failed")
        except Exception:  # noqa: BLE001 — 状态更新失败不阻断执行
            pass
        # S47-E5: 旁路消除 — 批准执行后落 canonical PLAN-* (session_plans 仅工作态)
        if r.get("ok"):
            try:
                from factory_console import product_truth as pt
                _cplan = pt.create_plan(
                    root, project_id=_exec_project_id,
                    prd_id=str(plan.get("prd_id") or ""),
                    goal=str(plan.get("goal") or plan.get("title") or "")[:300],
                    tasks=[dict(t) for t in (plan.get("tasks") or [])][:50],
                    order=[str(x) for x in (plan.get("order") or [])][:50],
                    acceptance=[str(x) for x in (plan.get("acceptance") or [])][:20],
                    ask_approval=False, idempotency_key=f"plan-exec-{_exec_project_id}",
                    actor="human")
                try:
                    pt.transition_plan(root, _cplan["id"], "approved", actor="human")
                except Exception:  # noqa: BLE001 — 已是 approved/pending 均可
                    pass
                r["canonical_plan_id"] = _cplan["id"]
            except Exception as exc:  # noqa: BLE001 — canonical 落盘失败诚实标注
                r["canonical_plan_error"] = f"{type(exc).__name__}: {exc}"
        # P1-FIX: 建任务成功后自动初始化执行链 (ExecState, 依赖来自 backlog SSOT)
        # → 用户后续 "开始执行/继续" 由 chain_next 依赖感知逐任务推进
        if r.get("ok"):
            try:
                from .exec_state import ExecState
                from org.management import ManagementStore
                from pathlib import Path as _Path

                # 依赖/backlog_id 从 backlog SSOT 读 (ManagementStore Task 对象,
                # list_backlog dict 可能缺 dependency — 直接读真实字段)
                _btasks: list = []
                try:
                    _pd = None
                    for _cand in (_Path(root) / "workspace" / "projects").iterdir():
                        _pj = _cand / "project.json"
                        if _pj.is_file():
                            try:
                                import json as _json

                                if str(_json.loads(_pj.read_text(encoding="utf-8")).get("id") or "") == _exec_project_id:
                                    _pd = _cand
                                    break
                            except Exception:  # noqa: BLE001
                                continue
                    if _pd is None:
                        _cand = _Path(root) / "workspace" / "projects" / _exec_project_id
                        if _cand.is_dir():
                            _pd = _cand
                    if _pd is not None:
                        _btasks = ManagementStore(_pd / "management").list_tasks()
                except Exception:  # noqa: BLE001 — 目录定位失败 → 空 (可 chain_start 重建)
                    _btasks = []
                _plan_tasks = []
                for _pt in (plan.get("tasks") or []):
                    _ttl = str(_pt.get("title") or "").strip()
                    _m = next((b for b in _btasks if str(getattr(b, "title", "") or "").strip() == _ttl), None)
                    _bid = str(getattr(_m, "id", "") or "") if _m else ""
                    _deps = [str(x) for x in (getattr(_m, "dependency", None) or [])] if _m else []
                    _plan_tasks.append(dict(_pt, backlog_id=_bid, dependency=_deps))
                _st = ExecState.load(root, str((ctx or {}).get("session_id") or ""))
                _st.start({
                    "goal": plan.get("goal") or "执行链",
                    "tasks": _plan_tasks,
                    "acceptance": plan.get("acceptance") or [],
                })
                _st.state["run_id"] = f"R{int(__import__('time').time() * 1000)}"
                _st.state["project_id"] = _exec_project_id
                _st.state["plan_id"] = plan.get("plan_id") or ""
                _st.state["session_id"] = str((ctx or {}).get("session_id") or "")
                _st.save(root)
                r["exec_chain"] = "ready"
            except Exception:  # noqa: BLE001 — 执行链初始化失败不阻断 (可 chain_start 重建)
                pass
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
        if tool_id == "create_project":
            # S34-P0-F2 + CORE-C2: 创建项目 (company 会话可用) — 统一走 ConsoleService Core
            _name = str(args.get("name") or "").strip()
            _goal = str(args.get("goal") or "").strip()
            if not _name:
                return {"ok": False, "output": "创建项目需要 name (项目名称)。请向用户确认项目名称后重试。"}
            try:
                from factory_console.api.projects import create_project as _core_create

                _r = _core_create(
                    service, idea=_goal or _name, name=_name,
                    project_type=str(args.get("project_type") or ""),
                    tech=str(args.get("tech") or ""),
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "output": f"项目创建失败: {exc}"}
            if _r is None:
                return {"ok": False, "output": "项目创建失败 (Core 未返回项目)。"}
            _pid = getattr(_r, "project_id", "") or str(_r.get("project_id") or "")
            return {"ok": True, "output": (
                f"项目已创建: {_pid} | 名称: {getattr(_r, 'name', '') or _name} | "
                f"goal: {_goal or '—'}。项目 ID 为 {_pid}, 后续可用 project_status 查看进度。"
            ), "project_id": _pid}

        if tool_id == "project_list":
            # 项目清单 — markdown 无序列表, 字段完整 (ID/名称/本地地址/Git地址/阶段/语言/任务分类/完成度/文档)
            # G1: 经 org ProjectStore 门面读取 (业务代码不直接碰 JSON 路径/结构)
            try:
                from org.projects import ProjectStore

                _projs = {
                    p.id: p.to_dict()
                    for p in ProjectStore(Path(root) / "org").list_projects()
                }
            except Exception:  # noqa: BLE001
                _projs = {}
            _blocks = []
            for _pid, _p in _projs.items():
                if not isinstance(_p, dict):
                    continue
                _blocks.append(_format_project_entry(root, _pid, _p, service=service))
            lines = [f"共 {len(_blocks)} 个项目:", ""]
            if _blocks:
                lines.append("\n\n".join(_blocks))
            lines.append("")
            lines.append(_PROJECT_LIST_ANSWER_TEMPLATE)
            return {"ok": True, "output": "\n".join(lines)}
        if tool_id == "get_product_record":
            # S47-E4/E5 + S49-FIX.1: 读 canonical; scope 强制 — 绝不跨项目
            try:
                from factory_console import product_truth as pt
                kind = str(args.get("kind") or "requirement").strip().lower()
                record_id = str(args.get("record_id") or "").strip()
                kind_plural = {"idea": "ideas", "discovery": "discoveries",
                               "requirement": "requirements",
                               "prd": "prds", "plan": "plans"}.get(kind)
                getter = {"idea": pt.get_idea, "discovery": pt.get_discovery,
                          "requirement": pt.get_requirement,
                          "prd": pt.get_prd, "plan": pt.get_plan}.get(kind)
                lister = {"idea": pt.list_ideas, "discovery": pt.list_discoveries,
                          "requirement": pt.list_requirements,
                          "prd": pt.list_prds, "plan": pt.list_plans}.get(kind)
                if getter is None or lister is None or not kind_plural:
                    return {"ok": False, "error": "kind 必须是 idea/discovery/requirement/prd/plan"}
                rec = None
                if record_id:
                    rec = getter(root, record_id)
                    if rec is None:
                        return {"ok": True, "output": f"{kind} {record_id}: 不存在"}
                    # S49-FIX.1 scope: 他项目记录 → 拒绝
                    (st, val) = pt.resolve_record_scope(root, kind_plural, record_id) or ("", "")
                    if st == "project" and project_id and val != project_id:
                        return {"ok": False, "scope_denied": True,
                                "error": f"{record_id} 属于项目 {val}, 当前项目 {project_id} — "
                                         f"禁止跨项目读取 (Tool Boundary)"}
                    if st == "unbound" and project_id:
                        return {"ok": True, "output": (
                            f"{kind} {record_id} · {rec.get('status')} · {rec.get('title') or ''}\n"
                            f"归属: 未绑定项目 (存在, 但不属于当前项目可确认的 Truth — "
                            f"如需本项目 Truth 请先经 idea/discovery 建链)")}
                else:
                    # recent: 只返回当前项目 scope 内记录 (经链解析)
                    scoped = pt.scoped_recent(root, kind_plural, project_id or "", max_n=1)
                    if scoped:
                        rec = scoped[0]
                    else:
                        unbound = [r for r in lister(root)
                                   if pt.resolve_record_scope(root, kind_plural,
                                                              str(r.get("id") or ""))[0] == "unbound"]
                        if unbound:
                            u = unbound[-1]
                            return {"ok": True, "output": (
                                f"{kind} 记录: 当前项目无绑定记录; 存在未绑定记录 "
                                f"{u.get('id')} ({str(u.get('title'))[:40]}) — 不冒充本项目 Truth; "
                                f"如需引用请先建立 idea/discovery 归属链")}
                        return {"ok": True, "output": f"{kind} 记录: 无 (当前项目未建立)"}
                if rec is None:
                    return {"ok": True, "output": f"{kind} 记录: 无 (尚未建立)"}
                body = (str(rec.get("description") or rec.get("input_ref") or
                            rec.get("goal") or "")[:6000])
                if kind == "prd":
                    vers = rec.get("versions") or []
                    if vers:
                        body = str(vers[-1].get("content", {}).get("body") or body)[:6000]
                if kind == "plan":
                    _tasks = rec.get("tasks") or []
                    body = (f"{body}\n任务: {len(_tasks)} 个 " +
                            " · ".join(str(t.get("title") or "")[:40] for t in _tasks[:10]))
                return {"ok": True, "output": (
                    f"{kind} {rec.get('id')} · {rec.get('status')} · {rec.get('title') or ''}\n"
                    f"内容:\n{body}")}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"读取失败: {type(exc).__name__}: {exc}"}

        if tool_id == "save_product_record":
            # S47-E3/E4: 会话真实产出 → canonical (新建 或 record_id 迭代 draft)
            try:
                from factory_console import product_truth as pt
                kind = str(args.get("kind") or "").strip().lower()
                title = str(args.get("title") or "").strip()
                content = str(args.get("content") or "").strip()
                record_id = str(args.get("record_id") or "").strip()
                if kind not in ("discovery", "requirement", "prd", "plan", "idea"):
                    return {"ok": False, "error": "kind 必须是 idea/discovery/requirement/prd/plan"}
                kind_plural = {"idea": "ideas", "discovery": "discoveries",
                               "requirement": "requirements", "prd": "prds",
                               "plan": "plans"}.get(kind)
                if record_id:
                    # 迭代: 深化已有记录 — S49-FIX.1: scope 强制
                    (st, val) = pt.resolve_record_scope(root, kind_plural, record_id) or ("", "")
                    if st == "project" and project_id and val != project_id:
                        return {"ok": False, "scope_denied": True,
                                "error": f"{record_id} 属于项目 {val}, 当前项目 {project_id} — "
                                         f"禁止跨项目修改 (Tool Boundary)"}
                    getter = {"idea": pt.get_idea, "discovery": pt.get_discovery,
                              "requirement": pt.get_requirement,
                              "prd": pt.get_prd, "plan": pt.get_plan}.get(kind)
                    existing = getter(root, record_id) if getter else None
                    if existing is None:
                        return {"ok": False, "not_found": True,
                                "error": f"{kind} {record_id} 不存在, 无法更新 (省略 record_id 新建)"}
                    # P1b: title 可省略 → 保留原标题 (REFINE 语义)
                    if not title:
                        title = str(existing.get("title") or "").strip()
                        if not title and kind != "prd":
                            return {"ok": False, "validation": {
                                "missing": ["title"], "repairable": False,
                                "reason": "原记录无 title 且未提供 — 需要向用户询问标题",
                                "required": ["title"]}}
                    if kind == "prd":
                        if not content:
                            return {"ok": False, "validation": {
                                "missing": ["content"], "repairable": False,
                                "reason": "PRD 深化需要 content (正文) — 需要用户提供新内容",
                                "required": ["content"]}}
                        upd = pt.update_prd_content(root, record_id, str(content)[:20000], actor="human")
                    elif kind == "discovery":
                        upd = pt.update_discovery(root, record_id, title=title,
                                                  input_ref=str(content)[:8000], actor="human")
                    elif kind == "idea":
                        upd = pt.update_idea(root, record_id, title=title,
                                             description=str(content)[:8000], actor="human")
                    elif kind == "plan":
                        return {"ok": False,
                                "error": "Plan 是不可变快照 (契约) — 修改请新建 PLAN; 若仍在 pending 可用 plan_development 重新生成"}
                    else:
                        upd = pt.update_requirement(root, record_id, title=title,
                                                    description=str(content)[:8000], actor="human")
                    return {"ok": True, "record": f"{kind} {record_id} 已深化更新", "id": record_id}
                # ---- S48-FIX: Lifecycle Gate enforcement (CREATE 合法性) ----
                if kind in ("requirement", "prd", "discovery", "plan", "idea"):
                    _since = ""
                    try:
                        from factory_console.console_sessions import SessionStore
                        _sid = str((ctx or {}).get("session_id") or "")
                        if _sid:
                            _sess = SessionStore(str(Path(root) / "console_sessions.json")).get_session(_sid)
                            _since = str((_sess or {}).get("created_at") or "")
                    except Exception:  # noqa: BLE001 — since 缺失退化为全局
                        pass
                    _gate = pt.lifecycle_gate(
                        root, project_id or "", kind,
                        idea_id=str(args.get("idea_id") or ""),
                        discovery_id=str(args.get("discovery_id") or ""),
                        since=_since)
                    if not _gate.get("allowed"):
                        return {"ok": False, "governance": {
                            "denied": True,
                            "required_action": _gate.get("action"),
                            "target_kind": _gate.get("target_kind"),
                            "target_id": _gate.get("target_id"),
                            "reason": _gate.get("reason")}}
                if not title:
                    return {"ok": False, "validation": {
                        "missing": ["title"], "repairable": False,
                        "reason": "CREATE 需要 title — 无法从上下文安全推断, 应向用户询问标题或让用户确认后重试",
                        "required": ["title"]}}
                if kind == "idea":
                    rec = pt.create_idea(root, project_id=project_id, title=title,
                                         description=str(content)[:8000],
                                         source="conversation", actor="human")
                elif kind == "discovery":
                    idea_id = str(args.get("idea_id") or "").strip()
                    if not idea_id:
                        return {"ok": False, "error": "discovery 需要 idea_id (先建/查 Idea)"}
                    rec = pt.create_discovery(root, idea_id=idea_id, title=title,
                                              input_ref=str(content)[:2000], actor="human")
                elif kind == "prd":
                    rec = pt.create_prd(root, project_id=project_id, title=title, actor="human")
                    if content:
                        pt.update_prd_content(root, rec["id"], str(content)[:20000], actor="human")
                else:  # requirement → canonical REQ-* (product_truth)
                    rec = pt.create_requirement(root, title=title,
                                                description=str(content)[:8000], source="conversation",
                                                actor="human")
                rid = rec.get("discovery_id") or rec.get("req_id") or rec.get("prd_id") or rec.get("plan_id") or str(rec.get("id") or "")
                return {"ok": True, "record": f"{kind} {rid} 已写入 canonical", "id": rid}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"保存失败: {type(exc).__name__}: {exc}"}

        if tool_id == "project_lifecycle":
            # S47-E1: 产品链各阶段真实状态 (canonical product_truth + org 资产)
            return _project_lifecycle(root, project_id)

        if tool_id == "project_status":
            # 单项目 — 与 project_list 复用同一无序列表字段格式
            _proj: dict[str, Any] = {}
            if root is not None:
                try:
                    from org.projects import ProjectStore

                    _p = ProjectStore(Path(root) / "org").get_project(project_id)
                    _proj = _p.to_dict() if _p is not None else {}
                except Exception:  # noqa: BLE001
                    _proj = {}
            if not isinstance(_proj, dict):
                _proj = {}
            return {"ok": True, "output": _format_project_entry(root, project_id, _proj, service=service)}
        if tool_id == "project_tasks":
            from .query_engine import _priority_tasks, _project_task_stats

            prio = str(args.get("priority") or "").upper()
            # S50-P0-FIX: 统一经 service (slug 正确解析) — 勿拼 project_id 目录
            _all_tasks: list[dict[str, Any]] = []
            if service is not None:
                try:
                    _bl = service.list_backlog(project_id) or {}
                    _all_tasks = [t for t in (_bl.get("tasks") or []) if isinstance(t, dict)]
                except Exception:  # noqa: BLE001 — service 失败 → legacy 路径
                    pass
            if not _all_tasks:
                for _tf in (
                    Path(root) / "workspace" / "projects" / Path(project_id).name
                    / "management" / "backlog" / "task.json",
                    Path(root) / "projects" / Path(project_id).name / "tasks.json",
                ):
                    try:
                        _data = json.loads(_tf.read_text(encoding="utf-8")) or {}
                        _list = (_data.get("tasks") or {})
                        _list = _list.values() if isinstance(_list, dict) else _list
                        _all_tasks = [t for t in _list if isinstance(t, dict)]
                        if _all_tasks:
                            break
                    except Exception:  # noqa: BLE001
                        continue
            if prio in ("P0", "P1", "P2", "P3"):
                tasks = [t for t in _all_tasks if str(t.get("priority") or "").upper() == prio]
                lines = [f"{prio} 任务 ({len(tasks)}):"] + [f"- {str(t.get('title') or '')[:50]} [{t.get('status')}]" for t in tasks[:12]]
                return {"ok": True, "output": "\n".join(lines) if tasks else f"{prio} 任务: 暂无"}
            st = _project_task_stats(root, project_id)
            if not _all_tasks and not st:
                return {"ok": True, "output": "暂无任务数据"}
            # S35-UI: detail=true → 返回任务明细 markdown 表格 (查看具体任务列表)
            if str(args.get("detail") or "").lower() in ("1", "true", "yes"):
                if not _all_tasks:
                    return {"ok": True, "output": "暂无任务数据"}
                lines = ["| 任务 | 模块 | 优先级 | 类型 | 状态 |", "| --- | --- | --- | --- | --- |"]
                for t in _all_tasks[:50]:
                    _name = str(t.get("name") or t.get("title") or t.get("id") or "")
                    _mod = str(t.get("feature") or t.get("epic") or "—")
                    _prio = str(t.get("priority") or "—")
                    _type = str(t.get("agent_type") or "—")
                    _st = str(t.get("status") or "todo")
                    lines.append(f"| {_name} | {_mod} | {_prio} | {_type} | {_st} |")
                return {"ok": True, "output": "\n".join(lines)}
            # S35-UI: 回答格式强制 — 第一行总数, 下面无序列表各状态, 末尾引导句
            # (前端会把"查看具体任务列表"渲染成可点击链接, 点击发送指令)
            # P0/P1 数量: 双路径读任务 (mgmt + legacy) 按 priority 统计
            _all_tasks: list[dict[str, Any]] = []
            _seen: set[str] = set()
            for _tf in (
                Path(root) / "workspace" / "projects" / Path(project_id).name
                / "management" / "backlog" / "task.json",
                Path(root) / "projects" / Path(project_id).name / "tasks.json",
            ):
                try:
                    _data = json.loads(_tf.read_text(encoding="utf-8")) or {}
                    _list = (_data.get("tasks") or {})
                    _list = _list.values() if isinstance(_list, dict) else _list
                    for t in _list:
                        if isinstance(t, dict) and str(t.get("id")) not in _seen:
                            _seen.add(str(t.get("id")))
                            _all_tasks.append(t)
                except Exception:  # noqa: BLE001
                    continue
            _p0n = sum(1 for t in _all_tasks if str(t.get("priority") or "").upper() == "P0")
            _p1n = sum(1 for t in _all_tasks if str(t.get("priority") or "").upper() == "P1")
            return {"ok": True, "output": (
                f"任务统计: 总数 {st['total']} | 待办 {st['todo']} | 完成 {st['done']} | 执行中 {st['running']} | 阻塞 {st['blocked']} | P0 {_p0n} | P1 {_p1n} | 进度 {st['pct']}%\n"
                f"【回答模板 — 必须严格按此格式输出, 不要输出本说明】\n"
                f"当前项目共有 {st['total']} 个任务\n\n"
                f"- 待办: {st['todo']} 个\n"
                f"- 完成: {st['done']} 个\n"
                f"- 执行中: {st['running']} 个\n"
                f"- 阻塞: {st['blocked']} 个\n"
                f"- P0: {_p0n} 个\n"
                f"- P1: {_p1n} 个\n\n"
                f"需要我查看具体任务列表，或者帮你启动某个任务吗？"
            )}
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
            # S50-P1A: Production Entry Gate — 无合法 PLAN 禁止生产 TASK
            if service is None:
                return {"ok": False, "error": "服务不可用"}
            _pg = _production_entry_gate(root, project_id, ctx)
            if not _pg.get("allowed"):
                return {"ok": False, "blocked": True,
                        "governance": {
                            "denied": True,
                            "reason": _pg.get("reason"),
                            "required_next": _pg.get("required_next")}}
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
        # ---- W7 (v1.1.253): 代码库符号地图 ----
        if tool_id == "repo_map":
            from .repo_map import build_repo_map

            return build_repo_map(root, project_id, str(args.get("query") or ""),
                                  max_chars=int(args.get("max_chars") or 1500))
        # ---- W5 (v1.1.251): skills 按需检索 ----
        if tool_id == "skill_search":
            from .skill_search import list_skills

            return list_skills(root, str(args.get("query") or ""),
                               top_k=int(args.get("max_results") or 10))
        # ---- Node Loop: Requirement Analysis (试点) ----
        if tool_id == "requirement_analysis_round":
            # 创建/恢复当前项目 active requirement-analysis NodeRun 并推进一回合
            try:
                from factory_console import requirement_analysis_node as ran
                from factory_console import node_runtime as nr
                node_id = "requirement-analysis"
                if nr.get_node(root, node_id) is None:
                    nr.register_node(root, node_id=node_id, name="requirement-analysis",
                                     node_type="requirement-analysis")
                run = nr.get_active_run(root, node_id, project_id=project_id)
                if run is None:
                    # 首轮: 收集输入 (用户原始请求来自 args.request 或会话 topic)
                    req = str(args.get("request") or
                              (ctx or {}).get("last_user") or "")[:2000]
                    run = nr.create_node_run(root, node_id,
                                             project_id=project_id,
                                             input_data={"request": req,
                                                         "project_id": project_id},
                                             trigger="user")
                    nr.bump_iteration(root, run["run_id"])
                elif run.get("state") == "WAITING_FOR_USER":
                    pend = [{"decision_id": d["decision_id"], "question": d["question"],
                             "options": d["options"]}
                            for d in (run.get("decisions") or [])
                            if d.get("status") == "PENDING"]
                    return {"ok": True, "need_user": True,
                            "node_run": run["run_id"], "state": "WAITING_FOR_USER",
                            "pending_questions": pend,
                            "output": "分析等待你的决策: " + json.dumps(pend, ensure_ascii=False)}
                # 读本项目 REQ 事实 (scoped; 无则空)
                truth = ""
                try:
                    from factory_console import product_truth as pt
                    sc = pt.scoped_recent(root, "requirements", project_id, max_n=1)
                    if sc:
                        r0 = sc[0]
                        truth = f"{r0.get('title')}: {str(r0.get('description') or '')[:1200]}"
                except Exception:  # noqa: BLE001
                    pass
                out = ran.run_round(root, run["run_id"],
                                    llm_fn=lambda pr: _simple_llm(pr, data_dir=str(root)),
                                    truth_snippet=truth)
                if out.get("state") == "WAITING_FOR_USER":
                    return {"ok": True, "need_user": True,
                            "node_run": run["run_id"], "state": "WAITING_FOR_USER",
                            "pending_questions": out.get("pending_questions"),
                            "output": f"[{out.get('dimension')}] {out.get('summary')} — 需要你决策: " +
                                      json.dumps(out.get("pending_questions"), ensure_ascii=False)}
                done = ran.finalize_if_done(root, run["run_id"])
                return {"ok": True, "need_user": False,
                        "node_run": run["run_id"],
                        "state": (done or {}).get("state") or out.get("state"),
                        "dimension": out.get("dimension"),
                        "completed": (done or {}).get("checkpoint", {}).get("completed_dimensions") if done else None,
                        "output": f"[{out.get('dimension')}] {out.get('summary')} "
                                  + ("· 需求分析完成" if done else
                                     f" · 未决问题: {json.dumps(out.get('open_questions') or [], ensure_ascii=False)}")}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"requirement_analysis_round: {exc}"}
        if tool_id == "requirement_analysis_answer":
            # 用户决策/回答 → record_decision (human) → 继续回合直至需用户或收敛
            try:
                from factory_console import requirement_analysis_node as ran
                from factory_console import node_runtime as nr
                did = str(args.get("decision_id") or "").strip()
                chosen = str(args.get("chosen") or "").strip()
                run = nr.get_active_run(root, "requirement-analysis", project_id=project_id)
                if run is None:
                    return {"ok": False, "error": "无活动 requirement-analysis NodeRun (先 requirement_analysis_round)"}
                if did and chosen:
                    nr.record_decision(root, run["run_id"], did, chosen=chosen, actor="human")
                pend = [d for d in (run.get("decisions") or []) if d.get("status") == "PENDING"]
                if pend:
                    return {"ok": True, "need_user": True,
                            "node_run": run["run_id"], "state": "WAITING_FOR_USER",
                            "pending_questions": [{"decision_id": d["decision_id"],
                                                   "question": d["question"],
                                                   "options": d["options"]} for d in pend],
                            "output": "仍有待决策: " + json.dumps([p["question"] for p in pend], ensure_ascii=False)}
                # 决策已清 → 续推进 (最多 3 回合防单次调用过长)
                for _ in range(3):
                    out = ran.run_round(root, run["run_id"],
                                    llm_fn=lambda pr: _simple_llm(pr, data_dir=str(root)))
                    if out.get("need_user"):
                        return {"ok": True, "need_user": True,
                                "node_run": run["run_id"], "state": "WAITING_FOR_USER",
                                "pending_questions": out.get("pending_questions"),
                                "output": f"[{out.get('dimension')}] {out.get('summary')} — 需要你决策: " +
                                          json.dumps(out.get("pending_questions"), ensure_ascii=False)}
                    done = ran.finalize_if_done(root, run["run_id"])
                    if done:
                        return {"ok": True, "node_run": run["run_id"], "state": "COMPLETED",
                                "output": "需求分析完成 (NodeRun COMPLETED): " +
                                          json.dumps({"dimensions": (done.get("checkpoint") or {}).get("completed_dimensions")}, ensure_ascii=False)}
                return {"ok": True, "node_run": run["run_id"], "state": "RUNNING",
                        "output": "分析回合推进中 (维度未全部覆盖)"}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"requirement_analysis_answer: {exc}"}
        # ---- memory_update ----
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
            # S34-P0-FIX: chain_start 也用 plan.project_id (company 会话 AI 识别项目后)
            _cs_project_id = str(args.get("project_id") or plan.get("project_id") or project_id or "").strip()
            tasks = args.get("tasks") or plan.get("tasks") or []
            goal = str(args.get("goal") or plan.get("goal") or "")[:120]
            if not tasks:
                return {"ok": False, "error": "没有任务 (先 plan_development 出计划)"}
            # P0-A (v1.1.244): 执行链 ↔ backlog 打通 — 启动时真实建任务, 映射 backlog_id
            _enriched: list[dict[str, Any]] = []
            _created_n = 0
            _id_by_title: dict[str, str] = {}
            for _t in tasks:
                _t2 = dict(_t)
                _bid = ""
                if service is not None and _cs_project_id:
                    try:
                        _c = service.create_task(
                            _cs_project_id, title=str(_t.get("title") or "")[:80],
                            description=str(_t.get("description") or ""),
                            priority=str(_t.get("priority") or "P2"),
                        )
                        if _c:
                            _bid = str(_c.get("id") or "")
                            _created_n += 1
                            _id_by_title[str(_t.get("title") or "").strip()] = _bid
                    except Exception:  # noqa: BLE001 — 建任务失败不阻断执行链
                        _bid = ""
                _t2["backlog_id"] = _bid
                _enriched.append(_t2)
            # P1-FIX: plan.order 顺序链 → 真实 dependency (title → backlog id resolve,
            # 写回 backlog Task SSOT + ExecState 任务 — 执行链依赖感知依据)
            _order = plan.get("order") or []
            for _t in _enriched:
                _bid = str(_t.get("backlog_id") or "")
                _ttl = str(_t.get("title") or "").strip()
                if not _bid:
                    continue
                _deps: list[str] = []
                if _order:
                    _pos = next(
                        (i for i, o in enumerate(_order)
                         if o == _ttl or (_ttl and o and (_ttl in o or o in _ttl))),
                        -1,
                    )
                    if _pos > 0:
                        _prev_title = str(_order[_pos - 1]).strip()
                        _prev_id = _id_by_title.get(_prev_title, "")
                        if not _prev_id:
                            _prev_id = next(
                                (v for k, v in _id_by_title.items()
                                 if _prev_title and (_prev_title in k or k in _prev_title)),
                                "",
                            )
                        if _prev_id and _prev_id != _bid:
                            _deps = [_prev_id]
                            try:
                                if service is not None and _cs_project_id:
                                    service.update_task(
                                        _cs_project_id, _bid, dependency=_deps)
                            except Exception:  # noqa: BLE001 — 依赖回写失败不阻断
                                pass
                _t["dependency"] = _deps
            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            r = st.start({"goal": goal or "执行链", "tasks": _enriched,
                          "acceptance": plan.get("acceptance") or []})
            st.save(root)
            if not r.get("ok"):
                return r
            # S34/S35-P0-2: 生成真实 run_id (会话执行链 Run), 关联 session/plan/task
            try:
                import uuid as _uuid

                _run_id = f"R{int(__import__('time').time() * 1000)}"
                st.state["run_id"] = _run_id
                st.state["project_id"] = _cs_project_id
                st.state["plan_id"] = plan.get("plan_id") or ""
                st.state["session_id"] = (ctx or {}).get("session_id") or ""
                st.save(root)
                # 关联 session.run_ids (会话 Run 卡可见)
                try:
                    if (ctx or {}).get("session_id"):
                        from factory_console.console_sessions import _sessions_store as _ss  # noqa: F401
                        sessions_store_mod = __import__("factory_console.console_sessions", fromlist=["SessionStore"])
                        _st = sessions_store_mod.SessionStore(str(Path(root) / "console_sessions.json"))
                        _st.add_run((ctx or {}).get("session_id"), _run_id)
                except Exception:  # noqa: BLE001 — 关联失败不阻断
                    pass
            except Exception:  # noqa: BLE001 — run_id 生成失败 → 用时间戳
                _run_id = f"R{int(__import__('time').time() * 1000)}"
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
                    args=(root, _cs_project_id, _sid, service, st),
                    daemon=True,
                )
                _t.start()
                return {"ok": True, "run_id": _run_id, "output": (
                    f"✅ 执行链已启动并后台自动执行 (Run {_run_id}): {goal or '执行链'} "
                    f"({len(tasks)} 个任务, 已建 backlog {_created_n} 个)。"
                    "后台逐任务委派执行中, 每个完成后结果回写 backlog; "
                    "全部完成会自动推送交付汇报。『进度』可随时查看。")}
            return {"ok": True, "run_id": _run_id, "output": (
                f"✅ 执行链已启动 (Run {_run_id}): {goal or '执行链'} ({len(tasks)} 个任务, "
                f"已建 backlog 任务 {_created_n} 个)。"
                "说『继续』/『推进』逐任务执行(每个完成后结果回写 backlog); "
                "『进度』查看状态; 敏感任务会先确认。"
                "也可以说『自动执行』(auto) 后台全部跑完。")}
        if tool_id == "chain_next":
            from .exec_state import ExecState

            st = ExecState.load(root, (ctx or {}).get("session_id") or "")
            if st.state.get("status") != "running":
                return {"ok": False, "error": "没有运行中的执行链 (先 chain_start)"}

            # P2-② + P0-F2: Recovery — stale running 先恢复。exec_ref = EXS-* (F1),
            # canonical TaskRun 证据优先: NodeRun (run-*) → EXS result → TASK-GW registry
            # (TASK-GW 仅作 legacy 兼容, 非 canonical)。UNKNOWN → 重排队 (不伪造)。
            try:
                from ..node_runtime import get_node_run
                from ..external_executor.task_registry import ExternalTaskRegistry
                from .audit import load_records

                _reg = ExternalTaskRegistry.load(root)

                def _run_status(ref: str) -> str | None:
                    _ref = str(ref or "").strip()
                    if not _ref:
                        return None
                    # 1) TaskRun (NodeRun run-*) — canonical (EXS.task_run_id → run-*)
                    if _ref.startswith("run-"):
                        _nr = get_node_run(root, _ref)
                        if _nr:
                            return {"COMPLETED": "done", "FAILED": "failed"}.get(
                                _nr.get("state")) or None
                    # 2) EXS result (canonical execution result) — result=success/failed
                    if _ref.startswith("EXS-"):
                        try:
                            for _rec in load_records(Path(root) / "exec" / "execution_records.json"):
                                if str(_rec.get("result_id") or "") == _ref:
                                    return {"success": "done", "failed": "failed"}.get(
                                        _rec.get("result")) or None
                        except Exception:  # noqa: BLE001 — 记录不可读 → 继续
                            pass
                    # 3) TASK-GW (legacy registry 兼容 — 旧 exec_ref 数据)
                    _r = _reg.get(_ref)
                    if _r:
                        _s = str(_r.get("status") or "")
                        return _s if _s in ("done", "failed") else None
                    return None

                _rec = st.recover(_run_status)
                if _rec.get("count"):
                    st.save(root)
                    for _t in _rec.get("recovered") or []:
                        try:
                            from .progress_card import log_chain_event

                            log_chain_event(root, (ctx or {}).get("session_id") or "",
                                            f"recovery: {_t}")
                        except Exception:  # noqa: BLE001
                            pass
            except Exception:  # noqa: BLE001 — registry 不可用 → 无证据重排队
                try:
                    _rec = st.recover(None)
                    if _rec.get("count"):
                        st.save(root)
                except Exception:  # noqa: BLE001
                    pass

            def _exec_fn(task):
                # 委派外部 AI 执行 (真实): 走执行器网关 (G1-G4: 选执行器/注册/验证/回填/审计)
                from ..external_executor.gateway import gateway_execute

                title = str(task.get("title") or "")
                # P0-F1: 先建 TaskRun 锚 (run-*), gateway 透传 task_id/task_run_id → EXS 锚
                run_id = _chain_task_run(root, task, project_id)
                r = gateway_execute(
                    title, data_dir=root, project_id=project_id, max_retry=1,
                    task_id=str(task.get("backlog_id") or ""),  # P0-F1
                    task_run_id=run_id,  # P0-F1
                )
                _exs = str(r.get("result_id") or "")  # P0-F2: EXS (成功/失败均已写入)
                # P0-F2: TaskRun finalize — 吸收外部执行结果 (零二次执行, 幂等)
                if run_id:
                    try:
                        from ..node_runtime import finalize_node_run

                        finalize_node_run(
                            root, run_id,
                            success=bool(r.get("ok")),
                            verification=dict(r.get("verify") or {}),
                            failure_reason=str(r.get("error") or ""),
                            actor="session-chain",
                            note=f"gateway result absorbed (EXS {_exs})",
                            exs_id=_exs,                      # P0-F4 (I8)
                            output=str(r.get("output") or ""),
                            artifact_root=root,
                        )
                    except Exception:  # noqa: BLE001 — finalize 失败不阻断委派链
                        pass
                # P2-C (Experience Bridge): finalize 终态 → canonical exp-*
                try:
                    if run_id and _exs:
                        from ..experience_bridge import record_execution

                        record_execution(
                            root, task_run_id=run_id, exs_id=_exs,
                            success=bool(r.get("ok")),
                            ver_status=str((r.get("verify") or {}).get("result") or ""),
                            project=project_id,
                            task=str(task.get("title") or "")[:80],
                            actor="session-chain",
                        )
                except Exception:  # noqa: BLE001 — bridge 失败不阻断
                    pass
                if not r.get("ok"):
                    return {"ok": False, "error": r.get("error") or "外部执行失败",
                            # P0-F2: 失败也回传 EXS (Task.exec_ref=EXS 在失败路径成立)
                            "exec_ref": _exs}
                return {"ok": True,
                        "output": (
                            f"{r.get('executor')} 完成 (任务 {r.get('task_id')}) · "
                            f"验证 {r.get('verify', {}).get('result') or 'unknown'} · "
                            f"{str(r.get('output') or '')[:300]}"),
                        "verify": dict(r.get("verify") or {}),
                        # P0-F1: exec_ref = EXS-* (result_id), 非 TASK-GW (task_id)
                        "exec_ref": _exs or str(r.get("task_id") or "")}

            r = st.next(_exec_fn, on_started=lambda: st.save(root))
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
                        _cur_cancelled = _cur.get("status") == "cancelled"
                        # P0-F1: exec_ref = EXS-* (Task 副本持久化; st.next 写入 result_id)
                        _exec_ref = str(_cur.get("exec_ref") or "") or str(_v.get("exec_ref") or "") or _bid
                        service.finish_task_exec(
                            project_id, _bid,
                            success=_cur_ok,
                            cancelled=_cur_cancelled,  # P2-①: cancelled 不得回写 FAILED
                            exec_ref=_exec_ref,
                            exec_result=(
                                f"{str(_cur.get('result') or '')[:300]}"
                                + (f" · 验证 {_v.get('result') or 'unknown'}" if _v else "")
                            ),
                            actor="session-chain",
                        )
                    except Exception:  # noqa: BLE001 — 回写失败不阻断执行链
                        pass
            # P2-④: Plan 终态聚合 (Task SSOT 幂等; 基于真实 Task 事实)
            try:
                _plan_id_r = str((st.state.get("plan_id") or ""))
                if _plan_id_r:
                    reconcile_plan(root, _plan_id_r)
            except Exception:  # noqa: BLE001 — 聚合失败不阻断执行链
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
        if tool_id == "compact_context":
            # T1 (v1.1.305): 手动上下文压缩 — 摘要 + PreCompact 交接 + 记忆沉淀
            try:
                from .handoff import ProjectSpine
                from .project_memory import MemoryStore
                from .context_layers import build_context, pick_depth

                focus = str(args.get("focus") or "")[:120]
                dd = str(root or "")
                summary_parts = ["【上下文压缩】"]
                # 1) PreCompact 交接写 Spine
                try:
                    _h2 = _get_hooks()
                    _h2.fire("PreCompact", {
                        "data_dir": dd, "project_id": project_id, "session_id": (ctx or {}).get("session_id") or "",
                        "question": focus, "last_answer": focus})
                    summary_parts.append("- 交接卡已写入 Spine (新会话可续接)")
                except Exception:  # noqa: BLE001
                    pass
                # 2) 当前问题摘要记忆
                if focus:
                    try:
                        mem = MemoryStore.load(dd, project_id)
                        mem.add(f"话题聚焦: {focus}", source="session", kind="pattern", authority="agent_claim")
                        mem.save(dd)
                    except Exception:  # noqa: BLE001
                        pass
                # 3) 返回压缩后上下文 (聚焦相关)
                try:
                    _mp2 = _model_profile(dd) if "_model_profile" in dir() else {}
                    _depth = pick_depth(_mp2.get("tier"), _mp2.get("context_window"))
                    block = build_context(dd, project_id, depth=_depth, query=focus)
                    if block:
                        summary_parts.append("【压缩后上下文】")
                        summary_parts.append(block[:800])
                except Exception:  # noqa: BLE001
                    pass
                return {"ok": True, "output": "\n".join(summary_parts)}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"压缩失败: {exc}"}
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
    # F-01: 新消息执行开始前清除会话取消标志 (幂等; 避免上一轮残留影响本轮)
    if session_id:
        try:
            from factory_console import run_liveness as _rl

            _rl.clear_session_cancel(session_id)
        except Exception:  # noqa: BLE001
            pass
    intent = understand_intent(
        question, llm_fn=lambda p: _simple_llm(p, data_dir=data_dir), history=history,
    )
    from .dialog_style import style_instruction

    # S10-127 P1.1: 分模型 prompt 模板 (强模型完整指令+自主; 弱模型精简+严收敛)
    from .model_prompt import pick_prompt

    _mconf = _resolve_model_conf(data_dir, need_fc=True)
    _mp = pick_prompt(_mconf.get("capabilities"), _mconf.get("context_window"),
                      _mconf.get("provider"))
    _max_calls = _mp["max_tool_calls"]
    _agent_system = _mp["system"]
    _reflection = _mp["reflection"]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _agent_system},
        # W4 (v1.1.250): Core Memory 注入 (persona + human 自编辑块, Letta)
        {"role": "system", "content": _core_render(data_dir)},
        # W5 (v1.1.251): skills 索引提示 (紧凑, 按需 skill_search)
        {"role": "system", "content": _skills_index(data_dir)},
        # v1.1.260: 项目源码路径事实 — 模型开局知道源码在哪 (治"找不到源码/扫错目录")
        {"role": "system", "content": _repo_fact(data_dir, project_id)},
        # v1.1.262: 深度审计引导 — 结构/审计/合理性类请求注入方法论 (抄 Hermes project-audit)
        {"role": "system", "content": _audit_guide(question, intent)},
        # v1.1.267: 深度调研引导 — 调研/研究/对比类请求注入方法论 (抄 Hermes 调研风格)
        {"role": "system", "content": _research_guide(question, intent)},
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
    # ---- 上下文连贯性: 话题账本视图优先, fallback 最近 N 轮 (含工具结果) ----
    hist_block = context_view if (context_view or "").strip() else _history_text(history)
    if hist_block:
        messages.append({"role": "system", "content": (
            f"【最近对话】(保持上下文连贯, 引用前文时注明; 与本次问题矛盾处以后者为准)\n{hist_block}"
        )})
    # Phase 3: 当前产品链 NodeRun 锚 — 若项目有 active NodeRun, 确定性注入
    # (Conversation 定位当前 Work → 交 Node; '继续/分析' = resume SAME run)
    _nr_ctx = _node_run_context(data_dir, project_id)
    if _nr_ctx:
        messages.append({"role": "system", "content": (
            "【当前产品链 NodeRun】(执行事实 SSOT — 据此继续工作, 勿另起炉灶)"
            f"\n{_nr_ctx}"
        )})
    # S49-FIX: 无论账本/文本, 最近工具执行结果必须可见 (跨轮复用, 防重查)
    _tool_hist = _tool_result_text(history, max_turns=3)
    if _tool_hist:
        messages.append({"role": "system", "content": (
            "【最近已查到的真实事实 (工具结果, 可直接引用, 勿重复调查)】\n" + _tool_hist
        )})
    # ---- S49-FIX: 回答合成纪律 (结论先行/复用已有事实/禁空转) ----
    messages.append({"role": "system", "content": (
        "【回答纪律】先直接回答用户当前这句, 再给依据 (已确认事实/证据来源); "
        "不确定处明说『不确定/推断/待确认』, 不把推断说成事实。"
        "若上文 [工具 X 结果] 或 AI 上轮已给出足够信息 → 直接基于它综合回答, "
        "不要重复调查/重复调用同批工具 (除非用户明确要新事实)。"
        "禁止『让我再看看/我再查一下/需要重新读取』式无结论空转 — "
        "每轮回答须给出判断、结论或明确的下一步。若确实需要补充一个关键新事实, "
        "最多调用一个针对性工具。"
    )})
    # ---- S47-E2: Semantic Governor + Conversation State (主语义控制) ----
    _gov_guide = ""
    _gov: dict[str, Any] = {}
    try:
        _cstate = _conv_state_load(data_dir, session_id) if (data_dir and session_id) else {}
        _gov = _govern_turn(
            question, _cstate, history,
            (lambda p: _simple_llm(p, data_dir=data_dir)) if data_dir else None)
        if _gov.get("relation") != "unknown":
            _gov_guide = _governance_guide(
                _gov.get("relation", ""), _gov.get("domain", ""),
                bool(_gov.get("needs_tool")), _cstate, question)
            # 更新会话状态 (供下一轮)
            if data_dir and session_id:
                _cstate.update({
                    "topic": _gov.get("topic") or _cstate.get("topic") or "",
                    "domain": _gov.get("domain") or _cstate.get("domain") or "",
                    "relation": _gov.get("relation") or "",
                })
                _conv_state_save(data_dir, session_id, _cstate)
    except Exception:  # noqa: BLE001 — governor 失败不阻断
        _gov_guide = ""
    if _gov_guide:
        messages.append({"role": "system", "content": _gov_guide})

    # ---- S47-E3.1: Active Work 锚定 (Truth-aware + state 持久化) ----
    try:
        if _gov_guide and session_id and data_dir:
            _wstate = _conv_state_load(data_dir, session_id)
            _wstate.update({"relation": _gov.get("relation", ""),
                            "topic": _gov.get("topic") or _wstate.get("topic") or "",
                            "domain": _gov.get("domain") or _wstate.get("domain") or ""})
            # 读真实 Truth 摘要 (product_lifecycle 同源, 供 resolver 判缺口)
            _truth = ""
            try:
                _tl = _project_lifecycle(data_dir, project_id)
                if _tl.get("ok"):
                    _truth = str(_tl.get("output") or "")[:1500]
            except Exception:  # noqa: BLE001
                pass
            _recovery, _aw = _work_recovery_guide(
                question, _wstate, history,
                (lambda p: _simple_llm(p, data_dir=data_dir)) if data_dir else None,
                truth_summary=_truth)
            if _recovery:
                messages.append({"role": "system", "content": _recovery})
                # E3.2: resolver 结构化输出真写回 state (跨轮锚定, replace 语义)
                if _aw:
                    _wstate["active_work"] = _aw.get("goal") or _wstate.get("active_work") or ""
                    _wstate["next_action"] = _aw.get("next_action") or ""
                    _wstate["current_stage"] = _aw.get("current_stage") or ""
                    _wstate["need_user_input"] = bool(_aw.get("need_user_input"))
                _conv_state_save(data_dir, session_id, _wstate)
    except Exception:  # noqa: BLE001 — recovery 失败不阻断
        pass

    # ---- E1/E2 降级: 语义 guide 未触发且上轮提议句尾匹配 → 词表/文本 guide ----
    if not _gov_guide:
        cont_guide = _continuation_guide_semantic(
            question, history,
            (lambda p: _simple_llm(p, data_dir=data_dir)) if data_dir else None)
        if cont_guide:
            messages.append({"role": "system", "content": cont_guide})
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
        # T9: query=question → 记忆相关召回 (跨会话记忆精准注入)
        _ctx_block = build_context(data_dir, project_id, depth=_depth, query=question)
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
    _usage_cost = 0.0
    import time as _time
    _start_ms = _time.monotonic() * 1000
    _converge = "reflection"
    # S34-003B: 上下文窗口兜底 (providers.json 无 catalog 时按模型名查表)
    try:
        from .llm_gateway import model_context_window as _lg_model_cw
    except Exception:  # noqa: BLE001
        _lg_model_cw = lambda _m: 0
    # ---- S2 (v1.1.243): 循环护栏 — 无进展检测 / 同工具连续失败 / 整轮超时 ----
    _guard: dict[str, Any] = {
        "tool_fail_streak": {},     # 工具名 → 连续失败次数
        "all_fail_rounds": 0,       # 连续"整轮全失败"轮数
        "warned_fail": set(),       # 已注入换策略提示的工具
        "warned_no_progress": False,
        "empty_retries": 0,         # S35-BUGFIX: 空回答连续重试次数 (上限防死循环)
        "claim_retries": 0,         # P0-001: 执行声称校验失败重试次数 (软收敛)
        "claim_retries_hard": 0,    # P0-001: 硬收敛轮声称校验重试次数
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
            # F-01: 会话取消检查 — 用户 Stop → 真实停止后续轮次 (循环边界, 幂等)
            if session_id:
                try:
                    from factory_console import run_liveness as _rl

                    if _rl.session_cancelled(session_id):
                        _cancel_answer = "（已停止）"
                        _audit_sess(data_dir, session_id, question, intent, calls,
                                    total_calls, max_rounds, _start_ms, "cancelled",
                                    _cancel_answer, _usage_prompt, _usage_completion)
                        try:
                            _finish_session_hooks(data_dir, project_id, session_id,
                                                  question, messages, _cancel_answer)
                        except Exception:  # noqa: BLE001
                            pass
                        return {
                            "answer": _cancel_answer, "calls": calls, "intent": intent,
                            "cancelled": True,
                            "evidence": [{"tool": c["tool"], "ok": c["ok"],
                                          "output": str(c.get("output") or c.get("error") or "")[:300]}
                                         for c in calls],
                            "usage": {"model": str(_mconf.get("model") or ""), "cancelled": True},
                        }
                except Exception:  # noqa: BLE001 — 取消检查失败不阻断
                    pass
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
                _usage_cost += float(_u.get("estimated_cost_usd") or 0.0)
            tcs = resp.get("tool_calls") or []
            if not tcs:
                # S1.1 (v1.1.244): 文本模拟工具调用检测 — 按 provider traits 开关 (A0: deepseek 需要, 强模型默认不需要)
                _content = resp.get("content") or ""
                _anti_fake = bool((_mp.get("traits") or {}).get("anti_fake_toolcall"))
                if _anti_fake and re.search(r"<tool_calls>|```tool_calls|</tool_calls>|<invoke name=", _content):
                    # A (v1.1.269): 代码级兑现 — 提取文本模拟的 invoke, 真实执行并回喂 (不靠模型自觉)
                    _fake = _extract_fake_invokes(_content)
                    _real = None
                    for _f in _fake[:1]:  # 一次兑现一个, 避免批量误执行
                        _fn = str(_f.get("name") or "")
                        if _fn in {t["function"]["name"] for t in tools} or _fn in _SESSION_TOOL_WHITELIST:
                            _fr = dispatch(_fn, _f.get("args") or {}, root=root, project_id=project_id,
                                           service=service, ctx=ctx)
                            _real = {"name": _fn, "args": _f.get("args") or {}, "result": _fr}
                            break
                    if _real:
                        total_calls += 1
                        calls.append({"tool": _real["name"], "params": _real["args"],
                                      "ok": _real["result"].get("ok"), "output": _real["result"].get("output"),
                                      "error": _real["result"].get("error")})
                        _tj = json.dumps(_real["result"], ensure_ascii=False)
                        messages.append({"role": "tool", "tool_call_id": f"fake-{total_calls}",
                                         "content": _tj[:6000]})
                        messages.append({"role": "system", "content": (
                            "已把你文本里写的工具调用(未走真实通道)自动兑现执行。"
                            "请基于真实工具结果继续回答; 以后需要工具请直接用真实调用通道。"
                        )})
                        continue
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
                # S34/S35-P0-1/6: 生产声明约束 — LLM 声称计划/任务/执行必须有工具 ID 证据
                from .answer_verify import production_claim_prompt

                messages.append({"role": "system", "content": production_claim_prompt()})
                # S35-UI: 建议任务格式引导 — 用户要"分析任务/补充任务/建议任务"时,
                # 建议项必须用 "- P0: 标题(理由)" 格式 (前端渲染"加入任务清单"按钮)
                if re.search(r"分析.{0,6}任务|补充.{0,6}任务|建议.{0,6}任务|还缺|缺口|需要补充", question):
                    messages.append({"role": "system", "content": (
                        "输出'建议补充的任务'清单时, 必须严格逐条用以下格式 (这是给程序的接口, 不是排版建议):\n"
                        "- P0: 任务标题(简短理由)\n"
                        "- P1: 任务标题(简短理由)\n"
                        "- P2: 任务标题(简短理由)\n"
                        "硬性要求:\n"
                        "1. 每行以 '- ' 开头, 接着 P0/P1/P2 + 英文冒号 + 空格;\n"
                        "2. 禁止用 '**P0 级**' '**P0:**' 'P0 级' 等变体;\n"
                        "3. 理由用半角括号 () 或中文括号 () 紧跟在标题后;\n"
                        "4. 建议任务全部用此格式集中列出 (可以放在回答末尾的'建议任务'小节), 每条一行。"
                    )})
                # W8 (v1.1.253 + v1.1.261 强化): 输出 guardrail — 数字+细节证据校验
                # 回答含数字/色值/版本/类名/路径 → 与已调工具结果比对; 无据 → 强制修正 (治"方向对、细节编")
                _answer = _strip_fake_toolcalls(resp.get("content") or "（模型未输出）")
                # P0 回归修复: 清洗后为空但工具已执行 → 强制自然语言总结 (不能返回空/协议)
                # S35-BUGFIX: 空回答无条件重试 (轮次用尽也重试 — 空回答不可交付, 优于超轮;
                # empty_retries 上限 3 次防死循环)
                if (not _answer.strip()) and calls and _guard["empty_retries"] < 3:
                    _guard["empty_retries"] += 1
                    messages.append({"role": "system", "content": (
                        "你刚才的输出是内部工具调用协议 (DSML), 不是给用户的回答。"
                        "请基于已执行的工具结果, 用自然语言直接回答用户的原始问题; "
                        "禁止再输出任何 <tool_calls>/<invoke>/<parameter> 标签。"
                    )})
                    continue
                if calls:
                    from .answer_verify import verify_details

                    _ref_text = "\n".join(
                        str(c.get("output") or c.get("error") or "") for c in calls)
                    _chk = verify_details(_answer, _ref_text)
                    if not _chk.get("ok") and total_calls < max_rounds - 1:
                        messages.append({"role": "system", "content": (
                            "【输出校验未通过 (W8 强化)】你回答中的这些数字/色值/版本/类名/路径在已调工具结果里找不到依据: "
                            + ", ".join(_chk.get("unverified") or []) + "。"
                            "请修正: 删除无据细节, 或明确标注『未查到具体值』, 或基于工具结果重述; "
                            "不要编造具体色值/路径/数字。"
                        )})
                        continue
                # P0-001: Execution Claim Validator — 执行声称必须有真实工具记录
                # (LLM output is not execution evidence; 零工具调用的声称 = 负证据)
                from .execution_truth import (
                    execution_claim_block_prompt, sanitize_hard_converge,
                    validate_execution_claims)
                # P0-FIX: 数量型事实比对 — actual_count 来自本轮真实 create_task 成功数
                _created_n = len([
                    c for c in calls
                    if c.get("tool") == "create_task" and c.get("ok") and c.get("output")
                ])
                _claim_v = validate_execution_claims(
                    _answer, calls, actual_count=_created_n)
                if not _claim_v["ok"]:
                    if _guard["claim_retries"] < 2:
                        _guard["claim_retries"] += 1
                        messages.append({"role": "system", "content": (
                            execution_claim_block_prompt(
                                _claim_v["missing"], _claim_v["reason"],
                                outcome=_claim_v.get("outcome") or "",
                                claimed_count=_claim_v.get("claimed_count"),
                                actual_count=_claim_v.get("actual_count")))})
                        continue
                    # 重试用尽仍声称无据 → 追加诚实标注, 不裸放行 (Final Response Sanitization)
                    _answer = sanitize_hard_converge(
                        _answer, calls, actual_count=_created_n)
                # 模型自主收敛 (直接回答/追问) — agentic: 不强制拦截
                if total_calls == 0:
                    _converge = "autonomous"
                _audit_sess(data_dir, session_id, question, intent, calls,
                            total_calls, max_rounds, _start_ms, _converge, _answer,
                            _usage_prompt, _usage_completion)
                try:
                    _finish_session_hooks(data_dir, project_id, session_id, question, messages, _answer)
                except Exception:  # noqa: BLE001
                    pass
                return {"answer": _answer, "calls": calls, "intent": intent,
                        "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls],
                        # S34-003B: 执行详情 — 模型/上下文/tokens 真实用量 (前端 ToolCallList 展示)
                        "usage": {"model": str(_mconf.get("model") or ""),
                                  "context_window": int(_mconf.get("context_window") or 0) or _lg_model_cw(str(_mconf.get("model") or "")),
                                  "prompt_tokens": _usage_prompt,
                                  "completion_tokens": _usage_completion,
                                  "total_tokens": _usage_prompt + _usage_completion,
                                  "elapsed_s": round((_time.monotonic() * 1000 - _start_ms) / 1000, 1),
                                  "estimated_cost_usd": round(_usage_cost, 6)}}
            if _guard["force_converge"]:
                break
            # 中间 assistant 消息入历史前也清洗文本模拟 <tool_calls> (模型可能同时输出真实调用+文本噪音)
            messages.append({"role": "assistant",
                             "content": _strip_fake_toolcalls(resp.get("content") or ""),
                             "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function") or {}
                tid = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                _tool_t0 = __import__("time").monotonic()
                # S34/S35-P0-5: Context→Tool Argument 注入 — 项目类工具结果学习 project_id,
                # 后续项目相关工具调用自动补参 (AI 识别项目后不再丢 project_id)
                _resolved_project_id = ""
                try:
                    if args.get("project_id"):
                        _resolved_project_id = str(args["project_id"])
                    elif tid in ("project_list", "project_status", "project_scan",
                                 "project_tasks", "project_structure", "project_plan"):
                        # 项目查询类: 从会话 project_id 或 AI 已传参数取
                        _resolved_project_id = str(project_id or "")
                except Exception:  # noqa: BLE001
                    pass
                # 项目相关写/查工具自动补 project_id (非项目工具不动)
                if _resolved_project_id and not args.get("project_id"):
                    if tid in ("project_tasks", "project_status", "project_scan",
                               "project_structure", "chain_start", "chain_next",
                               "chain_status", "task_action", "execute_plan",
                               "create_task", "project_plan", "plan_development",
                               "execute_task"):
                        _args = dict(args)
                        _args["project_id"] = _resolved_project_id
                        args = _args
                result = dispatch(tid, args, root=data_dir, project_id=_resolved_project_id or project_id, service=service, ctx=ctx)
                # 工具结果带 project_id → 学习 (本轮后续工具调用自动注入)
                if not _resolved_project_id:
                    _rpid = str(result.get("project_id") or "").strip()
                    if _rpid:
                        _resolved_project_id = _rpid
                        # 用学习到的 project_id 重跑项目查询类工具 (修正空参查询)
                        if tid in ("project_tasks", "project_status", "project_scan",
                                   "project_structure") and result.get("ok") is False:
                            _args2 = dict(args)
                            _args2["project_id"] = _resolved_project_id
                            result = dispatch(tid, _args2, root=data_dir,
                                              project_id=_resolved_project_id,
                                              service=service, ctx=ctx)
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
                # S10-127 M4.1 + T6: PostToolUse 审计 (工具调用全量落盘)
                try:
                    _get_hooks().fire("PostToolUse", {
                        "tool_id": tid, "args": args, "project_id": project_id,
                        "session_id": session_id, "result_ok": bool(result.get("ok")),
                        "data_dir": data_dir, "duration_ms": _tool_dur})
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
                                  "command": str(result.get("command") or "")[:2000],
                                  # T4 (v1.1.279): 全息展示 — 参数预览 + 结果截断 (完整结果在 calls 里)
                                  "params": json.dumps(args, ensure_ascii=False)[:500],
                                  "output": str(result.get("output") or "")[:2000]})
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
                # v1.1.266: 关键工具失败 → 注入"失败处理规则" (失败≠无数据, 重试或追问, 禁止编结论)
                if not result.get("ok") and tid in ("code_scan", "project_scan", "repo_map",
                                                     "read_code", "search_code", "project_structure"):
                    messages.append({"role": "system", "content": (
                        "工具执行失败。处理规则: ① 换工具/换路径/换参数重试 (不要重复同一调用); "
                        "② 仍失败 → 明确询问用户 (如『请确认项目源码路径』), 或诚实说明『定位失败, 需要确认』; "
                        "③ 【禁止】基于失败推断『无数据/无代码/项目不存在/仓库为空』等结论 — 失败≠没有, 别胡说。"
                    )})
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
        # P0-001: 硬收敛轮同样校验执行声称 — 一次重试机会, 用尽则追加诚实标注
        from .execution_truth import (
            execution_claim_block_prompt, sanitize_hard_converge,
            validate_execution_claims)
        _created_n_h = len([
            c for c in calls
            if c.get("tool") == "create_task" and c.get("ok") and c.get("output")
        ])
        _claim_h = validate_execution_claims(
            content, calls, actual_count=_created_n_h)
        if not _claim_h["ok"]:
            if _guard["claim_retries_hard"] < 1:
                _guard["claim_retries_hard"] += 1
                messages.append({"role": "system", "content": (
                    execution_claim_block_prompt(
                        _claim_h["missing"], _claim_h["reason"],
                        outcome=_claim_h.get("outcome") or "",
                        claimed_count=_claim_h.get("claimed_count"),
                        actual_count=_claim_h.get("actual_count")))})
                resp = call_with_tools(messages, None, data_dir=data_dir)
                content = resp.get("content") or ""
            else:
                content = sanitize_hard_converge(
                    content, calls, actual_count=_created_n_h)
        # S34-003B: 反射轮 usage 也累加 (工具调用循环后必走此路径)
        _u2 = resp.get("usage") or {}
        if _u2:
            _usage_prompt += int(_u2.get("prompt_tokens") or 0)
            _usage_completion += int(_u2.get("completion_tokens") or 0)
            _usage_cost += float(_u2.get("estimated_cost_usd") or 0.0)
        _converge = "hard_cap" if total_calls >= _max_calls else "reflection"
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, _converge, content,
                    _usage_prompt, _usage_completion)
        return {"answer": content[:2000], "calls": calls, "intent": intent,
                "evidence": [{"tool": c["tool"], "ok": c["ok"], "output": str(c.get("output") or c.get("error") or "")[:300]} for c in calls],
                # S34-003B: 执行详情 — 真实用量 (与 1457 一致)
                "usage": {"model": str(_mconf.get("model") or ""),
                          "context_window": int(_mconf.get("context_window") or 0) or _lg_model_cw(str(_mconf.get("model") or "")),
                          "prompt_tokens": _usage_prompt,
                          "completion_tokens": _usage_completion,
                          "total_tokens": _usage_prompt + _usage_completion,
                          "elapsed_s": round((_time.monotonic() * 1000 - _start_ms) / 1000, 1),
                          "estimated_cost_usd": round(_usage_cost, 6)}}
    except Exception as exc:  # noqa: BLE001 — LLM 不可用 → 回退旧路由
        _audit_sess(data_dir, session_id, question, intent, calls,
                    total_calls, max_rounds, _start_ms, "rejected", "",
                    _usage_prompt, _usage_completion)
        return {"answer": "", "rejected": True, "calls": calls, "evidence": [],
                "reason": f"原生 FC 不可用: {exc}"}


def _research_guide(question: str, intent: dict[str, Any]) -> str:
    """调研/研究/对比类请求 → 注入深度调研方法。其他 → 空。"""
    q = str(question or "")
    _kws = ("调研", "研究", "对比", "开源", "怎么做的", "如何处理", "如何实现", "查一下", "了解一下",
            "分析一下", "哪个好", "区别", "抄", "借鉴", "方案", "机制", "设计哲学")
    if any(k in q for k in _kws) and intent.get("intent") in ("analyze", "deep_analyze", "question"):
        return RESEARCH_METHOD_PROMPT
    return ""


def _audit_guide(question: str, intent: dict[str, Any]) -> str:
    """结构审计/合理性类请求 → 注入深度审计方法 + 报告格式。其他 → 空。"""
    q = str(question or "")
    _kws = ("结构", "合理", "审计", "扫描整体", "架构", "代码库", "体检", "评估", "审视", "健康")
    if any(k in q for k in _kws) and intent.get("intent") in ("analyze", "deep_analyze", "question"):
        return AUDIT_METHOD_PROMPT
    return ""


def _repo_fact(data_dir: str | Path | None, project_id: str) -> str:
    """项目源码仓库路径事实 (locate_repo → 兜底已知工作区 → 失败给指引)。

    S34-P0-F1: project_id 空 (company scope) → 绝不注入"当前项目源码" —
    AI 不得因系统存在工作区就假设有当前项目。
    """
    if not project_id or not str(project_id).strip():
        return (
            "【当前上下文】你处于公司级会话，当前没有绑定任何项目。"
            "不要假设存在'当前项目'，不要自动选择/猜测项目。"
            "用户提到具体项目时：先用 project_list 查项目清单；"
            "要创建新项目时：先向用户确认需求与名称，再调用创建项目流程。"
        )
    try:
        from .code_scan import locate_repo

        repo = locate_repo(data_dir, project_id)
    except Exception:  # noqa: BLE001
        repo = None
    if repo is None:
        # 兜底: 当前开发环境 AI Factory 自身源码在本地工作区
        _known = Path("/Users/Shared/work/ai-software-factory")
        if _known.is_dir():
            repo = _known
    if repo:
        return (
            f"【项目源码】当前项目源码仓库在: {repo}。"
            "查代码/结构/实现用 read_code/search_code/code_scan/repo_map (参数为仓库内相对路径); "
            "不要用 bash find 在数据目录扫源码。"
            "如果 code_scan 报『未定位仓库/仓库为空』, 是 project_id 或路径问题 — "
            "用 bash_exec 检查上面仓库路径, 不要据此下结论『项目无代码』。"
        )
    return (
        "【项目源码】未能自动定位源码仓库。查代码前先用 bash_exec 找仓库 (如 find /Users/Shared -maxdepth 3 "
        "-name '*.git' 2>/dev/null 或 ls 常见工作目录); 不要因为定位失败就断定项目没有代码。"
    )


def _skills_index(data_dir: str | Path | None) -> str:
    """W5: skills 紧凑索引提示 (OpenClaw <available_skills>)。失败安全 → 空。"""
    try:
        from .skill_search import index_prompt

        return index_prompt(data_dir)
    except Exception:  # noqa: BLE001
        return ""


def _extract_fake_invokes(text: str) -> list[dict[str, Any]]:
    """A (v1.1.269): 从回答文本提取 <invoke name=..><parameter name=..>..</invoke> 模拟调用 → [{name, args}].

    用于"代码级兑现": 模型把工具调用写成文本(没走真实通道) → 系统提取并真实执行, 不靠模型自觉。"""
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<invoke name="([^"]+)"[^>]*>([\s\S]*?)</invoke>',
        str(text or ""),
    ):
        name = m.group(1).strip()
        body = m.group(2) or ""
        args: dict[str, Any] = {}
        for pm in re.finditer(r'<parameter name="([^"]+)">([\s\S]*?)</parameter>', body):
            key = pm.group(1).strip()
            val = pm.group(2).strip()
            # 尝试 JSON 解析 (参数可能是 json); 失败当字符串
            try:
                import json as _j

                args[key] = _j.loads(val)
            except Exception:  # noqa: BLE001
                args[key] = val
        if name:
            out.append({"name": name, "args": args})
    return out


def _strip_fake_toolcalls(text: str) -> str:
    """清洗最终回答里的文本模拟工具调用 (模型把 <tool_calls> 写进回答 → 删除, 防"假装调用")。

    S34-003B 强化: 覆盖 <tool_calls> 块、<invoke> 调用、<parameter> 参数标签,
    无论是否配对/带属性 — 内部 Tool Protocol 绝不进入用户正文。
    兼容 DSML 全角变体 (模型可能输出 <｜DSML｜tool_calls> — U+FF5C 竖线伪装)。
    """
    t = str(text or "")
    # 全角竖线 U+FF5C → ASCII | (模型转义变体归一化: <｜DSML｜tool_calls> → <|DSML|tool_calls>)
    t = t.replace("｜", "|")
    t = re.sub(r"```tool_calls[\s\S]*?```", "", t)
    t = re.sub(r"```tool_call[\s\S]*?```", "", t)
    # DSML 前缀包装: <|DSML|tool_calls> / <||DSML||invoke ...> / <||DSML||parameter ...>
    # 任意 DSML 包裹标签 (0-2 竖线) → 还原为普通标签名再走常规清洗
    t = re.sub(r"<\|{0,2}\s*DSML\s*\|{0,2}(tool_calls|invoke|parameter)([^>]*)>",
               lambda m: f"<{m.group(1)}{m.group(2)}>", t)
    # DSML 变体整块: <tool_calls> ... (可能无配对闭合 → 删到文本尾)
    t = re.sub(r"<tool_calls>[\s\S]*?(?:</tool_calls>|$)", "", t)
    # 整块优先 (含嵌套 <parameter>): 先删完整块, 再删残留散标签
    t = re.sub(r"<tool_calls>[\s\S]*?</tool_calls>", "", t)
    t = re.sub(r"<invoke[^>]*name=\"[^\"]*\"[\s\S]*?</invoke>", "", t)
    t = re.sub(r"<invoke[^>]*>[\s\S]*?</invoke>", "", t)
    t = re.sub(r"<parameter[^>]*>[\s\S]*?</parameter>", "", t)
    t = re.sub(r"</?tool_calls>", "", t)
    t = re.sub(r"<\|?\s*DSML\s*\|?tool_calls>", "", t)
    t = re.sub(r"</?invoke[^>]*>", "", t)
    t = re.sub(r"</?parameter[^>]*>", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _core_render(data_dir: str | Path | None) -> str:
    """W4: Core Memory 渲染注入 (persona + human)。失败安全 → 空。"""
    try:
        from .memory_core import render

        return render(data_dir)
    except Exception:  # noqa: BLE001
        return ""


def _tool_result_text(history: list[dict[str, Any]] | None, max_turns: int = 3) -> str:
    """S49-FIX: 最近 N 轮 assistant 消息携带的工具执行结果 → 摘要文本。

    无论上下文走账本视图还是 _history_text, 工具结果都单独注入,
    保证下一轮 LLM 直接可见 (跨轮复用 — '结果呢?' 不重查的根因修复)。
    """
    if not history:
        return ""
    lines = []
    for h in history[-(max_turns * 2):]:
        if not isinstance(h, dict) or h.get("role") != "assistant":
            continue
        tcs = ((h.get("meta") or {}).get("tool_calls")) or []
        for c in tcs[:4]:
            tname = str(c.get("tool") or "")
            out = str(c.get("output") or c.get("error") or "")
            if tname and out:
                lines.append(f"- {tname}: {out[:280]}")
    return "\n".join(lines)


def _history_text(history: list[dict[str, Any]] | None, max_turns: int = 8) -> str:
    """S49-FIX: 最近 N 轮对话 + 每轮工具执行结果 → 文本块。

    Tool Result 必须成为下轮 LLM 可见上下文 (跨轮复用, 防重查):
    assistant 消息 meta.tool_calls[].output (持久化于会话) 一并注入。
    max_turns 默认 8 (Correctness first — 过薄丢事实)。
    """
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
        lines.append(f"{who}: {content[:600]}")
        if role == "assistant":
            tcs = ((h.get("meta") or {}).get("tool_calls")) or []
            for c in tcs[:4]:
                tname = str(c.get("tool") or "")
                out = str(c.get("output") or c.get("error") or "")
                if tname and out:
                    lines.append(f"  [工具 {tname} 结果] {out[:260]}")
    return "\n".join(lines)


def _last_assistant_text(history: list[dict[str, Any]] | None) -> str:
    if not history:
        return ""
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "assistant" and str(h.get("content") or "").strip():
            return str(h["content"])
    return ""


#: 短确认/否定/收窄 语义词 (S47-E1 continuation — 语言层通用, 非场景硬编码)
_CONFIRM_WORDS: tuple[str, ...] = ("需要", "好", "好的", "可以", "行", "要", "嗯", "ok", "yes", "对", "就这么办", "继续")
_REJECT_WORDS: tuple[str, ...] = ("不用", "不需要", "不必", "不要", "算了", "先不用", "no", "不了")
#: 上一轮 assistant 提议性问句 (结尾问用户是否要执行某动作)
_PROPOSAL_PATTERN = re.compile(r"(需要吗|要我|要不要|是否|怎么样|可以吗|如何|想不想|好不好|行吗|吗[?？]?)$")

def _continuation_guide(question: str, history: list[dict[str, Any]] | None) -> str:
    """S47-E1: 通用 continuation 引导 — 用户短确认/否定/收窄 回应上一轮 AI 提议。

    零场景硬编码: 只做 (短确认语义) + (上一轮 assistant 含提议问句) 两条件,
    任何「AI 提议 → 用户 需要/好/不用/先做X」都走同一引导。无提议 → 空。
    """
    q = (question or "").strip()
    if not q or not history:
        return ""
    last = None
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "assistant":
            last = str(h.get("content") or "").strip()
            break
    if not last or not _PROPOSAL_PATTERN.search(last[-200:]):
        return ""
    lowered = q.lower()
    is_confirm = any(w in lowered for w in _CONFIRM_WORDS) and len(q) <= 12
    is_reject = any(w in lowered for w in _REJECT_WORDS)
    if not (is_confirm or is_reject):
        return ""
    proposal = last[-600:]
    tone = ("确认并执行上一轮提议" if is_confirm and not is_reject
            else "拒绝上一轮提议" if is_reject else "按用户新指示调整")
    return (
        f"【上下文延续】上一轮你提议: {proposal}\n"
        f"用户本次回复是对该提议的回应 → 判定为「{tone}」。"
        f"确认 → 立即用工具执行该提议动作; 拒绝 → 不执行并简短说明; "
        f"用户给出新指示 → 以新指示为准 (可视为在上轮提议基础上收窄/修改)。"
        f"严禁把短确认回复说成『消息不完整/只发来几个字』。"
    )


# =====================================================================
# S47-E2: LLM 语义回合分类 (Semantic Turn Relation)
# 词表只作候选检测与降级; 判定交给 LLM — 自然语言多种表达 → 同语义。
# =====================================================================
_TURN_RELATION_PROMPT = """判定用户对 AI 上一条提议/陈述的回应关系 (只输出 JSON):
{"relation": "confirm|confirm_modify|decline|reference|redirect|ambiguous",
 "summary": "一句话概括用户意图 (含修改约束时写明)"}

规则 (语义判断, 勿按字面词匹配):
- 确认/同意继续上轮提议 (需要/好/可以/行/继续吧/你继续/就按这个来/没问题…) → confirm
- 确认但附加修改/约束/顺序要求 (可以，不过先…/继续，但先别…/好，先完善…/那就按你说的先做…)
  → confirm_modify (summary 必须含约束内容)
- 拒绝/暂停上轮提议 (不用/算了/先别/暂时不做/先放一下/这个先缓一缓…) → decline
- 指代上轮内容提问 (刚才那个方案呢/你提到的 PRD/继续刚才的工作/接着上面的…) → reference
- 改变方向/新目标/纠正 (先别做 PRD 重新梳理需求/我想改目标/先做登录不做支付…) → redirect
- 无法可靠判断 → ambiguous (宁可不猜)

上一条 AI 提议: {proposal}
用户消息: {message}"""

def _classify_turn_relation(message: str, last_assistant: str,
                            llm_fn: Callable[[str], str] | None) -> tuple[str, str]:
    """LLM 语义分类回合关系 (confirm/decline/modify/…)。失败 → ("", "") 走降级。"""
    try:
        if llm_fn is None:
            return "", ""
        prompt = (_TURN_RELATION_PROMPT
                  .replace("{proposal}", str(last_assistant)[-900:])
                  .replace("{message}", str(message)[:400]))
        raw = str(llm_fn(prompt) or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return "", ""
        parsed = json.loads(m.group(0))
        rel = str(parsed.get("relation") or "").strip()
        if rel not in ("confirm", "confirm_modify", "decline",
                       "reference", "redirect", "ambiguous"):
            return "", ""
        return rel, str(parsed.get("summary") or "")
    except Exception:  # noqa: BLE001 — 分类失败 → 降级 (不阻断)
        return "", ""


def _continuation_guide_semantic(question: str, history: list[dict[str, Any]] | None,
                                 llm_fn: Callable[[str], str] | None) -> str:
    """S47-E2: 语义 continuation 引导 — LLM 判定回合关系 (非词表行为)。

    词表仅做候选检测 (上轮是否含待回应提议 + 消息是否疑似回应);
    关系与约束由 LLM 语义判断 → 注入对应引导。任何表达方式 (确认/修改/
    拒绝/指代/转向) 同一机制。
    """
    q = (question or "").strip()
    if not q or not history:
        return ""
    last = None
    for h in reversed(history):
        if isinstance(h, dict) and h.get("role") == "assistant":
            last = str(h.get("content") or "").strip()
            break
    if not last or not _PROPOSAL_PATTERN.search(last[-200:]):
        return ""
    rel, summary = _classify_turn_relation(q, last, llm_fn)
    if not rel:
        # LLM 不可用 → 降级词表 (仅保护路径, 非主机制)
        return _continuation_guide(q, history)
    proposal = last[-600:]
    guide = {
        "confirm": (f"【上下文延续】用户确认上一轮提议 → 立即用工具执行该提议。"
                    f"上一轮提议: {proposal}"),
        "confirm_modify": (f"【上下文延续】用户确认上一轮提议, 但带修改/约束: {summary} → "
                           f"执行该提议时以用户约束为准 (先做约束内容, 或在约束范围内执行)。"
                           f"上一轮提议: {proposal}"),
        "decline": (f"【上下文延续】用户拒绝上一轮提议 ({summary}) → 不执行该提议,"
                    f" 简短确认后询问/等待新方向。上一轮提议: {proposal}"),
        "reference": (f"【上下文延续】用户在指代上轮内容提问 ({summary}) → 结合上一轮"
                      f" 提议/陈述作答, 不要另起炉灶或跳题。上一轮内容: {proposal}"),
        "redirect": (f"【上下文延续】用户改变方向/给出新目标 ({summary}) → 以新目标为准,"
                     f" 不执行旧提议。上一轮提议已放弃: {proposal}"),
        "ambiguous": (f"【上下文延续】用户回复含糊 ({summary}), 但正在回应上一轮提议。"
                      f" 若意图不明 → 提出最小澄清问题 (列出可能选项), 不要猜工具执行,"
                      f" 严禁说『消息不完整/只发来几个字』。上一轮提议: {proposal}"),
    }
    text = guide.get(rel) or ""
    if not text:
        return ""
    return text + "\n严禁把短回复说成『消息不完整/只发来几个字』；高置信执行, 中置信最小澄清, 低置信不猜。"



# =====================================================================
# S47-E2: Conversation Semantic Control Plane
# - governor: LLM 语义判定回合关系 + 域 + 是否需工具 (零关键词行为)
# - conv state: 轻量会话级状态 (topic/domain/pending/last_assistant)
# =====================================================================
_GOVERN_RELATIONS = ("new_goal", "continue", "confirm", "decline", "modify",
                     "reference", "complaint", "correction", "clarify",
                     "question", "opinion", "refinement", "unknown")
_GOVERN_DOMAINS = ("product_lifecycle", "project", "task", "execution",
                   "acceptance", "release", "conversation", "general")

_GOVERN_PROMPT = """理解用户当前这句话在整个对话中的语义 (只输出 JSON):
{"relation": "new_goal|continue|confirm|decline|modify|reference|complaint|correction|clarify|question|opinion|unknown",
 "domain": "product_lifecycle|project|task|execution|acceptance|release|conversation|general",
 "needs_tool": true|false,
 "topic": "一句话当前主题"}

语义规则 (基于对话上下文判断, 勿按字面词):
- 用户反馈 AI 答错/跑题/混乱/不是这个意思 → complaint 或 correction
  (needs_tool=false — 这是对话恢复, 不是项目查询)
- 用户在评价上一轮产出质量/要求更具体 (太模糊了/不够具体/再具体一点/
  展开细化/把功能拆开说) → refinement (needs_tool=true — 需读已有产出
  并深化, 不是解释现状)
- 继续上一轮工作/话题 (继续/接着/继续刚才/继续分析需求…) → continue
- 回应 AI 提议: 同意/接受/确认 (需要/可以/好/接受建议/就按这个来/继续吧…) → confirm;
  同意但带修改约束 (可以不过先…/继续但先别…) → modify;
  拒绝/暂停 (不用/算了/先别…) → decline
- 指代上轮内容提问 (刚才那个方案呢/你提到的 PRD…) → reference
- 用户提出新目标/换方向 → new_goal
- 纠正自己上句/澄清 (不是这个意思，我说的是…) → correction
- 事实/状态查询: 需求/PRD/方案/计划 完成度 → question + domain=product_lifecycle;
  项目进度/状态 → question + domain=project; 任务数/任务列表 → question + domain=task;
  执行/运行/验收/发布 → 对应 domain; 观点/评价/是否合理/你觉得 → opinion (needs_tool=false)
- 无法可靠判断 → unknown (宁可不猜; needs_tool=false)

对话状态: 上轮主题 {topic}; 上轮域 {domain}; 待确认提议: {pending}

最近对话:
{history}

用户消息: {message}"""


def _govern_turn(message: str, state: dict[str, Any],
                 history: list[dict[str, Any]] | None,
                 llm_fn: Callable[[str], str] | None) -> dict[str, Any]:
    """LLM 语义判定 (relation/domain/needs_tool/topic)。失败 → 保守默认
    (unknown/general/needs_tool=false — 不主动引导诊断工具)。"""
    default = {"relation": "unknown", "domain": "general",
               "needs_tool": False, "topic": state.get("topic") or ""}
    try:
        if llm_fn is None:
            return default
        hist_text = ""
        if history:
            lines = []
            for h in history[-6:]:
                if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
                    who = "用户" if h.get("role") == "user" else "AI"
                    lines.append(f"{who}: {str(h.get('content') or '')[:220]}")
            hist_text = "\n".join(lines[-6:])
        prompt = (_GOVERN_PROMPT
                  .replace("{topic}", str(state.get("topic") or "无"))
                  .replace("{domain}", str(state.get("domain") or "无"))
                  .replace("{pending}", str(state.get("pending") or "无")[:300])
                  .replace("{history}", hist_text[-1800:])
                  .replace("{message}", str(message)[:400]))
        raw = str(llm_fn(prompt) or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return default
        parsed = json.loads(m.group(0))
        rel = str(parsed.get("relation") or "unknown")
        if rel not in _GOVERN_RELATIONS:
            rel = "unknown"
        dom = str(parsed.get("domain") or "general")
        if dom not in _GOVERN_DOMAINS:
            dom = "general"
        return {
            "relation": rel,
            "domain": dom,
            "needs_tool": bool(parsed.get("needs_tool", False)),
            "topic": str(parsed.get("topic") or state.get("topic") or "")[:80],
        }
    except Exception:  # noqa: BLE001 — governor 失败不阻断 (保守)
        return default


def _conv_state_path(root: Any) -> Path | None:
    try:
        if root is None:
            return None
        return Path(str(root)) / "conv_state.json"
    except Exception:  # noqa: BLE001
        return None


def _conv_state_load(root: Any, session_id: str) -> dict[str, Any]:
    try:
        p = _conv_state_path(root)
        if p is None or not p.is_file() or not session_id:
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        s = data.get(session_id) or {}
        return s if isinstance(s, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _conv_state_save(root: Any, session_id: str, state: dict[str, Any]) -> None:
    try:
        p = _conv_state_path(root)
        if p is None or not session_id:
            return
        data = {}
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
        data[session_id] = {k: v for k, v in state.items() if v}
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001 — state 写失败不阻断会话
        pass


def _governance_guide(relation: str, domain: str, needs_tool: bool,
                      state: dict[str, Any], message: str) -> str:
    """按 governor 语义判定注入引导 (无关键词行为; 决定 是否/哪些 域工具)。"""
    topic = str(state.get("topic") or "当前话题")
    pending = str(state.get("pending") or "")
    g: list[str] = []
    if relation in ("complaint", "correction", "clarify"):
        g.append(
            f"【对话恢复】用户正在反馈/纠正/澄清 ({relation}) — 先回到主题「{topic}」"
            f"解释或修正上一轮回答; 不要调用项目诊断工具 (project_status/project_scan/"
            f"code_scan/bash_exec) 自证; 确需事实再针对性查一个工具。")
    elif relation == "refinement":
        g.append(
            f"【产出深化】用户在评价上一轮产出并要求更具体 ({relation}) — 保持主题"
            f"「{topic}」: 先用 get_product_record 读取最近真实产出 → 找出不够具体处"
            f" → 直接深化成更详细版本 (数值/条目/方案) → 用 save_product_record "
            f"(record_id) 更新同一条 draft; 不要解释现状/复述, 不要抛选择题。")
    elif relation == "confirm":
        if pending:
            g.append(f"【确认执行】用户确认了待执行提议 → 立即执行该提议: {pending[:400]}")
        else:
            g.append("【确认执行】用户表示同意/确认 → 执行对话中刚提出的下一步 (若无明确动作, 先简短确认并列出可执行项)。")
    elif relation == "modify":
        g.append(f"【确认+修改】用户同意但带约束 → 以用户新消息为准执行 (约束优先); 先做用户指定部分。"
                 f"原提议: {pending[:300]}")
    elif relation == "decline":
        g.append("【拒绝】用户拒绝上一轮提议 → 不执行; 简短确认后询问新方向。")
    elif relation in ("continue", "reference"):
        g.append(f"【延续】用户继续/指代上文 → 保持主题「{topic}」; 结合上文作答, 不要跳题或另起炉灶。")
    elif relation == "new_goal":
        g.append("【新目标】用户提出新目标/换方向 → 以新消息为准, 放弃旧提议。"
                 "若属于新产品/新功能想法: 产品链从 Idea 开始 — 先检查项目"
                 " canonical (project_lifecycle); 无 Idea 记录 → 用 "
                 "save_product_record(kind=idea) 建立链头, 再按 想法→需求理解"
                 "→需求 推进; 不要空诊断/空查询项目状态。")
    elif relation == "opinion":
        g.append("【观点/评价】用户在征求判断 → 基于已知信息推理回答即可; 无需调用工具。")
    if relation == "question" and domain != "general":
        _tool_hint = {
            "product_lifecycle": "project_lifecycle (需求/PRD/方案完成度 — 勿用 project_tasks)",
            "project": "project_status",
            "task": "project_tasks",
            "execution": "运行/执行状态工具",
            "acceptance": "验收 (ACC) 数据",
            "release": "发布/交付 (RELEASE) 数据",
        }.get(domain, "对应域查询工具")
        g.append(f"【事实查询】域 = {domain} → 查询工具: {_tool_hint}; 用真实事实再答, "
                 f"不要用其他域统计回答本域问题。")
    if not needs_tool and relation not in ("continue", "confirm", "modify", "reference"):
        g.append("【工具克制】本轮无需调用工具即可回答/处理 — 不要为了'回答点什么'而调用"
                 "项目诊断工具; 信息不足就基于对话说明或提出最小澄清。")
    if not g:
        return ""
    head = f"【语义引导】relation={relation} · domain={domain}"
    return head + "\n" + "\n".join(g) + "\n严禁把用户短回复说成『消息不完整/只发来几个字』。"


# =====================================================================
# S47-E3: Active Work Resolver (continue/confirm/modify/reference → 工作恢复)
# =====================================================================
_ACTIVE_WORK_PROMPT = """用户正在继续一段进行中的工作。基于对话状态 + 真实 Truth 判断工作恢复上下文 (只输出 JSON):
{"active_work": "当前进行中的工作名 (如 需求分析/PRD/任务拆解; 无 → null)",
 "current_stage": "当前阶段 (需求分析: 收集→整理→确认; PRD: 草稿→评审; 无 → null)",
 "next_action": "下一步具体生产动作一句话 (无 → null)",
 "need_user_input": true|false,
 "question": "必须问用户的问题 (仅当 need_user_input=true 且存在真正阻塞性缺口; 否则 null)",
 "reason": "判断依据一句话 (引用已知信息)"}

规则 (先做后问):
- 用户说"继续/接着做/继续刚才的/把…做完整"等 → 恢复上轮工作
- **先做后问**: 基于下方 Truth — 缺什么就补什么; 能从现有信息整理的直接
  整理 (可标注待确认); 只有真正阻塞产出且无法从现有信息推断的关键决策
  才 need_user_input=true。不要因为"问一遍更稳妥"就提问。
- next_action 必须是可执行动作: 整理需求清单/建立 Requirement/推进下一
  阶段 — 不是"重新分析/重新看项目"。

对话状态: topic={topic} domain={domain} relation={relation}
上轮提议: {pending}
已锚定 Active Work: {work} | 上一轮 Next Action: {prev_next}

当前真实 Truth (该工作相关):
{truth}

最近对话:
{history}
用户消息: {message}"""


def _resolve_active_work(message: str, state: dict[str, Any],
                         history: list[dict[str, Any]] | None,
                         llm_fn: Callable[[str], str] | None,
                         truth_summary: str = "") -> dict[str, Any]:
    """LLM 恢复 Active Work (工作名/阶段/下一步/是否需问)。失败 → 空 (不阻断)。"""
    try:
        if llm_fn is None:
            return {}
        hist_text = ""
        if history:
            lines = []
            for h in history[-6:]:
                if isinstance(h, dict) and h.get("role") in ("user", "assistant"):
                    who = "用户" if h.get("role") == "user" else "AI"
                    lines.append(f"{who}: {str(h.get('content') or '')[:220]}")
            hist_text = "\n".join(lines[-6:])
        prompt = (_ACTIVE_WORK_PROMPT
                  .replace("{topic}", str(state.get("topic") or "无"))
                  .replace("{domain}", str(state.get("domain") or "无"))
                  .replace("{relation}", str(state.get("relation") or "无"))
                  .replace("{pending}", str(state.get("pending") or "无")[:300])
                  .replace("{work}", str(state.get("active_work") or "无")[:80])
                  .replace("{prev_next}", str(state.get("next_action") or "无")[:200])
                  .replace("{truth}", str(truth_summary or "无 (未读取)")[-1500:])
                  .replace("{history}", hist_text[-1300:])
                  .replace("{message}", str(message)[:400]))
        raw = str(llm_fn(prompt) or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {}
        parsed = json.loads(m.group(0))
        out = {
            "active_work": str(parsed.get("active_work") or "")[:80],
            "current_stage": str(parsed.get("current_stage") or "")[:80],
            "next_action": str(parsed.get("next_action") or "")[:300],
            "need_user_input": bool(parsed.get("need_user_input", False)),
            "question": str(parsed.get("question") or "")[:200],
        }
        if out["active_work"]:
            return out
        return {}
    except Exception:  # noqa: BLE001 — resolver 失败不阻断
        return {}


def _work_recovery_guide(msg: str, state: dict[str, Any],
                         history: list[dict[str, Any]] | None,
                         llm_fn: Callable[[str], str] | None,
                         truth_summary: str = "") -> tuple[str, dict[str, Any]]:
    """S47-E3.2: continue/confirm/modify/reference → (执行引导, 更新后 state)。

    返回 (guide_text, updated_active_work) — resolver 结构化输出由调用方
    写回 conv_state (跨轮锚定); guide 含强执行约束 (need_user_input=False
    → 禁诊断/禁 ask, 必须执行 next_action 并落 canonical)。
    """
    rel = str(state.get("relation") or "")
    if rel not in ("continue", "confirm", "modify", "reference", "refinement"):
        return "", {}
    w = _resolve_active_work(msg, state, history, llm_fn, truth_summary)
    if not w:
        return "", {}
    aw = w.get("active_work") or ""
    na = w.get("next_action") or ""
    st = w.get("current_stage") or ""
    need_q = bool(w.get("need_user_input"))
    q = w.get("question") or ""
    active_work = {
        "goal": aw,
        "current_stage": st,
        "next_action": na,
        "need_user_input": need_q,
        "question": q or "",
        "blocked": need_q,
    }
    if not need_q:
        # 执行约束: 强指令 + 禁诊断/禁 ask
        lines = [
            f"【本轮执行指令 · 最高优先级】relation={rel}",
            f"- Active Work: {aw or '未知'} (阶段: {st or '推进中'})",
            f"- 必须执行 Next Action: {na}",
            "  → 若上方 Truth 已含该工作产出 (REQ-*/DISC-* 等): 引用原记录 ID 深化/完善,"
            " 禁止为同一工作重复新建记录 (幂等);",
            "  → 若无产出记录: 用 save_product_record 新建并落 canonical;",
            "- 禁止: 调用 project_status/project_scan/code_scan/bash_exec 重新诊断项目;",
            "- 禁止: 重复询问已确认的信息 (技术栈/范围/目标); 禁止回复『需要确认/你想分析什么』这类空问;",
            "- 完成后: 简短告诉用户本轮实际完成了什么 (产出记录 ID + 当前还缺什么 + 下一步)。",
        ]
        return "\n".join(lines), active_work
    # need_user_input=True → 只问最小阻塞问题 (不执行)
    lines = [
        f"【等待关键信息】Active Work: {aw or '未知'} (阶段: {st or '推进中'})",
        f"- 仅存在一个真正阻塞产出的未知信息 → 向用户提问: {q or '请补充关键决策'}",
        "- 不要调用项目诊断工具; 不要展开多问题列表; 只问最小问题。",
    ]
    return "\n".join(lines), active_work


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

def reconcile_plan(root: str | Path, plan_id: str) -> dict[str, Any]:
    """P2-④: Plan 终态聚合 — 基于 Task SSOT (plan_id 反查 backlog), 幂等。

    Case A: 无关联 Task (空 Plan) → completed
    Case B: 全 DONE → completed
    Case C: 存在非终态 (todo/ready/in_progress/review) → 保持 executing
            (独立任务可继续 / FAILED 可 retry)
    Case D: 全终态 且含 FAILED → failed
    Case E: 全终态 含 CANCELLED (无 FAILED) → 保持 executing + aggregate_note
            (PlanStatus 无 cancelled 契约 — 不擅自扩展, finding 记录)
    幂等: 聚合结果 ≠ 当前 status 才更新; 终态 (completed/failed) 不回落。
    禁止: 不新建 Task/Run; 不读 ExecState/WebUI。
    """
    import json as _json
    from datetime import datetime, timezone as _tz
    from pathlib import Path as _P

    _spf = _P(root) / "session_plans.json"
    if not _spf.is_file():
        return {"ok": False, "reason": "no plans"}
    try:
        _sp = _json.loads(_spf.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 损坏 → 不聚合
        return {"ok": False, "reason": "plans corrupt"}
    _sid, _plan = None, None
    for _k, _v in _sp.items():
        if str(_v.get("plan_id") or "") == plan_id:
            _sid, _plan = _k, _v
            break
    if _plan is None:
        return {"ok": False, "reason": f"plan not found: {plan_id}"}
    _cur = str(_plan.get("status") or "pending")
    if _cur == "completed":
        # completed 天然终态 (Task 不可从 done 回退) → 早退
        return {"ok": True, "plan_id": plan_id, "status": _cur, "changed": False,
                "task_count": -1, "note": "terminal — no change"}
    # failed 不早退: 允许 retry 恢复 (Case F: FAILED→retry→DONE → completed)
    _proj_id = str(_plan.get("project_id") or "")
    if not _proj_id:
        return {"ok": True, "plan_id": plan_id, "status": _cur, "changed": False,
                "task_count": -1, "reason": "no project_id — cannot aggregate"}
    # 按 plan_id 过滤 backlog Task (Task SSOT)
    _tasks: list = []
    try:
        from org.management import ManagementStore

        for _cand in (_P(root) / "workspace" / "projects").iterdir():
            _pj = _cand / "project.json"
            if not _pj.is_file():
                continue
            try:
                if str(_json.loads(_pj.read_text(encoding="utf-8")).get("id") or "") != _proj_id:
                    continue
            except Exception:  # noqa: BLE001
                continue
            _tasks = [t for t in ManagementStore(_cand / "management").list_tasks()
                      if str(getattr(t, "plan_id", "") or "") == plan_id]
            break
    except Exception:  # noqa: BLE001 — store 异常 → 无法聚合
        return {"ok": True, "plan_id": plan_id, "status": _cur, "changed": False,
                "task_count": -1, "reason": "store unavailable"}
    _TERMINAL = {"done", "failed", "cancelled"}
    _note = ""
    if not _tasks:
        _new_st = "completed"  # Case A: 空 Plan
    else:
        _sts: set[str] = set()
        for _t in _tasks:
            _sv = getattr(_t, "status", "")
            _sts.add(str(getattr(_sv, "value", "") or _sv).lower())
        if _sts <= {"done"}:
            _new_st = "completed"  # Case B
        elif _sts <= _TERMINAL:
            if "failed" in _sts:
                _new_st = "failed"  # Case D
            else:
                _new_st = _cur  # Case E: cancelled 无 failed — 保持, finding
                _note = ("tasks terminal with cancelled (no failed) — "
                         "PlanStatus lacks cancelled contract (P2 finding)")
        else:
            _new_st = _cur  # Case C: 非终态 → 保持 executing
    _changed = _new_st != _cur
    if _changed:
        _plan["status"] = _new_st
        _plan["completed_at"] = (
            datetime.now(_tz.utc).isoformat()
            if _new_st in ("completed", "failed")
            else _plan.get("completed_at", ""))
        if _note:
            _plan["aggregate_note"] = _note
        _sp[_sid] = _plan
        try:
            _spf.write_text(_json.dumps(_sp, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:  # noqa: BLE001 — 写失败不阻断
            pass
    return {"ok": True, "plan_id": plan_id, "status": _new_st, "changed": _changed,
            "task_count": len(_tasks), "note": _note or ""}


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

    def update_status(self, session_id: str, status: str) -> None:
        """P2-①: Plan 生命周期状态更新 (pending → executing/completed/failed)。

        幂等消费关键: 持久化 plan status, 防重复批准重复创建任务。
        """
        try:
            d = self._load()
            p = d.get(session_id)
            if isinstance(p, dict) and p.get("plan_id"):
                p["status"] = status
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
