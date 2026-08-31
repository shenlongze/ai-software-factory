# K4 Gap Analysis — Control Tower & Real-time Operations

> 日期: 2026-08-29 | HEAD: 86dcdb10 (v1.1.355)

## 15 项审计
| # | 能力 | 现状 | 判定 |
|---|------|------|------|
| 1 | Control Tower 读 SSOT | control_tower 全从真实 entities/runs/approvals 投影 | REAL |
| 2 | Project 状态实时 | project_status (K3, 实时计算) | REAL |
| 3 | Sprint 状态实时 | sprint_status (K3) | REAL |
| 4 | Task 状态实时 | task_progress (K2) | REAL |
| 5 | Node 状态实时 | production_run node_runs 有, 无 tower 层 | PARTIAL |
| 6 | Agent 状态实时 | workforce_status 只有计数, 无 agent 级 "谁在工作" | PARTIAL |
| 7 | Execution 状态实时 | work_overview execution_states | REAL |
| 8 | Approval 实时 | governance_pending (PENDING) | REAL |
| 9 | Failure 实时 | work_overview task_states 有 FAILED, 无 incident 视图 | PARTIAL |
| 10 | Evidence 实时 | 无 tower 层 evidence 视图 | MISSING |
| 11 | Event 驱动 projection | realtime_stream (audit events); 无 operational event stream | PARTIAL |
| 12 | polling-only | 是 (API 查询); 无 SSE/WebSocket | PARTIAL |
| 13 | hidden state | 无 | OK |
| 14 | duplicated state | 无 | OK |
| 15 | 无法解释 status | task FAILED 无原因链 | PARTIAL |

## 结论
- REAL: Project/Sprint/Task/Execution/Approval 状态投影 + realtime_stream
- MISSING: **统一 Operational State Contract / 全链路钻取 (project→evidence) / "谁在工作" agent 级视图 / Idle 原因 / Failure 原因链 / 断线恢复 (snapshot+replay) / 并发一致性验证**

## K4 最小设计
```
operational_state.py:
- OperationalState Contract: PLANNED/QUEUED/RUNNING/WAITING/BLOCKED/PAUSED/FAILED/RECOVERING/COMPLETED/CANCELLED
  (按实体语义: Agent=ACTIVE/RUNNING/IDLE/SUSPENDED/FAILED/RETIRED; Task=PLANNED/READY/RUNNING/BLOCKED/WAITING_APPROVAL/FAILED/COMPLETED/CANCELLED)
- 状态映射: entity.status → operational state (确定性, 非 LLM)
- 全链路钻取: project → sprint → task → node → agent → run → artifact → verification → evidence
- "谁在工作": agent 级 (从真实 run/task 依据: RUNNING task→agent RUNNING; 无 task→IDLE+原因)
- Idle 原因: no_eligible_task / waiting_dependency / policy_denied
- Failure 原因链: task FAILED → incident/recovery → evidence
- snapshot + replay: 断线恢复 (snapshot 当前全状态 + 事件流重放)

control_tower.py 扩展:
- operational_view: 统一 Operational State 视图 (谁在工作/谁卡住/为什么)
- drill_down: project→evidence 全链路
- agent_work: agent 级 "谁在工作" (真实依据)
- global_overview: Projects/Running/Waiting/Blocked/Approval/Failed + Workforce + Recent Activity
- snapshot: 一致性快照 (断线恢复用)
```

## 禁止
- 第二套 SSOT / LLM 计算状态 / Mock realtime / 绕过 Governance / 过度 UI
