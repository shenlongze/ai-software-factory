"""tests/console/test_console_s10_runtime.py — S10-002 Factory Runtime API 测试。

覆盖 (docs/sprint10/api-data-model.md §3-4 + workspace-architecture.md §6;
Adapter 层, 零 Core 修改 — 只消费 org.* 查询 + events 流):
- GET /api/projects/{id}/workflow:
  - 真实 workflow 200 (8 阶段链/template/is_mock=False)
  - mock fallback: 项目存在但无运行数据 → 200 is_mock=True (形状对齐
    workspace mock: Product→UX/UI→Architecture→Code→Test→Release)
  - 项目不存在 → 404 (mock 只兜底数据缺失, 不兜底不存在)
- GET /api/workflows/{id}/stages:
  - 200: 每阶段 status/agent_id(=role_id)/artifacts/duration_s/cost_usd
  - duration_s 从事件流推导 (stage_started → stage_completed 时间戳差)
  - cost_usd 未跟踪 → null (诚实; 仅 mock 带示例值)
  - 不存在 → 404
- GET /api/projects/{id}/timeline:
  - 五类节点聚合 (user/stage/artifact/review/error) + 关联维度提取
  - 审计事件 (console.viewed) 不进 Timeline (运行视图纯净)
  - 无事件 → [] / 项目不存在 → 404 / limit 截断
- SSE GET /api/events/stream:
  - 业务 7 类事件 (stage.started / stage.completed / artifact.created /
    approval.required / approval.completed / runtime.created /
    runtime.status.changed) + error 失败通道
  - since_seq 断点续推 / max_polls 停止 / 轮询可见新事件
  - 无事件库 → 单条 error (mock=True) 后关闭 (失败安全)
- RuntimeInstance 模型: 字段/默认值/类型校验 (Literal) / 状态流转
- 审计: runtime 端点命中 → console.viewed (view=project_workflow 等)

本目录自洽 (不跨目录依赖 helper): sys.path 挂 factory-core/factory-org/
factory-exec (同 tests/console/test_console_s9_org.py 装配); basename
全仓库唯一 (test_console_* 前缀)。事件构造用 Event.create + store.append
(确定性时间戳 — duration 断言不依赖真实时钟)。
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _pkg in ("factory-core", "factory-org", "factory-exec"):
    _dir = _ROOT / _pkg
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest

from events.models import Event, EventType
from org.projects import Project, ProjectStore
from org.workflow import WorkflowLifecycle

_console = importlib.import_module("factory-console")
_api = importlib.import_module("factory-console.api")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_models = importlib.import_module("factory-console.models")

try:
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)

# ------------------------------------------------------------------ fixtures


@pytest.fixture
def org_dir(tmp_path: Path) -> Path:
    """Org 数据空间 (与用户 ~/.factory 隔离)。"""
    return tmp_path / "factory" / "org"


@pytest.fixture
def project_store(org_dir: Path) -> ProjectStore:
    return ProjectStore(org_dir)


@pytest.fixture
def wlife(project_store: ProjectStore, event_logger) -> WorkflowLifecycle:
    """WorkflowLifecycle (logger 带事件库 — org.* 事件落库供 Runtime 消费)。"""
    return WorkflowLifecycle(project_store, logger=event_logger)


@pytest.fixture
def project_id(project_store: ProjectStore) -> str:
    project_store.save_project(Project(id="P-10", name="Ledger App", user_id="u1"))
    return "P-10"


@pytest.fixture
def service(wlife: WorkflowLifecycle, project_store: ProjectStore) -> Any:
    """ConsoleService (注入真实 org 装配 — S10-002 走真实数据空间)。"""
    return _console.ConsoleService(project_store=project_store, workflow_lifecycle=wlife)


@pytest.fixture
def client(service, event_logger):
    """真实服务 + EventLogger 的 TestClient (HTTP 集成断言)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ 构造辅助 (本目录自洽)


