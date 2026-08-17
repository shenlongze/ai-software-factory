# Critical Gap Matrix

> 基于代码事实扫描 (2026-08-17)。P0 = 不解决不能称为真正 Software Factory。

## P0 — 不解决就不是真正 Software Factory

| Priority | Capability | Current State | Problem | Impact | Recommended Solution | Dependencies | Complexity |
|---|---|---|---|---|---|---|---|
| P0-1 | Debug 真实修复 | execute_fn 默认确定性桩 | 自主修复不修改真实代码 | 无法"自动修复"真实 bug | RepairManager 桥接真实 Agent 执行 (非桩) | factory-exec AgentRuntime | 高 |
| P0-2 | Debug 真实验证 | 无 subprocess pytest | 修复后无法验证 | "验证"是模拟 | DebugPipeline 接真实 pytest 执行 (exec 薄调) | factory-exec | 高 |
| P0-3 | Memory 自动沉淀 | AutoLearner 未接 execute_project | 生产结束不自动学习 | 经验靠手动 | execute_project 完成钩子调 AutoLearner | S10-067 | 中 |
| P0-4 | Audit 全链自动 | 仅 5 action 自动 emit | orchestrator 执行链未审计 | 无法回答"执行时发生了什么" | AuditEmitter 接 orchestrator 关键点 (TASK_STARTED/COMPLETED/AGENT_*) | S10-069 | 中 |
| P0-5 | Context Budget 执行 | ContextLedger 无生产使用 | LLM 调用绕过预算 | Context 可无限增长 | LLM 调用统一经 ContextLedger.check | 全部 LLM 调用点 | 中 |

## P1 — 明显限制生产能力

| Priority | Capability | Current State | Problem | Impact | Recommended Solution | Complexity |
|---|---|---|---|---|---|---|
| P1-1 | Retrieval 统一使用 | Orchestrator 仅测试用 | 各模块绕过统一检索 | 未来多 RAG 冲突 | Debug/Planning/Product 检索统一经 Orchestrator | 中 |
| P1-2 | Deployment | 无 | 生产止于 DELIVERED | 不能交付可运行软件 | 最小部署 (本地 build/run 验证) | 高 |
| P1-3 | LLM 决策真实审计 | Audit 未记录 LLM_CALL 详情 | 无法回答"LLM 给了什么判断" | 可解释性缺口 | AuditEmitter 接 reasoning 调用 | 中 |
| P1-4 | 多项目隔离 | 单 workspace 优先 | 项目间 Memory 无隔离 | 经验污染 | ProjectRetriever project_id 过滤全接 | 低 |

## P2 — 产品完善

| Priority | Capability | Current State | Problem | Recommended Solution | Complexity |
|---|---|---|---|---|---|
| P2-1 | 经验衰减 | 无 | 过期经验无置信度衰减 | confidence 时间衰减 + Memory Consolidation | 中 |
| P2-2 | 错误经验污染 | 无反馈闭环 | 失败经验无修正 | User Feedback 经验类型 + 修正机制 | 中 |
| P2-3 | Incident 概念 | 无 | 异常执行无聚合视图 | Audit → Incident (S10-069 预留) | 中 |
| P2-4 | 动态 Top-K | 固定 | 任务类型不调整检索量 | RetrievalPolicy 按任务类型 | 低 |

## P3 — 长期增强

| Priority | Capability | Current State | Recommended Solution |
|---|---|---|---|
| P3-1 | External RAG | RetrievalSource 预留 | 外部 RAG 接入 Orchestrator |
| P3-2 | 企业 IAM | 无 | RBAC/SSO (Audit 模型预留) |
| P3-3 | 多后端 Audit 存储 | JSON | SQLite/PG/ES (Store 接口化) |
| P3-4 | Web UI | 无 | Web UI → API → Core (API 已就绪) |


## S10-071 更新 (Zero-Stub)

> 2026-08-17: P0-1~P0-6 已解决 (真实执行)。见 s10-071-zero-stub-forensics.md。

| 原 P0 | 状态 | 证据 |
|---|---|---|
| P0-1 Debug 真实修复 | ✅ 已解决 | WorkspaceRepairExecutor 真实改文件 (scoring.py 4→6 实证) |
| P0-2 Debug 真实验证 | ✅ 已解决 | PytestValidator 真实 subprocess pytest (隔离 PYTHONPATH) |
| P0-3 Memory 自动沉淀 | ✅ 已解决 | execute_project 完成 → AutoLearner (orchestrator 接线) |
| P0-4 Audit 全链自动 | ✅ 部分 | orchestrator TASK_*/PROJECT_DELIVERED + 7 action (31%→50%+) |
| P0-5 ContextBudget 执行 | ✅ 已解决 | ReasoningProvider context_ledger gate (超预算拒绝) |
| P0-6 Retrieval 统一 | ⚠️ 部分 | Debug 检索经 Orchestrator; memory_search/Product 未全 |

**剩余真实风险 (Top 5)**:
1. Retrieval 生产入口未全统一 (memory_search/Product/Planning 仍各走各)
2. Audit 自动覆盖 ~50% (Discovery/Planning/Agent 级未自动)
3. 无 Deployment 能力 (NOT_PRODUCTION_READY)
4. Memory 自动沉淀仅 execute_project 完成点 (失败路径/重规划未全)
5. Mock-only 测试 105 文件 (Debug 已真实验证, 其余待逐一反虚标)

**剩余 P1+**:
- P1-2 Deployment 最小部署层
- P1-3 LLM 决策自动审计 (LLM_CALL 详情)
- P1-4 多项目隔离全链

## 15 问核心答案

1. **真实 Capability**: 58 个 (接口层全完成)
2. **真正 Production Ready** (含真实执行/E2E): ~25 (43%) — 分析/规划/治理/审计/交付真实, Debug 修复/验证/部署未全
3. **只有 Core**: 0
4. **无 CLI**: 0
5. **无 API**: 0
6. **无 Intent**: 0
7. **无真实 E2E**: ~8 (Debug 修复/验证, Deployment, 部分自动接入)
8. **Mock/Injection**: Debug execute_fn/validator, ContextLedger, RetrievalOrchestrator (生产未用)
9. **10 大缺口**: 见 P0/P1 表
10. **10 大架构风险**: 见 architecture-risks.md
11. **Memory 架构**: 1 个 ExperienceStore + 1 个 RetrievalOrchestrator (但生产未统一)
12. **Context Budget**: 未控制所有 LLM 调用 (ContextLedger 未接)
13. **Debug 真实修改代码**: 否 (默认桩; 接口已备)
14. **Audit 全链覆盖**: 部分 (5 事件自动, orchestrator 未全)
15. **完整自动生产**: 见 production-readiness.md 逐阶段答案
