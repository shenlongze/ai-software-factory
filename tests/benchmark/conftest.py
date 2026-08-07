"""tests/benchmark/conftest.py — Benchmark 样本/verifier/runner 测试 fixtures (Phase A+++++)。

sys.path: 挂 factory-core (Core 包) + factory-exec (exec 包父目录 — 以 `exec`
导入), 同 tests/exec/conftest.py 模式。本目录自洽: 不跨目录依赖 helper;
测试文件 basename 一律 test_benchmark_* 前缀 (backend-developer skill 陷阱:
多非包目录共存时同名模块互相遮蔽)。

原则: 全部测试不调 LLM (verifier 纯静态/行为检查; runner 用 FakeProvider 注入
确定性回复), 不触碰 markpad 生产目录 (样本完整性测试对项目文件的存在性检查
带 skipif 守卫 — 项目目录缺失时跳过而非失败)。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:  # exec 包父目录 (factory-exec/exec/)
    sys.path.insert(0, str(_FACTORY_EXEC))

import pytest  # noqa: E402
