# AI Factory 2.0 — Production Core Contract (S0.5 Freeze)

> 日期: 2026-08-29 | 状态: FROZEN (S1 依据) | 依据: 三份审计报告 + 当前代码复核
> 目的: 防止 Domain Contract 在 S1-S4 连续返工
> 本阶段: 只固化 Contract — 零业务代码修改

---

## 0. 代码复核结论 (Contract 与现有代码对齐)

| 现有代码 | 能力 | 复用策略 |
|---------|------|---------|
| artifact_contract.py (346行) | set_artifact / get_artifact_version / validate | **扩展** (加生命周期状态机) |
| session/delivery.py (169行) | apply_patch(project_dir, patch_text) → (ok, msg) | **直接复用** (不重写) |
| external_executor/executor.py | run / record_invocation / verify_invocation / record_cost / auto_verify | **对齐契约** (补方法名) |
| llm_gateway.py | 3 类 Provider 适配 | **保留** |
| agent_loop.py (v3) | 内部编排者 | **接线** (Node 调用) |
| service.py | 业务层 | **保持同源** (CLI/API/WebUI) |
| events + audit | 事实源 | **保留** |

**架构决策: 新建 Artifact Contract → 复用现有 delivery.apply_patch → workspace。不建新 Delivery System。**

---

## 1. Domain Objects

### 核心 Identity 判定

| 对象 | Identity (真) | Metadata (非 Identity) |
|------|---------------|------------------------|
| Artifact | artifact_id + version | type / source / project / owner |
| Node | node_id (定义) | 输入/输出契约 (可变) |
| NodeRun | run_id | 执行细节 (不可变记录) |
| ProductionRun | production_run_id | 描述 / 计划 |
| Workspace | project_id + git state | 目录路径 (派生) |
| Commit | git hash | message / author |
| Evidence | evidence_id | 内容 (可追溯) |

---

## 2. Artifact Contract

```
Artifact = 生产闭环中 Node 产出的、可被验证与追溯的对象。
```

字段:
```
artifact_id: uuid (Identity)
version: int (单调递增)
type: prd | design | code_change | test | report | release_bundle
source: node_run_id (谁产出)
owner: 产出 Node (谁负责)
project_id
node_run_id
workspace_delta: 是否改变 workspace (bool)
state: 生命周期状态 (见 §3)
payload: 内容引用 (patch_text / 文件路径 / hash)
evidence_ids: 关联证据
created_at / updated_at
```

---

## 3. Artifact State Machine (最终 Contract)

```
┌────────────┐   create    ┌────────┐   auto      ┌──────────┐   auto    ┌─────────┐
│ GENERATED  │───────────→│ STAGED │───────────→│ REVIEWED │─────────→│ APPROVED│
└────────────┘            └────────┘            └──────────┘          └─────────┘
                                                                          │  approve (Human)
                                                                          ▼
┌────────────┐   validate  ┌───────────┐  apply   ┌────────┐  approve  ┌──────────┐
│  RELEASED  │←───────────│ COMMITTED │←────────│VALIDATED│←─────────│ APPLIED  │
└────────────┘            └───────────┘          └────────┘           └──────────┘
```

### 逐状态定义

| State | Entry Condition | Allowed Transition | Actor | Required Evidence | Side Effect | Failure | Rollback |
|-------|----------------|--------------------|-------|-------------------|-------------|---------|----------|
| GENERATED | Node 产出 payload | →STAGED (自动) | Node | payload hash | 无 | 失败→FAILED(不生成) | 无 |
| STAGED | 写入 artifact store | →REVIEWED (自动) | 系统 | 存储确认 | 持久化 artifact | 存储错误→FAILED | 删除记录 |
| REVIEWED | 自动审查通过 | →APPROVED | 系统 | L1-L3 验证结果 | 无 | 审查 FAIL→REPAIRING | 重新生成 |
| APPROVED | Human 批准 (或策略自动) | →APPLIED | Human/策略 | approval 记录 | 无 | 拒绝→REJECTED | 无 |
| APPLIED | delivery.apply_patch 成功 | →VALIDATED (自动) | 系统(delivery) | apply 输出 | **workspace 真实变更** | apply FAIL→REPAIRING | git reset |
| VALIDATED | build+test 通过 | →COMMITTED | 系统 | L4-L5 结果 | 无 | FAIL→REPAIRING | revert workspace |
| COMMITTED | git commit | →RELEASED | 系统 | commit hash | 版本化 | commit FAIL→RETRY | revert commit |
| RELEASED | 发布/打包 | (终态) | 系统 | release bundle | 交付 | 发布 FAIL→revert | 回滚发布 |

