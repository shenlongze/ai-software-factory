"""tests/s7/test_s7_integration.py — S7-001 集成链 + 向后兼容 (Integration, ADR-0039)。

覆盖 (任务清单: hire→project→sprint→task 关联链 / 向后兼容: 既有 roles.json
无 role_ref 加载零破坏 / 双体系兼容):
- 全链集成: company(software_company 模板) → hire → project → link task →
  sprint → add task → stage → artifact, 事件序列完整可审计
- 双体系统一: resolve_role_ref 3 链 (id 精确 / 公司内名称大小写不敏感 /
  exec 注册表 role_ref 匹配 — "qa" 别名经注册表解析到 tester 角色)
- CLI 统一解析: _resolve_role_id 委托 OrgLifecycle.resolve_role_ref
- 向后兼容: 既有 roles.json (无 role_ref 字段) 加载零破坏, role_ref 默认 "";
  无 role_ref 的角色走 1/2 链照常; 模板实例化后角色带 role_ref
- 数据空间隔离: ProjectStore 五新文件与 OrgStore 六旧文件同目录并存互不影响

依赖: 本目录 conftest 已挂 factory-core + factory-org + factory-exec。
"""

from __future__ import annotations

import json

import pytest

from org.cli import _resolve_role_id
from org.lifecycle import NotFoundError, OrgLifecycle
from org.models import Role
from org.projects import Project, ProjectLifecycle
from org.store import OrgStore

from s7_helpers import event_sequence, payload_of


@pytest.fixture
def org(org_store: OrgStore, logger) -> OrgLifecycle:
    return OrgLifecycle(org_store, logger=logger)


@pytest.fixture
def plife(project_store, logger) -> ProjectLifecycle:
    return ProjectLifecycle(project_store, logger=logger)


def _software_company(org: OrgLifecycle) -> str:
    return org.create_company("Acme", template="software_company", company_id="C-1").id


# ------------------------------------------------------------------ 全链集成


