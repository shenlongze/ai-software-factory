"""factory-console/production_experience.py — S14 Evidence-backed Production Experience.

从真实 Production Evidence + Evaluation 确定性提取生产经验 (非 LLM)。

- extract(root, production_run_id): 读取 ProductionRun + Evaluation → ExperienceRecord
  (evidence_refs/source_production_run_id/source_evaluation_id 必填)
- confidence: 透明公式 (evaluation 30 + final_verification 30 + lineage 20 + workspace 20)
- 幂等: 同 production_run_id → 同 experience (已存在返回现有)
- retrieve(context): 确定性关键词匹配 + ranking (无 vector), 只返回 ACTIVE
- lifecycle: ACTIVE / SUPERSEDED / INVALIDATED (store 层)
- record_outcome: success/failure count + confidence 更新 (可审计)

原则 (S14):
- Experience = derived knowledge, 不是事实源 (Event/Production 仍裁决事实)
- Experience 永远不能改变 Production/Artifact/Verification status
- 失败生产 → CANDIDATE (默认不检索推荐)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .memory.experience import (
    ExperienceRecord, make_record_id, SUCCESS_PATTERN, FAILURE_PATTERN, DEBUG_EXPERIENCE,
)
from .memory.experience_store import ExperienceStore
from .production_evaluation import evaluate as _evaluate, get_evaluation

#: 经验来源类型 (S14 只允许 PRODUCTION_DERIVED 自动进入 ACTIVE)
SOURCE_PRODUCTION_DERIVED = "PRODUCTION_DERIVED"

#: 检索 ranking 权重 (透明)
RANK_DOMAIN = 40
RANK_CONTEXT = 30
RANK_OBSERVATION = 20
RANK_CONFIDENCE = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _exp_file(root: Path | str) -> Path:
    return Path(root) / "memory" / "experiences.json"


def _meta_file(root: Path | str) -> Path:
    """扩展元数据 sidecar (ExperienceRecord 之外的 S14 字段)。"""
    return Path(root) / "memory" / "experiences_meta.json"


def _store(root: Path | str) -> ExperienceStore:
    return ExperienceStore(path=_exp_file(root))


def _load_meta(root: Path | str) -> dict[str, dict[str, Any]]:
    try:
        d = json.loads(_meta_file(root).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_meta(root: Path | str, meta: dict[str, dict[str, Any]]) -> None:
    p = _meta_file(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


# ------------------------------------------------------------------ 确定性提取

def extract(root: Path | str, production_run_id: str, *, force: bool = False) -> dict[str, Any]:
    """从 ProductionRun + Evaluation 确定性提取 Experience (幂等)。

    成功生产 (COMPLETED + verification PASS + lineage) → ACTIVE
    失败生产 → CANDIDATE (非推荐)
    """
    from .production_run import get_production_run
    from .node_runtime import get_node_run
    from .artifact_lifecycle import get_artifact

    run = get_production_run(root, production_run_id)
    if run is None:
        raise ValueError(f"ProductionRun 不存在: {production_run_id}")
    ev = _evaluate(root, production_run_id)
    store = _store(root)
    meta = _load_meta(root)

    # 幂等: 同 production_run 已存在 → 返回现有 (含 meta 扩展字段)
    if not force:
        for rid, m in meta.items():
            if m.get("source_production_run_id") == production_run_id:
                return _merge(store.get(rid), m)

    # 提取事实
    dims = ev["dimensions"]
    repair_count = ev.get("repair_count", 0)
    success = run.get("state") == "COMPLETED" and dims["verification"]["pass"]
    # 失败原因 (失败生产也提取, 但 CANDIDATE)
    failure_reason = ""
    if not success:
        for nr in run.get("node_runs", []):
            nrec = get_node_run(root, nr.get("run_id")) if nr.get("run_id") else None
            if nrec and nrec.get("failure_reason"):
                failure_reason = nrec["failure_reason"]
                break

    # evidence_refs (非空要求)
    evidence_refs = {
        "production_run_id": production_run_id,
        "evaluation_id": ev["evaluation_id"],
        "artifacts": run.get("artifacts", []),
        "node_runs": [nr.get("run_id") for nr in run.get("node_runs", []) if nr.get("run_id")],
    }

    # confidence (透明公式)
    confidence = 0
    if dims["completion"]["pass"]:
        confidence += 30
    if dims["verification"]["pass"]:
        confidence += 30
    if dims["lineage_integrity"]["pass"]:
        confidence += 20
    if dims["workspace_delivery"]["pass"]:
        confidence += 20

    # 观察/行动/结果 (确定性, 来自事实)
    if repair_count > 0:
        observation = f"production required {repair_count} repair(s) after verification failure"
        action = "automatic repair regenerated artifact and re-verified"
        record_type = DEBUG_EXPERIENCE
    elif success:
        observation = "production completed with verification passing on first attempt"
        action = "standard production pipeline executed successfully"
        record_type = SUCCESS_PATTERN
    else:
        observation = f"production failed: {failure_reason[:200]}"
        action = "production requires diagnosis and repair"
        record_type = FAILURE_PATTERN

    record = ExperienceRecord(
        id=f"exp-{uuid.uuid4().hex[:10]}",
        type=record_type,
        project=str(run.get("project_id") or ""),
        task=run.get("workflow_id") or "",
        agent="",
        role="",
        context=str(run.get("workflow_id") or "production"),
        problem=observation,
        action=action,
        result=f"state={run.get('state')} score={ev['overall_score']}",
        success=success,
        confidence=float(confidence) / 100.0,
        source=SOURCE_PRODUCTION_DERIVED,
        created_at=_now_iso(),
    )
    store.add(record)
    # 扩展字段 (sidecar meta)
    meta[record.id] = {
        "source_production_run_id": production_run_id,
        "source_evaluation_id": ev["evaluation_id"],
        "evidence_refs": evidence_refs,
        "status": "ACTIVE" if success else "CANDIDATE",
        "success_count": 0,
        "failure_count": 0,
        "created_at": record.created_at,
        "updated_at": _now_iso(),
    }
    _save_meta(root, meta)
    return _merge(record, meta[record.id])


def _merge(rec: Any, meta: dict[str, Any] | None) -> dict[str, Any]:
    """合并 ExperienceRecord + meta 扩展字段。"""
    d = rec.to_dict() if rec else {}
    if meta:
        d.update(meta)
    return d


# ------------------------------------------------------------------ Retrieval (确定性)

def retrieve(root: Path | str, context: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """确定性检索: 关键词匹配 + 透明 ranking。只返回 ACTIVE。"""
    store = _store(root)
    meta = _load_meta(root)
    ctx_lower = str(context or "").lower()
    # token 化 (中文 2-gram + 英文词)
    tokens = _tokenize(ctx_lower)
    scored = []
    for rec in store.records():
        m = meta.get(rec.id, {})
        status = m.get("status", "ACTIVE")
        if status != "ACTIVE":
            continue
        problem = str(rec.problem or "").lower()
        action = str(rec.action or "").lower()
        context_f = str(rec.context or "").lower()
        domain = str(rec.project or rec.task or "").lower()
        score = 0
        hit_tokens = 0
        for t in tokens:
            if t in problem or t in action:
                score += RANK_OBSERVATION
                hit_tokens += 1
            if t in context_f or t in domain:
                score += RANK_CONTEXT
                hit_tokens += 1
        if hit_tokens == 0:
            continue
        score += int(float(rec.confidence) * RANK_CONFIDENCE)
        scored.append((score, _merge(rec, m)))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:limit]]


def _tokenize(text: str) -> list[str]:
    """中文 2-gram + 英文词。"""
    import re

    tokens = []
    # 英文词
    tokens += [w for w in re.findall(r"[a-z][a-z0-9_]{1,}", text)]
    # 中文 2-gram
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    for chunk in cjk:
        if len(chunk) >= 2:
            tokens += [chunk[i:i + 2] for i in range(len(chunk) - 1)]
    return tokens


# ------------------------------------------------------------------ Lifecycle

def list_experiences(root: Path | str, status: str | None = None) -> list[dict[str, Any]]:
    store = _store(root)
    meta = _load_meta(root)
    out = []
    for rec in store.records():
        m = meta.get(rec.id, {})
        st = m.get("status", "ACTIVE")
        if status is None or st == status:
            out.append(_merge(rec, m))
    return out


def get_experience(root: Path | str, experience_id: str) -> dict[str, Any] | None:
    store = _store(root)
    meta = _load_meta(root)
    rec = store.get(experience_id)
    return _merge(rec, meta.get(experience_id)) if rec else None


def supersede(root: Path | str, old_id: str, new_id: str, *, reason: str = "") -> dict[str, Any]:
    """标记旧经验 SUPERSEDED (新经验替代)。"""
    store = _store(root)
    rec = store.get(old_id)
    if rec is None:
        raise ValueError(f"Experience 不存在: {old_id}")
    meta = _load_meta(root)
    m = meta.get(old_id, {})
    m["status"] = "SUPERSEDED"
    m["related_experience_id"] = new_id
    m["superseded_reason"] = reason
    m["updated_at"] = _now_iso()
    meta[old_id] = m
    _save_meta(root, meta)
    return _merge(rec, m)


def invalidate(root: Path | str, experience_id: str, *, reason: str = "") -> dict[str, Any]:
    """标记经验 INVALIDATED (被生产证据证明不可靠)。"""
    store = _store(root)
    rec = store.get(experience_id)
    if rec is None:
        raise ValueError(f"Experience 不存在: {experience_id}")
    meta = _load_meta(root)
    m = meta.get(experience_id, {})
    m["status"] = "INVALIDATED"
    m["invalidate_reason"] = reason
    m["updated_at"] = _now_iso()
    meta[experience_id] = m
    _save_meta(root, meta)
    return _merge(rec, m)


# ------------------------------------------------------------------ Outcome feedback

def record_outcome(root: Path | str, experience_id: str, production_run_id: str, *,
                   success: bool) -> dict[str, Any]:
    """记录经验在后续生产中的结果 (success/failure count + confidence 重算)。

    不覆盖原始 Production Evidence (只更新 derived experience)。
    """
    store = _store(root)
    rec = store.get(experience_id)
    if rec is None:
        raise ValueError(f"Experience 不存在: {experience_id}")
    meta = _load_meta(root)
    m = meta.get(experience_id, {})
    if success:
        m["success_count"] = int(m.get("success_count", 0)) + 1
    else:
        m["failure_count"] = int(m.get("failure_count", 0)) + 1
    sc = int(m.get("success_count", 0))
    fc = int(m.get("failure_count", 0))
    if sc + fc > 0:
        # 统计置信度 (一次成功 ≠ 100%)
        base = float(rec.confidence) * 100
        stat_conf = sc / (sc + fc) * 100
        m["confidence"] = round((base + stat_conf) / 200, 3)
    m["last_outcome_production"] = production_run_id
    m["updated_at"] = _now_iso()
    meta[experience_id] = m
    _save_meta(root, meta)
    return _merge(rec, m)
