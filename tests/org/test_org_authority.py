"""tests/org/test_org_authority.py — Default Deny 权限模型 (Phase 16A, ADR-0036)。

覆盖 (任务清单: authority deny):
- Default Deny 铁律: 无权限记录即拒绝; 未声明 permission 一律 deny
- Developer 拒 release.approve (高危操作硬拒绝, 模板物化后校验)
- CEO 唯一 release.approve (Human 最终批准权)
- 显式 deny 优先于任何 allow (同 (role, permission) last-write-wins)
- 离职员工权限即刻失效 (含审计事件 allowed=False)
- authority.checked 审计 (越权尝试也审计; payload 契约)
- check_authority_for_roles 纯函数路径 (不发事件)
"""

from __future__ import annotations

import pytest

from org.lifecycle import CompanyMismatchError, NotFoundError, OrgLifecycle
from org.store import OrgStore

from org_helpers import event_sequence, last_event, payload_of


@pytest.fixture
def lifecycle(org_store: OrgStore, logger) -> OrgLifecycle:
    return OrgLifecycle(org_store, logger=logger)


def _seed_software_company(lifecycle: OrgLifecycle) -> dict[str, str]:
    """software_company 模板实例化, 返回 {角色名: 角色 id}。"""
    lifecycle.create_company("Acme", template="software_company", company_id="C-1")
    return {
        r.name: r.id
        for r in lifecycle.store.list_roles_by_company("C-1")
    }


