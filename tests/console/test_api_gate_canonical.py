"""S1 第 1 刀 — canonical API Gate 测试。

验证 /api/conversations* 已切到唯一后端链 (conversation_app / golden_path):

- A: POST /api/conversations 只创建 conv-* (不再 conv_*)
- B: messages 端点 = CanonicalGoldenPath.handle — 与 CLI 同一后端逻辑
  (同一句自然语言经 API 与经 CLI 进入同一 Domain 事实 conversations/{cid}.json)
- D: Gate 语义不因 API 放宽 — PRD 未确认不能生成 Plan, Plan 未确认不能 execute
- E: GET /status 含 tree/阶段

FACTORY_API_SEMANTIC=0 → deterministic interpreter (无 LLM 依赖, 可复现)。
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

from factory_console import product_understanding as pu  # noqa: E402
from factory_console.web.backend.fastapi_adapter import build_app  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> str:
    return str(tmp_path / "factory")


@pytest.fixture()
def client(root: str, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FACTORY_API_SEMANTIC", "0")  # deterministic (无 LLM)
    return TestClient(build_app(None, factory_root=root))


def _new_conv(client: TestClient, title: str = "飞机大战") -> dict:
    r = client.post("/api/conversations", json={"title": title})
    assert r.status_code == 200, r.text
    return r.json()


def _say(client: TestClient, cid: str, text: str) -> dict:
    r = client.post(f"/api/conversations/{cid}/messages", json={"message": text})
    assert r.status_code == 200, r.text
    return r.json()


class TestCanonicalConversationAPI:
    def test_create_is_conv_dash(self, client: TestClient) -> None:
        """A: 只能创建 conv-*。"""
        conv = _new_conv(client)
        assert conv["id"].startswith("conv-"), conv["id"]
        assert not conv["id"].startswith("conv_")

    def test_messages_share_domain_facts_with_cli(self, client: TestClient,
                                                  root: str) -> None:
        """B: 同一句自然语言经 API 进入 conversations/{cid}.json (同 CLI 事实)。"""
        conv = _new_conv(client, "飞机大战")
        cid = conv["id"]
        body = _say(client, cid, "我想做一个飞机大战小游戏。")
        assert body["kind"] == "chat"
        body2 = _say(client, cid, "手机端。")
        assert body2["kind"] == "chat"
        # Domain 事实落盘 — 与 CLI (canonical shell → 同一 conversation_app) 同源
        conv_doc = pu.get_conversation(root, cid)
        assert conv_doc is not None
        facts = pu.list_facts(root, cid)
        contents = " ".join(str(f.get("content", "")) for f in facts)
        assert "飞机大战" in contents
        assert "手机端" in contents or "手机" in contents


class TestGateSemantics:
    def test_prd_not_confirmed_no_plan(self, client: TestClient) -> None:
        """D: PRD 未确认 → generate_plan 被 Gate 拒绝。"""
        conv = _new_conv(client)
        cid = conv["id"]
        _say(client, cid, "我想做一个飞机大战小游戏。")
        _say(client, cid, "手机端。")
        # 生成 PRD
        r = client.post(f"/api/conversations/{cid}/prd")
        assert r.status_code == 200
        assert r.json()["kind"] == "lifecycle"
        # 未 approve → plan 被拒
        r2 = client.post(f"/api/conversations/{cid}/plan")
        assert r2.status_code == 200
        body = r2.json()
        assert body["kind"] == "gate", body
        assert "确认" in body["reply"] or "PRD" in body["reply"]

    def test_plan_not_confirmed_no_execute(self, client: TestClient) -> None:
        """D: Plan 未确认 → execute 被 Gate 拒绝。"""
        conv = _new_conv(client)
        cid = conv["id"]
        _say(client, cid, "我想做一个飞机大战小游戏。")
        _say(client, cid, "手机端。")
        client.post(f"/api/conversations/{cid}/prd")
        r = client.post(f"/api/conversations/{cid}/prd/approve")
        assert r.status_code == 200 and r.json()["kind"] == "lifecycle"
        client.post(f"/api/conversations/{cid}/plan")
        # 未 approve plan → execute 被拒
        r2 = client.post(f"/api/conversations/{cid}/execute")
        assert r2.status_code == 200
        body = r2.json()
        assert body["kind"] == "gate", body
        assert "Plan" in body["reply"] or "计划" in body["reply"]

    def test_full_gate_chain_after_approvals(self, client: TestClient) -> None:
        """Gate 链: approve PRD + approve Plan 后, status 显示可执行阶段。"""
        conv = _new_conv(client)
        cid = conv["id"]
        _say(client, cid, "我想做一个飞机大战小游戏。")
        _say(client, cid, "手机端。")
        # PRD
        r = client.post(f"/api/conversations/{cid}/prd")
        assert r.json()["kind"] == "lifecycle"
        r = client.post(f"/api/conversations/{cid}/prd/approve")
        assert r.json()["kind"] == "lifecycle"
        # Plan
        r = client.post(f"/api/conversations/{cid}/plan")
        assert r.json()["kind"] == "lifecycle", r.json()
        r = client.post(f"/api/conversations/{cid}/plan/approve")
        assert r.json()["kind"] == "lifecycle"
        # status 含阶段 + 树
        r = client.get(f"/api/conversations/{cid}/status")
        assert r.status_code == 200
        st = r.json()
        assert "stage" in st
        assert "tree" in st
        assert st["tree"] is not None or st["tree"] == {}


class TestLegacyFrozen:
    def test_requirements_410(self, client: TestClient) -> None:
        """C: requirements/decisions → 410 legacy FROZEN 指引。"""
        conv = _new_conv(client)
        cid = conv["id"]
        r = client.post(f"/api/conversations/{cid}/requirements",
                        json={"title": "需求 A"})
        assert r.status_code == 410
        err = r.json()["error"]
        msg = str(err.get("message", "")) + str(err.get("detail", ""))
        assert "废弃" in msg or "FROZEN" in msg
        r2 = client.post(f"/api/conversations/{cid}/decisions",
                         json={"statement": "x"})
        assert r2.status_code == 410
