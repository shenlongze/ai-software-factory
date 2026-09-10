# AI Factory OS — 映射规则提案（MAPPING RULES PROPOSAL）

> 日期: 2026-09-11 | 性质: **纯文档提案（零搬家 / 零建目录 / 零改代码 / 零改 import）**
> 基线: HEAD=52c83854 @ 分支 `cleanup/os-core-restructure-2026-09-11`（备份: `archive/pre-os-cleanup-2026-09-11` tag `pre-os-cleanup-2026-09-11`）
> 目标: 把代码按"核心六段 + OS 服务 + 插件 + 投影"重新安家，核心只剩接口/契约，具体做法降为插件
> 成功判据: 行为不变（测试全绿+入口可跑通），核心行数掉一个数量级，无孤儿无重复

---

# A. 目标五层（仓库根下直接建，不套 src/）

```
core/          六段: conversation / capability / scheduler / node / events / governance
os_services/   organization / projects / memory / knowledge / workforce
extensions/    factories/software/{workflow,agents,assets} · skills · mcp · tools · models · workloads
projections/   cli / web / desktop
bootstrap/     装配与启动（注册顺序、加载、config、ids）
```

**判定规则（唯一）**：放得进这棵树 = 有家；放不进 = 孤儿候选（Step 4 处理）。
**禁止目录**：`utils/` `common/` `helpers/` `kernel/` `misc/`、根散落 `.py`、`*_backup/_old/_v2.py`。

---

# B. 顶层目录映射规则（已核实实际内容）

| 现有根目录 | 规模（py/行） | 实际内容 | 目标 |
|-----------|--------------|---------|------|
| `factory-console/` | 311 / 128,281 | 混合：os_core_* + canonical + session(128 旧链) + api/web + 服务 | **拆分，见 §C** |
| `factory-org/` | 18 / 12,052 | org 领域模型（Company/Dept/Role/Authority/Capability 池/Industry/Execution 模型） | `os_services/organization/`（Capability 池 → `core/capability/`） |
| `factory-exec/` | 52 / 22,158 | 执行域：roles/skill/tool/mcp/provider/agent_executor/developer/patch... | **拆**：roles→`os_services/organization/roles`；skill/tool/mcp/provider→`extensions/`；执行原语→`core/node/` |
| `factory-core/` | 138 / 33,814 | L4 旧数据层 24 包（agents/product/intelligence/providers/events/...） | **拆**：领域原语→`core/`；服务→`os_services/`；不可归→ `delete`/archive（Step 4） |
| `factory-runtime/` | 12 / 1,613 | 独立 runtime bundle | node 运行时→`core/node/`；其余按职责 |
| `exec/` | 0 | **空目录**（仅 checkpoints.json） | 不建，忽略 |
| `factory_console/` | 2 / 21 | **stub 转发层**（指向 factory-console） | `delete` 候选（命名废除后消失） |
| `bin/` | 0 py | 启动脚本 | `bootstrap/` |
| `scripts/` | 4 / 622 | 构建/工具脚本 | `bootstrap/scripts/` |
| `demo/` `examples/` | 2 / 23 | 演示 | `archive/`（不参与清理） |
| `unused/` `build/` `dist/` `node_modules/` | 0 py | 生成物/废弃 | **不动，不进 MAP** |
| `desktop/` | Tauri 壳 | 桌面端 | `projections/desktop/` |
| `tests/` | — | 全量测试 | 跟随被测代码搬家（不删/不改断言） |
| `docs/` | — | 文档 | 不动 |

---

# C. factory-console/ 拆分规则（最关键 —— 逐文件去向）

> 顶层 113 py + 子目录（api 24 / audit 10 / external_executor 11 / memory 12 / retrieval 7 / session 128 / tools 3 / web）

## C.1 顶层文件（113）逐文件去向

