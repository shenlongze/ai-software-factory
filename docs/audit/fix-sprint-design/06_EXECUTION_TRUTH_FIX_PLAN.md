# 06 — EXECUTION TRUTH FIX PLAN (STEP11)
> 最高优先级。目标: 三套 Truth 不形成 Parallel Truth (INV-012)

## 三关系判定
| 关系 | 判定 | 证据 |
|------|------|------|
| backlog TASK-* → execution_plan T-* | ABSENT → DEPRECATED/HISTORICAL | STEP4 EXECUTION_RELATION (无共享引用) |
| backlog TASK-* → exec T00x | ABSENT/UNKNOWN → 需映射 (FX-01) | exec records 无 TASK-* 引用 |
| execution_plan T-* → exec T00x | ABSENT (均历史/记录) | — |

## Fix 边界
FX-01: exec ExecutionRecord 增加 task_ref → 引用 backlog TASK-* (写时解析; 旧 T00x 保留历史不迁移)
FX-02: execution_plan 写入路径冻结 (actions M3 不再产生新任务事实; 标记 historical)
不做: 不合并存储 / 不删历史 / 不迁移旧数据

## 验收
- 新建 exec 执行记录可经 task_ref 回溯 backlog Task
- execution_plan.json 不再新增任务 (只读/历史标记)
- grep 证明无新平行 Task 写路径
