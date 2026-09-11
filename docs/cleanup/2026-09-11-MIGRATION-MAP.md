# MIGRATION_MAP（清理启动 — 逐文件归属）

> 日期: 2026-09-11 | 只读产出（未搬家/未建目标目录/未改 import/未删文件）
> 目标五层: kernel / services / extensions / projections / infrastructure / bootstrap
> 源码文件: 542 | tests 文件: 736（跟随被测代码，见文末）

## 源码文件（逐行）

| 现路径 | 归属层 | 目标路径 | 依据 | 依赖方向检查 | 备注 |
|---|---|---|---|---|---|
| `demo/repo/main.py` | archive | `archive/demo/main.py` | 演示 | ok | 2026-08-20 |
| `demo/repo/test_main.py` | archive | `archive/demo/test_main.py` | 演示 | ok | 2026-08-20 |
| `docs/validation/tests/test_validation_tools.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-07 |
| `docs/validation/tools/phase_a_validation.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-07 |
| `docs/validation/tools/verify_search_fix.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-07 |
| `factory-console/__init__.py` | bootstrap | `bootstrap/__init__.py` | 装配/入口脚本 | ok | 2026-08-18 |
| `factory-console/acceptance_truth.py` | extensions.factories | `extensions/factories/software/acceptance_truth.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-06 |
| `factory-console/adaptive_workforce.py` | services.organization | `services/organization/adaptive_workforce.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-30 |
| `factory-console/agent_kernel.py` | services.organization | `services/organization/agent_kernel.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-29 |
| `factory-console/agent_policy.py` | kernel.governance | `kernel/governance/agent_policy.py` | 审批/预算/审计挂点 | ok | 2026-08-14 契约 |
| `factory-console/api/__init__.py` | projections.gateway | `projections/gateway/__init__.py` | API 网关 | ok | 2026-08-26 |
| `factory-console/api/agent_executor.py` | projections.gateway | `projections/gateway/agent_executor.py` | API 网关 | ok | 2026-08-12 |
| `factory-console/api/approvals.py` | services.approval_runtime | `services/approval_runtime/approvals.py` | 审批流程服务 | ok | 2026-08-09 |
| `factory-console/api/artifacts.py` | projections.gateway | `projections/gateway/artifacts.py` | API 网关 | ok | 2026-08-10 |
| `factory-console/api/audit.py` | projections.gateway | `projections/gateway/audit.py` | API 网关 | ok | 2026-08-17 |
| `factory-console/api/backlog.py` | projections.gateway | `projections/gateway/backlog.py` | API 网关 | ok | 2026-08-26 |
| `factory-console/api/debug.py` | projections.gateway | `projections/gateway/debug.py` | API 网关 | ok | 2026-08-17 |
| `factory-console/api/decisions.py` | projections.gateway | `projections/gateway/decisions.py` | API 网关 | ok | 2026-08-06 |
| `factory-console/api/flow.py` | projections.gateway | `projections/gateway/flow.py` | API 网关 | ok | 2026-09-11 |
| `factory-console/api/intelligence.py` | projections.gateway | `projections/gateway/intelligence.py` | API 网关 | ok | 2026-08-06 |
| `factory-console/api/lifecycle.py` | projections.gateway | `projections/gateway/lifecycle.py` | API 网关 | ok | 2026-08-06 |
| `factory-console/api/mcp_api.py` | projections.gateway | `projections/gateway/mcp_api.py` | API 网关 | ok | 2026-08-27 |
| `factory-console/api/memory.py` | projections.gateway | `projections/gateway/memory.py` | API 网关 | ok | 2026-08-17 |
| `factory-console/api/product_intelligence.py` | projections.gateway | `projections/gateway/product_intelligence.py` | API 网关 | ok | 2026-08-17 |
| `factory-console/api/projects.py` | projections.gateway | `projections/gateway/projects.py` | API 网关 | ok | 2026-09-01 |
| `factory-console/api/providers.py` | projections.gateway | `projections/gateway/providers.py` | API 网关 | ok | 2026-08-06 |
| `factory-console/api/review_feedback.py` | kernel.governance | `kernel/governance/review_feedback.py` | 审批/预算/审计挂点 | ok | 2026-08-10 误归 |
| `factory-console/api/runtime.py` | projections.gateway | `projections/gateway/runtime.py` | API 网关 | ok | 2026-09-07 |
| `factory-console/api/runtime_session.py` | projections.gateway | `projections/gateway/runtime_session.py` | API 网关 | ok | 2026-08-12 |
| `factory-console/api/skill_api.py` | projections.gateway | `projections/gateway/skill_api.py` | API 网关 | ok | 2026-08-13 |
| `factory-console/api/sprint.py` | projections.gateway | `projections/gateway/sprint.py` | API 网关 | ok | 2026-08-11 |
| `factory-console/api/tool_api.py` | projections.gateway | `projections/gateway/tool_api.py` | API 网关 | ok | 2026-08-13 |
| `factory-console/api/workflow_start.py` | projections.gateway | `projections/gateway/workflow_start.py` | API 网关 | ok | 2026-08-10 |
| `factory-console/api/workflows.py` | projections.gateway | `projections/gateway/workflows.py` | API 网关 | ok | 2026-08-09 |
| `factory-console/application_formalization.py` | extensions.factories | `extensions/factories/software/application_formalization.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-08 |
| `factory-console/artifact_contract.py` | extensions.factories | `extensions/factories/software/artifact_contract.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-26 |
| `factory-console/artifact_lifecycle.py` | extensions.factories | `extensions/factories/software/artifact_lifecycle.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-05 |
| `factory-console/audit/__init__.py` | kernel.events | `kernel/events/__init__.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/audit_chain.py` | kernel.events | `kernel/events/audit_chain.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/audit_context.py` | kernel.events | `kernel/events/audit_context.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/audit_emitter.py` | kernel.events | `kernel/events/audit_emitter.py` | 唯一事实源(append-only) | ok | 2026-08-25 契约 |
| `factory-console/audit/audit_event.py` | kernel.events | `kernel/events/audit_event.py` | 唯一事实源(append-only) | ok | 2026-09-09 契约 |
| `factory-console/audit/audit_explain.py` | kernel.events | `kernel/events/audit_explain.py` | 唯一事实源(append-only) | ok | 2026-08-17 降级(无契约) |
| `factory-console/audit/audit_integrity.py` | kernel.events | `kernel/events/audit_integrity.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/audit_query.py` | kernel.events | `kernel/events/audit_query.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/audit_store.py` | kernel.events | `kernel/events/audit_store.py` | 唯一事实源(append-only) | ok | 2026-08-17 契约 |
| `factory-console/audit/trace_context.py` | kernel.events | `kernel/events/trace_context.py` | 唯一事实源(append-only) | ok | 2026-08-25 契约 |
| `factory-console/backup.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-27 |
| `factory-console/canonical_golden_path.py` | extensions.factories | `extensions/factories/software/canonical_golden_path.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-09 |
| `factory-console/chat_store.py` | kernel.conversation | `kernel/conversation/chat_store.py` | 会话=唯一业务入口 | ok | 2026-08-10 契约 |
| `factory-console/cli_doctor.py` | projections.cli | `projections/cli/cli_doctor.py` | 人类控制台 | ok | 2026-08-19 |
| `factory-console/cli_factory.py` | projections.cli | `projections/cli/cli_factory.py` | 人类控制台 | ok | 2026-09-09 |
| `factory-console/cli_services.py` | projections.cli | `projections/cli/cli_services.py` | 人类控制台 | ok | 2026-08-24 |
| `factory-console/config.py` | kernel.governance | `kernel/governance/config.py` | 审批/预算/审计挂点 | ok | 2026-08-10 误归 |
| `factory-console/console_sessions.py` | kernel.conversation | `kernel/conversation/console_sessions.py` | 会话=唯一业务入口 | ok | 2026-09-02 契约 |
| `factory-console/context_intelligence.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-31 |
| `factory-console/context_runtime.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-08-31 |
| `factory-console/control_tower.py` | projections.web | `projections/web/control_tower.py` | 控制台服务/视图 | ok | 2026-08-31 |
| `factory-console/conversation_app.py` | kernel.conversation | `kernel/conversation/conversation_app.py` | 会话=唯一业务入口 | ok | 2026-09-09 契约 |
| `factory-console/conversation_os.py` | kernel.conversation | `kernel/conversation/conversation_os.py` | 会话=唯一业务入口 | ok | 2026-09-08 降级(无契约) |
| `factory-console/conversation_quality.py` | kernel.conversation | `kernel/conversation/conversation_quality.py` | 会话=唯一业务入口 | ok | 2026-08-31 降级(无契约) |
| `factory-console/effectiveness_service.py` | extensions.factories | `extensions/factories/software/effectiveness_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-10 契约 |
| `factory-console/evidence_domain.py` | kernel.events | `kernel/events/evidence_domain.py` | 唯一事实源(append-only) | ok | 2026-09-05 契约 |
| `factory-console/exec_checkpoint.py` | kernel.node | `kernel/node/exec_checkpoint.py` | 执行节点原语 | ok | 2026-08-27 契约 |
| `factory-console/experience_bridge.py` | services.memory | `services/memory/experience_bridge.py` | 记忆/学习服务 | ok | 2026-09-06 |
| `factory-console/experiment_reliability.py` | extensions.factories | `extensions/factories/software/experiment_reliability.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/external_executor/__init__.py` | extensions.models | `extensions/models/__init__.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/asset_parsers.py` | extensions.models | `extensions/models/asset_parsers.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/executor.py` | extensions.models | `extensions/models/executor.py` | Model/Provider 插件 | ok | 2026-09-04 |
| `factory-console/external_executor/gateway.py` | extensions.models | `extensions/models/gateway.py` | Model/Provider 插件 | ok | 2026-09-04 |
| `factory-console/external_executor/host_assets.py` | extensions.models | `extensions/models/host_assets.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/metrics.py` | extensions.models | `extensions/models/metrics.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/monitor_detail.py` | extensions.models | `extensions/models/monitor_detail.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/registry.py` | extensions.models | `extensions/models/registry.py` | Model/Provider 插件 | ok | 2026-08-28 |
| `factory-console/external_executor/router.py` | extensions.models | `extensions/models/router.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/external_executor/schema.py` | extensions.models | `extensions/models/schema.py` | Model/Provider 插件 | ok | 2026-08-28 |
| `factory-console/external_executor/task_registry.py` | extensions.models | `extensions/models/task_registry.py` | Model/Provider 插件 | ok | 2026-08-28 |
| `factory-console/external_skills.py` | kernel.capability | `kernel/capability/external_skills.py` | 能力注册与解析(找谁做) | ok | 2026-08-27 契约 |
| `factory-console/flow_views.py` | projections.web | `projections/web/flow_views.py` | 控制台服务/视图 | ok | 2026-09-11 |
| `factory-console/golden_path.py` | extensions.factories | `extensions/factories/software/golden_path.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-09 |
| `factory-console/golden_suite.py` | projections.web | `projections/web/golden_suite.py` | 控制台服务/视图 | ok | 2026-08-31 |
| `factory-console/governance_service.py` | kernel.governance | `kernel/governance/governance_service.py` | 审批/预算/审计挂点 | ok | 2026-09-06 契约 |
| `factory-console/health_service.py` | projections.web | `projections/web/health_service.py` | 控制台服务/视图 | ok | 2026-08-30 |
| `factory-console/ids.py` | kernel.events | `kernel/events/ids.py` | 唯一事实源(append-only) | ok | 2026-09-01 契约 |
| `factory-console/integrity_lock.py` | kernel.governance | `kernel/governance/integrity_lock.py` | 审批/预算/审计挂点 | ok | 2026-08-30 降级(无契约) |
| `factory-console/intelligence_strategy.py` | extensions.factories | `extensions/factories/software/intelligence_strategy.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-31 |
| `factory-console/learning_engine_v2.py` | services.memory | `services/memory/learning_engine_v2.py` | 记忆/学习服务 | ok | 2026-08-31 |
| `factory-console/learning_truth.py` | services.memory | `services/memory/learning_truth.py` | 记忆/学习服务 | ok | 2026-09-06 |
| `factory-console/llm_control.py` | kernel.governance | `kernel/governance/llm_control.py` | 审批/预算/审计挂点 | ok | 2026-08-13 契约 |
| `factory-console/llm_experiment_service.py` | extensions.factories | `extensions/factories/software/llm_experiment_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/llm_router.py` | extensions.models | `extensions/models/llm_router.py` | Model/Provider 插件 | ok | 2026-08-14 |
| `factory-console/llm_semantic_interpreter.py` | kernel.conversation | `kernel/conversation/llm_semantic_interpreter.py` | 会话=唯一业务入口 | ok | 2026-09-08 契约 |
| `factory-console/local_ai.py` | extensions.models | `extensions/models/local_ai.py` | Model/Provider 插件 | ok | 2026-08-27 |
| `factory-console/memory/__init__.py` | services.memory | `services/memory/__init__.py` | 记忆/学习服务 | ok | 2026-08-25 |
| `factory-console/memory/auto_learn.py` | services.memory | `services/memory/auto_learn.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/decision_memory.py` | services.memory | `services/memory/decision_memory.py` | 记忆/学习服务 | ok | 2026-08-25 |
| `factory-console/memory/experience.py` | services.memory | `services/memory/experience.py` | 记忆/学习服务 | ok | 2026-09-06 |
| `factory-console/memory/experience_store.py` | services.memory | `services/memory/experience_store.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/extraction.py` | services.memory | `services/memory/extraction.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/learning_engine.py` | services.memory | `services/memory/learning_engine.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/learning_guards.py` | services.memory | `services/memory/learning_guards.py` | 记忆/学习服务 | ok | 2026-08-25 |
| `factory-console/memory/learning_loop.py` | services.memory | `services/memory/learning_loop.py` | 记忆/学习服务 | ok | 2026-08-25 |
| `factory-console/memory/learning_trace.py` | services.memory | `services/memory/learning_trace.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/recommendation.py` | services.memory | `services/memory/recommendation.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/memory/retrieval.py` | services.memory | `services/memory/retrieval.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/model_catalog.py` | extensions.models | `extensions/models/model_catalog.py` | Model/Provider 插件 | ok | 2026-08-13 |
| `factory-console/models.py` | extensions.models | `extensions/models/models.py` | Model/Provider 插件 | ok | 2026-08-29 |
| `factory-console/monitor.py` | projections.web | `projections/web/monitor.py` | 控制台服务/视图 | ok | 2026-09-01 |
| `factory-console/node_runtime.py` | kernel.node | `kernel/node/node_runtime.py` | 执行节点原语 | ok | 2026-09-11 契约 |
| `factory-console/operational_state.py` | projections.web | `projections/web/operational_state.py` | 控制台服务/视图 | ok | 2026-08-31 |
| `factory-console/ops_projection.py` | extensions.workloads | `extensions/workloads/ops_projection.py` | Workload 插件 | ok | 2026-08-30 |
| `factory-console/ops_scheduler.py` | kernel.scheduler | `kernel/scheduler/ops_scheduler.py` | 调度契约 | ok | 2026-08-30 降级(无契约) |
| `factory-console/optimization_engine.py` | extensions.factories | `extensions/factories/software/optimization_engine.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-31 |
| `factory-console/optimization_service.py` | extensions.factories | `extensions/factories/software/optimization_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/os_core_capability.py` | kernel.capability | `kernel/capability/os_core_capability.py` | 能力注册与解析(找谁做) | ok | 2026-09-10 契约 |
| `factory-console/os_core_company_organization.py` | services.organization | `services/organization/os_core_company_organization.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-console/os_core_evidence.py` | kernel.events | `kernel/events/os_core_evidence.py` | 唯一事实源(append-only) | ok | 2026-09-10 契约 |
| `factory-console/os_core_execution.py` | kernel.node | `kernel/node/os_core_execution.py` | 执行节点原语 | ok | 2026-09-10 契约 |
| `factory-console/os_core_identity.py` | services.organization | `services/organization/os_core_identity.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-console/os_core_outcome.py` | kernel.events | `kernel/events/os_core_outcome.py` | 唯一事实源(append-only) | ok | 2026-09-10 契约 |
| `factory-console/os_core_plugin.py` | kernel.capability | `kernel/capability/os_core_plugin.py` | 能力注册与解析(找谁做) | ok | 2026-09-10 契约 |
| `factory-console/os_core_professional.py` | services.organization | `services/organization/os_core_professional.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-console/os_core_project.py` | services.work | `services/work/os_core_project.py` | 项目/工作域 | ok | 2026-09-10 |
| `factory-console/os_core_resolution.py` | kernel.capability | `kernel/capability/os_core_resolution.py` | 能力注册与解析(找谁做) | ok | 2026-09-10 契约 |
| `factory-console/os_core_role.py` | services.organization | `services/organization/os_core_role.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-console/os_core_runtime.py` | kernel.node | `kernel/node/os_core_runtime.py` | 执行节点原语 | ok | 2026-09-10 契约 |
| `factory-console/os_core_scheduler.py` | kernel.scheduler | `kernel/scheduler/os_core_scheduler.py` | 调度契约 | ok | 2026-09-10 契约 |
| `factory-console/os_core_task.py` | kernel.node | `kernel/node/os_core_task.py` | 执行节点原语 | ok | 2026-09-10 契约 |
| `factory-console/os_core_task_node.py` | kernel.node | `kernel/node/os_core_task_node.py` | 执行节点原语 | ok | 2026-09-10 契约 |
| `factory-console/os_core_usage.py` | kernel.events | `kernel/events/os_core_usage.py` | 唯一事实源(append-only) | ok | 2026-09-10 契约 |
| `factory-console/os_core_verification.py` | kernel.events | `kernel/events/os_core_verification.py` | 唯一事实源(append-only) | ok | 2026-09-10 契约 |
| `factory-console/os_core_work.py` | services.work | `services/work/os_core_work.py` | 项目/工作域 | ok | 2026-09-10 |
| `factory-console/os_core_workforce.py` | services.organization | `services/organization/os_core_workforce.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-console/performance_selection.py` | services.organization | `services/organization/performance_selection.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-31 |
| `factory-console/plugin_kernel.py` | kernel.capability | `kernel/capability/plugin_kernel.py` | 能力注册与解析(找谁做) | ok | 2026-08-31 契约 |
| `factory-console/product_truth.py` | extensions.factories | `extensions/factories/software/product_truth.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-09 |
| `factory-console/product_understanding.py` | kernel.conversation | `kernel/conversation/product_understanding.py` | 会话=唯一业务入口 | ok | 2026-09-08 契约 |
| `factory-console/production_evaluation.py` | extensions.factories | `extensions/factories/software/production_evaluation.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/production_experience.py` | services.memory | `services/memory/production_experience.py` | 记忆/学习服务 | ok | 2026-08-30 |
| `factory-console/production_guidance.py` | extensions.factories | `extensions/factories/software/production_guidance.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/production_intelligence.py` | extensions.factories | `extensions/factories/software/production_intelligence.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/production_run.py` | extensions.factories | `extensions/factories/software/production_run.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-11 |
| `factory-console/production_runtime.py` | kernel.node | `kernel/node/production_runtime.py` | 执行节点原语 | ok | 2026-09-09 降级(无契约) |
| `factory-console/production_service.py` | extensions.factories | `extensions/factories/software/production_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-29 |
| `factory-console/professional_workflow.py` | extensions.factories | `extensions/factories/software/professional_workflow.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-31 |
| `factory-console/project_agile.py` | services.work | `services/work/project_agile.py` | 项目/工作域 | ok | 2026-09-11 |
| `factory-console/project_os.py` | services.work | `services/work/project_os.py` | 项目/工作域 | ok | 2026-08-31 |
| `factory-console/project_ssot.py` | services.work | `services/work/project_ssot.py` | 项目/工作域 | ok | 2026-09-01 |
| `factory-console/promotion_service.py` | extensions.factories | `extensions/factories/software/promotion_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-31 |
| `factory-console/recovery.py` | extensions.factories | `extensions/factories/software/recovery.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-29 |
| `factory-console/recovery_service.py` | extensions.factories | `extensions/factories/software/recovery_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/release_service.py` | extensions.factories | `extensions/factories/software/release_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/release_truth.py` | extensions.factories | `extensions/factories/software/release_truth.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-06 |
| `factory-console/requirement_analysis_node.py` | extensions.factories | `extensions/factories/software/requirement_analysis_node.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-07 |
| `factory-console/retrieval/__init__.py` | services.knowledge | `services/knowledge/__init__.py` | RAG/知识服务 | ok | 2026-08-26 |
| `factory-console/retrieval/external_source.py` | services.knowledge | `services/knowledge/external_source.py` | RAG/知识服务 | ok | 2026-08-26 |
| `factory-console/retrieval/knowledge_store.py` | services.knowledge | `services/knowledge/knowledge_store.py` | RAG/知识服务 | ok | 2026-08-26 |
| `factory-console/retrieval/models.py` | services.knowledge | `services/knowledge/models.py` | RAG/知识服务 | ok | 2026-08-17 |
| `factory-console/retrieval/orchestrator.py` | services.knowledge | `services/knowledge/orchestrator.py` | RAG/知识服务 | ok | 2026-08-17 |
| `factory-console/retrieval/retriever.py` | services.knowledge | `services/knowledge/retriever.py` | RAG/知识服务 | ok | 2026-08-17 |
| `factory-console/retrieval/unified.py` | services.knowledge | `services/knowledge/unified.py` | RAG/知识服务 | ok | 2026-08-17 |
| `factory-console/retry_policy.py` | kernel.node | `kernel/node/retry_policy.py` | 执行节点原语 | ok | 2026-08-30 契约 |
| `factory-console/review_feedback.py` | kernel.governance | `kernel/governance/review_feedback.py` | 审批/预算/审计挂点 | ok | 2026-08-10 契约 |
| `factory-console/rollback_service.py` | extensions.factories | `extensions/factories/software/rollback_service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-30 |
| `factory-console/run_liveness.py` | kernel.node | `kernel/node/run_liveness.py` | 执行节点原语 | ok | 2026-09-01 契约 |
| `factory-console/runtime_store.py` | kernel.node | `kernel/node/runtime_store.py` | 执行节点原语 | ok | 2026-08-10 契约 |
| `factory-console/self_healing.py` | extensions.factories | `extensions/factories/software/self_healing.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-31 |
| `factory-console/semantic_proposal.py` | kernel.conversation | `kernel/conversation/semantic_proposal.py` | 会话=唯一业务入口 | ok | 2026-09-08 契约 |
| `factory-console/service.py` | projections.web | `projections/web/service.py` | 控制台服务/视图 | ok | 2026-09-02 |
| `factory-console/session/__init__.py` | archive | `archive/session-m3/__init__.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-15 |
| `factory-console/session/action.py` | archive | `archive/session-m3/action.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-15 |
| `factory-console/session/actions.py` | archive | `archive/session-m3/actions.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-06 |
| `factory-console/session/actions_audit.py` | archive | `archive/session-m3/actions_audit.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/actions_debug.py` | archive | `archive/session-m3/actions_debug.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/actions_memory.py` | archive | `archive/session-m3/actions_memory.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/agent_entity.py` | services.organization | `services/organization/agent_entity.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-22 |
| `factory-console/session/agent_loop.py` | archive | `archive/session-m3/agent_loop.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-08 |
| `factory-console/session/agent_registry.py` | services.organization | `services/organization/agent_registry.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-22 |
| `factory-console/session/agents.py` | services.organization | `services/organization/agents.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-25 |
| `factory-console/session/analysis_tools.py` | archive | `archive/session-m3/analysis_tools.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-01 |
| `factory-console/session/answer_verify.py` | kernel.conversation | `kernel/conversation/answer_verify.py` | 会话=唯一业务入口 | ok | 2026-09-01 降级(无契约) |
| `factory-console/session/approval_store.py` | services.approval_runtime | `services/approval_runtime/approval_store.py` | 审批流程服务 | ok | 2026-08-28 |
| `factory-console/session/artifact_registry.py` | archive | `archive/session-m3/artifact_registry.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-22 |
| `factory-console/session/audit.py` | archive | `archive/session-m3/audit.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-15 |
| `factory-console/session/board.py` | projections.cli | `projections/cli/board.py` | 人类控制台 | ok | 2026-08-26 |
| `factory-console/session/budget.py` | archive | `archive/session-m3/budget.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/canonical_shell.py` | projections.cli | `projections/cli/canonical_shell.py` | 人类控制台 | ok | 2026-09-09 |
| `factory-console/session/capability_router.py` | kernel.capability | `kernel/capability/capability_router.py` | 能力注册与解析(找谁做) | ok | 2026-08-25 契约 |
| `factory-console/session/change_control.py` | archive | `archive/session-m3/change_control.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-26 |
| `factory-console/session/chat.py` | archive | `archive/session-m3/chat.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-27 |
| `factory-console/session/code_scan.py` | archive | `archive/session-m3/code_scan.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/commands.py` | projections.cli | `projections/cli/commands.py` | 人类控制台 | ok | 2026-08-25 |
| `factory-console/session/completion.py` | archive | `archive/session-m3/completion.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-15 |
| `factory-console/session/confirm.py` | archive | `archive/session-m3/confirm.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/conflicts.py` | archive | `archive/session-m3/conflicts.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/context.py` | services.memory | `services/memory/context.py` | 记忆/学习服务 | ok | 2026-08-15 |
| `factory-console/session/context_builder.py` | services.memory | `services/memory/context_builder.py` | 记忆/学习服务 | ok | 2026-08-16 |
| `factory-console/session/context_layers.py` | services.memory | `services/memory/context_layers.py` | 记忆/学习服务 | ok | 2026-08-29 |
| `factory-console/session/context_ledger.py` | services.memory | `services/memory/context_ledger.py` | 记忆/学习服务 | ok | 2026-08-17 |
| `factory-console/session/conversation.py` | kernel.conversation | `kernel/conversation/conversation.py` | 会话=唯一业务入口 | ok | 2026-08-25 误归 |
| `factory-console/session/core_loader.py` | archive | `archive/session-m3/core_loader.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-22 |
| `factory-console/session/cost_ledger.py` | archive | `archive/session-m3/cost_ledger.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/critical_path.py` | archive | `archive/session-m3/critical_path.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-23 |
| `factory-console/session/debug/__init__.py` | archive | `archive/session-m3/__init__.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/context_budget.py` | archive | `archive/session-m3/context_budget.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_engine.py` | archive | `archive/session-m3/debug_engine.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_memory.py` | archive | `archive/session-m3/debug_memory.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_pipeline.py` | archive | `archive/session-m3/debug_pipeline.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_session.py` | archive | `archive/session-m3/debug_session.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_strategy.py` | archive | `archive/session-m3/debug_strategy.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/debug_trace.py` | archive | `archive/session-m3/debug_trace.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/error_analysis.py` | archive | `archive/session-m3/error_analysis.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/repair_safety.py` | archive | `archive/session-m3/repair_safety.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/retrieval_policy.py` | archive | `archive/session-m3/retrieval_policy.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/root_cause.py` | archive | `archive/session-m3/root_cause.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/strategy_adaptation.py` | archive | `archive/session-m3/strategy_adaptation.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/debug/workspace_executor.py` | archive | `archive/session-m3/workspace_executor.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-17 |
| `factory-console/session/decision.py` | archive | `archive/session-m3/decision.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/decomposer.py` | archive | `archive/session-m3/decomposer.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/decomposition_evaluator.py` | archive | `archive/session-m3/decomposition_evaluator.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/delivery.py` | archive | `archive/session-m3/delivery.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-29 |
| `factory-console/session/dependencies.py` | archive | `archive/session-m3/dependencies.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/dialog_style.py` | kernel.conversation | `kernel/conversation/dialog_style.py` | 会话=唯一业务入口 | ok | 2026-08-27 降级(无契约) |
| `factory-console/session/discovery.py` | archive | `archive/session-m3/discovery.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/discovery_guide.py` | archive | `archive/session-m3/discovery_guide.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/discovery_intelligence.py` | archive | `archive/session-m3/discovery_intelligence.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/eval_judge.py` | archive | `archive/session-m3/eval_judge.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-27 |
| `factory-console/session/eval_loop.py` | archive | `archive/session-m3/eval_loop.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/eval_suite.py` | archive | `archive/session-m3/eval_suite.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-26 |
| `factory-console/session/evidence.py` | archive | `archive/session-m3/evidence.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/exec_state.py` | archive | `archive/session-m3/exec_state.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-02 |
| `factory-console/session/execution_policy.py` | archive | `archive/session-m3/execution_policy.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/execution_quality.py` | archive | `archive/session-m3/execution_quality.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/execution_replay.py` | archive | `archive/session-m3/execution_replay.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/execution_truth.py` | archive | `archive/session-m3/execution_truth.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-02 |
| `factory-console/session/expert_factory.py` | services.organization | `services/organization/expert_factory.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-25 |
| `factory-console/session/external_tools.py` | extensions.tools | `extensions/tools/external_tools.py` | Tool 插件 | ok | 2026-08-27 |
| `factory-console/session/gap_analyzer.py` | archive | `archive/session-m3/gap_analyzer.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/handoff.py` | archive | `archive/session-m3/handoff.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/handoff_bus.py` | archive | `archive/session-m3/handoff_bus.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-22 |
| `factory-console/session/intent.py` | kernel.conversation | `kernel/conversation/intent.py` | 会话=唯一业务入口 | ok | 2026-08-25 契约 |
| `factory-console/session/intent_core.py` | kernel.conversation | `kernel/conversation/intent_core.py` | 会话=唯一业务入口 | ok | 2026-09-07 契约 |
| `factory-console/session/lifecycle_store.py` | archive | `archive/session-m3/lifecycle_store.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/llm_gap.py` | archive | `archive/session-m3/llm_gap.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/llm_gateway.py` | extensions.models | `extensions/models/llm_gateway.py` | Model/Provider 插件 | ok | 2026-08-31 |
| `factory-console/session/llm_intent.py` | archive | `archive/session-m3/llm_intent.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/llm_task_proposal.py` | archive | `archive/session-m3/llm_task_proposal.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/loop_guard.py` | archive | `archive/session-m3/loop_guard.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/mcp_client.py` | extensions.mcp | `extensions/mcp/mcp_client.py` | MCP 插件 | ok | 2026-08-31 |
| `factory-console/session/mcp_tools.py` | extensions.mcp | `extensions/mcp/mcp_tools.py` | MCP 插件 | ok | 2026-08-28 |
| `factory-console/session/memory_core.py` | services.memory | `services/memory/memory_core.py` | 记忆/学习服务 | ok | 2026-08-28 |
| `factory-console/session/messages.py` | kernel.conversation | `kernel/conversation/messages.py` | 会话=唯一业务入口 | ok | 2026-08-15 契约 |
| `factory-console/session/model_prompt.py` | extensions.models | `extensions/models/model_prompt.py` | Model/Provider 插件 | ok | 2026-09-01 |
| `factory-console/session/naming.py` | archive | `archive/session-m3/naming.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-19 |
| `factory-console/session/observability.py` | projections.cli | `projections/cli/observability.py` | 人类控制台 | ok | 2026-08-31 |
| `factory-console/session/orchestrator.py` | archive | `archive/session-m3/orchestrator.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-02 |
| `factory-console/session/pipeline.py` | archive | `archive/session-m3/pipeline.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/pipeline_runner.py` | archive | `archive/session-m3/pipeline_runner.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-22 |
| `factory-console/session/plan_critic.py` | archive | `archive/session-m3/plan_critic.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/planning_trace.py` | archive | `archive/session-m3/planning_trace.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/product.py` | archive | `archive/session-m3/product.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-19 |
| `factory-console/session/product_intelligence.py` | extensions.workloads | `extensions/workloads/product_intelligence.py` | Workload 插件 | ok | 2026-08-17 |
| `factory-console/session/production_session.py` | archive | `archive/session-m3/production_session.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/progress.py` | projections.cli | `projections/cli/progress.py` | 人类控制台 | ok | 2026-08-15 |
| `factory-console/session/progress_card.py` | projections.cli | `projections/cli/progress_card.py` | 人类控制台 | ok | 2026-08-28 |
| `factory-console/session/project_memory.py` | services.memory | `services/memory/project_memory.py` | 记忆/学习服务 | ok | 2026-08-29 |
| `factory-console/session/project_scan.py` | services.work | `services/work/project_scan.py` | 项目/工作域 | ok | 2026-09-01 |
| `factory-console/session/quality.py` | archive | `archive/session-m3/quality.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-15 |
| `factory-console/session/query_engine.py` | archive | `archive/session-m3/query_engine.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-09-07 |
| `factory-console/session/reasoning.py` | archive | `archive/session-m3/reasoning.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-18 |
| `factory-console/session/renderer.py` | projections.cli | `projections/cli/renderer.py` | 人类控制台 | ok | 2026-08-24 |
| `factory-console/session/replanning.py` | archive | `archive/session-m3/replanning.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/repo_map.py` | services.work | `services/work/repo_map.py` | 项目/工作域 | ok | 2026-08-28 |
| `factory-console/session/repo_mode.py` | services.work | `services/work/repo_mode.py` | 项目/工作域 | ok | 2026-08-20 |
| `factory-console/session/review_gate.py` | kernel.governance | `kernel/governance/review_gate.py` | 审批/预算/审计挂点 | ok | 2026-08-16 契约 |
| `factory-console/session/review_view.py` | projections.cli | `projections/cli/review_view.py` | 人类控制台 | ok | 2026-08-16 |
| `factory-console/session/roles.py` | services.organization | `services/organization/roles.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-15 |
| `factory-console/session/router.py` | archive | `archive/session-m3/router.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/sandbox.py` | archive | `archive/session-m3/sandbox.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/scheduler.py` | archive | `archive/session-m3/scheduler.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-24 |
| `factory-console/session/session.py` | archive | `archive/session-m3/session.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-25 |
| `factory-console/session/session_audit.py` | archive | `archive/session-m3/session_audit.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/session_hooks.py` | archive | `archive/session-m3/session_hooks.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-29 |
| `factory-console/session/session_snapshots.py` | archive | `archive/session-m3/session_snapshots.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-29 |
| `factory-console/session/skill_search.py` | extensions.skills | `extensions/skills/skill_search.py` | Skill 插件 | ok | 2026-08-28 |
| `factory-console/session/slash.py` | projections.cli | `projections/cli/slash.py` | 人类控制台 | ok | 2026-08-15 |
| `factory-console/session/task_proposal.py` | archive | `archive/session-m3/task_proposal.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-16 |
| `factory-console/session/team_state.py` | services.organization | `services/organization/team_state.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-16 |
| `factory-console/session/teams.py` | services.organization | `services/organization/teams.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-15 |
| `factory-console/session/tool_search.py` | extensions.tools | `extensions/tools/tool_search.py` | Tool 插件 | ok | 2026-08-29 |
| `factory-console/session/tools.py` | extensions.tools | `extensions/tools/tools.py` | Tool 插件 | ok | 2026-08-20 |
| `factory-console/session/topic_ledger.py` | archive | `archive/session-m3/topic_ledger.py` | M3 旧链(CODE-REALITY 已证 dead 为主) | ok | 2026-08-28 |
| `factory-console/session/user_lifecycle.py` | services.organization | `services/organization/user_lifecycle.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-16 |
| `factory-console/session/web_tools.py` | extensions.tools | `extensions/tools/web_tools.py` | Tool 插件 | ok | 2026-08-28 |
| `factory-console/session/workloads/__init__.py` | extensions.workloads | `extensions/workloads/__init__.py` | Workload 插件 | ok | 2026-08-20 |
| `factory-console/session/workloads/backlog_sweeper.py` | extensions.workloads | `extensions/workloads/backlog_sweeper.py` | Workload 插件 | ok | 2026-08-21 |
| `factory-console/session/workspace.py` | services.work | `services/work/workspace.py` | 项目/工作域 | ok | 2026-08-16 |
| `factory-console/task_decomposition.py` | extensions.factories | `extensions/factories/software/task_decomposition.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-09 |
| `factory-console/task_tree.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-09-09 |
| `factory-console/testing_semantic_interp.py` | delete | `—` | 无匹配规则(孤儿候选) | — | 2026-09-08 |
| `factory-console/tools/adapters.py` | extensions.tools | `extensions/tools/adapters.py` | Tool 插件 | ok | 2026-08-27 |
| `factory-console/tools/executor.py` | extensions.tools | `extensions/tools/executor.py` | Tool 插件 | ok | 2026-08-27 |
| `factory-console/tools/registry.py` | extensions.tools | `extensions/tools/registry.py` | Tool 插件 | ok | 2026-08-27 |
| `factory-console/trace_query.py` | kernel.events | `kernel/events/trace_query.py` | 唯一事实源(append-only) | ok | 2026-09-09 契约 |
| `factory-console/unified_contract.py` | kernel.events | `kernel/events/unified_contract.py` | 唯一事实源(append-only) | ok | 2026-08-31 契约 |
| `factory-console/verification.py` | kernel.events | `kernel/events/verification.py` | 唯一事实源(append-only) | ok | 2026-08-29 契约 |
| `factory-console/verification_domain.py` | kernel.events | `kernel/events/verification_domain.py` | 唯一事实源(append-only) | ok | 2026-09-05 契约 |
| `factory-console/web/__init__.py` | projections.web | `projections/web/__init__.py` | Web 控制台 | ok | 2026-08-06 |
| `factory-console/web/backend/__init__.py` | projections.web | `projections/web/__init__.py` | Web 控制台 | ok | 2026-08-06 |
| `factory-console/web/backend/fastapi_adapter.py` | projections.web | `projections/web/fastapi_adapter.py` | Web 控制台 | ok | 2026-09-09 |
| `factory-console/workflow_canonical_bridge.py` | extensions.factories | `extensions/factories/software/workflow_canonical_bridge.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-06 |
| `factory-console/workflow_runner.py` | extensions.factories | `extensions/factories/software/workflow_runner.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-09-06 |
| `factory-console/workforce.py` | services.organization | `services/organization/workforce.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-30 |
| `factory-console/workforce_composition.py` | services.organization | `services/organization/workforce_composition.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-30 |
| `factory-console/workforce_os.py` | services.organization | `services/organization/workforce_os.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-10 |
| `factory-core/agents/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/agents/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/agents/registry.py` | archive | `archive/factory-core/registry.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/agents/skills.py` | archive | `archive/factory-core/skills.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/agents/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/assignment/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/assignment/allocator.py` | archive | `archive/factory-core/allocator.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/assignment/matcher.py` | archive | `archive/factory-core/matcher.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/assignment/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/assignment/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/change/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/change/analyzer.py` | archive | `archive/factory-core/analyzer.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/change/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/change/linker.py` | archive | `archive/factory-core/linker.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/change/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/change/service.py` | archive | `archive/factory-core/service.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/changeflow/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/changeflow/engine.py` | archive | `archive/factory-core/engine.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/changeflow/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/changeflow/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/changeflow/rules.py` | archive | `archive/factory-core/rules.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/changeflow/triggers.py` | archive | `archive/factory-core/triggers.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/cli/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/cli/commands.py` | archive | `archive/factory-core/commands.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-07 |
| `factory-core/cli/context.py` | archive | `archive/factory-core/context.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/cli/main.py` | archive | `archive/factory-core/main.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-07 |
| `factory-core/dashboard/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/dashboard/collector.py` | archive | `archive/factory-core/collector.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/dashboard/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/dashboard/renderer.py` | archive | `archive/factory-core/renderer.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/dashboard/views.py` | archive | `archive/factory-core/views.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/demo/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/demo/markpad.py` | archive | `archive/factory-core/markpad.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/events/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/events/logger.py` | archive | `archive/factory-core/logger.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/events/metrics.py` | archive | `archive/factory-core/metrics.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/events/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-09 |
| `factory-core/events/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/execution/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/execution/dispatcher.py` | archive | `archive/factory-core/dispatcher.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/execution/runner.py` | archive | `archive/factory-core/runner.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/execution/service.py` | archive | `archive/factory-core/service.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/git/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/git/client.py` | archive | `archive/factory-core/client.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/git/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/git/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/git/service.py` | archive | `archive/factory-core/service.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/decision.py` | archive | `archive/factory-core/decision.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/evaluate.py` | archive | `archive/factory-core/evaluate.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/intelligence/experience.py` | archive | `archive/factory-core/experience.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/recommend.py` | archive | `archive/factory-core/recommend.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/intelligence/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/calculators.py` | archive | `archive/factory-core/calculators.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/collectors.py` | archive | `archive/factory-core/collectors.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/reports.py` | archive | `archive/factory-core/reports.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/metrics/workspace.py` | archive | `archive/factory-core/workspace.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/orchestration/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/orchestration/engine.py` | archive | `archive/factory-core/engine.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/orchestration/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/orchestration/pipeline.py` | archive | `archive/factory-core/pipeline.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/product/experience.py` | archive | `archive/factory-core/experience.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/generation.py` | archive | `archive/factory-core/generation.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/lifecycle.py` | archive | `archive/factory-core/lifecycle.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/service.py` | archive | `archive/factory-core/service.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/product/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/project/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/project/loader.py` | archive | `archive/factory-core/loader.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/project/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/adapters/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/adapters/hermes.py` | archive | `archive/factory-core/hermes.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/capability.py` | archive | `archive/factory-core/capability.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/config.py` | archive | `archive/factory-core/config.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/costs.py` | archive | `archive/factory-core/costs.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/definitions.py` | archive | `archive/factory-core/definitions.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/providers/feedback.py` | archive | `archive/factory-core/feedback.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/integration.py` | archive | `archive/factory-core/integration.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/provider.py` | archive | `archive/factory-core/provider.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/registry.py` | archive | `archive/factory-core/registry.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/selector.py` | archive | `archive/factory-core/selector.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/providers/usage.py` | archive | `archive/factory-core/usage.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/recovery/__init__.py` | extensions.factories | `extensions/factories/software/__init__.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-06 |
| `factory-core/recovery/checkpoint.py` | extensions.factories | `extensions/factories/software/checkpoint.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-06 |
| `factory-core/recovery/models.py` | extensions.factories | `extensions/factories/software/models.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-06 |
| `factory-core/recovery/replay.py` | extensions.factories | `extensions/factories/software/replay.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-06 |
| `factory-core/recovery/service.py` | extensions.factories | `extensions/factories/software/service.py` | Factory 领域逻辑(Golden Path 等) | ok | 2026-08-06 |
| `factory-core/runtime/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/adapter.py` | archive | `archive/factory-core/adapter.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/adapters/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/adapters/echo.py` | archive | `archive/factory-core/echo.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/adapters/hermes.py` | archive | `archive/factory-core/hermes.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtime/registry.py` | archive | `archive/factory-core/registry.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/runtime/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/runtimes/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/runtimes/catalog.py` | archive | `archive/factory-core/catalog.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/runtimes/definitions.py` | archive | `archive/factory-core/definitions.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/runtimes/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/runtimes/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/tasks/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/tasks/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/tasks/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/understanding/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/analyzers/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/analyzers/artifact_detector.py` | archive | `archive/factory-core/artifact_detector.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/analyzers/document_analyzer.py` | archive | `archive/factory-core/document_analyzer.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/analyzers/project_analyzer.py` | archive | `archive/factory-core/project_analyzer.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-06 误归-archive/services |
| `factory-core/understanding/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/understanding/service.py` | archive | `archive/factory-core/service.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/validation/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/validation/engine.py` | archive | `archive/factory-core/engine.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/validation/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/validation/reports.py` | archive | `archive/factory-core/reports.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/validation/rules.py` | archive | `archive/factory-core/rules.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workflows/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/workflows/definitions.py` | archive | `archive/factory-core/definitions.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/workflows/engine.py` | archive | `archive/factory-core/engine.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/workflows/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/workflows/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-05 |
| `factory-core/workspace/__init__.py` | archive | `archive/factory-core/__init__.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workspace/config.py` | archive | `archive/factory-core/config.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workspace/loader.py` | archive | `archive/factory-core/loader.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workspace/manager.py` | archive | `archive/factory-core/manager.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workspace/models.py` | archive | `archive/factory-core/models.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-core/workspace/store.py` | archive | `archive/factory-core/store.py` | L4 旧数据层(宪法未覆盖) | ok | 2026-08-06 |
| `factory-exec/exec/__init__.py` | archive | `archive/factory-exec/__init__.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/agent_executor.py` | services.organization | `services/organization/agent_executor.py` | 执行角色(组织模型) | ok | 2026-08-12 |
| `factory-exec/exec/agent_runtime.py` | services.organization | `services/organization/agent_runtime.py` | 执行角色(组织模型) | ok | 2026-08-25 |
| `factory-exec/exec/approval.py` | services.approval_runtime | `services/approval_runtime/approval.py` | 审批流程服务 | ok | 2026-08-20 |
| `factory-exec/exec/architect.py` | archive | `archive/factory-exec/architect.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/benchmark/__init__.py` | archive | `archive/factory-exec/__init__.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/bugs.py` | archive | `archive/factory-exec/bugs.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/features.py` | archive | `archive/factory-exec/features.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/greenfield.py` | archive | `archive/factory-exec/greenfield.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/models.py` | archive | `archive/factory-exec/models.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/runner.py` | archive | `archive/factory-exec/runner.py` | M3 旧执行链 | ok | 2026-08-08 |
| `factory-exec/exec/benchmark/samples.py` | archive | `archive/factory-exec/samples.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/benchmark/verifiers.py` | archive | `archive/factory-exec/verifiers.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/budget.py` | archive | `archive/factory-exec/budget.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/candidate.py` | archive | `archive/factory-exec/candidate.py` | M3 旧执行链 | ok | 2026-08-08 |
| `factory-exec/exec/capability.py` | archive | `archive/factory-exec/capability.py` | M3 旧执行链 | ok | 2026-08-08 |
| `factory-exec/exec/cli.py` | archive | `archive/factory-exec/cli.py` | M3 旧执行链 | ok | 2026-08-25 |
| `factory-exec/exec/context.py` | archive | `archive/factory-exec/context.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/developer.py` | archive | `archive/factory-exec/developer.py` | M3 旧执行链 | ok | 2026-08-25 |
| `factory-exec/exec/employee_executor.py` | services.organization | `services/organization/employee_executor.py` | 执行角色(组织模型) | ok | 2026-08-08 |
| `factory-exec/exec/evaluator.py` | archive | `archive/factory-exec/evaluator.py` | M3 旧执行链 | ok | 2026-08-08 |
| `factory-exec/exec/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-07 误归-archive/services |
| `factory-exec/exec/execution_loop.py` | archive | `archive/factory-exec/execution_loop.py` | M3 旧执行链 | ok | 2026-08-13 |
| `factory-exec/exec/experience.py` | archive | `archive/factory-exec/experience.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/experience_ctx.py` | archive | `archive/factory-exec/experience_ctx.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/mcp.py` | extensions.mcp | `extensions/mcp/mcp.py` | MCP 插件 | ok | 2026-08-27 |
| `factory-exec/exec/models.py` | archive | `archive/factory-exec/models.py` | M3 旧执行链 | ok | 2026-09-04 |
| `factory-exec/exec/operations.py` | archive | `archive/factory-exec/operations.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/patch_filter.py` | archive | `archive/factory-exec/patch_filter.py` | M3 旧执行链 | ok | 2026-08-19 |
| `factory-exec/exec/pm.py` | archive | `archive/factory-exec/pm.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/progressive.py` | archive | `archive/factory-exec/progressive.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/project_adoption.py` | archive | `archive/factory-exec/project_adoption.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/provider.py` | extensions.models | `extensions/models/provider.py` | Model/Provider 插件 | ok | 2026-08-07 |
| `factory-exec/exec/providers/__init__.py` | extensions.models | `extensions/models/__init__.py` | Model/Provider 插件 | ok | 2026-08-07 |
| `factory-exec/exec/providers/anthropic.py` | extensions.models | `extensions/models/anthropic.py` | Model/Provider 插件 | ok | 2026-08-07 |
| `factory-exec/exec/providers/openai.py` | extensions.models | `extensions/models/openai.py` | Model/Provider 插件 | ok | 2026-08-07 |
| `factory-exec/exec/ranking.py` | archive | `archive/factory-exec/ranking.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/release.py` | archive | `archive/factory-exec/release.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/repo_index.py` | archive | `archive/factory-exec/repo_index.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/repo_intelligence.py` | archive | `archive/factory-exec/repo_intelligence.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/roles.py` | services.organization | `services/organization/roles.py` | 执行角色(组织模型) | ok | 2026-08-09 |
| `factory-exec/exec/runtime_session.py` | services.organization | `services/organization/runtime_session.py` | 执行角色(组织模型) | ok | 2026-08-13 |
| `factory-exec/exec/sandbox.py` | archive | `archive/factory-exec/sandbox.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/skill.py` | extensions.skills | `extensions/skills/skill.py` | Skill 插件 | ok | 2026-08-13 |
| `factory-exec/exec/store.py` | archive | `archive/factory-exec/store.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/exec/tester.py` | archive | `archive/factory-exec/tester.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/tool.py` | extensions.tools | `extensions/tools/tool.py` | Tool 插件 | ok | 2026-08-13 |
| `factory-exec/exec/tools/__init__.py` | extensions.tools | `extensions/tools/__init__.py` | Tool 插件 | ok | 2026-08-13 |
| `factory-exec/exec/tools/filesystem.py` | extensions.tools | `extensions/tools/filesystem.py` | Tool 插件 | ok | 2026-08-13 |
| `factory-exec/exec/uxui.py` | archive | `archive/factory-exec/uxui.py` | M3 旧执行链 | ok | 2026-08-09 |
| `factory-exec/exec/validation.py` | archive | `archive/factory-exec/validation.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-exec/scripts_diag_empty.py` | archive | `archive/factory-exec/scripts_diag_empty.py` | M3 旧执行链 | ok | 2026-08-07 |
| `factory-org/org/__init__.py` | services.organization | `services/organization/__init__.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-07 |
| `factory-org/org/approval.py` | services.organization | `services/organization/approval.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-09 |
| `factory-org/org/artifact.py` | services.organization | `services/organization/artifact.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-09 |
| `factory-org/org/capabilities.py` | services.organization | `services/organization/capabilities.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-11 |
| `factory-org/org/cli.py` | services.organization | `services/organization/cli.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-24 |
| `factory-org/org/demo.py` | services.organization | `services/organization/demo.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-09 |
| `factory-org/org/events.py` | kernel.events | `kernel/events/events.py` | 唯一事实源(append-only) | ok | 2026-08-09 误归-archive/services |
| `factory-org/org/execution.py` | services.organization | `services/organization/execution.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-11 |
| `factory-org/org/lifecycle.py` | services.organization | `services/organization/lifecycle.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-08 |
| `factory-org/org/management.py` | services.organization | `services/organization/management.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-04 |
| `factory-org/org/models.py` | services.organization | `services/organization/models.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-08 |
| `factory-org/org/project_adoption.py` | services.organization | `services/organization/project_adoption.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-24 |
| `factory-org/org/projects.py` | services.organization | `services/organization/projects.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-01 |
| `factory-org/org/registry.py` | services.organization | `services/organization/registry.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-07 |
| `factory-org/org/space.py` | services.organization | `services/organization/space.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-11 |
| `factory-org/org/store.py` | services.organization | `services/organization/store.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-09-01 |
| `factory-org/org/templates.py` | services.organization | `services/organization/templates.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-08 |
| `factory-org/org/workflow.py` | services.organization | `services/organization/workflow.py` | 组织模型(公司/部门/员工/角色) | ok | 2026-08-09 |
| `factory-runtime/bundle/factory_runtime_entry.py` | kernel.node | `kernel/node/factory_runtime_entry.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/__init__.py` | kernel.node | `kernel/node/__init__.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/bundle.py` | kernel.node | `kernel/node/bundle.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/cli.py` | kernel.node | `kernel/node/cli.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/errors.py` | kernel.node | `kernel/node/errors.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/health.py` | kernel.node | `kernel/node/health.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/logging.py` | kernel.node | `kernel/node/logging.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/manager.py` | kernel.node | `kernel/node/manager.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/paths.py` | kernel.node | `kernel/node/paths.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/state.py` | kernel.node | `kernel/node/state.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/runtime/watchdog.py` | kernel.node | `kernel/node/watchdog.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory-runtime/tests/test_bundle_contract.py` | kernel.node | `kernel/node/test_bundle_contract.py` | runtime 执行 | ok | 2026-08-07 误归-archive/services |
| `factory_console/__init__.py` | bootstrap | `bootstrap/__init__.py` | 装配/入口脚本 | ok | 2026-08-14 |
| `factory_console/cli_factory.py` | projections.cli | `projections/cli/cli_factory.py` | 人类控制台 | ok | 2026-08-14 |
| `scripts/coverage_report.py` | bootstrap | `bootstrap/coverage_report.py` | 装配/入口脚本 | ok | 2026-08-26 |
| `scripts/seed_plan_tasks.py` | bootstrap | `bootstrap/seed_plan_tasks.py` | 装配/入口脚本 | ok | 2026-08-26 |
| `scripts/smoke_24h.py` | bootstrap | `bootstrap/smoke_24h.py` | 装配/入口脚本 | ok | 2026-08-26 |
| `scripts/smoke_longrun.py` | bootstrap | `bootstrap/smoke_longrun.py` | 装配/入口脚本 | ok | 2026-08-26 |