class TestDefaultDeny:
    def test_no_record_is_denied(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        developer = roles["Developer"]
        # Default Deny: 未声明即拒绝 (即使无任何 Authority 记录)
        assert lifecycle.check_authority_for_roles([developer], "anything") is False

    def test_developer_denied_release_approve(self, lifecycle):
        """Developer 无 release.approve 记录 → 硬拒绝 (高危默认 deny)。"""
        roles = _seed_software_company(lifecycle)
        assert (
            lifecycle.check_authority_for_roles([roles["Developer"]], "release.approve")
            is False
        )

    def test_developer_allowed_code_modify(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        assert (
            lifecycle.check_authority_for_roles([roles["Developer"]], "code.modify")
            is True
        )

    def test_ceo_allowed_release_approve(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        assert (
            lifecycle.check_authority_for_roles([roles["CEO"]], "release.approve")
            is True
        )

    def test_pm_denied_code_modify(self, lifecycle):
        """未声明 permission 一律 deny (PM 无 code.modify 记录)。"""
        roles = _seed_software_company(lifecycle)
        assert (
            lifecycle.check_authority_for_roles([roles["Product Manager"]], "code.modify")
            is False
        )

    def test_qa_allowed_review_approve(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        assert (
            lifecycle.check_authority_for_roles([roles["QA"]], "review.approve")
            is True
        )

    def test_role_ids_denied_when_no_authorities(self, org_store, logger):
        """全新公司 (无权限记录) — 全部角色全部拒绝。"""
        lifecycle = OrgLifecycle(org_store, logger=logger)
        lifecycle.create_company("Solo", template="solo", company_id="C-1")
        role_id = lifecycle.store.list_roles_by_company("C-1")[0].id
        assert lifecycle.check_authority_for_roles([role_id], "anything") is False


class TestDenyPriority:
    def test_explicit_deny_overrides_allow(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        developer = roles["Developer"]
        assert lifecycle.check_authority_for_roles([developer], "code.modify") is True
        lifecycle.deny_authority(developer, "code.modify")
        # 显式 deny 优先于任何 allow (同 role, 同 permission)
        assert lifecycle.check_authority_for_roles([developer], "code.modify") is False

    def test_last_write_wins_regrant(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        developer = roles["Developer"]
        lifecycle.deny_authority(developer, "code.modify")
        assert lifecycle.check_authority_for_roles([developer], "code.modify") is False
        lifecycle.grant_authority(developer, "code.modify", effect="allow")
        assert lifecycle.check_authority_for_roles([developer], "code.modify") is True

    def test_deny_in_any_role_wins(self, lifecycle):
        """员工多角色: 任一角色显式 deny → 整体拒绝 (deny 优先)。"""
        roles = _seed_software_company(lifecycle)
        developer = roles["Developer"]
        pm = roles["Product Manager"]
        # 多角色集: PM allow task.schedule + Developer 对 task.schedule 无记录
        # → allow (无 deny); 再给 Developer 显式 deny → 整体拒绝
        assert lifecycle.check_authority_for_roles([pm, developer], "task.schedule") is True
        lifecycle.deny_authority(developer, "task.schedule")
        assert lifecycle.check_authority_for_roles([pm, developer], "task.schedule") is False

    def test_deny_emits_denied_event(self, lifecycle, event_store):
        roles = _seed_software_company(lifecycle)
        lifecycle.deny_authority(roles["Developer"], "release.approve")
        ev = last_event(event_store)
        assert ev.type.value == "org.authority.denied"
        assert ev.payload["permission"] == "release.approve"
        assert ev.payload["effect"] == "deny"
        assert ev.payload["role_id"] == roles["Developer"]

    def test_grant_emits_granted_event(self, lifecycle, event_store):
        roles = _seed_software_company(lifecycle)
        lifecycle.grant_authority(roles["Developer"], "deploy.run")
        ev = last_event(event_store)
        assert ev.type.value == "org.authority.granted"
        assert ev.payload["permission"] == "deploy.run"
        assert ev.payload["effect"] == "allow"

    def test_regrant_keeps_full_audit_trail(self, lifecycle, event_store):
        """last-write-wins 先删后建: 事件日志保留完整变更序 (granted→denied→granted)。"""
        roles = _seed_software_company(lifecycle)
        developer = roles["Developer"]
        lifecycle.grant_authority(developer, "code.modify")
        lifecycle.deny_authority(developer, "code.modify")
        lifecycle.grant_authority(developer, "code.modify")
        seq = event_sequence(event_store)
        tail = [t for t in seq if t.startswith("org.authority.")][-3:]
        assert tail == [
            "org.authority.granted",
            "org.authority.denied",
            "org.authority.granted",
        ]

    def test_grant_unknown_role_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.grant_authority("R-999", "deploy.run")

    def test_grant_invalid_effect_raises(self, lifecycle):
        roles = _seed_software_company(lifecycle)
        with pytest.raises(ValueError):
            lifecycle.grant_authority(roles["Developer"], "deploy.run", effect="maybe")


class TestCheckAuthority:
    def test_employee_allowed_via_role(self, lifecycle, org_store):
        roles = _seed_software_company(lifecycle)
        lifecycle.hire_employee(
            "C-1", "Ada", roles["Developer"], employee_id="E-1",
        )
        assert lifecycle.check_authority("E-1", "code.modify") is True
        assert lifecycle.check_authority("E-1", "release.approve") is False

    def test_checked_event_emitted(self, lifecycle, event_store, org_store):
        roles = _seed_software_company(lifecycle)
        lifecycle.hire_employee(
            "C-1", "Ada", roles["Developer"], employee_id="E-1",
        )
        lifecycle.check_authority("E-1", "release.approve")
        ev = last_event(event_store)
        assert ev.type.value == "org.authority.checked"
        assert ev.payload["employee_id"] == "E-1"
        assert ev.payload["permission"] == "release.approve"
        assert ev.payload["allowed"] is False
        assert ev.payload["role_ids"] == [roles["Developer"]]
        assert ev.result == "DENY"

    def test_denied_attempt_still_audited(self, lifecycle, event_store, org_store):
        """越权尝试也审计 (allowed=False 落库) — 权限模型可追溯。"""
        roles = _seed_software_company(lifecycle)
        lifecycle.hire_employee(
            "C-1", "Ada", roles["Developer"], employee_id="E-1",
        )
        assert lifecycle.check_authority("E-1", "release.approve") is False
        assert payload_of(event_store, "org.authority.checked")["allowed"] is False

    def test_left_employee_checked_denied_and_audited(
        self, lifecycle, event_store, org_store
    ):
        roles = _seed_software_company(lifecycle)
        lifecycle.hire_employee(
            "C-1", "Boss", roles["CEO"], employee_id="E-1",
        )
        assert lifecycle.check_authority("E-1", "release.approve") is True
        lifecycle.leave("E-1")
        assert lifecycle.check_authority("E-1", "release.approve") is False
        ev = last_event(event_store)
        assert ev.type.value == "org.authority.checked"
        assert ev.payload["allowed"] is False

    def test_unknown_employee_raises(self, lifecycle):
        with pytest.raises(NotFoundError):
            lifecycle.check_authority("E-999", "code.modify")

    def test_check_authority_for_roles_is_pure(self, lifecycle, event_store):
        """纯函数路径: 不发事件 (供服务层复用, 不污染审计流)。"""
        roles = _seed_software_company(lifecycle)
        before = len(event_sequence(event_store))
        lifecycle.check_authority_for_roles([roles["CEO"]], "release.approve")
        lifecycle.check_authority_for_roles([roles["Developer"]], "release.approve")
        assert len(event_sequence(event_store)) == before

    def test_empty_role_list_denied(self, lifecycle):
        assert lifecycle.check_authority_for_roles([], "anything") is False
