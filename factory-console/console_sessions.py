"""factory-console/console_sessions.py — Web 会话栏存储与回复 (K-7e)。

会话 (session): scope ∈ {company, project}; project 会话带 project_id。
消息 (message): role ∈ {user, assistant}; append-only, 按会话隔离。
存储: <root>/console_sessions.json (与 chat.json 平级; 线程安全 RLock;
失败安全: 损坏 → 空, 不可写 → 读正常写静默跳过)。

回复: 复用 session.reasoning.ReasoningProvider 装配链 (真实 LLM);
LLM 不可用/调用失败 → 诚实引导 (不假装 AI 回答, 与 REPL ChatService 同纪律)。
作用域感知: company 会话 → 全局产品经理 persona; project 会话 →
注入项目事实卡 (调用方传 facts, 本模块不查项目 — 单一职责)。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 合法作用域
VALID_SCOPES = ("company", "project")

#: 单会话消息上限 (防无限增长; 超出丢最旧 — KISS 滚动窗口, 同 chat_store)
MAX_MESSAGES_PER_SESSION = 200

#: 单会话上限 (防无限增长)
MAX_SESSIONS = 500

#: 回复字数上限 (默认)
DEFAULT_MAX_CHARS = 1200

#: 系统提示 (公司级 — 全局产品经理/技术负责人 persona, Web 工作台感知)
_COMPANY_PROMPT = """你是 AI Factory OS 的 AI 产品经理和技术负责人，运行在 Web 工作台。

当前视图: 公司 / 全局（用户当前不在某个具体项目里，或在用公司级会话）。

职责:
1. 理解用户想法, 帮助定义产品; 引导创建项目 (输入想法即可创建)
2. 发现需求缺口, 协助技术实现
3. **我能真实执行的操作** (用户要求时直接做, 别只说"建议"):
   - 创建/操作任务: "给 X 加功能" 建任务; "把 XX 标记完成/改成 P0/归档" 真实改
   - 记录想法: "记录个想法 XX" 建想法模块
   - 扫描分析: "扫描项目/分析 P0 任务" 返回真实任务/进度/判断/风险/建议
   - 查文档/产出物/监控/设置/仓库: 直接给真实数据 (含 git remote/领先提交)
   - 项目操作: 收藏/改名/删除; "推送代码" 真实 git push (敏感操作先确认)
   - 开发支持: 拆解需求 → 建任务 → 推进执行 (执行引擎真实产出代码/产物落盘),
     分析代码影响/检索代码与文档; 不是只能给片段 — 能驱动开发闭环真实落地
4. 诚实边界: 只描述真实能力; 事实卡没有的如实说"待查证", 不编造。
5. **用户问当前有哪些项目 / 重点项目 / 用什么模型时, 直接从事实卡回答**,
   不要只说"请到某页面查看"。
6. **实事求是铁律**: 只陈述事实卡/真实查询里的数据; 不编造分类/进度/结论。

当前空间事实:
{facts}

回答简洁、准确、友好, 用中文。当前作用域: 公司 (全局)。
"""

#: 系统提示 (项目级 — 带项目事实卡, Web 工作台感知)
_PROJECT_PROMPT = """你是 AI Factory OS 中负责当前项目的 AI 助手，运行在 Web 工作台。

当前项目事实卡:
{facts}

职责:
1. 针对当前项目回答 (改需求/看状态/分析影响); 用户问"当前是哪个项目"时
   直接告诉项目名 (来自事实卡), 不要反问
2. **我能真实执行**: 创建/操作任务 ("标记完成/开始/改 P0/归档"), 记录想法,
   扫描项目/按优先级查任务/查文档·产出物·监控·设置·仓库, 收藏/改名/推送
   (敏感操作先确认)。开发支持 = 拆解需求 → 建任务 → 推进执行 (引擎真实写代码/
   产物落盘), 分析代码影响与检索; 不是"只能给代码片段" — 能驱动开发闭环落地。
3. 需要真实数据时用下面事实卡直接回答 (扫描/任务统计/文档/仓库都是实时查的);
   查不到的如实说"待查证", 不编造项目状态。