def build_chain_wf(wlife: WorkflowLifecycle, project_id: str, *, approval: bool = False):
    """5 阶段链 (product-manager→architect→developer→tester→devops)。"""
    wf = wlife.create_workflow(project_id, "S10-002 Chain")
    for role_id in ("product-manager", "architect", "developer", "tester", "devops"):
        wlife.create_stage(
            wf.id, role_id, name=f"{role_id} stage", approval_required=approval
        )
    return wf


def mark_completed(wlife: WorkflowLifecycle, stage_id: str) -> None:
    """PENDING → READY → RUNNING → COMPLETED (受控转换表合法路径)。"""
    wlife.transition_stage(stage_id, "ready")
    wlife.transition_stage(stage_id, "running")
    wlife.transition_stage(stage_id, "completed")


def append_event(
    event_logger,
    type_: EventType | str,
    project_id: str,
    *,
    payload: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
    result: str = "OK",
) -> Event:
    """确定性事件入流 (Event.create + store.append; 可指定时间戳)。"""
    event = Event.create(
        type_,
        source="org",
        project_id=project_id,
        stage="x",
        action="x",
        result=result,
        payload=payload or {},
    )
    if timestamp is not None:
        event = event.model_copy(update={"timestamp": timestamp})
    return event_logger.store.append(event)


def parse_sse(lines: list[str]) -> list[dict[str, Any]]:
    """SSE 文本块 → [{name, data}] (event:/data: 块解析)。"""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in lines:
        if line.startswith("event: "):
            current["name"] = line[len("event: ") :]
        elif line.startswith("data: "):
            current["data"] = json.loads(line[len("data: ") :])
        elif line == "" and current:
            out.append(current)
            current = {}
    return out


class _StubLogger:
    """iter_sse_events 纯函数测试用 logger (带 store + 空 record)。"""

    def __init__(self, store: Any):
        self.store = store

    def record(self, *args: Any, **kwargs: Any) -> None:
        return None


class _BatchedStore:
    """轮询测试用假 store: 每次 query 返回一个批次 (记录调用参数)。"""

    def __init__(self, batches: list[list[Event]]):
        self._batches = list(batches)
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> list[Event]:
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._batches) - 1)
        return self._batches[index]


# ------------------------------------------------------------------ GET /projects/{id}/workflow


class TestProjectWorkflowEndpoint:
    def test_workflow_200_real_detail(self, client, wlife, project_id):
        """真实 workflow: 200 + 阶段链/template + is_mock=False。"""
        wf = build_chain_wf(wlife, project_id)
        resp = client.get(f"/api/projects/{project_id}/workflow")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == wf.id
        assert body["is_mock"] is False
        assert body["project_id"] == project_id
        assert [s["role_id"] for s in body["stages"]] == [
            "product-manager", "architect", "developer", "tester", "devops",
        ]
        assert body["template"][:4] == ["Idea", "PM", "Product", "UX/UI"]

    def test_workflow_mock_fallback_when_project_without_run(
        self, client, wlife, project_id
    ):
        """项目存在但无 workflow → 200 mock (is_mock=True, 形状对齐 workspace)。"""
        # 建第二个项目 (无任何 workflow 运行数据)
        wlife.store.save_project(Project(id="P-11", name="No Run", user_id="u1"))
        resp = client.get("/api/projects/P-11/workflow")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_mock"] is True
        assert body["project_name"] == "No Run"
        # 形状对齐前端 mock/workspace.ts MOCK_PROJECTS (6 阶段链 + 待审核挡板)
        assert [s["name"] for s in body["stages"]] == [
            "Product", "UX/UI", "Architecture", "Code", "Test", "Release",
        ]
        assert [s["status"] for s in body["stages"]] == [
            "completed", "completed", "waiting_review", "pending", "pending", "pending",
        ]
        assert body["pending_approvals"][0]["stage_id"] == "mock-architect"
        assert body["stages"][0]["artifact"]["type"] == "product"

    def test_workflow_unknown_project_404(self, client):
        """项目不存在 → 404 (mock 只兜底数据缺失, 不兜底不存在)。"""
        resp = client.get("/api/projects/nope/workflow")
        assert resp.status_code == 404

    def test_workflow_service_none_without_org(self):
        """无 org 装配 → service 返回 None (HTTP 层 404 语义)。"""
        assert _console.ConsoleService().get_project_workflow("P-1") is None
        assert _console.ConsoleService().project_exists("P-1") is False


