# AI Factory 总体规划 v3（2026-08-20）

> 定位: AI Company OS（数字企业运行模型）—— 创建、管理、运行、进化 AI 公司的操作系统。
> 一句话: LangChain 造 AI 员工, LangGraph 编排 AI 工作流, **AI Software Factory 建立和管理整个 AI 生产组织**。
> AI Factory 是"造专家的工厂"，不是某一个专家。
> 领域智能公式: **Skill + MCP + Knowledge + Workflow + Evaluation + Learning = 领域智能产业**。
> 铁律: 任何外部工具都不是完成任务的前提（增强层）。自我提升但必须可控。

---

# 0. 愿景与总体架构

## 0.1 产品形态：一个内核，四个入口

```
内核 = Agent 循环（读仓库→改→测→修）+ 多 Agent 编排 + 工具层（Skill/MCP）
  ├─ ① 终端代理 (CLI)     已有壳, 缺内核深度
  ├─ ② 想法→产品 (Web)    React 壳+FastAPI 已有, 缺内核打通
  ├─ ③ 编辑器内助手 (IDE)  新皮 (MCP/LSP), 薄
  └─ ④ 全自动 agent (沙箱) 复用 ExecutionLoop+沙箱, 薄
策略: 80% 做内核, 20% 包皮。顺序: 内核 → ①CLI → ②Web → ③IDE → ④沙箱。
```

## 0.2 分层架构

```
┌── 入口层 ──────────────────────────────────────────────┐
│ CLI (factory) · Web (React) · API (FastAPI) · IDE(MCP) │
├── 会话/编排层 ──────────────────────────────────────────┤
│ InteractiveSession · Orchestrator · HandoffBus ·       │
│ ChangeControl · ExpertFactory · FactorySpec           │
├── 员工层 (Agent) ───────────────────────────────────────┤
│ AgentEntity/Registry · DeveloperAgent · ExecutionLoop │
│ 多 LLM 路由 (planner/executor/reviewer)               │
├── 能力层 ───────────────────────────────────────────────┤
│ Skill · MCP · Knowledge · Workflow · Evaluation ·     │
│ Learning(画像/经验)                                    │
├── 治理层 ───────────────────────────────────────────────┤
│ ReviewGate(审批) · Budget · Audit · Permission         │
└── 存储/观测层 ──────────────────────────────────────────┘
│ projects/ · artifacts/ · agents/ · experience/ ·       │
│ factory_specs/ · audit · exec timeline                 │
```

---

# 1. 业务流（用户视角）

## BF-1 初始化与看门
```
factory init → doctor --fix → status
用户首次: 配置 provider / 工具发现 / 模型种子 → 全绿
```
## BF-2 定义行业工厂（一次，可复用）
```
factory factory new <industry> --spec 或交互引导
→ 生成 FactorySpec {employees, capabilities, workflows, governance, assets}
→ 预置 IT 工厂; 第二行业用同一底座复制
```
## BF-3 装配专家（"造专家"）
```
factory expert build --role PM --industry it --skills "..." 
→ ExpertFactory.assemble → AgentEntity (校验 skill/workflow/knowledge)
factory expert list
```
## BF-4 跑任务（三条子流）
```
4a 想法→交付: 我想做X → Discovery → 专家交接 → PRD → 审批 → 工程 → 执行 → 交付
4b 存量仓库:  factory repo ~/app "加导出" → 理解→计划→审批→改→测→修
4c 自主任务:  factory run --target "..." (沙箱, 长任务, 审批关键点)
```
## BF-5 审批与治理
```
PRD/计划/变更/关键执行 → ReviewGate → 用户批准/驳回 → 记录审计
```
## BF-6 查看与迭代
```
factory project status / exec history / artifact show
执行中需求变更 → factory change propose "加个导出" → 审批 → PRD v2 → 继续
```
## BF-7 自我提升（跨任务）
```
任务完成 → 经验采集 → 画像更新 → 下次决策引用 (开关可控)
```

---

# 2. 数据流

