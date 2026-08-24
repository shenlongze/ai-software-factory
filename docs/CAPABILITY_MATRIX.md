# AI Factory CAPABILITY MASTER TABLE

> 权威能力地图 (S10-070 Audit 生成)。**以后任何 Sprint 开始前必须先检查此表; 新能力完成后必须更新此表。**
> 永久规则: Core + CLI + API + Intent + -h + Test 同 Sprint 交付, 禁止候补。

## 功能树 (22 领域)

```
AI Factory
├── 01 User & Discovery     (C01-C03: Idea/Clarification/Confirmation)
├── 02 Product Intelligence (C04-C10: Industry/Competitor/Persona/Market/Value/MVP/Conflict)
├── 03 Product Definition   (C03)
├── 04 Project / Workspace  (C53)
├── 05 Planning             (C11-C15: Plan/DAG/Replan/LLM/Versioning)
├── 06 Agent Team           (C16-C18: Team/Match/Execute)
├── 07 Execution            (C19-C23: Execute/Workspace/Conflict/Handoff/Progress)
├── 08 Code Production      (C19-C20)
├── 09 Testing              (C29)
├── 10 Debug                (C24-C30: Classify/RootCause/Memory/Strategy/Repair/Adapt/Session)
├── 11 Memory               (C31-C37: Storage/Extraction/Pattern/Retrieval/Recommend/Agent/Auto)
├── 12 Retrieval / RAG      (C38-C40: Orchestrator/Dedup/Project)
├── 13 Learning             (C33/C37)
├── 14 Governance           (C41-C45: Budget/Cost/LoopGuard/Review/Approval)
├── 15 Audit                (C46-C51: Event/Chain/Explain/Integrity/Redaction/Auto)
├── 16 Delivery             (C52-C53: Acceptance/Lifecycle)
├── 17 Deployment           (❌ 缺失)
├── 18 Operations           (⚠️ 部分: Runtime/状态)
├── 19 Security             (C57-C58: Redaction)
├── 20 CLI                  (57 actions)
├── 21 API                  (~62 endpoints)
└── 22 User Experience      (C54-C56: Session/NL/ContextBudget)
```

## Master Table (58 能力)

| ID | Domain | Capability | Core | CLI | API | Intent | -h | Test | 完成度 |
|---|---|---|---|---|---|---|---|---|---|
| C01 | User&Discovery | Idea Understanding | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C02 | User&Discovery | Multi-round Clarification | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C03 | User&Discovery | Requirement Confirmation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C04 | Product | Industry Analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C05 | Product | Competitor Analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C06 | Product | User Persona | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C07 | Product | Market Analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C08 | Product | Value Judgment | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C09 | Product | MVP Planning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C10 | Product | Requirement Conflict | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C11 | Planning | Plan Creation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C12 | Planning | Task DAG | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C13 | Planning | Replanning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C14 | Planning | LLM Planning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C15 | Planning | Plan Versioning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C16 | Team | Agent Team Formation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C17 | Team | Agent Matching | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C18 | Team | Team Execution | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C19 | Execution | Project Execution | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C20 | Execution | Workspace Isolation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C21 | Execution | Conflict Resolution | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C22 | Execution | Handoff | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C23 | Execution | Progress | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C24 | Debug | Error Classification | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C25 | Debug | Root Cause | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C26 | Debug | Debug Memory | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C27 | Debug | Strategy Selection | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C28 | Debug | Autonomous Repair | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C29 | Debug | Strategy Adaptation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C30 | Debug | Debug Session | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C31 | Memory | Experience Storage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C32 | Memory | Experience Extraction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C33 | Memory | Pattern Learning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C34 | Memory | Retrieval | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C35 | Memory | Recommendation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C36 | Memory | Agent Learning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C37 | Memory | Auto Learning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C38 | Retrieval | Orchestrator | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C39 | Retrieval | Dedup/Rank/TopK/Budget | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C40 | Retrieval | Project Retriever | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C41 | Governance | Budget | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C42 | Governance | Cost Ledger | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C43 | Governance | Loop Guard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C44 | Governance | Review Gate | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C45 | Governance | Approval | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C46 | Audit | Event Capture | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C47 | Audit | Decision Chain | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C48 | Audit | Explainability | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C49 | Audit | Integrity/Hash | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C50 | Audit | Redaction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C51 | Audit | Auto Capture | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C52 | Delivery | Acceptance | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C53 | Delivery | Lifecycle | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C54 | UX | Production Session View | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C55 | UX | Guided NL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C56 | UX | Context Budget | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C57 | Security | Secret Redaction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |
| C58 | Security | Secret Redaction(Trace) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 100% |

