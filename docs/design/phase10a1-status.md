# AI Software Factory — Phase 10A-1: Intelligence Layer 基础

> 日期: 2026-08-06
> 前置: Phase 9d (1992388, 3393 tests)
> 目标: 认知层基础 — 模型 + 存储 + 事件 (不实现业务逻辑/LLM/自动执行)

## 架构定位

```
Human Layer → Approval/Decision → Intelligence Layer (认知层, 新增) → Capability → Execution → Core
Intelligence 只读 Core 数据; Core 不感知 Intelligence; 删除后 Factory 正常
```

## 范围

- factory-core/intelligence/ (models/store/events/__init__)
- Decision/Recommendation/ExperienceRecord (五域 + freshness/decay)/Evidence (6 来源)
- 独立空间 .factory/intelligence/ (原子写/隔离/删除 isolation)
- Event: decision.created/recommendation.created/experience.recorded/viewed
- docs/intelligence-layer-model.md + ADR-0030
- 测试: 新增 ≥70, 3393 不回归

## 禁止 (后续 Phase 10A-2~4)

Decision Engine / Recommendation Engine / 自动选择 / LLM 调用 / Experience 学习算法
