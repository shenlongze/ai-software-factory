"""tests/s8/test_s8_arch_agent.py — ArchitectAgent (Unit, S8-003)。

覆盖 (任务清单: ArchitectAgent 双输入强校验 + 解析链/垃圾拒绝/响亮错误):
- happy path: Product + UX/UI 双输入 → DesignArtifact 7 节全字段
- 宽容解析: markdown 围栏剥离 / 散文包裹 / 覆盖绑定 (design 参数优先)
- 双输入强校验: 构造缺 product / 缺 ux_ui / 空 dict / 非 dict →
  ArchitectError 响亮 (禁止脱离输入独立生成)
- set_product / set_ux_ui 空输入拒绝 (不变量全入口生效)
- 本地校验 (exec 侧同 CONTRACTS 规则): 缺 7 节字段 / 空节 / api_design
  缺 endpoints / endpoints 深度 / task_breakdown 深度 (module/task/
  api_contract/ui_guidance — Developer 消费)
- 垃圾响亮拒绝: 非 JSON / 非对象 / 缺字段 → ArchitectError
- provider 缺失 / provider 错误 → ArchitectError (不假装生成成功)
- 双输入消费证明: prompt 含 product (功能/MVP) + ux_ui (屏幕/组件) 内容

依赖: 本目录 conftest (pm_mock_provider) + s8_helpers。
"""

from __future__ import annotations

import json

import pytest

from exec.architect import (
    DESIGN_FIELDS,
    ArchitectAgent,
    ArchitectError,
    build_arch_executor,
)

from s8_helpers import (
    design_json,
    design_payload_ok,
    product_payload_ok,
    uxui_payload_ok,
)

#: task_breakdown 每项必含键 (Developer 消费: 模块/API 约定/UI 实现指导)
TASK_KEYS = ("module", "task", "api_contract", "ui_guidance")


def _agent(provider, **kwargs) -> ArchitectAgent:
    """双输入齐备的 ArchitectAgent (product + ux_ui 契约载荷)。"""
    return ArchitectAgent(
        provider,
        product=kwargs.pop("product", product_payload_ok()),
        ux_ui=kwargs.pop("ux_ui", uxui_payload_ok()),
        **kwargs,
    )


class TestDoubleInputStrongValidation:
    def test_construct_requires_both_inputs(self):
        """构造强校验: 缺任一输入 → ArchitectError (禁止脱离独立生成)。"""
        with pytest.raises(ArchitectError, match="product"):
            ArchitectAgent(None, ux_ui=uxui_payload_ok())
        with pytest.raises(ArchitectError, match="ux_ui"):
            ArchitectAgent(None, product=product_payload_ok())
        with pytest.raises(ArchitectError, match="product"):
            ArchitectAgent(None)

    def test_construct_rejects_empty_inputs(self):
        """空 dict / 非 dict 输入 → ArchitectError (强校验不变量)。"""
        with pytest.raises(ArchitectError, match="empty"):
            ArchitectAgent(None, product={}, ux_ui=uxui_payload_ok())
        with pytest.raises(ArchitectError, match="empty"):
            ArchitectAgent(None, product=product_payload_ok(), ux_ui={})
        with pytest.raises(ArchitectError, match="must be a dict"):
            ArchitectAgent(None, product="text", ux_ui=uxui_payload_ok())

    def test_set_product_rejects_empty(self):
        """set_product 空输入拒绝 (强校验全入口生效, 不变量永不被打破)。"""
        agent = _agent(None)
        with pytest.raises(ArchitectError):
            agent.set_product({})
        with pytest.raises(ArchitectError):
            agent.set_ux_ui(None)

    def test_bound_inputs_always_present(self):
        """构造后双输入恒存在 (design 永不缺输入 — 禁止脱离独立生成)。"""
        agent = _agent(None)
        assert agent.product
        assert agent.ux_ui


