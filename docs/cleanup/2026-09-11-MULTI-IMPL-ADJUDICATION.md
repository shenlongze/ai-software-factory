# 多实现裁定表（MULTI-IMPL ADJUDICATION）

> 日期: 2026-09-11 | 性质: **纯文档（零搬家/零改代码/零删文件）**
> 基线: `cleanup/os-core-restructure-2026-09-11` @ 52c83854(+2 docs/artifacts commits)
> 目的: HARD STOP 2（同一职责 ≥3 实现）的裁定依据。**人裁决后才进 Step 2。**
> 取证法: 行数=`wc -l`；最近改动=`git log -1 --date=short`；被 import 数=`grep -rl` 模块名（**通用文件名如 models/execution/logger 含泛匹配，仅参考**）；测试=file 名匹配。

---

## 建议图例
`KEEP-ACTIVE` 定为唯一实现，其余降 legacy ｜ `MERGE` 需合并（附规则） ｜ `KEEP-MULTI` 真需多份（附边界） ｜ `UNCLEAR` 无法判断，需人看

---

## 1. Role（4 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-org/org/models.py` (Role) | 193 | 2026-08-08 | tests/org | 162* | Role 实例=权限载体(`role_ref`→exec) | KEEP-MULTI(实例层) |
| `factory-exec/exec/roles.py` | 365 | 2026-08-09 | tests/exec | 6 | ROLE_REGISTRY；**org 侧 docstring 承认其为"事实源"** | KEEP-MULTI(Definition 层) |
| `factory-console/session/roles.py` | 171 | 2026-08-15 | tests/console | 6 | RoleSystem 关键词匹配旧链（orchestrator 用） | MERGE→legacy |
| `factory-console/os_core_role.py` | 211 | 2026-09-10 | tests/console | 1 | Role Assignment（MU-CORE-03） | KEEP-MULTI(Assignment 层) |

**域建议：KEEP-MULTI** ｜理由：三层语义清晰（Definition=exec/roles · Assignment=os_core_role · 实例=org.Role），非重复；`session/roles.py` 旧链降 legacy（orchestrator 收敛后退役）。

## 2. Project（5 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-org/org/projects.py` | 938 | 2026-09-01 | tests/org | 12 | ProjectLifecycle（L0 组织容器，最完整） | KEEP-ACTIVE(SSOT) |
| `factory-console/os_core_project.py` | 168 | 2026-09-10 | tests/console | 3 | OS 边界（委托 org），MU-CORE-05 | KEEP-ACTIVE(OS 边界) |
| `factory-console/project_os.py` | 270 | 2026-08-31 | tests/llm | 7 | ops/ 实体（legacy，与 org 双 store） | MERGE→legacy |
| `factory-console/project_agile.py` | 324 | 2026-09-11 | tests/console | 1 | Factory 敏捷视图（backlog/sprint） | KEEP-MULTI(projection) |
| `factory-console/project_ssot.py` | 94 | 2026-09-01 | tests/org | 1 | org↔project 漂移对齐（仅 name/status） | MERGE |

**域建议：MERGE** ｜规则：**org=Project SSOT**；`os_core_project`=OS 边界；`project_os`/`project_ssot` 合并入 org（或降 legacy）；`project_agile` 保留为 **projection**。

## 3. Approval（5-6 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/governance_service.py` | 343 | 2026-09-06 | tests/llm | 13 | S17 OS 服务（POLICIES+Release） | KEEP-ACTIVE(SSOT) |
| `factory-org/org/approval.py` | 191 | 2026-08-09 | tests/org | 5 | 工作流 ApprovaGate（接 org Workflow） | MERGE(委派 OS) |
| `factory-console/api/approvals.py` | 171 | 2026-08-09 | tests/console | 1 | Web 只读投影+POST→org | KEEP-MULTI(projection) |
| `factory-console/session/approval_store.py` | 100 | 2026-08-28 | tests/console | 2 | session bash 批准门 | MERGE→legacy |
| `factory-exec/exec/approval.py` | 242 | 2026-08-20 | tests/exec | 5 | git apply 硬门禁 | MERGE→legacy |
| `factory-console/golden_path.py`(双 Gate) | — | (保护区) | tests/console | — | PRD/Plan 文本门（非 governance 记录） | KEEP-MULTI(Factory 门)+上报 |

