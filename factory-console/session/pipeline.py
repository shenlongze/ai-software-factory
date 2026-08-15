"""factory-console/session/pipeline.py — AI Software Factory Pipeline 规则生成器 (S10-051 P0-P4)。

ProductIntent → PRD → EngineeringPlan → TaskTree → AgentAssignment → Lifecycle
的纯规则管线: 全部确定性规则生成, 不调 LLM、零新依赖 (纯标准库)。

设计: docs/sprint10/S10-051-pipeline-design.md §2-§4

组件:
- ProductDocument  — ProductIntent → PRD.md markdown (6 节: Product Overview /
  Problem / Target User / Core Features / Usage Scenario / Future Direction)
- EngineeringPlan  — PRD → engineering.json (architecture / modules / technical_tasks;
  architecture 按 platform 规则推导: mobile → "Flutter + Backend API" 等)
- TaskTree         — engineering → tasks.json (每模块一个 Epic; 每个 Epic 4 个任务:
  database schema / backend api / frontend page / test; Priority P0/P1;
  Agent Type backend/frontend/qa 规则映射)
- AgentAssignment  — tasks → execution_plan.json (task_id → agent, 复用
  actions.select_agent: frontend→flutter-dev / backend→backend-1 / qa→backend-1)
- Lifecycle        — 生命周期常量 + next_status() (IDEA → ... → DELIVERED)

边界:
- 纯规则生成器, 只产出结构化资产 dict/文本, 不落盘、不执行业务
  (落盘与 Action 编排在 actions.py: generate_prd / prepare_project)
- 不 import actions (避免循环依赖 — actions 引用 pipeline); select_agent 惰性注入
- 确定性: 无时间戳/随机, 同输入同输出 (测试可精确断言)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .intent import IntentObject
from .product import ProductIntent

#: 前端任务特征关键词 (与 actions.select_agent 同口径 — 供默认规则推导注释引用)
#: frontend 任务名含 "前端" → flutter-dev; 其余 → backend-1

#: 架构规则推导 (platform → 架构; 未匹配 → 默认)
ARCHITECTURE_BY_PLATFORM: dict[str, str] = {
    "mobile": "Flutter + Backend API",
    "web": "Web Frontend + Backend API",
    "desktop": "Desktop App + Backend API",
}

#: 默认架构 (platform 未指定/未知)
DEFAULT_ARCHITECTURE = "Backend API + Frontend"

#: 基础技术任务模板 (id, 名称, 类型) — 每个模块 4 个任务
BASE_TECHNICAL_TASKS: tuple[tuple[str, str, str], ...] = (
    ("database_schema", "数据库 Schema 设计", "database"),
    ("backend_api", "后端 API 实现", "backend"),
    ("frontend_page", "前端页面实现", "frontend"),
    ("test_suite", "测试用例编写", "test"),
)

#: 任务类型 → 优先级 (P0 核心 / P1 支撑)
TASK_PRIORITY: dict[str, str] = {
    "database": "P0",
    "backend": "P0",
    "frontend": "P1",
    "test": "P1",
}

#: 任务类型 → Agent Type (AgentAssignment 规则映射输入)
AGENT_TYPE_BY_TASK: dict[str, str] = {
    "database": "backend",
    "backend": "backend",
    "frontend": "frontend",
    "test": "qa",
}


def _slugify(text: str) -> str:
    """宽松 slug 化 (模块/任务 id 推导; 同 actions._slugify 口径, 避免跨模块私有依赖)。"""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    return slug


class Lifecycle:
    """项目生命周期 (设计 §4): IDEA → PRODUCT_DEFINED → ENGINEERING_READY →
    EXECUTION_READY → DEVELOPMENT → TESTING → DELIVERED。

    常量名大写 (设计口径), 值小写 (project.json status 落盘口径, 验收 E)。
    """

    IDEA = "idea"
    PRODUCT_DEFINED = "product_defined"
    ENGINEERING_READY = "engineering_ready"
    EXECUTION_READY = "execution_ready"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DELIVERED = "delivered"

    #: 完整状态序列 (顺序 = 生命周期推进方向)
    STATUSES: tuple[str, ...] = (
        IDEA,
        PRODUCT_DEFINED,
        ENGINEERING_READY,
        EXECUTION_READY,
        DEVELOPMENT,
        TESTING,
        DELIVERED,
    )

    @classmethod
    def next_status(cls, status: Optional[str]) -> Optional[str]:
        """下一个生命周期状态; 未知/已终态 → None (不静默推进)。"""
        if status not in cls.STATUSES:
            return None
        idx = cls.STATUSES.index(status)
        if idx + 1 >= len(cls.STATUSES):
            return None
        return cls.STATUSES[idx + 1]


class ProductDocument:
    """ProductIntent → PRD.md (规则生成, 设计 §4: 不过度智能, 未来 LLM 可替换)。

    from_product_intent(product) -> str: 6 节 markdown —
    Product Overview / Problem / Target User / Core Features / Usage Scenario /
    Future Direction。全部字段来自 ProductIntent, 缺失字段显式占位 (不静默)。
    """

    #: PRD 固定 6 节 (验收 A: Overview/Problem/Target User/Core Features/Usage Scenario/Future)
    SECTIONS: tuple[str, ...] = (
        "Product Overview",
        "Problem",
        "Target User",
        "Core Features",
        "Usage Scenario",
        "Future Direction",
    )

    @classmethod
    def from_product_intent(cls, product: ProductIntent) -> str:
        """ProductIntent → PRD markdown (确定性, 同输入同输出)。"""
        name = product.name or "(未命名产品)"
        platform = product.platform or "未指定"
        features = product.core_features or []
        user = product.user or "(未填写)"
        problem = product.problem or "(未填写)"
        lines = [
            f"# {name} — 产品需求文档 (PRD)",
            "",
            "## Product Overview",
            f"{name} 是一款面向 {user} 的产品, 运行平台: {platform}。",
            "",
            "## Problem",
            problem,
            "",
            "## Target User",
            user,
            "",
            "## Core Features",
        ]
        if features:
            lines.extend(f"- {feature}" for feature in features)
        else:
            lines.append("(待补充)")
        lines.extend(
            [
                "",
                "## Usage Scenario",
                (
                    f"用户在 {platform} 平台上使用 {name}, "
                    f"核心使用场景包括: {', '.join(features) if features else '(待补充)'}。"
                ),
                "",
                "## Future Direction",
                "未来方向: 多端适配 / 数据洞察 / 智能化增强 (规则占位, 后续可由 LLM 增强)。",
                "",
            ]
        )
        return "\n".join(lines)


class EngineeringPlan:
    """PRD → engineering.json (规则生成, 设计 §4): architecture/modules/technical_tasks。

    - architecture: platform 规则推导 (mobile/web/desktop → 对应架构; 其它 → 默认)
    - modules: core_features → 模块列表 [{name, slug}] (空 → 兜底 core 模块)
    - technical_tasks: 基础任务模板 (database/backend/frontend/test)
    """

    @classmethod
    def architecture_for(cls, platform: Optional[str]) -> str:
        """platform → 架构 (未匹配/未指定 → 默认架构)。"""
        if not platform:
            return DEFAULT_ARCHITECTURE
        return ARCHITECTURE_BY_PLATFORM.get(str(platform).strip().lower(), DEFAULT_ARCHITECTURE)

    @classmethod
    def modules_from(cls, product: ProductIntent) -> list[dict[str, str]]:
        """core_features → 模块列表 [{name, slug}] (中文名 slug 为空 → module-<n> 兜底, 保证唯一)。"""
        features = product.core_features or []
        if not features:
            return [{"name": "核心功能", "slug": "core"}]
        modules: list[dict[str, str]] = []
        for idx, feature in enumerate(features):
            slug = _slugify(feature) or f"module-{idx + 1}"
            modules.append({"name": str(feature), "slug": slug})
        return modules

    @classmethod
    def technical_tasks(cls) -> list[dict[str, str]]:
        """基础技术任务模板 (id/name/type — TaskTree 消费)。"""
        return [
            {"id": task_id, "name": name, "type": task_type}
            for task_id, name, task_type in BASE_TECHNICAL_TASKS
        ]

    @classmethod
    def from_prd(
        cls,
        product: ProductIntent,
        prd_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """ProductIntent (+ 可选 PRD 文本) → 工程计划 dict (engineering.json 内容)。

        prd_text 仅作来源标记 (规则管线不解析 PRD 文本 — 未来 LLM 版解析点)。
        """
        return {
            "name": product.name,
            "platform": product.platform,
            "architecture": cls.architecture_for(product.platform),
            "modules": cls.modules_from(product),
            "technical_tasks": cls.technical_tasks(),
            "prd_generated": bool(prd_text),
        }


class TaskTree:
    """engineering.json → tasks.json (设计 §4): 每模块一个 Epic, 每 Epic 4 任务。

    - Epics: [{id: epic-<slug>, name: "<模块> 系统", module}]
    - Tasks: [{id, epic, name, type, priority, agent_type}]
      - priority: database/backend → P0; frontend/test → P1
      - agent_type: database/backend → backend; frontend → frontend; test → qa
    """

    @classmethod
    def from_engineering(cls, plan: dict[str, Any]) -> dict[str, Any]:
        """工程计划 → 任务树 (epics + tasks, 确定性)。"""
        modules = plan.get("modules") or []
        epics: list[dict[str, str]] = []
        tasks: list[dict[str, str]] = []
        for module in modules:
            if isinstance(module, dict):
                mname = str(module.get("name") or "模块")
                mslug = str(module.get("slug") or _slugify(mname) or "core")
            else:
                mname = str(module)
                mslug = _slugify(mname) or "core"
            epic_id = f"epic-{mslug}"
            epics.append({"id": epic_id, "name": f"{mname} 系统", "module": mslug})
            for task_id, task_name, task_type in BASE_TECHNICAL_TASKS:
                tasks.append(
                    {
                        "id": f"task-{mslug}-{task_id}",
                        "epic": epic_id,
                        "name": f"{task_name} ({mname})",
                        "type": task_type,
                        "priority": TASK_PRIORITY.get(task_type, "P1"),
                        "agent_type": AGENT_TYPE_BY_TASK.get(task_type, "backend"),
                    }
                )
        return {"epics": epics, "tasks": tasks, "count": len(tasks)}


class AgentAssignment:
    """tasks.json → execution_plan.json (设计 §4): task_id → agent。

    from_tasks(task_tree, select_agent_fn, context) — select_agent_fn 复用
    actions.select_agent (frontend 任务名含 "前端" → flutter-dev; 其余 → backend-1;
    qa 无专属 agent → backend-1 兜底)。select_agent_fn 缺省 → 惰性 import
    actions.select_agent (避免模块级循环依赖)。
    """

    @classmethod
    def from_tasks(
        cls,
        task_tree: dict[str, Any],
        select_agent_fn: Optional[Callable[..., str]] = None,
        context: Any = None,
    ) -> dict[str, Any]:
        """任务树 → 分配结果 {"tasks": [{id, name, agent_type, agent}], "count"}。"""
        if select_agent_fn is None:
            from .actions import select_agent as _default_select

            select_agent_fn = _default_select
        tasks = task_tree.get("tasks") or []
        assignments: list[dict[str, Any]] = []
        for task in tasks:
            task_id = str(task.get("id") or "")
            task_name = str(task.get("name") or task_id)
            intent = IntentObject(
                intent_type="run_task",
                params={"objective": task_name},
                raw=task_name,
            )
            # select_agent_fn 签名兼容: (intent, context) / (intent) 均可
            try:
                agent = select_agent_fn(intent, context)  # type: ignore[operator]
            except TypeError:
                agent = select_agent_fn(intent)  # type: ignore[operator]
            assignments.append(
                {
                    "id": task_id,
                    "name": task_name,
                    "agent_type": task.get("agent_type"),
                    "agent": str(agent),
                }
            )
        return {"tasks": assignments, "count": len(assignments)}
