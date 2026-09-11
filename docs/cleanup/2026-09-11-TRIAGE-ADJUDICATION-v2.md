# 三分类裁定表 v2（按 Founder Core 边界宪法）

> 日期: 2026-09-11 | 性质: **纯只读（未搬家/未建目录/未改 import/未改代码/未删文件）**
> 基线: `cleanup/os-core-restructure-2026-09-11` | 依据: Founder 裁决的 Core 边界宪法
> 规模: **537 py 文件逐行核对**（factory-console 311 · factory-core 138 · factory-exec 52 · factory-org 18 · factory-runtime 12 · scripts/demo 6）

## 宪法基准（唯一裁决依据）

**Core 最小闭环** = 主体(Identity) → 意图(Intent) → 解析(Resolution) → 调用(Execution) → 验证(Verification) → 事实(Evidence/Observation) → 治理(Governance)

| 能力 | v1 归属 | Core 实现度 |
|---|---|---|
| Identity | Core | 最小（Principal/Identity） |
| Intent | Core | 实现 |
| Resolution | Core | 实现（找谁做） |
| Scheduling | OS Service | Core 只留 Contract |
| Execution | Core | Contract + Runtime Gate |
| Verification | Core | 最小闭环 |
| Evidence | Core | 实现 |
| Governance | Core Contract + Service | Core 实现 Gate |
| Observation | Core Fact + Service/Projection | Core 只留事实契约 |
| Organization(Company/Dept/Employee/Role) | Core 外 | 独立域 |
| Conversation | OS Service/Domain | 非 Projection |
| Approval 复杂流程 | OS Service | — |
| Memory/Learning | OS Service(+插件化底层) | — |
| Golden Path 13 节点 | Software Factory Extension | 绝不进 Core |
| Industry / Factory / Marketplace | Extension | — |
| CLI/Web/Workbench | Projection | 不得绕 Core |

## 依赖铁律
1. Extensions 只依赖 Core Contract/Port/SPI
2. Projections 不 import Extensions（走 CLI→OS API→Core→Extension→Core）
3. Core 只暴露契约与 SPI

## 逐文件分类（537 行）

