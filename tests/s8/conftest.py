"""tests/s8/conftest.py — S8-001 PM Agent 测试 fixtures (Sprint 8)。

本目录为 S8-001 双体系测试空间: org (factory-org) + exec (factory-exec)
同时挂载, 覆盖 S8-001 核心验收:
- PM role executable (roles.py: execution_kind/prompt 7 节/pm 别名)
- CONTRACTS product 类型 (7 节必填 + validation_rules) + idea 类型
- PMAgent (Idea → 结构化 Product Artifact; mock provider; 垃圾响亮拒绝)
- Workflow product stage 接入 (WorkflowLifecycle 复用, 不改 Runner 核心;
  executor = build_pm_executor; 事件 org.workflow.stage.*)

fixtures (同 tests/s7 模式):
- org_dir / project_store / db_path / logger / event_store: 事件集成断言
- wlife: WorkflowLifecycle (Workflow/Stage/Artifact 编排 + 审计事件)
- pm_mock_provider: mock provider 工厂 (LLM 输出注入, 零真实调用)

sys.path: 挂 factory-core + factory-org + factory-exec (同 s7 conftest)。
本目录自洽 (不跨目录依赖 helper); 测试文件 basename 一律 test_s8_* 前缀
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

from org.projects import ProjectStore
from org.store import OrgStore
from org.workflow import WorkflowLifecycle


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
    """带事件库的 EventLogger (S8-001 事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def wlife(project_store: ProjectStore, logger: EventLogger) -> WorkflowLifecycle:
    """WorkflowLifecycle (S7-003 复用, 零修改; logger 带事件库)。"""
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def project_id(project_store: ProjectStore) -> str:
    """预建项目 (Workflow 引用完整前置)。"""
    from org.projects import Project

    project_store.save_project(Project(id="P-8", name="Build App", user_id="u1"))
    return "P-8"


class _FakeProvider:
    """mock provider (零真实 LLM; LLM 输出注入, 捕获 request 供断言)。

    生产 provider = DeepSeek v4-pro (S8-001 约束); 测试一律注入本 mock —
    mock 当测试输入, 不当能力证明 (能力证明 = S8-005 真实 v4-pro)。
    """

    provider_id = "s8-fake"

    def __init__(self, content: str = "", *, error: str = ""):
        self._content = content
        self._error = error
        self.calls: list = []
        self.last_request = None

    def generate(self, request):
        self.calls.append(request)
        self.last_request = request
        from exec.provider import ProviderResponse

        if self._error:
            return ProviderResponse(content="", error=self._error)
        return ProviderResponse(content=self._content)


@pytest.fixture
def pm_mock_provider():
    """mock provider 工厂 (返回 _FakeProvider 实例, 调用方注入 LLM 输出)。"""

    def make(content: str = "", *, error: str = "") -> _FakeProvider:
        return _FakeProvider(content, error=error)

    return make
