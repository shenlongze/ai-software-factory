# S10-062 — LLM-Driven Autonomous Planning 架构设计

> 日期:2026-08-15 | Sprint: S10-062 | 架构 (基于 GAP 分析 G1-G9)
> 原则: LLM = Reasoning/Proposal Layer, Deterministic Engine = Enforcement Layer

---

## 1. 架构

```
                    ┌─────────────────────┐
                    │      LLM Planner    │
                    │  understand context │
                    │  analyze gap        │
                    │  propose action     │
                    │  propose task       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Deterministic Gate  │
                    │ schema/role/dup/cycle│
                    │ safety/limits       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ ReplanningEngine    │
                    └──────────┬──────────┘
                               ↓
                         Agent Execution
```

**绝对禁止 LLM 直接**: 修改 DAG / execution state / 绕过 Validator / ConflictResolver / Workspace / Validation / 标记 DELIVERED。

## 2. ContextBuilder (新增 context_builder.py)

```
AutonomousPlanningContext:
  {project, product, requirements, engineering, current_plan, completed_work,
   failed_work, validation, artifacts, workspace, team, capabilities,
   previous_decisions, previous_replans}
  每字段带 source 标识 (PRD.md/execution_state.json/validation_result.json)
  token budget 控制 (估算 + 裁剪)
```

## 3. ReasoningProvider (新增 reasoning.py)

```
class ReasoningProvider:
  analyze_gap(context) -> dict (结构化 GapAnalysis)
  propose_task(gap, context) -> dict (结构化 TaskProposal)
  evaluate_plan(context) -> dict (ReplanDecision)
  不硬编码模型: 复用 LLMControlPlane (DeepSeek/anthropic/本地)
  结构化输出: JSON extraction → schema validation → deterministic validation
```

## 4. LLMGapAnalyzer (增强 gap_analyzer.py)

```
输入: AutonomousPlanningContext + TaskContext
输出: GapAnalysis (schema 化, 与 S10-061 同结构)
fallback: LLM 失败 → deterministic GapAnalyzer → REQUEST_REVIEW
Evidence First: 判断引用 evidence {source, field, observation}
```

## 5. LLMTaskProposalEngine (增强 task_proposal.py)

```
输入: GapAnalysis + PRD + Engineering + DAG + existing + workspace + capabilities
输出: TaskProposal (title/description/objective/required_role/dependencies/
      acceptance_criteria/validation_command/priority/rationale/confidence/source_gap)
必须解释: WHY (解决 GAP) / HOW (验证完成) / DEPENDENCY (依赖原因)
fallback: LLM 失败 → deterministic TaskProposalEngine
```

## 6. PlanCritic (新增 plan_critic.py)

```
执行前检查计划缺口:
  输入: plan + PRD + engineering + capabilities
  输出: GapAnalysis (deployment missing 等)
  不直接修改 DAG → 走 GapAnalyzer → TaskProposal → Validator → ReplanningEngine
```

## 7. Deterministic Gate (复用)

```
TaskProposalValidator 12 项 / DuplicateDetector / DAG cycle / ConflictResolver /
AgentMatcher / limits — LLM 输出必须过同一 Gate
```

## 8. Fallback 链

```
LLM mode: LLM → Validator → Proposal
失败 (API error/timeout/invalid JSON/schema error/confidence 低/proposal 非法):
  → Deterministic Analyzer → Validator → Proposal
再失败: → REQUEST_REVIEW
不能因 LLM 挂了导致系统不可用
```

## 9. planning_trace.json

```
记录: provider/model/operation/input_context_hash/output/parsed_result/
      confidence/token_usage/latency/fallback_used/validation_result/final_decision
不记录 API key / 敏感信息
用途: debug/audit/cost analysis/future learning
```

## 10. cost/token 追踪

```
每次 LLM planning 调用: input_tokens/output_tokens/total_tokens/latency/estimated_cost
复用 AgentRuntime usage 结构 + execution_records 模式
Pilot 报告: Planning LLM cost + Agent execution cost + Total cost
```

## 11. planning_mode

```
deterministic: 现有行为 (S10-061 兼容)
llm: LLM 优先 (fallback deterministic)
hybrid: LLM 优先 + deterministic fallback (推荐默认)
```

## 12. 安全边界

```
REQUEST_REVIEW: destructive architecture / 删核心功能 / 大规模 DAG mutation /
confidence < 阈值 / 连续重复任务 / validation 连续失败 / replan 超限 / cost 超预算 /
不确定 required_role / 不确定 acceptance_criteria
```

## 13. 模块计划

```
新增: session/context_builder.py + reasoning.py + plan_critic.py
修改: session/gap_analyzer.py (+LLM) + task_proposal.py (+LLM) +
      replanning.py (planning_mode) + orchestrator.py (接入)
测试: test_session_llm_gap_analysis.py / test_session_llm_task_proposal.py /
      test_session_planning_context.py / test_session_plan_critic.py /
      test_session_planning_fallback.py (合计 >=120)
```

## 14. 真实 Pilot

```
ScorePocket: 初始计划 PM/Architect/Backend/Frontend/QA (缺持久化)
→ PRD/Engineering 含持久化要求 → PlanCritic/LLMGapAnalyzer 发现缺口
→ LLMTaskProposalEngine 生成 T006 (真实 LLM, 非测试注入)
→ Validator → DAG → AgentMatcher → 真实执行 → pytest → DELIVERED
```

## 15. 边界

- 不破坏 S10-054~061 (deterministic mode 仍工作)
- 不重建 provider 系统 (复用 LLMControlPlane)
- 模型名不硬编码 (ReasoningProvider 抽象)

---

> 架构完毕 | ContextBuilder + ReasoningProvider + LLM Gap/Proposal + PlanCritic + fallback + trace + cost
