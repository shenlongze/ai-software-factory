"""understanding — Project Understanding Layer (Phase 7, ADR-0021)。

项目理解: 任意路径 (Idea/PRD/Design/Development/Existing Code/Production)
只读分析 → 生命周期阶段识别 + 7 类产物检测 + 缺失分析 + 结构化建议。

- models: STAGES (10 阶段注册表) / ARTIFACT_KEYS (7 类产物注册表) /
  ProjectUnderstandingReport + StageDetection/ArtifactDetection/MissingAnalysis/
  NextAction (approval_required = Approval Gate 接口标注)
- analyzers: project_analyzer (基本信息) / document_analyzer (文档检测) /
  artifact_detector (ARTIFACT_DETECTORS 注册化产物检测)
- service: UnderstandingService (analyze 编排; 阶段链规则推断, 禁 LLM;
  只读分析 — 不写任何文件)
- events: understanding.started/completed/failed (+ CLI viewed) 审计事件辅助

工程规则 (冻结约束): Core 零修改; 确定性规则 (禁 LLM, 未来经 Provider 抽象);
Approval Gate 只设计接口 (不实现 Web UI); 无 Database/Web API。
"""

from .analyzers.artifact_detector import (
    ARTIFACT_DETECTORS,
    ArtifactDetector,
    ArtifactDetectorDef,
    collect_files,
)
from .analyzers.document_analyzer import DOCUMENT_KEYS, DocumentAnalyzer
from .analyzers.project_analyzer import ProjectAnalyzer
from .events import (
    record_understanding_completed,
    record_understanding_failed,
    record_understanding_started,
    record_understanding_viewed,
)
from .models import (
    ARTIFACT_KEYS,
    STAGES,
    ArtifactDetection,
    MissingAnalysis,
    NextAction,
    ProjectBasicInfo,
    ProjectUnderstandingReport,
    StageDetection,
    stage_index,
)
from .service import (
    ARTIFACT_STAGE,
    STAGE_EVIDENCE_PATTERNS,
    UnderstandingError,
    UnderstandingService,
    build_missing,
    build_next_actions,
    detect_stage,
)

__all__ = [
    # 注册表
    "STAGES",
    "ARTIFACT_KEYS",
    "ARTIFACT_DETECTORS",
    "DOCUMENT_KEYS",
    "ARTIFACT_STAGE",
    "STAGE_EVIDENCE_PATTERNS",
    # models
    "ProjectUnderstandingReport",
    "StageDetection",
    "ArtifactDetection",
    "MissingAnalysis",
    "NextAction",
    "ProjectBasicInfo",
    "stage_index",
    # analyzers
    "ProjectAnalyzer",
    "DocumentAnalyzer",
    "ArtifactDetector",
    "ArtifactDetectorDef",
    "collect_files",
    # service
    "UnderstandingService",
    "UnderstandingError",
    "detect_stage",
    "build_missing",
    "build_next_actions",
    # events
    "record_understanding_started",
    "record_understanding_completed",
    "record_understanding_failed",
    "record_understanding_viewed",
]
