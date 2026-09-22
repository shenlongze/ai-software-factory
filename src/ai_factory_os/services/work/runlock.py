"""仓库级**跨进程**运行锁 —— 挡住"同一个仓库同一时间两个人跑" ✗。

Founder 的问题（2026-09-22）: **「同一个仓库同一时间 两个人改？？？」**
真实现状（读过代码）:
  · 同一进程内安全 ✓ —— `decomposition.claim_leaf()` 是 CAS 认领（两个 agent 不会拿同一张卡）,
    同批内写同一文件会被 `scheduler_pump._split_by_conflict()` **降级为串行** ✓
  · **执行期有沙箱隔离** ✓ —— 每个执行在自己的副本里干活（`kernel/sandbox.py`:
    `<work_root>/exec-sandbox-<id>/project`, copytree 出来 + 收尾以 **patch** 形式导出）
    ⇒ 边干边覆盖**不会**发生 ✓
  · **跨进程不安全** ✗ —— 代码自述"不做跨进程文件锁"; 两个终端同时跑同一项目时:
      ① 同一张叶可能被**双领**（重复干活 ✗）
      ② 收尾的 **patch 要回到同一个项目工作副本** ⇒ 后到的应用会冲突/覆盖且不易察觉 ✗
    （scheduler_pump 里 `repo-uncommitted` + 「待核」就是这类痕迹）
本模块补的正是这一层（最小改动; 真隔离 = 每任务 worktree, 那是下一刀 ✓）:
  · 跑之前**原子抢占** `<root>/projects/<P>/.run.lock`（`O_CREAT|O_EXCL`, 跨进程安全 ✓）
  · 抢不到 ⇒ **明确拒绝并告诉你是谁在跑**（不静默覆盖 ✗）
  · 锁里的 PID 已死 ⇒ 判定为**陈旧锁** ⇒ 自动接管（并如实说明"接管了陈旧锁" ✓, 不假装从没锁过）
  · `--force` ⇒ 强抢（会覆盖对方改动 ✗ ⇒ 必须显式要求）
  · 释放**只删自己的锁**（PID 不符 ⇒ 不删别人正在用的 ✗）
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RunLockError(RuntimeError):
    """锁被别人占着 —— 调用方据此拒绝开跑（不要静默继续 ✗）。"""

    def __init__(self, message: str, holder: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.holder = holder or {}


def _lock_path(root: Path | str, project_id: str) -> Path:
    base = Path(root)
    return (base / "projects" / project_id / ".run.lock") if project_id else (base / ".run.lock")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # 存在但不是我的 ⇒ 活着 ✓
    except OSError:
        return True          # 判不准 ⇒ 保守当"活着"（宁可不接管 ✗）
    return True


def read_lock(root: Path | str, project_id: str = "") -> dict[str, Any]:
    """读当前锁（没有 ⇒ {}）—— 只读, 给人看"谁在跑" ✓。"""
    p = _lock_path(root, project_id)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return {}


def acquire(root: Path | str, project_id: str = "", *, command: str = "",
            force: bool = False) -> dict[str, Any]:
    """抢锁。成功返回锁信息（含 `took_over` 标记）; 被占 ⇒ raise RunLockError ✓。"""
    p = _lock_path(root, project_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    me = {"pid": os.getpid(), "host": socket.gethostname(),
          "started_at": datetime.now(UTC).isoformat(timespec="seconds"), "command": command}
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(me, fh, ensure_ascii=False)
        return {**me, "took_over": False}
    except FileExistsError:
        pass
    held = read_lock(root, project_id)
    _same_host = (not held.get("host")) or held.get("host") == me["host"]
    _alive = _pid_alive(int(held.get("pid") or 0)) if _same_host else True
    if _alive and not force:
        who = f"PID {held.get('pid')}"
        if held.get("host"):
            who += f"@{held['host']}"
        raise RunLockError(
            f"另一个进程正在跑这个项目（{who}, 从 {held.get('started_at') or '未知时间'} 开始, "
            f"命令: {held.get('command') or '未知'}）—— 等它跑完, 或用 --force 强抢（会覆盖它的改动 ✗）",
            holder=held,
        )
    note = "（接管了陈旧锁: 原 PID 已不在 ✓）" if not _alive else "（★ --force 强抢: 对方的改动可能被覆盖 ✗）"
    try:
        p.write_text(json.dumps(me, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        raise RunLockError(f"写锁失败: {type(exc).__name__}") from exc
    return {**me, "took_over": True, "note": note, "previous": held}


def release(root: Path | str, project_id: str = "") -> bool:
    """释放锁 —— **只删自己的**（PID 不符 ⇒ 不动, 免得删了别人正在用的 ✗）。"""
    p = _lock_path(root, project_id)
    if not p.is_file():
        return False
    held = read_lock(root, project_id)
    if int(held.get("pid") or 0) not in (0, os.getpid()):
        return False
    try:
        p.unlink()
    except OSError:
        return False
    return True