## DF-1 想法 → 资产链（主数据流）
```
ProductIntent
 → discovery.md(v1)          [artifact]
 → product/market/competitive/ux/architecture/test_plan/prd(v1..n)
    每份: {id,type,version,parent_artifact,created_by(agent_id),status,content_ref,event_id}
 → engineering.json / tasks.json / execution_plan.json
 → execution_state.json (每任务: id/agent/status/error/code_files)
 → delivery: 代码文件 + pytest 报告
 → exec timeline (时间/角色/工具/模型/token/cost)
```
## DF-2 专家画像流（学习闭环）
```
execution/evaluation 事件 → Experience{task,result,tools,cost,failure} 
 → AgentProfile{success_rate,quality,cost,speed,samples}
 → 下次决策检索注入 (带 source) → 回写
护栏: 样本<5 不计权 / 学习开关 / 预算上限
```
## DF-3 FactorySpec 流（行业复制）
```
IT 工厂实例 → 提取 FactorySpec → 自举验证(重新生成等价)
 → factory factory new <industry> → 第二实例 (换 Skill/Knowledge/Workflow)
```

## 2.5 核心数据模型（落盘 JSON）
| 模型 | 关键字段 | 存储 |
|---|---|---|
| AgentEntity | id/role/industry/provider/skills/knowledge_ref/workflow_ref/eval_ref/profile | agents/ |
| FactorySpec | employees/capabilities/workflows/governance/assets | factory_specs/ |
| Artifact | id/type/version/parent_artifact/created_by/status/content_ref/event_id | artifacts/<slug>/<type>/v<n>/ |
| ProductIntent | name/problem/user/platform/core_features/status/raw | projects/<slug>/product.json |
| ChangeProposal | source/what/why/affected_artifacts/affected_tasks/status | projects/<slug>/changes.json |
| Experience | task/result/tools/cost/duration/failure/decision_ctx | experience/ |
| AgentProfile | agent_id/success_rate/quality/cost/speed/samples | agents/<id>/profile.json |

---

# 3. 功能流（功能模块地图 + 依赖）

```
入口: CLI │ Web │ API │ IDE
  ▼
会话/编排: session · orchestrator · handoff_bus · change_control · expert_factory · factory_spec
  ▼
Agent: agent_entity · agent_registry · developer_agent(复用 exec) · execution_loop(复用) · model_routing
  ▼
能力: skill_registry · mcp_client(真连接) · knowledge_store · workflow_engine · evaluator · learning(经验/画像)
  ▼
治理: review_gate · budget · audit · permission
  ▼
存储/观测: artifact_registry · project_store · experience_store · exec_timeline · audit_store
```

**功能依赖（谁需要谁就绪）**
```
内核切片(agent循环+工具) ← 所有入口依赖
专家装配器 ← 依赖 skill/workflow/knowledge 就绪
HandoffBus ← 依赖 AgentEntity
需求变更 ← 依赖 artifact 版本化 + ReplanningEngine
学习闭环 ← 依赖 experience store + evaluator
FactorySpec ← 依赖 IT 工厂实例化完成
```

---

# 4. CLI 设计（命令树）

```
factory
├── init | doctor [--fix] | status | start | stop | version
├── project list | status | rename <id> <name> | create
├── agent list | show <id> | eval <id>          # 员工管理
├── expert build|list|rm                        # 造专家
├── factory new <industry> | spec show <id>     # 行业工厂
├── repo <path> "<目标>"                        # 存量仓库模式
├── product pipeline|analyze|prd|artifact show  # 产品管线
├── change propose <"..."> | list              # 需求变更
├── tools list|doctor|enable|disable            # 工具层
├── mcp list|add|connect|call                   # MCP 管理
├── exec history|status                         # 执行/观测
└── memory search|stats                         # 学习/经验
```

---

# 5. API 设计（REST, FastAPI）

```
/api/v1
  POST /agents                    创建专家 (AgentEntity)
  GET  /agents | /agents/{id} | /agents/{id}/profile
  POST /factories                 实例化行业工厂 (FactorySpec)
  GET  /factories/{id} | /factories/{id}/spec
  POST /tasks                     跑任务 (idea|repo|autonomous)
  GET  /tasks/{id} | GET /tasks/{id}/events (SSE)
  GET  /projects/{id}/artifacts | /timeline | /status
  POST /approvals                 审批 (ReviewGate)
  GET  /tools | POST /tools/{name}/call
  GET  /memory/experience | /memory/agents
  GET  /health | /version
```

---

# 6. 内核模块布局（新建文件）

