# AI Factory 2.0 — Target Architecture → Gap Map → Migration Strategy → Development Roadmap

> 日期: 2026-08-29 | 依据: 两份审计报告 + 当前 HEAD (024d9cee, v1.1.306) 真实代码复核
> 本阶段: 只建模/规划/迁移设计 — 零业务代码修改
> 核心原则: 每个决策必须回答 "Does this increase the probability of successful software delivery?" — 不能则 DEFER, 炫技则 REJECT, 只增代码量则 REJECT

---

## Executive Architecture Decision

**AI Factory 2.0 = 软件生产流水线的控制平面。核心迁移不是"加功能",而是把现有的、已验证的零件(事件溯源/治理/记忆/外部执行器/patch apply)接到一条真正的生产链路上。**

架构决策(三条硬约束):
1. **Node 是核心生产单元** — 一切生产行为(Node: 想法/PRD/代码/测试/发布)走统一 Node Runtime
2. **Artifact Lifecycle 是主链路** — Generated → Reviewed → Approved → Applied → Validated → Committed → Released;apply 必须成为必经状态
3. **Model/Executor Agnostic** — Agent 不绑 LLM;按能力需求选执行器(内部 LLM 或外部 codex/claude/hermes)

---

## 1. Current Architecture Truth (代码复核修正版)

**修正审计报告的两处判断(代码优先):**

| 报告判断 | 代码复核 | 修正 |
|---------|---------|------|
| "workspace 0 代码" | apply 实现存在 (delivery.py 169行 + workflow_runner.py:757) | 修正: **apply 是"未连接"** — 存在但项目执行路径不触发 |
| "patch 从不应用" | workflow_runner 被 service/API 调用 (活链路) | 修正: 有两条执行路径, 旧路径有 apply 但死, 新路径 (v3) 无 apply |

### 当前真实执行路径 (两条, 互不连通)

```
路径 A (旧, 有 apply 但被 v3 边缘化):
workflow_runner.py:757 → v4-pro 生成代码 → git apply → code artifact
  ↓ 被 service.py / api/workflow_start.py 调用
  ↓ 但: 12 项目停在规划层, 未走到此路径 (workspace 0 代码实证)

路径 B (新, v3 主循环, 无 apply):
WebUI 会话 → agent_loop.py (run_agent_native) → 生成 patch → ⛔ 停在"待批准"
  ↓ 28 工具 / 动态工具面 / 证据链 (强)
  ↓ 但: patch 生成后无 Apply 状态 (E2E 实证 "human review required before apply")
```

### 当前架构 Map (含状态标记)

```
CLI (cli_factory 4896行, PARTIAL-God) → service.py (4911行, PARTIAL-God) → factory-core (事件/验证, REAL)
API (fastapi_adapter, REAL 124路径) → service.py → core
WebUI (React 34.9K, PARTIAL 聊天优先) → API → service
Agent Runtime: agent_loop.py (v3, REAL) + orchestrator.py (v1/v2, DEAD 4133行) + actions.py (DEAD 4121行)
Executor: external_executor (REAL subprocess) + llm_gateway (REAL 3适配器) + workflow_runner (PARTIAL 有apply)
Artifact: artifact_contract.py (346行, PARTIAL 无生命周期) + delivery.py (REAL apply) + patches/* (真实75个)
Workspace: projects/* (规划层) + workspace/projects/* (0代码)
Event: factory.db events 表 (REAL 4831+) + audit_events.json (REAL 双写)
Memory: memory_core + project_memory + Spine (REAL 三层)
```

---

## 2. Target Architecture

