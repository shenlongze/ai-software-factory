# AI Factory 2.0 — Rebuild / Refocus Proposal

> 日期: 2026-08-29 | 依据: docs/audit/ai-factory-zero-to-current-audit.md (62/100, L3, PARTIAL)
> 本阶段: 只做 Reason/Compare/Model/Decide/Document — 零业务代码修改, 零 Sprint

---

## 1. Executive Decision

**AI Factory 2.0 的方向: 停止做"AI 员工管理系统",回到"软件生产流水线的控制平面"。**

一句话决策:
- **不重建**事件溯源、治理、记忆、外部执行器(四大强项)
- **必须重建**Artifact Lifecycle(补丁从不落地 → 代码真正进仓库)
- **必须砍掉**14K 死代码 + 6 个自认骨架的命令的虚假繁荣
- **必须聚焦**生产闭环而非无限增强聊天体验

---

## 2. Current Reality (已确认事实)

```
能力真实: CLI 40+ 命令 / API 124 路径 / WebUI bundle / event-sourcing 4831+ 事件
能力断裂: workspace 代码 = 0 (patch 生成但从不 apply)
结构债务: 14K 死代码 + God Objects (service 4911 + cli 4896)
测试真相: 614+5721 passed, 但真实 LLM 测试 = 0
战略漂移: Software Factory → AI Workforce Management
```

---

## 3. Root Cause Analysis

**"patch 不落地"不是 bug,是系统性根因链:**

```
Artifact Model 不完整 (patch 是产物, 但无生命周期)
    ↓
Execution Model 不完整 (执行停在"生成", 无"应用"状态)
    ↓
Node Model 不完整 (Node 不是闭环, 是 Prompt→LLM→输出)
    ↓
Verification 不完整 (只验证语法, 不验证业务)
    ↓
Delivery 不完整 (无 Build/Release/Operation)
```

**第二根因: 产品重心漂移。**
v1.1.200+ 会话系统爆发(AgentLoop v1→v2→v3)时,"生产执行"被"会话体验"挤出主航道。12 项目中 8 个停在规划层、0 任务 0 产物,是漂移的实证。

**第三根因: 无闭环反馈。**
Repair 是 L1,Learning 是事件记录不是闭环——工厂"生产出错"后没有自动修复→再验证的机制,所以没人敢让代码真正落地。

---

## 4. Strategic Repositioning

从:
```
AI Workforce OS — 管理 AI 员工 (谁在干活, 干得怎么样)
```
到:
```
Software Production OS — 保证软件真的被生产出来 (想法 → 可运行代码, 全流程可验证)
```

**判断: 原始愿景(Software Factory)是对的,漂移是执行层走偏,不是愿景错。**
"AI 员工"是手段,"产出软件"是目的。2.0 把目的放回第一位,员工/执行器只是可插拔的产能。

---

## 5. Product Definition

**AI Factory 2.0 是什么:**

> 一个软件生产流水线的控制平面(Control Plane):
> 编排多个 AI 执行器(Claude/Codex/Hermes/DeepSeek...),把"想法"分解为可验证的生产节点,每个节点产出带证据的产物,经审批后真正落进仓库,最终交付可运行软件。

**AI Factory 2.0 不是什么:**
- 不是 Chat App(会话只是交互入口,不是产品本体)
- 不是 AI IDE(不做编辑器,不抢 Claude Code/Codex 的编辑体验)
- 不是 Claude Code clone / Codex clone(它们是被编排的"工人",不是竞争对手)
- 不是 Agent Marketplace / Workflow SaaS(不卖模板,卖的是"生产保证")
- 不是 Multi-Agent Framework(多 Agent 是手段,高质量交付是目的)

**不可替代价值(Moat):**
> 单一 AI 工具(Claude Code/Codex)能"写代码";AI Factory 能"保证代码被写出来、被验证、被批准、被提交、可审计"。**生产保证(Production Assurance)是 AI Factory 独有的价值。**

---

## 6. Product Boundary

AI Factory 2.0 管什么、不管什么:

