"""factory-console/chat_store.py — S10-006.5 P1-A 对话记录存储 (最小版)。

轻量 JSON 存储 (KISS, 不重设计): 项目 → 消息列表 (append-only)。
- 文件: <root>/chat.json (root = 工厂根; 与 org/runtimes 平级)
- 记录: {project_id, message, created_at, run_id?}
- 失败安全: 文件损坏/不可写 → 读返回 [] / 写静默跳过 (聊天记录不影响
  核心流程 — 启动/审批/执行不受对话存储故障影响)。

只服务 POST /api/projects/{id}/chat 的消息落库 ("已启动 → 记录消息");
"未启动 → message 作为 idea 更新 + 触发 start" 由 api/workflow_start.py
组合 (本模块只存消息, 不判状态, 不触发执行 — 单一职责)。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: 单文件消息上限 (防无限增长; 超出丢最旧 — KISS 滚动窗口)
MAX_MESSAGES_PER_PROJECT = 500


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationStore:
    """对话记录 (append-only JSON; 线程安全 RLock)。"""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.is_file():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = {
                        str(k): list(v) for k, v in raw.items() if isinstance(v, list)
                    }
        except (OSError, ValueError):
            self._data = {}  # 损坏 → 空 (失败安全, 不拖垮 API)

    def _save(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return True
        except OSError:
            return False  # 不可写 → 静默 (记录尽力而为)

    def append(self, project_id: str, message: str, *, run_id: str | None = None) -> dict[str, Any]:
        """追加一条消息; 返回记录 {project_id, message, created_at, run_id?}。"""
        record: dict[str, Any] = {
            "project_id": project_id,
            "message": message,
            "created_at": _utc_now_str(),
        }
        if run_id:
            record["run_id"] = run_id
        with self._lock:
            messages = self._data.setdefault(project_id, [])
            messages.append(record)
            if len(messages) > MAX_MESSAGES_PER_PROJECT:
                del messages[: len(messages) - MAX_MESSAGES_PER_PROJECT]
            self._save()
        return record

    def list(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._data.get(project_id, []))

    def clear_project(self, project_id: str) -> bool:
        """删除项目全部对话记录 (S10-006.5 项目管理 — DELETE /projects/{id} 清理)。

        无记录 → True (幂等); 写盘失败 → False (失败安全: 聊天记录清理
        尽力而为, 不拖垮项目删除 — 删除主体已由 org 完成)。
        """
        with self._lock:
            if project_id not in self._data:
                return True
            del self._data[project_id]
            return self._save()

    def count(self, project_id: str) -> int:
        with self._lock:
            return len(self._data.get(project_id, []))


__all__ = ["ConversationStore", "MAX_MESSAGES_PER_PROJECT"]
