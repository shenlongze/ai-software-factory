"""数据流程图（DFD）投影 —— 数据长什么样、谁碰它、它跟谁有关系。

【为什么需要它】Founder: "还是堆砌，没有形式流程图，**没有数据流程**，
功能和功能之间看不到任何关系"。
⇒ 功能链路图回答"功能之间怎么串"；本投影回答"**数据**怎么串"（第二张图）。

【★ 铁律: 数据源必须是真实的, 不许编 —— 三个来源, 按可信度排序】
  ① declared（声明）: 节点字段 `data_entities` —— 由产线（拆解时）声明"本模块读/写哪些实体"。
     最可信: 是系统记录的, 可追溯。**目前产线还没产出 ⇒ 计数为 0（如实报, 不假装有）**。
  ② schema（实体关系）: 项目内真实数据模型文件（`*.prisma` 的 model + @relation / *.sql 的
     CREATE TABLE + FOREIGN KEY）⇒ 实体之间的真实关系。**这是"实体怎么连", 不是"模块怎么流"**,
     所以在图上单独一张, 不冒充流程。
  ③ evidence（线索）: 模块文案里出现的实体名 ⇒ ★ 只作【线索】(虚线), 且**必须报覆盖率 +
     点名未覆盖的模块**。实测真树覆盖 7/13 且会把"商品管理"漏成只碰 Sku ⇒ 绝不能当真话用。

【判据】任何"数据流"渲染之前先问: 这条边的来源是【声明/DDL/文案匹配】哪一种?
  答不出 ⇒ 不许画。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

#: 数据模型文件的搜索范围（项目工作区内）—— 只认这些, 不猜
_SCHEMA_GLOBS = ("**/*.prisma", "**/migrations/**/*.sql")
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next"}


def _iter_files(project_dir: Path) -> list[Path]:
    out: list[Path] = []
    for pat in _SCHEMA_GLOBS:
        for f in project_dir.glob(pat):
            if any(part in _SKIP_DIRS for part in f.parts):
                continue
            out.append(f)
    return sorted(set(out))


def extract_entities(project_dir: Path | str | None) -> dict[str, Any]:
    """从项目工作区抽【真实】实体与实体关系 —— 读 DDL, 不猜。

    返回 {source_file, entities:{名字: 被引用次数}, relations:[{from,to,via}]}。
    没找到模型文件 ⇒ 空结果（调用方据此说"没有数据模型可依据", 而不是编一张图）。
    """
    empty: dict[str, Any] = {"source_file": "", "entities": {}, "relations": []}
    if not project_dir:
        return empty
    base = Path(project_dir)
    if not base.is_dir():
        return empty

    for f in _iter_files(base):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if f.suffix == ".prisma":
            models = dict(re.findall(r"^model (\w+) \{([^}]*)\}", text, re.M | re.S))
            if not models:
                continue
            relations: list[dict[str, str]] = []
            for model, body in models.items():
                for line in body.splitlines():
                    rel = re.search(r"@relation\([^)]*\)", line)
                    if not rel:
                        continue
                    parts = line.split()
                    target = parts[1] if len(parts) > 1 else ""
                    if target not in models:
                        continue
                    fk = re.search(r"fields:\s*\[([^\]]+)\]", rel.group(0))
                    rf = re.search(r"references:\s*\[([^\]]+)\]", rel.group(0))
                    relations.append({
                        "from": model, "to": target,
                        "via": (fk.group(1) if fk else "?").strip(),
                        "ref": (rf.group(1) if rf else "id").strip(),
                    })
            refs = {m: 0 for m in models}
            for r in relations:
                refs[r["to"]] = refs.get(r["to"], 0) + 1
            return {"source_file": str(f.relative_to(base)), "entities": refs,
                    "relations": relations}

        # SQL 兜底: CREATE TABLE + FOREIGN KEY
        tables = re.findall(r'CREATE TABLE (?:IF NOT EXISTS )?"?(\w+)"?', text, re.I)
        if not tables:
            continue
        relations = []
        for a, b in re.findall(
                r'ALTER TABLE "?(\w+)"?[^;]*?FOREIGN KEY[^;]*?REFERENCES "?(\w+)"?', text, re.I):
            relations.append({"from": a, "to": b, "via": "", "ref": "id"})
        refs = {t: 0 for t in tables}
        for r in relations:
            refs[r["to"]] = refs.get(r["to"], 0) + 1
        return {"source_file": str(f.relative_to(base)), "entities": refs,
                "relations": relations}
    return empty


def _module_text(node: dict[str, Any], by_parent: dict[str, list[dict]], deep: bool = True) -> str:
    """模块的文案（默认含子树）—— 用于"线索"匹配。"""
    parts = [str(node.get("title") or ""), str(node.get("scope") or ""),
             str(node.get("acceptance") or "")]
    if deep:
        stack = [str(node.get("id") or "")]
        while stack:
            for child in by_parent.get(stack.pop(), []):
                parts += [str(child.get("title") or ""), str(child.get("scope") or ""),
                          str(child.get("acceptance") or "")]
                stack.append(str(child.get("id") or ""))
    return " ".join(parts)


def build_data_flow(tree: dict[str, Any], project_dir: Path | str | None = None) -> dict[str, Any]:
    """★ 投影 C: 数据流程图（数据实体 + 谁碰它 + 实体之间怎么连）。

    只出顶层模块（与功能链路图同一层粒度 —— 两个投影必须能互相对上）。
    返回里的每条 module_link 都带 kind: declared（声明）/ evidence（线索）。
    """
    from ai_factory_os.services.work import user_view as UV

    nodes = tree.get("nodes") or []
    doms = [n for n in nodes if n.get("kind") == "domain"]
    dom_ids = {str(n.get("id") or "") for n in doms}
    tops = [n for n in doms if str(n.get("parent_id") or "") not in dom_ids]
    if not tops:                                    # 兜底同 build_flow（不退化成空视图）
        tops = [n for n in doms if not str(n.get("parent_id") or "")] or list(doms)

    by_parent: dict[str, list[dict]] = {}
    for n in nodes:
        by_parent.setdefault(str(n.get("parent_id") or ""), []).append(n)

    schema = extract_entities(project_dir)
    ddl_names = list(schema["entities"].keys())      # ★ 真实清单（来自 DDL）—— 只用于"线索"匹配
    lower = {e.lower(): e for e in ddl_names}

    links: list[dict[str, Any]] = []
    missing: list[str] = []
    for m in tops:
        mid, mname = str(m.get("id") or ""), UV.node_name(m)
        declared = [str(d.get("name") or "") for d in (m.get("data_entities") or [])
                    if isinstance(d, dict)]
        if declared:
            for name in declared:
                links.append({"module_id": mid, "module": mname, "entity": name,
                              "kind": "declared"})
            continue
        # 声明没有 ⇒ 退到线索（虚线）, 且如实记下"这个模块只有线索/没有线索"
        text = _module_text(m, by_parent).lower()
        hits = [canon for low, canon in lower.items() if re.search(r"\b" + low, text)]
        if hits:
            for name in sorted(hits):
                links.append({"module_id": mid, "module": mname, "entity": name,
                              "kind": "evidence"})
        else:
            missing.append(mname)

    with_entity = len({x["module_id"] for x in links})
    entities_used = sorted({x["entity"] for x in links})
    declared_count = sum(1 for x in links if x["kind"] == "declared")
    # ★ 声明过的实体也要进【实体清单】—— 否则图上那条"声明线"会因为实体列里没有它而被静默丢掉
    declared_only = sorted({x["entity"] for x in links if x["kind"] == "declared"} - set(ddl_names))
    all_names = ddl_names + declared_only
    available = bool(all_names)
    hint = "" if declared_count else (
        "还没有产线声明（节点字段 data_entities 为空）⇒ 模块与实体之间的线目前只是【线索】, "
        "不是系统记录的事实。产线在拆解时声明后, 这些线会变成实线。")
    return {
        "available": available,
        "has_schema": bool(ddl_names),
        "source_file": schema["source_file"],
        # ★ 全部顶层模块都给（含没有任何线的那些）—— 缺口要让它在【图上】看得见, 不是只写在提示条里
        "modules": [{"id": str(m.get("id") or ""), "name": UV.node_name(m)} for m in tops],
        "entities": [{"name": n, "refs": schema["entities"].get(n, 0),
                      "from": "schema" if n in schema["entities"] else "declared"}
                     for n in all_names],
        "entities_used": entities_used,
        "relations": schema["relations"],
        "module_links": links,
        "coverage": {"modules": len(tops), "with_entity": with_entity, "missing": missing},
        "declared_count": declared_count,
        "evidence_count": sum(1 for x in links if x["kind"] == "evidence"),
        "hint": hint,
    }
