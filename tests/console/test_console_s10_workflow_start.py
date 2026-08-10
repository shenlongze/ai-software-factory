"""tests/console/test_console_s10_workflow_start.py — POST start/chat + GET run-status (S10-006.5 P1-A)。

覆盖 (factory-console/api/workflow_start.py + web/backend/fastapi_adapter.py +
workflow_runner.py — 真实装配, 假链注入):
- POST /api/projects/{id}/start → 200 {status:"started", project_id, run_id} (monkeypatch
  注入假链 — 零 LLM, 走真实 org 编排写事件/产物/进度; run_async=False 同步可断言)
- 404: 项目不存在 (start/chat/run-status 三端点)
- 409: 已有运行 (阻塞假链 + run_async=True → 诚实拒绝重复启动)
- 503: LLM key 缺失 (has_llm_key hermetic patch — 绝不依赖真实 key)
- POST /api/projects/{id}/chat → 400 空消息; 未启动 → idea 更新 + 触发 start
  ({status:"started"}) + 消息落库; 已启动 → 只记录 ({status:"recorded"}, 不重复启动)
- GET /api/projects/{id}/run-status → none (未启动) / running+pending (阻塞链) /
  completed+stages/totals (假链跑完)
- 事件可读: 假链写 org.* 事件后 GET /api/projects/{id}/timeline 出现 stage/artifact 节点
  (与 Timeline 同 events.db — 真实事件, 非伪造)

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_project_create.py 同模式)。
"""

from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

# factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_ws = importlib.import_module("factory-console.api.workflow_start")
_runner = importlib.import_module("factory-console.workflow_runner")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


# ------------------------------------------------------------------ 假链 (零 LLM, 真实 org 编排)


def make_fake_chain(**kwargs: object) -> dict[str, object]:
    """假链: 零 LLM, 走真实 org 编排 — workflow/stage/artifact + stage 事件 + 进度 JSON。

    与真实链同数据通路 (WorkflowLifecycle/ArtifactRegistry/EventLogger/Recorder),
    只不调 LLM: Timeline 的 stage/artifact 节点与 run-status 的 stages/totals
    全部来自真实落库数据 (非 mock 证明)。
    """
    wf_lifecycle = kwargs["wf_lifecycle"]
    logger = kwargs["logger"]
    project_id = str(kwargs["project_id"])
    idea = str(kwargs["idea"])
    run_id = str(kwargs["run_id"])
    runs_dir = Path(kwargs["runs_dir"])

    wf = wf_lifecycle.create_workflow(
        project_id, f"假链 WF [{run_id}]", workflow_id=f"WF-{run_id}"
    )
    stage = wf_lifecycle.create_stage(
        wf.id, "product-manager", name="product", stage_id=f"STG-{run_id}-PM"
    )
    art = wf_lifecycle.registry.create(
        stage_id=stage.id,
        type_="product",
        project_id=project_id,
        ref="file:///prd.md",
        producer_role="product-manager",
        metadata={"idea": idea, "title": f"{idea} PRD"},
        artifact_id=f"{project_id}-{run_id}-PRODUCT",
    )
    wf_lifecycle.registry.mark_generated(art.id)

    # stage 流转事件 (Timeline stage 节点数据源; 与真实链同事件类型)
    logger.record(
        "org.workflow.stage_started",
        source="fake-chain",
        project_id=project_id,
        stage=stage.id,
        payload={"stage_id": stage.id, "name": "product", "role_id": "product-manager"},
    )
    logger.record(
        "org.workflow.stage_completed",
        source="fake-chain",
        project_id=project_id,
        stage=stage.id,
        payload={
            "stage_id": stage.id,
            "name": "product",
            "role_id": "product-manager",
            "output_artifact_ids": [art.id],
        },
    )
    wf_lifecycle.activate(wf.id)
    wf_lifecycle.transition_workflow(wf.id, "completed")

    # 进度 JSON (run-status stages/totals — 与真实链同 Recorder/布局)
    recorder = _runner.Recorder(progress_path=runs_dir / project_id / run_id / "progress.json")
    recorder.stage("WF-TEST", "product", "product-manager")
    recorder.stage_done("COMPLETED", "fake chain ok")
    recorder._write_progress()  # 落盘 progress.json (run-status 读 updated_at/stages)
    return {
        "status": "completed",
        "stages": recorder.stages,
        "totals": recorder.totals(),
        "errors": recorder.errors,
    }


def _blocking_chain_factory(entered: threading.Event, release: threading.Event):
    """阻塞假链工厂 (409/pending 测试: run_async=True, 线程卡在 release.wait)。"""

    def chain(**kwargs: object) -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=15), "blocking chain release timeout"
        return {"status": "completed", "stages": [], "totals": {}, "errors": []}

    return chain


# ------------------------------------------------------------------ HTTP 层假链注入 (monkeypatch 路由模块导入的符号)


class _FakeChainConfig:
    """可配置假链旋钮 (chain_factory/run_async/start 调用计数 — 测试断言用)。"""

    chain_factory: object = None
    run_async: bool = False
    start_calls: int = 0


