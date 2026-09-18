"""apps/cli/_aliases — 装上「旧名 → 新路径」别名桥（compat_aliases）。

★ 为什么单独成模块（而不是在 main.py 里直接调 install()）:
   compat_aliases 要求"在任何 import 之前调用 install()", 但 main.py 里 import 区
   是连续的 —— 在中间插一句调用会让**其后所有 import** 被 ruff 判 E402
   (module level import not at top of file)。
   把 install() 放进本模块 ⇒ main.py 只需在 import 区第一行 `from . import _aliases`,
   既是合法 import, 又保证了"install 先于后续所有 import 执行"。

   （bin/factory 与 scripts/check_imports.py 是脚本入口, 直接一行调用即可, 无此约束。）
"""

from __future__ import annotations

import ai_factory_os.compat_aliases as _compat_aliases

_compat_aliases.install()

__all__: list[str] = []
