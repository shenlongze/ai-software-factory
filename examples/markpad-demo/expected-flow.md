# MarkPad Demo — 预期流程 (Phase 13A Demo Productization)

> 输入: `idea.json` (MarkPad 表格编辑器增强) + `requirements.json` (development /
> code,reasoning,generation / 4 条约束)
> 执行: `factory demo markpad` (临时工厂根 + Mock Provider, 生命周期/审批/决策真实)
> 输出: 完整阶段链日志 (每个阶段 Artifact / Event / Decision), `--json` 摘要, 退出码

## 1. 预期生命周期 (software_project 模板, 8 阶段)

```
idea → research → prd → [approval prd] → ui → [approval ui] → architecture → task → experience
```

| # | 阶段 | 类型 | 动作 | 预期产物 / 事件 |
|---|------|------|------|-----------------|
| 1 | idea | artifact_generation | advance | product_idea Artifact (随 idea 创建) |
| 2 | research | artifact_generation | generate (mock) + advance | research Artifact (provider=mock) |
| 3 | prd | artifact_generation | generate (mock) + advance | prd Artifact + 自动审批 APR (mandatory 门) |
| 4 | approval(prd) | approval | decide approve (人工) | Product Decision + 决策链节点 |
| 5 | ui | artifact_generation | generate (mock) + advance | ui Artifact + 自动审批 APR (mandatory 门) |
| 6 | approval(ui) | approval | decide approve (人工) | 决策链继续 |
| 7 | architecture | decision | create architecture + advance | architecture_decision Artifact + DecisionArtifact(architecture) |
| 8 | task | task | advance | task_plan Artifact + DecisionArtifact(task_plan) + Core Task (T-001, workflow=feature-delivery) |

## 2. 预期输出 (每个阶段)

- **Artifact**: id / type / version / status (Lineage: provider_id= mock, confidence)
- **Event**: stage.entered / stage.completed / generation.* / provider.* / approval.* / decision.created
- **Decision**: Product → Architecture → Task Plan 决策链 (3 节点, 类型序稳定)

## 3. 预期汇总

```
lifecycle:  LC-001 software_project → completed
artifacts:  ≥6 (product_idea / research / prd / ui / architecture_decision / task_plan + architecture)
decisions:  3 (product / architecture / task_plan)
tasks:      1 (T-001, workflow=feature-delivery)
approvals:  2 (APR-001 prd approved, APR-002 ui approved)
experience: ≥2 (正向 approved=True + 负向 approved=False)
events:     ≥30 (idea.created → lifecycle.started → stage.* → approval.* → generation.* → task 生成)
```

## 4. 验收标准

- [ ] `factory demo markpad` 退出码 0, 输出 8 阶段日志
- [ ] `factory demo markpad --json` 输出完整 JSON 摘要 (lifecycle/artifacts/decisions/tasks/experiences)
- [ ] 临时工厂根由 tempfile 创建 (不依赖 /tmp 固定路径), 默认退出清理
- [ ] Mock Provider 只生成内容; 生命周期/审批/决策/经验全部真实逻辑
- [ ] Core 零修改 (demo 是调用链, 不是新架构)
