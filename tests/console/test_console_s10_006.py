"""tests/console/test_console_s10_006.py — S10-006 Review Workflow (后端验收)。

覆盖 (Review Feedback Loop — Reject 意见结构化落库 + 两端点):
- ReviewFeedbackStore: save/get round-trip / next_round 递增 / 按产物 round
  升序 / 跨实例持久化 / 同 id 幂等覆盖 / 损坏文件响亮异常 / 缺文件空库
- ConsoleService: save round 按产物递增 / 空意见拒绝 (None, 不落库) /
  意见 trim / 缺 store 失败安全 (None) / list gate_id 过滤 / 缺 store 空列表
- HTTP (build_app + TestClient): POST 保存 (200, round=1) / 空意见 400 /
  缺 artifact_id 400 / 缺 store 503 (失败安全) / GET artifact+gate 过滤 /
  缺 store GET → [] / console.viewed 审计 (view=review_feedback)
- Adapter 装配: build_console_service 把 review_feedback_store 传入
  ConsoleService (S10-006 续跑缺口 — 传参修复验收)

本目录自洽 (conftest 已挂 factory-core + 仓库根; 本文件补 factory-org —
同 tests/console/test_console_s10_005.py 装配); basename 全仓库唯一
(test_console_* 前缀)。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _pkg in ("factory-org",):
    _dir = _ROOT / _pkg
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest

_console = importlib.import_module("factory-console")
_models = importlib.import_module("factory-console.models")
_feedback = importlib.import_module("factory-console.review_feedback")
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

ReviewFeedback = _models.ReviewFeedback
ReviewFeedbackStore = _feedback.ReviewFeedbackStore


def _record(**overrides: Any) -> ReviewFeedback:
    """反馈记录工厂 (固定 id/时间戳 — 确定性断言)。"""
    fields: dict[str, Any] = dict(
        id="fb-1",
        gate_id="gate-a",
        artifact_id="art-a",
        reviewer="console",
        comment="MVP 范围过大, 请重做",
        round=1,
        created_at="2026-08-10T00:00:00+00:00",
    )
    fields.update(overrides)
    return ReviewFeedback(**fields)


# ------------------------------------------------------------------ Store 层


class TestReviewFeedbackStore:
    def test_store_save_get_roundtrip(self, tmp_path: Path):
        """save → get 原样返回 (字段逐项一致)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        record = _record()
        store.save(record)
        loaded = store.get("fb-1")
        assert loaded is not None
        assert loaded.to_dict() == record.to_dict()

    def test_store_next_round_increments(self, tmp_path: Path):
        """next_round: 无记录 → 1; 保存后 → 2 (round 按产物递增)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        assert store.next_round("art-a") == 1
        store.save(_record())
        assert store.next_round("art-a") == 2
        # 其他产物不受影响 (round 按 artifact_id 独立递增)
        assert store.next_round("art-b") == 1

    def test_store_list_by_artifact_round_asc(self, tmp_path: Path):
        """按产物列出, round 升序 (下轮输入按序消费)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        store.save(_record(id="fb-2", round=2))
        store.save(_record(id="fb-1", round=1))
        store.save(_record(id="fb-x", artifact_id="art-b"))
        ids = [r.id for r in store.list_by_artifact("art-a")]
        assert ids == ["fb-1", "fb-2"]
        assert store.list_by_artifact("art-nope") == []

    def test_store_persists_across_instances(self, tmp_path: Path):
        """跨实例持久化: 新 store 实例读同一目录 → 记录仍在 (落盘)。"""
        dir_path = tmp_path / "fb"
        ReviewFeedbackStore(dir_path).save(_record())
        fresh = ReviewFeedbackStore(dir_path)
        assert fresh.count() == 1
        assert fresh.get("fb-1").comment == "MVP 范围过大, 请重做"

    def test_store_idempotent_overwrite(self, tmp_path: Path):
        """同 id 覆盖 = 幂等重放 (记录数不变, 内容更新)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        store.save(_record())
        store.save(_record(comment="第二轮意见"))
        assert store.count() == 1
        assert store.get("fb-1").comment == "第二轮意见"

    def test_store_corrupt_file_raises(self, tmp_path: Path):
        """损坏存储文件 → 响亮 CorruptReviewFeedbackError (绝不静默丢数据)。"""
        dir_path = tmp_path / "fb"
        dir_path.mkdir(parents=True)
        (dir_path / "review_feedback.json").write_text("{not json", encoding="utf-8")
        store = ReviewFeedbackStore(dir_path)
        with pytest.raises(_feedback.CorruptReviewFeedbackError):
            store.list_all()

    def test_store_missing_file_empty(self, tmp_path: Path):
        """文件不存在 (首写前) → 空库合法状态 (list_all [] / count 0)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        assert store.list_all() == []
        assert store.count() == 0
        assert store.get("nope") is None


