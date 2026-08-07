"""factory-exec/exec/capability.py — Model Capability Registry (Sprint 5 T5.4)。

模型能力声明式注册表 + 能力快照 + 模型经验统计 (设计依据:
docs/validation/sprint5-t51-execution-strategy-design.md §5, T5.1 已冻结):

    provider/model → 七项能力评分 (0-1 声明式) → 快照进 Candidate
                      (历史可解释) → 未来 Benchmark/选择 (T5.5)

三件套 (KISS, 单文件):
- ModelCapability: 单模型能力档案 (provider/model 必填 + 7 项 0-1 评分;
  0-1 clamp + 序列化 to_dict/from_dict; 通用 — 不绑定具体模型,
  示例配置 (deepseek-v4-flash 等) 是数据文件, 非代码)。
- CapabilityRegistry: 注册表 (register/get/list/find_by_capability/remove);
  本地 JSON 原子写 (tmp + os.replace, 禁数据库); 损坏失败安全 (读坏 → 空表,
  不破坏执行链); 内置示例配置 = 声明式 JSON 文件 (不硬编码到代码)。
- ModelExperienceStats: 模型经验统计 (成功/失败计数 + 按任务类型细分);
  只统计不评分 — 能力评分唯一写入口是 CapabilityRegistry.register
  (人工/Benchmark 更新, 第一阶段), 本类永不触碰分数 (测试强断言)。

Benchmark Integration (T5.4 §3, model_capability_snapshot):
- capability_snapshot(registry, provider, model): Candidate 保存时冻结
  registry 中该模型当前评分 ({"provider","model","scores","captured_at"});
  模型能力变化不影响历史候选 (历史结果可解释); 无 registry/无该模型 →
  {} 中性 (不臆造)。

KISS 边界: 本模块只依赖 stdlib + pydantic + 本层 models (零 Core 导入);
不跑真实 Benchmark / 不自动选模型 / 不改执行流程 (接入点全为可选参数,
缺省行为逐位不变); 不落数据库 (JSON 单文件)。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field, field_validator

from .models import _ExecModel

#: 七项能力评分 (0-1 声明式; 顺序固定 — 审计/序列化/校验共用单一事实源)。
CAPABILITY_SCORES: tuple[str, ...] = (
    "coding_score",      # 代码修改能力
    "reasoning_score",   # 推理能力
    "stability_score",   # 长任务稳定性 (reasoning 耗尽风险)
    "context_score",     # 长上下文利用能力
    "tool_use_score",    # 工具/结构化操作能力
    "cost_score",        # 成本 (高 = 便宜)
    "latency_score",     # 延迟 (高 = 快)
)

#: 内置示例配置文件名 (声明式 JSON — 数据不硬编码到代码)。
DEFAULT_CONFIG_FILE = Path(__file__).parent / "config" / "model_capabilities.json"


def _clamp01(value: Any) -> float:
    """0-1 clamp (非法输入 → 0.0 中性, 不臆造; 与 experience_ctx 同语义)。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


