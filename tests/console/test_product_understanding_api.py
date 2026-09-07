"""S49 / Phase 5 — Conversation Application Layer API 测试。

覆盖: 新 Conversation Domain (conv-*) 经 Application Service 暴露的端点:
- POST /api/conversations/{id}/product-understanding/messages (自然语言 → PU)
- GET  /api/conversations/{id}/product-understanding (快照)
- GET  /api/conversations/{id}/messages
- GET  /api/conversations/{id}/product-understanding/context (Context 连续性)
- POST /api/conversations/{id}/prd (PRD 派生)
- GET  /api/conversations/{id}/prd (PRD 列表/provenance)

conversation 创建经 ConversationApplicationService (domain 直建) — 与 legacy
POST /api/conversations (conversation_os conv_*) 并存不冲突 (S49 §13: API 只建
Boundary, 不一次性迁移; legacy 路由保持不动, 此处不测 legacy)。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from factory_console import conversation_app as ca  # noqa: E402
from factory_console.web.backend.fastapi_adapter import build_app  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def conv(root: str) -> dict:
    return ca.ConversationApplicationService(root).create(title="飞机大战")


@pytest.fixture()
def client(root: str) -> TestClient:
    return TestClient(build_app(None, factory_root=root))


def _feed(client: TestClient, conv_id: str, lines: list[str]) -> None:
    for line in lines:
        r = client.post(f"/api/conversations/{conv_id}/product-understanding/messages",
                        json={"message": line})
        assert r.status_code == 200, r.text


class TestPUMessages:
    def test_nl_messages_update_understanding(self, client: TestClient,
                                              conv: dict) -> None:
        _feed(client, conv["id"], [
            "我想做一个飞机大战小游戏。", "手机端。", "不要登录，打开就能玩。",
            "以后可以加排行榜。", "操作就用虚拟摇杆吧。",
        ])
        r = client.get(f"/api/conversations/{conv['id']}/product-understanding")
        assert r.status_code == 200
        snap = r.json()
        assert snap["version"] >= 5
        types = {f["type"] for f in snap["facts"]}
        assert {"IDEA", "REQUIREMENT", "CONSTRAINT", "FUTURE_IDEA", "DECISION"} <= types

    def test_unknown_conversation_404(self, client: TestClient) -> None:
        r = client.get("/api/conversations/conv-nope/product-understanding")
        assert r.status_code == 404
        r2 = client.post("/api/conversations/conv-nope/product-understanding/messages",
                         json={"message": "x"})
        assert r2.status_code == 404


class TestMessages:
    def test_messages_roundtrip(self, client: TestClient, conv: dict) -> None:
        _feed(client, conv["id"], ["手机端。"])
        r = client.get(f"/api/conversations/{conv['id']}/messages")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 2  # human + assistant reply


class TestContextContinuity:
    def test_context_includes_facts_and_messages(self, client: TestClient,
                                                 conv: dict) -> None:
        _feed(client, conv["id"], ["我想做一个飞机大战小游戏。", "手机端。"])
        r = client.get(f"/api/conversations/{conv['id']}/product-understanding/context")
        assert r.status_code == 200
        ctx = r.json()
        assert ctx["understanding_version"] >= 1
        assert any("飞机大战" in str(f["content"]) for f in ctx["facts"])
        assert ctx["by_type"]["IDEA"]


class TestPRDAPI:
    def test_prd_create_and_list(self, client: TestClient, conv: dict) -> None:
        _feed(client, conv["id"], ["我想做一个飞机大战小游戏。", "手机端。"])
        r = client.post(f"/api/conversations/{conv['id']}/prd",
                        json={"actor": "test"})
        assert r.status_code == 200, r.text
        prd = r.json()
        assert prd["version"] == 1
        assert prd["status"] == "draft"
        assert prd["source_product_understanding_version"] >= 1
        r2 = client.get(f"/api/conversations/{conv['id']}/prd")
        assert r2.status_code == 200
        assert r2.json()["count"] == 1

    def test_prd_without_understanding_400(self, client: TestClient,
                                           conv: dict) -> None:
        r = client.post(f"/api/conversations/{conv['id']}/prd")
        assert r.status_code == 400  # 无 Understanding → 拒绝派生 (诚实)


class TestUnderstandingStatementAPI:
    def test_statement_endpoint(self, client: TestClient, conv: dict) -> None:
        """Golden Path §12: 用户可见理解通过 API 暴露 (Confirmation Loop)。"""
        _feed(client, conv["id"], ["我想做一个飞机大战小游戏。", "手机端。"])
        r = client.get(
            f"/api/conversations/{conv['id']}/product-understanding/statement")
        assert r.status_code == 200
        stmt = r.json()["statement"]
        assert "我目前理解的是" in stmt
        assert "飞机大战" in stmt

    def test_gaps_endpoint(self, client: TestClient, conv: dict) -> None:
        """Golden Path §11: 主动缺口分析通过 API 暴露。"""
        _feed(client, conv["id"], ["我想做一个飞机大战小游戏。", "手机端。"])
        r = client.get(
            f"/api/conversations/{conv['id']}/product-understanding/gaps")
        assert r.status_code == 200
        assert isinstance(r.json()["gaps"], list)
