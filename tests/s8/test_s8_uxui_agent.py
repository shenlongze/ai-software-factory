"""tests/s8/test_s8_uxui_agent.py — UXUIDesignerAgent 结构化解析 (Unit, S8-002)。

覆盖 (任务清单: Product → 结构化 ux_ui / 解析链 / 垃圾拒绝 / 响亮错误):
- design: Product Artifact → UXUIArtifact (mock provider 注入合法 JSON)
- 解析宽容: ```json 围栏 / 前后散文子串回退 / 直接 JSON
- 消费 product 5 节: user_persona/user_journey/feature_list/mvp_scope/
  user_stories 内容进入 prompt (画像/旅程/功能/MVP/故事 → 设计驱动)
- 机器可读: 产物纯 JSON 结构化文本 (ASCII 布局嵌 wireframe.screens[].ascii),
  design() 零文件写入 (不生成图片文件)
- 响亮拒绝: 垃圾输出 / 非 dict / 缺 7 节 / 空节 / wireframe 深度结构失败
  (screens 非 list/空/缺 Screen 键/ascii 空/actions 非 list) / provider 缺失 /
  provider 错误 / 无 product / product 非 dict / 空响应
- prompt 组装: 含 product 摘要 + 7 节要求; max_tokens 透传
- set_product: 构造绑定 product 可替换

依赖: 本目录 conftest (pm_mock_provider) + s8_helpers。
"""

from __future__ import annotations

import json

import pytest

from exec.uxui import (
    UXUI_FIELDS,
    UXUIArtifact,
    UXUIDesignerAgent,
    UXUIDesignerError,
)

from s8_helpers import product_payload_ok, uxui_json, uxui_payload_ok

#: product 契约中 UX 消费的 5 节 (S8-001 report §S8-002 接入说明)
PRODUCT_UX_SECTIONS = (
    "user_persona",
    "user_journey",
    "feature_list",
    "mvp_scope",
    "user_stories",
)


class TestDesignHappyPath:
    def test_design_returns_uxui_artifact(self, pm_mock_provider):
        """合法 JSON → UXUIArtifact (7 节全字段)。"""
        provider = pm_mock_provider(uxui_json())
        artifact = UXUIDesignerAgent(provider, product=product_payload_ok()).design()
        assert isinstance(artifact, UXUIArtifact)
        assert artifact.information_architecture
        assert artifact.user_flow
        assert artifact.wireframe["screens"]
        assert artifact.screen_specifications
        assert artifact.component_definition
        assert artifact.design_tokens
        assert artifact.prototype

    def test_design_fenced_json(self, pm_mock_provider):
        """markdown 围栏 ```json 包裹 → 宽容剥离解析。"""
        provider = pm_mock_provider(uxui_json(fenced=True))
        artifact = UXUIDesignerAgent(
            provider, product=product_payload_ok()
        ).design()
        assert artifact.prototype

    def test_design_prose_wrapped(self, pm_mock_provider):
        """前后散文 + JSON 子串 → 子串回退解析 (不因多余文字拒绝)。"""
        provider = pm_mock_provider(uxui_json(prose=True))
        artifact = UXUIDesignerAgent(
            provider, product=product_payload_ok()
        ).design()
        assert artifact.screen_specifications

    def test_design_explicit_product_overrides_bound(self, pm_mock_provider):
        """design(product=...) 显式 product > 构造绑定 (覆盖语义)。"""
        provider = pm_mock_provider(uxui_json())
        agent = UXUIDesignerAgent(provider, product=product_payload_ok())
        other = product_payload_ok()
        other["user_persona"] = "显式传入的新画像"
        artifact = agent.design(other)
        assert artifact.prototype
        assert "显式传入的新画像" in provider.last_request.task_context

    def test_set_product_binds_default(self, pm_mock_provider):
        """set_product 绑定默认 product, 之后 design() 无参可跑 (executor 复用)。"""
        provider = pm_mock_provider(uxui_json())
        agent = UXUIDesignerAgent(provider).set_product(product_payload_ok())
        artifact = agent.design()
        assert artifact.wireframe
        assert "user_persona" in provider.last_request.task_context

    def test_prompt_contains_product_5_ux_sections(self, pm_mock_provider):
        """prompt 组装: 含 product 摘要 + UX 消费 5 节 (画像/旅程/功能/MVP/
        故事) + 7 节设计要求。"""
        provider = pm_mock_provider(uxui_json())
        payload = product_payload_ok()
        UXUIDesignerAgent(provider, product=payload).design()
        prompt = provider.last_request.task_context
        for section in PRODUCT_UX_SECTIONS:
            assert section in prompt, f"prompt 缺消费节: {section}"
        for section in UXUI_FIELDS:
            assert section in prompt, f"prompt 缺设计节: {section}"
        assert "25-40 岁上班族" in prompt  # persona 内容进入 prompt (消费证明)
        assert "支出记录" in prompt  # mvp_scope.in 内容进入 prompt

    def test_max_tokens_passthrough(self, pm_mock_provider):
        """max_tokens 构造参数透传 ProviderRequest。"""
        provider = pm_mock_provider(uxui_json())
        UXUIDesignerAgent(
            provider, product=product_payload_ok(), max_tokens=2048
        ).design()
        assert provider.last_request.max_tokens == 2048

    def test_to_dict_roundtrip(self):
        """UXUIArtifact.to_dict → from_dict 往返一致 (契约载荷)。"""
        payload = uxui_payload_ok()
        artifact = UXUIArtifact.from_dict(payload)
        assert artifact.to_dict() == payload
        assert list(artifact.to_dict()) == list(UXUI_FIELDS)

    def test_machine_readable_no_image_files(self, pm_mock_provider, tmp_path):
        """机器可读: ASCII 布局嵌 JSON (wireframe.screens[].ascii), design()
        零文件写入 — 不生成图片文件。"""
        provider = pm_mock_provider(uxui_json())
        artifact = UXUIDesignerAgent(
            provider, product=product_payload_ok()
        ).design()
        screens = artifact.wireframe["screens"]
        assert all("ascii" in s and s["ascii"] for s in screens)
        assert list(tmp_path.iterdir()) == []  # 无任何文件产出


