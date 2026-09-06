"""factory-console/workflow_canonical_bridge.py — S44 Workflow → Canonical Production Truth 吸收。

断链修复: workflow_runner (真实生产链: WF-DESIGN/WF-APP → factory-exec agents →
dist zip) 完成后, 其成功/失败从未进入 frozen canonical P0 chain
(TASK-* → run-* → EXS-* → art-* → ver-* → EVD-*)。

本模块 = 极薄 adapter (单一收尾调用点 _thread_main 报告落盘后):
  Workflow finalize (report.json status)
      ↓ absorb_workflow_to_canonical()
      ↓ TASK-* (backlog, 幂等) → run-* → EXS-* → art-* → ver-* → EVD-*
      ↓ 幂等键 = workflow run_id (R{ms}) 经 EXS.prompt 标记 "workflow:{run_id}"

原则 (S44 §4/§5): 不建第二套 truth — 只复用 P0 domain services;
workflow 自身 report/progress = orchestration/adapter 保留。
失败安全: 吸收失败不覆盖 workflow 真实状态 (report 已落盘, 吸收独立)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _import_console(mod: str):
    try:
        return __import__(f"factory_console.{mod}", fromlist=["*"])
    except ImportError:
        import importlib

        return importlib.import_module(mod)


def _exs_exists(root: Path | str, task_id: str) -> bool:
    """幂等探测: 该 workflow task (TASK-workflow-{run_id}) 是否已有 EXS。"""
    try:
        import json

        p = Path(root) / "exec" / "execution_records.json"
        if not p.is_file():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("records", [])
        return any(str(r.get("task_id") or "") == task_id for r in items)
    except Exception:  # noqa: BLE001 — 探测失败 → 不阻断 (幂等由再查覆盖)
        return False


def _verification_result(report: dict[str, Any]) -> tuple[str, str, str]:
    """workflow report → verification 事实 (真实 acceptance, 非伪造)。

    返回 (result, method, detail):
    - completed + acceptance.all_pass → PASS (method=workflow_acceptance)
    - completed 但 acceptance 有缺 → FAIL (诚实 — 不因 workflow COMPLETED 自动 PASS)
    - failed/cancelled → FAIL (execution 未成功)
    """
    status = str(report.get("final_workflow_status") or report.get("status") or "")
    if status != "COMPLETED":
        return "fail", "workflow_execution", f"workflow status={status}"
    acc = report.get("acceptance") or {}
    if acc.get("all_pass"):
        return "pass", "workflow_acceptance", "workflow acceptance all_pass"
    # 诚实 FAIL: 列出缺项 (不伪造 successful completion — S44 AC6)
    missing = [k for k, v in acc.items() if v is False]
    fails = [k for k, v in acc.items()
             if isinstance(v, dict) and any(x == "NOT-VALIDATED" for x in v.values())]
    return "fail", "workflow_acceptance", (
        f"workflow completed but acceptance gaps: "
        f"{missing[:6]} {fails[:6]}").strip()


def _dist_artifact(report: dict[str, Any], project_dir: Path) -> Optional[Path]:
    """找到真实交付物 (dist/app-*.zip) — absorption 的物证。"""
    dist = project_dir.parent / "dist"
    if dist.is_dir():
        zips = sorted(dist.glob("*.zip"))
        if zips:
            return zips[-1]
    return None


def absorb_workflow_to_canonical(
    *,
    org_dir: Path | str,
    project_id: str,
    workflow_run_id: str,
    status: str,  # "completed" / "failed" / "cancelled"
    report: dict[str, Any],
    project_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Workflow finalize → canonical P0 吸收 (幂等, 失败安全)。

    返回 {absorbed: bool, task_id, task_run_id, exs_id, artifact_ids,
    verification_id, evidence_ids} — 失败返回 {"absorbed": False, ...}。
    """
    root = Path(org_dir).parent
    pdir = Path(project_dir) if project_dir else None
    ok = bool(status == "completed" and
              str(report.get("final_workflow_status") or "") == "COMPLETED")
    # 确定性 task_id (workflow run 作 TASK FK — 幂等键基础; backlog 同步
    # 由 workflow 既有机制负责, 吸收层不建第二套 task)
    task_id = f"TASK-workflow-{workflow_run_id}"
    # 幂等: 该 workflow task 已吸收 (已有 EXS) → skip
    if _exs_exists(root, task_id):
        return {"absorbed": False, "reason": "already_absorbed",
                "workflow_run_id": workflow_run_id, "task_id": task_id}

    try:
        nr = _import_console("node_runtime")
        ex = _import_console("external_executor.executor")
        # 注册执行节点 (幂等; 真实 E2E 中可能已注册)
        try:
            nr.register_node(root, node_id="task-execution", name="task-execution",
                             node_type="task-execution")
        except Exception:  # noqa: BLE001 — 已注册/失败安全
            pass
        run = nr.create_node_run(root, "task-execution", task_id=task_id,
                                 trigger="workflow")
        run_id = str(run.get("run_id") or "")
        rec = ex.record_invocation(
            root, executor_id="factory-exec", mode="blackbox",
            host_agent="", prompt=f"workflow:{workflow_run_id}",
            project_dir=str(pdir) if pdir else "",
            exit_code=0 if ok else 1,
            output=str((report.get("totals") or {}).get("calls") or 0),
            error=str(report.get("errors") or "")[:200] if not ok else "",
            command="workflow_runner", duration_ms=0,
            task_id=task_id, task_run_id=run_id)
        exs_id = str(rec.get("result_id") or "")
        ver_res, method, detail = _verification_result(report)
        # 真实验证内容 (acceptance 摘要) → EVD 支撑
        import json as _json

        out = nr.finalize_node_run(
            root, run_id, success=ok, exs_id=exs_id,
            output=f"workflow {status}: {detail[:300]}",
            actor="workflow", note=f"absorbed workflow {workflow_run_id}",
            verification={"method": method, "result": ver_res,
                          "stdout": _json.dumps(report.get("acceptance") or {},
                                                ensure_ascii=False)[:500]},
            artifact_root=root,
        )
        art_ids = [str(a) for a in (out.get("artifact_ids") or [])
                   if isinstance(a, str)] if isinstance(out, dict) else []
        if not art_ids and isinstance(out, dict) and out.get("artifact_id"):
            art_ids = [str(out["artifact_id"])]
        ver = out.get("verification") or {}
        return {
            "absorbed": True,
            "task_id": task_id,
            "task_run_id": run_id,
            "exs_id": exs_id,
            "artifact_ids": art_ids,
            "verification_id": str(ver.get("verification_id") or "") if isinstance(ver, dict) else "",
            "evidence_ids": [],
            "workflow_run_id": workflow_run_id,
            "verification_status": ver_res,
        }
    except Exception as exc:  # noqa: BLE001 — 吸收失败: 不伪造, 返回失败
        return {"absorbed": False, "reason": f"absorption_error: {type(exc).__name__}: {exc}",
                "workflow_run_id": workflow_run_id}