# ------------------------------------------------------------------ GET /workflows/{id}/stages


class TestWorkflowStagesEndpoint:
    def test_stages_200_fields(self, client, wlife, project_id):
        """阶段运行明细: status/agent_id/artifacts/cost_usd 字段一次装配。"""
        wf = build_chain_wf(wlife, project_id)
        stage = wlife.list_stages(wf.id)[0]
        artifact = wlife.registry.create(
            stage_id=stage.id, type_="prd", project_id=project_id,
            ref="file:///docs/prd.json", producer_role=stage.role_id,
        )
        updated = stage.model_copy(update={"artifact_ref": artifact.id})
        wlife.store.save_stage(updated)

        resp = client.get(f"/api/workflows/{wf.id}/stages")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 5
        first = runs[0]
        assert first["status"] == "pending"
        assert first["agent_id"] == "product-manager"  # org 无独立 Agent — 角色即执行者
        assert first["role_id"] == "product-manager"
        assert first["artifacts"][0]["id"] == artifact.id
        assert first["artifacts"][0]["type"] == "prd"
        assert first["cost_usd"] is None  # org 未跟踪成本 — 诚实 null

    def test_stages_duration_derived_from_events(
        self, client, wlife, project_id, event_logger
    ):
        """duration_s 从事件流推导 (stage_started → stage_completed 时间戳差)。"""
        wf = build_chain_wf(wlife, project_id)
        stage = wlife.list_stages(wf.id)[0]
        base = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"workflow_id": wf.id, "stage_id": stage.id,
                     "role_id": stage.role_id, "name": stage.name},
            timestamp=base,
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_COMPLETED, project_id,
            payload={"workflow_id": wf.id, "stage_id": stage.id,
                     "output_artifact_ids": []},
            timestamp=base + timedelta(seconds=12.5),
        )
        runs = client.get(f"/api/workflows/{wf.id}/stages").json()
        first = runs[0]
        assert first["duration_s"] == pytest.approx(12.5)
        assert first["started_at"] == "2026-08-10T12:00:00+00:00"
        assert first["completed_at"] == "2026-08-10T12:00:12.500000+00:00"

    def test_stages_duration_none_without_completed_event(
        self, client, wlife, project_id, event_logger
    ):
        """缺 completed 事件 → duration_s None (诚实不臆造)。"""
        wf = build_chain_wf(wlife, project_id)
        stage = wlife.list_stages(wf.id)[0]
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"workflow_id": wf.id, "stage_id": stage.id,
                     "role_id": stage.role_id},
        )
        runs = client.get(f"/api/workflows/{wf.id}/stages").json()
        assert runs[0]["duration_s"] is None

    def test_stages_404_unknown_workflow(self, client):
        resp = client.get("/api/workflows/nope/stages")
        assert resp.status_code == 404

    def test_stages_service_none_without_org(self):
        assert _console.ConsoleService().get_workflow_stage_runs("WF-1") is None


# ------------------------------------------------------------------ GET /projects/{id}/timeline