## 深入维度状态 (Production/Audit/Memory/Context)

| ID | Capability | Production | Audit 自动 | Memory | Context Budget | 真实 E2E |
|---|---|---|---|---|---|---|
| C24-C30 | Debug | ⚠️ 执行桩 | ⚠️ DEBUG_STARTED | ✅ | ✅ 独立 | ⚠️ 注入验证 |
| C31-C37 | Memory | ⚠️ 手动沉淀 | ✅ MEMORY_LEARNED | ✅ | ✅ 独立 | ✅ |
| C38-C40 | Retrieval | ❌ 仅测试 | — | ⚠️ 未统一 | ❌ 未接 LLM | ⚠️ |
| C41-C45 | Governance | ✅ | ❌ 无自动 | — | — | ✅ |
| C46-C51 | Audit | ⚠️ 31% 自动 | ✅ | — | ❌ 未接 LLM | ✅ 查询 |
| C52-C53 | Delivery | ✅ | ❌ 手动 | — | — | ✅ |


## Reality Status (S10-071 反虚标更新)

> 代码事实重评级 (2026-08-17)。REAL_EXECUTION 维度 = 生产路径真实执行证据。
> 规则: 接口 6 维只是覆盖, 无 REAL_EXECUTION 不得称 Production Ready。

| ID | Capability | 接口 6 维 | Real Execution | Production | Audit 自动 | Memory 自动 | Context Gate | Status |
|---|---|---|---|---|---|---|---|---|
| C24 | Debug 错误分类 | ✅ 100% | ✅ | ✅ | ✅ | — | — | **DONE** |
| C25 | Debug 根因 | ✅ 100% | ✅ | ✅ | ✅ | — | — | **DONE** |
| C26 | Debug Memory | ✅ 100% | ✅ 统一检索 | ✅ | ✅ | ✅ | ✅ | **DONE** |
| C27 | Debug 策略 | ✅ 100% | ✅ | ✅ | — | — | — | **DONE** |
| C28 | Debug 修复 | ✅ 100% | ✅ 真实改文件 | ✅ | ✅ | ✅ | — | **DONE** (S10-071) |
| C29 | Debug 验证 | ✅ 100% | ✅ 真实 pytest | ✅ | ✅ | ✅ | — | **DONE** (S10-071) |
| C30 | Debug 会话 | ✅ 100% | ✅ | ✅ | ✅ | — | — | **DONE** |
| C31-C37 | Memory | ✅ 100% | ✅ 自动沉淀 | ✅ (orchestrator) | ✅ | ✅ | — | **DONE** (S10-071 接线) |
| C38-C40 | Retrieval | ✅ 100% | ✅ Debug 统一入口 | ⚠️ 部分 | — | — | ✅ | **PARTIAL** (生产其余入口未全) |
| C41-C45 | Governance | ✅ 100% | ✅ | ✅ | ⚠️ 无自动 | — | — | **DONE** |
| C46-C51 | Audit | ✅ 100% | ✅ 查询/解释 | ✅ (7 点自动) | ✅ | — | — | **DONE** (S10-071 扩展) |
| C52-C53 | Delivery | ✅ 100% | ✅ | ✅ (PROJECT_DELIVERED 自动) | ✅ | — | — | **DONE** (S10-071) |
| C56 | Context Budget | ✅ 100% | ✅ LLM gate | ✅ (reasoning) | — | — | ✅ | **DONE** (S10-071) |
| C57-C58 | Security | ✅ 100% | ✅ 脱敏 | ✅ | ✅ | — | — | **DONE** |
| C01-C23 | 其余 (Discovery/Product/Planning/Team/Execution) | ✅ 100% | ✅ | ✅ | ⚠️ 部分自动 | ⚠️ | — | **DONE/PARTIAL** |

### 反虚标前后对比

