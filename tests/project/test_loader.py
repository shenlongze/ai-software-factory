"""test_loader.py — project 配置加载器: project.yaml 解析 + agents/skills/workflows 映射。

覆盖: 项目定义字段 (名称/语言/仓库/技术栈) / 三张映射表 / 可选文件缺失 /
包装键与裸映射两种格式 / 损坏配置 → ProjectLoadError (不静默) /
映射一致性 (步骤 required_role/required_skill 全部可被 agents 满足)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from project.loader import (
    ProjectLoadError,
    default_examples_dir,
    discover_projects,
    load_project,
)

from conftest import _MARKPAD_FILES


class TestProjectDefParsing:
    def test_markpad_project_fields(self, examples_dir: Path):
        """project.yaml 解析: 名称/语言/仓库/技术栈。"""
        projects = discover_projects(examples_dir)
        assert [p.name for p in projects] == ["markpad"]
        p = projects[0]
        assert p.language == "dart"
        assert p.repository == "/Users/Shared/work/markpad"
        assert p.tech_stack == ["flutter", "dart"]
        assert p.description  # 非空

    def test_discover_empty_dir_returns_empty(self, tmp_path: Path):
        assert discover_projects(tmp_path / "no-such-examples") == []

    def test_discover_skips_dir_without_project_yaml(self, tmp_path: Path):
        (tmp_path / "foo").mkdir()
        assert discover_projects(tmp_path) == []

    def test_discover_sorts_by_name(self, tmp_path: Path):
        for name in ("zeta", "alpha"):
            d = tmp_path / name
            d.mkdir()
            (d / "project.yaml").write_text(
                f"name: {name}\nlanguage: x\n", encoding="utf-8"
            )
        assert [p.name for p in discover_projects(tmp_path)] == ["alpha", "zeta"]

    def test_broken_project_yaml_raises(self, tmp_path: Path):
        d = tmp_path / "broken"
        d.mkdir()
        (d / "project.yaml").write_text("name: [unclosed\n", encoding="utf-8")
        with pytest.raises(ProjectLoadError):
            discover_projects(tmp_path)

    def test_invalid_project_model_raises(self, tmp_path: Path):
        d = tmp_path / "bad"
        d.mkdir()
        (d / "project.yaml").write_text("name: 42\nlanguage: x\n", encoding="utf-8")
        with pytest.raises(ProjectLoadError):
            discover_projects(tmp_path)


class TestMappingLoading:
    def test_load_project_full_config(self, examples_dir: Path):
        """agents/skills/workflows 三张映射表完整加载。"""
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        assert [a.id for a in cfg.agents] == ["architect", "flutter-developer", "tester"]
        assert [a.role for a in cfg.agents] == ["product-manager", "developer", "test-engineer"]
        assert [s.id for s in cfg.skills] == ["architecture", "dart", "flutter", "testing"]
        assert [w.id for w in cfg.workflows] == ["bug-fix", "feature", "release"]

    def test_agent_mapping_fields(self, examples_dir: Path):
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        dev = next(a for a in cfg.agents if a.id == "flutter-developer")
        assert dev.role == "developer"
        assert dev.skills == ["flutter", "dart"]
        tester = next(a for a in cfg.agents if a.id == "tester")
        assert tester.role == "test-engineer"

    def test_skill_mapping_fields(self, examples_dir: Path):
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        fl = next(s for s in cfg.skills if s.id == "flutter")
        assert fl.category == "framework"
        assert "ui" in fl.capabilities

    def test_workflow_steps_carry_role_and_skill(self, examples_dir: Path):
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        feature = next(w for w in cfg.workflows if w.id == "feature")
        steps = feature.steps
        assert [s.id for s in steps] == ["architecture", "development", "testing", "validation"]
        assert steps[0].required_role == "product-manager"
        assert steps[0].required_skill == "architecture"
        assert steps[1].required_role == "developer"
        assert steps[1].required_skill == "flutter"
        bug = next(w for w in cfg.workflows if w.id == "bug-fix")
        assert [s.id for s in bug.steps] == ["reproduce", "diagnose", "fix", "verify"]

    def test_mapping_consistency_steps_match_agents(self, examples_dir: Path):
        """映射一致性: 每个步骤的 required_role/required_skill 都被某 agent 满足。"""
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        roles = {a.role for a in cfg.agents}
        skills = {s for a in cfg.agents for s in a.skills}
        for w in cfg.workflows:
            for st in w.steps:
                assert st.required_role in roles, f"{w.id}.{st.id} role {st.required_role!r}"
                assert st.required_skill in skills, f"{w.id}.{st.id} skill {st.required_skill!r}"

    def test_missing_project_returns_none(self, examples_dir: Path):
        assert load_project(examples_dir, "nope") is None

    def test_optional_files_missing_gives_empty_lists(self, examples_dir: Path):
        cfg = load_project(examples_dir, "markpad")
        assert cfg is not None
        for name in ("agents.yaml", "skills.yaml", "workflows.yaml"):
            (examples_dir / "markpad" / name).unlink()
        cfg2 = load_project(examples_dir, "markpad")
        assert cfg2 is not None
        assert cfg2.agents == [] and cfg2.skills == [] and cfg2.workflows == []
        assert cfg2.project.name == "markpad"

    def test_bare_mapping_format_supported(self, tmp_path: Path):
        """裸映射格式 (无包装键) 同样可解析。"""
        d = tmp_path / "p"
        d.mkdir()
        (d / "project.yaml").write_text("name: p\nlanguage: x\n", encoding="utf-8")
        (d / "agents.yaml").write_text(
            "a1:\n  role: developer\n  skills: [x]\n", encoding="utf-8"
        )
        (d / "workflows.yaml").write_text(
            "wf:\n  steps:\n    - id: s1\n      required_role: developer\n"
            "      required_skill: x\n",
            encoding="utf-8",
        )
        cfg = load_project(tmp_path, "p")
        assert cfg is not None
        assert [a.id for a in cfg.agents] == ["a1"]
        assert cfg.workflows[0].steps[0].required_role == "developer"

    def test_broken_agents_yaml_raises(self, examples_dir: Path):
        (examples_dir / "markpad" / "agents.yaml").write_text(
            "agents: [not, a, map]\n", encoding="utf-8"
        )
        with pytest.raises(ProjectLoadError):
            load_project(examples_dir, "markpad")

    def test_broken_workflow_entry_raises(self, examples_dir: Path):
        (examples_dir / "markpad" / "workflows.yaml").write_text(
            "workflows:\n  feature: just-a-string\n", encoding="utf-8"
        )
        with pytest.raises(ProjectLoadError):
            load_project(examples_dir, "markpad")


class TestExamplesDirResolution:
    def test_default_points_to_repo_examples(self):
        d = default_examples_dir()
        assert d.is_dir()
        assert (d / "markpad" / "project.yaml").is_file()
        # 仓库根/examples: factory-core/project → 仓库根
        assert d.name == "examples"

    def test_env_override(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FACTORY_EXAMPLES_DIR", str(tmp_path))
        assert default_examples_dir() == tmp_path

    def test_markpad_files_complete(self):
        """示例目录 5 文件齐全 (README + 4 YAML)。"""
        d = default_examples_dir() / "markpad"
        assert (d / "README.md").is_file()
        for name in _MARKPAD_FILES:
            assert (d / name).is_file(), f"missing {name}"