| 管 (Factory 职责) | 不管 (执行器职责) |
|---|---|
| 想法 → 产品定义 | 具体的代码编辑 (Codex/Claude 做) |
| 生产节点编排 | 逐行写代码 |
| 执行器选择/调度 | IDE 体验 |
| 验证策略 | 语法/单测细节 |
| 审批门 | 聊天体验 |
| 证据/审计 | 模型训练 |
| 产物/交付 | — |
| 成本/质量度量 | — |

---

## 7. Core Domain Model

| 对象 | 是什么 | 谁拥有 | 生命周期 | 关系 |
|------|--------|--------|---------|------|
| Organization | 生产实体 (一人公司/团队) | 用户 | 长期 | 拥有 Workspace |
| Workspace | 代码/产物工作区 | Organization | 项目级 | 容纳 Repository |
| Project | 一个软件交付单元 | Workspace | 想法→发布 | 含 Product/Workflow |
| Product | 产品的业务定义 | Project | 想法→迭代 | 产出 PRD |
| Workflow | 生产流程定义 | Project | 项目级 | 编排 Nodes |
| **Node** | **核心生产单元 (闭环)** | Workflow | 节点级 | 见 §8 |
| Task | Node 的拆解执行单元 | Node | 执行级 | 由 Executor 消费 |
| Agent | 角色+策略的装配体 | 系统 | 配置级 | 绑定 Executor/Model |
| Role | 职责定义 (PM/Eng/QA) | 系统 | 配置级 | 约束 Agent 行为 |
| Model | LLM 能力单元 | Provider | 配置级 | 被 Agent/Executor 用 |
| Executor | 执行能力 (本机/外部) | 系统 | 配置级 | 被 Node 调度 |
| Tool/Skill | 能力扩展 | 系统 | 配置级 | 被 Agent 用 |
| Context | Node 输入 (目标+证据+历史) | Node | 节点级 | 注入 Agent |
| **Artifact** | **可验证产物 (见 §11)** | Node | 生成→交付 | 核心生产对象 |
| Evidence | 产物可信依据 | Node | 永久 | 绑定 Artifact |
| Verification | 验证结果 | Node | 节点级 | 决定 PASS/FAIL |
| Approval | 人工批准 | 用户 | 审批级 | Gate 节点 |
| Event | 事实记录 | 系统 | append-only | 全链路 |
| Session | 人机交互上下文 | 用户 | 会话级 | 不混入生产 Run |

---

## 8. Node Model

**YES — Node 是 AI Factory 2.0 的核心生产单元。**

标准 Node Runtime:

```
Node Start
 ├── Load Context (目标/证据/历史/策略)
 ├── Understand (意图 + 输入校验)
 ├── Plan (拆解: 用什么 Agent/Executor/Model/工具)
 ├── Select (能力匹配: 见 §10 Model/Executor 选择)
 ├── Execute (委派 Executor 或内部 Agent)
 ├── Observe (收集输出 + 工具结果)
 ├── Generate Artifact (PRD/代码/报告/测试)
 ├── Verify (自动验证: 语法/测试/契约/业务规则)
 │    ├── PASS → 进 Approval Gate → Commit → Handoff
 │    └── FAIL → Diagnose → Repair (预算内) → Retry → Verify
 ├── Escalate (超预算/超时 → 人工)
 └── Emit Evidence Bundle
```

Node 配置:
```
Retry Policy: max_retries, backoff
Budget: max_tokens / max_cost / max_time
Timeout: 秒
Failure State: FAILED / ESCALATED (可恢复)
Checkpoint: 每步可恢复
Resume: FAILED → 从 Checkpoint 继续
Human Escalation: 规则可配置
Evidence: 每 Node 必须 emit (见 §12)
```

**Node 与 Task 区别: Node 是"生产闭环单元"(自带验证/修复/证据),Task 是"执行清单"(由 Executor 消费)。Node 包含 Task,不互斥。**

---

## 9. Agent Model

**明确选择: AI Factory 不自己实现超级 Agent。**

```
AI Factory = Agent Orchestrator / Production OS
Claude Code / Codex / Hermes / Pi / OpenClaw = 可插拔执行能力 (Executor)
DeepSeek / Qwen / Anthropic = 可插拔模型 (Provider)
```

