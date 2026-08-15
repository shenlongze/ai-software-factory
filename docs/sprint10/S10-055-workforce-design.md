# S10-055 — Agent Workforce Intelligence 设计

> 日期:2026-08-15 | Sprint: S10-055 (第二阶段) | Task 001-007 设计
> 目标: 让 AI Factory 从"任务执行器"升级为"AI 软件团队管理系统"

---

## 1. Phase 0 — 现状分析

### 已有资产
```
agents.json (~/.factory/agents/)   backend-1/flutter-dev/tester-1 (role/skills/status)
execution_records.json            18 条真实执行记录 (agent/result/cost)
select_agent()                    关键词硬编码 (前端→flutter-dev/其余→backend-1)
ExecutionOrchestrator             任务级执行 + feature 级视角 (S10-055 一阶段)
```

### 缺口
```
G1: Agent 选择是关键词硬编码, 无 Registry 2.0 (capabilities/supported_tasks/cost_profile)
G2: 无 AgentMatcher (skill 匹配/历史成功率/成本 综合决策)
G3: 无 agent_metrics.json (绩效追踪)
G4: execution_plan.json 无 agent reasoning (可解释调度)
G5: 无 Workforce Dashboard ("查看团队")
G6: Conversation 不能回答 "谁负责这个任务/为什么选这个 Agent"
G7: 审计无 Production Trace (Project→Feature→Task→Agent→Execution→Artifact→Validation→Cost)
```

---

## 2. 架构

```
Agent Registry 2.0 (agent.json)
    ↓
AgentMatcher (task → best agent: skill 匹配 + 历史成功率 + 成本)
    ↓
Agent Performance Tracking (agent_metrics.json, 从 execution_records 聚合)
    ↓
Execution Plan + Reasoning (execution_plan.json: agent + reason)
    ↓
Workforce Dashboard ("查看团队" → 团队状态)
    ↓
Conversation (谁负责/为什么选择 → Project Context + Execution State + Registry)
    ↓
Production Trace (完整生产审计)
```

## 3. 数据模型

### Agent Registry 2.0 (agents.json 扩展)
```json
{
  "backend-1": {
    "id": "backend-1", "name": "backend-1",
    "role": "Backend Engineer",
    "skills": ["python", "api", "database"],
    "supported_tasks": ["backend_api", "database_schema", "test"],
    "cost_profile": {"avg_cost": 1000, "cost_unit": "tokens"},
    "status": "available", "current_task": null
  }
}
```

### AgentMatcher
```
输入: Task {type, description, required_skills}
输出: {agent, score, reason}
评分: skill 匹配 (必备技能命中率) × 历史成功率 × (1/成本归一化)
无硬编码关键词 — 基于 Registry skills + execution_records 真实数据
```

### agent_metrics.json
```json
{
  "backend-1": {
    "agent": "backend-1",
    "total_tasks": 10, "success_count": 9, "failed_count": 1,
    "avg_cost": 1050, "avg_duration": 12.5,
    "success_rate": 0.9,
    "by_task_type": {"backend_api": {"total": 5, "success": 5}}
  }
}
```

### Execution Plan + Reasoning
```json
{"task": "实现API", "agent": "backend-1", "reason": "skill match 92% (python/api/database), 成功率 95%"}
```

## 4. 模块计划

```
factory-console/session/
  agents.py        (新增: AgentRegistry 2.0 + AgentMatcher + AgentMetrics)
  actions.py       (修改: select_agent → 走 AgentMatcher; +workforce action)
  intent.py/router.py (修改: +workforce 关键词 "查看团队")
  audit.py         (修改: +production_trace)
tests/console/
  test_session_agents.py (新增, >=100 测试)
docs/sprint10/S10-055-agent-workforce-intelligence.md
```

## 5. 执行流程

```
用户: "查看团队" → workforce intent → AgentRegistry.list + AgentMetrics → 团队状态
用户: "谁负责这个任务?" → Conversation → Execution State 最近任务 → Agent
用户: "为什么选择 backend-1?" → Execution Plan reason → 可解释
```

## 6. 边界

- 不重构已有 Pipeline (select_agent 兼容保留)
- 复用 agents.json + execution_records (不造新数据源)
- 真实数据驱动 (metrics 来自真实执行)
- Core 零改动

---

> 设计完毕 | Registry 2.0 + Matcher + Metrics + Reasoning + Dashboard + Trace
