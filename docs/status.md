# AI Software Factory — 当前实现状态总表

> 日期: 2026-08-08 | 依据: [Reality Audit v1.0](./audit/architecture-reality-audit.md) (附录 A–I)
> 基线: HEAD 审计后 | pytest 5493 | 158 事件 | 91 CLI 命令 | 147 commits | 185 docs
> 本表是**现状快照** (代码现实), 不是愿景。愿景与差距见 [vision.md](./vision.md) / [roadmap.md](./roadmap.md)。

---

## 1. 能力总表 (代码现实)

| 能力 | 状态 | 代码位置 | 测试 | 备注 |
|:-----|:----:|:---------|:----:|:-----|
| Event 事件溯源 (28 前缀) | ✅ DONE | factory-core/events/ (1097 行) | events 69 | 158 事件, 唯一事实源 |
| Task 任务模型 | ✅ DONE | factory-core/tasks/ (216 行) | tasks 22 | 最小任务模型 |
| Workflow 引擎 (任务级) | ✅ DONE | factory-core/workflows/ (1031 行) | 各域 | 4 内置技术模板, 无组织级编排 |
| Agent/Skill Registry (基础) | ✅ DONE | factory-core/agents/ (593 行) | agents 112 | 简单执行者模型; Skill 未进执行流程 |
| Assignment 分配 | ✅ DONE | factory-core/assignment/ (665 行) | assignment 134 | AgentAllocator, 任务级 |
| Execution 执行派发 | ✅ DONE | factory-core/execution/ (497 行) | execution 100 | Runtime Adapter |
| Runtime 管理/适配 | ✅ DONE | factory-core/runtime/ + runtimes/ (1130 行) | runtimes 93 | Hermes + 适配 |
| Recovery 断点恢复 | ✅ DONE | factory-core/recovery/ (811 行) | recovery 122 | checkpoint + 事件回放 |
| Orchestration 编排 | ✅ DONE | factory-core/orchestration/ (622 行) | orchestration 73 | 工作流管线 |
| Validation L1–L4 | ✅ DONE | factory-core/validation/ (566 行) | — | PASS/FAIL/SKIP/ERROR + 证据链 |
| Dashboard 16 视图 | ✅ DONE | factory-core/dashboard/ (2455 行) | dashboard 165 | 只读聚合 |
| Metrics 六域指标 | ✅ DONE | factory-core/metrics/ (1002 行) | metrics 113 | first_attempt_success 等 |
| Git 集成 (可选) | ✅ DONE | factory-core/git/ (736 行) | — | 失败安全, Core 零 Git 依赖 |
| Change 变更智能 | ✅ DONE | factory-core/change/ (1058 行) | change 196 | Files/Insertions/Deletions/Modules |
| ChangeFlow 变更驱动 | ✅ DONE | factory-core/changeflow/ (1081 行) | changeflow 144 | 4 规则引擎 + 触发链 |
| Understanding 项目理解 | ✅ DONE | factory-core/understanding/ (699 行) | understanding 4 | 阶段判断/技术栈/缺失分析 |
| Product 产品链路 | ✅ DONE | factory-core/product/ (4063 行) | **product 501** | Idea→PRD→Approval→UI→Task, CLI 17 命令 |
| Provider 管理/选择 | ✅ DONE | factory-core/providers/ (2992 行) | **providers 569** | 四因素推荐 + 成本聚合 |
| Intelligence 认知层 | ✅ DONE | factory-core/intelligence/ (3549 行) | **intelligence 509** | Decision/Recommendation/Experience/Risk |
| CLI (24 组) | ✅ DONE | factory-core/cli/ (6418 行) | cli 38 | 91 命令 |
| Console Web UI | ✅ DONE (管理台) | factory-console/ | console 172 | 7 只读页面 + 8 只读 API; 非工作台 |
| Runtime/Desktop/Distribution | ✅ DONE | factory-runtime/ + desktop/ | factory_runtime 130 + cargo 116 | Tauri 壳 + Managed/Command |
| 组织建模 (org) | ✅ DONE | factory-org/ (2081 行) | **org 192** | Company→Department→Role→Employee + Authority + Knowledge |
| 组织模板 (software_company) | ✅ DONE | factory-org/org/templates.py | org | 唯一模板 |
| Employee Registry | ✅ DONE | factory-org/org/registry.py | org | 只推荐不分配 |
| exec Context 装配 | ✅ DONE | factory-exec/exec/context.py | exec 1019 | 6 类 Context |
| exec Ranking | ✅ DONE | factory-exec/exec/ranking.py | exec | Top-K 6 因素 |
| exec Progressive Loading | ✅ DONE | factory-exec/exec/progressive.py | exec | 3 阶段加载 |
| exec Budget Control | ✅ DONE | factory-exec/exec/budget.py | exec | 4 任务类型 |
| exec Experience 回写 | ✅ DONE | factory-exec/exec/experience_ctx.py | exec | 17 字段 |
| exec Multi Run (N=3) | ✅ DONE | factory-exec/exec/candidate.py | exec | SequentialRunner |
| exec Evaluator (5 层) | ✅ DONE | factory-exec/exec/evaluator.py | exec | 确定性评估 |
| exec Capability Registry | ✅ DONE | factory-exec/exec/capability.py | exec | ModelCapability |
| exec DeveloperAgent | ✅ DONE (真实调用) | factory-exec/exec/developer.py | exec | LLM→Operation→Patch |
| exec Sandbox | ✅ DONE | factory-exec/exec/sandbox.py | exec | 副本 + patch |
| **真实生产闭环 (Bug Fix)** | ❌ **0%** | exec + providers | — | DeepSeek 25/27 空响应 (reasoning 耗尽) |
| Employee→Task 自动分配 | ❌ NOT IMPLEMENTED | (Registry 只推荐) | — | Sprint 7 |
| 组织级 Workflow (多员工接力) | ❌ NOT IMPLEMENTED | (Workflow 任务级) | — | Sprint 7 |
| 多角色员工 (产品/架构/测试/运营) | ❌ NOT IMPLEMENTED | (仅 DeveloperAgent) | — | Sprint 7 |
| 工作台 UI (Workspace/Org/Employee/…) | ❌ NOT IMPLEMENTED | (Console 管理台) | — | Sprint 8 |
| Skill/MCP/Domain Intelligence | ❌ NOT IMPLEMENTED | (Skill 未进流程, 无 MCP) | — | Sprint 10 |
| 多行业模板 (6+ 工厂) | ❌ NOT IMPLEMENTED | (仅 software_company) | — | Sprint 12 |
| Workspace 模型 (org 根) | ❌ NOT IMPLEMENTED | (根 = Company 硬编码) | — | Sprint 7 泛化 |
| Self Improvement 自改进 | ❌ NOT IMPLEMENTED | 无模块 | — | Sprint 11 |

