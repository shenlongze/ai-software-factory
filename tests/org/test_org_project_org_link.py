"""tests/org/test_org_project_org_link.py — 组织×工作正交: 项目关联公司/部门 (S10-1xx)。

覆盖:
- Project 模型 company_id/department_ids 字段（默认值向后兼容）
- register --company/--departments 透传
- company department create（渐进式建部门）
- project link 挂接/解绑部门（多对多, 渐进式）
- 部门不存在 → 明确错误
"""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ORG = import_module("factory-org.org.cli")
PROJECTS = import_module("factory-org.org.projects")


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _company(tmp_path: Path, cid: str = "C-1") -> str:
    ws = _ws(tmp_path)
    r = ORG.cmd_company_create(ws, SimpleNamespace(template="solo", name="测试", id=cid))
    return ws, r["company"]["id"]


def _department(ws: Path, cid: str, name: str, did: str) -> None:
    r = ORG._dispatch(ws, SimpleNamespace(
        command="company", company_command="department", department_command="create",
        company_id=cid, name=name, id=did))
    assert r.get("ok") is True, r


def _project(ws: Path, name: str, pid: str, company: str = "", departments: str = "") -> dict:
    repo = _ws_repo()
    return ORG.cmd_project_register(ws, SimpleNamespace(
        repo_path=str(repo), name=name, language="python", framework="",
        build_command="", test_command="", project_type="app", goal=name, id=pid,
        company=company, departments=departments))


def _ws_repo() -> Path:
    import tempfile
    repo = Path(tempfile.mkdtemp())
    (repo / "main.py").write_text("print('hi')", encoding="utf-8")
    return repo


class TestProjectOrgModel:
    def test_project_has_company_and_departments_defaults(self):
        proj = PROJECTS.Project(id="P-1", name="X")
        assert proj.company_id == ""
        assert proj.department_ids == []
        # 旧数据兼容: 显式 null → 空
        proj2 = PROJECTS.Project.model_validate(
            {"id": "P-1", "name": "X", "company_id": None})
        assert proj2.company_id == ""

    def test_register_with_company_and_departments(self, tmp_path):
        ws, cid = _company(tmp_path)
        _department(ws, cid, "前端", "D-fe")
        _department(ws, cid, "后端", "D-be")
        r = _project(ws, "记账", "P-1", company=cid, departments="D-fe,D-be")
        assert r["ok"] is True
        proj = r["project"]
        assert proj["company_id"] == cid
        assert proj["department_ids"] == ["D-fe", "D-be"]  # 多对多


class TestProjectLink:
    def test_link_and_unlink_departments(self, tmp_path):
        ws, cid = _company(tmp_path)
        _department(ws, cid, "前端", "D-fe")
        _department(ws, cid, "后端", "D-be")
        _project(ws, "记账", "P-1")
        # 渐进式: 项目先 Solo, 后期挂部门
        r = ORG._dispatch(ws, SimpleNamespace(
            command="project", project_command="link", project_id="P-1",
            departments="D-fe,D-be", unlink=""))
        assert r["project"]["department_ids"] == ["D-be", "D-fe"]
        # 解绑一个
        r2 = ORG._dispatch(ws, SimpleNamespace(
            command="project", project_command="link", project_id="P-1",
            departments="", unlink="D-fe"))
        assert r2["project"]["department_ids"] == ["D-be"]

    def test_link_missing_department_errors(self, tmp_path):
        ws, cid = _company(tmp_path)
        _project(ws, "记账", "P-1")
        r = ORG._dispatch(ws, SimpleNamespace(
            command="project", project_command="link", project_id="P-1",
            departments="D-nope", unlink=""))
        assert r["ok"] is False
        assert "department not found" in r["error"]

    def test_link_missing_project_errors(self, tmp_path):
        ws = _ws(tmp_path)
        r = ORG._dispatch(ws, SimpleNamespace(
            command="project", project_command="link", project_id="P-nope",
            departments="D-fe", unlink=""))
        assert r["ok"] is False
        assert "project not found" in r["error"]
