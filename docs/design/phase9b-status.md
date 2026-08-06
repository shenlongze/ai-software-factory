# AI Software Factory — Phase 9b: Product Provider Generation

> 日期: 2026-08-06
> 前置: Phase 9a (457bcc4, 3063 tests)
> 目标: Artifact + Provider Intelligence + Human Approval + Experience Loop (生成框架, 非简单内容生成器)

## 范围

- product/ 扩展: generation.py (GeneratedArtifactContext + 生成框架) + experience.py (GenerationExperience)
- Provider 复用: TaskRequirement → CostAwareSelector → Provider Recommendation (禁硬编码)
- 生成类型: Research/PRD/UI (第一阶段只框架, 不复杂 Prompt)
- Event: product.generation.started/completed/failed + product.experience.recorded
- Approval: 生成后等待人工批准 (PRD/UI mandatory 保持)
- 测试: 新增 ≥80, 3063 不回归
- ADR-0027

## 冻结约束

Core 零修改 (只允许 factory-core/product/ 扩展) / Provider 复用 Phase 8 / 禁直接调 LLM
