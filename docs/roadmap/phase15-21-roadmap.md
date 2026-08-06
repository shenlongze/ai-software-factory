# AI Software Factory — Roadmap Phase 15-21

> 日期: 2026-08-07 | 状态: 已确认 (用户授权)
> 前置: Phase 1-14B 完成 (v1.0.0-rc1 已发布, 4111 pytest + 92 Vitest, Core 冻结, 35 ADR, 137 EventType)
> 定位: AI Software Factory 不是 AI Code Generator — 是安全/可控/透明/可扩展的 Multi-Agent AI Production Platform

## 0. 产品目标 (Phase 15-21 总览)

```
Phase 15  产品化      普通用户安装即用 (Runtime Manager + Desktop Shell + Installer)
Phase 16  Agent 生态  Factory = 多 Agent 管理平台 (Provider/Agent/Skill/MCP Registry)
Phase 17  真实执行    Task → Agent 执行 → Code Change → Test → Review → Approval → Merge
Phase 18  安全治理    企业级安全 (Permission/Policy/Risk/Audit/Secret)
Phase 19  多 Agent 协作 AI 团队 (Product/Architect/Developer/Tester/Security/Deploy)
Phase 20  行业模板    垂直工厂 (Software/Data/E-commerce/Content/Office)
Phase 21  商业化     用户系统/Team/Billing/Marketplace/Cloud (最后)
```

## 1. 设计原则 (贯穿所有 Phase)

```
1. Core 冻结: 任何新能力必须 Extension 化 (独立目录/数据空间/测试/Removal Isolation)
2. 不绑定 LLM/Agent: Provider Registry 抽象, 支持 OpenAI/Anthropic/DeepSeek/Qwen/Kimi/Codex/Claude/Hermes/OpenClaw 等
3. 不替代 Human: AI 分析/推荐/执行; Human 授权/批准/负责 (Approval Gate 复用 9c)
4. Agent 行为可见: 做了什么/为什么/进度/哪个 Agent/Token/成本/结果 — 全部 Event + Audit
5. 执行安全: 可暂停/可恢复/可审计 (sandbox/trace/audit)
```

---

## Phase 15 — Product Runtime & Desktop Edition

### 产品目标

```
git clone + 开发环境 → 下载安装包 → 启动 → 使用
新用户无需源码即可运行
```

### 架构影响分析

```
- 新增 Extension: factory-runtime/ (Runtime Manager)
- Console Web UI 复用 (11A/11B 已有): Desktop Shell 内嵌或独立窗口
- Core 零修改 (runtime 是启动器, 非引擎)
- 数据目录: 用户级 (~/.factory 或平台规范目录) vs 项目级 (.factory/) 并存
```

### 模块规划

```
factory-runtime/
├── 15A launcher.py      启动 Core CLI + Console (uvicorn) + 生命周期管理
├── 15A config.py        配置管理 (合并默认/用户/项目三层)
├── 15A datadir.py       数据目录管理 (迁移/备份/隔离)
├── 15A logging.py       日志管理 (轮转/级别/路径)
├── 15A updater.py       更新管理 (版本检查/更新预案 — 不实现自动升级)
├── 15B desktop/         Tauri Shell (Rust 壳 + 内嵌 Web UI)
└── 15C installer/       打包 (Windows installer/macOS dmg/Linux package)
```

### 数据流

```
用户 → Desktop Shell → factory-runtime → factory CLI (Core) + Console API (11A)
                                             ↓
                                       .factory/ 数据目录
```

### 安全边界

```
- Runtime 只做启动/停止/日志, 不触碰业务数据写路径
- 数据目录权限: 用户私有
- 更新: 手动确认 (不自动执行未知代码)
```

### 依赖关系

```
15A 依赖: 11A/11B (Console), 现有 CLI
15B 依赖: 15A (后端), node build 产物 (frontend dist)
15C 依赖: 15B (打包目标)
```

### 开发顺序

```
15A Runtime Manager → 15B Desktop Shell (Tauri 技术评估先行) → 15C Installer
```

### 验收标准

```
- 新环境: 安装包 → 启动 → demo markpad 可跑 (无需源码)
- 15A: runtime start/stop/status/logs CLI + 数据目录迁移测试
- 15B: Tauri 壳打包成功 (至少 1 平台), 内嵌 Console UI 可用
- 15C: 3 平台产物 (至少 macOS dmg 实机验证; Windows/Linux CI 或交叉)
- 测试: 新增 ≥80, pytest 4111+ 不回归
```

---

## Phase 16 — Agent Ecosystem

### 产品目标

