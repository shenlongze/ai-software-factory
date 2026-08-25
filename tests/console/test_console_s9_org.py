"""tests/console/test_console_s9_org.py — S9-002 org 聚合 + 审批决定 (集成 + HTTP)。

覆盖 (S9-002 Console MVP 验收; 用户已解除 Console 冻结 — 唯一写路径 =
审批决定两 POST, 走 org Approval 状态机, source="console" 审计):
- GET /api/projects 聚合: workflow_id/current_stage/progress/stage_counts
- GET /api/workflows 8 阶段链: 进度聚合 + 单 workflow 全视图 (stages 按
  order 升序 / template / pending_approvals)
- GET /api/artifacts 过滤: project_id / workflow_id (stage 反查) / type
- GET /api/approval-gates: org 审批门清单 (决定操作对象)
- POST /api/approvals/{id}/approve|reject:
  - 成功: gate 终态 + workflow 恢复 ACTIVE / 停止 FAILED
  - 404: 门不存在
  - 409: 非 PENDING 门 (终态决定不可撤销)
  - 审计: org.approval.approved/rejected source="console" (reviewer 落库)
- 端到端: 建 workflow → Runner 到审批门挂起 → POST approve → 继续执行

本目录自洽 (不跨目录依赖 helper): sys.path 挂 factory-core/factory-org/
factory-exec (同 tests/s9 装配); basename 全仓库唯一 (test_console_* 前缀)。
executor 产物 metadata 与 org CONTRACTS 同源 (S9-001 冒烟阻断修复点)。
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
from org.workflow import WorkflowLifecycle, WorkflowRunner, WorkflowStatus

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
    """WorkflowLifecycle (logger 带事件库 — org.approval.* source 断言)。"""
    return WorkflowLifecycle(project_store, logger=event_logger)


@pytest.fixture
def project_id(project_store: ProjectStore) -> str:
    project_store.save_project(Project(id="P-9", name="Approval App", user_id="u1"))
    return "P-9"


@pytest.fixture
def service(wlife: WorkflowLifecycle, project_store: ProjectStore) -> _models.ConsoleService:
    """ConsoleService (注入真实 org 装配 — S9-002 聚合走真实数据空间)。"""
    return _console.ConsoleService(project_store=project_store, workflow_lifecycle=wlife)


@pytest.fixture
def client(service, event_logger):
    """真实服务 + EventLogger 的 TestClient (HTTP 集成断言)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ 构造辅助 (本目录自洽)

#: role → 契约合法产物 (与 org CONTRACTS 同源; 非 LLM 占位语义)
def _chain_executor(stage, context) -> dict:
    """S9-002 E2E mock executor (metadata 全部通过 validate_artifact 校验)。"""
    role = stage.role_id
    if role == "product-manager":
        return {
            "artifact_type": "prd",
            "ref": "file:///docs/prd.json",
            "metadata": {"problem": "p", "user": "u", "features": ["f1"]},
        }
    if role == "architect":
        return {
            "artifact_type": "design",
            "ref": "file:///docs/design.json",
            "metadata": {
                "system_architecture": "三层",
                "technical_stack": {"language": "python"},
                "database_design": {"storage": "json"},
                "api_design": {"endpoints": [{"method": "POST", "path": "/api/v1/x", "contract": "c"}]},
                "frontend_architecture": "console",
                "backend_architecture": "service",
                "task_breakdown": [{"module": "m", "task": "t", "api_contract": "a", "ui_guidance": "u"}],
            },
        }
    if role == "developer":
        return {
            "artifact_type": "code",
            "ref": "file:///src",
            "metadata": {"files": ["src/a.py"], "changes": "S9-002"},
        }
    if role == "tester":
        return {
            "artifact_type": "test",
            "ref": "file:///t.json",
            "metadata": {"results": {"passed": True, "total": 1, "failed": 0}, "bugs": []},
        }
    if role == "devops":
        return {
            "artifact_type": "release",
            "ref": "file:///dist/r.tar.gz",
            "metadata": {
                "build_result": {"status": "success", "command": "python -m build"},
                "version": "1.0.0",
                "package": {"name": "x", "type": "tar.gz", "files": ["dist/x.tar.gz"]},
                "release_notes": "S9-002",
                "deployment": "解压 → 安装 → 启动",
            },
        }
    raise AssertionError(f"no mock output for role {role!r}")


