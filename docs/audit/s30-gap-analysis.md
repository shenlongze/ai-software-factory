# S30 Gap Analysis — Workforce Intelligence & Organization Foundation

> 日期: 2026-08-29 | HEAD: 351a0a4c (v1.1.336)

## EXISTING (S16 复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| ROLE_CAPABILITIES (7 角色能力声明, 非 prompt) | workforce.py:24 | REAL |
| PERMISSION_MATRIX + FORBIDDEN_ACTIONS (权限边界) | workforce.py:47-63 | REAL |
| WORKFORCE_WORKFLOWS (专业流水线顺序) | workforce.py:66 | REAL |
| select_agent (AgentRegistry 按 role 匹配) | workforce.py:115 | REAL |
| create_task / get_tasks (TaskRecord) | workforce.py:140 | REAL |
| workforce_lineage (task→agent→artifact→verification) | workforce.py:174 | REAL |
| AgentEntity (id/role/industry) | session/agent_entity.py:65 | REAL (S1, 无 skills/tools/model) |
| Governance (S17) / ProductionRun / Evaluation | core | REAL |

## MISSING (S30 新增)
| GAP | 最小实现 |
|-----|---------|
| 组织层级 (Organization/Department/Workforce 一等实体 + lineage) | workforce_os.py |
| AgentProfile (正式 identity: capabilities/skills/tools/model/policy binding) | workforce_os.py |
| Workforce Lifecycle (DRAFT→ACTIVE→SUSPENDED→RETIRED, append-only + audit) | workforce_os.py |
| Performance Profile (从 Production Evidence 投影: success/verification/recovery/eval) | workforce_os.py |
| 确定性 Agent Selection (capability match → permission → policy, 非 LLM) | workforce_os.py |
| CLI/API | cli_factory + fastapi_adapter |

## 设计原则
- Workforce 是组织/Agent 层, **不是新事实源** (ProductionRun/Artifact/Verification/Evaluation 仍 SSOT)
- Performance 从真实 Production Evidence 投影 (不造数据)
- Agent 不能修改自身权限/capability/performance/自批准 (复用 S17 边界)

## 禁止
- 第二套 Agent Runtime/Task/Artifact/Experience/Evaluation/Governance/Experiment
- 字符串拼接 Workforce / prompt 代替 Contract / 写死 performance / fake E2E
