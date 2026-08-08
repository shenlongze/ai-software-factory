"""tests/s7/conftest.py — S7-001 统一生命周期模型测试 fixtures (Sprint 7, ADR-0039)。

本目录为双体系统一测试空间: org (factory-org) + exec (factory-exec) 同时挂载,
覆盖 S7-001 核心验收:
- resolve_role 3 链解析 / org_role_coverage / 模板 role_ref 完整性
- Project/Sprint/Stage/Artifact/ProjectTaskLink CRUD + 生命周期状态机 + 事件
- 集成链: hire → project → sprint → task 关联 → stage → artifact
- 向后兼容: 既有 roles.json 无 role_ref 加载零破坏 / 双体系并存

fixtures (同 tests/org 模式):
- org_dir: 独立 Org 数据空间 (<root>/org)
- org_store: OrgStore (六子库门面)
- project_store: ProjectStore (五新库门面, 与 OrgStore 同目录不同文件)
- db_path / logger / event_store: 事件集成断言 (org.project.* / org.sprint.* /
  org.stage.* / org.artifact.* 7 事件)

sys.path: 挂 factory-core (Core 包) + factory-org (org 包父目录) +
factory-exec (exec 包父目录 — 双体系统一解析链需要 exec 注册表真实可用)。
本目录自洽 (不跨目录依赖 helper); 测试文件 basename 一律 test_s7_* 前缀
(backend-developer skill 陷阱: 多非包目录共存时同名模块互相遮蔽)。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _pkg, _sub in (
    ("factory-core", None),
    ("factory-org", "org"),
    ("factory-exec", "exec"),
):
    _dir = _ROOT / _pkg
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest

from events.logger import EventLogger
from events.store import EventStore

from org.artifact import ArtifactRegistry
from org.projects import ProjectStore
from org.store import OrgStore


@pytest.fixture
def org_dir(tmp_path: Path) -> Path:
    """Org 数据空间 (<root>/org — 六旧库 + 五新库同目录并存)。"""
    return tmp_path / "factory" / "org"


@pytest.fixture
def org_store(org_dir: Path) -> OrgStore:
    return OrgStore(org_dir)


@pytest.fixture
def project_store(org_dir: Path) -> ProjectStore:
    """统一生命周期数据空间 (projects/sprints/stages/artifacts/links 五文件)。"""
    return ProjectStore(org_dir)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (S7-001 事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def registry(project_store: ProjectStore, logger: EventLogger) -> ArtifactRegistry:
    """ArtifactRegistry (S7-002; logger 带事件库, 事件集成断言)。"""
    return ArtifactRegistry(project_store, logger=logger)


@pytest.fixture
def no_logger_registry(project_store: ProjectStore) -> ArtifactRegistry:
    """logger=None: 事件全静默 (同既有 org 模式)。"""
    return ArtifactRegistry(project_store, logger=None)
