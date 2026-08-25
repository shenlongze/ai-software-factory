"""factory-console/retrieval/knowledge_store.py — K-6 项目级 RAG KnowledgeStore (S10-123)。

M5-2/B-8 核心: 项目文档入库 (README/docs/PRD/工程/质量/经验 → 片段+
元数据索引)
+ 三级分档 (raw 原始片段 / summary 章节摘要·目录 / knowledge 跨文档知识条目)
+ 增量重建 (mtime) + 确定性词频检索 (纯规则零依赖, 同输入同输出)。

- 扫描: 复用 board.list_project_docs / read_docs_config (多目录+扩展名), 不重造
- 索引: workspace/.factory_rag/<slug>/index.json — 独立目录, 零污染项目文件
- 失败安全: 单个文件损坏/二进制 → 跳过 + 记录, 不中断
- 分档规则 (确定性):
  * raw      — md/txt 段落 (正文片段)
  * summary  — md/txt 标题行 (章节目录/摘要) + json 顶层键
  * knowledge— json 键值条目 (工程/质量/产品数据) + knowledge 类文档
               (文件名含 knowledge/经验/lessons/learnings/最佳实践 的段落)
  * external — 外挂适配器命中 (M5-3, tier 标注诚实)
- 检索: 词频 (TF) 打分 — ASCII 词 + CJK 二元子词; reason 可解释
  ("命中关键词 X(tf=N) in 文件 F 片段 C"); embedding/LLM 仅可选
  (query(scorer=...) 注入点, 默认规则始终可用, 降级不崩)
- E-5: rag_query 入口发射 RAG_QUERY 审计事件 (trace_id 由 K-4 contextvar 自动填充)

诚实标注:
- 真实 embedding/LLM 检索未接入 — 纯规则词频为主; scorer 注入点就绪
  (接口先行)
- 二进制文档 (doc/docx) 与损坏文件无法确定性检索 → 跳过并记录 (失败安全)
- CJK 整句短语 (如 "如何部署" 连写) 可命中; 文档内短语被空格/换行拆散
  时不命中
  (词频子词匹配的固有局限, 如实标注)

设计: docs/sprint10/S10-123-k6-rag-plan.md §1-§2
边界:
- 纯标准库 (json/re/dataclasses/hashlib), 零新依赖
- 确定性: 同输入同输出 (打分/排序稳定, 无随机)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

__all__ = [
    "KnowledgeHit",
    "IngestResult",
    "KnowledgeStore",
    "rag_query",
]

#: 分档取值 (确定性分类)
TIER_RAW = "raw"              # 原始文档片段 (段落)
TIER_SUMMARY = "summary"      # 章节摘要/目录 (标题行 / json 顶层键)
TIER_KNOWLEDGE = "knowledge"  # 跨文档知识条目 (json 键值 / 知识类文档)
TIER_EXTERNAL = "external"    # 外挂适配器命中 (M5-3)

#: 默认分档 (查询全开)
DEFAULT_TIERS: tuple[str, ...] = (TIER_RAW, TIER_SUMMARY, TIER_KNOWLEDGE)

#: knowledge 类文档名模式 (段落 → knowledge 分档)
_KNOWLEDGE_NAME_PATTERNS: tuple[str, ...] = (
    "knowledge", "经验", "lessons", "learnings", "lesson", "learning",
    "best-practices", "最佳实践", "best_practice", "knowhow", "心得",
)

#: 文本扩展名 (可确定性分块)
_TEXT_EXTS: frozenset[str] = frozenset({".md", ".txt", ".markdown", ".rst"})
#: JSON 扩展名 (键值条目 → knowledge + summary)
_JSON_EXTS: frozenset[str] = frozenset({".json"})
#: 单块最大字符数 (超长段落切分, 防索引无界)
_MAX_CHUNK_LEN = 1000
#: 单文件最大块数 (防超大 json/文档拖垮索引)
_MAX_CHUNKS_PER_FILE = 500
#: 单条知识片段最大字符数
_MAX_FRAGMENT_LEN = 500

#: 索引文件版本 (结构变更 → +1, 旧索引忽略重建)
_INDEX_VERSION = 1


def _now_iso() -> str:
    """UTC 当前时间 ISO (索引元数据, 确定性无关)。"""
    return datetime.now(timezone.utc).isoformat()


def _is_knowledge_file(name: str) -> bool:
    """文件名是否 knowledge 类 (段落 → knowledge 分档)。"""
    lower = str(name or "").lower()
    return any(p in lower for p in _KNOWLEDGE_NAME_PATTERNS)


# ================================================================== 数据模型


@dataclass
class KnowledgeHit:
    """检索命中 (可解释, 引用源可追溯)。

    chunk_id: 索引内唯一块 id; file: 源文件相对名; fragment: 命中片段;
    score: 0-1 相关度 (确定性); tier: raw/summary/knowledge/external;
    reason: 可解释原因 ("命中关键词 X(tf=N) in 文件 F 片段 C");
    source: 命中来源 ("local" 或 "external:<name>")。
    """

    chunk_id: str
    file: str
    fragment: str
    score: float = 0.0
    tier: str = TIER_RAW
    reason: str = ""
    source: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file": self.file,
            "fragment": self.fragment,
            "score": round(float(self.score), 4),
            "tier": self.tier,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass
class IngestResult:
    """入库结果 (ingest / incremental_ingest 返回, 失败安全)。"""

    slug: str
    files_scanned: int = 0
    chunks_indexed: int = 0
    changed_files: list[str] = field(default_factory=list)
    removed_files: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)  # {file, reason}
    tiers: dict[str, int] = field(default_factory=dict)
    incremental: bool = False
    index_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "files_scanned": self.files_scanned,
            "chunks_indexed": self.chunks_indexed,
            "changed_files": list(self.changed_files),
            "removed_files": list(self.removed_files),
            "skipped": [dict(s) for s in self.skipped],
            "tiers": dict(self.tiers),
            "incremental": self.incremental,
            "index_path": self.index_path,
        }


# ================================================================== 确定性词频打分


_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-zA-Z0-9_]+")


def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.fullmatch(str(text or "")))


def _terms(text: str) -> list[str]:
    """token 化: ASCII 词 + CJK 连续段 (小写, 去重保序)。"""
    lowered = str(text or "").lower()
    tokens = _ASCII_RE.findall(lowered) + _CJK_RE.findall(lowered)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _query_terms(question: str) -> list[str]:
    """查询词: ASCII 词 + CJK 二元子词 (连续段≥2 拆二元组, 提高召回)。

    - 文档含整句 "支付系统" → 子词 支付/付系/系统 全部命中 (tf 高)
    - 文档含 "支付 系统" (被空格拆散) → 子词 支付/系统 命中 (仍可召回)
    确定性: 同输入同输出。
    """
    lowered = str(question or "").lower()
    tokens = _ASCII_RE.findall(lowered) + _CJK_RE.findall(lowered)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        cands = []
        if _is_cjk(t) and len(t) >= 2:
            cands = [t[i : i + 2] for i in range(len(t) - 1)]
        elif t:
            cands = [t]
        for c in cands:
            if c and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def _tf_score(fragment: str, question: str) -> tuple[float, str, list[tuple[str, int]]]:
    """确定性词频打分 → (score 0-1, reason, matched[(term, tf)])。

    score = 1 - 1/(1 + Σtf) — 单调于总词频, 无随机; 0 命中 → score 0。
    reason: "命中关键词 支付(tf=2)、系统(tf=1) in 片段 <chunk>" (调用方补文件)。
    """
    lowered = str(fragment or "").lower()
    matched: list[tuple[str, int]] = []
    total = 0
    for term in _query_terms(question):
        tf = lowered.count(term)
        if tf > 0:
            matched.append((term, tf))
            total += tf
    if total <= 0:
        return 0.0, "", []
    score = round(1.0 - 1.0 / (1.0 + total), 4)
    kw = "、".join(f"{t}(tf={n})" for t, n in matched[:5])
    if len(matched) > 5:
        kw += f" 等 {len(matched)} 词"
    reason = f"命中关键词 {kw}"
    return score, reason, matched


# ================================================================== 分块 (确定性)


def _split_paragraphs(lines: list[str], max_len: int) -> list[str]:
    """段落 → 块 (空行分隔; 超长段按 max_len 硬切; 空块丢弃)。"""
    chunks: list[str] = []
    para: list[str] = []
    for line in lines:
        if line.strip():
            para.append(line)
        else:
            if para:
                chunks.append("\n".join(para))
                para = []
    if para:
        chunks.append("\n".join(para))
    out: list[str] = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        while len(c) > max_len:
            out.append(c[:max_len])
            c = c[max_len:]
        out.append(c)
    return out


def _flatten_json(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    """json → 叶子 (key, value) 条目 (确定性深度优先, dict/list 递归)。"""
    items: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                items.extend(_flatten_json(v, key))
            else:
                if v is None or str(v) == "":
                    continue
                items.append((key, str(v)))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            key = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                items.extend(_flatten_json(v, key))
            else:
                if v is None or str(v) == "":
                    continue
                items.append((key, str(v)))
    return items


def _chunk_document(
    rel_name: str, content: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """文本文档 → 块 (raw 段落 + summary 标题行; knowledge 类文件段落
    → knowledge)。"""
    suffix = Path(rel_name).suffix.lower()
    chunks: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    try:
        text = str(content or "")
    except Exception as exc:  # noqa: BLE001 — 失败安全
        skipped.append({"file": rel_name, "reason": f"读取失败: {exc}"})
        return chunks, skipped
    is_knowledge = _is_knowledge_file(rel_name)
    lines = text.splitlines()
    para: list[str] = []
    seq = 0

    def _emit(seg: str, tier: str) -> None:
        nonlocal seq
        for part in _split_paragraphs([seg], _MAX_FRAGMENT_LEN):
            seq += 1
            chunks.append({
                "chunk_id": f"{rel_name}:{seq}",
                "file": rel_name,
                "tier": tier,
                "fragment": part,
                "start": 0,
            })

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") and suffix in (".md", ".markdown"):
            if para:
                _emit("\n".join(para), TIER_KNOWLEDGE if is_knowledge else TIER_RAW)
                para = []
            _emit(stripped, TIER_SUMMARY)  # 标题行 → summary (章节目录/摘要)
        elif not stripped:
            if para:
                _emit("\n".join(para), TIER_KNOWLEDGE if is_knowledge else TIER_RAW)
                para = []
        else:
            para.append(line)
    if para:
        _emit("\n".join(para), TIER_KNOWLEDGE if is_knowledge else TIER_RAW)
    return chunks, skipped


def _chunk_json(rel_name: str, content: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """json 文档 → summary (顶层键) + knowledge (叶子键值条目)。"""
    chunks: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    try:
        data = json.loads(str(content or ""))
    except Exception as exc:  # noqa: BLE001 — 失败安全
        skipped.append({"file": rel_name, "reason": f"JSON 解析失败: {exc}"})
        return chunks, skipped
    if not isinstance(data, (dict, list)):
        return chunks, skipped
    # summary: 顶层键 (章节/目录)
    keys = list(data.keys()) if isinstance(data, dict) else [f"[{i}]" for i in range(len(data))]
    for i, key in enumerate(keys):
        if i >= _MAX_CHUNKS_PER_FILE:
            break
        chunks.append({
            "chunk_id": f"{rel_name}:s{i + 1}",
            "file": rel_name,
            "tier": TIER_SUMMARY,
            "fragment": str(key),
            "start": 0,
        })
    # knowledge: 叶子键值条目
    for i, (key, value) in enumerate(_flatten_json(data)):
        if i >= _MAX_CHUNKS_PER_FILE:
            break
        fragment = f"{key}: {value}"[:_MAX_FRAGMENT_LEN]
        chunks.append({
            "chunk_id": f"{rel_name}:k{i + 1}",
            "file": rel_name,
            "tier": TIER_KNOWLEDGE,
            "fragment": fragment,
            "start": 0,
        })
    return chunks, skipped


def _chunk_file(rel_name: str, content: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """单文件 → 块 (按扩展名分发; 不支持的扩展名 → skipped 如实标注)。"""
    suffix = Path(rel_name).suffix.lower()
    if suffix in _JSON_EXTS:
        return _chunk_json(rel_name, content)
    if suffix in _TEXT_EXTS:
        return _chunk_document(rel_name, content)
    return [], [{"file": rel_name,
                 "reason": f"扩展名 {suffix or '(无)'} 暂不支持确定性检索"}]


# ================================================================== KnowledgeStore


class KnowledgeStore:
    """项目级 RAG 知识库 (M5-2/B-8): 入库/增量/检索 三级分档。

    workspace: 工厂数据根 (CLI data_dir / API factory_root);
    slug: 项目标识; 索引独立目录 workspace/.factory_rag/<slug>/index.json。
    """

    def __init__(self, workspace: Path | str, slug: str) -> None:
        self.workspace = Path(workspace)
        self.slug = Path(str(slug or "")).name
        self.index_path = self.workspace / ".factory_rag" / self.slug / "index.json"

    # ------------------------------------------------------------ 索引 IO (失败安全)

    def _load_index(self) -> dict[str, Any]:
        """读回索引 (缺失/损坏 → {}, 失败安全)。"""
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("version") == _INDEX_VERSION:
                return data
        except (OSError, json.JSONDecodeError):  # noqa: BLE001
            pass
        return {}

    def _save_index(self, index: dict[str, Any]) -> bool:
        """原子写索引 (tmp + os.replace; 失败 → False, 不抛)。"""
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.index_path)
            return True
        except OSError:  # noqa: BLE001 — 失败安全
            return False

    # ------------------------------------------------------------ 扫描 (复用 board)

    def _scan_docs(self) -> list[dict[str, Any]]:
        """复用 board.list_project_docs (read_docs_config 多目录+扩展名扫描)。

        只取 exists=True 的真实文件; 返回 {file, path, mtime, size}。
        失败安全: board 扫描异常 → [] (不中断)。
        """
        from ..session import board  # 延迟导入 (避免循环依赖)

        docs: list[dict[str, Any]] = []
        try:
            entries = board.list_project_docs(self.workspace, self.slug)
        except Exception:  # noqa: BLE001 — 失败安全
            return []
        for d in entries:
            if not d.get("exists"):
                continue
            rel = str(d.get("name") or "")
            src = str(d.get("source_dir") or "")
            path = Path(src) / rel if src else Path(rel)
            try:
                st = path.stat()
            except OSError:  # noqa: BLE001 — 失败安全
                continue
            docs.append({
                "file": rel,
                "path": path,
                "mtime": st.st_mtime,
                "size": st.st_size,
            })
        docs.sort(key=lambda d: d["file"])  # 确定性顺序
        return docs

    def _tally_tiers(self, chunks: list[dict[str, Any]]) -> dict[str, int]:
        tiers: dict[str, int] = {}
        for c in chunks:
            tiers[str(c.get("tier") or TIER_RAW)] = tiers.get(str(c.get("tier") or TIER_RAW), 0) + 1
        return tiers

    # ------------------------------------------------------------ 入库

    def ingest(self) -> IngestResult:
        """全量入库: 扫描全部项目文档 → 分块 → 索引 (独立目录, 零污染)。

        失败安全: 单文件损坏/二进制 → 跳过 + 记录, 不中断。
        """
        result = IngestResult(slug=self.slug, incremental=False,
                              index_path=str(self.index_path))
        files = self._scan_docs()
        chunks: list[dict[str, Any]] = []
        files_map: dict[str, dict[str, Any]] = {}
        for f in files:
            rel = f["file"]
            try:
                content = f["path"].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:  # noqa: BLE001 — 失败安全
                result.skipped.append({"file": rel, "reason": f"读取失败: {exc}"})
                continue
            file_chunks, skipped = _chunk_file(rel, content)
            if len(chunks) + len(file_chunks) > 20000:  # 防索引无界
                result.skipped.append({"file": rel, "reason": "索引上限 20000 块, 跳过"})
                continue
            chunks.extend(file_chunks)
            result.skipped.extend(skipped)
            files_map[rel] = {"mtime": f["mtime"], "size": f["size"]}
        result.files_scanned = len(files)
        result.chunks_indexed = len(chunks)
        result.changed_files = sorted(files_map.keys())
        result.tiers = self._tally_tiers(chunks)
        index = {
            "version": _INDEX_VERSION,
            "slug": self.slug,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "files": files_map,
            "chunks": chunks,
            "skipped": result.skipped,
        }
        if not self._save_index(index):
            result.skipped.append({"file": ".factory_rag", "reason": "索引写入失败"})
        return result

    def incremental_ingest(self) -> IngestResult:
        """增量重建: 只重扫 mtime/size 变更文件; 未变更文件块保留。

        - 新增/变更文件 → 重新分块; 删除文件 → 其块移除
        - 索引缺失/损坏 → 退化为全量 ingest (失败安全)
        """
        result = IngestResult(slug=self.slug, incremental=True,
                              index_path=str(self.index_path))
        old = self._load_index()
        if not old:
            full = self.ingest()
            full.incremental = True
            return full
        files = self._scan_docs()
        old_files = old.get("files") or {}
        old_chunks = [c for c in (old.get("chunks") or []) if isinstance(c, dict)]
        # 变更集: 新增 + mtime/size 变化
        changed: list[str] = []
        current_map: dict[str, dict[str, Any]] = {}
        for f in files:
            rel = f["file"]
            cur = {"mtime": f["mtime"], "size": f["size"]}
            current_map[rel] = cur
            prev = old_files.get(rel)
            if prev is None or prev.get("mtime") != f["mtime"] or prev.get("size") != f["size"]:
                changed.append(rel)
        removed = [rel for rel in old_files if rel not in current_map]
        result.changed_files = sorted(changed)
        result.removed_files = sorted(removed)
        # 重扫变更文件
        new_chunks: list[dict[str, Any]] = []
        for rel in sorted(changed):
            path = None
            for f in files:
                if f["file"] == rel:
                    path = f["path"]
                    break
            if path is None:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:  # noqa: BLE001 — 失败安全
                result.skipped.append({"file": rel, "reason": f"读取失败: {exc}"})
                continue
            file_chunks, skipped = _chunk_file(rel, content)
            new_chunks.extend(file_chunks)
            result.skipped.extend(skipped)
        # 保留未变更文件块; 变更文件旧块移除 (只留新块), 删除文件块移除
        dropped = set(removed) | set(changed)
        kept = [c for c in old_chunks if c.get("file") not in dropped]
        chunks = kept + [c for c in new_chunks]
        result.files_scanned = len(files)
        result.chunks_indexed = len(chunks)
        result.tiers = self._tally_tiers(chunks)
        index = {
            "version": _INDEX_VERSION,
            "slug": self.slug,
            "created_at": old.get("created_at", _now_iso()),
            "updated_at": _now_iso(),
            "files": current_map,
            "chunks": chunks,
            "skipped": (old.get("skipped") or []) + result.skipped,
        }
        if not self._save_index(index):
            result.skipped.append({"file": ".factory_rag", "reason": "索引写入失败"})
        return result

    # ------------------------------------------------------------ 检索 (确定性)

    def query(
        self,
        question: str,
        *,
        tiers: Optional[list[str]] = None,
        top_k: int = 5,
        scorer: Optional[Callable[[dict[str, Any], str], float]] = None,
    ) -> list[KnowledgeHit]:
        """确定性检索: 词频打分 → 分档过滤 → 排序 → Top-K。

        - tiers: None → 全部分档 (raw/summary/knowledge); 指定 → 只查该分档
        - scorer: 可选注入 (embedding/LLM 接入点 — 默认规则始终可用, 降级不崩)
        - 返回 KnowledgeHit (chunk_id/file/fragment/score/tier/reason/source)
        - 同输入同输出: 排序键 (-score, file, chunk_id) 稳定
        """
        question = str(question or "")
        if not question.strip():
            return []
        index = self._load_index()
        chunks = [c for c in (index.get("chunks") or []) if isinstance(c, dict)]
        if not chunks:
            return []
        tier_set = {str(t) for t in (tiers or DEFAULT_TIERS)}
        if not tier_set:
            return []
        scored: list[tuple[float, KnowledgeHit]] = []
        for c in chunks:
            if str(c.get("tier") or "") not in tier_set:
                continue
            fragment = str(c.get("fragment") or "")
            file_name = str(c.get("file") or "")
            chunk_id = str(c.get("chunk_id") or "")
            score, reason, _ = _tf_score(fragment, question)
            if scorer is not None:
                try:
                    score = float(scorer(c, question) or 0.0)
                except Exception:  # noqa: BLE001 — 降级不崩: 注入打分异常 → 规则
                    score, reason, _ = _tf_score(fragment, question)
            if score <= 0:
                continue
            reason = f"{reason} in 文件 {file_name} 片段 {chunk_id}"
            scored.append((score, KnowledgeHit(
                chunk_id=chunk_id,
                file=file_name,
                fragment=fragment,
                score=score,
                tier=str(c.get("tier") or TIER_RAW),
                reason=reason,
                source="local",
            )))
        scored.sort(key=lambda x: (-x[0], x[1].file, x[1].chunk_id))
        return [h for _, h in scored[: max(0, int(top_k or 0))]]


# ================================================= E-5 检索回路 (RAG_QUERY + trace_id)


def rag_query(
    workspace: Path | str,
    slug: str,
    question: str,
    *,
    tiers: Optional[list[str]] = None,
    top_k: int = 5,
    external_sources: Optional[list[Any]] = None,
    emitter: Any = None,
    emit_audit: bool = True,
) -> tuple[list[KnowledgeHit], dict[str, Any]]:
    """统一 RAG 查询入口: 本地 KnowledgeStore + 可选外部源 + RAG_QUERY 审计。

    - 本地: 确定性词频检索 (三级分档)
    - 外部源 (M5-3): 每个 source.search(query) → KnowledgeHit(tier=external,
      source="external:<name>"), 失败安全 (单源异常跳过)
    - E-5: RAG_QUERY 审计事件带 trace_id (K-4 contextvar 自动填充; 无上下文 → "")
    - 返回 (hits, stats): stats 含 local/external 命中数与 tiers
    """
    store = KnowledgeStore(workspace, slug)
    local_hits = store.query(question, tiers=tiers, top_k=max(0, int(top_k)))
    external_hits: list[KnowledgeHit] = []
    for src in (external_sources or []):
        name = str(getattr(src, "name", "") or "external")
        try:
            items = src.search(question, top_k=max(0, int(top_k))) or []
        except Exception:  # noqa: BLE001 — 单源失败不阻断
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            if not content.strip():
                continue
            source_name = str(item.get("source") or name)
            ext_score = 0.0
            try:
                ext_score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):  # noqa: BLE001
                ext_score = 0.0
            external_hits.append(KnowledgeHit(
                chunk_id=f"external:{name}:{i + 1}",
                file=f"external:{name}:{source_name}",
                fragment=content,
                score=max(0.0, min(1.0, ext_score)),
                tier=TIER_EXTERNAL,
                reason=f"外部源 {name} 命中 (score={round(ext_score, 4)})",
                source=f"external:{name}",
            ))
    merged = sorted(
        local_hits + external_hits,
        key=lambda h: (-h.score, h.file, h.chunk_id),
    )[: max(0, int(top_k))]
    stats = {
        "local_hits": len(local_hits),
        "external_hits": len(external_hits),
        "total_hits": len(merged),
        "tiers": sorted({h.tier for h in merged}),
        "top_k": max(0, int(top_k)),
    }
    if emit_audit:
        try:
            if emitter is None:
                from ..audit.audit_emitter import AuditEmitter

                emitter = AuditEmitter(workspace=workspace)
            emitter.emit(
                "RAG_QUERY",
                project_id=str(slug or ""),
                actor_type="user",
                decision_reason=f"RAG 查询: {str(question or '')[:80]}",
                result={
                    "question": str(question or ""),
                    "tiers": [str(t) for t in (tiers or DEFAULT_TIERS)],
                    "top_k": max(0, int(top_k)),
                    "hits": [h.to_dict() for h in merged],
                },
            )
        except Exception:  # noqa: BLE001 — 审计故障不阻断检索
            pass
    return merged, stats
