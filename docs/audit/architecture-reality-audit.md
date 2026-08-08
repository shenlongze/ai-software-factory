# AI Software Factory Reality Audit v1.0

> 日期: 2026-08-08 | 类型: 全面现实审计（基于真实代码/测试/文档/git, 不猜测）
> 基线: HEAD=a5f9d8b | pytest 5493 | 158 事件 | 90+ CLI 命令 | factory-core 32736 行 / exec 12353 行 / org 2081 行

## 1. Executive Summary

```
一句话回答核心问题:
"AI Software Factory 现在不是我们最初想做的那个东西。"
它现在是: 一个强大的"软件生产生命周期管理平台 + 组织建模 + 单 Agent 执行工程"。
它还不是: "能创建、管理、运行和进化 AI 公司的操作系统"。

差距本质: 我们有"公司"的骨架 (Company→Department→Role→Employee) 和"员工"的
一个原型 (Developer Agent 执行工程), 但没有: 员工真正干活 (生产 0%)、
员工协作 (组织级 Workflow)、员工多样化 (多角色)、工作台 (UI)、
多行业工厂 (只有软件)、自进化 (Self Improvement)。
```

## 2. Current System Reality（真实状态）

```
仓库结构 (边角料全扫):
  顶层: factory-core(25 模块)/factory-org/factory-exec/factory-console(Web)/factory-runtime
        /desktop(Tauri)/tests(285 文件)/docs(185 文件)
  空目录残留 (早期脚手架, 全空): knowledge/ mcp/ runtimes/ skills/ validation/
        workflows/ src/ agents/  ← 顶层占位, 无任何内容 (git 跟踪或忽略)
  配置: 仅 examples/markpad/{project,agents,workflows,skills}.yaml (示例)
  $SMOKE_ROOT/ (历史误提交已清理, 目录残留)

Core (冻结, 32736 行):
  events(158)/tasks/workflows/execution/approval/intelligence/metrics/product/
  agents/skills/providers/change/changeflow/git/understanding/project/dashboard/...

org (2081 行): Company→Department→Role→Employee→Authority→Knowledge
  Employee 字段: id/company_id/name/role_ids/capabilities/knowledge_scope/
                  experience_ref/performance/status/joined_at/left_at
  (无 Model/Memory/Skill/Workflow 绑定 — 不是完整"执行实体")

exec (12353 行): Context/Ranking/Progressive/Budget/Experience/MultiRun/
  Evaluator/Capability/Sandbox/Operation/DeveloperAgent/AgentRuntime

Console: 7 页面 (Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/
  Providers) — API 全只读 (GET /api/*)
```

## 3. Original Vision Alignment

| Vision 元素 | 状态 | 证据 |
|---|---|---|
| 创建 AI 公司 | ✅ 部分 | org Company/Department/Role/Employee + software_company 模板 |
| 管理 AI 公司 | ✅ 部分 | 生命周期 + 审批 + Console 管理台 |
| 运行 AI 公司 | ❌ | Employee 不干活 (生产 0%, Bug Fix 0%) |
| 进化 AI 公司 | ❌ | 无 Self Improvement 系统 |
| 多行业工厂 (IT/运维/电商/媒体/数据/办公) | ❌ | 只有 software_company 模板 |
| 外部工具 = 能力插件 | ✅ | 零依赖 (但也零增强: Skill/MCP 未进流程) |
| "造专家的工厂" | ❌ | 只造了一个专家 (Developer), 无专家工厂 |

## 4. Architecture Analysis（真实分层）

```
Desktop(Tauri 壳) → Runtime(Managed+Command) → Console(只读管理台)
  → factory-org (组织建模, 不与执行连接)
  → factory-exec (单 Agent 执行链: Task→Context→LLM→Patch→Evaluator→Experience)
  → factory-core (冻结原语)

Core/Extension 边界: ✅ 清晰 (exec/org 独立空间 + 事件解耦 + Removal 测试)
Layer 划分: ⚠️ 有"技术分层"但无"业务分层":
  缺 Workspace 层 (入口) / 缺组织级编排层 / 缺领域层 (行业模板)
```