```
Human (CLI / WebUI Production Control Tower)
   ↓
Experience Layer (会话=输入入口 + 生产线监控台=主视图)
   ↓
Application Service (service 拆分: production/node/artifact/gateway/console)
   ↓
Production Control Plane (Workflow/Node 编排 + Artifact Lifecycle + 审批 + 证据)
   ↓
Node Runtime (统一闭环: Plan→Execute→Verify→Repair→Apply→Commit)
   ↓
Agent Runtime (Role + Policy + 编排者)
   ↓
Executor Abstraction (统一契约)
   ├── NativeLLM (llm_gateway: deepseek/openai/anthropic/gemini/ollama)
   ├── External CLI (codex/claude/hermes/pi/openclaw — subprocess)
   └── WorkflowRunner (有 apply 的旧执行器, 迁移入 Executor 契约)
   ↓
Tools / MCP / Skills (能力扩展)
   ↓
Workspace / Repository (代码真实落点 — Apply 目标)
   ↓
Artifact Store (生命周期状态机)
   ↓
Verification (L1-L5) + Governance (门/红线) + Event/Evidence (事实源+证明)
```

---

## 3. Domain Model (Node 为核心)

### 核心对象定义

| 对象 | Purpose | Identity | Owner | Lifecycle | Persistence |
|------|---------|----------|-------|-----------|-------------|
| **Node** | 生产闭环单元 (定义) | node_id | Workflow | PENDING→…→COMPLETED/FAILED | nodes.json |
| **NodeRun** | Node 的一次执行 (实例) | run_id | Node | RUNNING→VERIFYING→… | runs.json + events |
| **Artifact** | Node 的可验证产物 | artifact_id | Node | 8 态生命周期 | artifact store |
| **ArtifactVersion** | Artifact 的版本 | artifact_id#vN | Artifact | immutable | 文件+hash |
| **WorkspaceState** | 代码落点状态 | workspace_id | Project | Applied→Validated→Committed | git + manifest |
| **Evidence** | 可接受性证明 | evidence_id | NodeRun | 永久 | evidence.json |
| **Approval** | 人工批准 | approval_id | User | PENDING→APPROVED/REJECTED | approvals.json |
| **Executor** | 执行能力 | executor_id | System | 配置级 | executors.json |
| **ModelProfile** | LLM 能力画像 | model_id | Provider | 配置级 | models.json |
| **Session** | 人机交互上下文 | session_id | User | 会话级 | console_sessions.json |

### 四类"运行"严格区分 (Proposal §8 落地)

```
Conversation Session: 人类↔Factory 交互 (已有, 保留)
Production Run:       Workflow 的一次执行 (新, = WorkflowRun)
Node Execution:       Node 的一次执行 (= NodeRun, 核心生产单元)
Agent Session:        执行器内部会话 (外部 codex/claude 自己的 session, 不建模)
```

**这四个不可混淆: 会话消息≠生产状态;NodeRun 才是生产事实。**

### Node / Agent / Executor / Model 边界

```
Node (编排者视角: 目标/输入/验证/审批) 
  → 选 Agent (角色+策略)
    → 选 Executor (内部 LLM 或外部 CLI)
      → 选 Model (能力匹配)
```

---

## 4. Artifact Lifecycle (第一核心迁移)

### 状态机 (基于代码事实设计)

```
GENERATED (Node 产出 patch/report/PRD)
   ↓
STAGED (写入 artifact store, 带 hash)
   ↓
REVIEWED (自动审查: 语法/契约/红线)
   ↓
APPROVED (人类批准 — 可配自动, 但默认人工)
   ↓
APPLIED (git apply → workspace — ★ 当前断裂点)
   ↓
VALIDATED (build + test + L1-L5)
   ↓
COMMITTED (git commit + evidence 绑定)
   ↓
RELEASED (打包/部署)
```

### 关键定义

```
Patch = Change Set (Artifact 的传输形态, 非最终产物)
Code = Applied 后的 Workspace 状态 (真实落点)
File = Workspace 中的具体变更单元
Workspace = Artifact Store 的代码投影 (真实目录)
Repository = git 托管 (Commit 的载体)
Commit = ArtifactVersion 的版本化+证据绑定
Build/Test Result = Evidence (非 Artifact)
Release = 可分发产物
Evidence = 该 Artifact 可被接受的证明包
```