### 判定: 8 态是否合理?

**合理,但两处必须明确:**
1. **STAGED 是轻量中间态** — 只做"写入存储+hash",不做审查(避免过度设计)
2. **REVIEWED 和 APPROVED 可合并为自动审查+人工批准** — 但保留两个状态以区分"机器查过"和"人批准过"(Evidence 不同)

---

## 4. Artifact / Patch / Workspace (最终决策)

**选择 Model B (Patch = Artifact Transformation):**

```
Artifact (code_change, 含 patch_text)
   ↓
Apply 转换 (delivery.apply_patch)
   ↓
Workspace (真实代码)
```

理由:
- Patch 是 Artifact 的"传输形态",不是独立产物 — workspace 状态才是产物
- 与现有 delivery.py 完全对齐 (apply_patch 就是 transformation)
- 避免 "patch 和 code 两个产物" 的双轨混乱

**Workspace 决策: Workspace 是 Artifact 的 Destination,不是 Artifact 的一部分。**
- Artifact = 内容 + 生命周期
- Workspace = 目标投影 (Apply 后才有代码)
- 两者通过 artifact.state=APPLIED + workspace_delta=true 关联

---

## 5. Artifact / Commit

**Commit 是 Repository State + Evidence of Application,不是 ArtifactVersion。**

```
Artifact version = artifact_id#vN (内容版本, 在 artifact store)
Commit = git hash (repository 状态, 在 git)
两者关系: Artifact.state=COMMITTED 时, 绑定 commit hash 作为证据
```

严格区分:
- ArtifactVersion 是**逻辑产物版本** (内容演进)
- Commit 是**物理仓库状态** (代码落点)
- 一个 ArtifactVersion 可能对应多个 Commit (如果 release 后又 hotfix)
- 一个 Commit 绑定一个 ArtifactVersion (通过 evidence)

---

## 6. Node Contract (定义)

```
Node = 生产步骤的定义 ("应该做什么")
```

```
node_id
type: discovery | product | prd | architecture | ux | engineering | qa | release | operation
input_contract: 需要的输入 (目标 / 上游 artifact 引用)
output_contract: 应产出 (artifact type + 成功标准)
policy:
  agent_role: 角色偏好
  executor_preference: 执行器偏好 (可空)
  model_requirement: 能力要求 (可空)
  budget: {max_tokens, max_cost, max_time}
  verification: [L1, L2, ...] 必须跑的验证
  approval_required: bool (Apply/Commit Gate)
  max_retries: int (默认 2)
```

---

## 7. NodeRun Contract (实例)

```
NodeRun = Node 的一次实际执行 ("一次实际做了什么")
```

```
run_id
node_id
production_run_id
state: PENDING→READY→RUNNING→VERIFYING→WAITING_APPROVAL→APPLYING→VALIDATING→COMMITTING→COMPLETED
       | FAILED | REPAIRING | BLOCKED | CANCELLED
input: 实际输入 (引用)
agent: 实际 Agent (角色)
executor: 实际执行器 (native / codex / claude / hermes)
model: 实际模型 (若 native)
artifacts: [artifact_id...]
evidence: [evidence_id...]
verification: {L1: PASS, L2: FAIL, ...}
repair_count: int
budget_used: {tokens, cost, time}
started_at / completed_at
```

**Node vs NodeRun 不可混: Node 是模板(可复用), NodeRun 是事实(不可变记录)。**

---

## 8. ProductionRun Contract

```
ProductionRun = Workflow 的一次执行 (生产 Run)
```

```
production_run_id
workflow_id
project_id
state: RUNNING | COMPLETED | FAILED | CANCELLED
node_runs: [run_id...]
trigger: user | schedule | event
artifacts: 最终产物引用
evidence: 全链路证据
```

### 四类运行最终区分 (冻结)

| 对象 | 是什么 | 持久化 |
|------|--------|--------|
| Conversation Session | 人类↔Factory 交互 (已有) | console_sessions.json |
| ProductionRun | Workflow 执行 (新) | runs.json + events |
| NodeRun | Node 执行实例 (新) | runs.json + events |
| Agent Session | 执行器内部会话 (不建模) | 外部 |