class TestHappyPath:
    def test_design_7_sections(self, pm_mock_provider):
        """双输入 → DesignArtifact: 7 节全字段 (契约载荷)。"""
        agent = _agent(pm_mock_provider(design_json()))
        artifact = agent.design()
        assert list(artifact.to_dict()) == list(DESIGN_FIELDS)
        assert artifact.system_architecture
        assert artifact.technical_stack
        assert artifact.database_design
        assert artifact.api_design["endpoints"]
        assert artifact.frontend_architecture
        assert artifact.backend_architecture
        assert artifact.task_breakdown

    def test_fenced_json(self, pm_mock_provider):
        artifact = _agent(pm_mock_provider(design_json(fenced=True))).design()
        assert artifact.system_architecture

    def test_prose_wrapped_json(self, pm_mock_provider):
        artifact = _agent(pm_mock_provider(design_json(prose=True))).design()
        assert artifact.system_architecture

    def test_design_args_override_bound(self, pm_mock_provider):
        """双输入解析链: design(product, ux_ui) 显式参数 > 构造绑定。"""
        provider = pm_mock_provider(design_json())
        agent = _agent(provider)
        artifact = agent.design(product_payload_ok(), uxui_payload_ok())
        assert artifact.task_breakdown

    def test_max_tokens_passthrough(self, pm_mock_provider):
        provider = pm_mock_provider(design_json())
        _agent(provider, max_tokens=2048).design()
        assert provider.last_request.max_tokens == 2048

    def test_prompt_consumes_both_inputs(self, pm_mock_provider):
        """双输入消费证明: prompt 含 product (功能/MVP) + ux_ui (屏幕/组件)
        内容 — 架构师基于双产物设计, 不凭空生成。"""
        provider = pm_mock_provider(design_json())
        _agent(provider).design()
        ctx = provider.last_request.task_context
        assert "个人记账" in ctx  # product 画像
        assert "支出记录" in ctx  # product mvp_scope
        assert "screen_1" in ctx  # ux_ui 屏幕
        assert "BalanceCard" in ctx  # ux_ui 组件

    def test_prompt_truncates_long_inputs(self, pm_mock_provider):
        """超长输入截断 (防上下文撑爆; 双输入各自截断)。"""
        big_product = product_payload_ok()
        big_product["feature_list"] = ["长功能"] * 5000
        provider = pm_mock_provider(design_json())
        _agent(provider, product=big_product).design()
        assert len(provider.last_request.task_context) < 30000


class TestLoudRejection:
    def test_bad_llm_output_not_json(self, pm_mock_provider):
        """垃圾输出 (不可解析) → ArchitectError 响亮 (不假装生成成功)。"""
        agent = _agent(pm_mock_provider("这不是 JSON, 随便一段文字"))
        with pytest.raises(ArchitectError, match="not valid JSON"):
            agent.design()

    def test_llm_output_not_object(self, pm_mock_provider):
        agent = _agent(pm_mock_provider("[1, 2, 3]"))
        with pytest.raises(ArchitectError, match="JSON object"):
            agent.design()

    def test_missing_required_fields(self, pm_mock_provider):
        """LLM 输出缺核心字段 (api_design) → 响亮拒绝。注: design_json(**p)
        无法表达"删除字段" (override 只增改), 此处直接序列化缺字段载荷。"""
        payload = design_payload_ok()
        del payload["api_design"]
        agent = _agent(pm_mock_provider(json.dumps(payload, ensure_ascii=False)))
        with pytest.raises(ArchitectError, match="api_design"):
            agent.design()

    def test_empty_section_loud(self, pm_mock_provider):
        payload = design_payload_ok()
        payload["system_architecture"] = "   "
        agent = _agent(pm_mock_provider(design_json(**payload)))
        with pytest.raises(ArchitectError, match="system_architecture"):
            agent.design()

    def test_api_design_missing_endpoints_loud(self, pm_mock_provider):
        payload = design_payload_ok()
        payload["api_design"] = {"base_url": "/api"}
        agent = _agent(pm_mock_provider(design_json(**payload)))
        with pytest.raises(ArchitectError, match="endpoints"):
            agent.design()

    def test_endpoint_missing_keys_loud(self, pm_mock_provider):
        payload = design_payload_ok()
        payload["api_design"]["endpoints"] = [{"method": "GET"}]
        agent = _agent(pm_mock_provider(design_json(**payload)))
        with pytest.raises(ArchitectError, match="endpoints\\[0\\]"):
            agent.design()

    def test_task_breakdown_missing_keys_loud(self, pm_mock_provider):
        """task_breakdown 深度校验: 每项缺 module/task/api_contract/
        ui_guidance → 响亮 (Developer 消费准备)。"""
        payload = design_payload_ok()
        payload["task_breakdown"] = [{"module": "m"}]
        agent = _agent(pm_mock_provider(design_json(**payload)))
        with pytest.raises(ArchitectError, match="task_breakdown\\[0\\]"):
            agent.design()

    def test_task_breakdown_empty_loud(self, pm_mock_provider):
        payload = design_payload_ok(task_count=0)
        agent = _agent(pm_mock_provider(design_json(**payload)))
        with pytest.raises(ArchitectError, match="task_breakdown"):
            agent.design()

    def test_no_provider_loud(self):
        """无 provider → ArchitectError 响亮 (诚实边界, 同 pm/uxui)。"""
        agent = _agent(None)
        with pytest.raises(ArchitectError, match="provider"):
            agent.design()

    def test_provider_error_loud(self, pm_mock_provider):
        agent = _agent(pm_mock_provider("", error="LLM 服务不可用"))
        with pytest.raises(ArchitectError, match="LLM 服务不可用"):
            agent.design()


