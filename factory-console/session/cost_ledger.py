"""factory-console/session/cost_ledger.py — CostRecord + CostLedger (S10-063 批次 A)。

Production Governance (GAP G3/G4, 设计 §4): 统一 Cost/Usage 记录 — 关联
project/sprint/task/agent/role/purpose/provider/model/tokens/cost/latency/
timestamp/parent_execution_id, append 落盘 cost_records.json (项目级
projects/<slug>/cost_records.json, 缺省 ~/.factory/cost/cost_records.json)。

组件:
- CostRecord   — 单条成本记录 (全字段 + to_dict/from_dict; purpose 白名单
  PURPOSES: DISCOVERY/PLANNING/TASK_PROPOSAL/PLAN_CRITIC/EXECUTION/REPAIR/
  REPLANNING/GAP_ANALYSIS/OTHER, 未知 purpose 归一 OTHER)
- CostLedger   — record (append 落盘, 失败安全) / records(project_id) 读回 /
  aggregate (total_cost/total_tokens/by_purpose/by_agent/by_task/by_sprint/
  planning/execution/repair/replanning 分项 + record_count) /
  estimate_cost (粗估 USD: 缺省 input=5e-7/token, output=1.5e-6/token;
  provider 特定可扩展 PROVIDER_RATES) / for_project(project_dir)

数据源复用: AgentRuntime usage (execution_records) → record;
planning_trace token_usage → record (调用方转换, 本模块只记录/聚合)。

设计: docs/sprint10/S10-063-production-governance-design.md §4
边界: 纯标准库 (json/pathlib/dataclasses/datetime), 零依赖, 不修改任何现有模块;
失败安全: 读 (缺失/损坏 → []) / 写 (目录不可写等 → 不抛, 记录仍返回)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: 缺省成本账本文件 (~/.factory/cost/cost_records.json — 设计 §4 资产口径;
#: 项目级记录 → projects/<slug>/cost_records.json, 由调用方显式指定)
DEFAULT_LEDGER_FILE = Path.home() / ".factory" / "cost" / "cost_records.json"

#: 项目级成本账本文件名 (projects/<slug>/cost_records.json)
COST_RECORDS_FILE_NAME = "cost_records.json"

# ---------------------------------------------------------------- purpose 常量

PURPOSE_DISCOVERY = "DISCOVERY"
PURPOSE_PLANNING = "PLANNING"
PURPOSE_TASK_PROPOSAL = "TASK_PROPOSAL"
PURPOSE_PLAN_CRITIC = "PLAN_CRITIC"
PURPOSE_EXECUTION = "EXECUTION"
PURPOSE_REPAIR = "REPAIR"
PURPOSE_REPLANNING = "REPLANNING"
PURPOSE_GAP_ANALYSIS = "GAP_ANALYSIS"
PURPOSE_OTHER = "OTHER"

#: 全部合法 purpose (未知 purpose → 归一 OTHER)
PURPOSES: tuple[str, ...] = (
    PURPOSE_DISCOVERY,
    PURPOSE_PLANNING,
    PURPOSE_TASK_PROPOSAL,
    PURPOSE_PLAN_CRITIC,
    PURPOSE_EXECUTION,
    PURPOSE_REPAIR,
    PURPOSE_REPLANNING,
    PURPOSE_GAP_ANALYSIS,
    PURPOSE_OTHER,
)

#: 规划阶段分项 (aggregate.planning_cost 口径 — 设计 §4 分项)
PLANNING_PURPOSES: tuple[str, ...] = (
    PURPOSE_DISCOVERY,
    PURPOSE_PLANNING,
    PURPOSE_TASK_PROPOSAL,
    PURPOSE_PLAN_CRITIC,
    PURPOSE_GAP_ANALYSIS,
)

# ---------------------------------------------------------------- 成本估算费率

#: 缺省估算费率 (USD/token 粗估 — 设计 §4; 输入/输出不同价)
DEFAULT_INPUT_RATE = 0.0000005
DEFAULT_OUTPUT_RATE = 0.0000015

#: provider 特定费率覆盖 (键 = provider 小写归一; 未知 provider → 缺省费率。
#: 可扩展 — 新增 provider 在此登记即可)
PROVIDER_RATES: dict[str, dict[str, float]] = {
    "deepseek": {"input": 0.0000002, "output": 0.0000006},
    "openai": {"input": 0.0000005, "output": 0.0000015},
    "anthropic": {"input": 0.0000015, "output": 0.0000075},
}


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式 (记录时间戳)。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CostRecord:
    """单条成本记录 (设计 §4): 全字段 + to_dict/from_dict。

    project_id / sprint_id / task_id / agent_id / role / purpose /
    provider / model / input_tokens / output_tokens / total_tokens /
    estimated_cost (USD) / latency (秒) / timestamp (UTC ISO) /
    parent_execution_id (审计关联 — GAP G8 基础)。
    """

    project_id: str = ""
    sprint_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    role: str = ""
    purpose: str = PURPOSE_OTHER
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    latency: float = 0.0
    timestamp: str = ""
    parent_execution_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """→ dict (落盘 cost_records.json / 聚合输入)。"""
        return {
            "project_id": self.project_id,
            "sprint_id": self.sprint_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "purpose": self.purpose,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "total_tokens": int(self.total_tokens),
            "estimated_cost": float(self.estimated_cost),
            "latency": float(self.latency),
            "timestamp": self.timestamp,
            "parent_execution_id": self.parent_execution_id,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CostRecord":
        """dict → CostRecord (缺失字段 → 缺省, 前向兼容/失败安全)。

        total_tokens 缺省 → input+output 推算; purpose 未知 → OTHER。
        """
        if not isinstance(data, dict):
            return cls()
        purpose = str(data.get("purpose") or PURPOSE_OTHER).upper()
        if purpose not in PURPOSES:
            purpose = PURPOSE_OTHER
        input_tokens = int(data.get("input_tokens") or 0)
        output_tokens = int(data.get("output_tokens") or 0)
        total_tokens = int(data.get("total_tokens") or 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return cls(
            project_id=str(data.get("project_id") or ""),
            sprint_id=str(data.get("sprint_id") or ""),
            task_id=str(data.get("task_id") or ""),
            agent_id=str(data.get("agent_id") or ""),
            role=str(data.get("role") or ""),
            purpose=purpose,
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=float(data.get("estimated_cost") or 0.0),
            latency=float(data.get("latency") or 0.0),
            timestamp=str(data.get("timestamp") or ""),
            parent_execution_id=str(data.get("parent_execution_id") or ""),
        )


class CostLedger:
    """成本账本 (设计 §4): record → cost_records.json (append)。

    record(cost) — CostRecord 或 dict → 归一化 dict (purpose 校验/时间戳兜底),
    append 落盘 (失败安全, 不抛; 即使落盘失败也返回记录);
    records(project_id=None) — 读回全部/按项目过滤 (失败安全 → []);
    aggregate(project_id=None) — 聚合 {total_cost, total_tokens, by_purpose,
    by_agent, by_task, by_sprint, planning_cost, execution_cost, repair_cost,
    replanning_cost, record_count};
    estimate_cost(input_tokens, output_tokens, provider, model) — 粗估 USD;
    for_project(project_dir) — 项目级账本实例 (projects/<slug>/cost_records.json)。
    """

    FILE_NAME = COST_RECORDS_FILE_NAME

    def __init__(self, file: Optional[Path] = None) -> None:
        self._file = Path(file) if file is not None else DEFAULT_LEDGER_FILE

    # ------------------------------------------------------------ record

    def record(self, cost: Any) -> dict[str, Any]:
        """记录一条成本 (CostRecord 或 dict) — append 落盘, 返回归一化 dict。

        失败安全: 落盘异常不抛; timestamp 缺省 → now (UTC ISO)。
        """
        if isinstance(cost, CostRecord):
            rec = cost.to_dict()
        elif isinstance(cost, dict):
            rec = dict(cost)
        else:
            rec = {}
        rec = CostRecord.from_dict(rec).to_dict()
        if not rec["timestamp"]:
            rec["timestamp"] = _now_iso()
        records = self.load()
        records.append(rec)
        self.save(records)
        return rec

    def records(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        """读回全部记录; project_id 给定 → 只返回该项目记录 (失败安全)。"""
        records = self.load()
        if project_id is None:
            return records
        return [r for r in records if r.get("project_id") == project_id]

    # ------------------------------------------------------------ aggregate

    def aggregate(self, project_id: Optional[str] = None) -> dict[str, Any]:
        """聚合 (设计 §4 分项): total / by_purpose / by_agent / by_task /
        by_sprint / planning|execution|repair|replanning_cost。

        planning_cost 口径 = DISCOVERY+PLANNING+TASK_PROPOSAL+PLAN_CRITIC+
        GAP_ANALYSIS (PLANNING_PURPOSES); execution=EXECUTION;
        repair=REPAIR; replanning=REPLANNING。
        """
        records = self.records(project_id)
        total_cost = 0.0
        total_tokens = 0
        by_purpose: dict[str, dict[str, Any]] = {}
        by_agent: dict[str, dict[str, Any]] = {}
        by_task: dict[str, dict[str, Any]] = {}
        by_sprint: dict[str, dict[str, Any]] = {}
        planning_cost = execution_cost = repair_cost = replanning_cost = 0.0
        for r in records:
            cost = float(r.get("estimated_cost") or 0.0)
            tokens = int(r.get("total_tokens") or 0)
            purpose = str(r.get("purpose") or PURPOSE_OTHER)
            total_cost += cost
            total_tokens += tokens
            self._bump(by_purpose, purpose, cost, tokens)
            if r.get("agent_id"):
                self._bump(by_agent, str(r["agent_id"]), cost, tokens)
            if r.get("task_id"):
                self._bump(by_task, str(r["task_id"]), cost, tokens)
            if r.get("sprint_id"):
                self._bump(by_sprint, str(r["sprint_id"]), cost, tokens)
            if purpose in PLANNING_PURPOSES:
                planning_cost += cost
            elif purpose == PURPOSE_EXECUTION:
                execution_cost += cost
            elif purpose == PURPOSE_REPAIR:
                repair_cost += cost
            elif purpose == PURPOSE_REPLANNING:
                replanning_cost += cost
        return {
            "total_cost": round(total_cost, 6),
            "total_tokens": int(total_tokens),
            "record_count": len(records),
            "by_purpose": by_purpose,
            "by_agent": by_agent,
            "by_task": by_task,
            "by_sprint": by_sprint,
            "planning_cost": round(planning_cost, 6),
            "execution_cost": round(execution_cost, 6),
            "repair_cost": round(repair_cost, 6),
            "replanning_cost": round(replanning_cost, 6),
        }

    @staticmethod
    def _bump(
        bucket: dict[str, dict[str, Any]], key: str, cost: float, tokens: int
    ) -> None:
        """聚合桶累加 (cost/tokens/calls)。"""
        item = bucket.setdefault(
            key, {"cost": 0.0, "tokens": 0, "calls": 0}
        )
        item["cost"] = round(item["cost"] + cost, 6)
        item["tokens"] += int(tokens)
        item["calls"] += 1

    # ------------------------------------------------------------ estimate

    def estimate_cost(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        provider: str = "",
        model: str = "",
    ) -> float:
        """粗估成本 (USD, 设计 §4): 缺省 input=5e-7 / output=1.5e-6 每 token;
        provider 特定费率 (PROVIDER_RATES, 键小写归一) 可覆盖; 未知 → 缺省。
        """
        key = str(provider or "").strip().lower()
        rates = PROVIDER_RATES.get(key, {})
        in_rate = rates.get("input", DEFAULT_INPUT_RATE)
        out_rate = rates.get("output", DEFAULT_OUTPUT_RATE)
        cost = float(input_tokens or 0) * in_rate + float(output_tokens or 0) * out_rate
        return round(cost, 8)

    # ------------------------------------------------------------ 读/写

    def save(self, records: Any) -> None:
        """整表落盘 (失败安全: 读写异常 → 不抛)。"""
        if not isinstance(records, list):
            records = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — 失败安全
            pass

    def load(self) -> list[dict[str, Any]]:
        """读回全部记录 (缺失/损坏 → [], 失败安全)。"""
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [CostRecord.from_dict(d).to_dict() for d in data]
        except Exception:  # noqa: BLE001 — 缺失/损坏 → 空记录
            pass
        return []

    def records_file(self) -> Path:
        """当前落盘文件路径。"""
        return Path(self._file)

    @classmethod
    def for_project(cls, project_dir: Any) -> "CostLedger":
        """项目级账本实例 → projects/<slug>/cost_records.json。"""
        return cls(file=Path(project_dir) / COST_RECORDS_FILE_NAME)
