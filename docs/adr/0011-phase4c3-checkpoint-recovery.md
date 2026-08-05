# ADR-0011 — Phase 4C-3: Checkpoint & Recovery

> 日期: 2026-08-06 | 状态: Accepted

## 背景

进程中断 (workflow RUNNING / execution RUNNING / agent WORKING) 后, 需要从持久化现场恢复:
checkpoint 保存停靠点快照, recover 回放事件链重建状态并与持久化比对, 纠正中断残留。
事件链是"发生了什么"的审计真相, 持久化是"现在卡在哪"的现场 — recover 以持久化现场为准纠正。

## 决策

### 1. RecoveryService 两个操作流: checkpoint / recover
`checkpoint(task_id)`: 任务存在 → 读 WorkflowRun/Assignments/Executions/Agent 状态 → 计算
event_seq 锚点 → 构建 Checkpoint 落盘 (存储先落地, 事件后发 — 铁律) → 发
recovery.started → recovery.completed。同任务重复 checkpoint 覆盖旧快照 (最新停靠点为准)。
`recover(task_id)`: 回放事件重建四域状态 (EventReplay) → 与持久化比对 → 纠正中断
(场景1 继续 Step / 场景2 Execution RUNNING→PENDING 可重试 / 场景3 释放 Agent) →
终态工作流拒绝 (场景4, resume_ok=False, 不改任何状态) → 发 recovery.started →
recovery.completed (result=OK/rejected) 或 recovery.failed (异常时)。

### 2. 回放终态不回头
Assignment 进入终态 (COMPLETED/FAILED/RELEASED) 后, 后续 assignment.* 事件不回改状态
(回放幂等 — 终态即审计终点)。released 后 completed 事件不把 assignment 改回 COMPLETED。

### 3. 恢复纠正不发域事件
纠正动作 (execution RUNNING→PENDING / assignment→RELEASED / agent→AVAILABLE) 直接经持久化
原语, 不发 agent.released 等域事件 — 恢复动作的审计由 recovery.* 事件 (recovery.completed
的 actions 清单) 承载, 与正常释放流事件隔离, 避免审计混淆。

### 4. 锚点语义: 快照时刻的最后任务事件
checkpoint.event_seq = 调用时刻该任务最后事件 seq; checkpoint 自身追加的 recovery.*
事件不计入 (锚点是快照时刻的停靠点, 不是操作后的审计位置)。recover 的 last_event 是
回放锚点 (事件链最后 seq), 每次 recover 追加 recovery.* 审计事件 → 锚点只增不减。

### 5. 幂等恢复
重复 recover 无 RUNNING execution / 非终态 assignment 可纠正时, 结果与动作清单稳定
(resume_ok/state 不变, 无纠正动作), 不产生重复副作用 — 纠正动作均以状态检查为前置。

### 6. Agent 释放保护
释放 assignment 时, 仅当 Agent 不再被任何非终态 assignment 占用才回 AVAILABLE
(恢复只纠正本任务现场, 不破坏其他任务对同一 Agent 的占用残留)。

## 验证

- pytest 1103+ 全绿 (recovery 122 用例全过)
- CLI 冒烟: 中断 execution + WORKING agent → checkpoint → recover → execution PENDING /
  agent AVAILABLE / continue step; 终态工作流 recover 拒绝不改状态
