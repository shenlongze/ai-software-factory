# AI Software Factory — Phase 9c: Human Decision Intelligence

> 日期: 2026-08-06
> 前置: Phase 9b (35bb150, 3148 tests)
> 目标: 通用人工决策系统 (非简单 approve/reject; 为 PRD/UI/Deploy/Operation 复用)

## 范围

- Approval Decision State Machine (pending/approved/rejected/changes_requested/delegated)
- Artifact Version Integration (approval 绑定 version, 禁覆盖历史)
- ApprovalExperience (optimization 数据接口)
- Approval Queue (待审核列表)
- Workflow Pause/Resume (PAUSED → approved → resume; rejected → 修改/终止)
- Event: approval.created/pending/approved/rejected/changes_requested/resumed
- Dashboard Product Approval View
- 测试: 新增 ≥100, 3148 不回归
- ADR-0028

## 冻结约束

Core 零修改 / Extension only / Event 唯一事实源 / Artifact lineage / Provider Intelligence 复用
