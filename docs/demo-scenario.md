# 预约系统完整演示 — Demo Scenario (Idea → Development)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 归属: Phase 12A-4 | 状态: 与实际能力一致 (4090 tests, 41 commits)
> 关联: [vision.md](./vision.md) · [lifecycle-model.md](./lifecycle-model.md) · [capability-architecture.md](./capability-architecture.md)
> · [human-console-model.md](./human-console-model.md) · [decision-intelligence-model.md](./decision-intelligence-model.md)
> · [recommendation-engine-model.md](./recommendation-engine-model.md) · [approval-model.md](./approval-model.md)
> · [experience-learning-model.md](./experience-learning-model.md) · [provider-selection-model.md](./provider-selection-model.md)

本文档是一份**可逐条复现**的演示脚本: 用户只说一句话 —— **"我要做一个预约系统"**,
AI Software Factory 从 Idea 一路推进到 Development, 每个阶段展示五件事:

1. **Extension** — 哪个能力模块在负责 (product / intelligence / providers / core)
2. **Decision** — 决策展示: 候选 + 评分 + 推荐 + 原因 (可复算, 非黑箱)
3. **Provider** — Provider 选择: Capability / Cost / Performance / Experience
4. **Approval** — 人工闸门: 谁批、批什么、证据是什么
5. **Cost / Experience** — 成本估算 + 经验闭环记录

> 演示铁律 (与系统一致): **AI 只产出候选与证据, 执行权永远在人**。
> 推荐≠执行, 批准≠自动跑。所有数字均可按文档公式复算。

---

## 0. 演示总览

**用户输入**: "我要做一个预约系统 —— 用户能在线选门店/服务/时间完成预约, 商家能管理排期。"

### 生命周期与阶段映射 (software_project 模板, 9d 声明式阶段链)

```
idea → research → prd → approval(prd) → ui → approval(ui) → architecture → task → Development
```

| Step | 阶段 | Extension 负责 | Decision | Provider | Approval | Cost 估算 | Experience |
|:--:|:-----|:--------------|:---------|:---------|:---------|:----------|:-----------|
| 1 | Idea | product (9a) | 无 (想法记录) | — | optional (重大方向才需确认) | $0 | — |
| 2 | Research | product 9b 生成 + providers (8B) | Provider 推荐 | hermes (free) | 无默认门 | $0 | research 经验记录 |
| 3 | PRD | product 9b 生成 + intelligence (10A) | Provider 推荐 (0.80/0.65/0.635) | hermes (free) | **mandatory gate=prd** | $0 | Generation + Approval 经验 |
| 4 | UI Design | product 9b 生成 | Provider 推荐 | hermes (free) | **mandatory gate=ui** | $0 | Generation + Approval 经验 |
| 5 | Architecture | intelligence (10A) 决策 + product 9d | 架构决策 (0.72/0.60/0.57, R1 high) | hermes (free) | recommended (可跳过) | $0 | 决策经验 |
| 6 | Task Planning | product 9d (task 阶段) | 决策链校验 (Product→Architecture→Task Plan) | — | 人工确认任务清单 | $0 | — |
| 7 | Development | core (task/workflow/execution/validation) | Agent/Provider 推荐 | hermes runtime | optional (抽查) | usage 实测 | execution 经验闭环 |

> **成本口径**: 本演示全部用内置 hermes Provider (本地执行, mode=free, 恒 $0)。
> 云 Provider (codex/claude) 作为候选参与评分与对比, 演示成本估算模型。

---

## 1. Step 1 — Idea (想法记录)

### 场景
用户的一句话想法进入 Factory, 固化为**可追溯的产品起点**。