class TestDesignLoudRejects:
    def test_garbage_output_rejected(self, pm_mock_provider):
        """垃圾输出 (无 JSON) → UXUIDesignerError 响亮 (不假装生成)。"""
        provider = pm_mock_provider("这不是 JSON, 随便一段文字")
        with pytest.raises(UXUIDesignerError, match="not valid JSON"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_non_dict_json_rejected(self, pm_mock_provider):
        """JSON 数组/标量 → 响亮拒绝 (ux_ui artifact 必须是对象)。"""
        provider = pm_mock_provider("[1, 2, 3]")
        with pytest.raises(UXUIDesignerError, match="JSON object"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_missing_section_rejected(self, pm_mock_provider):
        """缺 7 节核心字段 (如 design_tokens) → 响亮拒绝。"""
        payload = uxui_payload_ok()
        del payload["design_tokens"]
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="design_tokens"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_empty_str_section_rejected(self, pm_mock_provider):
        """prototype 空串 → 响亮拒绝 (非空约束, 同 CONTRACTS 规则)。"""
        payload = uxui_payload_ok()
        payload["prototype"] = ""
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="prototype"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screens_missing_rejected(self, pm_mock_provider):
        """wireframe 缺 screens 键 → 响亮拒绝 (结构校验)。"""
        payload = uxui_payload_ok()
        payload["wireframe"] = {"notes": "无 screens"}
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="screens"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screens_not_list_rejected(self, pm_mock_provider):
        """wireframe.screens 非 list → 响亮拒绝。"""
        payload = uxui_payload_ok()
        payload["wireframe"] = {"screens": "纯文本线框"}
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="screens"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screens_empty_rejected(self, pm_mock_provider):
        """wireframe.screens 空 list → 响亮拒绝 (每屏 ASCII 布局必给)。"""
        payload = uxui_payload_ok()
        payload["wireframe"] = {"screens": []}
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="screens"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screen_missing_ascii_rejected(self, pm_mock_provider):
        """Screen 缺 ascii (ASCII 布局) → 响亮拒绝 (机器可读线框必含)。"""
        payload = uxui_payload_ok()
        del payload["wireframe"]["screens"][0]["ascii"]
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="ascii"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screen_missing_components_rejected(self, pm_mock_provider):
        """Screen 缺 components → 响亮拒绝 (Screen 契约四键)。"""
        payload = uxui_payload_ok()
        del payload["wireframe"]["screens"][0]["components"]
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="components"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screen_actions_not_list_rejected(self, pm_mock_provider):
        """Screen.actions 非 list → 响亮拒绝。"""
        payload = uxui_payload_ok()
        payload["wireframe"]["screens"][0]["actions"] = "点击跳转"
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="actions"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_wireframe_screen_not_dict_rejected(self, pm_mock_provider):
        """Screen 非 dict → 响亮拒绝。"""
        payload = uxui_payload_ok()
        payload["wireframe"]["screens"][0] = "纯文字屏"
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="screens\\[0\\]"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_screen_specifications_empty_rejected(self, pm_mock_provider):
        """screen_specifications 空 → 响亮拒绝。"""
        payload = uxui_payload_ok()
        payload["screen_specifications"] = []
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="screen_specifications"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_design_tokens_empty_rejected(self, pm_mock_provider):
        """design_tokens 空 dict → 响亮拒绝 (设计规范必含)。"""
        payload = uxui_payload_ok()
        payload["design_tokens"] = {}
        provider = pm_mock_provider(json.dumps(payload))
        with pytest.raises(UXUIDesignerError, match="design_tokens"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_no_provider_rejected(self):
        """provider=None → 响亮拒绝 (不假装设计; 仅 DeepSeek v4-pro)。"""
        with pytest.raises(UXUIDesignerError, match="provider"):
            UXUIDesignerAgent(None, product=product_payload_ok()).design()

    def test_no_product_rejected(self, pm_mock_provider):
        """无 product (构造未绑定 + 未传参) → 响亮拒绝 (不臆造输入)。"""
        provider = pm_mock_provider(uxui_json())
        with pytest.raises(UXUIDesignerError, match="product artifact required"):
            UXUIDesignerAgent(provider).design()

    def test_non_dict_product_rejected(self, pm_mock_provider):
        """product 非 dict → 响亮拒绝 (配置错误立即暴露)。"""
        with pytest.raises(UXUIDesignerError, match="must be a dict"):
            UXUIDesignerAgent(pm_mock_provider(), product="纯文字产品")

    def test_provider_error_rejected(self, pm_mock_provider):
        """provider 调用失败 → 响亮拒绝 (error 透出)。"""
        provider = pm_mock_provider(error="upstream timeout")
        with pytest.raises(UXUIDesignerError, match="upstream timeout"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()

    def test_empty_response_rejected(self, pm_mock_provider):
        """provider 空响应 → 响亮拒绝 (不假装生成成功)。"""
        provider = pm_mock_provider("")
        with pytest.raises(UXUIDesignerError, match="empty provider response"):
            UXUIDesignerAgent(provider, product=product_payload_ok()).design()
