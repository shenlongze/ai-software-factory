# 00 — S50-P0-FIX REPORT (2026-09-07)

## 1-2. Root Cause / Evidence
- 写路径: execute_plan/chain_start → service._management_store(project_id)
  → space.ensure_space → workspace/projects/{slug=s50}/management/backlog/task.json
- 读路径: project_status(_format_project_entry) + project_tasks 经
  query_engine._project_task_stats 拼 workspace/projects/{project_id} +
  projects/{pid}/tasks.json → 不存在 → 0
- S50 证据: task.json 12 条真实; service.list_backlog(P-6ac1adb3)=12
  (build_console_service 直测); project_status 显示 0 → 读路径 bug
- 附加发现: chain_start 不感知 execute_plan 已建任务 → 重复建 6 (无
  plan_id) — execute_plan 幂等本身正常 (已消费拒绝 ✓)

## 3-5. Canonical Store / Identity Contract
- Canonical = service._management_store → space._effective_slug
  (project.slug → name slugify → id) — 写入已正确
- 读必须经同一 service 解析 (勿拼 project_id 目录)

## 6-9. 修复
- _format_project_entry(root, pid, proj, service=None): service 可用 →
  list_backlog 统计 (12 任务/8%); fallback query_engine
- project_status / project_list 传 service
- project_tasks: service.list_backlog 全量源 (priority/detail)

## 10-12. Tests / Regression / Changes
- 新测试 2 (create==list==status 2任务; 跨项目隔离) | 回归 95 passed
- commit 9e54596b

## 13-15. Remaining / Verdict
- Remaining: chain_start 重复建任务防护 (P1 — 与 execute_plan 幂等协调)
- Verdict: S50-P0-FIX ACCEPTED (create==visible 一致性修复)
