"""workflows/store.py — WorkflowStore: JSON 文件持久化 (单文件整体原子写, 标准库零依赖)。

设计依据:
- phase4a-status.md: JSON 持久化 — `.factory/workflows/workflows.json`, 原子写 os.replace,
  损坏文件报错 (参照 tasks/store.py 与 agents/store.py 模式)。
- 文件格式 (单文件双节, KISS):
  ```json
  {
    "workflows": {"feature-delivery": {Workflow dict}, ...},
    "runs":      {"WR-001": {WorkflowRun dict}, ...}
  }
  ```
  定义与运行实例同库: run 快照 workflow_id/workflow_name, 定义被删不影响历史运行。
- 原子写: 临时文件 + os.replace; 单进程本地使用, 不做文件锁。
- 损坏文件 (JSON 解析失败 / 模型校验失败 / 结构不符) → 抛 CorruptWorkflowStoreError,
  绝不静默返回空。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import Workflow, WorkflowRun


class WorkflowStoreError(Exception):
    """WorkflowStore 基础异常。"""


class CorruptWorkflowStoreError(WorkflowStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class WorkflowStore:
    """工作流定义 + 运行实例的 JSON 文件库 (单文件双节)。"""

    filename = "workflows.json"

    def __init__(self, workflows_dir: str | Path):
        self._dir = Path(workflows_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 读

    def _read_all(self) -> dict:
        """读整库为 {"workflows": {id: dict}, "runs": {id: dict}}; 不存在返回空库。"""
        if not self.path.exists():
            return {"workflows": {}, "runs": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptWorkflowStoreError(f"corrupt workflow store: {self.path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptWorkflowStoreError(f"corrupt workflow store: {self.path}: expected JSON object")
        for key in ("workflows", "runs"):
            if not isinstance(raw.get(key), dict):
                raise CorruptWorkflowStoreError(
                    f"corrupt workflow store: {self.path}: missing or invalid section {key!r}"
                )
        return raw

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """按 id 取工作流定义; 不存在返回 None。"""
        data = self._read_all()["workflows"].get(workflow_id)
        if data is None:
            return None
        return self._load_workflow(data)

    def list_workflows(self) -> list[Workflow]:
        """全部工作流定义 (按 id 排序)。"""
        workflows = []
        for data in self._read_all()["workflows"].values():
            workflows.append(self._load_workflow(data))
        return sorted(workflows, key=lambda w: w.id)

    def get_run(self, run_id: str) -> WorkflowRun | None:
        """按 run_id 取运行实例; 不存在返回 None。"""
        data = self._read_all()["runs"].get(run_id)
        if data is None:
            return None
        return self._load_run(data)

    def get_run_by_task(self, task_id: str) -> WorkflowRun | None:
        """按 task_id 取运行实例 (一个 task 至多一个 run); 不存在返回 None。"""
        for data in self._read_all()["runs"].values():
            run = self._load_run(data)
            if run.task_id == task_id:
                return run
        return None

    def list_runs(self) -> list[WorkflowRun]:
        """全部运行实例 (按 run_id 排序)。"""
        runs = []
        for data in self._read_all()["runs"].values():
            runs.append(self._load_run(data))
        return sorted(runs, key=lambda r: r.run_id)

    def _load_workflow(self, data: Any) -> Workflow:
        try:
            return Workflow.model_validate(data)
        except ValidationError as exc:
            raise CorruptWorkflowStoreError(f"corrupt workflow store: {self.path}: {exc}") from exc

    def _load_run(self, data: Any) -> WorkflowRun:
        try:
            return WorkflowRun.model_validate(data)
        except ValidationError as exc:
            raise CorruptWorkflowStoreError(f"corrupt workflow store: {self.path}: {exc}") from exc

    # ------------------------------------------------------------------ 写

    def save_workflow(self, workflow: Workflow) -> None:
        """upsert 工作流定义。"""
        raw = self._read_all()
        raw["workflows"][workflow.id] = workflow.to_dict()
        self._write_all(raw)

    def remove_workflow(self, workflow_id: str) -> bool:
        """删除工作流定义; 不存在返回 False (不影响已有运行实例)。"""
        raw = self._read_all()
        if workflow_id not in raw["workflows"]:
            return False
        del raw["workflows"][workflow_id]
        self._write_all(raw)
        return True

    def save_run(self, run: WorkflowRun) -> None:
        """upsert 运行实例。"""
        raw = self._read_all()
        raw["runs"][run.run_id] = run.to_dict()
        self._write_all(raw)

    def _write_all(self, data: dict) -> None:
        """原子写整库: 临时文件 + os.replace, 避免半写文件。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------ 便捷

    def workflow_ids(self) -> list[str]:
        """现有工作流定义 id 列表 (排序)。"""
        return sorted(self._read_all()["workflows"])

    def run_ids(self) -> list[str]:
        """现有运行实例 run_id 列表 (排序)。"""
        return sorted(self._read_all()["runs"])

    def next_run_id(self, prefix: str = "WR-") -> str:
        """自动编号: 取现有最大数字后缀 +1 (如 WR-001 → WR-002)。"""
        max_n = 0
        for run_id in self.run_ids():
            rest = run_id[len(prefix):] if run_id.startswith(prefix) else ""
            if rest.isdigit():
                max_n = max(max_n, int(rest))
        return f"{prefix}{max_n + 1:03d}"
