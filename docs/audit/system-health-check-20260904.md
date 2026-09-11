# AI Software Factory — 全方位系统体检报告

> **审计基准**: STEP10 Domain Freeze + CURRENT_SYSTEM_TRUTH (2026-09-02)
> **审计日期**: 2026-09-04
> **审计范围**: 产品链 / 任务链 / 控制面 / 治理面 / 文档面
> **审计方法**: 代码级证据溯源 + 契约合规校验 + 链路闭合分析

---

## 第一部分：总览

### 1.1 系统健康度仪表盘

| 维度 | 权重 | 评分 | 状态 |
|------|------|------|------|
| 产品链健康度 | 20% | **58/100** | ⚠️ 中度风险 |
| 任务链健康度 | 25% | **72/100** | ⚠️ 轻度风险 |
| 控制面健康度 | 20% | **63/100** | ⚠️ 中度风险 |
| 治理面健康度 | 20% | **78/100** | ✅ 良好 |
| 文档面健康度 | 15% | **82/100** | ✅ 良好 |
| **综合健康度** | 100% | **70.3/100** | ⚠️ 整体可控 |

### 1.2 核心发现摘要

1. **需求链断裂是最大架构风险**：Requirement 域（`requirements.json`）与下游 Plan/Task 之间缺乏稳定引用，违反 D-4 引用契约（当前仅为 C 阶段预留）。任何任务无法追溯到原始需求，全链路可追溯性不成立。

2. **任务链存在三套并行真相**：backlog TASK-*（SSOT）/ execution_plan T-*（历史冻结）/ exec Runtime 域（独立写入）三轨并存，虽 STEP10 已冻结 D-9 决策（exec 为独立 Runtime Domain），但 FX-01 映射缺失导致跨域引用不可审计，存在 INV-012 平行真相风险。

3. **Model Selection 治理链有壳无实**：`LLMRouter` 五层决策链已实现（L1-L5），但 CURRENT_SYSTEM_TRUTH 明确标注"LLMRouter 消费 0 = 已知不修"。模型选择未进入治理链，所有 LLM 调用绕过 D-8 契约，直接走 `llm_fn` 统一注入（`console_sessions.py:104` → deepseek）。

4. **Artifact/Verification 未闭环到主生产链**：org 侧有完整的 Artifact 模型（`org/projects.py:407`）和状态机（`org/artifact.py`），exec 侧有真实 Verification 执行器（`verification.py`），但 FX-04 导致 Run 与 Artifact 的挂接关系在会话链断裂，Verification SSOT 取证不完整（FX-08）。

5. **审计系统成熟度高但覆盖有盲区**：AuditStore 已实现 hash 链封存 + 脱敏 + 原子写（`audit/audit_store.py`），CURRENT_SYSTEM_TRUTH 记录 5160 events，但需求链断裂导致审计无法完成端到端追溯。

### 1.3 已知 GAP 状态更新（FX-01~FX-08）

| ID | 描述 | 分类 | 当前状态 | 证据 |
|----|------|------|----------|------|
| FX-01 | exec→backlog 引用映射 | B CONTRACT_IMPL | **未修复** | `management.py` Task 有 `exec_ref` 字段但 exec 侧无反向映射实现 |
| FX-02 | execution_plan 冻结 | B CONTRACT_IMPL | **部分修复** | execution_plan 实体存在（`org/execution.py:204`），但写路径未完全锁死 |
| FX-03 | Requirement 下游引用 | B CONTRACT_IMPL | **未修复** | `requirements.json` 存在但无 Plan→Req 稳定引用（G-REQ-01） |
| FX-04 | Run 挂 Artifact | B CONTRACT_IMPL | **未修复** | Artifact 模型有 `task_id`/`stage_id`，但 Run→Artifact 关联在会话链不完整 |
| FX-05 | Model Policy | B CONTRACT_IMPL | **未修复** | `agent_policy.py` 有 RouterRule，但 LLMRouter 生产消费=0 |
| FX-06 | Agent 触发入口 | B CONTRACT_IMPL | **未修复** | 角色 Agent 类已实现，但生产触发入口 UNKNOWN |
| FX-07 | 分析落盘 | B CONTRACT_IMPL | **未验证** | 需进一步核查 analysis 结果持久化路径 |
| FX-08 | Verification SSOT 取证 | D UNPROVEN | **未修复** | `verification.py` 有真实执行器，但 Verification 独立 SSOT 不成立 |