**域建议：MERGE** ｜规则：收敛为**单一 OS Approval 域**（governance_service 为 SSOT）；org/approval 委派；session/exec 门降 adapter；golden_path 双 Gate 保留为 Factory 门并**上报** OS。

## 4. Capability（6 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-org/org/capabilities.py` | 1557 | 2026-08-11 | tests/org | 1 | 六实体池（声明式目录） | KEEP-ACTIVE(目录) |
| `factory-console/os_core_capability.py` | 152 | 2026-09-10 | tests/console | 6 | OS Capability（CAP-*） | KEEP-ACTIVE(OS SSOT) |
| `factory-exec/exec/capability.py` | 578 | 2026-08-08 | tests/exec | 5 | **同名 CapabilityRegistry**（运行时能力分） | MERGE(改名+并表) |
| `factory-exec/exec/skill.py` | 420 | 2026-08-13 | tests/exec | 2 | SkillRegistry（运行时） | KEEP-MULTI(runtime) |
| `factory-console/workforce.py` | 252 | 2026-08-30 | tests/llm | 5 | ROLE_CAPABILITIES（角色→能力字符串） | MERGE |
| `factory-console/plugin_kernel.py` | 308 | 2026-08-31 | tests/llm | 12 | plugin capabilities（llm.complete 等） | KEEP-MULTI(plugin 契约) |

**域建议：MERGE** ｜规则：产**统一 Capability 词表**，各域用 `capability_ref` 引用；org=声明式目录、os_core=OS SSOT、plugin=运行时；消除 `CapabilityRegistry` 撞名。

