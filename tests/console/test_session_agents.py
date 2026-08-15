"""tests/console/test_session_agents.py — S10-055 Agent Workforce Intelligence (Task 001-007)。

设计: docs/sprint10/S10-055-workforce-design.md
覆盖 (验收 A-K):
A. AgentRegistry 2.0: 读 agents.json + 默认兜底 + supported_tasks/cost_profile 扩展字段
B. AgentMatcher: skill 匹配 + 成功率 + 成本 → {agent, score, reason} (注册表驱动,
   无硬编码关键词最终决策)
C. AgentMetrics: execution_records → agent_metrics.json (total/success/failed/
   avg_cost/success_rate/by_task_type)
D. Execution Plan Reasoning: execution_plan.json 含 reason ("skill match 92%...")
E. Workforce Dashboard: "查看团队" → agents [{id, role, status, success_rate}]
F. Task Owner: "谁负责这个任务" → 最近任务 agent
G. Agent Reason: "为什么选择" → reason
H. Production Trace: production_trace.json (Project→Feature→Task→Agent→Artifact→
   Validation→Cost)
I. 不修改核心/不引入依赖 (测试只 import session 层 + 纯标准库)
J. 新增 >=100 测试全绿 + 全量 pytest 不破坏基线
K. 回归: select_agent 兼容 / execute_project 不受影响

测试装配: tmp_path + 构造 agents.json/execution_records.json fixtures (零真实
~/.factory 污染, 零 LLM/网络); AgentMatcher/Metrics 一律注入显式 registry/metrics
(默认数据源路径经 monkeypatch 指向 tmp 文件, 保持 hermetic)。

basename 全仓库唯一 (test_session_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ACT_MOD = importlib.import_module("factory-console.session.action")
ACTIONS_MOD = importlib.import_module("factory-console.session.actions")
AGENTS_MOD = importlib.import_module("factory-console.session.agents")
AUDIT_MOD = importlib.import_module("factory-console.session.audit")
CONF_MOD = importlib.import_module("factory-console.session.confirm")
CTX_MOD = importlib.import_module("factory-console.session.context")
INTENT_MOD = importlib.import_module("factory-console.session.intent")
ORCH_MOD = importlib.import_module("factory-console.session.orchestrator")
PIPE_MOD = importlib.import_module("factory-console.session.pipeline")
ROUTER_MOD = importlib.import_module("factory-console.session.router")

AgentRegistry = AGENTS_MOD.AgentRegistry
AgentMatcher = AGENTS_MOD.AgentMatcher
AgentMetrics = AGENTS_MOD.AgentMetrics
ProductionTrace = AUDIT_MOD.ProductionTrace


# ------------------------------------------------------------------ 工具/夹具

def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry2() -> dict:
    """Registry 2.0 风格注册表 (含 supported_tasks/cost_profile)。"""
    return {
        "backend-1": {
            "id": "backend-1",
            "name": "backend-1",
            "role": "Backend Engineer",
            "skills": ["python", "api", "database"],
            "supported_tasks": ["backend_api", "database_schema", "test"],
            "cost_profile": {"avg_cost": 1000, "cost_unit": "tokens"},
            "status": "available",
            "current_task": None,
        },
        "flutter-dev": {
            "id": "flutter-dev",
            "name": "Flutter Dev",
            "role": "Frontend Engineer",
            "skills": ["flutter", "dart", "ui", "frontend"],
            "supported_tasks": ["frontend_page", "ui_interaction"],
            "cost_profile": {"avg_cost": 900, "cost_unit": "tokens"},
            "status": "available",
            "current_task": None,
        },
        "tester-1": {
            "id": "tester-1",
            "name": "tester-1",
            "role": "QA Engineer",
            "skills": ["test", "qa"],
            "supported_tasks": ["test_suite", "test"],
            "cost_profile": {"avg_cost": 500, "cost_unit": "tokens"},
            "status": "available",
            "current_task": None,
        },
    }


def _old_style() -> dict:
    """旧式扁平 agents.json (无 supported_tasks/cost_profile — 同真实 ~/.factory 口径)。"""
    return {
        "backend-1": {
            "id": "backend-1",
            "name": "backend-1",
            "role": "backend-developer",
            "description": "",
            "skills": ["development", "python"],
            "status": "AVAILABLE",
            "current_task": None,
        },
        "flutter-dev": {
            "id": "flutter-dev",
            "name": "Flutter Dev",
            "role": "developer",
            "description": "",
            "skills": ["flutter", "dart"],
            "status": "AVAILABLE",
            "current_task": None,
        },
        "tester-1": {
            "id": "tester-1",
            "name": "tester-1",
            "role": "tester",
            "description": "",
            "skills": ["test"],
            "status": "AVAILABLE",
            "current_task": None,
        },
    }


def _records() -> list[dict]:
    """固定执行记录 (backend-1 高成功率 + flutter-dev 低 + tester-1 无成本)。"""
    return [
        {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
         "task": "后端 API 实现", "result": "success", "result_id": "EXS-001",
         "timestamp": "2026-08-01T00:00:00+00:00", "cost": "0.0012"},
        {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
         "task": "后端 API 实现", "result": "success", "result_id": "EXS-002",
         "timestamp": "2026-08-01T00:00:01+00:00", "cost": "0.0010"},
        {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
         "task": "数据库 Schema 设计", "result": "success", "result_id": "EXS-003",
         "timestamp": "2026-08-01T00:00:02+00:00", "cost": "0.0008"},
        {"intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
         "task": "登录功能", "result": "failed", "result_id": "EXS-004",
         "timestamp": "2026-08-01T00:00:03+00:00", "error": "timeout"},
        {"intent": "run_task", "action": "agent.execute_task", "agent": "flutter-dev",
         "task": "前端页面实现", "result": "failed", "result_id": "EXS-005",
         "timestamp": "2026-08-01T00:00:04+00:00", "error": "compile error"},
        {"intent": "run_task", "action": "agent.execute_task", "agent": "tester-1",
         "task": "测试用例编写", "result": "success", "result_id": "EXS-006",
         "timestamp": "2026-08-01T00:00:05+00:00"},
    ]


def _intent(intent_type: str, **params):
    return INTENT_MOD.IntentObject(intent_type=intent_type, params=params, raw="test")


def _exec_ctx(root: Path, intent=None, **kw):
    return ACT_MOD.ExecutionContext(
        workspace=root,
        session=CTX_MOD.SessionContext(workspace=str(root)),
        user="user",
        intent=intent,
        **kw,
    )


class _FakeOrgCli:
    """Service Layer 桩 (monkeypatch _load_org_cli): 规范项目注册结果。"""

    def __init__(self, *, ok: bool = True, project=None, error=None) -> None:
        self.calls: list[tuple[object, object]] = []
        self.ok = ok
        self.project = project
        self.error = error

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        if not self.ok:
            return {"ok": False, "error": self.error or "注册失败", "exit_code": 1}
        return {
            "ok": True,
            "project": self.project
            or {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


@pytest.fixture
def fake_org(monkeypatch):
    org = _FakeOrgCli()
    monkeypatch.setattr(ACTIONS_MOD, "_load_org_cli", lambda: org)
    return org


def _product(**kw):
    prod = importlib.import_module("factory-console.session.product")
    data = dict(
        name="ScorePocket",
        problem="台球比赛计分麻烦",
        user="台球爱好者",
        core_features=["计分", "比赛记录", "排行榜"],
        raw="我想开发一个台球计分APP",
    )
    data.update(kw)
    return prod.ProductIntent(**data)


def _create_product_on_disk(root: Path, **kw):
    """create_product action 落盘 product.json → 返回 context (需 fake_org)。"""
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _product(**kw)
    result = ACTIONS_MOD.create_product(ctx)
    assert result.ok, result.message
    return ctx


def _matcher(tmp_path: Path, registry: dict | None = None, records: list[dict] | None = None):
    """hermetic AgentMatcher: 显式 registry + 从 records 聚合的 metrics。"""
    reg = registry if registry is not None else _registry2()
    met = AgentMetrics.compute(records if records is not None else _records())
    return AgentMatcher(registry=reg, metrics=met)


def _plan_tasks() -> list[dict]:
    """固定 execution_plan.json 任务 (含 reason, 供 task_owner/agent_reason/trace)。"""
    return [
        {"id": "T1", "name": "后端 API 实现", "agent_type": "backend", "agent": "backend-1",
         "feature": "计分", "epic": "比赛系统",
         "reason": "skill match 100% (python, api, database), 成功率 75%"},
        {"id": "T2", "name": "前端页面实现", "agent_type": "frontend", "agent": "flutter-dev",
         "feature": "客户端", "epic": "客户端",
         "reason": "skill match 100% (flutter, dart, ui, frontend), 成功率 50%"},
    ]


# ================================================================== 1. AgentRegistry 2.0 (验收 A)


def test_registry_load_default_file_missing_falls_back(tmp_path, monkeypatch):
    """agents.json 缺失 → 默认注册表兜底 (backend-1/flutter-dev/tester-1)。"""
    monkeypatch.setattr(AgentRegistry, "DEFAULT_FILE", tmp_path / "nope" / "agents.json")
    reg = AgentRegistry.load()
    assert set(reg) == {"backend-1", "flutter-dev", "tester-1"}


def test_registry_load_from_registry2_file(tmp_path):
    f = _write_json(tmp_path / "agents.json", _registry2())
    reg = AgentRegistry.load(f)
    assert set(reg) == {"backend-1", "flutter-dev", "tester-1"}


def test_registry_load_old_style_derives_extended_fields(tmp_path):
    """旧式扁平格式 → supported_tasks/cost_profile 缺省推导 (Registry 2.0 扩展)。"""
    f = _write_json(tmp_path / "agents.json", _old_style())
    reg = AgentRegistry.load(f)
    assert reg["backend-1"]["supported_tasks"] == ["backend_api", "database_schema", "test"]
    assert reg["backend-1"]["cost_profile"] == {"avg_cost": 1000.0, "cost_unit": "tokens"}


def test_registry_load_old_style_frontend_derivation(tmp_path):
    f = _write_json(tmp_path / "agents.json", _old_style())
    reg = AgentRegistry.load(f)
    assert reg["flutter-dev"]["supported_tasks"] == ["frontend_page", "ui_interaction"]


def test_registry_load_old_style_qa_derivation(tmp_path):
    f = _write_json(tmp_path / "agents.json", _old_style())
    reg = AgentRegistry.load(f)
    assert reg["tester-1"]["supported_tasks"] == ["test_suite", "test"]


def test_registry_load_corrupted_file_falls_back(tmp_path):
    f = tmp_path / "agents.json"
    f.write_text("{not json", encoding="utf-8")
    reg = AgentRegistry.load(f)
    assert set(reg) == {"backend-1", "flutter-dev", "tester-1"}


def test_registry_load_empty_dict_falls_back(tmp_path):
    f = _write_json(tmp_path / "agents.json", {})
    reg = AgentRegistry.load(f)
    assert set(reg) == {"backend-1", "flutter-dev", "tester-1"}


def test_registry_load_non_dict_falls_back(tmp_path):
    f = _write_json(tmp_path / "agents.json", ["not", "a", "dict"])
    reg = AgentRegistry.load(f)
    assert set(reg) == {"backend-1", "flutter-dev", "tester-1"}


def test_registry_load_preserves_extended_fields(tmp_path):
    """Registry 2.0 显式字段原样保留 (不覆盖推导值)。"""
    reg_data = _registry2()
    reg_data["backend-1"]["supported_tasks"] = ["custom_task"]
    reg_data["backend-1"]["cost_profile"] = {"avg_cost": 42, "cost_unit": "usd"}
    f = _write_json(tmp_path / "agents.json", reg_data)
    reg = AgentRegistry.load(f)
    assert reg["backend-1"]["supported_tasks"] == ["custom_task"]
    assert reg["backend-1"]["cost_profile"] == {"avg_cost": 42, "cost_unit": "usd"}


def test_registry_get_known_agent(tmp_path):
    f = _write_json(tmp_path / "agents.json", _registry2())
    agent = AgentRegistry.get("backend-1", f)
    assert agent is not None
    assert agent["id"] == "backend-1"
    assert agent["skills"] == ["python", "api", "database"]


def test_registry_get_unknown_agent(tmp_path):
    f = _write_json(tmp_path / "agents.json", _registry2())
    assert AgentRegistry.get("ghost", f) is None


def test_registry_list_sorted(tmp_path):
    f = _write_json(tmp_path / "agents.json", _registry2())
    ids = [a["id"] for a in AgentRegistry.list(f)]
    assert ids == sorted(ids)
    assert ids == ["backend-1", "flutter-dev", "tester-1"]


def test_registry_all_roles_unique(tmp_path):
    f = _write_json(tmp_path / "agents.json", _registry2())
    roles = AgentRegistry.all_roles(f)
    assert set(roles) == {"Backend Engineer", "Frontend Engineer", "QA Engineer"}
    assert len(roles) == len(set(roles))


def test_registry_skills_normalized_to_strings(tmp_path):
    f = _write_json(tmp_path / "agents.json", {"a1": {"skills": [1, None, "py"]}})
    reg = AgentRegistry.load(f)
    assert reg["a1"]["skills"] == ["1", "None", "py"]


def test_registry_missing_name_defaults_to_id(tmp_path):
    f = _write_json(tmp_path / "agents.json", {"a1": {"role": "R"}})
    reg = AgentRegistry.load(f)
    assert reg["a1"]["name"] == "a1"


def test_registry_default_status_and_current_task(tmp_path):
    f = _write_json(tmp_path / "agents.json", {"a1": {}})
    reg = AgentRegistry.load(f)
    assert reg["a1"]["status"] == "available"
    assert reg["a1"]["current_task"] is None
    assert reg["a1"]["role"] == "Developer"


def test_registry_default_agents_have_extended_fields():
    reg = AgentRegistry._normalize(AGENTS_MOD.DEFAULT_AGENTS)
    for aid in ("backend-1", "flutter-dev", "tester-1"):
        assert reg[aid]["supported_tasks"]
        assert reg[aid]["cost_profile"]["avg_cost"] > 0


def test_registry_derive_supported_tasks_role_backend():
    agent = {"role": "Backend Engineer", "skills": []}
    assert AgentRegistry.derive_supported_tasks(agent) == [
        "backend_api", "database_schema", "test",
    ]


def test_registry_derive_supported_tasks_skill_frontend():
    agent = {"role": "X", "skills": ["flutter", "dart"]}
    assert AgentRegistry.derive_supported_tasks(agent) == ["frontend_page", "ui_interaction"]


def test_registry_derive_supported_tasks_skill_test():
    agent = {"role": "X", "skills": ["test"]}
    assert AgentRegistry.derive_supported_tasks(agent) == ["test_suite", "test"]


def test_registry_derive_supported_tasks_unknown_default():
    agent = {"role": "X", "skills": []}
    assert AgentRegistry.derive_supported_tasks(agent) == [
        "backend_api", "database_schema", "test",
    ]


def test_registry_derive_cost_profile_default():
    assert AgentRegistry.derive_cost_profile({}) == {
        "avg_cost": 1000.0, "cost_unit": "tokens",
    }


def test_registry_derive_task_type_frontend():
    assert AGENTS_MOD._derive_task_type("实现前端页面") == "frontend"
    assert AGENTS_MOD._derive_task_type("写 flutter 组件") == "frontend"
    assert AGENTS_MOD._derive_task_type("优化 ui 布局") == "frontend"
    assert AGENTS_MOD._derive_task_type("界面交互") == "frontend"


def test_registry_derive_task_type_test():
    assert AGENTS_MOD._derive_task_type("编写测试用例") == "test"
    assert AGENTS_MOD._derive_task_type("写 pytest 测试") == "test"
    assert AGENTS_MOD._derive_task_type("qa 回归") == "test"


def test_registry_derive_task_type_backend_default():
    assert AGENTS_MOD._derive_task_type("实现登录功能") == "backend"
    assert AGENTS_MOD._derive_task_type("") == "backend"
    assert AGENTS_MOD._derive_task_type("给 main.py 添加排名功能") == "backend"


# ================================================================== 2. AgentMatcher (验收 B)


def test_matcher_frontend_task_picks_flutter_dev():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "frontend", "name": "前端页面实现"})
    assert result["agent"] == "flutter-dev"


def test_matcher_backend_task_picks_backend_1():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend", "name": "后端 API 实现"})
    assert result["agent"] == "backend-1"


def test_matcher_test_task_picks_tester_1():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "test", "name": "测试用例编写"})
    assert result["agent"] == "tester-1"


def test_matcher_ui_task_picks_frontend():
    m = _matcher(Path("/tmp"))
    assert m.match({"type": "ui", "name": "x"})["agent"] == "flutter-dev"


def test_matcher_flutter_type_picks_frontend():
    m = _matcher(Path("/tmp"))
    assert m.match({"type": "flutter", "name": "x"})["agent"] == "flutter-dev"


def test_matcher_database_type_picks_backend():
    m = _matcher(Path("/tmp"))
    assert m.match({"type": "database", "name": "x"})["agent"] == "backend-1"


def test_matcher_explicit_required_skills_wins():
    m = _matcher(Path("/tmp"))
    result = m.match({"required_skills": ["flutter", "dart"]})
    assert result["agent"] == "flutter-dev"


def test_matcher_custom_agent_wins_by_skills_no_keyword_decision():
    """无硬编码关键词决策: 注册表 skills 驱动 — 更强技能集的 Agent 胜出。"""
    reg = _registry2()
    reg["custom-1"] = {
        "id": "custom-1", "name": "custom-1", "role": "UI Expert",
        "skills": ["flutter", "dart", "ui", "frontend", "react"],
        "cost_profile": {"avg_cost": 900, "cost_unit": "tokens"},
    }
    m = _matcher(Path("/tmp"), registry=reg)
    result = m.match({"type": "frontend", "required_skills": ["flutter", "ui", "react"]})
    assert result["agent"] == "custom-1"


def test_matcher_success_rate_weighting():
    """成功率加权: 同技能同成本, 高成功率 Agent 胜出。"""
    reg = {
        "a": {"id": "a", "role": "R", "skills": ["python"], "cost_profile": {"avg_cost": 100}},
        "b": {"id": "b", "role": "R", "skills": ["python"], "cost_profile": {"avg_cost": 100}},
    }
    metrics = {
        "a": {"success_rate": 0.9, "total_tasks": 10},
        "b": {"success_rate": 0.1, "total_tasks": 10},
    }
    m = AgentMatcher(registry=reg, metrics=metrics)
    assert m.match({"required_skills": ["python"]})["agent"] == "a"


def test_matcher_cost_weighting():
    """成本归一化: 同技能同成功率, 更便宜 Agent 胜出。"""
    reg = {
        "expensive": {"id": "expensive", "role": "R", "skills": ["python"],
                      "cost_profile": {"avg_cost": 1000}},
        "cheap": {"id": "cheap", "role": "R", "skills": ["python"],
                  "cost_profile": {"avg_cost": 100}},
    }
    metrics = {
        "expensive": {"success_rate": 0.5},
        "cheap": {"success_rate": 0.5},
    }
    m = AgentMatcher(registry=reg, metrics=metrics)
    assert m.match({"required_skills": ["python"]})["agent"] == "cheap"


def test_matcher_skill_dominates_success_rate():
    """技能因子主导: 高成功率但零技能匹配的 Agent 不敌技能匹配者。"""
    reg = {
        "no-skill": {"id": "no-skill", "role": "R", "skills": [],
                     "cost_profile": {"avg_cost": 100}},
        "qa": {"id": "qa", "role": "R", "skills": ["test", "qa"],
               "cost_profile": {"avg_cost": 100}},
    }
    metrics = {"no-skill": {"success_rate": 0.9}, "qa": {"success_rate": 0.5}}
    m = AgentMatcher(registry=reg, metrics=metrics)
    assert m.match({"type": "test"})["agent"] == "qa"


def test_matcher_empty_registry_fail_safe():
    m = AgentMatcher(registry={}, metrics={})
    result = m.match({"type": "backend"})
    assert result["agent"] is None
    assert "无可用 Agent" in result["reason"]


def test_matcher_task_without_type_no_crash():
    m = _matcher(Path("/tmp"))
    result = m.match({})
    assert result["agent"] in ("backend-1", "flutter-dev", "tester-1")
    assert "reason" in result


def test_matcher_unknown_type_decides_by_sr_cost():
    """未知 task.type → 技能因子中性, 由成功率/成本决策 (非关键词)。"""
    reg = {
        "top": {"id": "top", "role": "R", "skills": ["python"],
                "cost_profile": {"avg_cost": 500}},
        "bottom": {"id": "bottom", "role": "R", "skills": ["python"],
                   "cost_profile": {"avg_cost": 500}},
    }
    metrics = {"top": {"success_rate": 0.95}, "bottom": {"success_rate": 0.3}}
    m = AgentMatcher(registry=reg, metrics=metrics)
    assert m.match({"type": "quantum_flux"})["agent"] == "top"


def test_matcher_reason_contains_skill_match():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend", "name": "后端 API 实现"})
    assert "skill match" in result["reason"]


def test_matcher_reason_contains_percentage_and_skills():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend", "name": "后端 API 实现"})
    assert "100%" in result["reason"]
    assert "python" in result["reason"]


def test_matcher_reason_contains_success_rate():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend"})
    assert "成功率" in result["reason"]


def test_matcher_reason_format_regex():
    import re

    m = _matcher(Path("/tmp"))
    result = m.match({"type": "frontend", "name": "前端页面实现"})
    assert re.fullmatch(r"skill match \d+% \(.*\), 成功率 \d+%", result["reason"])


def test_matcher_returns_agent_score_reason_keys():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend"})
    assert set(result) == {"agent", "score", "reason"}


def test_matcher_score_bounded():
    m = _matcher(Path("/tmp"))
    result = m.match({"type": "backend"})
    assert 0.0 <= result["score"] <= 1.0


def test_matcher_zero_skill_match_agent_still_returned():
    """零技能命中 → score 0, 仍返回 Agent (确定性 tie-break)。"""
    reg = {"a": {"id": "a", "role": "R", "skills": ["rust"],
                 "cost_profile": {"avg_cost": 100}}}
    m = AgentMatcher(registry=reg, metrics={})
    result = m.match({"type": "frontend"})
    assert result["agent"] == "a"
    assert result["score"] == 0.0
    assert "0%" in result["reason"]


def test_matcher_deterministic_same_input():
    m = _matcher(Path("/tmp"))
    r1 = m.match({"type": "backend", "name": "后端 API 实现"})
    r2 = m.match({"type": "backend", "name": "后端 API 实现"})
    assert r1 == r2


def test_matcher_tie_break_by_id():
    reg = {
        "z-agent": {"id": "z-agent", "role": "R", "skills": ["python"],
                    "cost_profile": {"avg_cost": 100}},
        "a-agent": {"id": "a-agent", "role": "R", "skills": ["python"],
                    "cost_profile": {"avg_cost": 100}},
    }
    m = AgentMatcher(registry=reg, metrics={})
    assert m.match({"required_skills": ["python"]})["agent"] == "a-agent"


def test_matcher_agent_type_derivation_frontend():
    m = _matcher(Path("/tmp"))
    assert m.match({"agent_type": "frontend"})["agent"] == "flutter-dev"


def test_matcher_agent_type_derivation_qa():
    m = _matcher(Path("/tmp"))
    assert m.match({"agent_type": "qa"})["agent"] == "tester-1"


def test_matcher_name_based_derivation():
    m = _matcher(Path("/tmp"))
    assert m.match({"name": "前端页面实现"})["agent"] == "flutter-dev"
    assert m.match({"name": "测试用例编写"})["agent"] == "tester-1"
    assert m.match({"name": "后端 API 实现"})["agent"] == "backend-1"


def test_matcher_no_required_skills_neutral_factor():
    """无必备技能 → 技能因子中性 (1.0), 决策由成功率/成本驱动。"""
    reg = {
        "a": {"id": "a", "role": "R", "skills": ["python"],
              "cost_profile": {"avg_cost": 100}},
        "b": {"id": "b", "role": "R", "skills": ["flutter"],
              "cost_profile": {"avg_cost": 100}},
    }
    metrics = {"a": {"success_rate": 0.8}, "b": {"success_rate": 0.4}}
    m = AgentMatcher(registry=reg, metrics=metrics)
    assert m.match({})["agent"] == "a"


def test_matcher_default_registry_loads_fallback(tmp_path, monkeypatch):
    """缺省 registry → AgentRegistry.load (monkeypatch 到 tmp 文件, hermetic)。"""
    f = _write_json(tmp_path / "agents.json", _registry2())
    monkeypatch.setattr(AgentRegistry, "DEFAULT_FILE", f)
    m = AgentMatcher()
    assert m.match({"type": "frontend"})["agent"] == "flutter-dev"


def test_matcher_reason_for_known_agent():
    m = _matcher(Path("/tmp"))
    result = m.reason_for("backend-1", {"type": "backend", "name": "后端 API 实现"})
    assert result["agent"] == "backend-1"
    assert "skill match" in result["reason"]
    assert "成功率" in result["reason"]


def test_matcher_reason_for_unknown_agent():
    m = _matcher(Path("/tmp"))
    result = m.reason_for("ghost", {"type": "backend"})
    assert result["agent"] == "ghost"
    assert result["reason"] is None


def test_matcher_reason_for_uses_agent_metrics():
    reg = {"a": {"id": "a", "role": "R", "skills": ["python"],
                 "cost_profile": {"avg_cost": 100}}}
    metrics = {"a": {"success_rate": 0.75}}
    m = AgentMatcher(registry=reg, metrics=metrics)
    result = m.reason_for("a", {"required_skills": ["python"]})
    assert "75%" in result["reason"]


def test_matcher_derive_required_skills_explicit_wins():
    task = {"type": "frontend", "required_skills": ["go"]}
    assert AgentMatcher.derive_required_skills(task) == ["go"]


def test_matcher_derive_required_skills_type_mapping():
    assert AgentMatcher.derive_required_skills({"type": "frontend"}) == [
        "flutter", "dart", "ui", "frontend",
    ]
    assert AgentMatcher.derive_required_skills({"type": "test"}) == ["test", "qa"]


def test_matcher_derive_required_skills_agent_type():
    assert AgentMatcher.derive_required_skills({"agent_type": "frontend"})[0] == "flutter"
    assert AgentMatcher.derive_required_skills({"agent_type": "qa"}) == ["test", "qa"]
    assert AgentMatcher.derive_required_skills({"agent_type": "backend"})[0] == "python"


def test_matcher_derive_required_skills_name():
    assert AgentMatcher.derive_required_skills({"name": "前端页面实现"})[0] == "flutter"
    assert AgentMatcher.derive_required_skills({"name": "测试用例"})[0] == "test"


def test_matcher_derive_required_skills_none_task():
    assert AgentMatcher.derive_required_skills(None)[0] == "python"


# ================================================================== 3. AgentMetrics (验收 C)


def test_metrics_compute_empty():
    assert AgentMetrics.compute([]) == {}


def test_metrics_compute_none_records():
    assert AgentMetrics.compute(None) == {}


def test_metrics_compute_totals():
    metrics = AgentMetrics.compute(_records())
    assert metrics["backend-1"]["total_tasks"] == 4
    assert metrics["backend-1"]["success_count"] == 3
    assert metrics["backend-1"]["failed_count"] == 1


def test_metrics_compute_success_rate():
    metrics = AgentMetrics.compute(_records())
    assert metrics["backend-1"]["success_rate"] == 0.75
    assert metrics["flutter-dev"]["success_rate"] == 0.0


def test_metrics_compute_avg_cost_numeric():
    metrics = AgentMetrics.compute(_records())
    assert metrics["backend-1"]["avg_cost"] == pytest.approx(0.0010, abs=1e-6)


def test_metrics_compute_avg_cost_zero_when_absent():
    metrics = AgentMetrics.compute(_records())
    assert metrics["tester-1"]["avg_cost"] == 0.0


def test_metrics_compute_avg_duration_zero_fail_safe():
    """记录无 duration 字段 → avg_duration 0.0 (失败安全)。"""
    metrics = AgentMetrics.compute(_records())
    assert metrics["backend-1"]["avg_duration"] == 0.0


def test_metrics_compute_by_task_type_totals():
    metrics = AgentMetrics.compute(_records())
    by_type = metrics["backend-1"]["by_task_type"]
    assert by_type["backend"]["total"] == 4
    assert by_type["backend"]["success"] == 3


def test_metrics_compute_by_task_type_multiple_types():
    records = [
        {"agent": "a", "result": "success", "task": "前端页面实现"},
        {"agent": "a", "result": "success", "task": "后端 API 实现"},
        {"agent": "a", "result": "failed", "task": "测试用例编写"},
    ]
    metrics = AgentMetrics.compute(records)
    by_type = metrics["a"]["by_task_type"]
    assert by_type["frontend"] == {"total": 1, "success": 1}
    assert by_type["backend"] == {"total": 1, "success": 1}
    assert by_type["test"] == {"total": 1, "success": 0}


def test_metrics_compute_explicit_task_type_field_wins():
    records = [
        {"agent": "a", "result": "success", "task": "神秘任务", "task_type": "custom"},
    ]
    metrics = AgentMetrics.compute(records)
    assert metrics["a"]["by_task_type"] == {"custom": {"total": 1, "success": 1}}


def test_metrics_compute_success_variants():
    for result in ("success", "ok", "passed", "completed", "done"):
        metrics = AgentMetrics.compute([{"agent": "a", "result": result}])
        assert metrics["a"]["success_count"] == 1, result


def test_metrics_compute_unknown_agent_bucket():
    metrics = AgentMetrics.compute([{"task": "x", "result": "success"}])
    assert metrics["unknown"]["total_tasks"] == 1


def test_metrics_compute_non_dict_records_ignored():
    metrics = AgentMetrics.compute(["junk", {"agent": "a", "result": "success"}])
    assert set(metrics) == {"a"}


def test_metrics_compute_cost_string_summary():
    records = [{"agent": "a", "result": "success", "cost": "0.5 · 320 tokens"}]
    metrics = AgentMetrics.compute(records)
    assert metrics["a"]["avg_cost"] == pytest.approx(0.5)


def test_metrics_load_from_records_file(tmp_path):
    f = _write_json(tmp_path / "records.json", _records())
    metrics = AgentMetrics.load_from_records(f)
    assert metrics["backend-1"]["total_tasks"] == 4


def test_metrics_load_from_records_missing_file(tmp_path):
    assert AgentMetrics.load_from_records(tmp_path / "nope.json") == {}


def test_metrics_load_from_records_corrupted(tmp_path):
    f = tmp_path / "records.json"
    f.write_text("oops", encoding="utf-8")
    assert AgentMetrics.load_from_records(f) == {}


def test_metrics_save_and_load_roundtrip(tmp_path):
    metrics = AgentMetrics.compute(_records())
    path = AgentMetrics.save(tmp_path / "sub" / "agent_metrics.json", metrics)
    assert path.is_file()
    loaded = AgentMetrics.load(path)
    assert loaded["backend-1"]["success_rate"] == 0.75
    assert loaded["backend-1"]["by_task_type"]["backend"]["total"] == 4


def test_metrics_save_creates_parent_dirs(tmp_path):
    path = AgentMetrics.save(tmp_path / "a" / "b" / "m.json", {"x": {}})
    assert path.parent.is_dir()


def test_metrics_load_missing_fail_safe(tmp_path):
    assert AgentMetrics.load(tmp_path / "nope.json") == {}


def test_metrics_load_corrupted_fail_safe(tmp_path):
    f = tmp_path / "m.json"
    f.write_text("{bad", encoding="utf-8")
    assert AgentMetrics.load(f) == {}


def test_metrics_load_non_dict_fail_safe(tmp_path):
    f = _write_json(tmp_path / "m.json", [1, 2, 3])
    assert AgentMetrics.load(f) == {}


def test_metrics_entry_shape():
    metrics = AgentMetrics.compute(_records())
    entry = metrics["backend-1"]
    assert set(entry) >= {
        "agent", "total_tasks", "success_count", "failed_count",
        "avg_cost", "avg_duration", "success_rate", "by_task_type",
    }


def test_metrics_success_rate_zero_total():
    metrics = AgentMetrics.compute([])
    assert metrics == {}


# ================================================================== 4. Execution Plan Reasoning (验收 D)


def test_assignment_from_tasks_reason_present(tmp_path):
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks(
        {"tasks": _plan_tasks()}, matcher=matcher
    )
    assert all(a["reason"] for a in plan["tasks"])


def test_assignment_reason_mentions_skill_match(tmp_path):
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks(
        {"tasks": [{"id": "T1", "name": "后端 API 实现", "agent_type": "backend"}]},
        matcher=matcher,
    )
    assert "skill match" in plan["tasks"][0]["reason"]


def test_assignment_agent_decision_unchanged_with_matcher(tmp_path):
    """Agent 决策不变 (select_agent_fn 兼容): frontend→flutter-dev。"""
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks(
        {"tasks": _plan_tasks()},
        select_agent_fn=ACTIONS_MOD.select_agent,
        matcher=matcher,
    )
    by_type = {a["agent_type"]: a["agent"] for a in plan["tasks"]}
    assert by_type["frontend"] == "flutter-dev"
    assert by_type["backend"] == "backend-1"


def test_assignment_custom_select_fn_reason_none_for_unknown(tmp_path):
    """自定义 select fn → agent 为注册表外 Agent → reason None (失败安全)。"""
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks(
        {"tasks": [{"id": "T1", "name": "x"}]},
        select_agent_fn=lambda intent, context=None: "custom-agent",
        matcher=matcher,
    )
    assert plan["tasks"][0]["agent"] == "custom-agent"
    assert plan["tasks"][0]["reason"] is None


def test_assignment_default_matcher_lazy(tmp_path, monkeypatch):
    """缺省 matcher → 惰性 AgentMatcher (默认注册表 → tmp, hermetic)。"""
    f = _write_json(tmp_path / "agents.json", _registry2())
    rec = _write_json(tmp_path / "records.json", _records())
    monkeypatch.setattr(AgentRegistry, "DEFAULT_FILE", f)
    monkeypatch.setattr(AGENTS_MOD, "DEFAULT_RECORDS_FILE", rec)
    plan = PIPE_MOD.AgentAssignment.from_tasks({"tasks": _plan_tasks()})
    assert all(a["reason"] for a in plan["tasks"])


def test_assignment_empty_tree_count_zero(tmp_path):
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks({"tasks": []}, matcher=matcher)
    assert plan["count"] == 0
    assert plan["tasks"] == []


def test_prepare_project_execution_plan_contains_reason(tmp_path, fake_org, monkeypatch):
    """D 落盘: prepare_project → execution_plan.json 含 reason。"""
    f = _write_json(tmp_path / "agents.json", _registry2())
    rec = _write_json(tmp_path / "records.json", _records())
    monkeypatch.setattr(AgentRegistry, "DEFAULT_FILE", f)
    monkeypatch.setattr(AGENTS_MOD, "DEFAULT_RECORDS_FILE", rec)
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _create_product_on_disk(root)
    result = ACTIONS_MOD.prepare_project(ctx)
    assert result.ok
    data = _read_json(root / "projects" / "scorepocket" / "execution_plan.json")
    assert data["tasks"]
    assert all(t["reason"] for t in data["tasks"])


def test_prepare_project_plan_agent_mapping_intact(tmp_path, fake_org, monkeypatch):
    """D 回归: 计划 agent 映射不变 (frontend→flutter-dev / 其余→backend-1)。"""
    f = _write_json(tmp_path / "agents.json", _registry2())
    monkeypatch.setattr(AgentRegistry, "DEFAULT_FILE", f)
    root = tmp_path / "ws"
    root.mkdir()
    ctx = _create_product_on_disk(root)
    ACTIONS_MOD.prepare_project(ctx)
    data = _read_json(root / "projects" / "scorepocket" / "execution_plan.json")
    for task in data["tasks"]:
        expected = (
            "flutter-dev"
            if task["agent_type"] == "frontend"
            else "backend-1"
        )
        assert task["agent"] == expected


def test_orchestrator_default_execute_fn_reason_passthrough(monkeypatch, tmp_path):
    """orchestrator._default_execute_fn 透传 plan reason 到执行结果。"""
    def fake_execute_task(ctx):
        return ACT_MOD.ActionResult(
            ok=True, status=ACT_MOD.STATUS_OK, message="ok",
            data={"execution": {"artifact": "a.patch", "cost": "0.1"}},
        )

    monkeypatch.setattr(ACTIONS_MOD, "execute_task", fake_execute_task)
    result = ORCH_MOD._default_execute_fn(
        {"name": "T1", "agent": "backend-1", "reason": "skill match 100%"},
        Path("/tmp/proj"), Path("/tmp/ws"),
    )
    assert result["reason"] == "skill match 100%"


def test_orchestrator_default_execute_fn_reason_missing_fail_safe(monkeypatch, tmp_path):
    """旧式 plan 无 reason → 空串 (失败安全)。"""
    def fake_execute_task(ctx):
        return ACT_MOD.ActionResult(ok=True, status=ACT_MOD.STATUS_OK, message="ok",
                                    data={"execution": {}})

    monkeypatch.setattr(ACTIONS_MOD, "execute_task", fake_execute_task)
    result = ORCH_MOD._default_execute_fn(
        {"name": "T1", "agent": "backend-1"}, Path("/tmp/proj"), Path("/tmp/ws")
    )
    assert result["reason"] == ""


def test_assignment_reason_preserves_feature_epic(tmp_path):
    matcher = _matcher(tmp_path)
    plan = PIPE_MOD.AgentAssignment.from_tasks(
        {"tasks": _plan_tasks()}, matcher=matcher
    )
    assert plan["tasks"][0]["feature"] == "计分"
    assert plan["tasks"][0]["epic"] == "比赛系统"


# ================================================================== 5. Workforce Dashboard (验收 E)


def test_workforce_action_returns_agents(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert result.ok
    assert result.data["count"] == 3


def test_workforce_action_agent_ids(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    ids = [a["id"] for a in result.data["agents"]]
    assert ids == ["backend-1", "flutter-dev", "tester-1"]


def test_workforce_action_role_field(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    by_id = {a["id"]: a for a in result.data["agents"]}
    assert by_id["backend-1"]["role"] == "Backend Engineer"
    assert by_id["flutter-dev"]["role"] == "Frontend Engineer"
    assert by_id["tester-1"]["role"] == "QA Engineer"


def test_workforce_action_status_field(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert all(a["status"] for a in result.data["agents"])


def test_workforce_action_success_rate_merged(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    by_id = {a["id"]: a for a in result.data["agents"]}
    assert by_id["backend-1"]["success_rate"] == 0.75
    assert by_id["flutter-dev"]["success_rate"] == 0.0


def test_workforce_action_total_tasks_merged(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    by_id = {a["id"]: a for a in result.data["agents"]}
    assert by_id["backend-1"]["total_tasks"] == 4


def test_workforce_action_no_metrics_none_success_rate(tmp_path, monkeypatch):
    """无绩效数据 → success_rate None / total 0 (不回落真实 ~/.factory 记录)。"""
    monkeypatch.setattr(AGENTS_MOD, "DEFAULT_RECORDS_FILE", tmp_path / "nope" / "records.json")
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    by_id = {a["id"]: a for a in result.data["agents"]}
    assert by_id["backend-1"]["success_rate"] is None
    assert by_id["backend-1"]["total_tasks"] == 0


def test_workforce_action_metrics_file_preferred(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    _write_json(
        tmp_path / "exec" / "agent_metrics.json",
        {"backend-1": {"success_rate": 0.5, "total_tasks": 99}},
    )
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    by_id = {a["id"]: a for a in result.data["agents"]}
    assert by_id["backend-1"]["total_tasks"] == 99
    assert by_id["backend-1"]["success_rate"] == 0.5


def test_workforce_action_render_view(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    _write_json(tmp_path / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert result.data["header"] == ["id", "role", "status", "success_rate", "total_tasks"]
    assert len(result.data["rows"]) == 3
    assert result.data["rows"][0][0] == "backend-1"


def test_workforce_action_message(tmp_path):
    _write_json(tmp_path / "agents" / "agents.json", _registry2())
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path))
    assert result.message == "团队共 3 名 Agent"


def test_workforce_action_no_product_needed(tmp_path):
    """Workforce 查询不依赖产品/项目 (全局团队视角)。"""
    result = ACTIONS_MOD.workforce(_exec_ctx(tmp_path / "empty"))
    assert result.ok


def test_workforce_intent_view_team():
    intent = INTENT_MOD.KeywordIntentParser().parse("查看团队")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_intent_team_status_priority():
    """\"团队状态\" → workforce (不被 show_status 的 \"状态\" 抢)。"""
    intent = INTENT_MOD.KeywordIntentParser().parse("团队状态")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_intent_bare_team():
    intent = INTENT_MOD.KeywordIntentParser().parse("团队")
    assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_intent_variants():
    for text in ("查看团队", "团队状态", "团队成员", "团队情况"):
        intent = INTENT_MOD.KeywordIntentParser().parse(text)
        assert intent is not None
        assert intent.intent_type == INTENT_MOD.INTENT_WORKFORCE


