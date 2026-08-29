"""S1: Artifact Lifecycle — 8 态状态机测试 (转换矩阵 + 非法拒绝 + 终态保护)。

覆盖: 合法转换矩阵 / 非法跳转拒绝 / 终态不可变 / 失败态 / 持久化 / 单一权威状态。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from factory_console.artifact_lifecycle import (  # noqa: E402
    LIFECYCLE_STATES,
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    create_artifact,
    get_artifact,
    transition_artifact,
    artifact_state,
    fail_artifact,
    ArtifactError,
    is_valid_transition,
)


def _art(tmp_path, **kw):
    return create_artifact(
        str(tmp_path), artifact_type=kw.get("type", "code_change"),
        patch_text=kw.get("patch_text"), project_id=kw.get("project", "P-test"),
        producer="test")


def test_allowed_transitions_matrix(tmp_path):
    """合法转换矩阵: 每步按表推进, 全部可达。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    chain = ["STAGED", "REVIEWED", "APPROVED", "APPLIED", "VALIDATED", "COMMITTED", "RELEASED"]
    for st in chain:
        art = transition_artifact(str(tmp_path), aid, st, actor="test",
                                  approval={"approval_id": "a1", "state": "APPROVED"})
        assert art["state"] == st
    # 终态
    assert artifact_state(str(tmp_path), aid) == "RELEASED"
    assert art["state"] in TERMINAL_STATES


def test_invalid_transitions_rejected(tmp_path):
    """非法跳转全部拒绝 (GENERATED→APPROVED 等)。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    bad = [
        ("GENERATED", "APPROVED"),
        ("GENERATED", "APPLIED"),
        ("GENERATED", "COMMITTED"),
        ("STAGED", "APPLIED"),
        ("REVIEWED", "APPLIED"),
        ("APPROVED", "COMMITTED"),
        ("APPLIED", "COMMITTED"),
        ("VALIDATED", "RELEASED"),
        ("GENERATED", "RELEASED"),
    ]
    for frm, to in bad:
        # 先把 art 推进到 frm (用合法链)
        cur = _art(tmp_path)
        cur_id = cur["artifact_id"]
        idx = LIFECYCLE_STATES.index(frm)
        for st in LIFECYCLE_STATES[1:idx + 1]:
            transition_artifact(str(tmp_path), cur_id, st, actor="test",
                                approval={"approval_id": "a1", "state": "APPROVED"})
        try:
            transition_artifact(str(tmp_path), cur_id, to, actor="test")
            assert False, f"非法转换未拒绝: {frm}→{to}"
        except ArtifactError:
            pass


def test_terminal_state_immutable(tmp_path):
    """终态 RELEASED 不可再转换 (I10)。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    for st in ["STAGED", "REVIEWED", "APPROVED", "APPLIED", "VALIDATED", "COMMITTED", "RELEASED"]:
        transition_artifact(str(tmp_path), aid, st, actor="test",
                            approval={"approval_id": "a1", "state": "APPROVED"})
    try:
        transition_artifact(str(tmp_path), aid, "STAGED", actor="test")
        assert False, "终态仍可转换"
    except ArtifactError:
        pass


def test_state_persisted_single_authority(tmp_path):
    """状态持久化: 重新读取 artifact, 单一权威 state, 无多 status 矛盾。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    transition_artifact(str(tmp_path), aid, "STAGED", actor="test")
    loaded = get_artifact(str(tmp_path), aid)
    assert loaded["state"] == "STAGED"
    # 只存在一个 state 字段 (无互相矛盾的 status)
    assert "state" in loaded
    assert loaded.get("status") is None
    assert loaded.get("lifecycle_status") is None


def test_fail_state_not_in_lifecycle(tmp_path):
    """FAILED 不在主链, 不可推进回生产主链。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    fail_artifact(str(tmp_path), aid, reason="test fail", actor="test")
    assert artifact_state(str(tmp_path), aid) == "FAILED"
    for st in ["STAGED", "REVIEWED", "APPROVED", "APPLIED"]:
        try:
            transition_artifact(str(tmp_path), aid, st, actor="test")
            assert False, f"FAILED 仍可回 {st}"
        except ArtifactError:
            pass


def test_history_records_all_transitions(tmp_path):
    """历史不可变记录: 每次转换 append, 带 actor/at/evidence。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    transition_artifact(str(tmp_path), aid, "STAGED", actor="alice")
    loaded = get_artifact(str(tmp_path), aid)
    history = loaded["history"]
    assert len(history) >= 2  # CREATED + STAGED
    assert history[-1]["to"] == "STAGED"
    assert history[-1]["actor"] == "alice"
    assert "at" in history[-1]


def test_identity_stable_across_transitions(tmp_path):
    """Identity 稳定: artifact_id 不随转换变化。"""
    art = _art(tmp_path)
    aid = art["artifact_id"]
    transition_artifact(str(tmp_path), aid, "STAGED", actor="test")
    loaded = get_artifact(str(tmp_path), aid)
    assert loaded["artifact_id"] == aid


def test_is_valid_transition_helper():
    assert is_valid_transition("GENERATED", "STAGED")
    assert not is_valid_transition("GENERATED", "APPROVED")
    assert is_valid_transition("APPROVED", "APPLIED")