### 解决 `???` — Patch 到 Workspace 的正式通道

```
AI generated patch
   ↓
delivery.apply_patch() ← 已存在 (git apply + 容错链), 迁移进 Node Runtime
   ↓
workspace (真实目录变更)
   ↓
build (验证可编译)
   ↓
test (验证业务)
   ↓
commit (git commit + run_id 关联)
```

**迁移决策: delivery.py 的 apply_patch 是现成资产, 直接接入 v3 路径的 Approval→Apply, 不需要重写。**

---

## 5. Node Runtime (Universal Node Execution Contract)

### Node State Machine

```
PENDING → READY → RUNNING → VERIFYING → WAITING_APPROVAL → APPLYING → VALIDATING → COMMITTING → COMPLETED
                                        ↘ REPAIRING → RUNNING (循环)
                        ↘ FAILED → (诊断) → REPAIRING 或 BLOCKED (escalate) 或 CANCELLED
```

### Node Execution Contract (每 Node 必须实现/继承)

```
Input:          结构化输入 (目标/参数/上一节点产物引用)
Context:        证据/记忆/项目约定/历史 (分层加载)
Objective:      明确的成功标准 (可验证)
Constraints:    预算 (tokens/cost/time)/红线/工具白名单
Agent Selection: 按 Role 匹配 (PM/Eng/QA...)
Executor Selection: 按能力 (见 §6)
Model Selection: 按 ModelProfile (见 §6)
Plan:           节点内拆解 (可空 — 简单节点直接执行)
Execute:        委派 Executor
Observe:        收集输出/工具结果
Artifact:       产出 (patch/report/PRD)
Verify:         自动验证 (L1-L5, 见 §7)
Repair:         失败→诊断→修复→重试 (预算内, 见 §8)
Approval:       Apply/Commit 前人工门 (可配)
Apply:          写入 workspace (delivery.apply_patch)
Commit:         git commit + evidence
Evidence:       emit Evidence Bundle
Handoff:        产出+状态交接给下一 Node
```

### 判定规则

```
什么时候 Verify?     Artifact 产出后立即 (自动, 不等人)
什么时候 Apply?      Approved 后立即 (自动, 审批通过即执行)
什么时候 Human Approval? Apply/Commit/Release 三 Gate (默认人工, 可配自动)
什么时候自动 Repair?  Verify FAIL 且 budget 未耗尽 (默认 2 次)
什么时候停止?        budget 耗尽 / max_retries 达 / 红线触发
什么时候 Escalate?   Repair 失败 → BLOCKED 等人 (带诊断证据)
```

---

## 6. Agent / Executor / Model 三层模型

### 关系

```
Role (PM/Eng/QA/Release) — 职责声明
  ↓ 装配
Agent (Role + Policy + 偏好 Executor/Model) — 可命名实体
  ↓ 调度
Agent Runtime (内部编排者: agent_loop 改造) — 唯一"大脑"不换
  ↓ 执行
Executor (NativeLLM / CodexCLI / ClaudeCLI / HermesCLI / WorkflowRunner) — 统一契约
  ↓ 能力
Model / ModelProfile (deepseek/anthropic/qwen/ollama...) — 可插拔
```

### Model Capability System

ModelProfile 字段 (llm_gateway 扩展):
```
tool_calling / structured_output / reasoning / context_window
vision / streaming / parallel_tools / cost_per_1k / latency_ms
reliability / instruction_following / coding / planning (0-1 评分)
```

Capability-based Selection:
```
Node "requires": {coding:0.8, context:64000, cost_max:0.05}
  → Capability Resolver (过滤+评分) → 候选 [CodexCLI, ClaudeCLI, NativeLLM(deepseek)]
  → 选择 (成本/可靠性/历史成功率加权) → 执行 → 记录 (task_type, executor, model, success, cost)
  → 回写 Learning (≥50 条后生效)
```

**Model Agnostic 的架构实现 = Executor 契约 + ModelProfile 评分 + 选择器;不是"支持多模型"一句话。**

