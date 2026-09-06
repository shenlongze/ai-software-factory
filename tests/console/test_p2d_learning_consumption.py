"""P2-D — Learning Consumption 测试 (OBS/CAND/PROM/PROFILE/RD)。

契约 (docs/audits/2026-09-06-learning-consumption-p2-contract/):
- 链: exp(anchored) → OBS → CAND → PROM(governed) → PROFILE-vN → Router → RD
- 唯一 writer; 幂等每层; Profile versioned; rollback; human-in-loop
- legacy 隔离 (intelligence 零读); router 零算法改 (只消费 profile 数据)
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path / "factory"


def _anchored_exp(r: Path, i: int, *, agent: str = "agent-1",
                  success: bool = True, task: str = "") -> str:
    """真实 canonical anchored exp (经 bridge — 非 fixture)。"""
    from factory_console.experience_bridge import record

    return record(r, source="execution", source_id=f"r{i}:e{i}",
                  type_="SUCCESS_PATTERN" if success else "FAILURE_PATTERN",
                  success=success, task_run_id=f"run-{i}", exs_id=f"EXS-{i}",
                  agent=agent, task=task)["id"]


def _chain(r: Path, n_obs: int = 3, *, agent: str = "agent-1",
           cap: str = "java", success: bool = True):
    """exp ×n → obs ×n → cand → prom(approve) → profile(apply)。返回各级 id。"""
    from factory_console import learning_truth as lt

    eids = []
    for i in range(n_obs):
        eid = _anchored_exp(r, i, agent=agent, success=success)
        lt.derive_observation(r, eid, capability=cap, agent=agent)
        eids.append(eid)
    cand = lt.propose_candidate(r, agent_id=agent, capability=cap,
                                proposed_delta=0.1)
    prom = lt.propose_promotion(r, cand["candidate_id"])
    lt.approve_promotion(r, prom["promotion_id"], decided_by="admin")
    prom = lt.get_promotion(r, prom["promotion_id"])  # 重新读 (approved)
    prof = lt.apply_promotion(r, prom["promotion_id"])
    return eids, cand, prom, prof


class TestObservation:
    def test_derive_from_anchored_exp(self, root) -> None:
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0)
        obs = lt.derive_observation(root, eid, capability="java")
        assert obs["observation_id"].startswith("OBS-")
        assert obs["source_experience_id"] == eid
        assert obs["signal"] == "SUCCESS" and obs["status"] == "CREATED"

    def test_failure_signal(self, root) -> None:
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0, success=False)
        obs = lt.derive_observation(root, eid, capability="java")
        assert obs["signal"] == "FAILURE"

    def test_idempotent_1exp_1obs(self, root) -> None:
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0)
        a = lt.derive_observation(root, eid, capability="java")
        b = lt.derive_observation(root, eid, capability="java")
        assert a["observation_id"] == b["observation_id"]
        assert len(lt.list_observations(root)) == 1

    def test_reject_legacy_exp(self, root) -> None:
        """无 canonical anchor 的 legacy exp → 拒绝 (禁无 provenance 学习)。"""
        from factory_console import learning_truth as lt
        from factory_console.memory.experience_store import ExperienceStore
        from factory_console.memory.experience import ExperienceRecord

        store = ExperienceStore.from_workspace(root)
        store.add(ExperienceRecord.from_dict(
            {"id": "exp-legacy", "type": "SUCCESS_PATTERN", "success": True,
             "source": "execution_records"}))  # 无 task_run_id/exs_id
        with pytest.raises(ValueError):
            lt.derive_observation(root, "exp-legacy", capability="java")

    def test_missing_exp(self, root) -> None:
        from factory_console import learning_truth as lt

        with pytest.raises(ValueError):
            lt.derive_observation(root, "exp-nope", capability="java")


class TestCandidate:
    def test_propose_from_obs(self, root) -> None:
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0)
        lt.derive_observation(root, eid, capability="java")
        cand = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                    proposed_delta=0.1)
        assert cand["candidate_id"].startswith("CAND-")
        assert cand["status"] == "PROPOSED"
        assert cand["evidence_count"] == 1
        assert cand["observation_ids"]

    def test_idempotent(self, root) -> None:
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0)
        lt.derive_observation(root, eid, capability="java")
        a = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                 proposed_delta=0.1)
        b = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                 proposed_delta=0.1)
        assert a["candidate_id"] == b["candidate_id"]

    def test_requires_obs(self, root) -> None:
        from factory_console import learning_truth as lt

        with pytest.raises(ValueError):
            lt.propose_candidate(root, agent_id="agent-1", capability="none",
                                 proposed_delta=0.1)


class TestPromotion:
    def test_gate_blocks_low_evidence(self, root) -> None:
        """<min_obs_gate obs → approve REJECT (治理拦低证据)。"""
        from factory_console import learning_truth as lt

        eid = _anchored_exp(root, 0)
        lt.derive_observation(root, eid, capability="java")
        cand = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                    proposed_delta=0.1)
        prom = lt.propose_promotion(root, cand["candidate_id"])  # gate=3
        with pytest.raises(ValueError):
            lt.approve_promotion(root, prom["promotion_id"], decided_by="admin")

    def test_approve_apply(self, root) -> None:
        from factory_console import learning_truth as lt

        _, cand, prom, prof = _chain(root, n_obs=3)
        assert prom["status"] == "APPROVED"
        assert prof["profile_id"].startswith("PROFILE-agent-1-v")
        assert prof["success_rate"] == 1.0

    def test_reject(self, root) -> None:
        from factory_console import learning_truth as lt

        eids = [_anchored_exp(root, i) for i in range(3)]
        for e in eids:
            lt.derive_observation(root, e, capability="java")
        cand = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                    proposed_delta=0.1)
        prom = lt.propose_promotion(root, cand["candidate_id"])
        lt.reject_promotion(root, prom["promotion_id"], decided_by="admin")
        assert lt.get_promotion(root, prom["promotion_id"])["status"] == "REJECTED"
        # rejected 不能 apply
        with pytest.raises(ValueError):
            lt.apply_promotion(root, prom["promotion_id"])

    def test_idempotent_1cand_1prom(self, root) -> None:
        from factory_console import learning_truth as lt

        eids = [_anchored_exp(root, i) for i in range(3)]
        for e in eids:
            lt.derive_observation(root, e, capability="java")
        cand = lt.propose_candidate(root, agent_id="agent-1", capability="java",
                                    proposed_delta=0.1)
        a = lt.propose_promotion(root, cand["candidate_id"])
        b = lt.propose_promotion(root, cand["candidate_id"])
        assert a["promotion_id"] == b["promotion_id"]


class TestProfile:
    def test_versioning_and_provenance(self, root) -> None:
        from factory_console import learning_truth as lt

        _, cand, prom, prof = _chain(root, n_obs=3)
        assert prof["version"] == 1
        assert prof["promotion_id"] == prom["promotion_id"]
        assert prof["candidate_id"] == cand["candidate_id"]
        # v2 from second capability
        for i in range(3, 6):
            eid = _anchored_exp(root, i, agent="agent-1")
            lt.derive_observation(root, eid, capability="go", agent="agent-1")
        cand2 = lt.propose_candidate(root, agent_id="agent-1", capability="go",
                                     proposed_delta=0.1)
        prom2 = lt.propose_promotion(root, cand2["candidate_id"])
        lt.approve_promotion(root, prom2["promotion_id"], decided_by="admin")
        prof2 = lt.apply_promotion(root, prom2["promotion_id"])
        assert prof2["version"] == 2
        assert prof2["profile_id"] == "PROFILE-agent-1-v2"
        # v1 保留可查
        v1 = lt.get_profile(root, "agent-1", version=1)
        assert v1 is not None and v1["profile_id"] == "PROFILE-agent-1-v1"

    def test_apply_idempotent(self, root) -> None:
        from factory_console import learning_truth as lt

        _, _, prom, prof = _chain(root, n_obs=3)
        again = lt.apply_promotion(root, prom["promotion_id"])
        assert again["profile_id"] == prof["profile_id"]
        assert lt.get_profile(root, "agent-1")["version"] == 1

    def test_rollback(self, root) -> None:
        from factory_console import learning_truth as lt

        _, _, prom, prof = _chain(root, n_obs=3)  # v1
        for i in range(3, 6):
            lt.derive_observation(root, _anchored_exp(root, i), capability="go")
        cand2 = lt.propose_candidate(root, agent_id="agent-1", capability="go",
                                     proposed_delta=0.1)
        prom2 = lt.propose_promotion(root, cand2["candidate_id"])
        lt.approve_promotion(root, prom2["promotion_id"], decided_by="admin")
        lt.apply_promotion(root, prom2["promotion_id"])  # v2
        assert lt.get_profile(root, "agent-1")["version"] == 2
        lt.rollback_profile(root, "agent-1", to_version=1, actor="admin")
        assert lt.get_profile(root, "agent-1")["version"] == 1
        # v2 历史保留
        assert lt.get_profile(root, "agent-1", version=2) is not None

    def test_router_profiles_shape(self, root) -> None:
        """Router 消费 shape: {agent_id: {success_rate}} (persona 映射)。"""
        from factory_console import learning_truth as lt

        _, _, _, prof = _chain(root, n_obs=3)
        rp = lt.router_profiles(root)
        assert rp["agent-1"]["success_rate"] == 1.0
        assert rp["agent-1"]["profile_id"] == prof["profile_id"]


class TestRoutingDecision:
    def test_record_and_idempotent(self, root) -> None:
        from factory_console import learning_truth as lt

        a = lt.record_routing_decision(root, task_run_id="run-1",
                                       selected_resource="agent-1")
        b = lt.record_routing_decision(root, task_run_id="run-1")
        assert a["decision_id"] == b["decision_id"]
        assert a["decision_id"].startswith("RD-")

    def test_requires_run(self, root) -> None:
        from factory_console import learning_truth as lt

        with pytest.raises(ValueError):
            lt.record_routing_decision(root, task_run_id="")

    def test_trace_full_chain(self, root) -> None:
        from factory_console import learning_truth as lt

        eids, cand, prom, prof = _chain(root, n_obs=3)
        rd = lt.record_routing_decision(root, task_run_id="run-next",
                                        selected_resource="agent-1",
                                        profile_id=prof["profile_id"],
                                        profile_version=prof["version"])
        tr = lt.trace_decision(root, rd["decision_id"])
        assert tr["decision"]["decision_id"] == rd["decision_id"]
        assert tr["profile"]["profile_id"] == prof["profile_id"]
        assert tr["promotion"]["promotion_id"] == prom["promotion_id"]
        assert tr["candidate"]["candidate_id"] == cand["candidate_id"]
        assert len(tr["observations"]) == 3
        assert set(tr["experience_ids"]) == set(eids)
        kinds = [c[0] for c in tr["chain"]]
        assert kinds == ["routing_decision", "profile", "promotion", "candidate"]


class TestRouterConsumption:
    def test_profile_changes_routing(self, root) -> None:
        """真实: governed profile → 路由决策变化 (before/after 同任务上下文)。"""
        from factory_console import learning_truth as lt
        from factory_console.session.action import ExecutionContext
        from factory_console.session.actions import select_agent

        # workspace agents.json: agent-1/agent-2 同 java 能力同 priority (中性基线)
        agents_dir = root / "agents"
        agents_dir.mkdir(parents=True)
        import json

        (agents_dir / "agents.json").write_text(json.dumps({
            "agent-1": {"capabilities": ["code_generation"], "priority": 0},
            "agent-2": {"capabilities": ["code_generation"], "priority": 0},
        }))
        # baseline: 无 profile → 路由确定性 (同键 → id asc → agent-1)
        class _I:
            parameters = {"objective": "实现 java 调试功能", "agent_id": None}

        class _S:  # SessionContext stub (select_agent 只用 workspace)
            session_id = "p2d-test"

        ctx = ExecutionContext(workspace=root, session=_S())
        before = select_agent(_I(), ctx)
        # 学习: agent-2 java ×3 成功 → governed profile (agent-2 高画像)
        for i in range(3):
            eid = _anchored_exp(root, i, agent="agent-2")
            lt.derive_observation(root, eid, capability="java", agent="agent-2")
        cand = lt.propose_candidate(root, agent_id="agent-2", capability="java",
                                    proposed_delta=0.2)
        prom = lt.propose_promotion(root, cand["candidate_id"])
        lt.approve_promotion(root, prom["promotion_id"], decided_by="admin")
        lt.apply_promotion(root, prom["promotion_id"])
        after = select_agent(_I(), ctx)
        # 决策变化必须来自 learning (agent-2 画像) 而非 random/hardcode
        assert before != after, "learning 未产生决策变化 (before==after)"
        assert after == "agent-2", \
            f"learning 未改变路由: before={before} after={after}"
