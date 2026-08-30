# Intelligence Plane (S42)

> 日期: 2026-08-29 | 冻结于 S42

## 1. 统一架构
```
Intelligence Plane
    └── IntelligenceStrategy (统一 Contract)
        ├── LearningStrategy (S37: Observation→Candidate→Evaluation→[STOP])
        ├── HealingStrategy (S39: Incident→Repair→S38→Recover)
        ├── OptimizationStrategy (S40: Opportunity→Candidate→S38→Promote)
        └── Future Strategies (同一 Contract 扩展)
        ↓
    Shared Pipeline (S38, 只有一套):
        Candidate → Evaluation → Experiment → Comparison → Governance → Canary → Promotion
```

## 2. 关键原则
- 不增加新 Loop; 把已有 Loop 统一为可扩展 Strategy Architecture
- 注册经 S31 Plugin Kernel (type=strategy) — 唯一 Registry
- Strategy 不得绕过 Core Governance / 直接改 Production
- 版本进 lineage (历史可解释)
- Learning 例外: [STOP] 语义 (S37 设计)
