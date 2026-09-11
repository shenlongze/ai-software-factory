# AI FACTORY OS — CURRENT CODE REALITY AUDIT (2026-09-06)

> 只读代码级全景审计 | AUDIT_BASELINE_HEAD = 7c6f0ed3
> 证据优先: file/function/caller/store/data; 禁以文档/测试代生产现实

---

## 1. BASELINE
- HEAD: 7c6f0ed3 (P2-D governed learning consumption)
- BRANCH: main
- WORKTREE: canonical 全 committed; 仅 demo/unused 并发噪音 + 用户文件 (unrelated)

## 2. EXECUTIVE VERDICT

AI Factory 当前真实状态 = **单人开发、以 JSON 文件域存储为 SSOT 的
"人类指挥 + 外部 Agent 执行委派 + canonical 生产事实账本" 系统**。
它不是多 Agent runtime, 也不是已部署的产品; 它是**生产事实管线 + 治理 +
学习账本**已真实贯通、但 agent 执行主要委派外部 CLI、WebUI 为 projection
的工作台。

整体成熟度: 域账本层 M3-REAL (P0-P2-D 六链已 commit), 运行时层 M2,
Workforce/Agent 运行时 M1, 部署/SRE M1。

最大三个真实优势:
1. canonical Production Truth 链真实: TASK→run→EXS→art→ver→EVD→RELEASE
   (代码+测试+隔离 E2E, 冻结 commit)
2. Learning Consumption 基础设施真实: exp→OBS→CAND→PROM(治理)→Profile→
   Router→RD 全链 (决策变化实证)
3. 治理 gate 真实: governance approval (release/learning_promotion),
   EXS 结果吸收零二次执行 (finalize 幂等)

最大三个真实缺口:
1. Agent 执行 = 外部 CLI 委派 (codex/claude/hermes subprocess), 无 canonical
   AgentRun/Agent Action SSOT — 系统不知 Agent 内部做了什么 (黑盒)
2. WebUI = projection 但 106 页面消费的 canonical 状态有限; 无 real-time
   Agent runtime 监控 (谁在干什么不可实时回答)
3. 真实生产数据近零: 各 canonical 域 (TASK-*/run-*/ver-*/RELEASE-*/OBS-*) 在
   真实库 0 记录 (P0-P2-D E2E 全在隔离 tmp); 84 exp/100 EXS = M3 历史遗留

## 3. REAL END-TO-END CHAINS

Product Chain: REAL (代码+测试) — product_truth.py services; 真实库 0 记录
Production Chain: REAL (代码+E2E) — P0-F4; 真实库 0 (仅 M3 EXS 100)
Learning Chain: REAL (代码+E2E) — P2-C/P2-D; 真实库 0
Operations Chain: PARTIAL — session/console_sessions 2 真实; 无 runtime 心跳
Governance Chain: REAL (approval gate 在 release/learning/rollback caller)

