# S10-062 — LLM-Driven Autonomous Planning & Semantic Gap Intelligence

> 日期:2026-08-15 | Sprint: S10-062 | LLM Autonomous Planning
> 状态: AI 真正理解软件生产上下文并自主规划下一步

---

## 1. 为什么 S10-061 不够

S10-061 的 GapAnalyzer/TaskProposal 纯 deterministic(信号词/模板)——AI 决定"如何重规划"但不理解"为什么"。S10-062 让 LLM 理解项目上下文、分析缺口语义、提出带 WHY/HOW/DEPENDENCY 解释的任务。

## 2. 架构原则

```
LLM = Reasoning/Proposal Layer (建议)
Deterministic Engine = Enforcement Layer (执行约束)
LLM 绝不直接: 修改 DAG / execution state / 绕过 Validator / 标记 DELIVERED
```

## 3. 新能力

| 能力 | 说明 |
|---|---|
| ContextBuilder | AutonomousPlanningContext (14 字段 + source 标识 + token budget + evidence 提取) |
| ReasoningProvider | analyze_gap/propose_task/evaluate_plan; 模型不硬编码 (LLMControlPlane); llm_fn 可注入 |
| LLMGapAnalyzer | LLM 优先 → 结构化 GapAnalysis → fallback deterministic → REQUEST_REVIEW |
| LLMTaskProposalEngine | LLM 生成 TaskProposal (WHY/HOW/DEPENDENCY) → Validator 12 项 gate → fallback |
| PlanCritic | 执行前检查计划缺口 (只输出, 不改 DAG) |
| planning_mode | deterministic / llm / hybrid (缺省 hybrid, 安全回退) |
| PlanningTrace | planning_trace.json (provider/model/tokens/latency/fallback_used; 脱敏) |
| Fallback 链 | LLM → deterministic → REQUEST_REVIEW (LLM 挂不影响系统) |
| 安全边界 | auto_mode/confidence 阈值/连续重复检测/超限 REQUEST_REVIEW |

## 4. 真实 LLM 验证 (DeepSeek, 无 mock)

```
=== 1. LLM Gap 分析 (1.9s) ===
detected=True | type=validation_failure | confidence=0.95
reason: "持久化验证失败,需要修复实现或测试以符合要求"
(LLM 理解: validation 失败 + 持久化需求 → 语义缺口判断)

=== 2. LLM 任务提案 (2.9s) ===
title: "修复比赛记录持久化验证失败"
required_role: backend
objective: "修复持久化相关代码或测试,使持久化验证通过"
acceptance_criteria: ["持久化测试通过", "pytest 成功"]
validation_command: pytest
WHY: "该任务直接处理当前验证失败,解决数据未正确保存的问题"
source: llm | fallback: False  ← 纯 LLM 生成, 非 deterministic 兜底
```

## 5. 测试

```
批次 A: planning_context + plan_critic = 122 passed
批次 B: llm_gap + llm_task_proposal + planning_fallback = 116 passed
批次 C: llm_planning_integration = 30 passed
合计: 268 新测试 (>=120 目标达成)
全量: 10422 passed + 1 skipped, 0 failed (10154 基线 → +268, 零回归)
```

## 6. 回答完成标准

| 标准 | 状态 |
|---|---|
| LLM 理解项目上下文 | ✅ ContextBuilder |
| GapAnalyzer 支持 LLM reasoning | ✅ LLMGapAnalyzer |
| TaskProposal 支持 LLM reasoning | ✅ LLMTaskProposalEngine |
| PlanCritic | ✅ |
| Evidence 可追踪 | ✅ source 标识 + evidence |
| LLM 输出结构化 | ✅ schema 校验 |
| deterministic validation/fallback | ✅ Validator + fallback 链 |
| duplicate/cycle/confidence/REQUEST_REVIEW | ✅ |
| planning trace | ✅ planning_trace.json |
| token/cost/latency tracking | ✅ trace 记录 |
| 真实 LLM Pilot | ✅ DeepSeek × 2 (gap + proposal) |
| 新任务来自 LLM proposal | ✅ source=llm, fallback=False |
| >=120 新测试 | ✅ 268 |
| 全量 0 failed | ✅ 10422 |

## 7. 技术债

- LLM 调用成本无单独 budget 上限(复用 max_replan)
- PlanCritic LLM 模式 (deterministic 已完成)
- REQUEST_REVIEW 无人工审批 UI
- Trace 无 token 精确计量 (fixture 为空)

## 8. 下一 Sprint 建议

```
S10-063 — 发布行动 (终极叙事就绪)
  "用户一句话 → AI 理解需求 → 设计 → 团队 → 执行 → 观察 → 语义理解缺口
   → LLM 自动提案 → 分配 → 执行 → 交付"
- 或 S10-063: LLM cost budget + PlanCritic LLM 模式
```

---

> S10-062 文档完毕 | LLM-Driven Autonomous Planning | 268 新测试 | 10422 全绿