```
Factory = 多 Agent 管理平台: 不实现 Agent 能力, 管理 Agent
Provider Registry (OpenAI/Anthropic/DeepSeek/Qwen/Kimi + 配置: model/endpoint/capability/cost/rate limit/security)
Agent Registry (Developer/Architect/Tester/Reviewer/Data)
Skill Registry (flutter-development/java-backend/excel-analysis/content-generation)
MCP Manager (filesystem/github/database/browser/docker)
```

### 架构影响分析

```
- 扩展 providers/ (8A/8B 已有 Registry + selector + capability/cost/usage): 增加具体 Provider 配置模式 + rate limit
- 扩展 agents/ + skills/ (已有基础): Registry 管理化 (声明式注册 + 测试)
- 新增 factory-mcp/ 或 mcp/ 填充: MCP Manager (占位目录 1 期已留)
- Core 零修改
```

### 模块规划

```
providers/registry 增强   Provider 配置 (model/endpoint/capability/cost/rate_limit/security)
factory-core/agents 增强  Agent Registry (注册/查询/分配)
factory-core/skills 增强  Skill Registry (声明式 capability.yaml)
factory-mcp/             MCP Manager (连接 filesystem/github/db/browser/docker)
```

### 数据流

```
TaskRequirement → Agent Registry (角色匹配) → Skill Registry (能力匹配)
                → Provider Registry (10A-3 推荐: Capability/Cost/Performance/Experience)
                → MCP (外部工具)
```

### 安全边界

```
- Provider endpoint 凭证: Secret Management (18 前置最小: 环境变量/文件权限, 禁明文入库)
- MCP 工具权限: 默认 deny (白名单)
- Registry 内容: 声明式校验 (capability.yaml 结构验证)
```

### 依赖关系

```
16 依赖: 8A-10A (Provider/Intelligence), 7 (Understanding)
16 前置 15 (Runtime 提供数据目录/配置统一)
16 的 Secret 最小处理前置 18 (或 16 内最小实现)
```

### 开发顺序

```
16A Provider 配置扩展 (rate limit/security) → 16B Agent/Skill Registry 管理化 → 16C MCP Manager
```

### 验收标准

```
- Provider: 5 家配置模式 (OpenAI/Anthropic/DeepSeek/Qwen/Kimi) 可注册/查询/测试
- Agent Registry: 5 角色注册/分配 (复用 assignment 4B-3)
- Skill Registry: 4 示例 skill 声明式注册
- MCP: filesystem + github 2 个适配器 (mock 测试)
- 测试: 新增 ≥120, 零回归
```

---

## Phase 17 — Real Execution Layer

### 产品目标

```
填补缺口: Task 创建后人工开发 → Task → Agent Execution → Code Change → Test → Review → Approval → Merge
新增 factory-execution: executor/sandbox/workspace/patch/validator
Agent 不直接修改用户环境: 全部 sandbox/trace/audit
```

### 架构影响分析

```
- 新增 Extension: factory-execution/ (独立执行空间)
- 复用: tasks (创建), execution (既有编排), git/change (6C/6D/6E), validation, workflows
- Agent 输出 = Patch (diff), 经 validator 校验 → 人工/策略批准 → merge
- Core 零修改 (execution 编排已有, 新增的是 agent 真实执行后端)
```

### 模块规划

```
factory-execution/
├── executor.py       Agent 执行器 (调 Agent CLI/API, 注入 workspace 快照)
├── sandbox.py        沙箱 (临时工作副本/容器/文件系统隔离)
├── workspace.py      工作区管理 (源副本 + 变更追踪)
├── patch.py          Patch 生成/应用 (git diff 格式, 与 6C 对齐)
└── validator.py      验证器 (语法/测试/变更范围检查, 与 validation L1-L4 对齐)
```

### 数据流

```
Task → factory-execution.executor → sandbox (工作副本)
     → Agent 执行 → patch.py (diff) → validator (测试/范围)
     → Review (Reviewer Agent 或人工) → Approval (9c) → Merge (git 6C)
全链: 事件 + trace (每步记录 agent/token/成本/耗时)
```

### 安全边界

```
- 沙箱: Agent 无网络默认? (配置化), 仅工作副本写权限
- 禁止: production/secret/危险操作 (18 Permission 强约束; 17 最小: sandbox 边界)
- Patch 白名单: 只允许声明文件范围 (Protocol v1.1 Allowed/Files/Forbidden)
- 可暂停/可恢复 (checkpoint 4C-3 复用)
```

### 依赖关系

```
17 依赖: 16 (Agent 选择), 6C/6D/6E (git/change), 9c (Approval), 4C (execution/recovery)
17 安全基线依赖 18 的 Permission 模型 (或 17 内最小沙箱先做)
```

### 开发顺序

```
17A sandbox+workspace (隔离执行) → 17B executor+patch (真实执行) → 17C validator+review 链
```

### 验收标准

