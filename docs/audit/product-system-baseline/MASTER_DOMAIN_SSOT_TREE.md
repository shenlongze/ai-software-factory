# MASTER DOMAIN / SSOT TREE — STEP 9 (2026-09-02)
> 数据事实由谁负责 — 本 STEP 最重要文档之一

```
状态图例: [CONFIRMED SSOT] [MULTIPLE TRUTHS] [PROJECTION] [UNKNOWN] [ABSENT]

Domain                          SSOT / Truth                         Persistence
│
├── Session                    [CONFIRMED SSOT] console_sessions.json
│                              Writer: SessionStore | ID: sess-*
│
├── Intent                     [PROJECTION] 消息内意图 (无独立 SSOT)
│
├── Requirement                [CONFIRMED SSOT] requirements.json
│                              Writer: agent_loop:795 | ID: req_*
│                              Reader: API | 下游: ABSENT
│
├── PRD                        [ABSENT] 无 domain entity (文档级审批门)
│
├── Plan                       [CONFIRMED SSOT] session_plans.json
│                              Writer: PendingPlanStore | ID: PLAN-*
│                              Lifecycle: pending→executing→completed/failed
│
├── Task  ⚠️ MULTIPLE TRUTHS — 冻结记录 (见下)
│
├── Run                        [CONFIRMED SSOT] gateway registry
│                              Writer: gateway_execute | ID: EXS-* (exec域) / R* (会话链)
│
├── ExecState                  [PROJECTION] session_exec/{sid}.json (可重建)
│
├── Artifact                   [CONFIRMED SSOT(exec域)] exec/results.json
│                              ID: ART-* | 会话链关联: ABSENT
│
├── Verification               [PROJECTION] ExecState verify + exec test_result
│                              SSOT: 未冻结
│
├── Audit                      [CONFIRMED SSOT] audit/audit_events.json
│                              Writer: AuditEmitter | 追加不可变
│
├── Agent                      [CONFIRMED SSOT] agents/agents.json
│                              ID: backend-1 等
│
├── Skill                      [CONFIRMED SSOT] skills/skills.json
│
├── LLM/Provider/Model         [CONFIRMED SSOT] providers.json
│                              选择层 SSOT: 未冻结 (LLMRouter 无消费者)
│
├── Project                    [CONFIRMED SSOT] org/projects.json
│
├── Experience                 [CONFIRMED SSOT(写)] memory/experience_store.json
│                              读消费: ABSENT
│
└── Learning/Release           [ABSENT→FUTURE]
```

## ⚠️ Task Domain Boundary — 三套 Truth 正式冻结 (最高优先级)

```
Domain A: backlog Task  [生产主链]
  Identifier: TASK-* | Storage: workspace/projects/*/management/backlog/task.json
  Producer: create_task/execute_plan | Consumer: ExecState
  Lifecycle: 八态 (todo→ready→in_progress→{review→done}|failed/cancelled)
  Plan 关系: PROVEN (plan_id) | Artifact 关系: ABSENT
  Runtime evidence: E2E (多轮)

Domain B: execution_plan Task  [M3 历史]
  Identifier: T-* | Storage: execution_plan.json
  Producer: orchestrator (actions.py:1758 路径) | Consumer: _run_queue
  Lifecycle: M3 流程 | Plan 关系: UNKNOWN | 会话链关系: ABSENT

Domain C: factory-exec Task  [员工执行]
  Identifier: T00x | Storage: exec/*.json (records/results)
  Producer: exec agent_executor | Consumer: exec 内部
  Lifecycle: 执行记录 | Artifact 关系: PROVEN (ART-*→T00x)
  Runtime evidence: records 100

三者关系:
  backlog → execution_plan: ABSENT (无共享引用)
  backlog → exec: UNKNOWN (exec 经 console 懒装配, task id 不互通)
  execution_plan → exec: ABSENT

结论 (冻结): 三套 Task Truth 并存 = 已确认事实 (STEP5 G-TRUTH-01)。
  同一"任务执行"概念三套标识/存储/生命周期 — 域边界契约未冻结 (UNKNOWN 归属)。
  本 STEP 不做合并判断。Task Template / Planning Entity / Runtime Instance /
  Execution Record / Projection 的边界分类: backlog≈Planning+Runtime 混合,
  exec T00x≈Execution Record, execution_plan≈历史 Planning — 边界语义未形式化。
