"""factory-console/experience_bridge.py — P2-C Experience Bridge (唯一 writer)。

契约 (docs/audits/2026-09-06-p2c-experience-bridge-contract/, 21 份含勘误):
- Canonical Experience = exp-* (memory/experience_store.json) — 唯一 SSOT
- 唯一 writer = ExperienceBridge (本模块) — CLI/API/WebUI/agent 禁止直写 store
- Experience = Production/Release Truth 的**单向派生** (anchor provenance):
  只存 task_run_id/exs_id/release_id/source_id (Model B), 其余经 canonical
  reverse_trace 获取; 绝不反向写生产
- 幂等: (source, source_id) 唯一 — 同 fact 重复触发 → 返回已有 exp (1→1)
- Trigger: finalize 终态后 (execution) + RELEASE 终态后 (release) — 调用侧接线
- Legacy: 既有 84 条 (M3, 无 FK) 不迁移; intelligence/experiences.json
  (85, factory-core S9) = LEGACY 隔离 (本模块不读不写)
- source 语义: "execution" / "release"; type 沿用 SUCCESS_PATTERN /
  FAILURE_PATTERN (成功/失败语义, 不把失败伪装成功)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _import_console(mod: str):
    try:
        return __import__(f"factory_console.{mod}", fromlist=["*"])
    except ImportError:
        import importlib

        return importlib.import_module(mod)


def _store(root: Path | str):
    """memory/experience_store.json 的 ExperienceStore (canonical SSOT)。"""
    m = _import_console("memory.experience_store")
    return m.ExperienceStore.from_workspace(Path(root))


def _find(root: Path | str, source: str, source_id: str):
    """按 (source, source_id) 查已存在经验 (幂等键)。"""
    try:
        recs = _store(root).records()
    except Exception:  # noqa: BLE001
        recs = []
    for r in recs:
        d = r.to_dict() if hasattr(r, "to_dict") else r
        if str(d.get("source") or "") == source and str(d.get("source_id") or "") == source_id:
            return d
    return None


def record(root: Path | str, *, source: str, source_id: str,
           type_: str, success: bool,
           task_run_id: str = "", exs_id: str = "", release_id: str = "",
           project: str = "", task: str = "", agent: str = "",
           context: str = "", problem: str = "", action: str = "",
           result: str = "", confidence: float = 0.5,
           actor: str = "") -> dict[str, Any]:
    """ExperienceBridge.record — 唯一写入入口 (幂等)。

    (source, source_id) 已存在 → 返回现有 (绝不重复 — 1→1)。
    source/source_id 必填; anchors 由调用方提供真实 canonical FK。
    """
    if not source or not source_id:
        raise ValueError("experience record requires source and source_id")
    existing = _find(root, source, source_id)
    if existing is not None:
        return existing
    m = _import_console("memory.experience")
    rec = m.ExperienceRecord(
        type=type_,
        project=str(project or ""),
        task=str(task or ""),
        agent=str(agent or ""),
        role="",
        context=str(context or "")[:500],
        problem=str(problem or "")[:500],
        action=str(action or "")[:500],
        result=str(result or "")[:500],
        success=bool(success),
        confidence=float(confidence or 0.5),
        source=source,
        task_run_id=str(task_run_id or ""),
        exs_id=str(exs_id or ""),
        release_id=str(release_id or ""),
        source_id=str(source_id or ""),
    )
    store = _store(root)
    stored = store.add(rec)
    return stored.to_dict() if hasattr(stored, "to_dict") else stored


# ---------------------------------------------------------------------------
# 执行经验 (Trigger-1: finalize 终态后 — 调用侧接线)
# ---------------------------------------------------------------------------


def record_execution(root: Path | str, *, task_run_id: str, exs_id: str,
                     success: bool, ver_status: str = "",
                     project: str = "", task: str = "",
                     actor: str = "") -> dict[str, Any]:
    """P0 执行终态 → exp-* (单向派生; 失败安全 — 不阻断调用方)。

    source="execution", source_id="{task_run_id}:{exs_id}".
    成功 + ver PASS → SUCCESS_PATTERN; 否则 FAILURE_PATTERN (不伪装成功)。
    """
    if not task_run_id or not exs_id:
        return {}  # 无 canonical anchor → 不记录 (禁止字符串推断)
    ok = bool(success) and str(ver_status or "") in ("", "PASS")
    type_ = "SUCCESS_PATTERN" if ok else "FAILURE_PATTERN"
    try:
        return record(root, source="execution",
                      source_id=f"{task_run_id}:{exs_id}",
                      type_=type_, success=ok,
                      task_run_id=task_run_id, exs_id=exs_id,
                      project=str(project or ""), task=str(task or ""),
                      agent=str(actor or ""),
                      result=("success" if ok else
                              (f"verification={ver_status}" if ver_status else "execution failed")),
                      confidence=0.9 if ok else 0.8,
                      actor=actor)
    except Exception:  # noqa: BLE001 — bridge 失败不阻断生产链
        return {}


# ---------------------------------------------------------------------------
# Release 经验 (Trigger-2: RELEASE 终态后 — 调用侧接线)
# ---------------------------------------------------------------------------


def record_release(root: Path | str, release_id: str, *,
                   outcome: str = "RELEASED", gate_missing: list[str] | None = None,
                   actor: str = "") -> dict[str, Any]:
    """P2-A Release 终态 → exp-* (单向派生; 失败安全)。

    source="release", source_id="{release_id}".
    RELEASED → SUCCESS_PATTERN; REJECTED/REVOKED/SUPERSEDED → FAILURE_PATTERN
    (release 决策经验 — 不复制 execution exp)。
    """
    if not release_id:
        return {}
    ok = str(outcome or "").upper() == "RELEASED"
    type_ = "SUCCESS_PATTERN" if ok else "FAILURE_PATTERN"
    try:
        return record(root, source="release", source_id=f"{release_id}",
                      type_=type_, success=ok,
                      release_id=release_id,
                      result=f"release {outcome}",
                      problem="; ".join(gate_missing or []) if not ok else "",
                      confidence=0.9 if ok else 0.8,
                      actor=actor)
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Reverse trace (exp → canonical production/release → product)
# ---------------------------------------------------------------------------


def trace_experience(root: Path | str, exp_id: str) -> dict[str, Any]:
    """exp-* → 生产事实 (纯 FK, 无推断)。

    返回 exp 记录 + anchor 解析结果:
      execution: run/EXS 存在性 + task/plan/prd/req/disc/idea (复用 P1 reverse)
      release:   RELEASE 记录 + gate
    """
    out: dict[str, Any] = {"experience": None, "release": None,
                           "run": None, "task": None, "plan": None,
                           "prd": None, "idea": None, "chain": []}
    try:
        recs = _store(root).records()
        exp = None
        for r in recs:
            d = r.to_dict() if hasattr(r, "to_dict") else r
            if str(d.get("id") or "") == exp_id:
                exp = d
                break
        if exp is None:
            return out
        out["experience"] = exp
        out["chain"].append(("experience", exp_id))
        rid = str(exp.get("release_id") or "")
        if rid:
            rt = _import_console("release_truth")
            rel = rt.get_release(root, rid)
            if rel:
                out["release"] = rel
                out["chain"].append(("release", rid))
                # release → task → product
                tr = rt.trace_release(root, rid)
                out["task"] = tr.get("task")
                out["plan"] = tr.get("plan")
                out["prd"] = tr.get("prd")
                out["idea"] = tr.get("idea")
                for k, v in tr.get("chain", []):
                    if (k, v) not in out["chain"]:
                        out["chain"].append((k, v))
                return out
        run_id = str(exp.get("task_run_id") or "")
        if run_id:
            nr = _import_console("node_runtime")
            run = nr.get_node_run(root, run_id)
            if run:
                out["run"] = run
                out["chain"].append(("task_run", run_id))
                task_id = str(run.get("task_id") or "")
                if task_id:
                    pt = _import_console("product_truth")
                    tr = pt.reverse_trace(root, task_id)
                    out["task"] = tr.get("task")
                    out["plan"] = tr.get("plan")
                    out["prd"] = tr.get("prd")
                    out["idea"] = tr.get("idea")
                    for k, v in tr.get("chain", []):
                        if (k, v) not in out["chain"]:
                            out["chain"].append((k, v))
    except Exception:  # noqa: BLE001 — trace 失败安全
        pass
    return out
