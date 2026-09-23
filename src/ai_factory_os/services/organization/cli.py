"""src/ai_factory_os/services/organization/cli.py — 组织 CLI (`factory-org` console script + 主 CLI 共享命令)。

命令 (Phase 16A 任务清单):
```
factory-org company create --template software_company --name X
factory-org company show <company_id>
factory-org employee hire --company X --role developer --capabilities python,java
factory-org employee list [--company X] [--role R] [--capability C]
factory-org authority check --role developer --permission release.approve
factory-org knowledge add --company X --domain docs --content "..."
factory-org knowledge list --company X
factory-org workflow create/list/show/run/status (S7-003 组织级编排壳)
factory-org approval list|show|approve|reject (S9-001 人工审批门)
```

架构:
- cmd_* 函数签名 (root: Path, args) → dict — 主 CLI (factory-core/cli) 延迟
  import 本模块后复用同一实现 (org 命令并入主 CLI, 单一实现零复制)。
- 每命令在 logger_scope 内打开事件库 (root/factory.db) + EventLogger,
  event_seq 在块内取 (WAL 关闭陷阱, 同 factory CLI 模式)。
- 错误映射: NotFoundError → exit_code 7 (未找到), 其余业务错误 → 1;
  cmd_* 捕获返回错误 dict, 不抛 (双 CLI 复用, 零异常管道)。
- --role 接受角色 id 或角色名 (大小写不敏感, 模板角色名 Developer ↔
  --role developer); --employee 接受员工 id。
- 只读命令发审计事件 (ADR-0002: 所有 CLI 行为必须产生 Event)。

Removal Isolation: 本模块只依赖 factory-core events 层 (Extension → Core
单向依赖); factory-core 零顶层 imports 本包。
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ai_factory_os.infrastructure.events.logger import EventLogger
from ai_factory_os.infrastructure.events.types import EventType
from ai_factory_os.infrastructure.events.store import EventStore

from . import events as org_events
from .approval import ApprovalError
from .artifact import ArtifactRegistry, ArtifactStateError
from .lifecycle import (
    NotFoundError,
    OrgLifecycle,
    OrgLifecycleError,
)
from .project_adoption import ProjectAdoption
from .projects import ProjectStore
from .store import OrgStore
from .workflow import (
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowError,
)

DEFAULT_ROOT = Path.home() / ".factory"


@contextmanager
def _logger_scope(root: Path) -> Iterator[EventLogger]:
    """打开事件库 + EventLogger 作用域 (退出关闭连接, 同 ctx.logger_scope)。"""
    store = EventStore(root / "factory.db")
    try:
        yield EventLogger(store)
    finally:
        store.close()


def _org_store(root: Path) -> OrgStore:
    return OrgStore(root / "org")


def _resolve_role_id(
    store: OrgStore, company_id: str | None, role_ref: str
) -> str:
    """角色引用 → 角色 id (S7-001 统一解析, 大小写不敏感)。

    有 company 作用域 → 委托 OrgLifecycle.resolve_role_ref (3 链: id 精确 /
    公司内名称大小写不敏感 / exec 注册表 role_ref 匹配 — 双体系统一);
    无 company → 全局 id/名称匹配 (employee list 全库过滤场景)。

    未找到 → NotFoundError (CLI 层错误映射 rc 7)。
    """
    if company_id is not None:
        return OrgLifecycle(store).resolve_role_ref(company_id, role_ref)
    if store.get_role(role_ref) is not None:
        return role_ref
    for role in store.list_roles():
        if role.name.strip().lower() == role_ref.strip().lower():
            return role.id
    raise NotFoundError(f"role not found: {role_ref!r}")


def _error(message: str, exit_code: int = 1) -> dict:
    return {"ok": False, "error": message, "exit_code": exit_code}


def _capabilities(args: Any) -> list[str]:
    raw = getattr(args, "capabilities", None) or ""
    return [c.strip() for c in raw.split(",") if c.strip()]


# ------------------------------------------------------------------ company

def cmd_company_create(root: Path, args: Any) -> dict:
    """company create — 模板实例化公司 (org.company.created 链事件)。"""
    with _logger_scope(root) as logger:
        try:
            company = OrgLifecycle(_org_store(root), logger=logger).create_company(
                args.name,
                template=getattr(args, "template", "solo") or "solo",
                company_id=getattr(args, "id", None),
            )
        except OrgLifecycleError as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_COMPANY_CREATED)
    return {
        "ok": True,
        "company": company.to_dict(),
        "department_count": len(company.departments),
        "event_seq": event_seq,
        "exit_code": 0,
    }





def _json_object(raw: str | None) -> dict[str, Any] | None:
    """--metadata/--payload JSON 对象解析 (None → None; 非法/非对象 → ValueError 响亮)。"""
    if raw is None:
        return None
    import json

    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("metadata/payload must be a JSON object")
    return value


def _artifact_registry(root: Path, logger: Any) -> ArtifactRegistry:
    return ArtifactRegistry(ProjectStore(root / "org"), logger=logger)


def cmd_artifact_create(root: Path, args: Any) -> dict:
    """artifact create — 创建产物 (org.artifact.created; 关联校验 + 契约载荷)。"""
    with _logger_scope(root) as logger:
        try:
            artifact = _artifact_registry(root, logger).create(
                args.stage,
                args.type,
                project_id=args.project,
                task_id=args.task,
                ref=args.ref,
                producer_role=args.producer_role,
                producer_agent=args.producer_agent,
                version=args.version,
                location=args.location,
                metadata=_json_object(args.metadata),
                artifact_id=args.id,
            )
        except (OrgLifecycleError, ArtifactStateError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_ARTIFACT_CREATED)
    return {"ok": True, "artifact": artifact.to_dict(), "event_seq": event_seq, "exit_code": 0}


def cmd_artifact_get(root: Path, args: Any) -> dict:
    """artifact get — 产物详情 (org.artifact.viewed 审计; 含 archived 可查)。"""
    with _logger_scope(root) as logger:
        try:
            artifact = _artifact_registry(root, logger).get(args.artifact_id)
        except (OrgLifecycleError, ArtifactStateError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        org_events.record_artifact_viewed(
            logger, count=1, filters={"artifact_id": args.artifact_id}
        )
        event_seq = org_events.last_seq(logger, EventType.ORG_ARTIFACT_VIEWED)
    return {"ok": True, "artifact": artifact.to_dict(), "event_seq": event_seq, "exit_code": 0}


def _artifact_filters(args: Any) -> dict[str, Any]:
    return {
        "project_id": args.project or None,
        "stage_id": args.stage or None,
        "task_id": args.task or None,
        "type_": args.type or None,
        "status": args.status or None,
        "include_archived": bool(getattr(args, "include_archived", False)),
    }


def cmd_artifact_query(root: Path, args: Any) -> dict:
    """artifact list/query — 组合过滤查询 (org.artifact.viewed 审计)。"""
    with _logger_scope(root) as logger:
        artifacts = _artifact_registry(root, logger).query(**_artifact_filters(args))
        org_events.record_artifact_viewed(logger, count=len(artifacts), filters=_artifact_filters(args))
        event_seq = org_events.last_seq(logger, EventType.ORG_ARTIFACT_VIEWED)
    return {
        "ok": True,
        "artifacts": [a.to_dict() for a in artifacts],
        "count": len(artifacts),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_artifact_update(root: Path, args: Any) -> dict:
    """artifact update — 更新字段 (org.artifact.updated; 状态只经转换表)。"""
    with _logger_scope(root) as logger:
        try:
            artifact = _artifact_registry(root, logger).update(
                args.artifact_id,
                ref=args.ref,
                producer_role=args.producer_role,
                producer_agent=args.producer_agent,
                version=args.version,
                location=args.location,
                metadata=_json_object(args.metadata),
            )
        except (OrgLifecycleError, ArtifactStateError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_ARTIFACT_UPDATED)
    return {"ok": True, "artifact": artifact.to_dict(), "event_seq": event_seq, "exit_code": 0}


def cmd_artifact_archive(root: Path, args: Any) -> dict:
    """artifact archive — 软删归档 (→archived 终态; org.artifact.archived)。"""
    with _logger_scope(root) as logger:
        try:
            artifact = _artifact_registry(root, logger).archive(args.artifact_id)
        except (OrgLifecycleError, ArtifactStateError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_ARTIFACT_ARCHIVED)
    return {"ok": True, "artifact": artifact.to_dict(), "event_seq": event_seq, "exit_code": 0}


def cmd_artifact_validate(root: Path, args: Any) -> dict:
    """artifact validate — 契约校验 (通过→validated / 失败→invalid; 事件审计)。

    成功路径 (ok=True) 包括校验失败 (result.ok=False, 产物置 invalid) —
    操作本身合法执行; 非法状态跳转 (如 created 未生成直接校验) → rc 1。
    """
    with _logger_scope(root) as logger:
        try:
            artifact, result = _artifact_registry(root, logger).validate(
                args.artifact_id, payload=_json_object(args.payload)
            )
        except (OrgLifecycleError, ArtifactStateError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_type = (
            EventType.ORG_ARTIFACT_VALIDATED if result.ok else EventType.ORG_ARTIFACT_FAILED
        )
        event_seq = org_events.last_seq(logger, event_type)
    return {
        "ok": True,
        "artifact": artifact.to_dict(),
        "result": result.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


# ------------------------------------------------------------------ workflow (S7-003)
# factory-org workflow create|list|show|run|status — 组织级编排壳 (Workflow
# DRAFT/ACTIVE/PAUSED/COMPLETED/FAILED + Stage 流转 + DAG 依赖 + Runner)。
# 每命令在 logger_scope 内打开事件库 + EventLogger (同既有模式); 读命令
# 发 org.workflow.viewed (ADR-0002); run 经 _build_workflow_runner 注入
# executor (S7-005 接真实 Role Executor; 未注入且需执行 → rc 1 响亮)。


def _workflow_lifecycle(root: Path, logger: Any) -> WorkflowLifecycle:
    return WorkflowLifecycle(ProjectStore(root / "org"), logger=logger)


def _build_workflow_runner(root: Path, logger: Any) -> WorkflowRunner:
    """构造 WorkflowRunner (executor 注入点 — 测试 monkeypatch / S7-005 接入)。

    S7-003 编排壳默认不注入 executor (零 LLM/零执行副作用); 真实执行由
    S7-005 提供 EmployeeExecutor 适配器 (runner 契约: executor(stage,
    context) → dict)。
    """
    return WorkflowRunner(_workflow_lifecycle(root, logger), logger=logger)


def cmd_workflow_create(root: Path, args: Any) -> dict:
    """workflow create — 创建编排壳 (org.workflow.created; 与项目关联校验)。"""
    with _logger_scope(root) as logger:
        try:
            workflow = _workflow_lifecycle(root, logger).create_workflow(
                args.project,
                args.name,
                workflow_id=getattr(args, "id", None),
            )
        except (WorkflowError, OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_WORKFLOW_CREATED)
    return {"ok": True, "workflow": workflow.to_dict(), "event_seq": event_seq, "exit_code": 0}


def cmd_workflow_list(root: Path, args: Any) -> dict:
    """workflow list — 工作流清单 (org.workflow.viewed 审计; 按项目过滤)。"""
    with _logger_scope(root) as logger:
        workflows = _workflow_lifecycle(root, logger).list_workflows(
            project_id=getattr(args, "project", None) or None
        )
        org_events.record_workflow_viewed(
            logger,
            count=len(workflows),
            filters={"project_id": getattr(args, "project", None) or None},
        )
        event_seq = org_events.last_seq(logger, EventType.ORG_WORKFLOW_VIEWED)
    return {
        "ok": True,
        "workflows": [w.to_dict() for w in workflows],
        "count": len(workflows),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def _workflow_detail(root: Path, logger: Any, workflow_id: str) -> dict:
    """workflow 详情 (workflow + 阶段序列 + 阶段产物引用; show/status 共用)。"""
    lifecycle = _workflow_lifecycle(root, logger)
    workflow = lifecycle.get_workflow(workflow_id)
    stages = lifecycle.list_stages(workflow_id)
    return {
        "workflow": workflow.to_dict(),
        "stages": [s.to_dict() for s in stages],
        "stage_count": len(stages),
        "artifacts": [a.to_dict() for a in lifecycle.workflow_artifacts(workflow_id)],
    }


def cmd_workflow_show(root: Path, args: Any) -> dict:
    """workflow show — 工作流详情 (org.workflow.viewed 审计; 含阶段明细)。"""
    with _logger_scope(root) as logger:
        try:
            detail = _workflow_detail(root, logger, args.workflow_id)
        except (WorkflowError, OrgLifecycleError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        org_events.record_workflow_viewed(
            logger, count=1, filters={"workflow_id": args.workflow_id}
        )
        event_seq = org_events.last_seq(logger, EventType.ORG_WORKFLOW_VIEWED)
    detail["event_seq"] = event_seq
    detail["ok"] = True
    detail["exit_code"] = 0
    return detail


def cmd_workflow_run(root: Path, args: Any) -> dict:
    """workflow run — 执行编排壳 (Runner: 就绪判定→Executor→Artifact 注册→推进)。

    executor 经 _build_workflow_runner 注入 (S7-005 接真实执行); 未注入且
    需执行 → rc 1 (编排壳诚实边界)。返回终态/挂起 workflow + 阶段状态。
    """
    with _logger_scope(root) as logger:
        try:
            workflow = _build_workflow_runner(root, logger).run(
                args.workflow_id,
                max_steps=getattr(args, "max_steps", None),
            )
        except (WorkflowError, OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        detail = _workflow_detail(root, logger, args.workflow_id)
    detail["workflow"] = workflow.to_dict()
    detail["ok"] = True
    detail["exit_code"] = 0
    return detail


def cmd_workflow_status(root: Path, args: Any) -> dict:
    """workflow status — 状态总览 (org.workflow.viewed 审计; 阶段计数)。"""
    with _logger_scope(root) as logger:
        try:
            detail = _workflow_detail(root, logger, args.workflow_id)
        except (WorkflowError, OrgLifecycleError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        org_events.record_workflow_viewed(
            logger, count=1, filters={"workflow_id": args.workflow_id}
        )
        event_seq = org_events.last_seq(logger, EventType.ORG_WORKFLOW_VIEWED)
    status_counts: dict[str, int] = {}
    for s in detail["stages"]:
        status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1
    detail["status_counts"] = status_counts
    detail["event_seq"] = event_seq
    detail["ok"] = True
    detail["exit_code"] = 0
    return detail


# ------------------------------------------------------------------ approval (S9-001)
# factory-org approval list|show|approve|reject — 人工审批门 (Approval Gate:
# approval_required stage COMPLETED → PENDING + workflow PAUSED → 人工决定)。
# 决定命令 (approve/reject) 发 org.approval.approved/rejected (ADR-0002 —
# 审批行为必须审计); 读命令 (list/show) 不独立发事件 (S9-001 任务约束事件
# +3 仅 created/approved/rejected — 审计锚点由决定事件承载, S9-005 Console
# 可视层补齐 viewed 类, 诚实边界见报告)。


def _approval_lifecycle(root: Path, logger: Any) -> WorkflowLifecycle:
    return _workflow_lifecycle(root, logger)


def cmd_approval_list(root: Path, args: Any) -> dict:
    """approval list — 审批门清单 (workflow/status/stage 过滤)。"""
    with _logger_scope(root) as logger:
        gates = _approval_lifecycle(root, logger).list_approvals(
            workflow_id=getattr(args, "workflow", None) or None,
            status=getattr(args, "status", None) or None,
            stage_id=getattr(args, "stage", None) or None,
        )
    return {
        "ok": True,
        "approvals": [g.to_dict() for g in gates],
        "count": len(gates),
        "exit_code": 0,
    }


def cmd_approval_show(root: Path, args: Any) -> dict:
    """approval show — 审批门详情 (gate + 关联 stage/workflow)。"""
    with _logger_scope(root) as logger:
        try:
            lifecycle = _approval_lifecycle(root, logger)
            gate = lifecycle.get_approval(args.gate_id)
            stage = lifecycle.get_stage(gate.stage_id)
            workflow = lifecycle.get_workflow(gate.workflow_id)
        except (WorkflowError, ApprovalError, OrgLifecycleError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
    return {
        "ok": True,
        "approval": gate.to_dict(),
        "stage": stage.to_dict(),
        "workflow": workflow.to_dict(),
        "exit_code": 0,
    }


def cmd_approval_approve(root: Path, args: Any) -> dict:
    """approval approve — 审批放行 (→APPROVED + workflow 恢复 PAUSED→ACTIVE)。

    --reviewer 决策人 (审计必需, 建议必填); --comment 放行理由。发
    org.approval.approved + org.workflow.started (from_status=paused)。
    """
    with _logger_scope(root) as logger:
        try:
            gate, workflow = _approval_lifecycle(root, logger).approve_approval(
                args.gate_id,
                reviewer=getattr(args, "reviewer", None) or "",
                comment=getattr(args, "comment", None) or "",
            )
        except (WorkflowError, ApprovalError, OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_APPROVAL_APPROVED)
    return {
        "ok": True,
        "approval": gate.to_dict(),
        "workflow": workflow.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def cmd_approval_reject(root: Path, args: Any) -> dict:
    """approval reject — 审批否决 (→REJECTED + workflow FAILED 停止, 记录原因)。

    --reviewer 决策人; --comment 否决理由 (写入 failed_reason 审计)。发
    org.approval.rejected + org.workflow.failed。
    """
    with _logger_scope(root) as logger:
        try:
            gate, workflow = _approval_lifecycle(root, logger).reject_approval(
                args.gate_id,
                reviewer=getattr(args, "reviewer", None) or "",
                comment=getattr(args, "comment", None) or "",
            )
        except (WorkflowError, ApprovalError, OrgLifecycleError, ValueError) as exc:
            return _error(str(exc), exit_code=7 if isinstance(exc, NotFoundError) else 1)
        event_seq = org_events.last_seq(logger, EventType.ORG_APPROVAL_REJECTED)
    return {
        "ok": True,
        "approval": gate.to_dict(),
        "workflow": workflow.to_dict(),
        "event_seq": event_seq,
        "exit_code": 0,
    }


def _project_adoption(root: Path, logger: Any) -> ProjectAdoption:
    """ProjectAdoption 服务 (ProjectStore + 事件 logger; S9-004 数据空间同目录)。"""
    return ProjectAdoption(ProjectStore(root / "org"), logger=logger)


def cmd_project_register(root: Path, args: Any) -> dict:
    """project register — 注册已有项目 (建项目 + 分析 + 基线 + 快照)。

    失败安全: repo_path 非目录 → 错误; 分析/基线/快照任何失败都不阻断注册
    (记录 unavailable)。发 org.project.created + registered/analyzed/
    baseline_recorded/context_snapshotted。
    """
    with _logger_scope(root) as logger:
        adoption = _project_adoption(root, logger)
        try:
            project = adoption.register(
                args.repo_path,
                name=args.name,
                language=args.language,
                framework=args.framework,
                build_command=args.build_command,
                test_command=args.test_command,
                project_type=args.project_type,
                goal=args.goal,
                project_id=args.id,
                company_id=getattr(args, "company", "") or "",
                department_ids=(
                    [d.strip() for d in str(getattr(args, "departments", "") or "").split(",") if d.strip()]
                    or None
                ),
            )
        except ValueError as exc:
            return _error(str(exc))
        baseline = (
            adoption.get_baseline(project.baseline_ref) if project.baseline_ref else None
        )
        analysis = (
            adoption.get_analysis(project.analysis_ref) if project.analysis_ref else None
        )
        baseline_payload = baseline.payload if baseline else {}
        analysis_payload = analysis.payload if analysis else {}
    return {
        "ok": True,
        "project": project.to_dict(),
        "analysis_ref": project.analysis_ref,
        "baseline_ref": project.baseline_ref,
        "snapshot_ref": project.snapshot_ref,
        "analysis": {
            "build_method": analysis_payload.get("build_method", ""),
            "test_method": analysis_payload.get("test_method", ""),
            "structure_count": len(analysis_payload.get("structure", [])),
            "valid": analysis.valid if analysis else False,
        },
        "baseline": {
            "build_status": baseline_payload.get("build", {}).get("status", ""),
            "test_status": baseline_payload.get("test", {}).get("status", ""),
            "test_passed": baseline_payload.get("test", {}).get("passed", 0),
            "test_failed": baseline_payload.get("test", {}).get("failed", 0),
            "valid": baseline.valid if baseline else False,
        },
        "exit_code": 0,
    }


def cmd_department_create(root: Path, args: Any) -> dict:
    """department create — 建部门 (Company 直属子节点; 发 org.department.created)。

    渐进式: 前期项目 Solo（无部门），后期建公司+部门 → 项目挂部门（无损升级）。
    """
    with _logger_scope(root):
        store = _org_store(root)
        lifecycle = OrgLifecycle(store)
        try:
            dept = lifecycle.create_department(
                args.company_id, args.name, department_id=args.id
            )
        except Exception as exc:  # noqa: BLE001 — 亮错
            return _error(str(exc))
    return {"ok": True, "department": dept.to_dict(), "exit_code": 0}


def cmd_project_link(root: Path, args: Any) -> dict:
    """project link — 项目关联/解绑部门（多对多可选, 渐进式挂接）。"""
    with _logger_scope(root) as logger:
        org_store = _org_store(root)
        adoption = _project_adoption(root, logger)
        try:
            project = adoption.get_project(args.project_id)
            if project is None:
                return _error(f"project not found: {args.project_id}")
            current = set(project.department_ids)
            deps = [d.strip() for d in (args.departments or "").split(",") if d.strip()]
            unlinks = [d.strip() for d in (args.unlink or "").split(",") if d.strip()]
            if deps:
                for d in deps:
                    if org_store.get_department(d) is None:
                        return _error(f"department not found: {d}")
                current |= set(deps)
            if unlinks:
                current -= set(unlinks)
            updated = project.model_copy(update={"department_ids": sorted(current)})
            adoption.store.save_project(updated)
        except Exception as exc:  # noqa: BLE001
            return _error(str(exc))
    return {"ok": True, "project": updated.to_dict(), "exit_code": 0}


def cmd_project_show(root: Path, args: Any) -> dict:
    """project show — 项目详情 + 分析/基线/快照记录 (读命令)。"""
    with _logger_scope(root) as logger:
        adoption = _project_adoption(root, logger)
        try:
            project = adoption.get_project(args.project_id)
        except NotFoundError as exc:
            return _error(str(exc))
        analysis = (
            adoption.get_analysis(project.analysis_ref) if project.analysis_ref else None
        )
        baseline = (
            adoption.get_baseline(project.baseline_ref) if project.baseline_ref else None
        )
        snapshot = (
            adoption.get_snapshot(project.snapshot_ref) if project.snapshot_ref else None
        )
    return {
        "ok": True,
        "project": project.to_dict(),
        "analysis": analysis.to_dict() if analysis else None,
        "baseline": baseline.to_dict() if baseline else None,
        "snapshot": snapshot.to_dict() if snapshot else None,
        "exit_code": 0,
    }


def cmd_project_list(root: Path, args: Any) -> dict:
    """project list — 项目清单 (读命令)。"""
    with _logger_scope(root) as logger:
        adoption = _project_adoption(root, logger)
        projects = adoption.list_projects()
    return {
        "ok": True,
        "count": len(projects),
        "projects": [p.to_dict() for p in sorted(projects, key=lambda p: p.id)],
        "exit_code": 0,
    }


def _print_result(args: Any, result: dict) -> None:
    if args.json:
        import json

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not result.get("ok"):
        print(f"error: {result.get('error')}", file=sys.stderr)
        return
    command = args.command
    if command == "company":
        company = result["company"]
        if args.company_command == "create":
            print("✔ 公司创建成功 (模板实例化)")
            print(f"  id          {company['id']}")
            print(f"  name        {company['name']}")
            print(f"  template    {company['template']}")
            print(f"  departments {result['department_count']}")
        else:
            print(f"公司 {company['id']} — {company['name']} (模板: {company['template']})")
            for dept in result["departments"]:
                print(f"  部门  {dept['name']} ({dept['id']})")
            for role in result["roles"]:
                human = " [Human]" if role.get("human") else ""
                print(f"  角色  {role['name']} ({role['id']}){human}")
        if result.get("event_seq") is not None:
            print(f"  event_seq   {result['event_seq']}")
    elif command == "employee":
        if args.employee_command == "hire":
            emp = result["employee"]
            print("✔ 员工入职")
            print(f"  id        {emp['id']}")
            print(f"  name      {emp['name']}")
            print(f"  company   {emp['company_id']}")
            print(f"  roles     {', '.join(emp['role_ids'])}")
            print(f"  caps      {', '.join(emp['capabilities']) or '(无)'}")
            if result.get("event_seq") is not None:
                print(f"  event_seq {result['event_seq']}")
        else:
            print(f"员工清单 ({result['count']} 人)")
            for emp in result["employees"]:
                print(f"  {emp['id']}  {emp['name']}  {emp['company_id']}  "
                      f"roles={len(emp['role_ids'])} caps={len(emp['capabilities'])}")
    elif command == "authority":
        print(f"权限校验: {result['permission']} → {result['result']}")
        print(f"  roles     {', '.join(result['role_ids'])}")
        if result.get("event_seq") is not None:
            print(f"  event_seq {result['event_seq']}")
    elif command == "knowledge":
        if args.knowledge_command == "add":
            item = result["knowledge"]
            print("✔ 知识入库 (公司隔离)")
            print(f"  id        {item['id']}")
            print(f"  company   {item['company_id']}")
            print(f"  domain    {item['domain']}")
            print(f"  version   {item['version']}")
            if result.get("event_seq") is not None:
                print(f"  event_seq {result['event_seq']}")
        else:
            print(f"知识清单 ({result['count']} 条) — 公司 {result['company_id']}")
            for item in result["knowledge"]:
                print(f"  {item['id']}  [{item['domain']}] v{item['version']}  {item['content']}")
    elif command == "artifact":
        _print_artifact_result(args, result)
    elif command == "workflow":
        _print_workflow_result(args, result)
    elif command == "approval":
        _print_approval_result(args, result)
    elif command == "project":
        _print_project_result(args, result)


def _print_project_result(args: Any, result: dict) -> None:
    """project 子命令人类可读输出 (register/show/list)。"""
    sub = getattr(args, "project_command", None) or ""
    if sub == "register":
        project = result["project"]
        print("✔ 项目注册成功 (已有代码库接入)")
        print(f"  id            {project['id']}")
        print(f"  name          {project['name']}")
        print(f"  repo_path     {project['repo_path']}")
        print(f"  language      {project['language'] or '(未识别)'}")
        print(f"  framework     {project['framework'] or '(未识别)'}")
        print(f"  project_type  {project['project_type'] or '-'}")
        print(f"  analysis_ref  {result['analysis_ref'] or '-'}")
        print(f"  baseline_ref  {result['baseline_ref'] or '-'}")
        print(f"  snapshot_ref  {result['snapshot_ref'] or '-'}")
        bl = result.get("baseline") or {}
        print(f"  baseline      build={bl.get('build_status')}  "
              f"test={bl.get('test_status')}  "
              f"passed={bl.get('test_passed')}  failed={bl.get('test_failed')}")
    elif sub == "show":
        project = result["project"]
        print(f"项目 {project['id']} — {project['name']}  [{project['lifecycle']}]")
        print(f"  repo_path     {project['repo_path'] or '-'}")
        print(f"  language      {project['language'] or '-'}")
        print(f"  framework     {project['framework'] or '-'}")
        print(f"  build_cmd     {project['build_command'] or '-'}")
        print(f"  test_cmd      {project['test_command'] or '-'}")
        print(f"  project_type  {project['project_type'] or '-'}")
        print(f"  analysis_ref  {project['analysis_ref'] or '-'}")
        print(f"  baseline_ref  {project['baseline_ref'] or '-'}")
        print(f"  snapshot_ref  {project['snapshot_ref'] or '-'}")
        if result.get("baseline"):
            payload = result["baseline"]["payload"]
            build = payload.get("build", {})
            test = payload.get("test", {})
            print(f"  baseline      build={build.get('status')}  "
                  f"test={test.get('status')}  "
                  f"passed={test.get('passed')}  failed={test.get('failed')}")
    else:
        print(f"项目清单 ({result['count']} 个)")
        for p in result["projects"]:
            print(f"  {p['id']}  {p['name']}  [{p['lifecycle']}]  "
                  f"lang={p['language'] or '-'}  repo={p['repo_path'] or '-'}")


def _print_workflow_result(args: Any, result: dict) -> None:
    """workflow 子命令人类可读输出 (list/show/run/status 共用)。"""
    sub = args.workflow_command
    if sub == "create":
        w = result["workflow"]
        print("✔ 工作流创建成功 (编排壳)")
        print(f"  id         {w['id']}")
        print(f"  project    {w['project_id']}")
        print(f"  name       {w['name']}")
        print(f"  status     {w['status']}")
    elif sub == "list":
        print(f"工作流清单 ({result['count']} 条)")
        for w in result["workflows"]:
            print(f"  {w['id']}  [{w['status']}]  {w['name']}  project={w['project_id']}  "
                  f"stages={len(w['stage_ids'])}")
    elif sub == "show":
        _print_workflow_detail(result, detailed=True)
    elif sub == "run":
        w = result["workflow"]
        verdict = "✔" if w["status"] == "completed" else "⏸"
        print(f"{verdict} 工作流执行结束: {w['id']} → {w['status']}")
        _print_workflow_detail(result, detailed=False)
    elif sub == "status":
        w = result["workflow"]
        print(f"工作流状态: {w['id']} [{w['status']}] — {w['name']}")
        counts = result.get("status_counts", {})
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "(无阶段)"
        print(f"  阶段      {summary}")
        _print_workflow_detail(result, detailed=True)
    if result.get("event_seq") is not None:
        print(f"  event_seq  {result['event_seq']}")


def _print_workflow_detail(result: dict, *, detailed: bool) -> None:
    """workflow 详情/状态共用输出 (stages 行 + 产物引用)。"""
    w = result["workflow"]
    print(f"  workflow   {w['id']} [{w['status']}] — {w['name']} (project {w['project_id']})")
    if w.get("failed_reason"):
        print(f"  reason     {w['failed_reason']}")
    for s in result.get("stages", []):
        deps = f" deps={','.join(s['depends_on'])}" if s.get("depends_on") else ""
        inputs = f" in={','.join(s['input_artifacts'])}" if s.get("input_artifacts") else ""
        outputs = f" out={','.join(s['output_artifacts'])}" if s.get("output_artifacts") else ""
        print(f"  stage      {s['id']}  [{s['status']}]  {s['role_id']}"
              f"{'  ' + s['name'] if s.get('name') else ''}{deps}{inputs}{outputs}")
    if detailed and result.get("artifacts"):
        for a in result["artifacts"]:
            print(f"  artifact   {a['id']}  [{a['type']}] {a['status']}  "
                  f"stage={a['stage_id']}")


def _print_approval_result(args: Any, result: dict) -> None:
    """approval 子命令人类可读输出 (list/show/approve/reject)。"""
    sub = args.approval_command
    if sub == "list":
        print(f"审批门清单 ({result['count']} 条)")
        for g in result["approvals"]:
            print(f"  {g['id']}  [{g['status']}]  stage={g['stage_id']}  "
                  f"workflow={g['workflow_id']}")
    elif sub == "show":
        g = result["approval"]
        w = result["workflow"]
        s = result["stage"]
        print(f"审批门 {g['id']} — [{g['status']}]")
        print(f"  stage      {g['stage_id']}  ({s['role_id']} / {s['name'] or '-'})")
        print(f"  workflow   {g['workflow_id']}  [{w['status']}] — {w['name']}")
        if g.get("reviewer"):
            print(f"  reviewer   {g['reviewer']}")
        if g.get("comment"):
            print(f"  comment    {g['comment']}")
        print(f"  requested  {g['requested_at']}")
        if g.get("approved_at"):
            print(f"  approved   {g['approved_at']}")
        if g.get("rejected_at"):
            print(f"  rejected   {g['rejected_at']}")
    elif sub == "approve":
        g = result["approval"]
        w = result["workflow"]
        verdict = "✔" if g["status"] == "approved" else "⏸"
        print(f"{verdict} 审批放行: {g['id']} → {g['status']}")
        print(f"  workflow   {w['id']} [{w['status']}] (恢复 PAUSED→ACTIVE)")
        if result.get("event_seq") is not None:
            print(f"  event_seq  {result['event_seq']}")
    elif sub == "reject":
        g = result["approval"]
        w = result["workflow"]
        print(f"✘ 审批否决: {g['id']} → {g['status']}")
        print(f"  workflow   {w['id']} [{w['status']}] (停止)")
        if w.get("failed_reason"):
            print(f"  reason     {w['failed_reason']}")
        if result.get("event_seq") is not None:
            print(f"  event_seq  {result['event_seq']}")


def _print_artifact_result(args: Any, result: dict) -> None:
    """artifact 子命令人类可读输出 (list/query 同实现, 详略不同)。"""
    sub = args.artifact_command
    if sub == "create":
        a = result["artifact"]
        print("✔ 产物创建成功")
        print(f"  id         {a['id']}")
        print(f"  type       {a['type']}")
        print(f"  stage      {a['stage_id']}")
        print(f"  status     {a['status']}")
        print(f"  project    {a['project_id'] or '-'}")
        print(f"  task       {a['task_id'] or '-'}")
        print(f"  version    {a['version']}")
    elif sub == "get":
        a = result["artifact"]
        print(f"产物 {a['id']} — [{a['type']}] {a['status']} v{a['version']}")
        print(f"  stage      {a['stage_id']}")
        print(f"  project    {a['project_id'] or '-'}")
        print(f"  task       {a['task_id'] or '-'}")
        print(f"  producer   {a['producer_role'] or '-'} / {a['producer_agent'] or '-'}")
        print(f"  ref        {a['ref'] or '-'}")
        print(f"  location   {a['location'] or '-'}")
        if a.get("invalid_reason"):
            print(f"  reason     {a['invalid_reason']}")
    elif sub in ("list", "query"):
        print(f"产物清单 ({result['count']} 条)")
        for a in result["artifacts"]:
            print(f"  {a['id']}  [{a['type']}] {a['status']}  v{a['version']}  "
                  f"stage={a['stage_id']}  project={a['project_id'] or '-'}")
    elif sub == "update":
        a = result["artifact"]
        print(f"✔ 产物已更新: {a['id']} [{a['type']}] {a['status']} v{a['version']}")
    elif sub == "archive":
        a = result["artifact"]
        print(f"✔ 产物已归档 (软删): {a['id']} [{a['type']}] → {a['status']}")
    elif sub == "validate":
        a = result["artifact"]
        r = result["result"]
        verdict = "通过" if r["ok"] else "失败"
        print(f"契约校验: {a['id']} [{a['type']}] → {verdict} (状态: {a['status']})")
        if r["missing"]:
            print(f"  缺失字段 {r['missing']}")
        if r["errors"]:
            print(f"  规则失败 {r['errors']}")
    if result.get("event_seq") is not None:
        print(f"  event_seq  {result['event_seq']}")
