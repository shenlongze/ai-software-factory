"""services.conversation.scoped_facts — 分层事实存储（按作用域隔离的记忆）。

★ 2026-09-19 新建（Founder 拍板的设计）。

【为什么需要（Founder 原话）】
  "会话有区分, 比如全局, 拥有独立的记忆, 在会话中选择项目, 那么就应该是项目级的记忆,
   除非用户在会话中明确, 公司有公司的记忆, 部门有部门的记忆, 这样 facts 就会被分开,
   体量会小一点" + "比如在公司下, 可以查全部门的所有信息"

【四条规则（本模块实现）】
  ① 归属（线性四级, 每事实只存一份）:
       全局 < 公司 < 部门 < 项目
  ② 可见（读）: 同公司横向可见 —— 公司级可查全部部门; 市场部能读 IT 部门的项目事实
               跨公司 ⇒ 拒绝（Default Deny, 复用 organization 的 Authority 语义）
  ③ 继承（查）: 从最具体往上找（项目 → 部门 → 公司 → 全局）; 同 key **下层覆盖上层**
  ④ 三层（送什么）: 全量(本模块存储) / 检索(FTS5, 刀3) / 最近(注入, 刀3)

【为什么"归属"和"可见"要分开（Founder 的反例）】
  "可能项目在 IT 部门, 市场部要查, 就查不到了" ——
  若把两者混成一件事, 线性四级就会挡住横向查询;
  拆开后: 事实仍只存一份（体量小）, 而"谁能读"由权限规则决定（横向可达）。

【存储布局（严格按 Founder 铁律: 属于项目的文件必须在项目目录下）】
  <root>/knowledge/global/facts.json                          ← 全局
  <root>/knowledge/companies/<co>/facts.json                  ← 公司级
  <root>/knowledge/companies/<co>/departments/<dept>/facts.json ← 部门级
  <root>/projects/<P-id>/knowledge/facts.json                 ← 项目级

【诚实边界】
  · 本模块**不删**旧数据: 会话内的 facts 保持原样（刀2 才切写入路径）——
    新能力先能跑、能验证, 再迁移, 避免"一半新一半旧"时把现有会话弄坏。
  · 检索（FTS5）与"最近 N 条注入"属刀3, 本刀只做**存储 + 继承读取**。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 层级（由泛到具体）—— 继承顺序即此序的逆序
LEVELS: tuple[str, ...] = ("global", "company", "department", "project")

#: 层级排序（用于"下层覆盖上层"的比较）
_ORDER: dict[str, int] = {lv: i for i, lv in enumerate(LEVELS)}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


# ------------------------------------------------------------------ 作用域

def make_scope(level: str, ident: str = "") -> dict[str, str]:
    """构造作用域 {level, id}。level 必须是四级之一（响亮报错, 不静默降级）。"""
    lv = str(level or "").strip().lower()
    if lv not in LEVELS:
        raise ValueError(f"非法作用域层级: {level!r}（可选: {', '.join(LEVELS)}）")
    return {"level": lv, "id": str(ident or "")}


def scope_from_conversation(conv: dict[str, Any] | None,
                            *, company_id: str = "", department_id: str = "") -> dict[str, str]:
    """从会话推断作用域（默认规则）。

    规则（Founder: "会话中选择项目 ⇒ 项目级; 除非用户在会话中明确"）:
      · 会话绑了项目   ⇒ project（项目级）
      · 会话属于某部门 ⇒ department
      · 会话属于某公司 ⇒ company
      · 都没有         ⇒ global（独立记忆）
    """
    c = conv or {}
    pid = str(c.get("project_id") or "").strip()
    if pid:
        return make_scope("project", pid)
    if str(department_id or "").strip():
        return make_scope("department", department_id)
    if str(company_id or "").strip():
        return make_scope("company", company_id)
    return make_scope("global", "")


# ------------------------------------------------------------------ 路径

def _facts_file(root: Path | str, scope: dict[str, str]) -> Path:
    """作用域 → 存储文件（项目级严格落在 projects/<P-id>/ 下）。"""
    base = Path(root)
    lv, ident = scope.get("level"), str(scope.get("id") or "")
    if lv == "project":
        return base / "projects" / ident / "knowledge" / "facts.json"
    if lv == "department":
        # 部门知识挂在公司下（<co>/departments/<dept>）；ident 形如 "co/dept" 或仅 dept
        co, _, dept = ident.partition("/")
        if dept:
            return base / "knowledge" / "companies" / co / "departments" / dept / "facts.json"
        return base / "knowledge" / "departments" / ident / "facts.json"
    if lv == "company":
        return base / "knowledge" / "companies" / ident / "facts.json"
    return base / "knowledge" / "global" / "facts.json"


def read_layer(root: Path | str, scope: dict[str, str]) -> list[dict[str, Any]]:
    """读**单层**（不继承）—— 失败安全。"""
    p = _facts_file(root, scope)
    if not p.is_file():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return list(d.get("facts") or [])
    except (OSError, ValueError):
        return []


# ------------------------------------------------------------------ 写

def add_fact(root: Path | str, scope: dict[str, str], *,
             fact_type: str, content: str, **extra: Any) -> dict[str, Any]:
    """往指定作用域写一条事实（同 key 同层 ⇒ 覆盖；跨层各存一份）。

    key = (type, content 归一)。同层重复 ⇒ 返回既有（幂等, 不重复堆）。
    """
    scope = make_scope(scope.get("level", ""), scope.get("id", ""))
    rows = read_layer(root, scope)
    key = (str(fact_type).strip().upper(), " ".join(str(content).split()))
    for r in rows:
        if (str(r.get("type") or "").upper(), " ".join(str(r.get("content") or "").split())) == key:
            return r
    f = {
        "id": f"fact-{uuid.uuid4().hex[:12]}",
        "scope": scope,
        "type": key[0],
        "content": key[1],
        "status": str(extra.get("status") or "PROPOSED"),
        "created_at": _now(),
        **{k: v for k, v in extra.items() if k != "status"},
    }
    p = _facts_file(root, scope)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows.append(f)
    p.write_text(json.dumps({"scope": scope, "facts": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return f


# ------------------------------------------------------------------ 读（继承 + 覆盖）

def _visible_scopes(scope: dict[str, str], *,
                    company_id: str = "", department_id: str = "",
                    same_company: bool = True) -> list[dict[str, str]]:
    """**可见链**（由具体到泛）—— 包含两部分:

      ① 继承链: 自己的层级向上（项目 → 部门 → 公司 → 全局）
      ② ★ 同公司横向: 同一家公司的**其它部门/项目**（Founder 的例子:
         "项目在 IT 部门, 市场部要查" ⇒ 必须能横向读到）

    ★ 为什么要把 ② 放在这里（而不是留给权限层）:
      因为"读"的语义就是"在我能看到的所有层里找" —— 分两个函数会让调用方各写一遍。
      权限过滤（谁能读、跨公司拒绝）在刀3 接 Authority 时收紧: 本函数只负责"候选集"。
    公司/部门：显式传入优先; 否则从 scope.id 里解析（形如 "公司/部门"）。
    """
    lv = scope.get("level") or "global"
    ident = str(scope.get("id") or "")
    chain: list[dict[str, str]] = []

    # 解析公司 / 部门（用于把项目挂回它的组织链）
    co = str(company_id or "")
    dept = str(department_id or "")
    if not co and lv == "department":
        co, _, dept = ident.partition("/")
    if not co and lv == "project":
        # 项目作用域未带公司信息 ⇒ 仅能到全局（诚实: 不猜它属于哪个公司）
        co = ""

    if lv == "project":
        chain.append(make_scope("project", ident))
        if dept:
            chain.append(make_scope("department", f"{co}/{dept}" if co else dept))
        if co:
            chain.append(make_scope("company", co))
    elif lv == "department":
        chain.append(make_scope("department", ident))
        if co:
            chain.append(make_scope("company", co))
    elif lv == "company":
        chain.append(make_scope("company", ident))
    chain.append(make_scope("global", ""))
    return chain


def _horizontal_scopes(root: Path | str, scope: dict[str, str], *,
                       company_id: str = "") -> list[dict[str, str]]:
    """同公司横向可见层（公司的所有部门 + 所有项目）—— 用于"市场部查 IT 的项目"。"""
    co = str(company_id or "")
    if not co and scope.get("level") == "department":
        co, _, _ = str(scope.get("id") or "").partition("/")
    if not co and scope.get("level") == "company":
        co = str(scope.get("id") or "")
    if not co:
        return []
    out: list[dict[str, str]] = []
    base = Path(root)
    ddir = base / "knowledge" / "companies" / co / "departments"
    if ddir.is_dir():
        for d in sorted(ddir.iterdir()):
            if d.is_dir():
                out.append(make_scope("department", f"{co}/{d.name}"))
    for p in sorted((base / "projects").glob("*/knowledge/facts.json")):
        out.append(make_scope("project", p.parent.parent.name))
    return out


def _slot(root: Path | str, scope: dict[str, str], row: dict[str, Any]) -> tuple[str, str]:
    """事实的**语义槽** —— 判重的键（同槽不同值 = 修改 ⇒ 顶替, 不共存）。

    ★ 2026-09-19: 先走**通用规则**（任何 `「前缀: 值」` 都归一到同一个槽）, 再回落
      会话层 `dimension_of`。为什么: `dimension_of` 的槽列表是**硬编码前缀**
      （"运行平台:"/"操作方式:"/"平台"/"目标用户"）, 实测「默认语言: 中文 / 默认语言: 英文」
      不在其列 ⇒ 不归一 ⇒ 两条并存（与 `_PRODUCT_HINT_RE` 同一类"枚举不全"的毛病）。
      通用规则: 内容形如 `X: Y` ⇒ 槽 = X（不管 X 叫什么）。
    """
    ftype = str(row.get("type") or "").upper()
    content = " ".join(str(row.get("content") or "").split())
    head, sep, tail = content.partition(":")
    if sep and head.strip() and tail.strip() and len(head) <= 20:
        return (ftype, f"slot:{head.strip()}")        # ★ 通用: 「前缀: 值」⇒ 同槽
    try:
        from ai_factory_os.services.conversation.understanding import dimension_of

        return (ftype, f"slot:{dimension_of(row)}")   # 复用会话层（IDEA→slot:idea 等）
    except Exception:  # noqa: BLE001 — 会话层不可用 ⇒ 回落全文（保守: 不误合并）
        return (ftype, f"exact:{content}")


def effective_facts(root: Path | str, scope: dict[str, str], *,
                    company_id: str = "", department_id: str = "",
                    horizontal: bool = True) -> dict[str, Any]:
    """**可见 + 继承 + 覆盖**后的有效事实（每条带 provenance）。

    顺序: 自己的链（具体→泛） → ★ 同公司横向（其它部门/项目）
    规则: 同 key **先到先得** ⇒ 越具体/越"自己的"越优先（下层覆盖上层）
    返回 {facts, by_level, provenance, horizontal_layers}
    """
    chain = _visible_scopes(scope, company_id=company_id, department_id=department_id)
    horizon = _horizontal_scopes(root, scope, company_id=company_id) if horizontal else []

    seen: dict[tuple[str, str], dict[str, Any]] = {}
    by_level: dict[str, int] = {}
    hlayers = 0
    for sc in chain + horizon:                        # ★ 自己链优先, 横向在后
        rows = read_layer(root, sc)
        by_level[sc["level"]] = by_level.get(sc["level"], 0) + len(rows)
        if sc in horizon:
            hlayers += 1 if rows else 0
        for r in rows:
            k = _slot(root, sc, r)                    # ★ 语义槽判重（同槽 ⇒ 顶替）
            if k in seen:
                continue                              # 已有更具体的同槽 ⇒ 跳过
            item = dict(r)
            item["provenance"] = sc["level"]          # ★ 可解释: 这条来自哪一层
            if sc in horizon:
                item["via"] = "same-company"          # ★ 标明是横向读到的
            seen[k] = item
    return {"scope": scope, "facts": list(seen.values()), "by_level": by_level,
            "count": len(seen), "horizontal_layers": hlayers}


def stats(root: Path | str, scopes: list[dict[str, str]]) -> dict[str, Any]:
    """各层事实体量（用于回答 Founder 关心的"体量会小一点"）。"""
    out: dict[str, int] = {}
    for sc in scopes:
        out[f"{sc.get('level')}:{sc.get('id') or '-'}"] = len(read_layer(root, sc))
    return {"layers": out, "total": sum(out.values())}

def upsert_fact(root: Path | str, scope: dict[str, str], fact: dict[str, Any]) -> dict[str, Any]:
    """**按语义槽**写入（同槽 ⇒ 顶替; 而非只是同 key 幂等）。

    与 `add_fact` 的区别: add_fact 只对"完全同 key"幂等;
    upsert_fact 还会把**同槽的旧值清掉**（例: 「默认语言: 中文」被「默认语言: 英文」顶替）。
    ⇒ 会话每次写入后调它全量刷, 分层里就始终是"该会话当前的真相"。
    """
    scope = make_scope(scope.get("level", ""), scope.get("id", ""))
    rows = read_layer(root, scope)
    key = _slot(root, scope, fact)
    kept: list[dict[str, Any]] = []
    for r in rows:
        if _slot(root, scope, r) == key:
            continue                                   # 同槽旧值 ⇒ 顶替（不保留）
        kept.append(r)
    row = {
        "id": str(fact.get("id") or f"fact-{uuid.uuid4().hex[:12]}"),
        "scope": scope,
        "type": str(fact.get("type") or "").upper(),
        "content": " ".join(str(fact.get("content") or "").split()),
        "status": str(fact.get("status") or "PROPOSED"),
        "source_message_id": str(fact.get("source_message_id") or ""),
        "conversation_id": str(fact.get("conversation_id") or ""),
        "updated_at": _now(),
    }
    kept.append(row)
    p2 = _facts_file(root, scope)
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(json.dumps({"scope": scope, "facts": kept}, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    return row

