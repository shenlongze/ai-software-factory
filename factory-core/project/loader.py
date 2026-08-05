"""project/loader.py — 只读加载 examples/*/project.yaml 等项目配置 (Phase 5A, ADR-0013)。

- YAML 解析依赖 PyYAML (轻量纯 wheel ~170KB, 已声明于 pyproject dependencies — ADR-0013 决策 3)
- 只读: 不写工厂状态, 不注册 agent/workflow — 仅解析与映射 (注册仍走既有 CLI/引擎 API)
- 约定 (KISS): project.yaml 必选; agents/skills/workflows.yaml 缺失时为空列表;
  解析/校验失败抛 ProjectLoadError (CLI 转退出码 1), 绝不静默返回空 (同 JSON store 铁律)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .models import (
    AgentMapping,
    ProjectConfig,
    ProjectDef,
    SkillDef,
    WorkflowMapping,
    WorkflowStepMapping,
)


class ProjectLoadError(Exception):
    """项目配置加载失败 (YAML 语法错误 / 模型校验失败)。"""


def default_examples_dir() -> Path:
    """默认 examples 目录 = 仓库根/examples; FACTORY_EXAMPLES_DIR 环境变量覆盖。

    factory-core/project/loader.py → parents[0]=project, [1]=factory-core, [2]=仓库根。
    """
    env = os.environ.get("FACTORY_EXAMPLES_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "examples"


def discover_projects(examples_dir: str | Path) -> list[ProjectDef]:
    """扫描 examples/*/project.yaml → ProjectDef 列表 (按 name 排序)。

    无 project.yaml 的目录跳过; 有但解析/校验失败 → ProjectLoadError (不静默跳过)。
    """
    base = Path(examples_dir)
    projects: list[ProjectDef] = []
    if not base.is_dir():
        return projects
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        proj_file = d / "project.yaml"
        if not proj_file.is_file():
            continue
        try:
            projects.append(ProjectDef.model_validate(_load_yaml(proj_file)))
        except (ValueError, TypeError) as exc:  # pydantic ValidationError 等 → 配置损坏
            raise ProjectLoadError(f"invalid project config in {proj_file}: {exc}") from exc
    projects.sort(key=lambda p: p.name)
    return projects


def load_project(examples_dir: str | Path, name: str) -> ProjectConfig | None:
    """加载 <examples_dir>/<name>/ 下完整配置; 无 project.yaml → None。

    可选文件 (agents/skills/workflows.yaml) 缺失或为空 → 对应列表为空。
    """
    pdir = Path(examples_dir) / name
    proj_file = pdir / "project.yaml"
    if not proj_file.is_file():
        return None
    project = _parse_project(proj_file)
    return ProjectConfig(
        project=project,
        agents=_load_agents(pdir / "agents.yaml"),
        skills=_load_skills(pdir / "skills.yaml"),
        workflows=_load_workflows(pdir / "workflows.yaml"),
    )


def _parse_project(path: Path) -> ProjectDef:
    try:
        return ProjectDef.model_validate(_load_yaml(path))
    except (ValueError, TypeError) as exc:
        raise ProjectLoadError(f"invalid project config in {path}: {exc}") from exc


def _load_yaml(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ProjectLoadError(f"invalid yaml in {path}: {exc}") from exc


def _load_optional_yaml(path: Path) -> Any:
    """可选配置文件: 缺失 → None; 存在 → 解析 (语法错误照抛)。"""
    if not path.is_file():
        return None
    return _load_yaml(path)


def _section_map(data: Any, section: str, path: Path) -> dict:
    """映射文件结构: 支持包装键 (agents: {id: ...}) 与裸映射 ({id: ...}) 两种格式。

    包装键存在且为 dict 时以其为准 (示例文件用包装键, 更可读); 否则整体作为映射。
    空文件/非映射 → {} (对应映射列表为空, 不报错 — 可选文件语义)。
    """
    if not isinstance(data, dict):
        return {}
    inner = data.get(section)
    if isinstance(inner, dict):
        return inner
    if section in data:
        raise ProjectLoadError(
            f"invalid {section} section in {path}: expected mapping under {section!r}"
        )
    return data


def _load_agents(path: Path) -> list[AgentMapping]:
    """agents.yaml: {agents: {id: {role, skills, ...}}} (或裸 {id: ...}) → 排序列表。"""
    data = _section_map(_load_optional_yaml(path), "agents", path)
    agents: list[AgentMapping] = []
    for agent_id, fields in data.items():
        if not isinstance(fields, dict):
            raise ProjectLoadError(f"invalid agent entry in {path}: {agent_id!r} (expected mapping)")
        try:
            # id 以包装键为准 (内层若冗余声明 id 同样被覆盖)
            agents.append(AgentMapping.model_validate({**fields, "id": agent_id}))
        except (ValueError, TypeError) as exc:
            raise ProjectLoadError(f"invalid agent config in {path}: {agent_id!r}: {exc}") from exc
    agents.sort(key=lambda a: a.id)
    return agents


def _load_skills(path: Path) -> list[SkillDef]:
    """skills.yaml: {skills: {id: {category, ...}}} (或裸 {id: ...}) → 排序列表。"""
    data = _section_map(_load_optional_yaml(path), "skills", path)
    skills: list[SkillDef] = []
    for skill_id, fields in data.items():
        if not isinstance(fields, dict):
            raise ProjectLoadError(f"invalid skill entry in {path}: {skill_id!r} (expected mapping)")
        try:
            # id 以包装键为准 (内层若冗余声明 id 同样被覆盖)
            skills.append(SkillDef.model_validate({**fields, "id": skill_id}))
        except (ValueError, TypeError) as exc:
            raise ProjectLoadError(f"invalid skill config in {path}: {skill_id!r}: {exc}") from exc
    skills.sort(key=lambda s: s.id)
    return skills


def _load_workflows(path: Path) -> list[WorkflowMapping]:
    """workflows.yaml: {workflows: {wf_id: {steps: [...]}}} (或裸 {wf_id: ...}) → 排序列表。"""
    data = _section_map(_load_optional_yaml(path), "workflows", path)
    workflows: list[WorkflowMapping] = []
    for wf_id, fields in data.items():
        if not isinstance(fields, dict):
            raise ProjectLoadError(f"invalid workflow entry in {path}: {wf_id!r} (expected mapping)")
        try:
            raw = dict(fields)
            raw["steps"] = [
                WorkflowStepMapping(**step) for step in raw.get("steps") or []
            ]
            # id 以包装键为准 (内层 id 冗余声明时同样被覆盖)
            workflows.append(WorkflowMapping.model_validate({**raw, "id": wf_id}))
        except (ValueError, TypeError) as exc:
            raise ProjectLoadError(f"invalid workflow config in {path}: {wf_id!r}: {exc}") from exc
    workflows.sort(key=lambda w: w.id)
    return workflows
