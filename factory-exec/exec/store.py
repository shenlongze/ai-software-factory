"""factory-exec/exec/store.py — 执行独立数据空间 (原子写, 损坏响亮失败)。

设计依据 (同 factory-org store / intelligence store 模式):
```
factory-exec/ (Phase A Extension):
  store: 独立数据空间 <root>/exec/
         requests.json    {"requests": {id: ExecutionRequest dict}}
         results.json     {"results": {id: ExecutionResult dict}}
         artifacts.json   {"artifacts": {id: Artifact dict}}
         approvals.json   {"approvals": {id: ApprovalRecord dict}}
         patches/          patch 文件落盘目录 (<request_id>.patch)
  — 与 tasks/agents/product/intelligence/org 等数据空间完全分离;
    删除 factory-exec 不影响 Factory (Core 零感知)
```

损坏语义 (同 ProductStore/IntelligenceStore): 核心目录数据损坏 → 响亮
CorruptExecStoreError (绝不静默返回空); 原子写 = 临时文件 + os.replace。
本模块只做持久化 (读/写整库), 无业务逻辑; **零顶层 imports events**
(Removal Isolation); 只依赖 stdlib + pydantic + 本层 models。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .models import (
    ApprovalRecord,
    Artifact,
    ExecutionRequest,
    ExecutionResult,
)

T = TypeVar("T", bound=BaseModel)


class ExecStoreError(Exception):
    """ExecStore 基础异常。"""


class CorruptExecStoreError(ExecStoreError):
    """存储文件损坏 (JSON 解析失败 / 结构不符 / 模型校验失败)。"""


class _SectionStore(Generic[T]):
    """单实体 JSON 记录库基类 (原子写/损坏响亮失败; 子类声明类属性即可)。"""

    _filename: str
    _section: str
    _model: type[T]

    def __init__(self, exec_dir: str | Path):
        self._dir = Path(exec_dir)

    @property
    def dir(self) -> Path:
        """数据空间目录 (<root>/exec)。"""
        return self._dir

    # ------------------------------------------------------------------ 读

    def _path(self) -> Path:
        return self._dir / self._filename

    def _read_all(self) -> dict[str, dict[str, Any]]:
        """读整库 {id: dict}; 文件不存在返回空库 (首次写前合法状态)。"""
        path = self._path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CorruptExecStoreError(
                f"corrupt exec store: {path}: {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get(self._section), dict):
            raise CorruptExecStoreError(
                f"corrupt exec store: {path}: missing or invalid section "
                f"{self._section!r}"
            )
        return raw[self._section]

    def _load(self, data: Any) -> T:
        try:
            return self._model.model_validate(data)
        except ValidationError as exc:
            raise CorruptExecStoreError(
                f"corrupt exec store: {self._path()}: {exc}"
            ) from exc

    # ------------------------------------------------------------------ 写

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        """原子写单文件: 临时文件 + os.replace (同目录, 同文件系统原子性)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path()
        tmp = self._dir / f".{self._filename}.{os.getpid()}.tmp"
        payload = {self._section: dict(sorted(records.items()))}
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, path)

    # ------------------------------------------------------------------ 通用 API

    def save(self, record: T) -> None:
        """upsert 记录 (同 id 覆盖 = 状态流转经 model_copy 新实例后落库)。"""
        records = self._read_all()
        records[record.id] = record.to_dict()  # type: ignore[attr-defined]
        self._write(records)

    def get(self, record_id: str) -> T | None:
        """按 id 取记录; 不存在返回 None。"""
        data = self._read_all().get(record_id)
        if data is None:
            return None
        return self._load(data)

    def list_all(self) -> list[T]:
        """全部记录 (按 id 排序, 审计友好)。"""
        return sorted(
            (self._load(data) for data in self._read_all().values()),
            key=lambda r: r.id,  # type: ignore[attr-defined, return-value]
        )

    def count(self) -> int:
        """记录总数。"""
        return len(self._read_all())

    def delete(self, record_id: str) -> bool:
        """删除记录; 不存在返回 False (幂等)。"""
        records = self._read_all()
        if record_id not in records:
            return False
        del records[record_id]
        self._write(records)
        return True


class RequestStore(_SectionStore[ExecutionRequest]):
    """ExecutionRequest 持久化 (requests.json)。"""

    _filename = "requests.json"
    _section = "requests"
    _model = ExecutionRequest


class ResultStore(_SectionStore[ExecutionResult]):
    """ExecutionResult 持久化 (results.json)。"""

    _filename = "results.json"
    _section = "results"
    _model = ExecutionResult


class ArtifactStore(_SectionStore[Artifact]):
    """Artifact 持久化 (artifacts.json; 与结果内嵌产物同源)。"""

    _filename = "artifacts.json"
    _section = "artifacts"
    _model = Artifact


class ApprovalStore(_SectionStore[ApprovalRecord]):
    """ApprovalRecord 持久化 (approvals.json)。"""

    _filename = "approvals.json"
    _section = "approvals"
    _model = ApprovalRecord


class ExecStore:
    """执行数据空间门面: 四子库 (requests/results/artifacts/approvals)。

    patches_dir: patch 文件落盘目录 (<exec_dir>/patches) — 与 JSON 数据空间
    同目录, 统一清理/迁移。
    """

    def __init__(self, exec_dir: str | Path):
        self._dir = Path(exec_dir)
        self._requests = RequestStore(self._dir)
        self._results = ResultStore(self._dir)
        self._artifacts = ArtifactStore(self._dir)
        self._approvals = ApprovalStore(self._dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def patches_dir(self) -> Path:
        return self._dir / "patches"

    # ------------------------------------------------------------- requests

    def save_request(self, record: ExecutionRequest) -> None:
        self._requests.save(record)

    def get_request(self, request_id: str) -> ExecutionRequest | None:
        return self._requests.get(request_id)

    def list_requests(self) -> list[ExecutionRequest]:
        return self._requests.list_all()

    def count_requests(self) -> int:
        return self._requests.count()

    # -------------------------------------------------------------- results

    def save_result(self, record: ExecutionResult) -> None:
        self._results.save(record)

    def get_result(self, result_id: str) -> ExecutionResult | None:
        return self._results.get(result_id)

    def get_result_by_request(self, request_id: str) -> ExecutionResult | None:
        """按 request_id 取执行结果 (审批 apply 定位 patch 用)。"""
        for result in self._results.list_all():
            if result.request_id == request_id:
                return result
        return None

    def list_results(self) -> list[ExecutionResult]:
        return self._results.list_all()

    def count_results(self) -> int:
        return self._results.count()

    # ------------------------------------------------------------- artifacts

    def save_artifact(self, record: Artifact) -> None:
        self._artifacts.save(record)

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def list_artifacts(self) -> list[Artifact]:
        return self._artifacts.list_all()

    def count_artifacts(self) -> int:
        return self._artifacts.count()

    # ------------------------------------------------------------- approvals

    def save_approval(self, record: ApprovalRecord) -> None:
        self._approvals.save(record)

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        return self._approvals.get(approval_id)

    def list_approvals(self) -> list[ApprovalRecord]:
        return self._approvals.list_all()

    def count_approvals(self) -> int:
        return self._approvals.count()
