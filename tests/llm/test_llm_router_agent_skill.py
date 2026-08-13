"""tests/llm/test_llm_router_agent_skill.py — S10-024 Router v1.1: L2 Agent/Skill 策略。

覆盖 (全 hermetic: agents_dir/skills_dir/providers_file 全 tmp 注入):
- B 验收: agent.yaml preferred 命中; Agent Policy > Skill Policy;
  fallback 链依次尝试; fallback 字符串/dict 两种格式兼容
- agent.yaml / skill.yaml 缺失 → None (策略层降级)
- 损坏 yaml → warning + None (失败安全)
- rule.provider 缺省 → ControlPlane 默认 (selected_provider_id);
  rule.model 缺省 → provider 默认模型

basename 全仓库唯一; sys.path 挂仓库根 (factory-console 包父目录)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录
    sys.path.insert(0, str(_ROOT))

_llm_control = importlib.import_module("factory-console.llm_control")
_llm_router = importlib.import_module("factory-console.llm_router")
_agent_policy = importlib.import_module("factory-console.agent_policy")

LLMRouter = _llm_router.LLMRouter
AgentPolicyStore = _agent_policy.AgentPolicyStore
AgentRoutingPolicy = _agent_policy.AgentRoutingPolicy
SkillRoutingPolicy = _agent_policy.SkillRoutingPolicy


# ------------------------------------------------------------------ 装配辅助


def make_control_plane(tmp_path: Path, providers: dict[str, dict] | None = None) -> "object":
    path = tmp_path / "providers.json"
    data = {"version": 1, "providers": {}}
    for pid, cfg in (providers or {}).items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _llm_control.LLMControlPlane(providers_file=path)


def make_router(
    tmp_path: Path,
    cp: "object",
    *,
    agents_dir: Path | None = None,
    skills_dir: Path | None = None,
) -> LLMRouter:
    store = AgentPolicyStore(
        agents_dir=agents_dir or tmp_path / "agents",
        skills_dir=skills_dir or tmp_path / "skills",
    )
    return LLMRouter(control_plane=cp, policy_store=store)


def write_yaml(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def two_provider_cp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "object":
    """deepseek(有key) + ollama(本地无key) 双 provider 基底。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return make_control_plane(
        tmp_path,
        {
            "deepseek": {"enabled": True, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"},
            "ollama": {"enabled": True, "models": ["qwen2.5-14b"]},
        },
    )


AGENT_YAML_DICT = """\
name: backend-1
llm:
  routing:
    preferred:
      model: deepseek-reasoner
      provider: deepseek
    fallback:
      - model: qwen2.5-14b
        provider: ollama
"""


# ------------------------------------------------------------------ agent.yaml preferred 命中


class TestAgentPreferred:
    """B 验收: agent.yaml preferred 命中。"""

    def test_agent_preferred_hit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(agents_dir / "backend-1" / "agent.yaml", AGENT_YAML_DICT)
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.source == "agent-skill-policy"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-reasoner"

    def test_agent_preferred_model_only_uses_control_plane_default_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preferred 只有 model (无 provider) → provider 取 ControlPlane 默认。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-chat\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.provider_id == "deepseek"  # 第一个 enabled+key
        assert choice.model_id == "deepseek-chat"

    def test_agent_preferred_provider_only_uses_provider_default_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preferred 只有 provider (无 model) → model 取 provider 默认模型。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"  # providers.json models[0]

    def test_agent_policy_loaded_as_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """数据访问层: load_agent_policy 返回 AgentRoutingPolicy 模型。"""
        agents_dir = tmp_path / "agents"
        write_yaml(agents_dir / "backend-1" / "agent.yaml", AGENT_YAML_DICT)
        store = AgentPolicyStore(agents_dir=agents_dir, skills_dir=tmp_path / "skills")

        policy = store.load_agent_policy("backend-1")

        assert isinstance(policy, AgentRoutingPolicy)
        assert policy.preferred is not None
        assert policy.preferred.model == "deepseek-reasoner"
        assert policy.preferred.provider == "deepseek"
        assert [r.model for r in policy.fallback] == ["qwen2.5-14b"]
        assert policy.fallback[0].provider == "ollama"


# ------------------------------------------------------------------ Agent > Skill 优先级


class TestAgentOverSkill:
    """B 验收: Agent Policy > Skill Policy (Agent 是执行主体)。"""

    def test_agent_preferred_beats_skill_preferred(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agent preferred 与 skill preferred 都可用 → agent 赢。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        skills_dir = tmp_path / "skills"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-chat\n      provider: deepseek\n",
        )
        write_yaml(
            skills_dir / "python" / "skill.yaml",
            "id: python\nllm:\n  routing:\n    preferred:\n      model: qwen2.5-14b\n      provider: ollama\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir, skills_dir=skills_dir)

        choice = router.route(agent_id="backend-1", skill_ids=["python"])

        assert choice is not None
        assert choice.provider_id == "deepseek"  # agent 策略 (deepseek-chat) 优先
        assert choice.model_id == "deepseek-chat"

    def test_skill_preferred_when_agent_policy_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """agent 无策略 → skill preferred 生效。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        skills_dir = tmp_path / "skills"
        write_yaml(
            skills_dir / "python" / "skill.yaml",
            "id: python\nllm:\n  routing:\n    preferred:\n      model: qwen2.5-14b\n      provider: ollama\n",
        )
        router = make_router(tmp_path, cp, skills_dir=skills_dir)

        choice = router.route(agent_id="backend-1", skill_ids=["python"])

        assert choice is not None
        assert choice.provider_id == "ollama"
        assert choice.model_id == "qwen2.5-14b"

    def test_first_skill_with_policy_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """多个 skill: 第一个有可用策略的命中。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        skills_dir = tmp_path / "skills"
        write_yaml(
            skills_dir / "python" / "skill.yaml",
            "id: python\nllm:\n  routing:\n    preferred:\n      model: deepseek-chat\n      provider: deepseek\n",
        )
        write_yaml(
            skills_dir / "flutter" / "skill.yaml",
            "id: flutter\nllm:\n  routing:\n    preferred:\n      model: qwen2.5-14b\n      provider: ollama\n",
        )
        router = make_router(tmp_path, cp, skills_dir=skills_dir)

        choice = router.route(agent_id="backend-1", skill_ids=["python", "flutter"])

        assert choice is not None
        assert choice.model_id == "deepseek-chat"  # python 在前

    def test_skill_policy_loaded_as_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """数据访问层: load_skill_policy 返回 SkillRoutingPolicy 模型。"""
        skills_dir = tmp_path / "skills"
        write_yaml(
            skills_dir / "python" / "skill.yaml",
            "id: python\nllm:\n  routing:\n    preferred:\n      model: qwen2.5-14b\n      provider: ollama\n",
        )
        store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=skills_dir)

        policy = store.load_skill_policy("python")

        assert isinstance(policy, SkillRoutingPolicy)
        assert policy.preferred is not None
        assert policy.preferred.model == "qwen2.5-14b"


# ------------------------------------------------------------------ fallback 链


class TestFallbackChain:
    """B 验收: preferred 不可用 → fallback 链依次尝试。"""

    def test_fallback_chain_tried_in_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preferred 的 provider 禁用 → fallback[0] (ollama) 命中。"""
        cp = make_control_plane(
            tmp_path,
            {
                "deepseek": {"enabled": True, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"},
                "anthropic": {"enabled": False, "models": ["claude-sonnet-4"], "api_key_ref": "env:ANTHROPIC_API_KEY"},
                "ollama": {"enabled": True, "models": ["qwen2.5-14b"]},
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: claude-sonnet-4\n      provider: anthropic\n"
            "    fallback:\n      - model: qwen2.5-14b\n        provider: ollama\n      - model: deepseek-chat\n        provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.provider_id == "ollama"  # preferred 禁用 → fallback[0]
        assert choice.model_id == "qwen2.5-14b"

    def test_fallback_skips_unusable_entries(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fallback[0] 无 key → 跳过 → fallback[1] 命中。"""
        cp = make_control_plane(
            tmp_path,
            {
                "openai": {"enabled": True, "models": ["gpt-4o"], "api_key_ref": "env:OPENAI_API_KEY"},
                "deepseek": {"enabled": True, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"},
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")  # openai 无 key
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: gpt-4o\n      provider: openai\n"
            "    fallback:\n      - model: gpt-4o\n        provider: openai\n      - model: deepseek-chat\n        provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.provider_id == "deepseek"  # fallback[0] 无 key 跳过 → [1]
        assert choice.model_id == "deepseek-chat"

    def test_fallback_string_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fallback 字符串列表: 仅 model, provider 取 ControlPlane 默认。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: ghost-model\n      provider: ghost-provider\n"
            "    fallback:\n      - qwen2.5-14b\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.model_id == "qwen2.5-14b"
        assert choice.provider_id == "deepseek"  # ControlPlane 默认 (第一个 enabled+key)

    def test_fallback_mixed_string_and_dict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fallback 混合: 字符串 + dict 两种格式同链兼容。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: ghost-model\n      provider: ghost-provider\n"
            "    fallback:\n      - qwen2.5-14b\n      - model: deepseek-chat\n        provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.model_id == "qwen2.5-14b"  # 字符串条目先命中

    def test_fallback_all_unusable_degrades(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """preferred + fallback 全不可用 → 降级 L3/L5 (fallback 层)。"""
        cp = make_control_plane(
            tmp_path,
            {
                "openai": {"enabled": True, "models": ["gpt-4o"], "api_key_ref": "env:OPENAI_API_KEY"},
                "deepseek": {"enabled": True, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"},
            },
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: gpt-4o\n      provider: openai\n"
            "    fallback:\n      - model: gpt-4o\n        provider: openai\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.source == "fallback"  # L2 全失败 → L3 缺 → L4 缺 → L5
        assert choice.provider_id == "deepseek"


# ------------------------------------------------------------------ 缺失/损坏


class TestPolicyStoreFailureSafe:
    """数据访问层: 缺失 → None; 损坏 → warning + None。"""

    def test_missing_agent_policy_none(self, tmp_path: Path) -> None:
        store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=tmp_path / "skills")
        assert store.load_agent_policy("ghost") is None

    def test_missing_skill_policy_none(self, tmp_path: Path) -> None:
        store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=tmp_path / "skills")
        assert store.load_skill_policy("ghost") is None

    def test_corrupt_agent_yaml_warning_and_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """损坏 yaml → warning 日志 + None (失败安全)。"""
        agents_dir = tmp_path / "agents"
        write_yaml(agents_dir / "backend-1" / "agent.yaml", "llm: [unclosed\n  routing:\n    bad")
        store = AgentPolicyStore(agents_dir=agents_dir, skills_dir=tmp_path / "skills")

        import logging

        with caplog.at_level(logging.WARNING, logger="factory.agent_policy"):
            policy = store.load_agent_policy("backend-1")

        assert policy is None
        assert any("corrupt" in r.message for r in caplog.records)

    def test_corrupt_skill_yaml_warning_and_none(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        skills_dir = tmp_path / "skills"
        write_yaml(skills_dir / "python" / "skill.yaml", "id: [python\n  llm: bad")
        store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=skills_dir)

        import logging

        with caplog.at_level(logging.WARNING, logger="factory.agent_policy"):
            policy = store.load_skill_policy("python")

        assert policy is None
        assert any("corrupt" in r.message for r in caplog.records)

    def test_yaml_without_llm_routing_none(self, tmp_path: Path) -> None:
        """合法 yaml 但无 llm.routing 段 → None (非损坏, 静默)。"""
        agents_dir = tmp_path / "agents"
        write_yaml(agents_dir / "backend-1" / "agent.yaml", "name: backend-1\nrole: developer\n")
        store = AgentPolicyStore(agents_dir=agents_dir, skills_dir=tmp_path / "skills")

        assert store.load_agent_policy("backend-1") is None

    def test_invalid_rule_entry_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fallback 非法条目 (非 str/dict) → 跳过不拖垮整条策略。"""
        cp = two_provider_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-chat\n      provider: deepseek\n"
            "    fallback:\n      - 42\n      - qwen2.5-14b\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.model_id == "deepseek-chat"  # preferred 已命中, 非法条目未影响