**Invariant: Conversation Session 永远不直接改 Workspace;一切生产变更必须经 NodeRun。**

---

## 9. Verification Contract

```
Verification = 对 Artifact/Workspace 的质量判定 (独立于执行)
```

验证对象 (按 Artifact type 选择):
```
code_change → L1 语法 + L2 单元测试 + L3 业务规则 + L4 build
prd/design → L3 规则检查 (完整性/一致性) + Human review
release_bundle → L5 发布验证
```

结果 (4 态, 非 bool):
```
PASS: 满足全部
FAIL: 明确不满足 (带证据) → Repair
INCONCLUSIVE: 证据不足 → 人工判断
BLOCKED: 外部依赖/红线 → 等解除
```

**Verification 不改变 Artifact,只产生 VerificationResult (Evidence 的一部分)。**

---

## 10. Evidence Contract

```
Evidence = "为什么可以相信这个结果" (可接受性证明)
Event = "系统发生了什么" (事实记录)
```

边界 (基于现有代码):
```
Event: events 表 append-only (已存在) — 记录事实, 不解释
Evidence: evidence bundle — 证明结论可接受 (execution+observation+verification+approval+commit)
```

一个生产结果的 Evidence Bundle:
```
execution: {executor, model, command, duration, cost}
observation: 工具/测试原始输出
artifact: {artifact_id, version, payload hash}
verification: {L1-L5 结果}
approval: {who, when, note} (若需要)
commit: {hash, message}
trace: {run_id, node_run_id, production_run_id}
```

**Evidence 与 Event 关系: Event 是 Evidence 的原料;Evidence 是给人看的结论包。两者都不可变,通过 trace_id 关联。**

---

## 11. Approval Contract

**决策: 单 Approval Gate, 但 approval 对象区分目标。避免 4 种 Approval 过度设计。**

```
Approval = 一个审批实例, 绑定目标 artifact
```

```
approval_id
artifact_id
approval_type: APPLY | COMMIT | RELEASE (批准的目标)
state: PENDING | APPROVED | REJECTED
requested_by: NodeRun
approved_by: user
note: 批注
```

- **何时必须存在**: Artifact.state=APPROVED 前 (APPLY/COMMIT/RELEASE 三个转换都需要)
- **何时可自动**: policy.approval_required=false (仅 demo/低风险;生产默认人工)
- **谁批准**: 项目 owner (登录用户) / 配置的审批人
- **批准的是什么**: 允许该 Artifact 进入下一个转换 (Apply→写 workspace / Commit→版本化 / Release→交付)

**Invariant: 无 APPROVED approval, artifact 不能 APPLIED/COMMITTED/RELEASED。**

---

## 12. Executor Contract (最小, 不过度设计)

基于现有 executor.py (已有 run/verify/record), 冻结最小契约:

```
Executor
├── prepare(ctx) → ok          # 环境/目录准备 (可空)
├── execute(task) → result     # 执行 (subprocess 或 native)
├── collect(result) → artifacts # 提取产物 (patch/text)
├── status(run_id) → state     # 查询 (可空 — 长任务)
├── cancel(run_id) → ok        # 取消 (可空)
└── cleanup(run_id) → ok       # 清理 (可空)
```

**只有 execute + collect 是必选;prepare/status/cancel/cleanup 可选 (有则用, 无则跳过)。不为未来扩展设计 10+ 方法。**

Executor 类型:
```
NativeLLM (llm_gateway 包装)
ExternalCLI (codex/claude/hermes — subprocess, 已有)
WorkflowRunner (旧执行器, 迁移)
```

---

## 13. Model / Executor Relationship (冻结)

```
Role (PM/Eng/QA — 职责)
  ↓ 装配 (不变)
Agent (Role + Policy + 偏好)
  ↓ 调度 (不变)
Executor (执行能力 — NativeLLM/ExternalCLI)
  ↓ 能力解析 (不变)
Model / ModelProfile (能力画像 — 仅 Native 时需要)
```

- **Executor 是执行单元 (含外部 CLI);Model 是 Executor 内部的 LLM 能力源 (仅 Native 路径需要)**
- 外部 CLI executor (codex/claude) 自带模型, Factory 不干预其内部模型
- Capability 选择: Node 声明 requirement → 选择 Executor → (Native 时) 选 Model

