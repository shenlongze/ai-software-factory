# AI Software Factory — 应用场景 (Use Cases)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 状态: 与实际能力一致 (Phase 1–11, 4090 pytest)
> 关联: [README](../README.md) · [vision.md](./vision.md) · [lifecycle-model.md](./lifecycle-model.md) · [design-principles.md](./design-principles.md)
>
> 本文档描述 5 类典型用户如何使用 AI Software Factory。每个场景包含:
> **痛点** (为什么需要它) / **Factory 如何解决** (对应哪项实际能力) / **示例流程** (真实 CLI 命令)。

---

## 场景 1 — 个人开发者: 一个人拥有 AI 软件团队

### 痛点

一个人要同时扮演产品经理、架构师、开发、测试。用 AI 助手写代码看似高效, 但:
- 每次对话从零开始, 项目上下文、之前定下的约定全部丢失;
- 没有验收机制, Agent 说"完成了"就是完成了, 改完代码不知道有没有破坏别的东西;
- 多个小项目并行时, 全靠脑子记, 极易混乱;
- 一次中断 (断网、超时、手滑) 就得从头再来。

### Factory 如何解决

- **角色化 Agent + 自动编排**: 注册 `product-manager` / `backend-developer` / `test-engineer` 等角色 Agent, 声明式工作流 `feature-delivery` 自动完成 架构 → 开发 → 测试 → 独立验收 的完整链路 (Phase 3–4)
- **独立验证**: L1–L4 四层验证引擎判定"是否真的完成", 不信任自报告; 验收标准 (acceptance) 在任务定义时先行写入 (Phase 3A/6D)
- **断点续跑**: checkpoint + 事件回放, 截断/失败从最近停靠点续跑, 零丢失 (Phase 4C-3)
- **一切可观测**: 20 视图 Dashboard + 事件时间线, 随时知道每个任务/Agent 在做什么 (Phase 4C-4 起)

### 示例流程

```bash
factory init                                  # 初始化工厂
factory agent add --id pm-1 --role product-manager --skills architecture
factory agent add --id dev-1 --role backend-developer --skills development,python
factory agent add --id test-1 --role test-engineer --skills testing,validation
factory runtime add --id echo --type mock     # 或 hermes 真实执行
factory task create --id T-001 --title "实现登录页" --acceptance "登录流程可用, 测试通过"
factory workflow run T-001 --auto             # 全自动: 匹配 Agent → 执行 → 验证
factory validate T-001                        # 独立验收 (L1–L4)
factory dashboard --view all                  # 观察工厂状态
```

> 一个人, 一套平台, 一支"永不失忆、每次必验"的 AI 团队。

---

## 场景 2 — 创业团队: 快速验证产品想法

### 痛点

从想法到可验证的产品, 链路漫长: 想法只在脑子里 → 需求说不清楚 → 文档没人写 → 开发出来才发现方向错了。更关键的是:
- 产品决策 (做什么、不做什么、值不值得做) 没有记录、没有把关;
- 需求没有验收标准, 开发完成与否全凭感觉;
- 试错成本高: 方向错了, 前期的上下文、决策、文档全部作废重来。

### Factory 如何解决

- **Product Intelligence** (Phase 9): `Idea → Research → PRD → [人工批准] → UI/架构 → 任务拆解` 的产品化链路, 想法被形式化为带验收标准的结构化 PRD
- **人工决策闸口** (Phase 9c): 产品决策的最终裁决权在人 —— PRD、UI、架构作为候选产物提交, `approval` 状态机批准/驳回 (5 态可逆, 产物版本化), 未经批准的产物不可能进入开发
- **任意阶段接入**: 项目带任何已有状态进入 (只有一句话想法 / 已写的 PRD / 原型代码), 从当前节点继续, 不重建 (原则⑨)
- **证据入事件库**: 调研结论、决策理由、批准记录全部落事件流, 事后可审计"当初为什么这么做"

### 示例流程

```bash
factory product idea create --title "宠物社交 App" --description "让养宠人交换经验"
factory product workflow start PI-001       # 启动产品生命周期 (Idea→Research→PRD→Architecture→Task Plan)
factory product generate --type research PI-001   # 调研候选产物
factory product generate --type prd PI-001        # PRD 候选产物, 自动挂起等待批准
factory product approval list --pending      # 查看待审批项 (含证据与推荐理由)
factory product approval decide APR-001 approve
factory product lifecycle advance PI-001    # 批准后推进到下一阶段
factory task create --id T-010 --title "实现首页信息流"   # 拆解出的任务进入开发
factory workflow run T-010 --auto
```