理由:
- 超级 Agent 是 Claude/Codex 已经做得很好的领域,重复造轮子 = 必输
- AI Factory 的差异化在"编排+验证+证据+治理",不在"单个 Agent 多聪明"
- 当前 external_executor(subprocess 调 codex/claude/hermes)已验证可行,应强化而非替换

**Agent 定义收敛为: Role + Policy + Executor/Model 绑定的装配体。**
内部会话 loop 保留,但定位是"编排者/调度者",不是"超级编码者"。

---

## 10. Model / Executor Model

**目标: Agent/Node 不绑定单一 LLM,按能力需求选执行器。**

```
Node (Capability Requirement)
 ├── Coding 任务 → Codex/Claude (代码执行器)
 ├── 简单生成任务 → DeepSeek/Qwen (低成本模型)
 ├── 规划/分析 → 当前会话模型
 ├── 本地敏感 → Hermes/本机
 └── 验证/审查 → 独立模型/审查器
```

Model Profile 字段:
```
tool_calling: bool
structured_output: bool
reasoning: bool (thinking/chain-of-thought)
context_window: int
vision: bool
streaming: bool
parallel_tool_calls: bool
cost_per_1k_in/out
latency_ms
reliability (失败率)
instruction_following: 0-1
coding_ability: 0-1
planning_ability: 0-1
```

选择策略 (Node 级声明):
```
"requires": {"coding": 0.8, "context_window": 64000, "cost_max": 0.05}
→ 从 Executor/Model 注册表过滤 + 评分 → 选中 → 执行 → 记录实际表现 → 反馈到 Learning
```

**llm_gateway(3 类适配器)保留并扩展为"Executor Adapter": 不只适配 Provider,还适配外部 CLI(codex/claude/hermes 已有 subprocess 适配)。**

---

## 11. Artifact Model (重建核心)

**当前断裂根因: Artifact 无生命周期。**

Artifact Lifecycle (2.0 必须实现):
```
Generated (Node 产出)
 ├── Reviewed (自动+人工审查)
 ├── Approved (审批 Gate)
 ├── Applied (真正写入 Workspace — 当前缺失!)
 ├── Validated (应用后验证: build/test)
 ├── Committed (git commit + evidence 绑定)
 └── Released (打包/部署)
```

明确:
- **Patch 是 Artifact 的一种形态(Change Set),不是最终产物**
- **Code 是 Artifact (Applied 后的 Workspace 状态)**
- **Workspace 是 Artifact Store(真实代码落点)**
- **Commit 是 Artifact 的版本化**
- **Verification Result 属于 Evidence,不是 Artifact**

**P0 实现: Apply 状态 — patch 审批通过后必须真正写入 workspace,然后 build/test/commit。没有 Apply 就没有工厂。**

---

## 12. Evidence Model

**AI Factory 2.0 的核心竞争力 = 证明 AI 做了什么,为什么可接受。**

最终生产结果携带的 Evidence Bundle:
```
Execution Record: 谁(executor)什么(model)何时, 输入/输出
Observation: 工具结果/测试输出 (原始)
Artifact 引用: patch/代码/产物 (hash)
Verification: 验证命令+结果 (PASS/FAIL)
Approval: 谁批准, 何时, 批注
Commit: git hash + diff 摘要
Cost: tokens/费用
Trace: 关联的 Node/Workflow/Project
```

**Evidence 与 Event 关系: Event 是事实记录(append-only),Evidence 是"可接受性证明"(可验证的结论)。Event 是 Evidence 的原料,Evidence 是给人类看的结论包。**

---

## 13. Verification Model

分层验证(现有 L1/L2/L3 保留并扩展):
```
L1 语法/静态: 编译/语法/lint (已有)
L2 单元/契约: pytest/契约测试 (已有)
L3 业务规则: 验收标准/业务断言 (需加强 — 当前只到语法)
L4 生产验证: build + 可运行性 + smoke test (新增)
L5 交付验证: 发布包/部署健康 (新增)
```

**验证结果必须: ①决定 Node PASS/FAIL(驱动 Repair);②进 Evidence Bundle;③可追溯回触发它的 Artifact。**

---

## 14. Production Loop (Target Production Graph)