class TestFullChain:
    def test_company_to_artifact_full_chain(self, org, plife, org_store, event_store):
        """hire → project → link task → sprint → add task → stage → artifact。"""
        company_id = _software_company(org)
        # 双体系统一解析: "qa" 别名 → 公司内 QA 角色 (role_ref=tester)
        qa_role_id = org.resolve_role_ref(company_id, "qa")
        qa_role = org_store.get_role(qa_role_id)
        assert qa_role.name == "QA"
        assert qa_role.role_ref == "tester"

        employee = org.hire_employee(
            company_id, "Ada", qa_role_id, capabilities=["testing"],
            employee_id="E-1",
        )
        assert employee.is_active

        project = plife.create_project("Ship v1", user_id="U-1", project_id="P-1")
        plife.link_task("P-1", "T-1")
        sprint = plife.create_sprint("P-1", "Sprint 1", sprint_id="S-1")
        sprint = plife.add_task_to_sprint("S-1", "T-1")
        stage = plife.create_stage("WF-1", "developer", order=1, stage_id="STG-1")
        artifact = plife.create_artifact(
            "STG-1", "code", ref="file:///src", artifact_id="A-1"
        )

        assert project.lifecycle.value == "idea"
        assert sprint.tasks == ["T-1"]
        assert stage.role_id == "developer"
        assert artifact.type.value == "code"

        # 数据空间: 六旧库 (知识未绑定, knowledge.json 未创建) + 五新库并存
        old_files = {p.name for p in org_store.files()}
        assert old_files == {
            "companies.json", "departments.json", "roles.json",
            "employees.json", "authorities.json",
        }
        new_files = {p.name for p in plife.store.files()}
        assert new_files == {
            "projects.json", "sprints.json", "stages.json",
            "artifacts.json", "project_task_links.json",
        }

    def test_chain_event_sequence_complete(self, org, plife, event_store):
        """全链事件序列: 组织事件 + 生命周期事件逐类可审计。"""
        company_id = _software_company(org)
        qa_role_id = org.resolve_role_ref(company_id, "qa")
        org.hire_employee(company_id, "Ada", qa_role_id, employee_id="E-1")
        plife.create_project("Ship v1", project_id="P-1")
        plife.link_task("P-1", "T-1")
        plife.create_sprint("P-1", "S1", sprint_id="S-1")
        plife.add_task_to_sprint("S-1", "T-1")
        plife.create_stage("WF-1", "developer", stage_id="STG-1")
        plife.create_artifact("STG-1", "prd", artifact_id="A-1")

        seq = event_sequence(event_store)
        for expected in (
            "org.company.created",
            "org.employee.joined",
            "org.project.created",
            "org.project.task_linked",
            "org.sprint.created",
            "org.sprint.task_added",
            "org.stage.created",
            "org.artifact.created",
        ):
            assert expected in seq, expected
        # 生命周期事件可重建关键字段
        p_payload = payload_of(event_store, "org.project.created")
        assert p_payload["project_id"] == "P-1" and p_payload["lifecycle"] == "idea"

    def test_project_lifecycle_integration(self, org, plife, event_store):
        """项目生命周期流转 + 事件: idea→active→maintained→archived 全程审计。"""
        company_id = _software_company(org)
        dev_role_id = org.resolve_role_ref(company_id, "developer")
        org.hire_employee(company_id, "Bob", dev_role_id, employee_id="E-2")
        plife.create_project("App", project_id="P-1")
        for state in ("active", "maintained", "archived"):
            plife.transition_lifecycle("P-1", state)
        # 取最后一次 lifecycle_changed (maintained→archived), 非首条
        lifecycle_events = [
            e for e in event_store.query()
            if e.type.value == "org.project.lifecycle_changed"
        ]
        assert len(lifecycle_events) == 3
        assert lifecycle_events[-1].payload["from_lifecycle"] == "maintained"
        assert lifecycle_events[-1].payload["to_lifecycle"] == "archived"
        assert plife.get_project("P-1").is_archived


# ------------------------------------------------------------------ 双体系统一


class TestDualSystemResolution:
    def test_resolve_role_ref_chain1_id_exact(self, org, org_store):
        """链 1: 角色 id 精确匹配 (全局唯一)。"""
        company_id = _software_company(org)
        roles = org_store.list_roles_by_company(company_id)
        assert org.resolve_role_ref(company_id, roles[0].id) == roles[0].id

    def test_resolve_role_ref_chain2_name_case_insensitive(self, org):
        """链 2: 公司内角色名大小写不敏感 (Developer == developer)。"""
        company_id = _software_company(org)
        role_id = org.resolve_role_ref(company_id, "Developer")
        assert org_store_role_name(org, role_id) == "Developer"
        assert org.resolve_role_ref(company_id, "developer") == role_id

    def test_resolve_role_ref_chain3_exec_alias(self, org):
        """链 3: exec 注册表统一解析 — "qa" 别名 → 公司内 QA 角色 (role_ref 匹配)。"""
        company_id = _software_company(org)
        qa_id = org.resolve_role_ref(company_id, "qa")
        role = org._store.get_role(qa_id)
        assert role.name == "QA"
        assert role.role_ref == "tester"

    def test_resolve_role_ref_chain3_exec_display_name(self, org):
        """链 3 显示名: "Test Engineer" 经注册表别名 → tester → QA 角色。"""
        company_id = _software_company(org)
        qa_id = org.resolve_role_ref(company_id, "Test Engineer")
        assert org._store.get_role(qa_id).role_ref == "tester"

    def test_resolve_role_ref_unknown_raises(self, org):
        company_id = _software_company(org)
        with pytest.raises(NotFoundError, match="role not found"):
            org.resolve_role_ref(company_id, "no-such-role")

    def test_cli_resolve_role_id_delegates(self, org, org_store):
        """CLI 统一解析: 有 company → 委托 OrgLifecycle.resolve_role_ref。"""
        company_id = _software_company(org)
        role_id = _resolve_role_id(org_store, company_id, "qa")
        assert org_store.get_role(role_id).role_ref == "tester"
        # 无 company → 全局 id/名称匹配
        role_id_2 = _resolve_role_id(org_store, None, "QA")
        assert role_id_2 == role_id

    def test_template_instantiated_roles_carry_role_ref(self, org, org_store):
        """模板实例化后 Role.role_ref 落库 (双体系单一事实源连接)。"""
        company_id = _software_company(org)
        refs = {
            r.name: r.role_ref
            for r in org_store.list_roles_by_company(company_id)
            if r.role_ref
        }
        assert refs == {
            "Product Manager": "product-manager",
            "Architect": "architect",
            "Developer": "developer",
            "QA": "tester",
        }


