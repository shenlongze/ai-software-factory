"""tests/console/test_external_skills.py — U-4 外部 skill 真实加载执行 (v1.1.189)。

Founder 2026-08-27: 外部 skill 在 agent 执行时真实注入指令 (不是 mock)。
覆盖:
- parse_skill_md: Codex 风格 frontmatter + 正文 → {id/name/description/instructions};
  无 frontmatter → id=目录名, 正文全为指令 (诚实兜底)
- load_external_skills: 扫描 <dir>/*/SKILL.md → 幂等写 skills.json (刷新不覆盖 id/name)
- Service._get_skill_registry: skills.json 条目注册进 SkillRegistry →
  SkillContext.instructions 可注入 (agent 执行真实用)
- HTTP: POST /api/skills/scan (默认/指定目录)
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-exec"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_ext = importlib.import_module("factory-console.external_skills")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_service_mod = importlib.import_module("factory-console.service")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装"
)


def _write_skill_md(skill_dir: Path, *, sid: str = "my-skill", name: str = "My Skill",
                    desc: str = "desc", body: str = "按以下规则做事") -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    md = skill_dir / "SKILL.md"
    md.write_text(
        f"---\nid: {sid}\nname: {name}\ndescription: {desc}\ncategory: external\nversion: 1.2.0\n---\n{body}",
        encoding="utf-8",
    )
    return md


class TestParseSkillMd:
    def test_parse_frontmatter_and_body(self, tmp_path):
        md = _write_skill_md(tmp_path / "my-skill")
        p = _ext.parse_skill_md(md)
        assert p["id"] == "my-skill"
        assert p["name"] == "My Skill"
        assert p["description"] == "desc"
        assert p["category"] == "external"
        assert p["version"] == "1.2.0"
        assert p["instructions"] == "按以下规则做事"

    def test_parse_no_frontmatter_fallback(self, tmp_path):
        d = tmp_path / "bare-skill"
        d.mkdir(parents=True)
        md = d / "SKILL.md"
        md.write_text("就是一段指令", encoding="utf-8")
        p = _ext.parse_skill_md(md)
        assert p["id"] == "bare-skill"
        assert p["instructions"] == "就是一段指令"


class TestLoadExternalSkills:
    def test_load_idempotent_and_refresh(self, tmp_path):
        skills_file = tmp_path / "skills.json"
        base = tmp_path / "external"
        _write_skill_md(base / "my-skill", body="v1 指令")
        loaded = _ext.load_external_skills(skills_file, [base])
        assert len(loaded) == 1 and loaded[0]["id"] == "my-skill"
        # 重扫 → 刷新 instructions, 不重复
        _write_skill_md(base / "my-skill", body="v2 指令")
        loaded2 = _ext.load_external_skills(skills_file, [base])
        assert len(loaded2) == 1
        data = json.loads(skills_file.read_text(encoding="utf-8"))
        assert data["skills"]["my-skill"]["instructions"] == "v2 指令"

    def test_scan_none_honest(self, tmp_path):
        skills_file = tmp_path / "skills.json"
        assert _ext.load_external_skills(skills_file, [tmp_path / "nope"]) == []


class TestSkillRegistryInjection:
    def test_external_skill_registered_into_registry(self, tmp_path):
        """U-4 核心: skills.json 外部 skill → SkillRegistry → 可注入指令。"""
        # 准备 skills.json
        skills_file = tmp_path / "skills" / "skills.json"
        skills_file.parent.mkdir(parents=True)
        skills_file.write_text(json.dumps({"skills": {
            "my-skill": {"id": "my-skill", "name": "My Skill", "category": "external",
                         "version": "1.0", "instructions": "按规则 A 做事"}
        }}), encoding="utf-8")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        registry = service._get_skill_registry()
        assert registry is not None
        skill = registry.get("my-skill")
        assert skill is not None
        assert skill.instructions == "按规则 A 做事"
        # AgentExecutionLoop 的注入源: skill_context_for 能拿到指令
        from exec.skill import skill_context_for
        ctx = skill_context_for("agent-1", ["my-skill"], registry)
        assert ctx is not None
        assert ctx.instructions == "按规则 A 做事"


@requires_fastapi
class TestExternalSkillsHttp:
    def test_scan_endpoint_loads(self, tmp_path):
        base = tmp_path / "external"
        _write_skill_md(base / "api-review", sid="api-review", name="API 审查")
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        app = _adapter.build_app(service, event_logger=None, factory_root=tmp_path)
        with TestClient(app) as c:
            r = c.post("/api/skills/scan", json={"dir": str(base)})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["count"] == 1
            assert body["loaded"][0]["id"] == "api-review"
            # 列表可见
            r = c.get("/api/skills")
            skills = r.json()["skills"]
            assert any(sk["id"] == "api-review" for sk in skills), skills
