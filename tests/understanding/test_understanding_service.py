"""tests/understanding/test_understanding_service.py — UnderstandingService 编排 (Phase 7, ADR-0021)。

覆盖: 完整 analyze 流程 (基本信息 → 文档检测 → 产物检测 → 阶段识别 → 缺失 →
建议) / 空项目 / 新项目 / 已有代码项目 / 文档完整项目 / 多项目各自报告 /
路径无效 → UnderstandingError + failed 事件 / 内部异常 → failed 后原样上抛 /
事件序列 (started → completed | failed, source="understanding") / logger=None
静默 (零事件) / 只读铁律 (分析前后项目目录逐字节相同)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from events.models import EventType
from understanding.service import UnderstandingError, UnderstandingService

from understanding_helpers import (
    code_project,
    code_test_project,
    complete_project,
    docs_complete_project,
    empty_project,
    make_project,
    ops_project,
    prd_project,
    readme_project,
    research_project,
    snapshot_tree,
)


def analyze(tmp_path: Path, builder, *, logger=None):
    root = builder(tmp_path / "proj")
    service = UnderstandingService(logger=logger)
    return root, service.analyze(str(root))


class TestAnalyzeFullReport:
    def test_empty_project_report(self, tmp_path):
        root, r = analyze(tmp_path, empty_project)
        assert r.path == str(root)
        assert r.basic_info.type == "empty"
        assert r.basic_info.status == "empty"
        assert r.basic_info.file_count == 0
        assert r.stage.stage == "IDEA"
        assert r.stage.confidence == 0.9
        assert r.missing.missing == [
            "PRD", "UI_DESIGN", "ARCHITECTURE", "SOURCE_CODE",
            "TEST", "DEPLOYMENT", "OPERATION",
        ]
        assert len(r.next_actions) == 7
        assert len(r.artifacts) == 7

    def test_new_project_readme(self, tmp_path):
        root, r = analyze(tmp_path, readme_project)
        assert r.basic_info.type == "documentation"
        assert r.basic_info.status == "planning"
        assert r.basic_info.scale == "tiny"
        assert r.basic_info.file_count == 1
        assert r.stage.stage == "PRD"
        assert r.missing.present == []
        assert r.missing.missing == [
            "PRD", "UI_DESIGN", "ARCHITECTURE", "SOURCE_CODE",
            "TEST", "DEPLOYMENT", "OPERATION",
        ]

    def test_code_project(self, tmp_path):
        root, r = analyze(tmp_path, code_project)
        assert r.basic_info.type == "application"
        assert r.basic_info.status == "in_development"
        assert r.basic_info.languages == ["python"]
        assert r.stage.stage == "DEVELOPMENT"
        assert r.missing.present == ["SOURCE_CODE"]
        assert len(r.next_actions) == 7  # 6 缺失 + validation 追加

    def test_code_test_project(self, tmp_path):
        root, r = analyze(tmp_path, code_test_project)
        assert r.basic_info.status == "developed"
        assert r.stage.stage == "TESTING"
        assert r.missing.present == ["SOURCE_CODE", "TEST"]

    def test_docs_complete_project(self, tmp_path):
        root, r = analyze(tmp_path, docs_complete_project)
        assert r.basic_info.type == "documentation"
        assert r.basic_info.status == "planning"
        assert r.stage.stage == "ARCHITECTURE"
        assert r.missing.present == ["PRD", "UI_DESIGN", "ARCHITECTURE"]

    def test_production_boundary(self, tmp_path):
        from understanding_helpers import prod_project

        root, r = analyze(tmp_path, prod_project)
        assert r.basic_info.status == "deployable"
        assert r.stage.stage == "PRODUCTION"
        assert r.missing.present == ["SOURCE_CODE", "TEST", "DEPLOYMENT"]

    def test_full_operational_project(self, tmp_path):
        root, r = analyze(tmp_path, complete_project)
        assert r.basic_info.type == "service"  # application + 部署 → service
        assert r.basic_info.status == "operational"
        assert r.stage.stage == "OPERATION"
        assert r.missing.present == [
            "PRD", "UI_DESIGN", "ARCHITECTURE", "SOURCE_CODE",
            "TEST", "DEPLOYMENT", "OPERATION",
        ]
        assert r.missing.missing == []
        assert r.next_actions == []

    def test_ops_project_status_operational(self, tmp_path):
        # 4 类 code 产物 (源码+测试+部署+运维) 即 operational — 无需产品文档
        root, r = analyze(tmp_path, ops_project)
        assert r.basic_info.status == "operational"
        assert r.stage.stage == "OPERATION"
        assert r.missing.present == ["SOURCE_CODE", "TEST", "DEPLOYMENT", "OPERATION"]
        assert r.missing.missing == ["PRD", "UI_DESIGN", "ARCHITECTURE"]

    def test_research_project(self, tmp_path):
        root, r = analyze(tmp_path, research_project)
        assert r.stage.stage == "RESEARCH"
        assert r.basic_info.status == "planning"

    def test_report_generated_at_utc_timestamp(self, tmp_path):
        root, r = analyze(tmp_path, empty_project)
        assert r.generated_at.endswith("Z")
        assert "T" in r.generated_at

    def test_path_object_accepted(self, tmp_path):
        root = code_project(tmp_path / "proj")
        service = UnderstandingService()
        r = service.analyze(root)  # Path 而非 str
        assert r.path == str(root)


class TestMultipleProjects:
    def test_each_project_gets_own_report(self, tmp_path):
        # 多项目: 各自分析互不影响, 报告 path/stage 独立
        empty = empty_project(tmp_path / "a-empty")
        docs = docs_complete_project(tmp_path / "b-docs")
        code = code_test_project(tmp_path / "c-code")
        service = UnderstandingService()
        ra = service.analyze(str(empty))
        rb = service.analyze(str(docs))
        rc = service.analyze(str(code))
        assert ra.stage.stage == "IDEA"
        assert rb.stage.stage == "ARCHITECTURE"
        assert rc.stage.stage == "TESTING"
        assert ra.path != rb.path != rc.path
        # 各自 artifacts 独立 (a 全缺失, c 含源码+测试)
        assert "SOURCE_CODE" in rc.missing.present
        assert "SOURCE_CODE" not in ra.missing.present
        assert rc.missing.missing == [
            "PRD", "UI_DESIGN", "ARCHITECTURE", "DEPLOYMENT", "OPERATION",
        ]


class TestErrors:
    def test_missing_path_raises(self, tmp_path):
        service = UnderstandingService()
        with pytest.raises(UnderstandingError, match="path not found"):
            service.analyze(str(tmp_path / "nope"))

    def test_file_path_raises_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x", encoding="utf-8")
        service = UnderstandingService()
        with pytest.raises(UnderstandingError, match="not a directory"):
            service.analyze(str(f))

    def test_internal_error_reraises(self, tmp_path, monkeypatch):
        root = empty_project(tmp_path / "p")
        service = UnderstandingService()
        monkeypatch.setattr(
            "understanding.service.collect_files",
            lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with pytest.raises(RuntimeError, match="boom"):
            service.analyze(str(root))


class TestEvents:
    def test_success_events_started_then_completed(self, tmp_path, logger, event_store):
        root, r = analyze(tmp_path, code_project, logger=logger)
        types = [e.type.value for e in event_store.query()]
        assert types[0] == "understanding.started"
        assert types[1] == "understanding.completed"

    def test_completed_payload_contract(self, tmp_path, logger, event_store):
        root, r = analyze(tmp_path, code_project, logger=logger)
        evs = [e for e in event_store.query()
               if e.type == EventType.UNDERSTANDING_COMPLETED]
        assert len(evs) == 1
        payload = evs[0].payload
        assert payload["path"] == str(root)
        assert payload["stage"] == "DEVELOPMENT"
        assert payload["confidence"] == 0.6
        assert payload["artifacts"] == ["SOURCE_CODE"]
        assert "PRD" in payload["missing"]

    def test_started_payload(self, tmp_path, logger, event_store):
        root, r = analyze(tmp_path, empty_project, logger=logger)
        evs = [e for e in event_store.query()
               if e.type == EventType.UNDERSTANDING_STARTED]
        assert evs[0].payload == {"path": str(root)}
        assert evs[0].source == "understanding"

    def test_failed_event_on_missing_path(self, tmp_path, logger, event_store):
        service = UnderstandingService(logger=logger)
        with pytest.raises(UnderstandingError):
            service.analyze(str(tmp_path / "nope"))
        evs = [e for e in event_store.query()
               if e.type == EventType.UNDERSTANDING_FAILED]
        assert len(evs) == 1
        assert evs[0].result == "ERROR"
        assert "path not found" in evs[0].payload["error"]

    def test_failed_event_on_internal_error(self, tmp_path, logger, event_store, monkeypatch):
        root = empty_project(tmp_path / "p")
        service = UnderstandingService(logger=logger)
        monkeypatch.setattr(
            "understanding.service.collect_files",
            lambda p: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        with pytest.raises(RuntimeError):
            service.analyze(str(root))
        evs = [e for e in event_store.query()
               if e.type == EventType.UNDERSTANDING_FAILED]
        assert len(evs) == 1
        assert "boom" in evs[0].payload["error"]

    def test_no_logger_no_events(self, tmp_path):
        root, r = analyze(tmp_path, code_project, logger=None)
        assert r.stage.stage == "DEVELOPMENT"  # 分析照常完成


class TestReadOnly:
    def test_analysis_does_not_modify_files(self, tmp_path):
        # 只读铁律: 分析前后项目目录逐字节相同 (含内容与文件集合)
        root = ops_project(tmp_path / "proj")
        before = snapshot_tree(root)
        service = UnderstandingService()
        service.analyze(str(root))
        service.analyze(str(root))  # 二次分析仍零写入
        assert snapshot_tree(root) == before

    def test_analysis_of_empty_dir_read_only(self, tmp_path):
        root = empty_project(tmp_path / "proj")
        before = snapshot_tree(root)
        UnderstandingService().analyze(str(root))
        assert snapshot_tree(root) == before
        assert list(root.iterdir()) == []  # 无新建文件/目录
