# SYSTEM INVENTORY — FACT DISCOVERY (2026-09-02)

> 全部条目由真实扫描产生 (目录遍历/import 分析/API 提取), 无推断。

## 0. 顶层结构

| ID | Type | Name | Path | 说明(证据) |
|----|------|------|------|-----------|
| S00 | Package | ai-software-factory | / | pyproject name=ai-software-factory v1.1.364 |
| S01 | Package | factory-console | factory-console/ | 268 py; Web 会话系统 (运行时加载) |
| S02 | Package | factory-core | factory-core/ | 138 py; Factory OS 核心 (独立包, console 零 import) |
| S03 | Package | factory-exec | factory-exec/ | 52 py; 员工执行器系统 (独立包) |
| S04 | Package | factory-runtime | factory-runtime/ | 12 py; runtime 管理器 (独立包) |
| S05 | Package | factory-org | factory-org/ | 18 py; 领域 SSOT (被 console import: from org.management) |
| S06 | Dir | tests | tests/ | 685 py / 606+ 测试文件 / 34 分组 |
| S07 | Dir | docs | docs/ | 数百份 md (S10-xxx 系列审计/S 系列) |
| S08 | Dir | demo | demo/ | 2 py |
| S09 | Dir | scripts | scripts/ | setup/install/deploy/smoke 等 |

## 1. 运行时组件 (uvicorn 启动链)

| ID | Type | Name | Path | 证据 |
|----|------|------|------|------|
| R01 | Entry | create_app | factory-console/web/backend/fastapi_adapter.py:7953 | build_app(service) + uvicorn.run |
| R02 | Service | ConsoleService | factory-console/service.py | 4927 行 |
| R03 | API | fastapi_adapter | factory-console/web/backend/fastapi_adapter.py | 7966 行, 371 端点 |
| R04 | Session | agent_loop | factory-console/session/agent_loop.py | 2744 行 |
| R05 | Executor | external_executor | factory-console/external_executor/ | gateway 205 / executor 466 / router 243 |
| R06 | Domain | org | factory-org/org/ | management 804 / projects 938 (SSOT) |
| R07 | Runtime | CLI | factory-console/cli_factory.py | 8145 行 |

## 2. 独立包 (不被 console import — import 矩阵: console→core/exec/runtime = 0 文件)

| ID | Package | 入口 | 证据 |
|----|---------|------|------|
| P01 | factory-core | factory-core/cli/main.py (12+ 子命令: init/task/agent/skill/workflow/runtime/validate) | 独立 CLI, 2605+3706 行 |
| P02 | factory-exec | factory-exec/exec/cli.py | 员工执行器 (developer/pm/architect/evaluator/execution_loop) |
| P03 | factory-runtime | factory-runtime/runtime/cli.py | runtime 管理器 (bundle/manager/watchdog) |

## 3. HTTP API 端点 (371 个, 全量提取自 fastapi_adapter.py)

| 组 | 数量 | 代表 |
|----|------|------|
| /api/projects* | ~40 | backlog/epic/feature/story/task/sprint/milestone/roadmap/requirements/plans |
| /api/sessions* | ~15 | messages/cancel/runs/snapshots/approvals/progress-card |
| /api/external-ai* | ~15 | adapters/route/auto/cost/verify/run |
| /api/production-runs* | ~15 | recovery/evaluation/experience/lineage/releases |
| /api/workforces* | ~15 | select/status/attach |
| /api/optimization* | ~20 | analyze/experiments/variants/llm-experiments |
| /api/learning* | ~10 | observations/run/candidates/conflicts |
| /api/memory* | ~10 | candidates/promote/conflicts/lifecycle |
| /api/agents* | ~10 | registry/profiles/skills/performance |
| /api/intelligence* | ~10 | analyses/strategies |
| /api/plugins* | ~8 | enable/disable/health/performance |
| /api/releases* | ~10 | execute/rollbacks/verification/health |
| /api/context* | ~10 | requests/resolve/rank/progressive |
| /api/experiments* | ~10 | population/compare/outcome/evidence |
| /api/runtime* | ~10 | runtimes/start/stop/screenshot |
| 其他 | ~140 | board/monitor/audit/events/approvals/incidents/recovery/contracts/entities... |

## 4. CLI (两条)

| ID | CLI | 入口 | 证据 |
|----|-----|------|------|
| C01 | console CLI | factory-console/cli_factory.py (8145 行) | factory 命令 |
| C02 | core CLI | factory-core/cli/main.py (2605) + commands.py (3706) | init/task/agent/skill/workflow/runtime |
| C03 | exec CLI | factory-exec/exec/cli.py | 员工执行 |
| C04 | runtime CLI | factory-runtime/runtime/cli.py | runtime 管理 |

## 5. WebUI

| ID | Type | Path | 证据 |
|----|------|------|------|
| U01 | Frontend | factory-console/web/frontend/ | vite + React (5180 端口, 之前 E2E 验证) |
| U02 | Desktop | desktop/ | 未扫描 (0 py 目录) |

## 6. 存储 (数据根 ~/.factory)

| ID | 实体 | 文件 | 证据 |
|----|------|------|------|
| D01 | Projects | org/projects.json | ProjectStore |
| D02 | Tasks | workspace/projects/*/management/backlog/task.json | ManagementStore |
| D03 | Plans | session_plans.json | PendingPlanStore |
| D04 | ExecState | session_exec/{sid}.json | ExecState |
| D05 | Runs | ~/.factory/... (ExternalTaskRegistry) | gateway |
| D06 | Audit | audit/audit_events.json | AuditStore |
| D07 | Sessions | console_sessions.json | SessionStore |
| D08 | Agents/Skills | agents.json / skills.json | fastapi:4064-4067 |
| D09 | UI prefs | ui_prefs.json | fastapi:3929 |