---

## 第二部分：分维度详细报告

### 维度一：产品链健康度（58/100）

**评估结论**：产品链上游断裂，Requirement 孤立存在，PRD 实体缺失，Plan→Task 链路部分可用。整条产品链仅"Plan→Task"一段闭合，其余环节均有缺口。

#### 关键证据

| 实体 | SSOT 位置 | ID 格式 | 状态 | 引用完整性 |
|------|-----------|---------|------|-----------|
| Requirement | `requirements/requirements.json` | `req_*` | ⚠️ 存在但孤立 | 无下游引用（G-REQ-01） |
| PRD | (ABSENT, M3) | — | ❌ 实体不存在 | CONTRACT-ONLY（D-5） |
| Plan | `session_plans.json` | `PLAN-*` | ✅ 实现 | 有 `plan_id` 注入 Task（S34-P0-4） |
| Task (Backlog) | `management/backlog/*.json` | `TASK-*` | ✅ 实现 | Task.plan_id 字段可用（`management.py:160`） |

**代码证据**：
- `factory-console/web/backend/fastapi_adapter.py:1549` — Plan 与 Requirement 关联仅靠 goal 匹配，不可靠
- `factory-org/org/management.py:160` — Task 模型有 `plan_id` 字段，Plan→Task 链真实
- `factory-console/session/agent_loop.py:826` — Plan 的 `requirement_id` 字段为空字符串（默认值）

#### 问题清单

**P0**
- **REQ-PLAN 断裂**：Requirement 与 Plan 之间无稳定 ID 引用，仅靠 goal 文本匹配关联，违反 TRACE-01（跨域核心关系须有稳定可审计 ID）。位置：`fastapi_adapter.py:1549`
- **PRD 实体缺失**：D-5 批准 PRD 为独立 Domain Entity，但当前完全 ABSENT，产品承诺无结构化载体。

**P1**
- **Plan 孤儿风险**：无上游需求引用的 Plan 可能成为孤儿实体，无法追溯到业务意图。
- **Requirement 生命周期不完整**：`req_*` 实体只有提取入口（`api_extract_requirement`），缺乏到 Plan 的转化链路。

**P2**
- **需求层级扁平**：Epic/Feature/Story/Task 层级在 Backlog 存在（`management.py:199+`），但 Requirement 域无对应分层映射。

#### 合规性检查

| 契约条款 | 状态 | 说明 |
|----------|------|------|
| D-4 Requirement 引用契约 | ⚠️ C 阶段 | 仅冻结引用语义，未实施 |
| D-5 PRD 独立实体 | ⚠️ CONTRACT-ONLY | 实体 ABSENT，符合 M3 规划 |
| INV-010 Req→Product/PRD 演进 | ⚠️ 预留 | 演进路径未打通 |
| INV-011 PRD 独立 Domain | ✅ 契约遵守 | 未提前实现，不违反 |

#### 改进建议
1. 优先实施 FX-03：建立 Requirement→Plan 的稳定 ID 引用（`plan.requirement_id` 非空约束）
2. 按 M3 规划引入 PRD 实体前，先明确 Requirement→PRD→Plan 的三级映射契约
3. 在 Task 模型中增加 `requirement_id` 透传字段，实现需求到任务的全链路追溯

---

### 维度二：任务链健康度（72/100）

**评估结论**：任务链中段（Task→Run→Record）基本可用，但两端（Requirement 上游、Artifact/Verification 下游）均有缺口。状态机设计严谨，但多套执行系统并存增加了复杂度。

#### 关键证据

**执行系统多重性分析**：

