# ADR-0001: Phase 1 EventType 六类口径与 events 表语义列决策

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase1-plan.md` §3.1/§4.1 · `docs/design/event-model.md` §2/§3/§5.1 · `docs/design/phase1-status.md`

## 背景

Phase 1 落地过程中, 三份文档对"六类事件"的表述不一致, 且 plan 的 DDL 缺少任务要求的字段:

1. **六类事件口径冲突**:
   - `phase1-status.md` 范围描述: 六类 Event = `task/agent/workflow/tool/validation/memory` (大类前缀)
   - `phase1-plan.md` §3.1: 六类最小事件 = `task.start / task.end / task.fail / tool.call / checkpoint / session.close` (具体事件名, 含完整模型代码)
   - `event-model.md` §3 六类字典: `task.* / agent.* / validation.* / workflow.* / system.* / human.*`

2. **events 表字段缺失**: `phase1-plan.md` §4.1 DDL 仅有 `task_id/agent_id` 两个维度列; 但任务要求 Event 模型含 `project_id/stage/action/result/evidence` 字段, 存储层需支持 `by_project` 查询, event-model §2.2 定义这四个语义列承载检索与指标。

## 决策

1. **EventType 按 phase1-plan §3.1 实现六类具体事件** (开发计划优先: 有可直接运行的模型代码、便捷方法签名与测试计划)。`phase1-status.md` 的六大类视为事件命名的大类前缀体系 (task./tool./…); 后续按 event-model §3 六类字典扩类时**加枚举成员即可**, type 列存字符串, 不改表结构。

2. **events 表融合 event-model §5.1 语义列**: 在 plan DDL 基础上增加 `project_id / stage / action / result / evidence` 列; 索引覆盖 `task_id / agent_id / project_id / type / timestamp`, 支撑 by_task / by_agent / by_project 回放与 `(stage, result)` 聚合。`payload` JSON 列兜底一切扩展。

3. **"validation 结果统计"指标口径**: MVP 无 `validation.*` 事件, 由 `result` 语义列的 `result_counts` 聚合承载 (OK/PASS/FAIL/ERROR/done/failed 分布); Phase 3 扩出 validation 事件后直接聚合, 不建统计表 (指标从事件算, event-model §6)。

4. **时间存储统一格式**: `%Y-%m-%dT%H:%M:%S.%fZ` (UTC, 固定小数秒), 保证字符串排序 == 时间排序, SQLite 时间范围过滤无歧义 (避免 `datetime.isoformat()` 微秒为 0 时省略小数部分导致的比较错位)。

## 后果

- 便捷方法 `task_fail` 的 `evidence` 同时写入语义列与 payload (语义列可检索, payload 兜底)。
- 新增事件类型 (如 `agent.started` / `validation.failed`) 无需迁移: 加 EventType 成员 + logger 便捷方法即可。
- 若后续需要按大类 (task/agent/validation/...) 聚合, 可由 type 前缀投影, 不另建列。