def org_store_role_name(org: OrgLifecycle, role_id: str) -> str:
    role = org._store.get_role(role_id)
    assert role is not None
    return role.name


# ------------------------------------------------------------------ 向后兼容


class TestBackwardCompat:
    def test_legacy_roles_json_without_role_ref_loads(self, org_store, tmp_path):
        """既有 roles.json (无 role_ref 字段) 加载零破坏 → 默认 ""。"""
        org_dir = org_store.dir
        org_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "roles": {
                "R-1": {
                    "id": "R-1",
                    "company_id": "C-1",
                    "department_id": "",
                    "name": "Developer",
                    "responsibility": "",
                    "authority_policy": {},
                    "human": False,
                    # 无 role_ref 字段 = S7-001 之前的数据
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
            }
        }
        (org_dir / "roles.json").write_text(
            json.dumps(legacy, ensure_ascii=False), encoding="utf-8"
        )
        reloaded = OrgStore(org_dir)
        role = reloaded.get_role("R-1")
        assert role is not None
        assert role.name == "Developer"
        assert role.role_ref == ""  # 缺省零影响

    def test_legacy_role_resolves_by_name_and_id(self, org, org_store):
        """无 role_ref 的角色走 1/2 链照常 (向后兼容行为不变)。"""
        company_id = _software_company(org)
        # 手工构造一个无 role_ref 的旧式角色
        legacy_role = Role(
            id="R-OLD", company_id=company_id, name="Reviewer", human=False,
        )
        org_store.save_role(legacy_role)
        assert org.resolve_role_ref(company_id, "R-OLD") == "R-OLD"      # 链 1
        assert org.resolve_role_ref(company_id, "reviewer") == "R-OLD"   # 链 2
        with pytest.raises(NotFoundError):
            org.resolve_role_ref(company_id, "ReviewerX")  # 链 3 不命中 → 报错

    def test_legacy_company_flow_unchanged(self, org, org_store):
        """既有公司创建/入职流程逐位不变 (双体系共存零破坏)。"""
        company_id = _software_company(org)
        roles = org_store.list_roles_by_company(company_id)
        assert {r.name for r in roles} == {
            "CEO", "Product Manager", "Architect", "Developer", "QA",
        }
        ceo = next(r for r in roles if r.name == "CEO")
        assert ceo.human is True and ceo.role_ref == ""

    def test_org_store_and_project_store_share_dir(self, org_store, project_store, org_dir):
        """六旧库 + 五新库同目录: 各自 files() 只报自己的文件 (零串扰)。"""
        org_store.save_role(Role(
            id="R-1", company_id="C-1", name="Developer", human=False,
        ))
        assert {p.name for p in org_store.files()} == {"roles.json"}
        assert project_store.files() == []
        project_store.save_project(Project(id="P-1", name="A"))
        assert {p.name for p in project_store.files()} == {"projects.json"}
        assert {p.name for p in org_store.files()} == {"roles.json"}