| 目标层 | 文件 |
|--------|------|
| **core/conversation** | conversation_app · conversation_os · product_understanding · conversation_quality · semantic_proposal · llm_semantic_interpreter · testing_semantic_interp · chat_store · console_sessions |
| **core/capability** | os_core_capability · os_core_plugin · plugin_kernel · external_skills |
| **core/scheduler** | os_core_scheduler · ops_scheduler · retry_policy · run_liveness · task_tree |
| **core/node** | os_core_task · os_core_task_node · os_core_execution · os_core_runtime · os_core_resolution · node_runtime · production_runtime · runtime_store · exec_checkpoint · requirement_analysis_node |
| **core/events** | os_core_evidence · os_core_verification · os_core_outcome · evidence_domain · verification · verification_domain · events · trace_query · ids · audit/(见 C.2) |
| **core/governance** | governance_service · review_feedback · integrity_lock · agent_policy · llm_control · config |
| **os_services/organization** | os_core_company_organization · os_core_identity · os_core_role · os_core_professional |
| **os_services/projects** | os_core_project · os_core_work · project_agile · project_os · project_ssot |
| **os_services/workforce** | os_core_workforce · workforce_os · workforce · workforce_composition · adaptive_workforce · performance_selection · agent_kernel |
| **os_services/memory** | learning_truth · learning_engine_v2 · experience_bridge · production_experience · memory/(见 C.2) |
| **os_services/knowledge** | context_runtime · context_intelligence · retrieval/(见 C.2) |
| **os_services/projects** | os_core_usage（成本计量 → 亦作 core/events 挂点，待裁定） |
| **extensions/factories/software/workflow** | golden_path · canonical_golden_path · task_decomposition · production_run · workflow_runner · workflow_canonical_bridge · professional_workflow · release_truth · acceptance_truth · artifact_lifecycle · artifact_contract · application_formalization · product_truth · production_service · production_guidance |
| **extensions/factories/software/** (SaaS 自治服务 → 亦可能属 os_services) | production_intelligence · production_evaluation · release_service · rollback_service · recovery · recovery_service · promotion_service · optimization_engine · optimization_service · self_healing · effectiveness_service · llm_experiment_service · experiment_reliability · intelligence_strategy |
| **extensions/models** | model_catalog · models · llm_router · local_ai |
| **extensions/workloads** | ops_projection · session/product_intelligence(→C.2) |
| **projections/cli** | cli_factory · cli_doctor · cli_services |
| **projections/web** | service · monitor · control_tower · operational_state · health_service · flow_views · golden_suite |
| **⚠️ 待裁定（跨层）** | backup · promotion_service(?) · ops_projection(?) |

## C.2 子目录规则

| 子目录 | 文件数 | 去向 | 说明 |
|--------|-------|------|------|
| `api/` | 24 | `projections/web/api/` | Web API 路由（纯函数层） |
| `audit/` | 10 | `core/events/audit/` | **唯一事实源审计链**（append-only）→ core |
| `external_executor/` | 11 | `extensions/models/` + `core/node/` | executor/gateway/router→node；registry/schema/parsers→extensions |
| `memory/` | 12 | `os_services/memory/` | 记忆/学习（experience/retrieval/learning_*） |
| `retrieval/` | 7 | `os_services/knowledge/` | RAG/知识（knowledge_store/retriever/external_source） |
| `session/` | **128** | **拆分（见 C.3）** | 旧 M3 链 + 工具；最大块 |
| `tools/` | 3 | `extensions/tools/` | adapters/executor/registry |
| `web/` | backend+frontend | `projections/web/` | FastAPI + 前端 |

## C.3 session/（128 文件）拆分 —— 最大风险块

| 去向 | 代表文件 |
|------|---------|
| `extensions/factories/software/workflow/` | pipeline · pipeline_runner · orchestrator · plan_critic · decomposer · replanning · review_gate · production_session · execution_truth · execution_replay · execution_quality · critical_path · dependencies · handoff · handoff_bus |
| `core/conversation/` | conversation · intent · intent_core · llm_intent · dialog_style · messages · answer_verify |
| `core/node/` | agent_loop · exec_state · sandbox · execution_policy · completion |
| `core/governance/` | approval_store · budget · confirm · cost_ledger · review_gate(?) |
| `core/events/` | audit · actions_audit · session_audit · evidence · lifecycle_store |
| `os_services/organization/` | agents · agent_entity · agent_registry · roles · teams · team_state · expert_factory |
| `os_services/memory/` | memory_core · project_memory · actions_memory · context_builder · context_layers · context_ledger · context |
| `os_services/projects/` | workspace · project_scan · repo_map · repo_mode |
| `extensions/tools/` | tools · external_tools · web_tools · tool_search · mcp_client · mcp_tools · mcp_tools |
| `extensions/skills/` | skill_search |
| `extensions/models/` | llm_gateway · model_prompt |
| `extensions/workloads/` | workloads/ · product_intelligence |
| `projections/cli/` | canonical_shell · slash · renderer · progress · progress_card · observability · board · review_view |
| `projections/web/` | — |
| `delete 候选` | actions_debug · scan 系列 · 空/过时（Step 4 核查） |

> ⚠️ session/ 128 文件"说不清去向"风险最高 → 若 >20% 无法定位将触发 HARD STOP。

---

# D. 不可归入五层的文件清单（孤儿第一手证据）

| 类别 | 文件 | 理由 | 建议 |
|------|------|------|------|
| **stub 转发层** | `factory_console/__init__.py` `factory_console/cli_factory.py` | 命名废除后无意义（指向 factory-console） | delete（Step 4 核查） |
| **构建产物** | `build/factory_console/*` `dist/*` | 生成物（含旧代码副本，易误判） | 不进 MAP / .gitignore |
| **演示** | `demo/*` `examples/*` `golden_suite.py` | 非生产 | archive/ |
| **调试/临时** | `session/actions_debug.py` `testing_semantic_interp.py` | 调试辅助 | 需人工裁定 |
| **疑似孤儿** | `backup.py` `monitor.py` `ops_projection.py` | 职责模糊 | Step 4 引用核查 |
| **废弃** | `unused/` 全部 | 已标废弃 | 不进 MAP（或 archive） |
| **需人工裁定（跨层冲突）** | `promotion_service` `ops_projection` `os_core_usage` `intelligence_strategy` | 同时说得通两层 | **HARD STOP 项** |

**孤儿初判数量级**：**约 15-25 个文件**（占 311 的 5-8%），**低于 20% 阈值** → 不触发 Step1 HARD STOP（但 §D "需人工裁定"项需你定）。

---

# E. 命名废除（factory-* → 五层）影响

| 受影响项 | 内容 | 规模 |
|---------|------|------|
| `pyproject.toml` packages | 现有：factory-core 24 子包（agents/assignment/change/.../workspace）+ `factory_console.*`(9 子包) + `exec.*` + `org` | **需整体重写**（≈40 条 package 路径） |
| 包映射机制 | 现状：`factory-console/`(连字符目录) → `factory_console`(包) + `factory-core`(源码根) → 顶层包 | 取消映射后 import 全变 |
| import 规模 | `factory_console.*` / `from .xxx` / 顶层包 `from agents|events|product...` | **估 500-1000+ 处**（需脚本统计，Step 2 前置） |
| CI 配置 | 尚未确认（需查 `.github/workflows`） | 待核 |
| 入口脚本 | `bin/factory` · `pyproject [project.scripts]` | 路径需更新 |
| 测试 import | tests/ 内 sys.path 注入 + import | 跟随搬家 |

> 建议：命名废除**最后做**（Step 2 完成搬家后统一改 import），或**先保留物理目录、只改内部结构**（降低风险）。

---

# 附：HARD STOP 触发条件核查（本轮）

| 条件 | 核查结果 | 是否触发 |
|------|---------|---------|
| factory-console >20% 说不清去向 | 约 5-8% | ❌ 未触发 |
| 某顶层目录内容与命名严重不符 | `factory-core` 名"core"实为旧数据层（**严重不符**）；`factory-console` 名"console"实含 core+engine+factory | ✅ **触发**（需人裁定命名） |
| 同一职责≥3 份实现 | **Role≥3 · Project≥4 · Approval≥5 · Capability≥5 · Agent≥4 · Scheduler≥4 · Learning≥4 · Audit=3 · Evidence=3 · Verification=2** | ✅ **触发**（多域） |
| 关键路径 TODO/FIXME | 未扫 | 待核 |

**结论**：本轮 **触发 HARD STOP 2 项**（命名严重不符 + 多域≥3 实现）——按 §4 铁律，**不擅自合并/搬迁**，需人裁定。

---

# HARD STOP

本文件为纯文档提案：**未建任何目录、未 git mv、未改 import、未改代码、未删文件、未推 cleanup 分支**。
等待指令后再进 Step 2。
