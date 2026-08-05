# AI Software Factory

> AI 软件生产操作系统 — 管理 AI 员工、组织软件生产流程、连接各种 Agent Runtime 的平台。

## 定位

AI Software Factory 不是一个聊天机器人，不是单个 Agent，不是代码生成工具。它是 AI 时代软件生产的操作系统：

```
传统软件体系                     AI Software Factory
-----------                     -------------------
Jira           →  Task Management
Jenkins        →  Workflow Engine
K8s Dashboard  →  Agent Management + Dashboard
Confluence     →  Knowledge System
CI/CD          →  Validation System
```

## 核心原则

1. 不绑定单一模型 / Agent 框架（Hermes / Claude Code / LangGraph / CrewAI / OpenHands 只作为 Runtime 执行器）
2. 所有状态必须可观察（Event Logger = 唯一事实来源）
3. 所有执行必须产生 Event
4. 所有完成必须经过 Validation（Agent 自报告 ≠ 完成）
5. 所有知识必须可沉淀（错误 = 工程资产）
6. 支持未来多项目（MarkPad / Java / Flutter / SaaS / 企业软件）

## 产品入口

| 入口 | 优先级 | 说明 |
|:-----|:------:|:-----|
| CLI | P0 | `factory init / task create / workflow run / logs` 等，工程师主入口 |
| Dashboard | P1 | CLI Dashboard / Markdown Dashboard，观察运行状态 |
| API | P2 | 未来自动化触发（GitHub Issue → Factory API → 任务 → Workflow） |

## 目录结构

```
ai-software-factory/
├── docs/              设计文档 (design/ = 从 MarkPad 实践抽象的设计稿)
├── factory-core/      核心 (Task Manager / Workflow Engine / Event Logger ...)
├── cli/               CLI 入口 (Typer)
├── dashboard/         Dashboard (Rich / Markdown)
├── api/               API 入口 (FastAPI, 未来)
├── agents/            Agent 注册表 / 角色定义
├── skills/            Skill 库 (独立于 Agent)
├── workflows/         Workflow 定义 (Feature / Bug / Release)
├── mcp/               MCP Manager (工具连接)
├── knowledge/         知识系统 (Architecture / Decision / Bug / Experience)
├── validation/        Validation Engine (规则 / Gate / Evidence)
└── runtimes/          Runtime Adapter (Hermes / LangGraph / ...)
```

## 技术栈（第一版）

Python 3.12+ / Pydantic / SQLite / Typer / Rich / FastAPI（不做微服务 / K8s / 复杂前端）

## 状态

Phase 0 — 项目初始化（骨架 + 设计稿就位，待架构确认）
