"""S10-063 批次 A — CostRecord + CostLedger 测试套件。

覆盖: CostRecord to_dict/from_dict/缺省/purpose 归一/total_tokens 推算;
estimate_cost (缺省费率 + provider 覆盖); record append + 持久化;
aggregate 聚合 (total/by_purpose/by_agent/by_task/by_sprint/planning/
execution/repair/replanning 分项); 失败安全。

装配: tmp_path; 禁真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

CL = import_module("factory-console.session.cost_ledger")


def _ledger(tmp_path: Path) -> CL.CostLedger:
    return CL.CostLedger(file=tmp_path / "cost_records.json")


def _record(**overrides) -> dict:
    base = {
        "project_id": "p1",
        "sprint_id": "s1",
        "task_id": "T1",
        "agent_id": "A1",
        "role": "coder",
        "purpose": "EXECUTION",
        "provider": "deepseek",
        "model": "m1",
        "input_tokens": 100,
        "output_tokens": 100,
        "total_tokens": 200,
        "estimated_cost": 0.02,
        "latency": 1.0,
        "timestamp": "2026-08-16T00:00:00+00:00",
        "parent_execution_id": "e1",
    }
    base.update(overrides)
    return base


# ================================================================== 1. CostRecord


class TestCostRecord:
    def test_purpose_constants(self):
        assert CL.PURPOSE_DISCOVERY == "DISCOVERY"
        assert CL.PURPOSE_EXECUTION == "EXECUTION"
        assert CL.PURPOSE_REPAIR == "REPAIR"
        assert CL.PURPOSE_REPLANNING == "REPLANNING"
        assert CL.PURPOSE_OTHER == "OTHER"
        assert "PLANNING" in CL.PURPOSES
        assert "TASK_PROPOSAL" in CL.PURPOSES
        assert "PLAN_CRITIC" in CL.PURPOSES
        assert "GAP_ANALYSIS" in CL.PURPOSES

    def test_to_dict_all_fields(self):
        rec = CL.CostRecord.from_dict(_record())
        d = rec.to_dict()
        assert d["project_id"] == "p1"
        assert d["sprint_id"] == "s1"
        assert d["task_id"] == "T1"
        assert d["agent_id"] == "A1"
        assert d["role"] == "coder"
        assert d["purpose"] == "EXECUTION"
        assert d["provider"] == "deepseek"
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 100
        assert d["total_tokens"] == 200
        assert d["estimated_cost"] == pytest.approx(0.02)
        assert d["latency"] == pytest.approx(1.0)
        assert d["parent_execution_id"] == "e1"

    def test_from_dict_roundtrip(self):
        rec = CL.CostRecord.from_dict(_record())
        assert CL.CostRecord.from_dict(rec.to_dict()) == rec

    def test_from_dict_missing_keys_defaults(self):
        rec = CL.CostRecord.from_dict({})
        assert rec.purpose == CL.PURPOSE_OTHER
        assert rec.project_id == ""
        assert rec.total_tokens == 0

    def test_from_dict_total_tokens_inferred(self):
        rec = CL.CostRecord.from_dict(
            {"input_tokens": 30, "output_tokens": 20, "estimated_cost": 0.01}
        )
        assert rec.total_tokens == 50

    def test_from_dict_unknown_purpose_normalized(self):
        rec = CL.CostRecord.from_dict({"purpose": "random_stuff"})
        assert rec.purpose == CL.PURPOSE_OTHER

    def test_from_dict_purpose_uppercased(self):
        rec = CL.CostRecord.from_dict({"purpose": "repair"})
        assert rec.purpose == "REPAIR"

    def test_from_dict_none_returns_default(self):
        assert CL.CostRecord.from_dict(None) == CL.CostRecord()


# ================================================================== 2. estimate_cost


class TestEstimateCost:
    def test_default_input_rate(self):
        ledger = _ledger(Path("/tmp/__none__"))
        # 5e-7 * 1000 = 0.0005
        assert ledger.estimate_cost(input_tokens=1000) == pytest.approx(0.0005)

    def test_default_output_rate(self):
        ledger = _ledger(Path("/tmp/__none__"))
        # 1.5e-6 * 1000 = 0.0015
        assert ledger.estimate_cost(output_tokens=1000) == pytest.approx(0.0015)

    def test_default_combined(self):
        ledger = _ledger(Path("/tmp/__none__"))
        cost = ledger.estimate_cost(input_tokens=1000, output_tokens=2000)
        assert cost == pytest.approx(0.0005 + 0.003)

    def test_provider_specific_override(self):
        ledger = _ledger(Path("/tmp/__none__"))
        cost = ledger.estimate_cost(
            input_tokens=1000, output_tokens=1000, provider="deepseek"
        )
        assert cost == pytest.approx(0.0002 + 0.0006)

    def test_unknown_provider_uses_default(self):
        ledger = _ledger(Path("/tmp/__none__"))
        cost = ledger.estimate_cost(
            input_tokens=1000, output_tokens=1000, provider="mystery-llm"
        )
        assert cost == pytest.approx(0.0005 + 0.0015)

    def test_zero_tokens_zero_cost(self):
        ledger = _ledger(Path("/tmp/__none__"))
        assert ledger.estimate_cost() == 0.0


# ================================================================== 3. record / 持久化


class TestRecord:
    def test_record_appends_to_file(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(CL.CostRecord.from_dict(_record()))
        ledger.record(CL.CostRecord.from_dict(_record(task_id="T2")))
        data = json.loads((tmp_path / "cost_records.json").read_text(encoding="utf-8"))
        assert len(data) == 2

    def test_record_returns_normalized_dict(self, tmp_path):
        ledger = _ledger(tmp_path)
        rec = ledger.record(_record(purpose="execution"))
        assert rec["purpose"] == "EXECUTION"
        assert rec["timestamp"]

    def test_record_default_timestamp(self, tmp_path):
        ledger = _ledger(tmp_path)
        rec = ledger.record(_record(timestamp=""))
        assert rec["timestamp"]

    def test_record_accepts_dict_and_dataclass(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_record())
        ledger.record(CL.CostRecord.from_dict(_record(task_id="T9")))
        assert len(ledger.load()) == 2

    def test_records_filter_by_project(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_record(project_id="p1"))
        ledger.record(_record(project_id="p2"))
        assert len(ledger.records("p1")) == 1
        assert len(ledger.records("p2")) == 1
        assert len(ledger.records()) == 2

    def test_for_project_uses_project_dir(self, tmp_path):
        ledger = CL.CostLedger.for_project(tmp_path)
        ledger.record(_record())
        assert (tmp_path / "cost_records.json").exists()

    def test_records_file_path(self, tmp_path):
        ledger = _ledger(tmp_path)
        assert ledger.records_file() == tmp_path / "cost_records.json"


# ================================================================== 4. aggregate


class TestAggregate:
    def _seed(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_record(task_id="T1", agent_id="A1", purpose="EXECUTION",
                              estimated_cost=0.02, total_tokens=200))
        ledger.record(_record(task_id="T2", agent_id="A2", purpose="REPAIR",
                              estimated_cost=0.01, total_tokens=100))
        ledger.record(_record(task_id="T3", agent_id="A1", purpose="REPLANNING",
                              estimated_cost=0.03, total_tokens=300))
        ledger.record(_record(task_id="T4", agent_id="A3", purpose="PLANNING",
                              estimated_cost=0.04, total_tokens=400))
        ledger.record(_record(task_id="T5", agent_id="A3", purpose="GAP_ANALYSIS",
                              estimated_cost=0.05, total_tokens=500))
        return ledger

    def test_aggregate_total(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["total_cost"] == pytest.approx(0.15)
        assert agg["total_tokens"] == 1500
        assert agg["record_count"] == 5

    def test_aggregate_by_purpose(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["by_purpose"]["EXECUTION"]["cost"] == pytest.approx(0.02)
        assert agg["by_purpose"]["REPAIR"]["calls"] == 1
        assert agg["by_purpose"]["REPLANNING"]["tokens"] == 300

    def test_aggregate_by_agent(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["by_agent"]["A1"]["calls"] == 2
        assert agg["by_agent"]["A3"]["cost"] == pytest.approx(0.09)

    def test_aggregate_by_task(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["by_task"]["T1"]["cost"] == pytest.approx(0.02)
        assert agg["by_task"]["T5"]["tokens"] == 500

    def test_aggregate_by_sprint(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["by_sprint"]["s1"]["calls"] == 5

    def test_aggregate_planning_cost(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        # PLANNING 0.04 + GAP_ANALYSIS 0.05 = 0.09
        assert agg["planning_cost"] == pytest.approx(0.09)

    def test_aggregate_execution_cost(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["execution_cost"] == pytest.approx(0.02)

    def test_aggregate_repair_cost(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["repair_cost"] == pytest.approx(0.01)

    def test_aggregate_replanning_cost(self, tmp_path):
        agg = self._seed(tmp_path).aggregate()
        assert agg["replanning_cost"] == pytest.approx(0.03)

    def test_aggregate_project_filter(self, tmp_path):
        ledger = _ledger(tmp_path)
        ledger.record(_record(project_id="p1", estimated_cost=0.02))
        ledger.record(_record(project_id="p2", estimated_cost=0.10))
        agg = ledger.aggregate("p1")
        assert agg["total_cost"] == pytest.approx(0.02)
        assert agg["record_count"] == 1

    def test_aggregate_empty(self, tmp_path):
        agg = _ledger(tmp_path).aggregate()
        assert agg["total_cost"] == 0.0
        assert agg["total_tokens"] == 0
        assert agg["record_count"] == 0
        assert agg["by_agent"] == {}


# ================================================================== 5. 失败安全


class TestFailSafe:
    def test_load_missing_file_empty(self, tmp_path):
        assert _ledger(tmp_path).load() == []

    def test_load_corrupt_file_empty(self, tmp_path):
        path = tmp_path / "cost_records.json"
        path.write_text("{corrupt", encoding="utf-8")
        assert _ledger(tmp_path).load() == []

    def test_save_failure_safe(self, tmp_path):
        ledger = _ledger(tmp_path)
        # 目标是不可写路径 (父目录为文件) → 不抛
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        ledger.record(_record())  # 正常记录
        ledger._file = blocker / "cost_records.json"
        ledger.save(ledger.load())  # 不抛
