"""test_s10_084_pipeline.py — Product Intelligence Pipeline (S10-084 P0)。

覆盖:
P0-A ArtifactRegistry: 版本化落盘 (write/latest/list, v+1 递增, 旧版本保留)
P0-B ProductPipeline: 7 角色资产链 (PM/Market/Competitive/UX/Architect/QA/PRD)
P0-C 重跑 → 版本递增 (v1 → v2)
P0-D discovery.md 落盘 ("整理需求不创建" → 资产, 不创建项目)
P0-E intent/route: "让PM分析" → product_pipeline
basename 全仓库唯一 (test_s10_0XX_* 前缀)。
"""

from __future__ import annotations

from pathlib import Path

from importlib import import_module

import pytest

ACT = import_module("factory-console.session.actions")
ART = import_module("factory-console.session.artifact_registry")
CTX = import_module("factory-console.session.context")
INT = import_module("factory-console.session.intent")
PIPE = import_module("factory-console.session.pipeline_runner")
PROD = import_module("factory-console.session.product")
SESS = import_module("factory-console.session.session")
CONV_MOD = import_module("factory-console.session.conversation")


class FakeOrgCli:
    def __init__(self):
        self.calls = []

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        return {
            "ok": True,
            "project": {"id": "p1", "name": args.name, "slug": "todo"},
            "exit_code": 0,
        }


def _product(**kw):
    data = dict(
        name="Todo管理",
        problem="手动测试太慢",
        user="想学后端的开发者",
        core_features=["增删改查", "列表", "认证"],
        raw="我想开发一个 Todo 管理 API，目标是学习后端开发。",
    )
    data.update(kw)
    return PROD.ProductIntent(**data)


# ---------------------------------------------------------------- P0-A/B/C Artifact + Pipeline

class TestArtifactRegistry:
    def test_write_latest_version_increment(self, tmp_path):
        reg = ART.ArtifactRegistry(tmp_path, "todo")
        r1 = reg.write("prd", "# PRD v1", created_by="pm")
        assert r1.version == 1
        assert r1.status == "draft"
        assert r1.content_ref.endswith("artifacts/prd/v1/artifact.md")
        assert (tmp_path / "projects" / "todo" / "artifacts" / "prd" / "v1" / "artifact.md").is_file()
        assert (tmp_path / "projects" / "todo" / "artifacts" / "prd" / "v1" / "artifact.json").is_file()
        # 重写 → v2, 旧版本保留
        r2 = reg.write("prd", "# PRD v2", created_by="pm", parent_event_id="ev-1")
        assert r2.version == 2
        assert r2.parent_event_id == "ev-1"
        assert reg.latest("prd").version == 2
        records = reg.list()
        assert [r.version for r in records] == [1, 2]
        assert (tmp_path / "projects" / "todo" / "artifacts" / "prd" / "v1" / "artifact.md").is_file()

    def test_write_empty_type_raises(self, tmp_path):
        reg = ART.ArtifactRegistry(tmp_path, "todo")
        with pytest.raises(ValueError):
            reg.write("", "x")


class TestProductPipeline:
    def test_run_creates_seven_artifacts(self, tmp_path):
        pipeline = PIPE.ProductPipeline(tmp_path, "todo")
        result = pipeline.run(_product(), source="conv-1")
        assert result.project == "todo"
        types = [r.type for r in result.records]
        assert types == ["product", "market_analysis", "competitive_analysis",
                         "ux_flow", "architecture", "test_plan", "prd"]
        for r in result.records:
            assert r.version == 1
            assert r.status == "draft"
            # M2 契约: created_by 一律 agent_id (agt- 前缀, 非 role 字符串)
            assert r.created_by.startswith("agt-")
            # 内容非空 (deterministic 兜底)
            md_path = Path(r.content_ref)
            assert md_path.is_file()
            assert md_path.read_text(encoding="utf-8").strip()
        # M2 契约: parent_artifact 血缘互引 (每资产指向上一资产)
        for i, r in enumerate(result.records):
            expected_parent = result.records[i - 1].id if i > 0 else ""
            assert (r.metadata or {}).get("parent_artifact") == expected_parent, (
                r.type,
                (r.metadata or {}).get("parent_artifact"),
                expected_parent,
            )
        assert "7 个资产" in result.summary

    def test_rerun_bumps_versions(self, tmp_path):
        pipeline = PIPE.ProductPipeline(tmp_path, "todo")
        pipeline.run(_product())
        result = pipeline.run(_product())
        assert all(r.version == 2 for r in result.records)

    def test_llm_failure_falls_back_to_deterministic(self, tmp_path):
        def boom(prompt, role):
            raise RuntimeError("llm down")
        pipeline = PIPE.ProductPipeline(tmp_path, "todo", llm_fn=boom)
        result = pipeline.run(_product())
        assert len(result.records) == 7
        assert all(Path(r.content_ref).read_text(encoding="utf-8").strip() for r in result.records)


class TestPipelineActionAndIntent:
    def test_intent_parses_to_pipeline(self):
        p = INT.KeywordIntentParser()
        for text in ("让PM分析", "产品管线", "跑产品管线", "让产品经理分析"):
            r = p.parse(text)
            assert r is not None, text
            assert r.intent_type == INT.INTENT_PRODUCT_PIPELINE, f"{text} → {r.intent_type}"
        # 不与既有意图冲突
        assert p.parse("产品分析").intent_type == INT.INTENT_PRODUCT_INTELLIGENCE
        assert p.parse("我想做CRM").intent_type == INT.INTENT_CREATE_PRODUCT

    def test_action_product_pipeline(self, monkeypatch, capsys, tmp_path):
        org = FakeOrgCli()
        monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
        root = tmp_path / "ws"
        root.mkdir()
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(root)),
            # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
            conversation_manager=CONV_MOD.ConversationManager(analyzer=None),
        )
        sess._dispatch("我想开发一个 Todo 管理 API，目标是学习后端开发。")
        sess._dispatch("手动测试太慢")
        sess._dispatch("想学后端的开发者")
        sess._dispatch("增删改查、列表、认证")
        sess._dispatch("y")
        capsys.readouterr()
        sess._dispatch("让PM分析")
        out = capsys.readouterr().out
        assert "产品管线完成" in out
        assert "7 个资产" in out
        # 资产落盘
        artifact_dirs = list((root / "projects" / "todo" / "artifacts").glob("*"))
        assert len(artifact_dirs) == 7


class TestDiscoveryArtifact:
    def test_summary_only_writes_discovery_artifact(self, monkeypatch, capsys, tmp_path):
        org = FakeOrgCli()
        monkeypatch.setattr(ACT, "_load_org_cli", lambda: org)
        root = tmp_path / "ws"
        root.mkdir()
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(root)),
            # 确定性测试模式: 发现流程禁用 LLM (不依赖真实 LLM/网络)
            conversation_manager=CONV_MOD.ConversationManager(analyzer=None),
        )
        sess._dispatch("我想开发一个记账软件")
        sess._dispatch("记账麻烦")
        sess._dispatch("个人用户")
        sess._dispatch("先帮我整理需求，不要创建项目。")
        out = capsys.readouterr().out
        assert "未创建任何项目" in out
        # 不创建项目 (org 无调用)
        assert org.calls == []
        # discovery 资产落盘 (draft)
        discovery = list((root / "projects").glob("*/artifacts/discovery/v1/artifact.md"))
        assert discovery, "discovery.md 未落盘"
        content = discovery[0].read_text(encoding="utf-8")
        assert "需求整理" in content
        assert "记账麻烦" in content
        assert "draft" in content
