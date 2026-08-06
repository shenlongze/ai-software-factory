"""tests/product/test_product_store.py — ProductStore: 独立空间 / 原子写 / 损坏失败 (Phase 9A, ADR-0026)。

覆盖: 四文件多节布局 (ideas/artifacts/approvals/workflows)、目录首次写自动创建、
upsert 覆盖、按 id 排序、跨实例 round-trip、损坏文件 (JSON 解析失败 / 结构不符 /
模型校验失败) → CorruptProductStoreError 响亮失败 (绝不静默空)、原子写无临时残留。
"""

from __future__ import annotations

import json

import pytest

from product.models import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalRequest,
    Artifact,
    ProductIdea,
    ProductWorkflow,
)
from product.store import CorruptProductStoreError, ProductStore


class TestLayoutAndBasics:
    def test_dir_created_on_first_write(self, product_dir):
        assert not product_dir.exists()
        store = ProductStore(product_dir)
        store.save_idea(ProductIdea(id="PI-001", title="t"))
        assert product_dir.is_dir()
        assert (product_dir / "ideas.json").exists()

    def test_idea_save_get_roundtrip(self, store):
        store.save_idea(ProductIdea(id="PI-001", title="AI 助手", description="d"))
        got = store.get_idea("PI-001")
        assert got is not None
        assert got.title == "AI 助手"
        assert got.description == "d"
        # 逐字段比较 (created_at 默认时间戳 round-trip 陷阱: 新构造对象时间不同)
        assert got.id == "PI-001"

    def test_idea_upsert_overwrites(self, store):
        store.save_idea(ProductIdea(id="PI-001", title="v1"))
        store.save_idea(ProductIdea(id="PI-001", title="v2"))
        assert store.get_idea("PI-001").title == "v2"
        assert len(store.list_ideas()) == 1

    def test_list_ideas_sorted_by_id(self, store):
        store.save_idea(ProductIdea(id="PI-003", title="c"))
        store.save_idea(ProductIdea(id="PI-001", title="a"))
        store.save_idea(ProductIdea(id="PI-002", title="b"))
        assert [i.id for i in store.list_ideas()] == ["PI-001", "PI-002", "PI-003"]

    def test_missing_get_returns_none(self, store):
        assert store.get_idea("PI-999") is None
        assert store.get_artifact("ART-999") is None
        assert store.get_workflow("PW-999") is None


class TestArtifacts:
    def test_artifact_save_get_list(self, store):
        store.save_artifact(Artifact(id="ART-001", type="prd"))
        store.save_artifact(Artifact(id="ART-002", type="ui"))
        got = store.get_artifact("ART-001")
        assert got is not None and got.type == "prd"
        assert [a.id for a in store.list_artifacts()] == ["ART-001", "ART-002"]

    def test_list_artifacts_by_type(self, store):
        store.save_artifact(Artifact(id="ART-001", type="prd"))
        store.save_artifact(Artifact(id="ART-002", type="prd"))
        store.save_artifact(Artifact(id="ART-003", type="ui"))
        assert [a.id for a in store.list_artifacts_by_type("prd")] == ["ART-001", "ART-002"]
        assert [a.id for a in store.list_artifacts_by_type("ui")] == ["ART-003"]

    def test_artifact_lineage_roundtrip(self, store):
        store.save_artifact(Artifact(
            id="ART-009", type="product_decision",
            provider_id="hermes", source_events=["ev-9"], version=2, confidence=0.7,
        ))
        got = store.get_artifact("ART-009")
        assert got.provider_id == "hermes"
        assert got.source_events == ["ev-9"]
        assert got.version == 2
        assert got.confidence == 0.7