class TestLocalValidation:
    def test_local_validate_matches_org_rules(self):
        """本地校验与 org CONTRACTS 双体系一致: 合法载荷零错误。"""
        from exec.architect import _local_validate

        assert _local_validate(design_payload_ok()) == []

    def test_local_validate_blank_str(self):
        from exec.architect import _local_validate

        payload = design_payload_ok()
        payload["backend_architecture"] = "  "
        errors = _local_validate(payload)
        assert any("backend_architecture" in e for e in errors)

    def test_local_validate_dict_rule(self):
        from exec.architect import _local_validate

        payload = design_payload_ok()
        payload["database_design"] = []
        errors = _local_validate(payload)
        assert any("database_design" in e for e in errors)


class TestExecutorRefs:
    def test_executor_metadata_has_artifact_refs(self, pm_mock_provider):
        """artifact_refs 强引用: executor 输出 metadata 带 [product_id,
        ux_ui_id] — 设计产物显式引用输入产物 id。"""
        provider = pm_mock_provider(design_json())
        executor = build_arch_executor(_agent(provider))
        stage = type("S", (), {"id": "STG-1", "role_id": "architect"})()
        context = {
            "project_id": "P-8",
            "inputs": [
                {"id": "A-PROD-9", "type": "product", "metadata": product_payload_ok()},
                {"id": "A-UXUI-9", "type": "ux_ui", "metadata": uxui_payload_ok()},
            ],
        }
        result = executor(stage, context)
        assert result["artifact_type"] == "design"
        assert result["ref"] == "file:///docs/design.json"
        assert result["metadata"]["artifact_refs"] == ["A-PROD-9", "A-UXUI-9"]
        # 7 节契约载荷完整 (artifact_refs 为附加键)
        for field in DESIGN_FIELDS:
            assert field in result["metadata"]

    def test_executor_requires_both_inputs_in_context(self, pm_mock_provider):
        """禁止脱离独立生成: context 缺任一输入产物 → ArchitectError (即使
        agent 构造已绑定 payload, executor 仍要求 context 输入 id 强引用)。"""
        provider = pm_mock_provider(design_json())
        executor = build_arch_executor(_agent(provider))
        stage = type("S", (), {"id": "STG-1", "role_id": "architect"})()
        with pytest.raises(ArchitectError, match="BOTH"):
            executor(stage, {"inputs": [{"id": "A-PROD-9", "type": "product", "metadata": product_payload_ok()}]})
        with pytest.raises(ArchitectError, match="BOTH"):
            executor(stage, {"inputs": []})
