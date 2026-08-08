"""tests/s8/test_s8_pm_agent.py — PMAgent 结构化解析 (Unit, S8-001)。

覆盖 (任务清单: 结构化解析 — markdown 围栏/JSON 提取/垃圾输出响亮拒绝):
- develop: Idea → ProductArtifact (mock provider 注入合法 JSON)
- 解析宽容: ```json 围栏 / 前后散文子串回退 / 直接 JSON
- 响亮拒绝: 垃圾输出 / 非 dict / 缺 7 节核心字段 / mvp_scope 缺 in|out /
  feature_list 空 / user_stories 空 / provider 缺失 / provider 错误 / 无 idea
- prompt 组装: 含 idea 文本 + 7 节要求; max_tokens 透传
- set_idea: 构造绑定想法可替换

依赖: 本目录 conftest (pm_mock_provider) + s8_helpers。
"""

from __future__ import annotations

import json

import pytest

from exec.pm import (
    PRODUCT_FIELDS,
    PMAgent,
    ProductArtifact,
    ProductManagerError,
)

from s8_helpers import product_json, product_payload_ok


class TestDevelopHappyPath:
    def test_develop_returns_product_artifact(self, pm_mock_provider):
        """合法 JSON → ProductArtifact (7 节全字段)。"""
        provider = pm_mock_provider(product_json())
        artifact = PMAgent(provider, idea="记账 App").develop()
        assert isinstance(artifact, ProductArtifact)
        assert artifact.market_analysis
        assert artifact.user_persona
        assert artifact.user_journey
        assert artifact.problem_statement
        assert artifact.feature_list
        assert artifact.mvp_scope["in"] and artifact.mvp_scope["out"]
        assert artifact.user_stories

    def test_develop_fenced_json(self, pm_mock_provider):
        """markdown 围栏 ```json 包裹 → 宽容剥离解析。"""
        provider = pm_mock_provider(product_json(fenced=True))
        artifact = PMAgent(provider, idea="x").develop()
        assert artifact.market_analysis

    def test_develop_prose_wrapped(self, pm_mock_provider):
        """前后散文 + JSON 子串 → 子串回退解析 (不因多余文字拒绝)。"""
        provider = pm_mock_provider(product_json(prose=True))
        artifact = PMAgent(provider, idea="x").develop()
        assert artifact.problem_statement

    def test_develop_explicit_idea_overrides_bound(self, pm_mock_provider):
        """develop(idea=...) 显式想法 > 构造绑定 (覆盖语义)。"""
        provider = pm_mock_provider(product_json())
        pm = PMAgent(provider, idea="旧想法")
        artifact = pm.develop("新想法")
        assert artifact.feature_list
        assert "新想法" in provider.last_request.task_context

    def test_set_idea_binds_default(self, pm_mock_provider):
        """set_idea 绑定默认想法, 之后 develop() 无参可跑 (executor 复用)。"""
        provider = pm_mock_provider(product_json())
        pm = PMAgent(provider).set_idea("记账 Web App")
        artifact = pm.develop()
        assert artifact.user_stories
        assert "记账 Web App" in provider.last_request.task_context

    def test_prompt_contains_idea_and_7_sections(self, pm_mock_provider):
        """prompt 组装: 含用户想法 + 7 节产品分析要求。"""
        provider = pm_mock_provider(product_json())
        PMAgent(provider).develop("做一个极简记账应用")
        prompt = provider.last_request.task_context
        assert "做一个极简记账应用" in prompt
        for section in PRODUCT_FIELDS:
            assert section in prompt
        assert "mvp_scope" in prompt and "in/out" in prompt

    def test_max_tokens_passthrough(self, pm_mock_provider):
        """max_tokens 构造参数透传 ProviderRequest。"""
        provider = pm_mock_provider(product_json())
        PMAgent(provider, idea="x", max_tokens=2048).develop()
        assert provider.last_request.max_tokens == 2048

    def test_to_dict_roundtrip(self):
        """ProductArtifact.to_dict → from_dict 往返一致 (契约载荷)。"""
        payload = product_payload_ok()
        artifact = ProductArtifact.from_dict(payload)
        assert artifact.to_dict() == payload
        assert list(artifact.to_dict()) == list(PRODUCT_FIELDS)


