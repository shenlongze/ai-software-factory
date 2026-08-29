# S16 Architecture Proposal — Multi-Agent Professional Workforce

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. AgentEntity (复用 + 冻结)
```
agent_id / role / industry / provider / system_prompt / skills / workflow_ref / tools
```
不新增重复模型; capabilities/permissions 放 workforce 注册表(role 级, 非 per-agent)。

## 2. Role Contract (冻结)
| Role | Capabilities | Permission Boundary |
|------|-------------|---------------------|
| product_manager | discover_product, create_prd, product_decision | 不能改代码/发布 |
| market_analyst | market_research, competitive_analysis | 不能改代码/发布 |
| ux_designer | design_ux, create_artifact | 不能改代码/发布 |
| software_architect | design_architecture, technical_decision | 不能发布 |
| software_developer | implement, repair | 不能 override QA/发布 |
| qa_engineer | verify, test, quality_decision | 不能伪造开发结果 |
| release_engineer | release_prepare, release_verify | 不能绕过 required verification |

## 3. Professional Loop (已有, 冻结)
```
Receive → Retrieve Experience → Decide → Execute → Verify → Artifact → Evidence → Handoff
```

## 4. Handoff Contract (复用, 冻结)
```
handoff_id / from_agent_id / to_agent_id / input_artifacts / created_at / status
```
只传 Artifact refs (无聊天状态)。

## 5. Workforce Orchestration (新增)
```
WorkforceOrchestrator
  - select_agent(role) → AgentEntity (Registry)
  - create_task(role, objective, input_artifacts) → TaskRecord
  - execute(workflow) → 串行 AgentRun + Handoff (复用 run_professional_workflow)
  - enforce_permission(role, action) → 权限边界
  - lineage(run_id) → 全链 (agent/decision/artifact/verification/handoff)
```

## 6. Lineage (扩展)
```
Idea → Task → Agent → Decision → Artifact → Verification → Evidence → Handoff → Next Agent
```
workforce_lineage(run_id) 聚合所有记录。

## 7. CLI/API
```
factory workforce list/agents/runs/status
GET /api/workforce | /api/workforce/agents | /api/workforce/runs/{id} | /api/workforce/lineage
```

## 8. 扩展角色 (Market/UX/Release)
预置 AgentEntity + capability/permission 注册;Release 走 Approval gate (Governance 保留)。

## 9. 禁止
- Central Mega-Agent / self-approve / 绕过 QA / 第二套 Kernel
