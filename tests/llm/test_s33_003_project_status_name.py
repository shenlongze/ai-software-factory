"""S34-001: project_status 项目名解析 — org/projects.json SSOT。"""

import json
from pathlib import Path

from factory_console.session.observability import project_status


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-abc").mkdir(parents=True)
    (ws / "projects" / "P-abc" / "project.json").write_text(
        json.dumps({"name": "P-abc", "status": "idea"}), encoding="utf-8"
    )
    (ws / "org").mkdir()
    (ws / "org" / "projects.json").write_text(
        json.dumps({"projects": {"P-abc": {"id": "P-abc", "name": "旅行记账"}}}),
        encoding="utf-8",
    )
    return ws


def test_project_status_uses_org_name(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    st = project_status(ws, ws / "projects" / "P-abc")
    # project.json name 是 ID 占位 → org 覆盖为真实名称
    assert st.get("project") == "旅行记账"
    assert st.get("lifecycle") == "idea"


def test_project_status_org_missing_falls_back(tmp_path: Path) -> None:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-def").mkdir(parents=True)
    (ws / "projects" / "P-def" / "project.json").write_text(
        json.dumps({"name": "P-def", "status": "idea"}), encoding="utf-8"
    )
    # 无 org/projects.json → 不崩溃, 用目录名兜底
    st = project_status(ws, ws / "projects" / "P-def")
    assert st.get("project") == "P-def"
