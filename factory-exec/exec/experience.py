"""factory-exec/exec/experience.py — Experience 记录 (复用 10A-4 ExperienceStore, 零新模型)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §8):
```
第一次闭环执行完成后记录:
  成功/失败 (result) | 耗时 (duration) | 成本 (usage → estimated_cost)
  问题原因 (failure_reason: 结构化) | 经验摘要 (summary: 供未来推荐)
→ ExperienceRecord (复用 10A-4, 五域/半衰期/正负信号)
→ 未来任务匹配加权 (高绩效 Agent 优先)
```

实现: 经 factory-core intelligence.experience.ExperienceAnalyzer.record_experience
(10A-4 Feedback Loop 入口 — 落库 ExperienceStore + intelligence.feedback.learned
事件 + domain/subject 派生; 只记录不执行, 禁自我修改铁律)。

映射:
- domain/subject_type: agent (Employee 是执行主体); subject_id = employee_id。
- task_type: request.task_id (空 → "development")。
- capability: ["development"] + 请求 input capabilities (员工能力)。
- result: success|failure (ExecutionResult.status 映射; 失败 = 负信号)。
- score: 0.8 成功 / 0.2 失败 (表现分; 经验是背书不是替代 — 不覆盖能力分)。
- quality_score: 验证通过 1.0 / 失败 0.3 (产出质量)。
- cost: usage.estimated_cost_usd → 成本效益分 clamp01(1 - cost/1.0) (None 缺省)。
- duration: ExecutionResult.duration (秒)。
- evidence: patch/report Artifact 引用 + failure_reason/摘要 (Evidence 六来源)。
"""

from __future__ import annotations

from typing import Any

from .models import ExecutionResult

#: 成功/失败表现分 (经验记录事实分, ADR-0033: 经验是背书不是替代)
SCORE_SUCCESS = 0.8
SCORE_FAILURE = 0.2
#: 产出质量分 (验证通过/失败)
QUALITY_PASS = 1.0
QUALITY_FAIL = 0.3


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _evidence(
    source_type: str, source_id: str, description: str
) -> dict[str, Any]:
    """Evidence dict 构造 (intelligence.models.Evidence 兼容; 六来源)。"""
    return {
        "source_type": source_type,
        "source_id": source_id,
        "description": description,
        "confidence": 1.0,
    }


class ExperienceRecorder:
    """执行结果 → 10A-4 ExperienceRecord (复用 ExperienceAnalyzer 入口)。

    analyzer: 10A-4 ExperienceAnalyzer (含 ExperienceStore + logger);
    duck-typed (record_experience 方法即可) — 不硬 import intelligence,
    删除 intelligence 包 → 装配点返回 None → 记录静默跳过 (审计增强数据,
    不破坏执行链路, 同 8B-3 usage 失败安全语义)。
    """

    def __init__(self, analyzer: Any = None) -> None:
        self._analyzer = analyzer

    @property
    def analyzer(self) -> Any:
        return self._analyzer

    def record(
        self,
        *,
        result: ExecutionResult,
        employee_id: str,
        request: Any = None,
    ) -> Any:
        """执行结果 → 经验记录 (analyzer 缺失 → 返回 None, 失败安全)。"""
        if self._analyzer is None:
            return None
        success = result.is_success
        task_type = (getattr(request, "task_id", "") or "").strip() or "development"
        capabilities = ["development"]
        if request is not None and isinstance(getattr(request, "input", None), dict):
            caps = request.input.get("capabilities") or []
            if isinstance(caps, list):
                capabilities = list(dict.fromkeys(capabilities + [str(c) for c in caps]))
        estimated = float(result.usage.get("estimated_cost_usd") or 0.0)
        cost = _clamp01(1.0 - estimated) if estimated > 0 else None
        evidence = []
        for artifact in result.artifacts:
            evidence.append(
                _evidence(
                    "artifact", artifact.id, f"{artifact.type.value} artifact"
                )
            )
        if not success:
            evidence.append(
                _evidence("event", result.id, f"failure_reason: {result.error}")
            )
        return self._analyzer.record_experience(
            subject_type="agent",
            subject_id=employee_id or "unknown-employee",
            task_type=task_type,
            capability=capabilities,
            result="success" if success else "failure",
            score=SCORE_SUCCESS if success else SCORE_FAILURE,
            quality_score=QUALITY_PASS if success else QUALITY_FAIL,
            cost=cost,
            duration=result.duration or None,
            confidence=0.8,
            evidence=evidence,
        )
