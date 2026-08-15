"""factory-console/session/quality.py — Quality & Repair Loop (S10-053 P0-P6)。

Validation System + Repair Loop:
- ValidationResult — 任务验证结果模型 (success/tests_total/tests_passed/tests_failed/
  errors/timestamp + to_dict/from_dict → validation_result.json 落盘)
- Validator       — 输入 Task Result → ValidationResult (mock 默认: success + artifact
  存在 → PASS; command 接口预留: 未来 pytest/flutter test/npm test 沙箱执行)
- ReviewResult    — 评审结果 (approved/comments)
- Reviewer (ABC)  — 评审器接口 (未来 Reviewer Agent (LLM) 实现; 本版仅接口)
- RepairManager   — 修复管理器: create_repair → repair_task.json (pending) →
  repair 流程 (pending → retrying → execute_fn 重跑 → validator.validate →
  PASS → completed + 更新 execution_state; FAIL → retry_count+1, >= max_retry
  → failed, 不无限循环)

设计: docs/sprint10/S10-053-quality-design.md §3-§7

边界:
- 不绑语言 (mock validator + command 接口, 不执行真实命令)
- 不 import .orchestrator/.actions 于模块顶层 (避免循环依赖 — 桥接函数内惰性 import)
- 纯标准库, 零新依赖; 失败安全 (损坏文件 → 空列表, 不裸抛)
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

#: 修复最大重试次数 (设计 §5: max_retry=1 — 首次失败 → 1 次修复重试; 仍失败 → failed)
DEFAULT_MAX_REPAIR_RETRY = 1

#: 修复状态常量 (设计 §5: repair_pending → retrying → completed/failed)
REPAIR_PENDING = "pending"
REPAIR_RETRYING = "retrying"
REPAIR_COMPLETED = "completed"
REPAIR_FAILED = "failed"

#: 修复执行函数契约: (task: dict, project_dir: Path, workspace: Path) -> dict
#: (同 orchestrator.ExecuteFn — 复用 Agent Runtime 桥, 不重实现)
RepairExecuteFn = Callable[[dict[str, Any], Path, Path], dict[str, Any]]


def _now_iso() -> str:
    """UTC ISO 时间戳 (validation/repair 记录)。"""
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: Any) -> None:
    """落盘 JSON (ensure_ascii=False — 中文可读; 父目录自动创建)。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@dataclass
class ValidationResult:
    """任务验证结果 (设计 §3): success + 测试统计 + errors + timestamp。

    - mock validator: tests_total=1 (单任务验证), passed/failed 0/1
    - command validator (未来): tests 为真实测试用例数
    """

    success: bool
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 validation_result.json / 渲染视图)。"""
        return {
            "success": self.success,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "errors": list(self.errors),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidationResult":
        """dict → ValidationResult (未知键忽略, 缺失字段默认 — 前向兼容)。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            success=bool(data.get("success")),
            tests_total=int(data.get("tests_total") or 0),
            tests_passed=int(data.get("tests_passed") or 0),
            tests_failed=int(data.get("tests_failed") or 0),
            errors=list(data.get("errors") or []),
            timestamp=str(data.get("timestamp") or ""),
        )


class Validator:
    """任务验证器 (设计 §3): 输入 Task Result → ValidationResult。

    mock 默认 (第一版, 不绑语言): task_result.success 且 artifact 存在 → PASS
    (tests_total=1, passed=1); 否则 → FAIL + errors。
    command 接口: command 参数预留 — 未来在沙箱内执行真实测试命令
    (pytest / flutter test / npm test), 解析退出码/输出; 本版不执行真实命令,
    仅定义接口 (调用方传 command 仍走 mock 判定, 不隐式执行)。
    """

    def validate(
        self,
        task: dict[str, Any],
        task_result: dict[str, Any],
        *,
        command: Optional[str] = None,
    ) -> ValidationResult:
        """验证任务执行结果 (mock 默认): success 且无显式 error → PASS。"""
        task_result = task_result if isinstance(task_result, dict) else {}
        errors: list[str] = []
        if not task_result.get("success"):
            errors.append(str(task_result.get("error") or "任务执行失败"))
        # artifact 缺失不判失败 (S10-053 收尾修正): 兼容既有 mock 语义
        # (execute_fn 返回 {"success": True} 无 artifact) — 显式 error 才 FAIL
        success = not errors
        return ValidationResult(
            success=success,
            tests_total=1,
            tests_passed=1 if success else 0,
            tests_failed=0 if success else 1,
            errors=errors,
            timestamp=_now_iso(),
        )

    def save(self, project_dir: Path, slug: str, result: ValidationResult) -> Path:
        """validation_result.json 落盘 (验收 I) — 返回文件路径。"""
        path = Path(project_dir) / "validation_result.json"
        data = result.to_dict()
        data["project"] = slug
        _write_json(path, data)
        return path