### Executor Contract (统一)

```
prepare() → 环境/目录/上下文准备
execute() → 执行 (subprocess 或原生)
observe() → 收集输出/工具结果
collect_artifacts() → 提取 patch/产物
collect_evidence() → 执行证据 (命令/输出/耗时)
verify() → 语法/契约快速验证
cleanup() → 清理
```

**现有 external_executor(executor.py subprocess) 已符合大部分契约, 迁移 = 补齐方法名 + 接入 Node Runtime。**

---

## 7. Verification Architecture

```
Node → Artifact → Verification (独立于执行)
  ├── L1 语法/静态 (已有: 语法检查)
  ├── L2 单元/契约 (已有: pytest)
  ├── L3 业务规则/验收 (已有雏形: 验收标准, 需加强)
  ├── L4 生产验证 (新增: build + 可运行性 + smoke)
  └── L5 交付验证 (新增: 发布包/部署健康)
```

Verification Result: **PASS / FAIL / INCONCLUSIVE / BLOCKED**(非 true/false)
- PASS → Approval → Apply
- FAIL → Repair 循环
- INCONCLUSIVE → 需人工判断 (证据不足)
- BLOCKED → 外部依赖/红线

Evidence Bundle (每个生产结果必须携带):
```
execution (executor/model/命令/耗时/成本) + observation (工具输出)
+ artifact (hash) + verification (L1-L5 结果) + approval (人/时间/批注)
+ commit (git hash) + trace (run_id 链路)
```

---

## 8. Repair Architecture

### Repair Contract

```
谁 Diagnose?   内部编排者 (agent_loop 的反思层, 读 FAIL 证据)
谁 Repair?     默认同一 Executor; 可配"换 Executor" (如 Codex 生成→Claude 修复)
是否换 Model?  可配 (失败可能因模型能力不足)
Max Retry:     2 (默认, 可配)
Budget:        与 Node 共享 (tokens/cost/time)
Context:       FAIL 证据 + 原目标 + 历史修复
Evidence:      每次修复记录 (attempt, executor, result)
Escalation:    retries 耗尽 → BLOCKED + 诊断证据给人
```

**编排能力: Repair 用不同 Executor 是 Factory 的差异化能力(如 Codex 实现→Claude 审查→Hermes 诊断→Codex 修复)。设计成可配置策略, 不强制。**

---

## 9. Workflow Model (Production Graph)

### 职责分离 (不重叠)

```
Workflow 管: 节点编排/依赖/并行/分支/Gate/循环
Node 管:     单个闭环 (目标→执行→验证→修复→落地)
Agent 管:    角色行为 (策略/工具/模型偏好)
```

### Production Graph Model

```
节点: Node (带 Run 状态)
边:   dependency (前置产物引用) / gate (Approval) / loop (Repair)
并行: 独立 Feature Nodes 并行 (多 Executor)
分支: Conditional (如: 测试失败 → Repair Node)
失败传播: FAILED → 上游 BLOCKED (带证据)
补偿: Release 失败 → 回滚 commit (git revert)
Resume: 从 FAILED/BLOCKED 的 Checkpoint 继续
```

---

## 10. Event Architecture (边界收敛)

```
Command (意图) → Event (事实) → Projection (状态视图) → Query (读)
Artifact/Evidence/Approval/Commit = 生产对象 (独立存储), 与 Event 通过 run_id 关联
```

**边界: 不"Everything=Event"。**
- Event: 发生了什么 (append-only, 已有)
- Artifact Store: 产出是什么 (文件+hash, 新)
- Evidence: 为什么可信 (证明包, 新)
- Projection: 状态怎么读 (Dashboard/CLI 视图)

---

## 11. Memory Architecture

```
三层保留 (REAL) + 一层新增:
Core Memory (persona/human)      — Agent 身份 (KEEP)
Project Memory (类型化+权威)      — 项目知识 (KEEP)
ProjectSpine (handoff/resume)    — 跨 Node/会话交接 (KEEP)
Node Experience (新增)            — 每 NodeRun 后: (task_type, executor, model, success, cost, repair_count) → 选择器参考
```

