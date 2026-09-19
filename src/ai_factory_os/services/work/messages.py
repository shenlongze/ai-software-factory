"""services.work.messages — Agent 间消息总线（实现方案书 §4.4）。

★ 2026-09-19 新增（吸收项 9 · 吸收自 amux 的 "@ each other + 来源戳"）。

【方案书 §4.4 的权威设计（本模块照它实现, 不改措辞）】
  通信架构: Message Bus（消息总线）
    "通信方式: 间接通信（通过工作记忆 + 消息总线）
     优势: 可审计、可追溯、解耦"
  消息格式:
    { "id": "msg_123456", "from": "planner", "to": "executor",   ← to 可选, 不指定则广播
      "type": "task_assignment", "correlation_id": "task_T2",
      "payload": {...}, "priority": 5 }

【amux 补的那一条（本模块的差异点）】
  "the server logs the true sender —— provenance is a fact, not a claim"
  ⇒ **服务端记录真实发送者**: 调用方传来的 `from_` 只当作"自称",
    真正落库的是 `sent_by`（由本模块按调用上下文写入）。二者不一致时, 判定以 sent_by 为准。
  ⇒ 为什么重要: 多 agent 协作里"谁说的"决定可信度; 若只信自称, 任何 agent 都能冒充别人。

【存储（append-only, 可审计）】
  <root>/work/messages.jsonl —— 每行一条消息（jsonl: 追加不覆盖, 天然可追溯）。
  另有 read(...) 支持按 to / correlation_id / since 过滤。

【诚实边界】
  · **广播语义**: `to=""` ⇒ 广播（读取方自己过滤）——不做"推送"（无长连接, 不假装实时）。
  · 不做送达确认（delivery ack）—— 那是会话/传输层的事; 本模块只保证"写入即事实"。
  · 不重排优先级: priority 落库供读取方自行排序（谁需要谁排, 不在写入时臆断）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 消息类型（与方案书示例一致; 未知类型不拒绝 —— 开放式, 便于扩展）
KINDS = (
    "task_assignment", "task_result", "question", "answer",
    "handoff", "status", "alert",
)


def _file(root: Path | str) -> Path:
    return Path(root) / "work" / "messages.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def send(
    root: Path | str,
    *,
    from_: str,
    to: str = "",
    kind: str = "status",
    payload: dict[str, Any] | None = None,
    correlation_id: str = "",
    priority: int = 5,
    sent_by: str = "",
) -> dict[str, Any]:
    """发一条 agent 间消息（append 到 jsonl, 返回落库后的完整消息）。

    `from_`: 发送方**自称**的身份。
    `to`: 空 ⇒ 广播。
    `sent_by`: ★ **服务端记录的真实发送者**（amux 的 provenance 原则）——
        调用方（执行/调度层）把真实上下文传进来; 为空则回落为 from_（并标注 verified=False）。
    """
    msg = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "from": str(from_),
        "to": str(to),                                   # 空 = 广播
        "type": str(kind) if kind else "status",
        "correlation_id": str(correlation_id),
        "payload": payload or {},
        "priority": max(1, min(10, int(priority or 5))),  # 方案书: 1-10
        "created_at": _now(),
        # ★ 来源戳: 真实发送者（事实）vs 自称（claim）
        "sent_by": str(sent_by or from_),
        "verified": bool(sent_by) and str(sent_by) != str(from_),
    }
    p = _file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
    return msg


def read(
    root: Path | str,
    *,
    to: str = "",
    correlation_id: str = "",
    since: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """读消息（newest-last）。过滤: 收件人（含广播）/ 关联 id / 时间下限。

    `to` 给了 ⇒ 返回"发给它的 + 广播的"（广播的存在意义就是被所有人看到）。
    失败安全: 文件缺失/行损坏 ⇒ 跳过该行（不抛）。
    """
    p = _file(root)
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except Exception:  # noqa: BLE001 — 坏行跳过
                continue
            if to and str(m.get("to") or "") not in ("", to):
                continue
            if correlation_id and str(m.get("correlation_id") or "") != correlation_id:
                continue
            if since and str(m.get("created_at") or "") < since:
                continue
            out.append(m)
    except Exception:  # noqa: BLE001
        return []
    return out[-int(limit):]


def thread(root: Path | str, correlation_id: str) -> list[dict[str, Any]]:
    """某关联任务的全部消息（按时间序）—— "这条任务上谁跟谁说了什么"。"""
    return read(root, correlation_id=correlation_id, limit=1000)


def senders(root: Path | str) -> dict[str, int]:
    """统计每个**真实发送者**发了多少条（审计/看板用; 以 sent_by 为准, 不信自称）。"""
    counts: dict[str, int] = {}
    for m in read(root, limit=10000):
        who = str(m.get("sent_by") or m.get("from") or "")
        counts[who] = counts.get(who, 0) + 1
    return counts
