# STEP 10 — DOMAIN / SSOT CONTRACT FREEZE (2026-09-02)

> 本文件记录的是 2026-09-02 人工批准的架构决策, 不是 AI 自主设计。

## 1. Status
FROZEN (Contract-only; 零代码, 零迁移)

## 2. Approval Date
2026-09-02

## 3. Human Approval Statement
D-1~D-10 由 shenlongze (CTO/架构 Owner) 于 2026-09-02 逐条批准。
本文件是批准结果的正式 Contract Freeze, 非 AI 设计产物。

## 4. Scope
- 冻结 Domain / SSOT / Relation / Execution Truth / Control Plane Attachment / 模块边界
- 不含实现设计 / 迁移 / 新实体创建

## 5. Architecture Principles (最高治理条款)
SSOT-01 任一事实只能有一个 Domain SSOT
SSOT-02 跨 Domain 可引用/映射/投影
SSOT-03 跨 Domain 不得形成第二个可独立修改的事实源
DOMAIN-01 不同实体可属不同 Domain
DOMAIN-02 不同 Domain ≠ 平行 Truth
TRACE-01 跨 Domain 核心关系须有稳定可审计 ID
TRACE-02 无 ID Contract 的关系 = UNPROVEN/UNKNOWN
FLOW-01 主链: Plan → Task → Run → Record/Artifact/Verification
CONTROL-01 Agent: Task → Capability Constraint → Router → Agent
CONTROL-02 Model: Task/Agent → Model Policy → Model Selection

## 6. D-1 ~ D-10 Decisions
D-1  Task 定义: B 分层 (Planning/Execution/Runtime 不同实体 ≠ 不同 SSOT)
D-2  关系: Plan → Task → Run → Record/Artifact/Verification 单向下钻
D-3  SSOT: 每 Domain 唯一 SSOT ("分层"≠"多 SSOT")
D-4  Requirement: C→A→B (先冻结引用契约, 保留 → Product/PRD → Plan 演进)
D-5  PRD: A 独立 Domain Entity (结构化产品承诺; 本 STEP 不建实体)
D-6  Artifact/Verification: Run/Record 持有, Task 经 Run 间接可达
D-7  Agent Selection: Task → Capability Constraint → Router → Agent
D-8  Model Selection: Task/Agent → Model Policy → Model Selection (治理链)
D-9  Execution Truth: B+D (backlog=Task SSOT; exec=Runtime 域; execution_plan=历史)
D-10 模块: console+org+exec=生产主链; core+runtime=独立模块
(细节见 01_ARCHITECTURE_DECISION_RECORD.md)

## 7. Task Domain Model
见 03_TASK_DOMAIN_CONTRACT.md
- Plan (计划事实) → Task (执行任务事实) → Run (运行事实) → {Record/Artifact/Verification}
- backlog TASK-* = Execution Task SSOT
- execution_plan T-* = 历史计划产物 (不再写新事实)
- exec T00x = Execution Record Domain (独立 Runtime 域, 引用对齐)

## 8. Domain / SSOT Matrix
见 02_DOMAIN_MODEL_FREEZE.md + 04_SSOT_CONTRACT.md
12 个正式 Domain; 每域唯一 Write Owner

## 9. Relation Contract
见 05_RELATION_CONTRACT.md (12 条关系, cardinality/direction/ID/status)

## 10. Execution Truth Contract
见 06_EXECUTION_TRUTH_CONTRACT.md
A=Task SSOT / B=历史 / C=Record 域 / D=Run / E=ExecutionRecord — 杜绝 Parallel Truth

## 11. Agent / Model Control Plane Contract
见 08_AGENT_SELECTION_CONTRACT.md + 09_MODEL_SELECTION_CONTRACT.md
Agent 选择 CURRENT M3 (router); Model 选择 CONTRACT-ONLY (LLMRouter 消费 0 不修)

## 12. Requirement → Product → Execution Contract
见 07_REQUIREMENT_PRODUCT_EXECUTION_CONTRACT.md
Req → (Product Intent/PRD) → Plan → Task → Run → Artifact/Verify → Audit
当前允许引用契约, 不设计死未来语义

