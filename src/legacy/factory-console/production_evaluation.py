"""factory-console/production_evaluation.py — S13 Production Evaluation.

基于真实 Production Evidence 的确定性质量评价 (非 LLM 打分)。

- evaluate(root, production_run_id) → ProductionEvaluation
- 读取: ProductionRun state/node_runs/artifacts/history + NodeRun attempts/verification
  + Artifact lifecycle + Handoff refs (全部真实事实, 无 session/memory)
- 维度 (加权和, 透明可审计):
  completion 20 / artifact_integrity 15 / verification 20 /
  lineage_integrity 20 / workspace_delivery 15 / repair_efficiency 10
- 历史 FAIL 不判最终 FAIL: final_status + historical_failures 分开记录
- 幂等: 已存在 evaluation → 返回现有; 可重复计算 (同一 evidence → 同一 score)
- Evaluation Artifact 持久化: evaluations/<run_id>.json (derived, 非事实源)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_run import get_production_run
from .node_runtime import get_node_run
from .artifact_lifecycle import get_artifact

#: 维度权重 (透明, 代码可审计)
WEIGHTS = {
    "completion": 20,
    "artifact_integrity": 15,
    "verification": 20,
    "lineage_integrity": 20,
    "workspace_delivery": 15,
    "repair_efficiency": 10,
}
TOTAL_WEIGHT = sum(WEIGHTS.values())  # 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _eval_path(root: Path | str, run_id: str) -> Path:
    return Path(root) / "evaluations" / f"{run_id}.json"


# ------------------------------------------------------------------ 维度评价 (确定性)

def _eval_completion(run: dict[str, Any]) -> dict[str, Any]:
    ok = run.get("state") == "COMPLETED"
    return {"score": 100 if ok else 0, "pass": ok,
            "detail": {"state": run.get("state")}}


def _eval_artifact_integrity(root: Path | str, artifacts: list[str]) -> dict[str, Any]:
    """最终 Artifact 存在 + lifecycle 有效。"""
    if not artifacts:
        return {"score": 0, "pass": False, "detail": {"error": "无 Artifact"}}
    valid = 0
    for aid in artifacts:
        art = get_artifact(root, aid)
        if art is not None and art.get("state") in ("GENERATED", "APPLIED", "COMMITTED", "RELEASED"):
            valid += 1
    ratio = valid / len(artifacts)
    return {"score": int(ratio * 100), "pass": valid > 0,
            "detail": {"total": len(artifacts), "valid": valid}}


def _eval_verification(run: dict[str, Any], root: Path | str) -> dict[str, Any]:
    """最终 Verification PASS + 历史失败统计。"""
    node_runs = run.get("node_runs", [])
    final_passes = 0
    total_attempts = 0
    failed_attempts = 0
    repair_count = 0
    for nr in node_runs:
        if not nr.get("run_id"):
            continue
        nrec = get_node_run(root, nr["run_id"])
        if not nrec:
            continue
        attempts = nrec.get("attempts", [])
        total_attempts += len(attempts) or 1
        prev_fail = False
        for a in attempts:
            v = a.get("verification") or {}
            status = v.get("status") or v.get("result")
            if status == "FAIL":
                failed_attempts += 1
                prev_fail = True
            elif prev_fail and status == "PASS":
                repair_count += 1  # S13: FAIL→PASS 序列 = 一次 repair
                prev_fail = False
            else:
                prev_fail = False
            if a.get("state") == "RETRY":
                repair_count += 1  # transient retry 也算一次尝试
        # 最终 NodeRun verification
        fv = nrec.get("verification") or {}
        if (fv.get("status") or fv.get("result")) == "PASS":
            final_passes += 1
    all_pass = run.get("state") == "COMPLETED" and final_passes == len(node_runs)
    return {"score": 100 if all_pass else 0, "pass": all_pass,
            "detail": {"final_passes": final_passes, "node_runs": len(node_runs),
                       "total_attempts": total_attempts, "failed_attempts": failed_attempts,
                       "repair_count": repair_count}}


def _eval_lineage(root: Path | str, run: dict[str, Any]) -> dict[str, Any]:
    """Lineage: 引用的 artifact 存在 + handoff 引用有效。"""
    artifacts = run.get("artifacts", [])
    missing = []
    for aid in artifacts:
        if get_artifact(root, aid) is None:
            missing.append(aid)
    # handoff refs (agents/handoffs)
    handoffs = Path(root) / "agents" / "handoffs"
    handoff_count = 0
    broken_handoffs = 0
    if handoffs.is_dir():
        for f in handoffs.glob("*.json"):
            try:
                h = json.loads(f.read_text(encoding="utf-8"))
                handoff_count += 1
                for aid in h.get("input_artifacts", []):
                    if get_artifact(root, aid) is None:
                        broken_handoffs += 1
            except (OSError, ValueError):
                broken_handoffs += 1
    ok = not missing and broken_handoffs == 0
    return {"score": 100 if ok else 0, "pass": ok,
            "detail": {"missing_artifacts": missing, "handoffs": handoff_count,
                       "broken_handoffs": broken_handoffs}}


def _eval_workspace(run: dict[str, Any]) -> dict[str, Any]:
    """Workspace delivery: ProductionRun COMPLETED 且至少一个 artifact 可 Apply。"""
    ok = run.get("state") == "COMPLETED" and len(run.get("artifacts", [])) > 0
    return {"score": 100 if ok else 0, "pass": ok,
            "detail": {"state": run.get("state"), "artifacts": len(run.get("artifacts", []))}}


def _eval_repair(verification_detail: dict[str, Any]) -> dict[str, Any]:
    """Repair efficiency: 0 修复 excellent, 1 acceptable, 2+ degraded。"""
    repair_count = verification_detail.get("repair_count", 0)
    if repair_count == 0:
        score = 100
    elif repair_count == 1:
        score = 80
    elif repair_count == 2:
        score = 60
    else:
        score = max(0, 40 - (repair_count - 3) * 10)
    return {"score": score, "pass": repair_count <= 2,
            "detail": {"repair_count": repair_count}}


# ------------------------------------------------------------------ Evaluation

def evaluate(root: Path | str, production_run_id: str, *, force: bool = False) -> dict[str, Any]:
    """评估 ProductionRun (确定性, 幂等)。

    force=True 重新计算; 默认: 已存在 → 返回现有 (不重复生成)。
    """
    run = get_production_run(root, production_run_id)
    if run is None:
        raise ValueError(f"ProductionRun 不存在: {production_run_id}")

    # 幂等: 已存在且非 force → 返回现有
    existing = _eval_path(root, production_run_id)
    if existing.exists() and not force:
        try:
            return json.loads(existing.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    dims = {
        "completion": _eval_completion(run),
        "artifact_integrity": _eval_artifact_integrity(root, run.get("artifacts", [])),
        "verification": _eval_verification(run, root),
        "lineage_integrity": _eval_lineage(root, run),
        "workspace_delivery": _eval_workspace(run),
        "repair_efficiency": _eval_repair(_eval_verification(run, root)["detail"]),
    }

    overall = sum(int(dims[k]["score"]) * WEIGHTS[k] for k in dims) // TOTAL_WEIGHT
    ver_detail = dims["verification"]["detail"]
    final_artifact = run.get("artifacts", [])[-1] if run.get("artifacts") else None

    eval_result = {
        "evaluation_id": f"eval-{uuid.uuid4().hex[:10]}",
        "production_run_id": production_run_id,
        "workflow_id": run.get("workflow_id"),
        "status": run.get("state"),
        "overall_score": overall,
        "dimensions": {k: {"score": dims[k]["score"], "pass": dims[k]["pass"],
                           "detail": dims[k]["detail"]} for k in dims},
        "repair_count": ver_detail.get("repair_count", 0),
        "verification_attempts": ver_detail.get("total_attempts", 0),
        "historical_failures": ver_detail.get("failed_attempts", 0),
        "final_artifact_id": final_artifact,
        "evidence_refs": {"node_runs": [nr.get("run_id") for nr in run.get("node_runs", [])],
                          "artifacts": run.get("artifacts", [])},
        "created_at": _now_iso(),
        "evaluator": "deterministic-s13",
    }
    # 持久化 (atomic)
    existing.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(existing.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(eval_result, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, existing)
    return eval_result


def get_evaluation(root: Path | str, production_run_id: str) -> dict[str, Any] | None:
    p = _eval_path(root, production_run_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def list_evaluations(root: Path | str) -> list[dict[str, Any]]:
    base = Path(root) / "evaluations"
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                out.append(d)
        except (OSError, ValueError):
            continue
    return out