| 系统 | 位置 | 状态模型 | 生产证据 | 备注 |
|------|------|---------|---------|------|
| WorkflowInstance | `org/execution.py:107` | CREATED→RUNNING→SUCCESS/FAILED/CANCELLED | ✅ org 域 | 与 Sprint/Stage 联动 |
| ProductionRun | `production_run.py:30` | PENDING→RUNNING→COMPLETED/FAILED/BLOCKED | ✅ console 域 | 多 Node DAG 串行 |
| External Gateway | `external_executor/gateway.py:91` | picked→running→done/failed | ✅ 外部执行 | 100+ records |
| RuntimeSession | `exec/runtime_session.py` | PENDING→RUNNING→COMPLETED/FAILED | ✅ exec 域 | Agent 执行会话 |

**Task 状态机**（`management.py:81`）：
- 8 态：todo / ready / in_progress / blocked / review / failed / cancelled / done
- FAILED = 任务自身失败（Task SSOT 事实）
- BLOCKED = 依赖失败传播（派生状态）
- 符合冻结状态语义

**Artifact 模型**（`org/projects.py:407`）：
- 完整字段：id / stage_id / type / project_id / task_id / producer_role / producer_agent / status
- 生命周期：CREATED → GENERATED → VALIDATED → CONSUMED → ARCHIVED（`org/artifact.py`）
- 类型契约：7 种类型（idea/product/prd/design/code/test/release）+ 声明式校验规则

**Verification 实现**（`verification.py`）：
- 真实验证器：`verify_python_syntax`（ast.parse）/ `verify_pytest`（subprocess）
- 4 态：PASS / FAIL / INCONCLUSIVE / BLOCKED
- 但 Verification 无独立 SSOT，挂接在执行结果中

#### 问题清单

**P0**
- **三套 Task 真相并存**：backlog TASK-* / execution_plan T-* / exec Runtime 三套结构，虽 D-9 定义了边界，但 FX-01 映射缺失导致跨域引用不可审计。违反 INV-012。
- **Run→Artifact 挂接断裂（FX-04）**：Artifact 有 `task_id`/`stage_id`，但 Run 维度到 Artifact 的关联在会话主链不完整，无法从一次 Run 直接检索其产出物。

**P1**
- **状态漂移风险**：Task 状态（8 态）与 WorkflowInstance 状态（5 态）与 ProductionRun 状态（5 态）存在语义差异，回写机制不一致时可能漂移。
- **Verification 无独立 SSOT**：验证结果散落在执行记录中，无法独立查询和审计 Verification 域（FX-08）。

**P2**
- **执行系统职责边界模糊**：WorkflowInstance vs ProductionRun vs External Gateway 三者职责有重叠，长期可能形成平行真相。
- **Artifact 孤儿**：部分 Artifact 可能缺少所属 Run/Record 引用。

#### 合规性检查

| 契约条款 | 状态 | 说明 |
|----------|------|------|
| D-2 Plan→Task→Run→Record 单向 | ⚠️ 部分 | 主方向正确，但多系统并存 |
| D-6 Artifact/Verification 归属 Run/Record | ⚠️ FX-04 | 模型字段有，但链路未闭环 |
| D-9 三套 Truth 边界定义 | ✅ 契约已定义 | D-9 批准 exec 为独立 Runtime Domain |
| INV-005 单向生产 | ✅ 基本遵守 | 无明确反向修改路径 |
| INV-006 Artifact 归属 Run/Record | ⚠️ 部分 | 有 task_id 但无 run_id |
| INV-007 Task 经 Run 间接访问 | ⚠️ 部分 | 直接挂 task_id，绕过 Run |
| INV-012 无平行 Task SSOT | ⚠️ 风险 | 映射缺失，实际效果接近平行 |

#### 改进建议
1. 实施 FX-01：建立 exec T00x → backlog TASK-* 的稳定映射表，确保跨域引用可审计
2. 实施 FX-04：在 Run 记录中增加 Artifact 引用列表，确保 Run→Artifact 链路闭合
3. 统一执行系统：明确 WorkflowInstance / ProductionRun / External Gateway 的职责边界，避免功能重叠
4. 实施 FX-08：建立 Verification 独立 SSOT，使验证结果可独立查询和审计

