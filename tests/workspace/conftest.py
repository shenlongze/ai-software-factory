"""tests/workspace/conftest.py — Phase 6A Workspace Layer 测试 fixtures。

sys.path 兜底同既有模式 (tests/cli, tests/dashboard); 复用 cli_helpers
(run_cli/open_events/event_types) 与 dashboard_helpers (数据构造)。

多项目 fixture: examples_dir 含 markpad (复制真实配置) + scorepocket + timeon
(最小配置, agents/skills/workflows.yaml 缺失 = 空列表, ADR-0013 约定)。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_CLI_TESTS = _ROOT / "tests" / "cli"
if str(_CLI_TESTS) not in sys.path:
    sys.path.insert(0, str(_CLI_TESTS))  # 复用 cli_helpers
_DASH_TESTS = _ROOT / "tests" / "dashboard"
if str(_DASH_TESTS) not in sys.path:
    sys.path.insert(0, str(_DASH_TESTS))  # 复用 dashboard_helpers

import pytest

from workspace.loader import managed_projects_dir

_MARKPAD_FILES = ("project.yaml", "agents.yaml", "skills.yaml", "workflows.yaml")

# scorepocket / timeon 最小项目配置 (仅 project.yaml, 增强字段 status/runtime_preferences)
SCOREPOCKET_PROJECT = """\
name: scorepocket
language: swift
repository: /Users/Shared/work/scorepocket
description: "ScorePocket — 本地记分板 (Swift/iOS)"
tech_stack: [swift, ios]
status: active
runtime_preferences:
  timeout_seconds: 120
"""

TIMEON_PROJECT = """\
name: timeon
language: typescript
repository: /Users/Shared/work/timeon
description: "TimeOn — 时间追踪 (TypeScript/Node)"
tech_stack: [typescript, node]
status: archived
runtime_preferences:
  timeout_seconds: 300
"""


def write_project_dir(base: Path, name: str, project_yaml: str, files: tuple[str, ...]) -> Path:
    """写一个项目目录 (project.yaml + 可选 agents/skills/workflows.yaml)。"""
    dst = base / name
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "project.yaml").write_text(project_yaml, encoding="utf-8")
    if files:
        src = _ROOT / "examples" / "markpad"
        for fname in files:
            (dst / fname).write_text((src / fname).read_text(encoding="utf-8"), encoding="utf-8")
    return dst


@pytest.fixture
def examples_dir(tmp_path: Path) -> Path:
    """临时 examples 目录: markpad (真实配置) + scorepocket + timeon (最小配置)。"""
    base = tmp_path / "examples"
    src_markpad = _ROOT / "examples" / "markpad"
    write_project_dir(base, "markpad",
                      (src_markpad / "project.yaml").read_text(encoding="utf-8"),
                      _MARKPAD_FILES)
    write_project_dir(base, "scorepocket", SCOREPOCKET_PROJECT, ())
    write_project_dir(base, "timeon", TIMEON_PROJECT, ())
    return base


@pytest.fixture
def factory_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (每个测试隔离)。"""
    return tmp_path / "factory"


@pytest.fixture
def managed_dir(factory_root: Path) -> Path:
    """用户管理项目目录 <root>/workspace/projects。"""
    return managed_projects_dir(factory_root)


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"
