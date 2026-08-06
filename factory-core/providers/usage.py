"""providers/usage.py — Provider 使用记录 + 性能聚合 (Phase 8B-2)。

设计依据:
- phase8b2-plan.md §3/§5: ProviderUsage (每次调用记录) → UsageStore
  (.factory/providers/usage.json 独立数据空间, 原子写, 损坏失败安全) →
  ProviderPerformanceStats (provider/model/version/period 维度聚合, 评审调整 3,
  从 usage 计算不落库 — §7 存储边界: 性能聚合事件驱动)。
- estimated_cost 由 CostModel 估算 (非真实计费, §8); 失败调用也记录
  (success=False + error, 成功率聚合的数据基础)。
- 损坏失败安全 (区别于 ProviderStore 的报错语义): usage 是审计增强数据,
  损坏/单条校验失败 → 跳过, 读命令永不因 usage 文件问题失败 (与
  dashboard 失败安全哲学一致)。

period 语义 (stats_from_usage / filter_by_period):
- day:  recorded_at 日期 == 今天 (UTC, 与事件时间戳口径一致)
- week: recorded_at 日期在最近 7 天 (含今天)
- all:  不过滤
- 非法 period → ValueError (CLI parser 以 choices 前置拦截)。

聚合分组: (provider_id, model, version) 三维度 (评审调整 3) — model/version
为 None 时归入 None 桶 (聚合未标注模型的使用记录)。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from events.models import format_timestamp, parse_timestamp

from .models import _id_sane

#: 合法聚合周期
PERIODS: tuple[str, ...] = ("day", "week", "all")


class ProviderUsage(BaseModel):
    """一次 Provider 调用使用记录 (审计增强数据, 非真实计费)。

    - id: 记录唯一键 (uuid hex, 存储层回填); execution_id: 关联执行 (可选);
      task_id: 执行所属任务 (可选, Phase 8B-3 集成层自动记录时回填)。
    - model/version: 使用的模型与版本 (评审调整 3 — 性能聚合维度)。
    - estimated_cost: CostModel 估算成本 (USD); latency_ms: 调用延迟
      (执行时长, Phase 8B-3 集成层计时); success/error: 成败与失败描述
      (失败也记录, 成功率聚合数据基础)。
    - recorded_at: 统一 UTC 时间戳格式 (events TS_FORMAT, 字符串排序即时间排序)。
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    provider_id: str
    execution_id: str | None = None
    task_id: str | None = None
    model: str | None = None
    version: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: int = 0
    success: bool = True
    error: str | None = None
    recorded_at: str = Field(
        default_factory=lambda: format_timestamp(datetime.now(timezone.utc))
    )

    @field_validator("provider_id")
    @classmethod
    def _usage_id_sane(cls, v: str) -> str:
        return _id_sane(v)

    @field_validator("prompt_tokens", "completion_tokens")
    @classmethod
    def _tokens_nonnegative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"tokens must be non-negative: {v}")
        return v

    @field_validator("latency_ms")
    @classmethod
    def _latency_nonnegative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"latency_ms must be non-negative: {v}")
        return v

    @field_validator("estimated_cost")
    @classmethod
    def _cost_nonnegative(cls, v: float) -> float:
        if v < 0.0:
            raise ValueError(f"estimated_cost must be non-negative: {v}")
        return v

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class ProviderPerformanceStats(BaseModel):
    """Provider 性能聚合 (provider/model/version/period 维度, 评审调整 3)。

    从 usage 记录计算, 不落库 (phase8b2-plan.md §7); period 标记聚合周期。
    Phase 8B-3 增强: failure_rate (失败率 = 1 - success_rate) / execution_count
    (执行次数, 与 calls 同值 — 兼容 8B-2 字段) / avg_duration_ms (平均执行
    时长, 与 avg_latency_ms 同值 — 执行时长口径别名) / avg_cost (单次平均
    估算成本 = total_cost / calls, CLI stats 与 Dashboard 展示列)。

    口径 (stats_from_usage 填充):
    - success_rate = 成功调用 / 总调用 (0 调用 → 0.0);
    - failure_rate = 1 - success_rate (0 调用 → 0.0);
    - execution_count = 总调用数 (= calls, 兼容别名);
    - avg_duration_ms = 平均执行时长 ms (= avg_latency_ms, 兼容别名);
    - avg_cost = total_cost / calls (0 调用 → 0.0);
    - total_cost = 估算成本累计; total_tokens = 全部 token 和。
    """

    provider_id: str
    model: str | None = None
    version: str | None = None
    period: str = "all"
    calls: int = 0
    execution_count: int = 0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_duration_ms: float = 0.0
    avg_cost: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @model_validator(mode="after")
    def _sync_compat_aliases(self) -> "ProviderPerformanceStats":
        """8B-2/8B-3 兼容别名同步: execution_count == calls, avg_duration_ms ==
        avg_latency_ms (docstring 契约: 同一口径的兼容别名, 不产生双真相)。

        构造时只给 8B-2 字段 (calls/avg_latency_ms) 或只给 8B-3 别名时, 另一方
        回填同值; 双方都显式给值 → 以显式值为准 (不覆盖)。
        """
        if self.execution_count == 0 and self.calls != 0:
            self.execution_count = self.calls
        elif self.calls == 0 and self.execution_count != 0:
            self.calls = self.execution_count
        if self.avg_duration_ms == 0.0 and self.avg_latency_ms != 0.0:
            self.avg_duration_ms = self.avg_latency_ms
        elif self.avg_latency_ms == 0.0 and self.avg_duration_ms != 0.0:
            self.avg_latency_ms = self.avg_duration_ms
        return self