def _wrapped_start(**kw: object) -> dict[str, object]:
    """路由层 start 包装: 注入假链 + 同步/异步旋钮 (测试用; 生产零影响)。"""
    _FakeChainConfig.start_calls += 1
    kw["chain_factory"] = _FakeChainConfig.chain_factory
    kw["run_async"] = _FakeChainConfig.run_async
    return _runner.start_project_workflow(**kw)


@pytest.fixture
def fake_start(monkeypatch: pytest.MonkeyPatch) -> _FakeChainConfig:
    """HTTP 层假链注入: monkeypatch 路由模块导入的 start_project_workflow 符号 +
    hermetic key (绝不依赖真实 ~/.hermes/.env key 存在)。"""
    _FakeChainConfig.chain_factory = make_fake_chain
    _FakeChainConfig.run_async = False
    _FakeChainConfig.start_calls = 0
    monkeypatch.setattr(_ws, "start_project_workflow", _wrapped_start)
    monkeypatch.setattr(_runner, "has_llm_key", lambda: True)
    return _FakeChainConfig


def _wait_run_finished(project_id: str, timeout_s: float = 8.0) -> None:
    """等后台线程结束 (_RUNNING 清空 — 防模块级状态泄漏污染后续测试)。"""
    deadline = time.monotonic() + timeout_s
    while _runner.is_project_running(project_id) and time.monotonic() < deadline:
        time.sleep(0.05)


