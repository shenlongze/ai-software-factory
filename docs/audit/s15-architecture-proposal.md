# S15 Architecture Proposal — Experience-Guided Autonomous Production

> 日期: 2026-08-29 | HEAD: 713d2882 (v1.1.320)

## 1. 可复用 (REAL)
| 能力 | 位置 |
|------|------|
| Experience retrieval (关键词+ranking) | production_experience.retrieve |
| Evaluation (S13) | production_evaluation |
| Repair (S12) | professional_workflow |
| 真实 executor (LLM/Codex/pytest) | build_real_executor_factory |
| Workflow context 注入点 | professional_workflow workflow_input.context |

## 2. GAP (S15 新增)
| GAP | 最小实现 |
|-----|---------|
| role/task_type 增强检索 + relevance score | production_guidance.retrieve_guidance |
| DecisionRecord (experience_ids/decision/reason) | production_guidance.record_decision |
| Experience Usage 追踪 (双向 lineage) | production_guidance.record_usage + get_usage |
| Guidance 注入 professional_workflow | run_professional_workflow(experience_guidance=True) |
| Baseline vs Guided 实验 | scripts/run_baseline_vs_guided.py |

## 3. 架构
```
Experience Registry → retrieve_guidance(role, task) → Guidance[]
  → workflow_input.context["experience_guidance"]
  → Agent (LLM 可见, ACCEPT/REJECT/PARTIAL 决策)
  → ProductionRun → Verification → Evaluation
  → record_usage + record_decision (双向 lineage)
  → extract 新 Experience (反馈闭环)
```

## 4. 安全
- Experience 只是 Guidance (注入 context, 无执行/mutation 权限)
- Agent Decision 仍经 Production Kernel (I8)
- Verification/Repair/Recovery 不被绕过
- No hidden state (只有显式 guidance 输入)

## 5. Scope Firewall
不做: Vector DB/Embedding/Semantic/Prompt 自动进化/Model 选择/Agent code mutation/WebUI
