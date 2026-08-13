"""tests/llm/test_llm_router_project.py — S10-024 Router v1.1: L3 Project Rule。

覆盖 (全 hermetic: project_dir/providers_file 全 tmp 注入):
- C 验收: project.yaml default 命中 → L3 (source="project-rule")
- task_types 按 task_type 命中; 未命中 task_type → default
- rule.provider/model 缺省语义 (ControlPlane 默认)
- project.yaml 缺失 → 降级 (L4/L5); 损坏 → warning + None (失败安全)
- load_project_rules 数据访问层: ProjectLlmConfig 模型解析

basename 全仓库唯一; sys.path 挂仓库根 (factory-console 包父目录)。
"""

from __future__ import annotations

import importlib
import json
import logging
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

LLMRouter = _llm_router.LLMRouter
AgentPolicyStore = _agent_policy.AgentPolicyStore
ProjectLlmConfig = _llm_router.ProjectLlmConfig


# ------------------------------------------------------------------ 装配辅助


def make_control_plane(tmp_path: Path, providers: dict[str, dict] | None = None) -> "object":
    path = tmp_path / "providers.json"
    data = {"version": 1, "providers": {}}
    for pid, cfg in (providers or {}).items():
        data["providers"][pid] = {"id": pid, **cfg}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _llm_control.LLMControlPlane(providers_file=path)


def make_router(tmp_path: Path, cp: "object") -> LLMRouter:
    store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=tmp_path / "skills")
    return LLMRouter(control_plane=cp, policy_store=store)


def write_project_yaml(project_dir: Path, text: str) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "project.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def deepseek_cp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> "object":
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return make_control_plane(
        tmp_path,
        {
            "deepseek": {"enabled": True, "models": ["deepseek-chat"], "api_key_ref": "env:DEEPSEEK_API_KEY"},
            "anthropic": {"enabled": True, "models": ["claude-sonnet-4"], "api_key_ref": "env:ANTHROPIC_API_KEY"},
        },
    )


PROJECT_YAML_DEFAULT = """\
llm:
  routing:
    default:
      provider: deepseek
      model: deepseek-reasoner
"""

PROJECT_YAML_TASK_TYPES = """\
llm:
  routing:
    default:
      provider: deepseek
      model: deepseek-chat
    task_types:
      code-review:
        provider: anthropic
        model: claude-sonnet-4
"""


# ------------------------------------------------------------------ L3 命中 (C 验收)


class TestProjectRuleHit:
    """C 验收: project.yaml 规则生效 (L3 命中, source="project-rule")。"""

    def test_project_default_hit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, PROJECT_YAML_DEFAULT)
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "project-rule"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-reasoner"
        assert choice.score is None
        assert choice.reasons[0] == "layer: project-rule"

    def test_project_task_type_hit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-1")
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, PROJECT_YAML_TASK_TYPES)
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir, task_type="code-review")

        assert choice is not None
        assert choice.source == "project-rule"
        assert choice.provider_id == "anthropic"
        assert choice.model_id == "claude-sonnet-4"

    def test_project_unknown_task_type_uses_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, PROJECT_YAML_TASK_TYPES)
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir, task_type="unknown-task")

        assert choice is not None
        assert choice.model_id == "deepseek-chat"  # default 兜底

    def test_project_rule_beats_system_recommendation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L3 命中 → 不再查 L4 (即使 capabilities 会给系统推荐)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        catalog = _model_catalog.ModelCatalog(
            models_file=tmp_path / "models.json", control_plane=cp
        )
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, PROJECT_YAML_DEFAULT)
        store = AgentPolicyStore(agents_dir=tmp_path / "agents", skills_dir=tmp_path / "skills")
        router = LLMRouter(control_plane=cp, model_catalog=catalog, policy_store=store)

        choice = router.route(project_dir=project_dir, required_capabilities=["code"])

        assert choice is not None
        assert choice.source == "project-rule"  # L3 优先于 L4
        assert choice.model_id == "deepseek-reasoner"

    def test_project_model_only_uses_control_plane_default_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """project default 只有 model → provider 取 ControlPlane 默认。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(
            project_dir,
            "llm:\n  routing:\n    default:\n      model: deepseek-chat\n",
        )
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "project-rule"
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"

    def test_project_provider_only_uses_provider_default_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(
            project_dir,
            "llm:\n  routing:\n    default:\n      provider: deepseek\n",
        )
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.provider_id == "deepseek"
        assert choice.model_id == "deepseek-chat"  # providers.json models[0]


# ------------------------------------------------------------------ 缺失/损坏 (失败安全)


class TestProjectRuleFailureSafe:
    """project.yaml 缺失 → 降级; 损坏 → warning + None。"""

    def test_missing_project_yaml_degrades(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """无 project.yaml → L3 跳过 → L5 fallback。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)
        project_dir = tmp_path / "project"  # 目录存在但无 project.yaml
        project_dir.mkdir(parents=True, exist_ok=True)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "fallback"
        assert choice.provider_id == "deepseek"

    def test_corrupt_project_yaml_warning_and_degrade(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """损坏 project.yaml → warning + 降级 L5 (失败安全)。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, "llm: [unclosed\n  routing: bad")
        router = make_router(tmp_path, cp)

        with caplog.at_level(logging.WARNING, logger="factory.llm_router"):
            choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "fallback"  # L3 损坏 → 降级 L4/L5
        assert any("corrupt" in r.message for r in caplog.records)

    def test_project_yaml_without_llm_routing_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """合法 project.yaml 但无 llm.routing → L3 无规则 → 降级。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, "name: demo-project\nversion: 1\n")
        router = make_router(tmp_path, cp)

        choice = router.route(project_dir=project_dir)

        assert choice is not None
        assert choice.source == "fallback"


# ------------------------------------------------------------------ load_project_rules


class TestLoadProjectRules:
    """数据访问层: load_project_rules 返回 ProjectLlmConfig。"""

    def test_load_project_rules_returns_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, PROJECT_YAML_TASK_TYPES)

        config = router.load_project_rules(project_dir)

        assert isinstance(config, ProjectLlmConfig)
        assert config.routing.default is not None
        assert config.routing.default.model == "deepseek-chat"
        assert "code-review" in config.routing.task_types
        assert config.routing.task_types["code-review"].provider == "anthropic"

    def test_load_project_rules_missing_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)
        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True, exist_ok=True)

        assert router.load_project_rules(project_dir) is None

    def test_load_project_rules_corrupt_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)
        project_dir = tmp_path / "project"
        write_project_yaml(project_dir, "llm: [unclosed")

        with caplog.at_level(logging.WARNING, logger="factory.llm_router"):
            config = router.load_project_rules(project_dir)

        assert config is None
        assert any("corrupt" in r.message for r in caplog.records)

    def test_load_project_rules_invalid_structure_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """llm.routing 字段非法 (default 非对象) → warning + None。"""
        cp = deepseek_cp(tmp_path, monkeypatch)
        router = make_router(tmp_path, cp)
        project_dir = tmp_path / "project"
        write_project_yaml(
            project_dir,
            "llm:\n  routing:\n    default: 42\n",
        )

        with caplog.at_level(logging.WARNING, logger="factory.llm_router"):
            config = router.load_project_rules(project_dir)

        assert config is None
        assert any("invalid" in r.message for r in caplog.records)
