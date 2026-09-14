"""旧模块名 → 新路径的运行时别名桥（绞杀者过渡层）。

用途：搬迁时【不再逐个改消费方的 import】。文件搬进新层后，在此登记别名，
      消费方继续用旧名字，解析由本桥接管。

核心保证（已 PoC 实测 7/7 通过）：
  ① 旧名可解析（含 from X import *）
  ② 拿到的是【同一个模块对象】→ isinstance / 类身份安全
     （实现要点：create_module 返回 importlib.import_module(目标) 的结果，
       而不是让 Python 新建一个模块）
  ③ 改名过的子模块也能映射（如 tasks.models → services.work.types）

用法：在【任何 import 之前】调用 install()。产品入口 bin/factory、
      验证脚本 scripts/check_imports.py 已接入。
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

#: 前缀映射：旧顶层名 → 新路径前缀。
#: 子模块自动跟随（tasks.store → ai_factory_os.services.work.store），
#: 因此【动态拼出来的模块名】也能命中（不必枚举）。
ALIAS_PREFIXES: dict[str, str] = {
    # ── 原 factory-core（已搬出者）──
    "tasks": "ai_factory_os.services.work",
    "events": "ai_factory_os.infrastructure.events",
    "agents": "ai_factory_os.plugins.agents",
    "git": "ai_factory_os.infrastructure.git",
    "workspace": "ai_factory_os.infrastructure.storage",
    "runtimes": "ai_factory_os.services.execution",
    "runtime": "ai_factory_os.services.execution.runtime",
    "understanding": "ai_factory_os.services.conversation",
    "intelligence": "ai_factory_os.services.learning",
    "change": "ai_factory_os.services.work.change",
    "execution": "ai_factory_os.services.execution",
    # ── 原 factory-org / exec / services ──
    "org": "ai_factory_os.services.organization",
    "skill": "ai_factory_os.plugins.skills.skill",
    "tool": "ai_factory_os.plugins.tools.tool",
    "mcp": "ai_factory_os.plugins.mcp.client",
    "roles": "ai_factory_os.plugins.agents.roles",
    "architect": "ai_factory_os.plugins.agents.architect",
    "developer": "ai_factory_os.plugins.agents.developer",
    "pm": "ai_factory_os.plugins.agents.pm",
    "tester": "ai_factory_os.plugins.agents.tester",
    "uxui": "ai_factory_os.plugins.agents.uxui",
}

#: 单名覆盖：R10 改名过的模块（models.py → types.py 等）
ALIAS_RENAMES: dict[str, str] = {
    "tasks.models": "ai_factory_os.services.work.types",
    "events.models": "ai_factory_os.infrastructure.events.types",
    "agents.models": "ai_factory_os.plugins.agents.types",
    "git.models": "ai_factory_os.infrastructure.git.types",
    "workspace.models": "ai_factory_os.infrastructure.storage.types",
    "runtime.models": "ai_factory_os.services.execution.runtime.types",
    "understanding.models": "ai_factory_os.services.conversation.types",
    "intelligence.models": "ai_factory_os.services.learning.types",
    "change.models": "ai_factory_os.services.work.change.types",
    "runtimes.models": "ai_factory_os.services.execution.runtime_types",
}

_SEP = "."  # 便于替换分隔符


def _target(fullname: str) -> str | None:
    """旧模块名 → 新模块名；无别名则 None。"""
    if fullname in ALIAS_RENAMES:
        return ALIAS_RENAMES[fullname]
    head, _, rest = fullname.partition(_SEP)
    prefix = ALIAS_PREFIXES.get(head)
    if prefix is None:
        return None
    return f"{prefix}{_SEP}{rest}" if rest else prefix


class _AliasLoader(importlib.abc.Loader):
    """让旧名指向【已存在的】新模块对象（关键：不是新建一份）。"""

    def __init__(self, target: str) -> None:
        self.target = target

    def create_module(self, spec):                      # noqa: ANN001
        return importlib.import_module(self.target)

    def exec_module(self, module) -> None:              # noqa: ANN001
        pass                                            # 目标模块已执行过


class AliasFinder(importlib.abc.MetaPathFinder):
    """置于 sys.meta_path 首位 → 优先于文件系统查找，旧名永远命中桥。"""

    def find_spec(self, fullname, path=None, target=None):   # noqa: ANN001
        real = _target(fullname)
        if real is None or real == fullname:
            return None
        return importlib.machinery.ModuleSpec(fullname, _AliasLoader(real))


_installed = False


def install() -> None:
    """装桥（幂等）。必须在【任何 import 之前】调用。"""
    global _installed
    if _installed:
        return
    sys.meta_path.insert(0, AliasFinder())
    _installed = True


def aliases() -> dict[str, dict[str, str]]:
    """当前登记的别名（供工具/报告用）。"""
    return {"prefixes": dict(ALIAS_PREFIXES), "renames": dict(ALIAS_RENAMES)}
