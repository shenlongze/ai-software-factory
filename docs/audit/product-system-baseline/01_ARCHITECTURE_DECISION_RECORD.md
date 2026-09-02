# 01 — ARCHITECTURE DECISION RECORD (STEP 10, 2026-09-02)

> 本文件记录的是 2026-09-02 人工批准的架构决策, 不是 AI 自主设计。

## ADR-001 Task Domain 分层 (D-1 B)
- Decision: Planning / Execution / Runtime 是不同实体, 不同实体 ≠ 不同 SSOT
- Rationale: 计划产物/生产任务/运行事实语义不同, 强行合并会污染各层
- Evidence: STEP 9 MASTER_DOMAIN_SSOT_TREE (backlog/execution_plan/exec 三套)
- 正式语义:
  Plan (计划事实) → Task (生产执行任务事实) → Run (一次运行事实)
  → {ExecutionRecord, Artifact, Verification}
- Status: FROZEN

## ADR-002 单向下钻 (D-2)
- Decision: Plan → Task → Run → Record/Artifact/Verification, 不得反向制造第二事实源
- Status: FROZEN

## ADR-003 Domain-local SSOT (D-3)
- Decision: 每个 Domain 只有一个 SSOT; "分层"≠"多 SSOT"
- Status: FROZEN

## ADR-004 Requirement 引用契约 (D-4 C→A→B)
- Decision: 先冻结引用契约 (非永久 Capture); 保留 requirement_id → Product Intent/PRD → Plan 演进
- Status: FROZEN (契约), PRD 实体 = CONTRACT-ONLY (M3 实施)

## ADR-005 PRD 独立 Domain Entity (D-5 A)
- Decision: PRD = 结构化产品承诺 (非 Markdown); 概念身份冻结, 实体不创建
- Status: FROZEN (身份/契约) / ABSENT (当前实体)

## ADR-006 Artifact/Verification 归属 (D-6)
- Decision: Run/Record 持有事实, Task 经 Run 间接可达; Task 上不建第二份 SSOT
- Status: FROZEN

## ADR-007 Agent Selection 输入语义 (D-7)
- Decision: Task → Capability Constraint → Router → Agent
- Status: FROZEN

## ADR-008 Model Selection 进治理链 (D-8)
- Decision: Task/Agent → Model Policy → Model Selection (治理链内)
- Status: FROZEN (契约) / 实施 UNKNOWN (LLMRouter 消费 0 已知, 不修)

## ADR-009 Execution Truth 分层+Domain (D-9 B+D)
- Decision: backlog=Execution Task SSOT; exec=独立 Runtime Domain; execution_plan=历史计划产物
  (不得继续为平行 Task SSOT); 不同 Domain ≠ 平行事实源
- Status: FROZEN (契约) / 迁移不实施

## ADR-010 模块边界 (D-10)
- Decision: console+org+exec = 生产主链; factory-core+factory-runtime = 独立模块
- Status: FROZEN

## 批准记录
- Human Approval: 2026-09-02 (shenlongze)
- Approval Statement: 本 ADR 记录的是人工批准结果, 非 AI 自主设计
