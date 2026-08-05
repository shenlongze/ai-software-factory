"""assignment/store.py — AssignmentStore: JSON 文件持久化 (单文件整体原子写, 标准库零依赖)。

设计依据:
- phase4b3-status.md: JSON 持久化 — `.factory/assignments/assignments.json`, 原子写
  os.replace, 损坏报错 (参照 agents/store.py 与 workflows/store.py 模式)。
- 目录由首次原子写自动创建 (同 runtime 模式, ADR-0006 决策 5): 不强制 init,
  不依赖 context.py 骨架。

文件格式: `{id: AgentAssignment dict}`, 按 id 排序写入 (人工审计与 git 差异友好)。
损坏文件 (JSON 解析失败 / 模型校验失败) → 抛 CorruptAssignmentStoreError, 绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from .models import AgentAssignment, AssignmentStatus


class AssignmentStoreError(Exception):
    """AssignmentStore 基础异常。"""


class CorruptAssignmentStoreError(AssignmentStoreError):
    """存储文件损坏 (JSON 解析失败或模型校验失败)。"""


class AssignmentStore:
    """工作关系 (Assignment) 的 JSON 文件库 (单文件单节, 以 id 为键)。"""

    filename = "assignments.json"

    def __init__(self, assignments_dir: str | Path):
        self._dir = Path(assignments_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 读

    def _read_all(self) -> dict[str, dict]:
        """读整库为 {id: dict}; 文件不存在返回空库。"""
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptAssignmentStoreError(f"corrupt assignment store: {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptAssignmentStoreError(
                f"corrupt assignment store: {self.path}: expected JSON object"
            )
        return raw

    def _load(self, data: Any) -> AgentAssignment:
        try:
            return AgentAssignment.model_validate(data)
        except ValidationError as exc:
            raise CorruptAssignmentStoreError(f"corrupt assignment store: {self.path}: {exc}") from exc

    def load(self, assignment_id: str) -> AgentAssignment | None:
        """按 id 取单条; 不存在返回 None。"""
        data = self._read_all().get(assignment_id)
        if data is None:
            return None
        return self._load(data)

    def load_all(self) -> dict[str, AgentAssignment]:
        """全部记录 {id: 模型}。"""
        return {k: self._load(v) for k, v in self._read_all().items()}

    def list(
        self,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
        status: AssignmentStatus | str | None = None,
    ) -> list[AgentAssignment]:
        """全部 Assignment (按 id 排序), 可选按任务/Agent/状态过滤。"""
        want = AssignmentStatus.parse(status) if isinstance(status, str) else status
        items = []
        for a in self.load_all().values():
            if task_id is not None and a.task_id != task_id:
                continue
            if agent_id is not None and a.agent_id != agent_id:
                continue
            if want is not None and a.status is not want:
                continue
            items.append(a)
        return sorted(items, key=lambda a: a.id)

    # ------------------------------------------------------------------ 写

    def save(self, assignment: AgentAssignment) -> None:
        """upsert 单条 (id 为键; 状态推进也走此路径: 保存新 status 即覆盖)。"""
        raw = self._read_all()
        raw[assignment.id] = assignment.to_dict()
        self._write_all(raw)

    def remove(self, assignment_id: str) -> bool:
        """删除单条; 不存在返回 False。"""
        raw = self._read_all()
        if assignment_id not in raw:
            return False
        del raw[assignment_id]
        self._write_all(raw)
        return True

    def _write_all(self, items: dict[str, dict]) -> None:
        """原子写整库: 临时文件 + os.replace, 避免半写文件; 按 id 排序 (审计友好)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {k: items[k] for k in sorted(items)}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 便捷

    def assignment_ids(self) -> list[str]:
        """现有 Assignment id 列表 (排序)。"""
        return sorted(self._read_all())

    def next_id(self, prefix: str = "ASG-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 ASG-001 → ASG-002)。"""
        max_n = 0
        for assignment_id in self.assignment_ids():
            rest = assignment_id[len(prefix):] if assignment_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"
