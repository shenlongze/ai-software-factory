"""tests/console/test_console_s9_003.py — S9-003 UX/UI Review Interface (后端验收)。

覆盖 (S9-003 Review 数据流 + Approval 集成 + comment 持久化):
- gate comment 持久化: approve/reject 带 comment → ApprovalGate.comment 落库
  (org ApprovalGateStore 既有 comment 字段 — S9-001 透传, 零新存储)
- Artifact 详情关联查询: GET /api/artifacts/{id} → metadata 契约载荷 (product
  6 节 / ux_ui 7 节) + review 审批门 (需求/设计确认门: status/comment/reviewer)
- POST approve/reject with comment (body {reviewer, comment}; 无 body 兼容
  S9-002; 409 终态不可撤销)
- 修改反馈数据流: reject comment 经 gate 存留 → 下一轮重生成输入 (标注为
  输入; 不改 Agent 核心 — 仅数据流, 产物 metadata 回注 review_feedback)

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
from org.workflow import WorkflowLifecycle, WorkflowStatus

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
    project_store.save_project(Project(id="P-9", name="Review App", user_id="u1"))
    return "P-9"


@pytest.fixture
def service(wlife: WorkflowLifecycle, project_store: ProjectStore) -> _models.ConsoleService:
    """ConsoleService (注入真实 org 装配 — Review 查询走真实数据空间)。"""
    return _console.ConsoleService(project_store=project_store, workflow_lifecycle=wlife)


@pytest.fixture
def client(service, event_logger):
    """真实服务 + EventLogger 的 TestClient (HTTP 集成断言)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ 构造辅助 (本目录自洽)

#: Review 页 PRD 6 节 (任务规格: market_analysis/user_persona/user_journey/
#: feature_list/mvp_scope/user_stories; CONTRACTS product 7 节含 problem_statement)
PRODUCT_REVIEW_SECTIONS: tuple[str, ...] = (
    "market_analysis",
    "user_persona",
    "user_journey",
    "feature_list",
    "mvp_scope",
    "user_stories",
)


def _product_payload_ok() -> dict[str, Any]:
    """合法 product 契约载荷 (7 节 — CONTRACTS 同构; 含 Review 页 6 节)。"""
    return {
        "market_analysis": "目标市场: 个人记账用户; 竞争: 手工表格/同类 App",
        "user_persona": "25-40 岁上班族, 需要简单记账与月度报表",
        "user_journey": "记录一笔支出 → 查看分类统计 → 月底生成报表",
        "problem_statement": "手工记账繁琐, 现有工具功能过重",
        "feature_list": ["支出记录", "分类统计", "月度报表"],
        "mvp_scope": {
            "in": ["支出记录", "分类统计"],
            "out": ["多人协作", "自动导入账单"],
        },
        "user_stories": [
            {"as-a": "用户", "i-want": "快速记录支出", "so-that": "不遗漏"},
            {"as-a": "用户", "i-want": "查看月度报表", "so-that": "掌握开销"},
        ],
    }


def _uxui_payload_ok() -> dict[str, Any]:
    """合法 ux_ui 契约载荷 (7 节; wireframe.screens 每屏含 name/ascii/
    components/actions — 机器可读 ASCII 布局, Review 页预览数据源)。"""
    screens = [
        {
            "name": "screen_home",
            "ascii": "+------------+\n| 余额卡片   |\n| 近期流水   |\n+------------+",
            "components": ["BalanceCard", "TransactionList"],
            "actions": ["下拉刷新", "点击流水进入详情"],
        },
        {
            "name": "screen_record",
            "ascii": "+------------+\n| 金额输入   |\n| 分类选择   |\n+------------+",
            "components": ["AmountInput", "CategoryPicker"],
            "actions": ["提交后返回首页"],
        },
    ]
    return {
        "information_architecture": {
            "screens": [s["name"] for s in screens],
            "navigation": "底部 Tab 导航: 首页/记录/报表",
        },
        "user_flow": [
            {"step": "打开应用", "screen": "screen_home"},
            {"step": "记录一笔支出", "screen": "screen_record"},
        ],
        "wireframe": {"screens": screens},
        "screen_specifications": [
            {
                "screen": "screen_home",
                "elements": ["余额卡片", "近期流水"],
                "behaviors": ["下拉刷新"],
                "acceptance": ["余额展示正确"],
            },
        ],
        "component_definition": [
            {"name": "BalanceCard", "description": "余额展示卡片", "usage": "首页顶部"},
            {"name": "AmountInput", "description": "金额输入框", "usage": "记录页"},
        ],
        "design_tokens": {
            "colors": {"primary": "#1A73E8", "background": "#FFFFFF"},
            "typography": {"title": "18px/600", "body": "14px/400"},
            "spacing": {"xs": 4, "sm": 8, "md": 16},
        },
        "prototype": "点击底部 Tab 切换; 记录页提交后返回首页并刷新余额; 纯文本描述。",
    }


