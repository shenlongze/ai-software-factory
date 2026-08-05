"""test_validation_rules.py — 三层规则纯函数测试 (正常 + 异常)。

覆盖: L1 (存在/数据/状态/文件完整 — 正常与异常), L2 (满足/不满足/SKIP), L3 Hook SKIP。
"""

from __future__ import annotations

import json

from tasks.models import TaskStatus

from validation import rules
from validation.models import ValidationStatus

from validation_helpers import (
    create_task, read_task_file, record_created, record_updated, write_raw_task,
)


class TestL1TaskExists:
    def test_pass_when_file_exists(self, task_store):
        create_task(task_store)
        r = rules.rule_task_exists("T-001", task_store.dir / "T-001.json")
        assert r.status is ValidationStatus.PASS
        assert r.id == "L1.task_exists"

    def test_fail_when_missing(self, task_store):
        r = rules.rule_task_exists("T-999", task_store.dir / "T-999.json")
        assert r.status is ValidationStatus.FAIL
        assert "not found" in r.message


class TestL1TaskData:
    def test_pass_valid_json(self, task_store):
        create_task(task_store)
        r = rules.rule_task_data("T-001", read_task_file(task_store.dir, "T-001"))
        assert r.status is ValidationStatus.PASS

    def test_fail_corrupt_json(self, task_store):
        """JSON 无法解析 → FAIL (损坏场景)。"""
        r = rules.rule_task_data("T-001", None, error="Expecting value: line 1 column 1")
        assert r.status is ValidationStatus.FAIL
        assert "不合法" in r.message

    def test_fail_model_invalid(self):
        """JSON 合法但模型校验失败 (id 含路径分隔符)。"""
        data = {"id": "a/b", "title": "x", "project": "p", "status": "BACKLOG"}
        r = rules.rule_task_data("T-001", data)
        assert r.status is ValidationStatus.FAIL

    def test_skip_when_file_missing(self):
        """文件缺失 → SKIP (由 task_exists 规则负责 FAIL)。"""
        r = rules.rule_task_data("T-999", None, error=None)
        assert r.status is ValidationStatus.SKIP


class TestL1TaskStatus:
    def test_pass_valid_status(self):
        r = rules.rule_task_status("T-001", {"status": "DEVELOPMENT"})
        assert r.status is ValidationStatus.PASS

    def test_pass_lowercase_status(self):
        """宽容解析: 小写也合法。"""
        r = rules.rule_task_status("T-001", {"status": "testing"})
        assert r.status is ValidationStatus.PASS

    def test_fail_invalid_status(self):
        r = rules.rule_task_status("T-001", {"status": "BOGUS"})
        assert r.status is ValidationStatus.FAIL

    def test_skip_when_no_data(self):
        r = rules.rule_task_status("T-001", None)
        assert r.status is ValidationStatus.SKIP


class TestL1TaskFiles:
    def test_pass_complete(self, task_store):
        create_task(task_store)
        r = rules.rule_task_files("T-001", read_task_file(task_store.dir, "T-001"))
        assert r.status is ValidationStatus.PASS

    def test_fail_missing_title(self):
        data = {"id": "T-001", "project": "p", "status": "BACKLOG"}
        r = rules.rule_task_files("T-001", data)
        assert r.status is ValidationStatus.FAIL
        assert "title" in r.message

    def test_fail_empty_title(self):
        """必填键存在但为空 → 不完整。"""
        data = {"id": "T-001", "title": "", "project": "p", "status": "BACKLOG"}
        r = rules.rule_task_files("T-001", data)
        assert r.status is ValidationStatus.FAIL

    def test_skip_when_no_data(self):
        r = rules.rule_task_files("T-001", None)
        assert r.status is ValidationStatus.SKIP


