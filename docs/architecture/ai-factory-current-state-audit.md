# AI Factory — Current State Audit（现实审计）

> 日期: 2026-08-08 | 类型: Reality Audit — 只基于代码/测试/文档/Git history, 不做推测
> 基线: HEAD=7ccdac3 | pytest 5493 (collect) | 158 事件 | 40 顶层 docs + 31 architecture + 15 validation + 35 ADR

## 1. Executive Summary

```
AI Software Factory 是一个"软件生产管理平台 + 组织建模 + 单 Agent 执行工程"。
不是 AI Company OS（组织-执行未连接、无工作台 UI、无多行业、无领域智能）。
不是 ChatBot / 纯代码生成器（有完整生命周期/审批/组织模型）。

强: Core 冻结 + 组织模型 (org) + 执行工程 (exec 28 模块) + 5493 测试
弱: 真实生产 0%（模型瓶颈）+ 组织-执行断链 + UI 管理台 + 多行业未开始
风险: 文档超前实现（vision/roadmap 描绘 AI Enterprise OS, 代码在"软件生产"层）
```

## 2. Code Reality（能力状态，引用代码）

| 能力 | 状态 | 代码位置 | 测试 |
|---|---|---|---|
| Organization Model (Company/Department/Role/Employee/Authority/Knowledge) | **DONE** | factory-org/org/models.py (Company:68/Department:89/Role:98/Employee:123/Authority:154) | tests/org 192 |
| 组织模板 (software_company) | **DONE** | factory-org/org/templates.py | tests/org |
| Employee Registry (只推荐不分配) | **DONE** | factory-org/org/registry.py | tests/org |
| Context Engine (6 类 Context) | **DONE** | factory-exec/exec/context.py | tests/exec 1019 |
| Ranking Engine (Top-K 6 因素) | **DONE** | factory-exec/exec/ranking.py | tests/exec |
| Progressive Loading (3 阶段) | **DONE** | factory-exec/exec/progressive.py | tests/exec |
| Budget Control (4 任务类型) | **DONE** | factory-exec/exec/budget.py | tests/exec |
| Experience Feedback (17 字段) | **DONE** | factory-exec/exec/experience_ctx.py | tests/exec |
| Multi Run (N=3 Sequential) | **DONE** | factory-exec/exec/candidate.py (SequentialRunner) | tests/exec |
| Evaluator (5 层确定性) | **DONE** | factory-exec/exec/evaluator.py | tests/exec |
| Capability Registry | **DONE** | factory-exec/exec/capability.py | tests/exec |
| Developer Agent (LLM→Operation→Patch) | **DONE** (真实调用) | factory-exec/exec/developer.py + agent_runtime.py | tests/exec |
| Sandbox (副本+patch) | **DONE** | factory-exec/exec/sandbox.py | tests/exec |
| Workflow Engine (Core 任务级) | **DONE** (任务级) | factory-core/workflows/ (WorkflowEngine) | tests/ 各域 |
| Agent Registry / Skill Registry (Core) | **DONE** (基础) | factory-core/agents/ (AgentRegistry/SkillRegistry) | tests/agents 112 |
| Intelligence (Decision/Recommendation/Experience) | **DONE** | factory-core/intelligence/ | tests/intelligence 509 |
| Lifecycle (Idea→PRD→Approval→Task) | **DONE** | factory-core/product/ | tests/product 501 |
| Runtime/Desktop/Console | **DONE** | factory-runtime/ + desktop/ + factory-console/ | tests/runtime 215 |
| Employee→Task 自动分配 | **NOT IMPLEMENTED** | (Registry 只推荐, 无分配器) | — |
| 组织级 Workflow (多员工接力) | **NOT IMPLEMENTED** | (Workflow 是任务级, 无组织编排) | — |
| 多角色员工执行 (产品/架构/测试/运营) | **NOT IMPLEMENTED** | (只有 DeveloperAgent) | — |
| 工作台 UI (Workspace/Org/Employee/Workflow/Monitoring/Config) | **NOT IMPLEMENTED** | (Console 7 页面管理台) | tests/console 172 |
| Skill/MCP/Domain Intelligence | **NOT IMPLEMENTED** | (Core skills 有 CLI 基础, 无 MCP/整合) | — |
| 多行业模板 (6+ 工厂) | **NOT IMPLEMENTED** | (只有 software_company) | — |
| Workspace 模型 | **NOT IMPLEMENTED** | (org 根是 Company) | — |

