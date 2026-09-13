"""factory-exec/exec/tools/filesystem.py — S10-018 Task 001 系统 Tool: filesystem.read。

设计依据 (S10-018-task001 用户约束 6 — 第一个真实 Tool):
```
filesystem.read: 读 workspace 内文件
  input:  {path: "src/parser.py"}        (相对路径, 沙箱内)
  output: {content: "<文件内容>", path: "src/parser.py"}
  沙箱:   只能访问 workspace root (ToolExecutor 经 context["workspace_root"] 注入)
  禁止:   任意系统路径 (/etc/passwd / ~/xxx / C:\\... / ../ 穿越 / symlink 逃逸)
```

沙箱实现 (防路径穿越铁律):
1. path 必须是非空相对路径 (绝对路径 / ~ / 盘符 → 拒绝 "path must be relative")。
2. 规范化: candidate = (workspace_root / path).resolve() — resolve 解 ../ 与
   symlink; 结果必须仍位于 workspace_root.resolve() 之下 (含等于 root 本身
   边界 — 文件不存在/目录/越界全部明确 ToolError, 不静默)。
3. 输出: 文件内容 (UTF-8 宽容解码) + 规范化后相对路径 (审计)。

依赖 (Removal Isolation): 只 import stdlib + 本层 tool 模型 (Tool/
ToolPermissionPolicy/ToolHandler); 不触碰其它 exec 主逻辑。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..tool import Tool, ToolHandler, ToolPermissionPolicy

#: 绝对路径前缀 (POSIX "/" / Windows 盘符 "C:" / 用户主目录 "~" — 全部拒绝)。
_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[/~])")


class ToolInputError(Exception):
    """Tool 输入/沙箱越界错误 (handler 内部使用 → ToolExecutor 转 ToolResult.failed)。"""


def _safe_resolve(workspace_root: str | Path, raw_path: str) -> Path:
    """沙箱内路径解析 (防穿越): 合法 → resolve 后的 Path; 非法 → ToolInputError。

    拒绝: 空/空白路径、绝对路径、~/主目录、盘符、resolve 后逃出 workspace root
    (含 symlink 逃逸 — resolve() 解链接后 must be inside)。
    """
    path_text = str(raw_path or "").strip()
    if not path_text:
        raise ToolInputError("path must be a non-empty relative path")
    if _ABSOLUTE_RE.match(path_text):
        raise ToolInputError("path must be relative (absolute paths are not allowed)")
    upper = path_text.upper()
    if "%2F" in upper or "%5C" in upper:
        raise ToolInputError("path must not contain encoded separators (%2F/%5C)")
    root = Path(workspace_root).resolve()
    candidate = (root / path_text).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ToolInputError("path outside workspace")
    return candidate


def filesystem_read_handler(input: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """filesystem.read handler: {path} → {content, path} (workspace 沙箱只读)。

    context["workspace_root"]: 沙箱根 (ToolExecutor 注入; 缺失 → 明确失败 —
    Tool 未装配沙箱根时禁止工作, 不假装成功)。
    """
    workspace_root = str(context.get("workspace_root") or "").strip()
    if not workspace_root:
        raise ToolInputError("workspace root not configured (tool executor has no workspace_root)")
    raw_path = str(input.get("path") or "").strip()
    target = _safe_resolve(workspace_root, raw_path)
    if not target.exists():
        raise ToolInputError(f"file not found: {raw_path}")
    if target.is_dir():
        raise ToolInputError(f"path is a directory (only files can be read): {raw_path}")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # 二进制宽容降级: 不冒充文本 (§6.3 失败安全 — 明确标注非文本)。
        content = target.read_bytes().decode("utf-8", errors="replace")
    rel = os.path.relpath(target, Path(workspace_root).resolve())
    return {"content": content, "path": rel}


def build_filesystem_read_tool() -> Tool:
    """构建系统 Tool filesystem.read (backend-1 白名单; 其他 Agent 默认禁止)。

    permission_policy (约束 8/9): backend-1 → 允许 filesystem.read; 其他
    Agent 默认禁止; 权限失败 → ToolExecutor 返回 ToolResult.failed +
    "permission denied" (Execution Loop 集成 → tool_failed 事件)。
    """
    return Tool(
        id="filesystem.read",
        name="Filesystem Read",
        description="读取 workspace 内文件内容 (沙箱只读; 禁止任意系统路径)",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}, "path": {"type": "string"}},
        },
        handler=filesystem_read_handler,
        permission_policy=ToolPermissionPolicy(allowed_agent_ids=["backend-1"]),
    )


__all__ = [
    "ToolInputError",
    "build_filesystem_read_tool",
    "filesystem_read_handler",
]