```
                 ┌──────────────────────────────────────┐
                 │         Product Workflow             │
 Idea → Discovery → Product → PRD → Architecture → UX   │
                 │         (每步是 Node, 产 Artifact)      │
                 └──────────────┬───────────────────────┘
                                ↓
                 ┌──────────────────────────────────────┐
                 │        Engineering Workflow          │
                 │  Task Tree (分解)                      │
                 │   ├── Node: Design → Code → Test      │
                 │   ├── Node: Build → Verify → Repair    │
                 │   └── Node: Integration → E2E          │
                 └──────────────┬───────────────────────┘
                                ↓
                 ┌──────────────────────────────────────┐
                 │        Delivery Workflow              │
                 │  Approval → Apply → Commit → Release   │
                 │  → Operation (监控/反馈)                │
                 └──────────────────────────────────────┘
```

关键判断:
- **Node 是每个方框;Workflow 是编排(可并行/循环);Gate 是 Approval**
- 并行: 独立 Feature 的 Engineering Nodes 可并行(多 Executor)
- 循环: Repair 循环(Verify FAIL → Diagnose → Repair → Retry)
- Human Approval: Apply/Commit/Release 三个 Gate 必设(可配自动)

---

## 15. Event Architecture

**保留 Event Sourcing 为事实源,但收敛边界:**

```
Command (用户/系统意图) → Event (事实记录) → Projection (状态视图) → Query (读取)
Artifact/Evidence/Approval/Commit 是"生产对象",有独立存储 + 与 Event 关联
```

避免 "Everything → Event" 过度复杂:
- 生产对象(Artifact/Evidence)不强行只存 Event 投影——它们有真实文件/DB 状态
- Event 记录"发生了什么",Artifact 存储"产出是什么",Evidence 证明"为什么可信"
- 三者通过 trace_id/exec_id 关联,不互相替代

---

## 16. CLI Strategy

**CLI 的产品职责: 生产控制台(Production Console),不是管理工具,不是调试器。**

```
factory idea '我想做X'         → 想法→产品定义 (Node)
factory product show           → 产品/PRD 状态
factory workflow run <id>      → 跑生产流程
factory node run <node>        → 跑单个节点
factory node status <node>     → 节点状态/证据
factory exec <task>            → 委派执行
factory verify <artifact>      → 验证产物
factory approve <id>           → 审批 (Apply 前置)
factory artifact list          → 产物清单+生命周期状态
factory project status         → 项目健康
factory agent list             → 执行器/Agent 状态
factory model select           → 模型/执行器选择
factory audit trace <id>       → 全链路追溯
```

**原则: CLI 与 API 必须共享同一 service 层(当前已成立,继续保持;新能力只在 service 层实现一次)。**

---

## 17. API Strategy

- 保持"CLI/API 同源"原则(已成立,强项)
- API 按"生产对象"分组: products/workflows/nodes/artifacts/evidence/approvals/executors/models/audit
- 新增: Apply/Commit/Release 端点(当前缺失)
- openapi 契约继续自动生成(124 路径已真实)

---

## 18. WebUI Strategy

**WebUI 从"会话聊天+仪表盘"转向"生产线监控台"。**

用户每天最需要看到:
```
1. 项目流水线总览 (Workflow 进度/阻塞点)  ← 第一屏
2. Node 执行详情 (正在跑什么/卡在哪/证据)  ← 核心
3. 审批队列 (待批准: Apply/Commit/Release)  ← 行动点
4. Artifact 状态 (生成→审批→应用→提交→发布)
5. 生产质量 (KPI: 落地率/失败率/人工干预率)
6. 审计追溯 (谁做了什么/证据)
```

会话面板保留但降级为"输入入口"(发想法/查看 Node 输出),不再是产品主体。

---

## 19. Multi-Agent Strategy

**选择方案 C: Workflow Node → Role → Agent → Executor**

```
方案 A (单 Agent):     简单任务够用, 但无法并行/无法专业分工
方案 B (Supervisor):   增加协调复杂度, 收益有限 (当前 14K 死代码就是 B 的失败尝试)
方案 C (Node+Role+Executor): 每个 Node 按需选执行器, 天然并行, 复杂度和收益平衡
```

理由:
- 多 Agent 不是目标,高质量生产才是
- 方案 C 复用现有 external_executor(已验证),不加新抽象
- 并行 = 多 Node 并行(每个 Node 自己的 Executor),不需要 Agent 间通信协议
- 何时不需要: 单一简单任务(单 Node 单 Executor 即可)

