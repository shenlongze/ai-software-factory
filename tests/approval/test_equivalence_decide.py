"""S1.5 等价性验证：decide（新 ai_factory_os.services.governance vs 旧 exec.ApprovalGate）。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from exec.approval import ApprovalError, ApprovalGate as OldGate  # noqa: E402
from exec.models import ApprovalDecision, ApprovalRecord as OldRecord  # noqa: E402
from exec.store import ExecStore  # noqa: E402
from ai_factory_os.services.governance import ApprovalDecideError  # noqa: E402
from ai_factory_os.services.governance import decide as new_decide  # noqa: E402
from ai_factory_os.services.governance.store import ApprovalStore  # noqa: E402


def _seed_old(tmp: Path) -> tuple[OldGate, str]:
    store = ExecStore(tmp / "exec")
    rec = OldRecord(id="APR-1", request_id="REQ-1", risk_level="low", required_roles=["developer"])
    store.save_approval(rec)
    return OldGate(store), "APR-1"


def _seed_new(tmp: Path) -> tuple[ApprovalStore, str]:
    store = ApprovalStore(tmp / "exec")
    from ai_factory_os.services.governance.store import ApprovalRecord as NewRecord
    store.save(NewRecord(id="APR-1", request_id="REQ-1", risk_level="low", required_roles=["developer"]))
    return store, "APR-1"


# 3 组输入：approve / reject / 二次决定（幂等保护）

def test_decide_approve_equivalence(tmp_path: Path) -> None:
    """approve：新旧最终状态一致。"""
    og, oid = _seed_old(tmp_path / "old")
    o = og.decide(oid, ApprovalDecision.APPROVED, decided_by="ceo", comment="ok")
    ns, nid = _seed_new(tmp_path / "new")
    n = new_decide(ns, nid, "approve", decided_by="ceo", comment="ok")
    assert n.decision == o.decision.value == "approved"
    assert n.decided_by == o.decided_by == "ceo"
    assert n.comment == o.comment == "ok"
    assert bool(n.decided_at) and bool(o.decided_at)


def test_decide_reject_equivalence(tmp_path: Path) -> None:
    """reject：新旧最终状态一致。"""
    og, oid = _seed_old(tmp_path / "old")
    o = og.decide(oid, ApprovalDecision.REJECTED, decided_by="cto", comment="no")
    ns, nid = _seed_new(tmp_path / "new")
    n = new_decide(ns, nid, "reject", decided_by="cto", comment="no")
    assert n.decision == o.decision.value == "rejected"


def test_decide_second_time_raises_both(tmp_path: Path) -> None:
    """二次决定：新旧都响亮报错（幂等保护）。"""
    og, oid = _seed_old(tmp_path / "old")
    og.decide(oid, ApprovalDecision.APPROVED, decided_by="ceo")
    with pytest.raises(ApprovalError):
        og.decide(oid, ApprovalDecision.REJECTED, decided_by="cto")

    ns, nid = _seed_new(tmp_path / "new")
    new_decide(ns, nid, "approve", decided_by="ceo")
    with pytest.raises(ApprovalDecideError):
        new_decide(ns, nid, "reject", decided_by="cto")


def test_decide_store_format_cross_readable(tmp_path: Path) -> None:
    """存储格式一致：新 decide 写的文件 → 旧 ExecStore 能读。"""
    ns, nid = _seed_new(tmp_path)
    new_decide(ns, nid, "approve", decided_by="ceo", comment="x")
    old_rec = ExecStore(tmp_path / "exec").get_approval("APR-1")
    assert old_rec is not None
    assert old_rec.decision.value == "approved"
    assert old_rec.decided_by == "ceo"


def test_on_approved_callback_fired(tmp_path: Path) -> None:
    """审计挂点：approve 时 on_approved 被调用（reject 不调用）。"""
    ns, nid = _seed_new(tmp_path / "a")
    calls = []
    new_decide(ns, nid, "approve", decided_by="ceo", on_approved=lambda r: calls.append(r.id))
    assert calls == ["APR-1"]

    ns2, nid2 = _seed_new(tmp_path / "b")
    calls2 = []
    new_decide(ns2, nid2, "reject", decided_by="ceo", on_approved=lambda r: calls2.append(r.id))
    assert calls2 == []
