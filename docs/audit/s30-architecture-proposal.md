# S30 Architecture Proposal — Workforce Intelligence & Organization Foundation

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Domain Model (冻结)
```
Organization (org_id/name/departments[])
  └─ Department (dept_id/name/workforces[])
      └─ Workforce (workforce_id/name/status(DRAFT|ACTIVE|SUSPENDED|RETIRED)/agents[])
          └─ AgentProfile (agent_id/role/capabilities[]/skills[]/tools[]/model/provider/policies[])
              ├─ Capability (确定性 Contract: create_prd/implement/verify...)
              ├─ SkillBinding (skill_id/level)
              ├─ ToolBinding (tool_id)
              ├─ ModelBinding (model/provider, 不持有 provider 实现细节)
              └─ PolicyBinding (policy_id)
```

## 2. Lifecycle (冻结)
```
DRAFT → ACTIVE → SUSPENDED ⇄ ACTIVE → RETIRED
append-only history + audit event + invalid transition 拒绝 + flock 并发安全
```

## 3. Performance Profile (冻结, 从 Evidence 投影)
```
agent_id / success_rate / verification_pass_rate / recovery_rate / failure_rate /
avg_duration / evaluation_score / sample_count / evidence_refs[] (真实 ProductionRun)
```

## 4. Deterministic Agent Selection (冻结)
```
Task → RequiredCapability → 候选 (capability match) → permission 检查 → policy
→ availability → 之后才可加 performance/experience ranking
第一版: 确定性选择 (非 LLM)
```

## 5. 边界
- Production Core = SSOT (Workforce 只投影/编排, 不改 Production Truth)
- 复用 S16 ROLE_CAPABILITIES/PERMISSION_MATRIX + S17 governance

## 6. CLI/API
```
factory org create/list | factory workforce create/show/list/status
factory agent list/show/performance | factory capability list
POST /api/organizations | GET /api/organizations
POST /api/workforces | GET /api/workforces/{id} | POST /api/workforces/{id}/status
GET /api/agents | GET /api/agents/{id}/performance
GET /api/capabilities
```