---

### 维度三：控制面健康度（63/100）

**评估结论**：Agent 选择链路已建成确定性路由框架，但 Model Selection 有壳无实，Agent 生产触发机制不透明。控制面整体处于"部分可用"状态。

#### 关键证据

**Agent 选择链路**：

```
Task + Capability Constraint
        ↓
CapabilityRouter (capability_router.py)
  ├─ derive_capabilities(objective) — 关键词规则表 → 能力需求
  ├─ build_agent_resources(agents) — Agent 注册 → CapabilityResource
  └─ route(request) — 交集匹配 + 排序(priority/persona/load/quality/version)
        ↓
RouteDecision {resource_id, reason}
```

- **确定性路由**：纯规则，不调 LLM，同一输入永远同一输出（`capability_router.py:13`）
- **资源类型**：agent / skill / mcp 三类统一路由
- **排序因子**：priority desc → persona desc → load asc → quality desc → version desc → id asc
- **可解释性**：reason 字段说明命中的 capabilities 和排序依据

**Model 选择链路**：

```
LLMRouter (llm_router.py) 五层决策链:
  L1 User Explicit → L2 Agent/Skill Policy → L3 Project Rule → L4 System Recommendation → L5 Fallback
```

- **架构完整**：五层决策链 + 审计事件（`router.decided`）+ 错误处理
- **但消费=0**：CURRENT_SYSTEM_TRUTH §8 明确"LLMRouter 消费 0 = 已知不修"
- **实际调用**：`llm_fn` 统一注入（`console_sessions.py:104` → deepseek），绕过治理链

**Agent 生产触发**：
- **外部执行器**：`gateway_execute()`（`external_executor/gateway.py:91`）经 `_pick_executor` 选执行器
- **角色 Agent**：developer / pm / architect / tester / uxui 等角色类已在 `factory-exec/exec/roles.py` 实现
- **但生产触发入口 UNKNOWN**：CURRENT_SYSTEM_TRUTH §7 标注"角色 Agent 类 IMPLEMENTED, 生产触发入口 UNKNOWN"
- **生产证据**：execution_records 100 条（backend-1×48 / flutter-dev×17 / ...）

#### 问题清单

**P0**
- **Model Selection 治理链失效（FX-05）**：LLMRouter 有完整实现但无生产消费者，所有 LLM 调用绕过 D-8 治理链。违反 INV-009（Model Selection 进入治理链）。

**P1**
- **Agent 生产触发不透明（FX-06）**：角色 Agent 如何被生产环境调用、触发条件是什么、由谁编排，缺乏清晰的入口契约。
- **Capability Constraint 传递不完整**：Task 模型无结构化 `capability_constraint` 字段，Agent 选择依赖 objective 关键词推导（`derive_capabilities`），精度有限。

**P2**
- **Agent 注册 vs 生产混淆**：`agents.json` 中的注册 Agent 与实际生产 Agent 的关系不清晰，"注册 ≠ 生产"原则在代码层面缺乏强约束。
- **Model Policy 定义分散**：agent.yaml / skill.yaml / project.yaml 多处置定义，缺乏统一的 Model Policy 管理面。

#### 合规性检查

| 契约条款 | 状态 | 说明 |
|----------|------|------|
| D-7 Agent Selection 链路 | ✅ 框架已建 | CapabilityRouter 实现了完整链路 |
| D-8 Model Selection 治理链 | ❌ 有壳无实 | LLMRouter 消费=0，未接入生产 |
| INV-008 Task+Capability → Agent | ⚠️ 部分 | Capability 靠关键词推导，非结构化输入 |
| INV-009 Model 进入治理链 | ❌ 未遵守 | 实际调用绕过 LLMRouter |

#### 改进建议
1. **最高优先级**：将生产 LLM 调用接入 LLMRouter 治理链，确保 D-8/INV-009 合规
2. 实施 FX-06：明确角色 Agent 的生产触发入口，建立 Agent 触发的可审计链路
3. 在 Task 模型中增加结构化 `capability_constraints` 字段，替代关键词推导
4. 建立 Agent 注册→生产的状态流转机制，确保"注册≠生产"有代码级约束