## 5. Agent（4 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/session/agents.py` | 754 | 2026-08-25 | tests/console | 19 | AgentRegistry 2.0（**主线在用**） | KEEP-ACTIVE |
| `factory-console/session/agent_entity.py` | 176 | 2026-08-22 | tests/console | 5 | agt-* 契约（空壳，无种子） | MERGE |
| `factory-console/session/agent_registry.py` | 173 | 2026-08-22 | tests/console | 7 | factory_agents.json 注册表 | MERGE |
| `factory-core/agents/models.py` | 107 | 2026-08-05 | tests/* | 162* | L4 legacy Agent | MERGE→legacy |

**域建议：MERGE** ｜规则：4→1，并入 **OS Identity(Agent)**；其余为 Identity 的 projection/adapter。

## 6. Scheduler（4 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/os_core_scheduler.py` | 181 | 2026-09-10 | tests/console | **0** | OS Scheduler（MU-CORE-12）但**零消费者** | ? |
| `factory-org/org/execution.py`(plan_tasks) | 1551 | 2026-08-11 | tests/org | 5 | 调度**模型**（纯函数） | ? |
| `factory-console/ops_scheduler.py` | 236 | 2026-08-30 | tests/llm | 3 | ops cron 循环 | ? |
| `factory-console/session/scheduler.py` | 458 | 2026-08-24 | tests/console | 1 | TaskScheduler（旧链 orchestrator 用） | ? |

**域建议：UNCLEAR** ｜理由：四者语义不同且**无一为"唯一 OS 调度"**（os_core_scheduler 是目标但 0 消费者未接线；org plan_tasks 是模型；ops_scheduler 是定时任务；session/scheduler 是旧链），**无法判断该留谁**，需你裁定。

## 7. Learning（4 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/learning_truth.py` | 580 | 2026-09-06 | tests/llm | 2 | P2-D 链（OBS→CAND→PROM→PROFILE），契约最新 | KEEP-ACTIVE |
| `factory-console/learning_engine_v2.py` | 369 | 2026-08-31 | tests/llm | 6 | S37 旧状态机 | MERGE→legacy |
| `factory-console/memory/experience_store.py` | 174 | 2026-08-17 | tests/llm | 19 | 经验存储（写方多） | KEEP-MULTI(存储) |
| `factory-core/intelligence/experience.py` | 332 | 2026-08-06 | tests/* | 27* | L4 legacy（85 条已隔离） | MERGE→legacy |

**域建议：MERGE** ｜规则：learning_truth 为 SSOT；learning_engine_v2/core-intelligence 降 legacy；experience_store 保留为记忆存储。

## 8. Audit（3 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/audit/audit_store.py` | 221 | 2026-08-17 | tests/console | **35** | 链式 AuditEvent（sha256），生产在用 | KEEP-ACTIVE |
| `factory-org/org/execution.py`(AuditStore) | 1551 | 2026-08-11 | tests/org | 5 | 自有 audit.log 格式（项目级） | MERGE→adapter |
| `factory-core/events/logger.py` | 119 | 2026-08-05 | tests/* | 24* | EventLogger（枚举冻结） | MERGE→legacy |

**域建议：KEEP-ACTIVE**（audit_events 唯一）｜其余降 adapter/legacy。

## 9. Evidence（3 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/evidence_domain.py` | 138 | 2026-09-05 | tests/console | 2 | EVD-*（生产在用，P0-F4） | KEEP-ACTIVE |
| `factory-console/os_core_evidence.py` | 120 | 2026-09-10 | tests/console | 1 | EV-*（OS，未接线） | MERGE(目标) |
| `factory-console/session/evidence.py` | 369 | 2026-08-24 | tests/console | 5 | EvidenceBundle（M3 legacy） | MERGE→legacy |

**域建议：MERGE** ｜规则：os_core_evidence(EV-*) 为目标 SSOT；evidence_domain(EVD-*) 迁入；session/evidence 降 legacy。

## 10. Verification（3 实现）

| 实现路径 | 行数 | 最近改动 | 测试 | imp | 判定证据 | 建议 |
|---------|------|---------|------|-----|---------|------|
| `factory-console/verification_domain.py` | 186 | 2026-09-05 | tests/console | 4 | ver-*（生产在用，P0-F3） | KEEP-ACTIVE |
| `factory-console/os_core_verification.py` | 84 | 2026-09-10 | tests/console | 2 | V-*（OS，未接线） | MERGE(目标) |
| `factory-console/verification.py` | 81 | 2026-08-29 | tests/console | 5 | **验证器**（pytest/语法，非 Truth） | KEEP-MULTI(工具) |

**域建议：MERGE** ｜规则：os_core_verification(V-*) 为目标；ver-* 迁入；verification.py 保留为**验证器工具**（非 Truth）。

---

# 建议汇总（10 域）

| 建议 | 域数 | 域 |
|------|------|-----|
| **KEEP-ACTIVE** | 1 | Audit |
| **MERGE** | 7 | Project · Approval · Capability · Agent · Learning · Evidence · Verification |
| **KEEP-MULTI** | 1 | Role |
| **UNCLEAR** | 1 | **Scheduler** |

# UNCLEAR 清单（需人裁定）

| 域 | 为什么无法判断 |
|----|---------------|
| **Scheduler** | 4 实现语义各异且**无一为"唯一 OS 调度"**：`os_core_scheduler`(目标但 imp=0 未接线) / `org/execution.plan_tasks`(模型) / `ops_scheduler`(cron) / `session/scheduler`(旧链)。无法按证据判定唯一实现 → **请你定**：谁是 OS Scheduler？其余是 adapter / legacy 还是不同子职责（cron vs 任务调度）？ |

---

# HARD STOP

本文件为纯文档：**未搬家、未建目录、未改 import、未改代码、未删文件、未推 cleanup 分支**。
10 域裁定建议已给出（1 UNCLEAR 需你定）→ **等你裁决后进 Step 2**。