# ------------------------------------------------------------------ Service 层


class TestReviewFeedbackService:
    def test_service_save_round_increments(self, tmp_path: Path):
        """同产物两次保存 → round 1, 2 (下轮重生成输入按序递增)。"""
        service = _console.ConsoleService(
            review_feedback_store=ReviewFeedbackStore(tmp_path / "fb")
        )
        first = service.save_review_feedback(
            gate_id="gate-a", artifact_id="art-a", reviewer="console", comment="第一轮意见"
        )
        second = service.save_review_feedback(
            gate_id="gate-a", artifact_id="art-a", reviewer="console", comment="第二轮意见"
        )
        assert first is not None and first.round == 1
        assert second is not None and second.round == 2
        assert second.id != first.id

    def test_service_save_empty_comment_none(self, tmp_path: Path):
        """空意见 → None (无反馈不落库, 诚实边界)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        service = _console.ConsoleService(review_feedback_store=store)
        assert (
            service.save_review_feedback(
                gate_id="gate-a", artifact_id="art-a", comment="   "
            )
            is None
        )
        assert store.count() == 0

    def test_service_save_trims_comment(self, tmp_path: Path):
        """意见首尾空白被裁剪后落库 (内容归一)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        service = _console.ConsoleService(review_feedback_store=store)
        record = service.save_review_feedback(
            gate_id="gate-a", artifact_id="art-a", comment="  请重做  "
        )
        assert record is not None
        assert record.comment == "请重做"

    def test_service_save_missing_store_none(self):
        """缺 store → None (失败安全 — 审批决定不受反馈保存失败影响)。"""
        service = _console.ConsoleService()
        assert (
            service.save_review_feedback(
                gate_id="gate-a", artifact_id="art-a", comment="意见"
            )
            is None
        )

    def test_service_list_gate_filter(self, tmp_path: Path):
        """list 按 artifact + gate 过滤 (round 升序)。"""
        store = ReviewFeedbackStore(tmp_path / "fb")
        store.save(_record(id="fb-1", gate_id="gate-a", artifact_id="art-a", round=1))
        store.save(_record(id="fb-2", gate_id="gate-b", artifact_id="art-a", round=2))
        service = _console.ConsoleService(review_feedback_store=store)
        assert [r.id for r in service.list_review_feedback("art-a")] == ["fb-1", "fb-2"]
        assert [r.id for r in service.list_review_feedback("art-a", gate_id="gate-b")] == ["fb-2"]
        assert service.list_review_feedback("art-a", gate_id="gate-nope") == []
        assert [r.id for r in service.list_review_feedback()] == ["fb-1", "fb-2"]

    def test_service_list_missing_store_empty(self):
        """缺 store → [] (失败安全, 读命令永不因数据缺失失败)。"""
        service = _console.ConsoleService()
        assert service.list_review_feedback("art-a") == []


# ------------------------------------------------------------------ HTTP 层


@pytest.fixture
def service(tmp_path: Path):
    """注入真实 ReviewFeedbackStore 的 ConsoleService (独立数据空间)。"""
    return _console.ConsoleService(
        review_feedback_store=ReviewFeedbackStore(tmp_path / "review_feedback")
    )


@pytest.fixture
def client(service, event_logger):
    """真实服务 + EventLogger 的 TestClient (HTTP 集成断言)。"""
    pytest.importorskip("fastapi")
    app = _adapter.build_app(service, event_logger=event_logger)
    with TestClient(app) as c:
        yield c


