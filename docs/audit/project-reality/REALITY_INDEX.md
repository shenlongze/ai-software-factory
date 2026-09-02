# REALITY INDEX (2026-09-02, STEP 8)
> 未来 AI 进入项目先读此索引。按 Domain → Capability → Contract → Evidence → Document

## 进入顺序
1. PROJECT_PROGRESS_SNAPSHOT.md (1 页全貌)
2. AI_FACTORY_PROJECT_REALITY_REPORT.md (26 节详述)
3. MASTER_STATUS_TABLE.md (29 能力基准表)
4. docs/audit/fact-discovery/ (STEP 1-5 事实+证据)
5. docs/audit/capability-maturity/ (STEP 7 评分)

## Domain 索引
| Domain | Capability | Contract | 证据文档 |
|--------|-----------|----------|----------|
| Session | 会话/意图 | execution-truth-contract | fact-discovery/SYSTEM_TRUTH_MAP |
| Requirement | 捕获 | agent_loop:795 | fact-discovery/REQUIREMENT_GAPS |
| PRD | 实体 | (ABSENT, M3) | fact-discovery/PRD_GAPS |
| Planning | 计划闭环 | orchestration-contract §24 | capability-maturity |
| Task | 八态+依赖 | management.py | fact-discovery/DATA_LINEAGE |
| Execution | 会话链 M4 | orchestration-recovery-contract | capability-maturity |
| Agent | router 选择 | gateway.py:18 | fact-discovery/AGENT_CONTROL |
| LLM | llm_fn 注入 | console_sessions:104 | fact-discovery/LLM_CONTROL |
| Model | 选择 (M1) | llm_router (消费 0) | fact-discovery/LLM_CONTROL_GAPS |
| Audit | 5160 事件 | audit_events | fact-discovery/SYSTEM_TRUTH_MAP |
| Learning | FUTURE | M4 承诺 L411 | 方案书 L411 |
| Release | FUTURE | — | — |

## 关键 Contract 文件
- docs/architecture/orchestration-contract.md (§24 Plan Closure)
- docs/architecture/orchestration-recovery-contract.md
- docs/architecture/data-governance.md (8 条宪法)
- 方案书 "AI Software Factory — 完整产品方案书.md" (27 原则源)
