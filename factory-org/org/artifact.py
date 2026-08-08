"""factory-org/org/artifact.py — Artifact System (Sprint 7 S7-002)。

设计依据 (sprint7-architecture.md §1/§3/§6):
- 每阶段产物 = 下一阶段输入: PRD → Design → Code → Test → Release
- Artifact 生命周期: CREATED → GENERATED → VALIDATED → CONSUMED → ARCHIVED;
  异常 INVALID (契约校验失败/执行失败), 可回 GENERATED 重生成 (失败恢复)
- 类型契约 (CONTRACTS 声明式): prd/design/code/test/bug_report/release 各自
  required_fields + validation_rules — 阶段间契约严格定义 (架构风险 1 缓解);
  S7-004 扩展: test 强化 (results.passed 必含) + bug_report 类型 (Tester 缺陷报告);
  S8-001 扩展: product 类型 (PM Agent 输出, 7 节必填: market_analysis/
  user_persona/user_journey/problem_statement/feature_list/mvp_scope/
  user_stories) + idea 类型 (PM 阶段输入, 自然语言);
  S8-002 扩展: ux_ui 类型 (UX/UI Designer Agent 输出, 7 节必填:
  information_architecture/user_flow/wireframe/screen_specifications/
  component_definition/design_tokens/prototype; 结构校验: wireframe dict
  必含 screens, screen_specifications list, design_tokens dict — 深度
  wireframe Screen 结构校验在 exec 侧 _local_validate, 双体系一致)
- 引用完整: stage/project 必须存在; task 须经 ProjectTaskLink 关联该项目
  (项目隔离铁律, 同 S7-001 add_task_to_sprint); producer_role 经 exec
  注册表校验 (未安装 → 跳过, Removal Isolation — 不假装校验)

与 S7-001 的关系:
- 模型: org/projects.py Artifact 扩展 (新增字段全部带默认值, 既有
  artifacts.json 数据加载零破坏 — 向后兼容)
- 存储: 复用 ProjectStore (artifacts.json 同一数据空间, 零新文件)
- ProjectLifecycle.create_artifact (S7-001 基础版) 原样保留; 本层
  ArtifactRegistry 为完整版 (完整模型 + CRUD + 状态机 + 契约校验 +
  组合查询), 两入口共享同一 store, 数据一致 (集成测试验证)。

约束: 零 LLM/零执行副作用 (真实生成 S7-005 编排壳接入); 只编排产物状态
与审计事件 (每转换 org.artifact.* 事件)。Core 冻结 (仅 events 枚举新增,
ADR-0001 决策 1 扩展路径)。
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from . import events as org_events
from .lifecycle import DuplicateError, NotFoundError
from .models import new_id, utcnow
from .projects import (
    ARTIFACT_TRANSITIONS,
    Artifact,
    ArtifactStatus,
    ArtifactType,
    ProjectStore,
    _validate_exec_role,
)


class ArtifactError(Exception):
    """Artifact System 基础异常。"""


class ArtifactStateError(ArtifactError):
    """非法状态转换 / 终态更新 (受控转换表拒绝)。"""


# ------------------------------------------------------------------ 类型契约


@dataclass
class ValidationResult:
    """契约校验结果 (缺失字段/规则失败 → ok=False)。"""

    type: str
    ok: bool
    missing: list[str] = dc_field(default_factory=list)
    errors: list[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "ok": self.ok,
            "missing": self.missing,
            "errors": self.errors,
        }


#: 类型契约 (声明式, 可扩展): 每类型 required_fields + validation_rules。
#: 规则 dict: {field: {"type": "str"|"list"|"dict", "min_length"/"min_items"/"min_keys": N}}。
#: 新增产物类型 = 枚举加成员 + 本表加条目 (单点扩展, 契约与枚举同源)。
CONTRACTS: dict[str, dict[str, Any]] = {
    "idea": {
        "required_fields": ("idea",),
        "validation_rules": {
            "idea": {"type": "str", "min_length": 1},
        },
    },
    "product": {
        "required_fields": (
            "market_analysis",
            "user_persona",
            "user_journey",
            "problem_statement",
            "feature_list",
            "mvp_scope",
            "user_stories",
        ),
        "validation_rules": {
            "market_analysis": {"type": "str", "min_length": 1},
            "user_persona": {"type": "str", "min_length": 1},
            "user_journey": {"type": "str", "min_length": 1},
            "problem_statement": {"type": "str", "min_length": 1},
            "feature_list": {"type": "list", "min_items": 1},
            "mvp_scope": {"type": "dict", "min_keys": 1, "required_keys": ["in", "out"]},
            "user_stories": {"type": "list", "min_items": 1},
        },
    },
    "ux_ui": {
        "required_fields": (
            "information_architecture",
            "user_flow",
            "wireframe",
            "screen_specifications",
            "component_definition",
            "design_tokens",
            "prototype",
        ),
        "validation_rules": {
            "information_architecture": {"type": "dict", "min_keys": 1},
            "user_flow": {"type": "list", "min_items": 1},
            "wireframe": {"type": "dict", "min_keys": 1, "required_keys": ["screens"]},
            "screen_specifications": {"type": "list", "min_items": 1},
            "component_definition": {"type": "list", "min_items": 1},
            "design_tokens": {"type": "dict", "min_keys": 1},
            "prototype": {"type": "str", "min_length": 1},
        },
    },
    "prd": {
        "required_fields": ("problem", "user", "features"),
        "validation_rules": {
            "problem": {"type": "str", "min_length": 1},
            "user": {"type": "str", "min_length": 1},
            "features": {"type": "list", "min_items": 1},
        },
    },
    "design": {
        "required_fields": ("architecture", "api", "database"),
        "validation_rules": {
            "architecture": {"type": "str", "min_length": 1},
            "api": {"type": "str", "min_length": 1},
            "database": {"type": "str", "min_length": 1},
        },
    },
    "code": {
        "required_fields": ("files", "changes"),
        "validation_rules": {
            "files": {"type": "list", "min_items": 1},
            "changes": {"type": "str", "min_length": 1},
        },
    },
    "test": {
        "required_fields": ("results", "bugs"),
        "validation_rules": {
            "results": {"type": "dict", "min_keys": 1, "required_keys": ["passed"]},
            "bugs": {"type": "list"},
        },
    },
    "bug_report": {
        "required_fields": ("location", "repro", "expected", "actual", "root_cause", "severity"),
        "validation_rules": {
            "location": {"type": "str", "min_length": 1},
            "repro": {"type": "str", "min_length": 1},
            "expected": {"type": "str", "min_length": 1},
            "actual": {"type": "str", "min_length": 1},
            "root_cause": {"type": "str", "min_length": 1},
            "severity": {"type": "str", "min_length": 1},
        },
    },
    "release": {
        "required_fields": ("version", "notes", "artifact_ref"),
        "validation_rules": {
            "version": {"type": "str", "min_length": 1},
            "notes": {"type": "str", "min_length": 1},
            "artifact_ref": {"type": "str", "min_length": 1},
        },
    },
}

_TYPE_CHECKS: dict[str, Any] = {
    "str": lambda v: isinstance(v, str),
    "list": lambda v: isinstance(v, list),
    "dict": lambda v: isinstance(v, dict),
}


def _check_rule(field: str, value: Any, rule: dict[str, Any]) -> str | None:
    """单条规则校验 → 失败信息 (None = 通过)。

    str 非空语义: min_length 按 strip 后长度判定 (纯空白视为空串 —
    与 exec 侧 _local_validate 同规则, 双体系一致; 契约意图 "非空")。
    """
    expected = rule.get("type")
    if expected and expected in _TYPE_CHECKS and not _TYPE_CHECKS[expected](value):
        return f"expected {expected}, got {type(value).__name__}"
    if isinstance(value, str):
        min_length = rule.get("min_length", 0)
        if len(value.strip()) < min_length:
            return f"min length {min_length}"
    elif isinstance(value, list):
        min_items = rule.get("min_items", 0)
        if len(value) < min_items:
            return f"min items {min_items}"
    elif isinstance(value, dict):
        min_keys = rule.get("min_keys", 0)
        if len(value) < min_keys:
            return f"min keys {min_keys}"
        required_keys = rule.get("required_keys")
        if required_keys:
            missing_keys = [k for k in required_keys if k not in value]
            if missing_keys:
                return f"missing required keys: {', '.join(missing_keys)}"
    return None


def validate_artifact(
    type_: ArtifactType | str, payload: dict[str, Any] | None
) -> ValidationResult:
    """类型契约校验 (缺失字段/规则失败 → ok=False; 调用方决定置 INVALID)。

    纯函数 (零副作用, CLI/Registry/测试共用); payload None → 视为空载荷
    (全部 required 缺失); type 宽容解析 (大小写不敏感); 未知类型 →
    ValueError (ArtifactType.parse 响亮失败)。
    """
    type_name = ArtifactType.parse(type_).value
    contract = CONTRACTS[type_name]  # 契约与枚举同源 (KeyError = 代码缺陷)
    payload = payload or {}
    missing = [f for f in contract["required_fields"] if f not in payload]
    errors: list[str] = []
    for field, rule in contract["validation_rules"].items():
        if field not in payload:
            continue  # 缺失字段已计入 missing
        err = _check_rule(field, payload.get(field), rule)
        if err is not None:
            errors.append(f"{field}: {err}")
    return ValidationResult(
        type=type_name, ok=not missing and not errors, missing=missing, errors=errors
    )


# ------------------------------------------------------------------ Registry


class ArtifactRegistry:
    """Artifact Registry: 完整模型 CRUD + 生命周期状态机 + 类型契约 + 组合查询。

    - create/get/list/update/archive (archive = 软删, 状态机 →archived 终态)
    - 关联校验 (引用完整): stage/project 必须存在; task 须经 link_task
      关联该项目; producer_role 经 exec 注册表校验 (未安装 → 跳过)
    - 状态转换受控: ARTIFACT_TRANSITIONS 转换表, 非法跳转 →
      ArtifactStateError (如 created 不能直接 archived)
    - 每转换审计事件: updated/validated/consumed/failed/archived (payload
      含 from_status/to_status, 事件唯一事实源)
    """

    def __init__(self, store: ProjectStore, *, logger: Any = None):
        self._store = store
        self._logger = logger

    @property
    def store(self) -> ProjectStore:
        return self._store

    # ------------------------------------------------------------ CRUD

    def create(
        self,
        stage_id: str,
        type_: ArtifactType | str,
        *,
        project_id: str = "",
        task_id: str = "",
        ref: str = "",
        producer_role: str = "",
        producer_agent: str = "",
        version: str = "1",
        location: str = "",
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> Artifact:
        """创建产物 (org.artifact.created; 状态 CREATED)。

        关联校验 (引用完整):
        - stage 必须存在 (产物挂阶段)
        - project_id 非空 → 项目必须存在
        - task_id 非空 → 必须经 link_task 关联到 project_id 该项目
          (项目隔离铁律; task 引用 Core Task id, org 侧映射表校验)
        - producer_role 非空 → exec 注册表校验 (未安装 → 跳过)
        """
        self._require_stage(stage_id)
        if project_id:
            self._require_project(project_id)
        if task_id:
            if not project_id:
                raise ValueError("task_id requires project_id (task 须关联项目)")
            if not any(
                l.task_id == task_id and l.project_id == project_id
                for l in self._store.list_task_links()
            ):
                raise NotFoundError(
                    f"task {task_id} not linked to project {project_id} "
                    f"(link_task 先关联)"
                )
        if producer_role:
            _validate_exec_role(producer_role)
        artifact_id = artifact_id or new_id("A")
        if self._store.get_artifact(artifact_id) is not None:
            raise DuplicateError(f"artifact already exists: {artifact_id}")
        artifact = Artifact(
            id=artifact_id,
            stage_id=stage_id,
            type=ArtifactType.parse(type_),
            ref=ref,
            project_id=project_id,
            task_id=task_id,
            producer_role=producer_role,
            producer_agent=producer_agent,
            version=version or "1",
            location=location,
            metadata=metadata or {},
        )
        self._store.save_artifact(artifact)
        org_events.record_artifact_created(self._logger, artifact=artifact)
        return artifact

    def get(self, artifact_id: str) -> Artifact:
        """按 id 取产物 (含 archived — 软删可查, 审计/恢复用)。"""
        artifact = self._store.get_artifact(artifact_id)
        if artifact is None:
            raise NotFoundError(f"artifact not found: {artifact_id}")
        return artifact

    def list(self, *, include_archived: bool = False) -> list[Artifact]:
        """全部产物 (软删语义: 默认隐藏 archived; include_archived=True 全量)。"""
        artifacts = self._store.list_artifacts()
        if not include_archived:
            artifacts = [a for a in artifacts if not a.is_archived]
        return artifacts

    def update(
        self,
        artifact_id: str,
        *,
        ref: str | None = None,
        producer_role: str | None = None,
        producer_agent: str | None = None,
        version: str | None = None,
        location: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """更新产物字段 (org.artifact.updated; 不改状态 — 状态只经转换表)。

        终态约束: archived 产物不可更新 (软删后不可改, ArtifactStateError);
        producer_role 变更经 exec 注册表校验; 无变更幂等 (不发事件)。
        """
        artifact = self.get(artifact_id)
        if artifact.is_archived:
            raise ArtifactStateError(
                f"archived artifact is immutable: {artifact_id}"
            )
        if producer_role is not None and producer_role:
            _validate_exec_role(producer_role)
        changes: dict[str, Any] = {}
        if ref is not None:
            changes["ref"] = ref
        if producer_role is not None:
            changes["producer_role"] = producer_role
        if producer_agent is not None:
            changes["producer_agent"] = producer_agent
        if version is not None:
            changes["version"] = version
        if location is not None:
            changes["location"] = location
        if metadata is not None:
            changes["metadata"] = metadata
        if not changes:
            return artifact  # 无变更幂等 (不发事件)
        changed_fields = sorted(changes.keys())
        changes["updated_at"] = utcnow()
        updated = artifact.model_copy(update=changes)
        self._store.save_artifact(updated)
        org_events.record_artifact_updated(
            self._logger,
            artifact=updated,
            from_status=artifact.status.value,
            to_status=updated.status.value,
            changed_fields=changed_fields,
        )
        return updated

    def archive(self, artifact_id: str) -> Artifact:
        """软删归档 (→archived 终态; 受控转换表: 仅 validated/consumed/invalid
        可归档 — created/generated 不可直接归档, 非法 → ArtifactStateError)。"""
        return self.transition(artifact_id, ArtifactStatus.ARCHIVED)

    # ------------------------------------------------------------ 状态机

    def transition(
        self,
        artifact_id: str,
        to_status: ArtifactStatus | str,
        *,
        reason: str = "",
        event_extra: dict[str, Any] | None = None,
    ) -> Artifact:
        """受控状态转换 (ARTIFACT_TRANSITIONS 转换表; 每转换审计事件)。

        非法跳转 → ArtifactStateError (如 created 不能直接 archived);
        同状态幂等 (不发事件); archived 终态不可再转 (转换表空)。
        invalid_reason/archived_at 随转换落库 (审计)。
        """
        artifact = self.get(artifact_id)
        target = ArtifactStatus.parse(to_status)
        if target == artifact.status:
            return artifact  # 幂等: 同状态不重复发事件
        allowed = ARTIFACT_TRANSITIONS.get(artifact.status.value, ())
        if target.value not in allowed:
            raise ArtifactStateError(
                f"invalid artifact transition: {artifact.status.value} → "
                f"{target.value} (allowed from {artifact.status.value}: "
                f"{', '.join(allowed) or 'none'})"
            )
        updates: dict[str, Any] = {"status": target, "updated_at": utcnow()}
        if target == ArtifactStatus.INVALID:
            updates["invalid_reason"] = reason
        elif target == ArtifactStatus.ARCHIVED:
            updates["archived_at"] = utcnow()
        updated = artifact.model_copy(update=updates)
        self._store.save_artifact(updated)
        self._emit_transition(artifact, updated, reason=reason, extra=event_extra)
        return updated

    def mark_generated(self, artifact_id: str) -> Artifact:
        """标记已生成 (→generated; created→generated 或 invalid→generated
        重生成 — 失败恢复路径)。"""
        return self.transition(artifact_id, ArtifactStatus.GENERATED)

    def validate(
        self,
        artifact_id: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> tuple[Artifact, ValidationResult]:
        """类型契约校验: 通过 → validated, 失败 → invalid (契约驱动)。

        payload 缺省用产物 metadata (创建/更新时写入的契约载荷); 返回
        (artifact, result) — 调用方据 result 判断。失败时产物置 INVALID
        (invalid_reason 落库), 事件 org.artifact.failed 携带 missing/errors
        (审计唯一事实源)。已 validated 且通过 → 幂等 (不重复发事件)。
        """
        artifact = self.get(artifact_id)
        content = payload if payload is not None else artifact.metadata
        result = validate_artifact(artifact.type, content)
        if result.ok:
            if artifact.status == ArtifactStatus.VALIDATED:
                return artifact, result  # 幂等
            updated = self.transition(
                artifact_id,
                ArtifactStatus.VALIDATED,
                event_extra={"missing": [], "errors": []},
            )
            return updated, result
        if artifact.status == ArtifactStatus.INVALID:
            return artifact, result  # 已失败 (幂等, 不重复发事件)
        updated = self.transition(
            artifact_id,
            ArtifactStatus.INVALID,
            reason="; ".join(result.missing + result.errors)
            or "contract validation failed",
            event_extra={"missing": result.missing, "errors": result.errors},
        )
        return updated, result

    def consume(self, artifact_id: str) -> Artifact:
        """产物被下一阶段消费 (→consumed; 仅 validated 可消费, 转换表受控)。"""
        return self.transition(artifact_id, ArtifactStatus.CONSUMED)

    def fail(self, artifact_id: str, *, reason: str = "") -> Artifact:
        """显式失败 (→invalid; 执行失败/人工判定; 可回 generated 重生成)。"""
        return self.transition(artifact_id, ArtifactStatus.INVALID, reason=reason)

    # ------------------------------------------------------------ 查询

    def query(
        self,
        *,
        project_id: str | None = None,
        stage_id: str | None = None,
        task_id: str | None = None,
        type_: ArtifactType | str | None = None,
        status: ArtifactStatus | str | None = None,
        include_archived: bool = False,
    ) -> list[Artifact]:
        """组合过滤查询 (project/stage/task/type/status; AND 语义)。

        软删语义: status 未指定 → 隐藏 archived; 显式 status="archived"
        可查归档产物; include_archived=True 忽略软删 (全量)。type/status
        宽容解析 (大小写不敏感)。
        """
        artifacts = self._store.list_artifacts()
        if project_id is not None:
            artifacts = [a for a in artifacts if a.project_id == project_id]
        if stage_id is not None:
            artifacts = [a for a in artifacts if a.stage_id == stage_id]
        if task_id is not None:
            artifacts = [a for a in artifacts if a.task_id == task_id]
        if type_ is not None:
            wanted = ArtifactType.parse(type_)
            artifacts = [a for a in artifacts if a.type == wanted]
        if status is not None:
            wanted = ArtifactStatus.parse(status)
            artifacts = [a for a in artifacts if a.status == wanted]
        elif not include_archived:
            artifacts = [a for a in artifacts if not a.is_archived]
        return artifacts

    # ------------------------------------------------------------ 内部辅助

    def _require_stage(self, stage_id: str) -> None:
        if self._store.get_stage(stage_id) is None:
            raise NotFoundError(f"stage not found: {stage_id}")

    def _require_project(self, project_id: str) -> None:
        if self._store.get_project(project_id) is None:
            raise NotFoundError(f"project not found: {project_id}")

    def _emit_transition(
        self,
        before: Artifact,
        after: Artifact,
        *,
        reason: str,
        extra: dict[str, Any] | None,
    ) -> None:
        """每转换一条审计事件 (payload 含 from_status/to_status)。"""
        from_status = before.status.value
        to_status = after.status.value
        extra = extra or {}
        if to_status == "generated":
            org_events.record_artifact_updated(
                self._logger,
                artifact=after,
                from_status=from_status,
                to_status=to_status,
                changed_fields=["status"],
            )
        elif to_status == "validated":
            org_events.record_artifact_validated(
                self._logger,
                artifact=after,
                from_status=from_status,
                missing=extra.get("missing", []),
                errors=extra.get("errors", []),
            )
        elif to_status == "consumed":
            org_events.record_artifact_consumed(
                self._logger, artifact=after, from_status=from_status
            )
        elif to_status == "invalid":
            org_events.record_artifact_failed(
                self._logger,
                artifact=after,
                from_status=from_status,
                reason=reason or after.invalid_reason,
                missing=extra.get("missing"),
                errors=extra.get("errors"),
            )
        elif to_status == "archived":
            org_events.record_artifact_archived(
                self._logger, artifact=after, from_status=from_status
            )