**判断: 只加"生产经验"一层(直接服务下一次 Node 选择), 不做复杂"组织记忆"。Memory 必须回答"如何帮助下一次生产", 否则 DEFER。**

---

## 12. CLI / API / WebUI

### 原则
```
CLI = Production Console (生产控制台)
API = 生产对象端点 (与 CLI 同源)
WebUI = Production Control Tower (生产线监控台)
三套共享 Application Service, 不产生第二套业务逻辑
```

### CLI Capability Matrix

| Capability | CLI | API | WebUI | 说明 |
|-----------|-----|-----|-------|------|
| idea | ✅ | ✅ | ✅ | 想法→产品 |
| product | ✅ | ✅ | ✅ | PRD 查看 |
| workflow | ✅ | ✅ | ✅ | 编排查看 |
| node run/status | ✅ | ✅ | ✅ | 核心 |
| artifact | ✅ | ✅ | ✅ | 生命周期 |
| verify | ✅ | ✅ | ✅ | 验证触发 |
| approve | ✅ | ✅ | ✅ | 审批 (Apply 前置) |
| repair | ✅(触发) | ✅ | ✅(看) | 手动触发/自动 |
| commit | ✅ | ✅ | ✅ | 落地 |
| release | ✅ | ✅ | ✅ | 发布 |
| agent/executor/model | ✅ | ✅ | ✅ | 配置 |
| audit | ✅ | ✅ | ✅ | 追溯 |

### WebUI Production Control Tower (核心页面)

```
用户第一眼: Factory Overview — 所有项目 Workflow 进度/阻塞/审批数
生产时:     Node Execution 详情 (正在跑什么/证据/输出)
出错时:     FAILED 详情 + Repair 选项 + 诊断证据
审批时:     Approval Queue (Apply/Commit/Release 三队列)
日常:       Artifact 生命周期看板 + KPI (落地率/失败率/人工干预) + Audit
```

**会话面板降级为输入入口(发想法/查看 Node 输出), 不再是主视图。**

---

## 13. Gap Map (Current → Target)

| Capability | Current | Target | Gap | Type | Effort | Priority |
|-----------|---------|--------|-----|------|--------|----------|
| Node Runtime | 无概念 | 核心单元 | 全新 | MISSING | 大 | P0 |
| Artifact Lifecycle | 无状态机 | 8 态 | 全新 | MISSING | 大 | P0 |
| Apply 接入 v3 | apply 存在但未连接 | 必经状态 | 接线 | BROKEN | 中 | P0 |
| 双执行路径 | A(旧有apply)+B(v3无) | 单路径 | 合并 | MISALIGNED | 中 | P0 |
| 真实 LLM E2E | 0 | ≥5 场景 | 全新 | UNPROVEN | 中 | P0 |
| 14K 死代码 | 存在 | 删除 | 清理 | LEGACY | 小 | P1 |
| service God Object | 4911行 | 拆分 | 重构 | PARTIAL | 大 | P1 |
| Repair Loop | L1 | 契约化 | 全新 | MISSING | 中 | P1 |
| Executor 契约 | external 有 | 统一 | 对齐 | PARTIAL | 中 | P1 |
| Model 选择 | router L4缺 | 能力选择 | 增强 | PARTIAL | 中 | P1 |
| Workflow Graph | 线性 | 图编排 | 增强 | PARTIAL | 大 | P1 |
| WebUI 监控台 | 聊天优先 | 生产塔 | 重构 | MISALIGNED | 大 | P1 |
| CLI 生产命令 | 有雏形 | 对齐 | 重构 | PARTIAL | 中 | P1 |
| Release/Operation | L0 | 基础 | 全新 | MISSING | 大 | P2 |
| 过时测试 | 50 红灯 | 全绿 | 清理 | LEGACY | 小 | P1 |
| MCP | 2 接入 | 深用 | 暂缓 | DEFER | — | P2 |

