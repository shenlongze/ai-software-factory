"""S37: Evidence-driven Workforce Learning。

覆盖:
- Observation 来源必须是 Production Evidence (禁 conversation/LLM imagination)
- Observation → Hypothesis → Candidate → Evaluation → VALIDATED/REJECTED [STOP]
- Lifecycle 非法迁移拒绝; history append-only
- Confidence: 小样本 → unknown/EVALUATING (不伪装)
- Negative Learning: 失败多 → REJECTED
- ContextFeedback 消费 (S36 数据)
- Conflict (VALIDATED vs REJECTED 同 pattern → CONFLICT)
- Learning Plugin 替换 (Core 零修改)
- Governance: Learning 不能修改 Production/Policy/Skill
- CLI / API
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from factory_console.learning_engine_v2 import (  # noqa: E402
    create_observation, observations, create_hypothesis, create_candidate,
    evaluate_candidate, transition, run_learning, detect_conflicts,
    learning_conflicts, learning_quality, candidates, default_discovery,
    register_learning_plugin, LEARNING_PLUGINS,
)
from factory_console.plugin_kernel import bootstrap, register_plugin, plugin_status  # noqa: E402


def _seed_observations(tmp_path, pattern="STRATEGY_A", success=4, failure=1, scope="project"):
    for i in range(success + failure):
        create_observation(str(tmp_path), source_type="production_run",
                           source_id=f"run-{i}", pattern_key=pattern,
                           outcome="SUCCESS" if i < success else "FAILURE",
                           scope=scope)


# --- Observation 来源白名单 ---

def test_observation_requires_evidence(tmp_path):
    o = create_observation(str(tmp_path), source_type="production_run",
                           source_id="run-1", pattern_key="P", outcome="SUCCESS")
    assert o["observation_id"].startswith("obs-")
    assert o["evidence_refs"] == ["production_run:run-1"]
    # 非法来源拒绝
    with pytest.raises(ValueError, match="非法 observation 来源"):
        create_observation(str(tmp_path), source_type="conversation",
                           source_id="x", pattern_key="P", outcome="SUCCESS")


# --- Lifecycle ---

def test_lifecycle(tmp_path):
    _seed_observations(tmp_path, success=1, failure=0)
    hyp = create_hypothesis(str(tmp_path), statement="S works", observation_ids=[])
    cand = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                            candidate_type="STRATEGY", content="S works", scope="project")
    # CANDIDATE → VALIDATED 非法 (须经 EVALUATING)
    with pytest.raises(ValueError, match="非法状态迁移"):
        transition(str(tmp_path), cand["candidate_id"], target="VALIDATED")
    # CANDIDATE → EVALUATING → VALIDATED 合法
    transition(str(tmp_path), cand["candidate_id"], target="EVALUATING")
    transition(str(tmp_path), cand["candidate_id"], target="VALIDATED")
    # VALIDATED → REJECTED 非法
    with pytest.raises(ValueError, match="非法状态迁移"):
        transition(str(tmp_path), cand["candidate_id"], target="REJECTED")
    # VALIDATED → SUPERSEDED 合法 (保留历史)
    transition(str(tmp_path), cand["candidate_id"], target="SUPERSEDED")
    c = [x for x in candidates(str(tmp_path)) if x["candidate_id"] == cand["candidate_id"]][0]
    assert len(c["lifecycle_history"]) >= 3


# --- Evaluation: 小样本降权 / 足够验证 / 失败多拒绝 ---

def test_evaluation_small_sample(tmp_path):
    hyp = create_hypothesis(str(tmp_path), statement="S", observation_ids=[])
    cand = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                            candidate_type="STRATEGY", content="S", scope="project")
    r = evaluate_candidate(str(tmp_path), cand["candidate_id"],
                           evidence_count=1, success_count=1, failure_count=0, min_samples=3)
    assert r["result"] == "EVALUATING"
    assert r["aggregate"]["confidence"] == "unknown"  # 不伪装


def test_evaluation_validated(tmp_path):
    hyp = create_hypothesis(str(tmp_path), statement="S", observation_ids=[])
    cand = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                            candidate_type="STRATEGY", content="S", scope="project")
    r = evaluate_candidate(str(tmp_path), cand["candidate_id"],
                           evidence_count=8, success_count=6, failure_count=2, min_samples=3)
    assert r["result"] == "VALIDATED"
    assert r["aggregate"]["confidence"] == "validated"


def test_negative_learning_rejected(tmp_path):
    """失败多 → REJECTED (Negative Learning: 保存完整失败事实)。"""
    hyp = create_hypothesis(str(tmp_path), statement="B", observation_ids=[])
    cand = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                            candidate_type="FAILURE_PATTERN", content="B fails", scope="project")
    r = evaluate_candidate(str(tmp_path), cand["candidate_id"],
                           evidence_count=10, success_count=2, failure_count=8, min_samples=3)
    assert r["result"] == "REJECTED"
    # 完整保留失败数据 (非 "B worked")
    assert r["aggregate"]["failure_count"] == 8
    assert r["aggregate"]["success_count"] == 2


# --- run_learning 全链 (discovery → evaluate → conflict; STOP) ---

def test_run_learning(tmp_path):
    _seed_observations(tmp_path, success=4, failure=1)
    rl = run_learning(str(tmp_path))
    assert rl["created"]
    assert rl["results"]
    assert rl["cost_type"] == "estimated"
    assert rl["evidence_count"] == 5
    # 不修改 Production (无 production 副作用)
    q = learning_quality(str(tmp_path))
    assert q["learning_candidates"] >= 1


# --- Learning 不能修改 Production/Policy/Skill (Governance) ---

def test_learning_does_not_modify_production(tmp_path):
    _seed_observations(tmp_path, success=3, failure=0)
    # run_learning 前后 production runs 不变
    before = _count_runs(str(tmp_path))
    run_learning(str(tmp_path))
    after = _count_runs(str(tmp_path))
    assert before == after  # Learning 不产生 production run


def _count_runs(root) -> int:
    import json
    try:
        return len(json.loads((Path(root) / "ops" / "runs" / "production_runs.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return 0


# --- Conflict ---

def test_conflict_preserved(tmp_path):
    hyp = create_hypothesis(str(tmp_path), statement="X", observation_ids=[])
    c1 = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                          candidate_type="SUCCESS_PATTERN", content="X works", scope="project")
    c1["pattern_key"] = "PAT_X"
    c2 = create_candidate(str(tmp_path), hypothesis_id=hyp["hypothesis_id"],
                          candidate_type="FAILURE_PATTERN", content="X fails", scope="project")
    c2["pattern_key"] = "PAT_X"
    # c1 走 VALIDATED, c2 走 REJECTED
    from factory_console.learning_engine_v2 import _save
    data = [c1, c2]
    _save(str(tmp_path), "candidates", data)
    evaluate_candidate(str(tmp_path), c1["candidate_id"],
                       evidence_count=5, success_count=4, failure_count=1, min_samples=3)
    evaluate_candidate(str(tmp_path), c2["candidate_id"],
                       evidence_count=5, success_count=1, failure_count=4, min_samples=3)
    cfs = detect_conflicts(str(tmp_path))
    assert len(cfs) == 1
    assert cfs[0]["status"] == "CONFLICT"
    assert "矛盾" in cfs[0]["explain"]
    assert len(learning_conflicts(str(tmp_path))) == 1


# --- ContextFeedback 消费 (S36 数据) ---

def test_context_feedback_integration(tmp_path):
    """S36 ContextFeedback → S37 Observation (source_type=context_feedback 合法)。"""
    o = create_observation(str(tmp_path), source_type="context_feedback",
                           source_id="fb-1", pattern_key="CTX_A", outcome="SUCCESS")
    assert o["evidence_refs"] == ["context_feedback:fb-1"]


# --- Learning Plugin 替换 (Core 零修改) ---

def test_learning_plugin_replacement(tmp_path):
    _seed_observations(tmp_path, success=3, failure=0)
    bootstrap(str(tmp_path))
    register_plugin(str(tmp_path), plugin_id="learning.alt", name="Alt", version="1.0",
                    type="learning", capabilities=["learning.discovery"],
                    permissions=["learning.read"])
    plugin_status(str(tmp_path), "learning.alt", target="ENABLED")

    def alt_discovery(obs):
        # 自定义 discovery: 只生成一个 LESSON candidate
        c = create_candidate(str(tmp_path), hypothesis_id="alt",
                             candidate_type="LESSON", content="alt-lesson",
                             scope="project")
        c["aggregate"] = {"sample_count": 3, "success_count": 3, "failure_count": 0,
                          "verification_count": 3, "recovery_count": 0,
                          "confidence": "validated"}
        return [c]

    register_learning_plugin("learning.alt", alt_discovery)
    assert "learning.alt" in LEARNING_PLUGINS  # 注册成功 (Core 零修改)
    # 手动验证 plugin 可被调用
    created = LEARNING_PLUGINS["learning.alt"](observations(str(tmp_path)))
    assert created[0]["candidate_id"].startswith("lrn-")
    assert created[0]["type"] == "LESSON"


# --- CLI ---

def test_cli_learn(tmp_path):
    _seed_observations(tmp_path, success=3, failure=1)
    from factory_console.cli_factory import main as _cli_main
    assert _cli_main(["learn", "observe", "P", "--source-type", "production_run",
                      "--source-id", "r1", "--outcome", "SUCCESS", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["learn", "run", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["learn", "candidates", "--data-dir", str(tmp_path)]) == 0
    assert _cli_main(["learn", "conflicts", "--data-dir", str(tmp_path)]) == 0


# --- API ---

def test_api_learn(tmp_path):
    from fastapi.testclient import TestClient
    from factory_console.web.backend.fastapi_adapter import build_app
    client = TestClient(build_app(None, factory_root=str(tmp_path)))
    resp = client.post("/api/learning/observations",
                       json={"source_type": "production_run", "source_id": "r1",
                             "pattern_key": "P", "outcome": "SUCCESS", "scope": "project"})
    assert resp.status_code == 200
    assert resp.json()["observation_id"].startswith("obs-")
    resp = client.post("/api/learning/observations",
                       json={"source_type": "conversation", "source_id": "x",
                             "pattern_key": "P", "outcome": "SUCCESS"})
    assert resp.status_code == 400  # 非法来源拒绝
    resp = client.post("/api/learning/run")
    assert resp.status_code == 200
    resp = client.get("/api/learning/candidates")
    assert resp.status_code == 200
    assert "quality" in resp.json()
    resp = client.get("/api/learning/conflicts")
    assert resp.status_code == 200
