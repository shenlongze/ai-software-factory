"""tests/llm/test_llm_router_priority.py — S10-024 Router v1.1: 五层决策优先级。

覆盖 (全 hermetic: providers_file/models_file/agents_dir/skills_dir 全 tmp 注入,
不写真实 ~/.factory):
- A 验收: L1 命中不再查下层; L1 缺 → L2; L2 缺 → L3; L3 缺 → L4; 全缺 → L5
- L1 provider 不存在/禁用 → 响亮 UserExplicitError (不静默降级)
- L1 provider 存在+enabled 但 key 缺失 → 降级下一层
- D 验收: 输出复用 ModelChoice {model_id, provider_id, score, reasons, source}
- G 验收: route() 后 router.decided_events 可记录 + event_logger.record 收到
  "router.decided" {provider_id, model_id, source, reason, score}

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
_model_catalog = importlib.import_module("factory-console.model_catalog")
_agent_policy = importlib.import_module("factory-console.agent_policy")

ModelChoice = _model_catalog.ModelChoice
LLMRouter = _llm_router.LLMRouter
AgentPolicyStore = _agent_policy.AgentPolicyStore
UserExplicitError = _llm_router.UserExplicitError


# ------------------------------------------------------------------ 装配辅助


def make_control_plane(
    tmp_path: Path, providers: dict[str, dict] | None = None
) -> "object":
    """ControlPlane (providers.json 预写; HOME 无关 — 显式路径注入)。"""
    path = tmp_path / "providers.json"
    data = {"version": 1, "providers": {}}
    for pid, cfg in (providers or {}).items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _llm_control.LLMControlPlane(providers_file=path)


def deepseek_cp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "object":
    """deepseek enabled + key 的 ControlPlane (测试常用基底)。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return make_control_plane(
        tmp_path,
        {
            "deepseek": {
                "enabled": True,
                "models": ["deepseek-chat"],
                "api_key_ref": "env:DEEPSEEK_API_KEY",
            }
        },
    )


def make_catalog(tmp_path: Path, cp: "object") -> "object":
    """ModelCatalog (models_file 注入 tmp; 首载自动写内置种子)。"""
    return _model_catalog.ModelCatalog(
        models_file=tmp_path / "models.json", control_plane=cp
    )


def make_router(
    tmp_path: Path,
    cp: "object",
    *,
    catalog: "object | None" = None,
    agents_dir: Path | None = None,
    skills_dir: Path | None = None,
    event_logger: "object | None" = None,
) -> LLMRouter:
    store = AgentPolicyStore(
        agents_dir=agents_dir or tmp_path / "agents",
        skills_dir=skills_dir or tmp_path / "skills",
    )
    return LLMRouter(
        control_plane=cp,
        model_catalog=catalog,
        policy_store=store,
        event_logger=event_logger,
    )


