"""conversation · PRD 形式化（PRD Domain Foundation）—— 搬迁自 factory_console.application_formalization。

PRD 从 Product Understanding **派生**（不是独立创建、不是简单 PRD.md 文件）:
```
Product Understanding (source_product_understanding_version)
    ↓ derive_prd_sections
PRD Domain Object (versioned · 结构化 content + structured_content)
    ↓ render_prd_markdown（只读派生，不破坏现有文件 Artifact 能力）
PRD.md Artifact (可选投影)
```

记录模型:
    id: PRD-* | conversation_id | version | status: draft|approved|archived
    source_product_understanding_version: int   ← **provenance 锚点**（派生自哪个 understanding 版本）
    content / structured_content / history[{version, at, actor, note}]

存储: `<root>/conversations/{cid}.json` 内的 `conversation.prds`（与 understanding 同文档
—— 原子一致，同一会话的 PRD 版本序列完整可追）。

跨域处理（按 SSoT R3/R5）:
    · `ensure_project_binding`（建会话↔项目绑定）经 `bind_lookups()` **注入**，本域不调老区。
      未接线 → 跳过同步（与老区原语义一致: 项目建不出来不阻断 PRD 创建 ✓）
    · `_sync_prd_to_project` 保留为**本模块能力** —— 它是把 PRD 这个产出投影到
      `projects/<P-id>/product_truth/prds.json`，属本域自己的产出落地。
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import understanding as pu

PRD_STATUSES: tuple[str, ...] = ("draft", "approved", "archived")

#: 跨域钩子: 建会话↔项目绑定（bootstrap 注入）
EnsureProjectBinding = Callable[[Any, str], str]
_hooks: dict[str, Any] = {}


def bind_lookups(*, ensure_project_binding: EnsureProjectBinding | None = None) -> None:
    """注入跨域能力（bootstrap 装配时调用；None 项保持不变）。"""
    if ensure_project_binding is not None:
        _hooks["ensure_project_binding"] = ensure_project_binding


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

def _sync_prd_to_project(root: Path | str, project_id: str, prd: dict[str, Any]) -> None:
    """把 PRD 同步进项目 product_truth/prds.json ✓（铁律: 有项目属性进项目 ✓）。

    写法: 读项目文件（兼容包装/扁平两格式 ✓）→ upsert by id ✓ → 原子写（pid 临时名 ✓）
    """
    f = Path(root) / "projects" / project_id / "product_truth" / "prds.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    cur: dict[str, Any] = {}
    if f.is_file():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                # ★ 兼容两格式（读侧必须兼容 ✓ 否则读空→覆盖丢数据 ✗）
                _wrapped = d.get("prds")
                cur = _wrapped if isinstance(_wrapped, dict) else d
        except (OSError, ValueError):
            cur = {}
    cur[str(prd.get("id"))] = prd
    tmp = f.with_name(f".{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, f)


def _prds(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc.setdefault("prds", [])


def create_prd(root: Path | str, conversation_id: str, *, actor: str = "",
               title: str = "") -> dict[str, Any]:
    """从当前 Understanding 派生 PRD v1 (唯一 PRD writer 之一; draft)。

    若已有同名 draft → 抛错 (防止误解: 修改应走 update_prd 生成新 version)。
    """
    pu._ensure_conv_doc(root, conversation_id)  # noqa: SLF001 — 存在性检查
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
    # ★ 铁律（有 project_id 的进项目 ✓）: 批准前同步一份到项目 product_truth ✓
    #   失败安全: 项目建不出来 → 不阻断 PRD 创建 ✓（但要吵一声 ✓）
    _bind = _hooks.get("ensure_project_binding")
    if _bind is not None:
        try:
            _pid = _bind(root, conversation_id) or ""
            if _pid:
                rec["project_id"] = _pid
                _sync_prd_to_project(root, _pid, rec)
        except Exception as exc:  # noqa: BLE001 — 失败安全 ✓ 不阻断 ✓
            sys.stderr.write(f"  ⚠ PRD 同步到项目失败（{type(exc).__name__}: {exc}）"
                             f" —— PRD 仍在会话内 ✓ 但 UAT/交付会看不到 ✗\n")

    with pu._lock:  # noqa: SLF001 — 同包复用事务锁
        doc2 = pu._load_conv(root, conversation_id)  # noqa: SLF001
        if doc2 is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        prds = _prds(doc2)
        for p in prds:
            if p.get("status") == "draft":
                raise ValueError(
                    f"已有 draft PRD ({p['id']} v{p['version']}) — 修改请走 update_prd")
        prds.append(rec)
        pu._save_conv(root, conversation_id, doc2)  # noqa: SLF001
    return json.loads(json.dumps(rec, ensure_ascii=False))


def _structured_mapping(sections: dict[str, Any]) -> dict[str, Any]:
    """structured_content: 每 section 标记其溯源 fact (粗略 — fact id 溯源在
    content.provenance.facts 已保留; 此处保留 section → 内容列表的映射)。"""
    return {k: list(v) if isinstance(v, list) else v
            for k, v in sections.items() if k != "provenance"}


def get_prd(root: Path | str, conversation_id: str, prd_id: str) -> dict[str, Any] | None:
    doc = pu._load_conv(root, conversation_id)  # noqa: SLF001
    if doc is None:
        return None
    for p in _prds(doc):
        if p.get("id") == prd_id:
            return json.loads(json.dumps(p, ensure_ascii=False))
    return None


def list_prds(root: Path | str, conversation_id: str) -> list[dict[str, Any]]:
    doc = pu._load_conv(root, conversation_id)  # noqa: SLF001
    if doc is None:
        return []
    return [json.loads(json.dumps(p, ensure_ascii=False)) for p in _prds(doc)]


def update_prd(root: Path | str, conversation_id: str, prd_id: str, *,
               title: str = "", actor: str = "") -> dict[str, Any]:
    """修改 = 从**最新 Understanding** 重新派生 → 新 version (PRD 版本化; Test F)。

    仅 draft 可更新; approved/archived → ValueError (走新 PRD / 不原地改)。
    """
    with pu._lock:  # noqa: SLF001
        doc = pu._load_conv(root, conversation_id)  # noqa: SLF001
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
        pu._save_conv(root, conversation_id, doc)  # noqa: SLF001
        return updated


def approve_prd(root: Path | str, conversation_id: str, prd_id: str, *,
                actor: str = "") -> dict[str, Any]:
    """draft → approved (人工批准门; S49 §八 不实现完整 workflow, 只留转换)。"""
    with pu._lock:  # noqa: SLF001
        doc = pu._load_conv(root, conversation_id)  # noqa: SLF001
        if doc is None:
            raise ValueError(f"conversation 不存在: {conversation_id}")
        prds = _prds(doc)
        idx = next((i for i, p in enumerate(prds) if p.get("id") == prd_id), None)
        if idx is None:
            raise KeyError(f"PRD 不存在: {prd_id}")
        cur = prds[idx]
        # ★ 同步项目侧副本（2026-09-15 修）: 抽成本地函数, **两条路径都调** ——
        #   包括"已经是 approved 直接返回"那条, 否则历史上已经批准过、
        #   但项目侧副本还停在 draft 的 PRD 永远修不回来（幂等 ✓）。
        def _mirror() -> None:
            try:
                _pid = str(doc.get("project_id") or "")
                if _pid:
                    _sync_prd_to_project(root, _pid, cur)
            except Exception:  # noqa: BLE001 — 投影失败不阻断批准 ✓
                pass

        if cur.get("status") == "approved":
            _mirror()                      # 已是 approved: 补一次同步（幂等）
            return cur
        if cur.get("status") != "draft":
            raise ValueError(f"PRD {prd_id} 状态 {cur.get('status')} 不可批准")
        cur["status"] = "approved"
        cur["updated_at"] = _now_iso()
        cur.setdefault("history", []).append(
            {"version": cur.get("version"), "at": _now_iso(), "actor": actor,
             "note": "approved"})
        pu._save_conv(root, conversation_id, doc)  # noqa: SLF001
        # ★ 同步项目侧副本（2026-09-15 修，端到端实测暴露）:
        #   `_sync_prd_to_project` 此前**只在创建 PRD 时**调用 ⇒ 项目侧
        #   `product_truth/prds.json` 的副本永远停在 `draft`，而会话侧已 `approved`
        #   —— **同一个 PRD 两个状态**（实测: project_17daec18072e 项目侧 draft /
        #   会话侧 approved）。批准也必须同步，否则任何读项目侧的视图都会说谎。
        _mirror()
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
