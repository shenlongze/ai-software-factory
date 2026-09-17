"""infrastructure/context — 上下文控制面（Context Control Plane）。

来源: 2026-09-15 自 _pending_migration/factory_console/context_runtime.py 迁入。
· runtime.py — ContextRequest / ContextBudget / ContextResolver（确定性管线:
  scope→permission→policy→retrieval→ranking→budget→snapshot）/ ContextSnapshot /
  ContextDecision + LocalMemoryPlugin（注册到 plugins/kernel, type=memory）。
"""
