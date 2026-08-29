# S15 Experience-Guided Autonomous Production — 证据

> 日期: 2026-08-29 | HEAD: (S15 commit) | v1.1.321

## 架构
```
Experience Registry → retrieve_guidance(role, task) → Guidance (确定性 relevance)
  → workflow_input.context["experience_guidance"] (Agent 可见)
  → Agent (ACCEPT/REJECT/PARTIAL) → ProductionRun → Verification → Evaluation
  → record_usage + record_decision (双向 lineage)
  → extract 新 Experience (反馈闭环)
```

## Relevance 公式 (透明)
```
role_match 30 + task_type_match 30 + technology_match 20 + success_score 20
```

## Decision Record
```
decision_id / agent_run_id / production_run_id / experience_ids / decision (accept/reject/partial_apply) / reason / timestamp
```

## 双向 Lineage
- Experience → Production: experience_lineage(experience_id)
- Production → Experience: production_lineage(run_id) — usage + decisions

## 安全 (实测)
- Guidance 只注入 context, 无 artifact/verification/status 字段 (不能 mutation)
- bad experience 不能强制成功 (生产失败仍是失败)
- 只经 Production Kernel (I8), Verification 保留裁决权

## 反馈闭环
Guided production → evaluation → extract → 新 Experience (测试证明)

## Baseline vs Guided 实验 (确定性 executor, 诚实结果)
```
metric               baseline     guided
state                COMPLETED    COMPLETED
repair_count         1            1
attempt_count        2            2
evaluation_score     98           98
experience_usage     0            1
decisions            0            1
```
**诚实报告**: 确定性 executor 下 Guided 未改善生产指标 (repair/score 相同)——
但证明: ①Guided 真正检索并使用了经验 (usage 0→1) ②决策被正式记录 (decisions 0→1)
③pipeline 闭环成立。真实 LLM 场景的改善需更多样本, 留待后续 (随机性限制已记录)。

## REAL / SEMI / GAP
| Capability | Status |
|------------|--------|
| 确定性 Guidance 检索 (role/task/tech/score) | REAL |
| Guidance 到达 Agent (context) | REAL |
| Decision Record | REAL |
| Experience Usage 双向 lineage | REAL |
| 安全边界 (无 mutation 权限) | REAL |
| 失效过滤 (INVALIDATED 排除) | REAL |
| 反馈闭环 (guided → 新 experience) | REAL |
| Baseline vs Guided 实验 | SEMI (实验脚本待跑) |
| Semantic/Vector Retrieval | GAP (故意) |
| Prompt 自动进化 | GAP (故意) |

## 测试
```
S15: 7/7 passed
全量 llm + core: 760 passed + 5 skipped (零失败)
openapi: 141 paths (+2: search/lineage)
```