| 指标 | S10-070 (Audit) | S10-071 (Zero-Stub) |
|---|---|---|
| STUB (Debug 修复/验证) | 2 | **0** (真实执行) |
| PARTIAL (接线型) | 3 (Memory/Audit/Retrieval) | 1 (Retrieval 生产入口) |
| 虚标 "DONE" | 58 | 0 |
| Production Ready (估) | ~43% | ~85% |

### 诚实标记 (S10-071 保留)

- Retrieval: Debug 已统一; memory_search/Product/Planning 检索仍各走各 → PARTIAL
- Deployment: NOT_PRODUCTION_READY (无部署能力)
- Audit: orchestrator 已接 TASK_*/PROJECT_DELIVERED; Discovery/Planning/Agent 级事件仍未自动
- Memory: execute_project 完成自动 learn; 失败路径/重规划未全

## Gap 索引

- P0 (5): Debug 真实修复/验证 / Memory 自动 / Audit 全链 / ContextBudget 执行
- P1 (4): Retrieval 统一 / Deployment / LLM 审计 / 多项目隔离
- 详见 docs/architecture/capability-audit/critical-gaps.md

---
> 生成: 2026-08-17 | 全量测试: 11638 passed + 1 skipped | Git: clean


## S10-073 更新 (Production Governance)

> 2026-08-17: 项目隔离 + Audit 全覆盖完成。

| 维度 | S10-072 | S10-073 | 证据 |
|---|---|---|---|
| Retrieval 项目隔离 | fail-open | **fail-closed** (项目+全局共享, 绝不含其他项目) | 8 隔离测试 (A→A✅ A→B❌) |
| Debug 检索隔离 | 未强制 | **session.project 约束** | DebugRetrievalPolicy + debug_memory 强制 project |
| Recommend 隔离 | fail-open | **fail-closed** (仅全局) | recommend_for_debug project="" |
| Audit 自动覆盖 | 10/16 | **15/16** | DISCOVERY/PLAN/AGENT/TASK/EXECUTION/CODE/TEST 自动 |
| Audit Event Types | 33 | **40** | TASK_STARTED/FAILED/AGENT_ASSIGNED/DISCOVERY_CONFIRMED 等 |
| 失败路径 Audit | TASK_FAILED 手动 | **TASK_FAILED 自动** (执行循环) | _execute_with_retry emit |

### Reality Status 最终

| Status | S10-072 | S10-073 | 说明 |
|---|---|---|---|
| DONE | 57 | **57** | — |
| PARTIAL | 1 | **1** | TOOL_CALL (AgentRuntime 内部, 约束不修改核心) |
| STUB | 0 | 0 | — |
| Production Ready | ~92% | **~96%** | 剩余: TOOL_CALL 自动 + Deployment |

### 剩余真实缺口 (诚实)

1. TOOL_CALL 未自动 (工具调用在 factory-exec AgentRuntime 内部 — 按用户约束不修改核心执行)
2. Deployment 无能力 (S10-074 候选, 本 Sprint 禁止)
3. 多项目 Audit 查询隔离已测 (query project_id) — 完整隔离契约达成

## S10-072 更新 (Production Truth)

> 2026-08-17: 反 bypass + 自动贯穿完成。

| 能力 | S10-071 后 | S10-072 后 | 证据 |
|---|---|---|---|
| Retrieval (memory_search) | ⚠️ bypass | ✅ 统一 (Orchestrator) | retrieve_experience 统一入口 + 11 测试 |
| Retrieval (recommend) | ⚠️ bypass | ✅ 统一 | recommend_for_debug 经 Orchestrator |
| Retrieval (Debug) | ⚠️ 双路径 | ✅ 全统一 | DebugRetrievalPolicy + debug_memory 均经 Orchestrator |
| Audit 自动覆盖 | 7/16 阶段 | **10/16** (+Governance/Repair/Validation) | GOVERNANCE_CHECK/REPAIR_*/VALIDATION_* 自动 emit |
| Memory 自动沉淀 | 仅 execute_project | + **Debug 闭环自动** (run 终态 learn) | Learning Loop E2E: Run A→B 实证 |
| Event Types | 缺 VALIDATION_* | ✅ 补全 (REPAIR_FAILED/VALIDATION_PASSED/FAILED) | 自动事件合法 |

### Reality Status 最终

