"""factory-exec/exec/benchmark/__init__.py — Benchmark 包 (Phase A+++++)。

样本集: 5 Bug + 3 Feature + 1 Greenfield (bugs.py / features.py / greenfield.py),
每个样本含 verifier 验收 (纯 Python 静态/行为检查, 不依赖 LLM)。
执行框架: runner.py (样本 → factory-exec 执行链 → 7 指标 + 五维评分)。

顶层 __init__ 不 import 子模块 (延迟加载, 同 exec 包语义): 导入 benchmark
零副作用; 使用方显式 `from exec.benchmark.samples import ALL_SAMPLES`。
"""

from __future__ import annotations

__version__ = "0.1.0"