class UsageStoreError(Exception):
    """UsageStore 基础异常。"""


class UsageStore:
    """Provider 使用记录 JSON 文件库 (独立文件 usage.json, 与 catalog.json 同目录)。

    - 独立数据空间: <providers_dir>/usage.json (phase8b2-plan.md §7), 与
      Provider 定义 catalog.json 完全分离 — 删除 usage 文件不影响 Provider 目录。
    - 原子写: 临时文件 + os.replace (同 ProviderStore 模式)。
    - 损坏失败安全: 文件损坏/单条校验失败 → 跳过 (list 返回可读部分, 读命令
      永不因 usage 文件问题失败); append 在损坏文件上从空重建。
    - 文件格式 (KISS, 单节):
      ```json
      {"records": [ {ProviderUsage dict}, ... ]}
      ```
    """

    filename = "usage.json"

    def __init__(self, providers_dir: str | Path):
        self._dir = Path(providers_dir)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def path(self) -> Path:
        return self._dir / self.filename

    # ------------------------------------------------------------------ 写

    def record(self, usage: ProviderUsage) -> ProviderUsage:
        """追加一条使用记录 (原子写); 返回带存储层回填 id 的记录。"""
        records = self._read_all()
        records.append(usage)
        self._write_all(records)
        return usage

    def clear(self) -> None:
        """清空全部使用记录 (重建空库)。"""
        self._write_all([])

    # ------------------------------------------------------------------ 读

    def list(self) -> list[ProviderUsage]:
        """全部使用记录 (按 recorded_at 升序); 损坏 → 可读部分/空列表。"""
        return sorted(self._read_all(), key=lambda r: r.recorded_at)

    def count(self) -> int:
        return len(self._read_all())

    # ------------------------------------------------------------------ 内部

    def _read_all(self) -> list[ProviderUsage]:
        """读整库; 文件不存在 → 空; 损坏 (JSON/结构/单条校验) → 失败安全跳过。"""
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []  # 损坏失败安全: 解析失败 → 空库
        if not isinstance(raw, dict) or not isinstance(raw.get("records"), list):
            return []
        records: list[ProviderUsage] = []
        for item in raw["records"]:
            try:
                records.append(ProviderUsage.model_validate(item))
            except Exception:
                continue  # 单条损坏 → 跳过 (不拖垮整库)
        return records

    def _write_all(self, records: list[ProviderUsage]) -> None:
        """原子写整库: 临时文件 + os.replace (同 ProviderStore 模式)。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._dir / f".{self.filename}.{os.getpid()}.tmp"
        payload = {
            "records": [r.to_dict() for r in sorted(records, key=lambda r: r.recorded_at)]
        }
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.path)


# ------------------------------------------------------------------ period 过滤 (纯函数)


def filter_by_period(
    records: list[ProviderUsage], period: str = "all",
) -> list[ProviderUsage]:
    """按聚合周期过滤记录 (day|week|all); 非法 period → ValueError。"""
    if period == "all":
        return records
    if period not in PERIODS:
        raise ValueError(f"invalid period: {period!r} (expected one of: {', '.join(PERIODS)})")
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=6)  # week = 最近 7 天 (含今天)
    out: list[ProviderUsage] = []
    for r in records:
        try:
            day = parse_timestamp(r.recorded_at).date()
        except ValueError:
            continue  # 时间戳无法解析 → 不参与 period 过滤 (失败安全)
        if period == "day":
            if day == today:
                out.append(r)
        else:  # week
            if day >= cutoff:
                out.append(r)
    return out


def stats_from_usage(
    records: list[ProviderUsage],
    *,
    provider_id: str | None = None,
    period: str = "all",
    model: str | None = None,
    version: str | None = None,
) -> list[ProviderPerformanceStats]:
    """从使用记录聚合性能统计 (provider/model/version 维度, 按 period 过滤)。

    Args:
        records: 使用记录 (UsageStore.list())。
        provider_id/model/version: 可选维度过滤 (None = 不过滤)。
        period: day|week|all (见 filter_by_period)。

    Returns:
        按 (provider_id, model, version) 排序的统计列表; 无记录 → []。
        口径 (Phase 8B-3 增强): success_rate = 成功调用 / 总调用 (0 调用 →
        0.0); failure_rate = 1 - success_rate; execution_count = 调用数
        (= calls); avg_duration_ms = 平均执行时长 ms (= avg_latency_ms);
        total_tokens = 全部 token 和; total_cost = 估算成本累计。
    """
    recs = filter_by_period(records, period)
    if provider_id is not None:
        recs = [r for r in recs if r.provider_id == provider_id]
    if model is not None:
        recs = [r for r in recs if r.model == model]
    if version is not None:
        recs = [r for r in recs if r.version == version]
    groups: dict[tuple[str, str | None, str | None], list[ProviderUsage]] = {}
    for r in recs:
        groups.setdefault((r.provider_id, r.model, r.version), []).append(r)
    stats: list[ProviderPerformanceStats] = []
    for (pid, m, ver), items in sorted(groups.items()):
        calls = len(items)
        ok = sum(1 for i in items if i.success)
        success_rate = round(ok / calls, 4) if calls else 0.0
        avg_latency = round(sum(i.latency_ms for i in items) / calls, 2) if calls else 0.0
        total_cost = round(sum(i.estimated_cost for i in items), 6)
        stats.append(
            ProviderPerformanceStats(
                provider_id=pid,
                model=m,
                version=ver,
                period=period,
                calls=calls,
                execution_count=calls,
                success_rate=success_rate,
                failure_rate=round(1.0 - success_rate, 4),
                avg_latency_ms=avg_latency,
                avg_duration_ms=avg_latency,
                avg_cost=round(total_cost / calls, 6) if calls else 0.0,
                total_tokens=sum(i.total_tokens for i in items),
                total_cost=total_cost,
            )
        )
    return stats


# ------------------------------------------------------------------ Phase 8B-3: 性能分 + Declared vs Actual


def performance_score_from_stats(
    stats: ProviderPerformanceStats | None,
) -> float:
    """从聚合统计计算性能分 (0-1, Phase 8B-3, ADR-0025)。

    - 无统计 / 0 执行 → 0.5 中性 (8B-2 兼容: 无 usage 数据不臆造性能,
      推荐排序退化为成本优先语义)。
    - 有数据: 成功率 (60% 权重) + 时长归一 (40% 权重) —
      duration_score = clamp(1 - avg_duration_ms/60_000, 0, 1) (60s 内线性
      递减, 60s+ 记 0)。归一基准常量即文档 (估算模型, 非真实计费)。
    """
    if stats is None or stats.execution_count <= 0:
        return 0.5
    duration_score = max(0.0, 1.0 - stats.avg_duration_ms / 60_000.0)
    return round(0.6 * stats.success_rate + 0.4 * duration_score, 4)


def declared_vs_actual(
    profiles: dict[str, Any] | None,
    stats: list[ProviderPerformanceStats],
) -> list[dict[str, Any]]:
    """Declared vs Actual 对比 (Provider Intelligence Loop 可视化数据源)。

    - declared = 能力基线声明值 (ProviderCapabilityProfile 平均 matrix 质量分,
      无 profile → None — 无声明不臆造)。
    - actual = 实测聚合 (成功率先按 provider 合并多个 (model, version) 桶:
      success_rate = 全部成功 / 全部调用; avg_duration_ms 按调用数加权;
      execution_count = 调用数; 无 usage 记录 → None 字段)。
    - gap = declared - actual_success_rate (正 = 表现不及声明, 负 = 优于声明;
      任一侧缺失 → None)。
    返回按 provider_id 排序的对比条目 dict (JSON 友好, CLI/Dashboard 展示用)。
    """
    profiles = dict(profiles or {})
    actual: dict[str, dict[str, Any]] = {}
    for s in stats:
        acc = actual.setdefault(s.provider_id, {"ok": 0, "calls": 0, "latency": 0.0})
        acc["ok"] += round(s.success_rate * s.calls)
        acc["calls"] += s.calls
        acc["latency"] += s.avg_duration_ms * s.calls
    out: list[dict[str, Any]] = []
    for provider_id in sorted(set(profiles) | set(actual)):
        profile = profiles.get(provider_id)
        declared = None
        if profile is not None:
            matrix = getattr(profile, "matrix", None) or {}
            declared = (
                round(sum(float(v) for v in matrix.values()) / len(matrix), 4)
                if matrix else None
            )
        acc = actual.get(provider_id)
        if acc and acc["calls"]:
            actual_success = round(acc["ok"] / acc["calls"], 4)
            actual_duration = round(acc["latency"] / acc["calls"], 2)
        else:
            actual_success = actual_duration = None
        entry: dict[str, Any] = {
            "provider_id": provider_id,
            "declared_score": declared,
            "actual_success_rate": actual_success,
            "actual_avg_duration_ms": actual_duration,
            "actual_execution_count": acc["calls"] if acc else 0,
        }
        entry["gap"] = (
            round(declared - actual_success, 4)
            if declared is not None and actual_success is not None else None
        )
        out.append(entry)
    return out


def stats_by_provider(
    records: list[ProviderUsage],
    period: str = "all",
) -> dict[str, ProviderPerformanceStats]:
    """按 provider 合并多 (model, version) 桶 → 单一统计 (推荐/展示注入用)。

    聚合口径与 stats_from_usage 一致, 只是跨 model/version 合并:
    - success_rate = 全部成功 / 全部调用; failure_rate = 1 - success_rate;
    - avg_duration_ms (= avg_latency_ms) 按调用数加权; avg_cost = 全部成本 /
      全部调用; total_tokens / total_cost 求和。
    - 无记录 → 空 dict。period 过滤语义同 stats_from_usage (day|week|all)。
    """
    acc: dict[str, dict[str, float | int]] = {}
    for s in stats_from_usage(records, period=period):
        a = acc.setdefault(
            s.provider_id, {"calls": 0, "ok": 0, "latency": 0.0, "tokens": 0, "cost": 0.0},
        )
        a["calls"] = int(a["calls"]) + s.calls
        a["ok"] = int(a["ok"]) + round(s.success_rate * s.calls)
        a["latency"] = float(a["latency"]) + s.avg_duration_ms * s.calls
        a["tokens"] = int(a["tokens"]) + s.total_tokens
        a["cost"] = float(a["cost"]) + s.total_cost
    out: dict[str, ProviderPerformanceStats] = {}
    for provider_id, a in sorted(acc.items()):
        calls = int(a["calls"])
        success_rate = round(int(a["ok"]) / calls, 4) if calls else 0.0
        avg_duration = round(float(a["latency"]) / calls, 2) if calls else 0.0
        out[provider_id] = ProviderPerformanceStats(
            provider_id=provider_id,
            period=period,
            calls=calls,
            execution_count=calls,
            success_rate=success_rate,
            failure_rate=round(1.0 - success_rate, 4) if calls else 0.0,
            avg_latency_ms=avg_duration,
            avg_duration_ms=avg_duration,
            avg_cost=round(float(a["cost"]) / calls, 6) if calls else 0.0,
            total_tokens=int(a["tokens"]),
            total_cost=round(float(a["cost"]), 6),
        )
    return out