def _build_chain_wf(wlife: WorkflowLifecycle, project_id: str, *, gate_count: int = 1) -> Any:
    """5 阶段链 (product-manager→architect→developer→tester→devops);
    前 gate_count 个 approval_required 阶段 (需求/设计确认门挡板)。"""
    wf = wlife.create_workflow(project_id, "S9-003 Chain")
    for role_id, gate in (
        ("product-manager", gate_count >= 1),
        ("architect", gate_count >= 2),
        ("developer", False),
        ("tester", False),
        ("devops", False),
    ):
        wlife.create_stage(wf.id, role_id, name=f"{role_id} stage", approval_required=gate)
    return wf


def _make_product_artifact(wlife: WorkflowLifecycle, project_id: str, wf) -> Any:
    """product 产物 (7 节契约载荷; 挂 workflow 首阶段 — 需求确认门对象)。"""
    stage = wlife.list_stages(wf.id)[0]
    artifact = wlife.registry.create(
        stage_id=stage.id,
        type_=ArtifactType.PRODUCT,
        project_id=project_id,
        ref="file:///docs/product.json",
        producer_role=stage.role_id,
        metadata=_product_payload_ok(),
    )
    return artifact


# ------------------------------------------------------------------ gate comment 持久化


class TestGateCommentPersist:
    def test_approve_comment_persisted_on_gate(self, wlife, project_id):
        """approve 带 comment → gate.comment 落库 (org ApprovalGateStore)。"""
        wf = _build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        _, workflow = wlife.approve_approval(
            gate.id, reviewer="console", comment="范围确认: MVP 只做支出记录", source="console"
        )
        assert workflow.status == WorkflowStatus.ACTIVE  # 恢复
        persisted = wlife.get_approval(gate.id)
        assert persisted.status.value == "approved"
        assert persisted.comment == "范围确认: MVP 只做支出记录"
        assert persisted.reviewer == "console"
        assert persisted.approved_at is not None

    def test_reject_comment_persisted_on_gate(self, wlife, project_id):
        """reject 带 comment → gate.comment 落库 (否决原因审计)。"""
        wf = _build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)

        _, workflow = wlife.reject_approval(
            gate.id, reviewer="human", comment="MVP 范围过大: 移除月度报表", source="console"
        )
        assert workflow.status == WorkflowStatus.FAILED  # 停止
        persisted = wlife.get_approval(gate.id)
        assert persisted.status.value == "rejected"
        assert persisted.comment == "MVP 范围过大: 移除月度报表"
        assert persisted.rejected_at is not None
        assert "移除月度报表" in workflow.failed_reason

    def test_approve_without_comment_default_empty(self, wlife, project_id):
        """无 comment 决定 → gate.comment 保持空串 (S9-002 兼容零破坏)。"""
        wf = _build_chain_wf(wlife, project_id)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(wlife.list_stages(wf.id)[0].id)
        wlife.approve_approval(gate.id, reviewer="console", source="console")
        assert wlife.get_approval(gate.id).comment == ""


# ------------------------------------------------------------------ Artifact 详情 (metadata + review 门)


