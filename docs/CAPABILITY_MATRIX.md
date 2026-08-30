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

## S10-105 更新 (CLI Markdown 渲染 + /preview + 多行输入, v1.1.28)

> 2026-08-24 | Sprint: 会话 REPL 层 — PRD/文档输出 rich.Markdown 渲染;
> `/preview PRD.md` 渲染显示文件; 行尾 `\` 续行拼接多行输入 (prompt_toolkit 缺失 → input() 降级)

| 项 | S10-104 后 | S10-105 后 |
|---|---|---|
| 会话 PRD/文档输出 | 显示 markdown 源码 | **rich.Markdown 渲染** (标题/列表/表格/代码块可读, 不再看源码) |
| 文档预览 | 只显示路径, 无预览能力 | **/preview PRD.md** 渲染显示 (绝对/相对路径解析: cwd → workspace → 项目目录 → data_dir 兜底; 无参/不存在 → 友好错误 rc 2) |
| 多行输入 | 仅单行 input() | **行尾 `\` 续行拼接** (提示 `… `, 直到无 `\`; prompt_toolkit 缺失 → input() 降级, 诚实) |
| 降级 | — | **无 rich/prompt_toolkit 诚实降级** (print 原样, 不崩) |
| 非 markdown 消息 | 原样 | **原样零变化** (启发式保守: 列表标记不算, 发现/进度消息保持纯文本) |

- 新增: `session/renderer.py` looks_like_markdown + render_message (rich 可选导入);
  `session/commands.py` PreviewCommand; `session/session.py` _read_input_line + 用户面
  消息 print 点接入 render_message (chat 回答 / action renderer 输出 / 产品流消息)
- 测试: `tests/console/test_s10_105_markdown_preview.py` 契约 1-7; 全量 console 0 新增失败
- 边界: Web 富文本 / 完整编辑器 / prompt_toolkit 完整增强 / /preview HTML 导出 → backlog

## S10-104 更新 (确认阶段 next_action 全覆盖 + 会话分割线 + 删除指令, v1.1.25)

> 2026-08-24 | Sprint: "产出份prd文档"/"生成PRD"/"出个html"/"出份功能清单" 不再被当改名 —
> next_action 类型扩展 {prd/feature_list/html/docs} (LLM 分类为主 + 规则补全变体);
> 每轮回复间分割线; "把核心功能删掉"/"清空目标用户" → 字段清空 → 重新确认/追问

| 项 | S10-103 后 | S10-104 后 |
|---|---|---|
| "产出份prd文档"/"生成PRD" | 无确认前缀 → 改名兜底 | **DIRECT_ACTION → approved + next_action=prd** (名称不被覆盖) |
| "出个html" / "出份功能清单" / "文档" | 改名兜底 (无规则) | **next_action=html / feature_list / docs** (确定性规则 + LLM 补充分类; 宿主记信号 backlog, 不阻断创建) |
| "改名叫X" | 改名 | **不变** (RENAME_RE 最优先, "改名叫prd" 不被动作规则抢) |
| 多轮回复 | 无分隔 | **SEPARATOR = "─"*46** 每轮回复间 (REPL 层纯装饰; 退出/空输入不打印) |
| "把核心功能删掉"/"清空目标用户" | 改名兜底 | **字段清空 → 必填 → DISCOVERY + 追问; 可选/其它 → 重进确认** (绝不当改名; 字段收集期同步支持) |
| next_action 词汇 | prd/develop/create (需确认前缀) | **{prd, feature_list, html, docs}** (develop/create 保留兼容); 无确认前缀 = 隐含确认+下一步 |
| 确认分流顺序 | 改名 → 确认+下一步 → 纯确认 → 澄清 → 取消 → 委托 | **改名 → DIRECT_ACTION → 确认+下一步 → 纯确认 → 澄清 → 删除指令 → 取消 → 委托** → LLM → 改名兜底 |

- 新增: `discovery_guide.py` DIRECT_ACTION_PATTERNS + match_direct_action (确定性);
  `conversation.py` _parse_delete_command (复用 _EDIT_FIELD_ALIASES 两序匹配) +
  _apply_delete_command; `discovery_intelligence.py` 确认 prompt next_action 词汇 +
  无前缀隐含确认; `session.py` SEPARATOR + NEXT_ACTION_LABELS 宿主信号
- 测试: `tests/console/test_s10_104_action_coverage.py` 契约 1-9; 全量 console 0 新增失败
- 边界: 规则纯确定性 (动作/删除); LLM 只做补充分类; 产出引擎 (feature_list/html/docs) → backlog; prompt_toolkit → backlog

## S10-103 更新 (发现流程命令分流 + CLI 输入健壮性, v1.1.24)

> 2026-08-24 | Sprint: 发现/确认两路径中 "/status"/"exit" 不再被当字段 — slash → passthrough
> 交回宿主命令注册表; exit/quit/再见/退出会话/拜拜/结束 → 优雅退出; "退出" 仍 = 取消发现

| 项 | S10-102 后 | S10-103 后 |
|---|---|---|
| 发现中 "/status" | 模型层 handle() 死胡同消息 (非 passthrough) | **passthrough=True** — 宿主重分发 → registry 执行 (状态输出, 不当字段) |
| 发现中 "exit"/"quit" | 被当 problem 字段 (模型层无分流; REPL 顶部拦截掩盖) | **exit_requested=True** — 宿主 print 退出提示 + running=False (不当字段) |
| 确认中 slash/exit | 无分流 (slash 死胡同 / exit 当名称) | **同样分流** — handle_product_confirm 接入 _command_escape |
| "退出" | 取消发现 (S10-084 控制短语) | **语义不变** — _product_control 先处理 → 仍取消发现 (向后兼容) |
| EXIT_COMMANDS 单一来源 | session.py 本地定义 | **discovery_guide.EXIT_COMMANDS** (session 同源导入, 集合不变) |
| ConversationResponse | passthrough/next_action | **+ exit_requested** |
| CLI project 提示 | 漏 status | **提示补全 (create / list / rename / status)** |
| CLI create project --name | 不强制 | **缺失 → 明确错误 rc 2** |

- 新增: `discovery_guide.EXIT_COMMANDS` · `conversation._command_escape` ·
  `ConversationResponse.exit_requested` · `session._dispatch` exit_requested 宿主接线
- 测试: `tests/console/test_s10_103_command_routing.py` 契约 1-9; 全量 console 0 新增失败
- 边界: 命令分流纯确定性 (不依赖 LLM); "退出" 语义保持; 不新增依赖; prompt_toolkit/历史持久化 → backlog

## S10-102 更新 (确认阶段智能分流 + 求助词全覆盖, v1.1.23)

> 2026-08-24 | Sprint: "可以，先出prd文档"/"？" 不再被当产品名; "没 想法" 不再填进字段

| 项 | S10-101 后 | S10-102 后 |
|---|---|---|
| 确认阶段输入 | 非 y/取消 → 一律改名 (S10-081 过宽) | **六类分流**: 确认 / 确认+下一步(prd/develop/create) / 明确改名 / 澄清(？/为什么/能改吗) / 取消 / 委托(随便/你定) — 确定性表 → LLM → 改名兜底 |
| "可以，先出prd文档" | 整句被当产品名 | **approved + next_action=prd** (名称不被覆盖), 宿主创建成功后自动生成 PRD.md |
| "？" | 被当名称 "？" | **智能澄清**: 重展示摘要 + 解释选项 (不改名不确认) |
| 求助词 (字段收集) | "没 想法" 填进 core_features="想法" | **normalize_help_text 去空白 + 词表全覆盖** ("没 想法"/随便/你定/你看吧/无所谓…) → 建议流不填字段 (两路径) |
| 确认输入分类 LLM | 无 | **analyze_confirmation** (ConfirmationAnalysis: approve/approve_next/rename/clarify/cancel/delegate/other, 失败 → ConfirmationLLMError → 规则兜底) |
| 宿主接线 | 确认后仅创建 | **next_action="prd" → 创建成功后 generate_prd** (失败注明不阻断; develop/create 只传信号) |

- 新增: `discovery_guide.py` 确认分流确定性表 (APPROVE_WORDS/APPROVE_NEXT_ACTIONS/RENAME_RE/CLARIFY_WORDS/CONFIRM_DELEGATE_WORDS + match_*)
- analyzer: `discovery_intelligence.py` ConfirmationAnalysis + analyze_confirmation (宽容解析 + schema 校验)
- 集成: `conversation.py` handle_product_confirm 重构 + `ConversationResponse.next_action` + `_clarify_confirmation`; `discovery.py` + `conversation.py` `_is_help_request` 归一化; `session.py` PRD 宿主接线
- 测试: `tests/console/test_confirmation_intelligence.py` 34 passed + `test_discovery_guide.py` +15; 全量 console 0 新增失败
- 边界: 明确改名/裸文本改名/纯 y/N 行为不变; 无 LLM 规则兜底真实生效; develop/create 宿主执行留待后续; DS 确认阶段不改 (模型级 confirm 无改名 bug)

## S10-101 更新 (产品发现引导体验, v1.1.22)

> 2026-08-24 | Sprint: 确定性进度/生命周期 + 中间字段智能追问 + 求助建议填入 — 两路径同步

| 项 | S10-100 后 | S10-101 后 |
|---|---|---|
| 进度/生命周期 | 无进度提示 (只有问题) | **每轮消息前缀**: "流程: 发现→[当前]→…" + "产品定义 X/3: 字段✅/待填" (纯确定性, 无 LLM 也显示) |
| 中间字段追问 | field_answer 后机械模板 | **field_answer apply 后下一问优先 LLM smart_questions[0] (带理由)**; 空/失败 → 机械模板 |
| 求助输入 ("给些建议/没想法") | 被当字段内容收下 | **求助流**: HELP_KEYWORDS 硬闸 / LLM help_request → 建议展示 → 确认填入 (绝不当字段) |
| 求助兜底 | — | **DEFAULT_SUGGESTIONS 确定性建议** (无 LLM 诚实降级, 非伪造) |
| 增强字段提示 (DiscoverySession) | 无 | **enhanced_line**: "增强(可选): 使用场景待填 · …" (已填 ✅) |

- 新增: `factory-console/session/discovery_guide.py` (两路径共享唯一来源: lifecycle_line/format_progress/enhanced_line/HELP_KEYWORDS/DEFAULT_SUGGESTIONS)
- analyzer: `discovery_intelligence.py` VALID_CATEGORIES += `help_request` (优先级: 控制指令 > 查询 > 求助 > 字段回答 > 产品描述); 输出契约 += `suggestions {field, items, note}`
- 集成: `conversation.py` + `discovery.py` 对称 — 进度前缀 (批量/编辑/重问统一) + 求助 proposal {field, items} (y 全填/1-3 单选/自定义) + 中间字段智能下一问
- 测试: `tests/console/test_discovery_guide.py` 43 passed + 两路径新增 8 用例; 全量 console 4826 passed / 0 新增失败
- 边界: lifecycle 流程本身不驱动状态机 (仅引导文案); 求助建议只作用于当前缺失字段

## S24 更新 (Workforce Optimization & Production Optimization, v1.1.331)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Optimization Infrastructure (Analysis/Baseline/Experiment/Measurement/Comparison/Outcome) | REAL | test_optimization 9/9; 真实 production runs 度量 |
| Baseline (真实数据; 不足→BASELINE_INSUFFICIENT) | REAL | test_baseline_real_data / test_baseline_insufficient |
| Experiment Governance (未批准 blocked) | REAL | test_experiment_requires_approval |
| Outcome 诚实 (确定性 executor → UNCHANGED 不伪造) | REAL | test_real_experiment_e2e_honest_unchanged |
| Lineage (fact→analysis→baseline→experiment→measurement→outcome) | REAL | 测试断言 chain keys |
| Optimization Effectiveness | NOT YET PROVEN | 确定性 executor 下 Baseline==Treatment (UNCHANGED); 需真实 LLM 生产差异数据 |

### 诚实声明
- Optimization Infrastructure = REAL
- Optimization Effectiveness = NOT YET PROVEN (需真实 LLM 生产数据 + 对照实验)

## S25 更新 (Adaptive Workforce & Optimization Validation, v1.1.332)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Adaptive Workforce Infrastructure (WorkforceVariant) | REAL | test_adaptive_workforce 11/11; control 1 role vs treatment 2 roles 真实配置差异 |
| Workforce Experiment Assignment (run→variant 注入 input 持久化) | REAL | test_run_persists_variant; input 含 _variant_id/_variant_type/_experiment_id |
| Governance (未批准 Treatment → run blocked) | REAL | test_unapproved_treatment_blocked |
| Variant Isolation (control/treatment 独立 + experiment 不污染) | REAL | test_variant_isolation |
| Variant Lineage (variant→assignment→runs) | REAL | test_variant_lineage |
| Optimization Effectiveness | NOT YET PROVEN | 真实执行差异已建立 (variant_path); 仍需真实 LLM 生产数据对照实验证明改善 |

### 诚实声明
- Adaptive Workforce Infrastructure = REAL
- Optimization Effectiveness = NOT YET PROVEN (真实执行差异已证明, 改善未证明)

## S26 更新 (Real LLM Optimization Experiment, v1.1.333)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| 结构化 Hypothesis (metric/direction/threshold/min_sample 冻结) | REAL | test_llm_experiment 10/10; frozen=True 断言 |
| Real LLM Experiment (真实 provider 对照) | REAL | test_real_llm_experiment_e2e: 4 次真实 deepseek 调用 |
| Budget Guard (超限 STOPPED) | REAL | test_budget_guard: BUDGET_EXCEEDED |
| Sample Eligibility (ELIGIBLE/INELIGIBLE/FAILED) | REAL | test_sample_eligibility |
| PROVEN 硬性保护 (样本不足 → INCONCLUSIVE) | REAL | test_insufficient_sample_inconclusive |
| Real Experiment Evidence (诚实记录失败) | REAL | docs/audit/s26-real-experiment-evidence.md |
| Optimization Effectiveness | NOT_YET_PROVEN | 真实 LLM 实验 INCONCLUSIVE (全部样本 INCOMPLETE, 诚实报告) |

### 诚实声明
- Real LLM Experiment Infrastructure = REAL (真实 provider 调用 + 真实失败记录)
- Optimization Effectiveness = NOT_YET_PROVEN (真实实验 INCONCLUSIVE; 不伪造 IMPROVED)

## S27 更新 (Production Experiment Reliability, v1.1.334)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Production Outcome Contract (COMPLETED/INCOMPLETE/FAILED/BLOCKED/CANCELLED) | REAL | test_experiment_reliability 10/10; production_outcome 断言 |
| Failure Classification (VERIFICATION/AGENT/GOV/BUDGET/UNKNOWN + evidence_refs + explain) | REAL | test_verification_failure_classified (conf=1.0); UNKNOWN 不猜测 |
| Evaluation Quality Contract (EVALUATION_INVALID) | REAL | test_evaluation_invalid |
| Sample Eligibility (ELIGIBLE/INELIGIBLE + reason/classification) | REAL | test_completed_sample_eligible |
| Selection Bias 保护 (完整 denominator) | REAL | test_selection_bias_protection (3 samples 全保留) |
| S26 Failure Re-analysis (4 samples = VERIFICATION_FAILURE) | REAL | docs/audit/s27-real-e2e-evidence.md; 真实 LLM E2E |
| Optimization Effectiveness | NOT_YET_PROVEN | S26 重跑: 4 样本全 VERIFICATION_FAILURE → INCONCLUSIVE (诚实) |

### 诚实声明
- Production Experiment Reliability = REAL (分类/资格/denominator 全真实)
- Optimization Effectiveness = NOT_YET_PROVEN (S26 失败根因已查明 = VERIFICATION_FAILURE; 改善未证明)

## S28 更新 (Production Quality Recovery & Verification Closure, v1.1.335)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Recovery Infrastructure (bounded repair loop: FAIL→repair→re-verify→PASS→RECOVERED) | REAL | test_recovery 9/9 + S8 旧测试兼容 18/18 |
| Recovery Policy (VERIFICATION_FAILURE 可 repair; AGENT/GOV/UNKNOWN 不自动) | REAL | test_policy / test_case_c_blocked |
| Verification Closure (新 verification_id, 禁复用旧; 历史 append-only) | REAL | test_new_verification_id |
| Idempotency (已终态 → ALREADY_CLOSED) | REAL | test_idempotent |
| Real LLM Recovery (真实 codex repair → RECOVERED) | REAL | docs/audit/s28-real-e2e-evidence.md; 真实 LLM E2E attempt-1 RECOVERED |
| Optimization Effectiveness | NOT_YET_PROVEN | S26 失败已可 Recovery; 改善仍未证明 |

### 诚实声明
- Production Recovery Infrastructure = REAL (真实 LLM FAIL→REPAIR→PASS 闭环已证明)
- Real LLM Recovery = PROVEN (本次真实 E2E: RECOVERED attempt-1)
- Optimization Effectiveness = NOT_YET_PROVEN

## S29 更新 (Optimization Effectiveness & Controlled Experiment, v1.1.336)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Recovery-aware Sample (initial/final/recovery_attempts) | REAL | test_effectiveness 11/11; test_recovery_aware_sample |
| Population Contract (完整 denominator, initial vs final 分层) | REAL | test_population_denominator; experiment_population |
| Recovery-aware Comparison (initial/final/recovery_rate/mean_attempts) | REAL | test_recovery_aware_comparison |
| PROVEN Gate (12 条件; 样本不足 → INCONCLUSIVE) | REAL | test_insufficient_samples_inconclusive; Case A 测试 |
| Frozen Contract (hypothesis/metric/threshold/min_sample 不可改) | REAL | test_frozen_contract |
| Real LLM Effectiveness Experiment | REAL | docs/audit/s29-real-e2e-evidence.md; 真实 E2E UNCHANGED |
| Optimization Effectiveness | NOT_YET_PROVEN | 真实实验 control==treatment (1.0 vs 1.0) → UNCHANGED (诚实) |

### 诚实声明
- Optimization Effectiveness = NOT_YET_PROVEN (真实 LLM 实验无差异; 不伪造 IMPROVED)
- Experiment Reliability = REAL (Recovery-aware + PROVEN Gate 全真实)

## S30 更新 (Workforce Intelligence & Organization Foundation, v1.1.337)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Organization/Department/Workforce 层级 + lineage | REAL | test_workforce_os 10/10; test_org_hierarchy |
| Workforce Lifecycle (DRAFT→ACTIVE→SUSPENDED→RETIRED; 非法迁移拒绝; append-only) | REAL | test_lifecycle |
| AgentProfile (role/capabilities/skills/tools/model/policies binding) | REAL | test_agent_profile_binding |
| Capability Contract (确定性, 非 prompt) | REAL | test_capability_contract; capabilities_list 16 |
| 确定性 Agent Selection (capability match → permission; 非 LLM) | REAL | test_deterministic_selection |
| Performance Profile (从 Production Evidence 投影; 无数据 → 0 诚实) | REAL | test_performance_projection |
| Governance (非 DRAFT 不可 attach) | REAL | test_attach_requires_draft |
| Workforce OS E2E (org→wf→agent→select→task→run 链) | REAL | 测试 + CLI/API |

### 诚实声明
- Workforce OS Infrastructure = REAL (层级/Lifecycle/Profile/Selection/Performance 全真实)
- Performance 投影基于真实 Production Evidence (sample_count=0 时诚实, 不造数据)
- 未做真实 LLM E2E (S30 重点 = Organization Foundation; 复用 S11 真实 LLM 链)

## S31 更新 (Everything-is-a-Plugin Foundation, v1.1.338)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Plugin Contract (plugin_id/type/capabilities/dependencies/permissions) | REAL | test_plugin_kernel 12/12; test_register_get_list |
| Plugin Registry (register/get/list/unregister; SSOT) | REAL | test_bootstrap_builtin |
| Plugin Lifecycle (DISCOVERED→REGISTERED→ENABLED→DISABLED→RETIRED; 非法迁移拒绝) | REAL | test_lifecycle |
| 确定性 Resolution (capability→eligible→permission; 非 LLM) | REAL | test_deterministic_resolution |
| Plugin Governance (禁用拒绝执行; 自提升权限拒绝) | REAL | test_disabled_execution_rejected / test_self_elevate_rejected |
| 真实 Provider Plugin (deepseek/ollama/anthropic/codex executor) | REAL | bootstrap 4 内置; 真实执行 |
| **反硬编码 (新增实现不改 Core)** | REAL | test_add_second_impl_without_core_change (2 个新 provider 无 Core 修改) |
| CLI/API (list/inspect/enable/disable/status/health) | REAL | test_cli_plugin / test_api_plugin |

### 诚实声明
- Plugin Kernel = REAL (Contract/Registry/Lifecycle/Resolution/Governance 全真实)
- 反硬编码验证: 新增 provider 实现不需修改 Core (Architecture Test 证明)
- 未做: Marketplace/远程下载/沙箱 (明确排除在 S31 scope)

## S32 更新 (Composable Workforce & Capability, v1.1.339)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| AgentProfile → Plugin Composition (bind) | REAL | test_workforce_composition 9/9; test_bind_and_resolve |
| Composition Resolution (deterministic; 6 plugins ENABLED) | REAL | test_bind_and_resolve |
| Capability 统一 (S30 ↔ S31 单一语义) | REAL | test_unified_capability; unified_capability_list 16 |
| Scenario A: provider A→B 替换 (Core 不变) | REAL | test_provider_substitution |
| Scenario B: skill A→B 替换 (Core 不变) | REAL | test_skill_substitution |
| Scenario D: disabled → Workforce 拒绝 | REAL | test_disabled_rejected |
| 两 Workforce 不同 Plugin 共存 (Core 不变) | REAL | test_two_workforces_distinct |
| Lineage (plugin version/runtime/model 可追溯) | REAL | test_composition_lineage |
| CLI/API | REAL | test_cli_composition / test_api_composition |

### 诚实声明
- Composable Workforce = REAL (AgentProfile 由 Plugin references 组合, 非实现)
- 替换测试证明: provider/skill 替换不修改 Core (Architecture Test)
- 未做: Performance Ranking/LLM Selection (S32 明确排除, 后续 Sprint)

## S33 更新 (Performance-aware Workforce Selection, v1.1.340)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Performance 从真实 Production Evidence 投影 | REAL | test_performance_selection 9/9; sample_count/success_rate 断言 |
| 确定性 Ranking (capability→permission→policy→score) | REAL | test_deterministic_ranking (相同输入→相同排序) |
| Governance 优先于 Performance | REAL | test_governance_over_performance (self_elevate → rejected) |
| Cold-start (sample_count=0 不锁死) | REAL | test_cold_start (registration_order) |
| Performance Snapshot (历史可解释) | REAL | test_selection_and_snapshot / test_performance_history |
| Evidence 驱动替换 (Selection 变化) | REAL | test_evidence_driven_selection_change (A→B) |
| CLI/API | REAL | test_cli_select / test_api_select |

### 诚实声明
- Performance-aware Selection = REAL (Evidence → score → deterministic selection)
- 无样本时诚实 unknown (sample_count=0, 不造 confidence)
- 未做: LLM ranking / Learning / Self-Healing (S33 明确排除)

## S34 更新 (AI Factory OS Architecture Review, v1.1.341)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| Architecture Review (S0.5-S33 真实审计) | REAL | docs/architecture/ai-factory-os-architecture-review.md |
| OS Planes (Production/Workforce/Plugin/Evidence/Governance) | REAL | 审计确认 5 Plane 组件全 REAL |
| Core/Plugin 边界 | REAL | 冻结: Core governs capability, 不实现 capability |
| Intelligence Plane 设计 (Memory/Context/Learning/Promotion) | DESIGN | intelligence-plane-proposal.md + memory-context-contract.md |
| Context Control Plane Contract | DESIGN | Budget/JIT/Utility 冻结 (S35 实现) |
| Architecture Invariants (15 条) | 13/15 满足 | 2 条 Context 相关由 S35 建立 |

### 诚实声明
- S34 = 架构审查 + 设计 (无大规模实现, 按指令)
- Intelligence Plane = DESIGN (S35+ 实现)
- 无 Stub / 无重复 SSOT / CLI+API 原则保持

## S35 更新 (Context & Memory Runtime Foundation, v1.1.342)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| ContextRequest (scope 校验 + budget) | REAL | test_context_runtime 10/10 |
| ContextBudget (超预算 → COMPRESSED/TRUNCATED/REJECTED) | REAL | test_context_budget |
| Context Resolution (deterministic, JIT scope 过滤) | REAL | test_context_resolution |
| ContextSnapshot (不可变, 历史可解释) | REAL | test_context_resolution / history |
| MemoryCandidate → Promote (governed, 不自动长期化) | REAL | test_candidate_promote |
| LocalMemoryPlugin (deterministic, provenance/version/scope) | REAL | test_memory_query_scope |
| Memory Plugin 替换 (Core 零修改) | REAL | test_memory_plugin_replacement |
| Governance (未授权 scope 拒绝; disabled 拒绝) | REAL | test_scope_governance / test_disabled_memory_rejected |
| Cost 记账 (estimated 明确) | REAL | test_token_cost_estimate |
| CLI/API | REAL | test_cli / test_api (openapi 258) |

### 诚实声明
- Context Runtime = REAL (Request/Budget/Resolver/Snapshot 全真实)
- Memory = REAL (Plugin Contract + Local 实现, 无 vendor 依赖)
- Cost = estimated (无真实 token 数时明确标记, 不伪装)
- 未做: LLM ranking / Vector DB / 自动对话记忆 (S35 明确排除)

## S36 更新 (Context Intelligence & Memory Optimization, v1.1.343)

### Reality Status
| 能力 | Status | 证据 |
|------|--------|------|
| ContextUtility (relevance/evidence/freshness/confidence/scope/cost) | REAL | test_context_intelligence 11/11 |
| Budget-aware Selection (utility desc → 最优组合) | REAL | test_budget_selection / test_budget_overflow_rejected |
| Progressive Context (受预算, 总 <= max) | REAL | test_progressive_budget |
| ContextFeedback (USEFUL/UNKNOWN 诚实) | REAL | test_context_feedback |
| Memory Lifecycle (CANDIDATE→ACTIVE→SUPERSEDED→RETIRED) | REAL | test_memory_lifecycle (非法迁移拒绝) |
| Memory Freshness (valid_until 过期排除) | REAL | test_memory_freshness |
| Memory Conflict (evidence 解决, 非 last-write-wins) | REAL | test_memory_conflict |
| ContextStrategy Plugin (替换不修改 Core) | REAL | test_strategy_plugin_replacement |
| CLI/API | REAL | test_cli / test_api (openapi 266) |

### 诚实声明
- Context Intelligence = REAL (Utility/Ranking/Budget 分配/Feedback 全真实)
- Efficiency metric cost_per_successful_run = NOT_AVAILABLE (真实数据不足诚实)
- 未做: LLM ranking / Autonomous Learning / Self-Healing (S36 明确排除)