def test_workforce_router_mapping():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["workforce"] == "workforce"


def test_workforce_action_registered():
    action = ACTIONS_MOD.build_default_actions().get("workforce")
    assert action is not None
    assert action.handler is ACTIONS_MOD.workforce
    assert action.metadata["sensitive"] is False
    assert action.metadata["category"] == "workforce"


def test_workforce_not_sensitive_confirm():
    gate = CONF_MOD.ConfirmationGate()
    assert gate.confirm("workforce", _intent("workforce")) is True


def test_workforce_snapshot_shape(tmp_path):
    rows = AGENTS_MOD.workforce_snapshot(
        agents_file=_write_json(tmp_path / "agents.json", _registry2()),
        records_file=_write_json(tmp_path / "records.json", _records()),
    )
    assert len(rows) == 3
    row = rows[0]
    assert set(row) >= {"id", "name", "role", "status", "success_rate", "total_tasks", "avg_cost"}


def test_workforce_snapshot_fallback_default_registry(tmp_path):
    """agents_file 不存在 → 默认注册表兜底 (失败安全)。"""
    rows = AGENTS_MOD.workforce_snapshot(agents_file=tmp_path / "nope.json")
    assert {r["id"] for r in rows} == {"backend-1", "flutter-dev", "tester-1"}


