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

#: 一节里可能装"表/实体"的键名（LLM 产出形状不定, 契约只要求"非空对象"）
_ENT_KEYS = ("tables", "models", "entities", "collections", "schemas", "table", "model")
#: 这些键下面是【字段/结构】而不是实体名（防止把 "fields" 当实体; 守卫抓过我漏这条）
_NON_ENT_KEYS = ("fields", "columns", "indexes", "indices", "relations", "keys", "primary",
                 "foreign", "constraints", "attributes", "props", "properties", "description",
                 "note", "notes", "type", "types", "options", "config", "meta")
_MAX_ENTS = 80          #: 防一次倒几百个（设计制品里塞全库）


def _clean_name(x: Any) -> str:
    s = str(x or "").strip().strip("\"'`,;")
    if "." in s:                      # "public.users" / "db.users" ⇒ 取尾段
        s = s.split(".")[-1]
    return s


def entities_from_design(section: Any) -> list[str]:
    """从架构设计制品的 `database_design` 节里取【实体/表名】—— ★ 从零场景的第一来源。

    为什么需要它（本轮实跑踩到）: DDL 是**任务要做出来的东西**, 从零跑真实场景时还不存在
    ⇒ 只认 DDL 就等于"数据流程图在这一环必然空着"（`declare` 只能诚实拒绝）。
    而架构设计制品里本来就有 `database_design` 这一节（契约: "对象, 模型/表结构"）。

    形状不定（LLM 产出）⇒ 容忍多种写法（按可信度从高到低）:
      ① {"tables": [{"name": "User", ...}, ...]} / {"models": {...}} …
      ② {"User": {字段…}, "Order": {…}}   ← 以实体名为键
      ③ [{"name": "User"}, "Order", ...]  ← 直接列表
      ④ 兜底: 文本里形如 `CREATE TABLE x` / `表名: users` / `"name": "User"` 也捞
    去重保序; 太短的名字（<2）丢掉（防把 "id"/"a" 当实体）。
    """
    names: list[str] = []
    seen: set[str] = set()

    def _add(v: Any) -> None:
        s = _clean_name(v)
        if len(s) >= 2 and s.lower() not in ("table", "model", "entity", "name", "true", "false") \
                and s not in seen:
            seen.add(s)
            names.append(s)

    def _walk(o: Any, depth: int = 0, in_container: bool = False, top: bool = False) -> None:
        """★ 只在【容器里】和【顶层】取实体名 —— 绝不下探进实体的字段描述。

        真跑踩到（第一版）: 下探时把字符串一律当实体 ⇒ 53 个"实体"里混进散文
        （"本设计包含…"）和字段类型（"BIGINT UNSIGNED AUTO_INCREMENT"）✗
        """
        if depth > 3 or len(names) >= _MAX_ENTS:
            return
        if isinstance(o, str):
            if top:                                     # 顶层裸字符串才算（列表里见下）
                _add(o)
            return
        if isinstance(o, list):
            for it in o:
                if isinstance(it, str) and (top or in_container):
                    _add(it)                            # 容器里/顶层: 字符串 = 实体名
                else:
                    _walk(it, depth + 1, in_container, False)
            return
        if isinstance(o, dict):
            # 这一层有"表/模型"容器 ⇒ 其它同级键（overview/conventions/…）是结构性说明, 不是实体
            has_container = any(str(k).lower() in _ENT_KEYS for k in o)
            for k, v in o.items():
                kl = str(k).lower()
                if kl in _ENT_KEYS:                      # ① 键名就是"表/模型"
                    if isinstance(v, str):
                        _add(v)                          # {"table": "users"} / {"model": "User"}
                    else:
                        _walk(v, depth + 1, True, False)
                elif kl in _NON_ENT_KEYS:
                    continue                             # 字段/索引/关系…: 不是实体
                elif isinstance(v, str) and in_container and kl in ("name", "table", "entity", "model"):
                    _add(v)                              # ② 容器里 {"name": "User"}
                elif isinstance(v, (dict, list)) and (in_container or not has_container):
                    _add(k)                              # ③ 容器里/整节以实体名为键
                    _walk(v, depth + 1, True, False)
                # 其余一律不下探（散文/字段说明 ⇒ 不取）
            return

    _walk(section, top=True)
    if not names and section:                            # ④ 兜底: 当文本捞
        text = str(section)
        for pat in (r"CREATE\s+TABLE\s+\"?(\w+)\"?", r"表名?\s*[:：]\s*(\w+)",
                    r"\"name\"\s*:\s*\"(\w+)\""):
            for m in re.findall(pat, text, re.I):
                _add(m)
    return names[:_MAX_ENTS]


def entity_catalog(root: Path | str, project_id: str,
                   workspace_dir: Path | str | None = None) -> dict[str, Any]:
    """★ 实体清单的**唯一解析处**（declare / 数据流程图 都走这里, 免得两处各认一套）。

    来源优先级（★ 本轮实跑踩到后改的）:
      ① **架构设计制品的 `database_design` 节** —— 从零场景的权威依据（DDL 还没被做出来时也在）
      ② 项目工作区里的 DDL（`*.prisma` / `*.sql`）—— 真做出来之后可用（还能给实体关系）
      ③ 都没有 ⇒ names 为空（调用方据此诚实拒绝, 绝不编）

    返回 {names:[...], source:"design:<id>"|"ddl:<file>"|"", detail:"人话", relations:[...]}
    """
    out: dict[str, Any] = {"names": [], "source": "", "detail": "", "relations": []}
    # ① 设计制品
    try:
        from ai_factory_os.services.organization.projects import ProjectStore

        store = ProjectStore(Path(root) / "org")
        cands = [a for a in store.list_artifacts()
                 if str(getattr(a, "project_id", "") or "") == str(project_id or "")
                 and "design" in str(getattr(a, "type", "") or "").lower()]
        for art in reversed(cands):                      # 取最新的那份
            meta = dict(getattr(art, "metadata", {}) or {})
            names = entities_from_design(meta.get("database_design"))
            if names:
                out.update(names=names, source=f"design:{getattr(art, 'id', '')}",
                           detail=f"架构设计制品的 database_design 节（{len(names)} 个实体）")
                return out
    except Exception:  # noqa: BLE001 — 拿不到设计制品 ⇒ 往下走（DDL）
        pass
    # ② DDL
    base = Path(workspace_dir) if workspace_dir else (Path(root) / "projects" / str(project_id or ""))
    if project_id or workspace_dir:
        got = extract_entities(base)
        if got.get("entities"):
            out.update(names=list(got["entities"].keys()),
                       source=f"ddl:{got.get('source_file') or ''}",
                       detail=f"项目里的数据模型文件（{got.get('source_file') or ''}）",
                       relations=list(got.get("relations") or []))
    return out


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