## 5. Domain Model Analysis

```
存在的领域概念 (代码级):
  ✅ Company/Department/Role/Employee/Authority/Knowledge (org/models.py)
  ✅ Approval (product/models.py: ApprovalGate/ApprovalStatus)
  ✅ Experience (intelligence: ExperienceRecord + exec: ContextExperienceRecord)
  ✅ Workflow (Core: WorkflowEngine + 4 内置模板)
  ✅ Agent (Core agents/models.py: id/name/role/skills/status/current_task)
  ✅ Capability (exec: ModelCapability + Employee.capabilities)

不存在的领域概念:
  ❌ Workspace (org 根 = Company 硬编码, 12 处引用)
  ❌ Organization 抽象 (Company 绑定, 无 type 泛化)
  ❌ Responsibility (Role 有 responsibility 字符串字段, 无结构化职责模型)
  ❌ Business Process (Workflow 全是软件技术流程, 无业务流程模板)
  ❌ Factory Template (只有 software_company; 无 IT/电商/媒体工厂)
  ❌ KPI/Performance 体系 (Employee.performance 是 float, 无考核闭环)
  ❌ Policy 系统 (无独立 Policy; RiskLevel 在 intelligence, 未成治理层)
  ❌ Audit 系统 (无 AuditRecord; 用 Event 流代替 — 部分满足)
  ❌ Self Improvement (无模块; 仅字面出现在 demo/product)
```

## 6. Missing Concepts（Top 5 缺失）

```
1. 组织-执行连接 (Employee 不干活; Registry 只推荐不分配; 无 Workflow 编排)
2. 真实生产闭环 (LLM 瓶颈: 25/27 空响应 → Bug Fix 0%; 工程层无法补偿)
3. 多角色员工 (只有 DeveloperAgent; 产品/架构/测试/运营 Agent = 0)
4. 工作台 UI (7 只读管理页; 无 Workspace/Org/Employee/Workflow/Monitoring/Config)
5. 多行业工厂 (software_company 唯一模板; 6+ 工厂 = 0)
```

## 7. Direction Deviation Analysis（方向偏离）

```
正确方向 (继续):
  ✅ Core 冻结纪律 + 事件溯源 (137→158) — 架构不腐化
  ✅ org 模型结构 (Company→Department→Role→Employee — 正确骨架)
  ✅ 执行工程 (Context 智能/MultiRun/Evaluator — 架构级正确)
  ✅ 审批/验证/审计基础设施
  ✅ Provider 可替换 (Ollama 验证就绪)

可能偏离:
  ⚠️ exec 28 模块过度工程倾向: 12353 行执行工程 vs Bug Fix 0%
     (模型瓶颈下, 工程边际收益递减; 应先换模型再扩工程)
  ⚠️ 顶层空目录 (knowledge/mcp/skills/...) 是"设计先行"残留:
     文档设计 22 份 vs 实现滞后 → 蓝图驱动而非需求驱动
  ⚠️ Agent 模型停留在"Runtime 执行者" (Core agents: role/skills/current_task)
     而非 AI Employee (无 authority/memory/kpi/model) — 两套模型并存
     (Core Agent vs org Employee 未统一)
  ⚠️ Workflow 全技术流程 (feature-delivery/desktop-feature/bug-fix/release)
     无业务流程 (电商增长/内容生产/运营) — 与多行业愿景脱节
```

## 8. Risk Assessment

```
1. 定位漂移风险: 文档宣称 Enterprise OS, 代码是生产管理平台
   → 外部评估 (投资人/用户) 差距明显; 需诚实分层或加速实现
2. 模型单点: 全部真实执行依赖 DeepSeek API — Ollama 本地是唯一脱钩路径
3. 过度工程: 12353 行 exec vs 0 生产 — 换模型前工程继续扩张是浪费
4. 双 Agent 模型: Core Agent (Runtime 执行者) vs org Employee (组织身份)
   未统一 — 未来连接层会撞墙
5. 空目录/占位残留: knowledge/mcp/skills 顶层空壳 — 暗示"规划了没做"
6. 测试-能力错配: 5493 测试全绿但真实生产 0% — 测试覆盖工程, 未覆盖"能干活"
```

