# AI Software Factory — Phase 5A: Production Example Layer

> 日期: 2026-08-06
> 前置: Phase 1-4C-4 (1203 tests, 77ea59e)
> 目标: 用 Factory 管理真实项目 — 第一个 Example: MarkPad

## 范围

- examples/markpad/ (project.yaml/agents.yaml/skills.yaml/workflows.yaml/README.md)
- Project Definition (名称/语言/仓库路径/技术栈)
- Agent Mapping (flutter developer/tester/architect)
- Workflow Mapping (feature/bug-fix/release)
- CLI: factory project list / factory project show markpad
- 验证: 真实 MarkPad bug fix 任务 → workflow run --auto 完整链路 (Task→Workflow→Assignment→Execution→Hermes→Validation→Dashboard)

## 禁止

修改 Hermes / factory-core 核心逻辑 / 新增数据库 / 新增 Web