# ================================================================== 6. Task Owner (验收 F)


def _project_with_state(root: Path, slug: str = "demo", tasks=None, name="DemoApp"):
    pdir = root / "projects" / slug
    _write_json(pdir / "product.json", {"name": name})
    _write_json(pdir / "project.json", {"name": name, "slug": slug})
    state = {"project": slug, "status": "development", "tasks": tasks or []}
    _write_json(pdir / "execution_state.json", state)
    return pdir


def test_task_owner_from_state(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_state(
        root,
        tasks=[
            {"id": "T1", "name": "后端 API 实现", "agent": "backend-1", "status": "completed"},
            {"id": "T2", "name": "前端页面实现", "agent": "flutter-dev", "status": "pending"},
        ],
    )
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.ok
    assert result.data["agent"] == "flutter-dev"
    assert result.data["task"] == "前端页面实现"
    assert result.data["project"] == "demo"


def test_task_owner_last_task_wins(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_state(
        root,
        tasks=[
            {"id": "T1", "name": "第一个任务", "agent": "backend-1"},
            {"id": "T2", "name": "最近任务", "agent": "tester-1"},
        ],
    )
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.data["agent"] == "tester-1"
    assert result.data["task"] == "最近任务"


def test_task_owner_skips_task_without_agent(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_state(
        root,
        tasks=[
            {"id": "T1", "name": "无负责人", "agent": None},
            {"id": "T2", "name": "有负责人", "agent": "backend-1"},
        ],
    )
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.data["agent"] == "backend-1"


def test_task_owner_falls_back_to_records(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _write_json(root / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.ok
    assert result.data["agent"] in ("backend-1", "flutter-dev", "tester-1")
    assert result.data["task"]


def test_task_owner_falls_back_when_state_missing(tmp_path):
    """无产品/状态 → 回落 execution_records。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_json(root / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.data["agent"] == "tester-1"  # 记录末条 (最近)


def test_task_owner_no_data_message(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.ok
    assert result.data["agent"] is None
    assert "未找到任务负责人" in result.message


def test_task_owner_corrupted_state_falls_back(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    _write_json(pdir / "product.json", {"name": "DemoApp"})
    (pdir / "execution_state.json").write_text("{broken", encoding="utf-8")
    _write_json(root / "exec" / "execution_records.json", _records())
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert result.ok
    assert result.data["agent"] is not None


def test_task_owner_message_format(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_state(
        root,
        tasks=[{"id": "T1", "name": "记录比分", "agent": "backend-1", "status": "completed"}],
    )
    result = ACTIONS_MOD.task_owner(_exec_ctx(root))
    assert "最近任务「记录比分」由 backend-1 负责" in result.message


def test_task_owner_intent_who_responsible():
    intent = INTENT_MOD.KeywordIntentParser().parse("谁负责这个任务")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_TASK_OWNER


def test_task_owner_intent_variants():
    for text in ("谁负责", "谁在做", "谁开发", "谁负责这个任务"):
        intent = INTENT_MOD.KeywordIntentParser().parse(text)
        assert intent is not None
        assert intent.intent_type == INTENT_MOD.INTENT_TASK_OWNER


def test_task_owner_router_and_registered():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["task_owner"] == "task_owner"
    action = ACTIONS_MOD.build_default_actions().get("task_owner")
    assert action is not None
    assert action.metadata["sensitive"] is False


# ================================================================== 7. Agent Reason (验收 G)


def _project_with_plan(root: Path, slug: str = "demo", plan=None):
    pdir = root / "projects" / slug
    _write_json(pdir / "product.json", {"name": "DemoApp"})
    plan = plan if plan is not None else {"tasks": _plan_tasks(), "count": 2}
    _write_json(pdir / "execution_plan.json", plan)
    return pdir


def test_agent_reason_from_plan(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_plan(root)
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert result.ok
    assert result.data["reason"] == (
        "skill match 100% (python, api, database), 成功率 75%"
    )
    assert result.data["agent"] == "backend-1"
    assert result.data["task"] == "后端 API 实现"


def test_agent_reason_message(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_plan(root)
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert "选择 backend-1 的理由" in result.message
    assert "skill match" in result.message


def test_agent_reason_no_plan(tmp_path):
    """有产品无 plan → ok + reason None + 明确提示。"""
    root = tmp_path / "ws"
    root.mkdir()
    _write_json(root / "projects" / "demo" / "product.json", {"name": "DemoApp"})
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert result.ok
    assert result.data["reason"] is None
    assert "未找到 Agent 选择理由" in result.message


def test_agent_reason_plan_without_reason(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _project_with_plan(
        root,
        plan={"tasks": [{"id": "T1", "name": "x", "agent": "backend-1"}], "count": 1},
    )
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert result.data["reason"] is None
    assert "无 reason" in result.message


def test_agent_reason_no_product_error(tmp_path):
    """无产品 → 明确错误 (同 project_progress 口径), 不静默。"""
    root = tmp_path / "ws"
    root.mkdir()
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert result.ok is False
    assert "未找到产品定义" in result.message


def test_agent_reason_corrupted_plan_fail_safe(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    _write_json(pdir / "product.json", {"name": "DemoApp"})
    (pdir / "execution_plan.json").write_text("{bad", encoding="utf-8")
    result = ACTIONS_MOD.agent_reason(_exec_ctx(root))
    assert result.ok
    assert result.data["reason"] is None


def test_agent_reason_intent_why():
    intent = INTENT_MOD.KeywordIntentParser().parse("为什么选择 backend-1")
    assert intent is not None
    assert intent.intent_type == INTENT_MOD.INTENT_AGENT_REASON


def test_agent_reason_intent_variants():
    for text in ("为什么选择", "为什么是", "为什么选"):
        intent = INTENT_MOD.KeywordIntentParser().parse(text)
        assert intent is not None
        assert intent.intent_type == INTENT_MOD.INTENT_AGENT_REASON


def test_agent_reason_router_and_registered():
    routes = ROUTER_MOD.IntentRouter().routes()
    assert routes["agent_reason"] == "agent_reason"
    action = ACTIONS_MOD.build_default_actions().get("agent_reason")
    assert action is not None
    assert action.metadata["sensitive"] is False


# ================================================================== 8. Production Trace (验收 H)


def _trace_project(tmp_path: Path, slug: str = "demo", with_records=True):
    """完整 trace fixture: product/project/state/validation + workspace records。"""
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / slug
    _write_json(pdir / "product.json", {"name": "DemoApp"})
    _write_json(pdir / "project.json", {"name": "DemoApp", "slug": slug})
    _write_json(
        pdir / "execution_state.json",
        {
            "project": slug,
            "status": "delivered",
            "tasks": [
                {"id": "T1", "name": "后端 API 实现", "agent": "backend-1",
                 "feature": "计分", "epic": "比赛系统", "status": "completed",
                 "artifact": "patches/p1.patch", "validation": "passed"},
                {"id": "T2", "name": "前端页面实现", "agent": "flutter-dev",
                 "feature": "客户端", "epic": "客户端", "status": "completed",
                 "artifact": "patches/p2.patch", "validation": "passed"},
            ],
        },
    )
    _write_json(
        pdir / "validation_result.json",
        {"success": True, "tests_total": 6, "tests_passed": 6,
         "tests_failed": 0, "errors": []},
    )
    if with_records:
        _write_json(
            root / "exec" / "execution_records.json",
            [
                {"agent": "backend-1", "task": "后端 API 实现", "result": "success",
                 "cost": "0.0012"},
                {"agent": "flutter-dev", "task": "前端页面实现", "result": "success",
                 "cost": "0.5 · 320 tokens"},
            ],
        )
    return root, pdir


def test_trace_build_project_meta(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["project"] == {"name": "DemoApp", "slug": "demo"}


def test_trace_build_features_grouped(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    names = [f["name"] for f in trace["features"]]
    assert names == ["计分", "客户端"]


def test_trace_build_task_chain_fields(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    task = trace["features"][0]["tasks"][0]
    assert task["id"] == "T1"
    assert task["name"] == "后端 API 实现"
    assert task["agent"] == "backend-1"
    assert task["status"] == "completed"
    assert task["artifact"] == "patches/p1.patch"
    assert task["validation"] == "passed"


def test_trace_build_cost_from_records(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    task = trace["features"][0]["tasks"][0]
    assert task["cost"] == pytest.approx(0.0012)


def test_trace_build_cost_string_summary(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    task = trace["features"][1]["tasks"][0]
    assert task["cost"] == pytest.approx(0.5)


def test_trace_build_cost_total(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["cost_total"] == pytest.approx(0.5012)


def test_trace_build_cost_zero_without_records(tmp_path):
    root, pdir = _trace_project(tmp_path, with_records=False)
    trace = ProductionTrace.build(pdir, workspace=root)
    assert all(t["cost"] == 0 for f in trace["features"] for t in f["tasks"])
    assert trace["cost_total"] == 0


def test_trace_build_validation_summary(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["validation"] == {
        "success": True, "tests_total": 6, "tests_passed": 6,
        "tests_failed": 0, "errors": [],
    }


def test_trace_build_counts(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["tasks_total"] == 2
    assert trace["tasks_completed"] == 2
    assert trace["agents"] == ["backend-1", "flutter-dev"]


def test_trace_build_missing_state_fail_safe(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    _write_json(pdir / "project.json", {"name": "DemoApp"})
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["features"] == []
    assert trace["tasks_total"] == 0
    assert trace["validation"] == {}


def test_trace_build_ungrouped_feature_fallback(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    _write_json(
        pdir / "execution_state.json",
        {"tasks": [{"id": "T1", "name": "x", "agent": "backend-1", "status": "pending"}]},
    )
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["features"][0]["name"] == ProductionTrace.UNGROUPED_FEATURE


def test_trace_build_corrupted_sources_fail_safe(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "execution_state.json").write_text("{bad", encoding="utf-8")
    (pdir / "validation_result.json").write_text("nope", encoding="utf-8")
    trace = ProductionTrace.build(pdir, workspace=root)
    assert trace["tasks_total"] == 0
    assert trace["validation"] == {}


def test_trace_save_writes_file(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    path = ProductionTrace.save(pdir, trace)
    assert path == pdir / "production_trace.json"
    assert path.is_file()


def test_trace_save_roundtrip(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = ProductionTrace.build(pdir, workspace=root)
    ProductionTrace.save(pdir, trace)
    loaded = _read_json(pdir / "production_trace.json")
    assert loaded == trace


def test_write_production_trace_convenience(tmp_path):
    root, pdir = _trace_project(tmp_path)
    trace = AUDIT_MOD.write_production_trace(pdir, workspace=root)
    assert (pdir / "production_trace.json").is_file()
    assert trace["tasks_total"] == 2


# ================================================================== 9. 回归 (验收 K)


def test_regression_select_agent_explicit_agent_id():
    assert ACTIONS_MOD.select_agent(_intent("run_task", agent_id="custom-9")) == "custom-9"


def test_regression_select_agent_frontend_keywords():
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="实现前端页面")) == "flutter-dev"
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="写 flutter 组件")) == "flutter-dev"


def test_regression_select_agent_default_backend():
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="实现登录功能")) == "backend-1"
    assert ACTIONS_MOD.select_agent(_intent("run_task", objective="")) == "backend-1"


def test_regression_select_agent_none_safe():
    assert ACTIONS_MOD.select_agent(None) == "backend-1"


def test_regression_execute_task_reason_present(monkeypatch, tmp_path):
    """execute_task 仍正常 + 结果含 reason (Matcher 附加, 不改变决策)。"""
    root = tmp_path / "ws"
    root.mkdir()

    class FakeExec:
        def __init__(self):
            self.calls = []

        def cmd_exec_run(self, root, args):
            self.calls.append((root, args))
            return {"ok": True, "exit_code": 0, "artifacts": [{"path": "a.patch"}],
                    "usage": {"cost_usd": 0.1, "total_tokens": 100}}

    fake = FakeExec()
    monkeypatch.setattr(ACTIONS_MOD, "_load_exec_cli", lambda: fake)
    intent = _intent("run_task", objective="实现登录功能")
    result = ACTIONS_MOD.build_default_actions().get("agent.execute_task").execute(
        _exec_ctx(root, intent=intent)
    )
    assert result.ok
    assert fake.calls[0][1].agent == "backend-1"
    assert "reason" in result.data["execution"]
    assert "skill match" in result.data["execution"]["reason"]


def test_regression_build_default_actions_baseline():
    reg = ACTIONS_MOD.build_default_actions()
    for name in ("create_project", "create_product", "list_projects", "show_status",
                 "agent.execute_task", "generate_prd", "prepare_project",
                 "execute_project", "project_progress", "repair_task", "accept_project",
                 "workforce", "task_owner", "agent_reason"):
        assert reg.get(name) is not None, name


def test_regression_router_baseline_intents():
    routes = ROUTER_MOD.IntentRouter().routes()
    for intent_type, action in {
        "create_project": "create_project",
        "run_task": "agent.execute_task",
        "execute_project": "execute_project",
        "project_progress": "project_progress",
        "accept_project": "accept_project",
    }.items():
        assert routes[intent_type] == action


def test_regression_intent_baseline_parse():
    assert INTENT_MOD.KeywordIntentParser().parse("实现登录功能").intent_type == "run_task"
    assert INTENT_MOD.KeywordIntentParser().parse("项目进度").intent_type == "project_progress"
    assert INTENT_MOD.KeywordIntentParser().parse("生成PRD").intent_type == "generate_prd"


def test_regression_orchestrator_execute_project_smoke(tmp_path):
    """orchestrator.execute_project 不受影响 (mock execute_fn, 含 reason plan)。"""
    root = tmp_path / "ws"
    root.mkdir()
    pdir = root / "projects" / "demo"
    _write_json(pdir / "project.json", {"name": "DemoApp"})
    _write_json(
        pdir / "execution_plan.json",
        {"tasks": [
            {"id": "T1", "name": "后端 API 实现", "agent": "backend-1",
             "agent_type": "backend", "reason": "skill match 100%"},
        ], "count": 1},
    )
    calls = []

    def execute_fn(task, project_dir, workspace):
        calls.append(task)
        return {"success": True, "artifact": "a.patch", "cost": "0.1",
                "reason": task.get("reason", "")}

    orch = ORCH_MOD.ExecutionOrchestrator(root)
    result = orch.execute_project("demo", execute_fn=execute_fn)
    assert result.completed_tasks == 1
    assert result.failed_tasks == 0
    # S10-055: 执行完成 + 验证通过 → 停在 USER_ACCEPTANCE (人工验收门, 不自动交付)
    assert result.status == ORCH_MOD.Lifecycle.USER_ACCEPTANCE
    assert calls[0]["reason"] == "skill match 100%"


def test_regression_metrics_records_append_unchanged(tmp_path):
    """audit.record_execution 追加行为不变 (metrics 兼容消费)。"""
    rec_file = _write_json(tmp_path / "exec" / "execution_records.json", _records())
    AUDIT_MOD.record_execution(
        {"agent": "backend-1", "task": "新任务", "result": "success"}, rec_file
    )
    records = AUDIT_MOD.load_records(rec_file)
    assert len(records) == 7
    metrics = AgentMetrics.compute(records)
    assert metrics["backend-1"]["total_tasks"] == 5