## 9. Recommended Correction（方向纠正, 非局部优化）

```
A. 先证明生产 (模型换档):
   Ollama qwen3:8b 本地跑 9 样本 → Bug Fix >0% → 才有"公司能运行"
B. 统一模型:
   Core Agent 并入 org Employee (Employee = 执行实体: +model/memory/kpi)
   消除双模型 (这是组织-执行连接的先决条件)
C. 组织-执行连接:
   Employee→Task 分配 + Workflow 编排 (多角色员工复用 exec 引擎)
D. 诚实文档:
   vision 分"愿景/已实现/进行中"; 清空顶层占位目录 (或实现)
E. 业务化 Workflow:
   加 1 个业务流程模板 (如内容生产) 验证"非软件"可扩展
```

## 10. Future Roadmap（校准后）

```
Sprint 6: 模型换档 + 生产闭环验证 (Ollama, Bug Fix ≥60%)
Sprint 7: Employee 统一 + 组织-执行连接 (分配器 + 多角色)
Sprint 8: 工作台 UI (Workspace/Org/Employee/Workflow/Monitoring)
Sprint 9: 业务流程模板 + 第二行业 (内容/电商)
Sprint 10: Skill/MCP 整合 + Domain Intelligence
Sprint 11: Self Improvement (观察→分析→建议→批准→改进)
Sprint 12: 多行业工厂 (6+ 模板)
```

---

## 附: 七个核心问题直接回答

**Q1: 现在系统本质是什么?**
"一个软件生产生命周期管理平台 + 组织建模器 + 单 Agent 执行引擎"
(不是 workflow automation engine — 比它多 org/审批; 不是 enterprise OS — 比它少生产/协作/领域)

**Q2: 距离 Vision 多远?**
**约 25%**。依据: 创建/管理 ✅ (组织+生命周期), 运行 ❌ (生产 0%), 进化 ❌,
多行业 ❌, 工作台 ❌。骨架 ~40%, 生产/协作/领域 ~10-20%。

**Q3: 正确方向模块**
| 模块 | 原因 |
|---|---|
| factory-core 冻结纪律 | 事件溯源/Removal 测试 — 架构不腐化 |
| factory-org 模型 | Company→Department→Role→Employee 骨架正确 |
| factory-exec 执行工程 | Context/MultiRun/Evaluator — 架构级正确 (待模型兑现) |
| 审批/验证基础设施 | 人工闸门 = 企业级信任前提 |
| Provider 可替换 | Ollama 验证就绪 — 架构承诺兑现中 |

**Q4: 可能偏离模块**
| 模块 | 为什么 | 影响 |
|---|---|---|
| exec 28 模块工程 | 模型瓶颈下边际收益递减 | 换模型前继续扩张 = 浪费 |
| Core Agent vs org Employee | 双模型未统一 | 连接层撞墙 |
| Workflow 全技术流程 | 无业务流程模板 | 多行业愿景脱节 |
| 顶层空目录 (knowledge/mcp/skills) | 设计先行残留 | 蓝图≠能力 |
| 文档 22 份设计 vs 实现 | 蓝图驱动 | 外部评估偏差 |

**Q5: 最大缺失 Top 5**
1. 组织-执行连接 2. 真实生产闭环 (模型) 3. 多角色员工 4. 工作台 UI 5. 多行业工厂

**Q6: 按当前路线 6 个月预测**
"架构继续完美, 生产仍然 0%"。exec 扩到 40+ 模块, 文档 150+ 份,
测试 7000+, 但换模型前 Bug Fix 仍 ~0% → 产品不可用, 投资人/用户不买单。

