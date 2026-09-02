# PROJECT STATE TREE — STEP 9 (2026-09-02)
> 所有 AI 进入项目的第一入口

```
AI FACTORY (v1.1.364)
│
├── REAL / CLOSED (M4 — 生产闭环, 有 E2E+持久化+审计证据)
│   ├── Session / Intent / Planning / Task Mgmt / Dependency / Execution
│   ├── Cancellation / Aggregation / Audit / LLM Invocation / Project Mgmt
│   └── 证据: 多轮 E2E + 1049+ 测试 + session_exec 6 + audit 5160
│
├── REAL / PRODUCTION (M3 — 生产运行)
│   ├── Agent Selection / Agent Execution (records 100)
│   ├── Recovery / Governance / Tool / WebUI / CLI
│   └── 证据: execution_records / recover E2E / 浏览器 E2E
│
├── REAL / INTEGRATED NOT CLOSED (M2)
│   ├── Requirement Persistence (无下游)
│   ├── Verification (无独立下游)
│   └── Artifact (exec 域, 会话链无关联)
│
├── IMPLEMENTED / NOT PRODUCTION (M1)
│   ├── Model Selection (LLMRouter 消费 0)
│   ├── Skill / Discovery / Experience(写)
│   └── Product Intelligence 分析 (不落盘)
│
├── ABSENT (M0)
│   ├── Requirement Traceability / PRD Entity / Model Fallback
│   └── 会话链 Replan / Learning 闭环 / Release 闭环
│
├── FUTURE (产品自标 M3/M4 🚧📐)
│   ├── Replan+需求变更回流 (M3) / PRD 深度化 (M3)
│   ├── Experience→Learning (M4) / Release (M3/M4)
│   └── 备注: 不视为当前缺陷
│
└── UNKNOWN
    ├── factory-core 生产职责 / factory-runtime 生产职责 / factory.db 用途
    ├── exec 角色 Agent 触发入口 / Release-Learning 运行时
    ├── Verification downstream contract / 371 API 未触发部分
    └── WebUI 全量一致性 / 独立模块生产义务