## tests/（736 文件，跟随被测代码）

| 现路径 | 归属 | 备注 |
|---|---|---|
| `tests/agents/agent_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_agent_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_agent_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_agent_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_builtin_skills.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_cli_agents.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_cli_skills.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_skill_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/agents/test_skill_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/api/test_api_debug.py` | tests(跟随) | 随被测模块迁移 |
| `tests/api/test_api_memory.py` | tests(跟随) | 随被测模块迁移 |
| `tests/api/test_api_product_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/assignment_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_agent_allocator.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_agent_matcher.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_agent_status.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_assignment_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_assignment_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_assignment_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_cli_assignments.py` | tests(跟随) | 随被测模块迁移 |
| `tests/assignment/test_execution_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/driver.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/__init__.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/arithmetic.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/datavalid.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/report.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/stats.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/s6b/textutil.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/__init__.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/test_arithmetic.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/test_datavalid.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/test_report.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/test_stats.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/project_template/tests/test_textutil.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s6b/tasks.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s8_demo/demo_full_chain.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s8_demo/smoke_uxui.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/s9_pilot/pilot_s9_005.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/test_benchmark_runner.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/test_benchmark_samples.py` | tests(跟随) | 随被测模块迁移 |
| `tests/benchmark/test_benchmark_verifiers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/change_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_analyzer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_dashboard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_failsafe.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_linker.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_multiproject.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/change/test_change_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/changeflow_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/test_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/test_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/test_rules.py` | tests(跟随) | 随被测模块迁移 |
| `tests/changeflow/test_trigger_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/cli/cli_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/cli/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/cli/test_cli_commands.py` | tests(跟随) | 随被测模块迁移 |
| `tests/cli/test_cli_exit_codes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/cli/test_cli_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/console_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_agent_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_analysis_tools.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_api_gate_canonical.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_approval_apply.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_artifact_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_audit_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_audit_core.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_backlog_legacy_merge.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_backup.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_canonical_golden_path.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_capability_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_config.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_demo.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_demo_run.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_doctor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_factory_create.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_init.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_project_run.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_services.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_cli_structure.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_confirmation_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_agent_executor_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_backlog_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_config.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_isolation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_lifecycle_acceptance.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_management_acceptance.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_mcp_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_project_confirm.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_project_create.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_project_draft.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_runtime_session_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s10_005.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s10_006.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s10_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s10_workflow_start.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s9_003.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_s9_org.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_sessions.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_skill_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_sprint_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_suggest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_tool_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_console_web_adapter.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_debug_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_debug_core.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_debug_part2_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_debug_part2_core.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_discovery_guide.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_discovery_llm_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_discovery_session_llm.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_docs_with_status.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_evidence_attach.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_exec_state_recovery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_execution_semantics_s2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_execution_truth.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_execution_truth_intent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_execution_truth_p0.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_execution_truth_prefix.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_assets.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_m3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_metrics.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_router.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_external_skills.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_feature_idea_pipeline.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_flow_views_s2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_frontend_team.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_golden_path_e2e.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_golden_path_gates.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_llm_intent_parser.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_llm_semantic_interpreter.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_local_ai.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m1_continuation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m2_agent_core.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m3a_decomposer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m3b_critical_path.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m3c_scheduler.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m3d_evaluator.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_m3e_full_chain.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_memory_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_memory_core.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_memory_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_monitor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_mu08_verify_no_autopass.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_node_loop_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_orchestration_dag.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_org_manage_action.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_capability.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_company_organization.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_execution_control.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_execution_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_identity.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_plugin.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_project.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_resolution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_role_professional.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_runtime_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_scheduler.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_task_execution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_work.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_os_core_workforce.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p0_f1_identity_relations.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p0_f2_writeback.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p0_f3_verification.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p0_f4_artifact_evidence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p1_product_truth.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p2_release_truth.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p2c_experience_bridge.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_p2d_learning_consumption.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_phase3_convergence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_plan_aggregation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_plan_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_planning_orchestration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_planning_p1.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_post_cut3_fixes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_product_understanding_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_product_understanding_ssot.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_project_agile_s2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_project_docs_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_query_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_real_conversation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_real_llm_smoke.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_real_production_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_recursive_decomposition_s2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_release_packaging.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_requirement_analysis_node.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_070_e2e.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_070_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_071_p0_wiring.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_071_workspace_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_072_audit_auto.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_072_memory_auto.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_072_retrieval_unified.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_073_audit_coverage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_073_isolation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_074_deployment.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_075_nl_entry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_076_context_safety.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_077_factory_query.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_078_provider_ux.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_079_resume_project.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_081_naming.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_082_conversational_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_083_execution_delivery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_084_pipeline.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_089_dependency_fix.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_098_banner_version.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_103_command_routing.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_104_action_coverage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_105_markdown_preview.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_109_field_routing.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_110_board_project_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_111_m3_finish.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_112_registry_consistency.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_112_symmetric_paths.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_113_execution_replay.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_114_skill_activation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_115_board_consistency.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_115_lifecycle_single_source.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_116_campaign_plan.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_116_capability_router.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_117_execution_quality.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_118_discovery_context_keep.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_119_learning_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_120_trace_chain.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_121_eval_suite.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_123_k6_rag.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_125_api_standard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s10_125_c2_contract_wiring.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s44_workflow_canonical.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s45_acceptance_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e1_continuation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e1_conversation_intent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e2_governor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e2_semantic_continuity.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e3_continuation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e4_refinement.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s47_e5_chain.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s48_lifecycle_gate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s49_fix1_tool_safety.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s49_fix_context.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s50_p0fix_task_truth.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_s50_p1a_entry_gate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_semantic_proposal.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_action.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_agent_execution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_agents.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_autonomous_replanning.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_budget.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_cancel.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_completion.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_confirm.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_context.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_conversation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_cost_ledger.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_cost_trace.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_discovery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_evidence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_execution_policy.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_execution_time.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_feature_delivery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_gap_analyzer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_governance_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_governance_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_guided_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_intent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_intent_execution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_llm_gap_analysis.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_llm_planning_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_llm_task_proposal.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_loop_guard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_orchestrator.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_pilot.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_pipeline.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_plan_critic.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_planning_context.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_planning_fallback.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_product.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_product_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_product_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_production_session.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_quality.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_renderer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_replanning.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_repo_mode.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_restart_golden_path.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_review_gate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_review_ux.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_router.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_slash.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_task_proposal.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_team.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_team_decision.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_team_execution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_team_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_teams.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_tools.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_user_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_ux_blockers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_session_webui_bridge.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_settings_api.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_t5_task_continuity_e2e.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_task_decomposition.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_task_exec_bridge.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_task_exec_writeback.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_tools_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_tools_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_trace_query_s2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_understanding_confirmation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/console/test_workload_backlog.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/dashboard_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_cli_dashboard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_dashboard_collector.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_dashboard_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_dashboard_metrics.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_dashboard_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_dashboard_renderer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_workspace_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/dashboard/test_workspace_dashboard_views.py` | tests(跟随) | 随被测模块迁移 |
| `tests/demo/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/demo/test_demo_installation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/demo/test_demo_markpad_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/demo/test_demo_markpad_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/test_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/test_logger.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/test_metrics.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/test_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/events/test_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/exec_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_approval_decide.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_agent_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_approval.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_budget.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_candidate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_candidate_strategy.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_capability.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_capability_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_context.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_developer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_developer_reliability.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_employee_executor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_evaluator.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_evaluator_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_execution_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_experience.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_experience_ctx.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_experience_feedback.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_mcp.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_mcp_stdio.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_operations.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_progressive.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_provider.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_provider_openai.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_ranking.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_ranking_pipeline.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_repo_index.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_repo_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_roles.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_runtime_session.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_sandbox.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_skill.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_tester.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_tool.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_validation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/exec/test_exec_validation_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_cli_execution_run.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_echo_adapter.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_execution_dispatcher.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_execution_runner.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_execution_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/execution/test_execution_workflow_linkage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/frt_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_health.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_logging.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_manager.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_paths.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_state.py` | tests(跟随) | 随被测模块迁移 |
| `tests/factory_runtime/test_frt_watchdog.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/git_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_client.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_dashboard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_failsafe.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_multiproject.py` | tests(跟随) | 随被测模块迁移 |
| `tests/git/test_git_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/intelligence_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_decision.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_decision_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_evaluate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_evidence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_experience.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_experience_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_experience_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_recommend.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_recommend_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_removal.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/intelligence/test_intelligence_store_atomic.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_adaptive_workforce.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_agent_kernel.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_artifact_apply_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_artifact_invariants.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_artifact_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_autonomous_repair.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_context_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_context_layers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_context_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_control_tower.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_conversation_os.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_conversation_quality.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_effectiveness.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_executor_gateway.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_executor_gateway_permissions.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_experiment_reliability.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_gateway_session_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_governance.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_guided_production.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_handoff.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_health_monitor.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_integrity_hardening.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_intelligence_strategy.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_k7_journeys.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_k9_projects_list.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_learning_engine_v2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_control_key.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_control_persistence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_control_runtime_binding.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_experiment.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_gateway_agent_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_gateway_shapes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_router_agent_skill.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_router_binding.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_router_priority.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_llm_router_project.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_mcp_client.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_mcp_tools_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_model_catalog_persistence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_model_catalog_query.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_model_catalog_router_compat.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_model_prompt.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_node_artifact_e2e.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_node_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_openapi_generation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_operational_state.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_ops_control_tower.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_optimization.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_optimization_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_performance_selection.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_permission_modes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_plugin_kernel.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_production_entry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_production_evaluation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_production_experience.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_production_intelligence.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_production_run.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_professional_workflow.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_project_os.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_promotion_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_prompt_cache.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_real_execution_binding.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_real_executor_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_recovery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_recovery_control.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_release.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_release_verification.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_repair_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_rollback.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_s30_003_session_run.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_s33_003_project_status_name.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_sandbox.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_scan_todos.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_self_healing.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_session_hooks.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_session_snapshots.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_stream_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_task_tree.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_tool_search.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_tool_search_dynamic_surface.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_topic_ledger_fastpath.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_unified_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_workforce.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_workforce_composition.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_workforce_e2e.py` | tests(跟随) | 随被测模块迁移 |
| `tests/llm/test_workforce_os.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/metrics_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/test_metrics_calculators.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/test_metrics_collectors.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/test_metrics_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/test_workspace_aggregation.py` | tests(跟随) | 随被测模块迁移 |
| `tests/metrics/test_workspace_comparison.py` | tests(跟随) | 随被测模块迁移 |
| `tests/orchestration/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/orchestration/test_orchestration_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/orchestration/test_orchestration_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/orchestration/test_orchestration_hermes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/orchestration/test_orchestration_pipeline.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/org_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_audit_notification.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_capability_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_concurrency.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_concurrency_lock.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_dispatcher.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_event_coverage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_execution_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_execution_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_management_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_agent_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_audit_capability.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_authority.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_binding_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_capability_gate.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_capability_resolver.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_industry_llm_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_instance_snapshot.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_knowledge.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_legacy_binding.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_mcp_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_project_org_link.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_skill_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_store_atomic.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_templates.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_org_workflow_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_plan_dependency.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_project_entity.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_project_history.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_project_lifecycle_flow.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_project_lifecycle_sync.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_project_space.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_scheduler.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_task_cancelled.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_task_failed_semantics.py` | tests(跟随) | 随被测模块迁移 |
| `tests/org/test_task_state_machine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/product_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_approval_queue_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_artifact_version_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_cli_decide_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_dashboard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_events_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_generation_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_generation_context.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_generation_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_generator.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_cli_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_dashboard_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_decision_chain_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_engine_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_registry_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_lifecycle_removal_9d.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_pause_resume_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_removal.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_service_approval.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_service_ideas.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_service_workflow.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_state_machine_9c.py` | tests(跟随) | 随被测模块迁移 |
| `tests/product/test_product_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/project/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/project/test_cli_project.py` | tests(跟随) | 随被测模块迁移 |
| `tests/project/test_integration_markpad.py` | tests(跟随) | 随被测模块迁移 |
| `tests/project/test_loader.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/providers_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_adapter_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_capability_8b2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_cli_8b1.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_config_8b1.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_costs_8b2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_declared_actual_8b3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_events_8b1.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_failures.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_feedback_8b3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_hermes.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_integration_8b1.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_performance_8b3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_recommend_8b3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_selector.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_usage_8b2.py` | tests(跟随) | 随被测模块迁移 |
| `tests/providers/test_provider_usage_auto_8b3.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/recovery_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_checkpoint_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_cli_recovery.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_event_replay.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_recovery_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_recovery_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/recovery/test_state_reconstruction.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/runtime_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_cli_runtime.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_cli_runtime_test.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_hermes_adapter.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_hermes_execution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_runtime_adapter.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_runtime_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_runtime_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_runtime_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_runtime_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtime/test_workflow_execute_step.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/catalog_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_capability_search.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_crud.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_definitions.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_catalog_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/runtimes/test_cli_catalog.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/s7_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_artifact_registry.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_devtest_loop.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_full_chain_demo.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_projects.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_role_resolution.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_tester_role.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_artifact.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_crud.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_dag.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_integration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_runner.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_stage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s7/test_s7_workflow_state.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/s8_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_arch_agent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_arch_role.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_design_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_pm_agent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_pm_role.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_product_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_release_agent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_release_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_release_role.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_uxui_agent.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_uxui_contract.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_uxui_role.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_workflow_product.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_workflow_release.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s8/test_s8_workflow_uxui.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/s9_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_004_analyzer.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_004_registration.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_approval_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_approval_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_approval_lifecycle.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_approval_model.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_approval_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_smoke.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_workflow_approve.py` | tests(跟随) | 随被测模块迁移 |
| `tests/s9/test_s9_workflow_reject.py` | tests(跟随) | 随被测模块迁移 |
| `tests/tasks/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/tasks/task_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/tasks/test_task_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/tasks/test_task_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_cli.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_dashboard.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_detectors.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_service.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/test_understanding_stage.py` | tests(跟随) | 随被测模块迁移 |
| `tests/understanding/understanding_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/test_cli_validate_report.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/test_validation_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/test_validation_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/test_validation_reports.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/test_validation_rules.py` | tests(跟随) | 随被测模块迁移 |
| `tests/validation/validation_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_cli_workflows.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_workflow_definitions.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_workflow_engine.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_workflow_events.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_workflow_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/test_workflow_store.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workflows/workflow_helpers.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/conftest.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/test_workspace_config.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/test_workspace_loader.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/test_workspace_manager.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/test_workspace_models.py` | tests(跟随) | 随被测模块迁移 |
| `tests/workspace/test_workspace_store.py` | tests(跟随) | 随被测模块迁移 |