---

## 20. Memory Strategy

**保留三层记忆(已验证),定位明确:**

```
Core Memory (persona/human)      → Agent 身份与用户画像 (已有, KEEP)
Project Memory (类型化+权威)       → 项目知识/决策/错误→解法 (已有, KEEP)
ProjectSpine (handoff/resume)    → 跨 Node/会话交接 (已有, KEEP)
```

**新增: Node 级记忆 — 每个 Node 执行后的"经验"回写 Project Memory(什么策略成功/失败),供后续 Node 选择时参考。**

---

## 21. Learning Strategy

**不要做复杂 self-improving 系统。先做"可观察的反馈闭环":**

AI Factory 2.0 真正需要学习(按优先级):
```
1. Model/Executor Selection (哪个执行器对什么任务成功率最高)  ← 最有价值
2. Failure Patterns (什么任务/什么输入容易失败 → 提前预防)
3. Cost Optimization (同样质量, 更低成本路径)
4. Repair Strategy (什么修复最有效)
```

实现: 每个 Node 完成后记录 (task_type, executor, model, success, cost, latency, repair_count) → 聚合 → 选择器加权。**先积累数据(≥50 条真实执行),再谈自动选择;证据不足不提前实现。**

---

## 22. Governance Strategy

**保留并强化(当前强项):**
```
权限门 (PreToolUse + governance_rules.json)  — KEEP
批准门 (APR, Apply/Commit/Release Gate)       — 扩展为三 Gate
审计链 (audit_events + events 双写)           — KEEP
红线配置                                      — KEEP
```

**新增: 生产级治理 — Approval 是 Apply 的硬前置(当前 patch 停在这,应变成"批准后自动 Apply")。**

---

## 23. Target Architecture

```
Human (CLI / WebUI)
   ↓
Experience Layer (会话输入 + 生产线监控台)
   ↓
Production Control Plane (service: Workflow/Node/Artifact/Approval/Evidence)
   ↓
Workflow / Node Engine (Node Runtime: Plan→Execute→Verify→Repair→Emit)
   ↓
Agent Runtime (角色+策略装配, 内部编排者)
   ↓
Executor Abstraction (llm_gateway + external_executor 统一)
   ├── Provider 适配 (deepseek/openai/anthropic/gemini/ollama)
   └── 外部 CLI 适配 (codex/claude/hermes/pi/openclaw)
   ↓
Tools / MCP / Skills
   ↓
Workspace / Repository (代码真实落点 — Apply 目标)
   ↓
Artifact Store (生成→审批→应用→验证→提交→发布)
   ↓
Verification (L1-L5) + Governance (门/红线)
   ↓
Event / Evidence (事实源 + 可接受性证明)
```

---

## 24. Keep / Delete / Merge / Refactor / Rebuild / Defer

| Module | Decision | Why | Target Role |
|--------|----------|-----|-------------|
| factory-core (events/verify) | **KEEP** | 强项, 事件溯源真实 | 事实源基础 |
| service.py (4911行) | **REFACTOR** | God Object, 但同源价值大 | 拆: production/console/gateway services |
| cli_factory.py (4896行) | **REFACTOR** | God Object, 命令真实 | 拆: 每命令组薄壳→service |
| agent_loop.py (1823行) | **REFACTOR** | v3 主循环真实 | 编排者(不写代码) |
| orchestrator.py (4133) | **DELETE** | 死代码, v3 已覆盖 | 无 |
| actions.py (4121) | **DELETE** | 死代码, v3 已覆盖 | 无 |
| conversation/discovery/product_intelligence/replanning/decomposer | **DELETE** | 死代码 (~7K) | 无 |
| memory_core / project_memory / Spine | **KEEP** | 真实可用 | 三层记忆 |
| external_executor | **KEEP+扩展** | 真实 subprocess 委派 | Executor Abstraction 核心 |
| llm_gateway | **KEEP+扩展** | 3 类适配器真实 | +外部 CLI 适配统一 |
| workflow_runner (1181) | **REFACTOR** | 真实但需接 Node 模型 | Workflow Engine |
| task (tasks.json) | **MERGE** | 与 Node 概念重叠 | 并入 Node 执行单元 |
| agent (agents.json) | **REFACTOR** | 元数据真实, 无实体 | Agent=Role+Policy+Executor 绑定 |
| skills | **KEEP** | 147+ 真实 | 能力扩展 |
| MCP | **DEFER** | 仅 2 接入, 价值未证 | 后置 |
| router (llm_router) | **REFACTOR** | L4 缺失, 模型名不一致 | 并入 Model/Executor 选择 |
| WebUI | **REFOCUS** | 从聊天转向生产线监控台 | Experience Layer |
| API | **KEEP** | 同源真实 | 生产对象端点 |
| events | **KEEP** | 强项 | 事实源 |
| audit/governance | **KEEP** | 强项 | 证据+门 |
| **Artifact Lifecycle (Apply)** | **REBUILD** | 当前断裂根因 | 核心生产闭环 |
| **Repair/Learning** | **REBUILD** | L1 缺失 | 闭环反馈 |

