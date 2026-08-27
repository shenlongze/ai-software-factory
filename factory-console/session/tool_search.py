"""factory-console/session/tool_search.py — BM25 风格动态工具检索 (S10-127 M2).

背景: 21 个静态工具每次全量塞给弱模型 → 选择压力大 → "扫代码返回文档"。
方案 (参考 Eino ToolSearch + tool-search-oss MIT):
- catalog_summary(tools): 工具名+一句话分组目录 (~400 token), 首轮注入让模型知道有什么
- discover_tools(tools, query, top_k): 词频/子串打分 → top-k 全 schema
- tool_search_schema(): 元工具 schema (模型主动搜索)

评分 (Eino 风格, 中英兼容):
  工具名拆分部分精确 == 词 → 10 · 拆分部分包含词 → 5 · 全名包含 → 3
  · 描述包含 → 2 · 关键词命中 → 4 (累加, 每词取最高, 跨词求和)

零依赖 (纯 stdlib)。"""
from __future__ import annotations

import re
from typing import Any

#: 元工具: 模型通过它按需发现工具 (首轮只给核心 + 检索结果)
TOOL_SEARCH_ID = "tool_search"


def _split_name(name: str) -> list[str]:
    """camelCase/snake_case/kebab → 词列表 (小写)。"""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = s.replace("_", " ").replace("-", " ")
    return [w for w in s.lower().split() if w]


def _query_tokens(query: str) -> list[str]:
    """查询 → 词列表 (中文整段保留做子串匹配; 英文拆 camelCase)。"""
    toks: list[str] = []
    for part in re.split(r"[\s,，。;；:：、/|!?！？]+", (query or "").lower()):
        part = part.strip()
        if not part:
            continue
        if re.search(r"[\u4e00-\u9fff]", part):
            toks.append(part)
        else:
            toks.extend(_split_name(part))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _tool_fn(tool: dict[str, Any]) -> dict[str, Any]:
    return tool.get("function") or {}


def _keywords(tool: dict[str, Any]) -> list[str]:
    meta = (tool.get("metadata") or {}).get("keywords") or []
    return [str(k).lower() for k in meta]


def _cn_bigrams(text: str, size: int = 2) -> set[str]:
    """中文 2-gram 集合 (英文/符号忽略)。"""
    cjk = re.findall(r"[\u4e00-\u9fff]+", text.lower())
    grams: set[str] = set()
    for chunk in cjk:
        if len(chunk) <= size:
            grams.add(chunk)
            continue
        for i in range(len(chunk) - size + 1):
            grams.add(chunk[i:i + size])
    return grams


def _score_token(token: str, name_parts: list[str], name_l: str, desc_l: str,
                 name_bigrams: set[str], desc_bigrams: set[str], kws: list[str]) -> int:
    best = 0
    if token in name_parts:
        best = 10
    elif any(token in p for p in name_parts):
        best = 5
    elif token in name_l:
        best = 3
    elif token in desc_l:
        best = 2
    for kw in kws:
        if token in kw or kw in token:
            best = max(best, 4)
    # 中文 bigram 召回 (整段不命中时按片段加权; 上限防噪音)
    if best < 4 and any("\u4e00" <= ch <= "\u9fff" for ch in token):
        t_bigrams = _cn_bigrams(token)
        hits = len(t_bigrams & name_bigrams) * 2 + len(t_bigrams & desc_bigrams)
        if hits > 0:
            best = max(best, min(4, hits))
    return best


def score_tool(tool: dict[str, Any], query: str) -> int:
    """单工具评分 (未命中 → 0)。整段子串 + 中文 bigram 双轨。"""
    fn = _tool_fn(tool)
    name = str(fn.get("name") or "")
    desc = str(fn.get("description") or "")
    if not name:
        return 0
    name_l = name.lower()
    desc_l = desc.lower()
    name_parts = _split_name(name)
    name_bigrams = _cn_bigrams(name)
    desc_bigrams = _cn_bigrams(desc)
    kws = _keywords(tool)
    score = 0
    for tok in _query_tokens(query):
        score += _score_token(tok, name_parts, name_l, desc_l,
                              name_bigrams, desc_bigrams, kws)
    return score


def discover_tools(
    tools: list[dict[str, Any]],
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """按 query 检索 top-k 工具 (全 schema)。query 空 → 空列表。"""
    if not tools or not (query or "").strip():
        return []
    scored = [(score_tool(t, query), t) for t in tools if score_tool(t, query) > 0]
    scored.sort(key=lambda x: (-x[0], str((x[1].get("function") or {}).get("name") or "")))
    return [t for _, t in scored[:top_k]]


def catalog_summary(tools: list[dict[str, Any]], max_len: int = 2200) -> str:
    """工具目录摘要 (首轮注入: 让模型知道有哪些工具可搜)。"""
    lines: list[str] = ["【可用工具目录】(工具较多, 按需用 tool_search 搜索具体工具的完整参数)"]
    for t in tools:
        fn = _tool_fn(t)
        name = str(fn.get("name") or "")
        desc = str(fn.get("description") or "")
        if not name:
            continue
        one = desc.split("。")[0].split(";")[0].split(";")[0][:40]
        lines.append(f"- {name}: {one}")
    out = "\n".join(lines)
    return out if len(out) <= max_len else out[:max_len] + "…"


def tool_search_schema() -> dict[str, Any]:
    """tool_search 元工具 schema (模型主动按需发现工具)。"""
    return {
        "type": "function",
        "function": {
            "name": TOOL_SEARCH_ID,
            "description": "按关键词搜索可用工具, 返回匹配的工具名列表; 需要调某个工具但不确定它的准确名字/参数时用",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "描述你要做什么, 如 '扫描项目' / '读取代码' / '查看文档'"},
                    "max_results": {"type": "integer", "description": "最多返回几个 (默认 5)"},
                },
                "required": ["query"],
            },
        },
    }


def expand_matches(
    tools: list[dict[str, Any]],
    visible: list[dict[str, Any]],
    matched_names: list[str],
) -> list[dict[str, Any]]:
    """把命中的工具 schema 加入可见列表 (累积, 不重复)。"""
    have = {str((t.get("function") or {}).get("name") or "") for t in visible}
    out = list(visible)
    for t in tools:
        name = str((t.get("function") or {}).get("name") or "")
        if name in matched_names and name not in have:
            out.append(t)
            have.add(name)
    return out
