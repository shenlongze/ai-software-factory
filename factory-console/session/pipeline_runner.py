"""factory-console/session/pipeline_runner.py — Product Intelligence Pipeline (S10-084 P0)。

Idea → PRD 多角色资产链: PM/Market/Competitive/UX/Architect/QA/SeniorPM 依次真实产出
版本化 Artifact (artifact_registry) + Audit 事件 (ARTIFACT_CREATED, artifact_reference +
parent_event_id 血缘), 供 PRD/工程/审批消费。

- 每个角色: LLM 可用 → 角色 prompt 生成; 失败/无 LLM → deterministic 模板
  (复用 ProductIntelligenceEngine / pipeline.ProductDocument, 不复制业务)
- 纯标准库; 失败安全 (单角色失败不中断整链 — 该角色用 deterministic 兜底)
- 零依赖 Action: 由 actions.product_pipeline 编排 (与 create_product 同模式)

设计: docs/sprint10/S10-084-plan.md §4-§6
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .artifact_registry import ArtifactRecord, ArtifactRegistry
from .product import ProductIntent

#: 角色链 (role_id, artifact_type, 标题) — Operating Model Phase 1-5 对应
ROLES: tuple[tuple[str, str, str], ...] = (
    ("pm", "product", "产品策略"),
    ("market", "market_analysis", "市场分析"),
    ("competitive", "competitive_analysis", "竞品分析"),
    ("ux", "ux_flow", "用户体验"),
    ("architect", "architecture", "架构设计"),
    ("qa", "test_plan", "测试方案"),
    ("prd", "prd", "产品需求文档 (PRD)"),
)

#: LLM 失败/无 LLM → deterministic 兜底 (不空资产)
_ROLE_PROMPTS: dict[str, str] = {
    "pm": "你是产品经理。基于产品信息输出产品策略 (定位/用户价值/核心能力/非目标范围/商业模式), 中文 markdown。",
    "market": "你是市场分析师。输出市场规模/用户趋势/机会窗口, 中文 markdown。",
    "competitive": "你是竞品分析师。输出直接竞品/间接竞品/替代方案/机会点, 中文 markdown。",
    "ux": "你是 UX 设计师。输出用户流程/页面结构/信息架构, 中文 markdown。",
    "architect": "你是软件架构师。输出技术选型/系统设计/数据模型/风险, 中文 markdown。",
    "qa": "你是 QA 负责人。输出单元/集成/安全/性能测试方案, 中文 markdown。",
    "prd": "你是资深产品经理。基于产品信息输出详细 PRD (背景/用户故事/功能需求/验收标准), 中文 markdown。",
}


@dataclass
class PipelineResult:
    """管线结果: 项目 + 角色资产记录列表。"""

    project: str
    records: list[ArtifactRecord] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.records:
            return f"产品管线未产出资产 ({self.project})"
        lines = [f"产品管线完成: {len(self.records)} 个资产 ({self.project}):"]
        for r in self.records:
            lines.append(f"  v{r.version} {r.type} [{r.created_by}] {r.status}")
        lines.append("可输入 '项目列表' 或 /project 查看; 确认后 '准备开发' 进入工程。")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "records": [r.to_dict() for r in self.records],
            "count": len(self.records),
        }


class ProductPipeline:
    """产品管线编排器: 依次跑 7 角色 → 版本化资产 + 审计事件。"""

    def __init__(
        self,
        workspace: Any,
        slug: str,
        *,
        llm_fn: Optional[Callable[[str, str], str]] = None,
    ) -> None:
        self.workspace = workspace
        self.slug = str(slug)
        self.llm_fn = llm_fn
        self.registry = ArtifactRegistry(workspace, self.slug)

    def run(self, product: ProductIntent, *, source: str = "") -> PipelineResult:
        """跑完整角色链; 单角色异常 → deterministic 兜底, 不中断。"""
        result = PipelineResult(project=self.slug)
        parent_event_id = ""
        for role_id, artifact_type, _title in ROLES:
            try:
                content = self._generate(role_id, product)
            except Exception:  # noqa: BLE001 — 兜底
                content = self._deterministic(role_id, product)
            record = self.registry.write(
                artifact_type,
                content,
                created_by=role_id,
                source=source or (product.raw or product.name or ""),
                status="draft",
                parent_event_id=parent_event_id,
            )
            # 审计血缘: ARTIFACT_CREATED (失败安全, 不中断业务)
            record.event_id = self._emit(record, parent_event_id)
            parent_event_id = record.event_id or parent_event_id
            result.records.append(record)
        return result

    # ------------------------------------------------------------ 生成

    def _generate(self, role_id: str, product: ProductIntent) -> str:
        """角色产出: LLM 可用 → LLM; 否则 deterministic (不抛)。"""
        if self.llm_fn is not None:
            try:
                prompt = f"{_ROLE_PROMPTS.get(role_id, '')}\n产品: {product.to_summary()}"
                text = str(self.llm_fn(prompt, role_id) or "").strip()
                if text:
                    return text
            except Exception:  # noqa: BLE001 — LLM 失败 → deterministic
                pass
        return self._deterministic(role_id, product)

    def _deterministic(self, role_id: str, product: ProductIntent) -> str:
        """确定性模板 (复用现有引擎, 不复制业务)。"""
        if role_id == "pm":
            return self._pm_md(product)
        if role_id == "market":
            return self._market_md(product)
        if role_id == "competitive":
            return self._competitive_md(product)
        if role_id == "ux":
            return self._ux_md(product)
        if role_id == "architect":
            return self._architect_md(product)
        if role_id == "qa":
            return self._qa_md(product)
        if role_id == "prd":
            return self._prd_md(product)
        return f"# {role_id}\n(规则占位)"

    # ------------------------------------------------------------ 各角色模板

    def _pm_md(self, product: ProductIntent) -> str:
        name = product.name or "(未命名产品)"
        features = "、".join(product.core_features) if product.core_features else "(待补充)"
        return (
            f"# 产品策略: {name}\n\n"
            f"## 产品定位\n面向 {product.user or '(待补充)'} 的 {name}。\n\n"
            f"## 用户价值\n{product.problem or '(待补充)'}\n\n"
            f"## 核心能力\n- {features}\n\n"
            f"## 非目标范围\n第一版不做: 多端高级定制 / 复杂权限 / 深度数据分析 (规则占位, LLM 可细化)。\n\n"
            f"## 商业模式\n待评估 (规则占位: 订阅 / 买断 / 增值服务)。\n"
        )

    def _market_md(self, product: ProductIntent) -> str:
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

    def _competitive_md(self, product: ProductIntent) -> str:
        try:
            from .product_intelligence import ProductIntelligenceEngine
            c = ProductIntelligenceEngine().analyze_competitor(product)
            comp_lines = []
            for comp in (c.competitors or []):
                comp_lines.append(
                    f"- {comp.get('name') or '(未命名)'} ({comp.get('category') or '未知'}): "
                    f"优势 {', '.join(comp.get('strengths') or []) or '(待补充)'}"
                )
            if not comp_lines:
                comp_lines.append("- (待补充)")
            adv = "\n".join(f"- {a}" for a in (c.advantages or [])) or "- (待补充)"
            diff = "\n".join(f"- {d}" for d in (c.differentiation_opportunities or [])) or "- (待补充)"
            return (
                f"# 竞品分析: {product.name or '(未命名产品)'}\n\n"
                f"## 竞品\n{chr(10).join(comp_lines)}\n\n"
                f"## 自身优势\n{adv}\n\n"
                f"## 差异化机会\n{diff}\n"
            )
        except Exception:  # noqa: BLE001 — 失败安全
            return "# 竞品分析\n\n## 竞品\n(待补充)\n\n## 差异化机会\n(待补充)\n"

    def _ux_md(self, product: ProductIntent) -> str:
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

    def _architect_md(self, product: ProductIntent) -> str:
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

    def _qa_md(self, product: ProductIntent) -> str:
        features = "、".join(product.core_features) if product.core_features else "核心功能"
        return (
            f"# 测试方案: {product.name or '(未命名产品)'}\n\n"
            f"## 覆盖范围\n{features}\n\n"
            f"## 测试层级\n- 单元测试: 核心逻辑\n- 集成测试: API/模块联动\n"
            f"- 安全测试: 认证/注入/越权\n- 性能测试: 关键路径响应时间\n"
            f"(规则占位, QA 可细化)\n"
        )

    def _prd_md(self, product: ProductIntent) -> str:
        try:
            from .pipeline import ProductDocument
            return ProductDocument.from_product_intent(product)
        except Exception:  # noqa: BLE001
            return product.to_summary()

    # ------------------------------------------------------------ 审计血缘

    def _emit(self, record: ArtifactRecord, parent_event_id: str) -> str:
        """ARTIFACT_CREATED 审计事件 (失败安全 → ""). 返回 audit_id 供血缘链。"""
        try:
            from ..audit.audit_emitter import AuditEmitter
            ev = AuditEmitter(workspace=self.workspace).emit(
                "ARTIFACT_CREATED",
                project_id=self.slug,
                agent_id=record.created_by,
                actor_type="agent",
                actor_id=record.created_by,
                artifact_reference=record.content_ref,
                parent_event_id=parent_event_id,
                artifact_type=record.type,
                artifact_version=record.version,
            )
            return str(getattr(ev, "audit_id", "") or "") if ev is not None else ""
        except Exception:  # noqa: BLE001 — 审计故障不中断
            return ""