---

## 14. Dependency Graph & Critical Path

```
Artifact Lifecycle (状态机)
   ↓
Node Runtime (消费 Artifact)
   ↓
Apply 接入 (delivery.apply_patch → Node)
   ↓
Verification (L1-L5 接入 Node)
   ↓
Repair Loop (依赖 Verification FAIL)
   ↓
Commit/Release (依赖 Apply+Verify)
   ↓
WebUI 监控台 (依赖 Node/Artifact 状态)

Executor 契约 → Agent Runtime → Node Runtime → Workflow
Domain Model → Application Service → API → CLI/WebUI
```

**Critical Path: Artifact Lifecycle → Node Runtime → Apply 接入 → Verification → Repair → 监控台**
(M1-M4 里程碑即沿此路径)

---

## 15. Migration Strategy

**选择: Strangler Migration (绞杀者迁移) + Module Replacement 组合。**

不重写,不堆补丁,用"新 Node 骨架逐步绞杀旧路径":

```
Phase 0 (M1): 建 Node 骨架 (domain model + 状态机 + 最小 runtime)
   └── 旧系统照常运行 (并行)
Phase 1 (M2): Node 接入现有执行器 (executor 契约化: 包装 external_executor + workflow_runner)
   └── 旧路径 A/B 开始走 Node (从"项目执行"场景切入)
Phase 2 (M3): Apply + Verify + Repair 进 Node Runtime
   └── v3 会话生成 patch → Node → Apply (闭环第一次真正落地)
Phase 3 (M4): 监控台 WebUI + CLI 对齐
   └── 旧 Dashboard 逐步收敛
Phase 4 (M5): 删死代码 + 旧路径下线
   └── orchestrator/actions 删除 (Strangler 完成)
```

### 特殊处理

```
v1/v2 orchestrator/actions: Strangler 末期删除 (M5), 先确认无隐式引用
v3 agent_loop: 保留为内部编排者 (REFACTOR 加 Node 接线), 不重写
service God Object: 拆分生产/console/gateway (M2-M3 渐进, 不一次)
CLI God Object: 每命令组薄壳→service (随 service 拆分)
legacy conversation: 保留为会话入口, 降级
```

---

## 16. Legacy (14K 死代码) Removal Strategy

```
确认: orchestrator.py/actions.py/conversation.py/discovery.py/product_intelligence.py/replanning.py/decomposer.py
引用检查: retrieval/unified.py + audit_emitter 是类型导入还是运行时依赖 (第一步跑 grep+import 测试)
动态引用: 无 (无 getattr/importlib 动态加载这些模块 — 需验证)
测试覆盖: 删除前跑全量 pytest (当前 614+5721 基线)
迁移: 若 session.py/pipeline.py 被 WebUI 间接用 → 先迁到 service 再删
删除: 分批 (每批 2-3 模块) + 每批全量测试
回归: 删除后全量 + demo E2E 复跑

判定: orchestrator+actions 主体 = Safe Delete (v3 覆盖); session.py/pipeline.py = Needs Migration; 其余 = Safe Delete
```

---

## 17. Real LLM E2E Strategy

### Production-grade LLM E2E

```
分层:
Smoke:    1 条最简 (demo 升级: 真 LLM 生成 + apply + 验证) — 每 CI 跑
Contract: Executor 契约测试 (mock 外部 CLI, 真 LLM 内部)
E2E:      5 个生产场景 (见 §18) — 每天跑 (真 LLM + 真 apply)
Regression: 删除死代码后全量复跑
Canary:   新 Executor/Model 上线前, 用固定场景验证

治理:
真实 API Cost: 预算控制 (每 E2E 限制 tokens)
Secrets: 读 ~/.hermes/.env (已有), 测试数据目录隔离 (demo workspace)
Rate Limit: 重试+退避
Flakiness: 结果重试 2 次; 记录 flaky 率
Record/Replay: 失败场景记录输入, 可离线重放 (debug_cases.json 已有雏形)
```

