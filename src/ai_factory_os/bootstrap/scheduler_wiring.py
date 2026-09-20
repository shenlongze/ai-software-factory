"""bootstrap.scheduler_wiring — 把 core/scheduler 的 Ports 接到真实服务（唯一装配点）。

★ 2026-09-19 新增（M3 平台心脏 · 刀1）—— 此前 `core/scheduler` 是**零装配的骨架**:
  tick/evaluate/rank/allocate 全部写完且契约齐备, 但 bootstrap 从没给它写过适配 ⇒
  "决定下一步是谁"这件事在运行时**不存在**。本文件把它接上。

【设计原则（照 core/scheduler/ports.py 的自述）】
  "调度器不 import services/plugins/infrastructure; 它只声明'我需要能问世界这些问题',
   由 bootstrap 在装配时把真实实现接上 —— 换个治理/资源实现, 调度器一行不动。"
  ⇒ 所以适配器全部住在这里（bootstrap）: core 保持纯净, 换实现只改本文件。

【数据源映射（每个 Port 接哪个真源）】
  ClockPort     ← 系统时间（UTC ISO; 注入以便判定可复现）
  WorkPort      ← services/work/decomposition 的**任务树**（叶 = TaskNode 候选）
                  + services/validation/acceptance（accepted outcome = 验收通过）
  ResourcePort  ← services/organization（Member = 员工任职）+ capability 声明
  LoadPort      ← services/execution（活跃执行数）+ kernel/budget（剩余预算）
  GatePort      ← services/governance/gates（是否已获批）
  ExecutionPort ← 只读查询（active_for）; create 由**驱动**负责（刀2）

【刀1 边界（诚实标注）】
  · 本刀只做到: **tick() 能真跑并产出 Decision**（READY / BLOCKED / …）——
    即"平台心脏能判定"。
  · **不含**: 真执行（ExecutionPort.create 起线程池/调 agent）、事件回流、并发上限
    ⇒ 那是刀2（照 Hermes async_delegation 的两级并发 + 批量占一槽 + 完成事件回流）。
  · 失败安全: 任何数据源缺/坏 → 该 Port 返回"空/未就绪"而非抛异常
    （调度器必须能对着空世界跑, 不能因为一个 store 缺失就崩）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_factory_os.contracts.governance import GateKind
from ai_factory_os.contracts.organization import Capacity, Member
from ai_factory_os.contracts.resource import Capability, Match, ProviderType, Resolution
from ai_factory_os.contracts.work import TaskNode
from ai_factory_os.core.scheduler.ports import Ports


# ------------------------------------------------------------------ ① Clock

class SystemClock:
    """ClockPort —— 系统时间（UTC ISO8601）。注入以便判定可复现。"""

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


# ------------------------------------------------------------------ ② Work

class TaskTreeWork:
    """WorkPort —— 任务树（services/work/decomposition）的只读投影。

    节点来源: `<root>/projects/<P>/tasks/<plan_id>.json` 或 `<root>/task_trees/*.json`
    的 nodes（kind == "task" 的叶 = 可调度的 TaskNode; domain/project 是组织结构不参与调度）。

    验收判据（照 contracts/work TaskNode 自述: "完成的判据不是跑完了, 而是有 accepted Outcome"）:
      叶的 status == "accepted" 或存在对应 acceptance 记录 ⇒ has_accepted_outcome = True。
      刀1 用**叶自身状态**作判据（诚实: 更严的"验收记录"接 validation 是刀2 的事）。
    """

    def __init__(self, root: Path | str, plan_id: str = "", project_id: str = "") -> None:
        self._root = Path(root)
        self._plan_id = plan_id
        self._project_id = project_id
        self._cache: dict[str, Any] | None = None

    # ── 内部: 载入任务树（惰性 + 失败安全）
    def invalidate(self) -> None:
        """丢弃缓存 —— ★ 任务树被外部改动后必须调用（如调度驱动回写叶状态）。

        为什么必须有它: 适配器缓存了树 ⇒ 回写后仍读旧树 ⇒ 下游叶永远"前驱未验收"
        （实测: A/B/C 回写成 completed 后 D 仍 blocked）。
        """
        self._cache = None

    def _tree(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        self._cache = {}
        try:
            from ai_factory_os.services.work import decomposition as D

            if self._plan_id:
                t = D.load_tree(self._root, self._plan_id, self._project_id)
                self._cache = t or {}
            else:
                # 没指定 plan → 取该项目/全局的最新一棵
                trees = D.list_trees(self._root, self._project_id)
                if trees:
                    pid = trees[-1].get("plan_id") or ""
                    self._cache = D.load_tree(self._root, pid, self._project_id) or {}
        except Exception:  # noqa: BLE001 — 调度器必须能对空世界跑
            self._cache = {}
        return self._cache

    def _leaves(self) -> list[dict[str, Any]]:
        return [n for n in (self._tree().get("nodes") or []) if n.get("kind") == "task"]

    def _find(self, node_id: str) -> dict[str, Any] | None:
        for n in self._tree().get("nodes") or []:
            if str(n.get("id") or "") == node_id:
                return n
        return None

    # ── WorkPort 协议
    def get_node(self, node_id: str) -> TaskNode | None:
        n = self._find(node_id)
        if n is None or n.get("kind") != "task":
            return None
        # ★ 2026-09-19 修（装配实测暴露）: 树里叶的 depends_on 指向**自己的 domain 节点**
        #   （那是"归属"不是"可调度先决"）—— 直接拿来用会永远"前驱未验收" ⇒ 全 BLOCKED。
        #   正确做法（与 services/work/decomposition.parallel_groups 一致）:
        #     叶的可调度依赖 = 【祖先域的跨域依赖】所对应的**叶**
        #   （域 A 依赖域 B ⇒ A 的叶依赖 B 的叶; 域归属本身不产生依赖）。
        deps = tuple(self._schedulable_deps(str(n.get("id") or "")))
        return TaskNode(
            id=str(n.get("id") or ""),
            task_id=str(self._tree().get("plan_id") or ""),
            name=str(n.get("title") or ""),
            sequence=int(n.get("sequence") or 0),
            depends_on=deps,
            required_capability_refs=tuple(
                str(c) for c in (n.get("required_capabilities") or [])
            ),
            status=str(n.get("status") or "pending"),
        )

    def _schedulable_deps(self, leaf_id: str) -> list[str]:
        """把一个叶的依赖解析成【其它叶的 id】（摊掉 domain 层）。

        ★ 判据只有一份实现 —— 与关键路径（`services/work/keypath`) 同源:
          规则、以及"归属不是先决"那条铁律都写在 `keypath.schedulable_deps` 里。
          这里只负责喂树（本适配器缓存的那份）。
        """
        from ai_factory_os.services.work import keypath as _kp

        return _kp.schedulable_deps(list(self._tree().get("nodes") or []), leaf_id)

    def list_nodes(self, task_id: str = "") -> list[TaskNode]:
        """列出叶（task_id 给了就只看该计划 —— 刀1 只支持单计划）。"""
        if task_id and task_id != str(self._tree().get("plan_id") or ""):
            return []
        out = []
        for n in self._leaves():
            node = self.get_node(str(n.get("id") or ""))
            if node is not None:
                out.append(node)
        return out

    def has_accepted_outcome(self, node_id: str) -> bool:
        n = self._find(node_id)
        if n is None:
            return False
        return str(n.get("status") or "").lower() in ("accepted", "done", "completed")

    def deadline_of(self, node_id: str) -> str:
        n = self._find(node_id)
        return str((n or {}).get("deadline") or "")

    def priority_of(self, node_id: str) -> str:
        n = self._find(node_id)
        return str((n or {}).get("priority") or "")


# ------------------------------------------------------------------ ③ Resource

class OrgResource:
    """ResourcePort —— 组织成员 + 能力声明。

    Member: agents.json（53 条）→ 每条的 id/name/role/skills → Member（org_id=公司, capacity）。
    Resolution: 由**本适配器**按 matcher 语义现算（skill 命中 ⇒ Match）——
      刀1 用最简规则: 节点声明的能力 vs 成员 skills 有交集 ⇒ match。
      ★ 不 import matcher 的评分（那是"选人排序", 属 services; 调度器只要"谁可以做"）。
    """

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._members: dict[str, Member] | None = None

    def _load(self) -> dict[str, Member]:
        if self._members is not None:
            return self._members
        self._members = {}
        for cand in (self._root / "agents" / "agents.json",
                     self._root / "org" / "agents.json"):
            if not cand.is_file():
                continue
            try:
                import json
                data = json.loads(cand.read_text())
                rows = data if isinstance(data, list) else list(data.values())
                for r in rows:
                    if not isinstance(r, dict):
                        continue
                    mid = str(r.get("id") or "")
                    if not mid:
                        continue
                    self._members[mid] = Member(
                        id=mid,
                        org_id=str(r.get("org_id") or r.get("company") or ""),
                        identity_id=str(r.get("identity_id") or mid),
                        name=str(r.get("name") or ""),
                        role_ids=(str(r.get("role") or ""),) if r.get("role") else (),
                        capacity=Capacity(max_concurrent=int(r.get("max_concurrent") or 1)),
                        status=str(r.get("status") or "active"),
                    )
                break
            except Exception:  # noqa: BLE001
                continue
        return self._members

    def resolution_for(self, node_id: str) -> Resolution | None:
        """按节点的 required_capability_refs 现算匹配（无声明 → None, 由 evaluate 报原因）。"""
        # 节点来自 WorkPort（同 root）—— 直接自己找, 避免 Ports 间耦合
        try:
            from ai_factory_os.services.work import decomposition as D
            n = None
            for t in D.list_trees(self._root):
                tree = D.load_tree(self._root, str(t.get("plan_id") or ""))
                if not tree:
                    continue
                for x in tree.get("nodes") or []:
                    if str(x.get("id") or "") == node_id:
                        n = x
                        break
                if n:
                    break
            if n is None:
                return None
            want = [str(c) for c in (n.get("required_capabilities") or [])]
            if not want:
                return None
        except Exception:  # noqa: BLE001
            return None
        matches: list[Match] = []
        for m in self._load().values():
            caps = {str(r) for r in m.role_ids}
            if caps & set(want):
                matches.append(Match(
                    capability_id=sorted(caps & set(want))[0],
                    member_id=m.id, identity_id=m.identity_id,
                    provider_type=ProviderType.AGENT,   # ★ 契约用枚举, 不是字符串
                    provider_ref=m.id, match_type="deterministic",
                ))
        return Resolution(
            id=f"RES-{node_id[-8:]}", task_node_id=node_id,
            required_capability_refs=tuple(want), matches=tuple(matches),
            status="resolved" if matches else "unresolved",
            unresolved_capabilities=() if matches else tuple(want),
            reason="" if matches else "无成员具备所需能力",
        )

    def member(self, member_id: str) -> Member | None:
        return self._load().get(member_id)

    def capability(self, capability_id: str) -> Capability | None:
        """能力 = 角色名（刀1 的简化: 一个角色名就是一个能力声明）。

        ★ 诚实: 真实的 Capability 带 approval/cost 声明（在 services/organization/
          capabilities.py 的 CapabilityEntity）—— 接它是刀2 的事。刀1 返回 None ⇒
          evaluate 的 approval_granted 条件不触发（即"刀1 不做审批门"）。
        """
        return None


# ------------------------------------------------------------------ ④ Load

class SimpleLoad:
    """LoadPort —— 容量与预算（刀1: 容量恒为 0 占用, 预算视为充足）。

    ★ 诚实标注: 刀1 不接真实执行数/预算 ⇒ active_count 恒 0（不会因容量不足 defer）、
      remaining_budget 返回一个足够大的值。刀2 接 execution + kernel/budget。
    """

    def __init__(self, root: Path | str, budget: float = 1.0e9) -> None:
        self._root = Path(root)
        self._budget = budget

    def active_count(self, member_id: str) -> int:
        return 0

    def remaining_budget(self, scope_ref: str) -> float:
        return self._budget


# ------------------------------------------------------------------ ⑤ Gate

class AllowAllGate:
    """GatePort —— 刀1: 不设门（always approved）。

    ★ 诚实标注: 真实门在 services/governance/gates.py（check_governance）。
      刀1 不接 ⇒ evaluate 的 approval_granted 不会拦（且 Capability 无 approval 声明时
      本就 _needs_gate=False）。刀2 接真门。
    """

    def is_approved(self, subject_ref: str, kind: GateKind = GateKind.BEFORE) -> bool:
        return True


# ------------------------------------------------------------------ ⑥ Execution（只读）

class NullExecution:
    """ExecutionPort —— 刀1 只实现只读查询（active_for 恒 None）; create 待刀2。

    create 若被调用 ⇒ 响亮抛错（不静默假装创建, 否则 tick 会说"调度成功"而实际没跑）。
    """

    def active_for(self, node_id: str) -> None:
        return None

    def create(self, node_id: str, *, resolution_id: str, member_id: str, identity_id: str) -> Any:
        raise NotImplementedError(
            "刀1 不含执行创建 —— 线程池驱动 + 并发上限 + 事件回流是刀2（照 Hermes async_delegation）。"
        )


# ------------------------------------------------------------------ 装配

class StoreExecution:
    """★ ExecutionPort 的真实实现 —— 把就绪叶**创建成 PENDING 执行请求**（第 1 刀收尾）。

    【为什么现在做】`NullExecution` 自述: "刀1 不含执行创建 —— 线程池驱动 + 并发上限
    + 事件回流是**刀2**（照 Hermes async_delegation）"。而刀2 的这三件**已经实现**
    （`bootstrap/scheduler_pump.drive`）⇒ 缺的只是"创建"这一块（本类）。

    【分工】
      · 本端口 `create`: 建 PENDING 执行请求（写 RuntimeStore）⇒ tick 能返回 `scheduled`
      · `drive`: 把 `scheduled` 用线程池跑掉（并发上限 + 事件回流 + 回写叶状态）
        ⇒ 两者合起来才是"平台心脏"的完整回路。

    【与 NullExecution 的关系】不移除 NullExecution（它是诚实的"未装配"占位, 别的场景仍可用）;
    本类作为 `wire_scheduler` 的**默认执行端口**。
    """

    def __init__(self, root: Path | str, *, plan_id: str = "") -> None:
        from ai_factory_os.services.execution.runtime.store import open_runtime_store

        self._root = Path(root)
        self._plan_id = plan_id
        self._store = open_runtime_store(root)

    def active_for(self, node_id: str) -> Any:
        """该叶是否已有**活跃**执行（PENDING/RUNNING）—— 防同一叶被重复创建。

        ★ 返回**执行请求对象**（不是 id 字符串）—— `evaluate.py:37` 会读 `active.id`
        （实测: 返回 str 会 `AttributeError: 'str' object has no attribute 'id'`）。
        无活跃 ⇒ None。
        """
        try:
            for r in self._store.list_executions():
                if str((r.input or {}).get("node_id") or "") != node_id:
                    continue
                st = str(getattr(r.status, "value", r.status) or "").upper()
                if st in ("PENDING", "RUNNING"):
                    return r
        except Exception:  # noqa: BLE001 — 查不到 ⇒ 视为无活跃（调用方另有限流）
            return None
        return None

    def _brief(self, node_id: str) -> tuple[str, str]:
        """★ 给执行体的【任务简报】（标题 + 验收 + 该动哪些文件 + 项目仓库）。

        为什么必须有它（真跑踩到）: 原来 input 里只有路由键（node_id/member_id…）⇒ 适配器组出的
        prompt 只有 "execute execution EXR-001" —— **执行体不知道要干什么**, 只能自己翻树猜
        （EXR-005 那次就是这么"猜对"的, 不可靠）。派活就得把活说清楚。
        失败安全: 读不到叶 ⇒ ("", "")（退回旧行为, 不编）。
        """
        try:
            import json as _json

            from ai_factory_os.services.work import decomposition as D

            tree = D.load_tree(self._root, self._plan_id)
            if not tree:
                return "", ""
            leaf = next((n for n in (tree.get("nodes") or [])
                         if str(n.get("id") or "") == node_id), None)
            if not leaf:
                return "", ""
            title = str(leaf.get("display_name") or leaf.get("title") or "").strip()
            acc = str(leaf.get("acceptance") or "").strip()
            files = [str(x) for x in (leaf.get("expected_files") or [])]
            pid = str(tree.get("project_id") or "")
            repo = ""
            try:
                data = _json.loads((self._root / "org" / "projects.json").read_text(encoding="utf-8"))
                rows = data.get("projects") if isinstance(data, dict) else data
                if isinstance(rows, dict):
                    repo = str((rows.get(pid) or {}).get("repo_path") or "")
                elif isinstance(rows, list):
                    repo = next((str(r.get("repo_path") or "") for r in rows
                                 if isinstance(r, dict) and str(r.get("id")) == pid), "")
            except Exception:  # noqa: BLE001
                repo = ""
            lines = [f"任务: {title}"]
            if acc:
                lines.append(f"验收标准: {acc}")
            if files:
                lines.append("预期产出文件: " + ", ".join(files))
            if pid:
                lines.append(f"项目: {pid}" + (f"  仓库: {repo}" if repo else ""))
            # ★ 2026-09-21（"无固定流程(可编排)"接进主链）: 树挂了流程 ⇒ 说明这是第几步、要求什么技能
            step = self._workflow_step(node_id)
            if step:
                lines.append(f"流程步骤 {step['step_index']}/{step['steps_total']}: "
                             f"{step['step_name']}"
                             + (f"（本步要求技能: {step['required_skill']}）" if step["required_skill"] else "")
                             + f"  [流程 {step['workflow_id']}]")
                lines.append("纪律: 只做【本步骤】的事; 完成后系统会推进到下一步（走完全部步骤才算任务完成）。")
            lines.append("纪律: 只做这一件事; 自检后再收工; 不要改与本任务无关的文件。")
            return title, "\n".join(lines)
        except Exception:  # noqa: BLE001 — 简报失败不阻塞派发（执行体退回旧行为）
            return "", ""

    def _workflow_step(self, node_id: str) -> dict[str, Any] | None:
        """该叶当前的【流程步骤】（树未挂流程 ⇒ None ⇒ 行为与现状完全一致）。

        挂了流程: 无 run 则先启动（run_key = 叶 id, 不碰任务域账本 —— 见 engine.start_run_for 自述）;
                  有 run 则取当前步骤。失败安全: 引擎不可用 ⇒ 返回 None 并**不假装有流程**。
        """
        try:
            from ai_factory_os.services.work import decomposition as D

            wf_id = D.tree_workflow(self._root, self._plan_id)
            if not wf_id:
                return None
            eng = workflow_engine(self._root)
            run = eng.run_for(node_id)
            if run is None:
                run, _ = eng.start_run_for(node_id, wf_id)
            plan = eng.step_plan(run)
            # ★ 引擎语义: 步骤要 RUNNING 才算"正在做"; 若当前步还是 PENDING（推进后未启/中断恢复）
            #   ⇒ 这里启动它（重复启动会被引擎拒绝, 忽略即可）。
            if plan.get("step_id"):
                try:
                    eng.start_step(node_id, str(plan["step_id"]))
                except Exception:  # noqa: BLE001 — 已 RUNNING/状态不符: 不影响取步骤
                    pass
            return plan if plan.get("step_id") else None
        except Exception as exc:  # noqa: BLE001 — 流程不可用 ⇒ 退回单步执行, 但**可见**
            import sys as _sys
            print(f"⚠ 流程步骤读取失败（该叶按单步执行）: {type(exc).__name__}: {str(exc)[:80]}",
                  file=_sys.stderr)
            return None

    def create(self, node_id: str, *, resolution_id: str,
               member_id: str, identity_id: str) -> Any:
        """建一个 PENDING 执行请求（**不**真跑 —— 跑是 drive 的事, 与 ADR-0006 决策 2 一致）。"""
        from ai_factory_os.services.execution.runtime.types import (
            ExecutionRequest, ExecutionStatus,
        )

        eid = self._store.next_execution_id(prefix="EXR-")
        _task, _instr = self._brief(node_id)          # ★ 把"活"说清楚（见 _brief 自述）
        _step = self._workflow_step(node_id) or {}
        req = ExecutionRequest(
            id=eid,
            task_id=self._plan_id,                      # ★ 任务树 id（pump 用它定位叶）
            status=ExecutionStatus.PENDING,
            input={                                    # ★ pump/_claim_and_run 读这几个键
                "node_id": node_id,
                "resolution_id": resolution_id,
                "member_id": member_id,
                "identity_id": identity_id,
                # ★ 适配器把它组进 prompt（原来缺这两个键 ⇒ 执行体只收到 "execute execution EXR-x"）
                "task": _task,
                "instruction": _instr,
                # ★ 流程步骤（未挂流程 ⇒ 空 ⇒ 下游行为不变）
                "workflow_id": str(_step.get("workflow_id") or ""),
                "workflow_step": str(_step.get("step_id") or ""),
                "workflow_step_name": str(_step.get("step_name") or ""),
                "workflow_step_index": int(_step.get("step_index") or 0),
                "workflow_steps_total": int(_step.get("steps_total") or 0),
            },
        )
        self._store.save_execution(req)
        return req


def workflow_engine(root: Path | str) -> Any:
    """装配【流程引擎】—— 唯一装配点（store 落在 `<root>/workflows/`）。

    ★ 2026-09-21（"无固定流程(可编排)"接进主链）:
      · 首次使用（store 里一个定义都没有）时把【内置定义】注册进去（幂等, 只做一次）——
        之后内置定义就是**可编辑的数据**: 用户改/删都由 store 说了算（不会被他改完又"复活"）。
      · 不注入 task_store: 主链的 run_key 是【叶 id】, 不碰任务域账本（见 engine.start_run_for 自述）。
    """
    from ai_factory_os.services.work.workflows.definitions import BUILTIN_WORKFLOWS
    from ai_factory_os.services.work.workflows.engine import WorkflowEngine
    from ai_factory_os.services.work.workflows.store import WorkflowStore

    store = WorkflowStore(Path(root) / "workflows")
    try:
        if not store.workflow_ids():                      # 空 ⇒ 首次: 注册内置
            for wf in BUILTIN_WORKFLOWS.values():
                store.save_workflow(wf)
    except Exception:  # noqa: BLE001 — 注册失败不阻塞（后续 get_workflow 会响亮报缺失）
        pass
    return WorkflowEngine(store)


def wire_scheduler(
    root: Path | str,
    *,
    plan_id: str = "",
    project_id: str = "",
    budget: float = 1.0e9,
) -> Ports:
    """装配 core/scheduler 的全部 Ports —— **平台心脏的唯一注入点**。

    用法:
        ports = wire_scheduler(root, plan_id="PLAN-xxx")
        from ai_factory_os.core.scheduler.loop import tick
        result = tick(ports)               # → TickResult(scheduled, decisions, deferred)
        # 刀1: scheduled 为空（NullExecution 不创建执行）; decisions 里能看每个叶的五态
    """
    return Ports(
        clock=SystemClock(),
        work=TaskTreeWork(root, plan_id=plan_id, project_id=project_id),
        resource=OrgResource(root),
        load=SimpleLoad(root, budget=budget),
        gate=AllowAllGate(),
        # ★ 2026-09-19（第 1 刀收尾）: 用真实执行端口（创建 PENDING 请求）——
        #   原为 NullExecution（刀1 占位, create 响亮抛错）⇒ run --plan 一个执行都建不出来。
        #   NullExecution 保留（诚实占位, 别的场景仍可用）。
        execution=StoreExecution(root, plan_id=plan_id),
    )
