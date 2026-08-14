# S10-027 Task D — Product Module Roadmap

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 战略设计,未修改代码
> 目标:为未来独立产品化做准备(模块定位/市场价值/独立可能性/技术债)

---

## 1. LLM Router → AI Decision Router 产品

| 维度 | 分析 |
|---|---|
| 模块定位 | 五层决策链(User > Agent/Skill > Project > System > Fallback)输出 ModelChoice |
| 市场价值 | **高** — LLM 选型是 2026 年企业刚需:多模型成本/能力/延迟权衡;Router 输出可解释(source/reason/score)是差异化 |
| 独立产品可能性 | **高** — 可独立为:SDK 库 + CLI + 轻量服务;输入 task 特征输出模型选择;对接任意 OpenAI 兼容端点 |
| 当前技术债 | ① ModelChoice 定义在 model_catalog.py(应提升共享类型)② 依赖 ControlPlane/ModelCatalog 具体类(应接口化)③ usage 反馈数据未接(智能路由前置) |
| 独立化第一步 | 提取 llm_router + model_catalog + agent_policy 为独立包 `factory-router`(内部引用改接口) |

## 2. Governance → AI Governance OS

| 维度 | 分析 |
|---|---|
| 模块定位 | 审批门/权限链(Agent→Skill→Tool 3 环)/事件溯源审计/org 组织域 |
| 市场价值 | **中高** — 企业上 AI 最大顾虑是可控性;Governance OS = 审批/审计/合规层 |
| 独立产品可能性 | **中高** — AI 执行需要"人类审批门 + 全审计",可独立为策略引擎 + 审计服务 |
| 当前技术债 | ① 权限链硬编码 SYSTEM_AGENT_SKILLS(策略引擎缺失)② 审计浏览器缺失(有记录无查询 UI)③ 审批门与 Quality Gate 未连接 |
| 独立化第一步 | 策略引擎(RBAC 声明文件)→ 审计查询 API → 审计 UI(Phase 3 治理增强路线) |

## 3. Project RAG → Enterprise Knowledge Engine

| 维度 | 分析 |
|---|---|
| 模块定位 | 项目知识检索(当前仅 CLI 占位 factory rag) |
| 市场价值 | **中** — 企业知识库/代码库问答;但竞争激烈(已有成熟产品) |
| 独立产品可能性 | **中** — 需先实现基础 RAG 才能谈产品;差异化在"项目生命周期知识"(Idea→Artifact 全过程)而非通用 RAG |
| 当前技术债 | 完全未实现(占位) |
| 独立化第一步 | S10-027 不做;建议后续:文档索引 → 检索 API → 前端 |

## 4. Agent Lifecycle → Agent Management Platform

| 维度 | 分析 |
|---|---|
| 模块定位 | Agent 注册/技能绑定/生命周期(org Employee + exec Agent 双模型) |
| 市场价值 | **中高** — Agent 治理/编排平台;但 LangGraph/CrewAI 竞争 |
| 独立产品可能性 | **中高** — 差异化在"治理驱动"(Skill 权限链/审批)而非编排 |
| 当前技术债 | ① Agent 双模型(org Employee vs exec Agent 系统映射 hack)② provider 装配依赖 console 层(职责倒挂)③ 前端执行触发未接 |
| 独立化第一步 | 单 Agent 模型统一 → provider 装配下沉 exec → UI 执行触发 |

## 5. 其他模块

| 模块 | 市场价值 | 独立可能性 | 技术债 | 优先级 |
|---|---|---|---|---|
| Control Plane | 中高 | 高(边界最清晰) | 低 | 随 Router 一起 |
| Model Catalog | 中 | 中高 | ModelChoice 归属 | 随 Router 一起 |
| Execution | 中 | 中 | provider 装配倒挂 | 低 |
| Skill 市场 | 中高 | 中高 | 权限链硬编码 | 中 |

## 6. 独立产品机会排序(最终)

| 排序 | 产品 | 依据 |
|---|---|---|
| 1 | **AI Decision Router** | 市场刚需 + 现有实现最完整 + 可解释性差异化;独立成本最低 |
| 2 | **AI Governance OS** | 企业可控性刚需;审批/审计已有基础;策略引擎是关键缺口 |
| 3 | **Agent Management Platform** | Agent 治理定位清晰;但竞争激烈,需先解双模型债 |
| 4 | **Enterprise Knowledge Engine** | 市场大但竞争激烈;当前 RAG 未实现,投入产出待评估 |

## 7. 战略建议

1. **洋葱式开源与产品化并行**(用户既有战略):先独立 Router/Control Plane(洋葱最外层),开源获客 + 验证市场
2. **技术债优先级**:ModelChoice 共享类型 → Agent 单模型 → 策略引擎 → usage 接 Router(智能路由前置)
3. **不扩范围**:S10-027 只做审计与准备,不实现任何独立化(Sprint 约束)

---

> 路线图完毕 | 战略设计 | 独立化执行留待后续 Sprint