**Q7: 重新校准架构路线**
"先生产, 再连接, 后领域": 换模型 (6) → Employee 统一+连接 (7) → 工作台 (8)
→ 业务流程 (9) → Skill/MCP 领域 (10) → 自改进 (11) → 多行业 (12)。
核心原则: 每 Sprint 必须产出"真实可演示的生产结果", 禁止纯工程扩张。
```

---

# 附录 A — 模块级细节（全部 25 个 Core 模块 + 扩展）

```
模块           行数    类数   职责
agents         593    16    Agent/Skill Registry (简单执行者模型)
assignment     665    12    任务分配 (AgentAllocator)
change         1058   9     变更分析 (Files/Insertions/Deletions/Modules)
changeflow     1081   10    变更驱动工作流 (触发器)
cli            6418   2     CLI (91 命令函数式)
dashboard      2455   21    Dashboard 16 视图
demo           440    3     markpad 演示
events         1097   6     事件溯源 (158 事件, 28 前缀)
execution      497    11    执行派发 (Runtime Adapter)
git            736    7     git 操作 (可选能力)
intelligence   3549   40    Decision/Recommendation/Experience/Risk
metrics        1002   18    质量指标 (first_attempt_success 等)
orchestration  622    6     编排
product        4063   34    产品链路 (Idea→PRD→Approval→UI→Task, 501 测试)
project        336    7     project.yaml
providers      2992   28    Provider 管理/选择/成本 (Core 层)
recovery       811    11    checkpoint 恢复
runtime        599    13    Runtime 管理
runtimes       531    9     Runtime 适配
tasks          216    6     任务模型 (最小)
understanding  699    8     项目理解 (阶段判断/技术栈)
validation     566    4     L1-L4 验证
workflows      1031   18    Workflow 引擎 + 4 技术模板
workspace      679    11    workspace init

扩展:
  factory-exec 12353 行 (ranking 2061 最大 / context 971 / repo_intelligence 958
    / experience_ctx 923 / progressive 837 / developer 694 / candidate 641
    / agent_runtime 607 / capability 578 / repo_index 528 / cli 485 / budget 476
    / operations 437 / evaluator 429 ...)
  factory-org 2081 行 (models/store/registry/lifecycle/authority/knowledge/templates/cli)
```

# 附录 B — CLI 命令全景（91 命令, 24 组）

```
product 17 (最大: idea/analyze/decide/approve/design/architecture/plan/task...)
org 7 (company/hire/employee/role/authority/knowledge...)  provider 7  change 7
exec 6  agent 5  runtime 5  workflow 4  intelligence 4  task 4
git 3  execution 3  checkpoint 2  console 2  skill 2  project 2  workspace 2
dashboard 1  demo 1  event 1  metrics 1  recover 1  status 1  understand 1  validate 1  init 1

观察: product 命令最多 (17) → 产品链路是 CLI 最重投入
     exec 6 (run/status/approval/providers/...) → 执行层 CLI 薄 (引擎在 Python API)
```

# 附录 C — 事件体系全景（158 事件, 28 前缀）

```
ORG 21 (最大: company/employee/role 生命周期)  PRODUCT 15  INTELLIGENCE 14
APPROVAL 11  PROVIDER 9  CHANGE 7  WORKFLOW 7  TASK 6  RUNTIME 6
AGENT 5  ASSIGNMENT 5  EXECUTION 5  GIT 5  ORCHESTRATION 5  WORKSPACE 5
VALIDATION 5  UNDERSTANDING 4  CONSOLE 3  IDEA 3  PROJECT 3  RECOVERY 3  SKILL 3  SYSTEM 3
CHECKPOINT 1  DASHBOARD 1  METRICS 1  SESSION 1  TOOL 1

观察: 组织事件最多 (org.*) → 组织层事件完备
     无 workflow.* 组织级事件 (workflow 7 是任务级)
     无 learning/improvement 事件前缀
