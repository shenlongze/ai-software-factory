"""factory-console/session/session_hooks.py — 会话级 Hooks 生命周期 (S10-127 M4).

事件模型 (参考 Claude Hooks + passbaton 5 hooks 设计, 非代码复用):
- SessionStart     会话开始 → 注入 Spine 交接 + 最近 decision/error→solution
- UserPromptSubmit 用户消息提交 → 相关记忆注入
- PreToolUse       工具调用前 → 敏感动作门 (deny+reason) + 审计
- PostToolUse      工具调用后 → 追踪/记录 (审计)
- PreCompact       上下文压缩前 → 生成结构化交接写 Spine
- SessionEnd       会话结束 → 提取 decision/error→solution/rule → project_memory

Hook = Python 函数 (ctx: dict) -> HookResult | None
HookResult = {"action": "allow"|"deny"|"inject", "reason": str, "content": str}
- deny: 短路 (调用方返回拦截错误)
- inject: 提供注入内容 (SessionStart 收集进 messages)
- allow/None: 继续

失败安全: hook 异常 → 记录日志, 不阻断会话。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

logger = logging.getLogger("factory.session_hooks")

#: 事件全集 (顺序即生命周期)
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SessionEnd",
)

#: 敏感动作工具 (M4.3 审计标记; 破坏性动作 deny 门)
SENSITIVE_TOOLS = {
    "create_task", "task_action", "execute_plan", "chain_start",
    "chain_next", "delegate_external", "external_route", "plan_development",
}
#: 危险/破坏性动作 (默认 deny — 当前无此类工具, 框架预留)
DANGEROUS_TOOLS = {"git_push", "delete", "remove", "reset"}


class SessionHooks:
    """会话级 Hook 注册表 + 分发。"""

    def __init__(self) -> None:
        self._registry: dict[str, list[Callable[[dict[str, Any]], Any]]] = {e: [] for e in EVENTS}

    # ------------------------------------------------------------ 注册
    def register(self, event: str, fn: Callable[[dict[str, Any]], Any]) -> None:
        if event not in self._registry:
            raise ValueError(f"unknown hook event: {event}")
        if fn not in self._registry[event]:
            self._registry[event].append(fn)

    def register_many(self, event: str, fns: list[Callable[[dict[str, Any]], Any]]) -> None:
        for fn in fns:
            self.register(event, fn)

    # ------------------------------------------------------------ 分发
    def fire(self, event: str, ctx: dict[str, Any]) -> list[dict[str, Any]]:
        """触发事件, 返回全部 HookResult (异常 hook 记日志不阻断)。"""
        results: list[dict[str, Any]] = []
        for fn in self._registry.get(event, []):
            try:
                r = fn(ctx)
                if isinstance(r, dict):
                    results.append(r)
            except Exception:  # noqa: BLE001 — hook 失败不拖垮会话
                logger.warning("session_hooks %s hook error: %s", event, fn)
        return results

    def denied(self, results: list[dict[str, Any]]) -> dict[str, Any] | None:
        """任一 deny → 返回该结果 (短路)。"""
        for r in results:
            if r.get("action") == "deny":
                return r
        return None

    def injected(self, results: list[dict[str, Any]]) -> str:
        """收集 inject 内容 (SessionStart/UserPromptSubmit 用)。"""
        parts = [str(r.get("content") or "") for r in results if r.get("action") == "inject"]
        return "\n".join(p for p in parts if p.strip())


# ---------------------------------------------------------------------------
# 内置 hooks (M4.2)
# ---------------------------------------------------------------------------

def _spine_ctx(ctx: dict[str, Any]):
    from .handoff import ProjectSpine

    data_dir = ctx.get("data_dir")
    project_id = ctx.get("project_id")
    if not data_dir or not project_id:
        return None
    return ProjectSpine.load(data_dir, project_id)


def session_start_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """SessionStart: 注入 Spine 交接面 + 最近 error→solution 记忆 (Closure over replay)。

    注: run_agent_native 已注入 Spine.view + 记忆块; 本 hook 补充"待续"提示 (低权威也显示),
    避免重复 (返回 None 表示无额外注入, 框架允许空)。
    """
    try:
        sp = _spine_ctx(ctx)
        if sp is None:
            return None
        rp = sp.data.get("resume_point") or {}
        hc = sp.data.get("handoff_card") or {}
        parts: list[str] = []
        if rp.get("task_id"):
            parts.append(f"- 上次断点任务: {rp.get('task_id')} ({rp.get('note') or ''})")
        if hc.get("progress"):
            parts.append(f"- 交接进度: {hc.get('progress')}")
            for ns in (hc.get("next_steps") or [])[:3]:
                parts.append(f"- 下一步: {ns}")
        if not parts:
            return None
        return {"action": "inject",
                "content": "【会话续接】(来自 SessionStart hook)\n" + "\n".join(parts)}
    except Exception:  # noqa: BLE001
        return None


def pre_compact_hook(ctx: dict[str, Any]) -> None:
    """PreCompact: 从当前上下文生成结构化交接写入 Spine (压缩前不丢进展)。

    ctx: {data_dir, project_id, session_id, question, last_answer, current_task}
    """
    try:
        sp = _spine_ctx(ctx)
        if sp is None:
            return None
        progress = str(ctx.get("last_answer") or "")[:200]
        current_task = str(ctx.get("current_task") or "")
        if progress or current_task:
            sp.set_handoff(
                progress=f"会话 {ctx.get('session_id') or ''} 进行中: {progress or '—'}",
                next_steps=[current_task] if current_task else [],
                source="agent_claim",  # AI 自述 — 低权威, 仅参考
            )
            if current_task:
                sp.set_resume_point(task_id=current_task, note="会话压缩前交接", source="agent_claim")
            sp.save(ctx.get("data_dir"))
        return None
    except Exception:  # noqa: BLE001
        return None


#: 提取规则 (保守, 无 LLM 不幻觉): (正则, kind)
_EXTRACT_RULES = [
    (r"(决定|采用|选定|选择用|决定用)[^。\n]{2,60}", "decision"),
    (r"(报错|错误|失败|异常)[^。\n]{0,30}(解决|修复|改为|换成|原因是)[^。\n]{2,60}", "error"),
    (r"(记住|以后|总是|今后|不要再|必须)[^。\n]{2,60}", "learning"),
    (r"(统一|规范|模式是|套路是|标准是)[^。\n]{2,60}", "pattern"),
]


def session_end_hook(ctx: dict[str, Any]) -> None:
    """SessionEnd: 从对话提取 decision/error→solution/learning → project_memory (5 类)。

    ctx: {data_dir, project_id, messages | transcript}
    规则提取 (保守): 命中关键词模式的句子 → 写入记忆, authority=agent_claim (AI 自述, 低权威)。
    """
    try:
        data_dir = ctx.get("data_dir")
        project_id = ctx.get("project_id")
        if not data_dir or not project_id:
            return None
        texts: list[str] = []
        msgs = ctx.get("messages") or ctx.get("transcript") or []
        for m in msgs:
            # 只从真实对话提取 (user/assistant), 排除 system 提示 (避免噪音记忆)
            if str(m.get("role") or "") not in ("user", "assistant"):
                continue
            c = str(m.get("content") or "")
            if c:
                texts.append(c)
        blob = "\n".join(texts)
        if len(blob) < 10:
            return None
        from .project_memory import MemoryStore

        mem = MemoryStore.load(data_dir, project_id)
        added = 0
        for pattern, kind in _EXTRACT_RULES:
            for mm in re.finditer(pattern, blob):
                snippet = mm.group(0).strip().replace("\n", " ")[:180]
                before = len(mem.entries)
                mem.add(snippet, source="session", kind=kind, authority="agent_claim")
                if len(mem.entries) > before:
                    added += 1
                if added >= 8:
                    break
            if added >= 8:
                break
        mem.save(data_dir)
        return None
    except Exception:  # noqa: BLE001
        return None


def pre_tool_use_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """PreToolUse: 危险/破坏性动作 → deny; 敏感动作 → 仅审计标记 (不误伤现有审批流程)。

    ctx: {tool_id, args, ...}
    """
    tool_id = str(ctx.get("tool_id") or "")
    if tool_id in DANGEROUS_TOOLS:
        return {"action": "deny", "reason": f"工具 {tool_id} 属于破坏性动作, 已默认拦截 (S10-127 M4.3)"}
    # 敏感动作: 由现有审批逻辑处理, 这里仅记录审计 (dispatch 调方写 session_audit)
    return None


def build_default_hooks() -> SessionHooks:
    """默认注册表 (M4.2 内置 hooks + M4.3 动作门)。"""
    h = SessionHooks()
    h.register("SessionStart", session_start_hook)
    h.register("PreCompact", pre_compact_hook)
    h.register("SessionEnd", session_end_hook)
    h.register("PreToolUse", pre_tool_use_hook)
    return h