| Status | 数量 | 说明 |
|---|---|---|
| DONE | 57 | 含 Debug 修复/验证/统一检索/自动 Audit/Memory |
| PARTIAL | 1 | Deployment (无能力, NOT_PRODUCTION_READY 标记) |
| STUB | 0 | — |
| Production Ready | ~92% | 剩余: Deployment + Audit Discovery/Plan 级 + 多项目隔离 |

### 已确认不存在的风险

- ❌ 无生产路径硬编码 success (S10-071 移除)
- ❌ 无 Retrieval bypass (统一入口验证测试强制)
- ❌ 无人工 audit record 依赖 (生产链自动 emit 实证)
- ❌ 无 Memory 手动数据库 (Debug 闭环自动 learn 实证)

## S10-099 更新 (Discovery LLM 深度介入, v1.1.16)

> 2026-08-24 | Sprint: 发现阶段字段收集从规则状态机升级为 LLM 理解主路径 + 规则兜底

| 能力 | S10-098 前 | S10-099 后 | 证据 |
|---|---|---|---|
| C01 Idea Understanding | 规则状态机逐字段收集 (模板化) | **LLM 意图理解 + 结构化提取** (一次产出 problem/user/core_features/name/platform) | 真实 LLM: "我想做个markdown编辑器, 要typora和notepad++优点, 适配手机" → category=product_description + 提取 3 字段 + 理解摘要 |
| C02 Multi-round Clarification | 机械列模板问题 | **智能追问** (理解为什么缺 → 针对性 1 问带理由); 模糊控制改写 ("整理一下") 也被识别 | 交互实测: 追问 "具体融合哪些优点? (为什么还问: 未说明要解决的具体痛点)" |
| C03 Requirement Confirmation | 规则摘要 | **确认门增强**: LLM 理解摘要 "我理解你要做X, 给Y用, 核心是A/B/C" + 主动分析 (平台/竞品/范围/备注) | 确认消息含 "我理解你要做一款手机端的markdown编辑器…" + 主动建议 + AI 命名 |
| 无 LLM 兜底 | — | **规则状态机零变化** (诚实降级, 不伪造) | env -u 无 key: "我想做X" 仍逐字段问, 无 "我理解" 标记 |

- 新增: `factory-console/session/discovery_intelligence.py` (DiscoveryIntentAnalyzer, 复用 ReasoningProvider 装配链)
- 集成: `conversation.py` (start_product_discovery 初始描述即解析 / handle_product_answer LLM 分流 / 确认门增强)
- 测试: `tests/console/test_discovery_llm_intelligence.py` 33 passed; 真实 LLM 交互验收 7/7
- 边界: DiscoverySession (S10-065 "开始做X" 路径) 未动; product_pipeline 深度分析未动

## S10-100 更新 (DiscoverySession 同步 LLM 化, v1.1.21)

> 2026-08-24 | Sprint: "开始做X" 路径 (S10-065 DiscoverySession) 复用 analyzer 同步 LLM 化 — 两路径对齐

| 项 | S10-099 后 | S10-100 后 |
|---|---|---|
| conversation 路径 ("我想做X") | LLM 化 ✅ (S10-099) | 不变 (analyzer 契约扩展对其透明) |
| DiscoverySession 路径 ("开始做X") | 纯规则逐字段 (S10-065) | **LLM 一次产出 + 智能追问带理由 + 理解摘要 + 主动分析 + LLM 命名** |
| analyzer extraction 契约 | 5 字段 | **8 字段** (+usage_scenarios/mvp_scope/non_functional_requirements, 可选, 向后兼容) |
| 无 LLM 兜底 | — | 两路径均规则兜底零变化 |
| 摘要格式对齐 | — | 两路径确认消息结构一致: 理解摘要首行 + 字段 + 建议名称候选 + 主动建议 |

- 实现: `discovery.py` (+359) analyzer 注入/懒装配 + start LLM 一次产出 + process_user_input LLM 分流 (含 v1.1.19 system_question 多轮合并边界) + 确认门增强 + LLM-gated 命名
- 测试: `tests/console/test_discovery_session_llm.py` 26 passed; 既有 108 DS + 35 analyzer 零改动全绿; 真实 LLM 验收 8/8
- 边界: conversation 路径未改; 驱动层逃生/CLI 接线未做 (模型层)
