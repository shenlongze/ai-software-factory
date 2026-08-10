"""tests/console/test_console_lifecycle_acceptance.py — S10-009 Task 006 验收场景 (Migration + Acceptance)。

覆盖 (project-lifecycle.md §八/§九 验收场景 + S10-009-plan.md Task 6, 真实装配
端到端 — build_console_service → org ProjectStore + ProjectSpaceStore + 假链):

- 场景 1 (Draft + Discovery 持久化): POST /api/projects {idea} 无 name →
  unnamed-project-XXX (lifecycle=discovery, draft=true) + idea/ + discovery/
  目录存在; AI 提问 (discovery/answer 模拟) → 问答持久化 (conversation.json)
- 场景 2 (Confirm): 确认 "AI Note" → ai-note/ 目录 + CONFIRMED + 索引正确 +
  conversation/discovery 保留 (rename 后逐字节一致)
- 场景 3 (旧项目兼容): 预置旧项目 (仅 org/projects.json: P-OLD name="ScorePocket"
  lifecycle=idea) → list/get 读取正常 + 懒迁移 (list/get 首次访问 ensure_space
  回填目录镜像) + 既有 API (PATCH rename / DELETE / start 假链) 不破坏
- 场景 4 (index 重建): 删除 workspace/projects.json → 列表不受影响 (list 不依赖
  缓存) + 索引自愈 (get_slug 未命中重建) + rebuild_index 目录扫描恢复
- 全链回归: draft→answer→complete→confirm→start (workflow runner 假链 — 零 LLM,
  真实 org 编排写事件/产物) 整条用户旅程 + Timeline 事件可见

basename 全仓库唯一 (test_console_* 前缀); fastapi/httpx 未安装 → HTTP 类跳过
(与 test_console_project_confirm.py 同模式)。测试真实装配 (build_console_service
→ org ProjectStore + ProjectSpaceStore 落盘 factory_root)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_ORG = _ROOT / "factory-org"
if str(_FACTORY_ORG) not in sys.path:
    sys.path.insert(0, str(_FACTORY_ORG))

#: factory-console 包名含连字符 → importlib 加载 (同 tests/console 其余测试模式)
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


# ------------------------------------------------------------------ helpers


def _space_dir(factory_root: Path, project_id: str) -> Path:
    """项目空间目录 (workspace/projects/{slug} — 经 index 自愈查询)。"""
    from org.space import ProjectSpaceStore

    space = ProjectSpaceStore(factory_root)
    slug = space.get_slug(project_id)
    assert slug is not None, f"no space slug for project {project_id}"
    return space.space_dir(slug)


def _index_map(factory_root: Path) -> dict:
    """workspace/projects.json 索引 (id→slug)。"""
    from org.space import ProjectSpaceStore

    return ProjectSpaceStore(factory_root).list_index()


def _org_project(factory_root: Path, project_id: str):
    """org/projects.json 镜像记录。"""
    from org.projects import ProjectStore

    return ProjectStore(factory_root / "org").get_project(project_id)


def _seed_legacy_project(
    factory_root: Path,
    *,
    project_id: str = "P-OLD",
    name: str = "ScorePocket",
    goal: str = "做一个台球计分 App",
    lifecycle: str = "idea",
) -> None:
    """预置旧项目 (仅 org/projects.json — 无 workspace 目录, 旧字段形状)。

    与 S10-009 前存量数据一致: slug/draft 等新字段缺省 (Project 模型宽容解析),
    lifecycle 用旧值 idea。返回后 workspace/ 应完全不存在 (懒迁移前零目录)。
    """
    from org.models import utcnow
    from org.projects import Project, ProjectState, ProjectStore

    store = ProjectStore(factory_root / "org")
    legacy = Project(
        id=project_id,
        name=name,
        user_id="console",
        goal=goal,
        lifecycle=ProjectState.parse(lifecycle),
        updated_at=utcnow(),
    )
    assert legacy.slug == ""  # 旧项目无 slug (懒迁移需按 name 回填目录)
    assert not legacy.draft
    store.save_project(legacy)
    assert not (factory_root / "workspace").exists()  # 预置后零 workspace 目录


def _draft_id(client) -> str:
    resp = client.post("/api/projects", json={"idea": "我要做一个AI笔记软件"})
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


# ------------------------------------------------------------------ 假链 (零 LLM, 真实 org 编排 — 全链回归 start 段)


def _make_fake_chain(**kwargs: object) -> dict[str, object]:
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


class _FakeChainConfig:
    """可配置假链旋钮 (chain_factory/run_async — 测试断言用)。"""

    chain_factory: object = None
    run_async: bool = False


def _wrapped_start(**kw: object) -> dict[str, object]:
    """路由层 start 包装: 注入假链 + 同步执行 (测试用; 生产零影响)。"""
    kw["chain_factory"] = _FakeChainConfig.chain_factory
    kw["run_async"] = _FakeChainConfig.run_async
    return _runner.start_project_workflow(**kw)


@pytest.fixture
def fake_start(monkeypatch: pytest.MonkeyPatch) -> _FakeChainConfig:
    """HTTP 层假链注入: monkeypatch 路由模块导入的 start_project_workflow 符号 +
    hermetic key (绝不依赖真实 ~/.hermes/.env key 存在)。"""
    _FakeChainConfig.chain_factory = _make_fake_chain
    _FakeChainConfig.run_async = False
    monkeypatch.setattr(_ws, "start_project_workflow", _wrapped_start)
    monkeypatch.setattr(_runner, "has_llm_key", lambda: True)
    return _FakeChainConfig


@pytest.fixture
def client(factory_root: Path, event_logger):
    """真实装配 (build_console_service → org ProjectStore + ProjectSpaceStore +
    ConversationStore 落盘 factory_root; event_logger 事件库与 Timeline 同源)。"""
    service = _adapter.build_console_service(factory_root, event_logger=event_logger)
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


# ================================================================== 场景 1: Draft + Discovery 持久化


@requires_fastapi
class TestScenario1DraftDiscovery:
    """验收场景 1: \"我要做一个AI笔记软件\" → unnamed draft (DISCOVERY) + idea/discovery
    目录 + 问答持久化。"""

    def test_draft_creates_unnamed_discovery_with_dirs(self, client, factory_root: Path):
        """POST {idea} 无 name → unnamed-project-XXX (discovery, draft) + idea/ +
        discovery/ 目录存在 (project.json 信源落库)。"""
        resp = client.post("/api/projects", json={"idea": "我要做一个AI笔记软件"})
        assert resp.status_code == 201
        body = resp.json()
        pid = body["project_id"]
        assert body["name"].startswith("unnamed-project-")
        assert body["lifecycle"] == "discovery"
        assert body["draft"] is True

        space_dir = _space_dir(factory_root, pid)
        assert space_dir.name.startswith("unnamed-project-")
        assert (space_dir / "idea").is_dir()
        assert (space_dir / "discovery").is_dir()
        data = json.loads((space_dir / "project.json").read_text(encoding="utf-8"))
        assert data["id"] == pid
        assert data["lifecycle"] == "discovery"
        assert data["draft"] is True
        # idea 资产初始化 (原始想法落库)
        idea_conversation = json.loads(
            (space_dir / "idea" / "conversation.json").read_text(encoding="utf-8")
        )
        assert idea_conversation["idea"] == "我要做一个AI笔记软件"
        assert idea_conversation["conversation"][0]["content"] == "我要做一个AI笔记软件"
        assert (space_dir / "idea" / "idea.md").is_file()
        # discovery 会话初始化 (空会话 + session_id)
        discovery = json.loads(
            (space_dir / "discovery" / "conversation.json").read_text(encoding="utf-8")
        )
        assert discovery["session_id"].startswith("DS-")
        assert discovery["status"] == "active"
        assert discovery["conversation"] == []

    def test_discovery_answer_persists_qa(self, client, factory_root: Path):
        """AI 提问 (discovery/answer 模拟) → 问答持久化 (可多次, 顺序保留)。"""
        pid = _draft_id(client)
        first = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台是什么?", "answer": "手机 App"},
        )
        assert first.status_code == 200
        assert first.json()["count"] == 1
        second = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "核心功能?", "answer": "AI 自动整理笔记"},
        )
        assert second.status_code == 200
        assert second.json()["count"] == 2

        discovery = json.loads(
            (_space_dir(factory_root, pid) / "discovery" / "conversation.json").read_text(
                encoding="utf-8"
            )
        )
        conversation = discovery["conversation"]
        assert [e["question"] for e in conversation] == ["目标平台是什么?", "核心功能?"]
        assert [e["answer"] for e in conversation] == ["手机 App", "AI 自动整理笔记"]
        assert all(e["asked_at"] and e["answered_at"] for e in conversation)

    def test_discovery_complete_creates_product_definition(self, client, factory_root: Path):
        """问答后 complete → product_defined + product-definition.md (含澄清记录)。"""
        pid = _draft_id(client)
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        resp = client.post(f"/api/projects/{pid}/discovery/complete")
        assert resp.status_code == 200
        assert resp.json()["lifecycle"] == "product_defined"
        assert resp.json()["product_definition_ref"] == "discovery/product-definition.md"

        space_dir = _space_dir(factory_root, pid)
        definition = (space_dir / "discovery" / "product-definition.md").read_text(
            encoding="utf-8"
        )
        assert "我要做一个AI笔记软件" in definition  # 原始想法
        assert "手机 App" in definition  # 澄清记录
        discovery = json.loads(
            (space_dir / "discovery" / "conversation.json").read_text(encoding="utf-8")
        )
        assert discovery["status"] == "completed"
        # org 镜像 + 信源同步
        org = _org_project(factory_root, pid)
        assert org is not None and org.lifecycle.value == "product_defined"
        mirror = json.loads((space_dir / "project.json").read_text(encoding="utf-8"))
        assert mirror["lifecycle"] == "product_defined"


# ================================================================== 场景 2: Confirm → ai-note + CONFIRMED + 索引


@requires_fastapi
class TestScenario2Confirm:
    """验收场景 2: 确认 \"AI Note\" → ai-note/ 目录 + CONFIRMED + 索引正确 +
    conversation/discovery 保留。"""

    def test_confirm_renames_to_slug_dir_confirmed(self, client, factory_root: Path):
        """confirm {name: AI Note} → 200 {slug: ai-note, lifecycle: confirmed};
        目录 rename + 索引 + org 镜像全更新。"""
        pid = _draft_id(client)
        old_dir = _space_dir(factory_root, pid)
        assert old_dir.name.startswith("unnamed-project-")

        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        assert resp.json() == {
            "project_id": pid,
            "name": "AI Note",
            "slug": "ai-note",
            "lifecycle": "confirmed",
        }
        assert not old_dir.exists()  # 旧目录已 rename 走
        new_dir = factory_root / "workspace" / "projects" / "ai-note"
        assert new_dir.is_dir()
        # 索引正确 (id → 新 slug, 无 unnamed 残留)
        assert _index_map(factory_root) == {pid: "ai-note"}
        # org 镜像 (id 稳定, name/slug/lifecycle/draft 更新)
        org = _org_project(factory_root, pid)
        assert org is not None
        assert org.id == pid
        assert org.name == "AI Note"
        assert org.slug == "ai-note"
        assert org.lifecycle.value == "confirmed"
        assert org.draft is False
        # 信源 project.json
        data = json.loads((new_dir / "project.json").read_text(encoding="utf-8"))
        assert data["name"] == "AI Note"
        assert data["slug"] == "ai-note"
        assert data["lifecycle"] == "confirmed"

    def test_confirm_preserves_idea_and_discovery_conversation(self, client, factory_root: Path):
        """conversation/discovery 保留: 问答记录 rename 后逐字节一致 (文件不丢失)。"""
        pid = _draft_id(client)
        client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        old_dir = _space_dir(factory_root, pid)
        before = {
            "idea_conversation": (old_dir / "idea" / "conversation.json").read_bytes(),
            "idea_md": (old_dir / "idea" / "idea.md").read_bytes(),
            "discovery_conversation": (old_dir / "discovery" / "conversation.json").read_bytes(),
        }
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        new_dir = factory_root / "workspace" / "projects" / "ai-note"
        assert (new_dir / "idea" / "conversation.json").read_bytes() == before["idea_conversation"]
        assert (new_dir / "idea" / "idea.md").read_bytes() == before["idea_md"]
        assert (
            (new_dir / "discovery" / "conversation.json").read_bytes()
            == before["discovery_conversation"]
        )
        discovery = json.loads(
            (new_dir / "discovery" / "conversation.json").read_text(encoding="utf-8")
        )
        assert discovery["conversation"][0]["answer"] == "手机 App"


# ================================================================== 场景 3: 旧项目兼容 (懒迁移 + 既有 API 不破坏)


@requires_fastapi
class TestScenario3LegacyMigration:
    """验收场景 3: 预置旧项目 (仅 org/projects.json: P-OLD ScorePocket lifecycle=idea)
    → list/get 读取正常 + 懒迁移回填目录镜像 + 既有 API (PATCH/DELETE/start) 不破坏。"""

    def test_legacy_list_reads_normally(self, client, factory_root: Path):
        """旧项目 list 读取正常 (GET /api/projects 含 P-OLD, 名称/状态正确)。"""
        _seed_legacy_project(factory_root)
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        by_id = {p["id"]: p for p in resp.json()}
        assert "P-OLD" in by_id
        assert by_id["P-OLD"]["name"] == "ScorePocket"
        assert by_id["P-OLD"]["status"] == "idea"  # 旧 lifecycle 值兼容保留

    def test_legacy_lazy_migration_on_list(self, client, factory_root: Path):
        """懒迁移 (list 路径): GET /api/projects 后 ensure_space 回填目录镜像 +
        index 自愈可查。"""
        _seed_legacy_project(factory_root)
        assert not (factory_root / "workspace" / "projects" / "scorepocket").exists()
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        # 目录镜像回填 (workspace/projects/scorepocket/project.json 信源)
        mirror_dir = factory_root / "workspace" / "projects" / "scorepocket"
        assert mirror_dir.is_dir()
        data = json.loads((mirror_dir / "project.json").read_text(encoding="utf-8"))
        assert data["id"] == "P-OLD"
        assert data["name"] == "ScorePocket"
        assert data["lifecycle"] == "idea"
        # 骨架目录一并回填 (目录信源布局完整)
        assert (mirror_dir / "idea").is_dir()
        assert (mirror_dir / "discovery").is_dir()
        # index 自愈: get_slug 未命中 → 目录扫描重建可查
        from org.space import ProjectSpaceStore

        assert ProjectSpaceStore(factory_root).get_slug("P-OLD") == "scorepocket"

    def test_legacy_get_run_status_reads_normally_and_migrates(self, client, factory_root: Path):
        """旧项目 get 路径读取正常 (run-status → none) + 懒迁移 (get 首次访问回填)。"""
        _seed_legacy_project(factory_root)
        resp = client.get("/api/projects/P-OLD/run-status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "none"
        # get 路径同样触发懒迁移 (project_exists 读取即回填)
        mirror_dir = factory_root / "workspace" / "projects" / "scorepocket"
        assert mirror_dir.is_dir()
        assert (mirror_dir / "project.json").is_file()

    def test_legacy_patch_rename_works(self, client, factory_root: Path):
        """既有 API 不破坏: PATCH rename 旧项目 → 200 + org 落库 + 列表可见新名。"""
        _seed_legacy_project(factory_root)
        resp = client.patch("/api/projects/P-OLD", json={"name": "ScorePocket Pro"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "ScorePocket Pro"
        org = _org_project(factory_root, "P-OLD")
        assert org is not None and org.name == "ScorePocket Pro"
        listed = {p["id"]: p for p in client.get("/api/projects").json()}
        assert listed["P-OLD"]["name"] == "ScorePocket Pro"

    def test_legacy_delete_works(self, client, factory_root: Path):
        """既有 API 不破坏: DELETE 旧项目 → 200 {deleted: true} + org 记录移除。"""
        _seed_legacy_project(factory_root)
        resp = client.delete("/api/projects/P-OLD")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": True, "project_id": "P-OLD"}
        assert _org_project(factory_root, "P-OLD") is None
        # 删除后再查 → 404 (项目已不存在)
        assert client.get("/api/projects/P-OLD/run-status").status_code == 404

    def test_legacy_start_works_fake_chain(self, client, factory_root: Path, fake_start):
        """既有 API 不破坏: start 旧项目 (假链) → 200 started + run-status completed
        (真实 org 编排写事件/产物 — 旧项目可正常启动执行链)。"""
        _seed_legacy_project(factory_root)
        resp = client.post("/api/projects/P-OLD/start")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["project_id"] == "P-OLD"
        assert body["run_id"].startswith("R")
        run = client.get("/api/projects/P-OLD/run-status").json()
        assert run["status"] == "completed"
        assert run["runs"][0]["run_id"] == body["run_id"]
        assert run["runs"][0]["status"] == "completed"
        assert run["runs"][0]["stages"][0]["stage"] == "product"


# ================================================================== 场景 4: index 删除 → 扫描重建


@requires_fastapi
class TestScenario4IndexRebuild:
    """验收场景 4: 删除 workspace/projects.json → 列表不受影响 (list 不依赖缓存) +
    索引自愈 (get_slug 未命中重建) + rebuild_index 目录扫描恢复。"""

    def test_index_delete_project_list_recovers(self, client, factory_root: Path):
        """删 index → GET /api/projects 列表恢复 (项目仍可见 — list 不依赖缓存)。"""
        pid = _draft_id(client)
        client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        assert space.index_path.is_file()  # confirm 后索引存在
        space.index_path.unlink()  # 删除 index 文件
        assert not space.index_path.exists()
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        by_id = {p["id"]: p for p in resp.json()}
        assert by_id[pid]["name"] == "AI Note"

    def test_index_delete_self_heal_on_indexed_operation(self, client, factory_root: Path):
        """删 index → 依赖索引的写路径 (discovery/answer 经 get_slug) 自愈重建。"""
        from org.space import ProjectSpaceStore

        pid = _draft_id(client)
        space = ProjectSpaceStore(factory_root)
        space.rebuild_index()  # 正常状态: 索引存在
        assert space.index_path.is_file()
        slug = space.get_slug(pid)
        space.index_path.unlink()  # 删除 index 文件
        assert not space.index_path.exists()
        resp = client.post(
            f"/api/projects/{pid}/discovery/answer",
            json={"question": "目标平台?", "answer": "手机 App"},
        )
        assert resp.status_code == 200
        # 自愈: get_slug 未命中 → 目录扫描重建 → 索引文件恢复且映射正确
        assert space.index_path.is_file()
        assert space.list_index() == {pid: slug}

    def test_index_rebuild_direct_restores_map(self, client, factory_root: Path):
        """ProjectSpaceStore.rebuild_index: 删 index 后目录扫描重建 → id→slug 全量恢复。"""
        pid = _draft_id(client)
        client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        from org.space import ProjectSpaceStore

        space = ProjectSpaceStore(factory_root)
        space.index_path.unlink()
        assert space.list_index() == {}
        rebuilt = space.rebuild_index()
        assert rebuilt == {pid: "ai-note"}
        assert space.index_path.is_file()
        assert space.list_index() == {pid: "ai-note"}


# ================================================================== 全链回归 (draft→answer→complete→confirm→start 假链)


@requires_fastapi
class TestFullJourneyRegression:
    """全链回归: 整条用户旅程 draft→answer→complete→confirm→start (假链) 端到端。"""

    def test_full_journey_draft_to_start(self, client, factory_root: Path, fake_start):
        """draft → 问答 → complete → confirm → start (假链) → run-status completed
        + Timeline 事件可见 + 最终目录/索引状态正确。"""
        # 1. draft (无 name)
        pid = _draft_id(client)
        # 2. AI 提问 → 问答持久化 (两次)
        for question, answer in (
            ("目标平台是什么?", "手机 App"),
            ("核心功能?", "AI 自动整理笔记"),
        ):
            resp = client.post(
                f"/api/projects/{pid}/discovery/answer",
                json={"question": question, "answer": answer},
            )
            assert resp.status_code == 200
        # 3. complete → product_defined
        resp = client.post(f"/api/projects/{pid}/discovery/complete")
        assert resp.status_code == 200
        assert resp.json()["lifecycle"] == "product_defined"
        # 4. confirm → CONFIRMED + ai-note 目录
        resp = client.post(f"/api/projects/{pid}/confirm", json={"name": "AI Note"})
        assert resp.status_code == 200
        assert resp.json()["slug"] == "ai-note"
        assert resp.json()["lifecycle"] == "confirmed"
        new_dir = factory_root / "workspace" / "projects" / "ai-note"
        assert new_dir.is_dir()
        # 问答记录随目录保留 (全链不丢失)
        discovery = json.loads(
            (new_dir / "discovery" / "conversation.json").read_text(encoding="utf-8")
        )
        assert discovery["conversation"][1]["answer"] == "AI 自动整理笔记"
        # 5. start (假链, 同步) → started
        resp = client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["run_id"].startswith("R")
        # 6. run-status → completed (stages/totals 来自真实落库)
        run = client.get(f"/api/projects/{pid}/run-status").json()
        assert run["status"] == "completed"
        assert run["runs"][0]["status"] == "completed"
        assert run["runs"][0]["stages"][0]["stage"] == "product"
        assert "total_tokens" in run["runs"][0]["totals"]
        # 7. Timeline 事件可见 (假链写真实 org.* 事件 — 与 Timeline 同 events.db)
        timeline = client.get(f"/api/projects/{pid}/timeline").json()
        stage_events = [
            e
            for e in timeline
            if e["type"] == "stage"
            and e["event_type"] in ("org.workflow.stage_started", "org.workflow.stage_completed")
        ]
        assert stage_events, f"no stage events in timeline: {timeline}"
        assert any(e["type"] == "artifact" for e in timeline)
        assert any(e["event_type"] == "org.workflow.completed" for e in timeline)
        # 8. 最终状态: 索引正确 + org 镜像 confirmed
        assert _index_map(factory_root) == {pid: "ai-note"}
        org = _org_project(factory_root, pid)
        assert org is not None and org.lifecycle.value == "confirmed"
        assert org.slug == "ai-note"
        assert org.draft is False
