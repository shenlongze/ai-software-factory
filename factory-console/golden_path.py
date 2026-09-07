"""factory-console/golden_path.py — Golden Path 编排域 (Cognitive Golden Path Phase 4/5)。

打通真链 (Golden Path §4/§16-§20):
```
Product Understanding (conversation-scoped)
  → PRD (application_formalization — structured, versioned, provenance)
  → User Approval ("就按这个做" → approve_prd)
  → Development Plan (product_truth PLAN-* — prd_id/prd_version provenance)
  → User Approval (approve_plan)
  → Production Runtime (production_runtime.execute_task, 逐 task 经 approved plan)
```

边界 (Golden Path §3/§20/§25):
- 复用现有 product_truth (正式资产层 PLAN-*) / production_runtime (唯一生产入口),
  **不创建第二套 Task/Plan/Production Truth**。
- **Production Gate**: execute 前必须存在 user-approved PRD + user-approved Plan。
  任何未确认路径被拒 — 返回明确错误, 绝不放行。
- Intent 不是产品生命周期 Truth: 本模块无 Intent; 生产触发 = approved Plan。
- PRD 内容 → plan tasks 生成 (deterministic 映射, 供验收; 生产可接 LLM 细化)。
"""
from __future__ import annotations

from typing import Any

from factory_console import product_truth as pt
from factory_console import product_understanding as pu
from factory_console import application_formalization as fmt


class GoldenPathError(ValueError):
    """Golden Path 流程错误 (缺前置/未批准/状态非法)。"""


# ------------------------------------------------------------------ 阶段查询

def path_status(root: str, conversation_id: str) -> dict[str, Any]:
    """当前 Golden Path 阶段总览 (供 UI/CLI/测试断言 Truth)。"""
    prds = fmt.list_prds(root, conversation_id)
    snap = pu.understanding_snapshot(root, conversation_id)
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
        "approved_prd": next((p for p in prds if p.get("status") == "approved"),
                             None),
        "plans": [
            {"id": p["id"], "status": p["status"], "goal": p.get("goal", "")}
            for p in pt.list_plans(root, prd_id=next(
                (x["id"] for x in prds if x.get("status") == "approved"), ""))
        ] if any(p.get("status") == "approved" for p in prds) else [],
    }


# ------------------------------------------------------------------ PRD → approval → Plan

def generate_prd(root: str, conversation_id: str, *, actor: str = "") -> dict[str, Any]:
    """Understanding → PRD v1 (须已有 Understanding; 已有 draft 则更新为新 version)。

    幂等语义: 无 PRD → create; 有 draft → update (重新从最新 Understanding 派生)。
    """
    prds = fmt.list_prds(root, conversation_id)
    drafts = [p for p in prds if p.get("status") == "draft"]
    if drafts:
        return fmt.update_prd(root, conversation_id, drafts[-1]["id"], actor=actor)
    return fmt.create_prd(root, conversation_id, actor=actor)


def approve_prd(root: str, conversation_id: str, prd_id: str, *,
                actor: str = "") -> dict[str, Any]:
    """用户确认 PRD (Golden Path §18: PRD generated ≠ PRD approved)。"""
    prd = fmt.get_prd(root, conversation_id, prd_id)
    if prd is None:
        raise GoldenPathError(f"PRD 不存在: {prd_id}")
    if prd.get("status") != "draft":
        raise GoldenPathError(
            f"PRD {prd_id} 当前 status={prd.get('status')} — 仅 draft 可确认")
    return fmt.approve_prd(root, conversation_id, prd_id, actor=actor)


def _derive_plan_tasks(prd: dict[str, Any]) -> list[dict[str, Any]]:
    """PRD content → Development Plan task 列表 (deterministic 映射)。

    每个功能需求/约束/决定 → 一条 task; 结构化 {id, title, kind}。
    """
    content = prd.get("content", {})
    tasks: list[dict[str, Any]] = []
    seq = 0
    overview = content.get("overview", {}) if isinstance(content, dict) else {}
    goal = str(overview.get("name") or overview.get("problem") or "")[:120]

    def _task(title: str, kind: str) -> None:
        nonlocal seq
        seq += 1
        tasks.append({"id": f"T{seq}", "title": str(title)[:200], "kind": kind})

    # 骨架
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