def _norm_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _now_iso() -> str:
    """统一 UTC 时间戳 (ISO 8601, 字符串排序 == 时间排序)。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _norm_dict(value: Any) -> dict[str, Any]:
    return dict(value) if value is not None else {}


def capability_key(provider: str, model: str) -> str:
    """注册表键 (provider::model — 字符串键 JSON 友好)。"""
    return f"{_norm_str(provider)}::{_norm_str(model)}"


# ================================================================ ModelCapability

class ModelCapability(_ExecModel):
    """单模型能力档案 (T5.4 §1; 7 项 0-1 评分, 声明式)。

    - provider / model: 必填 (空串/纯空白 → 拒绝 — 拼写错误即失败);
    - 七项评分: 缺省 0.0 中性, 输入 clamp [0,1] (越界不报错, 钳制归一);
    - created_at / updated_at: 创建/更新时间 (审计锚点; register 覆盖时
      刷新 updated_at, 保留 created_at);
    - 通用: 不绑定具体模型 (示例数据在 exec/config/ 声明式 JSON 文件);
    - 序列化: to_dict (JSON 友好) / from_dict (model_validate 逆操作)。
    """

    provider: str
    model: str
    coding_score: float = 0.0
    reasoning_score: float = 0.0
    stability_score: float = 0.0
    context_score: float = 0.0
    tool_use_score: float = 0.0
    cost_score: float = 0.0
    latency_score: float = 0.0
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    @field_validator("provider", "model", mode="before")
    @classmethod
    def _names_required(cls, v: Any) -> str:
        name = _norm_str(v).strip()
        if not name:
            raise ValueError("provider and model are required (non-blank)")
        return name

    @field_validator(*CAPABILITY_SCORES, mode="before")
    @classmethod
    def _scores_clamp(cls, v: Any) -> float:
        return _clamp01(v)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCapability:
        """dict → ModelCapability (to_dict 的逆操作)。"""
        return cls.model_validate(data)

    @property
    def scores(self) -> dict[str, float]:
        """七项评分 dict (能力名 → 0-1 分; 审计/快照/查询共用)。"""
        return {name: float(getattr(self, name)) for name in CAPABILITY_SCORES}

    def score(self, capability: str) -> float:
        """单项能力分 (未知能力名 → 0.0 中性, 不臆造)。"""
        if capability not in CAPABILITY_SCORES:
            return 0.0
        return float(getattr(self, capability))


def load_default_config(path: str | Path | None = None) -> list[ModelCapability]:
    """内置示例能力配置 (声明式 JSON 文件 — 数据不硬编码到代码)。

    读取 exec/config/model_capabilities.json; 文件缺失/损坏 → 空列表
    (失败安全, 调用方按空处理); 单条坏 → 跳过该条。
    """
    p = Path(path) if path is not None else DEFAULT_CONFIG_FILE
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = raw.get("models") if isinstance(raw, dict) else []
    if not isinstance(items, list):
        return []
    out: list[ModelCapability] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            out.append(ModelCapability.model_validate(item))
        except Exception:  # noqa: BLE001 — 单条损坏跳过 (失败安全)
            continue
    return out


# ================================================================ CapabilityRegistry

class CapabilityRegistry:
    """模型能力注册表 (T5.4 §2; 通用 — 不绑定具体模型)。

    - register / get / list / find_by_capability / remove / count / has;
    - 本地存储: JSON 单文件原子写 (tmp + os.replace; 禁数据库);
    - 损坏失败安全: 读盘失败 → 空表 (审计增强数据, 不破坏执行链);
      单条坏 → 跳过该条;
    - 内置示例: seed_defaults() 灌入声明式 JSON 配置 (已有条目不覆盖,
      防示例数据覆盖用户数据);
    - 评分写入口唯一 = register() (人工/Benchmark 更新) — 经验统计
      (ModelExperienceStats) 永不触碰评分 (第一阶段, 测试强断言);
    - root None → 内存模式 (不落盘; save() no-op — 测试/纯内存用)。
    """

    def __init__(
        self,
        root: str | Path | None = None,
        filename: str = "model_capabilities.json",
        *,
        seed_defaults: bool = False,
    ) -> None:
        self.root = Path(root) if root is not None else None
        self.filename = filename
        self.path = self.root / filename if self.root is not None else None
        self._capabilities: dict[tuple[str, str], ModelCapability] = {}
        self._load()
        if seed_defaults:
            self.seed_defaults()

    # ------------------------------------------------------------- 读写

    def _load(self) -> None:
        """读盘 (损坏 → 空表失败安全; 单条坏 → 跳过)。"""
        if self.path is None or not self.path.exists():
            self._capabilities = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._capabilities = {}
            return
        items = raw if isinstance(raw, list) else []
        loaded: dict[tuple[str, str], ModelCapability] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                cap = ModelCapability.model_validate(item)
            except Exception:  # noqa: BLE001 — 单条损坏跳过 (失败安全)
                continue
            loaded[(cap.provider, cap.model)] = cap
        self._capabilities = loaded

    def save(self) -> None:
        """全量原子写 (tmp + os.replace; root None 内存模式 → no-op)。"""
        if self.path is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)  # type: ignore[union-attr]
        payload = json.dumps(
            [c.to_dict() for c in self.list()], ensure_ascii=False, indent=2
        )
        fd, tmp = tempfile.mkstemp(
            prefix=f".{self.filename}.", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _persist(self) -> None:
        """变更后落盘 (root None → no-op)。"""
        if self.path is not None:
            self.save()

    # ------------------------------------------------------------- CRUD

    def register(
        self, capability: ModelCapability | dict[str, Any]
    ) -> ModelCapability:
        """注册/覆盖一个模型能力 (按 provider+model 键; 覆盖刷新 updated_at)。

        这是能力评分的唯一写入口 (人工/Benchmark 更新) — 经验统计/执行
        流程永不自动调用本方法 (第一阶段禁自动改分铁律)。
        """
        cap = (
            capability if isinstance(capability, ModelCapability)
            else ModelCapability.model_validate(capability)
        )
        existing = self._capabilities.get((cap.provider, cap.model))
        if existing is not None:
            cap.created_at = existing.created_at  # 保留首次创建时间
        cap.updated_at = _now_iso()
        self._capabilities[(cap.provider, cap.model)] = cap
        self._persist()
        return cap

    def get(self, provider: str, model: str) -> ModelCapability | None:
        """按 provider+model 查 (未知 → None, 不臆造)。"""
        return self._capabilities.get((_norm_str(provider), _norm_str(model)))

    def has(self, provider: str, model: str) -> bool:
        return (provider, model) in self._capabilities

    def list(self) -> list[ModelCapability]:
        """全部能力档案 (按 provider+model 排序 — 审计友好)。"""
        return sorted(
            self._capabilities.values(), key=lambda c: (c.provider, c.model)
        )

    def count(self) -> int:
        return len(self._capabilities)

    def remove(self, provider: str, model: str) -> bool:
        """删除一个模型能力 (不存在 → False; 删除成功 → True)。"""
        key = (_norm_str(provider), _norm_str(model))
        if key not in self._capabilities:
            return False
        del self._capabilities[key]
        self._persist()
        return True

    # ------------------------------------------------------------- 查询

    def find_by_capability(
        self, capability: str, min_score: float = 0.0
    ) -> list[ModelCapability]:
        """按能力找模型: 该能力评分 ≥ min_score 的模型 (降序 — 决策友好)。

        - 未知能力名 → ValueError (拼写错误即失败, 同 extra=forbid 契约);
        - min_score clamp [0,1]; 排序: 分数降序 → provider → model (确定)。
        """
        if capability not in CAPABILITY_SCORES:
            raise ValueError(
                f"unknown capability: {capability!r} "
                f"(expected one of {', '.join(CAPABILITY_SCORES)})"
            )
        threshold = _clamp01(min_score)
        hits = [
            c for c in self._capabilities.values()
            if c.score(capability) >= threshold
        ]
        hits.sort(
            key=lambda c: (-c.score(capability), c.provider, c.model)
        )
        return hits

    # ------------------------------------------------------------- 内置示例

    def seed_defaults(self, *, force: bool = False) -> int:
        """灌入内置示例配置 (声明式 JSON 文件)。

        已有条目不覆盖 (防示例覆盖用户数据; force=True 强制覆盖);
        返回新增条数。
        """
        added = 0
        for cap in load_default_config():
            key = (cap.provider, cap.model)
            if force or key not in self._capabilities:
                self._capabilities[key] = cap
                added += 1
        if added:
            self._persist()
        return added

    # ------------------------------------------------------------- 快照

    def snapshot(self, provider: str, model: str) -> dict[str, Any]:
        """能力快照 (T5.4 §3): Candidate 保存时冻结当前评分。

        {"provider", "model", "scores": {7 项}, "captured_at"} —
        历史结果可解释: 模型能力后续变化不影响已保存候选;
        无该模型 → {} 中性 (不臆造)。
        """
        cap = self.get(provider, model)
        if cap is None:
            return {}
        return {
            "provider": cap.provider,
            "model": cap.model,
            "scores": cap.scores,
            "captured_at": _now_iso(),
        }


def capability_snapshot(
    registry: Any, provider: str, model: str
) -> dict[str, Any]:
    """registry 能力快照 (duck-typed: registry None / 无 snapshot 方法 /
    无该模型 → {} 中性 — 调用方绝不因快照失败而破坏执行链)。"""
    if registry is None:
        return {}
    method = getattr(registry, "snapshot", None)
    if not callable(method):
        return {}
    return _norm_dict(method(provider, model))


# ================================================================ ModelExperienceStats

class ModelExperienceStats:
    """模型经验统计 (T5.4 §4; 统计字段, 禁自动改分铁律)。

    - 键: (provider, model), 可带 task_type 细分维度 (如: 该模型在此任务
      类型的成功率);
    - record_candidate(): ExecutionCandidate 喂入 (provider/model/is_success —
      与 experience_ctx 词汇同源: candidate.to_experience_signals 已映射);
    - 只统计不评分: 本类永不触碰 ModelCapability 评分 — 能力评分唯一
      更新途径 = CapabilityRegistry.register (人工/Benchmark, 第一阶段;
      测试强断言);
    - 复用 experience_ctx (T4.4) 语义, 不重复建库 (内存计数, 可序列化
      to_dict/from_dict 随审计输出落盘)。
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        if data:
            self.from_dict(data)

    # ------------------------------------------------------------- 记录

    def record(
        self,
        *,
        provider: str,
        model: str,
        success: bool,
        task_type: str = "",
    ) -> None:
        """记录一次成功/失败 (model 空 → 跳过 — 无模型信息不臆造)。"""
        model = _norm_str(model).strip()
        if not model:
            return
        key = capability_key(provider, model)
        bucket = self._data.setdefault(
            key, {"attempts": 0, "successes": 0, "failures": 0, "by_task_type": {}}
        )
        bucket["attempts"] = int(bucket["attempts"]) + 1
        if success:
            bucket["successes"] = int(bucket["successes"]) + 1
        else:
            bucket["failures"] = int(bucket["failures"]) + 1
        tt = _norm_str(task_type).strip()
        if tt:
            sub = bucket["by_task_type"].setdefault(
                tt, {"attempts": 0, "successes": 0, "failures": 0}
            )
            sub["attempts"] = int(sub["attempts"]) + 1
            if success:
                sub["successes"] = int(sub["successes"]) + 1
            else:
                sub["failures"] = int(sub["failures"]) + 1

    def record_candidate(self, candidate: Any, task_type: str = "") -> None:
        """ExecutionCandidate → 统计 (duck-typed; 空 model → 跳过)。"""
        model = _norm_str(getattr(candidate, "model", "")).strip()
        if not model:
            return
        self.record(
            provider=_norm_str(getattr(candidate, "provider", "")),
            model=model,
            success=bool(getattr(candidate, "is_success", False)),
            task_type=task_type,
        )

    def record_candidates(
        self, candidates: Iterable[Any], task_type: str = ""
    ) -> int:
        """批量喂入候选 (返回实际记录条数)。"""
        count = 0
        for candidate in candidates:
            if _norm_str(getattr(candidate, "model", "")).strip():
                self.record_candidate(candidate, task_type=task_type)
                count += 1
        return count

    # ------------------------------------------------------------- 查询

    def _bucket(
        self, provider: str, model: str
    ) -> dict[str, Any] | None:
        return self._data.get(capability_key(provider, model))

    def attempts(self, provider: str, model: str, task_type: str = "") -> int:
        bucket = self._bucket(provider, model)
        if bucket is None:
            return 0
        tt = _norm_str(task_type).strip()
        if not tt:
            return int(bucket["attempts"])
        sub = bucket["by_task_type"].get(tt)
        return int(sub["attempts"]) if sub else 0

    def successes(self, provider: str, model: str, task_type: str = "") -> int:
        bucket = self._bucket(provider, model)
        if bucket is None:
            return 0
        tt = _norm_str(task_type).strip()
        if not tt:
            return int(bucket["successes"])
        sub = bucket["by_task_type"].get(tt)
        return int(sub["successes"]) if sub else 0

    def failures(self, provider: str, model: str, task_type: str = "") -> int:
        bucket = self._bucket(provider, model)
        if bucket is None:
            return 0
        tt = _norm_str(task_type).strip()
        if not tt:
            return int(bucket["failures"])
        sub = bucket["by_task_type"].get(tt)
        return int(sub["failures"]) if sub else 0

    def success_rate(
        self, provider: str, model: str, task_type: str = ""
    ) -> float | None:
        """成功率 (无样本 → None, 不臆造 0)。"""
        attempts = self.attempts(provider, model, task_type=task_type)
        if attempts <= 0:
            return None
        return round(self.successes(provider, model, task_type=task_type) / attempts, 3)

    def model_summary(
        self, provider: str, model: str
    ) -> dict[str, Any] | None:
        """单模型汇总 (跨任务类型聚合; 无记录 → None)。"""
        bucket = self._bucket(provider, model)
        if bucket is None:
            return None
        attempts = int(bucket["attempts"])
        successes = int(bucket["successes"])
        return {
            "provider": _norm_str(provider),
            "model": _norm_str(model),
            "attempts": attempts,
            "successes": successes,
            "failures": int(bucket["failures"]),
            "success_rate": round(successes / attempts, 3) if attempts else None,
            "by_task_type": {
                tt: dict(sub) for tt, sub in bucket["by_task_type"].items()
            },
        }

    def totals(self) -> dict[str, int]:
        """全量汇总 (attempts/successes/failures)。"""
        attempts = successes = failures = 0
        for bucket in self._data.values():
            attempts += int(bucket["attempts"])
            successes += int(bucket["successes"])
            failures += int(bucket["failures"])
        return {
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
        }

    def keys(self) -> list[tuple[str, str]]:
        """有记录的 (provider, model) 列表 (排序 — 审计友好)。"""
        return sorted(
            (p, m) for p, m in (k.split("::", 1) for k in self._data)
        )

    # ------------------------------------------------------------- 序列化

    def to_dict(self) -> dict[str, Any]:
        """全量统计 dict (JSON 友好; 审计输出可落盘, 不重复建库)。"""
        return {
            key: {
                "attempts": int(b["attempts"]),
                "successes": int(b["successes"]),
                "failures": int(b["failures"]),
                "by_task_type": {
                    tt: dict(sub) for tt, sub in b["by_task_type"].items()
                },
            }
            for key, b in self._data.items()
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """dict → 统计 (计数非法/负值逐字段钳制 0; 失败安全, 单条坏不丢桶)。"""
        self._data = {}

        def _safe_int(v: Any) -> int:
            try:
                return max(0, int(v))
            except (TypeError, ValueError):
                return 0

        for key, bucket in _norm_dict(data).items():
            if not isinstance(key, str) or not isinstance(bucket, dict):
                continue
            by_task_type: dict[str, dict[str, int]] = {}
            for tt, sub in _norm_dict(bucket.get("by_task_type")).items():
                if not isinstance(tt, str) or not isinstance(sub, dict):
                    continue
                by_task_type[tt] = {
                    "attempts": _safe_int(sub.get("attempts")),
                    "successes": _safe_int(sub.get("successes")),
                    "failures": _safe_int(sub.get("failures")),
                }
            self._data[key] = {
                "attempts": _safe_int(bucket.get("attempts")),
                "successes": _safe_int(bucket.get("successes")),
                "failures": _safe_int(bucket.get("failures")),
                "by_task_type": by_task_type,
            }