class TestApprovals:
    def test_gate_save_get_list(self, store):
        store.save_gate(ApprovalGate(id="prd", artifact_type="prd", required="mandatory"))
        store.save_gate(ApprovalGate(id="ui", artifact_type="ui"))
        assert store.get_gate("prd").required == "mandatory"
        assert [g.id for g in store.list_gates()] == ["prd", "ui"]

    def test_request_save_get(self, store):
        store.save_request(ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd"))
        got = store.get_request("APR-001")
        assert got is not None
        assert got.status == "pending"

    def test_list_pending_requests(self, store):
        store.save_request(ApprovalRequest(id="APR-001", artifact_id="ART-001", gate="prd"))
        store.save_request(ApprovalRequest(
            id="APR-002", artifact_id="ART-002", gate="ui", status="approved",
        ))
        pending = store.list_pending_requests()
        assert [r.id for r in pending] == ["APR-001"]

    def test_decision_save_get(self, store):
        store.save_decision(ApprovalDecision(id="APD-001", request_id="APR-001"))
        got = store.get_decision("APD-001")
        assert got is not None and got.request_id == "APR-001"


class TestWorkflows:
    def test_workflow_save_get(self, store):
        store.save_workflow(ProductWorkflow(
            id="PW-001", idea_id="PI-001", stages=["research"], current_stage="research",
        ))
        got = store.get_workflow("PW-001")
        assert got is not None
        assert got.current_stage == "research"

    def test_get_workflow_by_idea(self, store):
        store.save_workflow(ProductWorkflow(id="PW-001", idea_id="PI-001"))
        wf = store.get_workflow_by_idea("PI-001")
        assert wf is not None and wf.id == "PW-001"

    def test_get_workflow_by_idea_missing(self, store):
        assert store.get_workflow_by_idea("PI-999") is None


class TestRoundtripAcrossInstances:
    def test_reload_reads_written_data(self, product_dir):
        s1 = ProductStore(product_dir)
        s1.save_idea(ProductIdea(id="PI-001", title="t"))
        s1.save_artifact(Artifact(id="ART-001", type="prd"))
        s2 = ProductStore(product_dir)
        assert s2.get_idea("PI-001").title == "t"
        assert s2.get_artifact("ART-001").type == "prd"

    def test_files_are_utf8_json_with_ensure_ascii_false(self, product_dir):
        s = ProductStore(product_dir)
        s.save_idea(ProductIdea(id="PI-001", title="AI 助手"))
        raw = (product_dir / "ideas.json").read_text(encoding="utf-8")
        assert "AI 助手" in raw  # ensure_ascii=False: 中文原文落盘

    def test_atomic_write_no_tmp_leftover(self, product_dir):
        s = ProductStore(product_dir)
        s.save_idea(ProductIdea(id="PI-001", title="t"))
        leftovers = [p.name for p in product_dir.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []


class TestCorruption:
    @pytest.fixture(autouse=True)
    def _mkdir_for_corruption(self, product_dir):
        """损坏检测只对真实存在的文件生效 — 父目录须先建 (backend-developer 陷阱)。

        只放本类内 (共享/模块级 autouse 会破坏 test_dir_created_on_first_write
        的 `assert not product_dir.exists()` 逆断言 — Phase 8B-2 同款教训)。
        """
        product_dir.mkdir(parents=True, exist_ok=True)
        yield

    def test_invalid_json_raises(self, product_dir):
        (product_dir / "ideas.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(CorruptProductStoreError):
            ProductStore(product_dir).list_ideas()

    def test_non_object_root_raises(self, product_dir):
        (product_dir / "ideas.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(CorruptProductStoreError):
            ProductStore(product_dir).list_ideas()

    def test_missing_section_raises(self, product_dir):
        (product_dir / "approvals.json").write_text(
            json.dumps({"gates": {}, "requests": {}}), encoding="utf-8"
        )  # 缺 decisions 节
        with pytest.raises(CorruptProductStoreError):
            ProductStore(product_dir).list_decisions()

    def test_model_validation_failure_raises(self, product_dir):
        (product_dir / "ideas.json").write_text(
            json.dumps({"ideas": {"PI-001": {"title": "no id field"}}}), encoding="utf-8"
        )
        with pytest.raises(CorruptProductStoreError):
            ProductStore(product_dir).list_ideas()

    def test_corrupt_other_file_isolated(self, product_dir):
        # ideas.json 完好, artifacts.json 损坏 — 互不影响
        s = ProductStore(product_dir)
        s.save_idea(ProductIdea(id="PI-001", title="t"))
        (product_dir / "artifacts.json").write_text("garbage", encoding="utf-8")
        assert s.get_idea("PI-001").title == "t"
        with pytest.raises(CorruptProductStoreError):
            s.list_artifacts()
