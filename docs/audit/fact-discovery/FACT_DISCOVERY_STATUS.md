# FACT DISCOVERY STATUS — AI FACTORY (2026-09-02)

> 本报告只含扫描证据。无评分,无判断,无修复建议。
> 扫描方法: 目录遍历 / import 分析 / API 提取 / grep 命中 / 代码定位。

## 1. Repository Coverage

| 区域 | 状态 |
|------|------|
| factory-console (268 py) | 已扫描: 规模/API 371/LLM 调用/入口/存储写点; 逐文件功能未全读 |
| factory-org (18 py) | 已扫描: management/projects SSOT (前几轮深度审计) |
| factory-core (138 py) | 已扫描: 文件清单/规模/独立 CLI/零 import; 内部逐模块未读 |
| factory-exec (52 py) | 已扫描: 文件清单 (员工执行器); 内部未读 |
| factory-runtime (12 py) | 已扫描: 文件清单 (runtime 管理); 内部未读 |
| tests (685 py / 606 文件 / 34 组) | 已扫描: 目录分组; 未逐测试读取 |
| docs (数百 md) | 已列目录; 未全文读取 |
| WebUI (frontend/) | 未扫描 (仅知 vite+React, 5180 端口) |
| desktop/ | 未扫描 (0 py) |
| examples/ projects/ workspace/ exec/ | 未扫描 |

## 2. Evidence Coverage — 核心事实 (已定位)

| 事实 | 证据 |
|------|------|
| 运行时 = console+org | fastapi_adapter.py:7953 create_app → ConsoleService |
| 371 HTTP 端点 | fastapi_adapter.py 全量 @app 提取 |
| 5 个独立包, 互不 import | grep import 矩阵: console→core/exec/runtime = 0 |
| console import org | from org.management (E2E 运行链) |
| LLM 调用 175+, 154 直接形态 (88%) | grep llm_fn/llm_raw/chat_completion |
| Plan/Task/ExecState/Run SSOT | session_plans.json / backlog / session_exec / registry |
| 生产执行链 | agent_loop execute_plan→chain_next→gateway→finish→reconcile |
| actions/M3 链与 agent_loop 分离 | agent_loop 无 actions import |
| Requirement/PRD 无结构化持久化 | product_intelligence action 返回 markdown 无 save |
| Release/Learning 端点存在 | /api/releases, /api/learning (持久化未验证) |

## 3. Trace Breaks (链路中断点, 已定位)

| Break | 证据 |
|-------|------|
| Requirement → Plan: 需求分析结果不落盘 | actions.py:2864-2893 (markdown return, 无 write) |
| 会话链 → actions/M3 链: 零 import | agent_loop 无 actions |
| console → factory-core: 零 import | import 矩阵 |
| console → factory-exec (员工执行器): 零 import | import 矩阵 |
| Artifact → Task: result_id 未回写 backlog | 前几轮审计 (exec_ref 有, artifact_ref 无) |

## 4. Duplicate Facts / Duplicate Execution (已定位)

| 重复 | 证据 |
|------|------|
| 执行系统 A (会话链): backlog+ExecState+gateway | agent_loop |
| 执行系统 B (M3): execution_plan.json+orchestrator+production_run | actions.py:1758 |
| 执行系统 C (员工执行器): factory-exec (独立包) | factory-exec/exec/ |
| LLM 调用分散 (40+ 文件直接调用) | LLM_CALL_GRAPH |
| CLI 双套 (console cli_factory 8145 + core cli/main 2605) | 两文件 |

## 5. Independent / Non-Independent Modules

| 模块 | 独立 | 证据 |
|------|------|------|
| org.management/projects | YES (领域 SSOT) | 无 service 依赖 |
| external_executor | YES | gateway/executor/router 自成体系 |
| factory-core (整体) | YES (独立包) | 独立 CLI + 零 console import |
| factory-exec (整体) | YES (独立包) | 独立 CLI |
| factory-runtime (整体) | YES (独立包) | 独立 CLI |
| session/exec_state | YES | 投影, 可独立测试 |
| agent_loop / actions / orchestrator | NO (大流程片段) | 相互/Service 强耦合 |

## 6. Unresolved Relationships (未解决关系)

| 关系 | 状态 |
|------|------|
| factory-core ↔ console 是否应一体 | 未验证 (零 import 是设计还是断裂? 未知) |
| factory-exec 员工执行器 ↔ gateway 外部执行器 | 未验证 (是否同一能力两套实现) |
| Release/Learning/Experience 持久化实体 | UNKNOWN (端点存在, store 未定位) |
| Requirement/Brainstorm/PRD 数据模型 | UNKNOWN (未定位结构化实体) |
| WebUI 状态来源 | UNKNOWN (未浏览器审计) |
| desktop/ examples/ 内容 | UNKNOWN (未扫描) |

## 7. 未扫描区域 (显式列出)

1. factory-core 内部逐模块行为 (providers/product/orchestration/workflows/understanding/change/agents/assignment)
2. factory-exec 内部 (员工执行器逐文件)
3. factory-runtime 内部
4. WebUI frontend 源码
5. desktop/
6. examples/ projects/ workspace/ exec/ 内容
7. tests/ 逐测试文件 (仅目录分组)
8. docs/ 全文 (仅目录)
9. factory-console 268 py 中未在前几轮审计覆盖的文件 (memory/retrieval/learning/optimization/control_tower 等)
10. factory-console/api/ (23 文件) 与 factory-console/tools/ 内部
