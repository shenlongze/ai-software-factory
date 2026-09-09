"""factory-console/golden_path.py — Golden Path 编排域 (S1 第 2 刀: 执行收敛)。

打通真链 (Golden Path §4/§16-§20, CT 断层 F1/F2 收敛):
```
Product Understanding (conversation-scoped)
  → PRD (application_formalization — structured, versioned, provenance)
  → User Approval ("就按这个做" → approve_prd)
  → Multi-level Task Tree (task_decomposition — canonical 树域)
  → Development Plan (product_truth PLAN-* — 叶级任务, prd provenance)
  → User Approval (approve_plan)
  → Production (production_run 图编排 → node_runtime.execute_node_run → 真实 executor)
```

边界 (Golden Path §3/§20/§25 + S1-G9):
- 计划级执行统一收敛到 production_run 图编排 (register_workflow →
  create_production_run → execute_production_run); 单节点内核 =
  node_runtime.execute_node_run (事件唯一发射点)。不建第二套
  Plan/Task/Production Truth。
- Task Tree 是工作组织结构; Loop 是执行语义 (node_runtime.execute_node_run)。
- 拆解: 生产接 LLM decomposer (注入), 失败/非法 → 确定性模板兜底
  (degraded 诚实标注)。
- **Production Gate**: execute 前必须存在 user-approved PRD + user-approved Plan。
- Intent 不是产品生命周期 Truth: 本模块无 Intent。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from factory_console import product_truth as pt
from factory_console import product_understanding as pu
from factory_console import application_formalization as fmt
from factory_console import task_decomposition as td

MAX_PLAN_TASKS = 200


class GoldenPathError(ValueError):
    """Golden Path 流程错误 (缺前置/未批准/状态非法)。"""


# ------------------------------------------------------------------ 阶段查询

def path_status(root: str, conversation_id: str) -> dict[str, Any]:
    """当前 Golden Path 阶段总览 (供 UI/CLI/测试断言 Truth)。"""
    prds = fmt.list_prds(root, conversation_id)
    snap = pu.understanding_snapshot(root, conversation_id)
    approved_prd = next((p for p in prds if p.get("status") == "approved"),
                        None)
    plans = (pt.list_plans(root, prd_id=approved_prd["id"])
             if approved_prd else [])
    approved_plans = [p for p in plans if p.get("status") == "approved"]
    tree_summary = None
    if approved_plans:
        tree_summary = td.tree_summary(
            td.load_task_tree(root, approved_plans[-1]["id"]))
    return {
        "conversation_id": conversation_id,
        "understanding_version": snap["version"],
        "fact_count": len(snap["facts"]),
        "prds": [
            {"id": p["id"], "version": p["version"], "status": p["status"],
             "source_product_understanding_version":
                 p.get("source_product_understanding_version")}
            for p in prds
        ],
        "prd_count": len(prds),
        "approved_prd": approved_prd,
        "plans": [
            {"id": p["id"], "status": p["status"], "goal": p.get("goal", "")}
            for p in plans
        ],
        "tree": tree_summary,
    }


def plan_tree(root: str, plan_id: str) -> dict[str, Any]:
    """只读: 某 Plan 的多级任务树 (缺失 → exists=False, 不抛)。"""
    return td.tree_summary(td.load_task_tree(root, plan_id))


# ------------------------------------------------------------------ PRD → approval

# ------------------------------------------------------------------ 认知段审计 (M2a, S1-5)

def _emit_cognitive(root: str, event_type: str, *, conversation_id: str,
                    actor: str, evidence: dict[str, Any]) -> None:
    """认知段审计事件 (PRD/Plan/理解) — 失败安全, 复用 AuditStore。

    trace_id = conversation_id (全链可关联); 审计故障不中断业务。
    """
    try:
        from .audit.audit_event import EVENT_TYPES, AuditEvent
        from .audit.audit_store import AuditStore
        if str(event_type) not in EVENT_TYPES:
            return
        store = AuditStore(workspace=str(root))
        # evidence 参数是 list 语义 (AuditEvent); dict 详情存 metadata
        detail = dict(evidence or {})
        # 取首个存在的业务 id (prd_id/plan_id/id) 包成单元素列表 — 防按字符迭代
        first_id = None
        for k in ("prd_id", "plan_id", "id"):
            v = detail.get(k)
            if v:
                first_id = str(v)
                break
        ev_list = ([{"type": str(event_type), "id": first_id}]
                   if first_id else [])
        event = AuditEvent.create(
            str(event_type),
            trace_id=str(conversation_id),
            project_id=str(conversation_id),
            actor_id=str(actor or "human"),
            actor_type="human",
            action="cognitive",
            source="golden_path",
            decision="allow",
            decision_reason="golden_path_cognitive",
            evidence=ev_list,
            metadata=detail,
            result={"ok": True},
        )
        store.append(event)
    except Exception:  # noqa: BLE001 — 审计故障不中断业务 (同 AuditEmitter 纪律)
        pass


def generate_prd(root: str, conversation_id: str, *, actor: str = "") -> dict[str, Any]:
    """Understanding → PRD v1 (须已有 Understanding; 已有 draft 则更新为新 version)。

    幂等语义: 无 PRD → create; 有 draft → update (重新从最新 Understanding 派生)。
    """
    prds = fmt.list_prds(root, conversation_id)
    drafts = [p for p in prds if p.get("status") == "draft"]
    if drafts:
        obj = fmt.update_prd(root, conversation_id, drafts[-1]["id"], actor=actor)
    else:
        obj = fmt.create_prd(root, conversation_id, actor=actor)
    # M2a: PRD_CREATED 审计事件 (成功路径)
    _emit_cognitive(root, "PRD_CREATED", conversation_id=conversation_id,
                    actor=actor,
                    evidence={"prd_id": obj.get("id"), "version": obj.get("version"),
                              "status": obj.get("status"),
                              "source_understanding_version":
                                  obj.get("source_product_understanding_version")})
    return obj


def approve_prd(root: str, conversation_id: str, prd_id: str, *,
                actor: str = "") -> dict[str, Any]:
    """用户确认 PRD (Golden Path §18: PRD generated ≠ PRD approved)。"""
    prd = fmt.get_prd(root, conversation_id, prd_id)
    if prd is None:
        raise GoldenPathError(f"PRD 不存在: {prd_id}")
    if prd.get("status") != "draft":
        raise GoldenPathError(
            f"PRD {prd_id} 当前 status={prd.get('status')} — 仅 draft 可确认")
    obj = fmt.approve_prd(root, conversation_id, prd_id, actor=actor)
    # M2a: PRD_APPROVED 审计事件
    _emit_cognitive(root, "PRD_APPROVED", conversation_id=conversation_id,
                    actor=actor,
                    evidence={"prd_id": obj.get("id"), "version": obj.get("version"),
                              "status": obj.get("status")})
    return obj


def _prd_goal(prd: dict[str, Any]) -> str:
    content = prd.get("content", {}) if isinstance(prd.get("content"), dict) else {}
    overview = content.get("overview", {}) if isinstance(content, dict) else {}
    return str(overview.get("problem") or overview.get("name")
               or prd.get("id"))[:300]


# ------------------------------------------------------------------ PRD → Task Tree → Plan

def generate_plan(root: str, conversation_id: str, *, actor: str = "",
                  decompose: bool = True,
                  decomposer: Callable[[dict[str, Any]], dict[str, Any]]
                  | None = None) -> dict[str, Any]:
    """Approved PRD → 多级任务树 → Development Plan (product_truth PLAN-*, 叶级)。

    decompose=True: task_decomposition.decompose_prd (interpreter=decomposer,
    None → 确定性模板); 树落盘 task_trees/{plan_id}.json, PLAN.tasks = 叶摘要。
    decompose=False: 兼容旧单层路径 (不落树; 主要供无 PRD content 的退化场景)。
    """
    prds = fmt.list_prds(root, conversation_id)
    approved = [p for p in prds if p.get("status") == "approved"]
    if not approved:
        raise GoldenPathError(
            "尚无 approved PRD — 用户确认 PRD 后才能生成 Development Plan")
    prd = approved[-1]

    if decompose:
        tree = td.decompose_prd(prd, interpreter=decomposer)
        tasks, order = td.tree_to_plan(tree)
        if not tasks:
            raise GoldenPathError(
                "任务拆解未产生可执行叶任务 — 无法生成 Plan")
        if len(tasks) > MAX_PLAN_TASKS:
            raise GoldenPathError(
                f"任务树叶数 {len(tasks)} 超过上限 {MAX_PLAN_TASKS} — 拆解过细")
        goal = _prd_goal(prd)
        plan = pt.create_plan(
            root,
            project_id=conversation_id,
            prd_id=prd["id"],
            prd_version=int(prd.get("version") or 1),
            goal=goal,
            tasks=tasks,
            order=order,
            acceptance=[str(t.get("title") or t.get("id"))[:200] for t in tasks],
            ask_approval=True,
            actor=actor or "human",
            idempotency_key=f"gp-plan:{conversation_id}:{prd['id']}:v{prd.get('version')}",
        )
        tree["plan_id"] = plan["id"]
        td.save_task_tree(root, plan["id"], tree)
        # M2a: PLAN_CREATED 审计事件
        _emit_cognitive(root, "PLAN_CREATED", conversation_id=conversation_id,
                        actor=actor,
                        evidence={"plan_id": plan.get("id"),
                                  "tasks": len(plan.get("tasks") or []),
                                  "tree_id": plan.get("id"),
                                  "decomposer": tree.get("decomposer"),
                                  "degraded": bool(tree.get("degraded"))})
        return plan

    # 兼容: 旧单层平铺 (decompose=False, 不落树)
    tasks = _derive_plan_tasks(prd)
    if not tasks:
        raise GoldenPathError("PRD 无可派生任务 — 无法生成 Plan")
    plan = pt.create_plan(
        root,
        project_id=conversation_id,
        prd_id=prd["id"],
        prd_version=int(prd.get("version") or 1),
        goal=_prd_goal(prd),
        tasks=tasks,
        order=[t["id"] for t in tasks],
        acceptance=[str(t.get("title") or t.get("id"))[:200] for t in tasks],
        ask_approval=True,
        actor=actor or "human",
        idempotency_key=f"gp-plan:{conversation_id}:{prd['id']}:v{prd.get('version')}",
    )
    # M2a: PLAN_CREATED 审计事件 (单层兼容路径)
    _emit_cognitive(root, "PLAN_CREATED", conversation_id=conversation_id,
                    actor=actor,
                    evidence={"plan_id": plan.get("id"),
                              "tasks": len(plan.get("tasks") or []),
                              "decomposer": "flat", "degraded": False})
    return plan


def _derive_plan_tasks(prd: dict[str, Any]) -> list[dict[str, Any]]:
    """PRD content → 单层 task 列表 (兼容路径; 新主链走 task_decomposition)。"""
    content = prd.get("content", {}) if isinstance(prd.get("content"), dict) else {}
    overview = content.get("overview", {}) if isinstance(content, dict) else {}
    goal = str(overview.get("name") or overview.get("problem") or "")[:120]
    tasks: list[dict[str, Any]] = []
    seq = 0

    def _task(title: str, kind: str) -> None:
        nonlocal seq
        seq += 1
        tasks.append({"id": f"T{seq}", "title": str(title)[:200], "kind": kind})

    _task(f"项目搭建: {goal}" if goal else "项目搭建", "setup")
    for f in content.get("functional_requirements", []) if isinstance(
            content, dict) else []:
        _task(f"实现功能: {f}", "feature")
    for c in content.get("constraints", []) if isinstance(content, dict) else []:
        _task(f"满足约束: {c}", "constraint")
    for d in content.get("decisions", []) if isinstance(content, dict) else []:
        _task(f"落实决定: {d}", "decision")
    _task("验证与交付", "verify")
    return tasks


def approve_plan(root: str, plan_id: str, *, actor: str = "") -> dict[str, Any]:
    """用户确认 Development Plan (叶级; Golden Path §20)。"""
    plan = pt.get_plan(root, plan_id)
    if plan is None:
        raise GoldenPathError(f"Plan 不存在: {plan_id}")
    if plan.get("status") != "pending":
        raise GoldenPathError(
            f"Plan {plan_id} 当前 status={plan.get('status')} — 仅 pending 可确认")
    obj = pt.approve_plan(root, plan_id, actor=actor)
    # M2a: APPROVAL_DECIDED (decision=approve, plan_id) — trace 用 plan.project_id
    # (canonical 链 = conversation_id; legacy 空则不关联 trace)
    conv_id = str(plan.get("project_id") or "")
    _emit_cognitive(root, "APPROVAL_DECIDED",
                    conversation_id=conv_id or plan_id, actor=actor,
                    evidence={"decision": "approve", "plan_id": plan_id,
                              "prd_id": plan.get("prd_id"),
                              "status": obj.get("status")})
    return obj


# ------------------------------------------------------------------ Production Gate

def _require_gates(root: str, conversation_id: str) -> tuple[dict[str, Any],
                                                             dict[str, Any]]:
    """Production Gate: 必须有 approved PRD + approved Plan (按 conversation 溯源)。"""
    prds = fmt.list_prds(root, conversation_id)
    approved_prds = [p for p in prds if p.get("status") == "approved"]
    if not approved_prds:
        raise GoldenPathError(
            "Production Gate 拒绝: 尚无用户确认的 PRD。"
            "流程: 生成 PRD → 用户确认('就按这个做') → Plan → 用户确认 → 才可执行。")
    prd = approved_prds[-1]
    plans = pt.list_plans(root, prd_id=prd["id"])
    approved_plans = [p for p in plans if p.get("status") == "approved"]
    if not approved_plans:
        raise GoldenPathError(
            "Production Gate 拒绝: 该 PRD 尚无用户确认的 Development Plan。"
            "请先确认 Plan 后再执行。")
    return prd, approved_plans[-1]


# ------------------------------------------------------------------ 执行 (production_run 收敛)

def _noop_guard(leaf: dict[str, Any], workspace_dir: Path,
                result: dict[str, Any]) -> dict[str, Any]:
    """NO_OP/完成态识别: executor exit 0 但无变更, 且 expected_files 已存在
    → COMPLETED + evidence (防 2/7 复发: 重叠/已完成任务不得伪装成失败)。"""
    if result.get("ok"):
        return result
    err = str(result.get("error") or "")
    if "未产生新文件" not in err:
        return result
    expected = [str(x) for x in (leaf.get("expected_files") or [])]
    if not expected:
        return result
    missing = [f for f in expected
               if not (workspace_dir / f).exists()]
    if missing:
        return result
    return {
        "ok": True,
        "output": result.get("output") or "",
        "error": "",
        "artifact_type": str(result.get("artifact_type") or "code_change"),
        "verification": {
            "result": "PASS",
            "source": "no-change: already satisfied (expected files present)",
            "error": "",
            "new_files": [],
        },
    }


def _capability_executor(leaf: dict[str, Any], capability_fn: Any,
                         workspace_dir: Path | None = None
                         ) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """测试/宿主注入 capability → executor_fn 契约 (叶上下文注入 input.task)。

    含 NO_OP guard: capability 报"未产生新文件"但 expected_files 已存在 →
    COMPLETED (与默认真实 executor 同语义, 防 2/7 复发)。
    """
    ws = Path(workspace_dir or ".")

    def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
        inp = dict(input_data or {})
        inp["task"] = dict(leaf)
        r = capability_fn(inp) or {}
        ok = bool(r.get("ok"))
        wrapped = {
            "ok": ok,
            "output": r.get("output") or {},
            "error": r.get("error") or "",
            "artifact_type": str(r.get("artifact_type")
                                 or inp.get("artifact_type") or "code_change"),
            "verification": r.get("verification") or {
                "result": "PASS" if ok else "FAIL",
                "source": "capability_fn",
                "error": "" if ok else (r.get("error")
                                        or "capability returned ok=False"),
            },
        }
        if not ok and "未产生新文件" in str(wrapped.get("error") or ""):
            expected = [str(x) for x in (leaf.get("expected_files") or [])]
            missing = [f for f in expected if not (ws / f).exists()]
            if expected and not missing:
                return {
                    "ok": True,
                    "output": wrapped.get("output") or "",
                    "error": "",
                    "artifact_type": wrapped.get("artifact_type") or "code_change",
                    "verification": {
                        "result": "PASS",
                        "source": "no-change: already satisfied "
                                  "(expected files present)",
                        "error": "",
                        "new_files": [],
                    },
                }
        return wrapped

    return _fn


def _default_executor_factory(root: str, conversation_id: str,
                              executor_name: str = ""
                              ) -> Callable[[str],
                                            Callable[[dict[str, Any]],
                                                     dict[str, Any]]] | None:
    """默认真实 executor factory: 每叶 build_real_executor + NO_OP guard。

    无可用外部 executor → None (执行层按叶诚实 FAILED)。
    """
    from factory_console.production_runtime import build_real_executor

    workspace = Path(root) / "golden_path_workspace" / str(conversation_id)
    base = build_real_executor(root, executor_name=executor_name,
                               workspace_dir=str(workspace))
    if base is None:
        return None
    leaf_by_id: dict[str, dict[str, Any]] = {}

    def _factory(node_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        leaf = leaf_by_id.get(node_id, {})

        def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
            inp = dict(input_data or {})
            if leaf:
                inp["task"] = dict(leaf)
            return _noop_guard(leaf, workspace, base(inp))

        return _fn

    _factory.set_leaves = lambda leaves: leaf_by_id.update(  # type: ignore[attr-defined]
        {n.get("id"): n for n in leaves if n.get("id")})
    return _factory


def _run_result_from_fn(root: str, executor_fn: Any, leaf: dict[str, Any],
                        conversation_id: str, plan: dict[str, Any],
                        prd: dict[str, Any]) -> dict[str, Any]:
    """单叶定向: 直接跑 executor_fn (不经 execute_task, 供定向重试)。"""
    from factory_console.node_runtime import (  # noqa: PLC0415
        create_node_run, execute_node_run, register_node,
    )

    try:
        register_node(root, node_id=leaf["id"],
                      name=str(leaf.get("title") or leaf["id"])[:120],
                      node_type="plan_task",
                      input_contract={"goal": plan.get("goal", "")},
                      output_contract={"deliverable": "verified"},
                      execution_policy={"actor": "human",
                                        "source": "golden-path"})
    except Exception:  # noqa: BLE001 — 幂等 upsert 已存在可复用
        pass
    try:
        nr = create_node_run(str(root), node_id=leaf["id"],
                             input_data={"task": dict(leaf),
                                         "goal": plan.get("goal", ""),
                                         "approved_plan_id": plan.get("id")},
                             trigger="golden-path:leaf")
        run = execute_node_run(root, nr["run_id"], executor_fn=executor_fn,
                               executor_name="leaf",
                               artifact_root=str(root), max_attempts=1)
    except Exception as exc:  # noqa: BLE001 — 内核异常 → 诚实 FAILED
        return {"state": "FAILED", "run_id": None, "artifact_id": None,
                "evidence": {}, "verification": "FAIL",
                "error": f"execute_node_run exception: {exc}", "output": None}
    vref = run.get("verification")
    verification_status = "FAIL"
    evidence = {}
    if isinstance(vref, dict):
        verification_status = vref.get("status") or "FAIL"
        if vref.get("verification_id"):
            evidence["verification_id"] = vref["verification_id"]
    if run.get("run_id"):
        evidence["node_run_id"] = run["run_id"]
    return {"run_id": run.get("run_id"), "state": run.get("state"),
            "artifact_id": run.get("artifact_id"), "evidence": evidence,
            "verification": verification_status,
            "error": run.get("failure_reason"), "output": None}


def execute_approved(root: str, conversation_id: str, *,
                     actor: str = "human", capability_fn: Any = None,
                     task_id: str = "",
                     executor_fn: Any = None,
                     real_executor: bool = False,
                     executor_name: str = "",
                     executor_factory: Any = None) -> dict[str, Any]:
    """Approved Plan → Production (唯一 Golden Path 生产入口, S1 收敛)。

    统一到 production_run 图编排: tree 叶 → register_workflow(workflow_id=plan_id)
    → create_production_run → execute_production_run (串行、依赖感知、BLOCKED)。
    执行能力解析: executor_factory(node_id)->fn > capability_fn (全叶注入)
    > 默认真实 executor (codex/claude/hermes); 无可用 → 叶诚实 FAILED。
    task_id 指定 → 单叶执行 (兼容/定向, 走 execute_task 单节点内核)。

    返回 {plan_id, prd_id, executed[], production_run_id, state}
    """
    from factory_console.node_runtime import get_node_run  # noqa: PLC0415
    from factory_console.production_run import (  # noqa: PLC0415
        create_production_run, execute_production_run, register_workflow,
    )

    _prd, plan = _require_gates(root, conversation_id)
    tree = td.load_task_tree(root, plan["id"])
    leaves = (td.tree_leaves(tree) if tree else list(plan.get("tasks") or []))
    if not leaves:
        raise GoldenPathError("Approved Plan 无任务叶 — 无法执行")
    order = list(plan.get("order") or [n.get("id") for n in leaves])
    by_id = {n.get("id"): n for n in leaves}
    leaves_ordered = [by_id[i] for i in order if i in by_id]

    # 单叶定向 (task_id)
    if task_id:
        leaf = by_id.get(task_id)
        if leaf is None:
            raise GoldenPathError(f"任务叶不存在: {task_id}")
        from factory_console.production_runtime import execute_task  # noqa: PLC0415

        if executor_factory is not None:
            fn = executor_factory(task_id)
            return {
                "plan_id": plan["id"], "prd_id": _prd["id"],
                "production_run_id": None, "state": None,
                "executed": [{"task": leaf, "result": _run_result_from_fn(
                    root, fn, leaf, conversation_id, plan, _prd)}],
            }
        return {
            "plan_id": plan["id"], "prd_id": _prd["id"],
            "production_run_id": None, "state": None,
            "executed": [{"task": leaf, "result": execute_task(
                root, leaf["id"], project_id=conversation_id,
                input_data={"goal": plan.get("goal", ""), "task": leaf,
                            "approved_prd_id": _prd.get("id"),
                            "approved_plan_id": plan.get("id")},
                actor=actor, capability_fn=capability_fn)}],
        }

    # 执行能力 factory
    if executor_factory is None and capability_fn is not None:
        cap = capability_fn
        leaves_map = {n.get("id"): n for n in leaves}
        ws_dir = Path(root) / "golden_path_workspace" / str(conversation_id)

        def _cap_factory(node_id: str):
            return _capability_executor(leaves_map.get(node_id, {}), cap,
                                        workspace_dir=ws_dir)

        executor_factory = _cap_factory
    elif executor_factory is None:
        executor_factory = _default_executor_factory(root, conversation_id,
                                                     executor_name=executor_name)
    if executor_factory is None:
        raise GoldenPathError(
            "无可用执行能力 (capability/executor_factory/真实 executor 均不可用) — 禁止占位假成功")
    if hasattr(executor_factory, "set_leaves"):
        executor_factory.set_leaves(leaves)  # type: ignore[attr-defined]

    # workflow 图 (叶顺序 = plan.order 拓扑; 依赖边来自叶; 叶上下文入 input_static)
    nodes = [{"node_id": n["id"],
              "depends_on": [d for d in (n.get("depends_on") or [])
                             if d in by_id],
              "input_static": {
                  "task": {k: n.get(k) for k in
                           ("id", "title", "kind", "scope", "change_type",
                            "expected_files", "prd_ref", "depends_on")},
                  "goal": plan.get("goal", ""),
                  "approved_prd_id": _prd.get("id"),
                  "approved_plan_id": plan.get("id"),
              }}
             for n in leaves_ordered]
    register_workflow(root, workflow_id=plan["id"],
                      name=f"plan {plan['id']}", project_id=conversation_id,
                      nodes=nodes)
    prun = create_production_run(
        root, plan["id"],
        input_data={"conversation_id": conversation_id,
                    "prd_id": _prd["id"], "plan_id": plan["id"],
                    "goal": plan.get("goal", "")},
        trigger=f"golden-path:{actor}")
    run = execute_production_run(root, prun["run_id"],
                                 executor_factory=executor_factory,
                                 artifact_root=str(root), actor=actor)

    executed = []
    for nr in run.get("node_runs", []):
        nid = nr.get("node_id")
        leaf = by_id.get(nid, {})
        result = {"run_id": nr.get("run_id"), "state": nr.get("state"),
                  "artifact_id": nr.get("artifact_id"), "evidence": {},
                  "verification": "FAIL", "error": None, "output": None}
        if nr.get("run_id"):
            try:
                nrun = get_node_run(root, nr["run_id"]) or {}
                result["state"] = nrun.get("state") or result["state"]
                result["error"] = nrun.get("failure_reason")
                vref = nrun.get("verification")
                if isinstance(vref, dict):
                    result["verification"] = vref.get("status") or "FAIL"
                    if vref.get("verification_id"):
                        result["evidence"]["verification_id"] = vref["verification_id"]
                result["evidence"]["node_run_id"] = nr["run_id"]
                if nrun.get("artifact_id"):
                    result["artifact_id"] = nrun["artifact_id"]
                # output 回填 (artifact payload.output — 与 execute_task 语义一致)
                if nrun.get("artifact_id"):
                    try:
                        from factory_console.artifact_lifecycle import get_artifact
                        art = get_artifact(root, nrun["artifact_id"]) or {}
                        payload = art.get("payload")
                        if isinstance(payload, dict):
                            result["output"] = payload.get("output", payload)
                        else:
                            result["output"] = payload
                    except Exception:  # noqa: BLE001 — output 读取失败不影响状态
                        pass
            except Exception:  # noqa: BLE001 — 证据读取失败不阻断 (状态以 run 记录为准)
                pass
        executed.append({"task": leaf, "result": result})

    return {"plan_id": plan["id"], "prd_id": _prd["id"],
            "production_run_id": prun["run_id"], "state": run.get("state"),
            "executed": executed}


__all__ = [
    "GoldenPathError",
    "path_status", "plan_tree", "generate_prd", "approve_prd", "generate_plan",
    "approve_plan", "execute_approved", "_derive_plan_tasks",
]