class TestTimelineEndpoint:
    def _seed_five_types(self, event_logger, project_id: str) -> list[str]:
        """五类事件 (user/stage/artifact/review/error) 入流 → 期望 type 序列。"""
        append_event(
            event_logger, EventType.ORG_PROJECT_CREATED, project_id,
            payload={"project_id": project_id, "name": "Ledger App"},
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"workflow_id": "WF-1", "project_id": project_id,
                     "stage_id": "STG-1", "role_id": "product-manager",
                     "name": "PM"},
        )
        append_event(
            event_logger, EventType.ORG_ARTIFACT_CREATED, project_id,
            payload={"artifact_id": "ART-1", "type": "prd",
                     "project_id": project_id},
        )
        append_event(
            event_logger, EventType.ORG_APPROVAL_CREATED, project_id,
            payload={"gate_id": "GATE-1", "stage_id": "STG-1",
                     "workflow_id": "WF-1", "project_id": project_id},
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_FAILED, project_id,
            payload={"workflow_id": "WF-1", "project_id": project_id,
                     "stage_id": "STG-2", "reason": "executor error"},
            result="FAIL",
        )
        return ["user", "stage", "artifact", "review", "error"]

    def test_timeline_aggregates_five_types(self, client, event_logger, project_id):
        """Timeline 聚合: user/stage/artifact/review/error 五类 + 关联维度。"""
        expected = self._seed_five_types(event_logger, project_id)
        resp = client.get(f"/api/projects/{project_id}/timeline")
        assert resp.status_code == 200
        body = resp.json()
        assert [e["type"] for e in body] == expected
        by_type = {e["type"]: e for e in body}
        assert by_type["stage"]["stage_id"] == "STG-1"
        assert by_type["stage"]["agent_id"] == "product-manager"
        assert by_type["artifact"]["artifact_id"] == "ART-1"
        assert by_type["review"]["gate_id"] == "GATE-1"
        assert by_type["error"]["status"] == "FAIL"
        assert "executor error" in by_type["error"]["message"]
        assert by_type["user"]["event_type"] == "org.project.created"
        assert [e["seq"] for e in body] == sorted(e["seq"] for e in body)

    def test_timeline_skips_audit_events(self, client, event_logger, project_id):
        """console.viewed 等审计事件不进 Timeline (运行视图纯净)。"""
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"stage_id": "STG-1"},
        )
        event_logger.record(
            EventType.CONSOLE_VIEWED, source="console", project_id=project_id,
            stage="viewed", action="view console dashboard", result="OK",
            payload={"view": "dashboard"},
        )
        body = client.get(f"/api/projects/{project_id}/timeline").json()
        assert len(body) == 1
        assert body[0]["event_type"] == "org.workflow.stage_started"

    def test_timeline_empty_when_no_events(self, client, project_id):
        """项目存在但无事件 → [] (诚实空态, 前端空态展示)。"""
        resp = client.get(f"/api/projects/{project_id}/timeline")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_timeline_unknown_project_404(self, client):
        assert client.get("/api/projects/nope/timeline").status_code == 404

    def test_timeline_limit_truncates(self, client, event_logger, project_id):
        """limit 截断 (取最近 N 条)。"""
        for _ in range(3):
            append_event(
                event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
                payload={"stage_id": f"STG-{_}"},
            )
        body = client.get(
            f"/api/projects/{project_id}/timeline?limit=2"
        ).json()
        assert len(body) == 2
        assert body[-1]["stage_id"] == "STG-2"


# ------------------------------------------------------------------ SSE /api/events/stream


