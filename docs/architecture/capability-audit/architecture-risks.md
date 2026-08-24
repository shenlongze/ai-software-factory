# Architecture Risks

> 证据: 代码扫描 (2026-08-17)。Probability: 高/中/低 | Severity: 高/中/低

| # | Risk | Evidence | Impact | Prob | Sev | Recommendation |
|---|---|---|---|---|---|---|
| R1 | **Retrieval 未统一** | RetrievalOrchestrator 仅测试使用; Debug/Product 各自检索 | 多 RAG 冲突/重复检索 | 高 | 高 | 生产 LLM 调用统一经 Orchestrator |
| R2 | **Context Budget 未执行** | ContextLedger 仅定义, LLM 调用绕过 | Context 无限增长/Cost 爆炸 | 高 | 高 | LLM 调用统一 check() |
| R3 | **Debug 执行桩化** | execute_fn 默认确定性桩 | 修复能力是模拟 | 高 | 高 | RepairManager 真实桥接 |
| R4 | **Audit 覆盖缺口** | 仅 5 action 自动 emit; orchestrator 未接 | 无法回答执行审计 | 高 | 中 | 全链接入 AuditEmitter |
| R5 | **Memory 非自动** | AutoLearner 未接 execute_project | 经验沉淀靠手动 | 中 | 中 | 生产钩子 |
| R6 | **Mock-only 测试** | 105 测试文件含 mock/patch; Debug 验证注入 | Test Illusion | 中 | 中 | 真实 pytest E2E |
| R7 | **无部署能力** | 生产止于 DELIVERED | 不能交付可运行软件 | 中 | 高 | 最小部署层 |
| R8 | **单一存储** | 全 JSON (audit/memory/debug/state) | 规模增长瓶颈 | 中 | 中 | Store 接口化迁移 |
| R9 | **多项目隔离** | workspace 优先, 无显式项目 Memory 隔离 | 经验污染 | 中 | 中 | project_id 全链过滤 |
| R10 | **LLM 依赖** | 真实能力依赖 DeepSeek; fallback 规则兜底 | Provider 故障 | 中 | 中 | fallback 链已验证 (S10-062) |
| R11 | **状态分散** | lifecycle/execution_state/governance 三处 | 状态不一致 | 中 | 中 | UserLifecycle 映射层 (S10-065) |
| R12 | **无经验衰减** | confidence 静态 | 过期经验误导 | 中 | 低 | 时间衰减 |
| R13 | **无 IAM** | 全 user 权限 | 企业安全缺口 | 高 | 高 | RBAC (Audit 模型预留) |
| R14 | **Secret 防护** | Audit 脱敏✅; 但 execution_records 原始 error 可能含 key | 泄漏风险 | 低 | 高 | 全资产脱敏统一 |

## 重复架构检测

- Memory: **1 套** ExperienceStore (✅ 无重复)
- Retrieval: **2 套** (MemoryRetriever + DebugExperienceRetriever + 新 Orchestrator — 未统一)
- Trace: **4 套** (PlanningTrace/LearningTrace/DebugTrace + AuditEvent — Audit 统一层已建, 未全接)
- Context Budget: **2 套** (DebugContextBudget + ContextLedger — 未统一)

## State 一致性

- 三处状态: pipeline.Lifecycle / orchestrator.ExecutionState / governance_status
- S10-065 UserLifecycle 映射层已建, 但内部三处仍独立 — 一致性靠测试保障
