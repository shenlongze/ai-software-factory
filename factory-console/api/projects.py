"""factory-console/api/projects.py — 项目路由函数 (GET 只读 + POST 创建/建议)。

GET /projects: 全部项目只读投影 (ProjectSummary): id/name/lifecycle
stage/status/last activity。无项目 → 空列表。

POST /projects (S10-006.5 P0 Fix — 用户第一公里): {idea, name?, project_type,
tech} → 从 idea 提取项目名 → 复用 org ProjectLifecycle.create_project
(org.project.created 事件审计, 不扩 Core 枚举) → ProjectCreatedSummary
{project_id, name, idea, status}。失败安全:
- idea 空 → ValueError (HTTP 层 400 — 空想法不创建)
- project_store 缺失/创建失败 → None (HTTP 层 503 — 存储不可用)
- project_type/tech 非法值 → ValueError (HTTP 层 400; 宽容收窄,
  不伪造 AI 技术选型 — 未识别 → 默认值)

S10-007 阶段三增强 (想法确认对话):
- POST /projects 支持显式 {name}: 用户确认的名称优先落库 (suggest 卡片确认
  后传), 规则 slug 仅兜底 (无 name → extract_project_name)。旧调用 {idea}
  无 name 仍可用 (规则兜底, 向后兼容)。
- POST /projects/suggest {idea} → IdeaSuggestion {suggested_name, slug,
  summary, questions, ai_generated}: 真实 LLM 小调用 (1 次 ~$0.001, 提议
  名称/一句话理解/1-3 澄清问题); LLM 不可用/超时/解析失败 → 诚实 fallback
  (规则提炼 + ai_generated=false, 不冒充 AI 理解)。

项目名提取 (extract_project_name): KISS 规则式, 非 LLM —
1) 去常见动词/语气前缀 (开发一个/我想开发/做一个/...)
2) 轻量中文关键词 → 英文 slug 映射 (记账→ledger, 待办→todo, ...)
   未命中关键词 → 保留中文 slug (小写化/连字符化)
3) 结果为空 → "" (调用方 fallback project_id)
诚实边界: 这是规则提取, 不是 AI 理解 — 覆盖常见 demo 场景即可。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from ..events import record_console_viewed

logger = logging.getLogger(__name__)
from ..models import (
    ConfirmProjectSummary,
    DiscoveryAnswerSummary,
    DiscoveryCompleteSummary,
    IdeaSuggestion,
    ProjectCreatedSummary,
    ProjectDraftSummary,
    ProjectSummary,
    ProjectUpdatedSummary,
)

#: API 路由标识 (事件 payload view 名, 11B FastAPI 薄层同用)
VIEW = "projects"

#: 常见动词/语气前缀 (去前缀提取核心词; 按长度降序 — 长前缀优先匹配)
_IDEA_PREFIXES: tuple[str, ...] = (
    "我想开发一个", "我想要开发", "请帮我开发", "帮我开发一个", "我想做一个",
    "开发一个", "帮我做个", "我想要一个", "我想要做", "请开发", "我想开发",
    "帮我做", "帮我建", "做一个", "实现一个", "写一个", "开发", "实现",
    "创建", "做个", "做", "写",
)

#: 轻量中文关键词 → 英文 slug (KISS 映射, 覆盖常见 demo 场景; 未命中 → 中文 slug)
_IDEA_KEYWORD_MAP: dict[str, str] = {
    "记账": "ledger",
    "待办": "todo",
    "博客": "blog",
    "商城": "shop",
    "电商": "shop",
    "聊天": "chat",
    "音乐": "music",
    "日历": "calendar",
    "笔记": "notes",
    "相册": "photos",
    "照片": "photos",
    "视频": "video",
    "天气": "weather",
    "翻译": "translate",
    "健身": "fitness",
    "理财": "finance",
    "阅读": "reader",
    "会议": "meeting",
    "问卷": "survey",
    "投票": "poll",
}

#: 尾部中文噪声词 (如 "记账 应用" / "博客 网站" — 项目名不含通用词;
#: 英文 "App" 类后缀不在其中 — 关键词命中时作为后缀保留, "记账 App" → "ledger-app")
_TRAILING_NOISE: tuple[str, ...] = ("应用软件", "应用", "软件", "程序", "系统", "工具", "网站")

#: 头部量词 (fallback 可读名提炼用: "一个记账 App" → 去 "一个" → "记账";
#: 不影响 slug 提取 — 关键词映射独立于头部量词)
_LEADING_QUANTIFIERS: tuple[str, ...] = ("一个", "一款", "一套", "个", "款")


def _trailing_english_suffix(tail: str) -> str:
    """提取尾部纯英文后缀 ("清单 App" → "app"; 无英文结尾 → "")。

    关键词映射后原文尾部保留策略: 英文后缀 (App/Web/...) 是用户对形态的
    描述, 保留进项目名; 中文尾部 (清单/网站/...) 属噪声, 丢弃。仅匹配
    末尾连续的 ASCII 字母 — "记账 App 2.0" 这类复杂尾部不保留 (KISS)。
    """
    match = re.search(r"[a-zA-Z]+$", tail.strip())
    return match.group(0) if match else ""


def extract_project_name(idea: str) -> str:
    """从 idea 提取项目名 (规则式 slug; 空/纯噪声 → "")。

    示例:
      "开发一个记账 App"     → "ledger-app" (英文 App 后缀保留)
      "开发一个待办清单 App" → "todo-app"
      "我想开发一个待办清单" → "todo" (中文尾部丢弃)
      "做一个博客网站"       → "blog"
      "帮我开发一个天气应用" → "weather"
      "hello world"          → "hello-world"
      ""                     → ""
    """
    text = str(idea or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for prefix in _IDEA_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if not text:
        return ""
    # 关键词映射优先 (中文核心词 → 英文 slug; 最长匹配)
    matched_keyword = ""
    matched_slug = ""
    for keyword, slug in _IDEA_KEYWORD_MAP.items():
        if keyword in text and len(keyword) > len(matched_keyword):
            matched_keyword = keyword
            matched_slug = slug
    if matched_keyword:
        # 映射保留原文尾部英文后缀再 slug (\"记账 App\" → \"ledger-app\");
        # 中文尾部噪声丢弃 (\"待办清单\" → \"todo\")
        tail = text[text.index(matched_keyword) + len(matched_keyword):].strip()
        suffix = _trailing_english_suffix(tail)
        combined = matched_slug + (f"-{suffix}" if suffix else "")
        return _slugify(combined)
    # 未命中 → 尾部中文噪声去除 (长度保护 — 主体不短于噪声时不误删整词)
    for noise in _TRAILING_NOISE:
        if text.lower().endswith(noise) and len(text) > len(noise):
            text = text[: -len(noise)].strip()
            break
    if not text:
        return ""
    # 未命中关键词 → 保留原文 slug (中文保留 — 诚实, 不伪造翻译)
    return _slugify(text)


def _slugify(text: str) -> str:
    """任意文本 → URL 安全 slug (小写; 非字母数字 → 连字符; 压缩; 去首尾)。"""
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def list_projects(
    service: Any,
    *,
    logger: Any = None,
) -> list[ProjectSummary]:
    """GET /projects — 项目清单 (只读聚合 + console.viewed 审计)。"""
    projects = service.list_projects()
    if logger is not None:
        record_console_viewed(
            logger, view=VIEW, count=len(projects), extra={"projects": [p.id for p in projects]}
        )
    return projects


def create_project(
    service: Any,
    idea: str,
    *,
    name: str = "",
    project_type: str = "",
    tech: str = "",
    logger: Any = None,
) -> ProjectCreatedSummary | None:
    """POST /projects — 从 idea 创建 org 项目 (S10-006.5 创建闭环)。

    S10-007 阶段三增强: name 显式传入 (用户确认的名称) 优先落库; 无 name
    → 规则提取兜底 (向后兼容旧 {idea} 调用)。idea 空 → ValueError (HTTP
    400); project_type/tech 非法 → ValueError (HTTP 400); project_store
    缺失/创建失败 → None (HTTP 503 — 存储不可用, 失败安全)。成功 →
    ProjectCreatedSummary {project_id, name, idea, status} — 事件
    org.project.created 由 ProjectLifecycle 落库 (复用, 不扩 Core 枚举),
    本层不重复审计。
    """
    cleaned = str(idea or "").strip()
    if not cleaned:
        raise ValueError("idea is required (空想法不创建)")
    explicit_name = str(name or "").strip()
    # 显式 name (用户确认) 优先; 规则 slug 仅兜底 (兼容无 name 旧调用)
    final_name = explicit_name or extract_project_name(cleaned) or ""
    summary = service.create_project(
        cleaned,
        name=final_name or None,
        project_type=project_type or None,
        tech=tech or None,
    )
    if summary is None:
        return None
    status = (
        summary.lifecycle.value
        if hasattr(summary.lifecycle, "value")
        else str(summary.lifecycle)
    )
    return ProjectCreatedSummary(
        project_id=summary.id,
        name=summary.name or final_name or summary.id,
        idea=cleaned,
        status=status,
    )


def create_draft_project(
    service: Any,
    idea: str,
    *,
    project_type: str = "",
    tech: str = "",
    logger: Any = None,
) -> ProjectDraftSummary | None:
    """POST /projects 无 name → 创建 DRAFT (S10-009 Task 4: unnamed draft)。

    idea (无显式 name) → service.create_draft_project: org Project
    (lifecycle=discovery, draft=true, name=unnamed-project-{ts}) +
    ProjectSpace 目录骨架 + idea/discovery 资产初始化。idea 空 →
    ValueError (HTTP 400 — 空想法不创建); project_store/space 缺失或创建
    失败 → None (HTTP 503 — 存储不可用, 失败安全); 成功 → ProjectDraftSummary
    {project_id, name, idea, status, lifecycle, draft} (与旧 {idea, name}
    兼容路径的 ProjectCreatedSummary 形状区分 — 前端确认创建不受影响)。
    """
    cleaned = str(idea or "").strip()
    if not cleaned:
        raise ValueError("idea is required (空想法不创建)")
    project = service.create_draft_project(
        cleaned,
        project_type=project_type or None,
        tech=tech or None,
    )
    if project is None:
        return None
    lifecycle = (
        project.lifecycle.value
        if hasattr(project.lifecycle, "value")
        else str(project.lifecycle)
    )
    return ProjectDraftSummary(
        project_id=project.id,
        name=project.name,
        idea=cleaned,
        status=lifecycle,
        lifecycle=lifecycle,
        draft=bool(project.draft),
    )


def save_discovery_answer(
    service: Any,
    project_id: str,
    question: str,
    answer: str,
    *,
    logger: Any = None,
) -> DiscoveryAnswerSummary | None:
    """POST /projects/{id}/discovery/answer — Discovery 问答持久化 (S10-009 Task 4)。

    {question, answer} → discovery/conversation.json 追加 (可多次, 顺序保留)。
    错误语义: 空 answer/question → ValueError (HTTP 400 — 空问答不记录);
    项目不存在/store 缺失 → None (HTTP 404)。成功 → DiscoveryAnswerSummary
    {project_id, question, answer, count}。
    """
    cleaned_q = str(question or "").strip()
    cleaned_a = str(answer or "").strip()
    if not cleaned_a:
        raise ValueError("answer is required (空答案不记录)")
    if not cleaned_q:
        raise ValueError("question is required (空问题不记录)")
    result = service.save_discovery_answer(project_id, cleaned_q, cleaned_a)
    if result is None:
        return None
    return DiscoveryAnswerSummary(
        project_id=result["project_id"],
        question=result["question"],
        answer=result["answer"],
        count=result["count"],
    )


def complete_discovery(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> DiscoveryCompleteSummary | None:
    """POST /projects/{id}/discovery/complete — 完成 Discovery (S10-009 Task 4)。

    生成 discovery/product-definition.md (基于 idea + 沟通记录) + lifecycle
    discovery → product_defined。错误语义: 未在 discovery 状态 → ValueError
    (HTTP 层 409 — 状态冲突); 项目不存在/store 缺失 → None (HTTP 404)。
    成功 → DiscoveryCompleteSummary {project_id, name, lifecycle,
    product_definition_ref}。
    """
    project = service.complete_discovery(project_id)
    if project is None:
        return None
    lifecycle = (
        project.lifecycle.value
        if hasattr(project.lifecycle, "value")
        else str(project.lifecycle)
    )
    return DiscoveryCompleteSummary(
        project_id=project.id,
        name=project.name,
        lifecycle=lifecycle,
        product_definition_ref="discovery/product-definition.md",
    )


def confirm_project_route(
    service: Any,
    project_id: str,
    name: str,
    *,
    logger: Any = None,
) -> ConfirmProjectSummary | None:
    """POST /projects/{id}/confirm — Confirm+Rename 事务 (S10-009 Task 5)。

    {name} → service.confirm_project 事务 (校验→快照→写 project.json→
    目录 rename [os.replace 原子]→索引/引用更新→失败回滚), 成功 →
    ConfirmProjectSummary {project_id, name, slug, lifecycle: confirmed}。
    错误语义: 空 name → ValueError (HTTP 400 — 空名字不确认); 状态未到
    确认点 / slug 冲突 → service 抛 ProjectConfirmConflictError (HTTP 层
    409 — 诚实拒绝, 事务预检失败零变更); 项目不存在/store 缺失 → None
    (HTTP 404); 事务执行失败 (已回滚) → service 抛 ConfirmTransactionError
    (HTTP 层 503 — 存储不可用, 可重试)。
    """
    cleaned = str(name or "").strip()
    if not cleaned:
        raise ValueError("name is required (空名字不确认)")
    project = service.confirm_project(project_id, cleaned)
    if project is None:
        return None
    lifecycle = (
        project.lifecycle.value
        if hasattr(project.lifecycle, "value")
        else str(project.lifecycle)
    )
    return ConfirmProjectSummary(
        project_id=project.id,
        name=project.name,
        slug=project.slug,
        lifecycle=lifecycle,
    )


# ------------------------------------------------------------------ S10-007 想法建议 (LLM + 诚实 fallback)


#: suggest LLM 提示 (小调用: 提议名称/一句话理解/1-3 澄清问题 — 纯 JSON 输出)
_SUGGEST_PROMPT = (
    "你是产品经理。用户想开发一个软件, 想法是: 「{idea}」。\n"
    "请: 1) 给项目起一个有意义的中文名 (2-6 字, 如 \"记账小助手\"); "
    "2) 生成 URL 安全 slug (小写英文+连字符, 如 ledger-app); "
    "3) 用一句话总结你的理解 (≤30 字); "
    "4) 列出 1-3 个最需要向用户澄清的问题 (每个 ≤20 字)。\n"
    "只输出纯 JSON 对象, 禁止 markdown/代码块/多余文字, 格式:\n"
    '{{"suggested_name": "...", "slug": "...", "summary": "...", '
    '"questions": ["..."]}}'
)


def _parse_suggest_json(content: str) -> dict[str, Any] | None:
    """LLM 输出 → dict (宽容解析链: 剥围栏 → 整体 loads → {..} 子串回退)。

    仍失败 → None (调用方走诚实 fallback — 解析失败不冒充 AI 理解)。
    """
    if not content:
        return None
    text = content.strip()
    candidates: list[str] = []
    # 1) 剥 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)
    # 2) {..} 子串回退 (前后文字剥离)
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _fallback_suggestion(idea: str) -> IdeaSuggestion:
    """诚实 fallback (LLM 不可用/超时/解析失败): 规则提炼, 不冒充 AI。

    suggested_name = 可读核心词提炼 ("一个记账 App" → "记账"); slug = 规则
    extract_project_name (既有映射); summary 明确标注规则模式; questions = []
    (诚实: 规则无法提问); ai_generated = false — 前端据此显示"快速模式"。
    """
    return IdeaSuggestion(
        idea=idea,
        suggested_name=_readable_name_from_idea(idea),
        slug=extract_project_name(idea),
        summary="AI 理解暂不可用 — 已按规则从想法中提炼项目名 (快速模式)",
        questions=[],
        ai_generated=False,
    )


def _readable_name_from_idea(idea: str) -> str:
    """规则提炼可读项目名 (fallback; 非 slug — 中文可读名)。

    链: 去动词前缀 → 去头部量词 (一个/一款) → 去尾部中文噪声 → 去尾部英文
    后缀 (App/Web) → 截断 20 字。空 → "" (调用方兜底)。
    """
    text = str(idea or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for prefix in _IDEA_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    for quantifier in _LEADING_QUANTIFIERS:
        if text.startswith(quantifier):
            text = text[len(quantifier):].strip()
            break
    for noise in _TRAILING_NOISE:
        if text.lower().endswith(noise) and len(text) > len(noise):
            text = text[: -len(noise)].strip()
            break
    # 尾部纯英文后缀 (App/Web/...) 去掉 — 形态词不属于名称
    text = re.sub(r"\s+[a-zA-Z]+$", "", text).strip()
    return text[:20]


def _build_suggest_provider() -> Any:
    """按配置构建真实 Provider (deepseek/openai/ollama → OpenAI 兼容端点;
    anthropic → Messages API)。key 已由 load_llm_key 进程内注入 (禁明文)。

    小调用超时: 30s (想法理解秒级任务 — 超时 → 调用方走诚实 fallback)。
    """
    from ..config import get_config
    from ..workflow_runner import _setup_sys_path, load_llm_key

    _setup_sys_path()  # 挂 factory-core/factory-org/factory-exec (幂等)
    load_llm_key()  # 解析配置 key → 注入 provider 专属环境变量 (仅检查不注入 → 干净环境读不到)
    llm = get_config().get_llm()
    if llm["provider"] == "anthropic":
        from exec.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=llm["model"], base_url=llm["base_url"], timeout=30)
    from exec.providers.openai import OpenAIProvider

    kwargs: dict[str, Any] = {
        "model": llm["model"],
        "base_url": llm["base_url"],
        "timeout": 30,
    }
    if llm["provider"] == "ollama":
        kwargs["api_key"] = "ollama"  # 本地占位 (Ollama 不校验 Authorization)
    return OpenAIProvider(**kwargs)


def _suggest_via_llm(idea: str) -> IdeaSuggestion | None:
    """真实 LLM 小调用 (1 次, ~$0.001): 提议名称/理解/澄清问题。

    失败安全 (任何异常 → None, 调用方走诚实 fallback): key 缺失 → None;
    ProviderError (HTTP/网络/无 key) → None; 空输出/解析失败/契约缺字段
    (suggested_name 空) → None。不打印/不落盘 key 明文。
    """
    from ..workflow_runner import _setup_sys_path, has_llm_key

    if not has_llm_key():
        return None  # 无 key → 诚实 fallback (不假装 AI 理解)
    try:
        _setup_sys_path()  # 先挂 factory-core/org/exec (import exec.provider 依赖)
        from exec.provider import ProviderRequest

        provider = _build_suggest_provider()
        response = provider.generate(
            ProviderRequest(task_context=_SUGGEST_PROMPT.format(idea=idea), max_tokens=2048)
        )
    except Exception as exc:  # noqa: BLE001 — 失败安全铁律: 任何 provider 异常 → fallback
        logger.warning("suggest: LLM 调用失败, 走快速模式: %s: %s", type(exc).__name__, str(exc)[:200])
        return None
    if not response.ok or not response.content:
        return None
    parsed = _parse_suggest_json(response.content)
    if parsed is None:
        return None
    suggested_name = str(parsed.get("suggested_name") or "").strip()
    if not suggested_name:
        return None  # 契约: 名称必填 (缺 → fallback, 不冒充)
    slug = str(parsed.get("slug") or "").strip() or extract_project_name(idea)
    summary = str(parsed.get("summary") or "").strip() or "已理解你的想法, 确认后即可开始开发"
    raw_questions = parsed.get("questions")
    questions: list[str] = []
    if isinstance(raw_questions, list):
        for item in raw_questions:
            text = str(item or "").strip()
            if text and len(questions) < 3:
                questions.append(text[:40])
    return IdeaSuggestion(
        idea=idea,
        suggested_name=suggested_name[:20],
        slug=_slugify(slug)[:60],
        summary=summary[:120],
        questions=questions,
        ai_generated=True,
    )


def suggest_project(
    service: Any,
    idea: str,
    *,
    logger: Any = None,
    llm_fn: Callable[[str], IdeaSuggestion | None] | None = None,
) -> IdeaSuggestion:
    """POST /projects/suggest — AI 想法理解 (S10-007 阶段三增强)。

    真实 LLM 小调用 → {suggested_name, slug, summary, questions,
    ai_generated=true}; LLM 不可用/超时/解析失败/契约缺字段 → 诚实 fallback
    (规则提炼, ai_generated=false — 前端标注"快速模式")。idea 空 →
    ValueError (HTTP 400 — 空想法不分析)。失败安全: 任何 LLM 异常都不拖垮
    API (fallback 兜底, 不 5xx — 建议是非关键路径, 用户仍可走快速模式)。

    llm_fn: 测试注入 (单元测试不依赖真实网络; 生产默认 None → 真实 LLM)。
    """
    cleaned = str(idea or "").strip()
    if not cleaned:
        raise ValueError("idea is required (空想法不分析)")
    suggestion = llm_fn(cleaned) if llm_fn is not None else _suggest_via_llm(cleaned)
    if suggestion is None:
        return _fallback_suggestion(cleaned)
    return suggestion


def update_project(
    service: Any,
    project_id: str,
    *,
    name: str | None = None,
    idea: str | None = None,
    starred: bool | None = None,
    archived: bool | None = None,
    logger: Any = None,
) -> ProjectUpdatedSummary | None:
    """PATCH /projects/{id} — 更新项目名/idea (S10-006.5 项目管理)。

    name/idea 任一非空 → org Project 对应字段落库 (service 层校验 + 保存,
    本层只投影)。错误语义: 空 name/idea / 无事可做 → ValueError (HTTP 400);
    项目不存在/store 缺失 → None (HTTP 404)。成功 → ProjectUpdatedSummary
    {project_id, name, idea, status} — idea = org Project.goal 原样回显
    (诚实, 不伪造); status 为当前生命周期 (更新不改生命周期)。
    """
    project = service.update_project(project_id, name=name, idea=idea, starred=starred, archived=archived)
    if project is None:
        return None
    status = (
        project.lifecycle.value
        if hasattr(project.lifecycle, "value")
        else str(project.lifecycle)
    )
    return ProjectUpdatedSummary(
        project_id=project.id,
        name=project.name or project.id,
        idea=project.goal or "",
        status=status,
    )


def delete_project(
    service: Any,
    project_id: str,
    *,
    logger: Any = None,
) -> bool | None:
    """DELETE /projects/{id} — 删除项目 (S10-006.5 项目管理; 运行中保护)。

    service 层组合: 运行中检查 (ProjectConflictError → HTTP 409 诚实拒绝)
    → org 删除 (org.project.deleted 事件失败安全落库) → workflow_runs/{id}
    + chat.json 清理 (失败安全)。项目不存在/store 缺失 → None (HTTP 404);
    成功 → True (HTTP 200 {deleted: true})。
    """
    return service.delete_project(project_id)


__all__ = [
    "VIEW",
    "complete_discovery",
    "confirm_project_route",
    "create_draft_project",
    "create_project",
    "delete_project",
    "extract_project_name",
    "list_projects",
    "save_discovery_answer",
    "suggest_project",
    "update_project",
]
