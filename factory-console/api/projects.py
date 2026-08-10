"""factory-console/api/projects.py — 项目路由函数 (GET 只读 + POST 创建)。

GET /projects: 全部项目只读投影 (ProjectSummary): id/name/lifecycle
stage/status/last activity。无项目 → 空列表。

POST /projects (S10-006.5 P0 Fix — 用户第一公里): {idea, project_type,
tech} → 从 idea 提取项目名 → 复用 org ProjectLifecycle.create_project
(org.project.created 事件审计, 不扩 Core 枚举) → ProjectCreatedSummary
{project_id, name, idea, status}。失败安全:
- idea 空 → ValueError (HTTP 层 400 — 空想法不创建)
- project_store 缺失/创建失败 → None (HTTP 层 503 — 存储不可用)
- project_type/tech 非法值 → ValueError (HTTP 层 400; 宽容收窄,
  不伪造 AI 技术选型 — 未识别 → 默认值)

项目名提取 (extract_project_name): KISS 规则式, 非 LLM —
1) 去常见动词/语气前缀 (开发一个/我想开发/做一个/...)
2) 轻量中文关键词 → 英文 slug 映射 (记账→ledger, 待办→todo, ...)
   未命中关键词 → 保留中文 slug (小写化/连字符化)
3) 结果为空 → "" (调用方 fallback project_id)
诚实边界: 这是规则提取, 不是 AI 理解 — 覆盖常见 demo 场景即可。
"""

from __future__ import annotations

import re
from typing import Any

from ..events import record_console_viewed
from ..models import ProjectCreatedSummary, ProjectSummary

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
    project_type: str = "",
    tech: str = "",
    logger: Any = None,
) -> ProjectCreatedSummary | None:
    """POST /projects — 从 idea 创建 org 项目 (S10-006.5 创建闭环)。

    idea 空 → ValueError (HTTP 400); project_type/tech 非法 → ValueError
    (HTTP 400); project_store 缺失/创建失败 → None (HTTP 503 — 存储不可
    用, 失败安全)。成功 → ProjectCreatedSummary {project_id, name, idea,
    status} — 事件 org.project.created 由 ProjectLifecycle 落库 (复用,
    不扩 Core 枚举), 本层不重复审计。
    """
    cleaned = str(idea or "").strip()
    if not cleaned:
        raise ValueError("idea is required (空想法不创建)")
    name = extract_project_name(cleaned) or ""
    summary = service.create_project(
        cleaned,
        name=name or None,
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
        name=summary.name or name or summary.id,
        idea=cleaned,
        status=status,
    )


__all__ = ["VIEW", "create_project", "extract_project_name", "list_projects"]
