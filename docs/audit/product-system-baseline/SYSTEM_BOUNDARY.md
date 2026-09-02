# SYSTEM BOUNDARY — STEP 9 (2026-09-02)
> 什么属于哪一层 (package 职责 = 实际证据, 非名称)

```
AI Factory 系统边界
│
├── Core (生产核, 运行时加载)
│   ├── factory-console  — Web/会话/执行编排入口 (uvicorn 8011, 371 API)
│   └── factory-org      — 领域 SSOT (projects/backlog/management, console 69 import)
│
├── Agent Runtime (执行层, 深度集成)
│   └── factory-exec     — 员工执行器 (console 79 引用; records 100; 独立 CLI)
│
├── Control Plane (未闭环)
│   ├── llm_router/llm_gateway (console 内) — 调用真实, 选择未接
│   └── external_executor router — Agent 选择真实 (生产)
│
├── Product Intelligence (部分)
│   ├── product_intelligence / discovery_intelligence (console session)
│   └── PRD 域 — ABSENT
│
├── 独立模块 (意图独立 — 原则 P-MOD-01 支撑, 生产职责 UNKNOWN)
│   ├── factory-core     — 独立 Factory OS (CLI+测试+ADR 完整, 全仓消费 0)
│   └── factory-runtime  — runtime 管理器 (无运行痕迹)
│
├── 外部系统 (增强层非依赖 — 方案书 L60)
│   ├── LLM providers (deepseek 等)
│   ├── 外部 Agent CLI (claude/codex — external adapters)
│   └── 工具 (skill/MCP — 非必要条件)
│
└── UI/CLI (接入层)
    ├── WebUI (5180 vite) — View (不拥有事实)
    ├── CLI (console/core/exec/runtime 4 条)
    └── Desktop — 空
```
