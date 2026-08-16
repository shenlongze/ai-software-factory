# S10-062 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-062 | P0 现状审查
> 审查方式: 读取真实代码 (gap_analyzer/task_proposal/replanning/orchestrator/agents/roles/dependencies/quality/exec/llm_control)

---

## 核心问题回答

### 1. 当前哪些决策是 deterministic?
```
全部: GapAnalyzer (信号词匹配) / TaskProposalEngine (规则模板) /
ReplanningEngine (8 决策规则) / Validator (12 项检查) / DuplicateDetector /
ConflictResolver / DAG cycle 保护 — 100% deterministic (S10-061 完成)
```

### 2. 哪些地方已经使用 LLM?
```
AgentRuntime (factory-exec/exec/agent_runtime.py): execute_task → DeepSeek/
anthropic (LLMControlPlane 选 provider) → patch 产物
→ session 层决策 (gap/task/replan) 全部 deterministic, 无 LLM
```

### 3. 当前 Agent 能看到多少项目上下文?
```
execute_fn(task, project_dir, workspace) + task["context"] (S10-057):
  {project, completed_tasks, artifacts, messages, decisions, previous_decisions}
→ 有基础上下文, 但无结构化项目画像 (PRD/engineering/requirements)
```

### 4. 如何安全地把上下文交给 LLM?
```
❌ 无 ContextBuilder — 无 token budget / 来源标识 / 信息裁剪
→ S10-062 核心: 构建 AutonomousPlanningContext (来源标识 + token 控制)
```

### 5/6. 当前 LLM 调用成本 / token usage 如何记录?
```
AgentRuntime: usage=output.usage → execution_records.json (agent 执行)
→ session 层 planning 调用无 cost 追踪 (新增)
```

### 7. 当前模型失败如何 fallback?
```
LLMControlPlane: provider 失败 → 回退 anthropic (exec.cli 层)
→ session 层 planning 无 fallback (新增: LLM → deterministic → REQUEST_REVIEW)
```

### 8/9/10/11. 防止 LLM 非法 Task / 重复 / 改已完成 / 绕 Validation?
```
S10-061 Validator (12 项) + DuplicateDetector + DAG cycle 已存在 (deterministic 门)
→ LLM 输出必须过同一 Gate — 架构原则: LLM=建议, Deterministic=执行
```

### 12. LLM 只负责"建议", deterministic 负责"执行约束"?
```
❌ 当前无 LLM 层 — S10-062 核心架构: LLM Planner → Deterministic Gate → ReplanningEngine
```

---

## GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **LLM Gap Analyzer** | GapAnalyzer 纯信号词, 无 LLM reasoning |
| G2 | **LLM Task Proposal** | TaskProposalEngine 纯模板, 无 LLM 生成 (WHY/HOW/DEPENDENCY) |
| G3 | **ContextBuilder** | 无结构化项目上下文 (PRD/engineering/requirements + token budget + 来源标识) |
| G4 | **ReasoningProvider** | 无统一 LLM 抽象 (analyze_gap/propose_task/evaluate_plan; 模型不硬编码) |
| G5 | **PlanCritic** | 无执行前计划缺口检查 |
| G6 | **planning_trace.json** | 无 LLM 决策追踪 (provider/model/input_hash/output/tokens/latency/fallback) |
| G7 | **cost/token 追踪** | session 层 planning 调用无 cost 记录 |
| G8 | **fallback 链** | 无 LLM→deterministic→REQUEST_REVIEW |
| G9 | **planning_mode** | 无 deterministic/llm/hybrid 模式切换 |

## 可复用 ✅

| 能力 | 复用方式 |
|---|---|
| GapAnalyzer (deterministic) | LLM fallback 基础 |
| TaskProposalEngine/Validator/DuplicateDetector | LLM 输出 deterministic Gate |
| ReplanDecision (8 决策) | LLM PLAN_EVALUATION 输出复用 |
| ReplanningEngine + _insert_tasks | 执行层不变 |
| TaskDependencyGraph/ConflictResolver/AgentMatcher | 执行约束不变 |
| LLMControlPlane (factory-console/llm_control.py) | provider 选择复用 (不重建 provider 系统) |
| AgentRuntime usage 记录 | cost 结构复用 |
| execution_records.json | cost 资产复用 |

## 架构设计方向

```
                    ┌─────────────────────┐
                    │      LLM Planner    │  (G4 ReasoningProvider)
                    │  understand context │
                    │  analyze gap        │
                    │  propose action     │
                    │  propose task       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Deterministic Gate  │  (复用 S10-061 Validator/Duplicate/Cycle)
                    │ schema/role/dup/cycle│
                    │ safety/limits       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ ReplanningEngine    │  (S10-060 不变)
                    └──────────┬──────────┘
                               ↓
                         Agent Execution   (AgentRuntime 不变)

模块:
  context_builder.py   — AutonomousPlanningContext (G3)
  reasoning.py         — ReasoningProvider + LLMGapAnalyzer + LLMTaskProposalEngine (G1/G2/G4)
  plan_critic.py       — PlanCritic (G5)
  planning_trace.py    — planning_trace.json (G6)
  replanning.py/orchestrator.py — planning_mode (G9) + fallback (G8) + cost (G7)
```

## 不该现在做 🚫

- 不重建 provider 系统 (复用 LLMControlPlane)
- 不硬编码模型名 (ReasoningProvider 抽象)
- 不做 PyPI/marketing/UI/SaaS/并行 DAG
- 不破坏 S10-054~061 任何能力

---

> GAP 完毕 | G1-G9 缺失 | 复用充分 | 架构原则: LLM=Reasoning, Deterministic=Enforcement