@requires_fastapi
class TestWorkflowStartHttp:
    """POST start / chat + GET run-status 端点 (真实装配 TestClient)。"""

    @pytest.fixture
    def client(self, factory_root: Path, event_logger):
        """真实装配 (build_console_service → org ProjectStore + ConversationStore
        落盘 factory_root; event_logger 事件库与 Timeline 同源)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        app = _adapter.build_app(service, event_logger=event_logger)
        with TestClient(app) as c:
            yield c

    def _create_project(self, client, idea: str = "开发一个记账 App") -> str:
        resp = client.post("/api/projects", json={"idea": idea})
        assert resp.status_code == 201, resp.text
        return resp.json()["project_id"]

    # ------------------------------------------------------------- start

    def test_start_200_started(self, client, fake_start):
        """POST start (假链同步) → 200 {status: started, project_id, run_id}。"""
        pid = self._create_project(client)
        resp = client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["project_id"] == pid
        assert body["run_id"].startswith("R")

    def test_start_404_unknown_project(self, client, fake_start):
        """start 项目不存在 → 404 (诚实: 不存在不假装启动)。"""
        resp = client.post("/api/projects/P-NOT-EXIST/start")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_start_409_duplicate_while_running(self, client, fake_start):
        """重复启动: 已有运行中的 workflow → 409 (诚实拒绝; 阻塞链 run_async=True)。"""
        entered, release = threading.Event(), threading.Event()
        fake_start.run_async = True
        fake_start.chain_factory = _blocking_chain_factory(entered, release)
        pid = self._create_project(client)
        try:
            first = client.post(f"/api/projects/{pid}/start")
            assert first.status_code == 200
            assert entered.wait(timeout=5), "blocking chain not entered"
            second = client.post(f"/api/projects/{pid}/start")
            assert second.status_code == 409
            assert "already running" in second.json()["detail"]
        finally:
            release.set()
            _wait_run_finished(pid)

    def test_start_503_no_llm_key(self, client, monkeypatch):
        """key 缺失 → 503 (hermetic: has_llm_key patch False — 不依赖真实环境)。"""
        monkeypatch.setattr(_runner, "has_llm_key", lambda: False)
        pid = self._create_project(client)
        resp = client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 503
        assert "key" in resp.json()["detail"].lower()

    # ------------------------------------------------------------- chat

    def test_chat_empty_400(self, client, fake_start):
        """chat 空消息 → 400 (空消息不发送)。"""
        pid = self._create_project(client)
        resp = client.post(f"/api/projects/{pid}/chat", json={"message": "   "})
        assert resp.status_code == 400
        assert "message is empty" in resp.json()["detail"]

    def test_chat_404_unknown_project(self, client, fake_start):
        """chat 项目不存在 → 404。"""
        resp = client.post(
            "/api/projects/P-NOT-EXIST/chat", json={"message": "加个暗色模式"}
        )
        assert resp.status_code == 404

    def test_chat_unstarted_updates_idea_and_starts(
        self, client, fake_start, factory_root: Path
    ):
        """chat 未启动 → idea 更新 (org Project.goal) + 触发 start + 消息落库。"""
        pid = self._create_project(client, idea="开发一个记账 App")
        resp = client.post(f"/api/projects/{pid}/chat", json={"message": "加个暗色模式"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["run_id"].startswith("R")
        assert body["recorded"] is True
        # idea 更新 (org Project.goal — 新 run 以此为新输入)
        service = _adapter.build_console_service(factory_root)
        assert service.project_idea(pid) == "加个暗色模式"
        # 消息落库 (chat.json — append-only)
        chat_path = Path(factory_root) / "chat.json"
        data = json.loads(chat_path.read_text(encoding="utf-8"))
        messages = data.get(pid, [])
        assert messages and messages[-1]["message"] == "加个暗色模式"

    def test_chat_running_recorded_no_restart(self, client, fake_start, monkeypatch):
        """chat 已启动 → 只记录消息 (recorded), 不重复触发 start。"""
        monkeypatch.setattr(_ws, "is_project_running", lambda project_id: True)
        pid = self._create_project(client)
        resp = client.post(f"/api/projects/{pid}/chat", json={"message": "继续优化"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "recorded"
        assert body["run_id"] is None
        assert body["recorded"] is True
        assert fake_start.start_calls == 0  # 已启动 → 不重复启动

    # ------------------------------------------------------------- run-status

    def test_run_status_none_before_start(self, client, fake_start):
        """run-status 未启动 → {status: none} (前端据此显示\"开始开发\"按钮)。"""
        pid = self._create_project(client)
        resp = client.get(f"/api/projects/{pid}/run-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == pid
        assert body["status"] == "none"
        assert body["runs"] == []

    def test_run_status_completed_with_progress(self, client, fake_start):
        """假链跑完 → {status: completed} + runs[0] 带 stages/totals (成本可见)。"""
        pid = self._create_project(client)
        started = client.post(f"/api/projects/{pid}/start")
        assert started.status_code == 200
        run_id = started.json()["run_id"]
        resp = client.get(f"/api/projects/{pid}/run-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["current_run_id"] == run_id
        assert body["runs"] and body["runs"][0]["run_id"] == run_id
        run = body["runs"][0]
        assert run["status"] == "completed"
        assert run["stages"] and run["stages"][0]["stage"] == "product"
        assert run["totals"]["calls"] == 0
        assert "total_tokens" in run["totals"]
        assert run["updated_at"] is not None

    def test_run_status_pending_while_running(
        self, client, fake_start, factory_root: Path
    ):
        """run 进行中 (report/progress 未落) → status=running, 该 run 显示 pending。"""
        entered, release = threading.Event(), threading.Event()
        fake_start.run_async = True
        fake_start.chain_factory = _blocking_chain_factory(entered, release)
        pid = self._create_project(client)
        try:
            started = client.post(f"/api/projects/{pid}/start")
            assert started.status_code == 200
            assert entered.wait(timeout=5), "blocking chain not entered"
            run_id = started.json()["run_id"]
            # 空 run 目录 → _read_run 失败安全 pending (真实布局: report 未落)
            run_dir = Path(factory_root) / "workflow_runs" / pid / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            resp = client.get(f"/api/projects/{pid}/run-status")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "running"
            assert body["runs"] and body["runs"][0]["status"] == "pending"
        finally:
            release.set()
            _wait_run_finished(pid)

    def test_run_status_404_unknown_project(self, client, fake_start):
        """run-status 项目不存在 → 404。"""
        resp = client.get("/api/projects/P-NOT-EXIST/run-status")
        assert resp.status_code == 404

    # ------------------------------------------------------------- 事件可读 (Timeline 同源)

    def test_timeline_stage_events_visible_after_start(self, client, fake_start):
        """假链写事件后 GET timeline → stage + artifact 节点 (与 Timeline 同 events.db)。"""
        pid = self._create_project(client)
        resp = client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 200
        timeline = client.get(f"/api/projects/{pid}/timeline")
        assert timeline.status_code == 200
        events = timeline.json()
        stage_events = [
            e
            for e in events
            if e["type"] == "stage"
            and e["event_type"] in ("org.workflow.stage_started", "org.workflow.stage_completed")
        ]
        assert stage_events, f"no stage events in timeline: {events}"
        assert stage_events[0]["stage_id"] is not None
        assert any(e["type"] == "artifact" for e in events), "artifact event missing"
        assert any(e["event_type"] == "org.workflow.completed" for e in events)


# ------------------------------------------------------------------ 路由函数层 (无 HTTP 依赖)


class TestWorkflowStartRouteFunctions:
    """workflow_start 路由函数语义 (直接调用, 无 HTTP 绑定)。"""

    def test_start_empty_idea_raises_value_error(self, factory_root: Path, event_logger):
        """start 项目 idea 为空 → ValueError (HTTP 层 400)。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("")
        assert summary is not None
        with pytest.raises(ValueError):
            _ws.start_project_workflow_route(
                service, summary.id, events_db_path=event_logger.store.db_path
            )

    def test_chat_empty_message_raises_value_error(
        self, factory_root: Path, event_logger
    ):
        """chat 空消息 → ValueError (HTTP 层 400); 消息不落库。"""
        service = _adapter.build_console_service(factory_root, event_logger=event_logger)
        summary = service.create_project("开发一个记账 App")
        assert summary is not None
        with pytest.raises(ValueError):
            _ws.chat_route(
                service, summary.id, "   ", events_db_path=event_logger.store.db_path
            )
        store = service.get_conversation_store()
        assert store is not None
        assert store.count(summary.id) == 0
