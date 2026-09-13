"""factory-console/production_guidance.py — S15 Experience-Guided Autonomous Production.

让真实生产中积累的 Experience 成为 Agent 的可追溯决策依据 (Guidance, 非指令)。

- retrieve_guidance(root, role, task_context): 确定性检索 + role/task 匹配 relevance
  (role_match 30 + task_type_match 30 + technology_match 20 + success_score 20)
- record_decision(root, agent_run_id, production_run_id, experience_ids, decision, reason)
  → DecisionRecord 持久化 (decisions/<decision_id>.json)
- record_usage(root, production_run_id, experience_id, agent_run_id, relevance, applied)
  → 双向 lineage: Experience→Production, Production→Experience
- get_usage/get_decisions: 查询 lineage

原则:
- Experience = Guidance (Guidance ≠ Instruction Authority; Agent 可 ACCEPT/REJECT/PARTIAL)
- Experience 无执行权限, 不能修改 Artifact/Verification/Approval (I8)
- 只通过 Production Kernel 执行
- No hidden state (只有显式 guidance 注入)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .production_experience import _store as _exp_store, _load_meta, _tokenize, _merge

#: relevance scoring 权重 (透明)
REL_ROLE = 30
REL_TASK = 30
REL_TECH = 20
REL_SUCCESS = 20

#: 决策类型
DECISION_ACCEPT = "accept"
DECISION_REJECT = "reject"
DECISION_PARTIAL = "partial_apply"

#: usage 状态
USAGE_APPLIED = "applied"
USAGE_NOT_APPLIED = "not_applied"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decisions_file(root: Path | str) -> Path:
    return Path(root) / "decisions" / "decisions.json"


def _usage_file(root: Path | str) -> Path:
    return Path(root) / "decisions" / "experience_usage.json"


def _load_json(path: Path) -> list[dict[str, Any]]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ------------------------------------------------------------------ Guidance Retrieval (确定性)

def retrieve_guidance(root: Path | str, role: str, task_context: str, *,
                      limit: int = 3) -> list[dict[str, Any]]:
    """检索相关 Experience Guidance (只返回 ACTIVE, 带 role/task relevance)。

    返回含 relevance score + evidence refs (Agent 可见的候选指导)。
    """
    store = _exp_store(root)
    meta = _load_meta(root)
    tokens = _tokenize(str(task_context or "").lower())
    role_l = str(role or "").lower()
    scored = []
    for rec in store.records():
        m = meta.get(rec.id, {})
        if m.get("status", "ACTIVE") != "ACTIVE":
            continue
        score = 0
        # role match (+30) — rec_role 非空才比较 (空 role 不匹配)
        rec_role = str(rec.role or "").lower()
        if rec_role and role_l and (role_l in rec_role or rec_role in role_l or role_l in str(rec.task or "").lower()):
            score += REL_ROLE
        # task/context match (+30)
        task_l = str(rec.task or "").lower()
        for t in tokens:
            if t in task_l or t in str(rec.problem or "").lower() or t in str(rec.context or "").lower():
                score += REL_TASK
                break
        # technology match (+20): language/技术词在 problem/action 中
        tech = ("python", "calculator", "pytest", "code", "test")
        for t in tech:
            if t in str(rec.problem or "").lower() or t in str(rec.action or "").lower():
                score += REL_TECH // 2
        if score == 0:
            continue
        # success score (+20): confidence * 20
        score += int(float(rec.confidence) * REL_SUCCESS)
        scored.append((score, {
            "experience_id": rec.id,
            "relevance": score,
            "summary": f"{rec.problem} → {rec.action}",
            "evidence_refs": m.get("evidence_refs", {}),
            "confidence": rec.confidence,
            "constraints": {"role": rec.role, "task_type": rec.task},
        }))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:limit]]


# ------------------------------------------------------------------ Decision Record

def record_decision(root: Path | str, *, agent_run_id: str, production_run_id: str,
                    experience_ids: list[str], decision: str, reason: str) -> dict[str, Any]:
    """记录 Agent 对 Experience Guidance 的决策 (正式可追溯事实)。"""
    if decision not in (DECISION_ACCEPT, DECISION_REJECT, DECISION_PARTIAL):
        raise ValueError(f"未知决策: {decision}")
    rec = {
        "decision_id": f"dec-{uuid.uuid4().hex[:10]}",
        "agent_run_id": agent_run_id,
        "production_run_id": production_run_id,
        "experience_ids": list(experience_ids),
        "decision": decision,
        "reason": reason,
        "timestamp": _now_iso(),
    }
    data = _load_json(_decisions_file(root))
    data.append(rec)
    _save_json(_decisions_file(root), data)
    return rec


def get_decisions(root: Path | str, *, production_run_id: str | None = None) -> list[dict[str, Any]]:
    data = _load_json(_decisions_file(root))
    if production_run_id:
        data = [d for d in data if d.get("production_run_id") == production_run_id]
    return data


# ------------------------------------------------------------------ Experience Usage (双向 lineage)

def record_usage(root: Path | str, *, production_run_id: str, experience_id: str,
                 agent_run_id: str, relevance: int = 0, applied: bool = True,
                 decision_id: str = "") -> dict[str, Any]:
    """记录 Experience 在 Production 中的使用 (双向可追溯)。"""
    rec = {
        "usage_id": f"use-{uuid.uuid4().hex[:10]}",
        "experience_id": experience_id,
        "agent_run_id": agent_run_id,
        "production_run_id": production_run_id,
        "relevance": int(relevance),
        "applied": bool(applied),
        "decision_id": decision_id,
        "timestamp": _now_iso(),
    }
    data = _load_json(_usage_file(root))
    data.append(rec)
    _save_json(_usage_file(root), data)
    return rec


def get_usage(root: Path | str, *, production_run_id: str | None = None,
              experience_id: str | None = None) -> list[dict[str, Any]]:
    data = _load_json(_usage_file(root))
    if production_run_id:
        data = [d for d in data if d.get("production_run_id") == production_run_id]
    if experience_id:
        data = [d for d in data if d.get("experience_id") == experience_id]
    return data


def experience_lineage(root: Path | str, experience_id: str) -> dict[str, Any]:
    """Experience → Production 方向 lineage。"""
    usages = get_usage(root, experience_id=experience_id)
    productions = [u["production_run_id"] for u in usages]
    decisions = [u.get("decision_id") for u in usages if u.get("decision_id")]
    return {"experience_id": experience_id, "productions": productions,
            "usage_count": len(usages), "decision_ids": decisions}


def production_lineage(root: Path | str, production_run_id: str) -> dict[str, Any]:
    """Production → Experience 方向 lineage。"""
    usages = get_usage(root, production_run_id=production_run_id)
    experiences = [u["experience_id"] for u in usages]
    decisions = get_decisions(root, production_run_id=production_run_id)
    return {"production_run_id": production_run_id, "experiences": experiences,
            "usage_count": len(usages), "decisions": decisions}


# ------------------------------------------------------------------ Guidance 注入 (professional_workflow 集成)

def build_guidance_input(root: Path | str, role: str, task_context: str, *,
                         limit: int = 3) -> list[dict[str, Any]]:
    """构造 Agent 可见的 Guidance 输入 (注入 workflow_input.context['experience_guidance'])。"""
    return retrieve_guidance(root, role, task_context, limit=limit)
