"""tests/console/test_real_llm_smoke.py — R0 A2 REAL LLM Smoke (opt-in)。

真实 DeepSeek 调用证据 (不是 fake interpreter 冒充):
    FACTORY_REAL_LLM=1 .venv/bin/python -m pytest tests/console/test_real_llm_smoke.py -q

依赖 (均只读):
    ~/.factory/providers.json (deepseek enabled, api_key_ref=env:DEEPSEEK_API_KEY)
    进程环境 DEEPSEEK_API_KEY (providers.json 只存 env 引用, 不存明文)

无 key / 未显式开启 → skip (CI 不依赖真实网络/Key; 不冒充 REAL_LLM_SMOKE)。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "factory-core")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("FACTORY_REAL_LLM") != "1"
    or not os.environ.get("DEEPSEEK_API_KEY"),
    reason="opt-in REAL LLM smoke: FACTORY_REAL_LLM=1 + DEEPSEEK_API_KEY",
)


def test_real_llm_semantic_understanding(tmp_path: Path) -> None:
    from factory_console.canonical_golden_path import CanonicalGoldenPath

    orch = CanonicalGoldenPath(str(tmp_path), semantic=True)
    conv = orch.create_conversation(title="REAL LLM smoke")["id"]

    res = orch.handle(
        conv,
        "我想做一个飞机大战小游戏，可以在浏览器运行，"
        "需要飞机移动、发射子弹、敌机出现和基本得分。",
    )
    assert res["kind"] == "chat", f"真实 LLM smoke 未走理解管道: {res}"
    snap = orch.understanding.snapshot(conv)
    assert snap.get("facts"), (
        "真实 LLM 未产生任何事实 — LLM 不可用被降级 (CLARIFY)。"
        f"res={res}"
    )
    assert res.get("reply"), "真实 LLM smoke 无回复"

    # 第二轮: 自然语言修改理解 (证明是连续理解, 非一次性)
    res2 = orch.handle(conv, "不需要登录，打开就能玩")
    assert res2["kind"] == "chat", res2
    assert orch.understanding.snapshot(conv)["version"] >= snap["version"]
