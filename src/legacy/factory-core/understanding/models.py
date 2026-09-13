"""understanding/models.py — Project Understanding 领域模型 (Pydantic v2, 只读)。

设计依据:
- phase7-plan.md §2: ProjectUnderstandingReport + StageDetection + ArtifactDetection
  + MissingAnalysis + NextAction (action/reason/risk/approval_required)
- 冻结约束 (architecture-freeze-2026-08): Core 零修改, Extension 扩展; 本包为
  全新 Extension 模块, 只读分析 (不写任何文件), 禁 LLM (规则分析 + Mock)。
- Approval Gate 只设计接口: NextAction.approval_required 标注人工批准需求
  (PRD/UI/Deploy = mandatory 节点), 不实现 Web UI (Phase 11)。

注册表:
- STAGES: 10 个生命周期阶段 (IDEA/RESEARCH/PRD/UI_DESIGN/ARCHITECTURE/
  DEVELOPMENT/TESTING/RELEASE/PRODUCTION/OPERATION) — 阶段链单调推进,
  注册化可扩展 (新增阶段 = 加成员 + 阶段链规则在 service.py)。
- ARTIFACT_KEYS: 7 类产物 (PRD/UI_DESIGN/ARCHITECTURE/SOURCE_CODE/TEST/
  DEPLOYMENT/OPERATION) — 与 artifact_detector.py 的 ARTIFACT_DETECTORS
  注册表一一对应, 可扩展。

模型语义: 全部为只读投影 (分析结果), to_dict() = model_dump(mode="json")
供 CLI --json 与测试断言共用 (同 tasks/agents models 风格); 时间戳统一 UTC。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from events.models import format_timestamp

# ------------------------------------------------------------------ 注册表

#: 10 阶段注册表 (顺序即阶段链: 单调推进, 后者蕴含前者)。可扩展: 新增阶段 =
#: 在 STAGES 末尾追加成员 + service.py 阶段链规则补充对应产物/证据映射。
STAGES: tuple[str, ...] = (
    "IDEA",
    "RESEARCH",
    "PRD",
    "UI_DESIGN",
    "ARCHITECTURE",
    "DEVELOPMENT",
    "TESTING",
    "RELEASE",
    "PRODUCTION",
    "OPERATION",
)

#: 7 类产物注册表键 (与 artifact_detector.py ARTIFACT_DETECTORS 一一对应)。
#: 可扩展: 注册新检测器时在末尾追加键 (ArtifactDetection.artifact 不做
#: 严格枚举校验, 保证注册化扩展不破坏模型 — 集合完整性由注册表测试守住)。
ARTIFACT_KEYS: tuple[str, ...] = (
    "PRD",
    "UI_DESIGN",
    "ARCHITECTURE",
    "SOURCE_CODE",
    "TEST",
    "DEPLOYMENT",
    "OPERATION",
)


def stage_index(stage: str) -> int:
    """阶段在 STAGES 中的序号 (阶段链比较用); 未知阶段 → len(STAGES)。"""
    try:
        return STAGES.index(stage)
    except ValueError:
        return len(STAGES)


def _normalize_stage(value: str) -> str:
    """宽松归一: 大小写不敏感 + 空白清理 (模型校验与 CLI 解析共用)。"""
    return value.strip().upper()


# ------------------------------------------------------------------ 模型

class StageDetection(BaseModel):
    """阶段识别结果: stage 来自 STAGES 注册表 + confidence + evidence。

    confidence 语义 (确定性规则, 禁 LLM — phase7-plan.md §2): 证据强度 =
    支持当前阶段的产物/证据数量, 公式见 service.py::detect_stage
    (链驱动: 每类存在产物 +0.1, 基座 0.5, 上限 0.95; IDEA/空项目 0.9)。
    """

    model_config = ConfigDict(frozen=False)

    stage: str = "IDEA"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)

    @field_validator("stage", mode="before")
    @classmethod
    def _stage_normalize(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError(f"stage must be a string, got {type(v).__name__}")
        normalized = _normalize_stage(v)
        if normalized not in STAGES:
            raise ValueError(
                f"unknown stage: {v!r} (expected one of: {', '.join(STAGES)})"
            )
        return normalized

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ArtifactDetection(BaseModel):
    """单个产物检测结果 (注册表键 → present + detail)。

    artifact 不做枚举校验 (注册化扩展: 新增检测器键即合法); detail 列出
    匹配到的相对路径 (逗号分隔, 上限 8 条 + 计数)。
    """

    artifact: str
    present: bool = False
    detail: str = ""

    @field_validator("artifact", mode="before")
    @classmethod
    def _artifact_clean(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("artifact must be a non-empty string")
        return v.strip()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class MissingAnalysis(BaseModel):
    """缺失分析: 7 类产物中缺失 / 存在的注册表键列表 (按 ARTIFACT_KEYS 序)。"""

    missing: list[str] = Field(default_factory=list)
    present: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class NextAction(BaseModel):
    """结构化建议 (仅建议, 不自动执行 — phase7-plan.md §Next Action)。

    approval_required: Approval Gate 接口标注 (PRD/UI_DESIGN/DEPLOYMENT =
    mandatory 节点 → True, 需人工批准; 其余 recommended/optional → False),
    只设计接口不实现 Web UI (冻结报告 §四)。
    """

    action: str
    reason: str
    risk: str
    approval_required: bool = False

    @field_validator("action", "reason", "risk")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("action/reason/risk must be non-empty")
        return v

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProjectBasicInfo(BaseModel):
    """项目基本信息 (规则推断: 目录/文件扩展名 — 禁 LLM, 确定性)。

    type: empty/documentation/script/application/service (优先级链);
    scale: tiny(0-5) / small(6-50) / medium(51-300) / large(>300) 按文件数;
    status: empty/planning/in_development/developed/deployable/operational
    (与产物存在性对应, 见 project_analyzer.py)。
    """

    name: str = ""
    type: str = "empty"
    languages: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    scale: str = "tiny"
    status: str = "empty"
    file_count: int = 0
    dir_count: int = 0

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProjectUnderstandingReport(BaseModel):
    """一次项目理解的完整报告 (只读投影, 供 CLI --json / Dashboard 消费)。"""

    path: str
    basic_info: ProjectBasicInfo = Field(default_factory=ProjectBasicInfo)
    stage: StageDetection = Field(default_factory=StageDetection)
    artifacts: list[ArtifactDetection] = Field(default_factory=list)
    missing: MissingAnalysis = Field(default_factory=MissingAnalysis)
    next_actions: list[NextAction] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: format_timestamp(datetime.now(timezone.utc))
    )

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")
