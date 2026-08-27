"""factory-console/session/topic_ledger.py — 会话话题账本 (TopicLedger v2, v1.1.211).

Founder 2026-08-27 (重构: 上一版碎片化/摘要烂/切换靠每轮多分类):
- 会话级上下文, 要取舍/要压缩/要分块 — 聊 B 时不带 A 细节, 回 A 时 A 的摘要+最近细节都在
- 核心 = 延续判断(二分类) + 显式切换 + running summary(增量合成), 不碎片

结构 (<data_dir>/session_topics/<session_id>.json):
  topics: [ {id, label, summary, messages[{role,content,ts}], count, last_active_at} ]
  只有 1 个 active (当前话题), 其余 frozen (只留 summary + 最近 2 条)

- append(user): LLM 判断「是否延续当前话题」→ 续: 进当前块; 切: 冻结旧块 → 新建/切回旧块
- append(assistant): 直接进当前块 (不判断, 与 user 同块)
- 滚动压缩: 块内消息 > COMPRESS_AT → 最老一批经 LLM 合成进 running summary (兜底不编造)
- build_view: 当前块(摘要+最近 N 轮) + 其他块每块一行摘要 (控制 token)
失败安全: 文件坏/LLM 挂 → 不崩 (规则兜底: 归当前块; 无块 → 建块)。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

#: 块内消息超过该数 → 触发滚动压缩
COMPRESS_AT = 12
#: 每次压缩把最老多少条合成进摘要
COMPRESS_BATCH = 6
#: 注入视图: 当前块保留最近多少轮详细
VIEW_CURRENT_TURNS = 6
#: 其他块每块摘要上限 (字)
VIEW_OTHER_SUMMARY = 60
#: 其他块最多展示数 (防爆炸)
VIEW_OTHER_MAX = 8
#: running summary 总长上限 (字)
SUMMARY_MAX = 600
#: 冻结块保留最近几条原文 (切回时给一点近况)
FROZEN_KEEP_MSGS = 2

_CONTINUE_PROMPT = """你是会话话题管理器。当前正在聊的话题:
话题: {label}
摘要: {summary}

用户最新消息: {message}

判断这条消息是否延续当前话题:
- 延续 (继续聊同一件事) → 输出 {{"continue": true}}
- 切换/开新话题 → 输出 {{"continue": false, "label": "<一句话新话题标签>", "switch_to": "<已有的旧话题id, 若是回到之前聊过的; 否则 null>"}}
只输出 JSON, 不要多余文字。"""

_SUMMARY_PROMPT = """把【旧摘要】和【新对话】合并成一段新摘要 (保留: 已定决策/结论/关键事实/待办; 丢弃: 寒暄/过程/过时细节; ≤150字)。
旧摘要: {old}
新对话:
{text}
新摘要:"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


