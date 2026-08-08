"""tests/s9/conftest.py — S9-001 Approval Gate 测试 fixtures (Sprint 9)。

本目录为 S9-001 测试空间: org (factory-org) 挂载 (审批门在 org 侧;
exec 注册表经 factory-exec 挂载供 role_id 校验), 覆盖 S9-001 核心验收:
- ApprovalGate 模型 + 受控状态机 (APPROVAL_TRANSITIONS, 终态不可撤销)
- ApprovalGateStore 持久化 (approvals.json 原子写 + 损坏失败安全)
- Workflow 接线: approval_required stage COMPLETED → PENDING + PAUSED;
  approve 继续 (PAUSED→ACTIVE) / reject 停止 (→FAILED)
- 事件契约 org.approval.created/approved/rejected (EventType +3)
- CLI approval list/show/approve/reject
- 冒烟: executor 全链三挡板 (metadata 与 org CONTRACTS 同源)

fixtures (同 tests/s7 模式):
- org_dir: 独立 Org 数据空间 (<root>/org)
- org_store: OrgStore (六旧库门面)
- project_store: ProjectStore (五新库门面, 与 OrgStore 同目录不同文件)
- db_path / logger / event_store: 事件集成断言 (org.approval.* 3 事件)
- wlife: WorkflowLifecycle (Workflow/Stage/Artifact + Approval Gate 接线)
- project_id: 预建项目 (Workflow 引用完整前置)

sys.path: 挂 factory-core (Core 包) + factory-org (org 包父目录) +
factory-exec (exec 包父目录 — role_id 校验需要 exec 注册表真实可用)。
本目录自洽 (不跨目录依赖 helper); 测试文件 basename 一律 test_s9_* 前缀
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

from org.approval import ApprovalGateStore
from org.projects import Project, ProjectStore
from org.store import OrgStore
from org.workflow import WorkflowLifecycle


@pytest.fixture
def org_dir(tmp_path: Path) -> Path:
    """Org 数据空间 (<root>/org — 六旧库 + 五新库 + approvals.json 并存)。"""
    return tmp_path / "factory" / "org"


@pytest.fixture
def org_store(org_dir: Path) -> OrgStore:
    return OrgStore(org_dir)


@pytest.fixture
def project_store(org_dir: Path) -> ProjectStore:
    """统一生命周期数据空间 (projects/sprints/stages/artifacts/links 五文件)。"""
    return ProjectStore(org_dir)


@pytest.fixture
def approval_store(org_dir: Path) -> ApprovalGateStore:
    """ApprovalGate 持久化 (approvals.json — S9-001 新数据空间)。"""
    return ApprovalGateStore(org_dir)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (S9-001 事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def wlife(project_store: ProjectStore, logger: EventLogger) -> WorkflowLifecycle:
    """WorkflowLifecycle (S7-003 复用 + S9-001 审批门接线; logger 带事件库)。"""
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def no_logger_wlife(project_store: ProjectStore) -> WorkflowLifecycle:
    """logger=None 的 WorkflowLifecycle (事件全静默 — CLI 种子/零事件断言)。"""
    return WorkflowLifecycle(project_store, logger=None)


@pytest.fixture
def project_id(project_store: ProjectStore) -> str:
    """预建项目 (Workflow 引用完整前置)。"""
    project_store.save_project(Project(id="P-9", name="Approval App", user_id="u1"))
    return "P-9"
