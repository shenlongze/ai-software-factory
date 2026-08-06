# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec — factory-runtime-bundle (Phase 15A-3c-2)。

产物: dist/factory-runtime-bundle/factory-runtime-bundle (onedir, macOS 无
后缀; Windows 为 .exe)。构建: scripts/build-runtime-bundle.sh。

设计要点:
1. 入口 = factory-runtime/bundle/factory_runtime_entry.py (绝对导入 stub:
   `from runtime.cli import main`) — PyInstaller 把入口 script 当独立脚本
   收集, 顶层相对导入在 script 模式会 ImportError; stub 用绝对导入使
   runtime 作为包加载, 内部相对导入 + bundle 内部路由 (__core/__console,
   见 runtime/cli.py _bundle_route) 一并生效。stub 零业务逻辑。
2. hidden imports 全收集, 禁止复制代码:
   - 运行时第三方: platformdirs / rich / pydantic / yaml / fastapi /
     uvicorn / httpx (collect_submodules 递归)。
   - factory-core 全部顶层包 (collect_submodules, 排除 `runtime`)。
   - factory-console (含连字符 namespace 包): 显式子模块清单 +
     fastapi_adapter (pathex 定位)。
   - 前端 build 产物 (datas) → bundle 内 console_web/ (缺 → 纯 API 模式)。
3. ★ 顶层 `runtime` 同名冲突 (factory-runtime/runtime vs
   factory-core/runtime): PyInstaller modulegraph 全局唯一包名, 入口
   依赖 factory-runtime/runtime → core 的 `from runtime.store import ...`
   无法静态收集。解法: 两包子模块文件名零重叠, 在 Analysis 后把
   factory-core/runtime 的子模块以完整模块名 (runtime.store 等) 追加进
   a.pure — PyInstaller frozen importer 按完整名从 pyz 加载, 同名共存,
   无需复制/重命名任何代码 (验证: bundle __core 冒烟跑真实 Core)。
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
REPO_ROOT = SPEC_DIR.parents[1]  # factory-runtime/bundle/ → repo 根
RUNTIME_DIR = REPO_ROOT / "factory-runtime"  # 含顶层 `runtime` 包 (绝对导入 stub 依赖)
CORE_DIR = REPO_ROOT / "factory-core"
CONSOLE_DIR = REPO_ROOT / "factory-console"
BACKEND_DIR = CONSOLE_DIR / "web" / "backend"
FRONTEND_DIST = CONSOLE_DIR / "web" / "frontend" / "dist"
RUNTIME_ENTRY = REPO_ROOT / "factory-runtime" / "bundle" / "factory_runtime_entry.py"

# ---------------------------------------------------------------- 收集清单

#: factory-core 顶层包 (排除 runtime — 与 factory-runtime 同名, TOC 合并)
CORE_PACKAGES = [
    "agents", "assignment", "change", "changeflow", "cli", "dashboard",
    "demo", "events", "execution", "git", "intelligence", "metrics",
    "orchestration", "product", "project", "providers", "recovery",
    "runtimes", "tasks", "understanding", "validation", "workflows",
    "workspace",
]

#: factory-console 显式子模块 (含连字符 namespace 包, importlib 动态导入;
#: 不用 collect_submodules — 顶层名非合法标识符, 显式清单最稳)
CONSOLE_MODULES = [
    "factory-console",
    "factory-console.api",
    "factory-console.api.approvals",
    "factory-console.api.decisions",
    "factory-console.api.intelligence",
    "factory-console.api.lifecycle",
    "factory-console.api.projects",
    "factory-console.api.providers",
    "factory-console.events",
    "factory-console.models",
    "factory-console.service",
]

#: 运行时第三方依赖 (递归收集; uvicorn 纯 asyncio fallback, 无需
#: uvloop/httptools 等加速器 — KISS)
THIRD_PARTY = ["platformdirs", "yaml", "rich", "pydantic", "fastapi", "uvicorn", "httpx"]

hidden_core = [m for pkg in CORE_PACKAGES for m in collect_submodules(pkg)]
hidden_third = [m for pkg in THIRD_PARTY for m in collect_submodules(pkg)]


def _core_runtime_entries() -> list[tuple[str, str, str]]:
    """factory-core/runtime 子模块 → 完整模块名 TOC 条目 (同名共存)。

    跳过 __init__.py — 顶层 `runtime` 已由 factory-runtime 占用; core
    模块全部经 `from runtime.<sub> import ...` 子模块导入, 不依赖顶层
    re-export (已核对 factory-core 源码)。
    """
    entries: list[tuple[str, str, str]] = []
    rt = CORE_DIR / "runtime"
    for py in sorted(rt.glob("*.py")):
        if py.name == "__init__.py":
            continue
        entries.append((f"runtime.{py.stem}", str(py), "PYMODULE"))
    for py in sorted((rt / "adapters").glob("*.py")):
        if py.name == "__init__.py":
            entries.append(("runtime.adapters", str(py), "PYMODULE"))
        else:
            entries.append((f"runtime.adapters.{py.stem}", str(py), "PYMODULE"))
    return entries


def _console_datas() -> list[tuple[str, str]]:
    """前端 build 产物 (SPA) → bundle 内 console_web/; 缺 → 纯 API 模式。"""
    if not FRONTEND_DIST.is_dir():
        return []
    return [(str(FRONTEND_DIST), "console_web")]


# ------------------------------------------------------------------ Analysis

a = Analysis(
    [str(RUNTIME_ENTRY)],
    # RUNTIME_DIR 置于最前: stub 绝对导入 `runtime.cli` 必须解析到
    # factory-runtime/runtime (同名冲突: factory-core/runtime 无 cli.py,
    # 若被 modulegraph 先命中会收集失败或张冠李戴)
    pathex=[str(RUNTIME_DIR), str(REPO_ROOT), str(CORE_DIR), str(CONSOLE_DIR), str(BACKEND_DIR)],
    binaries=[],
    datas=_console_datas(),
    hiddenimports=hidden_core + CONSOLE_MODULES + hidden_third + ["fastapi_adapter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

#: ★ 同名 runtime 包合并: core 子模块以完整名进入 pyz (见模块 docstring)
a.pure += _core_runtime_entries()

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="factory-runtime-bundle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="factory-runtime-bundle",
)
