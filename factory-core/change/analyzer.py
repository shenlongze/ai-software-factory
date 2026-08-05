"""change/analyzer.py — ChangeAnalyzer: 路径分析 (Files/Insertions/Deletions/
Affected modules) + L4 Change Validation 判定规则 (Phase 6D, ADR-0019)。

设计依据:
- phase6d-status.md: ChangeAnalyzer (task_id/files/insertions/deletions/
  affected_modules) — 路径分析, 禁 LLM (ADR-0019 决策 2): 全部确定性规则,
  无网络/无模型调用, 纯函数可单测。
- L4 规则语义: Task 描述 (标题) vs Git Change 证据 → PASS/FAIL/SKIP:
  - SKIP: 无 git 关联 (非仓库 / 无提交 / 无文件变更)
  - PASS: 存在关联提交 (commit 已解析出 task_id) 或任务标题与变更路径/模块重叠
  - FAIL: 有变更证据但既无关联提交、标题也与路径/模块无重叠 (变更疑似无关)

本模块同时承载 L4 判定纯函数 (l4_checks/l4_verdict) — change.service 与
validation.rules.rule_change 共用同一套判定, 不复制逻辑 (DRY)。
"""

from __future__ import annotations

import re
from typing import Any

from git.models import GitChange, GitCommit

from .models import ChangeAnalysis, ChangeContext

# 模块推断噪声目录 (路径分段过滤, 不产生模块名)
_NOISE_DIRS = frozenset({"__pycache__", ".git", "node_modules", "dist", "build", ".venv", "venv"})

# 任务标题 token 化: 非字母数字分隔 (中文标题整段保留, 英文按词)
_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9\u4e00-\u9fff]+")

# 路径匹配对照: 文件路径分段 + 模块名 (标题 token 与之重叠判定)
_L4_CHECK_IDS = ("L4.commit_link", "L4.path_match")


def _module_chain(path: str) -> list[str]:
    """单个变更路径 → 模块链 (目录分段 + 文件模块名, 最具体在前)。

    规则 (确定性, 禁 LLM):
    - 按 '/' 分段, 过滤噪声目录 (__pycache__/.git/node_modules/...);
    - .py 文件去掉扩展名作模块名; 其他文件 (README.md/package.json) 保留文件名段;
    - 生成从最具体到最宽泛的后缀链: 'change/analyzer.py' → ['analyzer',
      'change.analyzer']; 'src/app.py' → ['app', 'src.app']。
    """
    parts = [p for p in path.split("/") if p and p not in _NOISE_DIRS]
    if not parts:
        return []
    stem = parts[-1]
    if stem.endswith(".py"):
        parts[-1] = stem[:-3]
    return [".".join(parts[i:]) for i in range(len(parts))]


def affected_modules(files: list[str], *, limit: int = 50) -> list[str]:
    """全部变更路径的模块并集 (去重排序, 上限 limit 防病态路径)。"""
    out: set[str] = set()
    for f in files:
        out.update(_module_chain(f))
    return sorted(out)[:max(1, limit)]


class ChangeAnalyzer:
    """路径分析器 (纯函数组合, 无副作用; 禁 LLM — 确定性规则)。"""

    def analyze(
        self,
        task_id: str,
        *,
        changes: list[GitChange] | None = None,
        files: list[str] | None = None,
        commits: list[str] | None = None,
    ) -> ChangeAnalysis:
        """一次任务的变更分析。

        - files: 显式 files ∪ changes[].files (排序去重);
        - insertions/deletions: changes 行数求和 (文件级);
        - affected_modules: 模块推断 (目录分段规则);
        - commits: 显式提交哈希列表 (ChangeService 解析回填)。
        失败安全: 空输入 → 全空字段 (不抛)。
        """
        changes = list(changes or [])
        files = list(dict.fromkeys([*(files or []), *[f for c in changes for f in c.files]]))
        files = sorted(files)
        insertions = sum(c.insertions for c in changes)
        deletions = sum(c.deletions for c in changes)
        return ChangeAnalysis(
            task_id=task_id,
            files=files,
            insertions=insertions,
            deletions=deletions,
            affected_modules=affected_modules(files),
            commits=list(dict.fromkeys(commits or [])),
        )


