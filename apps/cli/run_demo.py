#!/usr/bin/env python3
"""apps/cli/run_demo.py — 新地基第一次真实运行（CLI 投影）。

把 plugins/factories/software 的流程模板喂给 core/scheduler，看它自己排出该做什么。

    python apps/cli/run_demo.py

本脚本只做三件事：装配（内存世界）、调度（tick）、展示（打印过程）。
不修改任何数据、不调用模型、不执行真实工作。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ai_factory_os.contracts.execution import Execution, Outcome  # noqa: E402
from ai_factory_os.contracts.governance import GateKind  # noqa: E402
from ai_factory_os.contracts.organization import Capacity, Member  # noqa: E402
from ai_factory_os.contracts.resource import Match, ProviderType, Resolution  # noqa: E402
from ai_factory_os.contracts.scheduling import DecisionKind  # noqa: E402
from ai_factory_os.contracts.work import TaskNode  # noqa: E402
from ai_factory_os.core.scheduler.loop import tick  # noqa: E402
from ai_factory_os.core.scheduler.ports import Ports  # noqa: E402
from ai_factory_os.plugins.factories.software.capabilities import CAPABILITY_BY_ID  # noqa: E402
from ai_factory_os.plugins.factories.software.bindings import BINDINGS  # noqa: E402
from ai_factory_os.plugins.factories.software.template import instantiate  # noqa: E402
from ai_factory_os.plugins.tools.local_actions import check_artifact, write_artifact  # noqa: E402

WORKSPACE = Path("/tmp/ai-factory-demo")
ARTIFACT = WORKSPACE / "deliverable.md"

# --------------------------------------------------------------------- 角色

ENGINEER, OWNER, REVIEWER = "M-ENG", "M-PO", "M-QA"
BY_PROVIDER = {
    ProviderType.AGENT: ENGINEER,
    ProviderType.SKILL: ENGINEER,
    ProviderType.TOOL: REVIEWER,
    ProviderType.HUMAN: OWNER,
    ProviderType.MCP: ENGINEER,
}


class World:
    """内存世界 —— 实现调度器的全部端口。真实系统里这些由 services 提供。"""

    def __init__(self, nodes: tuple[TaskNode, ...]) -> None:
        self.now = "2026-09-14T09:00:00Z"
        self.nodes = {n.id: n for n in nodes}
        self.members = {
            ENGINEER: Member(id=ENGINEER, org_id="O-1", identity_id="ID-ENG", name="工程师",
                             capacity=Capacity(max_concurrent=1)),
            OWNER: Member(id=OWNER, org_id="O-1", identity_id="ID-PO", name="产品负责人",
                          capacity=Capacity(max_concurrent=5)),
            REVIEWER: Member(id=REVIEWER, org_id="O-1", identity_id="ID-QA", name="验收人",
                             capacity=Capacity(max_concurrent=2)),
        }
        self.accepted: set[str] = set()
        self.actives: dict[str, Execution] = {}
        self.approved: set[str] = set()
        self.created: list[Execution] = []
        self.outcomes: list[Outcome] = []
        self._seq = 0
        # 能力 → 成员（按需解析）
        self.impl_member = {
            b.capability_id: BY_PROVIDER[b.provider_type]
            for b in reversed(BINDINGS)
            if b.capability_id in CAPABILITY_BY_ID
        }

    # ------------------------------------------------------------ 端口实现

    def now_iso(self) -> str:
        return self.now

    def get_node(self, node_id: str) -> TaskNode | None:
        return self.nodes.get(node_id)

    def list_nodes(self, task_id: str = "") -> list[TaskNode]:
        return list(self.nodes.values())

    def has_accepted_outcome(self, node_id: str) -> bool:
        return node_id in self.accepted

    def deadline_of(self, node_id: str) -> str:
        return ""

    def priority_of(self, node_id: str) -> str:
        return "P1"

    def resolution_for(self, node_id: str) -> Resolution | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        matches = []
        for cap_ref in node.required_capability_refs:
            member = self.impl_member.get(cap_ref)
            if member is None:
                return Resolution(id=f"RS-{node_id}", task_node_id=node_id,
                                  status="unresolved", unresolved_capabilities=(cap_ref,))
            matches.append(Match(capability_id=cap_ref, member_id=member,
                                 identity_id=self.members[member].identity_id,
                                 provider_type=ProviderType.AGENT))
        return Resolution(id=f"RS-{node_id}", task_node_id=node_id,
                          required_capability_refs=node.required_capability_refs,
                          matches=tuple(matches), status="resolved")

    def member(self, member_id: str) -> Member | None:
        return self.members.get(member_id)

    def capability(self, capability_id: str):
        return CAPABILITY_BY_ID.get(capability_id)

    def active_count(self, member_id: str) -> int:
        return sum(1 for e in self.actives.values()
                   if e.member_id == member_id and e.status in ("queued", "running"))

    def remaining_budget(self, scope_ref: str) -> float:
        return 1_000.0

    def is_approved(self, subject_ref: str, kind: GateKind = GateKind.BEFORE) -> bool:
        return subject_ref in self.approved

    def active_for(self, node_id: str) -> Execution | None:
        active = self.actives.get(node_id)
        return active if active is not None and active.status in ("queued", "running") else None

    def create(self, node_id: str, *, resolution_id: str, member_id: str,
               identity_id: str) -> Execution:
        self._seq += 1
        execution = Execution(id=f"EX-{self._seq}", task_node_id=node_id,
                              resolution_id=resolution_id, member_id=member_id,
                              actor_identity_id=identity_id, status="running")
        self.actives[node_id] = execution
        self.created.append(execution)
        return execution

    def finish(self, execution: Execution, *, accepted: bool = True) -> None:
        self.actives[execution.task_node_id] = Execution(
            id=execution.id, task_node_id=execution.task_node_id, status="done")
        outcome = Outcome(id=f"OC-{execution.id}",
                          execution_id=execution.id,
                          status="accepted" if accepted else "rejected")
        self.outcomes.append(outcome)
        if accepted:
            self.accepted.add(execution.task_node_id)

    @property
    def ports(self) -> Ports:
        return Ports(clock=self, work=self, resource=self, load=self, gate=self, execution=self)


# --------------------------------------------------------------------- 展示

def _line(char: str = "─") -> None:
    print(char * 72)


def _cost(cap) -> str:
    """成本估算的可读表示（钱 > token > 时间）。"""
    cost = cap.cost
    if cost.money:
        return f"成本 {cost.money}"
    if cost.tokens:
        return f"tokens {cost.tokens}"
    if cost.seconds:
        return f"耗时 {cost.seconds}s"
    return "成本 0"


def _execute(cap) -> tuple[bool, str]:
    """执行一个动作。被标注为「真实」的两项会真的落盘 / 真的读盘校验。"""
    if cap.id == "CAP-EXECUTE":
        result = write_artifact(ARTIFACT, f"# 交付物\n\n由调度器驱动产生：{cap.name}\n")
        return True, f"[真实] 写入 {result['path']}（{result['bytes']} 字节）"
    if cap.id == "CAP-VERIFY":
        result = check_artifact(ARTIFACT, expect="由调度器驱动产生")
        return bool(result["ok"]), f"[真实] 校验 {ARTIFACT.name} → {result['reason']}"
    if cap.id in ("CAP-CONFIRM-PRD", "CAP-CONFIRM-PLAN"):
        return True, "[模拟] 人工确认"
    return True, "[模拟] 产出（未接真实实现）"


def main() -> int:
    graph = instantiate(project_id="DEMO-1", company_id="C-1", name="做一个待办清单应用",
                        goal="用户能新建/完成/删除待办")
    world = World(graph.nodes)

    print()
    print("AI Factory OS — 新地基第一次真实运行")
    _line("═")
    print("工厂模板   software（来自 plugins/factories/software）")
    print(f"项目       {graph.project.id}  {graph.project.name}")
    print(f"工作结构   1 项目 → 1 工作 → 1 任务 → {len(graph.nodes)} 个节点")
    print("资源池     工程师(并发1) · 产品负责人(并发5) · 验收人(并发2)")
    print("审批门     交付节点需产品负责人批准（来自能力声明，不是写死的流程）")
    _line("─")
    print("⚠️ 诚实标注：")
    print("   真实的 —— 调度判定、排序、容量约束、依赖解锁、审批门拦截；")
    print("             「执行生产」与「验证结果」两步：真的写文件、真的读盘校验")
    print("   模拟的 —— 其余节点（理解/方案/计划/确认/交付）尚未接真实实现")
    print("   真实系统里：全部执行由 plugins 提供，验收由证据判定")
    print(f"   工作目录 {WORKSPACE}")
    _line("═")

    for round_no in range(1, 20):
        result = tick(world.ports)
        ready = [d for d in result.decisions if d.kind is DecisionKind.READY]
        blocked = [d for d in result.decisions if d.kind is DecisionKind.BLOCKED]

        if not result.scheduled and not ready:
            if not blocked:
                break
            # 全部阻塞在审批 → 人批准后继续（演示「门是数据」）
            waiting = [d for d in blocked if "approval_granted" in d.failed_conditions]
            if waiting and not world.approved:
                node = world.nodes[waiting[0].task_node_id]
                print(f"\n【第 {round_no} 轮】系统停下等人 —— 需要审批")
                print(f"  节点 {node.id}  {node.name}")
                cap = CAPABILITY_BY_ID[node.required_capability_refs[0]]
                print(f"  原因 能力 {cap.id} 声明了 approval.mode={cap.approval.mode.value}"
                      f"，审批角色={cap.approval.approver_role}")
                print("  → 产品负责人批准（演示）")
                world.approved.add(node.id)
                print("  → 已批准，继续调度")
                continue
            print(f"\n【第 {round_no} 轮】没有可推进的节点，停止")
            for d in blocked:
                print(f"  {world.nodes[d.task_node_id].name:8s} ← {'; '.join(d.reasons)}")
            break

        print(f"\n【第 {round_no} 轮 调度】")
        for d in result.decisions:
            node = world.nodes[d.task_node_id]
            mark = {DecisionKind.READY: "就绪", DecisionKind.BLOCKED: "阻塞",
                    DecisionKind.COMPLETED: "已完成"}.get(d.kind, d.kind.value)
            reason = ("; ".join(d.reasons)) if d.kind is not DecisionKind.COMPLETED else ""
            print(f"  [{mark}] {node.name:8s} {reason}")

        for execution in [world.actives[n] for n in
                          [d.task_node_id for d in ready] if n in world.actives]:
            node = world.nodes[execution.task_node_id]
            member = world.members[execution.member_id]
            cap = CAPABILITY_BY_ID[node.required_capability_refs[0]]
            print(f"  分配 → {node.name} 交给 {member.name}({member.id})  执行 {execution.id}"
                  f"  {_cost(cap)}")
            ok, detail = _execute(cap)
            world.finish(execution, accepted=ok)
            print(f"  执行 → {detail}")
            print(f"  完成 → {execution.id} → 验收 "
                  f"{'accepted → 解锁后继' if ok else 'rejected → 后继保持阻塞'}")

    print()
    _line("═")
    print(f"最终：{len(world.accepted)}/{len(graph.nodes)} 个节点通过验收")
    print(f"      {len(world.created)} 次执行 · {len(world.outcomes)} 个验收结果")
    if ARTIFACT.exists():
        print(f"      真实产物 {ARTIFACT}（{ARTIFACT.stat().st_size} 字节）")
    _line("═")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
