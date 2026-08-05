"""changeflow/rules.py — Change Rule Engine: 4 条变更驱动规则 (Phase 6E, ADR-0020)。

设计依据:
- phase6e-status.md: 4 规则 — ① Validation L4 PASS ② Commit linked Task
  ③ Required files changed ④ Project runtime preference → 各自 PASS/FAIL/SKIP。
- 判定语义 (同 change.analyzer.l4_verdict 聚合哲学, 但更简单): 总判定 =
  任一 ERROR → ERROR > 任一 FAIL → FAIL > 任一 PASS → PASS > 全 SKIP → SKIP
  (SKIP = 规则不适用/无证据, 不得拉低 PASS — 同 validation 聚合语义)。

规则输入 = RuleContext (ChangeWorkflowEngine 装配的只读快照):
- validation_status: 规则①输入 — L4 Change Validation 判定 (None = 未评估)。
- linked_commits: 规则②输入 — 关联到本任务的提交哈希 (CommitLinker 解析)。
- changed_files: 规则②③输入 — 任务变更文件路径 (analyze.files 合并)。
- required_files: 规则③配置 — 触发前置必须变更的文件 (空 = 规则不适用 → SKIP)。
- runtime_pref / available_runtimes: 规则④输入 — 项目偏好 runtime id 与
  已注册且 AVAILABLE 的 runtime 集合 (偏好未配置 → SKIP)。

每条规则为纯函数 (无副作用, 可单测); evaluate_rules 组合 4 规则, 全部
规则 id 恒定 (RULES 元组, Dashboard/CLI 断言依赖)。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import RuleResult

# 规则注册表: 顺序即评估顺序 (稳定, Dashboard/CLI 展示依赖)
RULES = ("validation.l4", "commit.linked", "required.files", "runtime.pref")


class RuleContext(BaseModel):
    """4 规则共享的只读输入快照 (ChangeWorkflowEngine.build_context 装配)。

    字段缺省即\"无证据/未配置\" — 对应规则 SKIP (不适用), 绝不误报 FAIL。
    """

    task_id: str
    project_id: str = ""
    validation_status: str | None = None   # L4 判定 (PASS/FAIL/SKIP/ERROR; None=未评估)
    required_validation: str = "PASS"       # 规则①要求的状态 (ChangeTrigger.required_validation)
    linked_commits: list[str] = Field(default_factory=list)   # 关联提交哈希
    changed_files: list[str] = Field(default_factory=list)    # 任务变更文件路径
    required_files: list[str] = Field(default_factory=list)   # 规则③必需文件 (空=不适用)
    runtime_pref: str | None = None          # 规则④项目偏好 runtime id (None=不适用)
    available_runtimes: set[str] = Field(default_factory=set)  # 已注册 AVAILABLE runtime id


# ------------------------------------------------------------------ 规则①: Validation L4 PASS

def rule_validation_l4(ctx: RuleContext) -> RuleResult:
    """L4 Change Validation 必须达到 required_validation (默认 PASS)。

    - 未评估 (validation_status=None) → SKIP (无证据, 不适用)。
    - 判定 == 要求状态 → PASS; 其余 (FAIL/SKIP/ERROR) → FAIL (评估不通过,
      不触发后续 workflow — 变更证据不足)。
    """
    if ctx.validation_status is None:
        return RuleResult(
            rule_id="validation.l4", status="SKIP",
            message="无 L4 Change Validation 结果 (未评估)",
        )
    if ctx.validation_status == ctx.required_validation:
        return RuleResult(
            rule_id="validation.l4", status="PASS",
            message=f"L4 验证 {ctx.validation_status} == 要求 {ctx.required_validation}",
        )
    return RuleResult(
        rule_id="validation.l4", status="FAIL",
        message=f"L4 验证 {ctx.validation_status} != 要求 {ctx.required_validation}",
    )


# ------------------------------------------------------------------ 规则②: Commit linked Task

def rule_commit_linked(ctx: RuleContext) -> RuleResult:
    """变更必须已关联到任务 (存在解析出 task_id 的提交)。

    - 无任何提交证据 (linked_commits 与 changed_files 皆空) → SKIP (无 git 关联)。
    - 有关联提交 → PASS。
    - 有变更文件但无关联提交 → FAIL (变更疑似未关联任务 — 同 L4.commit_link 语义)。
    """
    if not ctx.linked_commits and not ctx.changed_files:
        return RuleResult(
            rule_id="commit.linked", status="SKIP",
            message="无 git 变更证据 (无关联提交且无变更文件)",
        )
    if ctx.linked_commits:
        return RuleResult(
            rule_id="commit.linked", status="PASS",
            message=f"{len(ctx.linked_commits)} 个提交关联任务 {ctx.task_id}",
        )
    return RuleResult(
        rule_id="commit.linked", status="FAIL",
        message=f"有变更文件但无提交关联任务 {ctx.task_id}",
    )


# ------------------------------------------------------------------ 规则③: Required files changed

def rule_required_files(ctx: RuleContext) -> RuleResult:
    """触发前置的必需文件必须发生变更 (如 CHANGELOG.md / VERSION)。

    - required_files 未配置 (空) → SKIP (规则不适用)。
    - 变更文件覆盖全部必需文件 → PASS。
    - 缺失任一必需文件 → FAIL (发布/验收类前置文件未更新, 不应触发)。
    """
    if not ctx.required_files:
        return RuleResult(
            rule_id="required.files", status="SKIP",
            message="未配置必需文件 (规则不适用)",
        )
    changed = set(ctx.changed_files)
    missing = [f for f in ctx.required_files if f not in changed]
    if not missing:
        return RuleResult(
            rule_id="required.files", status="PASS",
            message=f"必需文件已变更: {', '.join(ctx.required_files)}",
        )
    return RuleResult(
        rule_id="required.files", status="FAIL",
        message=f"必需文件未变更: {', '.join(missing)}",
    )


# ------------------------------------------------------------------ 规则④: Project runtime preference

def rule_runtime_pref(ctx: RuleContext) -> RuleResult:
    """项目偏好 runtime 必须已注册且 AVAILABLE (执行触发工作流的前置条件)。

    - 未配置偏好 (runtime_pref 为空) → SKIP (规则不适用)。
    - 偏好 runtime 在可用集合中 → PASS。
    - 偏好 runtime 未注册/不可用 → FAIL (无执行资源, 不应触发)。
    """
    if not ctx.runtime_pref:
        return RuleResult(
            rule_id="runtime.pref", status="SKIP",
            message="项目未配置 runtime 偏好 (规则不适用)",
        )
    if ctx.runtime_pref in ctx.available_runtimes:
        return RuleResult(
            rule_id="runtime.pref", status="PASS",
            message=f"偏好 runtime {ctx.runtime_pref} 可用",
        )
    return RuleResult(
        rule_id="runtime.pref", status="FAIL",
        message=f"偏好 runtime {ctx.runtime_pref} 未注册或不可用",
    )


# ------------------------------------------------------------------ 组合

def evaluate_rules(ctx: RuleContext) -> list[RuleResult]:
    """按注册表顺序评估 4 规则 (全部规则恒返回, 不短路 — Dashboard 展示完整)。"""
    return [
        rule_validation_l4(ctx),
        rule_commit_linked(ctx),
        rule_required_files(ctx),
        rule_runtime_pref(ctx),
    ]


def overall_status(results: list[RuleResult]) -> str:
    """4 规则总判定 (SKIP 不得拉低 PASS):

    任一 ERROR → ERROR > 任一 FAIL → FAIL > 任一 PASS → PASS > 全 SKIP → SKIP。
    """
    statuses = [r.status for r in results]
    if any(s == "ERROR" for s in statuses):
        return "ERROR"
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    if any(s == "PASS" for s in statuses):
        return "PASS"
    return "SKIP"
