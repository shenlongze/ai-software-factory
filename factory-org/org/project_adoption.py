"""factory-org/org/project_adoption.py — Existing Project Adoption (S9-004)。

已有项目接入编排 (org 侧, 只消费 — 不修改 Workflow/Artifact/Approval):

- ProjectAdoptionStore: 三个新数据空间文件 (project_analyses.json /
  project_baselines.json / context_snapshots.json) — 与 ProjectStore 同目录
  (<root>/org/), 既有数据零接触, 向后兼容;
- ProjectAdoption.register: 注册 = 建项目 (ProjectLifecycle.create_project) +
  分析 (exec.project_adoption.analyze_project, 复用 repo_intelligence) +
  基线 (build/test 命令执行或语法检查) + 上下文快照 → 三条记录 + Project
  字段引用 (analysis_ref/baseline_ref/snapshot_ref) + 4 审计事件。

失败安全 (三原则, 注册永不因分析/基线失败而失败):
1. exec 未安装 (Removal Isolation) → 分析/基线/快照记录 unavailable 原因,
   Project 仍注册成功;
2. build/test 命令缺失 → baseline 记录 status "unavailable" (不崩溃);
3. 分析/基线异常 → 记录 errors + unavailable 载荷, 生命周期不受阻。

记录载荷与 factory-org CONTRACTS 同源 (project_analysis/baseline 契约 —
经 validate_artifact 纯函数校验, 零副作用; 记录 id 供后续 Agent 读取
上下文输入, 标注为输入)。

设计依据: docs/sprint9/sprint9-architecture.md §3 (Existing Project Adoption:
register_project(路径, 语言, 构建命令, 测试命令) → Project 模型扩展 +
沙箱快照 + 基线测试运行确认环境可用)。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from . import events as org_events
from .artifact import ArtifactType, validate_artifact
from .models import _OrgModel, _norm_list, new_id, utcnow
from .projects import Project, ProjectLifecycle, ProjectStore
from .store import _SectionStore


class ProjectAnalysisRecord(_OrgModel):
    """仓库分析记录 (project_analyses.json; 载荷 = CONTRACTS project_analysis)。"""

    id: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    valid: bool = True                    # CONTRACTS 校验结果 (契约形状)
    errors: list[str] = Field(default_factory=list)  # 校验缺失/失败原因
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("errors", mode="before")
    @classmethod
    def _errors_none(cls, v: Any) -> Any:
        return _norm_list(v)


class BaselineRecord(_OrgModel):
    """基线验证记录 (project_baselines.json; 载荷 = CONTRACTS baseline)。"""

    id: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_none(cls, v: Any) -> Any:
        return v if v is not None else {}

    @field_validator("errors", mode="before")
    @classmethod
    def _errors_none(cls, v: Any) -> Any:
        return _norm_list(v)


class ContextSnapshotRecord(_OrgModel):
    """上下文快照记录 (context_snapshots.json; 供 Agent 上下文输入标注)。"""

    id: str
    project_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_none(cls, v: Any) -> Any:
        return v if v is not None else {}


# ------------------------------------------------------------------ 存储


class ProjectAnalysisSection(_SectionStore[ProjectAnalysisRecord]):
    """分析记录持久化 (project_analyses.json)。"""

    _filename = "project_analyses.json"
    _section = "project_analyses"
    _model = ProjectAnalysisRecord


class BaselineSection(_SectionStore[BaselineRecord]):
    """基线记录持久化 (project_baselines.json)。"""

    _filename = "project_baselines.json"
    _section = "project_baselines"
    _model = BaselineRecord


class ContextSnapshotSection(_SectionStore[ContextSnapshotRecord]):
    """快照记录持久化 (context_snapshots.json)。"""

    _filename = "context_snapshots.json"
    _section = "context_snapshots"
    _model = ContextSnapshotRecord


class ProjectAdoptionStore:
    """S9-004 记录数据空间门面 (三文件; 与 ProjectStore 同目录并存)。"""

    def __init__(self, org_dir: str | Path) -> None:
        self._dir = Path(org_dir)
        self._analyses = ProjectAnalysisSection(self._dir)
        self._baselines = BaselineSection(self._dir)
        self._snapshots = ContextSnapshotSection(self._dir)

    @property
    def dir(self) -> Path:
        return self._dir

    # ----------------------------------------------------------- analysis
    def save_analysis(self, record: ProjectAnalysisRecord) -> None:
        self._analyses.save(record)

    def get_analysis(self, record_id: str) -> ProjectAnalysisRecord | None:
        return self._analyses.get(record_id)

    def list_analyses(self) -> list[ProjectAnalysisRecord]:
        return self._analyses.list_all()

    # ------------------------------------------------------------ baseline
    def save_baseline(self, record: BaselineRecord) -> None:
        self._baselines.save(record)

    def get_baseline(self, record_id: str) -> BaselineRecord | None:
        return self._baselines.get(record_id)

    def list_baselines(self) -> list[BaselineRecord]:
        return self._baselines.list_all()

    # ------------------------------------------------------------ snapshot
    def save_snapshot(self, record: ContextSnapshotRecord) -> None:
        self._snapshots.save(record)

    def get_snapshot(self, record_id: str) -> ContextSnapshotRecord | None:
        return self._snapshots.get(record_id)

    def list_snapshots(self) -> list[ContextSnapshotRecord]:
        return self._snapshots.list_all()

    # -------------------------------------------------------------- 数据空间
    def files(self) -> list[Path]:
        """三个数据文件 (存在者; 测试/审计用)。"""
        return sorted(
            p
            for p in (
                self._dir / "project_analyses.json",
                self._dir / "project_baselines.json",
                self._dir / "context_snapshots.json",
            )
            if p.exists()
        )


# ------------------------------------------------------------------ 服务


def _load_exec_adoption() -> Any | None:
    """exec.project_adoption 懒加载 (Removal Isolation: 未安装 → None)。

    与 projects.py _validate_exec_role 同模式 — org 侧不硬依赖 exec;
    不可用时不假装校验, 记录 unavailable 原因。
    """
    try:
        import exec.project_adoption  # type: ignore[import-not-found]

        return exec.project_adoption
    except ImportError:
        return None


def _analysis_unavailable_payload(reason: str) -> dict[str, Any]:
    """分析不可用载荷 (契约形状完整 — 字段标记 unavailable, 不崩溃)。"""
    return {
        "language": "unknown",
        "framework": "",
        "structure": [
            {
                "path": "(root)",
                "responsibility": f"analysis unavailable: {reason}",
                "file_count": 0,
            }
        ],
        "dependencies": {"edge_count": 0, "file_count": 0},
        "build_method": "unavailable",
        "test_method": "unavailable",
    }


class ProjectAdoption:
    """已有项目接入服务: 注册 → 分析 → 基线 → 快照 → 记录引用 (事件审计)。

    只消费: ProjectLifecycle (建项目) + CONTRACTS 校验 (validate_artifact) +
    exec.project_adoption (分析/基线/快照执行); 不修改 Workflow/Artifact/
    Approval 状态机, 不改 Developer 核心。exec 缺失 → 全链 unavailable
    (Removal Isolation), 注册仍成功。
    """

    def __init__(
        self,
        store: ProjectStore,
        *,
        logger: Any = None,
        lifecycle: ProjectLifecycle | None = None,
        adoption_store: ProjectAdoptionStore | None = None,
    ) -> None:
        self._store = store
        self._logger = logger
        self._lifecycle = lifecycle or ProjectLifecycle(store, logger=logger)
        self._adoption = adoption_store or ProjectAdoptionStore(store.dir)

    @property
    def store(self) -> ProjectStore:
        return self._store

    @property
    def adoption_store(self) -> ProjectAdoptionStore:
        return self._adoption

    # ------------------------------------------------------------ 注册

    def register(
        self,
        repo_path: str | Path,
        *,
        name: str = "",
        language: str = "",
        framework: str = "",
        build_command: str = "",
        test_command: str = "",
        project_type: str = "",
        goal: str = "",
        user_id: str = "",
        project_id: str | None = None,
    ) -> Project:
        """注册已有项目 (org.project.created + registered; 自动分析/基线/快照)。

        repo_path 必须为存在的目录 (否则 ValueError — 响亮失败, 不静默);
        name 缺省 = 目录名。语言/框架缺省自动检测 (exec 可用时)。
        """
        path = Path(repo_path)
        if not path.is_dir():
            raise ValueError(f"repo path is not a directory: {repo_path}")
        name = name or path.name or "adopted-project"
        project = self._lifecycle.create_project(
            name, user_id=user_id, goal=goal, project_id=project_id
        )
        analysis = self._analyze(path, project.id)
        detected_language = analysis.payload.get("language", "") if analysis else ""
        baseline = self._baseline(
            path,
            project.id,
            analysis_ref=analysis.id if analysis else "",
            build_command=build_command,
            test_command=test_command,
            language=language or detected_language,
        )
        snapshot = self._snapshot(path, project.id)
        updated = project.model_copy(
            update={
                "repo_path": str(path.resolve()),
                "language": language or detected_language,
                "framework": framework
                or (analysis.payload.get("framework", "") if analysis else ""),
                "build_command": build_command,
                "test_command": test_command,
                "project_type": project_type,
                "analysis_ref": analysis.id if analysis else "",
                "baseline_ref": baseline.id if baseline else "",
                "snapshot_ref": snapshot.id if snapshot else "",
                "updated_at": utcnow(),
            }
        )
        self._store.save_project(updated)
        org_events.record_project_registered(
            self._logger, project=updated, repo_path=str(path.resolve())
        )
        return updated

    # ------------------------------------------------------------ 查询

    def get_analysis(self, record_id: str) -> ProjectAnalysisRecord | None:
        return self._adoption.get_analysis(record_id)

    def get_baseline(self, record_id: str) -> BaselineRecord | None:
        return self._adoption.get_baseline(record_id)

    def get_snapshot(self, record_id: str) -> ContextSnapshotRecord | None:
        return self._adoption.get_snapshot(record_id)

    def list_analyses(self) -> list[ProjectAnalysisRecord]:
        return self._adoption.list_analyses()

    def list_baselines(self) -> list[BaselineRecord]:
        return self._adoption.list_baselines()

    def list_snapshots(self) -> list[ContextSnapshotRecord]:
        return self._adoption.list_snapshots()

    def list_projects(self) -> list[Project]:
        return self._lifecycle.list_projects()

    def get_project(self, project_id: str) -> Project:
        return self._lifecycle.get_project(project_id)

    # ------------------------------------------------------------ 内部

    def _analyze(self, path: Path, project_id: str) -> ProjectAnalysisRecord | None:
        """Repository Analyzer → 分析记录 (exec 缺失/异常 → unavailable 记录)。"""
        mod = _load_exec_adoption()
        if mod is None:
            return self._save_analysis(
                project_id,
                _analysis_unavailable_payload("exec not installed"),
                errors=["exec not installed (factory-exec not available)"],
            )
        try:
            payload = mod.analyze_project(path)
        except Exception as exc:  # 失败安全: 分析异常不阻断注册
            return self._save_analysis(
                project_id,
                _analysis_unavailable_payload(f"analysis failed: {exc}"),
                errors=[f"analysis failed: {exc}"],
            )
        result = validate_artifact(ArtifactType.PROJECT_ANALYSIS, payload)
        record = self._save_analysis(
            project_id,
            payload,
            valid=result.ok,
            errors=result.missing + result.errors,
        )
        org_events.record_project_analyzed(
            self._logger,
            project_id=project_id,
            analysis_ref=record.id,
            language=payload.get("language", ""),
            framework=payload.get("framework", ""),
        )
        return record

    def _save_analysis(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        valid: bool = True,
        errors: list[str] | None = None,
    ) -> ProjectAnalysisRecord:
        record = ProjectAnalysisRecord(
            id=new_id("PA"),
            project_id=project_id,
            payload=payload,
            valid=valid,
            errors=errors or [],
        )
        self._adoption.save_analysis(record)
        return record

    def _baseline(
        self,
        path: Path,
        project_id: str,
        *,
        analysis_ref: str,
        build_command: str,
        test_command: str,
        language: str,
    ) -> BaselineRecord:
        """Baseline Validation → 基线记录 (build/test 失败安全)。"""
        mod = _load_exec_adoption()
        payload: dict[str, Any]
        errors: list[str] = []
        if mod is None:
            payload = {
                "build": {
                    "status": "unavailable",
                    "command": "",
                    "output_head": "exec not installed",
                },
                "test": {
                    "status": "unavailable",
                    "command": "",
                    "output_head": "exec not installed",
                    "passed": 0,
                    "failed": 0,
                },
                "analysis_ref": analysis_ref,
            }
            errors = ["exec not installed (factory-exec not available)"]
        else:
            try:
                payload = mod.run_baseline(
                    path,
                    build_command=build_command,
                    test_command=test_command,
                    language=language,
                )
            except Exception as exc:  # 失败安全: 基线异常不阻断注册
                payload = {
                    "build": {
                        "status": "unavailable",
                        "command": "",
                        "output_head": f"baseline failed: {exc}",
                    },
                    "test": {
                        "status": "unavailable",
                        "command": "",
                        "output_head": f"baseline failed: {exc}",
                        "passed": 0,
                        "failed": 0,
                    },
                    "analysis_ref": analysis_ref,
                }
                errors = [f"baseline failed: {exc}"]
            else:
                payload["analysis_ref"] = analysis_ref
        result = validate_artifact(ArtifactType.BASELINE, payload)
        record = self._save_baseline(
            project_id,
            payload,
            valid=result.ok,
            errors=result.missing + result.errors + errors,
        )
        build_status = payload.get("build", {}).get("status", "unavailable")
        test_status = payload.get("test", {}).get("status", "unavailable")
        org_events.record_project_baseline_recorded(
            self._logger,
            project_id=project_id,
            baseline_ref=record.id,
            build_status=build_status,
            test_status=test_status,
        )
        return record

    def _save_baseline(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        valid: bool = True,
        errors: list[str] | None = None,
    ) -> BaselineRecord:
        record = BaselineRecord(
            id=new_id("BL"),
            project_id=project_id,
            payload=payload,
            valid=valid,
            errors=errors or [],
        )
        self._adoption.save_baseline(record)
        return record

    def _snapshot(self, path: Path, project_id: str) -> ContextSnapshotRecord:
        """Context Snapshot → 快照记录 (exec 缺失/异常 → unavailable 快照)。"""
        mod = _load_exec_adoption()
        if mod is None:
            payload = {
                "tree": [],
                "tree_entries": 0,
                "important_files": [],
                "important_count": 0,
                "architecture": {
                    "entry_points": [],
                    "core_modules": [],
                    "tech_stack": [],
                    "risk_areas": [],
                    "summary_text": "context snapshot unavailable: exec not installed",
                },
                "summary_text": "context snapshot unavailable: exec not installed",
            }
        else:
            try:
                payload = mod.build_context_snapshot(path)
            except Exception as exc:  # 失败安全: 快照异常不阻断注册
                payload = {
                    "tree": [],
                    "tree_entries": 0,
                    "important_files": [],
                    "important_count": 0,
                    "architecture": {
                        "entry_points": [],
                        "core_modules": [],
                        "tech_stack": [],
                        "risk_areas": [],
                        "summary_text": f"context snapshot unavailable: {exc}",
                    },
                    "summary_text": f"context snapshot unavailable: {exc}",
                }
        record = ContextSnapshotRecord(
            id=new_id("CS"), project_id=project_id, payload=payload
        )
        self._adoption.save_snapshot(record)
        org_events.record_project_context_snapshotted(
            self._logger,
            project_id=project_id,
            snapshot_ref=record.id,
            tree_entries=payload.get("tree_entries", 0),
            important_count=payload.get("important_count", 0),
        )
        return record