## 2. 测试全景 (附录 D, pytest 5493 / 285 文件)

| 域 | 测试数 | 域 | 测试数 |
|:---|:---:|:---|:---:|
| exec | 1019 | factory_runtime | 130 |
| providers | 569 | recovery | 122 |
| product | 501 | metrics | 113 |
| intelligence | 509 | agents | 112 |
| change | 196 | execution | 100 |
| org | 192 | runtimes | 93 |
| console | 172 | orchestration | 73 |
| dashboard | 165 | events | 69 |
| changeflow | 144 | cli 38 / benchmark 36 / project 34 / tasks 22 / demo 21 | — |

> 观察: exec+providers+intelligence+product ≈ 40% — 工程/认知测试为主;
> **无真实 LLM 集成测试 (全 mock)**; 测试覆盖"工程", 未覆盖"能干活"。

## 3. 事件体系 (附录 C, 158 事件 / 28 前缀)

- 最大: ORG 21 (company/employee/role 生命周期) · PRODUCT 15 · INTELLIGENCE 14 · APPROVAL 11 · PROVIDER 9
- 无 `workflow.*` 组织级事件 (workflow 7 是任务级); 无 learning/improvement 前缀

## 4. CLI 命令 (附录 B, 91 命令 / 24 组)

- product 17 (最大) · org 7 · provider 7 · change 7 · exec 6 · agent 5 · runtime 5 · workflow 4 · intelligence 4 · task 4
- 观察: 产品链路 CLI 投入最重; exec CLI 薄 (引擎在 Python API)

## 5. Git 历史 (附录 E, 147 commits, 全在 2026-08)

- docs 61 (41%) / test 45 (31%) / feat 28 (19%) / fix 13 (9%) → 文档+测试占 72%, 代码实现 19%
- 阶段: 12B-13A (验证) → 14 (开源) → 15 (Runtime/Desktop) → 16A (org) → Phase A (exec) → Sprint 3/4/5

## 6. 文档状态分类 (185 份)

| 分类 | 范围 | 状态 |
|:-----|:-----|:----:|
| 已实现描述 | system-architecture-review / project-structure / quality-report / lifecycle-model (已校准) / 本文档 | ✅ 与代码一致 |
| DESIGN ONLY 蓝图 | docs/ 顶层 + architecture/ 设计文档 49 份 (agent-/skill-/memory-/workflow-/intelligence-… 模型, 见各文档标题下状态行) | 📐 蓝图, 未实现或部分实现 |
| 过期 (数字演进) | 部分 sprint 报告 (T4.1 报 5126 vs 现 5493 — 结论仍有效) | 🟡 数字过期, 结论有效 |
| 冲突 (已校准) | vision.md / README.md / roadmap.md / ai-enterprise-operating-model.md (2026-08-08 分层修正) | 🔄 已校准 |
| 审计 | audit/architecture-reality-audit.md + architecture/ai-factory-*-audit.md (4 份) | ✅ 基准 |

## 7. 空目录残留 (附录 G, 11 个顶层占位)

`agents/ cli/ dashboard/ knowledge/ mcp/ runtimes/ skills/ src/ validation/ workflows/` — 全空, 设计先行残留;
清空或实现 (校准路线 Sprint 10 起)。

## 8. 校准路线 (摘要, 详见 roadmap.md)

| Sprint | 目标 | 核心交付 |
|:--:|:-----|:---------|
| 6 | 模型换档 + 生产闭环 | Ollama qwen3:8b, Bug Fix ≥60% |
| 7 | Employee 统一 + 组织-执行连接 | Core Agent 并入 org Employee, 分配器 + 多角色 |
| 8 | 工作台 UI | Workspace/Org/Employee/Workflow/Monitoring 视图 |
| 9 | 业务流程 + 第二行业 | 1 业务流程模板 (内容生产等) + 1 行业模板 |
| 10 | Skill/MCP + Domain Intelligence | Skill 进执行流程, MCP 接入 |
| 11 | Self Improvement | 观察→分析→建议→批准→改进 |
| 12 | 多行业工厂 | 6+ 行业模板 |

---

*本文件由技术文档工程师维护; 与审计报告同步更新。状态变更先改代码/测试, 再改本表。*
