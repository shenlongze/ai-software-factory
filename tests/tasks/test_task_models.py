"""test_models.py — Task 模型 (phase2-status: Pydantic Task + 五状态)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tasks.models import Task, TaskStatus
from task_helpers import make_task


class TestDefaults:
    def test_defaults(self):
        t = Task(id="T-001", title="hello")
        assert t.id == "T-001"
        assert t.title == "hello"
        assert t.project == "default"
        assert t.type == "feature"
        assert t.status is TaskStatus.BACKLOG
        assert t.owner is None
        assert t.workflow == "feature-delivery"
        assert isinstance(t.created_at, datetime) and t.created_at.tzinfo is not None
        assert isinstance(t.updated_at, datetime) and t.updated_at.tzinfo is not None

    def test_five_statuses_roundtrip(self):
        """五状态枚举全部可构造、可序列化。"""
        for s in TaskStatus:
            t = Task(id="T-1", title="x", status=s)
            assert t.status is s
            loaded = Task.model_validate(t.to_dict())
            assert loaded.status is s

    def test_status_case_insensitive(self):
        t = Task(id="T-1", title="x", status="development")
        assert t.status is TaskStatus.DEVELOPMENT
        assert TaskStatus.parse("  done  ") is TaskStatus.DONE

    def test_status_parse_rejects_invalid(self):
        with pytest.raises(ValueError, match="invalid task status"):
            TaskStatus.parse("bogus")
        with pytest.raises(ValidationError):
            Task(id="T-1", title="x", status="bogus")

    def test_to_dict_json_safe(self):
        d = make_task().to_dict()
        assert d["status"] == "BACKLOG"
        assert isinstance(d["created_at"], str)


class TestIdValidation:
    @pytest.mark.parametrize("bad", ["", "  ", ".", "..", "a/b", "a\\b"])
    def test_invalid_id_rejected(self, bad):
        with pytest.raises(ValidationError, match="invalid task id"):
            Task(id=bad, title="x")

    def test_id_stripped(self):
        t = Task(id="  T-001  ", title="x")
        assert t.id == "T-001"


class TestTimestamps:
    def test_utc_aware(self):
        t = make_task()
        assert t.created_at.tzinfo == timezone.utc
        assert t.updated_at.tzinfo == timezone.utc