```
- sandbox: 执行不污染用户环境 (字节级验证)
- executor: 1 真实 Agent (codex/hermes) 完成小任务 (冒烟) + mock 全链测试
- patch: 生成/应用/冲突处理
- validator: 失败拦截 (测试不过 → 不 merge)
- 全链: Task→...→Merge 事件完整 (agent/token/成本审计)
- 测试: 新增 ≥150, 零回归
```

---

## Phase 18 — Security & Governance

### 产品目标

```
企业级安全模型: Permission/Policy/Risk Engine/Audit/Secret Management
Agent 权限: read source / modify workspace / run test 允许; production/secret/危险 禁止
Risk Low/Medium/High: High → 必须 Approval
```

### 架构影响分析

```
- 新增 Extension: factory-security/
- 复用: 10A-2 Risk R1-R5 (扩展策略化), 9c Approval (强制门), 137 EventType (Audit 扩展)
- Policy: 声明式 (policy.yaml), 默认 deny
- Core 零修改
```

### 模块规划

```
factory-security/
├── permission.py   权限模型 (Agent/操作/资源 矩阵)
├── policy.py       策略引擎 (声明式 policy.yaml, 默认 deny)
├── risk.py         Risk Engine (扩展 10A-2 R1-R5 + 执行风险)
├── audit.py        Audit (只追加审计日志, Event 唯一事实源)
└── secrets.py      Secret Management (环境变量/Keychain/加密文件, 禁明文)
```

### 数据流

```
Agent 操作请求 → Policy (允许/拒绝) → Risk Engine (low/medium/high)
   → high → Approval (9c 强制) → Audit 记录
Secret: 调用时注入, 不落库/不打印
```

### 安全边界

```
- 默认 deny: 未声明权限 = 拒绝
- 危险操作: production access/secret access/破坏性命令 → 硬禁止或 high+approval
- Audit 只追加 (append-only)
- Secret: 禁明文存储/日志/事件 payload
```

### 依赖关系

```
18 依赖: 17 (执行安全落地), 10A-2 (Risk), 9c (Approval)
18 前置 17 的安全基线 (或并行: 17A 后 18A)
```

### 开发顺序

```
18A Permission+Policy (默认 deny) → 18B Risk Engine (执行风险) → 18C Audit+Secret
```

### 验收标准

```
- Permission: 矩阵校验 (允许/禁止用例)
- Policy: policy.yaml 声明式 + 默认 deny 验证
- Risk: 执行风险分级 (高危 → approval 强制)
- Audit: 只追加验证 + 全链审计查询
- Secret: 无明文扫描测试 (禁 token/密码入库)
- 测试: 新增 ≥120, 零回归
```

---

## Phase 19 — Multi-Agent Collaboration

### 产品目标

```
AI 团队协作: Product/Architect/Developer/Tester/Security/Deploy Agent
协作流: 需求→规划→设计→开发→测试→安全检查→Human Approval
```

### 架构影响分析

```
- 扩展 agents/ (角色注册已有) + orchestration (4C 已有) 协作编排
- 新协作流程: 复用 9d Lifecycle (阶段链) + 4B-3 Assignment (角色分配)
- 新增协作协议: Agent 间消息 (事件驱动) — 不直接互调
- Core 零修改
```

### 模块规划

```
factory-core/agents 扩展    6 角色定义 (Product/Architect/Developer/Tester/Security/Deploy)
factory-core/orchestration 扩展  协作编排 (阶段链 + 角色接力)
factory-collab/ (可选)      Agent 间消息/上下文传递 (事件命名空间 collab.*)
```

### 数据流

```
需求(Idea) → Product Agent → Architect Agent → Developer Agent (17 执行)
→ Tester Agent (验证) → Security Agent (18 检查) → Human Approval → Deploy Agent
每步: Artifact + Event + 上下文传递 (source_events 链)
```

### 安全边界

```
- Agent 间无直接信任: 事件传递, 权限独立校验 (18)
- 上下文: 最小传递 (只传需要的 Artifact)
- 每角色权限边界 (Developer 无 production, Security 只读+审计)
```

### 依赖关系

```
19 依赖: 16 (Agent 生态), 17 (执行), 18 (安全)
19 前置: 16-18 完成 (协作 = 生态 + 执行 + 安全的组合)
```

### 开发顺序

```
19A 角色定义+协作编排 → 19B 上下文传递 (collab.* 事件) → 19C 全链演练
```

### 验收标准

```
- 6 角色注册 + 阶段链编排
- 完整协作链: 需求→...→Deploy 事件完整 (mock agent)
- 上下文传递: source_events 链可追溯
- 权限边界: 角色越权拒绝
- 测试: 新增 ≥130, 零回归
```

---

## Phase 20 — Industry Factory Templates

### 产品目标

