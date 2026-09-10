# 三分类裁定表（TRIAGE ADJUDICATION）— 事实源 / 投影 / legacy

> 日期: 2026-09-11 | 性质: **纯文档（零搬家/零建目录/零改 import/零改代码/零删文件）**
> 基线: `cleanup/os-core-restructure-2026-09-11`
> 范围: 7 个 MERGE 域（Project·Approval·Capability·Agent·Learning·Evidence·Verification）+ Scheduler
> 规则（用户裁决）: 先定唯一事实源；其余归 PROJECTION（读事实源的视图，保留）或 LEGACY（→archive/legacy/）
> 通用筛选器: 若"看似多份"实为 **定义/分配/实例三层** → KEEP-MULTI（正确分层，非重复）

---

## 0. Scheduler（已裁决）

```
域: Scheduler
事实源: factory-console/os_core_scheduler.py   证据: 181行 / imp=0 / tests/console + tests/org/test_scheduler.py / 最近 2026-09-10
投影:
  - （无）
并合(数据契约，非多实现):
  - factory-org/org/execution.py(plan_tasks)  → 并入 core/scheduler/ 作为"调度数据契约"
移出(不同维度):
  - factory-console/ops_scheduler.py          → os_services/ops/（定时/cron，非任务调度）
legacy:
  - factory-console/session/scheduler.py      → archive/legacy/  理由: TaskScheduler 旧链遗留（orchestrator 依赖）
未决: 无
边界: core/scheduler 只做"看事实状态 → 返回下一个该执行谁"；cron/周期触发属服务内部定时器，不进 core
```

## 1. Project

```
域: Project
事实源: factory-org/org/projects.py   证据: 938行 / imp=12 / tests/org(全套) / 最近 2026-09-01
投影:
  - factory-console/project_agile.py   ← 读事实源的"Factory 敏捷视图"(backlog/sprint)
  - factory-console/os_core_project.py ← OS 边界（委托事实源，含 conversation 引用解析）
legacy:
  - factory-console/project_os.py      → archive/legacy/  理由: ops/ 实体系统，与 org 双 store 冗余
  - factory-console/project_ssot.py    → archive/legacy/  理由: org↔project 漂移对齐，事实源统一后无意义
未决: 无
```

## 2. Approval

```
域: Approval
事实源: factory-console/governance_service.py   证据: 343行 / imp=13 / tests/llm / 最近 2026-09-06
投影:
  - factory-console/api/approvals.py      ← 读事实源的 Web 只读投影（+POST 委派）
  - factory-org/org/approval.py           ← 读事实源的"工作流 ApprovaGate"（委派）
特殊(Factory 门，保留):
  - factory-console/golden_path.py 双 Gate ← Factory 内部 PRD/Plan 文本门，保留并**上报** OS Approval
legacy:
  - factory-console/session/approval_store.py → archive/legacy/  理由: session bash 批准门，收敛后无用
  - factory-exec/exec/approval.py             → archive/legacy/  理由: git apply 硬门，属旧执行链
未决: 无
```

## 3. Capability

```
域: Capability
事实源: factory-console/os_core_capability.py   证据: 152行 / imp=6 / tests/console / 最近 2026-09-10
投影:
  - factory-org/org/capabilities.py    ← 读事实源的"声明式能力目录"视图（六实体池：Skill/Agent/MCP/WorkflowTemplate/Industry/LLMConfig）
legacy:
  - factory-exec/exec/capability.py    → archive/legacy/  理由: 同名 CapabilityRegistry 撞名，运行时能力分迁入事实源
  - factory-console/workforce.py(ROLE_CAPABILITIES) → archive/legacy/  理由: 角色→能力字符串表，改 capability_ref 引用后无用
保留(契约，非本域多实现，归 extensions):
  - factory-console/plugin_kernel.py   → extensions（plugin 契约）
  - factory-exec/exec/skill.py         → extensions/skills（运行时 Skill，非能力真相）
未决: org/capabilities.py 保留为"目录层"还是"第二事实源"？→ 见 §未决
```

## 4. Agent

```
域: Agent
事实源: factory-console/os_core_identity.py   证据: 231行 / imp=12 / tests/console / 最近 2026-09-10（Agent 归 Identity）
投影:
  - （无）
legacy:
  - factory-console/session/agents.py       → archive/legacy/  理由: AgentRegistry 2.0（主线现用），迁入 Identity 后退役
  - factory-console/session/agent_entity.py → archive/legacy/  理由: agt-* 契约空壳（无种子）
  - factory-console/session/agent_registry.py → archive/legacy/ 理由: factory_agents.json 第二注册表
  - factory-core/agents/models.py           → archive/legacy/  理由: L4 legacy Agent
未决: ⚠️ 迁移窗口内 session/agents.py 仍是主线活跃实现（imp=19）→ **迁移顺序需定**（先建 Identity 投影，再退 legacy）
```

