# S10-051 — AI Software Factory Pipeline

> 日期:2026-08-15 | Sprint: S10-051 | 架构 + 流程 + 验证
> 状态: 实现完成, 真实 Pipeline 验证通过

---

## 1. 完整生命周期

```
User Idea ("我想开发一个台球比赛计分APP")
    ↓
ProductIntent (DISCOVERY 多轮: problem/user/core_features)
    ↓
create_product → projects/<slug>/product.json (status: project_created)
    ↓
prepare_project (确认后)
    ├─ PRD.md              (ProductDocument: 6 节)
    ├─ engineering.json    (architecture/modules/technical_tasks)
    ├─ tasks.json          (Epic/Task/Priority/Agent Type)
    ├─ execution_plan.json (task → agent, 复用 select_agent)
    └─ project.json        (status: execution_ready)
    ↓
"Project Ready For Engineering."
    ↓
(未来) Agent Execution → Development → Testing → Delivered
```

## 2. 生成资产(projects/<slug>/)

| 文件 | 内容 | 生成器 |
|---|---|---|
| product.json | ProductIntent | create_product (S10-050) |
| PRD.md | Product Overview/Problem/Target User/Core Features/Usage Scenario/Future Direction | ProductDocument |
| engineering.json | architecture (platform 推导) + modules + technical_tasks | EngineeringPlan |
| tasks.json | 12 任务 (3 Epic × 4: database/backend/frontend/test, P0/P1) | TaskTree |
| execution_plan.json | task_id → agent (backend→backend-1/frontend→flutter-dev) | AgentAssignment |
| project.json | Lifecycle status (execution_ready) | prepare_project |

## 3. 真实验证(2026-08-15, 隔离 HOME)

```
> 我想开发一个台球比赛计分APP
> (追问 problem/user/core_features)
> 确认创建? → y → (product.json 落盘)
> 准备开发 → 确认 → ✔ Project Ready For Engineering.

落盘验证:
  PRD.md: 6 节完整 ✅
  engineering.json: architecture="Backend API + Frontend", modules=[计分,比赛记录,排行榜] ✅
  tasks.json: 12 任务 (P0/P1, backend/frontend/qa) ✅
  execution_plan.json: backend→backend-1, frontend→flutter-dev ✅
```

## 4. 模块

| 模块 | 职责 | 状态 |
|---|---|---|
| pipeline.py | ProductDocument/EngineeringPlan/TaskTree/AgentAssignment/Lifecycle (纯规则) | ✅ |
| intent.py | +generate_prd +prepare_project 关键词 | ✅ |
| actions.py | +generate_prd +prepare_project (资产落盘) | ✅ |
| router.py | 映射 | ✅ |
| conversation.py | 产品创建后引导 "是否生成工程计划?" | ✅ |

## 5. 测试

```
新增: test_session_pipeline.py 100 测试
覆盖: PRD 生成/落盘/EngineeringPlan/TaskTree/AgentAssignment/Lifecycle/prepare_project/确认/完整 Demo/回归
全量: (验证中, 基线 8480 → 期望 8580)
```

## 6. AI Factory vs 普通 Agent Framework

| 维度 | 普通 Agent Framework | AI Factory |
|---|---|---|
| 入口 | 开发者写代码编排 | 用户表达想法 (自然语言) |
| 产品层 | 无 | ProductIntent + PRD (产品资产) |
| 工程层 | 无 | EngineeringPlan + TaskTree (工程资产) |
| 执行层 | Agent 编排 | Agent 执行 (复用 S10-049) |
| 产出 | 代码 | 产品资产 + 工程资产 + 执行记录 (可审计) |

**AI Factory 不是"让 Agent 干活" — 是"从想法到交付的完整软件工厂流水线"。**

## 7. 未来扩展

```
LLM Planning:  EngineeringPlan/TaskTree 规则生成 → LLM 生成 (接口已定型)
PRD 深化:      ProductDocument → LLM 增强 (使用场景/验收标准)
Execution:     execution_plan.json → 自动 run_task (S10-049 execute_task)
Lifecycle:     DEVELOPMENT/TESTING/DELIVERED 状态推进
```

## 8. 边界

- 规则生成(不调 LLM, 未来可替换为 LLM Planning)
- 输出全部落盘为项目资产(非打印)
- 复用 ProductIntent/select_agent/ActionRegistry/Router
- Core 零改动

---

> S10-051 文档完毕 | Software Factory Pipeline 落地 | 100 新测试 | 真实 Pipeline 验证通过
