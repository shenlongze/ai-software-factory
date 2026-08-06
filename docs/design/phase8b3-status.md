# AI Software Factory — Phase 8B-3: Provider Execution Intelligence

> 日期: 2026-08-06
> 前置: Phase 8B-2 (6c23628, 2744 tests)
> 目标: Provider = Capability + Cost + Performance + Experience (执行经验层)

## 范围

- Usage 自动接入 Execution 生命周期 (集成层, 不破坏链路)
- Performance 聚合增强 (Declared vs Actual 区分)
- Recommendation 增加历史表现权重 (capability+cost+performance, 只推荐)
- Human Feedback 接口预留 (ProviderFeedback + provider.feedback.created)
- CLI/Dashboard 增强 (stats/recommend 增强)
- docs/provider-intelligence-model.md (Intelligence Loop)
- 测试: 新增 ≥100, 2744 不回归

## 冻结约束

Core 零修改 / providers 独立 / Event 唯一事实源 / Removal Isolation / 不实现支付 / 不自动切换 / 不绑定 OpenAI/Claude
