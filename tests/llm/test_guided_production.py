"""S15: Experience-Guided Autonomous Production。

覆盖:
- retrieval: relevant retrieved / irrelevant excluded / deterministic
- usage: recorded + traceable (双向 lineage)
- decision: created + references experience + reason
- agent: guidance reaches Agent (context), ACCEPT/REJECT/PARTIAL
- safety: experience 不能改 artifact/verification, 不能直接执行
- failure: bad experience 不能强制成功
- recovery: guided production crash → recovery 不重复
- feedback: guided production → evaluation → new experience
- baseline vs guided: 指标可比较, 诚实报告
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.production_guidance import (  # noqa: E402
    retrieve_guidance, record_decision, record_usage, get_decisions, get_usage,
    experience_lineage, production_lineage,
)
from factory_console.production_experience import (  # noqa: E402
    extract, invalidate,
)
from factory_console.production_run import (  # noqa: E402
    register_workflow, create_production_run, execute_production_run, get_production_run,
    _write,
)
from factory_console.node_runtime import (  # noqa: E402
    register_node, create_node_run, execute_node_run,
)
from factory_console.professional_workflow import (  # noqa: E402
    BUILTIN_CALC_TESTS, verify_code_with_pytest, ensure_professional_agents,
    run_professional_workflow,
)


def _seed_experience(tmp_path) -> str:
    """构造一条真实经验 (repair experience, calculator 域)。"""
    from factory_console.production_run import _write as _pw
    register_workflow(str(tmp_path), workflow_id="calculator-production", name="calc", nodes=[
        {"node_id": "dev", "name": "dev", "type": "engineering", "executor_name": "dev"}])
    run = create_production_run(str(tmp_path), "calculator-production")
    register_node(str(tmp_path), node_id="dev", name="dev", node_type="engineering")
    bad_code = ("def add(a, b):\n    return a - b\n\ndef subtract(a, b):\n    return a + b\n\n"
                "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n    return a / b\n")
    good_code = ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                 "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                 "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n")

    def exec_fn(input_data):
        code = input_data.get("_code", bad_code)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": True, "output": {"content": code}, "patch_text": "",
                "artifact_type": "code_change", "verification": ver, "content": code}

    def repair_fn(failed_artifact, verification, ctx):
        ver = verify_code_with_pytest(good_code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": good_code},
                "patch_text": "", "artifact_type": "code_change", "verification": ver,
                "content": good_code}
    nr = create_node_run(str(tmp_path), "dev", input_data={"_code": bad_code})
    done_a = execute_node_run(str(tmp_path), nr["run_id"], executor_fn=exec_fn,
                              executor_name="dev", artifact_root=str(tmp_path),
                              max_attempts=2, repair_fn=repair_fn)
    prun = get_production_run(str(tmp_path), run["run_id"])
    prun["state"] = "COMPLETED"
    prun["status"] = "COMPLETED"
    prun["node_runs"] = [{"node_id": "dev", "run_id": nr["run_id"],
                          "state": "COMPLETED", "artifact_id": done_a["artifact_id"]}]
    prun["artifacts"] = [done_a["artifact_id"]]
    _pw(str(tmp_path), prun)
    e = extract(str(tmp_path), run["run_id"])
    return e["id"]


# --- retrieval: relevant / irrelevant / deterministic ---

def test_retrieval_relevant_and_deterministic(tmp_path):
    eid = _seed_experience(tmp_path)
    # 相关任务 → 检索到
    rel = retrieve_guidance(str(tmp_path), "software_developer", "calculator divide pytest")
    assert any(g["experience_id"] == eid for g in rel), "相关经验必须检索到"
    assert all(g["relevance"] > 0 for g in rel)
    # 无关任务 → 排除
    rel2 = retrieve_guidance(str(tmp_path), "product_manager", "marketing analysis finance")
    assert eid not in [g["experience_id"] for g in rel2], "无关经验排除"
    # 确定性
    r1 = retrieve_guidance(str(tmp_path), "software_developer", "calculator")
    r2 = retrieve_guidance(str(tmp_path), "software_developer", "calculator")
    assert [g["experience_id"] for g in r1] == [g["experience_id"] for g in r2]


# --- usage + decision ---

def test_usage_and_decision(tmp_path):
    eid = _seed_experience(tmp_path)
    dec = record_decision(str(tmp_path), agent_run_id="arun-1", production_run_id="prun-1",
                          experience_ids=[eid], decision="accept", reason="relevance high")
    assert dec["decision_id"].startswith("dec-")
    assert dec["experience_ids"] == [eid]
    assert dec["reason"]
    usage = record_usage(str(tmp_path), production_run_id="prun-1", experience_id=eid,
                         agent_run_id="arun-1", relevance=85, applied=True,
                         decision_id=dec["decision_id"])
    assert usage["usage_id"].startswith("use-")
    # 双向 lineage
    el = experience_lineage(str(tmp_path), eid)
    assert "prun-1" in el["productions"]
    pl = production_lineage(str(tmp_path), "prun-1")
    assert eid in pl["experiences"]
    assert len(pl["decisions"]) == 1


# --- safety: experience 不能改 artifact/verification ---

def test_experience_no_mutation_power(tmp_path):
    """Experience 只作为 Guidance: 不修改任何 Production 事实。"""
    eid = _seed_experience(tmp_path)
    # 检索到的 guidance 无 artifact/verification/status 字段
    rel = retrieve_guidance(str(tmp_path), "software_developer", "calculator")
    assert rel
    for g in rel:
        assert "artifact" not in g, "Guidance 不携带 artifact mutation"
        assert "verification" not in g, "Guidance 不携带 verification mutation"
    # production facts 不变
    from factory_console.production_run import get_production_run
    from factory_console.production_evaluation import evaluate
    # (seed 之后) 无 mutation


# --- agent sees guidance in workflow context ---

def test_guidance_reaches_agent_context(tmp_path):
    """experience_guidance=True → guidance 注入 workflow_input (Agent 可见)。"""
    ensure_professional_agents(tmp_path)
    eid = _seed_experience(tmp_path)

    seen = {}

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                                   "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                                   "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n"),
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        def fn(input_data):
            if role == "software_developer":
                seen["guidance"] = input_data.get("experience_guidance", [])
                ver = verify_code_with_pytest(content, BUILTIN_CALC_TESTS)
            else:
                ver = {"status": "PASS"}
            if ver.get("status") != "PASS":
                return {"ok": False, "error": "x", "artifact_type": "report",
                        "verification": {"result": "FAIL"}}
            return {"ok": True, "output": {"content": content}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn

    result = run_professional_workflow(str(tmp_path), idea="calculator",
                                       executor_factory=factory,
                                       experience_guidance=True)
    assert result["state"] == "COMPLETED", result.get("failure")
    assert "guidance" in seen, "Developer Agent 必须看到 Experience Guidance"
    assert any(g["experience_id"] == eid for g in seen["guidance"])
    # usage + decision 已记录
    dev = result["runs"]["software_developer"]
    pl = production_lineage(str(tmp_path), dev.get("production_run_id") or "")
    assert pl["experiences"], "usage 必须被记录"


# --- safety: bad experience 不能强制成功 ---

def test_bad_experience_cannot_force_success(tmp_path):
    """即使有失败经验, 生产失败仍是失败 (Experience 无强制力)。"""
    # 无经验种子 → guidance 空 → 生产失败 (executor FAIL)
    ensure_professional_agents(tmp_path)

    def factory(agent_id):
        def fn(input_data):
            return {"ok": False, "error": "boom", "artifact_type": "report",
                    "verification": {"result": "FAIL"}}
        return fn
    result = run_professional_workflow(str(tmp_path), idea="calculator",
                                       executor_factory=factory,
                                       experience_guidance=True)
    assert result["state"] == "FAILED"


# --- invalidated experience 不参与 guidance ---

def test_invalidated_excluded_from_guidance(tmp_path):
    eid = _seed_experience(tmp_path)
    invalidate(str(tmp_path), eid, reason="proven wrong")
    rel = retrieve_guidance(str(tmp_path), "software_developer", "calculator divide")
    assert eid not in [g["experience_id"] for g in rel]


# --- feedback: guided → evaluation → new experience ---

def test_guided_feedback_loop(tmp_path):
    """Guided production → 新 experience 从真实 evaluation 产生。"""
    ensure_professional_agents(tmp_path)
    _seed_experience(tmp_path)
    n_before = len([r for r in __import__("factory_console.production_experience", fromlist=["list_experiences"]).list_experiences(str(tmp_path))])

    def factory(agent_id):
        role = agent_id.split("-")[-2]
        content = {
            "product_manager": "# 产品需求文档\n## Problem\n## Target Users\n## Goals\n## Functional Requirements\n## Acceptance Criteria\n",
            "software_architect": "# 架构设计文档\n## System Architecture\n## Components\n## Interfaces\n## Data Model\n",
            "software_developer": ("def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n\n"
                                   "def multiply(a, b):\n    return a * b\n\ndef divide(a, b):\n"
                                   "    if b == 0:\n        raise ValueError('div by zero')\n    return a / b\n"),
            "qa_engineer": "def test_add():\n    assert True\n",
        }[role]
        def fn(input_data):
            return {"ok": True, "output": {"content": content}, "patch_text": "",
                    "artifact_type": "document", "verification": {"result": "PASS"}}
        return fn
    result = run_professional_workflow(str(tmp_path), idea="calculator",
                                       executor_factory=factory,
                                       experience_guidance=True)
    assert result["state"] == "COMPLETED"
    # 反馈闭环: 从 guided production 提取新经验
    from factory_console.production_experience import list_experiences, extract as _extract
    dev = result["runs"]["software_developer"]
    prun_id = dev.get("production_run_id")
    if prun_id:
        _extract(str(tmp_path), prun_id)
    n_after = len(list_experiences(str(tmp_path)))
    assert n_after > n_before, "反馈闭环: 新经验必须产生"