@requires_fastapi
class TestReviewFeedbackHttp:
    def test_http_post_saves_record(self, client, service, tmp_path: Path):
        """POST /api/review-feedback → 200: 记录落库 (round=1 首轮)。"""
        resp = client.post(
            "/api/review-feedback",
            json={
                "artifact_id": "art-a",
                "gate_id": "gate-a",
                "reviewer": "console",
                "comment": "MVP 范围过大, 请重做",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["artifact_id"] == "art-a"
        assert body["gate_id"] == "gate-a"
        assert body["round"] == 1
        assert body["comment"] == "MVP 范围过大, 请重做"
        assert body["id"].startswith("fb-")
        # 真实落盘 (独立数据空间文件)
        store_path = tmp_path / "review_feedback" / "review_feedback.json"
        assert store_path.exists()
        assert service.list_review_feedback("art-a")[0].id == body["id"]

    def test_http_post_round_increments(self, client):
        """同产物第二次 POST → round 2 (round 按产物递增)。"""
        for comment in ("第一轮", "第二轮"):
            resp = client.post(
                "/api/review-feedback",
                json={"artifact_id": "art-a", "gate_id": "gate-a", "comment": comment},
            )
            assert resp.status_code == 200
        rounds = [r["round"] for r in client.get("/api/review-feedback?artifact_id=art-a").json()]
        assert rounds == [1, 2]

    def test_http_post_empty_comment_400(self, client):
        """空意见 → 400 (无反馈不落库, 诚实边界)。"""
        resp = client.post(
            "/api/review-feedback",
            json={"artifact_id": "art-a", "gate_id": "gate-a", "comment": "   "},
        )
        assert resp.status_code == 400
        assert "comment" in resp.json()["detail"]

    def test_http_post_missing_artifact_id_400(self, client):
        """缺 artifact_id → 400 (round 按产物递增, 无产物无意义)。"""
        resp = client.post(
            "/api/review-feedback",
            json={"artifact_id": "  ", "gate_id": "gate-a", "comment": "意见"},
        )
        assert resp.status_code == 400
        assert "artifact_id" in resp.json()["detail"]

    def test_http_post_missing_store_503(self):
        """缺 store → 503 (失败安全: 审批决定不受反馈保存失败影响)。"""
        pytest.importorskip("fastapi")
        app = _adapter.build_app(_console.ConsoleService())
        with TestClient(app) as c:
            resp = c.post(
                "/api/review-feedback",
                json={"artifact_id": "art-a", "gate_id": "gate-a", "comment": "意见"},
            )
        assert resp.status_code == 503

    def test_http_get_filters_by_artifact_and_gate(self, client, service):
        """GET ?artifact_id=&gate_id= 过滤 (无过滤 → 全库)。"""
        service.save_review_feedback(
            gate_id="gate-a", artifact_id="art-a", comment="意见A"
        )
        service.save_review_feedback(
            gate_id="gate-b", artifact_id="art-a", comment="意见B"
        )
        service.save_review_feedback(
            gate_id="gate-c", artifact_id="art-b", comment="意见C"
        )
        assert len(client.get("/api/review-feedback").json()) == 3
        art_a = client.get("/api/review-feedback?artifact_id=art-a").json()
        assert [r["comment"] for r in art_a] == ["意见A", "意见B"]
        gate_b = client.get(
            "/api/review-feedback?artifact_id=art-a&gate_id=gate-b"
        ).json()
        assert [r["comment"] for r in gate_b] == ["意见B"]
        assert client.get("/api/review-feedback?gate_id=gate-c").json()[0]["artifact_id"] == "art-b"

    def test_http_get_no_store_empty(self):
        """缺 store → GET 200 [] (失败安全空态)。"""
        pytest.importorskip("fastapi")
        app = _adapter.build_app(_console.ConsoleService())
        with TestClient(app) as c:
            resp = c.get("/api/review-feedback?artifact_id=art-a")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_http_get_audit_view(self, client, event_store):
        """命中 GET 端点 → console.viewed (view=review_feedback) 只读审计。"""
        client.get("/api/review-feedback?artifact_id=art-a")
        views = [
            ev.payload.get("view")
            for ev in event_store.query()
            if ev.type.value == "console.viewed"
        ]
        assert "review_feedback" in views


# ------------------------------------------------------------------ Adapter 装配 (传参验收)


class TestAdapterWiring:
    def test_build_console_service_wires_review_feedback_store(self, tmp_path: Path):
        """S10-006 续跑缺口修复: build_console_service 必须把装配好的
        review_feedback_store 传入 ConsoleService (此前只装配未传参 → 反馈
        保存/查询永远按空处理)。"""
        root = tmp_path / "factory"
        service = _adapter.build_console_service(root)
        assert service._review_feedback_store is not None
        # 端到端: 经装配服务保存 → 真实落盘到 <root>/review_feedback.json
        record = service.save_review_feedback(
            gate_id="gate-a", artifact_id="art-a", comment="装配验收意见"
        )
        assert record is not None
        assert record.round == 1
        store_path = root / "review_feedback.json"
        assert store_path.exists()
        assert service.list_review_feedback("art-a")[0].comment == "装配验收意见"