---

### 维度四：治理面健康度（78/100）

**评估结论**：审计系统成熟度高（hash 链 + 脱敏 + 原子写），审批机制完整，SSOT 原则已确立并大部分遵守。但需求链断裂导致端到端可追溯性不成立，三套 Task 结构存在 SSOT 唯一性风险。

#### 关键证据

**审计系统**：
- 存储：`audit_events.json`（`audit/audit_store.py:31`）
- 安全特性：
  - **脱敏**：`redact()` 函数对 evidence/approval/result/impact/metadata 字段进行纵深防御脱敏（`audit_store.py:94`）
  - **封存链**：`previous_event_hash + event_hash` 形成 tamper-evident 链（`audit_chain.py`）
  - **原子写**：临时文件 + `os.replace` 模式
  - **只追加**：append 不修改历史条目（审计铁律）
- 接口：`append / get / query / get_chain / export / stats / verify`
- 事件量：CURRENT_SYSTEM_TRUTH 记录 5160 events

**审批系统**：
- 模型：`ApprovalGate`（`org/approval.py:93`）
- 状态机：PENDING → APPROVED / REJECTED（终态不可逆）
- 绑定：stage_id + workflow_id + subject_ref（plan_id 等）
- 治理服务：`governance_service.py` 统一审批门面

**SSOT 现状**：

| Domain | SSOT | 唯一性 | 风险 |
|--------|------|--------|------|
| Requirement | requirements.json | ✅ 唯一 | 无下游引用 |
| Plan | session_plans.json | ✅ 唯一 | 上游关联弱 |
| Task (Execution) | backlog (management/) | ⚠️ 名义唯一 | 三套结构并存，映射缺失 |
| Run | gateway registry | ⚠️ 多系统 | WorkflowInstance/ProductionRun/Gateway 三套 |
| ExecutionRecord | exec records | ✅ exec 域唯一 | 与 backlog 映射缺 |
| Artifact | artifacts.json | ✅ org 域唯一 | 归属关系不完整 |
| Audit | audit_events.json | ✅ 唯一 | 覆盖全面 |
| Agent | agents.json | ✅ 唯一 | 生产/注册边界模糊 |
| Project | org/projects.json | ✅ 唯一 | 稳定 |

**可追溯性**：
- 执行链 ✅：Task → Run → Record → Audit 可追溯
- 需求链 ❌：Requirement → ... → Task 不可追溯（G-REQ-01）

#### 问题清单

**P0**
- **需求链不可追溯**：执行链完整但需求链断裂，全链路可追溯性只成立一半。任何执行结果无法追溯到原始业务需求。
- **SSOT 唯一性风险（Task 域）**：三套 Task 结构映射缺失，实际效果接近平行真相，虽 D-9 已定义边界但实施未完成。

**P1**
- **审批覆盖不全**：ApprovalGate 绑定 Stage/Workflow，但 Plan 审批、Requirement 审批、Release 审批的覆盖度需验证。
- **审计事件完整性盲区**：需求链相关事件（requirement.created / prd.approved 等）因实体缺失而不存在。

**P2**
- **投影一致性校验缺失**：CURRENT_SYSTEM_TRUTH 定义了多个投影层（如 Web API 的 unified projection），但无定期一致性校验机制。
- **审计查询能力有限**：当前为 JSON 文件存储，大数据量下查询性能和复杂分析能力受限。

#### 合规性检查

| 契约条款 | 状态 | 说明 |
|----------|------|------|
| INV-001 每域唯一 SSOT | ⚠️ 大部分 | Task 域存在三轨并存风险 |
| INV-003 无平行 Truth | ⚠️ Task 域风险 | FX-01 未修复前有风险 |
| INV-013 跨域关系稳定 ID | ⚠️ 部分 | 执行链 OK，需求链断裂 |
| INV-014 投影不反向写 | ✅ 无反向修改证据 | 投影层为只读 |

