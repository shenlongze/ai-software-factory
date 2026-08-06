"""understanding/analyzers/artifact_detector.py — 产物检测 (注册化检测器, 禁 LLM)。

设计依据:
- phase7-plan.md §1/§2: artifact_detector.py 产物检测 (源码/tests/构建配置/
  发布配置/部署配置) + ARTIFACT_DETECTORS 注册表 (7 类, 可扩展)
- 工程规则: 确定性规则分析 (禁 LLM); 只读 (仅 Path 遍历, 零写操作);
  注册化扩展 = 向 ARTIFACT_DETECTORS 追加 ArtifactDetectorDef 条目。

ARTIFACT_DETECTORS 注册表 (7 类, 与 models.ARTIFACT_KEYS 一一对应):
- 每类检测器携带 doc_patterns (文档类产物: PRD/UI/架构/部署/运维文档的常见
  文件名) 与 code_patterns (代码/配置类产物: 源码目录/扩展名/构建配置/
  测试/部署/运维基础设施)。两类模式互补: document_analyzer.py 只匹配
  doc_patterns (文档检测职责), 本模块匹配 code_patterns + 目录结构推断。

匹配语义 (确定性, 大小写不敏感):
- 模式按相对路径 (正斜杠, 小写) 做三态匹配: ① basename 精确相等
  (dockerfile) ② 路径前缀 (src/ 匹配 src/main.dart) ③ 路径子串
  (tests/ 匹配 tests/unit/test_a.py)。目录模式 (src/、test/) 天然覆盖
  子树; 扩展名模式 (*.py) 匹配 basename。
- 隐藏目录 (HIDDEN_DIRS: .git/.dart_tool/node_modules/build/...) 整体跳过
  — 避免依赖目录污染计数与检测 (markpad 的 build/ 即 Flutter 构建产物)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import ArtifactDetection

# 跳过分析的隐藏/依赖目录 (相对路径组件精确匹配; 大小写不敏感)
HIDDEN_DIRS = frozenset({
    ".git", ".svn", ".hg", ".idea", ".vscode", ".factory", ".dart_tool",
    ".build", ".next", ".nuxt", ".gradle", ".mvn", ".tox", ".eggs",
    "node_modules", "venv", ".venv", "env", "__pycache__", "build", "dist",
    "coverage", "htmlcov", "target", "out", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "Pods", ".symlinks", ".metadata", "tmp", "temp",
    ".worktrees", ".trunk", ".cache", ".local", ".bundle",
})

# 常见源码扩展名 → 语言 (ProjectAnalyzer.languages 与 SOURCE_CODE 检测共用)
SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "python", ".dart": "dart", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".java": "java",
    ".rs": "rust", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin", ".c": "c", ".h": "c", ".cpp": "cpp",
    ".hpp": "cpp", ".cc": "cpp", ".cs": "csharp", ".scala": "scala",
    ".vue": "vue", ".svelte": "svelte", ".html": "html", ".css": "css",
    ".scss": "scss", ".sql": "sql", ".sh": "shell", ".bash": "shell",
    ".zsh": "shell", ".lua": "lua", ".r": "r", ".m": "objective-c",
    ".zig": "zig", ".ex": "elixir", ".exs": "elixir", ".fs": "fsharp",
}

# 构建/包配置文件 (存在 → SOURCE_CODE 强证据; 同时驱动 tech_stack 推断)
BUILD_MANIFESTS: dict[str, str] = {
    "pubspec.yaml": "dart", "pubspec.lock": "dart", "package.json": "node",
    "package-lock.json": "node", "yarn.lock": "node", "pnpm-lock.yaml": "node",
    "go.mod": "go", "go.sum": "go", "Cargo.toml": "rust", "Cargo.lock": "rust",
    "pyproject.toml": "python", "setup.py": "python", "requirements.txt": "python",
    "Pipfile": "python", "poetry.lock": "python", "pom.xml": "java",
    "build.gradle": "java", "build.gradle.kts": "java", "settings.gradle": "java",
    "Gemfile": "ruby", "composer.json": "php", "package.xml": "php",
    "CMakeLists.txt": "cpp", "Makefile": "cpp", "mix.exs": "elixir",
    "project.clj": "clojure", "csproj": "csharp", "*.csproj": "csharp",
}


@dataclass(frozen=True)
class ArtifactDetectorDef:
    """单个产物检测器定义 (注册表条目)。

    key: 注册表键 (models.ARTIFACT_KEYS 成员, 可扩展追加);
    name/description: 展示与说明;
    doc_patterns: 文档类常见文件名 (document_analyzer.py 专用);
    code_patterns: 代码/配置类模式 (本模块专用);
    detail_hint: 检测到时的 detail 前缀 (如 "源码目录 lib/")。
    """

    key: str
    name: str
    description: str
    doc_patterns: tuple[str, ...] = ()
    code_patterns: tuple[str, ...] = ()
    detail_hint: str = ""


#: 7 类产物注册表 (models.ARTIFACT_KEYS 一一对应; 可扩展 = 追加条目)。
#: 匹配模式均为小写相对路径 (调用侧负责 lower), 见模块 docstring 三态匹配。
ARTIFACT_DETECTORS: dict[str, ArtifactDetectorDef] = {
    "PRD": ArtifactDetectorDef(
        key="PRD",
        name="产品需求文档",
        description="PRD/需求文档 (docs/prd.md 等常见文件名)",
        doc_patterns=(
            "prd.md", "prd.txt", "prd.adoc", "prd.rst",
            "requirements.md", "requirements.txt",
            "product-requirements.md", "product-requirement.md",
            "产品需求文档.md", "产品需求.md", "需求文档.md", "需求说明书.md",
            "docs/prd.md", "docs/requirements.md",
        ),
        detail_hint="PRD 文档",
    ),
    "UI_DESIGN": ArtifactDetectorDef(
        key="UI_DESIGN",
        name="UI 设计文档",
        description="界面设计稿/设计文档 (docs/ui.md、designs/ 目录等)",
        doc_patterns=(
            "ui.md", "ui-design.md", "ui_design.md", "design.md",
            "designs/", "design/", "ui/", "ui-design/",
            "设计稿.md", "界面设计.md", "原型.md",
            "docs/ui.md", "docs/design.md",
        ),
        detail_hint="UI 设计文档",
    ),
    "ARCHITECTURE": ArtifactDetectorDef(
        key="ARCHITECTURE",
        name="架构文档",
        description="架构/技术设计文档 (docs/architecture.md 等)",
        doc_patterns=(
            "architecture.md", "arch.md", "architecture-design.md",
            "technical-design.md", "tech-design.md", "design.md",
            "architecture/", "docs/architecture.md", "docs/arch.md",
            "docs/architecture-design.md", "docs/technical-design.md",
            "架构.md", "架构设计.md", "技术方案.md", "技术设计.md",
        ),
        detail_hint="架构文档",
    ),
    "SOURCE_CODE": ArtifactDetectorDef(
        key="SOURCE_CODE",
        name="源码",
        description="源码目录 (src/lib/app) / 源码扩展名 / 构建配置文件",
        code_patterns=(
            "src/", "lib/", "app/", "source/",
            "*.py", "*.dart", "*.js", "*.ts", "*.jsx", "*.tsx", "*.go",
            "*.java", "*.rs", "*.rb", "*.php", "*.swift", "*.kt", "*.c",
            "*.cpp", "*.h", "*.cs", "*.scala", "*.vue", "*.svelte",
            "pubspec.yaml", "package.json", "go.mod", "cargo.toml",
            "pyproject.toml", "setup.py", "requirements.txt",
            "pom.xml", "build.gradle", "gemfile", "composer.json",
            "cmakelists.txt", "mix.exs",
        ),
        detail_hint="源码",
    ),
    "TEST": ArtifactDetectorDef(
        key="TEST",
        name="测试",
        description="测试目录 (test/tests) / 测试文件命名约定",
        code_patterns=(
            "test/", "tests/", "__tests__/", "spec/", "specs/",
            "test_*.py", "*_test.py", "*_test.dart", "*_test.go",
            "*_test.rb", "*_test.rs", "*_test.js", "*_test.ts",
            "*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts",
            "*_spec.dart", "*_spec.rb", "*_spec.py",
        ),
        detail_hint="测试",
    ),
    "DEPLOYMENT": ArtifactDetectorDef(
        key="DEPLOYMENT",
        name="部署配置",
        description="部署/发布配置 (Dockerfile/docker-compose/k8s/CI 发布)",
        doc_patterns=(
            "deployment.md", "deploy.md", "release.md", "release-notes.md",
            "部署.md", "部署文档.md", "发布.md", "发布文档.md",
            "docs/deployment.md", "docs/deploy.md",
        ),
        code_patterns=(
            "dockerfile", "dockerfile.*", "docker-compose.yml",
            "docker-compose.yaml", "compose.yml", "compose.yaml",
            "deploy/", "deployment/", "k8s/", "kubernetes/", "helm/",
            "terraform/", "*.tf", "serverless.yml", "serverless.yaml",
            ".github/workflows/deploy", ".github/workflows/release",
            "scripts/deploy", "scripts/release",
        ),
        detail_hint="部署配置",
    ),
    "OPERATION": ArtifactDetectorDef(
        key="OPERATION",
        name="运维配置",
        description="运维/监控产物 (runbook/监控配置/CI 工作流/ops 脚本)",
        doc_patterns=(
            "runbook.md", "runbooks.md", "ops.md", "operations.md",
            "monitoring.md", "oncall.md", "incident.md",
            "运维.md", "运维手册.md", "应急预案.md",
            "docs/runbook.md", "docs/ops.md",
        ),
        code_patterns=(
            ".github/workflows/", "ops/", "operations/", "monitoring/",
            "grafana/", "prometheus/", "alertmanager/", "datadog/",
            "runbook", "runbooks/", "scripts/monitor", "scripts/backup",
            "*.service", "systemd/", "sre/", "chaos/",
        ),
        detail_hint="运维配置",
    ),
}

#: 文档类产物键 (doc_patterns 非空 → document_analyzer 职责范围)
DOCUMENT_KEYS: tuple[str, ...] = tuple(
    key for key, d in ARTIFACT_DETECTORS.items() if d.doc_patterns
)


def collect_files(root: Path) -> list[Path]:
    """递归收集相对路径列表 (跳过 HIDDEN_DIRS; 只读, 含隐藏文件如 .github/)。"""
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(part.lower() in HIDDEN_DIRS for part in rel.parts[:-1]):
            continue  # 文件位于隐藏目录内 → 跳过
        files.append(rel)
    return files


def _rel_key(path: Path) -> str:
    """相对路径 → 小写正斜杠键 (匹配基准)。"""
    return path.as_posix().lower()


def _match(rel_key: str, pattern: str) -> bool:
    """单模式三态匹配: basename 相等 / 路径前缀 (目录) / 路径子串。

    确定性规则 (禁 LLM): 模式为小写; rel_key 为小写相对路径。
    ① 前缀匹配 — "src/" 命中 "src/main.dart"; ② basename 精确 —
    "dockerfile" 命中根级 Dockerfile; ③ 子串 — "test/" 命中
    "tests/unit/test_a.py" (目录名含 test); ④ glob ("*.py") 匹配 basename。
    """
    if pattern.startswith("*."):
        return rel_key.endswith(pattern[1:])
    if pattern.endswith("/"):
        return rel_key.startswith(pattern)
    if "/" not in pattern:
        return rel_key == pattern or f"/{pattern}" in rel_key
    return pattern in rel_key


def _first_has_any(paths: list[Path], patterns: tuple[str, ...]) -> tuple[bool, list[str]]:
    """按注册表模式检测: 返回 (命中?, 命中相对路径列表, 上限 8 条)。"""
    hits: list[str] = []
    for path in paths:
        rel_key = _rel_key(path)
        if any(_match(rel_key, p) for p in patterns):
            hits.append(path.as_posix())
            if len(hits) >= 8:
                break
    return bool(hits), hits


def _detail(hits: list[str], hint: str, total: int) -> str:
    """detail 文本: 前 8 条路径 + 溢出计数。"""
    shown = ", ".join(hits)
    extra = f" (+{total - len(hits)} 项)" if total > len(hits) else ""
    return f"{hint}: {shown}{extra}" if hint else f"{shown}{extra}"


class ArtifactDetector:
    """代码/配置类产物检测器 (遍历 ARTIFACT_DETECTORS 注册表的 code_patterns)。

    只读: 仅 collect_files + 模式匹配, 零写操作, 零事件 (分析审计事件由
    UnderstandingService 发出 — 同 collector 只读边界)。
    """

    def __init__(self, registry: dict[str, ArtifactDetectorDef] | None = None) -> None:
        # 注册表可注入 (测试可传入子集/自定义注册表验证可扩展性), 缺省全量。
        self._registry = registry if registry is not None else ARTIFACT_DETECTORS

    def detect(self, root: Path, files: list[Path] | None = None) -> dict[str, ArtifactDetection]:
        """检测全部代码/配置类产物 → {key: ArtifactDetection} (仅含 code_patterns 键)。"""
        paths = files if files is not None else collect_files(root)
        results: dict[str, ArtifactDetection] = {}
        for key, d in self._registry.items():
            if not d.code_patterns:
                continue
            found, hits = _first_has_any(paths, d.code_patterns)
            total = len(hits)
            # 源码目录 (src/lib/app) 是 SOURCE_CODE 的强信号, 即使无已知扩展名
            if key == "SOURCE_CODE" and not found:
                src_dirs = [p for p in paths if any(
                    part.lower() in ("src", "lib", "app", "source")
                    for part in p.parts[:-1]
                )]
                if src_dirs:
                    found = True
                    hits = [p.as_posix() for p in src_dirs[:8]]
                    total = len(src_dirs)
            results[key] = ArtifactDetection(
                artifact=key,
                present=found,
                detail=_detail(hits, d.detail_hint, total) if found else "",
            )
        return results

    @staticmethod
    def scan_extensions(files: list[Path]) -> dict[str, int]:
        """源码扩展名 → 出现次数 (ProjectAnalyzer.languages 数据源, 只读)。"""
        counts: dict[str, int] = {}
        for path in files:
            ext = path.suffix.lower()
            lang = SOURCE_EXTENSIONS.get(ext)
            if lang is not None:
                counts[lang] = counts.get(lang, 0) + 1
        return counts

    @staticmethod
    def scan_manifests(files: list[Path]) -> list[str]:
        """构建/包清单 → 技术栈列表 (去重保序; pubspec → flutter 增强)。"""
        stack: list[str] = []
        basenames = {p.name.lower() for p in files}
        for pattern, tech in BUILD_MANIFESTS.items():
            hit = pattern in basenames or any(
                _match(p.as_posix().lower(), pattern) for p in files
            )
            if hit and tech not in stack:
                stack.append(tech)
        if "pubspec.yaml" in basenames and "flutter" not in stack:
            stack.append("flutter")
        return stack
