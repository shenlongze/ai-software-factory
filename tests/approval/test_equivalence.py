"""S1.4 等价性验证：ai_factory_os.services.governance（新） vs factory-exec（旧）。

断言：规则一致 / 存储格式一致 / 决策状态机一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core"), str(_ROOT / "factory-exec")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from ai_factory_os.services.governance import ApprovalGate, ApprovalStore  # noqa: E402
from ai_factory_os.services.governance import classify_risk as new_risk  # noqa: E402
from exec.approval import classify_risk as old_risk  # noqa: E402

# 3 组输入：低 / 中 / 高风险
CASES = [
    ("low", "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1 @@\n-a\n+b\n", 1),
    ("medium", "diff --git a/src/x.py b/src/x.py\n+config = 1\n", 2),
    ("high", "diff --git a/requirements.txt b/requirements.txt\n+++ /dev/null\n", 1),
]


@pytest.mark.parametrize("name,patch,changed", CASES)
def test_classify_risk_equivalence(name: str, patch: str, changed: int) -> None:
    """规则一致：新旧 classify_risk 同输入 → 同 (risk_level, roles)。"""
    assert new_risk(patch, changed_files=changed) == old_risk(patch, changed_files=changed)


def test_store_format_readable_by_old(tmp_path: Path) -> None:
    """存储格式一致：新 store 写的文件 → 旧 ExecStore 能读。"""
    from exec.store import ExecStore

    new_store = ApprovalStore(tmp_path / "exec")
    rec = ApprovalGate(new_store).request("REQ-1", patch_text=CASES[0][1])
    assert (tmp_path / "exec" / "approvals.json").is_file()

    old_store = ExecStore(tmp_path / "exec")
    old_rec = old_store.get_approval(rec.id)
    assert old_rec is not None, "旧实现必须能读新实现写入的记录"
    assert old_rec.request_id == "REQ-1"
    assert old_rec.risk_level == "low"


def test_decide_state_machine_equivalence(tmp_path: Path) -> None:
    """决策状态机一致：pending → approved；二次决定 → 报错。"""
    store = ApprovalStore(tmp_path / "exec")
    gate = ApprovalGate(store)
    rec = gate.request("REQ-2", patch_text=CASES[1][1], risk_level="low", required_roles=["developer"])
    assert rec.decision == "pending"
    rec2 = gate.decide(rec.id, "approve", decided_by="ceo", comment="ok")
    assert rec2.decision == "approved"
    with pytest.raises(Exception):  # 二次决定 → 报错（原 ApprovalError 语义）
        gate.decide(rec.id, "reject")


def test_governance_gate_contract(tmp_path: Path) -> None:
    """契约：ApprovalGate 实现 ai_factory_os GovernanceGate.check(action)。

    绞杀刀13：契约由 kernel.governance.contracts.Decision 改为
    ai_factory_os.contracts.governance.Verdict；字段 verdict → kind，
    取值不变（仍为 "approval"/"allow"/"deny"），故断言逐字等价。
    """
    gate = ApprovalGate(ApprovalStore(tmp_path / "exec"))
    rec = gate.request("REQ-3", patch_text=CASES[0][1], risk_level="low", required_roles=["developer"])
    d = gate.check({"approval_id": rec.id})
    assert d.kind.value == "approval" and not d.allowed  # pending → approval
    gate.decide(rec.id, "approve", decided_by="ceo")
    assert gate.check({"approval_id": rec.id}).allowed  # approved → allow
