"""factory-console/session/critical_path.py — 关键路径标注引擎 (M3b, S10-090 M3-2)。

把 M3a DecomposeEngine 的原子叶子（只有树关系, 无横向依赖边）补上**横向依赖边
(DAG)** 并计算**关键路径**（计划层标注）— "拆到不能拆" 之后告诉执行层: 哪些任务
在最长链上 (CRITICAL), 哪些是汇聚点 (merge), 整链预估多久。

依赖边推断来源（优先级: 确定性 > 可解释 > 可跳过）:
  ① 技术层确定性链 (同 feature): db → api → frontend → test（硬编码模板, 兜底）
  ② 跨 feature 共享: 共享 target_file / 共享模块目录 → 边（确定性检测）
  ③ LLM 注入点: llm_fn(leaves, edges) → 额外依赖（失败 → 跳过, 用①②）
  ④ 落盘: dependencies.json（项目级）+ plan.json 内含 edges（下次可复用）

关键路径算法:
  1. 依赖边逐条 add_dependency（复用 dependencies.py — 成环拒绝 + 审计）
  2. topological_order → 拓扑序列（失败安全）
  3. est_minutes 沿拓扑累加: dist[task] = max(dist[dep]) + est[task]
  4. 最长链 = 关键路径（从 dist 最大节点回溯 max dist 前驱）
  5. estimated_duration = max dist（整链预估）
  6. merge point: 入度 ≥ 2 的节点 → merges[]（只标注, 不调度）

落盘: projects/<slug>/plan.json {tasks[], edges[], critical_path[], merges[],
estimated_duration, summary_text} + projects/<slug>/dependencies.json。

失败安全铁律:
  - 环 → add_dependency 拒绝 + PLAN_KEYPATH_COMPUTED(status=cycle_rejected) 审计,
    不产出关键路径（诚实: 不伪造最长链）, 不崩溃
  - LLM 推断失败 → 确定性技术层链兜底（不伪造）
  - 任何异常 → 返回部分结果 + 明确 error（不抛）
  - 落盘故障 → 返回 None（不中断）

审计: PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED（AuditEmitter）。

设计: docs/sprint10/S10-090-m3b-critical-path-plan.md
边界:
- 纯标准库 + 复用 dependencies.py（只读, 不修改其核心）
- 只做计划层标注; 不做 M3-3 并行调度 / M3-4 动态分配 / 质量评估
- 向后兼容: M3a 无依赖边输入 → 默认技术层链（不崩溃）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .dependencies import TaskDependencyGraph

#: 技术层确定性链（同 feature 硬编码模板 — 设计 §1 来源①）
TECHNICAL_CHAIN: tuple[str, str, str, str] = ("db", "api", "frontend", "test")

#: 任务 → 技术层序号（id 后缀优先, agent_type 兜底; 未知层 → None 不参与链）
_LAYER_MAP: dict[str, int] = {
    "db": 0, "database": 0,
    "api": 1, "backend": 1, "server": 1,
    "frontend": 2, "ui": 2, "front": 2, "web": 2,
    "test": 3, "qa": 3, "tests": 3,
}

#: 边来源标注（kind 三态: technical/shared/llm; source 可解释）
KIND_TECHNICAL = "technical"
KIND_SHARED = "shared"
KIND_LLM = "llm"
KIND_EXPLICIT = "explicit"


def _now_iso() -> str:
    """UTC 当前时间 ISO 格式（落盘 updated_at）。"""
    return datetime.now(timezone.utc).isoformat()


def _coerce_edge(item: Any) -> Optional[dict[str, Any]]:
    """任意边输入 → 标准边 dict {from_task, to_task, kind, source}。

    dict: 取 from_task/to_task（可含 kind/source）; tuple/list: (from, to)。
    非法 → None（失败安全, 跳过）。
    """
    if isinstance(item, dict):
        frm = str(item.get("from_task") or item.get("from") or "")
        to = str(item.get("to_task") or item.get("to") or "")
        if not frm or not to:
            return None
        return {
            "from_task": frm,
            "to_task": to,
            "kind": str(item.get("kind") or KIND_EXPLICIT),
            "source": str(item.get("source") or "input"),
        }
    if isinstance(item, (tuple, list)) and len(item) >= 2:
        frm, to = str(item[0] or ""), str(item[1] or "")
        if not frm or not to:
            return None
        return {"from_task": frm, "to_task": to, "kind": KIND_EXPLICIT, "source": "input"}
    return None


def _norm_file(path: Any) -> str:
    """target_file 归一化（空/缺失 → ""; 相对路径正斜杠）。"""
    p = str(path or "").strip()
    if not p:
        return ""
    return Path(p).as_posix().lstrip("./")


class CriticalPathResult:
    """关键路径计算结果（计划层标注; to_dict 供落盘/CLI 展示）。

    - tasks: 叶子 + critical 标记（True = 在关键路径上 → CRITICAL）
    - edges: {from_task, to_task, kind, source}
    - critical_path: 最长链任务 id 列表（环拒绝 → 空, 诚实不伪造）
    - merges: [{task, deps[>=2]}]（入度 ≥ 2 汇聚点, 只标注不调度）
    - estimated_duration: 关键路径总 est_minutes（整链预估）
    - order: 拓扑序列; cycle_rejected / error: 失败安全状态
    """

    def __init__(
        self,
        *,
        project_id: str = "",
        tasks: Optional[list[dict[str, Any]]] = None,
        edges: Optional[list[dict[str, Any]]] = None,
        critical_path: Optional[list[str]] = None,
        merges: Optional[list[dict[str, Any]]] = None,
        estimated_duration: int = 0,
        order: Optional[list[str]] = None,
        events: Optional[list[str]] = None,
        cycle_rejected: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.project_id = str(project_id or "")
        self.tasks: list[dict[str, Any]] = list(tasks or [])
        self.edges: list[dict[str, Any]] = list(edges or [])
        self.critical_path: list[str] = list(critical_path or [])
        self.merges: list[dict[str, Any]] = list(merges or [])
        self.estimated_duration = int(estimated_duration or 0)
        self.order: list[str] = list(order or [])
        self.events: list[str] = list(events or [])
        self.cycle_rejected = bool(cycle_rejected)
        self.error: Optional[str] = error

    # ------------------------------------------------------------ 视图

    @property
    def summary_text(self) -> str:
        """CLI 展示摘要: 关键路径 + 整链预估 + 汇聚点（§5 summary_text）。"""
        if not self.tasks:
            return "关键路径: 无任务（未标注）"
        if self.cycle_rejected or not self.critical_path:
            reason = self.error or "依赖成环"
            return f"关键路径不可用: {reason}（失败安全, 未伪造最长链）"
        chain = " → ".join(self.critical_path)
        if self.merges:
            merges_note = "汇聚点 " + "、".join(
                f"{m['task']}({'/'.join(m['deps'])})" for m in self.merges
            )
        else:
            merges_note = "无汇聚点"
        return (
            f"关键路径: {chain}（预计 {self.estimated_duration} 分钟; "
            f"{merges_note}）"
        )

    def to_dict(self) -> dict[str, Any]:
        """计划层标注视图（plan.json 核心字段 + 摘要, 供 CLI/审计）。"""
        return {
            "project_id": self.project_id,
            "tasks": self.tasks,
            "edges": self.edges,
            "critical_path": self.critical_path,
            "merges": self.merges,
            "estimated_duration": self.estimated_duration,
            "order": self.order,
            "cycle_rejected": self.cycle_rejected,
            "error": self.error,
            "events": self.events,
            "summary_text": self.summary_text,
        }


class CriticalPathEngine:
    """关键路径标注引擎（S10-090 M3-2）。

    compute(leaves, *, edges=None, llm_fn=None) → CriticalPathResult:
    - leaves: M3a 原子叶子（id/est_minutes/agent_type/target_file/parent）
    - edges: 显式依赖边（dependencies.json 复用, 可空）
    - llm_fn: 可选 LLM 注入点（失败 → 跳过, 用确定性①②）
    """

    def __init__(
        self,
        workspace: Any = None,
        project_id: str = "",
        *,
        audit: Optional[Any] = None,
    ) -> None:
        """workspace: 工厂根（落盘 projects/<slug>/）; audit: 显式注入（测试隔离）。"""
        self.workspace = Path(workspace) if workspace is not None else None
        self.project_id = str(project_id or "")
        self._audit = audit  # None → 运行时懒装配 AuditEmitter
        self._reset()

    # ------------------------------------------------------------ 状态/审计

    def _reset(self) -> None:
        self._events: list[str] = []

    def _emit(self, event_type: str, **fields: Any) -> None:
        """发射审计事件（失败安全: 审计故障不中断标注）。"""
        self._events.append(event_type)
        try:
            if self._audit is not None:
                self._audit.emit(event_type, project_id=self.project_id, **fields)
                return
            if self.workspace is not None:
                from ..audit.audit_emitter import AuditEmitter

                AuditEmitter(workspace=self.workspace).emit(
                    event_type, project_id=self.project_id, **fields
                )
        except Exception:  # noqa: BLE001 — 失败安全铁律
            pass

    # ------------------------------------------------------------ 依赖边推断

    @staticmethod
    def _layer_index(leaf: dict[str, Any]) -> Optional[int]:
        """任务 → 技术层序号（id 后缀优先, agent_type 兜底; 未知 → None）。"""
        lid = str(leaf.get("id") or "").rsplit("-", 1)[-1].lower()
        if lid in _LAYER_MAP:
            return _LAYER_MAP[lid]
        agent = str(leaf.get("agent_type") or "").lower()
        return _LAYER_MAP.get(agent)

    @classmethod
    def infer_edges(
        cls,
        leaves: list[dict[str, Any]],
        *,
        edges: Optional[list[Any]] = None,
        llm_fn: Optional[Callable[..., Any]] = None,
    ) -> list[dict[str, Any]]:
        """依赖边推断（设计 §1 来源①②③④; 确定性, 失败安全）。

        ① 技术层确定性链（同 feature）: db → api → frontend → test
        ② 跨 feature 共享: 共享 target_file / 共享模块目录（确定性检测）
        ③ LLM 注入点: llm_fn(leaves, edges) → 额外依赖（失败 → 跳过, 用①②）
        ④ 显式边（dependencies.json 复用）先入（去重, 同边保留先入者）
        """
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(frm: str, to: str, kind: str, source: str) -> None:
            if not frm or not to or frm == to:
                return  # 自依赖/空 id → 平凡环/非法, 跳过
            key = (frm, to)
            if key in seen:
                return  # 幂等去重
            seen.add(key)
            out.append({"from_task": frm, "to_task": to, "kind": kind, "source": source})

        leaves = list(leaves or [])

        # ④ 显式边（依赖文件复用 — 先入, 与①②③去重）
        for item in edges or []:
            e = _coerce_edge(item)
            if e is not None:
                add(e["from_task"], e["to_task"], e["kind"], e["source"])

        # ① 技术层确定性链（同 feature 内按层序号串联）
        by_parent: dict[str, list[dict[str, Any]]] = {}
        for leaf in leaves:
            pid = str(leaf.get("parent") or "").strip()
            if pid:
                by_parent.setdefault(pid, []).append(leaf)
        for pid, group in by_parent.items():  # noqa: B007 — pid 仅分组键
            layered: list[tuple[int, dict[str, Any]]] = []
            for leaf in group:
                idx = cls._layer_index(leaf)
                if idx is not None:
                    layered.append((idx, leaf))
            layered.sort(key=lambda item: (item[0], str(item[1].get("id") or "")))
            for i in range(len(layered) - 1):
                idx_a, leaf_a = layered[i]
                idx_b, leaf_b = layered[i + 1]
                if idx_a >= idx_b:
                    continue  # 同层/逆序 → 不串（技术层链只按严格递增）
                add(
                    str(leaf_a.get("id")),
                    str(leaf_b.get("id")),
                    KIND_TECHNICAL,
                    "technical_chain",
                )

        # ② 跨 feature 共享: 共享 target_file（跨 parent, id 字典序定向）
        by_file: dict[str, list[dict[str, Any]]] = {}
        for leaf in leaves:
            f = _norm_file(leaf.get("target_file"))
            if f:
                by_file.setdefault(f, []).append(leaf)
        for f, group in by_file.items():  # noqa: B007 — f 仅分组键
            ordered = sorted(group, key=lambda l: str(l.get("id") or ""))
            for i in range(len(ordered) - 1):
                for j in range(i + 1, len(ordered)):
                    a, b = ordered[i], ordered[j]
                    if a.get("parent") != b.get("parent"):
                        add(
                            str(a.get("id")),
                            str(b.get("id")),
                            KIND_SHARED,
                            "shared_target_file",
                        )

        # ② 跨 feature 共享: 共享模块目录（同目录不同文件, 确定性检测）
        by_dir: dict[str, list[dict[str, Any]]] = {}
        for leaf in leaves:
            f = _norm_file(leaf.get("target_file"))
            if f:
                parent_dir = str(Path(f).parent)
                if parent_dir and parent_dir != ".":
                    by_dir.setdefault(parent_dir, []).append(leaf)
        for d, group in by_dir.items():  # noqa: B007 — d 仅分组键
            ordered = sorted(group, key=lambda l: str(l.get("id") or ""))
            for i in range(len(ordered) - 1):
                for j in range(i + 1, len(ordered)):
                    a, b = ordered[i], ordered[j]
                    if (
                        a.get("parent") != b.get("parent")
                        and a.get("target_file") != b.get("target_file")
                    ):
                        add(
                            str(a.get("id")),
                            str(b.get("id")),
                            KIND_SHARED,
                            "shared_module",
                        )

        # ③ LLM 注入点（失败 → 跳过, 用①②确定性兜底 — 不伪造）
        if llm_fn is not None:
            try:
                raw = llm_fn(leaves, out)
                if isinstance(raw, (list, tuple)):
                    for item in raw:
                        e = _coerce_edge(item)
                        if e is not None:
                            add(e["from_task"], e["to_task"], e["kind"], e["source"])
            except Exception:  # noqa: BLE001 — LLM 推断失败 → 确定性兜底
                pass

        return out

    # ------------------------------------------------------------ 关键路径

    def compute(
        self,
        leaves: list[dict[str, Any]],
        *,
        edges: Optional[list[Any]] = None,
        llm_fn: Optional[Callable[..., Any]] = None,
        infer: bool = True,
    ) -> CriticalPathResult:
        """计算关键路径 + merge 标注 + 落盘（失败安全, 不抛）。

        流程（设计 §2）:
          1. 依赖边推断 → 有向图（add_dependency 逐条, 成环拒绝 + 审计）
          2. topological_order → 拓扑序列（失败安全）
          3. dist[task] = max(dist[dep]) + est[task]（沿拓扑累加）
          4. 最长链 = 关键路径（dist 最大节点回溯 max dist 前驱）
          5. estimated_duration = max dist; merge = 入度 ≥ 2
        """
        self._reset()
        tasks = [dict(l) for l in (leaves or [])]
        task_ids = [str(t.get("id") or "") for t in tasks]
        result = CriticalPathResult(project_id=self.project_id)
        try:
            inferred = self.infer_edges(tasks, edges=edges, llm_fn=llm_fn if infer else None)
            graph = TaskDependencyGraph()
            rejected: list[dict[str, Any]] = []
            for e in inferred:
                # edge from→to ⇒ to_task 依赖 from_task（from 先执行）
                if not graph.add_dependency(str(e["to_task"]), str(e["from_task"])):
                    rejected.append(e)
            accepted = [e for e in inferred if e not in rejected]

            if rejected:
                # 环 → 拒绝 + 审计; 不产出关键路径（诚实, 不伪造最长链）
                result.cycle_rejected = True
                first = rejected[0]
                result.error = (
                    f"依赖成环已拒绝: {first['from_task']}→{first['to_task']} "
                    f"({rejected[0].get('source', 'cyclic dependency')})"
                )
                result.edges = accepted
                result.tasks = [dict(t, critical=False) for t in tasks]
                self._emit(
                    "PLAN_KEYPATH_COMPUTED",
                    status="cycle_rejected",
                    decision="critical_path_skipped",
                    result={
                        "rejected_edges": rejected,
                        "edge_count": len(inferred),
                        "accepted_edge_count": len(accepted),
                    },
                    risk="依赖成环 → 关键路径不可靠, 失败安全拒绝标注",
                )
                result.events = list(self._events)
                self._save(result)
                return result

            # 拓扑序列（复用 dependencies.py — 失败安全）
            order = graph.topological_order(task_ids)
            result.order = order

            # est_minutes 沿拓扑累加: dist[task] = max(dist[dep]) + est[task]
            est = {
                tid: int(t.get("est_minutes") or 0) for t, tid in
                zip(tasks, task_ids)
            }
            dist: dict[str, int] = {}
            for tid in order:
                best = 0
                for dep in graph.get(tid):
                    if dep in dist:
                        best = max(best, dist[dep])
                dist[tid] = best + est.get(tid, 0)

            # 最长链: dist 最大节点（并列 → 拓扑序首个, 确定性）回溯
            end = max(order, key=lambda tid: dist.get(tid, 0)) if order else ""
            path: list[str] = []
            cur = end
            while cur:
                path.append(cur)
                deps = graph.get(cur)
                prev = max(deps, key=lambda d: dist.get(d, -1)) if deps else ""
                if not prev or prev == cur or prev in path:
                    break  # DAG 下 prev==cur/回环不应发生; 防御性终止
                cur = prev
            path.reverse()
            result.critical_path = path
            result.estimated_duration = dist.get(end, 0) if end else 0

            # CRITICAL 标记（§3: 关键路径上任务 → critical=True）
            crit_set = set(path)
            result.tasks = [
                dict(t, critical=(tid in crit_set)) for t, tid in zip(tasks, task_ids)
            ]
            result.edges = accepted

            # merge point（§4: 入度 ≥ 2 → 汇聚点, 只标注不调度）
            merges: list[dict[str, Any]] = []
            for tid in task_ids:
                deps = graph.get(tid)
                if len(deps) >= 2:
                    merges.append({"task": tid, "deps": deps})
            result.merges = merges

            # 审计: PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED
            self._emit(
                "PLAN_KEYPATH_COMPUTED",
                status="ok",
                result={
                    "critical_path": path,
                    "estimated_duration": result.estimated_duration,
                    "edge_count": len(accepted),
                    "task_count": len(task_ids),
                },
            )
            for m in merges:
                self._emit(
                    "PLAN_MERGE_MARKED",
                    task_id=str(m["task"]),
                    result={"deps": m["deps"], "indegree": len(m["deps"])},
                )
            result.events = list(self._events)
            self._save(result)
            return result
        except Exception as exc:  # noqa: BLE001 — 失败安全: 部分结果 + error
            result.error = str(exc)
            result.tasks = [dict(t, critical=False) for t in tasks]
            result.edges = []
            self._emit(
                "PLAN_KEYPATH_COMPUTED",
                status="error",
                result={"error": str(exc), "task_count": len(task_ids)},
            )
            result.events = list(self._events)
            self._save(result)
            return result

    # ------------------------------------------------------------ 落盘

    def _plan_dict(self, result: CriticalPathResult) -> dict[str, Any]:
        """plan.json 落盘内容（设计 §5: tasks/edges/critical_path/merges/
        estimated_duration + summary_text）。"""
        return {
            "project_id": self.project_id,
            "tasks": result.tasks,
            "edges": result.edges,
            "critical_path": result.critical_path,
            "merges": result.merges,
            "estimated_duration": result.estimated_duration,
            "order": result.order,
            "cycle_rejected": result.cycle_rejected,
            "error": result.error,
            "events": result.events or self._events,
            "summary_text": result.summary_text,
            "updated_at": _now_iso(),
        }

    def _deps_dict(self, result: CriticalPathResult) -> dict[str, Any]:
        """dependencies.json 落盘内容（项目级依赖图 + 边, 可复用回注）。"""
        graph: dict[str, list[str]] = {}
        for e in result.edges:
            graph.setdefault(str(e["to_task"]), [])
            if str(e["from_task"]) not in graph[str(e["to_task"])]:
                graph[str(e["to_task"])].append(str(e["from_task"]))
        return {
            "project_id": self.project_id,
            "edges": result.edges,
            "graph": graph,
            "updated_at": _now_iso(),
        }

    def save(self, result: CriticalPathResult) -> Optional[tuple[Path, Path]]:
        """落盘 plan.json + dependencies.json（失败安全: 故障 → None, 不抛）。"""
        try:
            if self.workspace is None or not self.project_id:
                return None
            project_dir = self.workspace / "projects" / self.project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            plan = project_dir / "plan.json"
            deps = project_dir / "dependencies.json"
            plan.write_text(
                json.dumps(self._plan_dict(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            deps.write_text(
                json.dumps(self._deps_dict(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return plan, deps
        except Exception:  # noqa: BLE001 — 失败安全: 落盘故障不中断
            return None

    def _save(self, result: CriticalPathResult) -> None:
        """compute 内部落盘（失败静默 — 标注结果仍返回）。"""
        self.save(result)

    # ------------------------------------------------------------ 加载复用

    @classmethod
    def load_dependencies(cls, workspace: Any, project_id: str) -> list[dict[str, Any]]:
        """读 projects/<slug>/dependencies.json → 边列表（缺失/损坏 → 空, 失败安全）。"""
        path = Path(workspace) / "projects" / str(project_id or "") / "dependencies.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            edges = data.get("edges") if isinstance(data, dict) else None
            return [e for e in (edges or []) if _coerce_edge(e) is not None]
        except Exception:  # noqa: BLE001 — 失败安全
            return []


__all__ = [
    "CriticalPathEngine",
    "CriticalPathResult",
    "TECHNICAL_CHAIN",
]
