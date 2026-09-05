"""P1 — Product Truth 测试。

契约 (D1-D20): 5 domain (Idea/Discovery/Requirement/PRD/Plan) + FK + traceability
+ PRD projection 边界 + Plan immutable + legacy 隔离 + idempotency。
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
def workroot(tmp_path: Path) -> Path:
    return tmp_path / "factory"


def _pt(workroot: Path):
    from factory_console import product_truth as pt

    return pt


def _full_chain(workroot: Path):
    """建完整链 idea→disc→req→prd→plan, 返回各级 id。"""
    pt = _pt(workroot)
    idea = pt.create_idea(workroot, project_id="P-1", title="记账App",
                          description="简化记账", actor="test")
    disc = pt.create_discovery(workroot, idea_id=idea["id"], title="调研", actor="test")
    pt.complete_discovery(workroot, disc["id"], findings=[{"f": "x"}], decision="做")
    req = pt.create_requirement(workroot, discovery_id=disc["id"], title="需求1")
    pt.transition_requirement(workroot, req["id"], "validated")
    pt.transition_requirement(workroot, req["id"], "approved")
    prd = pt.create_prd(workroot, project_id="P-1", title="记账PRD",
                        requirement_ids=[req["id"]])
    pt.approve_prd(workroot, prd["id"], content={"spec": "v2"})
    plan = pt.create_plan(workroot, project_id="P-1", prd_id=prd["id"],
                          prd_version=2, goal="做记账", tasks=[{"title": "t1"}])
    pt.approve_plan(workroot, plan["id"])
    return {"idea": idea, "disc": disc, "req": req, "prd": prd, "plan": plan}


# ---------------------------------------------------------------- Identity


class TestIdentity:
    def test_ids_unique_prefix(self, workroot: Path) -> None:
        pt = _pt(workroot)
        c = _full_chain(workroot)
        assert c["idea"]["id"].startswith("IDEA-")
        assert c["disc"]["id"].startswith("DISC-")
        assert c["req"]["id"].startswith("REQ-")
        assert c["prd"]["id"].startswith("PRD-")
        assert c["plan"]["id"].startswith("PLAN-")
        ids = [c[k]["id"] for k in c]
        assert len(ids) == len(set(ids))

    def test_store_isolation_from_legacy(self, workroot: Path) -> None:
        """P1 store 在 product_truth/ 下; 不写 legacy (product/ideas.json 等)。"""
        pt = _pt(workroot)
        _full_chain(workroot)
        pt_dir = workroot / "product_truth"
        assert (pt_dir / "ideas.json").is_file()
        assert (pt_dir / "discoveries.json").is_file()
        assert (pt_dir / "requirements.json").is_file()
        assert (pt_dir / "prds.json").is_file()
        assert (pt_dir / "plans.json").is_file()
        # legacy 目录不产生 (product/ideas.json 未写)
        assert not (workroot / "product").exists()


# ---------------------------------------------------------------- Lifecycle


class TestLifecycle:
    def test_idea_lifecycle(self, workroot: Path) -> None:
        pt = _pt(workroot)
        idea = pt.create_idea(workroot, title="i")
        assert idea["status"] == "created"
        pt.transition_idea(workroot, idea["id"], "refined")
        pt.transition_idea(workroot, idea["id"], "validated")
        pt.transition_idea(workroot, idea["id"], "approved")
        assert pt.get_idea(workroot, idea["id"])["status"] == "approved"
        with pytest.raises(ValueError):
            pt.transition_idea(workroot, idea["id"], "created")  # 非法回退

    def test_requirement_lifecycle(self, workroot: Path) -> None:
        pt = _pt(workroot)
        req = pt.create_requirement(workroot, title="r")
        pt.transition_requirement(workroot, req["id"], "validated")
        pt.transition_requirement(workroot, req["id"], "approved")
        assert pt.get_requirement(workroot, req["id"])["status"] == "approved"

    def test_prd_versioning(self, workroot: Path) -> None:
        pt = _pt(workroot)
        prd = pt.create_prd(workroot, title="p")
        assert prd["current_version"] == 1
        prd = pt.approve_prd(workroot, prd["id"], content={"spec": "v2"})
        assert prd["current_version"] == 2 and prd["status"] == "approved"
        assert len(prd["versions"]) == 2

    def test_plan_lifecycle_and_immutable(self, workroot: Path) -> None:
        pt = _pt(workroot)
        plan = pt.create_plan(workroot, goal="g")
        assert plan["status"] == "pending"
        pt.approve_plan(workroot, plan["id"])
        assert pt.get_plan(workroot, plan["id"])["status"] == "approved"
        # 无原地语义 update API (immutable snapshot) — 模块无 update_plan 函数
        assert not hasattr(pt, "update_plan_semantics")
        # approve 后想改 → 新 plan
        plan2 = pt.create_plan(workroot, goal="g2")
        assert plan2["id"] != plan["id"]


# ---------------------------------------------------------------- FK / Trace


class TestFKTrace:
    def test_forward_trace(self, workroot: Path) -> None:
        pt = _pt(workroot)
        c = _full_chain(workroot)
        ft = pt.forward_trace(workroot, c["idea"]["id"])
        assert [d["id"] for d in ft["discoveries"]] == [c["disc"]["id"]]
        assert [r["id"] for r in ft["requirements"]] == [c["req"]["id"]]
        assert [p["id"] for p in ft["prds"]] == [c["prd"]["id"]]
        assert [p["id"] for p in ft["plans"]] == [c["plan"]["id"]]

    def test_reverse_trace_from_task(self, workroot: Path, monkeypatch) -> None:
        """TASK → PLAN → PRD → REQ → DISC → IDEA (mock task 指向真实 plan)。"""
        import factory_console.product_truth as ptmod
        from factory_console import product_truth as pt

        c = _full_chain(workroot)
        fake_task = {"id": "TASK-abc", "plan_id": c["plan"]["id"]}

        def fake_find_task(root, task_id):
            return fake_task

        monkeypatch.setattr(ptmod, "_find_task", fake_find_task)
        tr = pt.reverse_trace(workroot, "TASK-abc")
        assert tr["task"]["plan_id"] == c["plan"]["id"]
        assert tr["plan"]["id"] == c["plan"]["id"]
        assert tr["prd"]["id"] == c["prd"]["id"]
        assert tr["prd_version"] == 2
        assert tr["requirement"]["id"] == c["req"]["id"]
        assert tr["discovery"]["id"] == c["disc"]["id"]
        assert tr["idea"]["id"] == c["idea"]["id"]
        assert [s[0] for s in tr["chain"]] == \
            ["task", "plan", "prd", "requirement", "discovery", "idea"]

    def test_reverse_no_plan_legacy_task(self, workroot: Path, monkeypatch) -> None:
        """无 plan_id 的 LEGACY 任务 → 不伪造上游 (仅 task)。"""
        import factory_console.product_truth as ptmod
        from factory_console import product_truth as pt

        def fake_find_task(root, task_id):
            return {"id": "TASK-legacy"}

        monkeypatch.setattr(ptmod, "_find_task", fake_find_task)
        tr = pt.reverse_trace(workroot, "TASK-legacy")
        assert tr["task"] is not None and tr["plan"] is None and tr["idea"] is None
        assert tr["chain"] == [("task", "TASK-legacy")]


# ---------------------------------------------------------------- Idempotency


class TestIdempotency:
    def test_idea_idempotency_key(self, workroot: Path) -> None:
        pt = _pt(workroot)
        a = pt.create_idea(workroot, title="x", idempotency_key="k1")
        b = pt.create_idea(workroot, title="x", idempotency_key="k1")
        assert a["id"] == b["id"]
        assert len(pt.list_ideas(workroot)) == 1

    def test_discovery_idempotent_per_idea(self, workroot: Path) -> None:
        pt = _pt(workroot)
        idea = pt.create_idea(workroot, title="i")
        a = pt.create_discovery(workroot, idea_id=idea["id"], title="调研")
        b = pt.create_discovery(workroot, idea_id=idea["id"], title="调研")
        assert a["id"] == b["id"]

    def test_transition_idempotent(self, workroot: Path) -> None:
        pt = _pt(workroot)
        idea = pt.create_idea(workroot, title="i")
        pt.transition_idea(workroot, idea["id"], "validated")
        # 同态转换幂等
        assert pt.transition_idea(workroot, idea["id"], "validated")["status"] == "validated"

    def test_no_duplicate_chain_on_repeat(self, workroot: Path) -> None:
        """E2E-3 语义: 重复 create_plan (同 idempotency) → 单 plan。"""
        pt = _pt(workroot)
        c = _full_chain(workroot)
        p2 = pt.create_plan(workroot, project_id="P-1", prd_id=c["prd"]["id"],
                            prd_version=2, goal="做记账", idempotency_key="plan-1")
        p3 = pt.create_plan(workroot, project_id="P-1", prd_id=c["prd"]["id"],
                            prd_version=2, goal="做记账", idempotency_key="plan-1")
        assert p2["id"] == p3["id"]
        assert len(pt.list_plans(workroot)) == 2  # _full_chain 1 + 幂等 1


# ---------------------------------------------------------------- PRD boundary


class TestPRDBoundary:
    def test_prd_truth_not_document(self, workroot: Path) -> None:
        """PRD-* store 是 truth; 本域不写 PRD.md (projection 由 generator 负责)。"""
        pt = _pt(workroot)
        _full_chain(workroot)
        prds = pt.list_prds(workroot)
        assert len(prds) == 1 and prds[0]["id"].startswith("PRD-")
        # 本域不产生 PRD.md (document projection 是独立 renderer 职责)
        assert not (workroot / "PRD.md").exists()


# ---------------------------------------------------------------- Legacy


class TestLegacy:
    def test_legacy_stores_untouched(self, workroot: Path) -> None:
        """P1 操作不触碰 legacy: session_plans.json / requirements.json /
        product/ideas.json 保持原样 (不存在时不创建)。"""
        pt = _pt(workroot)
        _full_chain(workroot)
        assert not (workroot / "session_plans.json").exists()
        assert not (workroot / "requirements").exists()
        assert not (workroot / "product").exists()
