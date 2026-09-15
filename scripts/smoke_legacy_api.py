#!/usr/bin/env python3
"""老区 API 可构建性冒烟 —— 删/改老区依赖后, 服务必须还能起。

为什么需要它（本刀踩过这条线）:
    老区 `factory_console/web/backend/fastapi_adapter` 是**正在跑的** HTTP 实现,
    它的 `create_app()` 里有许多**裸的动态导入** `_console_import(...)`
    —— 那是 `importlib.import_module`, **没有容错**: 删掉任何一个被引用的老区模块,
    只要引用处没改成可选, `create_app()` 就抛 ImportError ⇒ **整个 API 起不来**
    （不只是某一个端点失效）。

    删 `console_sessions` 时正是这条线: 14 个端点受影响是"局部", 但
    `create_app()` 崩是"全局"。故把"服务能构建"固化为常驻门。

覆盖:
    ① `create_app()` 可构建（不抛异常）
    ② 路由数 > 0（不是空壳）
    ③ 老区 `/api/*` 端点数 ≥ 基线 389（防误删端点）
    ④ `/api/sessions` 那 14 个端点仍在（实现降级 ≠ 端点消失；WebUI 挂起中）

用法: python scripts/smoke_legacy_api.py        退出码 0=通过 / 1=失败
副作用: tempdir 作为数据根, 零污染用户数据 ✓
"""
from __future__ import annotations

import re
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "src",
          ROOT / "src" / "ai_factory_os" / "_pending_migration",
          ROOT / "src" / "ai_factory_os" / "_pending_migration" / "factory_console"):
    sys.path.insert(0, str(p))
warnings.filterwarnings("ignore", category=DeprecationWarning)

#: 老区端点基线（2026-09-15 实测）；只允许增/持平, 减即报红
ENDPOINT_BASELINE = 389
ADAPTER = (ROOT / "src" / "ai_factory_os" / "_pending_migration" / "factory_console"
           / "web" / "backend" / "fastapi_adapter.py")


def main() -> int:
    cases: list[tuple[str, bool, str]] = []

    # ③ 端点数（静态扫, 不依赖运行时）
    src = ADAPTER.read_text(encoding="utf-8")
    n_ep = len(re.findall(r'@app\.(?:get|post|put|delete|patch)\(\s*"/api/', src))
    cases.append((f"③ 老区 /api 端点数 ≥ {ENDPOINT_BASELINE}",
                  n_ep >= ENDPOINT_BASELINE, f"实测 {n_ep}"))
    n_sess = len(re.findall(r'@app\.(?:get|post|put|delete|patch)\(\s*"/api/sessions', src))
    cases.append(("④ /api/sessions 14 端点仍在", n_sess == 14, f"实测 {n_sess}"))

    # ①② 运行时: create_app() 能否构建
    try:
        from ai_factory_os.compat_aliases import install
        install()
        from factory_console.web.backend.fastapi_adapter import create_app

        app = create_app(factory_root=Path(tempfile.mkdtemp()))
        n_routes = len(app.routes)
        cases.append(("① create_app() 可构建", True, ""))
        cases.append(("② 路由数 > 0", n_routes > 0, f"{n_routes}"))
    except Exception as exc:  # noqa: BLE001 — 构建失败就是本脚本要抓的东西
        cases.append(("① create_app() 可构建", False, f"{type(exc).__name__}: {exc}"))
        cases.append(("② 路由数 > 0", False, "未构建"))

    print("── 老区 API 可构建性冒烟（删/改老区依赖后, 服务必须还能起）")
    ok = sum(1 for _, v, _ in cases if v)
    for n, v, got in cases:
        print(f"   [{'PASS' if v else 'FAIL'}] {n}" + (f"   ← {got}" if got else ""))
    print(f"   {ok}/{len(cases)} 通过")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
