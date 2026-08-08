"""factory-exec/exec/roles.py — 多角色模型 (统一 Employee 抽象, 不复制 Agent)。

Sprint 6: Employee 可绑定多角色 (org Employee.role_ids 已有), 每个角色 =
capabilities + prompt 模板 (角色职责/输出格式) + workflow 阶段映射。执行时
按角色选择 prompt/能力 (EmployeeExecutor 消费本注册表)。

角色清单 (任务要求): ProductManager / UIDesigner / Architect / Developer /
Tester / DevOps — 统一 RoleDefinition 声明式注册, 零 Agent 复制。

诚实标注 (execution_kind):
- "executable": 有真实 LLM 执行路径 (Developer — AgentRuntime/DeveloperAgent
  已实现, production_validate 真实闭环验证; Tester — S7-004 TesterAgent 已实现,
  测试执行确定性 + 失败分析/缺陷报告 LLM 结构化输出; ProductManager — S8-001
  PMAgent 已实现, Idea → 结构化 Product Artifact (7 节) LLM 生成 + CONTRACTS
  product 契约校验)。
- "planning": 角色已定义 (capabilities + prompt 模板 + 阶段映射), 但尚无
  独立 LLM 执行路径 — 只能产出规划产物 (demo_ui_feature 拆解演示走此路径,
  明确标注"规划产物, 非 LLM 执行")。不假装可执行。

设计约束:
- 声明式: 角色 = 数据 (dataclass frozen), 零逻辑; 注册表 dict 单一事实源。
- KISS: 只依赖 stdlib (零 pydantic — 与 templates.py 同构, 减少序列化面)。
- 与 org Role 的关系: org.Role 是权限/责任载体 (Default Deny); 本模块是
  执行能力定义 (prompt/能力/阶段)。两者互补: Employee.role_ids 引用 org
  Role (权限), EmployeeExecutor 按 role_id 查本注册表 (执行 prompt)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RoleError(Exception):
    """角色注册表错误 (未注册 role_id 等)。"""


@dataclass(frozen=True)
class RoleDefinition:
    """声明式角色定义 (capabilities + prompt 模板 + workflow 阶段映射)。

    role_id: 注册表键 (kebab-case, 如 "product-manager")。
    name: 角色显示名 (如 "Product Manager")。
    capabilities: 角色能力集 (与 Employee.capabilities 同词汇, 执行时合并)。
    prompt_template: 角色 prompt (职责说明 + 输出格式) — 执行时按角色选择。
    workflow_stages: 该角色负责的 workflow 阶段 id (验收演示拆解映射)。
    execution_kind: "executable" | "planning" — 诚实标注 (见模块 docstring)。
    """

    role_id: str
    name: str
    capabilities: tuple[str, ...] = ()
    prompt_template: str = ""
    workflow_stages: tuple[str, ...] = ()
    execution_kind: str = "planning"

    @property
    def is_executable(self) -> bool:
        """是否有真实 LLM 执行路径 (当前 Developer + Tester + ProductManager)。"""
        return self.execution_kind == "executable"


# ------------------------------------------------------------------ 角色定义

#: Product Manager — 想法 → 产品分析 (S8-001 executable: PMAgent 已实现,
#: Idea → 结构化 Product Artifact (7 节), 输出 JSON 经 CONTRACTS product 校验)
_PM_PROMPT = (
    "你是一名 Product Manager (产品经理)。职责: 把用户想法 (Idea) 转化为结构化"
    "产品分析产物 (Product Artifact), 覆盖 7 节: 市场分析 (market_analysis) / "
    "用户画像 (user_persona) / 用户旅程 (user_journey) / 问题定义 "
    "(problem_statement) / 功能清单 (feature_list) / MVP 范围 (mvp_scope, "
    "含 in/out 边界) / 用户故事 (user_stories, 每项含 as-a/i-want/so-that)。\n"
    "输出格式: 严格 JSON 对象, 7 节字段齐全, 仅输出 JSON, 不要任何多余文字。"
)

#: UI Designer — 界面/交互设计 (规划角色)
_UI_PROMPT = (
    "你是一名 UI Designer (UI 设计师)。职责: 根据需求设计界面结构与交互, "
    "关注可用性与视觉一致性。\n"
    "输出格式: 设计说明 (界面结构 / 交互流程 / 关键组件 / 状态)。"
)

#: Architect — 架构决策与技术方案 (规划角色)
_ARCH_PROMPT = (
    "你是一名 Architect (架构师)。职责: 决定技术方案、模块划分与关键实现路径, "
    "评估改动影响面。\n"
    "输出格式: 技术方案 (模块结构 / 数据流 / 关键实现点 / 风险)。"
)

#: Developer — 技术实现 (唯一 executable 角色: AgentRuntime/DeveloperAgent 已实现)
_DEV_PROMPT = (
    "你是一名 Developer (开发工程师)。职责: 按需求与技术方案实现代码修改, "
    "保持最小改动与现有风格, 修改后必须通过验证。\n"
    "输出格式: 结构化操作 <operations> JSON 或统一 diff <patch> (由系统执行)。"
)

#: Tester — 测试验证与缺陷分析 (S7-004 executable: TesterAgent 已实现 —
#: 测试执行经确定性验证循环 (unittest/pytest, 不靠 LLM 猜), 失败分析/缺陷报告
#: 经 LLM 结构化输出)
_TESTER_PROMPT = (
    "你是一名 Tester (测试工程师)。职责: 运行测试 (确定性验证循环, unittest/pytest), "
    "分析失败输出, 生成结构化缺陷报告 (bug report: 位置/复现/期望/实际/根因/严重级), "
    "并生成修复任务回传 Developer。测试通过 → 明确通过结论。\n"
    "输出格式: 测试结果 (results: passed/failed 计数) + 缺陷列表 (bugs, 每项含 "
    "location/repro/expected/actual/root_cause/severity) + 修复任务 (repair task)。"
)

#: DevOps — 部署/运维 (规划角色)
_DEVOPS_PROMPT = (
    "你是一名 DevOps 工程师。职责: 部署方案、环境配置与发布流程, 保证交付物"
    "可构建、可运行。\n"
    "输出格式: 部署方案 (构建步骤 / 部署步骤 / 验证步骤 / 回滚)。"
)

ROLE_REGISTRY: dict[str, RoleDefinition] = {
    "product-manager": RoleDefinition(
        role_id="product-manager",
        name="Product Manager",
        capabilities=("requirement", "planning", "product_analysis"),
        prompt_template=_PM_PROMPT,
        workflow_stages=("product",),
        execution_kind="executable",
    ),
    "ui-designer": RoleDefinition(
        role_id="ui-designer",
        name="UI Designer",
        capabilities=("ui_design", "prototyping"),
        prompt_template=_UI_PROMPT,
        workflow_stages=("design",),
        execution_kind="planning",
    ),
    "architect": RoleDefinition(
        role_id="architect",
        name="Architect",
        capabilities=("architecture", "design"),
        prompt_template=_ARCH_PROMPT,
        workflow_stages=("architecture",),
        execution_kind="planning",
    ),
    "developer": RoleDefinition(
        role_id="developer",
        name="Developer",
        capabilities=("coding", "python", "debugging"),
        prompt_template=_DEV_PROMPT,
        workflow_stages=("development",),
        execution_kind="executable",
    ),
    "tester": RoleDefinition(
        role_id="tester",
        name="Tester",
        capabilities=("testing", "verification"),
        prompt_template=_TESTER_PROMPT,
        workflow_stages=("testing",),
        execution_kind="executable",
    ),
    "devops": RoleDefinition(
        role_id="devops",
        name="DevOps",
        capabilities=("deployment", "ops", "release"),
        prompt_template=_DEVOPS_PROMPT,
        workflow_stages=("deployment",),
        execution_kind="planning",
    ),
}

#: 角色清单 (按 role_id 排序, 审计友好)
ROLE_IDS: tuple[str, ...] = tuple(sorted(ROLE_REGISTRY))


# ------------------------------------------------------------------ 注册表 API

def get_role(role_id: str) -> RoleDefinition | None:
    """按 role_id 取角色定义; 未注册 → None (调用方按配置缺口处理)。"""
    return ROLE_REGISTRY.get(role_id)


def require_role(role_id: str) -> RoleDefinition:
    """按 role_id 取角色; 未注册 → RoleError (响亮暴露拼写错误)。"""
    role = ROLE_REGISTRY.get(role_id)
    if role is None:
        raise RoleError(
            f"unknown role: {role_id!r} (available: {', '.join(ROLE_IDS)})"
        )
    return role


def list_roles() -> list[RoleDefinition]:
    """全部角色定义 (按 role_id 排序)。"""
    return [ROLE_REGISTRY[k] for k in ROLE_IDS]


def list_role_dicts() -> list[dict[str, Any]]:
    """角色清单 dict (CLI/报告展示; 只读)。"""
    return [
        {
            "role_id": r.role_id,
            "name": r.name,
            "capabilities": list(r.capabilities),
            "workflow_stages": list(r.workflow_stages),
            "execution_kind": r.execution_kind,
        }
        for r in list_roles()
    ]


def executable_role_ids() -> list[str]:
    """可执行角色 (有真实 LLM 路径) — developer + tester (S7-004) +
    product-manager (S8-001 PMAgent), 诚实标注。"""
    return [r.role_id for r in list_roles() if r.is_executable]


def capabilities_for_role(role_id: str) -> tuple[str, ...]:
    """角色能力集; 未注册 → RoleError。"""
    return require_role(role_id).capabilities


# ------------------------------------------------------------------ 统一角色解析 (S7-001)
# 单一角色注册表 = 本模块 ROLE_REGISTRY (事实源)。org 模板角色 (templates.py)
# 经 role_ref/别名指向本注册表; 一切查找大小写不敏感 (Developer == developer)。
# 向后兼容: require_role/get_role 语义逐位不变 (精确 role_id), 新增 resolve_role
# 是统一的宽松入口 (role_id / 显示名 / 别名), 既有调用零影响。

#: 显示名/别名 → role_id (大小写不敏感; 归一化后查询; 注册表内建名自动覆盖)
ROLE_ALIASES: dict[str, str] = {
    "pm": "product-manager",
    "ui": "ui-designer",
    "dev": "developer",
    "qa": "tester",
    "test engineer": "tester",
    "devops engineer": "devops",
}


def normalize_role_ref(ref: Any) -> str:
    """角色引用归一: strip + 小写 + 折叠空白 (大小写不敏感解析基础)。"""
    return " ".join(str(ref).strip().lower().split())


def _builtin_name_index() -> dict[str, str]:
    """注册表内建名称索引 (显示名归一化 → role_id; 惰性构建, 只读)。"""
    return {
        normalize_role_ref(r.name): r.role_id
        for r in ROLE_REGISTRY.values()
        if r.name
    }


def resolve_role(ref: Any) -> RoleDefinition:
    """统一角色解析 (单一注册表入口, S7-001): 大小写不敏感。

    解析链 (有序):
      1. role_id 精确匹配 (ROLE_REGISTRY 键)
      2. 显示名大小写不敏感匹配 (如 "product manager" / "Product Manager")
      3. 别名匹配 (ROLE_ALIASES, 如 "pm" / "qa")
    未解析 → RoleError (响亮暴露拼写错误, 不静默降级)。
    """
    key = normalize_role_ref(ref)
    role = ROLE_REGISTRY.get(key)
    if role is not None:
        return role
    role = ROLE_REGISTRY.get(_builtin_name_index().get(key, ""))
    if role is not None:
        return role
    role = ROLE_REGISTRY.get(ROLE_ALIASES.get(key, ""))
    if role is not None:
        return role
    raise RoleError(
        f"unknown role: {ref!r} (available: {', '.join(ROLE_IDS)})"
    )


def try_resolve_role(ref: Any) -> RoleDefinition | None:
    """resolve_role 的宽容版本: 未解析 → None (调用方按配置缺口处理)。"""
    try:
        return resolve_role(ref)
    except RoleError:
        return None


#: org 模板角色名 (归一化) → exec 注册表 role_id (S7-001 双体系统一映射)。
#: CEO 为 Human 角色 (最终批准权唯一, 非 Agent), 无 exec 执行角色 — 不入表。
ORG_TEMPLATE_ROLE_MAP: dict[str, str] = {
    "product manager": "product-manager",
    "architect": "architect",
    "developer": "developer",
    "qa": "tester",
}


def org_template_role_map() -> dict[str, str]:
    """org 模板角色 → exec role_id 只读快照 (审计/测试友好, 防外部改表)。"""
    return dict(ORG_TEMPLATE_ROLE_MAP)


def org_role_coverage() -> dict[str, dict[str, Any]]:
    """org 模板角色 → exec 注册表覆盖审计 (S7-001 双体系统一证明)。

    每条: 模板角色名 (归一化) → {role_id, resolved, execution_kind,
    capabilities}; resolved=False 表示该 org 角色在注册表缺失 (审计风险,
    应随角色演进同步补表)。CEO (Human) 不在表内。
    """
    coverage: dict[str, dict[str, Any]] = {}
    for org_name, role_id in ORG_TEMPLATE_ROLE_MAP.items():
        role = ROLE_REGISTRY.get(role_id)
        coverage[org_name] = {
            "role_id": role_id,
            "resolved": role is not None,
            "execution_kind": role.execution_kind if role else "",
            "capabilities": list(role.capabilities) if role else [],
        }
    return coverage


def merge_capabilities(*capability_sets: Any) -> list[str]:
    """多来源能力合并 (去重保序; None/非 list 输入安全跳过)。

    EmployeeExecutor 用: employee.capabilities ∪ 绑定角色 capabilities —
    统一 Employee 抽象 (员工多技能集 + 角色能力), 不复制 Agent。
    """
    merged: list[str] = []
    for caps in capability_sets:
        if not isinstance(caps, (list, tuple)):
            continue
        for c in caps:
            s = str(c).strip()
            if s and s not in merged:
                merged.append(s)
    return merged
