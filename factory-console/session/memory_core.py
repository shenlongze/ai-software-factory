"""factory-console/session/memory_core.py — Core Memory (W4, v1.1.250).

抄 Letta core memory: 两块"永远在上下文"的可编辑文本 — persona(agent身份, 固定)
+ human(用户画像/当前上下文, 可自编辑, 有上限)。模型可用 memory_update 工具自编辑
human 块 (self-editing memory); 会话结束钩子提取关键信息更新 human。

结构 (<root>/memory_core.json):
{
  "persona": "你是...",            # 固定身份 (首次写入, 之后只读)
  "human": "用户偏好/当前项目/最近话题...",  # 动态, ≤HUMAN_MAX_CHARS
  "updated_at"
}

- load(): 读 (缺失 → 默认 persona + 空 human)
- ensure(root): 缺失 → 写默认
- update_human(root, text, *, append=False): 更新 human (上限截断, 保头尾)
- render(root, max_chars): 渲染注入 system 的文本 (human 截断)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: human 块上限 (Letta core_memory 每块 ~2000 chars)
HUMAN_MAX_CHARS = 1500
#: 注入 system 时 human 显示上限 (更小, 省 token)
RENDER_HUMAN_MAX = 800

DEFAULT_PERSONA = (
    "你是 AI Factory 的会话 Agent (AI 助手): 能查项目真实数据、管理任务、驱动开发执行链、"
    "网络搜索、沙箱执行命令; 诚实不编造, 数据要工具证据; 用中文自然回答。"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def core_file(root: str | Path) -> Path:
    return Path(root) / "memory_core.json"


def load(root: str | Path | None) -> dict[str, Any]:
    """读 core memory; 缺失 → 默认 (persona + 空 human)。"""
    if not root:
        return {"persona": DEFAULT_PERSONA, "human": "", "updated_at": ""}
    try:
        d = json.loads(core_file(root).read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("persona"):
            return {"persona": str(d["persona"]), "human": str(d.get("human") or ""),
                    "updated_at": str(d.get("updated_at") or "")}
    except Exception:  # noqa: BLE001 — 坏文件 → 默认
        pass
    return {"persona": DEFAULT_PERSONA, "human": "", "updated_at": ""}


def save(root: str | Path | None, data: dict[str, Any]) -> None:
    if not root:
        return
    try:
        p = core_file(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = _now_iso()
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def update_human(root: str | Path | None, text: str, *, append: bool = False) -> dict[str, Any]:
    """更新 human 块 (self-editing)。append=True → 追加到末尾; 超上限截断 (保头尾)。"""
    d = load(root)
    new = str(text or "").strip()
    human = d.get("human") or ""
    if append and human:
        human = human.rstrip() + "\n" + new
    else:
        human = new
    if len(human) > HUMAN_MAX_CHARS:
        # 保头尾: 前面 2/3 + 分隔 + 后面 (含分隔符长度)
        _sep = "\n…(截断)…\n"
        head = human[: int(HUMAN_MAX_CHARS * 0.7)]
        tail = human[-(HUMAN_MAX_CHARS - len(head) - len(_sep)):]
        human = head + _sep + tail
    d["human"] = human
    save(root, d)
    return d


def render(root: str | Path | None, max_chars: int = RENDER_HUMAN_MAX) -> str:
    """渲染注入 system 的 core 文本: persona + human(截断)。空 human → 只 persona。"""
    d = load(root)
    lines = [f"【Core Memory · Persona】{d.get('persona') or DEFAULT_PERSONA}"]
    human = (d.get("human") or "").strip()
    if human:
        if len(human) > max_chars:
            human = human[:max_chars] + "\n…(human 块截断, 可用 memory_update 查看/更新)"
        lines.append(f"【Core Memory · Human】{human}")
    return "\n".join(lines)


def extract_and_update(root: str | Path | None, session: dict[str, Any] | None,
                       question: str, answer: str) -> None:
    """会话收尾提取: 更新 human 块 (当前项目/最近话题/任务状态)。轻量, 不调 LLM。"""
    if not root:
        return
    try:
        facts: list[str] = []
        if session and session.get("project_id"):
            facts.append(f"当前项目: {session.get('project_id')}")
        if session and session.get("title"):
            facts.append(f"最近会话: {str(session.get('title'))[:50]}")
        q = str(question or "").strip()[:80]
        if q:
            facts.append(f"用户最近问题: {q}")
        if facts:
            update_human(root, " | ".join(facts), append=True)
    except Exception:  # noqa: BLE001 — 提取失败不阻断
        pass


__all__ = ["load", "save", "update_human", "render", "extract_and_update",
           "core_file", "DEFAULT_PERSONA", "HUMAN_MAX_CHARS"]
