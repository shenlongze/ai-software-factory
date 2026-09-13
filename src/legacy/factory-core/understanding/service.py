"""understanding/service.py — UnderstandingService: 项目理解编排 (只读, 规则分析, 禁 LLM)。

设计依据:
- phase7-plan.md §1/§2/§4: analyze(path) 编排 = 项目基本信息 → 文档检测 →
  产物检测 → 阶段识别 (按 artifact 组合推断 stage + confidence + evidence) →
  缺失分析 → 建议 (NextAction: action/reason/risk/approval_required)
- 冻结约束 (architecture-freeze-2026-08): Core 零修改; 本包为全新 Extension
  模块; 只读 (分析不写任何文件, 字节级只读性由测试守住); 禁 LLM (全部确定性
  规则; 未来 LLM 增强经 Provider 抽象 — Phase 8)。
- Approval Gate 只设计接口: NextAction.approval_required 标注 mandatory 节点
  (PRD/UI/DEPLOYMENT → True), 不实现 Web UI (Phase 11)。
- 事件边界: 服务层经注入的 EventLogger 发 understanding.started/completed/
  failed (source="understanding"); logger 为 None 时全部静默 (同既有模块
  registry/engine 可选 logger 模式)。CLI 读命令审计 (understanding.viewed)
  由命令层发出 (source="cli", ADR-0002)。

阶段识别规则 (确定性, phase7-plan.md §2):
- 按 artifact 组合推断: 无任何产物 → IDEA; 研究文档 → RESEARCH; 仅 README/
  文档 → PRD; +UI → UI_DESIGN; +架构文档 → ARCHITECTURE; +源码 →
  DEVELOPMENT; +tests → TESTING; +发布配置 (RELEASE 证据) → RELEASE;
  +部署配置 → PRODUCTION; +运维 → OPERATION (单调阶段链)。
- confidence 按证据强度: 支持当前阶段的产物/证据数 n → min(0.95, 0.5 + 0.1n);
  IDEA (空项目) 特例 0.9; RESEARCH/README 弱证据 0.6。
- evidence 列出依据: "artifact:<KEY> (<detail>)" / "evidence:<STAGE> (<files>)"。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from events.models import format_timestamp

from .analyzers.artifact_detector import (
    ArtifactDetector,
    _first_has_any,
    collect_files,
)
from .analyzers.document_analyzer import DocumentAnalyzer
from .analyzers.project_analyzer import ProjectAnalyzer
from .events import (
    record_understanding_completed,
    record_understanding_failed,
    record_understanding_started,
)
from .models import (
    ARTIFACT_KEYS,
    ArtifactDetection,
    MissingAnalysis,
    NextAction,
    ProjectUnderstandingReport,
    StageDetection,
)

# ------------------------------------------------------------------ 注册表

#: 产物键 → 直接蕴含的阶段 (阶段链位置 = STAGES 序号; 单调推进)
ARTIFACT_STAGE: dict[str, str] = {
    "PRD": "PRD",
    "UI_DESIGN": "UI_DESIGN",
    "ARCHITECTURE": "ARCHITECTURE",
    "SOURCE_CODE": "DEVELOPMENT",
    "TEST": "TESTING",
    "DEPLOYMENT": "PRODUCTION",
    "OPERATION": "OPERATION",
}

#: 阶段链 (与 models.STAGES 同序; ARTIFACT_STAGE 值均在此列)
_ARTIFACT_CHAIN: tuple[str, ...] = tuple(ARTIFACT_STAGE)

#: 非 7 类产物的阶段证据 (注册化, 可扩展): 发布配置 → RELEASE;
#: 研究文档 → RESEARCH。模式语义同 ARTIFACT_DETECTORS (小写相对路径三态匹配)。
STAGE_EVIDENCE_PATTERNS: dict[str, tuple[str, ...]] = {
    "RESEARCH": (
        "docs/research", "research.md", "research.txt", "research/",
        "market-analysis.md", "market-research.md", "competitor-analysis.md",
        "market-analysis/", "调研.md", "调研报告.md", "竞品分析.md",
    ),
    "RELEASE": (
        "changelog.md", "changelog.txt", "changelog/", "releases.md",
        "release.md", "release-notes.md", "version", "version.json",
        "release/", ".github/workflows/release", "发布记录.md", "版本记录.md",
    ),
}

#: 基础文档弱证据 (仅 README → PRD 阶段)
_README_PATTERNS = ("readme.md", "readme.txt", "readme", "readme.rst", "readme.adoc")

#: NextAction 建议目录 (缺失产物 → 结构化建议; approval_required = Approval
#: Gate mandatory 节点: PRD/UI/Deploy → True, 其余 recommended/optional → False)
_ACTION_CATALOG: dict[str, tuple[str, str, str, bool]] = {
    "PRD": (
        "补充 PRD 文档 (docs/prd.md)",
        "缺少产品需求文档: 需求未成文, 后续设计与验收缺乏依据",
        "需求理解偏差导致返工与范围蔓延",
        True,
    ),
    "UI_DESIGN": (
        "补充 UI 设计稿 (docs/ui.md 或 designs/)",
        "缺少界面设计: 视觉方向未确认",
        "UI 返工/体验不一致",
        True,
    ),
    "ARCHITECTURE": (
        "补充架构文档 (docs/architecture.md)",
        "缺少架构设计: 大型改动缺乏技术方向依据",
        "架构漂移/技术债累积",
        False,
    ),
    "SOURCE_CODE": (
        "开始编码实现 (src/ 或 lib/)",
        "仅有文档无源码: 项目尚未进入开发阶段",
        "停留在规划阶段, 可行性未验证",
        False,
    ),
    "TEST": (
        "补充自动化测试 (tests/)",
        "缺少测试产物: 代码质量无独立验证",
        "回归缺陷/验证失败",
        False,
    ),
    "DEPLOYMENT": (
        "补充部署配置 (Dockerfile/docker-compose/deploy/)",
        "缺少部署配置: 无法进入可发布状态",
        "发布流程缺失/环境不一致",
        True,
    ),
    "OPERATION": (
        "补充运维配置 (runbook/监控)",
        "缺少运维产物: 上线后无监控与应急手段",
        "线上事故响应迟缓",
        False,
    ),
}


class UnderstandingError(Exception):
    """路径无效/分析前置错误 (CLI 映射 → 退出码 1; 内部异常原样上抛)。"""


# ------------------------------------------------------------------ 纯规则函数

def _evidence_hits(files: list[Path], patterns: tuple[str, ...]) -> list[str]:
    """阶段证据命中文件列表 (与检测器同款三态匹配, 上限 8 条)。"""
    found, hits = _first_has_any(files, patterns)
    return hits if found else []


def _merge_detections(
    doc: dict[str, ArtifactDetection], code: dict[str, ArtifactDetection],
) -> dict[str, ArtifactDetection]:
    """文档检测 ∪ 代码检测 → 每键合并 (任一命中 → present, detail 拼接)。"""
    merged: dict[str, ArtifactDetection] = {}
    for key in ARTIFACT_KEYS:
        d = doc.get(key) or ArtifactDetection(artifact=key)
        c = code.get(key) or ArtifactDetection(artifact=key)
        details = [x.detail for x in (d, c) if x.detail]
        merged[key] = ArtifactDetection(
            artifact=key,
            present=d.present or c.present,
            detail="; ".join(details),
        )
    return merged


def detect_stage(
    path: Path,
    artifacts: dict[str, ArtifactDetection],
    files: list[Path],
) -> StageDetection:
    """阶段识别 (确定性规则, 禁 LLM — phase7-plan.md §2)。

    阶段链单调推进: 存在产物取最高蕴含阶段; 发布配置证据在代码阶段
    (DEVELOPMENT/TESTING) 时推进到 RELEASE; 无产物时按 研究文档 → README
    → IDEA 递降弱证据。confidence = min(0.95, 0.5 + 0.1 × 支持证据数)。
    """
    present_chain = [k for k in _ARTIFACT_CHAIN if artifacts[k].present]

    if not present_chain:
        research = _evidence_hits(files, STAGE_EVIDENCE_PATTERNS["RESEARCH"])
        if research:
            return StageDetection(
                stage="RESEARCH",
                confidence=0.6,
                evidence=[f"evidence:RESEARCH ({', '.join(research)})"],
            )
        readme = _evidence_hits(files, _README_PATTERNS)
        if readme:
            return StageDetection(
                stage="PRD",
                confidence=0.6,
                evidence=["evidence:PRD (README.md 基础文档)"],
            )
        return StageDetection(
            stage="IDEA",
            confidence=0.9,
            evidence=[f"no artifacts detected in {path}"],
        )

    stage = ARTIFACT_STAGE[present_chain[-1]]
    supporting = len(present_chain)
    evidence = [f"artifact:{k} ({artifacts[k].detail})" for k in present_chain]

    release = _evidence_hits(files, STAGE_EVIDENCE_PATTERNS["RELEASE"])
    if release and stage in ("DEVELOPMENT", "TESTING"):
        stage = "RELEASE"
        supporting += 1
        evidence.append(f"evidence:RELEASE ({', '.join(release)})")

    confidence = min(0.95, 0.5 + 0.1 * supporting)
    return StageDetection(stage=stage, confidence=round(confidence, 2), evidence=evidence)


def build_missing(artifacts: dict[str, ArtifactDetection]) -> MissingAnalysis:
    """缺失分析: 7 类产物按 ARTIFACT_KEYS 序分列 missing/present。"""
    present = [k for k in ARTIFACT_KEYS if artifacts[k].present]
    return MissingAnalysis(
        missing=[k for k in ARTIFACT_KEYS if k not in present],
        present=present,
    )


def build_next_actions(
    artifacts: dict[str, ArtifactDetection], stage: StageDetection | None = None,
) -> list[NextAction]:
    """结构化建议 (仅建议, 不自动执行): 每缺失产物一条 + 源码缺测试的
    validation 建议 (追加在末尾, 顺序确定可断言)。"""
    actions: list[NextAction] = []
    for key in ARTIFACT_KEYS:
        if not artifacts[key].present:
            action, reason, risk, approval = _ACTION_CATALOG[key]
            actions.append(NextAction(
                action=action, reason=reason, risk=risk, approval_required=approval,
            ))
    if artifacts["SOURCE_CODE"].present and not artifacts["TEST"].present:
        actions.append(NextAction(
            action="运行 validation 校验 (factory validate)",
            reason="存在源码但缺少测试产物: 建议执行验证引擎确认当前质量基线",
            risk="无独立验证, 缺陷可能进入下一阶段",
            approval_required=False,
        ))
    return actions


# ------------------------------------------------------------------ 服务

class UnderstandingService:
    """项目理解编排服务 (只读分析; logger 可选 → 事件静默)。

    analyze(path) → ProjectUnderstandingReport: 校验路径 → 发 started →
    编排四步 (基本信息/文档检测/产物检测/阶段识别/缺失/建议) → 发 completed;
    任何异常 → 发 failed 后原样上抛 (调用方决定退出码)。
    """

    def __init__(self, logger: Any = None) -> None:
        self._logger = logger
        self._project_analyzer = ProjectAnalyzer()
        self._document_analyzer = DocumentAnalyzer()
        self._artifact_detector = ArtifactDetector()

    def analyze(self, path: str | Path) -> ProjectUnderstandingReport:
        p = Path(path)
        if not p.is_dir():
            message = f"path not found: {p}" if not p.exists() else f"not a directory: {p}"
            error = UnderstandingError(message)
            record_understanding_failed(self._logger, path=str(p), error=error)
            raise error

        record_understanding_started(self._logger, path=str(p))
        try:
            files = collect_files(p)
            basic_info = self._project_analyzer.analyze(p, files)
            doc = self._document_analyzer.detect(p, files)
            code = self._artifact_detector.detect(p, files)
            artifacts = _merge_detections(doc, code)
            stage = detect_stage(p, artifacts, files)
            missing = build_missing(artifacts)
            next_actions = build_next_actions(artifacts, stage)
            report = ProjectUnderstandingReport(
                path=str(p),
                basic_info=basic_info,
                stage=stage,
                artifacts=[artifacts[k] for k in ARTIFACT_KEYS],
                missing=missing,
                next_actions=next_actions,
                generated_at=format_timestamp(datetime.now(timezone.utc)),
            )
        except Exception as exc:  # 内部异常 → failed 事件 + 原样上抛
            record_understanding_failed(self._logger, path=str(p), error=exc)
            raise

        record_understanding_completed(self._logger, report=report)
        return report