### CLI 演示
```bash
$ factory product idea create --title "预约系统" \
    --description "用户在线选择门店/服务/时间完成预约, 商家管理排期" \
    --goals "用户可在 3 分钟内完成预约, 商家排期可一键确认"
✔ 想法已创建 PI-001
  artifact  ART-001  (type: product_idea, status: created)
  events    idea.created (source=product)
```

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | product (Phase 9A Product Intelligence 基础): `ProductIdea` + `product_idea` Artifact 同步落库 (Idea 即 Artifact) |
| **Decision** | 无决策 (Idea Gate = optional)。只记录, 不评判。Idea 阶段的候选与证据是后续 research 的输入 |
| **Provider** | 不涉及 (无 AI 调用) |
| **Approval** | Idea gate optional — 仅重大方向需产品负责人确认; 本演示直接继续 |
| **Cost** | $0.00 (纯本地记录) |
| **Experience** | 无 |

---

## 2. Step 2 — Research (调研: 市场/竞品/机会分析)

### 场景
Factory 启动生命周期, 用 AI 能力产出市场/竞品调研结论。

### CLI 演示
```bash
# 启动生命周期 (9d 声明式模板)
$ factory product lifecycle start PI-001
✔ 生命周期已启动 LC-001 (template: software_project)
  当前阶段: idea
  阶段链: idea → research → prd → approval(prd) → ui → approval(ui) → architecture → task

# 生成调研产物 (9b 生成编排: TaskRequirement → CostAwareSelector → ProviderAdapter)
$ factory product generate PI-001 --type research
✔ 生成完成 ART-002 (type: research, provider: hermes, confidence: 0.70)
  provider      hermes   (source: recommendation, estimated_cost: $0.00/call)
  approval      research 无默认审批门 (optional)

# 推进: idea → research → prd
$ factory product lifecycle advance PI-001
✔ stage completed: idea → entered: research
$ factory product lifecycle advance PI-001
✔ stage completed: research → entered: prd
```

### Decision 展示 (Provider 推荐, CostAwareSelector 8B-2)
research 生成需求: `TaskRequirement{task_type: research, required_capabilities: [analysis]}`

| 候选 | capability (analysis) | 估算成本 | 排序依据 | 推荐 |
|:-----|:-----|:-----|:-----|:-----|
| hermes | 0.60 (内置基线, evidence: builtin+smoke) | $0.00 (free) | 成本最低 → 推荐 | ✅ |
| codex (注入候选) | 0.85 (vendor 声明) | $10.50/调用 | 贵 → 不推荐 | — |
| claude (注入候选) | 0.90 (vendor 声明) | $17.50/调用 | 贵 → 不推荐 | — |

**原因**: 能力过滤 (analysis ≥ 门槛) 通过 → 成本升序 (free=0 优先) → 质量分降序。
hermes 本地免费且能力达标 → 推荐。**只推荐不自动切换** (推荐器零副作用)。

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | product 9b `ProductGenerator` (生成编排) + providers 8B `CostAwareSelector` (选择) + providers 8A Adapter (执行) |
| **Decision** | CostAwareSelector 推荐: hermes (score 依据成本优先 + 能力门槛); 事件 `provider.selected (source=recommendation)` |
| **Provider** | Capability: analysis 0.60 / Cost: free / Performance: 声明基线 / Experience: 冷启动 0.5 中性分 |
| **Approval** | 无默认审批门 (research 产物仅作证据沉淀, 不阻塞流程) |
| **Cost** | 1 次生成 × hermes free = $0.00 (若用 codex: 1 × $10.50) |
| **Experience** | `product experience record ART-002 --rating 3 --approved true --comment "竞品覆盖不全, 需补本地生活类竞品"` → GenerationExperience 落库, hermes 的 experience 分从 0.5 冷启动上升 |

---

## 3. Step 3 — PRD (需求文档生成 + 人工批准闸口)

### 场景
Factory 生成结构化 PRD, **未经过人工批准的 PRD 不可能进入 UI/架构** (mandatory gate)。

