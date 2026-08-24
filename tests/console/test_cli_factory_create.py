"""tests/console/test_cli_factory_create.py — factory create 统一入口 (v1.1.17)。

覆盖: create company / department / project 三种类型 + 项目关联公司部门。
bin/factory 薄包装, 直接测 FactoryCLI.create_cmd (隔离 HOME)。
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import argparse
import json

import pytest

CF = import_module("factory-console.cli_factory")


@pytest.fixture
def factory_cli(tmp_path, monkeypatch):
    """隔离数据目录 (HOME 隔离, ConfigProvider 默认 ~/.factory 指向 tmp)。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path))  # 若 config 支持
    app = CF.FactoryCLI(CF.ConfigProvider())
    # 强制 data_dir 指向临时 (不依赖 HOME 解析)
    app.data_dir = tmp_path / ".factory"
    return app


def _args(**kw):
    base = dict(command="create", create_type="", name="", template="solo", company="",
                departments="", goal="", id=None, language="", framework="",
                build_command="", test_command="", project_type="", repo_path=None,
                json=True)
    base.update(kw)
    return argparse.Namespace(**base)


class TestCreateCompany:
    def test_create_company(self, factory_cli):
        rc = factory_cli.create_cmd(_args(create_type="company", name="测试", id="C-1"))
        assert rc == 0
        data = json.loads((factory_cli.data_dir / "org" / "companies.json").read_text())
        assert "C-1" in data["companies"]


class TestCreateDepartment:
    def test_create_department_requires_company(self, factory_cli):
        rc = factory_cli.create_cmd(_args(create_type="department", name="财务"))
        assert rc == 2  # 缺 --company

    def test_create_department(self, factory_cli):
        factory_cli.create_cmd(_args(create_type="company", name="测试", id="C-1"))
        rc = factory_cli.create_cmd(
            _args(create_type="department", company="C-1", name="财务", id="D-1"))
        assert rc == 0
        data = json.loads((factory_cli.data_dir / "org" / "departments.json").read_text())
        assert "D-1" in data["departments"]


class TestCreateProject:
    def test_create_project_with_org_link(self, factory_cli):
        factory_cli.create_cmd(_args(create_type="company", name="测试", id="C-1"))
        factory_cli.create_cmd(
            _args(create_type="department", company="C-1", name="财务", id="D-1"))
        rc = factory_cli.create_cmd(
            _args(create_type="project", name="记账", id="P-1",
                  company="C-1", departments="D-1", goal="记账"))
        assert rc == 0
        data = json.loads((factory_cli.data_dir / "org" / "projects.json").read_text())
        proj = data["projects"]["P-1"]
        assert proj["company_id"] == "C-1"
        assert proj["department_ids"] == ["D-1"]  # 组织×工作正交: 项目挂部门

    def test_create_project_solo(self, factory_cli):
        """便捷铁律: 前期只要项目 (无组织), Solo 最简。"""
        rc = factory_cli.create_cmd(_args(create_type="project", name="记账", id="P-1"))
        assert rc == 0
        data = json.loads((factory_cli.data_dir / "org" / "projects.json").read_text())
        proj = data["projects"]["P-1"]
        assert proj["company_id"] == ""
        assert proj["department_ids"] == []

    def test_unknown_type(self, factory_cli):
        rc = factory_cli.create_cmd(_args(create_type="team", name="X"))
        assert rc == 2
