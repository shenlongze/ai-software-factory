"""factory-core/intelligence/models.py — Intelligence Layer 领域模型 (Pydantic v2)。

设计依据:
- phase10a1-status.md §范围 + phase10a-plan.md §2 (数据模型):
  1. **Decision = 智能产物, ≠ Approval** (phase10a-plan §Q2): Decision 承载 AI 的
     分析/选项/推荐/证据/评分 (status: open/recommended/accepted/rejected), 人工确认
     走 9c Approval 状态机 (approval.*, 本层不复制)。Decision 只分析+推荐+解释,
     **不自动执行**。
  2. **Recommendation 必须支持解释**: reasoning (list[str]) 逐条说明为什么;
     evidence (list[Evidence]) 支撑事实; confidence/risk 量化不确定度。
  3. **ExperienceRecord 五域 + freshness/decay**: domain ∈ provider|agent|workflow|
     project|decision (统一经验模型, phase10a-plan §Q3); freshness (0-1) 表达
     "历史经验不永久有效" — 未来评分 = performance(score) × confidence × freshness,
     decay 用指数半衰期纯函数 (decay_freshness, 10A-4 学习算法不在此实现)。
  4. **Evidence 六来源 + 可追溯**: source_type ∈ artifact|event|experience|
     external_data|human_input|provider_output (防 AI 自我循环, phase10a-plan §Q4:
     事实优先, 每个推荐附证据链; 事件/Artifact 是事实, AI 输出是建议)。
- 模型风格参照 product/models.py (Phase 9a): to_dict() = model_dump(mode="json")
  供 store/CLI --json/测试断言共用; 时间戳统一 UTC (events.models.format_timestamp,
  字符串排序 == 时间排序); 状态流转经 model_copy(update=...) 新实例。
- 本模块只 import events.models (公共接口), 不 import product/providers/runtime
  (Removal Isolation: 删除 intelligence/ 不影响 Factory; 反向删除 product/ 等
  也不影响本层 — 纯 stdlib + pydantic + Core 公共接口)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from events.models import TS_FORMAT, format_timestamp, parse_timestamp

#: 指数衰减半衰期缺省 (30 天): 经验在 30 天后新鲜度降为 0.5
DEFAULT_HALF_LIFE_DAYS = 30.0


def _now() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    return format_timestamp(datetime.now(timezone.utc))


def _new_id() -> str:
    """全局唯一 id (store 持久化主键)。"""
    return uuid4().hex


def decay_freshness(age_seconds: float, half_life_seconds: float) -> float:
    """指数衰减纯函数: freshness = 0.5 ** (age / half_life)。

    - age = 0 → 1.0 (刚产生/刚使用, 最新鲜)
    - age = half_life → 0.5 (一个半衰期)
    - age = 2 × half_life → 0.25
    - 历史经验不永久有效: age → ∞ 时 freshness → 0 (但永不为负)。
    非学习算法: 只是模型层的确定性衰减数学, 10A-4 的经验学习不在此实现。
    """
    if half_life_seconds <= 0:
        raise ValueError(f"half_life_seconds must be > 0, got {half_life_seconds}")
    if age_seconds < 0:
        raise ValueError(f"age_seconds must be >= 0, got {age_seconds}")
    return 0.5 ** (age_seconds / half_life_seconds)


class EvidenceSource(str, Enum):
    """Evidence 六来源 (phase10a-plan §Q4 防自我循环: 事实可追溯)。

    artifact / event 为 Factory 内部事实 (Core 数据, 只读); experience 为历史
    经验记录; external_data 为外部事实源; human_input 为人工输入 (决策依据);
    provider_output 为 AI/Provider 输出 (建议, 事实优先级最低 — 事实优先)。
    """

    ARTIFACT = "artifact"            # Factory Artifact (9a product_* 等)
    EVENT = "event"                  # Core 审计事件 (event_id 锚点)
    EXPERIENCE = "experience"        # 历史经验记录 (ExperienceRecord id)
    EXTERNAL_DATA = "external_data"  # 外部事实源 (文档/基准/公开数据引用)
    HUMAN_INPUT = "human_input"      # 人工输入 (评审意见/需求/反馈)
    PROVIDER_OUTPUT = "provider_output"  # AI/Provider 输出 (建议, 非事实)


class ExperienceDomain(str, Enum):
    """统一经验模型五域 (phase10a-plan §Q3): provider/agent/workflow/project/decision。"""

    PROVIDER = "provider"
    AGENT = "agent"
    WORKFLOW = "workflow"
    PROJECT = "project"
    DECISION = "decision"


class ExperienceResult(str, Enum):
    """经验结果: success (正样本) / failure (负样本 — 反事实记录, §Q4 机制 4)。"""

    SUCCESS = "success"
    FAILURE = "failure"


class DecisionStatus(str, Enum):
    """Decision 生命周期 (AI 推荐产物, ≠ Approval 状态机)。

    open (已生成, 待推荐) → recommended (已给出推荐) → accepted (人工采纳) |
    rejected (人工否决)。accepted/rejected 只是 Decision 的记录语义 (人工决定
    回写), 人工确认的闸门机制本体在 9c Approval (approval_request_id 可绑定)。
    """

    OPEN = "open"
    RECOMMENDED = "recommended"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    """决策风险等级 (10A-2 规则检测输出, ADR-0031): low/medium/high。

    high = 触发高风险规则 (架构变更/部署策略/Provider 迁移/成本上升) →
    requires_approval=true (复用 9c ApprovalGate); medium = 竞争激烈或置信度
    低 (需人工确认); low = 未触发任何风险规则。等级 → 数值风险
    (Decision.risk 0-1) 映射见 decision.RISK_LEVEL_TO_NUMERIC。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Evidence(BaseModel):
    """单条证据: 支撑 Decision/Recommendation 的事实引用 (可追溯/可审计)。

    Lineage: source_type + source_id 组成唯一引用 (如 event:<event_id> /
    artifact:<artifact_id> / experience:<experience_id>), description 解释该
    证据支撑什么, confidence 表达证据本身的可靠度 (0-1)。
    """

    source_type: EvidenceSource
    source_id: str
    description: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=_now)

    @field_validator("source_type", mode="before")
    @classmethod
    def _coerce_source_type(cls, v: Any) -> EvidenceSource:
        return EvidenceSource(v) if isinstance(v, str) else v

    def lineage_ref(self) -> str:
        """规范化引用: f"{source_type}:{source_id}" (证据链可追溯锚点)。"""
        return f"{self.source_type.value}:{self.source_id}"

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ApprovalBinding(BaseModel):
    """9c Approval 绑定点 (10A-2, ADR-0031): 高风险决策 → 复用 ApprovalGate。

    只描述"往哪个 Artifact 绑审批", 不携带任何审批状态机 (9c 本体不复制):
    artifact_id = 已存在的 product Artifact id (request_approval 前置条件 —
    任何 Artifact 可申请, 门不绑定 PRD/UI); gate 缺省按 artifact.type 解析
    默认门; by = 申请人 (缺省 "intelligence"); note = 申请备注。
    """

    artifact_id: str
    gate: str | None = None
    by: str = "intelligence"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class DecisionOption(BaseModel):
    """决策候选选项 (10A-2 引擎输入/输出, ADR-0031)。

    - factors: 四因素评估数据 (capability/cost/performance/experience, 每项
      0-1) — 来自 context 提供的评估数据 (规则评分输入, 不绑定 LLM)。
    - score (0-1): 综合评分 — 引擎按四因素加权计算回填 (无 factors 时取
      context 提供的评估分); reasoning: 评分解释 (逐条为什么, 可审计)。
    - evidence: 该选项的证据链 (禁无证据推荐 — 引擎强制每选项 ≥1 证据)。
    """

    id: str
    name: str
    description: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    factors: dict[str, float] = Field(default_factory=dict)
    reasoning: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    disadvantages: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("factors")
    @classmethod
    def _factors_in_range(cls, v: dict[str, float]) -> dict[str, float]:
        for key, value in v.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"factor {key!r} must be in [0, 1], got {value}")
        return v

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class DecisionContext(BaseModel):
    """决策上下文 (10A-2 引擎输入): 只读事实快照, 引擎只消费不修改。

    - subject: 决策对象 id (task/project/idea/artifact); decision_type 受控
      词汇 (provider_selection/architecture_change/deployment_strategy/
      provider_migration/... — 高风险规则按此分类)。
    - objective/constraints: 决策目标与约束 (规则分析观察来源 + 风险关键词
      检测输入)。
    - available_options: 候选选项 (携带四因素评估数据或 context 评估分)。
    - evidence_sources: 证据链 (六来源, 必须 ≥1 — 禁无证据决策)。
    - approval: 可选 9c Approval 绑定点 (高风险 + 已装配审批服务时提交请求)。
    """

    subject: str
    decision_type: str = "general"
    objective: str = ""
    constraints: list[str] = Field(default_factory=list)
    available_options: list[DecisionOption] = Field(default_factory=list)
    evidence_sources: list[Evidence] = Field(default_factory=list)
    approval: ApprovalBinding | None = None
    created_at: str = Field(default_factory=_now)

    @field_validator("available_options", mode="before")
    @classmethod
    def _coerce_options(cls, v: Any) -> list[DecisionOption]:
        if v is None:
            return []
        return [o if isinstance(o, DecisionOption) else DecisionOption.model_validate(o) for o in v]

    @field_validator("constraints", mode="before")
    @classmethod
    def _coerce_constraints(cls, v: Any) -> list[str]:
        # 容器字段 None → 默认空 (CLI --context JSON 可能带 null, before 模式
        # 在类型检查前归一 — 同 available_options/evidence_sources 模式)
        if v is None:
            return []
        return list(v)

    @field_validator("evidence_sources", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class DecisionAnalysis(BaseModel):
    """分析产物 (10A-2 流程第 1 步, ADR-0031): Context → Analysis。

    - factors: 决策因素聚合评估 (四因素 0-1 归一, 来自选项因素均值/中性分)。
    - observations: 分析观察 (决策类型/目标/约束/候选数 — 逐条规则生成)。
    - confidence (0-1): 分析置信度 (证据量规则计算); evidence: 分析依据证据链。
    """

    decision_type: str = "general"
    subject: str = ""
    factors: dict[str, float] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class RiskAssessment(BaseModel):
    """风险检测产物 (10A-2 流程第 4 步, ADR-0031): 规则检测输出。

    - risk_level: low/medium/high (高风险触发: 架构变更/部署策略/Provider
      迁移/成本上升; medium: 竞争激烈或低置信度)。
    - requires_approval: high 或 低置信度 → True (复用 9c ApprovalGate)。
    - reasons: 逐条风险解释 (可读); rules_triggered: 命中的规则锚点
      (decision_type:<t> / option:<id>:<risk> / context:<text>, 可审计)。
    """

    risk_level: str = RiskLevel.LOW.value
    requires_approval: bool = False
    reasons: list[str] = Field(default_factory=list)
    rules_triggered: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class DecisionResult(BaseModel):
    """决策结果 (10A-2 流程输出, ADR-0031): 推荐 + 备选 + 置信度 + 风险 + 审批。

    由 Decision 派生 (decision_result), 不独立持久化 — 落库事实是 Decision
    Artifact (options/recommendation/confidence/risk_level/evidence 全链可追溯)。
    """

    decision_id: str
    recommendation: str
    alternatives: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: str = RiskLevel.LOW.value
    requires_approval: bool = False
    approval_request_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class Decision(BaseModel):
    """智能决策产物: 分析 + 选项 + 推荐 + 证据 + 评分 (AI 推荐, 不自动执行)。

    - options (list[dict]): 选项集合, 10A-2 引擎写入 DecisionOption.to_dict()
      (id/name/score/factors/reasoning/evidence 全链可追溯)。
    - recommendation: 推荐选项标识 (options 内 id); None = 尚未给出推荐。
    - evidence: 决策依据证据链 (Evidence 六来源, 可追溯) — 禁无证据决策。
    - confidence (0-1): 推荐置信度; risk (0-1): 推荐风险 (risk_level 等级 →
      数值映射, low=0.2/medium=0.5/high=0.8)。低 confidence → 应降级为
      "需要人工"而非自动采纳 (§Q4 机制 5)。
    - risk_level (low/medium/high) + requires_approval (10A-2): 规则风险检测
      输出 — high → requires_approval=true (复用 9c ApprovalGate)。
    - analysis: DecisionAnalysis.to_dict() 快照 (分析全链可审计)。
    - status: DecisionStatus (open/recommended/accepted/rejected) — Decision
      ≠ Approval: approval_request_id 可绑定 9c 审批请求 (可选)。
    """

    id: str = Field(default_factory=_new_id)
    decision_type: str = "general"      # provider_selection/architecture_change/... (10A-2 受控词汇)
    subject_id: str                     # 决策对象 id (task/project/idea/artifact)
    description: str = ""               # 决策问题描述 (分析对象)
    options: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: str | None = None   # 推荐选项标识 (引擎定义 options 内 key)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: str = RiskLevel.LOW.value  # low/medium/high (10A-2 规则检测输出)
    requires_approval: bool = False        # high 风险 / 低置信度 → True (9c 复用)
    analysis: dict[str, Any] | None = None  # DecisionAnalysis.to_dict() 快照 (10A-2)
    evidence: list[Evidence] = Field(default_factory=list)
    status: DecisionStatus = DecisionStatus.OPEN
    approval_request_id: str | None = None  # 可选: 绑定 9c Approval 请求 (复用不复制)
    created_at: str = Field(default_factory=_now)

    @field_validator("risk_level", mode="before")
    @classmethod
    def _coerce_risk_level(cls, v: Any) -> str:
        return RiskLevel(v).value if isinstance(v, str) else v.value if isinstance(v, RiskLevel) else v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> DecisionStatus:
        return DecisionStatus(v) if isinstance(v, str) else v

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")

    def with_status(self, status: DecisionStatus | str) -> Decision:
        """状态流转 (返回新实例, 落库用返回值 — 调用方持有的旧引用不自动更新)。"""
        return self.model_copy(update={"status": DecisionStatus(status) if isinstance(status, str) else status})


class Recommendation(BaseModel):
    """推荐产物: 目标 + 评分 + 解释 (reasoning) + 证据 + 置信度/风险。

    - 必须支持解释: reasoning (list[str]) 逐条说明为什么推荐 (10A-3 引擎生成,
      本层只保证字段存在与持久化)。
    - 只推荐不执行: 本模型不携带任何执行指令, 执行决策权在人 (Approval) 或
      未来编排层显式调用 (phase10a-plan §Q1 边界铁律)。
    - evidence: 推荐依据证据链 (六来源); confidence/risk: 0-1 量化。
    """

    id: str = Field(default_factory=_new_id)
    target_type: str                    # provider/agent/skill/workflow/... (10A-3 受控词汇)
    target_id: str                      # 目标对象 id
    score: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(default_factory=list)  # 解释: 逐条为什么
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=_now)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ExperienceRecord(BaseModel):
    """统一经验记录 (五域 + freshness/decay)。

    - domain 五域 + subject_id 定位经验对象 (provider:<provider_id> 等)。
    - result: success/failure (负样本 = 反事实记录, §Q4 机制 4 — 失败经验同样
      记录, 防"只记成功"的自我循环偏差)。
    - score (0-1): 该次表现分 (performance); confidence (0-1): 记录可靠度。
    - freshness (0-1): 当前新鲜度 (记录/使用时 = 1.0, 之后按半衰期指数衰减 —
      历史经验不永久有效); 未来评分 = score × confidence × freshness
      (effective_score)。
    - usage_count/last_used: 使用计量 (mark_used 更新; 使用即刷新新鲜度 —
      被反复验证的经验保持有效)。
    """

    id: str = Field(default_factory=_new_id)
    domain: ExperienceDomain
    subject_id: str
    result: ExperienceResult = ExperienceResult.SUCCESS
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=_now)
    last_used: str | None = None        # 最近使用时间 (None = 从未被使用)
    usage_count: int = Field(default=0, ge=0)
    freshness: float = Field(default=1.0, ge=0.0, le=1.0)  # 上次刷新时的新鲜度

    @field_validator("domain", mode="before")
    @classmethod
    def _coerce_domain(cls, v: Any) -> ExperienceDomain:
        return ExperienceDomain(v) if isinstance(v, str) else v

    @field_validator("result", mode="before")
    @classmethod
    def _coerce_result(cls, v: Any) -> ExperienceResult:
        return ExperienceResult(v) if isinstance(v, str) else v

    def current_freshness(
        self,
        now: str | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> float:
        """当前新鲜度: 从最近锚点 (last_used 或 created_at) 起按半衰期衰减。

        now 传 None 用当前 UTC 时间 (测试可注入固定时间戳做确定性断言)。
        """
        anchor = self.last_used or self.created_at
        now_dt = parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
        age_s = (now_dt - parse_timestamp(anchor)).total_seconds()
        return decay_freshness(max(age_s, 0.0), half_life_days * 86400.0)

    def effective_score(
        self,
        now: str | None = None,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    ) -> float:
        """未来评分 = performance(score) × confidence × freshness (Q3 影响链基础)。

        纯模型层计算, 不含任何学习/加权算法 (10A-4 才实现经验→推荐的影响链)。
        """
        return self.score * self.confidence * self.current_freshness(now, half_life_days)

    def mark_used(self, now: str | None = None) -> ExperienceRecord:
        """记录一次使用: usage_count +1, last_used = now, freshness 重置 1.0。

        返回新实例 (model_copy), 落库用返回值 — 调用方持有的旧引用不自动更新。
        """
        used_at = now if now is not None else _now()
        return self.model_copy(
            update={
                "last_used": used_at,
                "usage_count": self.usage_count + 1,
                "freshness": 1.0,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")