**答案: 证明有效 = 5 个生产场景 + 真实 LLM + 真实 apply + 真实验证, 每天跑, 结果入 Evidence。**

---

## 18. Factory Production Acceptance Tests (5 场景)

| # | 场景 | Input | Expected Artifact | Workspace Change | Verification | Evidence | Commit |
|---|------|-------|-------------------|------------------|--------------|----------|--------|
| 1 | 新项目 | "做一个待办清单 CLI" | PRD+TaskTree+Code | main.py 等真实文件 | pytest PASS | bundle 完整 | 有 |
| 2 | 新 Feature | "给现有项目加导出功能" | Code+Test | 新增 export.py+test | pytest PASS | bundle | 有 |
| 3 | Bug Fix | "修复登录崩溃" | Code+Test | 修复文件+回归测试 | pytest PASS | bundle | 有 |
| 4 | Refactor | "重构为分层结构" | Code | 文件重组 | 原测试全 PASS | bundle | 有 |
| 5 | Failed+Repair | "实现会失败的排序" | 初始 FAIL→Repair→Code | 修复后文件 | 首 FAIL 证据+终 PASS | bundle 含修复链 | 有 |

每个场景断言: workspace 有代码 / git commit 存在 / evidence 完整 / approval 记录。

---

## 19. KPI

| KPI | Baseline | 3-month | 6-month |
|-----|----------|---------|---------|
| Idea→Running Software Success Rate | 0% (未闭环) | 60% | 80% |
| Code Landing Rate (生成→落地) | 0% (workspace 0) | 70% | 90% |
| Artifact Acceptance Rate | — | 75% | 85% |
| Verification Pass Rate | — | 85% | 90% |
| Repair Success Rate | L1 | 50% | 70% |
| Human Intervention Rate | 100% (手动) | 30% | 15% |
| Mean Production Time (想法→代码) | — | 2h | 45min |
| Cost / Successful Delivery | — | $1 | $0.5 |
| Failure Recovery Rate | — | 60% | 80% |

---

## 20. 3-Month Milestones

| M | Goal | Exit Criteria | Dependencies | Deliverables |
|---|------|---------------|--------------|--------------|
| M1 | Production Core | Node domain+状态机+最小 runtime 跑通 1 个 Node | 无 | node.py, artifact.py, lifecycle |
| M2 | Real Execution | Node 接 executor, 1 个真实项目走到 Applied | M1 | executor 契约, apply 接入 |
| M3 | Verify & Repair | L1-L5 接入, Repair 循环生效 | M2 | verification.py, repair.py |
| M4 | Control Tower | WebUI 生产线监控台 + CLI 对齐 | M2 | 监控台页面, CLI 命令 |
| M5 | Real Factory Pilot | 5 个 Acceptance Test 全过 + 删死代码 | M3+M4 | E2E 套件, 死代码清理 |

---

## 21. Recommended Sprint Sequence (拆 Sprint 前最后一层)

```
S1 (M1a): Artifact Lifecycle 状态机 + 存储 (无 Node)
S2 (M1b): Node domain + NodeRun + 最小 Runtime (Plan→Execute→Artifact)
S3 (M2a): Executor 契约 (包装 external_executor + workflow_runner)
S4 (M2b): Apply 接入 v3 路径 (Approval→Apply→Validate→Commit) ← 第一个真实闭环
S5 (M3a): Verification L1-L5 接入 Node
S6 (M3b): Repair Loop (预算内自动修复)
S7 (M4a): 真实 LLM E2E 套件 (5 场景) — 从 S4 开始每天跑
S8 (M4b): WebUI 监控台 v1 (Workflow 进度 + Node 详情 + 审批队列)
S9 (M5a): CLI 生产命令对齐
S10 (M5b): 删死代码 (分批) + 全量回归
S11 (M5c): KPI 面板 + Release 初版
```

