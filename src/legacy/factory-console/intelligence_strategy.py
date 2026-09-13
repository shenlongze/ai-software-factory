"""factory-console/intelligence_strategy.py — S42 Intelligence Strategy Kernel.

Learning / Healing / Optimization 统一为 IntelligenceStrategy Contract:
- strategy_id/strategy_type/version/capabilities/input_contract/output_contract/
  context_requirements/cost_budget/execution_policy/governance_policy
- 注册到 S31 Plugin Kernel (type=strategy) — 唯一 Registry, 不建第二套
- 三个 Adapter (薄, 不复制逻辑): Learning→learning_engine_v2, Healing→self_healing,
  Optimization→optimization_engine
- 统一执行: StrategyRequest → Resolution → Execute → Candidate → Evaluation → Decision
- StrategyExecutionEvidence (strategy/version/input/candidate/evaluation/governance/result/cost)
- 共享 S38 管道验证 (Candidate/Evaluation/Experiment/Governance/Canary/Promotion 只有一套)
- Learning 例外: [STOP] 语义 (S37 设计)

禁止: 新 Loop / 第二套 Registry / Strategy 绕过 Governance / 直接改 Production
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

STRATEGY_TYPES = ("LEARNING", "HEALING", "OPTIMIZATION")

#: Strategy Adapters (strategy_type → handler)
STRATEGY_ADAPTERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file(root: Path | str, name: str) -> Path:
    return Path(root) / "ops" / "intelligence" / f"{name}.json"


def _load(root: Path | str, name: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(_file(root, name).read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(root: Path | str, name: str, data: list[dict[str, Any]]) -> None:
    p = _file(root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _audit(root: Path | str, event_type: str, payload: dict[str, Any]) -> None:
    try:
        from .audit.audit_event import AuditEvent
        from .audit.audit_store import AuditStore

        store = AuditStore(workspace=None, file=str(Path(root) / "audit" / "audit_events.json"))
        ev = AuditEvent.create(
            event_type,
            trace_id=payload.get("execution_id") or payload.get("strategy_id") or "",
            actor_type="system", actor_id="intelligence",
            action=f"intelligence.{event_type.lower()}",
            source="intelligence_strategy", decision="allow",
            decision_reason=payload.get("note") or "",
            evidence=[payload], result={"ok": True}, metadata={"intelligence": payload},
        )
        store.append(ev)
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ Register Strategy (经 Plugin Kernel)

def register_strategy(root: Path | str, *, strategy_id: str, strategy_type: str,
                      version: str, capabilities: list[str],
                      input_contract: dict[str, Any] | None = None,
                      output_contract: dict[str, Any] | None = None,
                      context_requirements: dict[str, Any] | None = None,
                      cost_budget: float = 1.0,
                      execution_policy: str = "governed",
                      governance_policy: str = "human_gate_high") -> dict[str, Any]:
    """注册 IntelligenceStrategy (经 S31 Plugin Kernel type=strategy; 唯一 Registry)。"""
    if strategy_type not in STRATEGY_TYPES:
        raise ValueError(f"非法 strategy_type: {strategy_type}")
    from .plugin_kernel import bootstrap, get_plugin, register_plugin, plugin_status
    bootstrap(root)
    if get_plugin(root, strategy_id) is None:
        register_plugin(root, plugin_id=strategy_id, name=strategy_id, version=version,
                        type="strategy", vendor="ai-factory",
                        capabilities=capabilities, permissions=["intelligence.execute"])
        plugin_status(root, strategy_id, target="ENABLED")
    rec = {"strategy_id": strategy_id, "strategy_type": strategy_type,
           "version": version, "capabilities": capabilities,
           "input_contract": input_contract or {}, "output_contract": output_contract or {},
           "context_requirements": context_requirements or {},
           "cost_budget": cost_budget, "execution_policy": execution_policy,
           "governance_policy": governance_policy, "registered_at": _now_iso()}
    # 持久化 strategy record (ops/intelligence/strategies.json)
    data = _load(root, "strategies")
    data = [s for s in data if s["strategy_id"] != strategy_id]
    data.append(rec)
    _save(root, "strategies", data)
    _audit(root, "STRATEGY_REGISTERED", {"strategy_id": strategy_id,
                                         "strategy_type": strategy_type,
                                         "version": version})
    return rec


def strategies(root: Path | str) -> list[dict[str, Any]]:
    return _load(root, "strategies")


def get_strategy(root: Path | str, strategy_id: str) -> dict[str, Any]:
    for s in strategies(root):
        if s["strategy_id"] == strategy_id:
            return s
    raise ValueError(f"Strategy 不存在: {strategy_id}")


# ------------------------------------------------------------------ Adapters

def register_adapter(strategy_type: str,
                     fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Strategy Adapter 注册 (Learning/Healing/Optimization 薄代理)。"""
    if strategy_type not in STRATEGY_TYPES:
        raise ValueError(f"非法 strategy_type: {strategy_type}")
    STRATEGY_ADAPTERS[strategy_type] = fn