---

# Part B 预判清单（HARD STOP 预检）

## 依赖方向违规（铁律）
| 文件 | 违规内容 | 违反铁律 |
|------|---------|---------|
| `factory-console/web/backend/fastapi_adapter.py` | import `golden_path` / `production_run` / `task_decomposition`（extensions） | **铁律 2**：Projections 只 import API Gateway |

**共 1 处**。其余检查（projections 直连 kernel、extensions import kernel 实现）= 0 ✅

## 层级冲突（同时说得通两层）
| 文件 | 冲突候选 | 本 MAP 取值 | 理由 |
|------|---------|-----------|------|
| `factory-console/project_agile.py` | services.work ↔ extensions.factories | `services.work` | backlog/sprint 属工作域视图 |
| `factory-console/os_core_plugin.py` | kernel.capability ↔ extensions.mcp | `kernel.capability` | Plugin 注册表属能力层边界 |
| `factory-console/flow_views.py` | projections.web ↔ projections.cli | `projections.web` | 视图层 |

**共 3 处**（均给定了取值 + 理由，非阻塞）。

## kernel 六段现有命中数
| 段 | 命中文件数 |
|----|-----------|
| conversation | 14 |
| capability | 6 |
| scheduler | **2** |
| node | 22 |
| events | 31 |
| governance | 8 |

> **六段均有命中**（无缺失段）；scheduler 最薄（2：os_core_scheduler + ops_scheduler），符合"Core 只留 Contract"设计。

## 同一职责 ≥3 份实现的域
Role(4) · Project(5) · Approval(6) · Capability(6) · Agent(4) · Scheduler(4) · Learning(4) · Audit(3) · Evidence(3) · Verification(3) —— **共 10 域**（详见 `2026-09-11-MULTI-IMPL-ADJUDICATION.md`）

## archive（243，45%）构成
`factory-core/` 138 · `factory-exec/` 52 · `factory-console/session/` 剩余(M3) · `demo/` 2
> 均为宪法未覆盖的 L4 / M3 legacy 域 → 统一归 archive（Step 4 处置）。**未触发 >50% 阈值**。

## delete 候选（8）
无匹配规则文件（详见表中 `delete` 行）——**Step 4 引用核查后再定，不擅删**。