```
垂直行业模板 (声明式, capability.yaml):
Software (Java/Flutter/Web/Backend) / Data (Excel/SQL/BI)
E-commerce (商品分析/运营/客服) / Content (自媒体/文案/图片/视频) / Office (自动化办公/Excel Macro)
```

### 架构影响分析

```
- 纯声明式扩展: templates/ 目录 + capability.yaml (capability-architecture.md 已设计)
- 复用: 9d Stage Registry (多生命周期类型), 16 Registry, 17 执行, 19 协作
- 不新增引擎: 模板 = 预配置的组合
- Core 零修改
```

### 模块规划

```
templates/
├── software/    Java/Flutter/Web/Backend 工厂模板 (生命周期+角色+Skill 组合)
├── data/        Excel/SQL/BI
├── ecommerce/   商品分析/运营/客服
├── content/     自媒体/文案/图片/视频
└── office/      自动化办公/Excel Macro
每模板: lifecycle.yaml + roles.yaml + skills.yaml + policies.yaml
```

### 数据流

```
用户选模板 → 实例化 (生命周期+角色+Skill 装配) → 项目运行 (19 协作链)
```

### 安全边界

```
- 模板默认最小权限 (policy.yaml 随模板)
- 模板校验: 声明式结构验证 (禁恶意模板)
```

### 依赖关系

```
20 依赖: 16/17/18/19 全部 (模板 = 组合)
20 前置: Phase 19 完成
```

### 开发顺序

```
20A Software Factory 模板 (2 个: Java/Flutter) → 20B Data + Content → 20C E-commerce + Office
```

### 验收标准

```
- Software 模板: Java/Flutter 可实例化运行 (demo 级)
- 模板校验: 结构验证 + 恶意模板拒绝
- 测试: 新增 ≥100 (模板结构/实例化/校验), 零回归
```

---

## Phase 21 — Commercial Platform (最后)

### 产品目标

```
用户系统/Team/Workspace/Billing/Marketplace/Cloud
```

### 架构影响分析

```
- 商业系统独立 (factory-platform/ 或 SaaS 服务), 不污染 Core/Extension
- 复用: 14A/14B feedback-model, 11A Console (多租户扩展)
- 开源 Core 保持 (Apache-2.0), 商业层增值
```

### 模块规划 (设计先行, 实现按商业模式确认)

```
factory-platform/ (商业扩展, 独立部署)
├── users.py       用户系统 (认证/授权)
├── teams.py       Team/Workspace 多租户
├── billing.py     Billing (支付 — 不实现具体支付商)
├── marketplace.py Marketplace (模板/Agent/Skill 市场)
└── cloud.py       Cloud 部署 (托管)
```

### 安全边界

```
- 商业层与开源 Core 隔离 (数据/进程/部署)
- 多租户数据隔离
- 支付合规 (PCI 外包 — 不接触卡数据)
```

### 依赖关系

```
21 依赖: 1-20 全部 + 商业模式确认
21 前置: v1.0 正式版 + 社区验证 (14B 反馈)
```

### 开发顺序

```
21A 用户+Team (设计) → 21B Billing+Marketplace (设计) → 21C Cloud (评估)
(每步需商业模式确认, 三挡板)
```

### 验收标准

```
- 用户系统: 注册/登录/授权 (设计评审通过后实现)
- 多租户: 数据隔离验证
- 无支付集成 (Billing 接口预留)
- 商业化前: 商业模式文档 + 用户确认
```

---

## 2. 全局依赖图

```
Phase 15 (Runtime/Desktop) ← 11A/11B Console
Phase 16 (Agent 生态)     ← 8A-10A, 15
Phase 17 (真实执行)       ← 16, 6C/6D/6E, 9c, 4C
Phase 18 (安全治理)       ← 17, 10A-2, 9c
Phase 19 (多 Agent 协作)  ← 16+17+18
Phase 20 (行业模板)       ← 19
Phase 21 (商业化)         ← 全部 + 商业模式确认
```

## 3. 开发顺序总览

```
15 → 16 → 17 → 18 → 19 → 20 → 21
(18 可在 17A 后并行启动安全基线; 21 每步需商业模式确认)
每 Phase: 架构评审 → 确认 → 开发 (Extension 化) → 测试 → 验证 → 报告
```

## 4. 全局验收标准 (每 Phase 共性)

```
- Core 零修改 (git diff 验证)
- Extension 独立 (Removal Isolation 测试)
- Event 唯一事实源 (每 Phase 新事件进 137+)
- 测试: 每 Phase 新增 ≥80-150, 既有全绿
- 安全: 默认 deny + 高危 approval + Audit
- 可见性: 每 Agent 行为 = 事件 (做了什么/为什么/进度/Token/成本/结果)
```