### CLI 演示
```bash
# 生成 PRD (9b: generation+reasoning 能力; 生成后自动申请审批 → lifecycle paused)
$ factory product generate PI-001 --type prd
✔ 生成完成 ART-003 (type: prd, provider: hermes, confidence: 0.80)
  provider      hermes   (source: recommendation, estimated_cost: $0.00/call)
  approval      已自动申请 APR-001 (gate: prd, status: pending) — 生命周期暂停等待人工

$ factory product lifecycle status PI-001
  当前阶段: approval (gate: prd)        # lifecycle = paused
  pending_approval: APR-001 (artifact: ART-003, gate: prd)
  next_actions: decide APR-001 (approve | reject | changes_requested | delegate)

# 人工审核台 (11A CLI) 与 Web (11B) 看到同一份待办:
$ factory console approvals
  pending  APR-001  artifact ART-003  gate prd  confidence 0.80  risk low
```

### Decision 展示 (推荐引擎 10A-3, 四因素加权, 权重 0.35/0.30/0.20/0.15)
任务: `prd`, 能力要求: `generation, reasoning`

| 候选 | capability | performance | cost | experience | 综合分 | 分项贡献 |
|:-----|:-----:|:-----:|:-----:|:-----:|:-----:|:-----|
| **hermes** | 0.75 | 0.80 | 1.00 (free) | 0.62 (含 research 经验) | **0.80** | 0.263+0.240+0.200+0.093 |
| codex | 0.85 | 0.70 | 0.30 | 0.55 | 0.65 | 0.298+0.210+0.060+0.083 |
| claude | 0.90 | 0.65 | 0.25 | 0.50 (冷启动) | 0.635 | 0.315+0.195+0.050+0.075 |

```
+ capability 0.75 (任务要求能力: generation, reasoning — 矩阵均分)
+ cost 1.00 (本地执行 free, 成本效益最高)
± experience 0.62 (research 阶段 1 条记录聚合, 高于冷启动中性 0.5)
综合评分 = Σ(因素 × 权重) = 0.7955 → 归一 0.80
风险: spread=0.15 (>0.1 无 R1) / 无短板 (min 0.62) / 非冷启动 → low, 无需审批绑定
```

**原因**: hermes 能力达标且免费, 经验分高于冷启动中性分 (research 阶段刚验证过) →
综合第一。推荐**只读**: 不切换任何配置, 执行决策权在生成编排 (9b 已装配)。

### 人工批准 (Approval)
| 项 | 内容 |
|:-----|:-----|
| **Gate** | prd — **mandatory** (approval-model 节点表) |
| **Approver** | 产品负责人 |
| **Evidence** | PRD Artifact (ART-003: 目标/用户/范围/功能/验收标准) + 生成 Lineage (provider/confidence/事件链) |
| **CLI** | `factory product approval decide APR-001 approve --comment "需求覆盖完整, 验收标准可执行"` |
| **联动** | 批准 → `approval.approved` + `product.prd.approved` 事件 → Product Decision Artifact + `DecisionArtifact(type=product)` 决策链起点 → 生命周期自动推进到 ui (9d handle_approval_outcome) |
| **反向** | reject / changes_requested → 生命周期停留 paused, 修改产物后**重新审批** (9c 终态可逆, Artifact Version v1→v2 绑定) |

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | product 9b (生成) + intelligence 10A-3 (推荐评分, 规则驱动不绑定 LLM) + product 9c/9d (审批状态机 + 生命周期暂停/推进) |
| **Decision** | 推荐引擎四因素评分 (可复算) + 9c ApprovalGate 绑定 |
| **Provider** | hermes (Capability 0.75 / Cost free / Performance 0.80 / Experience 0.62) |
| **Approval** | **PRD mandatory 人闸口** — 未批准不得进入 UI/架构 |
| **Cost** | 1 次生成 $0.00 (hermes); 若用 claude: 1 × $17.50 |
| **Experience** | `product experience record ART-003 --rating 4 --approved true` + ApprovalExperience (decision=approved, decided_by=human) |

