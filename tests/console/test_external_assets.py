"""tests/console/test_external_assets.py — M2 宿主资产发现与导入。

设计依据: 设计文档 §4.3 + Founder (标签/冲突/分组)。
覆盖:
- scan_adapter_assets: agents (toml/md-frontmatter) / skills (SKILL.md 复用 U-4) /
  plugins (catalog) / persona
- import_assets: agent → agents.json (命名空间 + source/kind/role/tags/host);
  skill → skills.json (命名空间前缀 + instructions); plugin/persona → catalog
- 冲突: 幂等刷新 / 手工同 ID 跳过保留
- HTTP: GET /{id}/assets + POST /{id}/import
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

_host = importlib.import_module("factory-console.external_executor.host_assets")
_schema = importlib.import_module("factory-console.external_executor.schema")
_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi 未安装")


def _adapter_with_assets(tmp_path: Path, *, kind: str = "codex"):
    agents_dir = tmp_path / "agents"
    skills_dir = tmp_path / "skills"
    agents_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)
    # toml agent (codex 风格)
    (agents_dir / "arch.toml").write_text(
        'name = "architecture-examiner"\ndescription = "架构审查"\ndeveloper_instructions = "你严格审查架构"',
        encoding="utf-8",
    )
    # skill
    (skills_dir / "review-skill" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skills_dir / "review-skill" / "SKILL.md").write_text(
        "---\nid: review-skill\nname: 审查技能\ndescription: 审查规范\n---\n按审查清单做事",
        encoding="utf-8",
    )
    # plugin dir
    (tmp_path / "plugins" / "openai-bundled").mkdir(parents=True, exist_ok=True)
    spec = {
        "id": kind, "name": "Test", "binary": "t",
        "invocation": {"non_interactive": ["{prompt}"], "project_dir": "cwd"},
        "host_assets": {
            "agents": {"dir": str(agents_dir), "glob": "*", "format": "toml",
                       "fields": {"name": "name", "description": "description",
                                  "prompt": "developer_instructions"}},
            "skills": {"dir": str(skills_dir), "glob": "*", "format": "skill-md"},
            "plugins": {"dir": str(tmp_path / "plugins"), "glob": "*", "format": "dirs"},
        },
    }
    return _schema.ExternalExecutorAdapter(**spec)


class TestScan:
    def test_scan_agents_skills_plugins(self, tmp_path):
        adapter = _adapter_with_assets(tmp_path)
        assets = _host.scan_adapter_assets(adapter)
        kinds = {a["kind"] for a in assets}
        assert {"agent", "skill", "plugin"} <= kinds
        agents = [a for a in assets if a["kind"] == "agent"]
        names = {a["name"] for a in agents}
        assert names >= {"architecture-examiner"}
        # 命名空间 + 角色
        arch = next(a for a in agents if a["name"] == "architecture-examiner")
        assert arch["id"] == "codex.architecture-examiner"
        assert arch["role"] == "architect"
        assert arch["source"] == "codex"
        # skill 复用 U-4 解析 + 命名空间
        skill = next(a for a in assets if a["kind"] == "skill")
        assert skill["id"] == "codex.review-skill"
        assert "审查清单" in skill["instructions"]


    def test_scan_md_frontmatter_agent(self, tmp_path):
        """claude 风格: md-frontmatter (--- yaml --- + body)。"""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "ux.md").write_text(
            '---\nname: ux-examiner\ndescription: UX 审查\ntools: Read\nmodel: sonnet\n---\n你审查 UX',
            encoding="utf-8",
        )
        spec = {
            "id": "claude", "name": "Claude", "binary": "c",
            "invocation": {"non_interactive": ["-p", "{prompt}"], "project_dir": "cwd"},
            "host_assets": {"agents": {"dir": str(agents_dir), "glob": "*.md", "format": "md-frontmatter",
                                       "fields": {"name": "name", "description": "description", "prompt": "body"}}},
        }
        adapter = _schema.ExternalExecutorAdapter(**spec)
        assets = _host.scan_adapter_assets(adapter)
        ux = next(a for a in assets if a["kind"] == "agent" and a["name"] == "ux-examiner")
        assert ux["id"] == "claude.ux-examiner"
        assert ux["role"] == "designer"
        assert "你审查 UX" in ux["prompt"]


class TestImport:
    def _import(self, tmp_path):
        adapter = _adapter_with_assets(tmp_path)
        assets = _host.scan_adapter_assets(adapter)
        agents_file = tmp_path / "out" / "agents.json"
        skills_file = tmp_path / "out" / "skills.json"
        r = _host.import_assets(adapter, assets, agents_file=agents_file, skills_file=skills_file)
        return r, agents_file, skills_file

    def test_import_agents_and_skills(self, tmp_path):
        r, agents_file, skills_file = self._import(tmp_path)
        assert "codex.architecture-examiner" in r["imported_agents"]
        assert "codex.review-skill" in r["imported_skills"]
        assert any(c["kind"] == "plugin" for c in r["catalog"])
        agents = json.loads(agents_file.read_text(encoding="utf-8"))["agents"]
        arch = agents["codex.architecture-examiner"]
        assert arch["source"] == "codex" and arch["kind"] == "agent"
        assert arch["role"] == "architect" and arch["host"]["file"].endswith("arch.toml")
        skills = json.loads(skills_file.read_text(encoding="utf-8"))["skills"]
        assert skills["codex.review-skill"]["instructions"].startswith("按审查清单")

    def test_import_idempotent_and_manual_conflict(self, tmp_path):
        r, agents_file, skills_file = self._import(tmp_path)
        # 幂等: 重复导入 → 刷新不重复
        adapter = _adapter_with_assets(tmp_path)
        assets = _host.scan_adapter_assets(adapter)
        r2 = _host.import_assets(adapter, assets, agents_file=agents_file, skills_file=skills_file)
        assert len(r2["imported_agents"]) == len(r["imported_agents"])  # 不重复
        # 手工同 ID (无 source) → 跳过保留
        agents = json.loads(agents_file.read_text(encoding="utf-8"))["agents"]
        agents["codex.architecture-examiner"] = {"id": "codex.architecture-examiner", "name": "手工版", "role": "x"}
        json.dump({"agents": agents}, open(agents_file, "w", encoding="utf-8"))
        r3 = _host.import_assets(adapter, assets, agents_file=agents_file, skills_file=skills_file)
        assert "codex.architecture-examiner" in r3["skipped"]
        agents = json.loads(agents_file.read_text(encoding="utf-8"))["agents"]
        assert agents["codex.architecture-examiner"]["name"] == "手工版"  # 保留手工


@requires_fastapi
class TestAssetsHttp:
    def _app(self, tmp_path):
        service = _adapter.build_console_service(tmp_path, event_logger=None)
        return _adapter.build_app(service, event_logger=None, factory_root=tmp_path)

    def test_assets_and_import_endpoints(self, tmp_path):
        # 用真实 hermes (121 skills) 太重 → 用自定义适配器 + 临时目录
        from factory_console.external_executor.registry import build_registry

        adapter = _adapter_with_assets(tmp_path)
        reg = build_registry(tmp_path)
        reg.save(adapter)
        with TestClient(self._app(tmp_path)) as c:
            r = c.get("/api/external-ai/codex/assets")
            assert r.status_code == 200, r.text
            assert r.json()["count"] >= 3
            r = c.post("/api/external-ai/codex/import", json={})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["imported"] >= 2
