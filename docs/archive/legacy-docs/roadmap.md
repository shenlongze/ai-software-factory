# AI Software Factory — 路线图（历史归档）

> [!IMPORTANT] 已取代（2026-08-21）
> 本路线图为 2026-08-08 版本，已被 [docs/MASTER-PLAN-2026-08.md](./MASTER-PLAN-2026-08.md)（AI Company OS 总体规划 v3）取代。
> 保留仅因历史引用；新规划一律以 MASTER-PLAN 与 [完整产品方案书](../AI%20Software%20Factory%20—%20完整产品方案书.md) 为准。

> 版本: v3.0 | 日期: 2026-08-08 | 状态: 依 [Reality Audit v1.0](./audit/architecture-reality-audit.md) 校准
> 校准原则: **先生产, 再连接, 后领域** — 每 Sprint 必须产出"真实可演示的生产结果", 禁止纯工程扩张。
> 关联文档: [vision.md](./vision.md)(愿景·诚实分层) · [status.md](./status.md)(实现状态总表)
> · [architecture-reality-audit.md](./audit/architecture-reality-audit.md)(审计基准)

---

## 0. 总览 (校准后)

**当前现实 (2026-08-08)**: 系统是**软件生产生命周期管理平台 + 组织建模 + 单 Agent 执行工程**。
pytest 5493 全绿 / 158 事件 / 147 commits / 185 docs。Vision 达成度约 25% — 创建/管理 ✅,
运行 ❌ (Bug Fix 0%, 模型瓶颈), 进化 ❌, 多行业 ❌, 工作台 ❌。

原 Phase 7–11 规划中的多数内容 (Understanding / Provider / Product / Console) **已在 Phase A +
Sprint 3–5 期间实际完成** (见 §1)。本路线图未来部分不再沿用旧 Phase 编号, 改为 **Sprint 6–12
校准路线** — 对齐审计 §10 的推荐方向。

```
已完成 (Phase 1–16A + Phase A + Sprint 3/4/5)     校准路线 (Sprint 6–12)
┌──────────────────────────────┐      ┌──────────────────────────────┐
│ Core 冻结 (事件/任务/工作流/    │      │ Sprint 6  模型换档 (Ollama,     │
│  执行/验证/恢复/Dashboard)      │ ───▶ │           Bug Fix ≥60%)        │
│ Extension (Git/Change/Product)│      │ Sprint 7  Employee 统一+连接     │
│ Intelligence (决策/推荐/经验)   │      │ Sprint 8  工作台 UI              │
│ Human Console (7 只读管理页)    │      │ Sprint 9  业务流程模板+第二行业   │
│ org (Company→…→Employee)      │      │ Sprint 10 Skill/MCP+Domain Intel│
│ exec (Context/MultiRun/…,     │      │ Sprint 11 Self Improvement      │
│   12353 行, 生产 0%)           │      │ Sprint 12 多行业工厂 (6+ 模板)    │
└──────────────────────────────┘      └──────────────────────────────┘
```

---

## 1. 已完成 (Phase 1–16A + Phase A + Sprint 3/4/5)

### 1.1 Phase 1–6E (Core 基础, 累计 2159 tests 当时)

| Phase | 名称 | 核心交付 |
|:--:|------|---------|
| 1 | Event Logger MVP | Pydantic 不可变 Event + SQLite append-only EventStore + Metrics 聚合 |
| 2 | Factory Control CLI | Task 系统 + CLI (init/task/status/logs/validate) + Event 集成 |
| 3A | Validation Engine | 三层验证 (L1 Factory / L2 Workflow / L3 Artifact) + Event + CLI Report |
| 3B | Agent + Skill Registry | Agent/Skill 模型 + Registry (find_by_skill) + JSON 持久化 + CLI |
| 4A | Workflow Engine | Workflow/Step 状态机 + Engine + 内置定义 + Task.workflow 关联 + CLI |
| 4B-1 | Runtime Adapter Interface | Execution 模型 + RuntimeAdapter 抽象 + RuntimeRegistry + execute_step + CLI |
| 4B-2 | Execution Dispatch Layer | Dispatcher/Runner/Service + EchoRuntimeAdapter + Workflow 联动 + CLI |
| 4B-3 | Agent Assignment Layer | Assignment 模型 + Matcher (role/skill/AVAILABLE) + Allocator + CLI |
| 4C-1 | Hermes Runtime Adapter | HermesRuntimeAdapter (subprocess) + 五类失败→FAILED + runtime test |
| 4C-2 | Execution Orchestration Flow | OrchestrationEngine + Pipeline + 失败无半完成 + --auto |
| 4C-3 | Checkpoint Recovery | Checkpoint + EventReplay + RecoveryService (四场景) + CLI |
| 4C-4 | Dashboard MVP | FactorySnapshot + Collector (只读) + Rich Renderer (六视图) + CLI |
| 5A | Production Example Layer | examples/markpad + 加载器 + CLI project |
| 5A.1 | Runtime Catalog | RuntimeDefinition + Catalog + 独立 catalog.json + 默认定义 |
| 5B | Metrics Intelligence Layer | FactoryMetrics 六域 + Collector + Calculator + CLI metrics |
| 6A | Multi Project Workspace Layer | workspace/ (Workspace+ProjectDefinition+Manager+自动发现) + CLI |
| 6B | Workspace Operations Dashboard | dashboard/metrics/events --workspace + 13 视图 |
| 6C | Git Integration Layer | git/ (Client 失败安全 + Service + task↔git 关联) + CLI |
| 6D | Change Intelligence Layer | change/ (commit 解析 + analyzer + 自动关联 + L4 Change Validation) |
| 6E | Change Driven Workflow Layer | changeflow/ (ChangeTrigger + 4 规则引擎 + ChangeWorkflowEngine 触发链) |

