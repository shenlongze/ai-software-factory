# 06 — EXECUTION TRUTH CONTRACT (STEP 10, 2026-09-02)

## 五实体正式语义 (杜绝 Parallel Truth)

| 实体 | 语义 | 角色 | 允许写 | 只允许引用 |
|------|------|------|--------|-----------|
| A. backlog Task (TASK-*) | Execution Task Domain SSOT | 生产主链任务事实 | ManagementStore (八态转换) | ExecState/UI/API |
| B. execution_plan Task (T-*) | 历史计划产物 (M3) | 历史结构 — 不再写入新事实 | 无 (冻结写入) | 只读/迁移参考 |
| C. factory-exec Task (T00x) | Execution Record Domain | 员工执行记录事实 | exec store | 审计/查询 |
| D. Run | 一次运行事实 | 会话链运行 | gateway | 回写 |
| E. ExecutionRecord | 执行过程事实 | 员工执行完整记录 | exec store | 审计 |

## 核心保证 (INV-012)
- A 是 Execution Task 的唯一 SSOT
- B 不得继续形成独立平行 Task SSOT (不再产生新任务事实; 语义=历史/计划产物)
- C 是独立 Runtime Domain 的事实, 非第二 Task SSOT (通过映射引用对齐, 不平行可写)
- 任何代码不得同时维护两套可独立修改的 Task 状态

## 映射契约 (未来 Fix Sprint 依据, 本 STEP 不实施)
- C 记录引用 A 的 task_id 时使用 A 的 ID (TASK-*) 而非本地 T00x (CONTRACT-ONLY)
- B 的读取需映射到 A 或标记 historical (CONTRACT-ONLY)