class TestSseEndpoint:
    def _seed_sse_events(self, event_logger, project_id: str, wf_id: str) -> None:
        """stage.started / stage.completed / artifact.created /
        approval.required / error 五类事件入流。"""
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"workflow_id": wf_id, "project_id": project_id,
                     "stage_id": "STG-1", "role_id": "product-manager",
                     "name": "PM"},
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_COMPLETED, project_id,
            payload={"workflow_id": wf_id, "project_id": project_id,
                     "stage_id": "STG-1", "role_id": "product-manager",
                     "name": "PM", "output_artifact_ids": ["ART-1"]},
        )
        append_event(
            event_logger, EventType.ORG_ARTIFACT_CREATED, project_id,
            payload={"artifact_id": "ART-1", "type": "prd", "project_id": project_id},
        )
        append_event(
            event_logger, EventType.ORG_APPROVAL_CREATED, project_id,
            payload={"gate_id": "GATE-1", "stage_id": "STG-1",
                     "workflow_id": wf_id, "project_id": project_id},
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_FAILED, project_id,
            payload={"workflow_id": wf_id, "project_id": project_id,
                     "stage_id": "STG-2", "reason": "executor error"},
            result="FAIL",
        )

    @requires_fastapi
    def test_sse_stream_five_event_names(self, client, event_logger, project_id):
        """SSE 流: 五类事件名 + data 契约 (event:/data: 块)。"""
        self._seed_sse_events(event_logger, project_id, "WF-1")
        with client.stream(
            "GET",
            f"/api/events/stream?project_id={project_id}&max_polls=1&poll_interval=0.05",
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            lines = list(resp.iter_lines())
        events = parse_sse(lines)
        assert [e["name"] for e in events] == [
            "stage.started", "stage.completed", "artifact.created",
            "approval.required", "error",
        ]
        by_name = {e["name"]: e["data"] for e in events}
        assert by_name["stage.started"]["stage_id"] == "STG-1"
        assert by_name["stage.started"]["agent_id"] == "product-manager"
        assert by_name["stage.completed"]["artifact_id"] == "ART-1"
        assert by_name["stage.completed"]["cost_usd"] is None
        assert by_name["artifact.created"]["type"] == "prd"
        assert by_name["approval.required"]["gate_id"] == "GATE-1"
        assert by_name["error"]["reason"] == "executor error"

    @requires_fastapi
    def test_sse_content_type_and_headers(self, client, event_logger, project_id):
        """SSE 响应头 (text/event-stream + no-cache)。"""
        with client.stream(
            "GET", f"/api/events/stream?project_id={project_id}&max_polls=1"
        ) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["cache-control"] == "no-cache"

    @requires_fastapi
    def test_sse_store_unavailable_error_mock(self, service, project_id):
        """无事件库 → 单条 error (mock=True) 后关闭 (失败安全)。"""
        app = _adapter.build_app(service)  # 不注入 event_logger
        with TestClient(app) as c:
            with c.stream(
                "GET",
                f"/api/events/stream?project_id={project_id}&max_polls=1",
            ) as resp:
                assert resp.status_code == 200
                lines = list(resp.iter_lines())
        events = parse_sse(lines)
        assert len(events) == 1
        assert events[0]["name"] == "error"
        assert events[0]["data"]["mock"] is True
        assert "unavailable" in events[0]["data"]["reason"]

    @requires_fastapi
    def test_sse_since_seq_resume_http(self, client, event_logger, project_id):
        """since_seq 断点续推 (只推新事件)。"""
        self._seed_sse_events(event_logger, project_id, "WF-1")
        all_seqs = [e.seq for e in event_logger.store.query(project_id=project_id)]
        resume_from = max(all_seqs) - 1
        with client.stream(
            "GET",
            f"/api/events/stream?project_id={project_id}&since_seq={resume_from}"
            f"&max_polls=1&poll_interval=0.05",
        ) as resp:
            lines = list(resp.iter_lines())
        events = parse_sse(lines)
        assert len(events) == 1  # 只推最后一条 (error)
        assert events[0]["name"] == "error"


# ------------------------------------------------------------------ iter_sse_events 纯函数


class TestIterSseEvents:
    def test_pure_mapping_and_skip_unknown(self, event_logger, project_id):
        """纯函数: org 事件 → (name, data); 未知类型跳过。"""
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"stage_id": "S1", "role_id": "pm", "name": "PM"},
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_READY, project_id,
            payload={"stage_id": "S1", "role_id": "pm"},
        )  # stage_ready 不在 SSE 映射 → 跳过
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=event_logger,
                max_polls=1,
                poll_interval=0.01,
            )
        )
        assert [(name, data["stage_id"]) for name, data in out] == [
            ("stage.started", "S1"),
        ]

    def test_pure_since_seq_and_max_polls(self, event_logger, project_id):
        """since_seq 传给 store; max_polls 停止轮询。"""
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"stage_id": "S1", "role_id": "pm"},
        )
        first_seq = event_logger.store.query(project_id=project_id)[0].seq
        fake = _BatchedStore([
            event_logger.store.query(project_id=project_id),
            [],
        ])
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(fake),
                since_seq=0,
                max_polls=2,
                poll_interval=0.01,
            )
        )
        assert [name for name, _ in out] == ["stage.started"]
        assert fake.calls[0]["since_seq"] == 0
        assert fake.calls[1]["since_seq"] == first_seq  # 上轮尾 seq → 断点续推

    def test_pure_polls_for_new_events(self, event_logger, project_id):
        """轮询可见新事件 (首轮空 → 次轮新事件入流)。"""
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"stage_id": "S1", "role_id": "pm"},
        )
        fresh = [event_logger.store.query(project_id=project_id)[0]]
        fake = _BatchedStore([[], fresh])
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(fake),
                max_polls=2,
                poll_interval=0.01,
            )
        )
        assert [name for name, _ in out] == ["stage.started"]

    def test_pure_no_store_error_event(self):
        """logger=None → 单条 error (mock=True) 后结束。"""
        out = list(
            _api.iter_sse_events(_console.ConsoleService(), "P-1", max_polls=3)
        )
        assert len(out) == 1
        assert out[0][0] == "error"
        assert out[0][1]["mock"] is True

    def test_pure_store_error_failsafe(self, project_id):
        """store.query 异常 → error (mock=True) 后结束 (失败安全)。"""

        class _BrokenStore:
            def query(self, **kwargs: Any) -> list[Event]:
                raise RuntimeError("db locked")

        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(_BrokenStore()),
                max_polls=2,
            )
        )
        assert out[0][0] == "error"
        assert out[0][1]["mock"] is True

    def test_pure_stage_completed_duration(self, event_logger, project_id):
        """stage.completed → duration_s (与最近 stage_started 时间戳差)。"""
        base = datetime(2026, 8, 10, 9, 0, 0, tzinfo=timezone.utc)
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_STARTED, project_id,
            payload={"stage_id": "S1", "role_id": "pm", "name": "PM"},
            timestamp=base,
        )
        append_event(
            event_logger, EventType.ORG_WORKFLOW_STAGE_COMPLETED, project_id,
            payload={"stage_id": "S1", "role_id": "pm",
                     "output_artifact_ids": ["A1"]},
            timestamp=base + timedelta(seconds=8),
        )
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=event_logger,
                max_polls=1,
            )
        )
        names = {name for name, _ in out}
        assert "stage.started" in names
        completed = next(data for name, data in out if name == "stage.completed")
        assert completed["artifact_id"] == "A1"
        assert completed["duration_s"] == pytest.approx(8.0)
        assert completed["cost_usd"] is None