---

## 4. Step 4 — UI Design (UI 原型生成 + 人工批准闸口)

### 场景
PRD 批准后, Factory 产出 UI 方向/流程/原型候选产物, **视觉方向同样必须人工批准** (mandatory)。

### CLI 演示
```bash
$ factory product generate PI-001 --type ui
✔ 生成完成 ART-004 (type: ui, provider: hermes, confidence: 0.75)
  provider      hermes   (source: recommendation, estimated_cost: $0.00/call)
  approval      已自动申请 APR-002 (gate: ui, status: pending) — 生命周期暂停

$ factory product approval decide APR-002 approve --comment "信息架构清晰, 预约流程 3 步到位"
✔ 已批准 APR-002 → Product Decision 已记录 → 生命周期推进到 architecture
```

### Decision 展示 (推荐引擎)
任务: `ui`, 能力要求: `generation` → hermes capability = 0.80 (矩阵); 其余候选同 PRD 轮,
hermes 以 free 成本 + 经验 0.65 (PRD 批准正反馈) 保持第一。

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | product 9b (生成) + intelligence 10A-3 (推荐) + product 9c/9d (审批/推进) |
| **Decision** | Provider 推荐 (同公式) + UI 方向决策经 9c approval (approved) |
| **Provider** | hermes (Capability 0.80 / Cost free / Performance 0.80 / Experience 0.65 上升) |
| **Approval** | **UI mandatory 人闸口** — approver 产品 + 用户代表; 证据 = UI 原型 + 交互说明 + 评审记录 |
| **Cost** | 累计 3 次生成 × $0.00 = **$0.00** (估算; 云方案 3 × $10.50 = $31.50) |
| **Experience** | `product experience record ART-004 --rating 5 --approved true --comment "原型可直接开发"` |

---

## 5. Step 5 — Architecture (架构决策, 决策智能)

### 场景
UI 批准后进入架构阶段。architecture 是 **decision 阶段**: 前置校验 (architecture 产物 +
Product Decision 链完整) → 产生 Architecture Decision → 决策链中段记录。
架构 gate 级别 **recommended** (大改动必须人工, 小改动可自动) — 本演示走人工确认。

### CLI 演示
```bash
# architecture 候选产物 ART-005 已就绪 (9b 生成编排框架, GENERATION_TYPES 声明式扩展点;
# CLI 内置 research/prd/ui, 其余生成类型经装配点注入 — 引擎只校验产物存在)
# 上一步 ui 批准后, handle_approval_outcome 已自动推进 → 当前阶段 architecture

# 决策链校验 (product 决策 + architecture 产物) 通过 → 推进 decision 阶段
$ factory product lifecycle advance PI-001
✔ stage completed: architecture → entered: task
  architecture_decision ART-006 已落库
  DecisionArtifact(type=architecture, source=ART-005, approved_reference=ART-006)
```

### Decision 展示 (Decision Intelligence 10A-2, 权重 0.40/0.25/0.20/0.15)
决策类型: `architecture_change` — 触犯 R1 (高风险决策类型) → **requires_approval=true**

| 候选方案 | capability | cost | performance | experience | 综合分 |
|:-----|:-----:|:-----:|:-----:|:-----:|:-----:|
| **单体 (模块化)** | 0.80 | 0.70 | 0.60 | 0.70 | **0.72** |
| 微服务 | 0.90 | 0.30 | 0.50 | 0.40 | 0.60 |
| Serverless | 0.70 | 0.40 | 0.80 | 0.20 | 0.57 |