def build_chain_wf(
    wlife: WorkflowLifecycle, project_id: str, *, gate_count: int = 1
) -> Any:
    """8 阶段链 (product-manager→architect→developer→tester→devops);
    前 gate_count 个 approval_required 阶段 (审批门挡板)。返回 Workflow。"""
    wf = wlife.create_workflow(project_id, "S9-002 Chain")
    for role_id, gate in (
        ("product-manager", gate_count >= 1),
        ("architect", gate_count >= 2),
        ("developer", False),
        ("tester", False),
        ("devops", gate_count >= 3),
    ):
        wlife.create_stage(wf.id, role_id, name=f"{role_id} stage", approval_required=gate)
    return wf


def _mark_completed(wlife: WorkflowLifecycle, stage_id: str) -> None:
    """PENDING → READY → RUNNING → COMPLETED (受控转换表合法路径)。"""
    wlife.transition_stage(stage_id, "ready")
    wlife.transition_stage(stage_id, "running")
    wlife.transition_stage(stage_id, "completed")


def _pending_gate(wlife: WorkflowLifecycle, workflow_id: str):
    gates = [
        g for g in wlife.list_approvals(workflow_id=workflow_id)
        if g.status.value == "pending"
    ]
    assert len(gates) == 1, "预期恰一个待审门"
    return gates[0]


# ------------------------------------------------------------------ GET /projects 聚合


class TestProjectsAggregation:
    def test_project_includes_workflow_projection(self, service, wlife, project_id):
        """org 项目 → workflow_id/current_stage/progress/stage_counts 聚合。"""
        wf = build_chain_wf(wlife, project_id)
        stages = wlife.list_stages(wf.id)
        _mark_completed(wlife, stages[0].id)  # 1/5 完成
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)

        summary = next(p for p in service.list_projects() if p.id == project_id)
        assert summary.workflow_id == wf.id
        assert summary.workflow_status == "active"
        assert summary.current_stage == stages[1].name  # 第一个未完成阶段
        assert summary.progress == pytest.approx(1 / 5)
        assert summary.stage_counts == {"pending": 4, "completed": 1}

    def test_project_without_workflow_no_projection(self, service, project_id):
        """无 workflow 项目 → 聚合字段保持默认 (None/0.0/{}), 零破坏。"""
        summary = next(p for p in service.list_projects() if p.id == project_id)
        assert summary.workflow_id is None
        assert summary.current_stage is None
        assert summary.progress == 0.0
        assert summary.stage_counts == {}

    def test_http_projects_include_aggregation(self, client, wlife, project_id):
        """GET /api/projects → JSON 含 org 聚合字段。"""
        wf = build_chain_wf(wlife, project_id)
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        item = next(p for p in resp.json()["items"] if p["id"] == project_id)
        assert item["workflow_id"] == wf.id
        assert item["workflow_status"] == "draft"
        assert item["progress"] == 0.0
        assert item["stage_counts"]["pending"] == 5


# ------------------------------------------------------------------ GET /workflows (8 阶段链)


