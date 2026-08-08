#!/usr/bin/env python3
"""S8-005 单步冒烟 — UX/UI design (真实 DeepSeek v4-pro)。

只跑设计链第一段: 用最近一次 demo 产出的 VALIDATED product artifact
(org/artifacts.json A-S8-PRODUCT) → UXUIDesignerAgent.design() → 断言
JSON 解析成功 + 7 节齐全。目标: 验证 demo7 的 UX/UI 输出格式问题
(输出 12579/9953 chars 但解析失败) 已被解析宽容 + prompt 强化修复。

成本: 1 次真实 LLM 调用 (~$0.004)。成功/失败都如实输出, 不 mock。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/Users/Shared/work/ai-software-factory")
for p in ("factory-core", "factory-org", "factory-exec"):
    sys.path.insert(0, str(ROOT / p))

BASE = ROOT / "factory-exec" / "benchmark_s8_demo"
sys.path.insert(0, str(BASE))

from demo_full_chain import Recorder, build_provider  # noqa: E402
from exec.uxui import UXUIDesignerAgent  # noqa: E402


def load_product() -> dict:
    arts = json.loads((BASE / "org" / "artifacts.json").read_text(encoding="utf-8"))
    registry = arts.get("artifacts", arts)
    art = registry.get("A-S8-PRODUCT") if isinstance(registry, dict) else None
    if not art:
        raise SystemExit("A-S8-PRODUCT artifact not found in org/artifacts.json")
    meta = art.get("metadata") or {}
    if not meta:
        raise SystemExit("A-S8-PRODUCT has empty metadata")
    return meta


def main() -> int:
    recorder = Recorder()
    provider = build_provider(recorder)
    product = load_product()
    print(f"[smoke] product loaded: {sorted(product.keys())}", flush=True)

    agent = UXUIDesignerAgent(provider=provider, product=product)
    artifact = agent.design(product)
    d = artifact.to_dict()
    ok = sorted(d.keys()) == sorted(
        [
            "information_architecture",
            "user_flow",
            "wireframe",
            "screen_specifications",
            "component_definition",
            "design_tokens",
            "prototype",
        ]
    )
    print(f"[smoke] UX/UI artifact keys ({len(d)}): {sorted(d.keys())}", flush=True)
    print(f"[smoke] wireframe.screens={len(d.get('wireframe', {}).get('screens', []))}", flush=True)
    print(f"[smoke] user_flow={len(d.get('user_flow', []))} ", flush=True)
    print(f"[smoke] totals: {json.dumps(recorder.totals(), ensure_ascii=False)}", flush=True)
    print(f"[smoke] RESULT: {'PASS' if ok else 'FAIL'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
