# K3 Control Tower — 实时状态投影

> 日期: 2026-08-29

## 投影链
```
Events / Production State (SSOT)
    ↓
Projection (实时计算)
    ↓
Control Tower (project_status/sprint_status/work_overview)
```

## 能力
- Project→Sprint→Task 各层 status/progress
- Workforce: running/waiting/blocked/error/idle
- Governance: pending approvals
- Realtime: 最近事件流 (correlation 可追溯)

## 原则
不创建第二套数据库状态; 每次查询实时从 SSOT 投影。
