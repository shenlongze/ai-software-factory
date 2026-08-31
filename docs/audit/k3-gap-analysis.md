# K3 Gap Analysis — Real Project Operating Loop

> 日期: 2026-08-29 | HEAD: 7df80320 (v1.1.354)

## 20 项审计
| # | 能力 | 现状 | 判定 |
|---|------|------|------|
| 1 | Conversation↔Project 关联 | conv 无 project_id 绑定 | MISSING |
| 2 | Conversation↔Requirement | conversation_os extract_requirement (parent=conv) | REAL |
| 3 | Requirement→Project/Sprint/Task | task_tree 有 requirement→task; 无 project/sprint | PARTIAL |
| 4 | Sprint 正式 Entity | unified_contract 有 sprint_ 前缀, 无 service | MISSING |
| 5 | Task 生命周期跟踪 | task_tree (DRAFT→READY→RUNNING→COMPLETED/FAILED) | REAL |
| 6 | Task↔Agent/Workforce | execute_subtask 有 role; 无 agent 回写 | PARTIAL |
| 7 | Execution 回写 Task 状态 | execute_subtask 更新 task status | REAL |
| 8 | Verification 回写 Task | run state→task status (间接) | PARTIAL |
| 9 | Evidence 回写 Project | 无 project evidence | MISSING |
| 10 | Conversation 读真实 Project State | 无 | MISSING |
| 11 | Requirement 修改→影响 Task | 无 version/replan | MISSING |
| 12 | Task failure→回 Conversation | explain_failure (K1) | PARTIAL |
| 13 | Approval 阻塞/恢复 Work | governance request_approval; 无 task 级 gate | PARTIAL |
| 14 | Project 统一状态投影 | 无 (旧 ops_projection 是 release 级) | MISSING |
| 15 | Sprint 统一状态投影 | 无 | MISSING |
| 16 | Task 统一状态投影 | task_progress (K2) | REAL |
| 17 | Control Tower 读 SSOT | control_tower 全从真实投影 | REAL |
| 18 | 状态变化 Event/Audit/Lineage | S43 entity bump + audit | REAL |
| 19 | Global Context / Hidden State | 无 (state 驱动) | OK |
| 20 | Duplicated model/lifecycle | 无 | OK |

## 结论
- REAL: Task Tree/Control Tower/Conversation 基础 (K1/K2)
- MISSING: **Project/Sprint service + Conversation↔Project 绑定 + 状态投影 + Replan + Approval gate**

## K3 最小设计 (不建第二套 SSOT)
```
project_os.py:
- Project Entity (S43 project_ 前缀): 从 Requirement 创建, 绑定 conv
- Sprint Entity (S43 sprint_ 前缀): project 下创建, 绑定 tasks
- Project→Sprint→Task 层级 (parent_id, 可追溯)
- Execution 回写: task status → sprint/project 状态投影 (实时计算)
- Requirement v2: 新 req 版本 → 识别受影响 task → replan (新 task)
- Approval gate: 高风险 task 执行前 request_approval → 用户批准 → 继续
- project_status: 从真实 task/run/evidence 投影 (Project/Sprint/Task 各层)
- conversation_os 扩展: 创建 project 绑定 conv; "项目做到哪里" 从真实投影回答
```

## 禁止
- 第二套 SSOT / 第二套 Task/Project 模型 / Fake Evidence / LLM 决定 lifecycle