def generate_plan(root: str, conversation_id: str, *, actor: str = "") -> dict[str, Any]:
    """Approved PRD → Development Plan (product_truth PLAN-*, provenance 保留)。

    前置: 必须有 approved PRD (Golden Path: PRD 确认后才能形成 Plan)。
    """
    prds = fmt.list_prds(root, conversation_id)
    approved = [p for p in prds if p.get("status") == "approved"]
    if not approved:
        raise GoldenPathError("尚无 approved PRD — 用户确认 PRD 后才能生成 Development Plan")
    prd = approved[-1]
    tasks = _derive_plan_tasks(prd)
    plan = pt.create_plan(
        root,
        prd_id=prd["id"],
        prd_version=int(prd.get("version") or 1),
        goal=str((prd.get("content") or {}).get("overview", {}).get("problem")
                 or prd["id"]),
        tasks=tasks,
        order=[t["id"] for t in tasks],
        acceptance=[str(x) for x in tasks],
        ask_approval=True,
        actor=actor or "human",
        idempotency_key=f"gp-plan:{conversation_id}:{prd['id']}:v{prd.get('version')}",
    )
    return plan


def approve_plan(root: str, plan_id: str, *, actor: str = "") -> dict[str, Any]:
    """用户确认 Development Plan (Golden Path §20: Plan approval 后进生产)。"""
    plan = pt.get_plan(root, plan_id)
    if plan is None:
        raise GoldenPathError(f"Plan 不存在: {plan_id}")
    if plan.get("status") != "pending":
        raise GoldenPathError(
            f"Plan {plan_id} 当前 status={plan.get('status')} — 仅 pending 可确认")
    return pt.approve_plan(root, plan_id, actor=actor)


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


def execute_approved(root: str, conversation_id: str, *,
                     actor: str = "human", capability_fn: Any = None,
                     task_id: str = "") -> dict[str, Any]:
    """Approved Plan → Production Runtime (唯一 Golden Path 生产入口)。

    逐 task 执行 (或指定 task_id)。前置: user-approved PRD + approved Plan —
    无确认绝不进生产 (RED-2 修复: 切断 Intent→Production 无条件路径)。

    执行前确保 plan task 已注册为 node (node_runtime.register_node 幂等) —
    NodeRun 事实锚定 node 定义, 复用现有 Node/NodeRun 生产链, 不建第二套。
    """
    from factory_console.node_runtime import register_node
    from factory_console.production_runtime import execute_task

    _prd, plan = _require_gates(root, conversation_id)
    tasks = list(plan.get("tasks") or [])
    if not tasks:
        raise GoldenPathError("Approved Plan 无 tasks — 无法执行")
    results = []
    for t in tasks:
        if task_id and t.get("id") != task_id:
            continue
        # node 注册 (幂等 upsert) — plan task → Node 定义
        try:
            register_node(
                root, node_id=t.get("id") or f"task-{t.get('title', '')[:20]}",
                name=str(t.get("title") or t.get("id") or "")[:120],
                node_type="plan_task",
                input_contract={"goal": plan.get("goal", "")},
                output_contract={"deliverable": "verified"},
                execution_policy={"actor": actor, "source": "golden-path"},
            )
        except Exception:  # noqa: BLE001 — node 已存在/等价 → 继续
            pass
        res = execute_task(
            root, t.get("id") or f"task-{t.get('title', '')[:20]}",
            project_id=conversation_id,
            input_data={"goal": plan.get("goal", ""), "task": t,
                        "approved_prd_id": _prd.get("id"),
                        "approved_plan_id": plan.get("id")},
            actor=actor,
            capability_fn=capability_fn,
        )
        results.append({"task": t, "result": res})
    return {"plan_id": plan["id"], "prd_id": _prd["id"],
            "executed": results}


__all__ = [
    "GoldenPathError",
    "path_status", "generate_prd", "approve_prd", "generate_plan",
    "approve_plan", "execute_approved", "_derive_plan_tasks",
]