class TestL2Workflow:
    def test_pass_history_consistent(self, task_store, logger):
        create_task(task_store)
        record_created(logger)
        task = task_store.get("T-001")
        r = rules.rule_workflow("T-001", task, logger.store.query(task_id="T-001"))
        assert r.status is ValidationStatus.PASS
        assert r.level == "L2"

    def test_pass_after_updated_event(self, task_store, logger):
        """事件历史有 task.updated → DEVELOPMENT, 状态一致 → PASS。"""
        create_task(task_store)
        record_created(logger)
        record_updated(logger, to="DEVELOPMENT")
        task = task_store.update_status("T-001", TaskStatus.DEVELOPMENT)
        r = rules.rule_workflow("T-001", task, logger.store.query(task_id="T-001"))
        assert r.status is ValidationStatus.PASS

    def test_fail_status_advanced_without_event(self, task_store, logger):
        """状态 DEVELOPMENT 但事件历史停在 BACKLOG (无 task.updated) → FAIL。"""
        create_task(task_store)
        record_created(logger)
        task = task_store.update_status("T-001", TaskStatus.DEVELOPMENT)
        r = rules.rule_workflow("T-001", task, logger.store.query(task_id="T-001"))
        assert r.status is ValidationStatus.FAIL
        assert "不一致" in r.message

    def test_fail_no_status_events(self, task_store):
        """有 workflow 定义但事件历史无状态记录 → FAIL。"""
        task = create_task(task_store)
        r = rules.rule_workflow("T-001", task, [])
        assert r.status is ValidationStatus.FAIL
        assert "无状态记录" in r.message

    def test_skip_no_workflow_definition(self, task_store):
        """无 workflow 定义 → SKIP (父任务约定)。"""
        task = create_task(task_store, workflow=None)
        r = rules.rule_workflow("T-001", task, [])
        assert r.status is ValidationStatus.SKIP
        assert "workflow" in r.message

    def test_skip_no_task(self):
        """任务不可用 (文件缺失/损坏) → SKIP。"""
        r = rules.rule_workflow("T-001", None, [])
        assert r.status is ValidationStatus.SKIP


class TestExpectStatus:
    def test_pass_when_matches(self, task_store):
        task = create_task(task_store)
        r = rules.rule_expect_status("T-001", task, TaskStatus.BACKLOG)
        assert r.status is ValidationStatus.PASS

    def test_fail_when_mismatch(self, task_store):
        task = create_task(task_store)
        r = rules.rule_expect_status("T-001", task, TaskStatus.DONE)
        assert r.status is ValidationStatus.FAIL
        assert "期望状态" in r.message

    def test_skip_when_not_requested(self, task_store):
        task = create_task(task_store)
        r = rules.rule_expect_status("T-001", task, None)
        assert r.status is ValidationStatus.SKIP

    def test_skip_no_task(self):
        r = rules.rule_expect_status("T-001", None, TaskStatus.DONE)
        assert r.status is ValidationStatus.SKIP


class TestL3Artifact:
    def test_hook_placeholder_skip(self):
        """L3 Hook 占位 → SKIP (预留 Flutter/Java/Python 验证器)。"""
        r = rules.rule_artifact("T-001")
        assert r.status is ValidationStatus.SKIP
        assert r.level == "L3"
        assert r.id == "L3.artifact"


class TestLoadTaskFile:
    def test_load_valid(self, task_store):
        create_task(task_store)
        data, task, error = rules.load_task_file("T-001", task_store.dir)
        assert data["id"] == "T-001"
        assert task is not None and task.title == "实现撤销/重做"
        assert error is None

    def test_load_missing(self, task_store):
        data, task, error = rules.load_task_file("T-999", task_store.dir)
        assert data is None and task is None and error is None

    def test_load_corrupt(self, task_store):
        write_raw_task(task_store.dir, "T-001", "{broken json")
        data, task, error = rules.load_task_file("T-001", task_store.dir)
        assert data is None and task is None
        assert error is not None

    def test_load_model_invalid(self, task_store):
        """模型校验失败: 保留原始 data 供细粒度规则诊断, task=None + error 非空。"""
        write_raw_task(task_store.dir, "T-001",
                       json.dumps({"id": "a/b", "title": "x", "project": "p", "status": "BACKLOG"}))
        data, task, error = rules.load_task_file("T-001", task_store.dir)
        assert data is not None and data["id"] == "a/b"
        assert task is None
        assert error is not None
