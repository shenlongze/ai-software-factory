"""tree_bridge — 任务树 → Workflow（编排消费任务树的桥）。

为什么需要（刀C 的核心）:
  审计发现编排引擎【已经】会做能力匹配 ✓：
    解析 step 的 required_skill/required_role → AgentMatcher → AgentAllocator → Execution
  但它的输入是【内置模板 workflow】(feature/bug/release) ✗ ——
  任务树（LLM 真实拆解 + 能力需求 + 依赖 DAG）和它之间【没有桥】✗

  本模块就是那座桥:
    树叶子任务（含 required_role/skill + depends_on）
      → 拓扑排序（依赖先）
      → WorkflowStep{id=实体id, name, order, required_skill, required_role}
      → Workflow（交给既有引擎执行: 按 order 推进 + 按能力匹配派活）

  设计原则（不重写引擎）:
    · 只做「翻译」—— 不碰 matcher/allocator/execution 的任何逻辑 ✓
    · step.id = task 实体 id → 执行结果可回溯到具体任务 ✓
    · order 由拓扑序得出 → 引擎按 order 推进即等价于「按依赖顺序」✓
    · 依赖未满足的任务不会排进前序（拓扑保证）✓
"""

from __future__ import annotations

from typing import Any

from ...work.workflows.models import Workflow, WorkflowStep

#: 兜底角色（任务没标 required_role 时用它，保证 matcher 有输入）
DEFAULT_ROLE = "executor"


def topological_leaves(tree: dict[str, Any],
                       entities: dict[str, dict[str, Any]] | None = None
                       ) -> list[dict[str, Any]]:
    """按【依赖优先】的拓扑序返回叶子任务（含实体字段合并）。

    entities: task_id → 实体（可选；用于取后端物化后的 required_role/skill）。
    无环保证: 上游 _break_cycles 已断环；这里再做一次防御（环内节点按原序追加）。
    """
    nodes = [n for n in (tree.get("nodes") or []) if isinstance(n, dict)]
    leaves = [n for n in nodes if n.get("kind") == "task"]
    ents = entities or {}

    def merged(n: dict[str, Any]) -> dict[str, Any]:
        e = ents.get(str(n.get("id"))) or {}
        out = dict(n)
        for k in ("required_role", "required_skill", "title", "change_type",
                  "expected_files"):
            if e.get(k) and not out.get(k):
                out[k] = e[k]
        return out

    leaves = [merged(n) for n in leaves]
    by_id = {str(n.get("id")): n for n in leaves}
    seen: set[str] = set()
    order: list[dict[str, Any]] = []

    def visit(nid: str, stack: set[str]) -> None:
        if nid in seen or nid in stack:
            return
        n = by_id.get(nid)
        if n is None:
            return
        stack.add(nid)
        for dep in (n.get("depends_on") or []):
            visit(str(dep), stack)
        stack.discard(nid)
        seen.add(nid)
        order.append(n)

    for n in leaves:
        visit(str(n.get("id")), set())
    # 防御: 环内节点（未被 visit 到）按原序收尾
    for n in leaves:
        if str(n.get("id")) not in seen:
            order.append(n)
    return order


def workflow_from_tree(tree: dict[str, Any], *,
                       workflow_id: str = "",
                       name: str = "",
                       entities: dict[str, dict[str, Any]] | None = None) -> Workflow:
    """任务树 → Workflow（叶子任务变成按拓扑序排列的 step）。

    step.id   = 叶子任务的实体 id（结果可回溯 ✓）
    step.order= 拓扑序位次（引擎按 order 推进 = 按依赖顺序 ✓）
    step.required_role / required_skill = 交给 AgentMatcher 做能力匹配 ✓
    """
    ordered = topological_leaves(tree, entities)
    if not ordered:
        raise ValueError("workflow_from_tree: 任务树没有叶子任务")

    steps: list[WorkflowStep] = []
    for i, n in enumerate(ordered, 1):
        role = str(n.get("required_role") or "").strip() or DEFAULT_ROLE
        skill = str(n.get("required_skill") or "").strip() or None
        steps.append(WorkflowStep(
            id=str(n.get("id") or f"step-{i}"),
            name=str(n.get("title") or f"任务 {i}")[:120],
            order=i,
            required_skill=skill,
            required_role=role,
        ))
    return Workflow(
        id=workflow_id or f"wf-{tree.get('tree_id') or 'tree'}",
        name=name or str(tree.get("goal") or "任务树工作流")[:120],
        description=(
            f"由任务树生成（{len(steps)} 个 step，按依赖拓扑序）· "
            f"tree_id={tree.get('tree_id', '')}"
        ),
        steps=steps,
    )
