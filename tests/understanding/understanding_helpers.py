"""tests/understanding/understanding_helpers.py — 项目理解测试项目构造工具 (唯一名 helper)。

场景项目构造 (tmp 目录内写真实文件, 供 UnderstandingService/CLI 只读分析):

- make_project(root, files): 按 {相对路径: 内容} 写文件树
- empty_project: 空目录 (无任何文件) → IDEA
- readme_project: 仅 README.md → PRD (弱证据)
- research_project: 研究文档 (docs/research.md) → RESEARCH
- prd_project: docs/prd.md → PRD (产物证据)
- ui_project: PRD + UI 设计 → UI_DESIGN
- docs_complete_project: PRD+UI+架构 → ARCHITECTURE (文档完整)
- code_project: src/ 源码 → DEVELOPMENT
- code_test_project: src/ + tests/ → TESTING
- release_project: 源码 + 发布配置 (changelog.md) → RELEASE
- prod_project: 源码+测试+部署 → PRODUCTION
- ops_project: 源码+测试+部署+运维 → OPERATION (全产物)
"""

from __future__ import annotations

from pathlib import Path

PRD_DOC = "docs/prd.md"
UI_DOC = "docs/ui.md"
ARCH_DOC = "docs/architecture.md"
DEPLOY_DOC = "docs/deployment.md"
OPS_DOC = "docs/runbook.md"


def make_project(root: Path, files: dict[str, str]) -> Path:
    """在 root 下按 {相对路径: 内容} 写文件树 (只写, 不校验)。"""
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def empty_project(root: Path) -> Path:
    """空项目: 空目录 (IDEA / 全缺失 / type=empty)。"""
    root.mkdir(parents=True, exist_ok=True)
    return root


def readme_project(root: Path) -> Path:
    """新项目: 仅 README (PRD 弱证据 / documentation / planning)。"""
    return make_project(root, {"README.md": "# Demo\n\nA new project.\n"})


def research_project(root: Path) -> Path:
    """研究阶段项目: 市场调研文档。"""
    return make_project(root, {
        "docs/research.md": "# Market research\n",
        "README.md": "# Demo\n",
    })


def prd_project(root: Path) -> Path:
    """PRD 阶段: 产品需求文档 (产物证据)。"""
    return make_project(root, {PRD_DOC: "# PRD\n\n## Requirements\n"})


def ui_project(root: Path) -> Path:
    """UI 设计阶段: PRD + UI 设计稿。"""
    return make_project(root, {
        PRD_DOC: "# PRD\n",
        UI_DOC: "# UI Design\n",
    })


def docs_complete_project(root: Path) -> Path:
    """文档完整项目: PRD + UI + 架构 (ARCHITECTURE 边界)。"""
    return make_project(root, {
        PRD_DOC: "# PRD\n",
        UI_DOC: "# UI\n",
        ARCH_DOC: "# Architecture\n",
    })


def code_project(root: Path) -> Path:
    """开发阶段: src/ 源码 (DEVELOPMENT / application / in_development)。"""
    return make_project(root, {
        "src/main.py": "def main():\n    print('hi')\n",
        "README.md": "# App\n",
    })


def code_test_project(root: Path) -> Path:
    """测试阶段: src/ + tests/ (TESTING / developed)。"""
    return make_project(root, {
        "src/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert main() == 1\n",
    })


def release_project(root: Path) -> Path:
    """发布阶段: 源码 + 发布配置 (RELEASE — DEVELOPMENT/TESTING 被 release 证据推进)。"""
    return make_project(root, {
        "src/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert main() == 1\n",
        "CHANGELOG.md": "# 1.0.0\n",
    })


def prod_project(root: Path) -> Path:
    """生产边界: 源码+测试+部署配置 (PRODUCTION / deployable)。"""
    return make_project(root, {
        "src/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert main() == 1\n",
        "Dockerfile": "FROM python:3.12\n",
    })


def ops_project(root: Path) -> Path:
    """运维阶段项目: 源码+测试+部署+运维 (OPERATION / operational; 4 类 code 产物)。"""
    return make_project(root, {
        "src/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert main() == 1\n",
        "Dockerfile": "FROM python:3.12\n",
        "ops/monitoring.yaml": "scrape: 30s\n",
    })


def complete_project(root: Path) -> Path:
    """7 类产物齐全的项目: PRD+UI+架构文档 + 源码+测试+部署+运维 (OPERATION / 无缺失)。"""
    return make_project(root, {
        PRD_DOC: "# PRD\n",
        UI_DOC: "# UI\n",
        ARCH_DOC: "# Architecture\n",
        "src/main.py": "def main():\n    return 1\n",
        "tests/test_main.py": "def test_main():\n    assert main() == 1\n",
        "Dockerfile": "FROM python:3.12\n",
        "ops/monitoring.yaml": "scrape: 30s\n",
    })


def snapshot_tree(root: Path) -> dict[str, bytes]:
    """目录字节级快照 {相对路径: bytes} (只读性断言: 分析前后必须逐字节相同)。

    过滤 SQLite WAL 侧文件不需要 (项目目录不含事件库); 含隐藏文件 (分析可能
    读取 .github 等), 全量比对最严格。
    """
    snap: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            snap[p.relative_to(root).as_posix()] = p.read_bytes()
    return snap
