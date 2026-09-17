"""infrastructure/config — 配置底座（Config Provider）。

来源: 2026-09-15 自 _pending_migration/factory_console/ 迁入。
· provider.py — ConfigProvider: 进程 env → 项目 .env → ~/.factory/config.json 三级逐 key 合并
  （S10-007 配置独立化: 禁止 Runtime 直接读 Hermes 路径）+ PROVIDER_DEFAULTS 等常量。
"""