class TestWorkflowList:
    def test_list_workflows_progress_aggregation(self, service, wlife, project_id):
        """阶段链进度聚合: stage_count/completed_count/progress/current_stage。"""
        wf = build_chain_wf(wlife, project_id)
        stages = wlife.list_stages(wf.id)
        _mark_completed(wlife, stages[0].id)

        out = service.list_workflows()
        assert len(out) == 1
        summary = out[0]
        assert summary.id == wf.id
        assert summary.project_id == project_id
        assert summary.stage_count == 5
        assert summary.completed_count == 1
        assert summary.progress == pytest.approx(0.2)
        assert summary.current_stage == stages[1].name
        assert summary.current_stage_status == "pending"

    def test_list_workflows_filters_by_project(self, service, wlife, project_id):
        """project_id 过滤 (org list_workflows 委托)。"""
        build_chain_wf(wlife, project_id)
        assert len(service.list_workflows(project_id=project_id)) == 1
        assert service.list_workflows(project_id="nope") == []

    def test_list_workflows_empty_without_org(self):
        """无 org 装配 → 空列表 (失败安全)。"""
        assert _console.ConsoleService().list_workflows() == []

    def test_http_workflows_200(self, client, wlife, project_id):
        build_chain_wf(wlife, project_id)
        resp = client.get("/api/workflows")
        assert resp.status_code == 200
        body = resp.json()["items"]
        assert len(body) == 1
        assert body[0]["project_id"] == project_id
        assert body[0]["stage_count"] == 5


class TestWorkflowDetail:
    def test_detail_8_stage_chain(self, service, wlife, project_id):
        """单 workflow 全视图: stages 按 order 升序 + template 规范 8 阶段链。"""
        wf = build_chain_wf(wlife, project_id)
        detail = service.get_workflow(wf.id)
        assert detail is not None
        assert detail.project_id == project_id
        assert [s.order for s in detail.stages] == [1, 2, 3, 4, 5]
        assert [s.role_id for s in detail.stages] == [
            "product-manager", "architect", "developer", "tester", "devops",
        ]
        assert detail.template == [
            "Idea", "PM", "Product", "UX/UI", "Architecture", "Development", "Test", "Release",
        ]
        assert all(isinstance(s.to_dict(), dict) for s in detail.stages)

    def test_detail_includes_artifact_projection(self, service, wlife, project_id):
        """阶段输出产物摘要投影 (artifact type/ref/status)。"""
        wf = build_chain_wf(wlife, project_id)
        stage = wlife.list_stages(wf.id)[0]
        artifact = wlife.registry.create(
            stage_id=stage.id, type_=ArtifactType.PRD, project_id=project_id,
            ref="file:///docs/prd.json", producer_role=stage.role_id,
        )
        # 回写 stage.artifact_ref (Runner 完成时自动追加 output_artifacts;
        # 手动 registry.create 不隐式回写 — 测试镜像 Runner 的回写语义)
        updated = stage.model_copy(update={"artifact_ref": artifact.id})
        wlife.store.save_stage(updated)
        detail = service.get_workflow(wf.id)
        assert detail is not None
        proj = detail.stages[0].artifact
        assert proj is not None
        assert proj.id == artifact.id
        assert proj.type == "prd"
        assert proj.workflow_id == wf.id  # stage 反查

    def test_detail_missing_returns_none(self, service):
        assert service.get_workflow("nope") is None

    def test_detail_empty_without_org(self):
        assert _console.ConsoleService().get_workflow("WF-1") is None

    def test_http_workflow_detail_200_and_404(self, client, wlife, project_id):
        wf = build_chain_wf(wlife, project_id)
        resp = client.get(f"/api/workflows/{wf.id}")
        assert resp.status_code == 200
        assert len(resp.json()["stages"]) == 5
        assert client.get("/api/workflows/nope").status_code == 404


# ------------------------------------------------------------------ GET /artifacts 过滤