---

## 14. Existing Code Integration Points (S1 依据)

```
新 Artifact Contract (state machine + store)
   ├── 读: artifact_contract.py 扩展 (复用 set_artifact/get_artifact_version)
   ├── apply: → session/delivery.py apply_patch (直接调用, 不重写)
   ├── verify: → 现有验证 (executor.auto_verify / 语法检查 / pytest)
   ├── commit: → git (delivery._git 复用)
   ├── event: → events 表 (现有 EventLogger)
   ├── evidence: → audit_events.json + evidence 新字段
   └── 审批: → 现有 ApprovalGate (复用)
```

**S1 不做: 不建新 delivery,不重写 apply,不设计新 event 系统。**

---

## 15. Contract Invariants (最终, 非机械复制)

```
I1:  Artifact 未 APPROVED 不能 APPLIED。
I2:  Applied Artifact 必须携带 Evidence (apply 输出)。
I3:  Artifact 未 VALIDATED 不能 COMMITTED。
I4:  NodeRun 未经过 VERIFYING 不能 COMPLETED。
I5:  ProductionRun 有未完成 NodeRun 不能 COMPLETED。
I6:  Commit 必须对应 Validated 的 Workspace 状态。
I7:  一切生产变更 (Apply/Commit/Release) 必须可审计 (事件+证据)。
I8:  外部 Executor 不能绕过 Artifact Lifecycle (产物必须走 GENERATED→…→COMMITTED)。
I9:  Conversation Session 不能直接改 Workspace (必须经 NodeRun)。
I10: Artifact 不可变 (修改 = 新 version, 不 UPDATE 旧记录)。
I11: NodeRun 是事实记录, 不可变; Node 是可编辑模板。
I12: 无 Approval 记录, 不允许 APPLIED/COMMITTED/RELEASED 转换。
```

---

## 16. Explicit Non-Goals (S1-S4 明确不做)

```
❌ 不建新 Delivery System (复用 delivery.py)
❌ 不设计 4 种 Approval (单 Gate + type 字段)
❌ 不实现多 Agent 实体 (Role+Policy+Executor 装配即够)
❌ 不实现复杂 Learning (先积累数据)
❌ 不深用 MCP (DEFER)
❌ 不重写 v3 agent_loop (只加 Node 接线)
❌ 不引入新依赖/新框架 (纯 Python + 现有栈)
❌ 不为"未来扩展"设计 10+ 方法 (最小契约)
❌ 不把 Conversation Session 与生产 Run 混为一谈
```

---

## 17. GO / NO-GO

### GO ✅

Contract 已稳定,与现有代码对齐,无 Blockers:
- Artifact 8 态状态机合理 (STAGED 轻量, REVIEWED/APPROVED 区分人机)
- Patch = Transformation (Model B), Workspace = Destination — 已定
- Commit = Repository State + Evidence, 非 ArtifactVersion — 已定
- Node/NodeRun/ProductionRun 边界清晰 — 已定
- 复用 delivery.py / artifact_contract.py / ApprovalGate — 已验证存在
- 12 条 Invariants 覆盖所有生产转换

### S1 定义 (不实现, 仅冻结目标)

```
S1 Objective: 实现 Artifact Lifecycle 状态机 + 存储 (无 Node/Executor)
S1 Scope:
  - artifact.py: GENERATED→STAGED→REVIEWED→APPROVED→APPLIED→VALIDATED→COMMITTED→RELEASED
  - 状态转换函数 (每个转换: 前置校验 + 副作用 + 证据绑定)
  - artifact store (扩展 artifact_contract.py: 读 version, 加 state)
  - 12 条 Invariants 的断言检查
  - 不接 Node / 不接 Executor / 不接 WebUI (纯后端)
S1 Acceptance Criteria:
  - 单元测试覆盖全部 8 态转换 + 非法转换拒绝 + 12 Invariants
  - apply_patch 复用验证 (1 个真实临时项目: 生成→审批→apply→validate→commit 全链)
  - 全量现有测试不回归 (614+5721 基线)
S1 Tests:
  - test_artifact_lifecycle.py: 状态机转换矩阵 (合法/非法)
  - test_artifact_invariants.py: 12 Invariants 断言
  - test_artifact_apply_integration.py: delivery.apply_patch 真实应用 (临时 git 仓库)
```

**结论: Contract FROZEN, S1 可以开始。**
