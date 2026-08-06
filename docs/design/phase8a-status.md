# AI Software Factory — Phase 8A: LLM Provider Abstraction

> 日期: 2026-08-06
> 前置: Phase 7 (8c198c9, 2310 tests)
> 目标: 解除 Hermes 单一绑定 — Provider = 能力来源之一 (Capability Orchestration)

## 范围

- factory-core/providers/ (models/registry/store/adapters/events)
- ProviderDefinition + ProviderRequest/Response (统一 I/O, 不绑 OpenAI 格式)
- ProviderAdapter 抽象 (generate/chat/stream)
- ProviderRegistry (register/get/list/find_by_capability/default)
- HermesProviderAdapter (与 runtime/adapters/hermes.py 并存)
- CLI: provider list/show/test
- Event: provider.registered/viewed/selected/execution.*
- Dashboard Provider View (默认关)
- 测试: 新增 ≥80, 2310 不回归, 0 Core 修改
- ADR-0022

## 冻结约束

Core 零修改 / Runtime 与 Provider 分离 / Hermes 双角色并存 / 删除 providers 不影响 Factory