4. 诚实边界: 只描述真实支持的能力; 不确定 → 明说"待查证"。

回答简洁、准确、友好, 用中文。当前作用域: 项目。
"""

#: 无 LLM 时的诚实引导 (不假装回答)
_FALLBACK = (
    "（AI 回复通道暂不可用 — 你的消息已记录。\n"
    "原因: LLM Provider 未配置或调用失败。\n"
    "建议: 打开 设置 → LLM / 模型 检查 Provider 与 Key；"
    "或查看项目页/开发者控制台的真实数据。）"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def llm_raw(prompt: str) -> str | None:
    """真实 LLM 原始输出 (供意图解析等结构化调用); 不可用/失败 → None。"""
    try:
        from .session.reasoning import ReasoningProvider

        provider = ReasoningProvider()
        llm_fn = provider._default_llm_fn()  # noqa: SLF001 — 同包复用装配链
        text = llm_fn(prompt, "chat")
        text = str(text or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 — LLM 挂 → None (调用方 fallback)
        return None


def _llm_answer(prompt: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str | None:
    """真实 LLM 回答 (截断); 不可用/失败 → None (调用方落诚实引导)。"""
    text = llm_raw(prompt)
    if not text:
        return None
    return text[:max_chars]


class SessionStore:
    """会话 + 消息存储 (append-only JSON; 线程安全 RLock; 失败安全)。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {"sessions": {}, "messages": {}}
        self._load()

    # ------------------------------------------------------------ 持久化
    def _load(self) -> None:
        try:
            if self._path.is_file():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    sessions = raw.get("sessions")
                    messages = raw.get("messages")
                    if isinstance(sessions, dict):
                        self._data["sessions"] = {
                            str(k): v for k, v in sessions.items() if isinstance(v, dict)
                        }
                    if isinstance(messages, dict):
                        self._data["messages"] = {
                            str(k): list(v) for k, v in messages.items() if isinstance(v, list)
                        }
        except (OSError, ValueError):
            self._data = {"sessions": {}, "messages": {}}

    def _save(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return True
        except OSError:
            return False  # 不可写 → 静默 (会话记录尽力而为)

    # ------------------------------------------------------------ 会话
    def list_sessions(
        self,
        *,
        scope: str | None = None,
        project_id: str | None = None,
        feature_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """按作用域过滤; 按 updated_at 倒序 (最近活跃在前)。"""
        with self._lock:
            out = []
            for s in self._data["sessions"].values():
                if scope is not None and s.get("scope") != scope:
                    continue
                if project_id is not None and s.get("project_id") != project_id:
                    continue
                if feature_id is not None and s.get("feature_id") != feature_id:
                    continue
                if task_id is not None and s.get("task_id") != task_id:
                    continue
                out.append(dict(s))
            out.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
            return out

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            s = self._data["sessions"].get(session_id)
            return dict(s) if s else None

    def create_session(
        self,
        *,
        scope: str,
        project_id: str | None = None,
        title: str | None = None,
        feature_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        if scope not in VALID_SCOPES:
            raise ValueError(f"非法作用域: {scope} (company|project)")
        if scope == "project" and not project_id:
            raise ValueError("项目级会话必须带 project_id")
        now = _now_iso()
        sid = _new_id("sess")
        session = {
            "id": sid,
            "scope": scope,
            "project_id": project_id if scope == "project" else None,
            "feature_id": feature_id if scope == "project" else None,
            "task_id": task_id if scope == "project" else None,
            "title": (title or "").strip() or "新会话",
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "summary": None,
        }
        with self._lock:
            sessions = self._data["sessions"]
            if len(sessions) >= MAX_SESSIONS:
                # 丢最旧 inactive (active 保留 — 防误删进行中)
                oldest = sorted(
                    (s for s in sessions.values() if s.get("status") != "active"),
                    key=lambda s: s.get("updated_at") or "",
                )
                if oldest:
                    del sessions[oldest[0]["id"]]
                    self._data["messages"].pop(oldest[0]["id"], None)
            sessions[sid] = session
            self._save()
        return dict(session)

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        summary: str | None = None,
        feature_id: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            s = self._data["sessions"].get(session_id)
            if s is None:
                return None
            if title is not None:
                s["title"] = title.strip() or s["title"]
            if status is not None:
                if status not in ("active", "archived"):
                    raise ValueError("非法状态: active|archived")
                s["status"] = status
            if summary is not None:
                s["summary"] = summary
            if feature_id is not None:
                s["feature_id"] = feature_id or None
            if task_id is not None:
                s["task_id"] = task_id or None
            s["updated_at"] = _now_iso()
            self._save()
            return dict(s)

    def touch(self, session_id: str) -> None:
        with self._lock:
            s = self._data["sessions"].get(session_id)
            if s is not None:
                s["updated_at"] = _now_iso()

    # ------------------------------------------------------------ 消息
    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._data["messages"].get(session_id, []))

    def append_message(
        self, session_id: str, role: str, content: str
    ) -> dict[str, Any] | None:
        if role not in ("user", "assistant"):
            raise ValueError("非法角色: user|assistant")
        with self._lock:
            s = self._data["sessions"].get(session_id)
            if s is None:
                return None
            record = {
                "id": _new_id("msg"),
                "session_id": session_id,
                "role": role,
                "content": content,
                "created_at": _now_iso(),
            }
            messages = self._data["messages"].setdefault(session_id, [])
            messages.append(record)
            if len(messages) > MAX_MESSAGES_PER_SESSION:
                del messages[: len(messages) - MAX_MESSAGES_PER_SESSION]
            s["updated_at"] = record["created_at"]
            # 首条用户消息 → 自动标题 (前 24 字)
            if s.get("title") in (None, "", "新会话") and role == "user":
                s["title"] = content.strip()[:24] or "新会话"
            self._save()
            return dict(record)

    def message_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._data["messages"].get(session_id, []))


def send_message(
    store: SessionStore,
    session_id: str,
    content: str,
    *,
    facts: str = "",
    reply_extra: str = "",
    llm_fn: Callable[[str], str | None] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """追加用户消息 + 生成 assistant 回复 (真实 LLM / 诚实降级)。

    返回 {user, assistant}; 会话不存在 → raise ValueError (404 语义)。
    llm_fn 可注入 (测试确定性); None → 真实 LLM (不可用 → 诚实引导)。
    """
    text = str(content or "").strip()
    if not text:
        raise ValueError("消息为空 (不发送)")
    session = store.get_session(session_id)
    if session is None:
        raise ValueError("会话不存在")
    user_msg = store.append_message(session_id, "user", text)
    if user_msg is None:
        raise ValueError("会话不存在")

    prompt = _build_prompt(session, text, facts=facts, reply_extra=reply_extra)
    reply: str | None = None
    if llm_fn is not None:
        try:
            reply = llm_fn(prompt)
        except Exception:  # noqa: BLE001 — 注入函数失败 → 诚实降级
            reply = None
    else:
        reply = _llm_answer(prompt, max_chars=max_chars)
    if not reply:
        reply = _FALLBACK
    assistant_msg = store.append_message(session_id, "assistant", reply)
    return {
        "user": user_msg,
        "assistant": assistant_msg,
        "session": store.get_session(session_id),
    }


def _build_prompt(
    session: dict[str, Any], question: str, *, facts: str = "", reply_extra: str = ""
) -> str:
    """按作用域组装 prompt (真实事实卡 + 可选标准输出指令)。"""
    fact_block = (facts or "").strip() or (
        "项目信息暂缺 (不编造)" if session.get("scope") == "project" else "（暂无）"
    )
    if session.get("scope") == "project":
        system = _PROJECT_PROMPT.format(facts=fact_block)
    else:
        system = _COMPANY_PROMPT.format(facts=fact_block)
    if reply_extra:
        system = f"{system}\n{reply_extra}"
    return f"{system}\n\n用户: {question}"


__all__ = [
    "SessionStore",
    "send_message",
    "VALID_SCOPES",
    "MAX_MESSAGES_PER_SESSION",
    "DEFAULT_MAX_CHARS",
]
