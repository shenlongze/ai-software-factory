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
    EXECUTION_READY → DEVELOPMENT → TESTING → VALIDATION_PASS →
    USER_ACCEPTANCE → DELIVERED。

    常量名大写 (设计口径), 值小写 (project.json status 落盘口径, 验收 E)。
    S10-053 P1 (设计 §4): VALIDATION_PASS 质量门 — TESTING 之后, DELIVERED 之前;
    无 ValidationResult.success 禁止进入 DELIVERED (停留在 TESTING/DEVELOPMENT)。
    S10-055 Task 005 (验收 E/F): USER_ACCEPTANCE 人工验收门 — VALIDATION_PASS
    之后, DELIVERED 之前; 执行完成 + 验证通过后停在 USER_ACCEPTANCE (待验收),
    经 accept_project 用户确认才进入 DELIVERED (不自动交付)。
    """

    IDEA = "idea"
    PRODUCT_DEFINED = "product_defined"
    ENGINEERING_READY = "engineering_ready"
    EXECUTION_READY = "execution_ready"
    DEVELOPMENT = "development"
    TESTING = "testing"
    VALIDATION_PASS = "validation_pass"
    USER_ACCEPTANCE = "user_acceptance"
    DELIVERED = "delivered"

    #: 完整状态序列 (顺序 = 生命周期推进方向)
    STATUSES: tuple[str, ...] = (
        IDEA,
        PRODUCT_DEFINED,
        ENGINEERING_READY,
        EXECUTION_READY,
        DEVELOPMENT,
        TESTING,
        VALIDATION_PASS,
        USER_ACCEPTANCE,
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


class FeatureTaskGenerator:
    """功能级 Task 生成器 (S10-055 Task 002, 验收 A/B): core_features → Epic/Task。

    与 TaskTree 的差异: TaskTree 按工程模块 × 技术层 (db/api/frontend/test) 生成
    模板任务; FeatureTaskGenerator 按用户功能 (core_features) 归类 Epic, 每个 Epic
    生成用户可感知的功能任务 (创建比赛/记录比分/保存历史/积分排名/统计/UI 交互…),
    非技术模板 (验收 A: 无 database_schema/backend_api/frontend_page/test_suite)。

    台球计分示例 (验收 B): core_features=[计分, 比赛记录, 排行榜] →
      Epic 比赛系统 (创建比赛/记录比分/保存历史) + Epic 排行榜 (积分排名/统计)
      + Epic 客户端 (UI 交互, platform=mobile → flutter; web → web)。

    结构: {"epics": [{id, name, features: [{name, tasks: [{id, name, agent_type,
    priority}]}]}], "tasks": [扁平视图 — 含 epic/epic_id/feature 归属, 供
    AgentAssignment / ExecutionOrchestrator (Feature Level Execution) /
    ProductProgressTracker 消费], "count"}。
    """

    #: 客户端 Epic 名称 (UI/交互 — 固定生成, 平台适配任务)
    CLIENT_EPIC_NAME = "客户端"

    #: 功能关键词 → Epic 名称 (顺序匹配第一个命中; 未命中 → f"{feature} 系统")
    FEATURE_EPIC_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
        (("比赛", "对局", "计分", "记分", "比分", "记录"), "比赛系统"),
        (("排行", "排名", "积分榜", "榜单"), "排行榜"),
        (("用户", "账号", "登录", "注册"), "用户系统"),
        (("支付", "订单", "购买", "商城"), "支付系统"),
    )

    #: 已知 Epic → 稳定 slug (中文名无 ASCII slug — 显式映射保证 id 确定性)
    EPIC_SLUGS: dict[str, str] = {
        "比赛系统": "match",
        "排行榜": "ranking",
        "用户系统": "user",
        "支付系统": "payment",
        "客户端": "client",
    }

    #: 功能关键词 → 功能任务 (id 后缀, 名称, agent_type, priority)
    #: 用户可感知功能, 非技术模板 (验收 A 口径)
    FEATURE_TASK_RULES: tuple[
        tuple[tuple[str, ...], tuple[tuple[str, str, str, str], ...]], ...
    ] = (
        (("比赛", "对局"), (("create-match", "创建比赛", "backend", "P0"),)),
        (
            ("计分", "记分", "比分", "双人计分"),
            (("record-score", "记录比分", "backend", "P0"),),
        ),
        (
            ("记录", "历史", "存档", "保存"),
            (("save-history", "保存历史", "backend", "P1"),),
        ),
        (
            ("排行", "排名", "积分榜"),
            (("ranking", "积分排名", "backend", "P1"), ("stats", "统计", "backend", "P1")),
        ),
        (
            ("用户", "账号", "登录"),
            (("register", "注册登录", "backend", "P0"), ("profile", "用户资料", "backend", "P1")),
        ),
        (("支付", "订单", "购买"), (("checkout", "下单支付", "backend", "P0"),)),
    )

    #: 未命中任何功能规则的兜底任务 (功能化命名, 非技术模板)
    FALLBACK_TASK_SUFFIXES: tuple[tuple[str, str, str, str], ...] = (
        ("core", "核心功能", "backend", "P0"),
        ("manage", "数据管理", "backend", "P1"),
        ("view", "界面展示", "frontend", "P1"),
    )

    #: 客户端 Epic → 平台适配任务 (platform=mobile → flutter 前端; web → web 前端)
    CLIENT_PLATFORM_TASKS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
        "mobile": (("ui-mobile", "客户端界面与交互", "frontend", "P1"),),
        "web": (("ui-web", "Web 界面与交互", "frontend", "P1"),),
        "desktop": (("ui-desktop", "桌面界面与交互", "frontend", "P1"),),
    }
    DEFAULT_CLIENT_TASKS: tuple[tuple[str, str, str, str], ...] = (
        ("ui", "界面与交互", "frontend", "P1"),
    )

    #: 任务缺省落组名 (旧式 execution_plan 无 feature 字段 — 向后兼容分组)
    UNGROUPED_FEATURE = "未分组"

    @classmethod
    def epic_for_feature(cls, feature: str) -> str:
        """功能文本 → Epic 名称 (关键词规则优先; 未命中 → f"{feature} 系统")。"""
        for keywords, epic_name in cls.FEATURE_EPIC_RULES:
            if any(keyword in feature for keyword in keywords):
                return epic_name
        return f"{feature} 系统"

    @classmethod
    def tasks_for_feature(cls, feature: str) -> list[tuple[str, str, str, str]]:
        """功能文本 → 功能任务列表 (全部命中规则合并; 未命中 → 兜底任务)。"""
        matched: list[tuple[str, str, str, str]] = []
        for keywords, tasks in cls.FEATURE_TASK_RULES:
            if any(keyword in feature for keyword in keywords):
                matched.extend(tasks)
        if matched:
            return matched
        return [
            (suffix, f"{feature} {name}", agent, priority)
            for suffix, name, agent, priority in cls.FALLBACK_TASK_SUFFIXES
        ]

    @classmethod
    def _epic_id(cls, epic_name: str, seq: int) -> str:
        """Epic id: 已知 slug 优先; 未知中文名 → epic-e<seq> 兜底 (保证唯一)。"""
        slug = cls.EPIC_SLUGS.get(epic_name)
        if slug:
            return f"epic-{slug}"
        return f"epic-{_slugify(epic_name) or f'e{seq}'}"

    @classmethod
    def from_product(cls, product: ProductIntent) -> dict[str, Any]:
        """ProductIntent → 功能级任务树 (epics 嵌套 + tasks 扁平, 确定性)。

        每 core_feature → 功能 Epic (关键词归类合并); 任务 = 该功能命中的功能任务
        (同一 Epic 内按任务名去重, 防跨 feature 重复 id); 末尾固定生成 客户端 Epic
        (UI/交互, 平台适配)。空 core_features → 仅客户端 Epic (兜底, 不报错)。
        """
        features = [
            str(feature).strip()
            for feature in (product.core_features or [])
            if str(feature).strip()
        ]
        epics: dict[str, dict[str, Any]] = {}
        seen_ids: dict[str, set[str]] = {}
        flat_tasks: list[dict[str, Any]] = []
        for feature in features:
            epic_name = cls.epic_for_feature(feature)
            if epic_name not in epics:
                epic_id = cls._epic_id(epic_name, len(epics) + 1)
                epics[epic_name] = {
                    "id": epic_id,
                    "name": epic_name,
                    "features": [],
                }
                seen_ids[epic_name] = set()
            epic = epics[epic_name]
            feature_tasks = cls.tasks_for_feature(feature)
            ftasks: list[dict[str, str]] = []
            for suffix, name, agent_type, priority in feature_tasks:
                task_id = f"task-{epic['id'].split('epic-', 1)[-1]}-{suffix}"
                if task_id in seen_ids[epic_name]:
                    continue  # 同 Epic 跨 feature 去重 (防重复 id)
                seen_ids[epic_name].add(task_id)
                ftasks.append(
                    {
                        "id": task_id,
                        "name": name,
                        "agent_type": agent_type,
                        "priority": priority,
                    }
                )
                flat_tasks.append(
                    {
                        "id": task_id,
                        "name": name,
                        "epic": epic_name,
                        "epic_id": epic["id"],
                        "feature": feature,
                        "agent_type": agent_type,
                        "priority": priority,
                    }
                )
            epic["features"].append({"name": feature, "tasks": ftasks})
        # 客户端 Epic (UI/交互 — 平台适配, 验收 B)
        client_id = cls._epic_id(cls.CLIENT_EPIC_NAME, len(epics) + 1)
        platform = str(product.platform or "").strip().lower()
        client_tasks = cls.CLIENT_PLATFORM_TASKS.get(platform, cls.DEFAULT_CLIENT_TASKS)
        client_feature: dict[str, Any] = {"name": cls.CLIENT_EPIC_NAME, "tasks": []}
        for suffix, name, agent_type, priority in client_tasks:
            task_id = f"task-client-{suffix}"
            client_feature["tasks"].append(
                {
                    "id": task_id,
                    "name": name,
                    "agent_type": agent_type,
                    "priority": priority,
                }
            )
            flat_tasks.append(
                {
                    "id": task_id,
                    "name": name,
                    "epic": cls.CLIENT_EPIC_NAME,
                    "epic_id": client_id,
                    "feature": cls.CLIENT_EPIC_NAME,
                    "agent_type": agent_type,
                    "priority": priority,
                }
            )
        epics[cls.CLIENT_EPIC_NAME] = {
            "id": client_id,
            "name": cls.CLIENT_EPIC_NAME,
            "features": [client_feature],
        }
        return {"epics": list(epics.values()), "tasks": flat_tasks, "count": len(flat_tasks)}


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
                    # S10-055 Task 004: 功能归属透传 (Feature Level Execution —
                    # execution_state 记录 task.feature; 旧式 plan 无此字段 → 兼容)
                    "feature": task.get("feature"),
                    "epic": task.get("epic"),
                }
            )
        return {"tasks": assignments, "count": len(assignments)}