# ------------------------------------------------------------------ L4 判定纯函数

def _title_tokens(title: str) -> set[str]:
    """任务标题 → 匹配 token 集 (去空、去重、小写)。

    中文标题整段为一个 token (无空格分词); 英文按词拆分 (如 'login page'
    → {'login', 'page'})。与路径分段 (小写) 重叠即命中。
    """
    if not title:
        return set()
    tokens = {t.lower() for t in _TOKEN_SPLIT_RE.split(title) if t}
    # 中文整段与单字符都保留 (字符级命中也算 — '登录' 与路径 login 无关, 但
    # 中文标题 '实现登录' 的整段 token 不会与英文路径重叠, 保守不误报)
    return tokens


def _evidence_tokens(files: list[str], modules: list[str]) -> set[str]:
    """变更路径/模块 → 匹配 token 集 (小写; 每段含中文时整段保留)。"""
    out: set[str] = set()
    for path in [*files, *modules]:
        for seg in path.replace(".", "/").split("/"):
            seg = seg.lower()
            if len(seg) >= 2:  # 单字符噪声 (如 'a'/'b') 不参与匹配
                out.add(seg)
    return out


def l4_checks(ctx: ChangeContext) -> list[dict[str, Any]]:
    """L4 逐规则判定: [{id, status, message}] (纯函数, 无副作用)。

    - L4.commit_link: 关联提交存在 (commit 已解析出 task_id == ctx.task_id)
      → PASS; 有证据但无关联 → FAIL; 无证据 → SKIP。
    - L4.path_match: 任务标题 token 与变更路径/模块重叠 → PASS;
      有证据但无重叠 → FAIL; 无证据/无标题 → SKIP。
    """
    if not ctx.is_repo or (not ctx.has_commits and not ctx.files):
        return [
            {"id": "L4.commit_link", "status": "SKIP", "message": "无 git 关联 (非仓库或无变更证据)"},
            {"id": "L4.path_match", "status": "SKIP", "message": "无 git 关联 (非仓库或无变更证据)"},
        ]
    linked = [c for c in ctx.commits if c.task_id == ctx.task_id]
    commit_link = {
        "id": "L4.commit_link",
        "status": "PASS" if linked else "FAIL",
        "message": (
            f"{len(linked)} 个提交关联任务 {ctx.task_id}"
            if linked
            else f"提交未关联任务 {ctx.task_id} (commit message/分支名无任务 ID)"
        ),
    }
    tokens = _title_tokens(ctx.task_title)
    evidence = _evidence_tokens(ctx.files, ctx.affected_modules)
    overlap = tokens & evidence if tokens else set()
    path_match = {
        "id": "L4.path_match",
        "status": "PASS" if overlap else ("SKIP" if not tokens else "FAIL"),
        "message": (
            f"标题与变更路径重叠: {', '.join(sorted(overlap))}"
            if overlap
            else ("任务无标题, 跳过路径匹配" if not tokens else "标题与变更路径/模块无重叠")
        ),
    }
    return [commit_link, path_match]


def l4_verdict(checks: list[dict[str, Any]]) -> str:
    """L4 总判定 (ADR-0019 决策 6, 与 rule_change 契约一致):

    FAIL 须双条件同时缺失 (有证据 AND 无关联提交 AND 标题无重叠) — 关联提交
    存在或标题与路径/模块重叠任一命中即 PASS (不因无关工作区文件误报)。
    顺序: ERROR 兜底 > 任一 PASS → PASS > 任一 FAIL → FAIL > 全 SKIP → SKIP。
    """
    statuses = [c.get("status", "SKIP") for c in checks]
    if any(s == "ERROR" for s in statuses):
        return "ERROR"
    if any(s == "PASS" for s in statuses):
        return "PASS"
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    return "SKIP"
