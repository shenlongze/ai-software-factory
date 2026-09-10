# 代码事实勘定（CODE REALITY）

> 日期: 2026-09-11 | 性质: **纯只读分析（未改代码/未建目录/未搬家）**
> 基线: `cleanup/os-core-restructure-2026-09-11` · 方法: grep 调用图 + git log + pytest collect
> 每节结论均带证据（文件路径 + 数字）

---

## 一、运行时调用链（当前真实主链）

```
入口: bin/factory → factory_console.cli_factory:main()  (cli_factory.py:8495 CanonicalShell().run())
  裸 `factory`
    → session/canonical_shell.py  CanonicalShell.run()
    → canonical_golden_path.py    CanonicalGoldenPath (Application Orchestrator)
    → golden_path.py              generate_prd/generate_plan/execute_approved (:176/:441/:482)
    → task_decomposition.py       task_trees/{plan_id}.json 落盘
    → production_run.py           register_workflow → create_production_run → execute_production_run
    → node_runtime.py             execute_node_run → 落盘 nodes/runs/{run_id}.json (:197 _write_run)
    → verification_domain.py      materialize_verification → ver-*  (:346 node_runtime)
    → evidence_domain.py          materialize_evidence → EVD-*
    → artifact_lifecycle.py       art-* 落盘
    → release_truth.py            RELEASE-* / gate_release
```
**链上模块（活）**：canonical_shell · canonical_golden_path · golden_path · conversation_app · product_understanding · product_truth · task_decomposition · production_run · production_runtime · node_runtime · verification(_domain) · evidence_domain · artifact_lifecycle · release_truth · project_agile

**链外模块（名字很像但不在链上 = 疑似 dead）**：`session/orchestrator.py` · `session/pipeline.py` · `session/actions.py`(M3 执行链) · `session/agent_*.py`(旧) · `session/router.py` · `session/replanning.py`

## 二、双主链矛盾 —— 哪条真跑？

| 链 | 入口证据 | 结论 |
|----|---------|------|
| **会话链（canonical）** | `cli_factory.py:8495 CanonicalShell().run()`（裸 `factory` 命令）→ CanonicalGoldenPath | **真跑（生产唯一）** |
| **M3 orchestrator 链** | `session/actions.py:1765/1901/… ExecutionOrchestrator(...)`；但 **`cli_factory` 对 actions 引用=0、`fastapi_adapter` 引用=0** | **dead（仅测试/内部引用）** |

- 证据 1：`grep -c 'actions\.' cli_factory.py` = **0**；fastapi_adapter = **0**
- 证据 2：`session/actions.py` 的引用方仅 `audit/audit_emitter.py`·`audit/audit_event.py`（且非入口）
- 证据 3：测试覆盖 `tests/orchestration/`(4) + `tests/exec/test_exec_ranking_pipeline.py` → 由测试锁活
- **结论**：canonical 链真跑；**M3 orchestrator 链是 dead（fallback 未接生产入口）**，其"活着"的假象来自测试与内部互引。

## 三、数据持久化真相