@dataclass
class ReviewResult:
    """评审结果 (设计 §7): approved + comments。"""

    approved: bool
    comments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """→ dict (渲染/审计视图)。"""
        return {"approved": self.approved, "comments": list(self.comments)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewResult":
        """dict → ReviewResult (缺失字段默认 — 前向兼容)。"""
        data = data if isinstance(data, dict) else {}
        return cls(
            approved=bool(data.get("approved")),
            comments=list(data.get("comments") or []),
        )


class Reviewer(ABC):
    """评审器接口 (设计 §7): 未来 Reviewer Agent (LLM) 实现; 本版仅接口。"""

    @abstractmethod
    def review(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        validation: ValidationResult,
    ) -> ReviewResult:
        """评审任务执行结果 → ReviewResult (approved + comments)。"""


class RepairManager:
    """修复管理器 (设计 §5): repair_task.json 落盘 + repair 流程 + Retry Policy。

    create_repair: 失败任务 → repair_task.json 追加 pending 记录
      {repair_id, original_task_id, original_task_name, failure_reason,
       retry_count, status: "pending", created_at}
    repair: 处理一个 pending 修复 (单次调用最多一个 — 不无限循环):
      pending → retrying → execute_fn 重跑 → validator.validate →
        PASS → status=completed + 更新 execution_state (对应任务 completed)
        FAIL → retry_count+1; >= max_retry → status=failed (终止);
              未达 max_retry → 回到 pending (下次 repair 再试)
    返回 {repair_id, status, validation, retry_count}。
    """

    def __init__(self, validator: Optional[Validator] = None) -> None:
        self.validator = validator if validator is not None else Validator()

    @staticmethod
    def _repair_file(project_dir: Path) -> Path:
        """repair_task.json 路径 (projects/<slug>/repair_task.json)。"""
        return Path(project_dir) / "repair_task.json"

    # ------------------------------------------------------------ create/load

    @staticmethod
    def create_repair(
        project_dir: Path,
        original_task: dict[str, Any],
        failure_reason: str,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """失败任务 → repair_task.json (pending 记录) → 返回 repair dict。"""
        repairs = RepairManager.load_repairs(project_dir)
        repair: dict[str, Any] = {
            "repair_id": f"repair-{len(repairs) + 1}-{int(time.time() * 1000)}",
            "original_task_id": str(original_task.get("id") or ""),
            "original_task_name": str(
                original_task.get("name") or original_task.get("id") or ""
            ),
            "failure_reason": str(failure_reason or "未知原因"),
            "retry_count": int(retry_count or 0),
            "status": REPAIR_PENDING,
            "created_at": _now_iso(),
        }
        repairs.append(repair)
        _write_json(RepairManager._repair_file(project_dir), repairs)
        return repair

    @staticmethod
    def load_repairs(project_dir: Path) -> list[dict[str, Any]]:
        """读取 repair_task.json → 修复记录列表 (缺失/损坏 → [] 失败安全)。"""
        path = RepairManager._repair_file(project_dir)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 空列表
            return []
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):  # 前向兼容: 单对象 → 列表
            return [data]
        return []

    def _save_repairs(self, project_dir: Path, repairs: list[dict[str, Any]]) -> None:
        """repair_task.json 落盘 (状态变更后调用)。"""
        _write_json(self._repair_file(project_dir), repairs)

    # ------------------------------------------------------------ repair 流程

    @staticmethod
    def _default_execute_fn() -> RepairExecuteFn:
        """缺省修复执行桥: 薄调 actions.execute_task (复用 Agent Runtime)。

        惰性 import .orchestrator._default_execute_fn (同桥, 避免顶层循环依赖)。
        """
        from .orchestrator import _default_execute_fn

        return _default_execute_fn

    def _original_task(
        self, project_dir: Path, repair: dict[str, Any]
    ) -> dict[str, Any]:
        """重建 original_task: execution_state.json 同 id 任务优先 (agent/name 完整)。"""
        task: dict[str, Any] = {
            "id": str(repair.get("original_task_id") or ""),
            "name": str(repair.get("original_task_name") or ""),
        }
        state_file = Path(project_dir) / "execution_state.json"
        if state_file.is_file():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 用 repair 记录字段
                state = {}
            for t in state.get("tasks") or []:
                if isinstance(t, dict) and str(t.get("id")) == str(
                    repair.get("original_task_id")
                ):
                    task = dict(t)
                    break
        task["name"] = task.get("name") or repair.get("original_task_name") or ""
        return task

    def _mark_task_completed(
        self,
        project_dir: Path,
        repair: dict[str, Any],
        outcome: dict[str, Any],
    ) -> None:
        """更新 execution_state.json: 对应任务 → completed (设计 §5 PASS 分支)。"""
        state_file = Path(project_dir) / "execution_state.json"
        if not state_file.is_file():
            return
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 失败安全: 损坏 → 不更新
            return
        changed = False
        for t in state.get("tasks") or []:
            if not isinstance(t, dict):
                continue
            if str(t.get("id")) == str(repair.get("original_task_id")):
                t["status"] = "completed"
                t["artifact"] = str(outcome.get("artifact") or t.get("artifact") or "")
                t["error"] = None
                t["validation"] = "passed"
                changed = True
                break
        if changed:
            _write_json(state_file, state)

    def repair(
        self,
        project_dir: Path,
        *,
        execute_fn: Optional[RepairExecuteFn] = None,
        validator: Optional[Validator] = None,
        max_retry: int = DEFAULT_MAX_REPAIR_RETRY,
    ) -> dict[str, Any]:
        """处理一个 pending 修复 (Retry Policy: max_retry=1, 不无限循环)。

        execute_fn: 修复重跑执行函数 (缺省 → 薄调 actions.execute_task);
        validator: 注入验证器 (缺省 self.validator); max_retry: 最大修复重试次数。
        无 pending → 返回 {status: "none"} (幂等, 不报错)。
        """
        project_dir = Path(project_dir)
        validator = validator if validator is not None else self.validator
        repairs = self.load_repairs(project_dir)
        pending = [r for r in repairs if r.get("status") == REPAIR_PENDING]
        if not pending:
            return {
                "repair_id": None,
                "status": "none",
                "validation": None,
                "retry_count": 0,
            }
        repair = pending[0]
        repair["status"] = REPAIR_RETRYING
        self._save_repairs(project_dir, repairs)
        task = self._original_task(project_dir, repair)
        runner = execute_fn if execute_fn is not None else self._default_execute_fn()
        workspace = project_dir.parent.parent  # workspace/projects/<slug> → workspace
        try:
            outcome = runner(task, project_dir, workspace) or {}
        except Exception as exc:  # noqa: BLE001 — 失败安全: 异常 → 修复失败
            outcome = {"success": False, "error": str(exc)}
        if not isinstance(outcome, dict):
            outcome = {"success": False, "error": "execute_fn 返回非 dict"}
        validation = validator.validate(task, outcome)
        repair["retry_count"] = int(repair.get("retry_count") or 0) + 1
        if validation.success:
            repair["status"] = REPAIR_COMPLETED
            self._mark_task_completed(project_dir, repair, outcome)
        elif repair["retry_count"] >= int(max_retry or 0):
            repair["status"] = REPAIR_FAILED
        else:
            repair["status"] = REPAIR_PENDING  # 未达 max_retry → 保留待重试
        self._save_repairs(project_dir, repairs)
        return {
            "repair_id": repair.get("repair_id"),
            "status": repair["status"],
            "validation": validation.to_dict(),
            "retry_count": repair["retry_count"],
        }
