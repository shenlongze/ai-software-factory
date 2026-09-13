"""factory_runtime_entry.py — PyInstaller 入口 stub (Phase 15A-3c-2)。

为什么需要 stub: PyInstaller 把入口 script 当独立脚本收集, 顶层相对导入
(`from . import ...`) 在 script 模式无父包会 ImportError。stub 用绝对导入
`from runtime.cli import main` — 使 runtime 作为包加载, 内部相对导入正常,
且 __core/__console 内部路由 (runtime.cli._bundle_route) 一并生效。

禁止: 本文件不含业务逻辑; 仅转发 runtime.cli:main。
"""

import sys

from runtime.cli import main  # noqa: E402 — 入口 stub 先导包后运行

if __name__ == "__main__":
    sys.exit(main())