---

## 25. 14K 死代码特别审查

```
为什么出现: AgentLoop v1(意图硬路由)/v2(计划审批) 被 v3(agentic) 推翻
什么时候被替换: v1.1.207 (v2) → v1.1.216 (v3) 推翻意图门
v3 是否覆盖: 是 — 工具面/意图/执行全在 agent_loop
隐式动态引用: 需验证 (session.py/pipeline.py 仍引用 orchestrator, 但那些引用者本身未被主链路用)
删除风险: 中 — 先确认 retrieval/unified.py 与 audit_emitter 的引用是类型导入还是运行时依赖
判定: 14K 中 orchestrator+actions 主体 = Safe Delete (先跑引用检查); session.py/pipeline.py = Needs Migration (若被 WebUI 间接用); 全部删除前跑一次全量测试
```

---

## 26. Competitive Position

**如果用户已经有 Claude Code/Codex/Hermes,为什么还需要 AI Factory?**

```
Claude Code/Codex = 单机工人: 打开目录, 写代码, 提交 (每次一个任务)
AI Factory       = 工厂控制平面: 把"想法→发布"分解为节点, 调度多个工人,
                   每个产物带证据, 经审批真正落地, 全程可审计

类比: Claude Code 是电焊工, AI Factory 是造船厂的管理系统+质检+流水线。
    造船厂不自己焊每一块钢板, 但它保证船被造出来、质量可查。
```

**Moat(护城河) = Production Assurance(生产保证):**
- 多执行器编排(不是单工具)
- 证据链(可证明"为什么可信")
- 治理门(可配置红线+审批)
- 生产闭环(代码真正落地+发布)
- 事件溯源(全历史可审计)

这五个能力,单靠 Claude Code/Codex 无法获得;这五个能力 AI Factory 已有 4 个强项,只差"生产闭环"补齐。

---

## 27. Anti-Patterns To Stop

1. **停止无限增强聊天**(思考链/证据链已够,别再给会话加功能)
2. **停止为 Multi-Agent 而 Multi-Agent**(20+ 外部角色注册表,无系统性接入 = 虚假繁荣)
3. **停止"生成但不落地"**(一切 Node 输出必须有 Apply 路径)
4. **停止技术炫技**(TopicLedger 分词/动态工具面已够,别再加深)
5. **停止用"测试数量"证明**(38% mock + 0 真实 LLM 测试 = 无法自证)
6. **停止兼容旧架构**(v3 已定,别再把 v1/v2 死代码当"历史资产"留着)
7. **停止并发会话污染 git**(工作区共享导致的 commit 归属混乱)

---

## 28. 反共识判断

```
过去哪些设计是正确的?  event-sourcing / governance / memory 三层 / external executor / CLI-API 同源
过去哪些设计虽先进但不应继续?  会话聊天无限增强 / 动态工具面继续深挖 / TopicLedger 复杂化
过去哪些是技术炫技?  为 Multi-Agent 而注册 20+ 外部角色 / 为事件而事件(读操作也发事件已过度)
过去哪些该砍?  14K 死代码 / 6 个自认骨架命令 / 双轨同步-流式分叉
过去哪些投入过多?  会话体验(思考链/证据链/审计 UI) — 都是外围, 不是生产核心
过去哪些投入不足?  Apply 闭环 / 真实 LLM E2E / Repair / Release — 生产核心全缺
如果今天重新开始, 哪些不会再做?  自研 AgentLoop v1/v2 的意图门硬路由; 20+ 外部角色注册表; 前端会话面板的大幅增强
如果只有 3 个月:  ① 补 Apply 闭环 (patch→workspace→commit)  ② 真实 LLM E2E 测试
                ③ 删 14K 死代码  ④ Repair 循环  ⑤ 生产线监控台 WebUI
```