# ------------------------------------------------------------------ S10-002: runtime.* SSE 契约 + RuntimeInstance 模型


class TestRuntimeSseContract:
    """runtime.created / runtime.status.changed 事件契约 (S10-004 发射点)。

    契约先行: org.runtime.* 事件类型尚无 EventType 枚举成员 (发射点在
    S10-004 Runtime 服务, 依 ADR-0001 扩展路径届时加枚举即可) — 本组测试
    用 SimpleNamespace 假事件 (type 为字符串) 锁定 SSE 映射与 data 形状,
    与 SSE_EVENT_MAP / 前端 RUNTIME_EVENT_NAMES 三方对齐。
    """

    @staticmethod
    def _runtime_event(type_: str, payload: dict[str, Any], seq: int = 1):
        return SimpleNamespace(
            type=SimpleNamespace(value=type_),
            payload=payload,
            agent_id=None,
            seq=seq,
            project_id="P-10",
            timestamp=None,
        )

    def test_sse_map_has_runtime_events(self):
        """SSE_EVENT_MAP 含 runtime.created / runtime.status.changed。"""
        assert _api.SSE_EVENT_MAP["org.runtime.created"] == "runtime.created"
        assert (
            _api.SSE_EVENT_MAP["org.runtime.status_changed"]
            == "runtime.status.changed"
        )

    def test_sse_map_has_approval_completed(self):
        """SSE_EVENT_MAP 含 approval.completed (业务 7 类之一)。"""
        assert _api.SSE_EVENT_MAP["org.approval.approved"] == "approval.completed"

    def test_approval_completed_mapping(self, event_logger, project_id):
        """org.approval.approved → approval.completed (stage_id/gate_id)。"""
        fake = _BatchedStore([
            [
                self._runtime_event(
                    "org.approval.approved",
                    {"gate_id": "GATE-1", "stage_id": "STG-1",
                     "workflow_id": "WF-1"},
                )
            ]
        ])
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(fake),
                max_polls=1,
            )
        )
        assert out[0][0] == "approval.completed"
        assert out[0][1] == {
            "stage_id": "STG-1",
            "gate_id": "GATE-1",
            "workflow_id": "WF-1",
        }

    def test_runtime_created_mapping(self, event_logger, project_id):
        """org.runtime.created → runtime.created (instance/type/status/artifact)。"""
        fake = _BatchedStore([
            [
                self._runtime_event(
                    "org.runtime.created",
                    {
                        "instance_id": "RT-1",
                        "type": "browser",
                        "status": "starting",
                        "artifact_id": "ART-9",
                    },
                )
            ]
        ])
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(fake),
                max_polls=1,
            )
        )
        assert [(name, data) for name, data in out] == [
            (
                "runtime.created",
                {
                    "instance_id": "RT-1",
                    "type": "browser",
                    "status": "starting",
                    "artifact_id": "ART-9",
                    "project_id": project_id,  # payload 缺省 → 事件级 project_id
                },
            ),
        ]

    def test_runtime_status_changed_mapping(self, event_logger, project_id):
        """org.runtime.status_changed → runtime.status.changed (状态流转)。"""
        fake = _BatchedStore([
            [
                self._runtime_event(
                    "org.runtime.status_changed",
                    {
                        "instance_id": "RT-1",
                        "status": "running",
                        "previous_status": "starting",
                    },
                    seq=2,
                )
            ]
        ])
        out = list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=_StubLogger(fake),
                max_polls=1,
            )
        )
        assert out[0][0] == "runtime.status.changed"
        assert out[0][1] == {
            "instance_id": "RT-1",
            "status": "running",
            "previous_status": "starting",
        }

    def test_runtime_instance_model_contract(self):
        """RuntimeInstance 模型: 字段/默认值/to_dict (与前端 types.ts 对齐)。"""
        inst = _models.RuntimeInstance(
            id="RT-1", project_id="P-10", type="browser"
        )
        d = inst.to_dict()
        assert d["id"] == "RT-1"
        assert d["project_id"] == "P-10"
        assert d["type"] == "browser"
        assert d["status"] == "starting"  # 默认 starting (生命周期入口)
        assert d["artifact_id"] is None
        assert d["url"] is None
        assert d["session"] is None
        assert d["created_at"] is None
        # terminal 实例: session 而非 url
        term = _models.RuntimeInstance(
            id="RT-2",
            project_id="P-10",
            type="terminal",
            status="running",
            session="term-42",
        )
        assert term.to_dict()["session"] == "term-42"
        assert term.to_dict()["url"] is None