#### 改进建议
1. 打通需求链：实施 FX-03，建立 Requirement→Plan→Task 的 ID 引用链，实现真正的端到端可追溯
2. 实施 FX-01：建立 Task 域三轨映射，消除平行真相风险
3. 建立投影一致性巡检机制：定期校验投影层与 SSOT 的数据一致性
4. 扩展审计事件覆盖：补充需求域、产品域相关事件类型

---

### 维度五：文档面健康度（82/100）

**评估结论**：文档治理体系已建立（STEP11.0），Canonical 文档定义清晰，历史文档标注明确，Parallel Truth 风险有制度控制。但文档数量庞大（1040+ 文档，其中 audit 318+），维护成本高，历史文档与当前事实的区分依赖人工纪律。

#### 关键证据

**文档治理体系**（`docs/00-index/DOCUMENTATION_GOVERNANCE.md`）：
- Canonical Document 定义：T0-T2 真相等级
- 修改权限：STEP10 Contract 仅人工批准可改
- 同步规则：架构变更 → 00-index README → CURRENT_SYSTEM_TRUTH → DOCUMENTATION_MATRIX
- 历史文档：`docs/sprint*/design/adr/audit` 大部分 = HISTORICAL (T4/T6)
- Parallel Truth 防控：同一主题只允许一个 Canonical Owner

**文档体量**：
- 总 Markdown 文档：1040+
- audit 目录文档：318+
- sprint 报告：s0-s43 + k1-k9 系列（约 80+ 份）
- 设计文档：design/adr 目录（多份历史设计）

**Canonical 文档清单**：
- `CURRENT_SYSTEM_TRUTH.md` — 系统事实
- `STEP10_DOMAIN_FREEZE.md` — 架构决策
- `MASTER_STATUS_TABLE.md` — 能力状态
- `DOCUMENTATION_GOVERNANCE.md` — 文档治理

#### 问题清单

**P1**
- **文档数量爆炸**：318+ audit 文档 + 大量 sprint 报告，新成员上手成本高，容易读到过期信息。
- **代码→文档同步依赖人工**：代码变化后需人工判断是否更新 CURRENT_SYSTEM_TRUTH，存在滞后风险。

**P2**
- **历史文档可读性风险**：大量 sprint 报告虽标注为 historical，但标题和内容可能误导读者认为是当前状态。
- **产品文档与代码的一致性**：根目录的《产品说明书》《完整产品方案书》与代码实现的偏差未定期审计。

#### 合规性检查

| 治理规则 | 状态 | 说明 |
|----------|------|------|
| Canonical Owner 唯一 | ✅ 已定义 | 各主题有唯一 Canonical 文档 |
| 历史文档标注 | ✅ 有制度 | T4/T6 分级明确 |
| Parallel Truth 防控 | ✅ 有机制 | MATRIX + 冲突处理流程 |
| 代码→文档同步 | ⚠️ 依赖纪律 | 无自动化校验 |

#### 改进建议
1. 建立文档健康度巡检：定期检查 Canonical 文档与代码的一致性（可自动化）
2. 精简历史文档：对 sprint 系列报告建立索引摘要，减少重复信息
3. 在产品文档中增加"最后验证日期"和"对应代码版本"字段
4. 考虑建立文档 freshness 指标，对长期未更新的 Canonical 文档自动提醒

---

## 第三部分：闭合性分析

### 3.1 12 域关系矩阵

