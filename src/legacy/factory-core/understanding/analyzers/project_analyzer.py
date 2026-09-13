"""understanding/analyzers/project_analyzer.py — 项目基本信息 (规则推断, 禁 LLM)。

设计依据:
- phase7-plan.md §1: project_analyzer.py 项目基本信息 (类型/技术栈/规模/状态)
- 工程规则: 确定性规则 (目录结构 + 文件扩展名 + 构建清单推断), 零 LLM;
  只读 (仅 Path 遍历统计)。

推断规则 (全部确定性, 供测试精确断言):
- type 优先级链: empty (无文件) > documentation (无源码产物) > script
  (有源码文件但无 src/lib/app 目录) > application (有 src/lib/app) >
  service (application + 部署配置存在)。
- scale: 按文件数 0-5 tiny / 6-50 small / 51-300 medium / >300 large。
- status: empty (无文件) / planning (仅文档) / in_development (有源码)
  / developed (源码+测试) / deployable (源码+测试+部署) / operational
  (源码+测试+部署+运维)。
- languages: 源码扩展名计数去重 (ArtifactDetector.scan_extensions)。
- tech_stack: 构建清单 (ArtifactDetector.scan_manifests, pubspec → flutter)。
"""

from __future__ import annotations

from pathlib import Path

from ..models import ProjectBasicInfo
from .artifact_detector import (
    ARTIFACT_DETECTORS,
    ArtifactDetector,
    collect_files,
    _first_has_any,
)

#: 源码/部署/运维目录名 (type/status 推断用, 小写)
_SRC_DIRS = frozenset({"src", "lib", "app", "source"})
_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs"})
_DEPLOY_DIRS = frozenset({"deploy", "deployment", "k8s", "kubernetes", "helm", "terraform"})
_OPS_DIRS = frozenset({"ops", "operations", "monitoring", "grafana", "prometheus", "runbook", "runbooks", "sre"})


class ProjectAnalyzer:
    """项目基本信息推断器 (纯规则, 只读, 零事件)。

    analyze(root) → ProjectBasicInfo; 空目录/损坏目录永不抛错 (失败安全,
    空工厂语义同 dashboard 空快照)。
    """

    def __init__(self) -> None:
        self._detector = ArtifactDetector()

    def analyze(self, root: Path, files: list[Path] | None = None) -> ProjectBasicInfo:
        paths = files if files is not None else collect_files(root)
        basenames = {p.name.lower() for p in paths}
        dirs = {part.lower() for p in paths for part in p.parts[:-1]}

        file_count = len(paths)
        dir_count = len({p.parts[:-1] for p in paths if p.parts[:-1]})
        has_code_files = any(
            p.suffix.lower()
            in (".py", ".dart", ".js", ".ts", ".jsx", ".tsx", ".go", ".java",
                ".rs", ".rb", ".php", ".swift", ".kt", ".c", ".cpp", ".h",
                ".cs", ".scala", ".vue", ".svelte")
            for p in paths
        )
        has_src_dir = bool(dirs & _SRC_DIRS)
        has_deploy = bool(dirs & _DEPLOY_DIRS) or self._has_pattern(paths, "DEPLOYMENT", code_only=True)
        has_test = bool(dirs & _TEST_DIRS) or self._has_pattern(paths, "TEST", code_only=True)
        has_ops = bool(dirs & _OPS_DIRS) or self._has_pattern(paths, "OPERATION", code_only=True)

        # --- type (优先级链) ---
        if file_count == 0:
            ptype = "empty"
        elif not (has_code_files or has_src_dir):
            ptype = "documentation"
        elif has_src_dir and has_deploy:
            ptype = "service"
        elif has_src_dir:
            ptype = "application"
        else:
            ptype = "script"

        # --- status ---
        if file_count == 0:
            status = "empty"
        elif not (has_code_files or has_src_dir):
            status = "planning"
        elif not has_test:
            status = "in_development"
        elif not has_deploy:
            status = "developed"
        elif not has_ops:
            status = "deployable"
        else:
            status = "operational"

        languages = sorted(self._detector.scan_extensions(paths))
        tech_stack = self._detector.scan_manifests(paths)

        return ProjectBasicInfo(
            name=root.name,
            type=ptype,
            languages=languages,
            tech_stack=tech_stack,
            scale=self._scale(file_count),
            status=status,
            file_count=file_count,
            dir_count=dir_count,
        )

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _scale(file_count: int) -> str:
        if file_count <= 5:
            return "tiny"
        if file_count <= 50:
            return "small"
        if file_count <= 300:
            return "medium"
        return "large"

    @staticmethod
    def _has_pattern(paths: list[Path], key: str, *, code_only: bool) -> bool:
        """注册表键的 code_patterns 是否命中 (type/status 推断复用, 只读)。"""
        d = ARTIFACT_DETECTORS[key]
        patterns = d.code_patterns if code_only else d.doc_patterns
        found, _ = _first_has_any(paths, patterns)
        return found
