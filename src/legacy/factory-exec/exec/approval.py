"""factory-exec/exec/approval.py — ApprovalGate (Human 门禁; 应用 patch 前必批)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §2/§6):
- 铁律: 执行权 != 审核权 (Runtime 执行, Human 批准)。
- 必须人工批准: ✅ 应用代码修改 (patch apply) ✅ 删除文件 ✅ 依赖升级
  ✅ 测试失败仍提交 ✅ 任何超出允许范围的动作。
- 规则: Approval 后 Apply; 拒绝 → 反馈给 Agent 修复循环 (comment 记录);
  高风险动作 = 硬拒绝 + 审计 (Default Deny)。

职责 (门禁, 无执行权 — 设计 §2):
- request(): 执行结果 → 审批记录 (pending, 待 Human 决定)。
- decide(): approve|rejected (终态落库; 二次决定 → ApprovalError 响亮)。
- apply(): **仅 APPROVED** 可应用 patch 到目标项目 (未批/已拒 → 硬拒绝
  ApprovalError; 已应用 → 拒绝重复应用, 幂等保护)。
- 状态机: pending → approved|rejected; approved → applied (置位)。

apply 实现: patch 文件 (ExecutionResult patch Artifact.path) 经 git apply 写入
目标项目 (目标须为 git 仓库; 非 git 仓库 → ApprovalError 响亮, 不静默降级 —
防\"悄悄改用户环境\"的不可审计路径)。拒绝 feedback: comment 承载, 审计
org.execution.approved 只发 approve 终态 (rejected 不发 approved 事件 — 事件
报告状态转换, 拒绝的审计经 approval record + 后续修复循环)。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import re

from . import events as exec_events
from .models import ApprovalDecision, ApprovalRecord, ExecutionResult, new_id, utcnow
from .store import ExecStore

#: 高风险信号 (爆炸半径大 → 必须 tech_lead/compliance 批准)
_HIGH_RISK_PATTERNS: tuple[str, ...] = (
    r"^--- a/.*(?:delete|删除)",
    r"^\+\+\+ /dev/null",  # 文件删除 (unified diff 标准标记)
    r"^[-+]\s*(?:rm\s|os\.remove|shutil\.rmtree)",
    r"requirements\.txt|pyproject\.toml|package\.json",
    r"^diff --git a/(?:db/|migrations/|infra/|deploy)",
)
def classify_risk(patch_text: str, *, changed_files: int = 1) -> tuple[str, list[str]]:
    """分级审批: 按爆炸半径判定 risk_level 与 required_roles (确定性规则)。

    high  → 删除/依赖升级/基础设施/多模块 → tech_lead (+compliance 若涉密)
    medium → 跨文件改动/核心配置 → tech_lead
    low   → 单文件常规修改 → developer
    """
    text = str(patch_text or "")
    if any(re.search(pat, text, re.M) for pat in _HIGH_RISK_PATTERNS):
        return "high", ["tech_lead", "compliance"]
    if changed_files >= 3:
        return "medium", ["tech_lead"]
    if changed_files >= 2 or "config" in text[:2000].lower():
        return "medium", ["tech_lead"]
    return "low", ["developer"]


class ApprovalError(Exception):
    """审批门禁失败 (未批准应用/重复决定/重复应用/patch 缺失/应用失败)。"""


class ApprovalGate:
    """审批门 (记录 + decide + apply; 只检查不执行 — 应用权在 Human 批准后)。"""

    def __init__(self, store: ExecStore, *, logger: Any = None, git_bin: str = "git"):
        self._store = store
        self._logger = logger
        self._git_bin = git_bin

    @property
    def store(self) -> ExecStore:
        return self._store

    # ------------------------------------------------------------------ request

    def request(
        self,
        result: ExecutionResult,
        *,
        approval_id: str | None = None,
        risk_level: str | None = None,
        required_roles: list[str] | None = None,
    ) -> ApprovalRecord:
        """执行结果 → 审批记录 (pending; 应用 patch 前必经此门)。

        分级: risk_level/required_roles 显式传入, 或按 patch 爆炸半径
        classify_risk 自动判定 (M1a 分级审批)。
        """
        if result.status.value != "success":
            raise ApprovalError(
                f"cannot request approval for failed execution: {result.id}"
            )
        patch_text = ""
        try:
            patch_path = self._patch_artifact_path(result)
            patch_text = Path(patch_path).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — patch 缺失不影响审批创建
            patch_text = ""
        if risk_level is None or required_roles is None:
            level, roles = classify_risk(patch_text)
            risk_level = risk_level or level
            required_roles = required_roles or roles
        record = ApprovalRecord(
            id=approval_id or new_id("APR"),
            request_id=result.request_id,
            risk_level=str(risk_level or "low"),
            required_roles=list(required_roles or []),
        )
        self._store.save_approval(record)
        return record

    # ------------------------------------------------------------------ decide

    def decide(
        self,
        approval_id: str,
        decision: str | ApprovalDecision,
        *,
        decided_by: str,
        comment: str = "",
    ) -> ApprovalRecord:
        """Human 决定 (approve → approved / reject → rejected; 终态不可逆)。

        二次决定 (已 approved/rejected) → ApprovalError (响亮, 防覆盖审计)。
        CLI 动词 approve|deny 在命令层映射为语义值, 本层只接受语义终态。
        """
        record = self._store.get_approval(approval_id)
        if record is None:
            raise ApprovalError(f"approval not found: {approval_id}")
        value = decision.value if isinstance(decision, ApprovalDecision) else decision
        if value not in ("approved", "rejected"):
            raise ApprovalError(f"invalid approval decision: {value!r}")
        if record.decision is not ApprovalDecision.PENDING:
            raise ApprovalError(
                f"approval already decided: {approval_id} = {record.decision.value}"
            )
        updated = record.model_copy(
            update={
                "decision": ApprovalDecision(value),
                "decided_by": decided_by,
                "comment": comment,
                "decided_at": utcnow(),
            }
        )
        self._store.save_approval(updated)
        if updated.decision is ApprovalDecision.APPROVED:
            exec_events.record_execution_approved(self._logger, approval=updated)
        return updated

    def get(self, approval_id: str) -> ApprovalRecord | None:
        """按 id 取审批记录 (CLI status 用)。"""
        return self._store.get_approval(approval_id)

    def list(self, status: str | None = None) -> list[ApprovalRecord]:
        """审批记录清单 (--status 过滤; 无过滤 → 全部按 id 排序)。"""
        records = self._store.list_approvals()
        if status:
            records = [r for r in records if r.decision.value == status]
        return records

    # ------------------------------------------------------------------ apply

    def apply(
        self,
        approval_id: str,
        target_dir: str | Path,
    ) -> tuple[ApprovalRecord, str]:
        """应用已批准 patch 到目标项目 (未批准 → 硬拒绝; 幂等防重复应用)。

        返回 (更新后 approval, 应用后的 patch 文本)。patch 源: ExecutionResult
        的 patch Artifact.path (运行时落盘的 git diff 文件)。
        """
        record = self._store.get_approval(approval_id)
        if record is None:
            raise ApprovalError(f"approval not found: {approval_id}")
        if record.decision is not ApprovalDecision.APPROVED:
            raise ApprovalError(
                f"patch apply requires approved approval "
                f"(current: {record.decision.value}) — 应用 patch 前必批"
            )
        if record.applied:
            raise ApprovalError(
                f"patch already applied: {approval_id} (applied_at={record.applied_at})"
            )
        result = self._store.get_result_by_request(record.request_id)
        if result is None:
            raise ApprovalError(
                f"execution result not found for request {record.request_id}"
            )
        patch_path = self._patch_artifact_path(result)
        target = Path(target_dir)
        if not target.is_dir():
            raise ApprovalError(f"target project dir not found: {target}")
        self._git_apply(target, patch_path)
        updated = record.model_copy(
            update={"applied": True, "applied_at": utcnow().isoformat()}
        )
        self._store.save_approval(updated)
        patch_text = Path(patch_path).read_text(encoding="utf-8")
        exec_events.record_execution_applied(
            self._logger, approval=updated, result=result, patch_path=patch_path
        )
        return updated, patch_text

    @staticmethod
    def _patch_artifact_path(result: ExecutionResult) -> str:
        """执行结果的 patch Artifact 落盘路径 (缺失 → 响亮 ApprovalError)。"""
        for artifact in result.artifacts:
            if artifact.type.value == "patch" and artifact.path:
                return artifact.path
        raise ApprovalError(
            f"execution result has no patch artifact: {result.id}"
        )

    def _git_apply(self, target: Path, patch_path: str) -> None:
        """git apply 写入目标项目 (非 git 仓库 → 响亮错误, 不静默降级)。"""
        try:
            check = subprocess.run(
                [self._git_bin, "-C", str(target), "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as exc:
            raise ApprovalError(f"git command not found: {self._git_bin}") from exc
        if check.returncode != 0:
            raise ApprovalError(
                f"target is not a git repository: {target} — 应用前须可审计"
            )
        proc = subprocess.run(
            [self._git_bin, "-C", str(target), "apply", str(patch_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise ApprovalError(
                f"git apply failed (rc {proc.returncode}): {proc.stderr.strip()[:300]}"
            )