### 1.2 Phase 7–16A + Phase A + Sprint 3/4/5 (实际完成, 旧 roadmap 标注"规划中"已过期)

| 阶段 | 名称 | 实际落地 | 测试 |
|:--:|------|---------|:--:|
| 7 | Project Understanding | `factory-core/understanding/` (699 行: 阶段判断/技术栈/缺失分析) | understanding 4 |
| 8 | LLM Provider Abstraction | `factory-core/providers/` (2992 行: registry/selector/costs/feedback) + exec 真实适配器 (anthropic/openai → DeepSeek) | providers 569 |
| 9 | Product Intelligence | `factory-core/product/` (4063 行: Idea→PRD→Approval→UI→Task, CLI 17 命令) | **product 501** |
| 10 | Operations | ❌ **未实现** (仅 release workflow 步骤; 无 deploy/monitor/incident) | — |
| 11 | Human Approval Console | ✅ factory-console (7 只读页面 + 8 只读 API + Simple/Expert) — 管理台, 非工作台 | console 172 |
| 12–14B | 开源发布 / 质量 / 演示 | v1.0.0-rc1 + demo 脚本 + real-world-validation | demo 21 |
| 15 | Runtime + Desktop | factory-runtime (Managed+Command) + desktop (Tauri+dmg) + Distribution | factory_runtime 130 |
| 16A | Organization Foundation | `factory-org` (2081 行: Company→Department→Role→Employee + Authority + Knowledge + software_company 模板) | **org 192** |
| Phase A | Execution MVP | `factory-exec` 起步 (DeveloperAgent 雏形) | exec 起步 |
| Sprint 3 | Context Engine | exec/context.py 6 类 Context + Ranking (Top-K 6 因素) + Progressive (3 阶段) + Budget (4 任务类型) | tests/exec 暴增 |
| Sprint 4 | 执行策略工程 | exec/ranking.py + progressive.py + budget.py + context 预算控制 (T41/T42/T43) | exec 1019 |
| Sprint 5 | 执行可靠性工程 | exec/developer.py + agent_runtime.py + evaluator.py (5 层确定性) + multi_run + sandbox + experience_ctx (17 字段) | exec 1019 |

> **诚实标注**: Sprint 3–5 是"执行工程", 不是"生产结果"。真实 LLM 链路已打通
> (OpenAI 兼容适配器 → DeepSeek), 但 Benchmark 显示 **25/27 空响应 → Bug Fix 0%** —
> 生产闭环未跑通, 这是 Sprint 6 的首要任务。

---

## 2. 校准路线 (Sprint 6–12)

> 依据审计 §9/§10: 先证明生产 (换模型), 再统一模型 (Employee), 再连接组织-执行,
> 然后工作台/业务流程/Skill/自改进/多行业。**每 Sprint 结束必须有真实可演示的生产结果**。

### Sprint 6 — 模型换档 + 生产闭环验证 (最高优先)

- **目标**: 打破 Bug Fix 0%。Ollama qwen3:8b 本地跑 9 样本 → Bug Fix ≥60%。
- **内容**: 拉取/配置 Ollama 本地模型; exec providers 增加 Ollama 适配器; 9 样本
  Benchmark (沿用 sprint5-t55 方法论) 对比 DeepSeek vs 本地; 修复 reasoning 耗尽
  导致的空响应 (prompt/采样/降级策略)。
