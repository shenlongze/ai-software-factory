# MASTER LIFECYCLE TREE — STEP 9 (2026-09-02)
> 用户输入后系统真实发生什么 (箭头状态: PROVEN/PARTIAL/ABSENT/UNKNOWN/FUTURE)

## CURRENT REAL FLOW (PROVEN 主链 — M4)
```
User
 ↓ PROVEN (session msg, 81)
Session
 ↓ PROVEN (intent 路由 + execution_truth)
Intent
 ↓ PROVEN (plan_development)
Plan (pending)
 ↓ PROVEN (approve → execute_plan, 幂等)
Task + Dependency (backlog, plan_id)
 ↓ PROVEN (ExecState 依赖门控)
Scheduling (Ready/Waiting/Blocked)
 ↓ PROVEN (chain_next → gateway)
Execution → Run
 ↓ PROVEN (finish_task_exec 回写 done/failed/cancelled)
Writeback
 ↓ PROVEN (recover: stale running→UNKNOWN/证据)
Recovery / Retry / Cancel
 ↓ PROVEN (reconcile_plan)
Aggregation (plan completed/failed)
 ↓ PROVEN (audit_events 5160 + task.history)
Audit
```

## BROKEN / PARTIAL LINKS
```
Intent → Requirement: PARTIAL (捕获真实 requirements.json; 无版本/变更)
Requirement → PRD: ABSENT (实体不存在)
PRD → Plan: ABSENT
Execution → Artifact: PARTIAL (exec ART-* 真实; 会话链无 artifact_ref)
Artifact → Verification: PARTIAL (exec test_result; 无下游消费)
Verification → Release: ABSENT (FUTURE)
Execution → Experience: PARTIAL (写入 84; 无读取消费)
```

## FUTURE FLOW (产品自标 M3/M4, 非当前)
```
Requirement 变更 → PRD v2 → replan (M3 L6620)
Experience → Learning → Future Decision (M4 L411)
Release 闭环 (M3/M4)
```

## 生命周期分层结论
- 主执行链 (意图→计划→任务→执行→聚合→审计): PROVEN M4
- 需求产品链 (需求→PRD→计划): 断 (Requirement 捕获 M2, 下游 ABSENT)
- 产物链 (执行→Artifact→Verification→Release): 半开 (exec 域真实, 闭环 ABSENT)
