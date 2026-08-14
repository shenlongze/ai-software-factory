# S10-046 Task 001 — CLI Current Architecture Audit

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 只读审计, 未修改代码
> 目标: 分析当前 CLI 架构, 为重新设计提供基线

---

## 1. 当前 CLI 命令树

```
factory (入口: factory-console/cli_factory.py, 2519 行, argparse)
├── init          — 首次初始化 (环境检测 + workspace + Provider 引导)
├── doctor        — 诊断 (环境/Provider/模型/Runtime/Router)
├── config        — 运行时配置 (show/set/check/path)
├── start/stop/status — 服务管理
├── service       — 服务注册表管理
├── project       — create (代理 org CLI) / list (只读)
├── run           — 执行任务 (薄代理 exec CLI; --project 必填, --task|--objective 之一)
├── run-status    — 结果查询 (薄代理 exec CLI)
├── demo          — init/status/reset/start/run (隔离演示环境)
├── agent         — Agent 管理骨架 (只读)
├── skill         — Skill 管理骨架 (只读)
├── task          — Task 管理骨架 (只读)
├── router        — Router 管理骨架 (只读: 决策链可用性)
├── rag           — RAG 占位
└── audit         — 审计查询骨架 (只读)
```

## 2. 已有能力映射

| CLI 命令 | 服务层 | 实现方式 |
|---|---|---|
| factory run | Execution Service (exec.cli.cmd_exec_run) | 薄代理 |
| factory run-status | Execution Service (cmd_exec_status) | 薄代理 |
| factory project create | Project Service (org.cli.cmd_project_register) | 薄代理 |
| factory project list | Project Service (projects.json 只读) | 本地读 |
| factory demo run | Execution + Project + Workspace | 编排 (复用现有) |
| factory init | ControlPlane (providers.json) | 本地逻辑 |
| factory doctor | Doctor Framework (检查注册表) | 本地逻辑 |
| factory config | Config System (config.json 白名单) | 本地逻辑 |
| factory router | Router (决策链可用性) | 只读展示 |
| factory agent/skill/task | Registry (agents.json/skills.json/tasks) | 只读展示 |
| factory audit | Events DB (事件库) | 只读查询 |

**核心模式: 薄代理 + 本地逻辑 + 只读展示, 服务层在 exec/org/ControlPlane。**

## 3. 当前用户体验问题

| # | 问题 | 严重度 | 说明 |
|---|---|---|---|
| U1 | **概念门槛高** | 高 | 用户需理解 project/task/agent/skill/provider/router |
| U2 | **命令工具而非会话** | 中 | 每条命令独立, 无上下文/会话 |
| U3 | **状态需手动追踪** | 中 | current project/agent 无记忆 |
| U4 | **自然语言不可用** | 中 | 只能 structured 命令, 不能 "帮我做 X" |
| U5 | **结果展示平铺** | 低 | 无 diff/进度/成本渲染 |
| U6 | **无补全** | 低 | 无 TAB 补全 (项目/agent/provider) |

## 4. 未来改造目标

| 目标 | 方向 |
|---|---|
| 降低学习成本 | 交互模式 + 自然语言入口 (Intent Layer) |
| 上下文保持 | Session Context (current project/agent) |
| 高效操作 | Slash Command (交互内快捷) |
| 专业体验 | 补全 + 渲染 (diff/进度/cost) |
| 架构稳定 | **一个 CLI 两种模式, 共享 Service Layer, 禁止第二套执行系统** |

## 5. 架构基线(设计依据)

```
factory (单一入口)
  ├── Command Mode (factory xxx — 现有 17+ 命令, 保留兼容)
  └── Interactive Session (factory — 未来, 共享 Service Layer)
        ├── Slash Command (/project /run ... → 同一服务)
        ├── Intent Layer (自然语言 → Intent Object → Policy → Workflow → Service)
        └── Session Context (current project/agent/provider/recent)
```

**原则: 不创建第二套执行系统 — 所有新入口最终都落到现有 Service Layer。**

---

> Task 001 完毕 | 基线: 17+ 命令/2519 行/薄代理模式 | 问题: 概念门槛高+无会话 | 目标: 一 CLI 两模式
