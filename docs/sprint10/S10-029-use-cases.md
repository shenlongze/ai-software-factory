# S10-029 Task 2 — Core Use Cases

> 日期:2026-08-14 | Sprint: S10-029 Product Validation | 产品设计,未修改代码
> 目标:设计 10 个真实使用场景,验证产品价值

---

## 场景 1:创业者一句话创建产品

| 项 | 内容 |
|---|---|
| 用户 | 创业团队 CEO/CTO |
| 触发 | 在 AI Factory 输入一句话:"做一个记账 App" |
| 流程 | suggest(想法理解)→ 需求澄清 → project 创建 → workflow 启动(产品→UX→开发→测试→发布)|
| AI Factory 能力 | projects suggest/confirm + start_project_workflow(真实链路)|
| 价值 | 从想法到可运行原型,数小时内;全程可观测 |
| 现状 | ✅ 已实现(S10-023 真实执行链;MarkPad 验证过)|
| 缺口 | 前端执行触发 UI(当前 CLI/API)|

## 场景 2:企业代码库智能分析

| 项 | 内容 |
|---|---|
| 用户 | 企业 IT / AI 团队 |
| 触发 | 导入 git 仓库 → AI Factory 分析结构/语言/依赖 → 生成项目画像 |
| 流程 | project register → analyzer(结构/语言/依赖)→ RAG 索引(未来)→ 问答/检索 |
| AI Factory 能力 | Project Analyzer(S10-028 Task 005 设计)+ 未来 RAG |
| 价值 | 新员工/新 Agent 快速理解代码库;知识沉淀 |
| 现状 | ⚠️ repo_index/repo_intelligence 部分有(exec);RAG 未实现 |
| 缺口 | RAG Engine(S10-028 已设计)|

## 场景 3:自动开发 Feature

| 项 | 内容 |
|---|---|
| 用户 | 创业团队 / 开发者 |
| 触发 | 在 backlog 建 task → 指派 Agent → AI 自动开发 |
| 流程 | task 创建 → Agent 执行(规划→编码→测试)→ 审批门 → 应用 patch |
| AI Factory 能力 | AgentExecutor.execute_task + DeveloperAgent + execution.approved 审批门 |
| 价值 | 重复开发自动化;人工只做审批;全程审计 |
| 现状 | ✅ 已实现(S10-023 真实执行;审批门)|
| 缺口 | UI 执行触发;backlog↔exec Task 单系统统一 |

## 场景 4:多模型成本优化

| 项 | 内容 |
|---|---|
| 用户 | AI 团队 / 创业团队 |
| 触发 | 配置多 Provider(deepseek/openai/anthropic/ollama)→ Router 按任务类型选模型 |
| 流程 | providers.json 配置 → Router 五层链决策 → usage 统计 → 成本分析 |
| AI Factory 能力 | ControlPlane + ModelCatalog + Router + usage 记录 |
| 价值 | 简单任务用便宜模型,复杂任务用强模型;成本下降 50-80% |
| 现状 | ✅ 已实现(S10-021~024;真实 usage $0.000278)|
| 缺口 | 智能路由(usage 反馈闭环,Phase 5);成本 Dashboard |

## 场景 5:企业 AI 治理

| 项 | 内容 |
|---|---|
| 用户 | 企业 IT / 合规 |
| 触发 | 规范 AI 员工权限;审计"谁让 AI 做了什么" |
| 流程 | Agent/Skill 权限配置 → 审批门 → 事件审计查询 → 合规报告 |
| AI Factory 能力 | 3 环权限链 + approval + events.db 审计 |
| 价值 | AI 执行可控可审计;满足合规要求 |
| 现状 | ⚠️ 部分(权限链/审批/审计有;策略引擎/审计 UI 缺)|
| 缺口 | Governance OS(策略引擎 + 审计浏览器)|

## 场景 6:AI 员工团队协作

| 项 | 内容 |
|---|---|
| 用户 | 创业团队 |
| 触发 | 建立虚拟团队:产品经理/后端/测试 Agent 协作完成项目 |
| 流程 | org 创建公司 → 雇佣员工(Agent)→ 分配任务 → 各 Agent 执行 → 审批 |
| AI Factory 能力 | org CLI(company/employee)+ agent 注册 + workflow |
| 价值 | 一人公司 = 多个 AI 员工;组织隐喻降低管理复杂度 |
| 现状 | ⚠️ 部分(org CLI 有;Multi Agent 编排未实现)|
| 缺口 | Multi Agent 协作(S10 路线 Phase 后)|

