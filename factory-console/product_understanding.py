"""factory-console/product_understanding.py — Product Understanding SSOT (S49/Phase 5)。

Conversation-scoped 产品认知事实层 (目标架构本体, 第四阶段 §29 裁决 conversation_os
→ RETIRE 的替代域; legacy conversation_os/session 本阶段不动)。

领域模型 (冻结):
```
Conversation (conv-*)
 ├── title / status (OPEN | ARCHIVED)
 ├── messages: [{id, role, content, created_at}]   (append-only, 供 source_message_id)
 └── understanding
      ├── version: int  (单调递增 — PRD provenance 锚点)
      └── facts: {fact_id: Fact}
           Fact: {id, conversation_id, type, content, status,
                  source_message_id, confidence, provenance,
                  supersedes: [fact_id], superseded_by: "",
                  created_at, updated_at}
           type ∈ IDEA | REQUIREMENT | CONSTRAINT | DECISION | QUESTION | FUTURE_IDEA
           status ∈ PROPOSED | CONFIRMED | SUPERSEDED | REJECTED
```

设计依据:
- S49 spec §1/§2/§4/§11/§12: Product Understanding = Conversation/Product Domain 的事实
  SSOT; Conversation ≠ Session; fact 必须带 conversation_id/source_message_id/
  confidence/provenance/status/timestamps; 修改是 supersession 不是新增重复。
- 复用本仓库 JSON store 惯例 (product_truth.py / chat_store.py): RLock +
  tmp + os.replace 原子写; 损坏读 → 失败安全。
- product_truth.py (P1 六层) 是**正式资产层** (REQ/PRD/PLAN, approved gate);
  本模块是**对话认知层** (可推断/可 supersede)。PRD formalize 时以
  source_product_understanding_version 锚定 (见 application_formalization.py)。
- 零依赖其它 factory_console 模块 (纯标准库), 供 app 层/测试自由引用。

Supersession 语义 (Test D):
- identity_key(fact) = (type, normalized content) — 同 key 且状态为有效
  (PROPOSED/CONFIRMED) 的旧事实存在时, 新 fact 顶替: 旧 status=SUPERSEDED +
  superseded_by=new_id; 新 fact.supersedes=[old_id]。
- effective facts = status ∈ {PROPOSED, CONFIRMED}; 同 key 二者并存时 CONFIRMED 优先
  (排序后只保留 CONFIRMED, PROPOSED 同 key 视为待确认重复)。

字段契约 (S49 §二):
id / conversation_id / type / content / status / source_message_id /
created_at / updated_at / confidence / provenance (+ supersession 关联)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ 常量/注册表

#: Fact 类型注册表 (可扩展: 新增类型 = 追加成员, 集合完整性由测试守住)
FACT_TYPES: tuple[str, ...] = (
    "IDEA", "REQUIREMENT", "CONSTRAINT", "DECISION", "QUESTION", "FUTURE_IDEA",
)

#: Fact 状态注册表
FACT_STATUSES: tuple[str, ...] = ("PROPOSED", "CONFIRMED", "SUPERSEDED", "REJECTED")

#: Conversation 状态
CONV_STATUSES: tuple[str, ...] = ("OPEN", "ARCHIVED")

#: 有效事实状态 (参与 understanding snapshot)
ACTIVE_STATUSES: tuple[str, ...] = ("PROPOSED", "CONFIRMED")

#: 消息角色
MESSAGE_ROLES: tuple[str, ...] = ("human", "assistant", "system")

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _conv_file(root: Path | str, conv_id: str) -> Path:
    return Path(root) / "conversations" / f"{conv_id}.json"


def _load_conv(root: Path | str, conv_id: str) -> dict[str, Any] | None:
    p = _conv_file(root, conv_id)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None  # 损坏 → 失败安全 (不拖垮读取方)


def _save_conv(root: Path | str, conv_id: str, data: dict[str, Any]) -> None:
    p = _conv_file(root, conv_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ 校验

def _norm_type(fact_type: str) -> str:
    t = str(fact_type or "").strip().upper()
    if t not in FACT_TYPES:
        raise ValueError(f"非法 fact type: {fact_type!r} (可选: {', '.join(FACT_TYPES)})")
    return t


def _norm_status(status: str) -> str:
    s = str(status or "").strip().upper()
    if s not in FACT_STATUSES:
        raise ValueError(f"非法 fact status: {status!r} (可选: {', '.join(FACT_STATUSES)})")
    return s


def normalize_content(content: Any) -> str:
    """内容规范化: 去空白/全半角/标点 — supersession identity 用。"""
    text = str(content or "").strip()
    text = text.replace("，", ",").replace("。", ".").replace("、", ",")
    text = text.replace("！", "!").replace("？", "?")
    text = " ".join(text.split())
    return text


# ------------------------------------------------------------------ Fact 创建/更新

def build_fact(*, conversation_id: str, fact_type: str, content: str,
               source_message_id: str = "", confidence: float = 1.0,
               provenance: str = "", status: str = "PROPOSED") -> dict[str, Any]:
    """构造 Fact dict (不落盘; 唯一 writer = upsert_fact)。"""
    now = _now_iso()
    return {
        "id": _new_id("fact"),
        "conversation_id": str(conversation_id or ""),
        "type": _norm_type(fact_type),
        "content": str(content or "").strip(),
        "status": _norm_status(status),
        "source_message_id": str(source_message_id or ""),
        "confidence": float(confidence),
        "provenance": str(provenance or ""),
        "supersedes": [],
        "superseded_by": "",
        "created_at": now,
        "updated_at": now,
    }


def identity_key(fact: dict[str, Any]) -> tuple[str, str]:
    """fact identity: (type, normalized content) — supersession 判重。"""
    return (_norm_type(fact.get("type", "")), normalize_content(fact.get("content", "")))


def dimension_of(fact: dict[str, Any]) -> str:
    """语义槽 (supersession 维度): 同槽不同值 = 修改 → 顶替, 不新增重复。

    规则 (确定性, 防误伤):
    - 带前缀槽的 content ("运行平台:"/"操作方式:"/"平台"/"目标用户") → slot:<name>
    - CONSTRAINT 含 登录 → slot:login
    - IDEA → slot:idea (一个 conversation 一个核心产品; 换想法 = 顶替)
    - FUTURE_IDEA / 普通 REQUIREMENT / 其它 → exact:<type>:<content>
      (多 future 想法 / 多功能需求可共存)
    """
    ftype = _norm_type(fact.get("type", ""))
    content = normalize_content(fact.get("content", ""))
    if ftype == "IDEA":
        return "slot:idea"
    if content.startswith("运行平台") or content.startswith("平台") \
            or content.lower().startswith("platform"):
        return "slot:platform"
    if content.startswith("操作方式") or content.startswith("交互方式"):
        return "slot:operation"
    if content.startswith("目标用户") or content.startswith("用户是") \
            or content.lower().startswith("target user"):
        return "slot:user"
    if ftype == "CONSTRAINT" and ("登录" in content or "login" in content.lower()):
        return "slot:login"
    return f"exact:{ftype}:{content}"


def _ensure_conv_doc(root: Path | str, conv_id: str) -> dict[str, Any]:
    """读 conversation 文档; 不存在 → 抛错 (create_conversation 必须先建)。"""
    doc = _load_conv(root, conv_id)
    if doc is None:
        raise ValueError(f"conversation 不存在: {conv_id}")
    return doc


def _mutate(root: Path | str, conv_id: str,
            fn) -> dict[str, Any]:
    """锁内读-改-写 conversation 文档; fn(doc) -> None (原地改)。"""
    with _lock:
        doc = _ensure_conv_doc(root, conv_id)
        fn(doc)
        _save_conv(root, conv_id, doc)
        return doc


# ------------------------------------------------------------------ Conversation

def create_conversation(root: Path | str, *, title: str = "新会话",
                        created_by: str = "human") -> dict[str, Any]:
    """创建 Conversation (conv-*; 目标域独立于 conversation_os conv_ legacy)。

    幂等: 同 title 不判重 — 每次创建独立 conversation (用户可开多个长期会话)。
    """
    if not title or not str(title).strip():
        raise ValueError("conversation title required")
    now = _now_iso()
    conv_id = _new_id("conv")
    doc = {
        "id": conv_id,
        "title": str(title).strip()[:200],
        "status": "OPEN",
        "created_by": str(created_by or ""),
        "messages": [],
        "understanding": {"version": 0, "facts": {}},
        "created_at": now,
        "updated_at": now,
    }
    with _lock:
        if _load_conv(root, conv_id) is not None:  # 天文概率碰撞 — 防御
            raise ValueError(f"conversation id 冲突: {conv_id}")
        _save_conv(root, conv_id, doc)
    return _public_conv(doc)


def get_conversation(root: Path | str, conv_id: str) -> dict[str, Any] | None:
    doc = _load_conv(root, conv_id)
    return _public_conv(doc) if doc is not None else None


def _public_conv(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc.get("id"),
        "title": doc.get("title"),
        "status": doc.get("status"),
        "created_by": doc.get("created_by", ""),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "messages_count": len(doc.get("messages") or []),
        "understanding_version": int((doc.get("understanding") or {}).get("version") or 0),
        "fact_count": len((doc.get("understanding") or {}).get("facts") or {}),
    }


def conversations(root: Path | str) -> list[dict[str, Any]]:
    d = Path(root) / "conversations"
    out = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob("conv-*.json")):
        doc = _load_conv(root, p.stem)
        if doc is not None:
            out.append(_public_conv(doc))
    return sorted(out, key=lambda c: str(c.get("created_at") or ""))


def append_message(root: Path | str, conv_id: str, *, role: str,
                   content: str) -> dict[str, Any]:
    """追加消息 (append-only; 返回 msg record — source_message_id 引用)。"""
    if role not in MESSAGE_ROLES:
        raise ValueError(f"非法 role: {role!r} (可选: {', '.join(MESSAGE_ROLES)})")
    if not str(content or "").strip():
        raise ValueError("message content required")
    now = _now_iso()
    msg = {"id": _new_id("msg"), "role": role,
           "content": str(content).strip(), "created_at": now}

    def _fn(doc: dict[str, Any]) -> None:
        doc.setdefault("messages", []).append(msg)
        doc["updated_at"] = now
    _mutate(root, conv_id, _fn)
    return dict(msg)


def messages(root: Path | str, conv_id: str) -> list[dict[str, Any]]:
    doc = _ensure_conv_doc(root, conv_id)
    return list(doc.get("messages") or [])


# ------------------------------------------------------------------ Understanding facts

def _facts(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return (doc.setdefault("understanding", {})
            .setdefault("facts", {}))


def _bump_understanding_version(doc: dict[str, Any]) -> int:
    u = doc.setdefault("understanding", {})
    u["version"] = int(u.get("version") or 0) + 1
    u["updated_at"] = _now_iso()
    return int(u["version"])


def upsert_fact(root: Path | str, conv_id: str, *, fact_type: str,
                content: str, source_message_id: str = "",
                confidence: float = 1.0, provenance: str = "",
                status: str = "PROPOSED") -> dict[str, Any]:
    """唯一 Fact writer (幂等 supersession 语义, Test D)。

    - 同 identity_key (type + normalized content) 的**有效**旧事实存在时:
      原地更新 (刷新 source/confidence/provenance, 不新增, 不产生历史噪音)。
    - 同 **语义槽** (dimension_of) 但内容不同 → 用户修改该维度:
      旧 status → SUPERSEDED + superseded_by=new_id; 新 fact supersedes=[old_id]。
      (例: 平台 "手机端" → "网页端" = 修改不是新增; 约束重申不产生两个冲突 Constraint)
    - 否则新增。
    - 每次成功写入 understanding.version +1 (PRD provenance 锚点)。
    """
    ftype = _norm_type(fact_type)
    if not str(content or "").strip():
        raise ValueError("fact content required")
    fstatus = _norm_status(status)
    key = (ftype, normalize_content(content))
    dim = dimension_of({"type": ftype, "content": content})
    new_fact = build_fact(conversation_id=conv_id, fact_type=ftype,
                          content=str(content).strip(),
                          source_message_id=source_message_id,
                          confidence=float(confidence),
                          provenance=provenance, status=fstatus)

    def _fn(doc: dict[str, Any]) -> None:
        facts = _facts(doc)
        # 1) 精确同 key 有效 → 原地更新 (刷新, 不新增)
        for fid, f in list(facts.items()):
            if f.get("status") not in ACTIVE_STATUSES:
                continue
            if identity_key(f) == key:
                f["source_message_id"] = source_message_id or f.get("source_message_id", "")
                if provenance:
                    f["provenance"] = provenance
                f["confidence"] = max(float(f.get("confidence") or 0.0),
                                      float(confidence))
                f["updated_at"] = _now_iso()
                _bump_understanding_version(doc)
                return
        # 2) 同语义槽不同值 → supersede (修改维度, 不新增重复)
        superseded = []
        for fid, f in list(facts.items()):
            if f.get("status") not in ACTIVE_STATUSES:
                continue
            if f.get("type") == ftype and dimension_of(f) == dim:
                facts[fid]["status"] = "SUPERSEDED"
                facts[fid]["superseded_by"] = new_fact["id"]
                facts[fid]["updated_at"] = _now_iso()
                superseded.append(fid)
        if superseded:
            new_fact["supersedes"] = superseded
        # 3) 落盘新 fact
        facts[new_fact["id"]] = new_fact
        _bump_understanding_version(doc)
    _mutate(root, conv_id, _fn)
    return dict(new_fact)


def transition_fact(root: Path | str, conv_id: str, fact_id: str, *,
                    to: str, actor: str = "") -> dict[str, Any]:
    """Fact 状态转换 (PROPOSED → CONFIRMED/REJECTED; 终态不可逆转)。

    - CONFIRMED: 用户明确确认 (S49 §18.2 高优先级事实)。
    - SUPERSEDED/REJECTED 为终态; 已 SUPERSEDED 不可再转换。
    """
    target = _norm_status(to)
    if target not in ("CONFIRMED", "REJECTED"):
        raise ValueError(f"非法目标状态: {to!r} (仅支持 CONFIRMED/REJECTED)")
    result: dict[str, Any] = {}

    def _fn(doc: dict[str, Any]) -> None:
        facts = _facts(doc)
        f = facts.get(fact_id)
        if f is None:
            raise KeyError(f"fact 不存在: {fact_id}")
        if f.get("status") in ("SUPERSEDED",):
            raise ValueError(f"fact {fact_id} 已 SUPERSEDED — 不可转换")
        if f.get("status") == target:
            result.update(f)  # 幂等
            return
        f["status"] = target
        f["updated_at"] = _now_iso()
        if actor:
            f["provenance"] = f"{f.get('provenance') or ''} confirmed_by={actor}".strip()
        result.update(f)
        _bump_understanding_version(doc)
    _mutate(root, conv_id, _fn)
    return dict(result)


def list_facts(root: Path | str, conv_id: str, *, fact_type: str = "",
               include_inactive: bool = False) -> list[dict[str, Any]]:
    """按 created_at 升序列出 facts (默认仅有效事实; fact_type 过滤)。"""
    doc = _ensure_conv_doc(root, conv_id)
    out = []
    for f in _facts(doc).values():
        if fact_type and f.get("type") != _norm_type(fact_type):
            continue
        if not include_inactive and f.get("status") not in ACTIVE_STATUSES:
            continue
        out.append(dict(f))
    return sorted(out, key=lambda x: str(x.get("created_at") or ""))


def understanding_version(root: Path | str, conv_id: str) -> int:
    doc = _ensure_conv_doc(root, conv_id)
    return int((doc.get("understanding") or {}).get("version") or 0)


def understanding_snapshot(root: Path | str, conv_id: str) -> dict[str, Any]:
    """当前理解快照 (context/PRD 构建输入; 同 key CONFIRMED 优先于 PROPOSED)。

    返回: {version, conversation_id, by_type: {TYPE: [fact...]}, facts: [全部有效]}
    """
    doc = _ensure_conv_doc(root, conv_id)
    version = int((doc.get("understanding") or {}).get("version") or 0)
    by_type: dict[str, list[dict[str, Any]]] = {t: [] for t in FACT_TYPES}
    # 同 key 多状态 → CONFIRMED 优先; PROPOSED 同 key 且被 CONFIRMED 覆盖 → 不重复列出
    seen_keys: set[tuple[str, str]] = set()
    ordered = sorted(_facts(doc).values(),
                     key=lambda f: str(f.get("created_at") or ""))
    for f in ordered:
        if f.get("status") not in ACTIVE_STATUSES:
            continue
        k = identity_key(f)
        has_confirmed = any(
            x.get("status") == "CONFIRMED" and identity_key(x) == k
            for x in ordered)
        if f.get("status") == "PROPOSED" and has_confirmed:
            continue
        if k in seen_keys:
            continue
        seen_keys.add(k)
        by_type.setdefault(str(f.get("type")), []).append(dict(f))
    facts_flat = [f for lst in by_type.values() for f in lst]
    return {"conversation_id": conv_id, "version": version,
            "by_type": by_type, "facts": facts_flat}


def close_conversation(root: Path | str, conv_id: str) -> dict[str, Any]:
    """归档 conversation (Session Restart 测试: Session1 close → Session2 仍可读)。"""
    def _fn(doc: dict[str, Any]) -> None:
        doc["status"] = "ARCHIVED"
        doc["updated_at"] = _now_iso()
    _mutate(root, conv_id, _fn)
    return get_conversation(root, conv_id) or {}


# ------------------------------------------------------------------ Context 构建 (S49 §六)

def build_context(root: Path | str, conv_id: str, *, recent_messages: int = 8,
                  max_facts: int = 40) -> dict[str, Any]:
    """从持久化 Understanding 构建上下文 (替代"猜产品是什么")。

    Conversation + recent messages + effective facts (type 分组, 截断 budget)。
    """
    doc = _ensure_conv_doc(root, conv_id)
    snap = understanding_snapshot(root, conv_id)
    msgs = list(doc.get("messages") or [])[-recent_messages:]
    facts = snap["facts"][-max_facts:]
    return {
        "conversation_id": conv_id,
        "conversation_title": doc.get("title", ""),
        "understanding_version": snap["version"],
        "recent_messages": [dict(m) for m in msgs],
        "facts": [dict(f) for f in facts],
        "by_type": {t: [dict(f) for f in lst] for t, lst in snap["by_type"].items()},
    }


__all__ = [
    "FACT_TYPES", "FACT_STATUSES", "CONV_STATUSES", "ACTIVE_STATUSES",
    "build_fact", "identity_key", "normalize_content",
    "create_conversation", "get_conversation", "conversations",
    "append_message", "messages", "close_conversation",
    "upsert_fact", "transition_fact", "list_facts",
    "understanding_version", "understanding_snapshot", "build_context",
]