class TestArtifactFiltering:
    def _seed(self, wlife, project_id):
        """两 workflow × 两产物 (prd + code) 数据基座。"""
        wf1 = build_chain_wf(wlife, project_id)
        wf2 = build_chain_wf(wlife, project_id)
        stage1 = wlife.list_stages(wf1.id)[0]
        stage2 = wlife.list_stages(wf2.id)[0]
        a_prd = wlife.registry.create(
            stage_id=stage1.id, type_=ArtifactType.PRD, project_id=project_id,
            ref="file:///docs/prd.json", producer_role=stage1.role_id,
        )
        a_code = wlife.registry.create(
            stage_id=stage1.id, type_=ArtifactType.CODE, project_id=project_id,
            ref="file:///src", producer_role="developer",
        )
        a_prd2 = wlife.registry.create(
            stage_id=stage2.id, type_=ArtifactType.PRD, project_id=project_id,
            ref="file:///docs/prd2.json", producer_role=stage2.role_id,
        )
        return wf1, wf2, a_prd, a_code, a_prd2

    def test_list_artifacts_all(self, service, wlife, project_id):
        _, _, a_prd, a_code, a_prd2 = self._seed(wlife, project_id)
        out = service.list_artifacts()
        assert {a.id for a in out} == {a_prd.id, a_code.id, a_prd2.id}

    def test_filter_by_project(self, service, wlife, project_id):
        self._seed(wlife, project_id)
        out = service.list_artifacts(project_id=project_id)
        assert len(out) == 3
        assert service.list_artifacts(project_id="other") == []

    def test_filter_by_workflow_stage_lookup(self, service, wlife, project_id):
        """workflow 过滤经 stage 反查 (Artifact 无 workflow 字段)。"""
        wf1, wf2, a_prd, a_code, a_prd2 = self._seed(wlife, project_id)
        out = service.list_artifacts(workflow_id=wf1.id)
        assert {a.id for a in out} == {a_prd.id, a_code.id}
        assert service.list_artifacts(workflow_id=wf2.id)[0].id == a_prd2.id

    def test_filter_by_type(self, service, wlife, project_id):
        self._seed(wlife, project_id)
        out = service.list_artifacts(type="prd")
        assert len(out) == 2
        assert all(a.type == "prd" for a in out)

    def test_combined_filters(self, service, wlife, project_id):
        wf1, *_ = self._seed(wlife, project_id)
        out = service.list_artifacts(workflow_id=wf1.id, type="code")
        assert len(out) == 1
        assert out[0].type == "code"

    def test_artifacts_empty_without_org(self):
        assert _console.ConsoleService().list_artifacts() == []

    def test_http_artifacts_filter(self, client, wlife, project_id):
        wf1, _, _, _, _ = self._seed(wlife, project_id)
        resp = client.get(f"/api/artifacts?workflow_id={wf1.id}&type=prd")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert resp.json()["items"][0]["workflow_id"] == wf1.id


# ------------------------------------------------------------------ GET /approval-gates


class TestApprovalGates:
    def test_list_gates_with_project_id(self, service, wlife, project_id):
        """审批门清单: project_id 经 gate → workflow 反查。"""
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        out = service.list_approval_gates()
        assert len(out) == 1
        assert out[0].id == gate.id
        assert out[0].workflow_id == wf.id
        assert out[0].project_id == project_id  # 反查
        assert out[0].status == "pending"

    def test_gates_status_filter(self, service, wlife, project_id):
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)
        assert service.list_approval_gates(status="pending")[0].id == gate.id
        assert service.list_approval_gates(status="approved") == []

    def test_gates_empty_without_org(self):
        assert _console.ConsoleService().list_approval_gates() == []

    def test_http_approval_gates_200(self, client, wlife, project_id):
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)
        resp = client.get("/api/approval-gates?status=pending")
        assert resp.status_code == 200
        assert resp.json()["items"][0]["id"] == gate.id
        assert resp.json()["items"][0]["project_id"] == project_id


# ------------------------------------------------------------------ POST approve/reject (HTTP)