- **退出标准**: 真实代码 bug 修复成功率 > 0% 且 ≥60%; Benchmark 报告 v2 产出。
- **关联**: [sprint5-t55-benchmark-report.md](./validation/sprint5-t55-benchmark-report.md)

### Sprint 7 — Employee 统一 + 组织-执行连接

- **目标**: 消除双 Agent 模型 (Core Agent vs org Employee)。
- **内容**: Core Agent 并入 org Employee (Employee = 执行实体: +model/memory/kpi);
  Employee→Task 分配器 (Registry 只推荐 → 可分配); 多角色员工 (产品/架构/测试/
  运营 Agent) 复用 exec 引擎。
- **退出标准**: 一个 Employee 从"被分配任务"到"产出真实可验证结果"的完整链路演示。

### Sprint 8 — 工作台 UI

- **目标**: Console 从"只读管理台"升级为"工作台"。
- **内容**: Workspace/Org/Employee/Workflow/Monitoring/Config 视图; 只读→可操作
  (分配/审批/启动); 数据源复用既有事件流。
- **退出标准**: 用户在 Web 上完成"建任务→分配 Employee→查看执行→审批"闭环。

### Sprint 9 — 业务流程模板 + 第二行业

- **目标**: 证明"非软件"可扩展。
- **内容**: 加 1 个业务流程模板 (如内容生产: 选题→撰稿→审核→发布), 验证 Workflow
  从技术流程扩展到业务流程; 第二行业模板 (内容/电商 之一)。
- **退出标准**: 业务流程模板端到端跑通, 与 feature-delivery 同等可观测可审批。

### Sprint 10 — Skill/MCP 整合 + Domain Intelligence

- **目标**: 外部工具进入核心流程。
- **内容**: Skill 进入执行流程 (Developer Agent 装配 Skill); MCP 工具协议接入;
  Domain Intelligence (行业知识注入 context)。
- **退出标准**: 一个 Skill/MCP 工具被真实执行流程调用并有可审计记录。

### Sprint 11 — Self Improvement (自改进)

- **目标**: 系统能"观察→分析→建议→批准→改进"。
- **内容**: 观察 (指标/失败模式) → 分析 (根因) → 建议 (改进提案) → 人工批准 →
  实施 (改进自身配置/流程) → 验证; 每步人工闸门, 不能无限自修改。
- **退出标准**: 一次真实的"系统发现自身缺陷→人工批准→改进→验证"闭环。

### Sprint 12 — 多行业工厂

- **目标**: 6+ 行业模板 (IT/运维/电商/媒体/数据/办公)。
- **内容**: Organization/Workflow/Knowledge/Role 四类模板按行业参数化; 模板市场/管理。
- **退出标准**: ≥3 个行业模板可独立初始化并跑通核心流程。

---

## 3. 节奏与退出标准

| Sprint | 名称 | 核心交付物 | 依赖 |
|:--:|------|---------|:--:|
| 6 | 模型换档 + 生产闭环 | Bug Fix ≥60% (9 样本 Benchmark v2) | exec providers 就绪 |
| 7 | Employee 统一 + 连接 | 单 Employee 端到端执行演示 | Sprint 6 (能干活才能连接) |
| 8 | 工作台 UI | Web 端管理→操作闭环 | Sprint 7 (有可操作对象) |
| 9 | 业务流程 + 第二行业 | 1 业务流程模板 + 1 行业模板 | Sprint 8 |
| 10 | Skill/MCP + Domain Intel | Skill/MCP 进执行流程 | Sprint 9 |
| 11 | Self Improvement | 自改进闭环 1 次 | Sprint 10 |
| 12 | 多行业工厂 | 6+ 行业模板 | Sprint 9–11 沉淀 |

**全局退出标准** (审计校准后): 可观测 · 可恢复 · 可信 (证据链) · 可复用 (经验) ·
**可生产 (Sprint 6 核心, 原缺口)** · 可连接 (组织-执行) · 可操作 (工作台) · 可扩展
(多行业) · 可进化 (自改进)。

> 每 Sprint 遵循既有纪律: 基线先跑 (`.venv/bin/pytest -q`, 5493) → 设计文档 + ADR →
> 自底向上实现 → 全量验证 + 真实结果 Benchmark → 提交推送。规划以本文件为准, 实施
> 细节以当阶段 design/ 文档与 ADR 为准。
