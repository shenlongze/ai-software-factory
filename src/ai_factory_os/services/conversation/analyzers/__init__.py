"""understanding/analyzers — 规则分析器 (禁 LLM, 确定性规则)。

- project_analyzer: 项目基本信息 (类型/技术栈/规模/状态, 目录/扩展名推断)
- document_analyzer: 文档检测 (PRD/UI/架构/部署/运维文档, 注册表 doc_patterns)
- artifact_detector: 产物检测 (源码/tests/构建/发布/部署配置, ARTIFACT_DETECTORS
  注册表 7 类, 可扩展) + 文件收集 (collect_files, 跳过隐藏/依赖目录)
"""

from .artifact_detector import (
    ARTIFACT_DETECTORS,
    ArtifactDetector,
    ArtifactDetectorDef,
    BUILD_MANIFESTS,
    DOCUMENT_KEYS as ARTIFACT_DOCUMENT_KEYS,
    HIDDEN_DIRS,
    SOURCE_EXTENSIONS,
    collect_files,
)
from .document_analyzer import DOCUMENT_KEYS, DocumentAnalyzer
from .project_analyzer import ProjectAnalyzer

__all__ = [
    "ARTIFACT_DETECTORS",
    "ArtifactDetector",
    "ArtifactDetectorDef",
    "BUILD_MANIFESTS",
    "DOCUMENT_KEYS",
    "DocumentAnalyzer",
    "HIDDEN_DIRS",
    "ProjectAnalyzer",
    "SOURCE_EXTENSIONS",
    "collect_files",
    "ARTIFACT_DOCUMENT_KEYS",
]
