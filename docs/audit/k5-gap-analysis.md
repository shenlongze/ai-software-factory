# K5 Gap Analysis — Conversation Experience & Control Tower Production Usability

> 日期: 2026-08-29 | HEAD: d95415fb (v1.1.356)

## 12 项审计
| # | 能力 | 现状 | 判定 |
|---|------|------|------|
| 1 | Conversation 作为普通用户入口 | conversation_os (K1) 有 Intent/多轮/Work 触发 | PARTIAL (CLI/API 有, Web 无) |
| 2 | 自然讨论 (非命令) | _make_reply 模板 (DISCUSS 澄清/讨论) | PARTIAL (模板级, 非 LLM) |
| 3 | 多轮保持 goal/decisions/pending/topic | ConversationState (K1) | REAL |
| 4 | Conversation→Requirement→Decision→Work 闭环 | K1/K3 (req/decision/project/task) | REAL |
| 5 | 用户确认→进入 Project/Sprint/Task | K3 create_project/create_sprint | REAL |
| 6 | Task 执行结果回 Conversation | K1 trigger_work summary + work_items | REAL |
| 7 | Conversation drill-down 到 Work | operational_state drill (K4) | PARTIAL (无 conversation 入口) |
| 8 | Control Tower 反映 Operational State | operational_state (K4) | REAL |
| 9 | Web/CLI/API 同一 SSOT/Contract | 全部经 Service | REAL |
| 10 | realtime stale/race/duplicate 风险 | polling + snapshot (K4) | PARTIAL (无 SSE) |
| 11 | 用户看"正在发生什么" | global_overview (K4) | REAL |
| 12 | Approval 属治理闭环 | K3 approve_task_execution | REAL |

## 结论
- REAL: Conversation 闭环/K3 全链/Operational State/Control Tower 投影
- MISSING: **用户语言质量验证 (8 项) / Golden Conversation Suite (G1-G20) / Conversation drill-down 入口 / Web Conversation 页 (前端) / 真实 LLM 多轮对话**

## K5 设计 (Production Usability, 不扩架构)
```
1. conversation_quality.py: 用户语言质量验证 (清晰/一致/不跑题/不遗忘/不幻觉/不越权/不过度行动/结果解释)
2. golden_suite.py: G1-G20 Golden Conversation Suite (deterministic contract tests + real LLM E2E)
3. conversation_os 扩展: drill_down (conversation→work 链路)
4. 前端: Conversation 页 (接 /api/conversations, 三入口: Conversation/Work/Control Tower)
5. Context Cost 可观测: conversation 每轮记录 token/context 估算
```

## 禁止
- 第二套 SSOT/Event/State/Governance; 不扩 Core; 不 mock E2E
