# AI Software Factory — Phase 8B-1: Provider Selection + Execution Integration

> 日期: 2026-08-06
> 前置: Phase 8A (722edf8, 2460 tests)
> 目标: 将 Provider 真正接入 Execution 流程 (选择 + 审计, 不实现 OpenAI/Claude Adapter)

## 范围

- providers/selector.py: ProviderSelector (优先级链 Project > Agent > Runtime > Default)
- providers/config.py 增强: runtime_preferences.provider 解析
- CLI 集成: execution run --provider (显式) + 项目配置 → provider.selected 事件
- Orchestration 集成: execute_workflow 装配时经 context 传递 (Phase 6E executor 注入模式)
- 事件: provider.selected + execution 关联审计
- 测试: 新增 ≥80, 2460 不回归
- ADR-0023

## 冻结约束

Core 零修改 (ExecutionRunner/WorkflowEngine 不动; ExecutionRequest.input dict 携带 provider_id, 不改模型)
Runtime/Provider 边界保持; Hermes 旧链路兼容 (无 provider 配置行为不变)
