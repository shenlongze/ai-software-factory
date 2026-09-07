"""factory-console/application_formalization.py — PRD Domain Foundation (S49/Phase 5 §八)。

PRD 从 Product Understanding 派生 (不是独立创建/不是简单 PRD.md 文件):
```
Product Understanding (source_product_understanding_version)
    ↓ derive
PRD Domain Object (versioned, 结构化 content + structured_content)
    ↓ render (不破坏现有文件 Artifact 能力)
PRD.md Artifact (可选投影)
```

本阶段只建立 Domain/Object 边界 — 完整 PRD Workflow (review/approve/publish) 属后续
Phase (S49 §八: 不要过早做完整 PRD Workflow; §九: Development Plan 只建边界不实现)。

记录模型 (S49 §八核心字段):
- id: PRD-* | conversation_id | version: int | status: draft|approved|archived
- source_product_understanding_version: int  (provenance — 派生自哪个 understanding version)
- content: dict (结构化 sections, 从 facts 组装)
- structured_content: dict (facts 溯源映射)
- created_at / updated_at / history: [{version, at, note}]

存储: <root>/conversations/{cid}.json 内 conversation.prds (与 understanding 同文档 —
  原子一致; 同一 conversation 的 PRD 版本序列完整可追)。
零依赖其它 factory_console 模块 (纯标准库 + product_understanding)。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from factory_console import product_understanding as pu

PRD_STATUSES: tuple[str, ...] = ("draft", "approved", "archived")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_prd_id() -> str:
    return f"PRD-{uuid.uuid4().hex[:12]}"


# ------------------------------------------------------------------ 派生

def derive_prd_sections(snapshot: dict[str, Any]) -> dict[str, Any]:
    """从 understanding snapshot 组装 PRD content sections (结构化, 不写死格式)。

    映射 (Internal Structured):
    - overview: name/problem/value 取自 IDEA + DECISION(定位)
    - functional_requirements: REQUIREMENT facts
    - constraints: CONSTRAINT facts + 含"不要/不能/必须"的 REQUIREMENT
    - decisions: DECISION facts
    - future_considerations: FUTURE_IDEA facts
    - open_questions: QUESTION facts (未决)
    - provenance: {source_understanding_version, facts: [{id, type, content}]}
    """
    by_type = snapshot.get("by_type", {})
    idea_facts = by_type.get("IDEA", [])
    req_facts = [f for f in by_type.get("REQUIREMENT", [])]
    con_facts = list(by_type.get("CONSTRAINT", []))
    dec_facts = list(by_type.get("DECISION", []))
    q_facts = list(by_type.get("QUESTION", []))
    future_facts = list(by_type.get("FUTURE_IDEA", []))

    # 平台/用户/名称从 REQUIREMENT 分离 (若以 "运行平台:" 等前缀表达)
    platform = ""
    target_users = ""
    name = ""
    functional = []
    for f in req_facts:
        content = str(f.get("content") or "")
        low = content.lower()
        if content.startswith("运行平台") or low.startswith("platform"):
            platform = content.split(":", 1)[-1].strip() if ":" in content else content
        elif content.startswith("目标用户") or low.startswith("user"):
            target_users = content.split(":", 1)[-1].strip() if ":" in content else content
        elif content.startswith("产品名称") or low.startswith("name"):
            name = content.split(":", 1)[-1].strip() if ":" in content else content
        else:
            functional.append(content)

    idea = idea_facts[0]["content"] if idea_facts else ""
    overview = {
        "name": name or (idea.split("做")[-1].strip() if idea else "") or "",
        "problem": idea,
        "target_users": target_users,
        "platform": platform,
    }
    return {
        "overview": overview,
        "functional_requirements": functional,
        "constraints": [str(f.get("content") or "") for f in con_facts],
        "decisions": [str(f.get("content") or "") for f in dec_facts],
        "future_considerations": [str(f.get("content") or "") for f in future_facts],
        "open_questions": [str(f.get("content") or "") for f in q_facts],
        "provenance": {
            "source_understanding_version": int(snapshot.get("version") or 0),
            "facts": [{"id": f.get("id"), "type": f.get("type"),
                       "content": f.get("content")}
                      for f in snapshot.get("facts", [])],
        },
    }


# ------------------------------------------------------------------ PRD 生命周期 (最小: draft → approved → archived)

def _prds(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc.setdefault("prds", [])


def create_prd(root: str, conversation_id: str, *, actor: str = "",
               title: str = "") -> dict[str, Any]:
    """从当前 Understanding 派生 PRD v1 (唯一 PRD writer 之一; draft)。

    若已有同名 draft → 抛错 (防止误解: 修改应走 update_prd 生成新 version)。
    """
    doc = pu._ensure_conv_doc(root, conversation_id)  # noqa: F841 — 存在性检查
    snap = pu.understanding_snapshot(root, conversation_id)
    if int(snap.get("version") or 0) <= 0:
        raise ValueError("尚无 Product Understanding — 无法派生 PRD")
    sections = derive_prd_sections(snap)
    prd_id = _new_prd_id()
    now = _now_iso()
    rec = {
        "id": prd_id,
        "conversation_id": conversation_id,
        "version": 1,
        "status": "draft",
        "title": str(title or "") or sections["overview"].get("name") or "PRD",
        "source_product_understanding_version": int(snap["version"]),
        "content": sections,
        "structured_content": _structured_mapping(sections),
        "created_at": now,
        "updated_at": now,
        "actor": actor,
        "history": [{"version": 1, "at": now, "actor": actor, "note": "created"}],
    }
    with pu._lock:
        doc2 = pu._load_conv(root, conversation_id)
        if doc2 is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        prds = _prds(doc2)
        for p in prds:
            if p.get("status") == "draft":
                raise ValueError(
                    f"已有 draft PRD ({p['id']} v{p['version']}) — 修改请走 update_prd")
        prds.append(rec)
        pu._save_conv(root, conversation_id, doc2)
    return json.loads(json.dumps(rec, ensure_ascii=False))


def _structured_mapping(sections: dict[str, Any]) -> dict[str, Any]:
    """structured_content: 每 section 标记其溯源 fact (粗略 — fact id 溯源在
    content.provenance.facts 已保留; 此处保留 section → 内容列表的映射)。"""
    return {k: list(v) if isinstance(v, list) else v
            for k, v in sections.items() if k != "provenance"}


def get_prd(root: str, conversation_id: str, prd_id: str) -> dict[str, Any] | None:
    doc = pu._load_conv(root, conversation_id)
    if doc is None:
        return None
    for p in _prds(doc):
        if p.get("id") == prd_id:
            return json.loads(json.dumps(p, ensure_ascii=False))
    return None


def list_prds(root: str, conversation_id: str) -> list[dict[str, Any]]:
    doc = pu._load_conv(root, conversation_id)
    if doc is None:
        return []
    return [json.loads(json.dumps(p, ensure_ascii=False)) for p in _prds(doc)]


def update_prd(root: str, conversation_id: str, prd_id: str, *,
               title: str = "", actor: str = "") -> dict[str, Any]:
    """修改 = 从**最新 Understanding** 重新派生 → 新 version (PRD 版本化; Test F)。

    仅 draft 可更新; approved/archived → ValueError (走新 PRD / 不原地改)。
    """
    with pu._lock:
        doc = pu._load_conv(root, conversation_id)
        if doc is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        prds = _prds(doc)
        idx = next((i for i, p in enumerate(prds) if p.get("id") == prd_id), None)
        if idx is None:
            raise KeyError(f"PRD 不存在: {prd_id}")
        cur = prds[idx]
        if cur.get("status") != "draft":
            raise ValueError(f"PRD {prd_id} 状态 {cur.get('status')} 不可更新 (仅 draft)")
        snap = pu.understanding_snapshot(root, conversation_id)
        sections = derive_prd_sections(snap)
        now = _now_iso()
        new_version = int(cur.get("version") or 1) + 1
        updated = json.loads(json.dumps(cur, ensure_ascii=False))
        updated["version"] = new_version
        updated["status"] = "draft"
        updated["title"] = str(title or "") or sections["overview"].get("name") or cur.get("title", "PRD")
        updated["source_product_understanding_version"] = int(snap["version"])
        updated["content"] = sections
        updated["structured_content"] = _structured_mapping(sections)
        updated["updated_at"] = now
        updated.setdefault("history", []).append(
            {"version": new_version, "at": now, "actor": actor, "note": "re-derived"})
        prds[idx] = updated
        pu._save_conv(root, conversation_id, doc)
        return updated


def approve_prd(root: str, conversation_id: str, prd_id: str, *,
                actor: str = "") -> dict[str, Any]:
    """draft → approved (人工批准门; S49 §八 不实现完整 workflow, 只留转换)。"""
    with pu._lock:
        doc = pu._load_conv(root, conversation_id)
        if doc is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        prds = _prds(doc)
        idx = next((i for i, p in enumerate(prds) if p.get("id") == prd_id), None)
        if idx is None:
            raise KeyError(f"PRD 不存在: {prd_id}")
        cur = prds[idx]
        if cur.get("status") == "approved":
            return cur
        if cur.get("status") != "draft":
            raise ValueError(f"PRD {prd_id} 状态 {cur.get('status')} 不可批准")
        cur["status"] = "approved"
        cur["updated_at"] = _now_iso()
        cur.setdefault("history", []).append(
            {"version": cur.get("version"), "at": _now_iso(), "actor": actor,
             "note": "approved"})
        pu._save_conv(root, conversation_id, doc)
        return cur


# ------------------------------------------------------------------ Artifact 投影 (不破坏文件能力)

def render_prd_markdown(prd: dict[str, Any]) -> str:
    """PRD Domain Object → PRD.md 文本投影 (现有文件 Artifact 兼容, 只读派生)。"""
    content = prd.get("content", {})
    ov = content.get("overview", {})
    lines = [f"# {prd.get('title', 'PRD')}",
             "", f"> PRD {prd.get('id')} v{prd.get('version')} | "
                 f"source understanding v{prd.get('source_product_understanding_version')} | "
                 f"status: {prd.get('status')}", ""]
    if ov.get("problem"):
        lines += ["## 概述", "", str(ov.get("problem")), ""]
    if ov.get("target_users"):
        lines += [f"- 目标用户: {ov['target_users']}"]
    if ov.get("platform"):
        lines += [f"- 平台: {ov['platform']}"]
    lines += ["", "## 功能需求", ""]
    lines += [f"- {x}" for x in content.get("functional_requirements", [])] or ["- (无)"]
    if content.get("constraints"):
        lines += ["", "## 约束", ""] + [f"- {x}" for x in content["constraints"]]
    if content.get("decisions"):
        lines += ["", "## 决策", ""] + [f"- {x}" for x in content["decisions"]]
    if content.get("future_considerations"):
        lines += ["", "## 未来考虑", ""] + [f"- {x}" for x in content["future_considerations"]]
    return "\n".join(lines) + "\n"


__all__ = [
    "PRD_STATUSES", "derive_prd_sections", "create_prd", "get_prd", "list_prds",
    "update_prd", "approve_prd", "render_prd_markdown",
]
