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

from pydantic import BaseModel, Field, field_validator, model_validator

from events.models import TS_FORMAT, format_timestamp, parse_timestamp

#: 指数衰减半衰期缺省 (30 天): 经验在 30 天后新鲜度降为 0.5
DEFAULT_HALF_LIFE_DAYS = 30.0


def _now() -> str:
    """统一 UTC 时间戳 (与 Event 存储格式一致, 字符串排序 == 时间排序)。"""
    return format_timestamp(datetime.now(timezone.utc))


def _new_id() -> str:
    """全局唯一 id (store 持久化主键)。"""
    return uuid4().hex


def _coerce_csv_list(v: Any) -> list[str]:
    """字符串/可迭代 → 去空串列表 (capability 等清单字段共用)。

    - None → []
    - str → split(",") 去空白过滤空段 ("code,reasoning" → ["code", "reasoning"];
      单值 "code" → ["code"] — 修复单字符拆分 bug: list("code") 会把字符串
      拆成 ['c','o','d','e'])。
    - 其他可迭代 (list/tuple/set) → list(v) 原样转换 (保持既有行为)。
    """
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return list(v)



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
    """统一经验模型六域 (phase10a-plan §Q3): provider/agent/workflow/project/decision。

    10A-4 (ADR-0033) 增补 skill: ExperienceRecord 全字段 subject_type 五类执行资源
    provider/agent/skill/workflow/project 全部落位 (skill = 能力技能包, 与 10A-3
    CandidateType 四类型同源 — 经验与推荐候选类型对齐, 纯增量枚举扩展)。
    """

    PROVIDER = "provider"
    AGENT = "agent"
    SKILL = "skill"
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
    """统一经验记录 (六域 + 全字段 + freshness/decay + negative_signal)。

    - domain/subject_type 六域 + subject_id 定位经验对象 (provider:<provider_id>
      等); subject_type 为显式过滤字段, 缺省派生自 domain (10A-4 全字段)。
    - task_type/capability: 任务分类 + 能力清单 (按 task_type+capability 聚合的
      检索键 — 10A-4 ExperienceAnalyzer 聚合维度)。
    - result: success/failure (负样本 = 反事实记录, §Q4 机制 4 — 失败经验同样
      记录, 防"只记成功"的自我循环偏差); negative_signal 派生属性: 失败经验
      为负信号, 聚合时扣分 (成功提高/失败降低未来推荐)。
    - score (0-1): 该次表现分 (performance); quality_score (0-1, 可选): 产出
      质量分; cost (0-1, 可选): 成本效益分 (高 = 单位产出成本低, 与推荐因素
      语义一致); duration (秒, 可选): 耗时; confidence (0-1): 记录可靠度。
    - evidence: 该次执行证据链 (六来源, 可追溯)。
    - freshness (0-1): 当前新鲜度 (记录/使用时 = 1.0, 之后按半衰期指数衰减 —
      历史经验不永久有效); 未来评分 = score × confidence × freshness
      (effective_score)。
    - usage_count/last_used: 使用计量 (mark_used 更新; 使用即刷新新鲜度 —
      被反复验证的经验保持有效)。
    """

    id: str = Field(default_factory=_new_id)
    domain: ExperienceDomain
    subject_id: str
    subject_type: str | None = None    # 显式主体类型 (缺省派生自 domain.value, 便于过滤)
    task_type: str = ""                # 任务类型 (如 development/testing)
    capability: list[str] = Field(default_factory=list)  # 本次任务锻炼/验证的能力
    result: ExperienceResult = ExperienceResult.SUCCESS
    score: float = Field(ge=0.0, le=1.0)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)  # 产出质量分 (可选)
    cost: float | None = Field(default=None, ge=0.0, le=1.0)           # 成本效益分 (高=好, 可选)
    duration: float | None = Field(default=None, ge=0.0)               # 耗时 (秒, 可选)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
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

    @field_validator("capability", mode="before")
    @classmethod
    def _coerce_capability(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    @model_validator(mode="after")
    def _derive_subject_type(self) -> ExperienceRecord:
        """subject_type 缺省派生自 domain (显式字段便于按类型过滤查询)。"""
        if self.subject_type is None:
            self.subject_type = self.domain.value
        return self

    @property
    def negative_signal(self) -> bool:
        """负经验信号: result == failure (反事实记录 — 失败经验降低未来评分)。

        单一事实源派生属性 (不落库, 与 result 永不失配); ExperienceAnalyzer
        聚合时按 negative_signal 扣分 (成功提高/失败降低)。
        """
        return self.result is ExperienceResult.FAILURE

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


# ==========================================================================
# Phase 10A-3: Recommendation Engine 模型 (ADR-0032) — 追加, 不改既有
# ==========================================================================


class CandidateType(str, Enum):
    """候选四类型抽象 (10A-3, ADR-0032): provider/agent/skill/workflow。

    "专业的人做专业的事": 同一推荐引擎对四类执行资源统一评分 — Provider
    (外部模型服务) / Agent (角色化执行者) / Skill (能力技能包) / Workflow
    (编排工作流)。类型只是候选属性, 评分公式与类型无关 (KISS)。
    """

    PROVIDER = "provider"
    AGENT = "agent"
    SKILL = "skill"
    WORKFLOW = "workflow"


class Candidate(BaseModel):
    """统一候选抽象 (10A-3, ADR-0032): 四类型 × 四因素 (各 0-1)。

    - id: 候选唯一标识; type: 四类型 (缺省 provider)。
    - capability (0-1): 能力匹配分 (覆盖任务所需能力程度); performance (0-1):
      性能分 (延迟/吞吐/成功率); cost (0-1): 成本效益分 (高 = 单位产出成本低,
      与 decision.py 因素语义一致); experience (0-1): 经验基线分, **缺省 0.5
      中性分** — 冷启动不惩罚新候选 (phase10a-plan §Q3 保护)。
    - evidence: 候选自身证据链 (可选; 推荐/决策产物可携带)。
    """

    id: str
    type: CandidateType = CandidateType.PROVIDER
    capability: float = Field(ge=0.0, le=1.0)
    performance: float = Field(ge=0.0, le=1.0)
    cost: float = Field(ge=0.0, le=1.0)
    experience: float = Field(default=0.5, ge=0.0, le=1.0)  # 中性缺省 (冷启动)
    description: str = ""
    evidence: list[Evidence] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: Any) -> CandidateType:
        return CandidateType(v) if isinstance(v, str) else v

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v: Any) -> list[Evidence]:
        if v is None:
            return []
        return [e if isinstance(e, Evidence) else Evidence.model_validate(e) for e in v]

    def factors(self) -> dict[str, float]:
        """四因素 dict (评分/事件 payload 共用, 键序同 recommend.RECOMMEND_FACTOR_KEYS)。"""
        return {
            "capability": self.capability,
            "performance": self.performance,
            "cost": self.cost,
            "experience": self.experience,
        }

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ReasoningDirection(str, Enum):
    """解释方向 (10A-3, ADR-0032): 正向原因 / 负向因素 / 中性说明 / 风险提示。

    解释系统三态 + 风险: positive = 该因素支撑推荐 (高分原因); negative =
    该因素是短板 (扣分因素); neutral = 中性分 (冷启动/无证据, 不褒不贬 —
    无经验不惩罚的表达); risk = 风险提示 (等级 + 需人工确认的理由)。
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    RISK = "risk"


class ReasoningItem(BaseModel):
    """单条解释 (10A-3, ADR-0032): 因素 + 方向 + 可读文本。

    结构化解释 (factor/direction 可机读过滤) + 文本 (可审计展示), 例:
    ReasoningItem(factor="capability", direction="positive",
    text="+ code capability 0.92") — 正向原因; 负向例: text="- 延迟较高
    (performance 0.31)"。
    """

    factor: str                          # capability/performance/cost/experience/risk/...
    direction: ReasoningDirection
    text: str

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, v: Any) -> ReasoningDirection:
        return ReasoningDirection(v) if isinstance(v, str) else v

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class RecommendationContext(BaseModel):
    """推荐上下文 (10A-3 引擎输入): 只读输入, 引擎只消费不修改。

    - task_type: 任务类型 (如 development/testing); required_capabilities:
      任务要求能力清单 (解释/过滤上下文, 如 code,reasoning)。
    - constraints: 约束清单; candidates: 候选集 (四类型统一抽象)。
    - budget (0-1, 可选): 成本分门槛 — 候选 cost 分 < budget → 过滤 (成本
      不可接受即"超预算"; 缺省 None 不过滤)。
    - quality_target (0-1, 可选): 能力分门槛 — 候选 capability 分 <
      quality_target → 过滤 (能力不达标不推荐, 同 8B 能力过滤语义; 缺省
      None 不过滤)。
    - historical_context: 历史经验记录 (candidate_id → ExperienceRecord 列表,
      可选 — 引擎集成 effective_score = score×confidence×freshness; 无记录
      → 候选声明经验分 (缺省中性 0.5), 冷启动不惩罚)。
    - approval: 可选 9c Approval 绑定点 (Decision 集成时高风险提交审批请求)。
    """

    task_type: str
    required_capabilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    budget: float | None = Field(default=None, ge=0.0, le=1.0)
    quality_target: float | None = Field(default=None, ge=0.0, le=1.0)
    historical_context: dict[str, list[ExperienceRecord]] = Field(default_factory=dict)
    approval: ApprovalBinding | None = None
    created_at: str = Field(default_factory=_now)

    @field_validator("candidates", mode="before")
    @classmethod
    def _coerce_candidates(cls, v: Any) -> list[Candidate]:
        if v is None:
            return []
        return [c if isinstance(c, Candidate) else Candidate.model_validate(c) for c in v]

    @field_validator("required_capabilities", "constraints", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    @field_validator("historical_context", mode="before")
    @classmethod
    def _coerce_historical(cls, v: Any) -> dict[str, list[ExperienceRecord]]:
        if v is None:
            return {}
        out: dict[str, list[ExperienceRecord]] = {}
        for key, records in v.items():
            out[key] = [
                r if isinstance(r, ExperienceRecord) else ExperienceRecord.model_validate(r)
                for r in records
            ]
        return out

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class CandidateEvaluation(BaseModel):
    """单候选评分结果 (10A-3 引擎中间产物, ADR-0032): 评分快照 + 解释。

    - factors: 四因素最终分 (experience 已集成 — 经验记录 effective_score
      聚合或候选声明/中性); score: 加权总分 (0-1); score_components: 各因素
      加权贡献 (可审计)。
    - reasoning: 该候选解释 (ReasoningItem 列表, 正负向 + 中性)。
    - experience_records: 命中的经验记录数 (0 = 冷启动); experience_source:
      records (经验记录集成) / declared (候选声明) / neutral (中性缺省)。
    """

    candidate_id: str
    candidate_type: str = CandidateType.PROVIDER.value
    score: float = Field(ge=0.0, le=1.0)
    factors: dict[str, float] = Field(default_factory=dict)
    score_components: dict[str, float] = Field(default_factory=dict)
    reasoning: list[ReasoningItem] = Field(default_factory=list)
    experience_records: int = Field(default=0, ge=0)
    experience_source: str = "neutral"   # records/declared/neutral

    @field_validator("reasoning", mode="before")
    @classmethod
    def _coerce_reasoning(cls, v: Any) -> list[ReasoningItem]:
        if v is None:
            return []
        return [r if isinstance(r, ReasoningItem) else ReasoningItem.model_validate(r) for r in v]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class RecommendationResult(BaseModel):
    """推荐结果 (10A-3 引擎输出, ADR-0032): 推荐 + 分项解释 + 风险。

    - top_candidate_id: 最高分候选 (None = 无候选通过过滤, 无法推荐 —
      宁缺毋滥, 同 8B "无能力证据不推荐" 语义)。
    - evaluations: 全部候选评分快照 (CandidateEvaluation.to_dict(), 排序后 —
      CLI 展示 + Decision 集成复用)。
    - score: top 候选总分; factor_scores: top 候选四因素分项。
    - reasoning: top 候选解释 (正向原因 + 负向因素 + 中性说明); risk_reasons:
      风险提示 (竞争激烈/短板/冷启动/低置信度)。
    - confidence (0-1): 推荐置信度 (分数差距/经验覆盖/候选深度); risk_level:
      low/medium/high; requires_approval: high 或低置信度 → True (9c 复用)。
    - filtered_candidates: 被 quality_target/budget 过滤掉的候选 id (可审计)。
    - 只推荐不执行: 本产物不携带任何执行指令; 执行决策权在人 (Approval)。
    """

    id: str = Field(default_factory=_new_id)
    task_type: str
    top_candidate_id: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    factor_scores: dict[str, float] = Field(default_factory=dict)
    evaluations: list[CandidateEvaluation] = Field(default_factory=list)
    reasoning: list[ReasoningItem] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_level: str = RiskLevel.LOW.value
    risk_reasons: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    filtered_candidates: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)

    @field_validator("evaluations", mode="before")
    @classmethod
    def _coerce_evaluations(cls, v: Any) -> list[CandidateEvaluation]:
        if v is None:
            return []
        return [
            e if isinstance(e, CandidateEvaluation) else CandidateEvaluation.model_validate(e)
            for e in v
        ]

    @field_validator("reasoning", mode="before")
    @classmethod
    def _coerce_reasoning(cls, v: Any) -> list[ReasoningItem]:
        if v is None:
            return []
        return [r if isinstance(r, ReasoningItem) else ReasoningItem.model_validate(r) for r in v]

    def positive_reasons(self) -> list[ReasoningItem]:
        """正向原因 (支撑推荐的理由, CLI 展示/测试断言)。"""
        return [r for r in self.reasoning if r.direction is ReasoningDirection.POSITIVE]

    def negative_reasons(self) -> list[ReasoningItem]:
        """负向因素 (推荐候选的短板, 不黑箱)。"""
        return [r for r in self.reasoning if r.direction is ReasoningDirection.NEGATIVE]

    def reasons_by_factor(self, factor: str) -> list[ReasoningItem]:
        """按因素过滤解释 (capability/performance/cost/experience 分项)。"""
        return [r for r in self.reasoning if r.factor == factor]

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")

    def to_artifact(
        self,
        target_type: str = "recommendation",
        evidence: list[Evidence] | None = None,
    ) -> Recommendation:
        """结果 → 10A-1 Recommendation Artifact (reasoning 扁平化为字符串)。

        target_type 缺省 "recommendation" (本产物对象类型); 调用方可按 top
        候选类型传 provider/agent/skill/workflow (四类型推荐产物可追溯)。
        evidence: top 候选证据链 (引擎传入; 模型层不持有候选引用)。
        """
        # risk 数值映射 (与 decision.RISK_LEVEL_TO_NUMERIC 同值, 模型层不
        # import decision — 避免循环依赖; 常量即文档: low 0.2/medium 0.5/high 0.8)
        risk_numeric = {"low": 0.2, "medium": 0.5, "high": 0.8}.get(self.risk_level, 0.2)
        return Recommendation(
            target_type=target_type,
            target_id=self.top_candidate_id or "",
            score=self.score,
            reasoning=[r.text for r in self.reasoning],
            evidence=list(evidence or []),
            confidence=self.confidence,
            risk=risk_numeric,
        )


# ==========================================================================
# Phase 10A-4: Experience Loop 模型 (ADR-0033) — 追加, 不改既有
# ==========================================================================


class ExperienceAggregation(BaseModel):
    """经验聚合统计 (10A-4, ADR-0033): 记录集 → 统计 + 正负聚合有效分。

    - subject_id/subject_type/task_type/capability: 聚合维度 (谁 / 什么任务 /
      什么能力); record_count: 记录数; success_count/failure_count: 正负样本
      计数 (negative_signal 落位); success_rate: 成功率。
    - avg_score/avg_confidence/avg_freshness: 记录均值 (avg_freshness 按聚合
      时刻计算 — 历史经验不永久有效); avg_cost: 平均成本效益分 (None = 记录
      未携带成本)。
    - effective_score (0-1): 正负聚合有效分 = clamp01(mean(sign × score×
      confidence×freshness)), 成功 + / 失败 − (失败经验降低评分, 成功提高);
      全失败 → 0.0, 无记录 → 0.0 (调用方处理冷启动中性 0.5)。
    - reasoning: 逐条聚合解释 (可审计展示)。
    """

    subject_id: str = ""
    subject_type: str = ""
    task_type: str = ""
    capability: list[str] = Field(default_factory=list)
    record_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_score: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_freshness: float = Field(default=0.0, ge=0.0, le=1.0)
    avg_cost: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: list[str] = Field(default_factory=list)

    @field_validator("capability", mode="before")
    @classmethod
    def _coerce_capability(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class ExperienceAnalysis(BaseModel):
    """单主体经验分析产物 (10A-4 分析器输出): 谁 + 什么任务 + 聚合结果 + 推理。

    - subject_id/subject_type: 经验主体 (provider:<id> / agent:<id> / ...)。
    - task_type/capability: 聚合过滤维度 (空 = 未过滤)。
    - aggregation: ExperienceAggregation 快照 (统计 + 正负聚合有效分)。
    - 只读分析: 不携带任何执行/修改指令 (经验分析 ≠ 自我修改)。
    """

    subject_id: str
    subject_type: str = ""
    task_type: str = ""
    capability: list[str] = Field(default_factory=list)
    aggregation: ExperienceAggregation = Field(default_factory=ExperienceAggregation)
    created_at: str = Field(default_factory=_now)

    @field_validator("capability", mode="before")
    @classmethod
    def _coerce_capability(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    @field_validator("aggregation", mode="before")
    @classmethod
    def _coerce_aggregation(cls, v: Any) -> ExperienceAggregation:
        if v is None:
            return ExperienceAggregation()
        return v if isinstance(v, ExperienceAggregation) else ExperienceAggregation.model_validate(v)

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class TaskRequirement(BaseModel):
    """任务需求 (10A-4 TaskEvaluator 输入): 任务类型 + 能力要求 + 门槛 + 约束。

    - task_type: 任务类型 (如 development/testing); required_capabilities:
      任务要求能力清单 (如 code,reasoning) — 与推荐上下文同源词汇。
    - quality_target (0-1, 可选): 能力分门槛; budget (0-1, 可选): 成本分门槛
      (评估上下文过滤语义, 与推荐过滤一致 — 本阶段只读经验, 门槛预留)。
    - constraints: 约束清单 (评估风险观察来源, 预留)。
    """

    task_type: str
    required_capabilities: list[str] = Field(default_factory=list)
    quality_target: float | None = Field(default=None, ge=0.0, le=1.0)
    budget: float | None = Field(default=None, ge=0.0, le=1.0)
    constraints: list[str] = Field(default_factory=list)

    @field_validator("required_capabilities", "constraints", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")


class TaskEvaluation(BaseModel):
    """任务评估产物 (10A-4 TaskEvaluator 输出): 推荐执行资源 + 置信度 + 风险。

    - recommended_agents/recommended_providers/recommended_skills: 按历史经验
      正负聚合有效分排序的推荐主体 (各条目 dict: id/score/records/
      success_rate/reasoning; 有效分 ≥ 0.5 中性门槛才推荐, 封顶 5 个/类)。
      workflow/project/decision 域记录不参与执行资源推荐 (非执行候选)。
    - reasoning: 逐条评估解释 (基于多少条经验 / 为什么推荐谁, 可审计)。
    - confidence (0-1): 评估置信度 (分数差距/类型覆盖/候选深度规则);
      risks: 风险清单 (冷启动/负经验主导/低置信度)。
    - 只读评估: 不触发任何执行/修改 (经验分析 ≠ 自我修改)。
    """

    task_type: str
    required_capabilities: list[str] = Field(default_factory=list)
    recommended_agents: list[dict[str, Any]] = Field(default_factory=list)
    recommended_providers: list[dict[str, Any]] = Field(default_factory=list)
    recommended_skills: list[dict[str, Any]] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risks: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)

    @field_validator("required_capabilities", "reasoning", "risks", mode="before")
    @classmethod
    def _coerce_str_lists(cls, v: Any) -> list[str]:
        return _coerce_csv_list(v)

    def recommended_count(self) -> int:
        """推荐主体总数 (CLI 展示/测试断言)。"""
        return (
            len(self.recommended_agents)
            + len(self.recommended_providers)
            + len(self.recommended_skills)
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON 友好序列化 (store/CLI --json/测试断言共用)。"""
        return self.model_dump(mode="json")
