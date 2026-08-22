"""factory-console/session/expert_factory.py — 专家装配器 (M2 A3, S10-087, 核心)。

"造专家": ExpertFactory.assemble(role, industry, skills, knowledge_ref,
workflow_ref, provider) → AgentEntity; 校验 skill 存在 / workflow 可执行 /
knowledge 可挂载; 装配出 7 个软件行业专家 (pm→market→competitive→ux→
architect→qa→prd), 供 HandoffBus 走真 Agent 链。

契约 (S10-087-M2 §2):
1. 缺 skill → ExpertAssemblyError 明确报错 (不静默, 列缺失技能)
2. workflow_ref 非空 → 必须可执行 (workflows 内置目录 BUILTIN_WORKFLOWS)
3. knowledge_ref 非空 → 必须可挂载 (知识源目录; 知识图谱 M5-M7 后置)
4. 无 LLM (provider=None) → 确定性兜底可用 (deterministic_content 非空)
5. id 一律 agt-<industry>-<role>-<n> (委托 agent_registry.next_id)

职责边界:
- 装配 = 身份/能力校验 + 生成 AgentEntity (不执行)
- 执行/产出在 pipeline_runner (LLM 或确定性兜底经本模块 deterministic_content)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .agent_entity import AgentEntity, ProviderRef
from .agent_registry import AgentRegistry
from .core_loader import load_core
from .product import ProductIntent

#: 默认行业 (软件行业 — M2 主验收面)
DEFAULT_INDUSTRY = "it"

#: 默认产品管线 7 角色链 (PM→Market→Competitive→UX→Architect→QA→SeniorPM,
#: 与既有 artifact 类型一一对应 — M1 零回归)
PIPELINE_ROLES: tuple[str, ...] = (
    "pm", "market", "competitive", "ux", "architect", "qa", "prd",
)

#: 软件行业专家技能目录 (能力描述非执行; 装配校验的存在性来源)
EXPERT_SKILLS: dict[str, dict[str, Any]] = {
    "product_strategy": {
        "name": "product_strategy",
        "category": "product",
        "description": "产品定位/用户价值/核心能力/商业模式策略",
        "capabilities": ["product_positioning", "value_proposition", "business_model"],
        "version": "1.0.0",
    },
    "market_research": {
        "name": "market_research",
        "category": "market",
        "description": "市场规模/用户趋势/机会窗口分析",
        "capabilities": ["market_size", "user_trend", "opportunity_window"],
        "version": "1.0.0",
    },
    "competitor_analysis": {
        "name": "competitor_analysis",
        "category": "market",
        "description": "直接/间接竞品、替代方案、差异化机会分析",
        "capabilities": ["competitor_mapping", "differentiation", "substitution"],
        "version": "1.0.0",
    },
    "ux_design": {
        "name": "ux_design",
        "category": "design",
        "description": "用户流程/页面结构/信息架构设计",
        "capabilities": ["user_flow", "information_architecture", "wireframe"],
        "version": "1.0.0",
    },
    "system_architecture": {
        "name": "system_architecture",
        "category": "architecture",
        "description": "技术选型/系统设计/数据模型/风险分析",
        "capabilities": ["tech_selection", "system_design", "data_modeling", "risk_analysis"],
        "version": "1.0.0",
    },
    "backend_engineering": {
        "name": "backend_engineering",
        "category": "backend",
        "description": "后端 API/数据库/服务实现设计",
        "capabilities": ["backend_api", "database_schema", "service_design"],
        "version": "1.0.0",
    },
    "quality_assurance": {
        "name": "quality_assurance",
        "category": "quality",
        "description": "单元/集成/安全/性能测试方案设计",
        "capabilities": ["test_plan", "test_case", "quality_gate"],
        "version": "1.0.0",
    },
    "prd_writing": {
        "name": "prd_writing",
        "category": "product",
        "description": "产品需求文档编写 (背景/用户故事/功能需求/验收标准)",
        "capabilities": ["prd_structure", "user_story", "acceptance_criteria"],
        "version": "1.0.0",
    },
}

#: 知识源目录 (knowledge_ref 可挂载面 — 真实存在的知识资产; 知识图谱 M5-M7 后置)
KNOWLEDGE_SOURCES: tuple[str, ...] = (
    "product_intelligence",  # session/product_intelligence.py (8 分析引擎)
    "engineering_plan",      # session/pipeline.py EngineeringPlan
    "context_ledger",        # session/context_ledger.py
    "evidence",              # session/evidence.py EvidenceBundle
)

#: 角色定义: role → 标题/资产类型/系统提示词/默认技能/默认知识/默认流程
ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "pm": {
        "title": "产品经理",
        "artifact_type": "product",
        "system_prompt": (
            "你是软件行业产品经理。输出产品策略: 产品定位/用户价值/核心能力/"
            "非目标范围/商业模式, 中文 markdown, 基于上一角色产出与产品信息。"
        ),
        "skills": ["product_strategy", "market_research"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
    "market": {
        "title": "市场分析师",
        "artifact_type": "market_analysis",
        "system_prompt": (
            "你是软件行业市场分析师。输出市场分析: 市场规模/用户趋势/机会窗口, "
            "中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["market_research"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
    "competitive": {
        "title": "竞品分析师",
        "artifact_type": "competitive_analysis",
        "system_prompt": (
            "你是软件行业竞品分析师。输出竞品分析: 直接竞品/间接竞品/替代方案/"
            "机会点, 中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["competitor_analysis"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
    "ux": {
        "title": "UX 设计师",
        "artifact_type": "ux_flow",
        "system_prompt": (
            "你是软件行业 UX 设计师。输出用户体验: 用户流程/页面结构/信息架构, "
            "中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["ux_design"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
    "architect": {
        "title": "软件架构师",
        "artifact_type": "architecture",
        "system_prompt": (
            "你是软件行业架构师。输出架构设计: 技术选型/系统设计/数据模型/风险, "
            "中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["system_architecture", "backend_engineering"],
        "knowledge_ref": "engineering_plan",
        "workflow_ref": "feature-delivery",
    },
    "backend": {
        "title": "后端工程师",
        "artifact_type": "backend_design",
        "system_prompt": (
            "你是软件行业后端工程师。输出后端设计: API 设计/数据模型/服务拆分, "
            "中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["backend_engineering"],
        "knowledge_ref": "engineering_plan",
        "workflow_ref": "feature-delivery",
    },
    "qa": {
        "title": "QA 负责人",
        "artifact_type": "test_plan",
        "system_prompt": (
            "你是软件行业 QA 负责人。输出测试方案: 单元/集成/安全/性能测试, "
            "中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["quality_assurance"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
    "prd": {
        "title": "资深产品经理 (SeniorPM)",
        "artifact_type": "prd",
        "system_prompt": (
            "你是软件行业资深产品经理。基于全部上游产出输出详细 PRD: 背景/"
            "用户故事/功能需求/验收标准, 中文 markdown, 消费上一角色产出。"
        ),
        "skills": ["prd_writing", "product_strategy"],
        "knowledge_ref": "product_intelligence",
        "workflow_ref": "feature-delivery",
    },
}


class ExpertAssemblyError(Exception):
    """专家装配失败 (缺 skill / workflow 不可执行 / knowledge 不可挂载)。

    消息明确列出失败面 — 不静默降级 (契约 §2.3)。
    """


def _builtin_skill_ids() -> set[str]:
    """core/agents/skills.py 内置技能 id 集合 (只读; 加载失败 → 空, 失败安全)。"""
    try:
        skills = load_core("agents.skills")
        return set(getattr(skills, "builtin_skill_ids", lambda: [])())
    except Exception:  # noqa: BLE001 — 失败安全
        return set()


def _builtin_workflow_ids() -> set[str]:
    """core/workflows/definitions.py 内置流程 id 集合 (只读; 失败安全 → 空)。"""
    try:
        definitions = load_core("workflows.definitions")
        wfs = getattr(definitions, "list_builtins", lambda: [])()
        return {str(getattr(wf, "id", "")) for wf in wfs if getattr(wf, "id", "")}
    except Exception:  # noqa: BLE001 — 失败安全
        return set()


class ExpertFactory:
    """专家装配器: 校验 + 生成 AgentEntity (身份层, 不执行)。

    可注入校验器 (测试/未来注册表):
    - skill_exists(skill_id) -> bool   (缺省: EXPERT_SKILLS + core 内置技能)
    - workflow_executable(wf_id) -> bool (缺省: BUILTIN_WORKFLOWS)
    - knowledge_mountable(ref) -> bool (缺省: KNOWLEDGE_SOURCES)
    - registry: AgentRegistry (id 编号/落盘; 缺省独立实例, 不自动落盘)
    """

    def __init__(
        self,
        *,
        skill_exists: Optional[Callable[[str], bool]] = None,
        workflow_executable: Optional[Callable[[str], bool]] = None,
        knowledge_mountable: Optional[Callable[[str], bool]] = None,
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        self._skill_exists = skill_exists or self._default_skill_exists
        self._workflow_executable = workflow_executable or self._default_workflow_executable
        self._knowledge_mountable = knowledge_mountable or self._default_knowledge_mountable
        self._registry = registry if registry is not None else AgentRegistry()

    # ------------------------------------------------------------ 缺省校验

    @staticmethod
    def _default_skill_exists(skill_id: str) -> bool:
        """缺省技能存在性: EXPERT_SKILLS ∪ core 内置技能 (只读)。"""
        sid = str(skill_id or "").strip()
        if not sid:
            return False
        if sid in EXPERT_SKILLS:
            return True
        return sid in _builtin_skill_ids()

    @staticmethod
    def _default_workflow_executable(workflow_id: str) -> bool:
        """缺省流程可执行性: workflows 内置目录。"""
        wid = str(workflow_id or "").strip()
        if not wid:
            return False
        return wid in _builtin_workflow_ids()

    @staticmethod
    def _default_knowledge_mountable(ref: str) -> bool:
        """缺省知识可挂载性: 知识源目录。"""
        r = str(ref or "").strip()
        if not r:
            return False
        return r in KNOWLEDGE_SOURCES

    # ------------------------------------------------------------ 装配

    def assemble(
        self,
        role: str,
        *,
        industry: str = DEFAULT_INDUSTRY,
        skills: Optional[list[str]] = None,
        knowledge_ref: str = "",
        workflow_ref: str = "",
        provider: Optional[ProviderRef] = None,
        system_prompt: str = "",
    ) -> AgentEntity:
        """装配一个专家: 校验 skill/workflow/knowledge → AgentEntity (agt- id)。

        缺 skill / 不可执行 / 不可挂载 → ExpertAssemblyError 明确报错。
        provider=None → 无 LLM 确定性兜底可用 (deterministic_content 非空)。
        """
        role = str(role or "").strip().lower()
        spec = ROLE_DEFINITIONS.get(role)
        if spec is None:
            valid = ", ".join(sorted(ROLE_DEFINITIONS))
            raise ExpertAssemblyError(f"未知专家角色: {role!r} (支持: {valid})")
        industry = str(industry or "").strip().lower()

        wanted = list(dict.fromkeys(skills or spec["skills"]))
        missing = [s for s in wanted if not self._skill_exists(s)]
        if missing:
            raise ExpertAssemblyError(
                f"装配角色 {role} 失败: 引用不存在/不可用的 skill: "
                f"{', '.join(missing)} (技能目录: {', '.join(sorted(EXPERT_SKILLS))})"
            )

        knowledge = str(knowledge_ref or spec.get("knowledge_ref") or "").strip()
        if knowledge and not self._knowledge_mountable(knowledge):
            raise ExpertAssemblyError(
                f"装配角色 {role} 失败: knowledge 不可挂载: {knowledge!r} "
                f"(知识源: {', '.join(KNOWLEDGE_SOURCES)})"
            )

        workflow = str(workflow_ref or spec.get("workflow_ref") or "").strip()
        if workflow and not self._workflow_executable(workflow):
            raise ExpertAssemblyError(
                f"装配角色 {role} 失败: workflow 不可执行: {workflow!r} "
                f"(内置流程: feature-delivery/desktop-feature/bug-fix/release)"
            )

        agent_id = self._registry.next_id(industry, role)
        prompt = system_prompt or spec["system_prompt"]
        return AgentEntity(
            id=agent_id,
            role=role,
            industry=industry,
            provider=provider,
            system_prompt=prompt,
            skills=wanted,
            knowledge_ref=knowledge,
            workflow_ref=workflow,
            tools=[],
            evaluation_ref="",
            profile=AgentEntity.model_fields["profile"].default_factory(),
        )

    def build_team(
        self,
        *,
        industry: str = DEFAULT_INDUSTRY,
        roles: Optional[list[str]] = None,
        provider: Optional[ProviderRef] = None,
        persist: bool = True,
    ) -> list[AgentEntity]:
        """装配专家团队 (缺省: 产品管线 7 角色链 pm→…→prd) + 落盘注册表。

        S10-088 T4: 装配后逐 agent registry.add 落盘 agents.json (专家可见,
        'expert build' 语义内置); persist=False → 仅装配不落盘 (测试/临时装配
        兼容, 不破坏既有调用面)。

        逐角色 assemble — 任一角色装配失败 → ExpertAssemblyError (整队失败,
        不静默跳过, 契约 §2.6); 落盘失败 → AgentRegistryError 明确报错。
        """
        role_list = list(roles or PIPELINE_ROLES)
        team = [
            self.assemble(role, industry=industry, provider=provider)
            for role in role_list
        ]
        if persist:
            for agent in team:
                self._registry.add(agent)
        return team

    # ------------------------------------------------------------ 确定性兜底

    def deterministic_content(self, role: str, product: ProductIntent) -> str:
        """无 LLM 确定性兜底 (契约 §2.5): 各角色产出非空 markdown。

        复用 ProductIntelligenceEngine / pipeline.ProductDocument (不复制业务);
        任何单角色兜底失败 → 非空规则占位 (仍非空, 可审计)。
        """
        role = str(role or "").strip().lower()
        generators = {
            "pm": self._pm_md,
            "market": self._market_md,
            "competitive": self._competitive_md,
            "ux": self._ux_md,
            "architect": self._architect_md,
            "backend": self._backend_md,
            "qa": self._qa_md,
            "prd": self._prd_md,
        }
        fn = generators.get(role)
        if fn is None:
            return f"# {role}\n(规则占位)"
        try:
            return fn(product)
        except Exception:  # noqa: BLE001 — 兜底: 单角色引擎异常 → 非空占位
            return f"# {role}\n\n## 产出\n(规则占位 — 确定性兜底异常, 非空可审计)\n"

    # ------------------------------------------------------------ 各角色模板

    @staticmethod
    def _pm_md(product: ProductIntent) -> str:
        name = product.name or "(未命名产品)"
        features = "、".join(product.core_features) if product.core_features else "(待补充)"
        return (
            f"# 产品策略: {name}\n\n"
            f"## 产品定位\n面向 {product.user or '(待补充)'} 的 {name}。\n\n"
            f"## 用户价值\n{product.problem or '(待补充)'}\n\n"
            f"## 核心能力\n- {features}\n\n"
            f"## 非目标范围\n第一版不做: 多端高级定制 / 复杂权限 / 深度数据分析 "
            f"(规则占位, LLM 可细化)。\n\n"
            f"## 商业模式\n待评估 (规则占位: 订阅 / 买断 / 增值服务)。\n"
        )

    @staticmethod
    def _market_md(product: ProductIntent) -> str:
        try:
            from .product_intelligence import ProductIntelligenceEngine

            m = ProductIntelligenceEngine().analyze_market(product)
            trends = "\n".join(f"- {t}" for t in (m.user_trends or [])) or "- (待补充)"
            return (
                f"# 市场分析: {product.name or '(未命名产品)'}\n\n"
                f"## 市场规模\n{m.market_size or '(待补充)'}\n\n"
                f"## 用户趋势\n{trends}\n\n"
                f"## 机会窗口\n{m.opportunity_window or '(待补充)'}\n"
            )
        except Exception:  # noqa: BLE001 — 失败安全
            return "# 市场分析\n\n## 市场规模\n(待补充)\n\n## 用户趋势\n(待补充)\n\n## 机会窗口\n(待补充)\n"

    @staticmethod
    def _competitive_md(product: ProductIntent) -> str:
        try:
            from .product_intelligence import ProductIntelligenceEngine

            c = ProductIntelligenceEngine().analyze_competitor(product)
            comp_lines = []
            for comp in c.competitors or []:
                comp_lines.append(
                    f"- {comp.get('name') or '(未命名)'} ({comp.get('category') or '未知'}): "
                    f"优势 {', '.join(comp.get('strengths') or []) or '(待补充)'}"
                )
            if not comp_lines:
                comp_lines.append("- (待补充)")
            adv = "\n".join(f"- {a}" for a in (c.advantages or [])) or "- (待补充)"
            diff = "\n".join(
                f"- {d}" for d in (c.differentiation_opportunities or [])
            ) or "- (待补充)"
            return (
                f"# 竞品分析: {product.name or '(未命名产品)'}\n\n"
                f"## 竞品\n{chr(10).join(comp_lines)}\n\n"
                f"## 自身优势\n{adv}\n\n"
                f"## 差异化机会\n{diff}\n"
            )
        except Exception:  # noqa: BLE001 — 失败安全
            return "# 竞品分析\n\n## 竞品\n(待补充)\n\n## 差异化机会\n(待补充)\n"

    @staticmethod
    def _ux_md(product: ProductIntent) -> str:
        features = product.core_features or ["(待补充)"]
        flows = []
        for f in features:
            flows.append(f"- {f}: 进入 → 操作 → 完成/反馈")
        return (
            f"# 用户体验: {product.name or '(未命名产品)'}\n\n"
            f"## 用户流程\n{chr(10).join(flows)}\n\n"
            f"## 页面结构\n首页 / 功能页 / 设置 (规则占位, UX 可细化)\n\n"
            f"## 信息架构\n按核心功能导航: {' / '.join(features)}\n"
        )

    @staticmethod
    def _architect_md(product: ProductIntent) -> str:
        try:
            from .pipeline import ARCHITECTURE_BY_PLATFORM, DEFAULT_ARCHITECTURE

            platform = (product.platform or "").lower()
            arch = ARCHITECTURE_BY_PLATFORM.get(platform, DEFAULT_ARCHITECTURE)
        except Exception:  # noqa: BLE001
            arch = "Backend API + Frontend"
        entities = "、".join(product.core_features) if product.core_features else "核心业务实体"
        return (
            f"# 架构设计: {product.name or '(未命名产品)'}\n\n"
            f"## 技术选型\n{arch} (规则推导, Architect 可细化)\n\n"
            f"## 系统设计\nFrontend → API → Service → Database\n\n"
            f"## 数据模型\n{entities} 相关实体 (规则占位, 由工程计划细化)\n\n"
            f"## 风险分析\n性能 / 安全 / 扩展性 (规则占位)\n"
        )

    @staticmethod
    def _backend_md(product: ProductIntent) -> str:
        entities = "、".join(product.core_features) if product.core_features else "核心业务实体"
        return (
            f"# 后端设计: {product.name or '(未命名产品)'}\n\n"
            f"## API 设计\nRESTful 资源: {entities} (规则占位, 后端可细化)\n\n"
            f"## 数据模型\n{entities} 实体 + 关系 (规则占位)\n\n"
            f"## 服务拆分\nAPI → Service → Repository (规则占位)\n"
        )

    @staticmethod
    def _qa_md(product: ProductIntent) -> str:
        features = "、".join(product.core_features) if product.core_features else "核心功能"
        return (
            f"# 测试方案: {product.name or '(未命名产品)'}\n\n"
            f"## 覆盖范围\n{features}\n\n"
            f"## 测试层级\n- 单元测试: 核心逻辑\n- 集成测试: API/模块联动\n"
            f"- 安全测试: 认证/注入/越权\n- 性能测试: 关键路径响应时间\n"
            f"(规则占位, QA 可细化)\n"
        )

    @staticmethod
    def _prd_md(product: ProductIntent) -> str:
        try:
            from .pipeline import ProductDocument

            return ProductDocument.from_product_intent(product)
        except Exception:  # noqa: BLE001
            return product.to_summary()


__all__ = [
    "DEFAULT_INDUSTRY",
    "PIPELINE_ROLES",
    "EXPERT_SKILLS",
    "KNOWLEDGE_SOURCES",
    "ROLE_DEFINITIONS",
    "ExpertFactory",
    "ExpertAssemblyError",
]
