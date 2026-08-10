"""tests/console/test_console_s10_005.py — S10-005 Artifact Center (后端验收)。

覆盖 (Artifact Center 数据源 — 复用 S9-003 详情 API, 仅新增 content 端点):
- GET /api/artifacts/{id}/content: location 文件文本 (Code diff 兜底 / Release
  下载源); 文件缺失/越界/不可读 → content null (失败安全, 查看器以 metadata
  为主); 产物不存在 → 404; 无 org → 404
- 路径穿越防护: location 指向 org 目录外 → content null (绝不读越界文件)
- 审计: 命中端点 → console.viewed (view=artifact_content) 只读审计

本目录自洽 (不跨目录依赖 helper): sys.path 挂 factory-core/factory-org/
factory-exec (同 tests/s9 装配); basename 全仓库唯一 (test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _pkg in ("factory-core", "factory-org", "factory-exec"):
    _dir = _ROOT / _pkg
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest

from org.artifact import ArtifactType
from org.projects import Project, ProjectStore
from org.workflow import WorkflowLifecycle

_console = importlib.import_module("factory-console")
_models = importlib.import_module("factory-console.models")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)

# ------------------------------------------------------------------ fixtures (同 S9-003 自洽)


@pytest.fixture
def org_dir(tmp_path: Path) -> Path:
    """Org 数据空间 (与用户 ~/.factory 隔离)。"""
    return tmp_path / "factory" / "org"


@pytest.fixture
def project_store(org_dir: Path) -> ProjectStore:
    return ProjectStore(org_dir)


@pytest.fixture
def wlife(project_store: ProjectStore, event_logger) -> WorkflowLifecycle:
    """WorkflowLifecycle (logger 带事件库 — 审计断言)。"""
    return WorkflowLifecycle(project_store, logger=event_logger)


@pytest.fixture
def project_id(project_store: ProjectStore) -> str:
    project_store.save_project(Project(id="P-10", name="Artifact Center App", user_id="u1"))
    return "P-10"


@pytest.fixture
def service(wlife: WorkflowLifecycle, project_store: ProjectStore) -> _models.ConsoleService:
    """ConsoleService (注入真实 org 装配 — content 查询走真实数据空间)。"""
    return _console.ConsoleService(project_store=project_store, workflow_lifecycle=wlife)


@pytest.fixture
def client(service, event_logger):
    """真实服务 + EventLogger 的 TestClient (HTTP 集成断言)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ 构造辅助


