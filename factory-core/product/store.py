"""factory-core/product/store.py — ProductStore: 独立数据空间 JSON 持久化 (原子写)。

设计依据:
- phase9a-status.md 冻结约束 (Extension 独立): `.factory/product/` 独立数据空间,
  与 tasks/agents/workflows/providers 等完全分离, 删除 product/ 不影响 Factory。
- 参照 providers/store.py + workflows/store.py 模式: 原子写 os.replace; 损坏文件
  (JSON 解析失败 / 结构不符 / 模型校验失败) → CorruptProductStoreError, 绝不
  静默返回空。
- 文件布局 (每文件一节或多节, KISS):
  ```
  .factory/product/
  ├── ideas.json       {"ideas": {id: ProductIdea dict}}
  ├── artifacts.json   {"artifacts": {id: Artifact dict}}
  ├── approvals.json   {"gates": {id: ApprovalGate dict},
  │                    "requests": {id: ApprovalRequest dict},
  │                    "decisions": {id: ApprovalDecision dict}}
  └── workflows.json   {"workflows": {id: ProductWorkflow dict}}
  ```
- 原子写: 临时文件 + os.replace; 单进程本地使用, 不做文件锁。
- 本模块只做持久化 (读/写整库), 无业务逻辑 (业务在 service.py), 零顶层 imports
  events (Removal Isolation 同 provider 模式)。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
    Artifact,
    ProductIdea,
    ProductWorkflow,
)

#: 每文件的节名 → 校验模型 (读路径按节恢复为领域对象)
_SECTIONS: dict[str, dict[str, type[BaseModel]]] = {
    "ideas.json": {"ideas": ProductIdea},
    "artifacts.json": {"artifacts": Artifact},
    "approvals.json": {
        "gates": ApprovalGate,
        "requests": ApprovalRequest,
        "decisions": ApprovalDecision,
    },
    "workflows.json": {"workflows": ProductWorkflow},
}


class ProductStoreError(Exception):
    """ProductStore 基础异常。"""


class CorruptProductStoreError(ProductStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class ProductStore:
    """产品智能层的 JSON 文件库 (独立空间 <root>/product/, 四文件多节)。"""

    def __init__(self, product_dir: str | Path):
        self._dir = Path(product_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    # ------------------------------------------------------------------ 读

    def _read_all(self, filename: str) -> dict:
        """读单文件为 {节名: {id: dict}}; 文件不存在返回空库 (各节空 dict)。"""
        sections = _SECTIONS[filename]
        path = self._dir / filename
        if not path.exists():
            return {name: {} for name in sections}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptProductStoreError(f"corrupt product store: {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise CorruptProductStoreError(
                f"corrupt product store: {path}: expected JSON object"
            )
        for name in sections:
            if not isinstance(raw.get(name), dict):
                raise CorruptProductStoreError(
                    f"corrupt product store: {path}: missing or invalid section {name!r}"
                )
        return raw

    def _load(self, filename: str, model: type[BaseModel], data: Any) -> BaseModel:
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise CorruptProductStoreError(
                f"corrupt product store: {self._dir / filename}: {exc}"
            ) from exc

    def _list(self, filename: str, section: str, model: type[BaseModel]) -> list[Any]:
        """节内全部记录 (按 id 排序, 审计友好)。"""
        records = [
            self._load(filename, model, data)
            for data in self._read_all(filename)[section].values()
        ]
        return sorted(records, key=lambda r: r.id)  # type: ignore[return-value]

    def _get(self, filename: str, section: str, model: type[BaseModel], record_id: str) -> Any | None:
        data = self._read_all(filename)[section].get(record_id)
        if data is None:
            return None
        return self._load(filename, model, data)

    # ------------------------------------------------------------------ 写

    def _write(self, filename: str, data: dict) -> None:
        """原子写单文件: 临时文件 + os.replace; 各节按 id 排序 (审计友好)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / filename
        tmp = self._dir / f".{filename}.{os.getpid()}.tmp"
        payload = {name: dict(sorted(records.items())) for name, records in data.items()}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    def _save(self, filename: str, section: str, record: BaseModel) -> None:
        raw = self._read_all(filename)
        raw[section][record.id] = record.to_dict()  # type: ignore[attr-defined]
        self._write(filename, raw)

    # ------------------------------------------------------------------ ideas

    def save_idea(self, idea: ProductIdea) -> None:
        """upsert 想法 (覆盖同 id)。"""
        self._save("ideas.json", "ideas", idea)

    def get_idea(self, idea_id: str) -> ProductIdea | None:
        return self._get("ideas.json", "ideas", ProductIdea, idea_id)  # type: ignore[return-value]

    def list_ideas(self) -> list[ProductIdea]:
        return self._list("ideas.json", "ideas", ProductIdea)  # type: ignore[return-value]

    # ------------------------------------------------------------------ artifacts

    def save_artifact(self, artifact: Artifact) -> None:
        """upsert Artifact (覆盖同 id; version 递增由 service 负责)。"""
        self._save("artifacts.json", "artifacts", artifact)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._get("artifacts.json", "artifacts", Artifact, artifact_id)  # type: ignore[return-value]

    def list_artifacts(self) -> list[Artifact]:
        return self._list("artifacts.json", "artifacts", Artifact)  # type: ignore[return-value]

    def list_artifacts_by_type(self, artifact_type: str) -> list[Artifact]:
        return [a for a in self.list_artifacts() if a.type == artifact_type]

    # ------------------------------------------------------------------ approvals (gates/requests/decisions)

    def save_gate(self, gate: ApprovalGate) -> None:
        """upsert 审批门定义 (id 默认 = artifact_type)。"""
        self._save("approvals.json", "gates", gate)

    def get_gate(self, gate_id: str) -> ApprovalGate | None:
        return self._get("approvals.json", "gates", ApprovalGate, gate_id)  # type: ignore[return-value]

    def list_gates(self) -> list[ApprovalGate]:
        return self._list("approvals.json", "gates", ApprovalGate)  # type: ignore[return-value]

    def save_request(self, request: ApprovalRequest) -> None:
        """upsert 审批请求 (decide 回填经 model_copy 新实例)。"""
        self._save("approvals.json", "requests", request)

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._get("approvals.json", "requests", ApprovalRequest, request_id)  # type: ignore[return-value]

    def list_requests(self) -> list[ApprovalRequest]:
        return self._list("approvals.json", "requests", ApprovalRequest)  # type: ignore[return-value]

    def list_pending_requests(self) -> list[ApprovalRequest]:
        return [r for r in self.list_requests() if r.status == ApprovalStatus.PENDING.value]

    def save_decision(self, decision: ApprovalDecision) -> None:
        """追加审批决定 (不可变记录)。"""
        self._save("approvals.json", "decisions", decision)

    def get_decision(self, decision_id: str) -> ApprovalDecision | None:
        return self._get("approvals.json", "decisions", ApprovalDecision, decision_id)  # type: ignore[return-value]

    def list_decisions(self) -> list[ApprovalDecision]:
        return self._list("approvals.json", "decisions", ApprovalDecision)  # type: ignore[return-value]

    # ------------------------------------------------------------------ workflows

    def save_workflow(self, workflow: ProductWorkflow) -> None:
        """upsert 产品工作流 (状态流转经 model_copy 新实例)。"""
        self._save("workflows.json", "workflows", workflow)

    def get_workflow(self, workflow_id: str) -> ProductWorkflow | None:
        return self._get("workflows.json", "workflows", ProductWorkflow, workflow_id)  # type: ignore[return-value]

    def get_workflow_by_idea(self, idea_id: str) -> ProductWorkflow | None:
        """按 idea_id 取工作流 (一个 idea 至多一个 run); 不存在返回 None。"""
        for data in self._read_all("workflows.json")["workflows"].values():
            wf = self._load("workflows.json", ProductWorkflow, data)
            if wf.idea_id == idea_id:  # type: ignore[attr-defined]
                return wf  # type: ignore[return-value]
        return None

    def list_workflows(self) -> list[ProductWorkflow]:
        return self._list("workflows.json", "workflows", ProductWorkflow)  # type: ignore[return-value]
