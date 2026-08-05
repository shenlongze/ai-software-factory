# AI Software Factory Framework — 设计任务

> 日期: 2026-08-04
> 状态: Architecture Analysis Phase (不修改业务代码)
> 目标: 将 Hermes + MarkPad 流程抽象为可迁移的 AI Software Factory Runtime

## 素材来源 (本会话实证经验)

- MarkPad 全周期: 重构 (A1-A5) → 稳定 (LIFECYCLE) → 功能 (Smart Input/Table/Backspace/Link/AutoPair) → Alpha 发布 → Bug 修复
- 模式: Orchestrator 委派 / 多角色 Agent / Skill 系统 / 双验证 / Decision Gate / Sprint / 用户验收
- 约 55 个 sub-agent 实例, 8 大交付, 全部双验证

## 产出

docs/ai-software-factory/
- architecture.md / agent-model.md / skill-model.md / workflow-model.md
- validation-model.md / memory-model.md / runtime-design.md / migration-plan.md

## 原则

- Agent = 员工, Workflow = 生产流程, Knowledge = 经验资产
- Validation = 质量体系, Orchestrator = 管理层
- 不绑定具体工具/模型, 逐步演进不推翻 Hermes
