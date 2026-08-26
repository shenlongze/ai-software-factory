"""tests/console/test_feature_idea_pipeline.py — 想法→细化→待办链路 (v1.1.144)。

Founder: "想法 → 会话中与 AI 讨论 → 细化后进待办 应该是一套逻辑" (1234 不返工)。
覆盖 (service + org.management):
- Feature.maturity: idea|refined 字段 (默认 refined 兼容); 非法 → ValueError
- create_feature(maturity=idea) → to_dict 带 maturity
- update_feature: 改名/描述/maturity (idea↔refined); 非法 maturity → 400 语义
- ensure_story_for_feature: Feature 下无 Story → 自动建; 已有 → 复用第一个
- create_task 绑定 idea Feature 下的 Story → 自动 idea→refined (细化完成)
- Story.feature_id 反向引用落盘 (任务→story→feature 溯源)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "factory-core", _ROOT / "factory-org"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
_service = importlib.import_module("factory-console.service")


def _build_service(root: Path):
    return _adapter.build_console_service(root, event_logger=None)


def _new_project(svc: Any) -> str:
    proj = svc.create_project("想法链路演示", name="Idea Pipeline Demo")
    assert proj is not None and proj.id
    return proj.id


class TestFeatureMaturity:
    def test_feature_model_default_refined(self):
        from org.management import Feature

        f = Feature(id="FEAT-1", name="正式模块")
        assert f.maturity == "refined"

    def test_feature_model_idea_and_invalid(self):
        from org.management import Feature

        assert Feature(id="FEAT-2", name="想法", maturity="idea").maturity == "idea"
        with pytest.raises(ValueError):
            Feature(id="FEAT-3", name="x", maturity="weird")

    def test_create_feature_idea_persists(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="AI 记账", maturity="idea")
        assert feat["maturity"] == "idea"
        got = svc.get_feature(pid, feat["id"])
        assert got["maturity"] == "idea"
        assert got["name"] == "AI 记账"

    def test_update_feature_rename_and_maturity(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="想法模块", maturity="idea")
        updated = svc.update_feature(pid, feat["id"], name="AI 记账", maturity="refined")
        assert updated["name"] == "AI 记账"
        assert updated["maturity"] == "refined"
        with pytest.raises(ValueError):
            svc.update_feature(pid, feat["id"], maturity="bad")
        with pytest.raises(ValueError):
            svc.update_feature(pid, feat["id"])  # 空 patch


class TestEnsureStoryForFeature:
    def test_creates_story_when_none(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="AI 记账", maturity="idea")
        story_id = svc.ensure_story_for_feature(pid, feat["id"])
        assert story_id
        story = next(
            (s for s in (svc.list_backlog(pid) or {}).get("stories", []) if s["id"] == story_id),
            None,
        )
        assert story is not None
        assert story["feature_id"] == feat["id"]  # 反向引用
        # feature.children 引用 story
        got = svc.get_feature(pid, feat["id"])
        assert story_id in got["children"]

    def test_reuses_first_story(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="AI 记账", maturity="idea")
        first = svc.ensure_story_for_feature(pid, feat["id"])
        second = svc.ensure_story_for_feature(pid, feat["id"])
        assert second == first


class TestAutoRefine:
    def test_create_task_under_idea_feature_flips_to_refined(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="AI 记账", maturity="idea")
        story_id = svc.ensure_story_for_feature(pid, feat["id"])
        svc.create_task(pid, title="语音记账", story_id=story_id)
        got = svc.get_feature(pid, feat["id"])
        assert got["maturity"] == "refined", "细化完成 (Feature 下有任务) → 自动转正式"
        # 任务出现在该 feature 下 (story.children)
        story = next(
            (s for s in (svc.list_backlog(pid) or {}).get("stories", []) if s["id"] == story_id),
            None,
        )
        assert story is not None and len(story["children"]) == 1

    def test_refined_feature_stays_refined(self, tmp_path):
        svc = _build_service(tmp_path)
        pid = _new_project(svc)
        feat = svc.create_feature(pid, name="正式模块")  # 默认 refined
        story_id = svc.ensure_story_for_feature(pid, feat["id"])
        svc.create_task(pid, title="任务A", story_id=story_id)
        assert svc.get_feature(pid, feat["id"])["maturity"] == "refined"