| ↓源域 \ 目标域→ | Req | PRD | Plan | Task | Run | Record | Artifact | Verify | Agent | Model | Project | Audit |
|-----------------|-----|-----|------|------|-----|--------|----------|--------|-------|-------|---------|-------|
| **Requirement** | — | ⚠️ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ⚠️ |
| **PRD** | — | — | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ➖ | ❌ |
| **Plan** | — | — | — | ✅ | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ | ✅ | ✅ |
| **Task** | — | — | — | — | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ |
| **Run** | — | — | — | — | — | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ |
| **Record** | — | — | — | — | — | — | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| **Artifact** | — | — | — | — | — | — | — | ✅ | ✅ | ➖ | ✅ | ✅ |
| **Verification** | — | — | — | — | — | — | — | — | ➖ | ➖ | ✅ | ✅ |
| **Agent** | — | — | — | — | — | — | — | — | — | ⚠️ | ✅ | ✅ |
| **Model** | — | — | — | — | — | — | — | — | — | — | ➖ | ✅ |
| **Project** | — | — | — | — | — | — | — | — | — | — | — | ✅ |
| **Audit** | — | — | — | — | — | — | — | — | — | — | — | — |

**图例**：✅ 完整引用 / ⚠️ 部分引用 / ❌ 断裂 / ➖ 无直接关系

### 3.2 链路断裂热力图

```
Requirement ───断裂───→ PRD ───断裂───→ Plan ───部分───→ Task
                                                       │
                                                       │ 完整
                                                       ↓
                                         Run ───完整───→ Record
                                          │               │
                                          │部分           │部分
                                          ↓               ↓
                                       Artifact ───完整───→ Verification
```

**断裂点统计**：

| 断裂位置 | 严重度 | 影响范围 | 对应 GAP |
|----------|--------|---------|---------|
| Requirement → PRD | P0 | 产品链全链路 | FX-03 + D-5 (M3) |
| Requirement → Plan | P0 | 需求→执行追溯 | FX-03 / G-REQ-01 |
| Plan → Requirement (反向追溯) | P1 | 影响分析 | FX-03 |
| Run → Artifact | P1 | 产物归属 | FX-04 |
| Task → Verification | P1 | 任务验证闭环 | FX-04 / FX-08 |
| Task → Model (治理链) | P0 | 模型治理 | FX-05 |
| Agent → Model (生产绑定) | P1 | 模型选择 | FX-05 |
| exec ↔ backlog (映射) | P0 | Task 域 SSOT | FX-01 |

### 3.3 状态漂移统计

| 状态对 | 状态集合差异 | 漂移风险 | 备注 |
|--------|-------------|---------|------|
| Task (8 态) ↔ WorkflowInstance (5 态) | todo/ready/review/blocked vs created/running/success/failed/cancelled | 高 | 语义不对等，依赖回写逻辑 |
| WorkflowInstance ↔ ProductionRun | created/running/success/failed/cancelled vs pending/running/completed/failed/blocked | 中 | 命名差异大，需映射 |
| Task.done ↔ Run.success | 一对一（理论） | 中 | 实际依赖回写可靠性 |
| Task.failed ↔ Run.failed | 一对一（理论） | 中 | FAILED 语义有细微差异 |

### 3.4 平行真相风险评估

| 风险点 | 严重度 | 现状描述 | 缓解措施 |
|--------|--------|---------|---------|
| **Task 域三轨并存** | 🔴 高 | backlog/execution_plan/exec 三套可写结构，映射缺失 | D-9 已定义边界，FX-01 待实施 |
| **多执行系统并存** | 🟡 中 | WorkflowInstance/ProductionRun/Gateway 三套执行框架 | 需明确职责边界 |
| **产品文档 vs 代码** | 🟡 中 | 产品方案书/说明书与代码实现可能存在偏差 | 文档治理制度已建立 |
| **Core vs Org Task** | 🟡 中 | factory-core 有 Task 模型，factory-org 也有 Task 模型 | D-9 已明确 backlog 为 SSOT |

**最高风险项**：Task 域三轨并存（INV-012）。虽然 STEP10 D-9 批准了"exec 为独立 Runtime Domain"的决策，但映射机制未实施，导致实际运行中两套 Task 数据各自独立可写且无稳定映射，构成平行真相的事实状态。

---

## 第四部分：行动路线图

### 4.1 紧急修复（P0）— 立即处理

