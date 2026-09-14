"""providers/capability.py — ProviderCapabilityProfile: 能力矩阵 + 任务匹配 (Phase 8B-2)。

设计依据:
- phase8b2-plan.md §3/§4: Provider 描述 "能做什么 (Capability)" — 能力矩阵
  (capability → quality score 0-1) + max_tokens/context_window + evidence
  (能力来源依据: 基准/文档/实测, 评审调整 1)。
- TaskRequirement (models.py, 评审调整 5) → 能力过滤: required_capabilities
  每个能力在 matrix 中的质量分 >= min_quality 才通过; 通过后按平均质量分排序。
- find_best_for_task / rank_for_task 是纯函数 (输入 profiles 可迭代或 dict,
  不触碰任何存储 — 与 ProviderSelector 同哲学, CostAwareSelector 复用)。

匹配语义:
- quality(capability): matrix 缺失的能力 → 0.0 (无证据 = 无能力, 不臆造)。
- has(capability, min_quality): quality >= min_quality。
- required_capabilities 为空 → 无能力要求, 全部 profile 通过 (按整体平均分排序)。
- score = 平均质量分 (0-1); 无 required 且 matrix 为空 → 1.0 (无要求即完全匹配)。

evidence 契约: 每条依据是来源描述字符串 (如 "benchmark: HumanEval 82.3" /
"vendor docs: context 200k" / "measured: factory usage 2026-08") — 只记录来源,
不校验内容 (审计追溯用, 非判定输入)。
"""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field, field_validator

from .models import TaskRequirement, _id_sane, _normalize_list


class ProviderCapabilityProfile(BaseModel):
    """一个 Provider 的能力质量画像 (capability → 质量分 0-1)。

    - matrix: capability → quality score (0-1); 缺失能力视为 0.0 (无证据)。
    - max_tokens / context_window: 模型窗口上限 (None = 未知/不限制)。
    - evidence: 能力来源依据列表 (基准/文档/实测, 评审调整 1) — 审计追溯用。
    """

    provider_id: str
    matrix: dict[str, float] = Field(default_factory=dict)
    max_tokens: int | None = None
    context_window: int | None = None
    evidence: list[str] = Field(default_factory=list)

    @field_validator("provider_id")
    @classmethod
    def _profile_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence_normalized(cls, v: list[str] | None) -> list[str]:
        return _normalize_list(v)

    @field_validator("matrix")
    @classmethod
    def _matrix_scores(cls, v: dict[str, float]) -> dict[str, float]:
        bad = {k: val for k, val in v.items() if not isinstance(val, (int, float))}
        if bad:
            raise ValueError(f"matrix scores must be numeric: {sorted(bad)}")
        out: dict[str, float] = {}
        for k, val in v.items():
            score = float(val)
            if score < 0.0 or score > 1.0:
                raise ValueError(f"matrix score out of range [0,1]: {k}={score}")
            out[k] = score
        return out

    # ------------------------------------------------------------------ 查询

    def quality(self, capability: str) -> float:
        """能力质量分; matrix 缺失 → 0.0 (无证据 = 无能力)。"""
        return float(self.matrix.get(capability, 0.0))

    def has(self, capability: str, min_quality: float = 0.0) -> bool:
        """能力是否满足质量门槛: 键存在 (有证据) 且 quality >= min_quality。

        matrix 缺失的能力 → 无证据 = 无能力 → False (无论门槛多低,
        不臆造能力 — min_quality=0.0 表示"键存在即可", 不是"0 分也通过")。
        """
        return capability in self.matrix and self.quality(capability) >= min_quality

    def average_quality(self, capabilities: Iterable[str]) -> float:
        """指定能力集合的平均质量分 (空集合 → 0.0; 缺失能力按 0.0 计)。"""
        caps = list(capabilities)
        if not caps:
            return 0.0
        return round(sum(self.quality(c) for c in caps) / len(caps), 4)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ------------------------------------------------------------------ 任务匹配 (纯函数)


def _coerce_profiles(profiles: Any) -> list[ProviderCapabilityProfile]:
    """输入归一: dict {id: profile} 或可迭代 profile → 列表 (容忍混合输入)。"""
    if profiles is None:
        return []
    if isinstance(profiles, dict):
        return [p for p in profiles.values() if isinstance(p, ProviderCapabilityProfile)]
    return [p for p in profiles if isinstance(p, ProviderCapabilityProfile)]


def rank_for_task(
    task_requirement: TaskRequirement | dict[str, Any],
    profiles: Iterable[ProviderCapabilityProfile] | dict[str, ProviderCapabilityProfile],
) -> list[tuple[ProviderCapabilityProfile, float]]:
    """能力过滤 + 质量分排序 (降序): TaskRequirement → 全部通过候选。

    过滤语义 (phase8b2-plan.md §4):
    1. required_capabilities 每个能力 quality >= min_quality (缺失能力 0.0 < 门槛
       即被过滤 — 无证据的能力不参与推荐)。
    2. required_capabilities 为空 → 无能力要求, 全部通过。
    3. score = 平均质量分 (required 为空 → 整体 matrix 平均; matrix 空 → 1.0)。
    返回 [(profile, score)] 按 score 降序 (稳定, 同分保输入序)。
    """
    req = _coerce_requirement(task_requirement)
    scored: list[tuple[ProviderCapabilityProfile, float]] = []
    for profile in _coerce_profiles(profiles):
        if req.required_capabilities:
            # 过滤: 每个 required 能力须有证据 (键存在) 且 quality >= min_quality;
            # 无证据 (matrix 缺失) → 不通过 (不臆造能力, has 语义见上)。
            if any(not profile.has(c, req.min_quality) for c in req.required_capabilities):
                continue
            qualities = [profile.quality(c) for c in req.required_capabilities]
            score = round(sum(qualities) / len(qualities), 4)
        elif profile.matrix:
            score = profile.average_quality(profile.matrix.keys())
        else:
            score = 1.0  # 无能力要求 + 无矩阵 → 完全匹配
        scored.append((profile, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def find_best_for_task(
    task_requirement: TaskRequirement | dict[str, Any],
    profiles: Iterable[ProviderCapabilityProfile] | dict[str, ProviderCapabilityProfile],
) -> tuple[ProviderCapabilityProfile, float] | None:
    """能力匹配最优: rank_for_task 首个 (无通过候选 → None)。"""
    ranked = rank_for_task(task_requirement, profiles)
    return ranked[0] if ranked else None


def _coerce_requirement(task_requirement: TaskRequirement | dict[str, Any]) -> TaskRequirement:
    """TaskRequirement 输入归一 (dict → 模型; 非法值由模型校验抛 ValidationError)。"""
    if isinstance(task_requirement, TaskRequirement):
        return task_requirement
    return TaskRequirement.model_validate(task_requirement)
