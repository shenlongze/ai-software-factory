"""旧代码隔离区与围栏的**单一来源**。

刀23 后布局（ADR-0037 方案 C 的收尾）：
    src/ai_factory_os/     新地基（受 R1–R17 约束）
    src/legacy/            隔离区（受"只减不增"约束）
      ├── factory-console/ ← 包名 factory_console（PYTHONPATH 提供）
      ├── factory-core/    ← sys.path 根: tasks / runtime / events / store / models ...
      ├── factory-exec/    ← 包名 exec
      ├── factory-org/     ← 包名 org
      (factory-runtime 已于刀27 迁入 src/ai_factory_os/infrastructure/process/)
      ├── factory_console/ ← 连字符目录名的转发壳
      └── repo_paths.py    ← 仓库根唯一计算器（被 legacy 代码共用）

常量原先在「工具」与「围栏测试」各有一份拷贝，改一处忘另一处就漂移（刀22 踩过）。
故集中在此，工具与围栏测试共用。
"""
from __future__ import annotations

#: 隔离区位置（相对仓库根）
LEGACY_PARTS: tuple[str, ...] = ("src", "legacy")

#: 隔离区内的分区（= src/legacy/ 下的一级目录名，用于跨分区边统计）
PARTITIONS: tuple[str, ...] = (
    "factory-console",
    "factory-core",
    "factory-exec",
    "factory-org",
    "factory_console",
)

#: 允许出现在根下的顶层目录。**根下不得出现任何 factory-***（ADR-0037 判定标准）。
ALLOWED_TOP: set[str] = {"src", "tests", "scripts", "docs", "bin", "apps", "examples"}

#: src/ 下只允许这两个：新地基 + 隔离区（防再长出第三个）
ALLOWED_UNDER_SRC: set[str] = {"ai_factory_os", "legacy"}

#: 已迁出隔离区、但仍被【非 Python 消费者】按名字引用的标识符。
#: 例: factory-runtime 刀27 迁入 src/ai_factory_os/infrastructure/process/，
#: 但桌面仍以 `factory-runtime` 这个 CLI 名调用它（Rust 子进程）——
#: 纯 import 分析永远看不见这类引用，故单独列出供名称扫描。
EXTERNAL_ONLY_NAMES: tuple[str, ...] = ("factory-runtime",)

#: legacy 代码对外暴露的顶层包名（新地基 R13 不得 import 它们）。
#: tasks/runtime/events/... 来自 src/legacy/factory-core（sys.path 根）；
#: exec/org 来自 package-dir 映射；factory_console 来自连字符目录转发壳。
LEGACY_TOP_NAMES: frozenset[str] = frozenset({
    # factory-core 顶层子包（sys.path 根暴露）
    "agents", "assignment", "change", "changeflow", "cli", "dashboard", "demo",
    "events", "execution", "git", "intelligence", "metrics", "orchestration",
    "product", "providers", "recovery", "runtime", "runtimes", "tasks",
    "understanding", "validation", "workflows", "workspace",
    # 映射包
    "exec", "org",
})