```
单体: 0.80×0.40 + 0.70×0.25 + 0.60×0.20 + 0.70×0.15 = 0.320+0.175+0.120+0.105 = 0.72
理由 (reasoning 逐条): capability 最高贡献 (权重 0.40) / cost 占优 (团队小, 单机部署) /
experience 有先例 (同规模项目历史记录) → 推荐 单体
风险: R1 触发 (decision_type=architecture_change) → high → 绑定 9c ApprovalGate
置信度: 0.5×spread(0.12) + 0.3×证据覆盖(1.0) + 0.2×因素完整(1.0) = 0.56
证据链 (六来源): artifact:ART-005 / event:architecture.decision / human_input:评审意见 / external_data:流量预估
```

**引擎边界**: Decision 只分析+推荐+解释, **不携带任何执行指令**; 审批通过也不自动改代码 —
执行由后续 task/development 编排显式发起。

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | intelligence 10A-2 `DecisionIntelligence` (决策链) + product 9d (阶段编排) |
| **Decision** | 四因素规则评分 + 推荐 (单体 0.72) + 证据链 + R1 high 风险 |
| **Provider** | 架构候选由 hermes 生成 (free); 决策本身规则驱动, 不调用 LLM |
| **Approval** | gate=architecture **recommended** (approval-model 节点表: 大改动必须人工, 小改动可自动) — 本演示决策 R1 high → 经 9c ApprovalGate 绑定 (gate=architecture) 人工确认; 引擎本身不暂停 (模板无 architecture approval 阶段) |
| **Cost** | 1 次生成 $0.00; 决策引擎 $0 (规则计算) |
| **Experience** | 决策采纳可回写 (经验/评估系统只记录不修改) |

---

## 6. Step 6 — Task Planning (任务拆解, 进入 Core 执行)

### 场景
task 阶段校验**完整决策链** (Product + Architecture), 产出 task_plan 产物 +
自动调用 TaskStore.create 生成 Core Task, **从产品层无缝衔接到工厂执行层**。

### CLI 演示
```bash
$ factory product lifecycle advance PI-001
✔ stage completed: task → lifecycle completed
  task_plan ART-007 已生成 (含决策链快照: product → architecture → task_plan)
  Task T-001 已创建: "Implement 预约系统 (task plan ART-007)"
    project: default | type: feature | workflow: feature-delivery

$ factory product lifecycle status PI-001
  lifecycle: LC-001 (completed)
  decisions: [product → architecture → task_plan]   # 决策链完整, 可审计
  next_actions: 任务已交 Core Workflow 执行 (workflow run T-001)
```

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | product 9d (task 阶段) — 经 TaskStore.create 既有 API 生成 Task, **零 Core 修改** (禁复制 Workflow Core) |
| **Decision** | 决策链校验 (Product→Architecture→Task Plan 三节点) + `DecisionArtifact(type=task_plan)` |
| **Provider** | 不涉及 (编排阶段) |
| **Approval** | 任务清单人工确认 (任务进入执行前可增删改; Gate 语义 optional) |
| **Cost** | $0.00 (纯编排) |
| **Experience** | task_plan 关联决策链 → 后续任务评估 (10A-4 TaskEvaluator) 可回溯依据 |

---

## 7. Step 7 — Development (Core 执行 + 验证 + 经验闭环)

### 场景
产品链结束, 进入 **Core 已实现的执行闭环**:
Task → Workflow → Agent Assignment → Execution (Runtime) → Validation (L1-L4) →
Git/Change Intelligence → Release; 结果沉淀为经验, 改进下一次推荐。

### CLI 演示
```bash
$ factory workflow run T-001                                  # 启动 feature-delivery
$ factory agent assign --task T-001 --step development --auto # AgentAllocator: role/skill/AVAILABLE
  ✔ 分配 developer → runtime hermes (runtime_preferences 路由)
$ factory execution run T-001 --auto                          # HermesRuntimeAdapter 实跑
  ✔ execution.started → completed (artifacts + events 全链路审计)

$ factory validate T-001                                      # 四层验证, 独立于执行者
  L1 Factory  PASS   (任务数据完整)
  L2 Workflow PASS   (步骤状态合法)
  L3 Artifact PASS   (产物存在于预期路径)
  L4 Change   PASS   (变更与任务描述一致, 确定性规则禁 LLM)
  ✔ validation.passed (exit 0) — 证据落 validation/artifacts/

$ factory change analyze T-001                                # 变更智能: Files/Insertions/Modules
$ factory change triggers register --target-workflow release   # 可选: 提交即发布 (6E)
```

