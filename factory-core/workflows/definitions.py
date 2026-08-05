"""workflows/definitions.py — 内置工作流定义。

设计依据:
- phase4a-status.md: 内置 workflow 定义 (desktop-feature: architecture→development→testing→validation)
- docs/design/workflow-model.md 在仓库中不存在 (同 ADR-0004 决策 4 的缺失文档情形),
  内置定义集以任务指令为准: feature-delivery (Task.workflow 默认值, 保证 CLI run 开箱可用) +
  desktop-feature + bug-fix + release 示例。

步骤的 required_skill/required_role 为声明性元数据 (后续 Phase 的 Agent Runtime 消费),
本阶段不自动分配、不校验存在性 (phase4a-status.md §禁止)。
"""

from __future__ import annotations

from .models import Workflow, WorkflowStep


def _feature_steps() -> list[WorkflowStep]:
    """特性类主干: 架构 → 开发 → 测试 → 独立验收 (phase4a-status.md)。"""
    return [
        WorkflowStep(id="architecture", name="架构设计", order=1,
                     required_skill="architecture", required_role="product-manager"),
        WorkflowStep(id="development", name="编码开发", order=2,
                     required_skill="development", required_role="backend-developer"),
        WorkflowStep(id="testing", name="测试验证", order=3,
                     required_skill="testing", required_role="test-engineer"),
        WorkflowStep(id="validation", name="独立验收", order=4,
                     required_skill="validation", required_role="test-engineer"),
    ]


def _bug_steps() -> list[WorkflowStep]:
    """缺陷修复主干: 复现 → 定位 → 修复 → 验证 (Bug 流程的压缩主干)。"""
    return [
        WorkflowStep(id="reproduce", name="复现缺陷", order=1,
                     required_skill="testing", required_role="test-engineer"),
        WorkflowStep(id="diagnose", name="定位根因", order=2,
                     required_skill="debugging", required_role="backend-developer"),
        WorkflowStep(id="fix", name="修复代码", order=3,
                     required_skill="development", required_role="backend-developer"),
        WorkflowStep(id="verify", name="回归验证", order=4,
                     required_skill="testing", required_role="test-engineer"),
    ]


def _release_steps() -> list[WorkflowStep]:
    """发布主干: 构建 → 测试 → 预发布 → 发布。"""
    return [
        WorkflowStep(id="build", name="构建产物", order=1,
                     required_skill="build", required_role="ops-engineer"),
        WorkflowStep(id="test", name="全量测试", order=2,
                     required_skill="testing", required_role="test-engineer"),
        WorkflowStep(id="stage", name="预发布验证", order=3,
                     required_skill="ops", required_role="ops-engineer"),
        WorkflowStep(id="publish", name="正式发布", order=4,
                     required_skill="release", required_role="ops-engineer"),
    ]


# 内置定义表: id → Workflow。feature-delivery 与 Task.workflow 默认值对齐 (tasks/models.py)。
BUILTIN_WORKFLOWS: dict[str, Workflow] = {
    "feature-delivery": Workflow(
        id="feature-delivery", name="功能交付",
        description="特性交付主干: 架构 → 开发 → 测试 → 独立验收",
        steps=_feature_steps(),
    ),
    "desktop-feature": Workflow(
        id="desktop-feature", name="桌面功能",
        description="桌面端特性主干: 架构 → 开发 → 测试 → 独立验收",
        steps=_feature_steps(),
    ),
    "bug-fix": Workflow(
        id="bug-fix", name="缺陷修复",
        description="缺陷修复主干: 复现 → 定位 → 修复 → 回归验证",
        steps=_bug_steps(),
    ),
    "release": Workflow(
        id="release", name="版本发布",
        description="发布主干: 构建 → 全量测试 → 预发布验证 → 正式发布",
        steps=_release_steps(),
    ),
}


def get_builtin(workflow_id: str) -> Workflow | None:
    """按 id 取内置定义; 不存在返回 None。"""
    wf = BUILTIN_WORKFLOWS.get(workflow_id)
    return None if wf is None else wf.model_copy(deep=True)


def list_builtins() -> list[Workflow]:
    """全部内置定义 (按 id 排序)。"""
    return [BUILTIN_WORKFLOWS[k].model_copy(deep=True) for k in sorted(BUILTIN_WORKFLOWS)]