## 13. Module Boundary
见 10_MODULE_BOUNDARY_CONTRACT.md
console+org+exec = 生产主链; core+runtime = 独立模块 (INV-015)

## 14. Current vs Future Boundary
CURRENT: Requirement capture / Planning / Execution Task / Run / Record(exec) / Artifact(exec) / Audit / Agent / Project
CONTRACT-ONLY: PRD 实体 / Model Selection / Requirement 下游引用 / Artifact 会话链关联
FUTURE (产品自标): Learning / Replan / Release / PRD 深度化

## 15. Contract Invariants
INV-001 一个事实只能有一个 Domain SSOT
INV-002 不同实体不代表不同事实源
INV-003 不同 Domain 不得形成平行 Truth
INV-004 Task 必须能明确定位其 Domain
INV-005 Plan → Task → Run → Record 单向生产
INV-006 Artifact/Verification 事实归属 Run/Record 域
INV-007 Task 经 Run 间接访问 Artifact/Verification
INV-008 Agent Selection 以 Task+Capability Constraint 为输入
INV-009 Model Selection 进入治理链
INV-010 Requirement 保留 → Product/PRD 演进引用语义
INV-011 PRD 概念身份 = 独立 Domain Entity
INV-012 backlog/execution_plan/exec 不得形成三个平行 Task SSOT
INV-013 跨 Domain 核心关系须稳定 ID 可审计
INV-014 Projection 不得反向成为事实源
INV-015 无生产证据模块不得描述为 CURRENT PRODUCTION

## 16. Forbidden States
- Task 携带第二份 Artifact/Verification 事实
- execution_plan 作为平行可写 Task SSOT 继续产生新任务事实
- Plan 被 Task/Run 反向修改
- exec T00x 与 backlog TASK-* 各自独立可写且无映射 (平行真相)
- Model Selection 绕过治理链直接改 provider

## 17. Known Contract Conflicts
- C-01: backlog TASK-* (当前唯一 Task 写路径) vs exec T00x (独立写路径) —
  批准决策 D-9: exec 为独立 Runtime Domain (引用对齐), 实施映射留 Fix Sprint
- C-02: requirements.json 无下游 (STEP5 G-REQ-01) vs 批准 D-4 引用契约 —
  一致 (C 阶段即冻结引用), 无冲突
- C-03: PRD 实体 ABSENT (M3) vs 批准 D-5 独立实体 — 一致 (CONTRACT-ONLY)
Conflicts 已记录, 无自行裁决项 (均与批准决策一致或属实施层)

## 18. Evidence Index
- STEP 1-5: docs/audit/fact-discovery/ (FACT_REGISTRY, FACT_VERIFICATION,
  RELATION_REGISTRY, EXECUTION_RELATION, GAP_REGISTRY)
- STEP 6: GAP_PRINCIPLE_MATRIX, SEVERITY_VALIDATION (原则冲突: P-DG-04 vs P-MOD-02)
- STEP 7: docs/audit/capability-maturity/ (29 能力, SSOT 三套真相证据)
- STEP 8: docs/audit/project-reality/ (MASTER_STATUS_TABLE, REALITY_INDEX)
- STEP 9: 本目录 MASTER_DOMAIN_SSOT_TREE (三套 Truth 冻结), SYSTEM_BOUNDARY

## 19. Impact Boundary
- 后续 Fix Sprint 挂载点: Task 映射 (C 引用 A ID) / Requirement 引用契约 /
  Model Policy 接入 / PRD 实体 (M3) — 均需遵守本 Contract
- 本 STEP 不触发任何代码/schema/API/数据变更

## 20. STEP 10 Completion Statement
架构决策层已冻结: 12 Domain / 唯一 SSOT / Task 分层语义 / Execution Truth 契约 /
Control Plane Attachment / 15 Invariants / 模块边界 — 全部人工批准, 零代码变更。
Ready for Fix Sprint (等待下一指令, 不自动进入)。