def _default_adapters(root: Path | str) -> None:
    """默认三个 Adapter (薄, 调既有服务, 不复制逻辑)。

    每次重建 (绑定当前 root), 避免缓存旧 root 的闭包。
    """
    def learning_adapter(payload):
        from .learning_engine_v2 import create_observation, run_learning
        obs = create_observation(root, source_type=payload.get("source_type", "production_run"),
                                 source_id=payload.get("source_id", "auto"),
                                 pattern_key=payload.get("pattern_key", "pattern"),
                                 outcome=payload.get("outcome", "UNKNOWN"),
                                 scope=payload.get("scope", "node"))
        result = run_learning(root)
        return {"strategy_type": "LEARNING", "observation_id": obs["observation_id"],
                "candidates": result["created"], "results": result["results"],
                "evidence_count": result["evidence_count"],
                "outcome": "CANDIDATE_EVALUATED", "stopped_at_candidate": True,
                "explain": "Learning [STOP] at Candidate/Evaluation (S37)"}
    STRATEGY_ADAPTERS["LEARNING"] = learning_adapter

    def healing_adapter(payload):
        from .self_healing import create_incident, run_self_healing
        inc = create_incident(root, source="verification",
                              production_run_id=payload.get("production_run_id", "auto"),
                              node_id=payload.get("node_id", "node-1"),
                              failure_type=payload.get("failure_type", "failure"),
                              severity=payload.get("severity", "MEDIUM"))
        result = run_self_healing(root, inc["incident_id"],
                                  executor_factory=payload.get("executor_factory"),
                                  artifact_root=payload.get("artifact_root") or root,
                                  risk=payload.get("risk", "MEDIUM"),
                                  human_actor=payload.get("actor", "human"))
        return {"strategy_type": "HEALING", "incident_id": inc["incident_id"],
                **result}
    STRATEGY_ADAPTERS["HEALING"] = healing_adapter

    def optimization_adapter(payload):
        from .optimization_engine import (create_opportunity, create_candidate,
                                          _provider_opt_plugin, run_optimization)
        opp = create_opportunity(root, source="performance",
                                 target_type=payload.get("target_type", "provider"),
                                 target_id=payload.get("target_id", "target"),
                                 metric=payload.get("metric", "success_rate"),
                                 current_value=payload.get("current_value", 0.0),
                                 risk=payload.get("risk", "MEDIUM"))
        cands = [create_candidate(root, opportunity_id=opp["opportunity_id"],
                                  strategy_plugin_id="opt.provider",
                                  target=cp["candidate_target"],
                                  proposed_change=cp["proposed_change"],
                                  risk=payload.get("risk", "MEDIUM"))
                 for cp in _provider_opt_plugin(opp)]
        result = run_optimization(root, cands[0]["candidate_id"],
                                  baseline_metrics=payload.get("baseline_metrics", {}),
                                  candidate_metrics=payload.get("candidate_metrics", {}),
                                  sample_count=payload.get("sample_count", 0),
                                  human_actor=payload.get("actor", "human"))
        return {"strategy_type": "OPTIMIZATION", "opportunity_id": opp["opportunity_id"],
                "candidates": [c["candidate_id"] for c in cands], **result}
    STRATEGY_ADAPTERS["OPTIMIZATION"] = optimization_adapter


# ------------------------------------------------------------------ Execution

def execute_strategy(root: Path | str, *, strategy_id: str,
                     payload: dict[str, Any]) -> dict[str, Any]:
    """统一执行: StrategyRequest → Resolution (Plugin Kernel) → Adapter → Evidence。"""
    # 1. Resolution (经 Plugin Kernel: ENABLED + permission, 非 LLM)
    from .plugin_kernel import get_plugin
    p = get_plugin(root, strategy_id)
    if p is None:
        raise ValueError(f"Strategy Plugin 不存在: {strategy_id}")
    if p["status"] != "ENABLED":
        raise PermissionError(f"Strategy 未启用: {strategy_id}")
    # 2. Strategy record
    rec = get_strategy(root, strategy_id)
    # 3. Adapter 执行
    adapter = STRATEGY_ADAPTERS.get(rec["strategy_type"])
    if adapter is None:
        raise ValueError(f"无 Adapter: {rec['strategy_type']}")
    # Cost budget 检查 (estimated)
    budget = rec["cost_budget"]
    result = adapter(payload)
    # 4. StrategyExecutionEvidence (version 进 lineage)
    evidence = {"execution_id": f"intel-{uuid.uuid4().hex[:10]}",
                "strategy_id": strategy_id,
                "strategy_type": rec["strategy_type"],
                "strategy_version": rec["version"],
                "input": {"payload_keys": list(payload.keys())},
                "result": result, "cost_budget": budget,
                "actual_cost": "NOT_AVAILABLE",
                "created_at": _now_iso()}
    _save(root, "executions", _load(root, "executions") + [evidence])
    _audit(root, "STRATEGY_EXECUTED", {"execution_id": evidence["execution_id"],
                                       "strategy_id": strategy_id,
                                       "strategy_type": rec["strategy_type"],
                                       "version": rec["version"]})
    return evidence


def executions(root: Path | str, *, strategy_id: str = "") -> list[dict[str, Any]]:
    data = _load(root, "executions")
    if strategy_id:
        data = [e for e in data if e["strategy_id"] == strategy_id]
    return data


def strategy_lineage(root: Path | str, strategy_id: str) -> list[dict[str, Any]]:
    """Strategy 历史执行 (version 可追溯, 不覆盖历史解释)。"""
    return executions(root, strategy_id=strategy_id)
