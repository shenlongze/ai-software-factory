"""infrastructure.locking — 跨进程文件锁（技术底座，与业务无关）。

为什么独立成能力: release / rollback / governance / health / ops 的
read-modify-write 都靠它做竞态保护 —— 它是**与业务无关的技术机制**，
按 SSoT §一 归 infrastructure ✓（2026-09-15 从 _pending_migration 归位）。
"""
from .integrity_lock import file_lock

__all__ = ["file_lock"]