---

## 29. 3-Month Direction

**Month 1 (闭环):** Apply 流水线(生成→审批→应用→验证→提交)+ 真实 LLM E2E 测试 + 删死代码
**Month 2 (反馈):** Repair 循环 + 执行器选择数据收集(50+ 真实执行)+ Node 级记忆
**Month 3 (产品):** 生产线监控台 WebUI(Workflow 进度/Node 详情/审批队列/质量 KPI)+ Release 初版

---

## 30. Next 5 Highest-Leverage Moves

1. **补 Apply 闭环** — patch 审批通过 → 真正写入 workspace → build/test → commit(把 L3 推到 L5 的关键一跳, 也解决"代码从不落地"的致命断点)
2. **真实 LLM E2E 测试** — 1 条"想法→代码→测试→提交"全链路真调 LLM, 用真实 patch 应用后跑 pytest(消除"测试都是 mock"质疑)
3. **删 14K 死代码** — 先引用检查(安全删除主体), 再全量测试验证(让架构可信)
4. **Repair 循环** — Verify FAIL → Diagnose → Repair → Retry(预算内), 让工厂能自愈
5. **生产线监控台** — WebUI 从聊天转向 Workflow/Node/Artifact/Approval/KPI(让"生产"成为用户每天看到的东西)

---

## 31. Final Decision

```
AI Factory 2.0 应该是什么?  软件生产流水线的控制平面 (Production Control Plane)
核心生产对象是什么?         Node (可验证的生产闭环单元) + Artifact (带生命周期的产物)
核心 Loop 是什么?          Node Loop: Plan → Execute → Verify → Repair → Apply → Commit
核心竞争力是什么?          Production Assurance (生产保证): 多执行器编排+证据+治理+落地闭环
Agent 在哪里?             Agent = Role + Policy + Executor 绑定 (装配体, 非超级智能体)
LLM 在哪里?              LLM 是 Executor 的能力源 (通过 Provider 适配, 可插拔)
Codex/Claude/Hermes/Pi/OpenClaw 在哪里?  可插拔执行能力 (Executor Abstraction 的下层)
Node 在哪里?             Workflow 的编排单元 (Node Runtime 标准闭环)
Artifact 在哪里?          Node 输出, 有生命周期 (生成→审批→应用→验证→提交→发布)
Evidence 在哪里?          Artifact 的可接受性证明 (Evidence Bundle)
Human 在哪里?             Approval Gate (Apply/Commit/Release) + 策略制定者
CLI 在哪里?              Production Console (生产控制台)
WebUI 在哪里?            Production Monitor (生产线监控台)
Event Store 在哪里?       事实源 (append-only, 与 Artifact/Evidence 关联, 不互相替代)
最应该删除什么?           14K 死代码 + 6 个骨架命令的虚假繁荣 + 会话无限增强
最应该停止做什么?         生成但不落地 / 为 Multi-Agent 而 Multi-Agent / 并发污染 git
最应该重建什么?           Artifact Lifecycle (Apply 闭环) + Repair/Learning 反馈环
未来 3 个月最重要的 5 件事? ①Apply 闭环 ②真实 LLM E2E ③删死代码 ④Repair ⑤生产线监控台
```

---

## ONE SENTENCE STRATEGY

> **AI Factory 2.0 = 软件生产流水线的控制平面: 编排 Claude/Codex/Hermes 等 AI 执行器,让"想法→PRD→代码→测试→发布"的每一步成为带证据、经审批、真正落地的生产节点——它是工厂本身,不是又一个会写代码的 AI 工具。**

*本提案基于 2026-08-29 现实审计(62/100, L3, PARTIAL)。零业务代码修改。*
