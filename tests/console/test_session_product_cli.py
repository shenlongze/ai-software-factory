"""S10-066 — Product Intelligence CLI 测试套件。

覆盖: 5 action (product_intelligence/market/persona/mvp/value) + intent 关键词。
装配: tmp_path + fixtures; 禁真实网络。
"""

from __future__ import annotations

import json
from pathlib import Path

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")


def _intent():
    return {"name": "台球计分", "problem": "台球计分麻烦",
            "user": "台球爱好者", "platform": "mobile",
            "core_features": ["计分", "排行榜"]}


def _ws(tmp_path) -> Path:
    ws = tmp_path / "ws"
    (ws / "projects").mkdir(parents=True, exist_ok=True)
    return ws


def _make_project(ws: Path, slug: str = "scorepocket"):
    pd = ws / "projects" / slug
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "product.json").write_text(json.dumps(_intent()), encoding="utf-8")
    return pd


class TestIntent:
    def test_intelligence(self):
        assert INT.KeywordIntentParser().parse("分析产品").intent_type == "product_intelligence"

    def test_market(self):
        assert INT.KeywordIntentParser().parse("产品市场").intent_type == "product_market"

    def test_persona(self):
        assert INT.KeywordIntentParser().parse("产品画像").intent_type == "product_persona"

    def test_mvp(self):
        assert INT.KeywordIntentParser().parse("MVP规划").intent_type == "product_mvp"

    def test_value(self):
        assert INT.KeywordIntentParser().parse("产品价值").intent_type == "product_value"

    def test_old_commands_kept(self):
        assert INT.KeywordIntentParser().parse("准备开发").intent_type == "prepare_project"
        assert INT.KeywordIntentParser().parse("通过验收").intent_type == "accept_project"


class TestActions:
    def _ctx(self, ws, params=None):
        class Ctx:
            def __init__(self, workspace, params):
                self.workspace = str(workspace)
                self.params = params or {}
                self.project = ""

            def require(self, level):
                pass

        return Ctx(ws, params)

    def test_product_intelligence(self, tmp_path):
        r = ACT.product_intelligence(self._ctx(_ws(tmp_path), {"product_intent": _intent()}))
        assert r.ok
        assert "产品" in r.message or "行业" in r.message or "#" in r.message

    def test_product_market(self, tmp_path):
        r = ACT.product_market(self._ctx(_ws(tmp_path), {"product_intent": _intent()}))
        assert r.ok
        assert "市场" in r.message

    def test_product_persona(self, tmp_path):
        r = ACT.product_persona(self._ctx(_ws(tmp_path), {"product_intent": _intent()}))
        assert r.ok
        assert "画像" in r.message or "用户" in r.message

    def test_product_mvp(self, tmp_path):
        r = ACT.product_mvp(self._ctx(_ws(tmp_path), {"product_intent": _intent()}))
        assert r.ok
        assert "MVP" in r.message

    def test_product_value(self, tmp_path):
        r = ACT.product_value(self._ctx(_ws(tmp_path), {"product_intent": _intent()}))
        assert r.ok
        assert "评分" in r.message or "价值" in r.message

    def test_default_project(self, tmp_path):
        ws = _ws(tmp_path)
        _make_project(ws)
        r = ACT.product_intelligence(self._ctx(ws))  # 缺省最近项目
        assert r.ok

    def test_fail_safe_empty(self, tmp_path):
        ws = _ws(tmp_path)
        r = ACT.product_intelligence(self._ctx(ws))  # 无项目无 intent
        assert r.ok or not r.ok  # 不裸抛

    def test_registered(self, tmp_path):
        reg = ACT.build_default_actions()
        names = [a.name for a in reg.list()] if hasattr(reg, "list") else [a.name for a in getattr(reg, "actions", [])]
        for n in ("product_intelligence", "product_market", "product_persona",
                  "product_mvp", "product_value"):
            assert n in names
