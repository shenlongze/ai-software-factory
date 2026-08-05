# AI Software Factory — Vision

> 版本: v1.0 | 日期: 2026-08-05

## 愿景

建设 AI 时代的软件生产操作系统——一个能够**管理 AI 员工、组织软件生产流程、连接各种 Agent Runtime** 的 AI 软件生产平台。

## 定位

```
AI Software Factory = AI 软件生产操作系统

不是聊天机器人
不是单个 Agent
不是代码生成工具
```

对应传统软件体系：

| 传统 | AI Software Factory |
|:-----|:--------------------|
| Jira | Task Management |
| Jenkins | Workflow Engine |
| K8s Dashboard | Agent Management + Dashboard |
| Confluence | Knowledge System |
| CI/CD | Validation System |

## 核心价值

1. **可管理** — 管理 AI 员工（Agent）的生命周期、职责、可靠性
2. **可观察** — 任何时刻知道 AI 员工在做什么、进度、阻塞（Event 唯一事实源）
3. **可验证** — Agent 自报告 ≠ 完成，Validation 结果 = 事实
4. **可积累** — 知识沉淀（架构决策/缺陷/经验 = 企业资产）
5. **可扩展** — 不绑定任何 Agent 框架，可替换 Runtime（Hermes/LangGraph/CrewAI/OpenHands...）
6. **可复制** — 一套平台支持多项目（MarkPad/Java/Flutter/SaaS/企业软件）

## 用户

- **工程师** — CLI 主入口，创建任务、跑流程、看状态
- **技术负责人** — Dashboard 观察工厂运行、Agent 健康、质量指标
- **管理层** — 项目进度、风险、交付质量总览

## 成功标准

- 一个任务从创建到交付全程可观察、可恢复、可验证
- 多项目并行生产，知识跨项目复用
- 新 Agent Runtime / 新角色 / 新 Skill 声明式接入（零代码）
- 自动化指标达标：first_attempt_success > 95%、path_errors = 0、human_intervention 最小化