```

# 附录 D — 测试全景（285 文件, 5493 测试）

```
exec 1019 (最大: 执行工程 29 文件)  providers 569  product 501  intelligence 509
change 196  org 192  console 172  dashboard 165  changeflow 144  assignment 134
factory_runtime 130  recovery 122  metrics 113  agents 112  execution 100
runtimes 93  orchestration 73  events 69  cli 38  benchmark 36  project 34
tasks 22  demo 21

观察: 工程测试占比高 (exec+providers+intelligence+product ≈ 40%)
     无真实 LLM 集成测试 (全是 mock)
     tests/exec 29 文件 (Sprint 4/5 从 6 文件暴增)
```

# 附录 E — Git 历史分析

```
147 commits, 全部 2026-08 (一个月内建成)
类型: docs 61 (41%) / test 45 (31%) / feat 28 (19%) / fix 13 (9%)
→ 文档+测试占 72%, 代码实现 19% — 蓝图驱动/测试驱动特征明显
阶段: 12B-13A (验证) → 14 (开源) → 15 (Runtime/Desktop) → 16A (org)
      → Phase A (exec) → Sprint 3/4/5 (Context/Execution 工程)
```

# 附录 F — 文档全清单（185 文件）

```
docs 顶层 41: vision/roadmap/lifecycle-model(12 阶段)/architecture/design-principles/
  core-boundary/extension-model/agent-model/skill-model/memory-model/
  workflow-model/validation-model/intelligence-layer-model/decision-intelligence-model/
  recommendation-engine-model/experience-learning-model/provider-*-model/
  human-console-*-model/configuration-model/capability-architecture/
  business-positioning/use-cases/demo-*/feedback-model/quality-report/...
architecture 32 (16A-20 设计 + 近期审计 4: strategic/alignment/current-state/reality)
validation 15 (product-proof/sprint 4-5/benchmark)
adr 35 (ADR-0001 起, 决策记录)
audit 1 (本报告)
roadmap (phase15-21 + 新规划)
观察: 设计文档 22+ 份远超实现文档 → 蓝图驱动; 近期审计文档 4 份 (08-08 密集产出)
```

# 附录 G — 空目录/残留清单（边角料）

```
11 个顶层空目录 (脚手架占位, 0 文件):
  agents/ cli/ dashboard/ knowledge/ mcp/ runtimes/ skills/ src/ validation/ workflows/
残留:
  $SMOKE_ROOT/ (7 文件, 历史误提交残留)
  build/factory_runtime_bundle + dist/factory-runtime-bundle (构建产物, gitignore)
  factory-core/ai_software_factory.egg-info (打包残留)
  .ruff_cache/.pytest_cache (缓存)
```

# 附录 H — 执行链路真实细节

```
真实 LLM 支持: exec/providers/anthropic.py + openai.py (2 真实适配器)
  Core providers 层有 registry/selector/costs/feedback (管理未接线到 exec 执行)
Provider 可替换已验证: openai-adapter → DeepSeek 端点 (零架构改动)
真实调用现状: DeepSeek 25/27 空响应 (reasoning 耗尽) / Ollama 本地未跑
本地模型: qwen3:8b 已确认 8GB 内存可行 (未拉取)
```

# 附录 I — 数据模型完整清单（核心 Pydantic）

```
org: Company/Department/Role/Employee/Authority/KnowledgeItem
exec: ExecutionRequest/ExecutionResult/ExecutionCandidate/ExecutionRun/
      EvaluationResult/CandidateScore/ContextCandidate/AssembledContext/
      StructuredCodeOperation/FileChange/ModelCapability/BudgetPolicy/BudgetTrace/
      ProgressiveTrace/ContextExperienceRecord
core: Task/Workflow/WorkflowStep/WorkflowRun/Agent/Skill/EventType/
      ApprovalGate/ApprovalStatus/DecisionContext/DecisionResult/ExperienceRecord/
      RecommendationResult/RiskAssessment/ProjectConfig/ValidationResult/
      ExecutionRunOutcome/ChangeAnalysis
```

