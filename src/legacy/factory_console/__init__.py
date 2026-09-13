"""factory_console — 统一 CLI 入口的可导入别名包 (S10-031 Task 2)。

真实实现位于 factory-console/ 目录 (名称含连字符, 无法作为生成式
console script 的 `from <module> import <attr>` 目标)。本包仅做
importlib 转发, 不包含任何业务逻辑。
"""
