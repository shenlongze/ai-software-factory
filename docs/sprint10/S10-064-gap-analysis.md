# S10-064 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-064 | P0 现状审查
> 战略: 从 BUILD THE FACTORY → USE THE FACTORY
> 目标: 不了解内部实现的用户, 从"我想做一个软件"→ 清晰交互 → AI Factory 自主生产 → 交付

---

## 核心问题: 用户能否"从想法到交付"无内部知识完成?

### 现状 (S10-055~063 已具备)

| 能力 | 位置 | 状态 |
|---|---|---|
| 分步命令 | actions.py: create_product/generate_prd/prepare_project/execute_project/project_progress/accept_project | ✅ |
| 意图路由 | intent.py: "我想开发一个X" → create_product | ✅ |
| 产品创建后引导 | conversation.py P6: "是否生成工程计划?" | ✅ |
| 进度查询 | project_progress: "项目进度/执行到哪了" | ✅ |
| 验收 | accept_project: "通过验收" → DELIVERED | ✅ |
| 治理 | S10-063: budget/review/status/budget CLI | ✅ |

### 缺失 (USE THE FACTORY 的 blocker)

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **端到端引导流程** | 用户需手动输入 5+ 命令 (创建→PRD→准备→执行→验收), 无一体化流程 |
| G2 | **一键"开始生产"** | 无单个意图把 create→prd→prepare→execute 串起来 |
| G3 | **实时生产进度反馈** | 执行中无流式/实时进度通知 (只有执行后查询) |
| G4 | **遇到问题的交互** | 失败/治理停止时无"AI 自主处理/必要时请求用户"的引导 |
| G5 | **产品化引导 (onboarding)** | 首次使用无"我能做什么"引导 |
| G6 | **生产进度视图** | 无友好汇总 (完成/进行中/待办/问题/成本) |
| G7 | **交付体验** | DELIVERED 后无"交付摘要" (产物/路径/成本/下一步) |

### 复用 (不重建)

| 能力 | 复用方式 |
|---|---|
| create_product/generate_prd/prepare_project/execute_project | 编排为端到端流程 (薄调, 不复制业务) |
| project_progress | 进度反馈基础 |
| accept_project | 交付终点 |
| conversation.py 引导 | 扩展为全流程引导 |
| governance (S10-063) | 遇到问题时请求用户 (review) |

### 架构方向

```
新增: session/guided_flow.py — 端到端引导编排 (不复制业务, 薄调现有 action)
      intent 路由: "开始生产"/"开始做"/"帮我做" → guided flow
      flow 状态: idea → clarifying → product → engineering → executing → review → delivered
修改: conversation.py 引导增强
      project_progress 增强 (实时进度 + 问题 + 成本)
测试: test_session_guided_flow.py (>=80)

用户视角:
  我想做一个软件 → AI 理解需求 → 继续询问/澄清 → 产品定义
  → 开始生产 → AI Team 工作中 (实时进度) → 遇到问题 (AI 自主/请求用户)
  → 完成 → 交付软件 (摘要)
```

### 不该现在做 🚫

- 不增加 Agent 决策/Replanning/GapAnalyzer 规则 (除非 GAP 证明是 blocker)
- 不做 UI 大改 (CLI/会话交互优先)
- 不重建 orchestration 内部

---

> GAP 完毕 | G1-G7 缺失 | 复用充分 | 核心: 引导式端到端体验
