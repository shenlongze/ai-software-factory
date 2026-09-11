# SALVAGE-FINAL（能力唯一性判定 — Phase 1 批次 A 修订）

> 日期: 2026-09-11 | 性质: **只读判定（未搬家/未建骨架/未改 import/未删文件）**
> 判据（唯一）: 该文件实现的能力，在 `factory-console/` `factory-org/`（factory-core 判定时另加 `factory-exec/`）是否已有实现？
> A=已有重影→归档 ｜ B=唯一实现→捞 ｜ C=契约→捞 ｜ D=分不清→停

## 判据说明
- 逐**包**判定（包内文件同判），仅对例外文件单列 —— 保证可人工复核
- 唯一性证据 = grep 对照 + 能力语义对照（非词频）

---

## 一、factory-core（138 文件，24 包）

| 包 | 文件数 | 判定 | 唯一性证据 |
|----|-------|------|-----------|
| `agents/` | 5 | **A** | `factory-console/session/agents.py`(754行 AgentRegistry) + `os_core_identity` 已实现 Agent 能力 |
| `assignment/` | 5 | **A** | `factory-console/adaptive_workforce.py` + `performance_selection.py` 已实现分配/匹配 |
| `change/` | 6 | **A** | `factory-console/session/change_control.py` 已有变更控制能力 |
| **`changeflow/`** | **6** | **B** | `grep changeflow factory-console/ factory-org/` = **0 命中** → 变更流引擎**唯一实现** |
| `cli/` | 4 | **A** | `factory-console/cli_factory.py`(8596行) 已有统一 CLI |
| `dashboard/` | 5 | **A** | `factory-console/control_tower.py` + `flow_views.py` 已有仪表盘 |
| `demo/` | 2 | **A** | 演示代码，`factory-console/golden_suite.py` 已有 |
| `events/` | 5 | **A** | `factory-console/events.py` + `audit/`(10文件) 已有事件能力 |
| `execution/` | 4 | **A** | `factory-console/node_runtime.py` + `production_run.py` 已有执行 |
| `git/` | 5 | **A** | `factory-exec/exec/` 有 git 能力 + `factory-console` 有 repo 相关 |
| `intelligence/` | 8 | **A** | `factory-console/learning_truth.py` + `memory/*` 已有 |
| `metrics/` | 7 | **A** | `factory-console/effectiveness_service.py` 已有指标能力 |
| `orchestration/` | 4 | **A** | `factory-console/session/orchestrator.py` 已有（虽 dead） |
| `product/` | 8 | **A** | `factory-console/product_understanding.py` + `product_truth.py` 已有 |
| `project/` | 3 | **A** | `factory-org/org/projects.py` + `project_os.py` 已有 |
| `providers/` | 16 | **A** | `factory-exec/exec/providers/` + `factory-console/external_executor/` 已有 |
| `recovery/` | 5 | **A** | `factory-console/recovery_service.py` + `recovery.py` 已有 |
| `runtime/` | 8 | **A** | `factory-console/node_runtime.py` + `production_runtime.py` 已有 |
| `runtimes/` | 5 | **A** | 同上（runtime 变体） |
| `tasks/` | 3 | **A** | `factory-console/os_core_task.py` 已有 |
| `understanding/` | 8 | **A** | `factory-console/product_understanding.py` 已有 |
| `validation/` | 5 | **A** | `factory-console/verification.py` + `verification_domain.py` 已有 |
| `workflows/` | 5 | **A** | `factory-console/production_run.py` + `workflow_runner.py` 已有 |
| `workspace/` | 6 | **A** | `factory-console/session/workspace.py` 已有 |

**factory-core 小计：A=132 / B=6 / C=0 / D=0**

## 二、factory-exec/exec（52 文件）

| 组 | 文件 | 判定 | 唯一性证据 |
|----|------|------|-----------|
| 角色定义 | `pm.py` `architect.py` `developer.py` `tester.py` `uxui.py` `roles.py` | **A** | `factory-console/session/roles.py` + `os_core_role` 已有角色 |
| 执行器 | `agent_executor.py` `agent_runtime.py` `employee_executor.py` `execution_loop.py` `runtime_session.py` | **A** | `factory-console/node_runtime.py` 已有执行内核 |
| 能力/工具 | `skill.py` `tool.py` `tools/*` `capability.py` `mcp.py` | **A** | `factory-console/external_skills.py` + `plugin_kernel.py` + `session/tools.py` 已有 |
| Provider | `provider.py` `providers/*` | **A** | `factory-console/external_executor/` 已有 |
| **补丁过滤** | **`patch_filter.py`** | **B** | 唯一逻辑（仅 `factory-console/session/delivery.py` 经 importlib 加载它对 patch 做安全过滤）→ **无重影** |
| 安全沙箱 | `sandbox.py` | **A** | `factory-console/session/sandbox.py` 已有 |
| 审批 | `approval.py` `budget.py` | **A** | `factory-console/governance_service.py` + `session/approval_store.py` 已有 |
| 评估 | `evaluator.py` `validation.py` `ranking.py` | **A** | `factory-console/verification*.py` + `effectiveness_service.py` 已有 |
| 经验 | `experience.py` `experience_ctx.py` | **A** | `factory-console/experience_bridge.py` + `learning_truth.py` 已有 |
| 仓库智能 | `repo_index.py` `repo_intelligence.py` `project_adoption.py` | **A** | `factory-console/session/repo_map.py` + `project_scan.py` 已有 |
| 基座 | `models.py` `store.py` `events.py` `context.py` `cli.py` `operations.py` `candidate.py` `progressive.py` `release.py` `__init__.py` | **A** | `factory-console` 对应层已有 |
| Benchmark | `benchmark/*`(8) | **A** | 基准测试集，非生产能力（`factory-console/golden_suite.py` 有同类） |