```
factory-console/session/
  agent_entity.py      AgentEntity + AgentProfile 模型
  agent_registry.py    工厂层专家注册/持久化
  expert_factory.py    专家装配器 (Skill+Knowledge+Workflow→Agent)
  handoff_bus.py       多 Agent 交接/共识/冲突
  model_routing.py     planner/executor/reviewer 多 LLM 路由
  change_control.py    需求变更回流
  repo_mode.py         存量仓库模式 (理解→计划→改→测→修)
  prd_deep.py          深度 PRD (LLM, schema 校验)
  engineering_deep.py  工程计划深度化
  learning.py          经验采集/画像/决策引用/护栏
  factory_spec.py      FactorySpec 模型 + 实例化
  tools.py             工具发现/注册 (MCP+AI CLI 委托)
  mcp_std_client.py    真实 MCP stdio 客户端 (替换 Mock)
  knowledge.py         知识库
factory-console/cli_repo.py     factory repo 命令
factory-console/cli_agent.py    agent/expert/factory 命令
```

---

# 7. 分阶段里程碑（版本 + 验收）

| 里程碑 | 版本 | 内容 | 验收（可演示） |
|---|---|---|---|
| M1 内核切片 | v1.1.5 | repo_mode + tools(发现/MCP真连) + 执行循环接线 | `factory repo` 对现有仓库改一个文件 + 测试绿 |
| M2 员工内核 | v1.1.6 | A1-A6: AgentEntity/Registry/装配器/HandoffBus/7角色/多LLM | `让PM分析` 走真 Agent 链, 资产互引 |
| M3 IT 工厂深度 | v1.1.7~1.1.8 | B1-B5: PRD深度/需求变更/审批/repo深度/工程深度 | 执行中"加导出"→PRD v2+新任务; 仓库修改+测试绿 |
| M4 自我提升 | v1.1.9 | C1-C5: 经验/画像/决策引用/评价回写/护栏 | 第二次同类任务引用第一次经验 |
| M5 真实E2E+模板 | v1.2.0 | D1-D3 + Web 入口打通 | 一句话→专家→PRD→工程→代码→pytest绿→历史可查; FactorySpec 自举 |
| M6 第二行业 | v1.2.x | E1-E3 | 同一底座第二行业最小闭环 |
| M7 入口扩展 | v1.3.x | ③IDE 插件 + ④自主沙箱 | IDE 内调用内核; 沙箱长任务自主完成 |

---

# 8. 后期拓展（扩展点）

| 扩展点 | 机制 | 例子 |
|---|---|---|
| 新行业 | FactorySpec 模板 | 运维/电商/自媒体/数据/办公 |
| 新入口 | 薄皮包内核 | IDE(LSP/MCP)、移动端、桌面(Tauri 已有) |
| 新工具 | MCP/skill 注册 | git/bash/file/search + 本机 AI CLI(增强) |
| 新模型 | provider 路由 | planner/executor/reviewer 分工, 多模型降级 |
| 多租户/团队 | agents/ 命名空间 + 权限 | 一个 OS 管多家"公司" |
| 领域知识 | knowledge_store | 行业文档/规则检索挂载专家 |

---

# 9. 维护（运行/升级/回滚/质量）

## 9.1 运行与监控
```
factory status (端口/进程/LLM/工具)
factory exec history (时间/角色/工具/模型/成本)
factory audit (审计链)
```
## 9.2 升级
- 版本: 语义化 (patch+1 每里程碑, minor 大功能, major 重构)
- 数据迁移: artifact/agents/factory_specs 版本化, 升级不破坏旧数据
## 9.3 回滚
- 项目级: git 快照 (S10-085 规划)
- 数据级: artifact v+n 旧版本保留, 可回退
## 9.4 质量
- 单元/回归: tests/console 全绿 (基线 11784)
- 真实 E2E: 每个里程碑在用户环境跑锚点场景 (唯一验收标准)
- 环境类失败: factory_runtime/llm 沙箱限制 — 真实环境验证
## 9.5 文档
- 每个模块 docstring + docs/ 设计文档 + CHANGELOG

---

# 10. 风险与护栏

| 风险 | 护栏 |
|---|---|
| LLM 幻觉 (PRD/计划) | 字段锚定, schema 校验, 模板兜底 |
| 多 Agent 成本 | 预算护栏 (budget.py), 并行控制 |
| 变更风暴 | 变更合并/上限, 审批 |
| 学习失控 | 学习开关, 样本可信度, 回滚 |
| 工具安全 | 权限门, 沙箱, TOOL_CALL 审计 |
| 计划漂移 | 每里程碑以"真实可演示"验收, 不造壳 |

---

**每里程碑独立提交、独立验收；以"真实可演示结果"为准。**