> 想法 → 可验证 MVP 的全链路可追溯, 每个产品决策都有人拍板、有据可查。

---

## 场景 3 — 企业研发部门: 管理多个 AI Agent

### 痛点

研发部门引入多个 AI Agent 并行干活后, 出现新的管理问题:
- **不可控**: 不知道每个 Agent 正在干什么、卡在哪、质量如何;
- **不可比**: 不同模型/Agent 能力参差, 选谁全凭口碑, 成本与性能没有数据;
- **不可审计**: 出了事故查不到"谁在什么时间做了什么、依据是什么";
- **无积累**: 团队踩过的坑不沉淀, 每个新项目重蹈覆辙。

### Factory 如何解决

- **可观测**: 事件流是唯一事实源 (含只读审计事件), 20 视图 Dashboard + 六域指标 (first_attempt_success_rate / path_errors / human_intervention), 多项目维度对比 (Phase 6B)
- **能力评估**: Provider 能力矩阵 (capability → 质量分 + evidence)、成本模型 (token/request/time/free)、性能聚合 (声明 vs 实测), 缺失能力视为 0 分 —— 无能力证据不推荐 (Phase 8B)
- **推荐引擎**: 按 Capability/Cost/Performance/Experience 四因素为任务推荐最适执行资源, 带逐条解释与风险等级; 高风险推荐必须人工审批 (Phase 10A)
- **经验沉淀**: 每个 Agent/Provider/工作流的成功与失败都记录为经验, 半衰期衰减, 反哺未来选择 (Phase 10A-4)
- **人类审核台**: Human Console Web UI (普通/专业双模式) —— 项目状态、待审批项、推荐理由、成本汇总一屏可见 (Phase 11)

### 示例流程

```bash
factory agent list --json                    # 全部 Agent 状态
factory agent assignments --agent dev-1      # 单个 Agent 的任务负载
factory dashboard --view agents_utilization  # Agent 利用率
factory metrics --project myproject          # 项目维度质量指标
factory provider stats                       # 各 Provider 性能聚合 (实测 vs 声明)
factory provider compare a b                 # 能力/成本对比
factory intelligence recommend --task development --capability code,reasoning \
    --candidate a:0.9:0.8:0.7:0.6 --candidate b:0.6:0.6:0.8:0.5:agent   # 选谁? 附解释
factory console dashboard                    # 人类审核台总览 (七域)
```

> 让 AI Agent 像正式员工一样被管理: 有工位 (注册)、有工作量 (分配)、有绩效 (指标)、有档案 (经验)、有人审 (Console)。

---

## 场景 4 — 软件外包团队: 自动化项目生命周期

### 痛点

外包团队同时接多个项目, 每个项目状态不一、交付节奏紧:
- 多项目并行, 上下文互相串扰, 交付质量不稳定;
- 验收靠人肉, 交付"完成"与否说不清;
- 变更管理混乱: 客户改需求 → 改代码 → 不知道哪些提交对应哪个任务、是否验证过;
- 项目交接即失忆: 接手的 Agent/工程师要从零理解项目。

### Factory 如何解决

- **多项目工作区**: `workspace` 层挂载多个项目 (每个项目独立仓库、独立数据空间、独立 runtime 偏好), 项目间零串扰 (Phase 6A)
- **任意阶段接入**: `factory understand <repo>` 只读扫描任意存量仓库, 产出 Understanding Report (阶段/技术栈/缺失/风险/建议), 一键生成项目配置草稿 —— 接盘项目不再从零开始 (Phase 7)
- **变更驱动交付**: 提交即发布 —— `git commit` → 变更分析 → L4 验证 → 触发器规则 → 自动启动 release 工作流, 每个提交与任务自动关联, 全程证据链 (Phase 6C/6D/6E)
- **验收标准先行**: acceptance 写入任务定义, 成为 L1–L4 验证的输入, 交付质量可度量、可举证 (Phase 3A)
- **零写命令铁律**: 平台对仓库只读 (git status/diff/commits + 审计), 不会擅自改客户代码 (Phase 6C)

### 示例流程