## 场景 7:本地 LLM 优先(隐私场景)

| 项 | 内容 |
|---|---|
| 用户 | 企业 IT / 隐私敏感团队 |
| 触发 | 配置 ollama 本地模型;代码不出本机 |
| 流程 | providers.json 配 ollama → Router L2/L4 选本地 → 执行 |
| AI Factory 能力 | ollama 已支持(无 key 语义)+ Router 策略 |
| 价值 | 敏感代码不出内网;零 API 成本 |
| 现状 | ✅ 已实现(ollama 支持)|
| 缺口 | 混合模式策略(开发用本地/生产用云端)需 project.yaml 配 |

## 场景 8:CI 质量门禁

| 项 | 内容 |
|---|---|
| 用户 | 创业团队 / AI 团队 |
| 触发 | CI 中跑 factory doctor --json;AI 产出质量不过门 → 阻塞 |
| 流程 | CI 调 doctor → 检查器评估 → exit code 门禁 |
| AI Factory 能力 | doctor --json + Evaluation(未来)+ Quality Gate |
| 价值 | AI 产出可验证;质量门禁自动化 |
| 现状 | ⚠️ doctor --json 有;Evaluation 未独立 |
| 缺口 | Evaluation Platform + CI 集成模板 |

## 场景 9:团队知识库(项目级 RAG)

| 项 | 内容 |
|---|---|
| 用户 | 创业团队 / 企业 IT |
| 触发 | 导入项目 → 自动建索引 → 团队成员问答("这个模块怎么改")|
| 流程 | project import → RAG index → query API / UI 问答 |
| AI Factory 能力 | RAG Engine(S10-028 Task 005 设计)|
| 价值 | 团队知识沉淀;新成员快速上手;AI 上下文增强 |
| 现状 | ❌ 未实现(设计完成)|
| 缺口 | RAG Engine 实现(Managed 先行)|

## 场景 10:多 Agent 竞标/评估

| 项 | 内容 |
|---|---|
| 用户 | AI 团队 |
| 触发 | 同一任务交给多个 Agent/模型 → 评估选择最优产出 |
| 流程 | 多 Run 执行(candidate)→ Evaluator 打分 → 选择/人工审批 |
| AI Factory 能力 | execution_strategy(多 Run)+ candidate/evaluator + approval |
| 价值 | 产出质量可比较;选择可解释;防单点失败 |
| 现状 | ⚠️ 部分(execution_strategy/candidate 已有)|
| 缺口 | Evaluation Platform 独立化 + 前端展示 |

## 场景矩阵总结

| # | 场景 | 画像 | 现状 | 价值 | 优先级 |
|---|---|---|---|---|---|
| 1 | 一句话建产品 | 创业 | ✅ 已实现 | 高(差异化) | 1 |
| 2 | 代码库分析 | 企业/AI | ⚠️ RAG 缺 | 高 | 5 |
| 3 | 自动开发 feature | 创业/开发 | ✅ 已实现 | 高(核心) | 2 |
| 4 | 多模型成本优化 | AI/创业 | ✅ 已实现 | 高 | 3 |
| 5 | 企业 AI 治理 | 企业 | ⚠️ 部分 | 高(变现) | 4 |
| 6 | AI 员工协作 | 创业 | ⚠️ MultiAgent 缺 | 中高 | 6 |
| 7 | 本地 LLM 优先 | 企业 | ✅ 已实现 | 中高 | 7 |
| 8 | CI 质量门禁 | 创业/AI | ⚠️ Eval 缺 | 中 | 8 |
| 9 | 团队知识库 RAG | 创业/企业 | ❌ 未实现 | 中 | 9 |
| 10 | 多 Agent 竞标 | AI | ⚠️ 部分 | 中 | 10 |

**关键洞察**:10 个场景中 5 个已可演示(1/3/4/7 完全,5 部分)——产品已有真实价值基础;缺口集中在 RAG/Evaluation/Governance 强化(与 S10-028 排序一致)。

---

> Task 2 完毕 | 10 核心场景设计完成 | 5 个场景当前即可演示
