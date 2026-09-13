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
from pathlib import Path
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
#: 权限模式 (P1.5): plan=只读(写工具deny) / acceptEdits=允许编辑 / auto=规则分类审计 / normal=默认
PERMISSION_MODES = ("normal", "plan", "acceptEdits", "auto")


def load_permission_mode(data_dir: str | None) -> str:
    """从 <data_dir>/session_permissions.json 读权限模式 (缺省 normal)。"""
    if not data_dir:
        return "normal"
    try:
        import json as _json
        from pathlib import Path as _P

        d = _json.loads((_P(data_dir) / "session_permissions.json").read_text(encoding="utf-8"))
        m = str(d.get("permission_mode") or "")
        if m in PERMISSION_MODES:
            return m
    except Exception:  # noqa: BLE001 — 缺/坏 → normal
        pass
    return "normal"


#: T7 治理规则文件名 (数据目录下)
GOVERNANCE_RULES_FILE = "governance_rules.json"


def load_governance_rules(data_dir: str | None) -> list[dict[str, Any]]:
    """T7: 从 <data_dir>/governance_rules.json 加载治理规则 (红线可配置)。

    每条规则:
      {"tool": "bash_exec", "arg_pattern": "rm -rf|DROP TABLE", "action": "deny", "reason": "..."}
      tool: 工具名 (支持 * 通配) | arg_pattern: 参数正则 (可选) | action: deny|require_approval
    匹配顺序: 第一条命中即生效。缺文件 → 空规则 (仅内置硬编码红线)。
    """
    if not data_dir:
        return []
    try:
        import json as _json
        from pathlib import Path as _P

        p = _P(data_dir) / GOVERNANCE_RULES_FILE
        if not p.exists():
            return []
        d = _json.loads(p.read_text(encoding="utf-8"))
        rules = d.get("rules") or []
        valid = []
        for r in rules:
            if str(r.get("tool") or ""):
                valid.append({
                    "tool": str(r.get("tool")),
                    "arg_pattern": str(r.get("arg_pattern") or ""),
                    "action": str(r.get("action") or "deny"),
                    "reason": str(r.get("reason") or f"治理规则拦截 {r.get('tool')}"),
                })
        return valid
    except Exception:  # noqa: BLE001 — 缺/坏 → 空规则, 不阻断
        return []


def _rule_match(rule: dict[str, Any], tool_id: str, args: Any) -> bool:
    """T7: 规则是否命中 — 工具名匹配 (* 通配) + 参数正则匹配 (可选)。"""
    tool_pat = str(rule.get("tool") or "")
    if tool_pat == "*":
        pass
    elif tool_pat.endswith("*"):
        if not tool_id.startswith(tool_pat[:-1]):
            return False
    elif tool_id != tool_pat:
        return False
    arg_pat = str(rule.get("arg_pattern") or "")
    if arg_pat:
        try:
            if not re.search(arg_pat, str(args or "")):
                return False
        except re.error:
            return False
    return True


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
    (r"(报错|错误|失败|异常|遇到|碰到)[^。\n]{0,30}(解决|修复|改为|换成|原因是|办法)[^。\n]{2,60}", "error"),
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
                # T11 (v1.1.293): 完整句提取 — 回溯到句首, 不从中途截 (旧版产出'以后者为准)'残句)
                start = mm.start()
                sent_start = max(blob.rfind("\n", 0, start), blob.rfind("。", 0, start), blob.rfind(";", 0, start)) + 1
                end = mm.end()
                sent_end_m = re.search(r"[。;\n]", blob[end:])
                sent_end = end + (sent_end_m.end() if sent_end_m else min(len(blob) - end, 60))
                snippet = blob[sent_start:sent_end].strip().replace("\n", " ")[:180]
                # 质量过滤: 过短 / 残句结尾 / 无主语残片
                if len(snippet) < 8:
                    continue
                if snippet.endswith((")", "）", ":", "：", "，", ",")):
                    continue
                before = len(mem.entries)
                mem.add(snippet, source="session", kind=kind, authority="agent_claim")
                if len(mem.entries) > before:
                    added += 1
                if added >= 8:
                    break
            if added >= 8:
                break
        mem.save(data_dir)
        # T10 (v1.1.292): SessionEnd 也写 Spine 交接卡 — 会话结束固化进展,
        # 新会话"继续做 XX"有据可依 (PreCompact 只在压缩时写, 普通结束会漏)
        try:
            from .handoff import ProjectSpine

            sp = ProjectSpine.load(data_dir, project_id)
            last_user = ""
            last_assistant = ""
            for m in msgs:
                if str(m.get("role") or "") == "user":
                    last_user = str(m.get("content") or "")[:150]
                elif str(m.get("role") or "") == "assistant":
                    last_assistant = str(m.get("content") or "")[:200]
            if last_user or last_assistant:
                sp.set_handoff(
                    progress=f"会话 {ctx.get('session_id') or ''} 结束: {last_assistant or last_user}",
                    next_steps=[last_user] if last_user else [],
                    source="agent_claim",
                )
                sp.save(data_dir)
        except Exception:  # noqa: BLE001 — Spine 失败不阻断
            pass
        return None
    except Exception:  # noqa: BLE001
        return None


