# K3 Architecture — Real Project Operating Loop

> 日期: 2026-08-29 | HEAD: (K3 commit)

## 1. Project OS 结构
```
Production Core (SSOT)
    ├── Project (S43 project_ 实体; parent=req; 绑定 conv)
    │   └── Sprint (S43 sprint_ 实体; parent=project; tasks[])
    │       └── Task (S43 task_ 实体; sprint_id/production_run_id)
    │           └── Run → Artifact → Evidence
    ├── Requirement (req_ 实体; version/supersedes)
    ├── Approval (S17; subject_type=task)
    └── Control Tower (projection, 读 SSOT)
```

## 2. 无第二套 SSOT
- Conversation/TaskTree/ControlTower 全部 projection (读真实 entities/runs/approvals)
- Project 状态 = 实时计算 (非存储)
- 无 duplicated model/lifecycle

## 3. Lineage
Project → Requirement → Conversation 全链可追溯 (trace_lineage)