| 文件路径 | 按宪法归属 | 层 | 证据(行数 / 最近改动) |
|---|---|---|---|
| `demo/repo/main.py` | UNCLEAR | UNCLEAR(工具/演示) | 11行 / 2026-08-20 |
| `demo/repo/test_main.py` | UNCLEAR | UNCLEAR(工具/演示) | 12行 / 2026-08-20 |
| `factory-console/__init__.py` | UNCLEAR | UNCLEAR(无匹配) | 84行 / 2026-08-18 |
| `factory-console/acceptance_truth.py` | GoldenPath-Factory | Extension | 281行 / 2026-09-06 |
| `factory-console/adaptive_workforce.py` | Organization | Org Model (Core 外) | 259行 / 2026-08-30 |
| `factory-console/agent_kernel.py` | UNCLEAR | UNCLEAR(无匹配) | 336行 / 2026-08-29 |
| `factory-console/agent_policy.py` | Governance | Core Contract + OS Service | 195行 / 2026-08-14 |
| `factory-console/api/__init__.py` | Web | Projection | 240行 / 2026-08-26 |
| `factory-console/api/agent_executor.py` | Web | Projection | 55行 / 2026-08-12 |
| `factory-console/api/approvals.py` | Approval-Service | OS Service (Core 留 Gate) | 171行 / 2026-08-09 |
| `factory-console/api/artifacts.py` | Web | Projection | 91行 / 2026-08-10 |
| `factory-console/api/audit.py` | Web | Projection | 326行 / 2026-08-17 |
| `factory-console/api/backlog.py` | Web | Projection | 200行 / 2026-08-26 |
| `factory-console/api/debug.py` | Web | Projection | 370行 / 2026-08-17 |
| `factory-console/api/decisions.py` | Web | Projection | 36行 / 2026-08-06 |
| `factory-console/api/flow.py` | Web | Projection | 60行 / 2026-09-11 |
| `factory-console/api/intelligence.py` | Web | Projection | 58行 / 2026-08-06 |
| `factory-console/api/lifecycle.py` | Web | Projection | 36行 / 2026-08-06 |
| `factory-console/api/mcp_api.py` | Web | Projection | 97行 / 2026-08-27 |
| `factory-console/api/memory.py` | Web | Projection | 196行 / 2026-08-17 |
| `factory-console/api/product_intelligence.py` | Web | Projection | 197行 / 2026-08-17 |
| `factory-console/api/projects.py` | Web | Projection | 663行 / 2026-09-01 |
| `factory-console/api/providers.py` | Web | Projection | 35行 / 2026-08-06 |
| `factory-console/api/review_feedback.py` | Governance | Core Contract + OS Service | 67行 / 2026-08-10 |
| `factory-console/api/runtime.py` | Web | Projection | 435行 / 2026-09-07 |
| `factory-console/api/runtime_session.py` | Web | Projection | 180行 / 2026-08-12 |
| `factory-console/api/skill_api.py` | Web | Projection | 55行 / 2026-08-13 |
| `factory-console/api/sprint.py` | Web | Projection | 288行 / 2026-08-11 |
| `factory-console/api/tool_api.py` | Web | Projection | 66行 / 2026-08-13 |
| `factory-console/api/workflow_start.py` | Web | Projection | 261行 / 2026-08-10 |
| `factory-console/api/workflows.py` | Web | Projection | 60行 / 2026-08-09 |
| `factory-console/application_formalization.py` | GoldenPath-Factory | Extension | 271行 / 2026-09-08 |
| `factory-console/artifact_contract.py` | GoldenPath-Factory | Extension | 346行 / 2026-08-26 |
| `factory-console/artifact_lifecycle.py` | GoldenPath-Factory | Extension | 544行 / 2026-09-05 |
| `factory-console/audit/__init__.py` | Observation | Core (Fact) | 54行 / 2026-08-17 |
| `factory-console/audit/audit_chain.py` | Observation | Core (Fact) | 168行 / 2026-08-17 |
| `factory-console/audit/audit_context.py` | Observation | Core (Fact) | 109行 / 2026-08-17 |
| `factory-console/audit/audit_emitter.py` | Observation | Core (Fact) | 178行 / 2026-08-25 |
| `factory-console/audit/audit_event.py` | Observation | Core (Fact) | 594行 / 2026-09-09 |
| `factory-console/audit/audit_explain.py` | Observation | Core (Fact) | 469行 / 2026-08-17 |
| `factory-console/audit/audit_integrity.py` | Observation | Core (Fact) | 107行 / 2026-08-17 |
| `factory-console/audit/audit_query.py` | Observation | Core (Fact) | 225行 / 2026-08-17 |
| `factory-console/audit/audit_store.py` | Observation | Core (Fact) | 221行 / 2026-08-17 |
| `factory-console/audit/trace_context.py` | Observation | Core (Fact) | 109行 / 2026-08-25 |
| `factory-console/backup.py` | UNCLEAR | UNCLEAR(无匹配) | 150行 / 2026-08-27 |
| `factory-console/canonical_golden_path.py` | GoldenPath-Factory | Extension | 287行 / 2026-09-09 |
| `factory-console/chat_store.py` | Conversation | OS Service/Domain | 98行 / 2026-08-10 |
| `factory-console/cli_doctor.py` | CLI | Projection | 564行 / 2026-08-19 |
| `factory-console/cli_factory.py` | CLI | Projection | 8507行 / 2026-09-09 |
| `factory-console/cli_services.py` | CLI | Projection | 459行 / 2026-08-24 |
| `factory-console/config.py` | Governance | Core Contract + OS Service | 328行 / 2026-08-10 |
| `factory-console/console_sessions.py` | Conversation | OS Service/Domain | 582行 / 2026-09-02 |
| `factory-console/context_intelligence.py` | Memory-Learning | OS Service | 320行 / 2026-08-31 |
| `factory-console/context_runtime.py` | Memory-Learning | OS Service | 417行 / 2026-08-31 |
| `factory-console/control_tower.py` | Web | Projection | 126行 / 2026-08-31 |
| `factory-console/conversation_app.py` | Conversation | OS Service/Domain | 589行 / 2026-09-09 |
| `factory-console/conversation_os.py` | Conversation | OS Service/Domain | 526行 / 2026-09-08 |
| `factory-console/conversation_quality.py` | Conversation | OS Service/Domain | 156行 / 2026-08-31 |
| `factory-console/effectiveness_service.py` | Factory | Extension | 354行 / 2026-08-30 |
| `factory-console/events.py` | Observation | Core (Fact) | 216行 / 2026-08-10 |
| `factory-console/evidence_domain.py` | Evidence | Core | 138行 / 2026-09-05 |
| `factory-console/exec_checkpoint.py` | Observation | Core (Fact) | 95行 / 2026-08-27 |
| `factory-console/experience_bridge.py` | Memory-Learning | OS Service | 219行 / 2026-09-06 |
| `factory-console/experiment_reliability.py` | Factory | Extension | 297行 / 2026-08-30 |
| `factory-console/external_executor/__init__.py` | Marketplace | Extension | 14行 / 2026-08-27 |
| `factory-console/external_executor/asset_parsers.py` | Marketplace | Extension | 85行 / 2026-08-27 |
| `factory-console/external_executor/executor.py` | Marketplace | Extension | 473行 / 2026-09-04 |
| `factory-console/external_executor/gateway.py` | Marketplace | Extension | 209行 / 2026-09-04 |
| `factory-console/external_executor/host_assets.py` | Marketplace | Extension | 266行 / 2026-08-27 |
| `factory-console/external_executor/metrics.py` | Marketplace | Extension | 115行 / 2026-08-27 |
| `factory-console/external_executor/monitor_detail.py` | Marketplace | Extension | 200行 / 2026-08-27 |
| `factory-console/external_executor/registry.py` | Marketplace | Extension | 152行 / 2026-08-28 |
| `factory-console/external_executor/router.py` | Marketplace | Extension | 243行 / 2026-08-27 |
| `factory-console/external_executor/schema.py` | Marketplace | Extension | 147行 / 2026-08-28 |
| `factory-console/external_executor/task_registry.py` | Marketplace | Extension | 107行 / 2026-08-28 |
| `factory-console/external_skills.py` | Marketplace | Extension | 136行 / 2026-08-27 |
| `factory-console/flow_views.py` | Web | Projection | 658行 / 2026-09-11 |
| `factory-console/golden_path.py` | GoldenPath-Factory | Extension | 630行 / 2026-09-09 |
| `factory-console/golden_suite.py` | Web | Projection | 292行 / 2026-08-31 |
| `factory-console/governance_service.py` | Governance | Core Contract + OS Service | 343行 / 2026-09-06 |
| `factory-console/health_service.py` | Web | Projection | 374行 / 2026-08-30 |
| `factory-console/ids.py` | Observation | Core (Fact) | 19行 / 2026-09-01 |
| `factory-console/integrity_lock.py` | Governance | Core Contract + OS Service | 83行 / 2026-08-30 |
| `factory-console/intelligence_strategy.py` | Factory | Extension | 245行 / 2026-08-31 |
| `factory-console/learning_engine_v2.py` | Memory-Learning | OS Service | 369行 / 2026-08-31 |
| `factory-console/learning_truth.py` | Memory-Learning | OS Service | 580行 / 2026-09-06 |
| `factory-console/llm_control.py` | Governance | Core Contract + OS Service | 362行 / 2026-08-13 |
| `factory-console/llm_experiment_service.py` | Factory | Extension | 333行 / 2026-08-30 |
| `factory-console/llm_router.py` | Marketplace | Extension | 410行 / 2026-08-14 |
| `factory-console/llm_semantic_interpreter.py` | Conversation | OS Service/Domain | 189行 / 2026-09-08 |
| `factory-console/local_ai.py` | Marketplace | Extension | 267行 / 2026-08-27 |
| `factory-console/memory/__init__.py` | Memory-Learning | OS Service | 92行 / 2026-08-25 |
| `factory-console/memory/auto_learn.py` | Memory-Learning | OS Service | 182行 / 2026-08-17 |
| `factory-console/memory/decision_memory.py` | Memory-Learning | OS Service | 246行 / 2026-08-25 |
| `factory-console/memory/experience.py` | Memory-Learning | OS Service | 158行 / 2026-09-06 |
| `factory-console/memory/experience_store.py` | Memory-Learning | OS Service | 174行 / 2026-08-17 |
| `factory-console/memory/extraction.py` | Memory-Learning | OS Service | 379行 / 2026-08-17 |
| `factory-console/memory/learning_engine.py` | Memory-Learning | OS Service | 287行 / 2026-08-17 |
| `factory-console/memory/learning_guards.py` | Memory-Learning | OS Service | 315行 / 2026-08-25 |
| `factory-console/memory/learning_loop.py` | Memory-Learning | OS Service | 337行 / 2026-08-25 |
| `factory-console/memory/learning_trace.py` | Memory-Learning | OS Service | 87行 / 2026-08-17 |
| `factory-console/memory/recommendation.py` | Memory-Learning | OS Service | 107行 / 2026-08-17 |
| `factory-console/memory/retrieval.py` | Memory-Learning | OS Service | 125行 / 2026-08-17 |
| `factory-console/model_catalog.py` | Marketplace | Extension | 392行 / 2026-08-13 |
| `factory-console/models.py` | Marketplace | Extension | 1011行 / 2026-08-29 |
| `factory-console/monitor.py` | Web | Projection | 235行 / 2026-09-01 |
| `factory-console/node_runtime.py` | UNCLEAR | UNCLEAR(无匹配) | 785行 / 2026-09-11 |
| `factory-console/operational_state.py` | Web | Projection | 249行 / 2026-08-31 |
| `factory-console/ops_projection.py` | Web | Projection | 151行 / 2026-08-30 |
| `factory-console/ops_scheduler.py` | UNCLEAR | UNCLEAR(无匹配) | 236行 / 2026-08-30 |
| `factory-console/optimization_engine.py` | Factory | Extension | 393行 / 2026-08-31 |
| `factory-console/optimization_service.py` | Factory | Extension | 450行 / 2026-08-30 |
| `factory-console/os_core_capability.py` | Resolution | Core | 152行 / 2026-09-10 |
| `factory-console/os_core_company_organization.py` | Organization | Org Model (Core 外) | 131行 / 2026-09-10 |
| `factory-console/os_core_evidence.py` | Evidence | Core | 120行 / 2026-09-10 |
| `factory-console/os_core_execution.py` | Execution | Core | 229行 / 2026-09-10 |
| `factory-console/os_core_identity.py` | Identity | Core | 231行 / 2026-09-10 |
| `factory-console/os_core_outcome.py` | Observation | Core (Fact) | 100行 / 2026-09-10 |
| `factory-console/os_core_plugin.py` | Marketplace | Extension | 143行 / 2026-09-10 |
| `factory-console/os_core_professional.py` | Organization | Org Model (Core 外) | 176行 / 2026-09-10 |
| `factory-console/os_core_project.py` | UNCLEAR | UNCLEAR(宪法未列 Project/Work) | 168行 / 2026-09-10 |
| `factory-console/os_core_resolution.py` | Resolution | Core | 248行 / 2026-09-10 |
| `factory-console/os_core_role.py` | Organization | Org Model (Core 外) | 211行 / 2026-09-10 |
| `factory-console/os_core_runtime.py` | Execution | Core | 350行 / 2026-09-10 |
| `factory-console/os_core_scheduler.py` | Scheduling | OS Service (Core 留 Contract) | 181行 / 2026-09-10 |
| `factory-console/os_core_task.py` | Execution | Core | 182行 / 2026-09-10 |
| `factory-console/os_core_task_node.py` | Execution | Core | 220行 / 2026-09-10 |
| `factory-console/os_core_usage.py` | Observation | Core (Fact) | 125行 / 2026-09-10 |
| `factory-console/os_core_verification.py` | Verification | Core | 84行 / 2026-09-10 |
| `factory-console/os_core_work.py` | UNCLEAR | UNCLEAR(宪法未列 Project/Work) | 271行 / 2026-09-10 |
| `factory-console/os_core_workforce.py` | Organization | Org Model (Core 外) | 302行 / 2026-09-10 |
| `factory-console/performance_selection.py` | Organization | Org Model (Core 外) | 238行 / 2026-08-31 |
| `factory-console/plugin_kernel.py` | Marketplace | Extension | 308行 / 2026-08-31 |
| `factory-console/product_truth.py` | GoldenPath-Factory | Extension | 861行 / 2026-09-09 |
| `factory-console/product_understanding.py` | Conversation | OS Service/Domain | 531行 / 2026-09-08 |
| `factory-console/production_evaluation.py` | GoldenPath-Factory | Extension | 241行 / 2026-08-30 |
| `factory-console/production_experience.py` | Memory-Learning | OS Service | 325行 / 2026-08-30 |
| `factory-console/production_guidance.py` | GoldenPath-Factory | Extension | 210行 / 2026-08-30 |
| `factory-console/production_intelligence.py` | GoldenPath-Factory | Extension | 495行 / 2026-08-30 |
| `factory-console/production_run.py` | GoldenPath-Factory | Extension | 554行 / 2026-09-11 |
| `factory-console/production_runtime.py` | GoldenPath-Factory | Extension | 499行 / 2026-09-09 |
| `factory-console/production_service.py` | GoldenPath-Factory | Extension | 164行 / 2026-08-29 |
| `factory-console/professional_workflow.py` | GoldenPath-Factory | Extension | 711行 / 2026-08-31 |
| `factory-console/project_agile.py` | Organization | OS Domain (Project) | 324行 / 2026-09-11 |
| `factory-console/project_os.py` | Organization | OS Domain (Project) | 270行 / 2026-08-31 |
| `factory-console/project_ssot.py` | Organization | OS Domain (Project) | 94行 / 2026-09-01 |
| `factory-console/promotion_service.py` | Factory | Extension | 392行 / 2026-08-31 |
| `factory-console/recovery.py` | Factory | Extension | 227行 / 2026-08-29 |
| `factory-console/recovery_service.py` | Factory | Extension | 292行 / 2026-08-30 |
| `factory-console/release_service.py` | Factory | Extension | 404行 / 2026-08-30 |
| `factory-console/release_truth.py` | GoldenPath-Factory | Extension | 419行 / 2026-09-06 |
| `factory-console/requirement_analysis_node.py` | Factory | Extension | 271行 / 2026-09-07 |
| `factory-console/retrieval/__init__.py` | Memory-Learning | OS Service | 59行 / 2026-08-26 |
| `factory-console/retrieval/external_source.py` | Memory-Learning | OS Service | 141行 / 2026-08-26 |
| `factory-console/retrieval/knowledge_store.py` | Memory-Learning | OS Service | 704行 / 2026-08-26 |
| `factory-console/retrieval/models.py` | Memory-Learning | OS Service | 116行 / 2026-08-17 |
| `factory-console/retrieval/orchestrator.py` | Memory-Learning | OS Service | 103行 / 2026-08-17 |
| `factory-console/retrieval/retriever.py` | Memory-Learning | OS Service | 154行 / 2026-08-17 |
| `factory-console/retrieval/unified.py` | Memory-Learning | OS Service | 84行 / 2026-08-17 |
| `factory-console/retry_policy.py` | UNCLEAR | UNCLEAR(无匹配) | 44行 / 2026-08-30 |
| `factory-console/review_feedback.py` | Governance | Core Contract + OS Service | 143行 / 2026-08-10 |
| `factory-console/rollback_service.py` | Factory | Extension | 415行 / 2026-08-30 |
| `factory-console/run_liveness.py` | Observation | Core (Fact) | 231行 / 2026-09-01 |
| `factory-console/runtime_store.py` | Observation | Core (Fact) | 179行 / 2026-08-10 |
| `factory-console/self_healing.py` | Factory | Extension | 370行 / 2026-08-31 |
| `factory-console/semantic_proposal.py` | Conversation | OS Service/Domain | 361行 / 2026-09-08 |
| `factory-console/service.py` | Web | Projection | 4927行 / 2026-09-02 |
| `factory-console/session/__init__.py` | UNCLEAR | UNCLEAR(session 未细分) | 16行 / 2026-08-15 |
| `factory-console/session/action.py` | UNCLEAR | UNCLEAR(session 未细分) | 127行 / 2026-08-15 |
| `factory-console/session/actions.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 4133行 / 2026-09-06 |
| `factory-console/session/actions_audit.py` | Evidence | Core | 353行 / 2026-08-28 |
| `factory-console/session/actions_debug.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 422行 / 2026-08-28 |
| `factory-console/session/actions_memory.py` | Memory-Learning | OS Service | 181行 / 2026-08-28 |
| `factory-console/session/agent_entity.py` | Organization | Org Model (Core 外) | 176行 / 2026-08-22 |
| `factory-console/session/agent_loop.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 4020行 / 2026-09-08 |
| `factory-console/session/agent_registry.py` | Organization | Org Model (Core 外) | 173行 / 2026-08-22 |
| `factory-console/session/agents.py` | Organization | Org Model (Core 外) | 754行 / 2026-08-25 |
| `factory-console/session/analysis_tools.py` | Factory | Extension | 151行 / 2026-09-01 |
| `factory-console/session/answer_verify.py` | Conversation | OS Service/Domain | 115行 / 2026-09-01 |
| `factory-console/session/approval_store.py` | Approval-Service | OS Service (Core 留 Gate) | 100行 / 2026-08-28 |
| `factory-console/session/artifact_registry.py` | UNCLEAR | UNCLEAR(session 未细分) | 212行 / 2026-08-22 |
| `factory-console/session/audit.py` | Evidence | Core | 219行 / 2026-08-15 |
| `factory-console/session/board.py` | CLI | Projection | 3230行 / 2026-08-26 |
| `factory-console/session/budget.py` | Governance | Core Contract + OS Service | 371行 / 2026-08-25 |
| `factory-console/session/canonical_shell.py` | CLI | Projection | 137行 / 2026-09-09 |
| `factory-console/session/capability_router.py` | UNCLEAR | UNCLEAR(session 未细分) | 594行 / 2026-08-25 |
| `factory-console/session/change_control.py` | UNCLEAR | UNCLEAR(session 未细分) | 760行 / 2026-08-26 |
| `factory-console/session/chat.py` | UNCLEAR | UNCLEAR(session 未细分) | 167行 / 2026-08-27 |
| `factory-console/session/code_scan.py` | UNCLEAR | UNCLEAR(session 未细分) | 292行 / 2026-08-28 |
| `factory-console/session/commands.py` | CLI | Projection | 794行 / 2026-08-25 |
| `factory-console/session/completion.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 117行 / 2026-08-15 |
| `factory-console/session/confirm.py` | Governance | Core Contract + OS Service | 84行 / 2026-08-25 |
| `factory-console/session/conflicts.py` | UNCLEAR | UNCLEAR(session 未细分) | 639行 / 2026-08-16 |
| `factory-console/session/context.py` | UNCLEAR | UNCLEAR(session 未细分) | 94行 / 2026-08-15 |
| `factory-console/session/context_builder.py` | Memory-Learning | OS Service | 612行 / 2026-08-16 |
| `factory-console/session/context_layers.py` | Memory-Learning | OS Service | 92行 / 2026-08-29 |
| `factory-console/session/context_ledger.py` | Memory-Learning | OS Service | 151行 / 2026-08-17 |
| `factory-console/session/conversation.py` | Conversation | OS Service/Domain | 1668行 / 2026-08-25 |
| `factory-console/session/core_loader.py` | UNCLEAR | UNCLEAR(session 未细分) | 40行 / 2026-08-22 |
| `factory-console/session/cost_ledger.py` | Governance | Core Contract + OS Service | 416行 / 2026-08-25 |
| `factory-console/session/critical_path.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 566行 / 2026-08-23 |
| `factory-console/session/debug/__init__.py` | UNCLEAR | UNCLEAR(session 未细分) | 335行 / 2026-08-17 |
| `factory-console/session/debug/context_budget.py` | Governance | Core Contract + OS Service | 98行 / 2026-08-17 |
| `factory-console/session/debug/debug_engine.py` | UNCLEAR | UNCLEAR(session 未细分) | 270行 / 2026-08-17 |
| `factory-console/session/debug/debug_memory.py` | UNCLEAR | UNCLEAR(session 未细分) | 149行 / 2026-08-17 |
| `factory-console/session/debug/debug_pipeline.py` | UNCLEAR | UNCLEAR(session 未细分) | 682行 / 2026-08-17 |
| `factory-console/session/debug/debug_session.py` | UNCLEAR | UNCLEAR(session 未细分) | 436行 / 2026-08-17 |
| `factory-console/session/debug/debug_strategy.py` | UNCLEAR | UNCLEAR(session 未细分) | 217行 / 2026-08-17 |
| `factory-console/session/debug/debug_trace.py` | UNCLEAR | UNCLEAR(session 未细分) | 132行 / 2026-08-17 |
| `factory-console/session/debug/error_analysis.py` | UNCLEAR | UNCLEAR(session 未细分) | 114行 / 2026-08-17 |
| `factory-console/session/debug/repair_safety.py` | UNCLEAR | UNCLEAR(session 未细分) | 143行 / 2026-08-17 |
| `factory-console/session/debug/retrieval_policy.py` | UNCLEAR | UNCLEAR(session 未细分) | 187行 / 2026-08-17 |
| `factory-console/session/debug/root_cause.py` | UNCLEAR | UNCLEAR(session 未细分) | 223行 / 2026-08-17 |
| `factory-console/session/debug/strategy_adaptation.py` | UNCLEAR | UNCLEAR(session 未细分) | 166行 / 2026-08-17 |
| `factory-console/session/debug/workspace_executor.py` | UNCLEAR | UNCLEAR(session 未细分) | 379行 / 2026-08-17 |
| `factory-console/session/decision.py` | UNCLEAR | UNCLEAR(session 未细分) | 360行 / 2026-08-16 |
| `factory-console/session/decomposer.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 816行 / 2026-08-24 |
| `factory-console/session/decomposition_evaluator.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 613行 / 2026-08-24 |
| `factory-console/session/delivery.py` | UNCLEAR | UNCLEAR(session 未细分) | 173行 / 2026-08-29 |
| `factory-console/session/dependencies.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 260行 / 2026-08-16 |
| `factory-console/session/dialog_style.py` | Conversation | OS Service/Domain | 80行 / 2026-08-27 |
| `factory-console/session/discovery.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 1285行 / 2026-08-24 |
| `factory-console/session/discovery_guide.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 290行 / 2026-08-25 |
| `factory-console/session/discovery_intelligence.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 536行 / 2026-08-25 |
| `factory-console/session/eval_judge.py` | UNCLEAR | UNCLEAR(session 未细分) | 118行 / 2026-08-27 |
| `factory-console/session/eval_loop.py` | UNCLEAR | UNCLEAR(session 未细分) | 418行 / 2026-08-25 |
| `factory-console/session/eval_suite.py` | UNCLEAR | UNCLEAR(session 未细分) | 1075行 / 2026-08-26 |
| `factory-console/session/evidence.py` | Evidence | Core | 369行 / 2026-08-24 |
| `factory-console/session/exec_state.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 250行 / 2026-09-02 |
| `factory-console/session/execution_policy.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 176行 / 2026-08-16 |
| `factory-console/session/execution_quality.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 567行 / 2026-08-25 |
| `factory-console/session/execution_replay.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 805行 / 2026-08-25 |
| `factory-console/session/execution_truth.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 305行 / 2026-09-02 |
| `factory-console/session/expert_factory.py` | Organization | Org Model (Core 外) | 613行 / 2026-08-25 |
| `factory-console/session/external_tools.py` | Factory | Extension | 155行 / 2026-08-27 |
| `factory-console/session/gap_analyzer.py` | UNCLEAR | UNCLEAR(session 未细分) | 662行 / 2026-08-16 |
| `factory-console/session/handoff.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 206行 / 2026-08-28 |
| `factory-console/session/handoff_bus.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 377行 / 2026-08-22 |
| `factory-console/session/intent.py` | Conversation | OS Service/Domain | 393行 / 2026-08-25 |
| `factory-console/session/intent_core.py` | Conversation | OS Service/Domain | 226行 / 2026-09-07 |
| `factory-console/session/lifecycle_store.py` | UNCLEAR | UNCLEAR(session 未细分) | 344行 / 2026-08-25 |
| `factory-console/session/llm_gap.py` | UNCLEAR | UNCLEAR(session 未细分) | 522行 / 2026-08-16 |
| `factory-console/session/llm_gateway.py` | Marketplace | Extension | 460行 / 2026-08-31 |
| `factory-console/session/llm_intent.py` | UNCLEAR | UNCLEAR(session 未细分) | 162行 / 2026-08-24 |
| `factory-console/session/llm_task_proposal.py` | UNCLEAR | UNCLEAR(session 未细分) | 494行 / 2026-08-16 |
| `factory-console/session/loop_guard.py` | UNCLEAR | UNCLEAR(session 未细分) | 297行 / 2026-08-16 |
| `factory-console/session/mcp_client.py` | Factory | Extension | 206行 / 2026-08-31 |
| `factory-console/session/mcp_tools.py` | Factory | Extension | 59行 / 2026-08-28 |
| `factory-console/session/memory_core.py` | Memory-Learning | OS Service | 125行 / 2026-08-28 |
| `factory-console/session/messages.py` | Conversation | OS Service/Domain | 388行 / 2026-08-15 |
| `factory-console/session/model_prompt.py` | Marketplace | Extension | 157行 / 2026-09-01 |
| `factory-console/session/naming.py` | UNCLEAR | UNCLEAR(session 未细分) | 148行 / 2026-08-19 |
| `factory-console/session/observability.py` | CLI | Projection | 219行 / 2026-08-31 |
| `factory-console/session/orchestrator.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 4209行 / 2026-09-02 |
| `factory-console/session/pipeline.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 599行 / 2026-08-25 |
| `factory-console/session/pipeline_runner.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 161行 / 2026-08-22 |
| `factory-console/session/plan_critic.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 338行 / 2026-08-16 |
| `factory-console/session/planning_trace.py` | UNCLEAR | UNCLEAR(session 未细分) | 298行 / 2026-08-16 |
| `factory-console/session/product.py` | UNCLEAR | UNCLEAR(session 未细分) | 171行 / 2026-08-19 |
| `factory-console/session/product_intelligence.py` | Factory | Extension | 1264行 / 2026-08-17 |
| `factory-console/session/production_session.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 702行 / 2026-08-16 |
| `factory-console/session/progress.py` | CLI | Projection | 190行 / 2026-08-15 |
| `factory-console/session/progress_card.py` | CLI | Projection | 121行 / 2026-08-28 |
| `factory-console/session/project_memory.py` | Memory-Learning | OS Service | 154行 / 2026-08-29 |
| `factory-console/session/project_scan.py` | Organization | OS Domain (Project) | 419行 / 2026-09-01 |
| `factory-console/session/quality.py` | UNCLEAR | UNCLEAR(session 未细分) | 455行 / 2026-08-15 |
| `factory-console/session/query_engine.py` | UNCLEAR | UNCLEAR(session 未细分) | 773行 / 2026-09-07 |
| `factory-console/session/reasoning.py` | UNCLEAR | UNCLEAR(session 未细分) | 604行 / 2026-08-18 |
| `factory-console/session/renderer.py` | CLI | Projection | 174行 / 2026-08-24 |
| `factory-console/session/replanning.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 1005行 / 2026-08-16 |
| `factory-console/session/repo_map.py` | Organization | OS Domain (Project) | 113行 / 2026-08-28 |
| `factory-console/session/repo_mode.py` | Organization | OS Domain (Project) | 208行 / 2026-08-20 |
| `factory-console/session/review_gate.py` | Governance | Core Contract + OS Service | 311行 / 2026-08-16 |
| `factory-console/session/review_view.py` | CLI | Projection | 119行 / 2026-08-16 |
| `factory-console/session/roles.py` | Organization | Org Model (Core 外) | 171行 / 2026-08-15 |
| `factory-console/session/router.py` | UNCLEAR | UNCLEAR(M3 旧链, 疑 dead) | 155行 / 2026-08-25 |
| `factory-console/session/sandbox.py` | UNCLEAR | UNCLEAR(session 未细分) | 110行 / 2026-08-28 |
| `factory-console/session/scheduler.py` | UNCLEAR | UNCLEAR(session 未细分) | 458行 / 2026-08-24 |
| `factory-console/session/session.py` | UNCLEAR | UNCLEAR(session 未细分) | 913行 / 2026-08-25 |
| `factory-console/session/session_audit.py` | Evidence | Core | 123行 / 2026-08-28 |
| `factory-console/session/session_hooks.py` | UNCLEAR | UNCLEAR(session 未细分) | 422行 / 2026-08-29 |
| `factory-console/session/session_snapshots.py` | UNCLEAR | UNCLEAR(session 未细分) | 115行 / 2026-08-29 |
| `factory-console/session/skill_search.py` | Factory | Extension | 70行 / 2026-08-28 |
| `factory-console/session/slash.py` | CLI | Projection | 86行 / 2026-08-15 |
| `factory-console/session/task_proposal.py` | UNCLEAR | UNCLEAR(session 未细分) | 646行 / 2026-08-16 |
| `factory-console/session/team_state.py` | Organization | Org Model (Core 外) | 306行 / 2026-08-16 |
| `factory-console/session/teams.py` | Organization | Org Model (Core 外) | 392行 / 2026-08-15 |
| `factory-console/session/tool_search.py` | Factory | Extension | 194行 / 2026-08-29 |
| `factory-console/session/tools.py` | Factory | Extension | 210行 / 2026-08-20 |
| `factory-console/session/topic_ledger.py` | UNCLEAR | UNCLEAR(session 未细分) | 317行 / 2026-08-28 |
| `factory-console/session/user_lifecycle.py` | Organization | Org Model (Core 外) | 176行 / 2026-08-16 |
| `factory-console/session/web_tools.py` | Factory | Extension | 212行 / 2026-08-28 |
| `factory-console/session/workloads/__init__.py` | Factory | Extension | 8行 / 2026-08-20 |
| `factory-console/session/workloads/backlog_sweeper.py` | Factory | Extension | 818行 / 2026-08-21 |
| `factory-console/session/workspace.py` | Organization | OS Domain (Project) | 330行 / 2026-08-16 |
| `factory-console/task_decomposition.py` | GoldenPath-Factory | Extension | 405行 / 2026-09-09 |
| `factory-console/task_tree.py` | UNCLEAR | UNCLEAR(无匹配) | 210行 / 2026-09-09 |
| `factory-console/testing_semantic_interp.py` | UNCLEAR | UNCLEAR(无匹配) | 204行 / 2026-09-08 |
| `factory-console/tools/adapters.py` | Factory | Extension | 84行 / 2026-08-27 |
| `factory-console/tools/executor.py` | Factory | Extension | 95行 / 2026-08-27 |
| `factory-console/tools/registry.py` | Factory | Extension | 172行 / 2026-08-27 |
| `factory-console/trace_query.py` | Observation | Core (Fact) | 241行 / 2026-09-09 |
| `factory-console/unified_contract.py` | Observation | Core (Fact) | 318行 / 2026-08-31 |
| `factory-console/verification.py` | Evidence | Core | 81行 / 2026-08-29 |
| `factory-console/verification_domain.py` | Evidence | Core | 186行 / 2026-09-05 |
| `factory-console/web/__init__.py` | Web | Projection | 1行 / 2026-08-06 |
| `factory-console/web/backend/__init__.py` | Web | Projection | 6行 / 2026-08-06 |
| `factory-console/web/backend/fastapi_adapter.py` | Web | Projection | 8596行 / 2026-09-09 |
| `factory-console/workflow_canonical_bridge.py` | GoldenPath-Factory | Extension | 169行 / 2026-09-06 |
| `factory-console/workflow_runner.py` | GoldenPath-Factory | Extension | 1330行 / 2026-09-06 |
| `factory-console/workforce.py` | Organization | Org Model (Core 外) | 252行 / 2026-08-30 |
| `factory-console/workforce_composition.py` | Organization | Org Model (Core 外) | 284行 / 2026-08-30 |
| `factory-console/workforce_os.py` | Organization | Org Model (Core 外) | 414行 / 2026-09-10 |
| `factory-core/agents/__init__.py` | Organization | Org Model (legacy L4) | 40行 / 2026-08-05 |
| `factory-core/agents/models.py` | Marketplace | Extension | 107行 / 2026-08-05 |
| `factory-core/agents/registry.py` | Organization | Org Model (legacy L4) | 263行 / 2026-08-05 |
| `factory-core/agents/skills.py` | Organization | Org Model (legacy L4) | 58行 / 2026-08-05 |
| `factory-core/agents/store.py` | Organization | Org Model (legacy L4) | 125行 / 2026-08-05 |
| `factory-core/assignment/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 35行 / 2026-08-05 |
| `factory-core/assignment/allocator.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 318行 / 2026-08-05 |
| `factory-core/assignment/matcher.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 85行 / 2026-08-05 |
| `factory-core/assignment/models.py` | Marketplace | Extension | 84行 / 2026-08-05 |
| `factory-core/assignment/store.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 143行 / 2026-08-05 |
| `factory-core/change/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 67行 / 2026-08-06 |
| `factory-core/change/analyzer.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 175行 / 2026-08-06 |
| `factory-core/change/events.py` | Observation | Core (Fact) | 123行 / 2026-08-06 |
| `factory-core/change/linker.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 170行 / 2026-08-06 |
| `factory-core/change/models.py` | Marketplace | Extension | 163行 / 2026-08-06 |
| `factory-core/change/service.py` | Web | Projection | 360行 / 2026-08-06 |
| `factory-core/changeflow/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 45行 / 2026-08-06 |
| `factory-core/changeflow/engine.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 386行 / 2026-08-06 |
| `factory-core/changeflow/events.py` | Observation | Core (Fact) | 160行 / 2026-08-06 |
| `factory-core/changeflow/models.py` | Marketplace | Extension | 164行 / 2026-08-06 |
| `factory-core/changeflow/rules.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 175行 / 2026-08-06 |
| `factory-core/changeflow/triggers.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 151行 / 2026-08-06 |
| `factory-core/cli/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 7行 / 2026-08-05 |
| `factory-core/cli/commands.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 3706行 / 2026-08-07 |
| `factory-core/cli/context.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 100行 / 2026-08-05 |
| `factory-core/cli/main.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 2605行 / 2026-08-07 |
| `factory-core/dashboard/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 36行 / 2026-08-06 |
| `factory-core/dashboard/collector.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 870行 / 2026-08-06 |
| `factory-core/dashboard/models.py` | Marketplace | Extension | 433行 / 2026-08-06 |
| `factory-core/dashboard/renderer.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 107行 / 2026-08-06 |
| `factory-core/dashboard/views.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 1009行 / 2026-08-06 |
| `factory-core/demo/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 14行 / 2026-08-06 |
| `factory-core/demo/markpad.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 426行 / 2026-08-06 |
| `factory-core/events/__init__.py` | Observation | Core (Fact, legacy L4) | 23行 / 2026-08-05 |
| `factory-core/events/logger.py` | Observation | Core (Fact, legacy L4) | 119行 / 2026-08-05 |
| `factory-core/events/metrics.py` | Observation | Core (Fact, legacy L4) | 174行 / 2026-08-05 |
| `factory-core/events/models.py` | Marketplace | Extension | 625行 / 2026-08-09 |
| `factory-core/events/store.py` | Observation | Core (Fact, legacy L4) | 227行 / 2026-08-05 |
| `factory-core/execution/__init__.py` | Execution | Core (legacy L4) | 44行 / 2026-08-05 |
| `factory-core/execution/dispatcher.py` | Execution | Core (legacy L4) | 109行 / 2026-08-05 |
| `factory-core/execution/runner.py` | Execution | Core (legacy L4) | 262行 / 2026-08-05 |
| `factory-core/execution/service.py` | Web | Projection | 82行 / 2026-08-05 |
| `factory-core/git/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 25行 / 2026-08-06 |
| `factory-core/git/client.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 279行 / 2026-08-06 |
| `factory-core/git/events.py` | Observation | Core (Fact) | 100行 / 2026-08-06 |
| `factory-core/git/models.py` | Marketplace | Extension | 103行 / 2026-08-06 |
| `factory-core/git/service.py` | Web | Projection | 229行 / 2026-08-06 |
| `factory-core/intelligence/__init__.py` | Memory-Learning | OS Service (legacy L4) | 208行 / 2026-08-06 |
| `factory-core/intelligence/decision.py` | Memory-Learning | OS Service (legacy L4) | 575行 / 2026-08-06 |
| `factory-core/intelligence/evaluate.py` | Memory-Learning | OS Service (legacy L4) | 216行 / 2026-08-06 |
| `factory-core/intelligence/events.py` | Observation | Core (Fact) | 420行 / 2026-08-06 |
| `factory-core/intelligence/experience.py` | Memory-Learning | OS Service (legacy L4) | 332行 / 2026-08-06 |
| `factory-core/intelligence/models.py` | Marketplace | Extension | 989行 / 2026-08-06 |
| `factory-core/intelligence/recommend.py` | Memory-Learning | OS Service (legacy L4) | 621行 / 2026-08-06 |
| `factory-core/intelligence/store.py` | Memory-Learning | OS Service (legacy L4) | 188行 / 2026-08-06 |
| `factory-core/metrics/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 53行 / 2026-08-06 |
| `factory-core/metrics/calculators.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 200行 / 2026-08-06 |
| `factory-core/metrics/collectors.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 87行 / 2026-08-06 |
| `factory-core/metrics/models.py` | Marketplace | Extension | 236行 / 2026-08-06 |
| `factory-core/metrics/reports.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 122行 / 2026-08-06 |
| `factory-core/metrics/store.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 68行 / 2026-08-06 |
| `factory-core/metrics/workspace.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 236行 / 2026-08-06 |
| `factory-core/orchestration/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 29行 / 2026-08-06 |
| `factory-core/orchestration/engine.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 380行 / 2026-08-06 |
| `factory-core/orchestration/events.py` | Observation | Core (Fact) | 132行 / 2026-08-06 |
| `factory-core/orchestration/pipeline.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 81行 / 2026-08-06 |
| `factory-core/product/__init__.py` | Memory-Learning | OS Service (legacy L4) | 67行 / 2026-08-06 |
| `factory-core/product/events.py` | Observation | Core (Fact) | 868行 / 2026-08-06 |
| `factory-core/product/experience.py` | Memory-Learning | OS Service (legacy L4) | 265行 / 2026-08-06 |
| `factory-core/product/generation.py` | Memory-Learning | OS Service (legacy L4) | 735行 / 2026-08-06 |
| `factory-core/product/lifecycle.py` | Memory-Learning | OS Service (legacy L4) | 783行 / 2026-08-06 |
| `factory-core/product/models.py` | Marketplace | Extension | 341行 / 2026-08-06 |
| `factory-core/product/service.py` | Web | Projection | 749行 / 2026-08-06 |
| `factory-core/product/store.py` | Memory-Learning | OS Service (legacy L4) | 255行 / 2026-08-06 |
| `factory-core/project/__init__.py` | Organization | OS Domain (Project, legacy L4) | 29行 / 2026-08-06 |
| `factory-core/project/loader.py` | Organization | OS Domain (Project, legacy L4) | 172行 / 2026-08-06 |
| `factory-core/project/models.py` | Marketplace | Extension | 135行 / 2026-08-06 |
| `factory-core/providers/__init__.py` | Factory | Extension (legacy L4) | 116行 / 2026-08-06 |
| `factory-core/providers/adapters/__init__.py` | Factory | Extension (legacy L4) | 26行 / 2026-08-06 |
| `factory-core/providers/adapters/hermes.py` | Factory | Extension (legacy L4) | 195行 / 2026-08-06 |
| `factory-core/providers/capability.py` | Factory | Extension (legacy L4) | 152行 / 2026-08-06 |
| `factory-core/providers/config.py` | Governance | Core Contract + OS Service | 89行 / 2026-08-06 |
| `factory-core/providers/costs.py` | Factory | Extension (legacy L4) | 189行 / 2026-08-06 |
| `factory-core/providers/definitions.py` | Factory | Extension (legacy L4) | 103行 / 2026-08-06 |
| `factory-core/providers/events.py` | Observation | Core (Fact) | 328行 / 2026-08-06 |
| `factory-core/providers/feedback.py` | Factory | Extension (legacy L4) | 176行 / 2026-08-06 |
| `factory-core/providers/integration.py` | Factory | Extension (legacy L4) | 263行 / 2026-08-06 |
| `factory-core/providers/models.py` | Marketplace | Extension | 235行 / 2026-08-06 |
| `factory-core/providers/provider.py` | Factory | Extension (legacy L4) | 70行 / 2026-08-06 |
| `factory-core/providers/registry.py` | Factory | Extension (legacy L4) | 175行 / 2026-08-06 |
| `factory-core/providers/selector.py` | Factory | Extension (legacy L4) | 494行 / 2026-08-06 |
| `factory-core/providers/store.py` | Factory | Extension (legacy L4) | 156行 / 2026-08-06 |
| `factory-core/providers/usage.py` | Factory | Extension (legacy L4) | 446行 / 2026-08-06 |
| `factory-core/recovery/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 23行 / 2026-08-06 |
| `factory-core/recovery/checkpoint.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 103行 / 2026-08-06 |
| `factory-core/recovery/models.py` | Marketplace | Extension | 98行 / 2026-08-06 |
| `factory-core/recovery/replay.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 245行 / 2026-08-06 |
| `factory-core/recovery/service.py` | Web | Projection | 342行 / 2026-08-06 |
| `factory-core/runtime/__init__.py` | Execution | Core (legacy L4) | 38行 / 2026-08-05 |
| `factory-core/runtime/adapter.py` | Execution | Core (legacy L4) | 43行 / 2026-08-05 |
| `factory-core/runtime/adapters/__init__.py` | Execution | Core (legacy L4) | 25行 / 2026-08-05 |
| `factory-core/runtime/adapters/echo.py` | Execution | Core (legacy L4) | 61行 / 2026-08-05 |
| `factory-core/runtime/adapters/hermes.py` | Execution | Core (legacy L4) | 166行 / 2026-08-05 |
| `factory-core/runtime/models.py` | Marketplace | Extension | 177行 / 2026-08-05 |
| `factory-core/runtime/registry.py` | Execution | Core (legacy L4) | 152行 / 2026-08-06 |
| `factory-core/runtime/store.py` | Execution | Core (legacy L4) | 189行 / 2026-08-05 |
| `factory-core/runtimes/__init__.py` | Execution | Core (legacy L4) | 31行 / 2026-08-06 |
| `factory-core/runtimes/catalog.py` | Execution | Core (legacy L4) | 163行 / 2026-08-06 |
| `factory-core/runtimes/definitions.py` | Execution | Core (legacy L4) | 79行 / 2026-08-06 |
| `factory-core/runtimes/models.py` | Marketplace | Extension | 133行 / 2026-08-06 |
| `factory-core/runtimes/store.py` | Execution | Core (legacy L4) | 125行 / 2026-08-06 |
| `factory-core/tasks/__init__.py` | Execution | Core (legacy L4) | 13行 / 2026-08-05 |
| `factory-core/tasks/models.py` | Marketplace | Extension | 71行 / 2026-08-05 |
| `factory-core/tasks/store.py` | Execution | Core (legacy L4) | 132行 / 2026-08-05 |
| `factory-core/understanding/__init__.py` | Memory-Learning | OS Service (legacy L4) | 87行 / 2026-08-06 |
| `factory-core/understanding/analyzers/__init__.py` | Memory-Learning | OS Service (legacy L4) | 34行 / 2026-08-06 |
| `factory-core/understanding/analyzers/artifact_detector.py` | Memory-Learning | OS Service (legacy L4) | 318行 / 2026-08-06 |
| `factory-core/understanding/analyzers/document_analyzer.py` | Memory-Learning | OS Service (legacy L4) | 56行 / 2026-08-06 |
| `factory-core/understanding/analyzers/project_analyzer.py` | Memory-Learning | OS Service (legacy L4) | 126行 / 2026-08-06 |
| `factory-core/understanding/events.py` | Observation | Core (Fact) | 117行 / 2026-08-06 |
| `factory-core/understanding/models.py` | Marketplace | Extension | 201行 / 2026-08-06 |
| `factory-core/understanding/service.py` | Web | Projection | 294行 / 2026-08-06 |
| `factory-core/validation/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 15行 / 2026-08-05 |
| `factory-core/validation/engine.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 170行 / 2026-08-06 |
| `factory-core/validation/models.py` | Marketplace | Extension | 47行 / 2026-08-05 |
| `factory-core/validation/reports.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 134行 / 2026-08-06 |
| `factory-core/validation/rules.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 200行 / 2026-08-06 |
| `factory-core/workflows/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 44行 / 2026-08-05 |
| `factory-core/workflows/definitions.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 93行 / 2026-08-05 |
| `factory-core/workflows/engine.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 512行 / 2026-08-05 |
| `factory-core/workflows/models.py` | Marketplace | Extension | 210行 / 2026-08-05 |
| `factory-core/workflows/store.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 172行 / 2026-08-05 |
| `factory-core/workspace/__init__.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 51行 / 2026-08-06 |
| `factory-core/workspace/config.py` | Governance | Core Contract + OS Service | 92行 / 2026-08-06 |
| `factory-core/workspace/loader.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 134行 / 2026-08-06 |
| `factory-core/workspace/manager.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 244行 / 2026-08-06 |
| `factory-core/workspace/models.py` | Marketplace | Extension | 107行 / 2026-08-06 |
| `factory-core/workspace/store.py` | UNCLEAR | UNCLEAR(宪法未覆盖 L4 包) | 51行 / 2026-08-06 |
| `factory-exec/exec/__init__.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 27行 / 2026-08-07 |
| `factory-exec/exec/agent_executor.py` | Organization | Org Model (Core 外) | 170行 / 2026-08-12 |
| `factory-exec/exec/agent_runtime.py` | Organization | Org Model (Core 外) | 704行 / 2026-08-25 |
| `factory-exec/exec/approval.py` | Approval-Service | OS Service (Core 留 Gate) | 242行 / 2026-08-20 |
| `factory-exec/exec/architect.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 605行 / 2026-08-09 |
| `factory-exec/exec/benchmark/__init__.py` | Factory | Extension | 13行 / 2026-08-07 |
| `factory-exec/exec/benchmark/bugs.py` | Factory | Extension | 135行 / 2026-08-07 |
| `factory-exec/exec/benchmark/features.py` | Factory | Extension | 84行 / 2026-08-07 |
| `factory-exec/exec/benchmark/greenfield.py` | Factory | Extension | 38行 / 2026-08-07 |
| `factory-exec/exec/benchmark/models.py` | Marketplace | Extension | 262行 / 2026-08-07 |
| `factory-exec/exec/benchmark/runner.py` | Factory | Extension | 1021行 / 2026-08-08 |
| `factory-exec/exec/benchmark/samples.py` | Factory | Extension | 24行 / 2026-08-07 |
| `factory-exec/exec/benchmark/verifiers.py` | Factory | Extension | 348行 / 2026-08-07 |
| `factory-exec/exec/budget.py` | Governance | Core Contract + OS Service | 476行 / 2026-08-07 |
| `factory-exec/exec/candidate.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 641行 / 2026-08-08 |
| `factory-exec/exec/capability.py` | Factory | Extension | 578行 / 2026-08-08 |
| `factory-exec/exec/cli.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 610行 / 2026-08-25 |
| `factory-exec/exec/context.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 971行 / 2026-08-07 |
| `factory-exec/exec/developer.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 756行 / 2026-08-25 |
| `factory-exec/exec/employee_executor.py` | Organization | Org Model (Core 外) | 264行 / 2026-08-08 |
| `factory-exec/exec/evaluator.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 429行 / 2026-08-08 |
| `factory-exec/exec/events.py` | Observation | Core (Fact) | 182行 / 2026-08-07 |
| `factory-exec/exec/execution_loop.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 878行 / 2026-08-13 |
| `factory-exec/exec/experience.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 129行 / 2026-08-07 |
| `factory-exec/exec/experience_ctx.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 923行 / 2026-08-07 |
| `factory-exec/exec/mcp.py` | Factory | Extension | 615行 / 2026-08-27 |
| `factory-exec/exec/models.py` | Marketplace | Extension | 296行 / 2026-09-04 |
| `factory-exec/exec/operations.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 437行 / 2026-08-07 |
| `factory-exec/exec/patch_filter.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 100行 / 2026-08-19 |
| `factory-exec/exec/pm.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 435行 / 2026-08-09 |
| `factory-exec/exec/progressive.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 837行 / 2026-08-07 |
| `factory-exec/exec/project_adoption.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 592行 / 2026-08-09 |
| `factory-exec/exec/provider.py` | Factory | Extension | 259行 / 2026-08-07 |
| `factory-exec/exec/providers/__init__.py` | Factory | Extension | 5行 / 2026-08-07 |
| `factory-exec/exec/providers/anthropic.py` | Factory | Extension | 209行 / 2026-08-07 |
| `factory-exec/exec/providers/openai.py` | Factory | Extension | 262行 / 2026-08-07 |
| `factory-exec/exec/ranking.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 2061行 / 2026-08-07 |
| `factory-exec/exec/release.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 586行 / 2026-08-09 |
| `factory-exec/exec/repo_index.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 528行 / 2026-08-07 |
| `factory-exec/exec/repo_intelligence.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 958行 / 2026-08-07 |
| `factory-exec/exec/roles.py` | Organization | Org Model (Core 外) | 365行 / 2026-08-09 |
| `factory-exec/exec/runtime_session.py` | Organization | Org Model (Core 外) | 480行 / 2026-08-13 |
| `factory-exec/exec/sandbox.py` | UNCLEAR | UNCLEAR(M3 旧执行链, 疑 dead) | 249行 / 2026-08-07 |
| `factory-exec/exec/skill.py` | Factory | Extension | 420行 / 2026-08-13 |
| `factory-exec/exec/store.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 260行 / 2026-08-07 |
| `factory-exec/exec/tester.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 446行 / 2026-08-09 |
| `factory-exec/exec/tool.py` | Factory | Extension | 397行 / 2026-08-13 |
| `factory-exec/exec/tools/__init__.py` | Factory | Extension | 0行 / 2026-08-13 |
| `factory-exec/exec/tools/filesystem.py` | Factory | Extension | 114行 / 2026-08-13 |
| `factory-exec/exec/uxui.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 517行 / 2026-08-09 |
| `factory-exec/exec/validation.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 144行 / 2026-08-07 |
| `factory-exec/scripts_diag_empty.py` | UNCLEAR | UNCLEAR(M3 旧执行链) | 76行 / 2026-08-07 |
| `factory-org/org/__init__.py` | Organization | Org Model (Core 外) | 16行 / 2026-08-07 |
| `factory-org/org/approval.py` | Approval-Service | OS Service (Core 留 Gate) | 191行 / 2026-08-09 |
| `factory-org/org/artifact.py` | Organization | Org Model (Core 外) | 658行 / 2026-08-09 |
| `factory-org/org/capabilities.py` | Organization | Org Model (Core 外) | 1557行 / 2026-08-11 |
| `factory-org/org/cli.py` | Organization | Org Model (Core 外) | 1352行 / 2026-08-24 |
| `factory-org/org/demo.py` | Organization | Org Model (Core 外) | 287行 / 2026-08-09 |
| `factory-org/org/events.py` | Observation | Core (Fact) | 1075行 / 2026-08-09 |
| `factory-org/org/execution.py` | Organization | Org Model (Core 外) | 1551行 / 2026-08-11 |
| `factory-org/org/lifecycle.py` | Organization | Org Model (Core 外) | 514行 / 2026-08-08 |
| `factory-org/org/management.py` | Organization | Org Model (Core 外) | 803行 / 2026-09-04 |
| `factory-org/org/models.py` | Marketplace | Extension | 193行 / 2026-08-08 |
| `factory-org/org/project_adoption.py` | Organization | Org Model (Core 外) | 532行 / 2026-08-24 |
| `factory-org/org/projects.py` | Organization | Org Model (Core 外) | 938行 / 2026-09-01 |
| `factory-org/org/registry.py` | Organization | Org Model (Core 外) | 102行 / 2026-08-07 |
| `factory-org/org/space.py` | Organization | Org Model (Core 外) | 274行 / 2026-08-11 |
| `factory-org/org/store.py` | Organization | Org Model (Core 外) | 396行 / 2026-09-01 |
| `factory-org/org/templates.py` | Organization | Org Model (Core 外) | 318行 / 2026-08-08 |
| `factory-org/org/workflow.py` | Organization | Org Model (Core 外) | 1295行 / 2026-08-09 |
| `factory-runtime/bundle/factory_runtime_entry.py` | Execution | Core (Runtime) | 16行 / 2026-08-07 |
| `factory-runtime/runtime/__init__.py` | Execution | Core (Runtime) | 22行 / 2026-08-07 |
| `factory-runtime/runtime/bundle.py` | Execution | Core (Runtime) | 54行 / 2026-08-07 |
| `factory-runtime/runtime/cli.py` | Execution | Core (Runtime) | 246行 / 2026-08-07 |
| `factory-runtime/runtime/errors.py` | Execution | Core (Runtime) | 11行 / 2026-08-07 |
| `factory-runtime/runtime/health.py` | Execution | Core (Runtime) | 159行 / 2026-08-07 |
| `factory-runtime/runtime/logging.py` | Execution | Core (Runtime) | 115行 / 2026-08-07 |
| `factory-runtime/runtime/manager.py` | Execution | Core (Runtime) | 577行 / 2026-08-07 |
| `factory-runtime/runtime/paths.py` | Execution | Core (Runtime) | 101行 / 2026-08-07 |
| `factory-runtime/runtime/state.py` | Execution | Core (Runtime) | 100行 / 2026-08-07 |
| `factory-runtime/runtime/watchdog.py` | Execution | Core (Runtime) | 127行 / 2026-08-07 |
| `factory-runtime/tests/test_bundle_contract.py` | Execution | Core (Runtime) | 85行 / 2026-08-07 |
| `scripts/coverage_report.py` | UNCLEAR | UNCLEAR(工具/演示) | 197行 / 2026-08-26 |
| `scripts/seed_plan_tasks.py` | UNCLEAR | UNCLEAR(工具/演示) | 242行 / 2026-08-26 |
| `scripts/smoke_24h.py` | UNCLEAR | UNCLEAR(工具/演示) | 48行 / 2026-08-26 |
| `scripts/smoke_longrun.py` | UNCLEAR | UNCLEAR(工具/演示) | 135行 / 2026-08-26 |

---

# 三份清单

## ① core 纯净性预测
拟进 Core 的文件中，是否含具体业务做法（golden/pipeline/workflow/backlog/具体角色名）：

| 检查 | 结果 |
|------|------|
| os_core_*.py 含 golden_path/pipeline/backlog/developer/architect 等 | **2 命中，但均为"否定式注释"**（os_core_runtime.py:3 "不重写 node_runtime/production_run"；os_core_work.py:6 "conversation_id 绝不作 work_id"） |
| **结论** | ✅ **core 候选纯净**（无业务做法）；仅注释提及，非实现依赖 |

> 真正含业务做法的是 canonical 链（golden_path/task_decomposition/production_run）→ 已归 `GoldenPath-Factory`（Extension），不进 Core。

## ② 反向依赖清单

| 检查 | 结果 |
|------|------|
| core-候选(os_core_*) import extensions/projections | **0 处** ✅ |
| projections(api/ web/) import extensions | **0 处** ✅ |
| **唯一越层** | `os_core_plugin.py` → `plugin_kernel`（Core 边界委托 Extension）→ 按铁律 3 应改依赖 SPI |
| **结论** | ✅ **无反向依赖违规**——分层方向当前基本正确 |

## ③ 双向真相清单（同时持有 状态+DTO+UI视图）

| 文件 | 视图/状态函数数 | 判定 |
|------|---------------|------|
| `factory-console/flow_views.py` | 1 | 纯视图（已归 Projection）✅ |
| `factory-console/operational_state.py` | 2 | 视图+状态 → **需拆**（State 归 Core，View 归 Projection） |
| `factory-console/control_tower.py` | 1 | 视图 → Projection ✅ |
| **结论** | — | **1 处需拆**（operational_state）；其余已纯视图 |

---

# UNCLEAR 说明（160 / 537 = 29%）

主要来源（**均为宪法未覆盖的旧域**，非分类失败）：
| 来源 | 数量 | 性质 |
|------|------|------|
| factory-console/session/*（M3 旧链残部） | 72 | M3 旧链，**CODE-REALITY 已证 dead** |
| factory-exec/exec/*（旧执行链） | 24 | M3 旧执行链 |
| factory-core/*（L4 旧数据层包: change/changeflow/git/metrics/recovery/validation/workflows/workspace/...） | ~40 | L4 legacy（宪法未列这些域） |
| scripts/ demo/ 其他 | ~24 | 工具/演示 |

**建议**：这些 UNCLEAR **不作逐条宪法映射**（宪法未覆盖），统一归 `archive/legacy`（Step 4 处置）；其中 `session/*` 72 个已由 CODE-REALITY 判定 dead。

---

# HARD STOP

纯只读：未搬家、未建目录、未改 import、未改代码、未删文件、未推分支。
v2 裁定表 + 三份清单已产出 → 停下等裁决。