| 数据（store） | 存储位置 | 写入方 | 读取方 | 事实源? |
|--------------|---------|--------|--------|--------|
| conversation | `conversations/{id}.json` | product_understanding (`:106-114`) | conversation_app / api | ⚠️ Factory 持有（OS 无实体） |
| PRD/plan | `product_truth/{kind}.json` + conv doc `prds` | product_truth · application_formalization | golden_path | ⚠️ 两处并存 |
| task tree | `task_trees/{plan_id}.json` | task_decomposition (`:63`) | golden_path / trace_query | ⚠️ vs os_core_task |
| node/NodeRun | `nodes/{definitions,runs}/*.json` | node_runtime (`:197`) | production_run | ⚠️ vs os_core_task_node |
| execution/run | `workflows/{definitions,runs}/*.json` | production_run (`:50-59`) | golden_path | ⚠️ vs os_core_execution |
| verification | `verifications/verifications.json`(ver-*) | verification_domain (`:346` via node_runtime) | release_truth / acceptance | ⚠️ vs os_core_verification(V-*) |
| evidence | `evidence/EVD-*.json` | evidence_domain | release_truth | ⚠️ vs os_core_evidence(EV-*) |
| artifact | `artifacts/{xx}/art-*.json` | artifact_lifecycle (`:86-92`) | node_runtime / release | ✅ Factory Engine |
| release | `releases/release_truth.json`(RELEASE-*) | release_truth (`:60`) | cli/web | ⚠️ vs os_core_outcome |
| acceptance | `acceptance/acceptance.json`(ACC-*) | acceptance_truth | release gate | ⚠️ |
| audit | `audit/audit_events.json` | audit/audit_store | trace_query | ✅ 链式 |
| org | `org/{companies,departments,roles,employees,authorities}.json` | org lifecycle | org CLI | ✅ OS 组织真相 |
| os_core_* | `{identity,role,professional,workforce,work,task,capability,resolution,execution,usage,verification,evidence,outcome}/*.json` | os_core_* | （无生产消费者） | ⚠️ 建了未接线 |
| memory/experience | `memory/experience_store.json` | experience_bridge | memory/* | ⚠️ |
| learning | `learning/*.json` | learning_truth | （薄） | ⚠️ 半闭环 |
| legacy 执行记录 | `exec/execution_records.json`(EXS-*) | external_executor (`:196-237`) | Web(`:888`) | ⚠️ Web 真用 |

> 结论：**23+ 独立 store**，多域双份（verification/evidence/task/execution/project）。**事实源唯一者**：audit · artifact · org。

## 四、入口真相

| 入口 | 能跑? | 证据 |
|------|------|------|
| **CLI 裸 `factory`** | ✅ | → CanonicalShell（cli_factory:8495） |
| **CLI 子命令 ~60 个** | 部分 | agent/approval/artifact/backup/chat/composition/context/ct/doctor/entity/eval/evd/evidence/experience/experiment/git/governance/heal/health/index/intelligence/learn/learning/llm/llm-experiment/mcp/memory/memory-lifecycle/ops/optimization/org/plugin/product/production/ptrace/promotion/quality/query/rag/recovery/release/release-truth/reliability/repo/rollback/schedule/select/service/skill/sources/status/stop/strategy/tasktree/todo/tools/tower/update/variant/verification/workflow/workforce/workforce-os/workload |
| **Web** | ⚠️ UNCLEAR | `web/backend/fastapi_adapter.py`（8596 行）；**启动命令未取证到**（`bin/factory start` 为预留 stub） |
| **API** | ⚠️ 部分 | fastapi_adapter 内 `/api/*` 路由（approvals/projects/task/workforce/conversations…） |
| **desktop (Tauri)** | ⚠️ 未验 | `desktop/` 存在 |
| **demo/examples** | — | 非生产 |
| **dead-entry** | ⚠️ | `bin/factory init\|project\|run`（文件自述"预留 stub, 阶段三实现"）；M3 orchestrator 链（§二） |

## 五、依赖方向实况

| 检查项 | 结果 | 证据 |
|--------|------|------|
| ① core-候选 import extensions | **1 处** | `os_core_plugin.py` → `plugin_kernel` |
| ② projections import extensions | 多 | `cli_factory` → 大量服务；`fastapi_adapter` → 服务/apps |
| ③ 循环依赖 | ⚠️ 存在 | `os_core` 内部互引：os_core_execution(8 处)、os_core_scheduler(11 处)、task/task_node/resolution/work/project 交叉引用 |
| os_core → os_core_project | 3 处 | work:66 / task:166 / resolution:74 |

> ① 结论：**core 候选基本不依赖 extensions（除 plugin 1 处）** → 分层方向基本正确
> ③ 结论：os_core 内部形成**网状互引**（10 模块交叉）→ 搬家时需按依赖序，否则断链

## 六、测试覆盖分布

| 域(tests/) | 文件数 | 对应实现 |
|-----------|-------|---------|
| console | **257** | factory-console（新旧混合） |
| llm | 86 | 服务层（learning/workforce/experiment/production） |
| exec | 40 | factory-exec |
| org | 39 | factory-org |
| product | 25 | product_truth/intelligence |
| s7/s8/s9 | 47 | 历史 sprint |
| intelligence | 14 | factory-core/intelligence |
| runtime/runtimes | 17 | runtime |
| providers/agents/assignment/change/git/dashboard | 各 8-19 | factory-core 各包 |
| **orchestration** | **4** | **M3 orchestrator（dead 链，被测试锁活）** |
| 其他(api/cli/events/recovery/tasks/…) | 各 2-10 | 散 |
| **全量 collect** | **14,491 tests** | — |

- **有实现无测试**：部分 os_core_* 域（如 os_core_usage / os_core_outcome 无独立测试文件）；`factory-runtime` 有 7
- **有测试无实现（对应）**：`tests/orchestration/`(4) 对应 dead 的 M3 orchestrator 链；`tests/s7/s8/s9`(47) 对应历史 sprint（实现可能已 legacy）

## UNCLEAR（需补信息）

1. **Web 启动方式**：`bin/factory start` 为预留 stub，实际启动命令未在代码中取证到（需查 scripts/ 或文档）
2. **os_core 内部循环依赖是否真环**：需完整 import 图（本轮只抽样 execution/scheduler）
3. **factory-core 138 文件**：未逐文件勘定（属 Step 4 范畴）

---

# HARD STOP

纯只读；未改任何代码。产出后停下，与三分类裁定表一起提交。
