"""conversation · 产品认知事实层（Product Understanding SSOT）—— 搬迁自 factory_console.product_understanding。

为什么它在这: 这是"**需求获取**"的真相 —— 会话里的用户话语落成**事实**
（IDEA / REQUIREMENT / CONSTRAINT / DECISION / QUESTION / FUTURE_IDEA），
每条都带 `source_message_id`（可追溯原话）+ `confidence` + `provenance`。
迁移前实测它是**活的**: 41 个会话 / 78 条事实（IDEA 25 · REQUIREMENT 42 ·
CONSTRAINT 6 · QUESTION 5），所以是**搬**不是删。

领域模型（冻结，不变）:
```
Conversation (conv-*)
 ├── title / status (OPEN | ARCHIVED)
 ├── messages: [{id, role, content, created_at}]   (append-only, 供 source_message_id)
 └── understanding
      ├── version: int  (单调递增 — PRD provenance 锚点)
      └── facts: {fact_id: Fact}
           type ∈ IDEA | REQUIREMENT | CONSTRAINT | DECISION | QUESTION | FUTURE_IDEA
           status ∈ PROPOSED | CONFIRMED | SUPERSEDED | REJECTED | DEFERRED
```

Supersession 语义（本模块的承重环节）:
  · 同 `identity_key`(type + 归一化内容) 且有效 → **原地更新**（不新增、无历史噪音）
  · 同 **语义槽** `dimension_of` 但值不同 → 旧事实 SUPERSEDED + 新事实 supersedes=[旧]
    （平台"手机端"→"网页端" = **修改**，不是新增；约束重申不产生两条冲突 CONSTRAINT）
  · 每次成功写入 understanding.version +1 —— 这是 PRD 的 provenance 锚点

数据落点（Founder 铁律 ✓）: `projects/<P-id>/conversations/` 优先，回落全局 `conversations/`；
未绑项目的会话在全局，绑定后由 move_conv_to_project 搬进项目目录。

分层: 本模块是**对话认知层**（可推断、可 supersede）；REQ/PRD/PLAN 的
**正式资产层**（approved gate）是另一个域（product_truth）—— 勿混。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from ai_factory_os.services.conversation import scoped_facts as _scoped  # ★ 刀2: 分层同步

# ------------------------------------------------------------------ 常量/注册表

#: Fact 类型注册表 (可扩展: 新增类型 = 追加成员, 集合完整性由测试守住)
FACT_TYPES: tuple[str, ...] = (
    "IDEA", "REQUIREMENT", "CONSTRAINT", "DECISION", "QUESTION", "FUTURE_IDEA",
)

#: Fact 状态注册表 (Golden Path: DEFERRED = 延后但非拒绝, 可恢复/被 supersede)
FACT_STATUSES: tuple[str, ...] = (
    "PROPOSED", "CONFIRMED", "SUPERSEDED", "REJECTED", "DEFERRED",
)

#: Conversation 状态
CONV_STATUSES: tuple[str, ...] = ("OPEN", "ARCHIVED")

#: 有效事实状态 (参与 understanding snapshot; DEFERRED/REJECTED/SUPERSEDED 不参与)
ACTIVE_STATUSES: tuple[str, ...] = ("PROPOSED", "CONFIRMED")

#: 非终态 (可被后续语义操作改变; SUPERSEDED 终态不可逆转)
MUTABLE_STATUSES: tuple[str, ...] = ("PROPOSED", "CONFIRMED", "DEFERRED", "REJECTED")

#: 消息角色
MESSAGE_ROLES: tuple[str, ...] = ("human", "assistant", "system")

_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    from ai_factory_os.infrastructure.ids import new_id as _canonical_id
    return _canonical_id(prefix, 12)


def _conv_file(root: Path | str, conv_id: str) -> Path:
    # ★ 属于项目的文件必须在项目目录下（Founder 铁律 ✓）
    #   优先级: projects/<P-id>/conversations/ ✓ → 回落全局 conversations/ ✓
    #   （未绑项目的会话仍在全局 ✓ —— 创建时还没项目，绑定后由
    #     move_conv_to_project 搬进项目 ✓）
    base = Path(root)
    for f in base.glob(f"projects/*/conversations/{conv_id}.json"):
        if f.is_file():
            return f
    return base / "conversations" / f"{conv_id}.json"


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
    """构造 Fact dict (不落盘; 唯一 writer = upsert_fact)。

    ★ `source_message_id` 是**契约字段**（事实必须可追溯: 它是从哪句话抽出来的）。
      2026-09-15 查证记录（结论: **历史空缺如实保留, 不回填**）::
        · 全库 78 条事实里 20 条缺它 —— **全部是 2026-09-14 的数据**
          （当时调用未传参）;
        · 代码侧已正确: 本模块 upsert_fact 与 `proposal.apply_operations` 都
          明确传 `source_message_id`; 新跑的 51 条 `semantic:add` 全带 id ✓
        · 为何不回填: 回填只能靠"内容相似度猜", 猜错就**污染溯源链** ——
          而这条链的价值恰恰在于它不能是猜的。20 条缺溯源, 好过 20 条假溯源 ✓
      ⇒ 下次看到"缺失百分比"先分清【历史数据】与【代码未接线】, 别冲进去改代码。
    """
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
        # ★ 项目归属（Founder: 会话/需求/文档都该有项目属性 ✓）
        #   首次理解成功后由 ensure_project_binding 绑定（幂等）
        "project_id": "",
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
    # ★ 会话可能在【项目目录】里（绑项目的会话）✓ → 两处都扫 ✓
    dirs = [Path(root) / "conversations"]
    dirs += sorted(Path(root).glob("projects/*/conversations"))
    out = []
    for d in dirs:
        if not d.is_dir():
            continue
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


def _effective_facts_of(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """会话的**有效事实**（排除 SUPERSEDED / REJECTED）—— 同步到分层时用。"""
    out: list[dict[str, Any]] = []
    for f in _facts(doc).values():
        if str(f.get("status") or "") in ("SUPERSEDED", "REJECTED"):
            continue
        out.append(dict(f))
    return out


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
        # 1b) 精确同 key 的 DEFERRED/REJECTED 旧事实 → 用户重新提出 (恢复/顶替):
        #     旧 fact 标 SUPERSEDED, 新 fact 继承身份 — 不新增冲突重复。
        superseded_old = []
        for fid, f in list(facts.items()):
            if f.get("status") not in ("DEFERRED", "REJECTED"):
                continue
            if identity_key(f) == key:
                facts[fid]["status"] = "SUPERSEDED"
                facts[fid]["superseded_by"] = new_fact["id"]
                facts[fid]["updated_at"] = _now_iso()
                superseded_old.append(fid)
        if superseded_old:
            new_fact["supersedes"] = superseded_old
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
            new_fact["supersedes"] = list(
                dict.fromkeys(list(superseded_old) + list(superseded)))
        # 3) 落盘新 fact
        facts[new_fact["id"]] = new_fact
        _bump_understanding_version(doc)
    _mutate(root, conv_id, _fn)

    # ★ 刀2（2026-09-19）: 同步到**分层存储** —— 让 facts 跨会话可见（Founder 的设计:
    #   会话绑项目 ⇒ 项目级; 否则公司/部门/全局）。
    #   做法: 每次写入后把该会话的**有效 facts 全量刷到它的作用域层**（幂等 ——
    #   分层按**语义槽**顶替, 因此 supersede 也能正确反映）。
    #   ★ 失败**不阻塞**主路径（facts 已落会话文件）: 分层是"共享视图", 挂了不该让理解失败。
    #   ⚠ 教训: `_mutate(root, conv_id, _fn)` 在本文件出现多处 —— 首次接线时替换到了
    #     append_message 里的那一处（实测表现为"分层 0 条"）⇒ 接线后**必须实测**。
    try:
        doc2 = _load_conv(root, conv_id) or {}
        scope = _scoped.scope_from_conversation(doc2)
        for f in _effective_facts_of(doc2):
            _scoped.upsert_fact(root, scope, f)
    except Exception:  # noqa: BLE001 — 共享视图失败不影响理解主路径
        pass
    return dict(new_fact)


def transition_fact(root: Path | str, conv_id: str, fact_id: str, *,
                    to: str, actor: str = "") -> dict[str, Any]:
    """Fact 状态转换 (PROPOSED → CONFIRMED/REJECTED/DEFERRED/SUPERSEDED)。

    - CONFIRMED: 用户明确确认。
    - REJECTED: 用户明确拒绝/否定 (终态)。
    - DEFERRED: 用户延后 (非终态 — 可从 DEFERRED 恢复为 PROPOSED/CONFIRMED)。
    - SUPERSEDED: 被新事实顶替 (终态 — 语义操作 UPDATE/REPLACE 经此显式置位)。
    - 已 SUPERSEDED 不可再转换 (走新 fact supersede)。
    """
    target = _norm_status(to)
    if target not in ("CONFIRMED", "REJECTED", "DEFERRED", "PROPOSED",
                      "SUPERSEDED"):
        raise ValueError(
            f"非法目标状态: {to!r} "
            f"(仅支持 PROPOSED/CONFIRMED/REJECTED/DEFERRED/SUPERSEDED)")
    result: dict[str, Any] = {}

    def _fn(doc: dict[str, Any]) -> None:
        facts = _facts(doc)
        f = facts.get(fact_id)
        if f is None:
            raise KeyError(f"fact 不存在: {fact_id}")
        if f.get("status") == "SUPERSEDED":
            raise ValueError(f"fact {fact_id} 已 SUPERSEDED — 不可转换")
        if f.get("status") == target:
            result.update(f)  # 幂等
            return
        f["status"] = target
        f["updated_at"] = _now_iso()
        if actor:
            f["provenance"] = f"{f.get('provenance') or ''} {to.lower()}_by={actor}".strip()
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


def get_fact(root: Path | str, conv_id: str, fact_id: str) -> dict[str, Any] | None:
    """按 id 取单个 fact (含非有效状态 — 供确认/审计读全量)。"""
    doc = _ensure_conv_doc(root, conv_id)
    f = _facts(doc).get(fact_id)
    return dict(f) if f is not None else None


def understanding_version(root: Path | str, conv_id: str) -> int:
    doc = _ensure_conv_doc(root, conv_id)
    return int((doc.get("understanding") or {}).get("version") or 0)


def understanding_snapshot(root: Path | str, conv_id: str) -> dict[str, Any]:
    """当前理解快照 (context/PRD 构建输入; 同 key CONFIRMED 优先于 PROPOSED)。

    返回: {version, conversation_id, by_type: {TYPE: [fact...]}, facts: [全部有效],
           deferred: [DEFERRED facts], rejected: [REJECTED facts]} — Golden Path
    用户可见 Confirmation Loop 需展示延后/否决项 (用户可恢复/重提)。
    """
    doc = _ensure_conv_doc(root, conv_id)
    version = int((doc.get("understanding") or {}).get("version") or 0)
    by_type: dict[str, list[dict[str, Any]]] = {t: [] for t in FACT_TYPES}
    # 同 key 多状态 → CONFIRMED 优先; PROPOSED 同 key 且被 CONFIRMED 覆盖 → 不重复列出
    seen_keys: set[tuple[str, str]] = set()
    ordered = sorted(_facts(doc).values(),
                     key=lambda f: str(f.get("created_at") or ""))
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for f in ordered:
        status = f.get("status")
        if status == "DEFERRED":
            deferred.append(dict(f))
            continue
        if status == "REJECTED":
            rejected.append(dict(f))
            continue
        if status not in ACTIVE_STATUSES:
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
            "by_type": by_type, "facts": facts_flat,
            "deferred": deferred, "rejected": rejected}


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
    "MUTABLE_STATUSES",
    "build_fact", "identity_key", "normalize_content",
    "create_conversation", "get_conversation", "conversations",
    "append_message", "messages", "close_conversation",
    "upsert_fact", "transition_fact", "list_facts", "get_fact",
    "understanding_version", "understanding_snapshot", "build_context",
]


def move_conv_to_project(root: Path | str, conv_id: str,
                         project_id: str) -> bool:
    """把会话文件搬进 projects/<P-id>/conversations/（幂等 + 失败安全 ✓）。

    为什么: Founder 铁律「属于这个项目的文件，一定需要在这个目录下」✓。
    幂等: 已在项目目录 / 源不存在 → 直接返回 False，不报错 ✓。
    原子: os.replace 同盘原子替换 ✓（不会出现半个文件 ✗）。
    """
    if not project_id:
        return False
    src = Path(root) / "conversations" / f"{conv_id}.json"
    dst = Path(root) / "projects" / project_id / "conversations" / f"{conv_id}.json"
    if not src.is_file() or dst.exists():
        return False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        return True
    except OSError as exc:
        import sys as _s
        print(f"[project] 会话迁移失败: {exc}", file=_s.stderr)
        return False
