# K4 Architecture — Control Tower & Real-time Operations

> 日期: 2026-08-29 | HEAD: (K4 commit)

## 1. 架构
```
Production Core (SSOT)
    ├── Entities (S43) / Runs (S3) / Approvals (S17) / Events (audit)
    ↓
Projection Layer (operational_state.py + control_tower.py)
    ├── work_overview / workforce_status / governance_pending / realtime_stream
    ├── drill_down (project→sprint→task→run→evidence + why)
    ├── who_is_working (agent 级真实依据 + Idle 原因)
    └── global_overview / snapshot
    ↓
Control Tower (CLI/API/Web)
```

## 2. 无第二套 SSOT
- 所有状态从真实 entities/runs/approvals/events 实时投影
- Control Tower 无自己的状态库
- Operational State Contract = 确定性映射 (entity.status → operational state, 非 LLM)

## 3. 一致性
- snapshot + restore: 断线恢复 (比较 executions/task_states/workforce)
- 最终一致性: task 变化 → tower 投影实时反映 (test_realtime_consistency)