@requires_fastapi
class TestApprovalDecisionHttp:
    def test_approve_success(self, client, wlife, project_id):
        """POST approve → 200: gate APPROVED + workflow PAUSED→ACTIVE。"""
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        resp = client.post(f"/api/approvals/{gate.id}/approve")
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "approve"
        assert body["gate"]["status"] == "approved"
        assert body["workflow_id"] == wf.id
        assert body["workflow_status"] == "active"
        assert wlife.get_workflow(wf.id).status == WorkflowStatus.ACTIVE

    def test_reject_success(self, client, wlife, project_id):
        """POST reject → 200: gate REJECTED + workflow FAILED 停止。"""
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        resp = client.post(f"/api/approvals/{gate.id}/reject")
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "reject"
        assert body["gate"]["status"] == "rejected"
        assert body["workflow_status"] == "failed"
        assert wlife.get_workflow(wf.id).status == WorkflowStatus.FAILED
        assert "approval rejected" in wlife.get_workflow(wf.id).failed_reason

    def test_missing_gate_404(self, client):
        assert client.post("/api/approvals/nope/approve").status_code == 404
        assert client.post("/api/approvals/nope/reject").status_code == 404

    def test_already_decided_409(self, client, wlife, project_id):
        """终态门再决定 → 409 Conflict (决定不可撤销 — 审计铁律)。"""
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)
        assert client.post(f"/api/approvals/{gate.id}/approve").status_code == 200
        assert client.post(f"/api/approvals/{gate.id}/approve").status_code == 409
        assert client.post(f"/api/approvals/{gate.id}/reject").status_code == 409

    def test_source_console_audit(self, client, wlife, project_id, event_store):
        """审计: org.approval.approved/rejected source="console" (决策入口区分)。"""
        wf = build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        client.post(f"/api/approvals/{gate.id}/approve")
        events = [e for e in event_store.query() if e.type.value == "org.approval.approved"]
        assert len(events) == 1
        # source 是 Event 顶层字段 (同 tests/s9 惯例: event.source == "cli");
        # payload 承载决定上下文 (reviewer/comment/gate_id 落库审计)
        assert events[0].source == "console"
        assert events[0].payload.get("reviewer") == "console"
        assert events[0].payload.get("gate_id") == gate.id

    def test_e2e_workflow_gate_approve_continue(self, client, wlife, project_id):
        """端到端: Runner 到审批门挂起 → POST approve → 继续执行下一阶段。"""
        wf = build_chain_wf(wlife, project_id, gate_count=2)  # 两门: approve 后续阶段再挂起
        runner = WorkflowRunner(wlife, executor=_chain_executor, logger=None)

        wf = runner.run(wf.id)
        assert wf.status == WorkflowStatus.PAUSED  # P1 门挂起
        gate = _pending_gate(wlife, wf.id)
        stages = wlife.list_stages(wf.id)
        assert stages[0].status.value == "completed"  # 门禁阶段已完成
        # 后续阶段未执行 (Runner 就绪评估已标 READY — 准备但未运行;
        # pending/ready/blocked 均表示尚未执行)
        assert stages[1].status.value in ("pending", "ready", "blocked")

        resp = client.post(f"/api/approvals/{gate.id}/approve")
        assert resp.status_code == 200

        wf = runner.run(wf.id)  # 继续: 下一阶段执行 → 下一门挂起
        assert wf.status == WorkflowStatus.PAUSED
        assert wlife.list_stages(wf.id)[1].status.value == "completed"
        # 第二门 pending (id 随机排序 — 不能依赖 [-1], 按 status 精确断言)
        pending = [
            g for g in wlife.list_approvals(workflow_id=wf.id)
            if g.status.value == "pending"
        ]
        assert len(pending) == 1
        assert pending[0].stage_id == wlife.list_stages(wf.id)[1].id

    def test_e2e_reject_stops_workflow(self, client, wlife, project_id):
        """端到端否决: workflow FAILED 停止, Runner 重跑响亮拒绝。"""
        from org.workflow import WorkflowStateError

        wf = build_chain_wf(wlife, project_id)
        runner = WorkflowRunner(wlife, executor=_chain_executor, logger=None)
        wf = runner.run(wf.id)
        gate = _pending_gate(wlife, wf.id)

        resp = client.post(f"/api/approvals/{gate.id}/reject")
        assert resp.status_code == 200
        assert wlife.get_workflow(wf.id).status == WorkflowStatus.FAILED
        with pytest.raises(WorkflowStateError, match="rejected approval gate"):
            runner.run(wf.id)
