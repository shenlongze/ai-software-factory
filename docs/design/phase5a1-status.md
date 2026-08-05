# AI Software Factory — Phase 5A.1: Runtime Catalog

> 日期: 2026-08-06
> 前置: Phase 1-5A (1237 tests)
> 目标: Runtime 能力描述层 (Catalog != Registry != Runtime)

## 范围

- factory-core/runtimes/ (models/catalog/store/definitions)
- RuntimeDefinition (id/name/type/description/capabilities/supported_tasks/version/status/metadata)
- RuntimeCatalog (register/get/list/remove/find_by_capability)
- 默认定义: hermes/echo/mock (只描述不执行)
- 持久化 (原子写)
- Registry 集成 (通过 catalog 查 definition, 不复制)
- CLI: runtime catalog list/show
- Event: runtime.catalog.registered/removed/viewed
- Dashboard: Runtime Catalog View
- 测试: 新增 ≥40, 1237 不回归

## 边界

Catalog=能力描述, Registry=实例可用状态, Runtime=执行器 — 三者分离
禁止: 修改 RuntimeAdapter/ExecutionRunner/Hermes Adapter / 合并 Registry / 数据库

## 注意

现有 runtime store 用 .factory/runtimes/runtimes.json (存实例+executions) — catalog 需独立文件 (如 catalog.json) 避免冲突
