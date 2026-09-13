"""旧代码围栏的**单一来源**：分区名单与允许的顶层目录。

为什么单独一个文件：这份常量原先在「工具」与「围栏测试」里各有一份拷贝，
改了一处忘另一处 → 测试算出的跨分区边与基线对不上（刀22 实际踩到）。
围栏这类东西的两份定义必然漂移，所以抽出来共用。
"""
from __future__ import annotations

#: 被绞杀对象（旧代码分区）。已归零并移出的：
#:   kernel（刀13）· services（刀20）· demo（刀22，迁入 examples/demo/）
#: 移出后若有人重建，R16 会直接拦下（ADR-0037：根下不应存在它们）。
LEGACY_ROOTS = (
    "factory-console",
    "factory-core",
    "factory-exec",
    "factory-org",
    "factory-runtime",
    "factory_console",
)

#: 允许出现在根下的顶层代码目录（其余一律 R16 拦下）。
#: examples/ 允许有代码：它既放工厂定义（project.yaml），也放示例仓库（demo/repo）。
ALLOWED_TOP: set[str] = set(LEGACY_ROOTS) | {
    "src", "tests", "scripts", "docs", "bin", "apps", "examples",
}