class TestArtifactDetailQuery:
    def test_detail_metadata_and_review_gate(self, service, wlife, project_id):
        """详情: product 契约载荷 (Review 6 节) + review 门 (pending 状态)。"""
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(artifact.stage_id)  # 需求确认门

        detail = service.get_artifact(artifact.id)
        assert detail is not None
        assert detail.type == "product"
        for section in PRODUCT_REVIEW_SECTIONS:
            assert section in detail.metadata  # 6 节齐全
        assert detail.metadata["feature_list"] == ["支出记录", "分类统计", "月度报表"]
        assert detail.review is not None
        assert detail.review.id == gate.id
        assert detail.review.stage_id == artifact.stage_id
        assert detail.review.status == "pending"
        assert detail.review.workflow_id == wf.id
        assert detail.review.project_id == project_id

    def test_detail_review_status_after_approve(self, service, wlife, project_id):
        """approve with comment → 详情 review.status=approved + comment 透传。"""
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(artifact.stage_id)
        wlife.approve_approval(
            gate.id, reviewer="console", comment="需求确认, 开始设计", source="console"
        )

        detail = service.get_artifact(artifact.id)
        assert detail is not None
        assert detail.review is not None
        assert detail.review.status == "approved"
        assert detail.review.comment == "需求确认, 开始设计"
        assert detail.review.reviewer == "console"

    def test_detail_review_none_without_gate(self, service, wlife, project_id):
        """无审批门的产物 → review=None (零破坏)。"""
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        detail = service.get_artifact(artifact.id)
        assert detail is not None
        assert detail.review is None
        assert detail.metadata["user_stories"]  # 载荷仍在

    def test_detail_missing_returns_none(self, service):
        """产物不存在 → None (404 语义由 HTTP 层映射)。"""
        assert service.get_artifact("nope") is None

    def test_http_detail_200_with_review(self, client, wlife, project_id):
        """GET /api/artifacts/{id} → 200: metadata 6 节 + review 门投影。"""
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(artifact.stage_id)

        resp = client.get(f"/api/artifacts/{artifact.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "product"
        for section in PRODUCT_REVIEW_SECTIONS:
            assert section in body["metadata"]
        assert body["review"]["id"] == gate.id
        assert body["review"]["status"] == "pending"

    def test_http_detail_404(self, client):
        """GET /api/artifacts/nope → 404 (不存在/无 org 统一映射)。"""
        assert client.get("/api/artifacts/nope").status_code == 404


# ------------------------------------------------------------------ POST approve/reject with comment (HTTP)


@requires_fastapi
class TestReviewDecideHttp:
    def _setup_gate(self, wlife, project_id):
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(artifact.stage_id)
        return wf, artifact, gate

    def test_http_approve_with_comment(self, client, wlife, project_id):
        """POST approve body {reviewer, comment} → 200 + comment 落库 + 恢复。"""
        wf, _, gate = self._setup_gate(wlife, project_id)
        resp = client.post(
            f"/api/approvals/{gate.id}/approve",
            json={"reviewer": "console", "comment": "需求确认: 增加导出功能"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "approve"
        assert body["gate"]["status"] == "approved"
        assert body["gate"]["comment"] == "需求确认: 增加导出功能"
        assert wlife.get_workflow(wf.id).status == WorkflowStatus.ACTIVE
        assert wlife.get_approval(gate.id).comment == "需求确认: 增加导出功能"

    def test_http_reject_with_comment(self, client, wlife, project_id):
        """POST reject body {reviewer, comment} → 200 + 否决原因落库 + 停止。"""
        wf, _, gate = self._setup_gate(wlife, project_id)
        resp = client.post(
            f"/api/approvals/{gate.id}/reject",
            json={"reviewer": "console", "comment": "设计方向不对: 改为底部 Tab"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "reject"
        assert body["gate"]["status"] == "rejected"
        assert body["gate"]["comment"] == "设计方向不对: 改为底部 Tab"
        assert wlife.get_workflow(wf.id).status == WorkflowStatus.FAILED
        assert "设计方向不对" in wlife.get_workflow(wf.id).failed_reason

    def test_http_decide_no_body_backward_compat(self, client, wlife, project_id):
        """无 body POST → 200 (S9-002 兼容: reviewer=console, comment='')。"""
        _, _, gate = self._setup_gate(wlife, project_id)
        resp = client.post(f"/api/approvals/{gate.id}/approve")
        assert resp.status_code == 200
        assert resp.json()["gate"]["comment"] == ""
        assert wlife.get_approval(gate.id).reviewer == "console"

    def test_http_decide_conflict_409_with_comment(self, client, wlife, project_id):
        """终态门再决定 (带 comment) → 409 (决定不可撤销 — 审计铁律)。"""
        _, _, gate = self._setup_gate(wlife, project_id)
        assert client.post(f"/api/approvals/{gate.id}/approve", json={"comment": "确认"}).status_code == 200
        resp = client.post(f"/api/approvals/{gate.id}/reject", json={"comment": "反悔"})
        assert resp.status_code == 409
        # 首次决定 comment 不被二次请求覆盖 (终态不可撤销)
        assert wlife.get_approval(gate.id).comment == "确认"


# ------------------------------------------------------------------ 修改反馈数据流 (comment → 下轮重生成输入)


class TestReviewFeedbackFlow:
    def test_review_comment_feeds_next_generation(self, service, wlife, project_id):
        """reject comment 经 gate 存留 → 下一轮重生成输入 (数据流, 不改 Agent 核心)。

        数据流: 1) 产物挂设计确认门; 2) reject 带 comment → gate.comment 落库;
        3) 下轮重生成读取 gate.comment 为反馈输入 (仅数据流 — 读取经 org
        既有查询接口, 不触碰 Agent 核心); 4) 产物回 generated + metadata
        回注 review_feedback (重生成路径复用 S9-001 invalid→generated)。
        """
        wf = _build_chain_wf(wlife, project_id)
        artifact = _make_product_artifact(wlife, project_id, wf)
        wlife.transition_workflow(wf.id, WorkflowStatus.ACTIVE)
        gate = wlife.request_approval(artifact.stage_id)
        wlife.reject_approval(
            gate.id, reviewer="human", comment="MVP 范围过大: 移除月度报表", source="console"
        )

        # 下一轮重生成: 读取 gate.comment 为反馈输入 (org 查询接口, 数据流可达)
        feedback = wlife.get_approval(gate.id).comment
        assert feedback == "MVP 范围过大: 移除月度报表"

        # 重生成路径 (不改 Agent 核心 — 复用既有状态机): invalid→generated
        # + metadata 回注反馈 (review_feedback 标注为输入)
        wlife.registry.mark_generated(artifact.id)
        regenerated = wlife.registry.update(
            artifact.id,
            metadata={**_product_payload_ok(), "review_feedback": feedback},
        )
        assert regenerated.status.value == "generated"
        assert regenerated.metadata["review_feedback"] == feedback
        # Review 页可读: 详情 metadata 含反馈标注 (下轮 Review 可见)
        detail = service.get_artifact(artifact.id)
        assert detail is not None
        assert detail.metadata["review_feedback"] == "MVP 范围过大: 移除月度报表"
        assert detail.review is not None and detail.review.status == "rejected"
