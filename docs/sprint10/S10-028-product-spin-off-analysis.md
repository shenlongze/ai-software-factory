# S10-028 Task 004 — Product Spin-off Analysis

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 战略分析,未修改代码
> 目标:评估 5 个模块从 AI Factory 拆出的商业化可行性

---

## 1. AI Decision Router

| 维度 | 分析 |
|---|---|
| 市场需求 | **高** — 多模型选型是 2026 企业刚需;成本/能力/延迟权衡;可解释决策(source/reason/score)是差异化 |
| 技术成熟度 | **80%** — S10-024 五层链已实现;缺 usage 反馈闭环(智能路由) |
| 独立产品可能性 | **最高** — SDK/库 + 轻量服务;对接任意 OpenAI 兼容端点 |
| 从 AI Factory 拆出成本 | **低** — 拆包:llm_router + model_catalog + agent_policy;ModelChoice 提升共享类型 |
| 商业路径 | ① 开源社区版(洋葱最外层,获客)② 企业版(智能路由/多租户)③ 按调用量 SaaS |
| 时间线 | 3-6 个月可拆 |

**判定:首选拆分 — 市场大、完成度高、成本低。**

## 2. AI Governance OS

| 维度 | 分析 |
|---|---|
| 市场需求 | **中高** — 企业上 AI 最大顾虑是可控性/合规/审计;监管趋严 |
| 技术成熟度 | **50%** — 审批门/3 环权限/事件溯源已有;策略引擎/RBAC/审计 UI 缺 |
| 独立产品可能性 | **中高** — 治理层天然独立(不依赖具体 AI 能力) |
| 从 AI Factory 拆出成本 | **中** — org + events + approval;需补策略引擎 |
| 商业路径 | ① 与 Router 打包企业方案(决策+治理)② 合规审计服务 ③ 私有化部署 |
| 时间线 | 6-9 个月 |

**判定:战略第二 — 与 Router 互补,可打包;需先补策略引擎。**

## 3. Agent Workforce Platform

| 维度 | 分析 |
|---|---|
| 市场需求 | **中高** — "AI 员工管理"概念兴起;但 LangGraph/CrewAI 竞争激烈 |
| 技术成熟度 | **60%** — Agent 注册/Skill 绑定/执行链有;双模型债/UI 触发缺 |
| 独立产品可能性 | **中高** — 差异化在治理驱动(非编排) |
| 从 AI Factory 拆出成本 | **中高** — 需先解 Agent 双模型 + 装配下沉 exec |
| 商业路径 | ① Agent 管理 SaaS ② 企业内部 AI 员工平台 ③ 与母平台绑定 |
| 时间线 | 9-12 个月 |

**判定:中远期 — 竞争激烈,差异化依赖治理;先修技术债。**

## 4. Project RAG Platform

| 维度 | 分析 |
|---|---|
| 市场需求 | **中** — 知识库/RAG 市场大但竞争饱和(Notion/各家 RAG) |
| 技术成熟度 | **0%** — 未实现(仅 CLI 占位) |
| 独立产品可能性 | **中** — 差异化在"项目生命周期知识"(Idea→Artifact)而非通用 RAG |
| 从 AI Factory 拆出成本 | **高** — 需先实现基础 RAG + 向量库集成(Task 005 有设计) |
| 商业路径 | ① 企业知识引擎 ② 与 RAG 外部存储(Chroma/Qdrant)集成服务 |
| 时间线 | 12+ 个月 |

**判定:远期 — 先实现基础,差异化积累后再说。**

## 5. AI Evaluation Platform

| 维度 | 分析 |
|---|---|
| 市场需求 | **中** — AI 产出评估是工程刚需;但工具成熟(已有评测平台) |
| 技术成熟度 | **30%** — evaluator/candidate 散落 exec,无独立模块 |
| 独立产品可能性 | **中** — 差异化在"治理驱动的质量门"(审批+评估联动) |
| 从 AI Factory 拆出成本 | **中** — 整合 evaluator + validation 为独立模块 |
| 商业路径 | ① 质量门/评估 SaaS ② CI 集成 |
| 时间线 | 9-12 个月 |

**判定:中远期 — 与 Governance 联动有协同,单独市场竞争力一般。**

## 6. 综合对比

| 产品 | 市场 | 成熟度 | 拆出成本 | 商业路径清晰度 | 优先级 |
|---|---|---|---|---|---|
| AI Decision Router | 高 | 80% | 低 | 高 | **1** |
| AI Governance OS | 中高 | 50% | 中 | 高 | **2** |
| Agent Workforce | 中高 | 60% | 中高 | 中 | 3 |
| Evaluation Platform | 中 | 30% | 中 | 中 | 4 |
| Project RAG | 中 | 0% | 高 | 中 | 5 |

## 7. 商业路径总策略

```
Phase 1 (0-6 月): AI Decision Router 独立
  - 洋葱式开源最外层 (providers → router)
  - 社区版开源获客 → 企业版 (智能路由/多租户)
  - 独立成本最低, 验证"模块独立产品"模式

Phase 2 (6-12 月): Router + Governance 打包企业方案
  - 决策 + 治理 = "可控的 AI 执行层" (企业卖点)
  - 私有化部署 + 合规审计

Phase 3 (12 月+): 平台生态
  - Agent Workforce / Evaluation / RAG 基于 Extension Contract (Task 003) 生长
  - Marketplace (Task 001 #10) 承载第三方扩展

核心: 母平台是载体, 拆出的产品反哺母平台知名度 (洋葱战略)
```

## 8. 拆分风险与对策

| 风险 | 对策 |
|---|---|
| 拆分破坏母平台 | Extension Contract 冻结(Task 003);拆分 = 新实现同一契约,不动内核 |
| 拆出后维护双份 | 拆出模块与母平台共享契约/CI;洋葱式开源让社区维护开源版 |
| 时机过早(市场未验证) | Router 先行(成本最低);其他等生态成熟 |
| 品牌稀释 | 母平台 AI Software Factory 定位不变;拆出产品是"源自 AI Factory" |

---

> Task 004 完毕 | 商业化拆分分析完成 | 推荐: Router 先行 → Governance 打包 → 生态生长
