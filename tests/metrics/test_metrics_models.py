"""tests/metrics/test_metrics_models.py — FactoryMetrics 领域模型测试 (创建/序列化)。"""

from __future__ import annotations

import json

from metrics.models import (
    AgentMetric,
    ExecutionMetrics,
    FactoryMetrics,
    FailureMetrics,
    TaskMetrics,
    ValidationMetrics,
    WorkflowMetrics,
)


class TestFactoryMetricsDefaults:
    def test_empty_defaults(self):
        """空指标: 全字段默认值, 不抛错 (空工厂语义)。"""
        m = FactoryMetrics()
        assert m.tasks.total == 0
        assert m.tasks.completed == 0
        assert m.tasks.failed == 0
        assert m.tasks.success_rate == 0.0
        assert m.executions.total == 0
        assert m.executions.first_attempt_success_rate == 0.0
        assert m.agents == {}
        assert m.agents_total == 0
        assert m.workflows.run_count == 0
        assert m.workflows.success_rate == 0.0
        assert m.validation.pass_rate == 0.0
        assert m.failures.failure_reason_count == {}
        assert m.project_id is None

    def test_generated_at_is_utc(self):
        from datetime import timezone

        m = FactoryMetrics()
        assert m.generated_at.tzinfo is not None
        assert m.generated_at.utcoffset() == timezone.utc.utcoffset(None)

    def test_nested_defaults(self):
        m = FactoryMetrics()
        assert m.tasks.by_status == {}
        assert m.executions.by_status == {}
        assert m.workflows.by_status == {}
        assert m.workflows.definitions == 0
        assert m.validation.total_rules == 0

    def test_project_id(self):
        m = FactoryMetrics(project_id="P-001")
        assert m.project_id == "P-001"
        assert FactoryMetrics().project_id is None


class TestFactoryMetricsValues:
    def test_created_with_values(self):
        m = FactoryMetrics(
            project_id="P-001",
            tasks=TaskMetrics(total=3, completed=2, failed=1, success_rate=0.5,
                              by_status={"DONE": 2, "BACKLOG": 1}),
            executions=ExecutionMetrics(total=4, success=3, failed=1,
                                        first_attempt_success_rate=0.75),
            agents={"A-001": AgentMetric(assignment_count=2, success_count=2,
                                         success_rate=1.0)},
            agents_total=1,
            workflows=WorkflowMetrics(run_count=2, completed=1, success_rate=0.5),
            validation=ValidationMetrics(total_rules=4, pass_count=3, pass_rate=0.75),
            failures=FailureMetrics(failure_reason_count={"testing": 1}),
        )
        assert m.tasks.total == 3
        assert m.executions.first_attempt_success_rate == 0.75
        assert m.agents["A-001"].success_rate == 1.0
        assert m.workflows.run_count == 2
        assert m.validation.pass_rate == 0.75
        assert m.failures.failure_reason_count == {"testing": 1}


class TestSerialization:
    def test_to_dict_roundtrip(self):
        m = FactoryMetrics(
            project_id="P-001",
            tasks=TaskMetrics(total=1, completed=1, success_rate=1.0),
            agents={"A-001": AgentMetric(assignment_count=1)},
        )
        data = m.to_dict()
        assert data["project_id"] == "P-001"
        assert data["tasks"]["completed"] == 1
        assert data["agents"]["A-001"]["assignment_count"] == 1
        restored = FactoryMetrics.model_validate(data)
        assert restored.to_dict() == data

    def test_to_dict_json_dumpable(self):
        """--json 出口: model_dump(mode=json) 必须可 json.dumps (无 datetime 残留)。"""
        m = FactoryMetrics(
            tasks=TaskMetrics(total=2, success_rate=0.5),
            failures=FailureMetrics(failure_reason_count={"dev": 1}),
        )
        payload = json.dumps(m.to_dict(), ensure_ascii=False)
        assert '"total": 2' in payload
        assert '"dev": 1' in payload

    def test_agents_dict_serialization(self):
        m = FactoryMetrics(
            agents={"A-002": AgentMetric(failed_count=1),
                    "A-001": AgentMetric(assignment_count=3, success_count=2,
                                         failed_count=1, success_rate=0.5)},
        )
        data = m.to_dict()
        assert isinstance(data["agents"], dict)
        assert data["agents"]["A-001"]["success_rate"] == 0.5
        assert data["agents"]["A-002"]["failed_count"] == 1

    def test_sub_model_to_dict(self):
        assert TaskMetrics().to_dict()["total"] == 0
        assert ExecutionMetrics(total=1).to_dict()["total"] == 1
        assert AgentMetric(assignment_count=2).to_dict()["assignment_count"] == 2
        assert WorkflowMetrics(run_count=1).to_dict()["run_count"] == 1
        assert ValidationMetrics(pass_count=1).to_dict()["pass_count"] == 1
        assert FailureMetrics(failure_reason_count={"x": 1}).to_dict()["failure_reason_count"] == {"x": 1}

    def test_failure_reason_count_preserves_order(self):
        """直方图保序 (most_common 次数降序) — JSON 序列化后顺序不变。"""
        m = FactoryMetrics(failures=FailureMetrics(
            failure_reason_count={"testing": 3, "dev": 1},
        ))
        assert list(m.to_dict()["failures"]["failure_reason_count"]) == ["testing", "dev"]
