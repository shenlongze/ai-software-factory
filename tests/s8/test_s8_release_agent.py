"""tests/s8/test_s8_release_agent.py — ReleaseAgent (Unit, S8-004)。

覆盖 (任务清单: ReleaseAgent 双输入强校验 + Test VALIDATED 门禁 + 解析链/
垃圾拒绝/响亮错误 + artifact_refs):
- happy path: Code + Test 双输入 → ReleaseArtifact 5 节全字段
- 宽容解析: markdown 围栏剥离 / 散文包裹 / 覆盖绑定 (release 参数优先)
- 双输入强校验: 构造缺 code / 缺 test / 空 dict / 非 dict → ReleaseError
  响亮 (禁止脱离输入独立生成 — 发布不能凭空捏造)
- ★ Test VALIDATED 强校验 (S8-004 质量门禁): test 缺 results / results 缺
  passed / 缺 bugs → ReleaseError 响亮 (未通过测试的产物禁止发布);
  set_test 同样拒绝
- set_code / set_test 空输入拒绝 (不变量全入口生效)
- 本地校验 (exec 侧同 CONTRACTS 规则): 缺 5 节字段 / 空节 / build_result
  缺 status/command / package 缺 name/type/files / files 空 list
- 垃圾响亮拒绝: 非 JSON / 非对象 / 缺字段 → ReleaseError
- provider 缺失 / provider 错误 → ReleaseError (不假装生成成功)
- 双输入消费证明: prompt 含 code (files/changes) + test (results/bugs) 内容
- build_release_executor: artifact_refs = [code_id, test_id]; context 缺任一
  输入 → ReleaseError (即使 agent 构造已绑定 payload)

依赖: 本目录 conftest (pm_mock_provider) + s8_helpers。
"""

from __future__ import annotations

import json

import pytest

from exec.release import (
    RELEASE_FIELDS,
    ReleaseAgent,
    ReleaseError,
    build_release_executor,
)

from s8_helpers import (
    code_payload_ok,
    release_json,
    release_payload_ok,
    qa_payload_ok,
)


def _agent(provider, **kwargs) -> ReleaseAgent:
    """双输入齐备的 ReleaseAgent (code + test 契约载荷, test VALIDATED)。"""
    return ReleaseAgent(
        provider,
        code=kwargs.pop("code", code_payload_ok()),
        test=kwargs.pop("test", qa_payload_ok()),
        **kwargs,
    )


class TestDoubleInputStrongValidation:
    def test_construct_requires_both_inputs(self):
        """构造强校验: 缺任一输入 → ReleaseError (禁止脱离独立生成)。"""
        with pytest.raises(ReleaseError, match="code"):
            ReleaseAgent(None, test=qa_payload_ok())
        with pytest.raises(ReleaseError, match="test"):
            ReleaseAgent(None, code=code_payload_ok())
        with pytest.raises(ReleaseError, match="code"):
            ReleaseAgent(None)

    def test_construct_rejects_empty_inputs(self):
        """空 dict / 非 dict 输入 → ReleaseError (强校验不变量)。"""
        with pytest.raises(ReleaseError, match="empty"):
            ReleaseAgent(None, code={}, test=qa_payload_ok())
        with pytest.raises(ReleaseError, match="empty"):
            ReleaseAgent(None, code=code_payload_ok(), test={})
        with pytest.raises(ReleaseError, match="must be a dict"):
            ReleaseAgent(None, code="text", test=qa_payload_ok())

    def test_set_code_rejects_empty(self):
        """set_code 空输入拒绝 (强校验全入口生效, 不变量永不被打破)。"""
        agent = _agent(None)
        with pytest.raises(ReleaseError):
            agent.set_code({})
        with pytest.raises(ReleaseError):
            agent.set_code(None)

    def test_bound_inputs_always_present(self):
        """构造后双输入恒存在 (release 永不缺输入 — 禁止脱离独立生成)。"""
        agent = _agent(None)
        assert agent.code
        assert agent.test