def pre_tool_use_hook(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """PreToolUse 动作门 (S10-127 M4.3 + P1.5 权限模式 + T7 治理规则):
    - T7 治理规则 (governance_rules.json) 优先: 命中 deny → 拦截; require_approval → 转审批
    - 危险/破坏性动作 → 永远 deny
    - plan 模式 (只读) → 写操作 (SENSITIVE_TOOLS) deny
    - auto 模式 → 敏感动作标记 audit (放行, 由审计/审批层处理)
    - acceptEdits/normal → 放行 (现有审批流程处理)

    ctx: {tool_id, args, permission_mode?, data_dir, ...}
    """
    tool_id = str(ctx.get("tool_id") or "")
    args = ctx.get("args")
    # T7: 治理规则优先 (可配置红线)
    for rule in load_governance_rules(ctx.get("data_dir")):
        if not _rule_match(rule, tool_id, args):
            continue
        action = str(rule.get("action") or "deny")
        reason = str(rule.get("reason") or f"治理规则拦截 {tool_id}")
        if action == "require_approval":
            return {"action": "allow", "require_approval": True, "reason": reason}
        return {"action": "deny", "reason": reason}
    if tool_id in DANGEROUS_TOOLS:
        return {"action": "deny", "reason": f"工具 {tool_id} 属于破坏性动作, 已默认拦截 (S10-127 M4.3)"}
    mode = str(ctx.get("permission_mode") or load_permission_mode(ctx.get("data_dir")))
    if mode not in PERMISSION_MODES:
        mode = "normal"
    if mode == "plan" and tool_id in SENSITIVE_TOOLS:
        return {"action": "deny",
                "reason": f"plan 模式(只读): 写操作 {tool_id} 已拦截; 切 acceptEdits/auto 或明确授权后再执行 (S10-127 P1.5)"}
    # 敏感动作: 由现有审批逻辑处理; auto 模式记录审计 (dispatch 调方写 session_audit)
    return None


def build_default_hooks() -> SessionHooks:
    """默认注册表 (M4.2 内置 hooks + M4.3 动作门 + T6 工具审计)。"""
    h = SessionHooks()
    h.register("SessionStart", session_start_hook)
    h.register("PreCompact", pre_compact_hook)
    h.register("SessionEnd", session_end_hook)
    h.register("PreToolUse", pre_tool_use_hook)
    # T6 (v1.1.281): 工具调用全量审计 — PostToolUse 写 audit_events.json (TOOL_CALL)
    h.register("PostToolUse", post_tool_use_hook)
    return h


def post_tool_use_hook(ctx: dict[str, Any]) -> None:
    """T6+T12: PostToolUse → 工具调用全量审计, 双写:
    1) audit_events.json (AuditStore TOOL_CALL, T6)
    2) events 表 (EventLogger.tool_call, T12 统一事件库 — factory.db)
    失败安全: 任一写失败不阻断会话。
    """
    data_dir = ctx.get("data_dir")
    tool_id = str(ctx.get("tool_id") or "")
    if not data_dir or not tool_id:
        return None
    try:
        from ..audit.audit_event import AuditEvent
        from ..audit.audit_store import AuditStore

        # T6: audit_events.json
        store = AuditStore(workspace=None, file=str(Path(data_dir) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            "TOOL_CALL",
            trace_id=str(ctx.get("session_id") or ""),
            project_id=str(ctx.get("project_id") or ""),
            agent_id="session-agent",
            actor_type="agent",
            actor_id="session-llm",
            action=tool_id,
            source="session_hooks",
            decision="allow",
            decision_reason="tool executed",
            evidence=[
                {
                    "args": str(ctx.get("args") or "")[:500],
                    "ok": bool(ctx.get("result_ok")),
                    "duration_ms": int(ctx.get("duration_ms") or 0),
                }
            ],
            result={"ok": bool(ctx.get("result_ok"))},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001 — 审计失败不阻断会话
        logger.warning("post_tool_use_hook audit failed: %s", exc_info=True)
    # T12: 统一事件库 — events 表 (factory.db; 失败安全)
    try:
        from events.logger import EventLogger
        from events.store import EventStore

        db = Path(data_dir) / "factory.db"
        if db.exists():
            logger_ = EventLogger(EventStore(db))
            logger_.tool_call(
                task_id=str(ctx.get("session_id") or ""),
                tool=tool_id,
                arg_summary=str(ctx.get("args") or "")[:200],
                result_summary=("OK" if ctx.get("result_ok") else str(ctx.get("result_ok")))[:200],
                duration_s=float(int(ctx.get("duration_ms") or 0)) / 1000.0,
                project_id=str(ctx.get("project_id") or ""),
                agent_id="session-agent",
                source="session_hooks",
            )
    except Exception:  # noqa: BLE001 — 事件库不可用不阻断
        logger.warning("post_tool_use_hook events failed: %s", exc_info=True)
    return None