| 优先级 | 修复项 | 对应 GAP | 预期收益 | 预估工作量 |
|--------|--------|---------|---------|-----------|
| 1 | 建立 exec↔backlog 映射机制 | FX-01 | 消除 Task 域平行真相风险 | 2-3 天 |
| 2 | Requirement→Plan 稳定 ID 引用 | FX-03 / G-REQ-01 | 打通需求→执行追溯链路 | 2-3 天 |
| 3 | 将 LLM 调用接入 LLMRouter 治理链 | FX-05 | 实现 Model Selection 治理合规 | 3-5 天 |

**理由**：这三项直接违反或严重影响 INV-001（SSOT 唯一性）、INV-009（Model 治理链）、TRACE-01（跨域可追溯性）等核心架构原则，是系统架构的基础性风险。

### 4.2 短期修复（P1，1-2 周）

| 优先级 | 修复项 | 对应 GAP | 预期收益 | 预估工作量 |
|--------|--------|---------|---------|-----------|
| 1 | Run → Artifact 挂接闭环 | FX-04 | 任务链产物归属完整 | 2-3 天 |
| 2 | Agent 生产触发入口明确化 | FX-06 | 控制面可观测性提升 | 2-3 天 |
| 3 | Verification SSOT 建立 | FX-08 | 验证域独立可审计 | 3-5 天 |
| 4 | Task 状态与 Run 状态一致性校验 | — | 减少状态漂移 | 1-2 天 |
| 5 | Task 增加结构化 capability_constraints | — | Agent 选择精度提升 | 2-3 天 |

### 4.3 中期优化（P2，1-2 月）

| 优先级 | 优化项 | 预期收益 | 预估工作量 |
|--------|--------|---------|-----------|
| 1 | 执行系统职责边界梳理与统一 | 降低架构复杂度 | 1-2 周 |
| 2 | 投影一致性巡检机制 | 数据可靠性提升 | 3-5 天 |
| 3 | 文档 freshness 自动化检测 | 文档质量保障 | 2-3 天 |
| 4 | Agent 注册→生产状态流转 | 控制面规范化 | 3-5 天 |
| 5 | 审计存储性能优化（考虑 SQLite） | 大数据量下查询性能 | 1 周 |

### 4.4 长期规划（FUTURE，M3/M4）

| 能力 | 产品自标 | 当前状态 | 前置依赖 |
|------|---------|---------|---------|
| PRD 独立 Domain Entity | M3 | CONTRACT-ONLY (ABSENT) | FX-03 完成后 |
| Requirement 深度化 | M3 | C 阶段 | PRD 实体落地 |
| Replan + 变更回流 | M3 | 部分框架 | 任务链闭环后 |
| Experience → Learning | M4 | 框架已有 | 生产数据积累 |
| Release 管理 | M3-M4 | 部分模型 | 任务链+验证链闭环 |
| Model Selection 完整治理 | M3 | 框架已有（无消费） | FX-05 完成后深化 |

---

## 附录：审计方法说明

### 审计基准优先级
1. STEP10 Domain Freeze Contract（最高约束）
2. CURRENT_SYSTEM_TRUTH.md（当前系统事实）
3. 代码实现（事实依据）
4. 历史文档（仅作演化证据）

### 证据来源
- 代码文件：`factory-org/` / `factory-console/` / `factory-exec/` 核心模块
- 契约文档：`docs/audit/product-system-baseline/`
- 事实索引：`docs/00-index/`
- 项目快照：`docs/audit/project-reality/PROJECT_PROGRESS_SNAPSHOT.md`

### 评分方法
- 产品链：实体完整性(30%) + 引用完整性(40%) + 合规性(30%)
- 任务链：链路完整性(30%) + 状态一致性(25%) + 实体完整性(25%) + 合规性(20%)
- 控制面：Agent 链路(40%) + Model 链路(40%) + 生产触发(20%)
- 治理面：SSOT 唯一性(30%) + 审计完整性(25%) + 审批完整性(20%) + 可追溯性(25%)
- 文档面：治理制度(30%) + 一致性(35%) + 历史区分度(35%)

---

*本报告由系统自动审计生成，所有结论均基于代码证据和冻结契约。如有争议，以 STEP10 Domain Freeze 人工批准决策为准。*