class TestRuntimeInstanceModel:
    """RuntimeInstance 模型: 状态默认/类型校验 (Literal)/CRUD 语义。

    只建模型 (S10-002), 不实现 Browser/Terminal — 实例创建/生命周期/
    截图由 S10-004 Runtime 服务实现; 本组测试锁定模型契约 (字段/默认值/
    校验/序列化), 前端 types.ts RuntimeInstance 同形状。
    """

    def test_status_defaults_to_starting(self):
        """status 默认 starting (生命周期入口), 不臆造 running。"""
        inst = _models.RuntimeInstance(id="RT-1", project_id="P-10")
        assert inst.status == "starting"
        assert inst.to_dict()["status"] == "starting"

    def test_type_defaults_to_browser(self):
        """type 默认 browser (唯一默认实例类型)。"""
        inst = _models.RuntimeInstance(id="RT-1", project_id="P-10")
        assert inst.type == "browser"

    def test_status_literal_rejects_unknown(self):
        """status 只接受 starting|running|stopped|error (Literal 校验)。"""
        for bad in ("ready", "paused", "destroyed", ""):
            with pytest.raises(Exception) as exc:
                _models.RuntimeInstance(id="RT-1", project_id="P-10", status=bad)
            assert "status" in str(exc.value) or "Literal" in str(exc.value)

    def test_type_literal_rejects_unknown(self):
        """type 只接受 browser|terminal (Literal 校验)。"""
        for bad in ("docker", "vm", "sandbox", ""):
            with pytest.raises(Exception) as exc:
                _models.RuntimeInstance(id="RT-1", project_id="P-10", type=bad)
            assert "type" in str(exc.value) or "Literal" in str(exc.value)

    def test_create_browser_with_url_and_artifact(self):
        """browser 实例: url + artifact_id 绑定 (预览对应产物)。"""
        inst = _models.RuntimeInstance(
            id="RT-1",
            project_id="P-10",
            type="browser",
            status="running",
            url="http://localhost:5173/preview/RT-1",
            artifact_id="ART-9",
            created_at="2026-08-10T09:00:00+00:00",
        )
        d = inst.to_dict()
        assert d["url"] == "http://localhost:5173/preview/RT-1"
        assert d["artifact_id"] == "ART-9"
        assert d["created_at"] == "2026-08-10T09:00:00+00:00"
        assert d["session"] is None  # browser 不携带 session

    def test_all_status_values_accepted(self):
        """四种合法 status 均可构造 (状态机全状态)。"""
        for status in ("starting", "running", "stopped", "error"):
            inst = _models.RuntimeInstance(
                id="RT-1", project_id="P-10", status=status  # type: ignore[arg-type]
            )
            assert inst.status == status

    def test_roundtrip_to_dict_json(self):
        """to_dict (json 模式) 可往返 — 前端/CLI --json 消费契约。"""
        import json as _json

        inst = _models.RuntimeInstance(
            id="RT-1",
            project_id="P-10",
            type="terminal",
            status="running",
            session="term-42",
            created_at="2026-08-10T09:00:00+00:00",
        )
        raw = _json.dumps(inst.to_dict())
        restored = _models.RuntimeInstance.model_validate(_json.loads(raw))
        assert restored.id == "RT-1"
        assert restored.session == "term-42"
        assert restored.status == "running"

    def test_copy_update_status_transition(self):
        """CRUD-U 语义: model_copy 状态流转 (starting→running→stopped)。"""
        inst = _models.RuntimeInstance(id="RT-1", project_id="P-10")
        running = inst.model_copy(update={"status": "running", "url": "http://x"})
        assert running.status == "running"
        stopped = running.model_copy(update={"status": "stopped"})
        assert stopped.status == "stopped"
        assert inst.status == "starting"  # 原对象不变 (不可变语义)


# ------------------------------------------------------------------ 审计


class TestRuntimeAudit:
    @requires_fastapi
    def test_runtime_endpoints_audited(
        self, client, event_logger, event_store, wlife, project_id
    ):
        """runtime 端点命中 → console.viewed (view=project_workflow 等)。"""
        build_chain_wf(wlife, project_id)
        client.get(f"/api/projects/{project_id}/workflow")
        client.get(f"/api/projects/{project_id}/timeline")
        views = {
            event.payload.get("view")
            for event in event_store.query()
            if event.type == EventType.CONSOLE_VIEWED
        }
        assert {"project_workflow", "project_timeline"} <= views

    def test_sse_connect_audited(self, event_logger, project_id, event_store):
        """SSE 连接 → console.viewed (view=events_stream)。"""
        list(
            _api.iter_sse_events(
                _console.ConsoleService(),
                project_id,
                logger=event_logger,
                max_polls=1,
            )
        )
        views = {
            event.payload.get("view")
            for event in event_store.query()
            if event.type == EventType.CONSOLE_VIEWED
        }
        assert "events_stream" in views
