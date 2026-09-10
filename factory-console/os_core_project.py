"""factory-console/os_core_project.py — OS Core Boundary: Project (MU-CORE-05).

Project = AI Factory OS Core 的 **Work Anchor**。

SSOT (rehome logically, 不新建第二个 store):
    factory-org/org/projects.py ProjectLifecycle -> <root>/org/projects.json
    （project_ssot.py 已声明 org = name/status 唯一可变真相; Web /api/projects 已走此路径）

语义 (Constitution v2 Art.13):
    Project ≠ Sprint ≠ Work ≠ Task ≠ TaskNode ≠ Execution ≠ Conversation ≠ Session
    conv_id / session_id 只能 reference project_id, 绝不作 project identity。

字段 (来自 org Project, 不复制):
    project_id / company_id / name / goal / lifecycle(status) / department_ids / created_at / updated_at
    Software Factory 专用字段 (repo_path/language/framework/build_command/...) 保留在 org Project,
    但它们是 Factory view / metadata, 不定义 OS Project 身份。

范围外 (后续 MU): Work/Workstream/Task/TaskNode/Execution/Capability/Plugin/Resolution/Resource/
Governance/HITL/SQLite。project_agile 保持 Agile View (本 MU 只提供投影校验路径)。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ORG_SRC = _REPO_ROOT / "factory-org"

OS_PROJECT_SSOT = "factory-org/org/projects.py"


def _org_modules() -> tuple[Any, Any]:
    try:
        from org import models as org_models
        from org import projects as org_projects
    except ModuleNotFoundError:
        src = str(_ORG_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)
        from org import models as org_models
        from org import projects as org_projects
    return org_models, org_projects


def _store(root: str | Path) -> Any:
    _, org_projects = _org_modules()
    return org_projects.ProjectStore(Path(root) / "org")


def _lifecycle(root: str | Path) -> Any:
    _, org_projects = _org_modules()
    return org_projects.ProjectLifecycle(_store(root))


def _require_company(root: str | Path, company_id: str) -> None:
    from .os_core_company_organization import get_company

    if get_company(root, company_id) is None:
        raise ValueError(f"Company 不存在: {company_id}")


# ---------------------------------------------------------------- Project CRUD

def create_project(root: str | Path, *, name: str, company_id: str = "", goal: str = "",
                   project_id: str | None = None) -> dict[str, Any]:
    """创建 OS Project (SSOT=org); company_id 若提供必须存在 (MU-CORE-01 边界)。"""
    org_models, _ = _org_modules()
    company_id = str(company_id or "")
    if company_id:
        _require_company(root, company_id)
    store = _store(root)
    lifecycle = _lifecycle(root)
    project = lifecycle.create_project(name, user_id="os", goal=goal, project_id=project_id)
    if company_id:
        project = project.model_copy(update={"company_id": company_id,
                                             "updated_at": org_models.utcnow()})
        store.save_project(project)
    return project.to_dict()


def get_project(root: str | Path, project_id: str) -> dict[str, Any] | None:
    project = _store(root).get_project(str(project_id))
    return project.to_dict() if project is not None else None


def list_projects(root: str | Path, *, company_id: str = "") -> list[dict[str, Any]]:
    projects = [p.to_dict() for p in _store(root).list_projects()]
    if company_id:
        projects = [p for p in projects if p.get("company_id", "") == str(company_id)]
    return projects


def set_project_company(root: str | Path, project_id: str, company_id: str) -> dict[str, Any]:
    """设置/迁移 Project 的 Company 归属 (company 必须存在)。"""
    org_models, _ = _org_modules()
    _require_company(root, company_id)
    store = _store(root)
    project = store.get_project(str(project_id))
    if project is None:
        raise ValueError(f"Project 不存在: {project_id}")
    project = project.model_copy(update={"company_id": str(company_id),
                                         "updated_at": org_models.utcnow()})
    store.save_project(project)
    return project.to_dict()


def set_project_lifecycle(root: str | Path, project_id: str, target: str) -> dict[str, Any]:
    """Project lifecycle 迁移 (org PROJECT_TRANSITIONS 单向无环; archived 终态)。"""
    lifecycle = _lifecycle(root)
    project = lifecycle.transition_lifecycle(str(project_id), target)
    return project.to_dict()


# ---------------------------------------------------------------- Conversation reference (≠ identity)

def link_conversation(root: str | Path, project_id: str, conversation_id: str) -> dict[str, Any]:
    """Conversation reference -> Project (写 conversation.project_id 引用; conv_id 不是 project_id)。"""
    from . import product_understanding as pu

    if get_project(root, project_id) is None:
        raise ValueError(f"Project 不存在: {project_id}")
    doc = pu._load_conv(root, conversation_id)
    if doc is None:
        raise ValueError(f"Conversation 不存在: {conversation_id}")
    doc["project_id"] = str(project_id)
    pu._save_conv(root, conversation_id, doc)
    return {"conversation_id": conversation_id, "project_id": str(project_id)}


def resolve_project_for_conversation(root: str | Path, conversation_id: str) -> dict[str, Any] | None:
    """Conversation -> project_id (reference) -> OS Project (SSOT 解析)。"""
    from . import product_understanding as pu

    doc = pu._load_conv(root, conversation_id)
    pid = str((doc or {}).get("project_id") or "")
    if not pid:
        return None
    return get_project(root, pid)


def conversations_for_project(root: str | Path, project_id: str) -> list[dict[str, Any]]:
    """列出引用该 Project 的 conversations (只读投影)。"""
    from . import product_understanding as pu

    out = []
    conv_dir = Path(root) / "conversations"
    if not conv_dir.is_dir():
        return out
    for f in sorted(conv_dir.glob("conv-*.json")):
        doc = pu._load_conv(root, f.stem)
        if doc is not None and str(doc.get("project_id") or "") == str(project_id):
            out.append({"conversation_id": doc.get("id"), "title": doc.get("title", ""),
                        "project_id": doc.get("project_id")})
    return out


__all__ = [
    "OS_PROJECT_SSOT",
    "conversations_for_project",
    "create_project",
    "get_project",
    "link_conversation",
    "list_projects",
    "resolve_project_for_conversation",
    "set_project_company",
    "set_project_lifecycle",
]