## 3. Documentation Reality

| 分类 | 文档 | 状态 |
|---|---|---|
| 已实现 | system-architecture-review / project-structure / quality-report / sprint T5.x reports / product-proof-report | ✅ 与代码一致 |
| 规划 | vision / roadmap / ai-enterprise-operating-system-reference / ai-employee-*-model / phase 16-20 设计 (22 份) | 📐 DESIGN ONLY (超前) |
| 已过期 | 部分 sprint 报告 (T4.1 报 5126 vs 现 5493 — 数字演进正常, 结论仍有效) | 🟡 数字过期, 结论有效 |
| 冲突 | vision.md (AI Enterprise OS 定位) vs 代码 (软件生产层) — **主要冲突** | 🔴 |
| 冲突 | ai-enterprise-operating-model.md Company ×3 vs org 模型 (Company 仍是根, 未泛化) | 🟡 |
| 冲突 | roadmap.md Phase 15-21 vs 实际 Sprint 体系 | 🟡 |

## 4. Architecture Reality（真实架构, 非理想）

```
┌─ Desktop (Tauri launcher) — 入口壳 (无业务)
├─ Runtime (Managed Services: Console + Command: Core CLI)
├─ Console Web UI — 7 只读管理页 (Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/Providers)
├─ factory-org — Company(root)→Department→Role→Employee + Authority + Knowledge
│     (Employee 有 capabilities/knowledge_scope/experience_ref; 无 Model/Memory 绑定)
├─ factory-exec — 单 Agent 执行链:
│     Task → Context(Ranking/Progressive/Budget/Experience) → DeveloperAgent
│     → LLM(Provider Adapter) → Operation/Sandbox → Validation → (Multi Run + Evaluator)
│     → Experience Record
│     (employee_id 松散传入; 无 Workflow 编排/无多角色)
├─ factory-core — 冻结原语: events(158)/tasks/workflows/execution/approval/
│     agents/skills/intelligence/metrics/product/providers/change/git...
└─ 数据: .factory/ (org/exec/intelligence/providers/console 独立空间, JSON 原子写)

真实关系:
  Workspace: 不存在 (根 = Company)
  Organization→Employee: 建模完整, 但 Employee 不"干活" (exec 松散接入)
  Workflow: Core 有任务级引擎 (WorkflowEngine), org 无组织级编排
  UI: 只读管理, 无操作/无工作台
```

## 5. 战略目标匹配分析

| 原始目标 | 实现度 | 证据 |
|---|---|---|
| AI Company OS (创建/管理/运行/进化 AI 公司) | **PARTIAL** | 创建/管理 ✅ (org+lifecycle); 运行/进化 ❌ (无生产闭环/无组织流程) |
| 造专家的工厂 | **PARTIAL** | 一个专家 (Developer) 造好了; 专家工厂 (多角色/多行业) 未开始 |
| 多行业工厂 (IT/运维/电商/自媒体/数据/办公) | **NOT IMPLEMENTED** | 只有 software_company 模板 |
| 组织级生产 (目标→部门协作→交付) | **NOT IMPLEMENTED** | Workflow 是任务级 |
| 工作台/监控/配置 | **NOT IMPLEMENTED** | 管理台 |

## 6. 重点问题回答

### Q1: AI Factory 当前到底是?

**判断: B+D 之间 — "软件生产 Workflow 平台 + 单 Agent 执行工具" (非 C AI Organization OS)**

