"""factory-exec/exec/benchmark/samples.py — 样本集注册表 (5 Bug + 3 Feature + 1 Greenfield)。

汇总 bugs.py / features.py / greenfield.py 为单一注册表, 供 runner / 报告 / 测试
统一引用。完整性约束 (唯一 id / 5-3-1 配比 / verifier 已注册) 由
tests/benchmark/test_benchmark_samples.py 校验 (不调 LLM)。
"""

from __future__ import annotations

from . import bugs, features, greenfield
from .models import BenchmarkSample

#: 全样本集 (5 Bug + 3 Feature + 1 Greenfield = 9)
ALL_SAMPLES: list[BenchmarkSample] = [
    *bugs.BUG_SAMPLES,
    *features.FEATURE_SAMPLES,
    *greenfield.GREENFIELD_SAMPLES,
]

#: 按 id 索引 (唯一性由测试校验; 重复 → 后注册覆盖, 与 provider registry 同语义)
SAMPLES_BY_ID: dict[str, BenchmarkSample] = {s.id: s for s in ALL_SAMPLES}

#: 各类型样本数 (报告/预检用)
KIND_COUNTS: dict[str, int] = {"bug": 5, "feature": 3, "greenfield": 1}
