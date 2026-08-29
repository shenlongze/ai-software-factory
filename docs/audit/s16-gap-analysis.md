# S16 Gap Analysis — Multi-Agent Professional Workforce

> 日期: 2026-08-29 | HEAD: 91ccacac (v1.1.321)

## Existing REAL (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| AgentEntity (id/role/industry/provider/system_prompt/skills/workflow_ref/tools) | session/agent_entity.py | REAL |
| AgentRegistry (add/get/list) | session/agent_registry.py | REAL |
| AgentRun (独立生产 Loop 经 ProductionRun) | agent_kernel.py | REAL |
| Handoff (artifact refs, from/to/input_artifacts) | agent_kernel.create_handoff | REAL |
| Professional Workflow (PM→Arch→Dev→QA) | professional_workflow.py | REAL |
| 真实 executor (LLM/Codex/pytest) | build_real_executor_factory | REAL |
| Repair (S12) / Recovery (S7) / Experience (S14/S15) | 各模块 | REAL |
| 4 专业角色 AgentEntity (S10) | professional_workflow | REAL |

## Missing (S16 新增)
| GAP | 最小实现 |
|-----|---------|
| Role Capability Contract (能力声明, 非 prompt) | workforce.py: ROLE_CAPABILITIES |
| Permission Boundary (每 Agent 权限范围) | workforce.py: ROLE_PERMISSIONS + enforce |
| Workforce Orchestration (role→agent 选择 + task record) | workforce.py: WorkforceOrchestrator |
| 更多角色 (Market Analyst/UX Designer/Release Engineer) | professional_workflow 扩展 AgentEntity |
| Multi-Agent 全链 Lineage API | workforce.py: workforce_lineage |
| CLI/API (workforce list/agents/runs) | cli_factory + fastapi_adapter |

## 设计原则
- Orchestrator 只调度不执行 (Agent 独立 Loop)
- 无 Central Mega-Agent (真多 AgentEntity)
- 权限: PM 不能改代码, Dev 不能 override QA, 无 self-approve
- Handoff 只传 Artifact refs (无聊天状态)
- Governance 保留 (Approval gate 在 Release)

## 禁止
- 第二套 Artifact/Verification/Repair/Recovery/Experience
- Fake autonomy / self-approve / 绕过 QA