```bash
factory workspace init --name client-a       # 新建客户工作区
factory project show client-a         # 查看项目技术栈/Agent/工作流映射
factory understand /path/to/repo      # 理解任意存量仓库 (只读)
factory task create --id T-201 --title "修复支付超时" --acceptance "超时重试通过, 无回归"
factory git status --project client-a        # 查看任务关联的仓库状态
factory change analyze T-201                 # 变更分析 (文件/插入/删除/模块)
factory change validate T-201                # L4 变更验证 (任务描述 vs 代码证据)
factory change triggers register --id TRIG-FEATURE-RELEASE --target-workflow release
                                             # 注册触发器 (规则: L4 PASS / commit.linked / required.files / runtime.pref)
factory change evaluate T-201                # 规则 PASS → 自动触发 release
factory change workflows T-201               # 查看完整变更流链
```

> 交付节奏从"人肉盯"变成"变更驱动": 改完 → 验证过 → 自动发布, 每个环节都有证据可交给客户。

---

## 场景 5 — AI Agent 平台基础设施: 承载异构 AI 能力

### 痛点

想要搭建/运营 AI Agent 平台的团队面对的问题是:
- 异构环境: Hermes、Codex、Claude、本地模型、各种 MCP 工具并存, 没有一个统一的管理面;
- 能力不可复用: Agent 与工具各自为政, 换一个模型就要动核心逻辑, 牵一发动全身;
- 无统一审计: 跨工具的执行过程无法追踪, 出了事故无法回溯;
- 无人工把关: 全自动化的 Agent 平台在关键决策点缺少人类审核能力。

### Factory 如何解决

- **统一抽象五层**: `Agent (角色) / Skill (能力) / MCP (工具) / Runtime (执行) / Provider (LLM)` 全部声明式注册, 上层编排只面向抽象 —— 换工具 = 改配置, 不是改流程 (原则③)
- **三区架构 (2026-08 冻结)**: Core (通用原语, 零领域依赖) / Extension (新能力一律声明式注册, 不修改 Core) / Human Layer (Approval Console) —— 新增一个 Runtime 或 Provider 不需要碰核心代码; 删除一个模块, 系统照常运行 (capability-architecture.md)
- **能力即积木**: 每个能力有明确输入/输出/能力描述/可发现/可组合/可替换, Factory 只负责 发现 → 注册 → 调度 → 审计 (docs/capability-architecture.md)
- **事件唯一事实源**: 所有执行、决策、审批落 append-only 事件流, 可回放重建状态 —— 平台级审计的基础 (原则①)
- **人工审核嵌入**: 任何高风险动作 (推荐、生成、切换) 经 Approval 状态机, 平台面向人类提供 Console 审核台 (Phase 9c/11)

### 示例流程

```bash
factory runtime add --id codex --type codex          # 声明式接入新 Runtime
factory skill add --id flutter-dev --category development --capabilities flutter
factory provider list                                # 统一目录 (Provider 以 catalog.json 声明式注册)
factory provider test --id claude-x                  # 连通性测试
factory runtime catalog list                         # 能力目录检索
factory intelligence recommend --task development --capability code \
    --candidate claude-x:0.9:0.8:0.7:0.6 --candidate hermes:0.7:0.9:0.6:0.8:agent \
    --quality 0.7                                    # 推荐 + 逐条解释; 高风险自动 requires_approval
factory product approval list --pending              # 高风险推荐 → 人工审批入口
factory event logs --workspace platform               # 全平台事件审计
```

> Factory 本身就可以作为 AI Agent 平台的操作系统: 底座提供注册、调度、审计、审核, 能力生态无限扩展。

---

## 场景速查

| 场景 | 核心诉求 | 对应能力 |
|:-----|:---------|:---------|
| 个人开发者 | 一个人拥有一支不遗忘、必验证的 AI 团队 | Agent/Workflow/Validation/Recovery/Dashboard (Phase 3–6) |
| 创业团队 | 想法快速形式化, 产品决策有人把关 | Product Intelligence + 人工批准闸口 (Phase 9) |
| 企业研发部门 | 多 Agent 可管理、可比、可审计、有沉淀 | 可观测 + Provider 评估 + 推荐引擎 + 经验 (Phase 8B/10A/11) |
| 外包团队 | 多项目并行, 变更驱动交付, 接盘不失忆 | Workspace + Understanding + Change Driven Workflow (Phase 6A/7/6E) |
| Agent 平台 | 异构能力统一管理, 零核心破坏, 平台级审计 | 统一抽象五层 + 三区架构 + 事件事实源 (Core/Extension/Human Layer) |
