"""流程模板（步骤图）+ 纯函数 instantiate() —— 纯数据，零 IO。

审批不是独立步骤，也不是流程常量：
    step-confirm-prd / step-confirm-plan 由**人**满足（ProviderType.HUMAN），
    后继节点依赖它们的 accepted Outcome → 没人确认，后继自动 blocked。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ai_factory_os.contracts.work import Project, Task, TaskNode, Work

from .acceptance import DELIVERY_ACCEPTANCE


@dataclass(frozen=True)
class StepSpec:
    """模板里的一步 —— key / 名称 / 需要的能力 / 前驱。"""

    key: str
    name: str
    capability_ref: str
    depends_on: tuple[str, ...] = ()
    condition: str = ""


STEPS: tuple[StepSpec, ...] = (
    StepSpec("step-understand", "理解目标", "CAP-UNDERSTAND"),
    StepSpec("step-draft-prd", "起草方案", "CAP-DRAFT-PRD", ("step-understand",)),
    StepSpec("step-confirm-prd", "确认方案", "CAP-CONFIRM-PRD", ("step-draft-prd",)),
    StepSpec("step-draft-plan", "起草计划", "CAP-DRAFT-PLAN", ("step-confirm-prd",)),
    StepSpec("step-confirm-plan", "确认计划", "CAP-CONFIRM-PLAN", ("step-draft-plan",)),
    StepSpec("step-execute", "执行生产", "CAP-EXECUTE", ("step-confirm-plan",)),
    StepSpec("step-verify", "验证结果", "CAP-VERIFY", ("step-execute",)),
    StepSpec("step-deliver", "交付", "CAP-DELIVER", ("step-verify",)),
)

# 条件步骤：仅当验证未通过才需要。
# ⚠️ 调度器目前**不支持条件依赖**，故声明但不下发（诚实标注，不生成错误的图）。
CONDITIONAL_STEPS: tuple[StepSpec, ...] = (
    StepSpec("step-repair", "修复失败", "CAP-REPAIR", ("step-verify",), "step-verify:rejected"),
)
CONDITIONAL_SUPPORTED = False


@dataclass(frozen=True)
class SoftwareGraph:
    """一次软件交付的完整工作结构。"""

    project: Project
    work: Work
    task: Task
    nodes: tuple[TaskNode, ...] = field(default_factory=tuple)


def instantiate(*, project_id: str, company_id: str, name: str, goal: str = "",
                deadline: str = "") -> SoftwareGraph:
    """把模板展开成 Project / Work / Task / TaskNode —— 纯函数。"""
    project = Project(id=project_id, company_id=company_id, name=name, goal=goal,
                      acceptance=DELIVERY_ACCEPTANCE, deadline=deadline, status="active")
    work = Work(id=f"{project_id}-W1", project_id=project_id, name="软件交付", status="active")
    task = Task(id=f"{project_id}-T1", work_id=work.id, name=name, priority="P1",
                acceptance=DELIVERY_ACCEPTANCE, status="todo")
    nodes = tuple(
        TaskNode(id=f"{project_id}-{step.key}", task_id=task.id, name=step.name, sequence=index,
                 depends_on=tuple(f"{project_id}-{dep}" for dep in step.depends_on),
                 required_capability_refs=(step.capability_ref,), status="pending")
        for index, step in enumerate(STEPS)
    )
    return SoftwareGraph(project=project, work=work, task=task, nodes=nodes)
