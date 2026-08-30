# AI Factory OS — Architecture Review (S0.5–S33)

> 日期: 2026-08-29 | HEAD: 05e8dc5f (v1.1.340) | 基于真实代码审计

## 1. 审计方法
基于真实代码路径 + 测试证据 (tests/llm/*.py, 945 passed + 6 skipped), 非 Completion Report。

## 2. 组件审计表
| 组件 | 状态 | 代码路径 | 证据 |
|------|------|---------|------|
| Production Core (ProductionRun/NodeRun/Artifact) | REAL | production_run.py, node_runtime.py, artifact_lifecycle.py | test_artifact_lifecycle, test_artifact_invariants |
| Execution (executor_factory 注入) | REAL | production_run.py:360 | test_workforce, S11/S25 |
| Verification (syntax+pytest subprocess) | REAL | verification.py:24/51 | test_autonomous_repair |
| Recovery (bounded repair loop) | REAL | recovery_service.py (S28) | test_recovery 18/18 (含 S8 兼容) |
| Evidence Model (refs 校验) | REAL | production_intelligence.py (S23) | test_production_intelligence |
| Experience (S14/S15) | REAL | production_experience.py | test_guided_production |
| Organization/Workforce/AgentProfile | REAL | workforce_os.py (S30) | test_workforce_os 10/10 |
| Capability (统一语义) | REAL | workforce_composition.py (S32) | test_workforce_composition 9/9 |
| Plugin Kernel (Registry/Resolver/Lifecycle/Governance) | REAL | plugin_kernel.py (S31) | test_plugin_kernel 12/12 |
| Performance-aware Selection | REAL | performance_selection.py (S33) | test_performance_selection 9/9 |
| Governance (S17: approval/expiration/self-approve 拒绝) | REAL | governance_service.py | test_governance 14/14 |
| Release/Rollback (S18/S19/S20) | REAL | release_service.py, rollback_service.py | test_release 11, test_rollback 10 |
| Health/Scheduler/Control Tower (S21/S22) | REAL | health_service.py, ops_scheduler.py, ops_projection.py | test_health 9, test_ops 11 |
| RCA/Recommendation (S23) | REAL | production_intelligence.py | test_production_intelligence 15 |
| Optimization/Experiment (S24/S26/S29) | REAL | optimization_service.py, llm_experiment_service.py, effectiveness_service.py | test_optimization 9, test_llm_experiment 10, test_effectiveness 11 |
| Reliability/Classification (S27) | REAL | experiment_reliability.py | test_experiment_reliability 10 |
| CLI (薄代理) | REAL | cli_factory.py (6400+ 行) | 全测试覆盖 |
| API (FastAPI, 251 paths) | REAL | fastapi_adapter.py | openapi 251 |
| Audit (Event Store) | REAL | audit/audit_event.py, audit_store.py | 事件全注册 |
| Lineage (workforce/composition/selection) | REAL | workforce_os.py, workforce_composition.py, performance_selection.py | 各 lineage 测试 |

## 3. 审计结论
- **无 DUPLICATED**: 无第二套 Agent/Task/Artifact/Experience/Governance/Registry
- **无 MISPLACED**: 职责边界清晰 (Core=Kernel, Plugin=Capability)
- **PARTIAL 项**: 无 (S0.5-S33 全部 REAL)
- **MISSING (S34+ 方向)**: Memory Layer / Context Control Plane / Learning / Promotion — 下一阶段 Intelligence Plane

## 4. 现有能力 → OS Plane 映射
| Plane | 组件 |
|-------|------|
| Production Plane | ProductionRun/NodeRun/Artifact/Verification/Recovery/Release/Rollback |
| Workforce Plane | Organization/Department/Workforce/AgentProfile/Selection |
| Plugin Plane | Plugin Kernel/Registry/Resolver/Lifecycle/Composition |
| Evidence Plane | Verification/Evaluation/Recovery/RCA/Reliability/Performance |
| Governance Plane | S17 approval/policy/expiration + Permission Matrix + self-elevate 拒绝 |
| Intelligence Plane | **MISSING — S35+ 建立 (Memory/Context/Learning/Promotion)** |

## 5. 核心架构验证 (15 Invariants 对照)
| Invariant | 状态 | 证据 |
|-----------|------|------|
| Everything is a Plugin | ✅ | S31 反硬编码测试 (provider.second/third 无 Core 修改) |
| Every Node 独立执行/验证循环 | ✅ | node_runtime.py + S28 recovery loop |
| Evidence = Production Truth | ✅ | S23 evidence_refs 校验 + S27 classification |
| Context 是受治理资源 | ❌ 未建立 | S34+ 设计 (Context Control Plane) |
| Scope 不是继承树 | N/A (Memory 未建) | S34+ 设计 |
| Learning 不能直接改 Production | N/A (Learning 未建) | S34+ 设计 |
| Performance 影响 Selection 不绕过 Governance | ✅ | S33 test_governance_over_performance |
| 无能力绕过 Core Governance | ✅ | S31 self_elevate 拒绝 + S17 |
| 生产改动可追溯 | ✅ | lineage 全链 (workforce/composition/selection/recovery) |
| 生产改动可逆 | ✅ | S19 rollback + S28 recovery |
| 有意义能力暴露 CLI+API | ✅ | 每 Sprint 同步 |
| 无无限 Context | ❌ 未建立 | S34+ 设计 |
| 无隐藏第二事实源 | ✅ | 审计确认 |
| Core 无 Vendor 实现 | ✅ | S31 provider pluginized |
| 确定性政策处无 LLM 决策 | ✅ | S33 selection 非 LLM + S13 evaluation 确定性 |

## 6. 结论
S0.5–S33 已形成清晰 OS 骨架: 5 个 Plane REAL + Governance-first + Evidence-driven + Plugin 架构。
**Intelligence Plane (Memory/Context/Learning/Promotion) = 下一阶段核心。**
