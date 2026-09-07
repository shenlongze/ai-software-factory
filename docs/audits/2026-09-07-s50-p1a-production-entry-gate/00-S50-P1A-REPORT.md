# 00 — S50-P1A REPORT: Production Entry Gate (2026-09-07)

## 1. Root Cause
create_task 工具无 gate — agent 在仅 IDEA(甚至空产品链)时可直接
create_task + 进入代码生产, 绕过 IDEA→DISC→REQ→PRD→PLAN。

## 2-3. Production entry audit
- create_task: 无 gate ← P1-a 修复点
- execute_plan: 有 gate (pending plan + 已消费状态拒绝) ✓
- chain_start/chain_next: 依赖 execute_plan/pending plan 前序 + ExecState ✓
- task_action: 操作已存在任务 (不创建) — 保留
- bash_exec: 写文件类被 APR 审批门拦截 ✓ (Human Control Plane 设计正确)
- 绕过路径确认: create_task 是唯一可直接生产 TASK 的 bypass

## 4-5. Gate boundary / Fix
- Boundary: 生产 TASK 创建需"项目已有合法 PLAN (canonical approved/
  executing) 或会话计划已批准" — 后端 enforce
- _production_entry_gate + create_task handler 集成
- DENIED → {ok:False, blocked, governance:{reason, required_next:PLAN}}
  — 无副作用, Conversation 可继续推进产品链

## 6. Before/After evidence
- Before (S50 rerun): 轮2 裸 create_task TASK-91149490 (无 plan)
- After (测试): IDEA 阶段 dispatch create_task → DENIED + backlog 0;
  PLAN approved 后 → 允许

## 7-8. Tests / Regression
5 (无 plan 拒/仅 REQ 拒/approved plan 允/偷跑 0 副作用/plan 后允)
回归 90 passed | attributable 0 (CLI pre-existing 维持)

## 9. Human Approval untouched
'继续' ≠ approve; APR 卡语义零改动 (脚本/会话不能绕过审批)

## 10. Remaining S50 blocker
P1-b (写文件 APR 需真实 WebUI 人工 approve) — 设计正确, 下一轮
需 S50 Browser Real E2E (人参与审批/ACC)。gate 链序补全后,
浏览器实操即可走 PLAN→TASK→…→Delivery。