class TopicLedger:
    """会话话题账本 v2: 延续判断 + 显式切换 + running summary。"""

    def __init__(self, session_id: str, data: dict[str, Any] | None = None):
        self.session_id = session_id
        self.topics: list[dict[str, Any]] = list((data or {}).get("topics") or [])

    # ------------------------------------------------------------ 持久化
    @classmethod
    def load(cls, data_dir: str | Path | None, session_id: str) -> "TopicLedger":
        ledger = cls(session_id)
        if not data_dir or not session_id:
            return ledger
        d = _load_json(Path(data_dir) / "session_topics" / f"{session_id}.json")
        ledger.topics = list(d.get("topics") or [])
        return ledger

    def save(self, data_dir: str | Path | None) -> None:
        if not data_dir or not self.session_id:
            return
        _save_json(Path(data_dir) / "session_topics" / f"{self.session_id}.json",
                   {"session_id": self.session_id, "topics": self.topics})

    # ------------------------------------------------------------ 块操作
    def _active(self) -> dict[str, Any] | None:
        act = [t for t in self.topics if not t.get("frozen")]
        if act:
            return act[0]
        return None

    def _find(self, tid: str) -> dict[str, Any] | None:
        return next((t for t in self.topics if t.get("id") == tid), None)

    def _new_block(self, label: str) -> dict[str, Any]:
        tid = f"t{len(self.topics) + 1}"
        return {"id": tid, "label": str(label or "")[:40] or "未命名话题",
                "summary": "", "messages": [], "count": 0,
                "last_active_at": _now_iso(), "frozen": False}

    def _freeze(self, topic: dict[str, Any], *, llm_fn: Callable[[str], str] | None) -> None:
        """切走时冻结: 压缩进 summary, 只留最近 FROZEN_KEEP_MSGS 条原文。"""
        if len(topic["messages"]) > FROZEN_KEEP_MSGS:
            old = topic["messages"][:-FROZEN_KEEP_MSGS]
            topic["messages"] = topic["messages"][-FROZEN_KEEP_MSGS:]
            topic["summary"] = self._merge_summary(topic, old, llm_fn=llm_fn)
        topic["frozen"] = True

    # ------------------------------------------------------------ 话题判断
    def _decide(self, message: str, *, llm_fn: Callable[[str], str] | None) -> dict[str, Any]:
        """延续判断 (二分类, 不碎片): 续/切(新建|切回)。无 LLM → 续 (稳)。"""
        cur = self._active()
        if cur is None:
            return {"continue": False, "label": message[:12], "switch_to": None}
        if llm_fn is not None:
            try:
                raw = str(llm_fn(_CONTINUE_PROMPT.format(
                    label=str(cur.get("label") or ""),
                    summary=str(cur.get("summary") or "（无）")[:200],
                    message=message,
                )) or "").strip()
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    d = json.loads(m.group(0))
                    if d.get("continue") is True:
                        return {"continue": True, "label": None, "switch_to": None}
                    label = str(d.get("label") or message[:12]).strip() or message[:12]
                    switch_to = str(d.get("switch_to") or "").strip() or None
                    if switch_to and self._find(switch_to):
                        return {"continue": False, "label": label, "switch_to": switch_to}
                    # switch_to 给的是旧话题但 id 不匹配 → 按 label 模糊匹配 (回到"记账App")
                    hit = self._match_by_label(label)
                    if hit:
                        return {"continue": False, "label": label, "switch_to": hit.get("id")}
                    return {"continue": False, "label": label, "switch_to": None}
            except Exception:  # noqa: BLE001 — LLM 挂 → 视为延续 (稳)
                pass
        return {"continue": True, "label": None, "switch_to": None}

    def _match_by_label(self, label: str) -> dict[str, Any] | None:
        """按标签模糊匹配冻结块 (回到之前聊过的XX)。"""
        low = (label or "").strip()
        if not low:
            return None
        for t in self.topics:
            if t.get("frozen") and (low in str(t.get("label") or "") or str(t.get("label") or "") in low):
                return t
        return None

    # ------------------------------------------------------------ 追加 + 压缩
    def append(
        self, role: str, content: str, *, llm_fn: Callable[[str], str] | None = None
    ) -> dict[str, Any]:
        """消息进账本: assistant 直接归当前块; user 做延续判断。返回 {topic_id, label, switched}。"""
        msg = str(content or "").strip()
        if not msg:
            return {"topic_id": None, "label": "", "switched": False}
        now = _now_iso()
        cur = self._active()
        switched = False
        if role != "assistant":
            decision = self._decide(msg, llm_fn=llm_fn)
            if not decision.get("continue", True):
                switched = True
                if cur is not None:
                    self._freeze(cur, llm_fn=llm_fn)
                target = self._find(decision.get("switch_to")) if decision.get("switch_to") else None
                if target is not None:
                    target["frozen"] = False
                    target["last_active_at"] = now
                    topic = target
                else:
                    topic = self._new_block(decision.get("label") or msg[:12])
                    self.topics.append(topic)
                cur = topic
        if cur is None:
            cur = self._new_block(msg[:12])
            self.topics.append(cur)
        cur["messages"].append({"role": role, "content": msg, "ts": now})
        cur["count"] = int(cur.get("count") or 0) + 1
        cur["last_active_at"] = now
        # 滚动压缩: 当前块消息过多 → 最老一批合成进 running summary
        if len(cur["messages"]) > COMPRESS_AT:
            old = cur["messages"][:COMPRESS_BATCH]
            cur["messages"] = cur["messages"][COMPRESS_BATCH:]
            cur["summary"] = self._merge_summary(cur, old, llm_fn=llm_fn)
        self._trim_topics()
        return {"topic_id": cur.get("id"), "label": cur.get("label"), "switched": switched}

    def _merge_summary(
        self, topic: dict[str, Any], msgs: list[dict[str, Any]],
        *, llm_fn: Callable[[str], str] | None,
    ) -> str:
        """旧摘要 + 新一批消息 → 合成新摘要 (LLM 增量; 兜底不编造)。"""
        old = str(topic.get("summary") or "").strip()
        text = "\n".join(
            f"{'用户' if m.get('role') == 'user' else 'AI'}: {str(m.get('content') or '')[:200]}"
            for m in msgs
        )
        if llm_fn is not None:
            try:
                raw = str(llm_fn(_SUMMARY_PROMPT.format(
                    old=old or "（无）", text=text,
                )) or "").strip()
                if raw:
                    return raw[:SUMMARY_MAX]
            except Exception:  # noqa: BLE001
                pass
        # 兜底: 旧摘要 + 新消息关键句 (取每条首行, 去重)
        picks: list[str] = [old] if old else []
        for m in msgs:
            c = str(m.get("content") or "").strip().splitlines()[0][:60]
            if c and c not in picks:
                picks.append(c)
        return "；".join(picks)[:SUMMARY_MAX]

    def _trim_topics(self) -> None:
        """块数上限: frozen 超过 VIEW_OTHER_MAX 时合并最老两块 (归档为一行摘要)。"""
        frozen = [t for t in self.topics if t.get("frozen")]
        if len(frozen) <= VIEW_OTHER_MAX:
            return
        frozen.sort(key=lambda t: str(t.get("last_active_at") or ""))
        a, b = frozen[0], frozen[1]
        a["summary"] = ("；".join(x for x in (str(a.get("summary") or ""), str(b.get("summary") or "")) if x))[:SUMMARY_MAX]
        a["label"] = f"{a.get('label')} / {b.get('label')}"[:60]
        a["messages"] = []
        a["count"] = int(a.get("count") or 0) + int(b.get("count") or 0)
        self.topics.remove(b)

    # ------------------------------------------------------------ 注入视图
    def build_view(self, *, current_turns: int = VIEW_CURRENT_TURNS, skip_last: int = 0) -> str:
        """当前块详细 (摘要+最近 N 轮) + 其他块每块一行摘要 (取舍控 token)。

        skip_last: 排除末尾 N 条 (刚 append 的当前消息, 避免与 user 消息重复)。"""
        cur = self._active()
        if cur is None:
            return ""
        lines: list[str] = []
        others = [t for t in self.topics if t is not cur]
        if others:
            lines.append("【会话话题】(当前: " + str(cur.get("label") or "") + ")")
            lines.append("- 其他话题: " + "；".join(
                f"{t.get('label')}: {str(t.get('summary') or '')[:VIEW_OTHER_SUMMARY]}"
                for t in others[-VIEW_OTHER_MAX:]
            ))
        lines.append("【当前话题 · " + str(cur.get("label") or "") + "】")
        if cur.get("summary"):
            lines.append("摘要: " + str(cur.get("summary"))[:400])
        _msgs = cur["messages"]
        if skip_last > 0:
            _msgs = _msgs[:-skip_last]
        recent = _msgs[-(current_turns * 2):]
        for m in recent:
            who = "用户" if m.get("role") == "user" else "AI"
            lines.append(f"{who}: {str(m.get('content') or '')[:300]}")
        return "\n".join(lines)
