# 05 — LEGACY BOUNDARY (P0-FINAL, 2026-09-04)

> Legacy 与 Current 边界确认 — 无迁移/无重构/无污染

---

## 1. 对象分类 (验收扫描)

| 对象 | 分类 | 代码证据 | 进入 canonical? |
|---|---|---|---|
| TASK-* (backlog) | **CURRENT CANONICAL Task** | org.management.Task | — |
| run-* (NodeRun) | **CURRENT CANONICAL TaskRun** | node_runtime | — |
| EXS-* | **CURRENT CANONICAL Execution result** | record_invocation | — |
| EXR-* | LEGACY/ADAPTER (exec 请求域) | exec models/store (AgentRuntime 域) | ✗ (未提升) |
| TASK-GW-* | ADAPTER (委派控制面) | task_registry (gateway 内部) | ✗ (recover 仅 legacy 兜底) |
| task-e1-* | LEGACY (M3 orchestrator) | orchestrator.py | ✗ |
| task-chg-* | LEGACY (change_control M3 项目域) | change_control.py (execution_plan.json) | ✗ |
| T-* | HISTORICAL (execution_plan) | STEP10 D-9 冻结 | ✗ |
| 历史 session_exec (6) | ORCHESTRATION STATE (E2E 测试痕迹) | session_exec/*.json | ✗ (未处置, 用户决策) |
| 历史 EXS (无锚) | 旧数据 | execution_records.json | ✗ (空锚保留) |
| factory.db | EVENT MIRROR | events 表 | ✗ (非 canonical authority) |

## 2. 零迁移确认 (验收扫描)

- grep migrate/migration/backfill/reconstruct/rebind: 仅 ProjectSpaceStore legacy
  目录懒迁移 (workspace 布局, 非 execution-truth) 与 console_sessions 协议迁移 —
  **无 TASK-*/run-*/EXS-* 数据重构**。
- E2E 全程隔离 tmp; ~/.factory 未被读写。
- 新代码只加字段/函数, 不迁移旧记录。

## 3. 边界原则

```
Legacy (EXR/TASK-GW/task-e1-*/T-*/task-chg-*/历史 session_exec)
      ║  historical only — 只读保留为证据; 不迁移/不重连/不复制
      ▼
Current Canonical: TASK-* → run-* → EXS-* → finalize → Task 终态
```

无任何代码把 legacy id 重建为 canonical 链 (recover 对 TASK-GW 只读兜底,
不写 canonical; 对旧数据空锚不猜测)。
