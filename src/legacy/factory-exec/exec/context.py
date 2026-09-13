"""factory-exec/exec/context.py — Context Assembly Engine v1 (Phase A++++++-2b)。

设计依据 (docs/architecture/ai-developer-capability-engine-model.md §2):
```text
Task (自然语言目标)
  → Requirement Context   (任务目标 + 验收标准 — 样本自带)
  → Code Context          (相关源文件: 全量核心 + symbol 索引相关)
  → Architecture Context  (模块结构 + 入口 + 目录职责 — Repository Intelligence)
  → History Context       (目标文件修改历史 git log)
  → Experience Context    (同类任务历史经验 + 失败模式 — ExperienceStore 10A-4)
  → Test Context          (相关测试: test_map 选择)
  → AI Native Context     (组装为结构化 prompt, token 预算分配)
```

组装策略 (Token 预算分级):
- 核心文件 (直接修改目标): 全量 ≤3000 行 (行号前缀内联);
- 超长文件 (≥500 行): 不全文内联 → symbol 索引 + 命中任务关键词的函数块
  (Phase A++++++-1 失败样本 FEAT-001 789 行 file_tree.dart 空内容根因修复);
- 相关文件 (调用链/依赖影响面): symbol 索引 + 关键段 (不全文);
- 架构/历史/经验: 摘要 (压缩);
- 总量上限 ≤120K chars (≈30K tokens); 超限按「核心 > 相关 > 上下文」截断。

Quality Score (0-1): 核心文件覆盖 / 相关文件命中 / 测试覆盖 / 经验可用
四维加权; 低分 (<0.5) → 扩大相关范围 1 轮再评分 (禁无限循环); 分数进
ExecutionRecord / BenchmarkResult (context_score 字段)。

Experience 集成: 历史失败模式 (symbol 锚点易错 / 超长文件空内容 / verifier
未达) → 影响 prompt 建议 (行号优先 / 关注 symbol 索引节 / 验证策略), 输出
Provider 建议 (同类任务成功率), 不自动切换 (只建议, 决策权在装配点)。

KISS 边界: 零 LLM、零数据库、零 Core 依赖; 全部确定性启发式; 失败安全
(任一环节异常 → 空节/空组装, 不破坏执行链 — 同 _project_context 语义)。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ================================================================ 常量

#: 组装总量上限 (字符数; ≈30K tokens, 设计 §2「预算分配: 核心 60%/相关 30%/上下文 10%」)
TOTAL_BUDGET_CHARS = 120_000
#: 核心文件全量内联上限 (行数; 超出 → 超长处理)
CORE_LINE_CAP = 3000
#: 超长文件阈值 (行数; ≥ → symbol 索引 + 命中关键词函数块, 不全文内联)
LONG_FILE_LINES = 500
#: 相关文件 (symbol 索引级) 数量上限
MAX_RELATED_FILES = 12
#: 测试文件内联 (symbol 索引级) 数量上限
MAX_TEST_FILES = 8
#: git log 摘要条目上限
HISTORY_MAX_ENTRIES = 8
#: 单个函数块内联行数上限 (超长文件关键段)
_SYMBOL_BLOCK_LINES = 80
#: 低分阈值 (低于 → 扩大相关范围 1 轮重组装)
_LOW_SCORE_THRESHOLD = 0.5
#: 质量分四维权重 (核心/相关/测试/经验)
_SCORE_WEIGHTS = {"core": 0.4, "related": 0.3, "test": 0.15, "experience": 0.15}

#: 任务关键词提取的停用词 (中英; 标识符匹配噪声)
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "of", "in", "on", "for", "with", "and", "or",
    "is", "are", "be", "it", "this", "that", "as", "at", "by", "from", "into",
    "file", "files", "should", "would", "will", "can", "could", "not",
    "修复", "请", "文件", "应该", "需要", "新增", "显示", "当前", "内容", "问题",
    "点击", "标签", "使用", "功能", "方法", "列表", "错误", "检查", "是否", "没有",
})

#: 标识符提取正则 (camelCase / PascalCase / snake_case / 点号路径段 / 裸词)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: camelCase/PascalCase 拆分 (replaceCurrent → replace, current; _cloneBlock → clone, block)
_CAMEL_SPLIT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+")
#: 任务文本中的符号样式词 (纯标识符形态, 可能是 Dart/JS 函数名)
_SYMBOL_LIKE_RE = re.compile(r"\b(?:[a-z][A-Za-z0-9]*_[A-Za-z0-9_]*|[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*)\b")


# ================================================================ Context 模型

def _norm_list(v: Any) -> Any:
    """None → [] 归一 (pydantic before validator 用: 类型检查前收到原始输入)。"""
    return v if v is not None else []


def _norm_str(v: Any) -> Any:
    """None → "" 归一 (str 字段 None 输入兜底)。"""
    return v if v is not None else ""


class ContextModel(BaseModel):
    """Context 模型基类: 严格字段 + JSON 友好导出 (同 exec.models._ExecModel)。"""

    model_config = {"extra": "forbid"}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class FileSlice(BaseModel):
    """文件片段: 相对路径 + 已渲染内容 (行号前缀) + 元数据。

    kind: core (全量内联) / related (symbol 索引 + 关键段) / test (symbol 索引)。
    truncated: 超长/超预算截断标志 (报告与质量分用)。
    symbol_index: 文件 symbol 摘要行 (related/test 片段的主体)。
    """

    rel_path: str
    content: str = ""
    kind: str = "core"
    line_count: int = 0
    truncated: bool = False
    symbol_index: str = ""

    @field_validator("rel_path", "content", "kind", "symbol_index", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)


class RequirementContext(ContextModel):
    """任务目标 + 验收标准 (样本自带; prompt 的 Task 节)。"""

    objective: str
    requirement: str = ""
    task_id: str = ""

    @field_validator("objective", "requirement", "task_id", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)

    def render(self) -> str:
        lines = ["## Task", self.objective.strip()]
        if self.requirement.strip():
            lines += ["", "## Requirement / Acceptance criteria", self.requirement.strip()]
        return "\n".join(lines)


class ArchitectureContext(ContextModel):
    """模块/入口/技术栈摘要 (Repository Intelligence L1+L2+L7+L6 压缩文本)。"""

    summary: str = ""
    entry_points: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary_none(cls, v: Any) -> Any:
        return _norm_str(v)

    @field_validator("entry_points", "modules", "tech_stack", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    def render(self) -> str:
        lines = ["## Architecture context"]
        if self.summary.strip():
            lines.append(self.summary.strip())
        else:
            lines.append("(仓库结构摘要不可用 — 仍以内联源文件为准)")
        return "\n".join(lines)


class CodeContext(ContextModel):
    """相关源文件: 核心全量 + 相关 symbol 索引/关键段 (Token 预算控制后)。"""

    core_files: list[FileSlice] = Field(default_factory=list)
    related_files: list[FileSlice] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("core_files", "related_files", "keywords", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    def render(self) -> str:
        lines = ["## Relevant source files"]
        if self.core_files:
            lines.append(
                "(核心文件 — 每行前缀 `N|` 为行号, 仅用于精确定位 location "
                "(symbol 或 line_range); 输出的代码内容绝不能包含行号前缀)"
            )
            for f in self.core_files:
                lines += ["", f"### {f.rel_path} ({f.line_count} 行)"]
                lines += ["```dart", f.content, "```"]
        if self.related_files:
            lines += [
                "",
                "(相关文件 — 修改影响面/调用方; 只给 symbol 索引与关键段, 不全文内联)",
            ]
            for f in self.related_files:
                lines += ["", f"### {f.rel_path} [related]"]
                if f.symbol_index:
                    lines += ["```dart", f.symbol_index, "```"]
                if f.content:
                    lines += ["```dart", f.content, "```"]
        if not self.core_files and not self.related_files:
            lines.append("(无可用源文件 — 从零构建场景, 以下仅凭任务描述)")
        return "\n".join(lines)


class HistoryContext(ContextModel):
    """目标文件修改历史 (git log 摘要; 沙箱单基线提交时为空 — 合法冷启动)。"""

    entries: list[str] = Field(default_factory=list)

    @field_validator("entries", mode="before")
    @classmethod
    def _entries_none(cls, v: Any) -> Any:
        return _norm_list(v)

    def render(self) -> str:
        lines = ["## Change history"]
        if self.entries:
            lines += [f"- {e}" for e in self.entries]
        else:
            lines.append("(无可用提交历史 — 沙箱基线或新项目)")
        return "\n".join(lines)


class ExperienceContext(ContextModel):
    """同类任务历史经验 + 失败模式 (ExperienceStore 10A-4 查询, 冷启动空)。"""

    task_type: str = ""
    record_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float | None = None
    failure_patterns: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    provider_hint: str = ""

    @field_validator("task_type", "provider_hint", mode="before")
    @classmethod
    def _strs_none(cls, v: Any) -> Any:
        return _norm_str(v)

    @field_validator("failure_patterns", "advice", mode="before")
    @classmethod
    def _lists_none(cls, v: Any) -> Any:
        return _norm_list(v)

    def render(self) -> str:
        lines = ["## Experience / past lessons"]
        if self.record_count <= 0:
            lines.append("(无同类任务历史经验 — 冷启动, 按通用规范执行)")
            return "\n".join(lines)
        rate = f"{self.success_rate:.0%}" if self.success_rate is not None else "-"
        lines.append(
            f"- 同类任务历史: {self.record_count} 条 "
            f"(成功 {self.success_count} / 失败 {self.failure_count}, 成功率 {rate})"
        )
        for p in self.failure_patterns[:5]:
            lines.append(f"- 常见失败模式: {p}")
        for a in self.advice[:6]:
            lines.append(f"- 建议: {a}")
        if self.provider_hint:
            lines.append(f"- Provider 建议: {self.provider_hint}")
        return "\n".join(lines)


class TestContext(ContextModel):
    """相关测试文件 (test_map 选择; symbol 索引级内联, 不全文)。"""

    test_files: list[FileSlice] = Field(default_factory=list)
    mapping: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("test_files", mode="before")
    @classmethod
    def _files_none(cls, v: Any) -> Any:
        return _norm_list(v)

    @field_validator("mapping", mode="before")
    @classmethod
    def _map_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    def render(self) -> str:
        lines = ["## Related tests"]
        if self.mapping:
            for src, tests in list(self.mapping.items())[:8]:
                lines.append(f"- {src} → {', '.join(tests[:4])}")
        if self.test_files:
            lines.append("(测试文件 symbol 索引 — 了解既有测试约定, 不必修改)")
            for f in self.test_files:
                if f.symbol_index:
                    lines += ["", f"### {f.rel_path} [test]", "```dart", f.symbol_index, "```"]
        if len(lines) == 1:
            lines.append("(无相关测试映射 — test_map 未命中或仓库无测试)")
        return "\n".join(lines)


class AssembledContext(ContextModel):
    """Context Assembly 产物: 6 节结构化 + 质量分 + 预算统计 + 文本渲染。

    render_prompt(): 组装为 Developer prompt 主体 (6 节; Conventions/Output
    format 由 developer.build_prompt 统一附加 — 保持 Stage 1 输出协议)。
    """

    requirement: RequirementContext
    architecture: ArchitectureContext
    code: CodeContext
    history: HistoryContext
    test: TestContext
    experience: ExperienceContext
    context_score: float = 0.0
    total_chars: int = 0
    token_estimate: int = 0

    @field_validator("context_score", mode="before")
    @classmethod
    def _score_none(cls, v: Any) -> Any:
        return v if v is not None else 0.0

    def render_prompt(self) -> str:
        """6 节结构化 prompt 主体 (Task → Architecture → Code → Tests → History → Experience)。"""
        sections = [
            self.requirement.render(),
            self.architecture.render(),
            self.code.render(),
            self.test.render(),
            self.history.render(),
            self.experience.render(),
        ]
        return "\n\n".join(s for s in sections if s.strip())

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        d["total_chars"] = self.total_chars
        d["token_estimate"] = self.token_estimate
        return d


# ================================================================ 选择器

def extract_task_keywords(objective: str, requirement: str = "") -> list[str]:
    """任务文本 → 标识符关键词 (symbol 索引匹配用; 确定性, 零 LLM)。

    提取: camelCase/PascalCase/snake_case 符号样式词 + 全部标识符拆分小写,
    过滤停用词, 保序去重。示例: 「replaceCurrent 只替换当前匹配」→
    [replace, current]; 「_cloneBlock 深拷贝」→ [clone, block]。
    """
    text = f"{objective} {requirement}"
    out: list[str] = []
    seen: set[str] = set()
    for m in _IDENT_RE.finditer(text):
        word = m.group(0)
        # 符号样式词 (含大写驼峰/下划线) 先整词入列, 再拆分
        for cand in (word.lower(),):
            if cand not in seen and cand not in _STOPWORDS and len(cand) >= 2:
                out.append(cand)
                seen.add(cand)
        for piece in _CAMEL_SPLIT_RE.findall(word):
            piece = piece.lower()
            if piece not in seen and piece not in _STOPWORDS and len(piece) >= 2:
                out.append(piece)
                seen.add(piece)
    return out


def select_symbols(ri: Any, keywords: list[str]) -> list[tuple[str, Any, float]]:
    """任务关键词 → 相关 Symbol (跨文件谁定义; 精确 > 前缀 > 包含)。

    返回 [(file, SymbolEntry, score)] 按得分降序 (得分: 精确 1.0 / 名前缀 0.8 /
    name 含词 0.6 / 词含 name 0.4)。ri: RepositoryIntelligence 门面 (已 analyze)。
    """
    if not keywords:
        return []
    hits: dict[tuple[str, str], tuple[Any, float]] = {}
    for kw in keywords:
        for path, sym in ri.index.symbols_by_name(kw):
            key = (path, sym.name)
            score = max(hits.get(key, (None, 0.0))[1], 1.0)
            hits[key] = (sym, score)
        for f in ri.index.files:
            for sym in f.symbols:
                sname = sym.name.lower()
                if sname == kw:
                    score = 1.0
                elif sname.startswith(kw):
                    score = 0.8
                elif kw in sname:
                    score = 0.6
                elif sname and sname in kw:
                    score = 0.4
                else:
                    continue
                key = (f.path, sym.name)
                cur = hits.get(key)
                if cur is None or score > cur[1]:
                    hits[key] = (sym, score)
    ranked = sorted(
        ((path, sym, score) for (path, _name), (sym, score) in hits.items()),
        key=lambda t: (-t[2], t[0]),
    )
    return ranked


def _importance_rank(ri: Any, rel: str) -> int:
    """文件重要性排序键 (high=0 / medium=1 / low=2; 缺失 → 1)。"""
    f = ri.index.find(rel)
    if f is None:
        return 1
    return {"high": 0, "medium": 1, "low": 2}.get(f.importance, 1)


def select_files(
    ri: Any,
    *,
    source_files: list[str],
    symbol_hits: list[tuple[str, Any, float]],
    keywords: list[str],
    widen: bool = False,
) -> tuple[list[str], list[str]]:
    """Task → 核心文件 (全量内联) + 相关文件 (symbol 索引级)。

    核心 = source_files (样本显式) ∪ 命中符号所在文件 (按重要性+得分排序);
    相关 = 依赖影响面 (谁 import 核心文件) ∪ 同模块文件 ∪ (widen 时) 次优符号
    文件。widen: 质量低分后的扩大搜索 (把相关提升为候选核心 + 追加同模块)。
    """
    core: list[str] = []
    for rel in source_files:
        if rel not in core:
            core.append(rel)
    for path, _sym, _score in symbol_hits:
        if path not in core:
            core.append(path)
    core.sort(key=lambda p: (_importance_rank(ri, p), p))
    if widen:
        # 扩大搜索 (质量低分 1 轮): 同模块文件 + 依赖影响面文件提升为核心候选
        # (低分时给模型更多内联上下文 — 禁无限循环, 只扩这一轮)
        for c in list(core):
            mod = ri.index.find(c)
            if mod is not None and mod.module:
                for f in ri.index.files_of_module(mod.module):
                    if f.path not in core:
                        core.append(f.path)
            for dep in ri.impact_of(c):
                if dep not in core:
                    core.append(dep)
        core.sort(key=lambda p: (_importance_rank(ri, p), p))
    core = core[: 8 if widen else 6]

    related: list[str] = []
    for c in core:
        for dep in ri.impact_of(c):
            if dep not in core and dep not in related:
                related.append(dep)
        mod = ri.index.find(c)
        if mod is not None and mod.module:
            for f in ri.index.files_of_module(mod.module):
                if f.path not in core and f.path not in related:
                    related.append(f.path)
    for path, _sym, _score in symbol_hits:
        if path not in core and path not in related:
            related.append(path)
    if widen:
        related.sort(key=lambda p: (_importance_rank(ri, p), p))
    else:
        related.sort(key=lambda p: (_importance_rank(ri, p), p))
    return core[:8], related[:MAX_RELATED_FILES]


def select_tests(ri: Any, core_files: list[str]) -> dict[str, list[str]]:
    """核心文件 → 相关测试映射 (test_map; 源文件 → 测试文件列表)。"""
    mapping: dict[str, list[str]] = {}
    for src in core_files:
        tests = ri.tests_for(src)
        if tests:
            mapping[src] = list(tests)
    return mapping


def git_history(
    root: str | Path, files: list[str], *, git_bin: str = "git", max_entries: int = HISTORY_MAX_ENTRIES
) -> list[str]:
    """目标文件 git log 摘要 (失败安全: 非 git/无历史 → 空列表, 合法冷启动)。

    沙箱副本通常只有基线提交 → 空; 真实项目 (带历史) 才有条目。经注入的
    git_bin (测试可控); 每条 `git log --oneline -N -- <file>` 一行。
    """
    if not files:
        return []
    entries: list[str] = []
    try:
        for rel in files[:6]:
            proc = subprocess.run(
                [git_bin, "-C", str(root), "log", "--oneline",
                 f"-{max_entries}", "--", rel],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                continue
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line and line not in entries:
                    entries.append(f"{rel}: {line}")
    except (OSError, subprocess.SubprocessError):  # noqa: BLE001 — 失败安全
        return []
    return entries[:max_entries]


def _render_lines(content: str) -> str:
    """文件内容 → 每行带 `N|` 行号前缀 (与 developer._render_lines 同语义;
    独立实现避免 import 环, 复制 8 行 KISS)。"""
    src_lines = content.splitlines()
    if not src_lines:
        return ""
    width = len(str(len(src_lines)))
    return "\n".join(f"{i + 1:>{width}}| {ln}" for i, ln in enumerate(src_lines))


def _symbol_blocks(lines: list[str], symbols: list[Any], keywords: list[str]) -> list[tuple[Any, int, int]]:
    """超长文件中命中关键词的符号块 [(symbol, start, end)] (关键段内联)。

    块范围: 定义行 → 下一个符号定义行前一行 / 文件尾 (与 OperationEngine
    块定位同语义); 每块 ≤_SYMBOL_BLOCK_LINES 行 (防单块撑爆预算)。
    """
    if not keywords:
        return []
    kws = [k for k in keywords if len(k) >= 3]
    hits: list[tuple[Any, int, int]] = []
    for i, sym in enumerate(symbols):
        name = sym.name.lower()
        if not any(k in name or name in k for k in kws):
            continue
        start = sym.line - 1
        end = symbols[i + 1].line - 2 if i + 1 < len(symbols) else len(lines) - 1
        end = max(start, min(end, start + _SYMBOL_BLOCK_LINES))
        hits.append((sym, start, end))
    return hits


def _file_symbol_index(ri: Any, rel: str, max_symbols: int = 60) -> str:
    """文件 symbol 索引文本 (related/test 片段主体; 定义行定位参考)。"""
    f = ri.index.find(rel)
    if f is None or not f.symbols:
        return ""
    lines = [f"// {s.kind.value} {s.name} @ line {s.line}" for s in f.symbols[:max_symbols]]
    if len(f.symbols) > max_symbols:
        lines.append(f"// ... ({len(f.symbols) - max_symbols} more symbols)")
    return "\n".join(lines)


def _read_file_text(root: Path, rel: str) -> list[str]:
    """沙箱内读文件 → 行列表 (缺失/读失败 → 空列表, 失败安全)。"""
    try:
        path = root / rel
        if not path.is_file():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:  # noqa: BLE001 — 失败安全
        return []


def _build_file_slices(
    ri: Any,
    root: Path,
    *,
    core_files: list[str],
    related_files: list[str],
    keywords: list[str],
    total_budget_chars: int,
) -> tuple[list[FileSlice], list[FileSlice], int]:
    """Token 预算控制: 核心全量 (≤3000 行) / 超长 symbol 索引+关键段 / 相关索引。

    返回 (core_slices, related_slices, used_chars)。预算分配: 核心优先 (先全部
    内联), 相关文件按重要性序内联 symbol 索引; 超限 → 截断相关段 (核心不截)。
    """
    core_slices: list[FileSlice] = []
    related_slices: list[FileSlice] = []
    used = 0
    budget_core = int(total_budget_chars * 0.6)
    budget_related = int(total_budget_chars * 0.3)

    for rel in core_files:
        lines = _read_file_text(root, rel)
        line_count = len(lines)
        if line_count <= 0:
            core_slices.append(FileSlice(rel_path=rel, kind="core", line_count=0))
            continue
        if line_count <= CORE_LINE_CAP:
            content = _render_lines("\n".join(lines))
            core_slices.append(
                FileSlice(rel_path=rel, kind="core", content=content, line_count=line_count)
            )
            used += len(content)
        else:
            # 超长文件: symbol 索引 + 命中关键词函数块 (不全文 — 789 行样本根因)
            symbols = ri.index.find(rel).symbols if ri.index.find(rel) is not None else []
            blocks = _symbol_blocks(lines, symbols, keywords)
            parts = [
                f"// (文件 {rel} 共 {line_count} 行, 超过 {CORE_LINE_CAP} 行上限 —",
                "//  以下为 symbol 索引 + 命中任务关键词的函数块; 完整文件不内联)",
            ]
            idx = _file_symbol_index(ri, rel)
            if idx:
                parts.append(idx)
            for sym, start, end in blocks[:6]:
                block_text = "\n".join(lines[start : end + 1])
                parts.append(f"// 关键段: {sym.kind.value} {sym.name} (行 {start + 1}-{end + 1}):")
                parts.append(_render_lines(block_text))
            content = "\n".join(parts)
            core_slices.append(
                FileSlice(
                    rel_path=rel, kind="core", content=content, line_count=line_count,
                    truncated=True, symbol_index=idx,
                )
            )
            used += len(content)
        if used > budget_core:
            break

    remaining = budget_related
    for rel in related_files:
        idx = _file_symbol_index(ri, rel)
        if not idx:
            continue
        slice_text = idx
        if len(slice_text) > remaining:
            slice_text = slice_text[: max(remaining - 80, 0)]
        if not slice_text.strip():
            continue
        related_slices.append(
            FileSlice(rel_path=rel, kind="related", content=slice_text,
                      line_count=0, symbol_index=idx)
        )
        used += len(slice_text)
        remaining -= len(slice_text)
        if remaining <= 0:
            break
    return core_slices, related_slices, used


def _build_test_slices(ri: Any, root: Path, mapping: dict[str, list[str]],
                       max_files: int = MAX_TEST_FILES) -> list[FileSlice]:
    """测试文件 → symbol 索引级片段 (不全文; 了解既有测试约定)。"""
    slices: list[FileSlice] = []
    seen: set[str] = set()
    for _src, tests in mapping.items():
        for t in tests:
            if t in seen or len(slices) >= max_files:
                continue
            seen.add(t)
            idx = _file_symbol_index(ri, t)
            slices.append(
                FileSlice(rel_path=t, kind="test", content=idx, symbol_index=idx)
            )
    return slices


# ================================================================ 质量分

def quality_score(
    *,
    core_files: list[FileSlice],
    related_files: list[FileSlice],
    mapping: dict[str, list[str]],
    keywords: list[str],
    experience: ExperienceContext,
) -> float:
    """Completeness 评分 0-1 (四维加权; 确定性, 零 LLM)。

    - core: 核心文件非空 + 平均内容完整度 (truncated 0.5 系数) — 权重 0.4;
    - related: 关键词命中相关文件的比例 (有相关文件且关键词≥1 时) — 权重 0.3;
    - test: 有测试映射的核心文件占比 — 权重 0.15;
    - experience: 有可用经验记录 (record_count>0) — 权重 0.15。
    """
    if not keywords:
        return 0.0
    if not core_files:
        return 0.0
    core_score = 0.0
    for f in core_files:
        if f.line_count <= 0:
            continue
        base = 1.0 if f.content else 0.2
        core_score += base * (0.5 if f.truncated else 1.0)
    core_score = core_score / len(core_files)
    related_score = 0.0
    if related_files:
        related_score = min(1.0, len(related_files) / 4.0)
    test_score = 0.0
    if mapping:
        test_score = 1.0
    exp_score = 1.0 if experience.record_count > 0 else 0.0
    score = (
        _SCORE_WEIGHTS["core"] * core_score
        + _SCORE_WEIGHTS["related"] * related_score
        + _SCORE_WEIGHTS["test"] * test_score
        + _SCORE_WEIGHTS["experience"] * exp_score
    )
    return round(max(0.0, min(1.0, score)), 3)


# ================================================================ Experience 集成

def _failure_patterns_of(records: list[Any]) -> list[str]:
    """经验记录 → 常见失败模式 (evidence "failure_reason: X" 提取 + 计数排序)。"""
    counts: dict[str, int] = {}
    for rec in records:
        if getattr(rec, "negative_signal", False) is not True:
            continue
        for ev in getattr(rec, "evidence", []) or []:
            desc = str(getattr(ev, "description", "") or "")
            if desc.startswith("failure_reason: "):
                reason = desc.split(":", 1)[1].strip().split(":")[0].strip()
                counts[reason] = counts.get(reason, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [f"{name} ×{n}" for name, n in ranked[:5]]


def experience_advice(analyzer: Any, task_type: str, *, keywords: list[str]) -> ExperienceContext:
    """ExperienceStore 查询 → ExperienceContext (历史成功率 + 失败模式 + 建议)。

    analyzer: duck-typed (records/aggregate 方法即可 — 10A-4 ExperienceAnalyzer
    或测试 FakeAnalyzer); None → 冷启动空 (失败安全, 不破坏组装链)。

    失败模式 → 建议映射 (设计 §4 决策影响):
    - operation_error/symbol 锚点失败多 → 建议行号优先 (symbol 易错);
    - empty_content 多 → 建议关注 symbol 索引节 (超长文件不全文);
    - verifier_failed 多 → 建议对照验收标准逐条核验;
    - provider_error 多 → Provider 建议 (同类任务成功率低时提示备选)。
    """
    if analyzer is None:
        return ExperienceContext(task_type=task_type)
    try:
        records = analyzer.records(task_type=task_type or None, capability=["development"])
    except Exception:  # noqa: BLE001 — 经验查询失败安全
        return ExperienceContext(task_type=task_type)
    records = list(records or [])
    ctx = ExperienceContext(task_type=task_type, record_count=len(records))
    if not records:
        return ctx
    successes = [r for r in records if getattr(r, "negative_signal", False) is not True]
    ctx.success_count = len(successes)
    ctx.failure_count = len(records) - len(successes)
    ctx.success_rate = round(len(successes) / len(records), 3)
    patterns = _failure_patterns_of(records)
    ctx.failure_patterns = patterns
    pattern_names = [p.split(" ×")[0] for p in patterns]
    if "operation_error" in pattern_names or "symbol" in " ".join(pattern_names):
        ctx.advice.append(
            "历史 symbol 定位失败较多 — 优先用精确行号 (line_range) 或核对 "
            "Relevant source files 中 `N|` 行号定位, 函数名偏差时改用行号兜底"
        )
    if "empty_content" in pattern_names:
        ctx.advice.append(
            "历史空内容较多 — 超长文件只内联 symbol 索引与关键段, 请直接输出 "
            "<operations>, 避免长推理空转"
        )
    if "verifier_failed" in pattern_names:
        ctx.advice.append(
            "历史验收未达较多 — 修改后逐条对照 Requirement/Acceptance criteria 核验"
        )
    if "patch_apply_failed" in pattern_names:
        ctx.advice.append(
            "历史补丁应用失败较多 — 用 <operations> 结构化操作 (系统确定性生成 diff)"
        )
    if not ctx.advice:
        ctx.advice.append("历史经验可用 — 保持最小改动, 优先结构化操作")
    if ctx.success_rate is not None and ctx.success_rate < 0.5:
        ctx.provider_hint = (
            f"同类任务历史成功率 {ctx.success_rate:.0%} 偏低 — 装配点可考虑 "
            "切换 Provider 或降低自动化期望 (本引擎只建议, 不自动切换)"
        )
    return ctx


# ================================================================ 组装器

class ContextAssembler:
    """Context Assembly Engine: Task → AssembledContext (6 节 + 质量分 + 预算)。

    构造:
    - root: 沙箱/项目副本根 (Repository Intelligence 分析 + 文件读取源)。
    - project_dir: 原始项目根 (git 历史查询; None → 用 root — 沙箱单基线)。
    - ri: RepositoryIntelligence 实例 (None → 惰性 analyze; 失败 → 空组装)。
    - analyzer: ExperienceAnalyzer 或 duck-typed (None → 冷启动)。
    - git_bin / total_budget_chars / core_line_cap: 可注入 (测试可控)。
    """

    def __init__(
        self,
        root: str | Path,
        *,
        project_dir: str | Path | None = None,
        ri: Any = None,
        analyzer: Any = None,
        git_bin: str = "git",
        total_budget_chars: int = TOTAL_BUDGET_CHARS,
        core_line_cap: int = CORE_LINE_CAP,
        long_file_lines: int = LONG_FILE_LINES,
        experience_store: Any = None,
    ) -> None:
        self._root = Path(root)
        self._project_dir = Path(project_dir) if project_dir else self._root
        self._ri = ri
        self._analyzer = analyzer
        self._git_bin = git_bin
        self._total_budget_chars = total_budget_chars
        self._core_line_cap = core_line_cap
        self._long_file_lines = long_file_lines
        # T4.4: ContextExperienceStore (None → 冷启动; 提供 → RankingPipeline
        # 真实经验接入: symbol_miss 提权/预算推荐/阶段序; 全部失败安全)
        self._experience_store = experience_store
        # T4.4: 最近一次 ranking_assemble 的 RankingPipelineResult (全链路
        # Trace 来源; None = 未走新路径/回退旧路径 — 装配方 Experience
        # Extractor 读取, 纯新增属性零回归)
        self._last_ranking_result: Any = None

    @property
    def last_ranking_result(self) -> Any:
        """最近一次 ranking_assemble 的 Pipeline 全产物 (None = 旧路径)。"""
        return self._last_ranking_result

    # ------------------------------------------------------------------ 内部

    def _intelligence(self) -> Any:
        """RepositoryIntelligence 实例 (惰性; 失败 → None — 组装降级为任务+源文件)。"""
        if self._ri is None:
            try:
                from .repo_intelligence import RepositoryIntelligence

                self._ri = RepositoryIntelligence(self._root).analyze()
            except Exception:  # noqa: BLE001 — 失败安全: 情报不可用不致命
                self._ri = None
        return self._ri

    def _architecture(self, ri: Any) -> ArchitectureContext:
        if ri is None or ri.architecture is None:
            return ArchitectureContext()
        arch = ri.architecture
        ctx = ArchitectureContext(
            entry_points=list(arch.entry_points or []),
            modules=[m.path for m in (ri.modules or [])][:12],
            tech_stack=list(arch.tech_stack or []),
        )
        try:
            ctx.summary = ri.format_context(
                max_files=80, include_modules=True,
                include_architecture=True, include_tests=False,
            )[: 8000]
        except Exception:  # noqa: BLE001 — 摘要失败安全
            ctx.summary = ""
        return ctx

    # ------------------------------------------------------------------ 组装

    def assemble(self, task: Any) -> AssembledContext:
        """Task (duck-typed: objective/requirement/source_files/task_id) → 组装上下文。

        流程: 关键词 → 符号匹配 → 文件选择 (核心/相关) → 影响面 → 测试 →
        历史 → 经验 → 预算渲染 → 质量分 (低分 → 扩大搜索 1 轮 → 重评分)。
        全程失败安全: 任一环节异常 → 该节空/降级, 不抛 (执行链不破坏)。
        """
        objective = getattr(task, "objective", "") or ""
        requirement = getattr(task, "requirement", "") or ""
        task_id = getattr(task, "task_id", "") or getattr(task, "id", "") or ""
        source_files = list(getattr(task, "source_files", None) or [])

        keywords = extract_task_keywords(objective, requirement)
        ri = self._intelligence()

        # 1) 符号匹配 + 文件选择 (第 1 轮)
        symbol_hits = select_symbols(ri, keywords) if ri is not None else []
        core_files, related_files = select_files(
            ri, source_files=source_files, symbol_hits=symbol_hits, keywords=keywords,
        ) if ri is not None else (source_files[:6], [])

        # 2) 影响面 / 测试 / 历史 / 经验
        mapping = select_tests(ri, core_files) if ri is not None else {}
        history_entries = git_history(
            self._project_dir, core_files[:6], git_bin=self._git_bin
        )
        exp = experience_advice(
            self._analyzer, task_type=task_id or "development", keywords=keywords
        )

        # 3) 预算渲染 (核心优先; 超长 symbol 索引 + 关键段)
        core_slices, related_slices, used = _build_file_slices(
            ri, self._root,
            core_files=core_files, related_files=related_files,
            keywords=keywords, total_budget_chars=self._total_budget_chars,
        )
        test_slices = _build_test_slices(ri, self._root, mapping)

        # 4) 质量分 → 低分扩大搜索 1 轮 (禁无限循环)
        score = quality_score(
            core_files=core_slices, related_files=related_slices,
            mapping=mapping, keywords=keywords, experience=exp,
        )
        if score < _LOW_SCORE_THRESHOLD and ri is not None:
            widened_core, widened_related = select_files(
                ri, source_files=source_files, symbol_hits=symbol_hits,
                keywords=keywords, widen=True,
            )
            if widened_core != core_files or widened_related != related_files:
                core_files, related_files = widened_core, widened_related
                mapping = select_tests(ri, core_files)
                history_entries = git_history(
                    self._project_dir, core_files[:6], git_bin=self._git_bin
                )
                core_slices, related_slices, used = _build_file_slices(
                    ri, self._root,
                    core_files=core_files, related_files=related_files,
                    keywords=keywords, total_budget_chars=self._total_budget_chars,
                )
                test_slices = _build_test_slices(ri, self._root, mapping)
                score = quality_score(
                    core_files=core_slices, related_files=related_slices,
                    mapping=mapping, keywords=keywords, experience=exp,
                )

        arch = self._architecture(ri)
        total_chars = used + sum(len(s.content) for s in test_slices)
        ctx = AssembledContext(
            requirement=RequirementContext(
                objective=objective, requirement=requirement, task_id=task_id
            ),
            architecture=arch,
            code=CodeContext(
                core_files=core_slices, related_files=related_slices, keywords=keywords
            ),
            history=HistoryContext(entries=history_entries),
            test=TestContext(test_files=test_slices, mapping=mapping),
            experience=exp,
            context_score=score,
            total_chars=total_chars,
            token_estimate=total_chars // 4,
        )
        return ctx

    def ranking_assemble(self, task: Any, *, progressive: bool = False) -> AssembledContext:
        """T4.1 Ranking Pipeline 新路径 (Task→候选→特征→评分→TopK→预算→组装)。

        与 assemble() 完全独立并存 (旧路径逐位不动 — Sprint 3 测试全绿是硬约束):
        内部 RankingPipeline 延迟 import (单向无环); 新路径任一环节异常 →
        回退旧 assemble() (执行链不破坏, 失败安全)。开关在装配点
        (agent_runtime ranking_enabled, 默认 False — 注入式门控, 新行为
        默认关在单元层、只开在装配点)。

        progressive (T4.2, 默认 False 旧路径兼容): True → 透传给
        RankingPipeline.run(progressive=True) 走渐进加载路径 (TopK→Budget
        后由 ProgressiveLoader 逐阶段加载 + 决策 + 审计 Trace); 渐进路径
        自身异常已由 Pipeline 内部回退一次性组装, 本方法 try/except 兜底
        只负责新路径整体 (含 Pipeline 装配) 失败 → 旧 assemble()。
        """
        try:
            from .ranking import RankingPipeline

            pipeline = RankingPipeline(
                self._root,
                project_dir=self._project_dir,
                ri=self._ri,
                analyzer=self._analyzer,
                git_bin=self._git_bin,
                experience_store=self._experience_store,
            )
            result = pipeline.run(task, progressive=progressive)
            self._last_ranking_result = result
            return result.assembled
        except Exception:  # noqa: BLE001 — 新路径失败安全: 回退旧路径
            self._last_ranking_result = None
            return self.assemble(task)
