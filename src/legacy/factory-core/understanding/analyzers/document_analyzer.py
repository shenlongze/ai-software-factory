"""understanding/analyzers/document_analyzer.py — 文档检测 (常见文件名匹配, 禁 LLM)。

设计依据:
- phase7-plan.md §1: document_analyzer.py 文档检测 (PRD/UI/架构/部署/运维文档)
- 工程规则: 确定性文件名/路径模式匹配; 只读; 注册化 (模式全部来自
  artifact_detector.ARTIFACT_DETECTORS 各条目的 doc_patterns, 不重复定义)。

职责边界: 本模块只检测文档类产物 (DOCUMENT_KEYS: PRD/UI_DESIGN/
ARCHITECTURE/DEPLOYMENT/OPERATION 的 doc_patterns); 代码/配置类产物
(SOURCE_CODE/TEST + code_patterns) 由 artifact_detector.py 负责。
两类结果由 UnderstandingService 按注册表键合并 (任一命中 → present)。
"""

from __future__ import annotations

from pathlib import Path

from ..models import ArtifactDetection
from .artifact_detector import (
    ARTIFACT_DETECTORS,
    ArtifactDetectorDef,
    _first_has_any,
    collect_files,
)

#: 文档类产物键 (注册表 doc_patterns 非空的条目; 可随注册表扩展)
DOCUMENT_KEYS: tuple[str, ...] = tuple(
    key for key, d in ARTIFACT_DETECTORS.items() if d.doc_patterns
)


class DocumentAnalyzer:
    """文档类产物检测器 (遍历注册表 doc_patterns, 只读, 零事件)。"""

    def __init__(self, registry: dict[str, ArtifactDetectorDef] | None = None) -> None:
        self._registry = registry if registry is not None else ARTIFACT_DETECTORS

    def detect(self, root: Path, files: list[Path] | None = None) -> dict[str, ArtifactDetection]:
        """检测全部文档类产物 → {key: ArtifactDetection} (仅含 doc_patterns 键)。

        匹配语义与 artifact_detector 一致 (三态: basename 相等 / 路径前缀 /
        子串, 大小写不敏感); detail 列出命中文件 (上限 8 条)。
        """
        paths = files if files is not None else collect_files(root)
        results: dict[str, ArtifactDetection] = {}
        for key, d in self._registry.items():
            if not d.doc_patterns:
                continue
            found, hits = _first_has_any(paths, d.doc_patterns)
            shown = ", ".join(hits)
            results[key] = ArtifactDetection(
                artifact=key,
                present=found,
                detail=(f"{d.detail_hint}: {shown}" if found else ""),
            )
        return results
