# 00 — S50 REPORT: Real User Acceptance / Idea→Delivery E2E (2026-09-07)

## Verdict: S50 BLOCKED — 断点: PLAN→TASK→推进 控制(任务可见性/幂等)

## 真实证据 (全新项目 专注计时器 S50, 真实 Conversation, 真实 LLM)
轮1 "我想做一个简单的 Web 专注计时器…" → REQ-a5e8ec4a (canonical) ✓
轮2 "继续" → execute_plan → PLAN-d2c3e7f7 (canonical) + **6 TASK 真建**
  (TASK-3613cbdd…, workspace/projects/s50/management/backlog/task.json,
  带 plan_id) ✓ 输出 "已建任务 6 个"
轮3-7 "继续" → execute_plan 反复 (agent 以为任务 0 / 计划已消费) —
  **幂等失效 → 任务重复建**: task.json 现 12 (6 带 plan + 6 无 plan 重复)
轮4 project_status 显示 "任务: 0" — 与实际 12 矛盾 (读取不一致)

## 断点 (P0)
1. **execute_plan 幂等失效**: 幂等检查 _existing=list_backlog(project_id)
   读空 → 每轮重复建 6 任务 (污染: 12 tasks; plan_id 关联丢失一半)
2. **project_status 显示 0 vs 实际 12**: 任务可见性不一致 → agent
   看不见真任务 → 反复 execute_plan 空转 (轮3-7)
3. execute_plan 假成功契约: created 空/重复不报错 (ok 恒 True)
4. 轮1 仍跳 idea/discovery (直 REQ — 链头引导不足, 已知 backlog)

## 已证明能工作的 (正面)
- Conversation→REQ→PLAN→TASK 创建 真落盘 (canonical + workspace)
- 执行能力存在: TASK-337e5a8d status=done (真实执行发生过)
- Gate/scope/recovery (S48-FIX/S49-FIX.1) 未退化

## UNRESOLVED (诚实标注)
service._management_store 同路径下 execute_plan create 成功但
project_status/list_backlog(幂等检查)读空 — 需审计 service 装配
(create_app 注入实例 vs agent_loop 内 service 路径) 具体差异;
id↔slug (P-6ac1adb3 vs s50) 层是否双 store 分叉。

## 最小修复方向 (建议, 未实施)
1. execute_plan 幂等/读取用同一 store key (修正 list_backlog 空读根因
   — 定位 create 与 read 的目录/key 分歧)
2. execute_plan: created==0 且 tasks 非空 → 返回结构化失败 (禁假成功)
3. project_status 与 execute_plan 用同一 project→space 解析
4. 回归: 任务重复建禁止 (幂等测试)

## 范围说明
未 bypass / 未 mock / 未用 workflow_runner。Chain 止于 TASK 阶段
(执行有发生但控制不可见) — ACC/Delivery 未触达即发现断点。