class TestDevelopLoudRejects:
    def test_garbage_output_rejected(self, pm_mock_provider):
        """垃圾输出 (无 JSON) → ProductManagerError 响亮 (不假装生成)。"""
        provider = pm_mock_provider("这不是 JSON, 随便一段文字")
        with pytest.raises(ProductManagerError, match="not valid JSON"):
            PMAgent(provider, idea="x").develop()

    def test_non_dict_json_rejected(self, pm_mock_provider):
        """JSON 数组/标量 → 响亮拒绝 (product artifact 必须是对象)。"""
        provider = pm_mock_provider("[1, 2, 3]")
        with pytest.raises(ProductManagerError, match="JSON object"):
            PMAgent(provider, idea="x").develop()

    def test_missing_section_rejected(self, pm_mock_provider):
        """缺 7 节核心字段 (如 problem_statement) → 响亮拒绝。"""
        payload = product_payload_ok()
        del payload["problem_statement"]
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(ProductManagerError, match="problem_statement"):
            PMAgent(provider, idea="x").develop()

    def test_empty_str_section_rejected(self, pm_mock_provider):
        """str 节空串 → 响亮拒绝 (非空约束, 同 CONTRACTS 规则)。"""
        payload = product_payload_ok()
        payload["market_analysis"] = ""
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(ProductManagerError, match="market_analysis"):
            PMAgent(provider, idea="x").develop()

    def test_mvp_scope_missing_out_rejected(self, pm_mock_provider):
        """mvp_scope 缺 out → 响亮拒绝 (in/out 边界必含)。"""
        payload = product_payload_ok()
        payload["mvp_scope"] = {"in": ["a"]}
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(ProductManagerError, match="mvp_scope"):
            PMAgent(provider, idea="x").develop()

    def test_feature_list_empty_rejected(self, pm_mock_provider):
        """feature_list 空 → 响亮拒绝 (min_items 约束)。"""
        payload = product_payload_ok()
        payload["feature_list"] = []
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(ProductManagerError, match="feature_list"):
            PMAgent(provider, idea="x").develop()

    def test_user_stories_empty_rejected(self, pm_mock_provider):
        """user_stories 空 → 响亮拒绝。"""
        payload = product_payload_ok()
        payload["user_stories"] = []
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(ProductManagerError, match="user_stories"):
            PMAgent(provider, idea="x").develop()

    def test_no_provider_rejected(self):
        """provider=None → 响亮拒绝 (不假装分析; 仅 DeepSeek v4-pro)。"""
        with pytest.raises(ProductManagerError, match="provider"):
            PMAgent(None, idea="x").develop()

    def test_no_idea_rejected(self, pm_mock_provider):
        """无想法 (构造未绑定 + 未传参) → 响亮拒绝 (不臆造输入)。"""
        provider = pm_mock_provider(product_json())
        with pytest.raises(ProductManagerError, match="idea required"):
            PMAgent(provider).develop()

    def test_provider_error_rejected(self, pm_mock_provider):
        """provider 调用失败 → 响亮拒绝 (error 透出)。"""
        provider = pm_mock_provider(error="upstream timeout")
        with pytest.raises(ProductManagerError, match="upstream timeout"):
            PMAgent(provider, idea="x").develop()

    def test_empty_response_rejected(self, pm_mock_provider):
        """provider 空响应 → 响亮拒绝 (不假装生成成功)。"""
        provider = pm_mock_provider("")
        with pytest.raises(ProductManagerError, match="empty provider response"):
            PMAgent(provider, idea="x").develop()