class TestTestValidatedGate:
    """★ S8-004 质量门禁: Test 必须 VALIDATED (test 契约 — results 必含
    passed + bugs list), 未通过测试的产物禁止发布。"""

    def test_construct_rejects_test_missing_results(self):
        test = {"bugs": []}
        with pytest.raises(ReleaseError, match="VALIDATED"):
            ReleaseAgent(None, code=code_payload_ok(), test=test)

    def test_construct_rejects_results_missing_passed(self):
        test = {"results": {"total": 3, "failed": 0}, "bugs": []}
        with pytest.raises(ReleaseError, match="passed"):
            ReleaseAgent(None, code=code_payload_ok(), test=test)

    def test_construct_rejects_test_missing_bugs(self):
        test = {"results": {"passed": True, "total": 3}}
        with pytest.raises(ReleaseError, match="bugs"):
            ReleaseAgent(None, code=code_payload_ok(), test=test)

    def test_set_test_rejects_not_validated(self):
        """set_test 未 VALIDATED → ReleaseError (门禁全入口生效)。"""
        agent = _agent(None)
        with pytest.raises(ReleaseError, match="VALIDATED"):
            agent.set_test({"results": {}})

    def test_release_method_rejects_not_validated(self, pm_mock_provider):
        """release(code, test) 显式参数未 VALIDATED → ReleaseError (门禁
        不因参数覆盖而绕过)。"""
        agent = _agent(pm_mock_provider(release_json()))
        with pytest.raises(ReleaseError, match="VALIDATED"):
            agent.release(code=code_payload_ok(), test={"results": {}})


class TestHappyPath:
    def test_release_5_sections(self, pm_mock_provider):
        """双输入 → ReleaseArtifact: 5 节全字段 (契约载荷)。"""
        agent = _agent(pm_mock_provider(release_json()))
        artifact = agent.release()
        assert list(artifact.to_dict()) == list(RELEASE_FIELDS)
        assert artifact.build_result["status"] == "success"
        assert artifact.version
        assert artifact.package["name"]
        assert artifact.package["files"]
        assert artifact.release_notes
        assert artifact.deployment

    def test_fenced_json(self, pm_mock_provider):
        artifact = _agent(pm_mock_provider(release_json(fenced=True))).release()
        assert artifact.version

    def test_prose_wrapped_json(self, pm_mock_provider):
        artifact = _agent(pm_mock_provider(release_json(prose=True))).release()
        assert artifact.version

    def test_release_args_override_bound(self, pm_mock_provider):
        """双输入解析链: release(code, test) 显式参数 > 构造绑定。"""
        provider = pm_mock_provider(release_json())
        agent = _agent(provider)
        artifact = agent.release(code_payload_ok(), qa_payload_ok())
        assert artifact.version

    def test_max_tokens_passthrough(self, pm_mock_provider):
        provider = pm_mock_provider(release_json())
        _agent(provider, max_tokens=2048).release()
        assert provider.last_request.max_tokens == 2048

    def test_prompt_consumes_both_inputs(self, pm_mock_provider):
        """双输入消费证明: prompt 含 code (files/changes) + test
        (results/bugs) 内容 — 发布基于产物, 不凭空生成。"""
        provider = pm_mock_provider(release_json())
        _agent(provider).release()
        ctx = provider.last_request.task_context
        assert "src/module_1.py" in ctx  # code files
        assert "S8-005 全链 Demo" in ctx  # code changes
        assert "passed" in ctx  # test results
        assert "bugs" in ctx  # test bugs

    def test_prompt_truncates_long_inputs(self, pm_mock_provider):
        """超长输入截断 (防上下文撑爆; 双输入各自截断)。"""
        big_code = code_payload_ok(file_count=1)
        big_code["changes"] = "长变更说明" * 5000
        provider = pm_mock_provider(release_json())
        _agent(provider, code=big_code).release()
        assert len(provider.last_request.task_context) < 20000


