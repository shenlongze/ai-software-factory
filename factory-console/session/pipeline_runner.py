"""factory-console/session/pipeline_runner.py — Product Intelligence Pipeline (S10-084/M2 A5)。

Idea → PRD 多角色资产链 (M2 员工内核接线): "让PM分析" → 7 个真实 Agent 实体
(ExpertFactory.assemble) 经 HandoffBus 依次交接产出版本化 Artifact —
created_by=agent_id (agt- 前缀) + parent_artifact 互引 (血缘双字段)。

- A5 契约 (S10-087-M2 §2): 每资产 created_by == agent_id; 资产互引
  (metadata.parent_artifact + parent_event_id); 无 LLM → 确定性兜底非空
- 每个角色: LLM 可用 → 角色 system_prompt 生成; 失败/无 LLM → deterministic
  兜底 (ExpertFactory.deterministic_content, 复用 ProductIntelligenceEngine /
  pipeline.ProductDocument, 不复制业务)
- M1 零回归: 资产类型/版本递增/审计事件链 (ARTIFACT_CREATED) 保持
- 纯标准库; 失败安全 (单角色 LLM 失败不中断整链 — deterministic 兜底)

设计: docs/sprint10/S10-084-plan.md §4-§6 + docs/sprint10/S10-087-M2-员工内核-plan.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .agent_entity import AgentEntity
from .artifact_registry import ArtifactRecord, ArtifactRegistry
from .expert_factory import ExpertFactory, PIPELINE_ROLES
from .handoff_bus import HandoffBlocked, HandoffBus
from .product import ProductIntent

#: 角色链 (role_id, artifact_type, 标题) — Operating Model Phase 1-5 对应
#: (M2: 由 ExpertFactory.assemble 生成对应 AgentEntity, 资产类型随角色定义)
ROLES: tuple[tuple[str, str, str], ...] = (
    ("pm", "product", "产品策略"),
    ("market", "market_analysis", "市场分析"),
    ("competitive", "competitive_analysis", "竞品分析"),
    ("ux", "ux_flow", "用户体验"),
    ("architect", "architecture", "架构设计"),
    ("qa", "test_plan", "测试方案"),
    ("prd", "prd", "产品需求文档 (PRD)"),
)

#: S10-088 T2: 交接消费上一资产正文的截断上限 (prompt 只嵌前 2000 字)
PARENT_CONTENT_LIMIT = 2000

#: 角色 → LLM 提示词后缀 (M2: AgentEntity.system_prompt 为主, 此处仅 LLM 路径增强)
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
            parent = (r.metadata or {}).get("parent_artifact") or ""
            lines.append(
                f"  v{r.version} {r.type} [{r.created_by}] parent={parent or '(根)'} {r.status}"
            )
        lines.append("可输入 '项目列表' 或 /project 查看; 确认后 '准备开发' 进入工程。")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "records": [r.to_dict() for r in self.records],
            "count": len(self.records),
        }


class ProductPipeline:
    """产品管线编排器 (M2 A5): ExpertFactory.assemble 7 专家 + HandoffBus 交接。"""

    def __init__(
        self,
        workspace: Any,
        slug: str,
        *,
        llm_fn: Optional[Callable[[str, str], str]] = None,
        factory: Optional[ExpertFactory] = None,
        bus: Optional[HandoffBus] = None,
    ) -> None:
        self.workspace = workspace
        self.slug = str(slug)
        self.llm_fn = llm_fn
        self.registry = ArtifactRegistry(workspace, self.slug)
        self.factory = factory or ExpertFactory()
        self.bus = bus or HandoffBus(workspace, self.slug, registry=self.registry)

    def run(self, product: ProductIntent, *, source: str = "") -> PipelineResult:
        """跑完整 Agent 链; 单角色 LLM 异常 → deterministic 兜底, 不中断。"""
        agents = self.factory.build_team(industry="it")
        try:
            handoff = self.bus.route(
                agents,
                produce=self._produce,
                product=product,
                source=source,
            )
        except HandoffBlocked as exc:
            # 冲突挂起等审批 — 明确报错 (契约 §2.6), 不静默降级
            raise RuntimeError(f"产品管线阻断 (等待审批 {exc.message.review_id}): {exc}") from exc
        return PipelineResult(project=self.slug, records=handoff.records)

    # ------------------------------------------------------------ 生成

    def _produce(
        self,
        agent: AgentEntity,
        parent_artifact_id: str,
        product: ProductIntent,
        parent_content: str = "",
    ) -> str:
        """角色产出: LLM 可用 → LLM (system_prompt + 上一资产内容 + 产品信息); 否则 deterministic。

        S10-088 T2: prompt 嵌 '上一资产内容: <前 PARENT_CONTENT_LIMIT 字>' —
        后一角色消费前一产出正文 (而非仅 asset id); 血缘 id 仍保留。根资产
        无上一产出 → '(无 — 根资产)' (明确, 不伪造)。
        """
        role = str(agent.role or "").lower()
        if self.llm_fn is not None:
            try:
                prev = str(parent_content or "").strip()[:PARENT_CONTENT_LIMIT]
                prompt = (
                    f"{agent.system_prompt or _ROLE_PROMPTS.get(role, '')}\n"
                    f"上一资产: {parent_artifact_id or '(根, 无)'}\n"
                    f"上一资产内容: {prev or '(无 — 根资产)'}\n"
                    f"产品: {product.to_summary()}"
                )
                text = str(self.llm_fn(prompt, role) or "").strip()
                if text:
                    return text
            except Exception:  # noqa: BLE001 — LLM 失败 → deterministic
                pass
        return self.factory.deterministic_content(role, product)

__all__ = ["ROLES", "PipelineResult", "ProductPipeline"]