def _make_artifact(
    wlife: WorkflowLifecycle,
    project_id: str,
    *,
    type_: ArtifactType = ArtifactType.CODE,
    location: str = "",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """产物 (默认 code 类型 — files/changes 契约载荷; location 可指向文件)。"""
    wf = wlife.create_workflow(project_id, "S10-005 Chain")
    wlife.create_stage(wf.id, "developer", name="developer stage", approval_required=False)
    stage = wlife.list_stages(wf.id)[0]
    return wlife.registry.create(
        stage_id=stage.id,
        type_=type_,
        project_id=project_id,
        ref="ref://artifact",
        producer_role=stage.role_id,
        location=location,
        metadata=metadata
        or {
            "files": ["src/app.py", "src/main.py"],
            "changes": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,3 @@\n+print('hi')",
        },
    )


# ------------------------------------------------------------------ content 端点 (service 层)


class TestArtifactContentService:
    def test_content_reads_location_file(self, service, wlife, project_id, org_dir):
        """location 指向存在的文本文件 → content 返回文件文本。"""
        payload_dir = org_dir / "artifacts"
        payload_dir.mkdir(parents=True, exist_ok=True)
        (payload_dir / "code.md").write_text("diff 内容:\n+新增行", encoding="utf-8")
        artifact = _make_artifact(wlife, project_id, location="artifacts/code.md")

        content = service.get_artifact_content(artifact.id)
        assert content is not None
        assert content.artifact_id == artifact.id
        assert content.type == "code"
        assert content.location == "artifacts/code.md"
        assert content.content == "diff 内容:\n+新增行"

    def test_content_null_when_file_missing(self, service, wlife, project_id):
        """location 指向不存在的文件 → content null (失败安全, 200 形状保留)。"""
        artifact = _make_artifact(wlife, project_id, location="artifacts/missing.md")
        content = service.get_artifact_content(artifact.id)
        assert content is not None
        assert content.content is None
        assert content.location == "artifacts/missing.md"

    def test_content_null_when_no_location(self, service, wlife, project_id):
        """location 为空 (metadata 已覆盖) → content null (不拖垮查看器)。"""
        artifact = _make_artifact(wlife, project_id)
        content = service.get_artifact_content(artifact.id)
        assert content is not None
        assert content.content is None
        assert content.location == ""

    def test_content_traversal_guard(self, service, wlife, project_id, org_dir):
        """路径穿越防护: location 指向 org 目录外 → content null (绝不读越界)。"""
        outside = org_dir.parent / "secret.txt"
        outside.write_text("机密", encoding="utf-8")
        artifact = _make_artifact(wlife, project_id, location="../secret.txt")

        content = service.get_artifact_content(artifact.id)
        assert content is not None
        assert content.content is None  # 越界被拒

    def test_content_missing_artifact_returns_none(self, service):
        """产物不存在 → None (HTTP 层映射 404)。"""
        assert service.get_artifact_content("nope") is None

    def test_content_unreadable_returns_null(self, service, wlife, project_id, org_dir):
        """目录伪装文件/不可读 → content null (失败安全)。"""
        payload_dir = org_dir / "artifacts"
        payload_dir.mkdir(parents=True, exist_ok=True)
        (payload_dir / "dir.md").mkdir()  # location 指向目录 → 非 file → null
        artifact = _make_artifact(wlife, project_id, location="artifacts/dir.md")
        assert service.get_artifact_content(artifact.id).content is None


# ------------------------------------------------------------------ content 端点 (HTTP)


@requires_fastapi
class TestArtifactContentHttp:
    def test_http_content_200_with_text(self, client, wlife, project_id, org_dir):
        """GET /api/artifacts/{id}/content → 200: location 文件文本。"""
        payload_dir = org_dir / "artifacts"
        payload_dir.mkdir(parents=True, exist_ok=True)
        (payload_dir / "release.md").write_text("v1.0.0 发布说明", encoding="utf-8")
        artifact = _make_artifact(
            wlife,
            project_id,
            type_=ArtifactType.RELEASE,
            location="artifacts/release.md",
            metadata={
                "version": "1.0.0",
                "build_result": {"status": "success", "command": "make build"},
                "package": {"name": "app.zip", "type": "zip", "files": ["app.js"]},
                "release_notes": "v1.0.0",
                "deployment": "nginx",
            },
        )
        resp = client.get(f"/api/artifacts/{artifact.id}/content")
        assert resp.status_code == 200
        body = resp.json()
        assert body["artifact_id"] == artifact.id
        assert body["type"] == "release"
        assert body["content"] == "v1.0.0 发布说明"

    def test_http_content_null_when_missing(self, client, wlife, project_id):
        """文件缺失 → 200 + content null (失败安全, 不 5xx)。"""
        artifact = _make_artifact(wlife, project_id, location="artifacts/nope.md")
        resp = client.get(f"/api/artifacts/{artifact.id}/content")
        assert resp.status_code == 200
        assert resp.json()["content"] is None

    def test_http_content_404(self, client):
        """产物不存在 → 404。"""
        assert client.get("/api/artifacts/nope/content").status_code == 404

    def test_http_content_audit_view(self, client, wlife, project_id, event_store):
        """命中 content 端点 → console.viewed (view=artifact_content) 只读审计。"""
        artifact = _make_artifact(wlife, project_id)
        client.get(f"/api/artifacts/{artifact.id}/content")
        views = [
            ev.payload.get("view")
            for ev in event_store.query_events(limit=50)
            if ev.type.value == "console.viewed" and ev.payload.get("view") == "artifact_content"
        ]
        assert views == ["artifact_content"]