```
证据:
  B Workflow 平台: ✅ Core WorkflowEngine + 生命周期 (Idea→PRD→Task) + Console 管理
  D AI Factory:   部分 — 有"工厂"管理 (org/lifecycle), 但无"生产" (Bug Fix 0%)
  C AI Organization OS: ❌ 组织-执行断链 (Employee 不干活), 无工作台, 无多行业
  A Agent 工具:    部分 — 有单 Agent 执行工程 (exec), 但不是"工具" (有组织/审批层)
```

### Q2: Organization/Company/Department/Role/Employee/Workspace 真实关系?

```
代码现状 (factory-org/org/models.py):
  Company (68) → Department (89) → Role (98) → Employee (123)
  Authority (154) 绑 Role | KnowledgeItem (177) 绑 Company
  Workspace: 不存在
  Company = 硬根 (12 处引用); 无 Organization 抽象; 无 type 泛化
Employee = 组织身份 (capabilities/knowledge_scope/experience_ref/status) — 非执行实体
```

### Q3: Workflow 在哪里?

```
✅ 任务级 Workflow: factory-core/workflows/ (WorkflowEngine/WorkflowStep/WorkflowRun) — DONE
❌ Agent 流程: 无 (exec 是任务→执行直连, 无编排)
❌ 组织流程: 无 (无"目标→部门接力")
❌ 生产流程: 无 (生命周期是审批链, 非生产流)
```

### Q4: UI 能力?

```
现有 7 页面 (factory-console/web/frontend/src/pages/):
  Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/Providers — 全部只读管理
缺失: Workspace/Organization 可视化/Employee 视图/Workflow 看板/Monitoring/Config Center
判定: 管理后台 (非工作台)
```

### Q5: 外部工具 (Skill/MCP/OpenClaw/Hermes)?

```
Skill: Core skills 有 CLI/Registry (agents/skills.py) — 未进执行流程 (Developer 不用 Skill)
MCP: 不存在
OpenClaw: 不存在
Hermes: 用于开发流程 (子代理), 非产品依赖
判定: 未进入核心流程 (外部工具 = 零依赖 ✅ 符合原则, 但也 = 无增强能力)
```

## 7. Gap Analysis

```
🔴 关键缺口 (阻塞产品):
  1. 真实生产 0% (模型瓶颈: deepseek-v4-flash 25/27 空响应)
  2. 组织-执行断链 (Employee 不干活, 无分配/无编排)
  3. 单 Agent (只有 Developer)

🟡 重要缺口:
  4. UI 管理台 (无工作台)
  5. Workspace/Organization 泛化
  6. 多行业模板

🟢 工程缺口 (已就绪待接):
  7. Skill 进执行 / MCP 整合 / Domain Intelligence
```

## 8. Risk

```
1. 文档-实现漂移: vision/roadmap 描绘 AI Enterprise OS, 代码在软件生产层
   → 外部评估 (投资人/用户) 会看到差距; 需诚实分层文档
2. 单点模型依赖: 当前全部真实执行依赖 DeepSeek (API) — 换 Ollama 消除
3. 工程 vs 产品: 28 个 exec 模块 / 5493 测试 / 119 文档 — 但 Bug Fix 0%
   → 过度工程风险: 用户要的是"能干活", 不是"架构完美"
4. 决策惯性: 大量投入 Context/Execution 工程 (Sprint 4/5), 换模型后这些才兑现价值
```

## 9. Recommended Next Step（仅建议, 非开发方案）

```
S1. 模型换档验证 (Ollama qwen3:8b 本地 — 已就绪, 零成本): 跑 9 样本
    → 验证生产闭环是否恢复 (Bug Fix >0%)
S2. 诚实文档分层: vision 分"愿景/已实现/进行中"三栏 (消除漂移)
S3. 组织-执行连接: Employee→Task 分配 + 多角色员工 (product/architect/test 复用 exec 引擎)
S4. 工作台 UI: 6 视图 (Workspace/Org/Employee/Workflow/Monitoring/Config)
S5. 多行业: 声明式模板扩展 (ecommerce/media/data 工厂)
```

---

**Reality Audit 完成。不修改/不优化/不重构。等待下一步指令。**
