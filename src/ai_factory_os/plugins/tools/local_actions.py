"""plugins.tools.local_actions — 最小真实动作（只依赖标准库）。

用途：证明调度链路能驱动**真实副作用**，而不是只跑 mock。
本文件不含任何 OS 语义 —— 它只是"能写文件 / 能校验文件"这两个动作本身。
"""
from __future__ import annotations

from pathlib import Path


def write_artifact(path: str | Path, content: str) -> dict:
    """真实写文件。返回 {ok, path, bytes}。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(target), "bytes": target.stat().st_size}


def check_artifact(path: str | Path, *, expect: str) -> dict:
    """真实校验：文件存在 且 含期望内容。返回 {ok, reason}。"""
    target = Path(path)
    if not target.exists():
        return {"ok": False, "reason": f"产物不存在: {target}"}
    text = target.read_text(encoding="utf-8")
    if expect not in text:
        return {"ok": False, "reason": f"缺少期望内容: {expect!r}"}
    return {"ok": True, "reason": f"校验通过（{len(text)} 字符）"}
