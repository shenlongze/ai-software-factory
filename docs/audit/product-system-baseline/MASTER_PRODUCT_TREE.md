# MASTER PRODUCT TREE — STEP 9 (2026-09-02)
> AI Factory 提供什么能力 (基于 STEP 1-8, 每个叶子绑定 M + 证据)

```
AI FACTORY 产品能力 (v1.1.364)
│
├── 01 交互层 Interaction
│   ├── Session 会话          [M4 CLOSED_LOOP]  console_sessions 81
│   ├── Intent 意图            [M4]  query_engine + execution_truth
│   └── Requirement 需求捕获    [M2]  requirements.json 7 (无下游)
│
├── 02 产品智能层 Product Intelligence  ⚠️ 未闭环
│   ├── Discovery 澄清         [M1]  discovery_intelligence (conversation 集成)
│   ├── Market/Competitive 分析 [M1]  product_intelligence (不落盘)
│   ├── PRD                   [M0]  实体 ABSENT (M3 承诺)
│   └── UX                    [M0]  无结构化实体
│
├── 03 规划层 Planning
│   ├── Plan 计划              [M4]  plan_development→session_plans
│   ├── Task 任务              [M4]  backlog 八态
│   ├── Dependency 依赖        [M4]  ExecState 门控
│   └── Scheduling 调度        [M4]  Ready/Waiting/Blocked E2E
│
├── 04 员工层 Workforce
│   ├── Agent 执行器           [M3]  records 100 (backend-1 等)
│   ├── Agent Selection 选择    [M3]  gateway router
│   ├── Skill                 [M1]  skills.json 2.5MB (消费未知)
│   └── Tool 工具              [M3]  _fc 注册 + E2E
│
├── 05 智能控制层 Intelligence Control  ⚠️ 未闭环
│   ├── LLM Invocation         [M4]  llm_fn→deepseek
│   ├── Provider               [M3]  providers.json
│   ├── Model Catalog          [M2]  providers models
│   ├── Model Selection        [M1]  LLMRouter 消费 0
│   └── Routing                [M1]  无生产消费者
│
├── 06 执行层 Execution
│   ├── Run                    [M4]  gateway registry
│   ├── Recovery               [M3]  ExecState.recover
│   ├── Retry                  [M4]  FAILED→READY
│   ├── Cancel                 [M4]  CANCELLED
│   └── Reconciliation         [M4]  reconcile_plan
│
├── 07 产物/验证层  ⚠️ 部分
│   ├── Artifact               [M2]  exec ART-* (会话链无关联)
│   └── Verification           [M2]  exec test_result
│
├── 08 治理层 Governance
│   ├── Audit                  [M4]  5160 events
│   ├── Approval               [M3]  approvals
│   └── Traceability           [PARTIAL] 执行链✅ 需求链❌
│
├── 09 学习层 Learning          [FUTURE M4]  experience 84 写无读
├── 10 发布层 Release           [FUTURE]  端点存在 runtime UNKNOWN
│
└── 11 项目管理 Project Mgmt    [M4]  org projects/backlog/sprint/roadmap