def write_yaml(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ L1 User Explicit


class TestLayer1UserExplicit:
    """L1: 用户显式指定 — 最高优先级。"""

    def test_l1_hit_no_lower_layers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 命中 (explicit) → 不再查下层 (即使 agent.yaml 会命中 L2)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "name: backend-1\nllm:\n  routing:\n    preferred:\n      model: deepseek-reasoner\n      provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1", explicit_provider="deepseek", explicit_model="deepseek-chat")

        assert choice is not None
        assert choice.source == "user-explicit"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"
        assert choice.score is None
        assert choice.reasons[0] == "layer: user-explicit"

    def test_l1_explicit_model_resolves_provider_via_catalog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """只给 explicit_model → 经 ModelCatalog 反查 provider。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        catalog = make_catalog(tmp_path, cp)
        router = make_router(tmp_path, cp, catalog=catalog)

        choice = router.route(explicit_model="deepseek-chat")

        assert choice is not None
        assert choice.source == "user-explicit"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"

    def test_l1_provider_not_found_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 provider 不存在 → 响亮 UserExplicitError (不静默降级)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)

        with pytest.raises(UserExplicitError):
            router.route(explicit_provider="ghost-provider")

    def test_l1_provider_disabled_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 provider 禁用 → 响亮 UserExplicitError。"""
        cp = make_control_plane(
            tmp_path,
            {"openai": {"enabled": False, "models": ["gpt-4o"], "api_key_ref": "env:OPENAI_API_KEY"}},
        )
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        router = make_router(tmp_path, cp)

        with pytest.raises(UserExplicitError):
            router.route(explicit_provider="openai")

    def test_l1_enabled_no_key_degrades_to_l2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 provider 存在+enabled 但 key 缺失 → 降级 L2 (agent 策略命中)。"""
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
            "llm:\n  routing:\n    preferred:\n      model: deepseek-chat\n      provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1", explicit_provider="openai")

        assert choice is not None
        assert choice.source == "agent-skill-policy"  # L1 无 key → L2 接管
        assert choice.provider_id == "deepseek"


# ------------------------------------------------------------------ 降级链 (A 验收)


class TestPriorityChain:
    """五层降级链: 每层缺失 → 下一层; 全缺 → L5 fallback。"""

    def test_l1_missing_degrades_to_l2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L1 缺 (无 explicit) → L2 agent 策略命中。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        agents_dir = tmp_path / "agents"
        write_yaml(
            agents_dir / "backend-1" / "agent.yaml",
            "llm:\n  routing:\n    preferred:\n      model: deepseek-reasoner\n      provider: deepseek\n",
        )
        router = make_router(tmp_path, cp, agents_dir=agents_dir)

        choice = router.route(agent_id="backend-1")

        assert choice is not None
        assert choice.source == "agent-skill-policy"
        assert choice.model_id == "deepseek-reasoner"

    def test_l2_missing_degrades_to_l3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L2 缺 (无 agent 策略) → L3 project.yaml 命中。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_yaml(
            project_dir / "project.yaml",
            "llm:\n  routing:\n    default:\n      provider: deepseek\n      model: deepseek-reasoner\n",
        )
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "project-rule"
        assert choice.model_id == "deepseek-reasoner"

    def test_l3_missing_degrades_to_l4(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L3 缺 (无 project) → L4 ModelCatalog.suggest 命中 (score 保留)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        catalog = make_catalog(tmp_path, cp)
        router = make_router(tmp_path, cp, catalog=catalog)

        choice = router.route(required_capabilities=["code"])

        assert choice is not None
        assert choice.source == "system-recommendation"
        assert choice.model_id == "deepseek-chat"  # 种子目录 cost 最低且能力命中
        assert choice.score is not None  # L4 score 保留
        assert "layer: system-recommendation" in choice.reasons

    def test_l4_missing_degrades_to_l5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L4 缺 (无 catalog) → L5 fallback = ControlPlane 第一个 enabled。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)  # catalog=None

        choice = router.route(required_capabilities=["code"])

        assert choice is not None
        assert choice.source == "fallback"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"  # providers.json models[0]

    def test_all_missing_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """全缺 (无 explicit/agent/project/catalog/无 enabled provider) → None。"""
        cp = make_control_plane(tmp_path)  # 空 providers.json
        router = make_router(tmp_path, cp)

        assert router.route() is None

    def test_l5_fallback_source_and_reasons(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L5 输出: source=fallback, reasons[0]=layer: fallback, score=None。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)

        choice = router.route()

        assert choice is not None
        assert choice.source == "fallback"
        assert choice.score is None
        assert choice.reasons[0] == "layer: fallback"
        assert "deepseek" in " ".join(choice.reasons)


# ------------------------------------------------------------------ D: ModelChoice 输出


class TestModelChoiceOutput:
    """D 验收: route() 返回 ModelChoice{model_id, provider_id, score, reasons, source}。"""

    def test_output_is_model_choice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """返回类型为 model_catalog.ModelChoice, 字段齐全。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)

        choice = router.route()

        assert isinstance(choice, ModelChoice)
        assert choice.model_id == "deepseek-chat"
        assert choice.provider_id == "deepseek"
        assert choice.score is None
        assert isinstance(choice.reasons, list) and choice.reasons
        assert choice.source == "fallback"

    def test_source_marks_hit_layer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """source ∈ {user-explicit, agent-skill-policy, project-rule, system-recommendation, fallback}。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        catalog = make_catalog(tmp_path, cp)
        router = make_router(tmp_path, cp, catalog=catalog)

        assert router.route(explicit_provider="deepseek").source == "user-explicit"
        assert router.route(required_capabilities=["code"]).source == "system-recommendation"

        router_no_catalog = make_router(tmp_path, cp)  # 无 catalog → L4 跳过
        assert router_no_catalog.route().source == "fallback"


# ------------------------------------------------------------------ G: router.decided 审计


class TestDecidedAudit:
    """G 验收: route() 后 router.decided 事件可记录。"""

    def test_decided_events_recorded_in_memory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """内存审计: decided_events 追加 {provider_id, model_id, source, reason, score}。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)

        choice = router.route(task_type="code-review")

        assert choice is not None
        assert len(router.decided_events) == 1
        event = router.decided_events[0]
        assert event["provider_id"] == "deepseek"
        assert event["model_id"] == "deepseek-chat"
        assert event["source"] == "fallback"
        assert event["reason"]
        assert event["score"] is None
        assert event["task_type"] == "code-review"  # task_type 随事件记录

    def test_event_logger_gets_router_decided(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """event_logger.record("router.decided", source="router", payload=event)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)

        class FakeLogger:
            def __init__(self) -> None:
                self.calls: list[tuple] = []

            def record(self, type_: str, **kwargs: object) -> None:
                self.calls.append((type_, kwargs))

        logger = FakeLogger()
        router = make_router(tmp_path, cp, event_logger=logger)

        router.route()

        assert len(logger.calls) == 1
        type_, kwargs = logger.calls[0]
        assert type_ == "router.decided"
        assert kwargs["source"] == "router"
        payload = kwargs["payload"]
        assert payload["provider_id"] == "deepseek"
        assert payload["model_id"] == "deepseek-chat"
        assert payload["source"] == "fallback"

    def test_audit_failure_safe(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """event_logger.record 抛异常 → 决策不受影响 (审计失败安全)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)

        class BrokenLogger:
            def record(self, type_: str, **kwargs: object) -> None:
                raise RuntimeError("audit store down")

        router = make_router(tmp_path, cp, event_logger=BrokenLogger())

        choice = router.route()  # 不抛异常
        assert choice is not None
        assert choice.source == "fallback"