## 4. CANONICAL SSOT MAP
Task→backlog TASK-* (service.create_task) | TaskRun→nodes run-* | EXS→exec/
execution_records | Artifact→art-* | Verification→ver-* | Evidence→EVD-* |
Release→RELEASE-* | Experience→memory exp-* | OBS/CAND/PROM/PROFILE/RD→learning/* |
Product (IDEA/DISC/REQ/PRD/PLAN)→product_truth/* — 全唯一 writer, JSON 文件

## 5. REAL CALL GRAPH (主入口)
User→WebUI(React 106 pages)→/api/* (fastapi_adapter) 或 CLI (cli_factory)
→session agent_loop.dispatch (L790) → intent → actions (service layer)
→ execute_plan/_chain_auto_worker → _chain_task_run (run-*) → gateway_execute
→ external_executor.executor subprocess codex/claude/hermes (黑盒)
→ finalize_node_run (EXS/art/ver/EVD 吸收, 幂等) → experience_bridge → exp
→ (learning) OBS/CAND/PROM/Profile → select_agent (Router) → RD → next run

## 6. CAPABILITY REALITY MATRIX
(见 07-report 详细; 摘要) Production chain REAL; Agent runtime PARTIAL;
Action SSOT MISSING; Workforce M1; WebUI projection REAL; Monitor PARTIAL。

## 7. WORKFORCE REALITY = M1 (SHELL+)
- workforce_os.py: org/workforce/agent 注册 + 静态状态机 (_next_state) —
  41 agents 真实 (agents.json: local-codex/claude/hermes + codex.* 派生)
- 无 heartbeat/idle/running 实时状态; 无 runtime 排程

## 8. AGENT REALITY = PARTIAL (B/C 混合)
- agent_loop.call_with_tools (L139): 原生 LLM tool-calling (对话内)
- external_executor.executor (L134): subprocess 委派外部 CLI (codex/claude/
  hermes — sandbox validate_command 前置) — 生产委派链主路
- 无 canonical AgentRun 实体; Agent = registry 声明 (agents.json) + adapter

## 9. AGENT ACTION REALITY = MISSING
- 无 AgentAction/ActionRecord 域; 执行 = executor 返回 {exit_code, output}
  (黑盒); 动作细节 (file/shell/API) 不在 canonical Action Truth
- audit_events.json = observation (非 action 域); cli agent_action = agents
  registry 增删, 非动作记录

## 10. ORCHESTRATION REALITY = M2-PARTIAL
- execute_plan + PendingPlanStore + progress_card (queue/recover) 真实
- plan 执行委派外部 agent; 自身无内部多-agent 编排 (无 task→subagent 分派
  到内部 agent runtime)

## 11. PRODUCTION REALITY = M3 (账本) / M2 (运行时)
- canonical 链真实 (代码+E2E); 真实数据 0 (canonical 域) — E2E 全 tmp
- 真实库: EXS 100 (M3 历史), 44 任务 (M3 projects), ver/art/evd/release 0

## 12. OPERATIONS REALITY = M2
- task queue/recover/progress 真实 (progress_card/registry)
- 无 runtime 心跳/stuck detection/cancel; session_exec 等 legacy 隔离

## 13. GOVERNANCE REALITY = M3 (gate 真实) / PARTIAL (action 控制)
- request_approval/decide (governance_service) caller: release (release_truth),
  learning promotion, rollback, effectiveness, llm_experiment — 真实
- 但危险 action 事前拦截: 仅 external executor sandbox validate_command
  (exec 前) — agent 内部动作无 interception

## 14. LEARNING REALITY = M3 基础 / 生产数据 0
- exp→OBS→CAND→PROM→Profile→Router→RD committed; 决策变化 E2E 实证
- 真实库: 84 exp (M3 legacy 无 anchor — 不可作 obs 源) → obs/cand/prom 0
- P2-D "学习改变下次选择" = 代码真实 + E2E 实证, 生产未运行

## 15. CONTEXT/MEMORY/KNOWLEDGE REALITY = M2
- Conversation context (session) 真实; experience retrieval (retrieval.py)
  代码在; 无独立 Knowledge 域 (未建)
- agent memory (Hermes/Codex 各自) ≠ AI Factory Learning (隔离正确)

## 16. INTEGRATION REALITY = M2
- Git/filesystem/terminal 经 sandbox+executor; HTTP web_tools; MCP 支持接口
  存在 (registry? 未见真 MCP server 连接); 无统一 Integration Plane
- 各 adapter 硬编码 (codex/claude/hermes registry)

## 17. DEPLOYMENT/SRE REALITY = M1
- Release Truth (RELEASE-*) ≠ Deployment (无 deploy 域 — 契约明确)
- 无 SLO/incident/alert; 本地进程 (uvicorn)

## 18. WEBUI REALITY = M3 projection
- 106 React pages; 全 API 投影; 零业务 localStorage
- run-status (S10-006.5) = tasks.json 静态聚合 (running count), 非实时

## 19. MULTI-LEDGER/LEGACY REALITY
- canonical 单 SSOT 每域 (P0-P2D 冻结); legacy 隔离: M3 production_run/
  TASK-GW/EXR/session_exec/rel-*/PI-*/req_*/intelligence(85)/ev-*/exec
  ART-*/org ArtifactRegistry — 全保留隔离, 无生产路径消费