### Decision 展示 (执行资源推荐, 10A-3)
任务: `development`, 能力: `code, reasoning` → 候选 agent/provider/skill/workflow 统一四因素评分:
hermes (cap 0.75 / perf 0.80 / cost 1.0 / exp 0.70) = 0.81 推荐, spread > 0.1 → 低风险直接采纳;
经验分 ≤ 能力分 (`min(experience, capability)`) — 历史背书不替代能力。

### 六维展示
| 维度 | 内容 |
|:-----|:-----|
| **Extension** | core (task/workflow/execution/validation/recovery) + agents/assignment + runtime (hermes adapter) + git/change (6C/6D/6E) + intelligence 10A-4 (评估) |
| **Decision** | AgentAllocator 分配 + 推荐引擎评分 (可复算) + L4 变更验证 (确定性规则) |
| **Provider** | hermes runtime (free); per-role 偏好可换 (architect→claude / developer→codex / tester→hermes, 换工具=改配置) |
| **Approval** | Code gate optional — AI 自主执行, 人工抽查; `validate approve/reject` 是 L3 实测入口 |
| **Cost** | usage 实测累计: `factory provider usage` / `factory provider stats` (估算非计费); 本演示 hermes 全免费 |
| **Experience** | 执行结果 → `intelligence.experience.record` (result=success, score×confidence×freshness, 30 天半衰期) → 下一次推荐自动读到更好依据 (**经验闭环**) |

---

## 8. 全程审计与观测 (Console 七域)

演示结束时, Human Console (11A API / 11B Web) 展示同一份只读事实:

```bash
$ factory console dashboard        # 七域: active_projects / pending_approvals / running_agents
                                   #       / recent_decisions / cost_summary / experience_summary / activity
$ factory dashboard --view lifecycle   # LC-001: completed, 阶段时间线完整
$ factory product approval history ART-003   # PRD: v1 approved → (若改) v2 重新审批
$ factory intelligence experience list      # provider/agent/skill 聚合有效分 (freshness 衰减可见)
$ factory event logs --workspace            # 唯一事实源: 全链事件可回放 (Recovery 依赖)
```

**Web UI (11B, 只读投影)**: 普通模式回答四个问题 —— 项目在跑什么 / AI 当前在做什么 /
有什么需要我决定 / 为什么这样推荐; 专家模式展开 Provider/Cost/Evidence/Event 全链。
界面无写路径 (Permission Boundary): 审批动作指向既有 CLI 状态机, 等价事件可审计
(Web 确认 = CLI approve = 同一批 `approval.granted` 事件)。

## 9. 演示要点 (给演示者的 3 条主线)

1. **人永远是闸门**: PRD/UI mandatory 未批准 → 生命周期停在 paused, 无绕过路径
   (CLI 退出码 4 语义); 演示中故意 reject 一次 → 打回返工 → v2 重新审批。
2. **每个推荐可复算**: 四因素 × 权重 + 证据链 + 风险规则, 高分低分都有解释, 不是黑箱。
3. **经验闭环可观察**: 同一 Provider 的 experience 分从冷启动 0.5 随记录上升,
   30 天半衰期衰减 — 展示 `intelligence experience list` 前后对比。

---

*本演示与 factory-core 实际能力逐条对应 (product/lifecycle.py 阶段链、
product/generation.py 生成编排、intelligence/decision.py+recommend.py+experience.py、
providers/selector.py+costs.py、approval 状态机、human-console 只读层), 无虚构功能。*