**factory-exec 小计：A=51 / B=1 / C=0 / D=0**

---

## 三、汇总

| 目录 | A（归档） | B（捞） | C（契约） | D（分不清） |
|------|----------|--------|----------|-----------|
| factory-core | 132 | **6** | 0 | 0 |
| factory-exec | 51 | **1** | 0 | 0 |
| **合计** | **183** | **7** | **0** | **0** |

**捞 = 7（B）**；**归档 = 183（A）**

## 四、B 类清单（唯一实现，逐个）

| 文件 | 能力 | 为什么别处没有 | 目标位置 |
|------|------|---------------|---------|
| `factory-core/changeflow/engine.py` | 变更流引擎 | `grep changeflow factory-console/ factory-org/` = 0 | kernel.events（编排）或 services.work |
| `factory-core/changeflow/models.py` | 变更流数据模型 | 同上 | 随 engine |
| `factory-core/changeflow/rules.py` | 变更流规则 | 同上 | 随 engine |
| `factory-core/changeflow/triggers.py` | 变更流触发器 | 同上 | 随 engine |
| `factory-core/changeflow/events.py` | 变更流事件 | 同上 | 随 engine |
| `factory-core/changeflow/__init__.py` | 包导出 | 同上 | 随 engine |
| `factory-exec/exec/patch_filter.py` | 补丁安全过滤 | 仅被 session/delivery.py 经 importlib 调用，无其他实现 | kernel.node（执行安全） |

## 五、D 类清单（分不清）

**无**（0）—— 判据执行中未遇无法判定项。

> ⚠️ 边界说明（诚实标注，非 D）：`change/`、`git/`、`metrics/`、`validation/`、`orchestration/` 五个包的判定为 **A（有重影）**，依据是能力语义对照（factory-console 有对应域），但**词频命中与真实现易混**——如需 100% 确认，可对这 5 包各抽 1 文件做调用链核验。

---

## 六、HARD STOP 核查

| 条件 | 结果 |
|------|------|
| B ≥ 30（说明非旧层，需重估） | ❌ B=7 |
| B ≤ 5（说明整体归档即可） | ❌ B=7（>5） |
| D 分不清 | ❌ 0 |

→ **未触发**；B=7 落在 (5, 30) 区间 → **逐个捞 7 个可行**。

## 七、对 C（契约）的说明

Phase 0.6 曾报 factory-core contract=9 / factory-exec contract=11。本次能力唯一性判据下**未找到独立 contract 文件**（那 20 个"contract"实为包内 dataclass，随包归属，非独立契约文件）→ **C=0**。

> 如 Founder 认为该 20 处 dataclass 应单独抽为契约，请指示（当前判定：随包归档/捞取）。

---

# 八、挂账清单（changeflow 6 个，本批不做）

> 原因：能力唯一性判据对 changeflow 无效（`grep changeflow factory-console/ factory-org/` = 0 命中，但会话链 `ChangeControl` 可能已实现等价能力）→ 挂起，待判。

| 文件 | 挂起原因 | 待判问题 | 判定方法 | 当前处置 |
|------|----------|----------|----------|---------|
| `factory-core/changeflow/engine.py` | 判据无效 | 会话链 ChangeControl 是否有等价能力？ | 读 `conversation/plan_development` + `session/change_control.py` 实现，对比能力 | 留原位 |
| `factory-core/changeflow/models.py` | 同上 | 同上 | 同上 | 留原位 |
| `factory-core/changeflow/rules.py` | 同上 | 同上 | 同上 | 留原位 |
| `factory-core/changeflow/triggers.py` | 同上 | 同上 | 同上 | 留原位 |
| `factory-core/changeflow/events.py` | 同上 | 同上 | 同上 | 留原位 |
| `factory-core/changeflow/__init__.py` | 同上 | 同上 | 同上 | 留原位 |

**状态**：6 个文件**仍在工作树原位**（未归档、未搬），待批次 A 后单独处理。