- exec/results.json mirror = legacy

## 20. REAL DATA REALITY (真实库 ~/.factory)
- canonical 域生产数据: **0** (P0-P2D E2E 全隔离 tmp — 诚实)
- legacy/M3: EXS 100, exp 84 (无 anchor), agents 41, tasks 44+
  (M3 projects), org projects 1 (27 项目在别处? — projects.json 1), 2 sessions
- test/fixture 不入真实库 (纪律)

## 21. FALSE-CAPABILITY FINDINGS
| 宣称 | 代码 | Runtime caller | 数据 | 结论 |
|---|---|---|---|---|
| Multi-Agent runtime | 部分 | 外部 CLI 委派 | 0 | PARTIAL (非内部) |
| Agent Action 域 | 无 | — | — | MISSING |
| Workforce 实时 | 注册+状态机 | 无 heartbeat | 41 注册 | M1 |
| Deployment | Release 记录 | 无 deploy | 0 | MISSING (≠Release) |
| Learning 闭环生产 | 代码+E2E | 无生产触发 | 0 | PARTIAL (E2E proven) |
| Monitoring real-time | run-status | tasks 聚合 | — | PARTIAL |
| Knowledge 域 | 无 | — | — | MISSING |
| MCP 真连 | 接口 | 未见 server | — | UNKNOWN/SHELL |

## 22. TOP GAPS
P0: 无 (canonical 链完整; 无 contract 破损)
P1: 生产数据零迁移风险 — canonical 域需真实运行 (非代码缺口)
P2: Agent Action SSOT / AgentRun 域缺失 (黑盒执行不可审计内部动作);
    Workforce runtime 状态 (heartbeat); Deployment 域; 危险动作事前
    interception 扩展
P3: Knowledge 域; MCP 真连; real-time 监控; SRE/incident

## 23. DEPENDENCY GRAPH
Session dispatch → intent/actions → service → domain store (JSON)
Execution: gateway → executor (subprocess agent) → finalize (absorb P0 chain)
Learning: bridge(exp) → learning_truth (OBS→CAND→PROM→Profile) → actions
  select_agent (Router) → RD
治理: governance_service ← release/learning/rollback/effectiveness

## 24. WHAT AI FACTORY ACTUALLY IS TODAY
真实 = **生产事实管线的 orchestrator 工作台**: 人类经 WebUI/CLI 下达任务 →
计划/任务 canonical → 委派外部真实 AI CLI (codex/claude/hermes) 执行 →
结果吸收为 EXS/art/ver/EVD canonical → release gate → experience →
governed learning → profile 影响后续 agent 选择。单机、JSON 域存储、
外部 agent 委派模型。

## 25. WHAT IS STILL MISSING
- 内部 Agent runtime (自托管执行, 非外部 CLI 黑盒)
- Agent Action canonical 域 (动作级审计/控制)
- Workforce 实时运行态
- Deployment/环境投放
- 生产数据真实运行 (所有 canonical 域 0)
- Knowledge 域 / MCP 实连 / real-time 监控

## 26. RECOMMENDED NEXT DEVELOPMENT ORDER
(供路线参考, 本审计不启动)
1. P2-E: 用真实生产实验验证闭环收益 (现有 infra 完整)
2. Agent Action/Execution 域: 把外部委派改为可审计动作事实
   (executor 内嵌 tool/action 记录 → ActionTruth)
3. 真实生产运行: 让 canonical 链在 ~/.factory 产生首批真实数据
4. Workforce runtime 状态 + WebUI real-time

## 27. FINAL VERDICT
AI Factory OS 当前 = 生产事实链 + 治理 + 学习账本**基础设施真实成立**
(P0-P2D, M3 级), 但 agent 执行是外部委派黑盒、无 Action 域、无真实生产
数据、WebUI 为 projection 无实时运行。它是"账本+委派"工作台, 距离
"内部多 Agent 自治生产工厂" 缺 Agent Action 域 + 运行时层 + 真实数据。