## 5. Learning

```
域: Learning
事实源: factory-console/learning_truth.py   证据: 580行 / imp=2 / tests/llm / 最近 2026-09-06（P2-D 契约最新）
投影:
  - factory-console/memory/experience_store.py ← 读事实源的"经验存储"视图（写方多，作记忆层）
legacy:
  - factory-console/learning_engine_v2.py        → archive/legacy/  理由: S37 旧状态机，被 learning_truth 取代
  - factory-core/intelligence/experience.py      → archive/legacy/  理由: L4 legacy（85 条已隔离）
未决: memory/* 其余文件（learning_loop/auto_learn/recommendation/retrieval）归属 → os_services/memory，是否含 legacy 需 Step 2 逐个核
```

## 6. Evidence

```
域: Evidence
事实源: factory-console/os_core_evidence.py   证据: 120行 / imp=1 / tests/console / 最近 2026-09-10（EV-*）
投影:
  - （无）
legacy:
  - factory-console/evidence_domain.py   → archive/legacy/  理由: EVD-*（P0-F4 现产），迁入 EV-* 后退役
  - factory-console/session/evidence.py  → archive/legacy/  理由: EvidenceBundle（M3 legacy）
未决: ⚠️ evidence_domain 是当前生产 writer（node_runtime 依赖）→ **迁移顺序需定**（先切 writer 到 EV-*，再退）
```

## 7. Verification

```
域: Verification
事实源: factory-console/os_core_verification.py   证据: 84行 / imp=2 / tests/console / 最近 2026-09-10（V-*）
投影:
  - （无）
legacy:
  - factory-console/verification_domain.py → archive/legacy/  理由: ver-*（P0-F3 现产），迁入 V-* 后退役
保留(工具，非 Truth):
  - factory-console/verification.py        → core/events 或 extensions（**验证器**：pytest/语法，产生真实验证信号，非事实源）
未决: ⚠️ verification_domain 是当前生产 writer（node_runtime 依赖）→ **迁移顺序需定**（同 Evidence）
```

---

# 三分类汇总

| 域 | 事实源 | 投影 | legacy |
|----|-------|------|--------|
| Scheduler | os_core_scheduler | 0（+1 数据契约并入，+1 移出到 ops） | 1（session/scheduler） |
| Project | org/projects | **2**（project_agile · os_core_project） | 2（project_os · project_ssot） |
| Approval | governance_service | **2**（api/approvals · org/approval） | 2（session/approval_store · exec/approval） |
| Capability | os_core_capability | **1**（org/capabilities 目录） | 2（exec/capability · workforce ROLE_CAPABILITIES） |
| Agent | os_core_identity | 0 | **4**（session/agents · agent_entity · agent_registry · core/agents） |
| Learning | learning_truth | **1**（memory/experience_store） | 2（learning_engine_v2 · core/intelligence） |
| Evidence | os_core_evidence | 0 | 2（evidence_domain · session/evidence） |
| Verification | os_core_verification | 0 | 1（verification_domain）+1 工具保留 |

**合计**：事实源 8 · 投影 6 · legacy 16 · 工具/契约保留 3

---

# UNCLEAR 清单

| 域 | 未决点 | 为什么 |
|----|-------|--------|
| Capability | `org/capabilities.py` 定位 | 1557 行六实体池：作为"目录层"保留，还是"第二事实源"？它比 os_core_capability(152行) 大 10 倍且含 Industry/WorkflowTemplate/LLMConfig，语义超出 Capability |
| Agent | 迁移顺序 | `session/agents.py` 现为**主线活跃**（imp=19）；退 legacy 前必须先建 Identity 投影，否则破坏生产 |
| Evidence/Verification | 迁移顺序 | `evidence_domain`/`verification_domain` 是**当前生产 writer**（node_runtime 依赖）；退 legacy 前必须先切 writer |
| Learning | memory/* 逐文件归属 | learning_loop/auto_learn/recommendation/retrieval 属 os_services/memory 还是 legacy，需 Step 2 逐个核 |

> 以上 UNCLEAR **均不影响事实源判定**（8 域事实源已明确），只影响**迁移顺序**——按铁律不擅自定，列入 Step 2 前置。

# HARD STOP

本文件为纯文档：**未搬家、未建目录、未改 import、未改代码、未删文件、未推分支**。
8 域三分类已完成 → **等你授权后才进 Step 2（git mv）**。