class TestLoudRejection:
    def test_bad_llm_output_not_json(self, pm_mock_provider):
        """垃圾输出 (不可解析) → ReleaseError 响亮 (不假装生成成功)。"""
        agent = _agent(pm_mock_provider("这不是 JSON, 随便一段文字"))
        with pytest.raises(ReleaseError, match="not valid JSON"):
            agent.release()

    def test_llm_output_not_object(self, pm_mock_provider):
        agent = _agent(pm_mock_provider("[1, 2, 3]"))
        with pytest.raises(ReleaseError, match="JSON object"):
            agent.release()

    def test_missing_required_fields(self, pm_mock_provider):
        """LLM 输出缺核心字段 (deployment) → 响亮拒绝。注: release_json(**p)
        无法表达"删除字段" (override 只增改), 此处直接序列化缺字段载荷。"""
        payload = release_payload_ok()
        del payload["deployment"]
        agent = _agent(pm_mock_provider(json.dumps(payload, ensure_ascii=False)))
        with pytest.raises(ReleaseError, match="deployment"):
            agent.release()

    def test_empty_section_loud(self, pm_mock_provider):
        payload = release_payload_ok()
        payload["release_notes"] = "   "
        agent = _agent(pm_mock_provider(release_json(**payload)))
        with pytest.raises(ReleaseError, match="release_notes"):
            agent.release()

    def test_build_result_missing_keys_loud(self, pm_mock_provider):
        payload = release_payload_ok()
        payload["build_result"] = {"outcome": "ok"}
        agent = _agent(pm_mock_provider(release_json(**payload)))
        with pytest.raises(ReleaseError, match="status"):
            agent.release()

    def test_package_missing_keys_loud(self, pm_mock_provider):
        payload = release_payload_ok()
        payload["package"] = {"id": "pkg-1"}
        agent = _agent(pm_mock_provider(release_json(**payload)))
        with pytest.raises(ReleaseError, match="files"):
            agent.release()

    def test_package_files_empty_loud(self, pm_mock_provider):
        payload = release_payload_ok(file_count=0)
        agent = _agent(pm_mock_provider(release_json(**payload)))
        with pytest.raises(ReleaseError, match="files"):
            agent.release()

    def test_no_provider_loud(self):
        """无 provider → ReleaseError 响亮 (诚实边界, 同 pm/uxui/arch)。"""
        agent = _agent(None)
        with pytest.raises(ReleaseError, match="provider"):
            agent.release()

    def test_provider_error_loud(self, pm_mock_provider):
        agent = _agent(pm_mock_provider("", error="LLM 服务不可用"))
        with pytest.raises(ReleaseError, match="LLM 服务不可用"):
            agent.release()


class TestLocalValidation:
    def test_local_validate_matches_org_rules(self):
        """本地校验与 org CONTRACTS 双体系一致: 合法载荷零错误。"""
        from exec.release import _local_validate

        assert _local_validate(release_payload_ok()) == []

    def test_local_validate_blank_str(self):
        from exec.release import _local_validate

        payload = release_payload_ok()
        payload["deployment"] = "  "
        errors = _local_validate(payload)
        assert any("deployment" in e for e in errors)

    def test_local_validate_build_result_dict_rule(self):
        from exec.release import _local_validate

        payload = release_payload_ok()
        payload["build_result"] = []
        errors = _local_validate(payload)
        assert any("build_result" in e for e in errors)


class TestExecutorRefs:
    def test_executor_metadata_has_artifact_refs(self, pm_mock_provider):
        """artifact_refs 强引用: executor 输出 metadata 带 [code_id, test_id]
        — 发布产物显式引用输入产物 id (审计/溯源)。"""
        provider = pm_mock_provider(release_json())
        executor = build_release_executor(_agent(provider))
        stage = type("S", (), {"id": "STG-1", "role_id": "devops"})()
        context = {
            "project_id": "P-8",
            "inputs": [
                {"id": "A-CODE-9", "type": "code", "metadata": code_payload_ok()},
                {"id": "A-TEST-9", "type": "test", "metadata": qa_payload_ok()},
            ],
        }
        result = executor(stage, context)
        assert result["artifact_type"] == "release"
        assert result["ref"] == "file:///dist/release.json"
        assert result["metadata"]["artifact_refs"] == ["A-CODE-9", "A-TEST-9"]
        # 5 节契约载荷完整 (artifact_refs 为附加键)
        for field in RELEASE_FIELDS:
            assert field in result["metadata"]

    def test_executor_requires_both_inputs_in_context(self, pm_mock_provider):
        """禁止脱离独立生成: context 缺任一输入产物 → ReleaseError (即使
        agent 构造已绑定 payload, executor 仍要求 context 输入 id 强引用)。"""
        provider = pm_mock_provider(release_json())
        executor = build_release_executor(_agent(provider))
        stage = type("S", (), {"id": "STG-1", "role_id": "devops"})()
        with pytest.raises(ReleaseError, match="BOTH"):
            executor(stage, {"inputs": [{"id": "A-CODE-9", "type": "code", "metadata": code_payload_ok()}]})
        with pytest.raises(ReleaseError, match="BOTH"):
            executor(stage, {"inputs": []})
