"""services.execution.rules — 执行域的纯规则（无 IO，可单测）。

原 factory-exec/exec/patch_filter.py → kernel/node/patch_filter.py → 此处（绞杀刀13）。

Artifact Boundary（S10-083 P0）：
    Agent 生成的 patch 只允许包含用户代码产物；内部系统状态文件
    （execution_state.json / task_state.json / agent_memory.json / workflow 状态）
    禁止进入用户 patch —— Agent 可读取，不可修改。

实现：解析 unified diff，剥离黑名单文件的 hunk，保留其余。纯函数，零 IO。
"""
from __future__ import annotations

import re
from collections.abc import Iterable

#: 禁止进入用户 patch 的路径片段（匹配文件名/路径任意位置）
_BLOCKED_PATTERNS: tuple[str, ...] = (
    "execution_state.json",
    "task_state.json",
    "agent_memory.json",
    "workflow_state.json",
    "validation_result.json",
    "repair_task.json",
    "execution_plan.json",
    ".factory-state",
)

#: 允许的代码/文档扩展名（白名单兜底 —— 其它未知文件仍允许，仅黑名单强禁）
_ALLOWED_SUFFIXES: tuple[str, ...] = (
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".kt", ".go", ".rs",
    ".c", ".cpp", ".h", ".dart", ".swift", ".rb", ".php", ".sh",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".css", ".html", ".vue", ".sql", ".env.example", "requirements.txt",
    "Dockerfile", "Makefile", "package.json", "pom.xml", "build.gradle",
)

_CODE_SUFFIXES: tuple[str, ...] = (
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".dart", ".kt", ".cpp",
)


def _file_blocked(path: str) -> bool:
    """判断 diff 路径是否命中黑名单（内部系统状态文件）。"""
    normalized = path.replace("\\", "/")
    base = normalized.split("/")[-1]
    return any(pat in normalized or pat in base for pat in _BLOCKED_PATTERNS)


def filter_patch(patch_text: str) -> tuple[str, list[str]]:
    """剥离状态文件 hunk，返回（干净 patch, 被剥离文件列表）。

    - 空/非 diff 输入 → 原样返回（兼容旧产物）
    - 被剥离文件 → 记录列表（审计/告警用，不失败）
    """
    text = str(patch_text or "")
    if not text.strip():
        return text, []
    blocked: list[str] = []
    kept_lines: list[str] = []
    in_blocked_file = False

    for line in text.splitlines():
        header = re.match(r"^diff --git a/(.+) b/.+$", line)
        marker = re.match(r"^(\+\+\+|---) (a/|b/)?(.+)$", line)
        if header or marker:
            current = header.group(1) if header else marker.group(3)  # type: ignore[union-attr]
            in_blocked_file = _file_blocked(current)
            if in_blocked_file:
                blocked.append(current)
            else:
                kept_lines.append(line)
            continue
        if in_blocked_file:
            continue  # 跳过被禁文件的全部内容（diff 头 + hunks）
        kept_lines.append(line)

    return "\n".join(kept_lines), blocked


def validate_delivery(files: Iterable[str], *, require_code: bool = False) -> tuple[bool, str]:
    """交付校验：项目文件是否满足真实产物要求。

    require_code=True 且无任何代码文件 → (False, 原因) —— 消除空目录 PASS。
    """
    file_list = list(files)
    if require_code and not any(f.endswith(_CODE_SUFFIXES) for f in file_list):
        return False, "任务要求生成代码但项目无任何代码文件 (0 个)"
    return True, ""