每 Sprint 约束: 必须有 Production Evidence (真实运行), 必须有 Rollback (git revert/checkpoint)。

---

## 22. Risks

| Risk | Mitigation |
|------|-----------|
| Node 过度设计 | 最小闭环先行 (S1-S4 只做 1 条路径), 再抽象 |
| Apply 破坏现有项目 | 先 demo workspace, 每 Apply 前 git snapshot (execution_replay 已有) |
| 真实 LLM 测试成本 | 预算控制 + 记录/replay 复用 |
| 死代码删除引入回归 | 分批 + 每批全量测试 + demo E2E |
| WebUI 重构过大 | 监控台 v1 只读 + 保留旧页面并行 |
| 并发 git 污染 | 每生产 Run 独立 worktree/workspace |

---

## 23. Final Decision

### 最终必须回答的 10 个问题

1. **核心 Domain Object**: Node(NodeRun) + Artifact(带生命周期)
2. **最小生产闭环**: Node → Execute → Artifact → Verify → Approve → Apply → Commit
3. **边界**: Node=编排单元; Agent=角色+策略; Executor=执行能力; Model=能力源
4. **边界**: Artifact=产物(8态); Workspace=落点; Commit=版本化+证据绑定
5. **边界**: Verification=质量判定(L1-L5); Evidence=可接受性证明; Approval=人工门
6. **Claude/Codex/Hermes/Pi/OpenClaw 位置**: Executor Abstraction 下层(可插拔执行能力, 统一契约)
7. **永久删除**: orchestrator/actions/conversation/discovery/product_intelligence/replanning/decomposer (14K)
8. **必须重构**: service God Object / cli God Object / agent_loop(加 Node 接线) / router(L4+能力选择)
9. **Critical Path**: Artifact Lifecycle → Node Runtime → Apply 接入 → Verification → Repair → 监控台
10. **宣布成为 Software Factory 的条件**: 5 个 Acceptance Test 全过 + Code Landing Rate ≥70% + Human Intervention ≤30% + 真实 LLM E2E 每天绿

---

## 最终交付摘要

```
Report Path: docs/audit/ai-factory-2-target-architecture-and-migration.md
Current → Target: 双路径(A有apply死/B无apply活) → 单路径(Node+Apply闭环)
Critical Path: Artifact Lifecycle → Node Runtime → Apply → Verify → Repair → 监控台
Top 10 Migration Actions:
  1. Artifact Lifecycle 状态机 (S1)
  2. Node domain + NodeRun (S2)
  3. Executor 契约 (S3)
  4. Apply 接入 v3 (S4) — 第一个真实闭环
  5. Verification L1-L5 (S5)
  6. Repair Loop (S6)
  7. 真实 LLM E2E 5 场景 (S7)
  8. WebUI 监控台 (S8)
  9. CLI 对齐 (S9)
  10. 删 14K 死代码 (S10)
3-Month Roadmap: M1 Production Core → M2 Real Execution → M3 Verify&Repair → M4 Control Tower → M5 Pilot
```

### 如果今天重新开始开发, 第一段代码写在哪里?

**写在 Artifact Lifecycle 状态机 (artifact.py: GENERATED→…→RELEASED + artifact store)。**

原因:
1. 它是所有断裂的根因(patch 无生命周期 → 不落地)
2. 它定义"生产对象",Node/Executor/Verification 全部围绕它展开
3. 它不依赖任何 LLM/执行器,可以立刻实现 + 立刻测试(纯状态机,零 mock 质疑)
4. 它一旦成立,Apply/Commit/Release 就有明确的落点——后续每个 Sprint 都在为"让 artifact 走到 RELEASED"服务

**这与"工厂先有质检和流水线,再招工人"同理: 先定义产物如何流动,再接入 AI 产能。**

---

*本阶段零业务代码修改。基于 2026-08-29 真实代码复核(修正: apply 存在但未连接 / workflow_runner 是活链路)。*
